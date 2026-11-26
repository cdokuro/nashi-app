package com.nashi.android.engine

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Environment
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec

data class MediaProbeResult(
    val isHls: Boolean,
    val mimeType: String,
    val totalBytes: Long = -1L
)

object HlsDownloadEngine {

    private fun originFrom(referer: String?): String? {
        if (referer.isNullOrBlank()) return null
        return try {
            val u = URL(referer)
            val portPart = if (u.port > 0 && u.port != u.defaultPort) ":${u.port}" else ""
            "${u.protocol}://${u.host}$portPart"
        } catch (_: Exception) {
            null
        }
    }

    /**
     * Probes an unknown/obfuscated URL with a tiny 1 KB Range GET to check if it is
     * actually an HLS playlist (#EXTM3U even on .txt/.png/extensionless URLs) or a real video/audio stream.
     */
    suspend fun probeMediaUrl(
        url: String,
        cookie: String?,
        referer: String?,
        origin: String?,
        userAgent: String?
    ): MediaProbeResult? = withContext(Dispatchers.IO) {
        var conn: HttpURLConnection? = null
        try {
            conn = (URL(url).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = true
                connectTimeout = 4500
                readTimeout = 4500
                requestMethod = "GET"
                setRequestProperty("Range", "bytes=0-1023")
                if (!userAgent.isNullOrBlank()) setRequestProperty("User-Agent", userAgent)
                if (!cookie.isNullOrBlank()) setRequestProperty("Cookie", cookie)
                if (!referer.isNullOrBlank()) setRequestProperty("Referer", referer)
                val effOrigin = origin?.takeIf { it.isNotBlank() } ?: originFrom(referer)
                if (!effOrigin.isNullOrBlank()) setRequestProperty("Origin", effOrigin)
            }
            val code = conn.responseCode
            if (code !in 200..299) return@withContext null

            val ct = (conn.contentType ?: "").lowercase().substringBefore(';').trim()
            val totalBytes = parseTotalSize(conn.getHeaderField("Content-Range"), conn.contentLengthLong)

            // Read up to 1024 bytes to check magic bytes (#EXTM3U / ftyp mp4 / webm)
            val buf = ByteArray(1024)
            val n = try { conn.inputStream.read(buf) } catch (_: Exception) { 0 }
            val headText = if (n > 0) String(buf, 0, n, Charsets.UTF_8).trimStart('\uFEFF', ' ', '\r', '\n') else ""

            if (ct.contains("mpegurl") || headText.startsWith("#EXTM3U")) {
                // Ignore pure segment lists if it's obviously tiny non-media; valid playlists have #EXT-X- or #EXTINF
                if (headText.contains("#EXT-X-") || headText.contains("#EXTINF") || ct.contains("mpegurl")) {
                    return@withContext MediaProbeResult(isHls = true, mimeType = "application/vnd.apple.mpegurl", totalBytes = totalBytes)
                }
            }

            // Detect real MP4/WebM/MKV/audio by Content-Type or ISO BMFF magic bytes ("ftyp")
            val isMp4Magic = n >= 12 && buf[4] == 'f'.code.toByte() && buf[5] == 't'.code.toByte() &&
                buf[6] == 'y'.code.toByte() && buf[7] == 'p'.code.toByte()
            if (ct.startsWith("video/") || isMp4Magic) {
                // Skip tiny ad/poster clips (< 150 KB) when total size is known
                if (totalBytes in 1..150_000) return@withContext null
                val mime = if (ct.startsWith("video/")) ct else "video/mp4"
                return@withContext MediaProbeResult(isHls = false, mimeType = mime, totalBytes = totalBytes)
            }
            if (ct.startsWith("audio/")) {
                if (totalBytes in 1..64_000) return@withContext null
                return@withContext MediaProbeResult(isHls = false, mimeType = ct, totalBytes = totalBytes)
            }
            null
        } catch (_: Exception) {
            null
        } finally {
            try { conn?.disconnect() } catch (_: Exception) {}
        }
    }

    private fun parseTotalSize(contentRange: String?, contentLength: Long): Long {
        if (!contentRange.isNullOrBlank()) {
            val slash = contentRange.lastIndexOf('/')
            if (slash >= 0) {
                val total = contentRange.substring(slash + 1).trim().toLongOrNull()
                if (total != null && total > 0) return total
            }
        }
        return contentLength
    }

