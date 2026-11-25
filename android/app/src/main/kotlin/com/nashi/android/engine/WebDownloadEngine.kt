package com.nashi.android.engine

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

data class DownloadResult(
    val file: File,
    val mimeType: String
)

object WebDownloadEngine {

    private const val UA = "Mozilla/5.0 (Linux; Android 15; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"

    suspend fun downloadMedia(
        rawUrl: String,
        outDir: File,
        onProgress: (Float) -> Unit
    ): DownloadResult? = withContext(Dispatchers.IO) {
        val urlStr = rawUrl.trim()
        if (!urlStr.startsWith("http://", true) && !urlStr.startsWith("https://", true)) return@withContext null
        try {
            val conn = openConn(urlStr)
            val contentType = (conn.contentType ?: "application/octet-stream").substringBefore(';').trim().lowercase()
            if (contentType.contains("text/html")) {
                val html = conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText().take(250_000) }
                conn.disconnect()
                val direct = extractDirectMediaUrl(html, urlStr) ?: return@withContext null
                return@withContext streamToFile(openConn(direct), direct, outDir, onProgress)
            }
            streamToFile(conn, urlStr, outDir, onProgress)
        } catch (_: Exception) {
            null
        }
    }

    private fun openConn(urlStr: String): HttpURLConnection {
        return (URL(urlStr).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = true
            connectTimeout = 15000
            readTimeout = 30000
            setRequestProperty("User-Agent", UA)
        }
    }

    private fun streamToFile(
        conn: HttpURLConnection,
        urlStr: String,
        outDir: File,
        onProgress: (Float) -> Unit
    ): DownloadResult? {
        return try {
            if (conn.responseCode !in 200..299) return null
            val mime = (conn.contentType ?: "application/octet-stream").substringBefore(';').trim().lowercase()
            val ext = extFromMimeOrUrl(mime, urlStr)
            val outFile = File(outDir, "web_${System.currentTimeMillis()}.$ext")
            val total = conn.contentLengthLong.coerceAtLeast(0L)
            var downloaded = 0L
            conn.inputStream.use { input ->
                FileOutputStream(outFile).use { output ->
                    val buf = ByteArray(16 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n <= 0) break
                        output.write(buf, 0, n)
                        downloaded += n
                        if (total > 0) onProgress((downloaded.toFloat() / total.toFloat()).coerceIn(0f, 1f))
                    }
                }
            }
            onProgress(1f)
            DownloadResult(outFile, mime)
        } catch (_: Exception) {
            null
        } finally {
            conn.disconnect()
        }
    }

    private fun extractDirectMediaUrl(html: String, baseUrl: String): String? {
        val patterns = listOf(
            Regex("""<meta[^>]+property=["']og:video(?::secure_url|:url)?["'][^>]+content=["']([^"']+)["']""", RegexOption.IGNORE_CASE),
            Regex("""<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:video(?::secure_url|:url)?["']""", RegexOption.IGNORE_CASE),
            Regex("""<(?:video|source|audio)[^>]+src=["']([^"']+\.(?:mp4|webm|m4a|mp3|mov)[^"']*)["']""", RegexOption.IGNORE_CASE),
            Regex("""<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']""", RegexOption.IGNORE_CASE),
            Regex("""<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:image["']""", RegexOption.IGNORE_CASE)
        )
        for (p in patterns) {
            val raw = p.find(html)?.groupValues?.getOrNull(1)?.replace("&amp;", "&") ?: continue
            return try { URL(URL(baseUrl), raw).toString() } catch (_: Exception) { raw }
        }
        return null
    }

    private fun extFromMimeOrUrl(mime: String, url: String): String = when {
        mime.contains("jpeg") || mime.contains("jpg") -> "jpg"
        mime.contains("png") -> "png"
        mime.contains("webp") -> "webp"
        mime.contains("gif") -> "gif"
        mime.contains("mp4") -> "mp4"
        mime.contains("webm") -> "webm"
        mime.contains("mpeg") -> "mp3"
        mime.contains("audio/mp4") || mime.contains("aac") -> "m4a"
        mime.contains("pdf") -> "pdf"
        else -> url.substringBefore('?').substringAfterLast('.', "").take(5).ifBlank { "bin" }
    }
}
