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

object HlsDownloadEngine {

    /**
     * Queues a direct video/file URL in Android's native system DownloadManager
     * carrying the WebView's exact Cookie, Referer, and User-Agent headers.
     * Supports multi-GB downloads (1.8GB / 4GB movies) cleanly in the background.
     */
    fun enqueueDirectDownload(
        context: Context,
        url: String,
        fileName: String,
        mimeType: String,
        cookie: String?,
        referer: String?,
        userAgent: String?
    ): Long {
        val cleanName = fileName.replace(Regex("[^a-zA-Z0-9._-]"), "_").ifBlank { "nashi_${System.currentTimeMillis()}.mp4" }
        val req = DownloadManager.Request(Uri.parse(url)).apply {
            setTitle(cleanName)
            setDescription("Nashi ile indiriliyor")
            if (mimeType.isNotBlank()) setMimeType(mimeType)
            if (!cookie.isNullOrBlank()) addRequestHeader("Cookie", cookie)
            if (!referer.isNullOrBlank()) addRequestHeader("Referer", referer)
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
     * Pure-Kotlin HLS (.m3u8) downloader supporting master playlists (picks best quality)
     * and AES-128 encrypted segments, carrying exact Cookie/Referer/User-Agent headers.
     */
    suspend fun downloadHlsToFile(
        m3u8Url: String,
        outFile: File,
        cookie: String?,
        referer: String?,
        userAgent: String?,
        onProgress: (Float, String) -> Unit
    ): Boolean = withContext(Dispatchers.IO) {
        try {
            val playlistText = fetchText(m3u8Url, cookie, referer, userAgent) ?: return@withContext false
            val targetUrl = pickBestVariantUrl(m3u8Url, playlistText)
            val mediaText = if (targetUrl != m3u8Url) {
                fetchText(targetUrl, cookie, referer, userAgent) ?: return@withContext false
            } else playlistText

            val lines = mediaText.lines().map { it.trim() }.filter { it.isNotEmpty() }
            val segments = mutableListOf<String>()
            var keyUrl: String? = null
            var ivBytes: ByteArray? = null

            for (line in lines) {
                if (line.startsWith("#EXT-X-KEY:")) {
                    if (line.contains("METHOD=AES-128", ignoreCase = true)) {
                        val uriMatch = Regex("""URI="([^"]+)"""").find(line)
                        keyUrl = uriMatch?.groupValues?.getOrNull(1)?.let { resolveUrl(targetUrl, it) }
                        val ivMatch = Regex("""IV=0x([0-9a-fA-F]+)""").find(line)
                        ivBytes = ivMatch?.groupValues?.getOrNull(1)?.let { hexToBytes(it) }
                    }
                } else if (!line.startsWith("#")) {
                    segments.add(resolveUrl(targetUrl, line))
                }
            }
            if (segments.isEmpty()) return@withContext false

            val aesKey = keyUrl?.let { fetchBytes(it, cookie, referer, userAgent) }
            var totalBytes = 0L
            FileOutputStream(outFile).use { out ->
                segments.forEachIndexed { idx, segUrl ->
                    val raw = fetchBytes(segUrl, cookie, referer, userAgent) ?: return@forEachIndexed
                    val data = if (aesKey != null && aesKey.size == 16) {
                        decryptAes128(raw, aesKey, ivBytes ?: sequenceIv(idx))
                    } else raw
                    out.write(data)
                    totalBytes += data.size
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

    private fun open(url: String, cookie: String?, referer: String?, ua: String?): HttpURLConnection {
        return (URL(url).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = true
            connectTimeout = 15000
            readTimeout = 30000
            if (!ua.isNullOrBlank()) setRequestProperty("User-Agent", ua)
            if (!cookie.isNullOrBlank()) setRequestProperty("Cookie", cookie)
            if (!referer.isNullOrBlank()) setRequestProperty("Referer", referer)
        }
    }

    private fun fetchText(url: String, cookie: String?, referer: String?, ua: String?): String? {
        val conn = open(url, cookie, referer, ua)
        return try {
            if (conn.responseCode !in 200..299) null else conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }

    private fun fetchBytes(url: String, cookie: String?, referer: String?, ua: String?): ByteArray? {
        val conn = open(url, cookie, referer, ua)
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