    /**
     * Queues a direct video/file URL in Android's native system DownloadManager
     * carrying the WebView's exact Cookie, Referer, Origin, and User-Agent headers.
     */
    fun enqueueDirectDownload(
        context: Context,
        url: String,
        fileName: String,
        mimeType: String,
        cookie: String?,
        referer: String?,
        userAgent: String?,
        origin: String? = null
    ): Long {
        val cleanName = fileName.replace(Regex("[^a-zA-Z0-9._-]"), "_").ifBlank { "nashi_${System.currentTimeMillis()}.mp4" }
        val req = DownloadManager.Request(Uri.parse(url)).apply {
            setTitle(cleanName)
            setDescription("Nashi ile indiriliyor")
            if (mimeType.isNotBlank()) setMimeType(mimeType)
            if (!cookie.isNullOrBlank()) addRequestHeader("Cookie", cookie)
            if (!referer.isNullOrBlank()) addRequestHeader("Referer", referer)
            val effOrigin = origin?.takeIf { it.isNotBlank() } ?: originFrom(referer)
            if (!effOrigin.isNullOrBlank()) addRequestHeader("Origin", effOrigin)
            if (!userAgent.isNullOrBlank()) addRequestHeader("User-Agent", userAgent)
            setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "Nashi/$cleanName")
            setAllowedOverMetered(true)
            setAllowedOverRoaming(true)
        }
        val dm = context.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        return dm.enqueue(req)
    }

    /**
     * Pure-Kotlin HLS (.m3u8 / disguised playlist) downloader supporting:
     * - Master playlists (auto-picks highest bandwidth variant)
     * - AES-128 encrypted segments + #EXT-X-MAP init segments
     * - Fake PNG/GIF header stripping on disguised TS segments (common on streaming CDNs)
     */
    suspend fun downloadHlsToFile(
        m3u8Url: String,
        outFile: File,
        cookie: String?,
        referer: String?,
        userAgent: String?,
        origin: String? = null,
        onProgress: (Float, String) -> Unit
    ): Boolean = withContext(Dispatchers.IO) {
        try {
            val playlistText = fetchText(m3u8Url, cookie, referer, origin, userAgent) ?: return@withContext false
            if (!playlistText.contains("#EXTM3U")) return@withContext false

            val targetUrl = pickBestVariantUrl(m3u8Url, playlistText)
            val mediaText = if (targetUrl != m3u8Url) {
                fetchText(targetUrl, cookie, referer, origin, userAgent) ?: return@withContext false
            } else playlistText

            val lines = mediaText.lines().map { it.trim() }.filter { it.isNotEmpty() }
            val segments = mutableListOf<String>()
            var initMapUrl: String? = null
            var keyUrl: String? = null
            var ivBytes: ByteArray? = null
            var mediaSeq = 0

            for (line in lines) {
                when {
                    line.startsWith("#EXT-X-MEDIA-SEQUENCE:") -> {
                        mediaSeq = line.substringAfter(':').trim().toIntOrNull() ?: 0
                    }
                    line.startsWith("#EXT-X-MAP:") -> {
                        val uriMatch = Regex("""URI="([^"]+)"""").find(line)
                        initMapUrl = uriMatch?.groupValues?.getOrNull(1)?.let { resolveUrl(targetUrl, it) }
                    }
                    line.startsWith("#EXT-X-KEY:") -> {
                        if (line.contains("METHOD=AES-128", ignoreCase = true)) {
                            val uriMatch = Regex("""URI="([^"]+)"""").find(line)
                            keyUrl = uriMatch?.groupValues?.getOrNull(1)?.let { resolveUrl(targetUrl, it) }
                            val ivMatch = Regex("""IV=0x([0-9a-fA-F]+)""").find(line)
                            ivBytes = ivMatch?.groupValues?.getOrNull(1)?.let { hexToBytes(it) }
                        }
                    }
                    !line.startsWith("#") -> {
                        segments.add(resolveUrl(targetUrl, line))
                    }
                }
            }
            if (segments.isEmpty()) return@withContext false

            val aesKey = keyUrl?.let { fetchBytes(it, cookie, referer, origin, userAgent) }
            var totalBytes = 0L
            FileOutputStream(outFile).use { out ->
                if (initMapUrl != null) {
                    val initData = fetchBytes(initMapUrl, cookie, referer, origin, userAgent)
                    if (initData != null) {
                        out.write(initData)
                        totalBytes += initData.size
                    }
                }
                segments.forEachIndexed { idx, segUrl ->
                    val raw = fetchBytes(segUrl, cookie, referer, origin, userAgent) ?: return@forEachIndexed
                    val decrypted = if (aesKey != null && aesKey.size == 16) {
                        decryptAes128(raw, aesKey, ivBytes ?: sequenceIv(mediaSeq + idx))
                    } else raw
                    val clean = stripDisguisedTsHeader(decrypted)
                    out.write(clean)
                    totalBytes += clean.size
                    val pct = (idx + 1).toFloat() / segments.size.toFloat()
                    onProgress(pct, "${idx + 1}/${segments.size} parça · ${String.format("%.1f", totalBytes / (1024.0 * 1024.0))} MB")
                }
            }
            totalBytes > 0L
        } catch (_: Exception) {
            try { outFile.delete() } catch (_: Exception) {}
            false
        }
    }

    /**
     * Some streaming CDNs disguise MPEG-TS segments by prepending a fake PNG/GIF header (8–32 bytes)
     * before the first 0x47 TS sync byte. Strip any leading garbage when two 0x47 sync bytes sit 188 bytes apart.
     */
    private fun stripDisguisedTsHeader(data: ByteArray): ByteArray {
        if (data.size < 376 || data[0] == 0x47.toByte()) return data
        val limit = minOf(64, data.size - 189)
        for (offset in 1..limit) {
            if (data[offset] == 0x47.toByte() && data[offset + 188] == 0x47.toByte()) {
                return data.copyOfRange(offset, data.size)
            }
        }
        return data
    }

    private fun pickBestVariantUrl(baseUrl: String, m3u8: String): String {
        val lines = m3u8.lines().map { it.trim() }
        var bestBw = -1L
        var bestUrl: String? = null
        for (i in lines.indices) {
            if (lines[i].startsWith("#EXT-X-STREAM-INF:")) {
                val bw = Regex("""BANDWIDTH=(\d+)""").find(lines[i])?.groupValues?.getOrNull(1)?.toLongOrNull() ?: 0L
                val next = lines.drop(i + 1).firstOrNull { it.isNotEmpty() && !it.startsWith("#") }
                if (next != null && bw >= bestBw) {
                    bestBw = bw
                    bestUrl = resolveUrl(baseUrl, next)
                }
            }
        }
        return bestUrl ?: baseUrl
    }

    private fun resolveUrl(base: String, rel: String): String = try {
        URL(URL(base), rel).toString()
    } catch (_: Exception) {
        rel
    }

    private fun open(url: String, cookie: String?, referer: String?, origin: String?, ua: String?): HttpURLConnection {
        return (URL(url).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = true
            connectTimeout = 15000
            readTimeout = 30000
            if (!ua.isNullOrBlank()) setRequestProperty("User-Agent", ua)
            if (!cookie.isNullOrBlank()) setRequestProperty("Cookie", cookie)
            if (!referer.isNullOrBlank()) setRequestProperty("Referer", referer)
            val effOrigin = origin?.takeIf { it.isNotBlank() } ?: originFrom(referer)
            if (!effOrigin.isNullOrBlank()) setRequestProperty("Origin", effOrigin)
        }
    }

    private fun fetchText(url: String, cookie: String?, referer: String?, origin: String?, ua: String?): String? {
        val conn = open(url, cookie, referer, origin, ua)
        return try {
            if (conn.responseCode !in 200..299) null else conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }

    private fun fetchBytes(url: String, cookie: String?, referer: String?, origin: String?, ua: String?): ByteArray? {
        val conn = open(url, cookie, referer, origin, ua)
        return try {
            if (conn.responseCode !in 200..299) null else conn.inputStream.use { it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }

    private fun decryptAes128(data: ByteArray, key: ByteArray, iv: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
        cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), IvParameterSpec(iv.copyOf(16)))
        return cipher.doFinal(data)
    }

    private fun sequenceIv(seq: Int): ByteArray {
        val iv = ByteArray(16)
        iv[12] = ((seq shr 24) and 0xFF).toByte()
        iv[13] = ((seq shr 16) and 0xFF).toByte()
        iv[14] = ((seq shr 8) and 0xFF).toByte()
        iv[15] = (seq and 0xFF).toByte()
        return iv
    }

    private fun hexToBytes(hex: String): ByteArray {
        val clean = hex.padStart(32, '0').takeLast(32)
        return ByteArray(16) { i -> clean.substring(i * 2, i * 2 + 2).toInt(16).toByte() }
    }
}
