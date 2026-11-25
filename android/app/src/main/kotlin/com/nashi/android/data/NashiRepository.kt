package com.nashi.android.data

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import android.provider.OpenableColumns
import androidx.core.content.FileProvider
import com.nashi.android.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

class NashiRepository(private val context: Context) {

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val mutex = Mutex()
    private val storeFile = File(context.filesDir, "nashi_store.json")
    val outputsDir = File(context.filesDir, "outputs").apply { mkdirs() }
    val workDir = File(context.cacheDir, "work").apply { mkdirs() }

    private val _store = MutableStateFlow(loadInitial())
    val store: StateFlow<NashiStore> = _store.asStateFlow()

    private val _toasts = MutableSharedFlow<String>(extraBufferCapacity = 16)
    val toasts: SharedFlow<String> = _toasts.asSharedFlow()

    private fun loadInitial(): NashiStore = try {
        if (storeFile.exists()) json.decodeFromString(storeFile.readText(Charsets.UTF_8)) else NashiStore()
    } catch (_: Exception) {
        NashiStore()
    }

    private suspend fun mutate(transform: (NashiStore) -> NashiStore) {
        mutex.withLock {
            val next = transform(_store.value)
            _store.value = next
            try {
                val tmp = File(context.filesDir, "nashi_store.json.tmp")
                tmp.writeText(json.encodeToString(next), Charsets.UTF_8)
                if (!tmp.renameTo(storeFile)) {
                    tmp.copyTo(storeFile, overwrite = true)
                    tmp.delete()
                }
            } catch (_: Exception) {}
        }
    }

    fun emitToast(msg: String) {
        _toasts.tryEmit(msg)
    }

    fun inspectUri(uri: Uri): StagedInput {
        val cr = context.contentResolver
        var name = "dosya"
        var size = 0L
        try {
            cr.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
                if (c.moveToFirst()) {
                    val ni = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    val si = c.getColumnIndex(OpenableColumns.SIZE)
                    if (ni >= 0) name = c.getString(ni) ?: name
                    if (si >= 0) size = c.getLong(si)
                }
            }
        } catch (_: Exception) {}
        val mime = (cr.getType(uri) ?: guessMime(name)).lowercase()
        val kind = when {
            mime.startsWith("image/") -> NashiFileKind.IMAGE
            mime.startsWith("video/") -> NashiFileKind.VIDEO
            mime.startsWith("audio/") -> NashiFileKind.AUDIO
            mime == "application/pdf" || name.endsWith(".pdf", true) -> NashiFileKind.PDF
            else -> NashiFileKind.OTHER
        }
        return StagedInput(uri = uri, name = name, mimeType = mime, sizeBytes = size, kind = kind)
    }

    private fun guessMime(name: String): String = when (name.substringAfterLast('.', "").lowercase()) {
        "jpg", "jpeg" -> "image/jpeg"
        "png" -> "image/png"
        "webp" -> "image/webp"
        "heic", "heif" -> "image/heic"
        "mp4", "m4v" -> "video/mp4"
        "mkv" -> "video/x-matroska"
        "mov" -> "video/quicktime"
        "webm" -> "video/webm"
        "mp3" -> "audio/mpeg"
        "m4a", "aac" -> "audio/mp4"
        "wav" -> "audio/wav"
        "flac" -> "audio/flac"
        "ogg" -> "audio/ogg"
        "pdf" -> "application/pdf"
        else -> "application/octet-stream"
    }

    fun newOutputFile(baseName: String, ext: String): File {
        val cleanBase = baseName.substringBeforeLast('.').replace(Regex("[^a-zA-Z0-9._-]"), "_").take(36).ifBlank { "nashi" }
        val ts = System.currentTimeMillis() % 1_000_000
        return File(outputsDir, "${cleanBase}_${ts}.${ext.lowercase()}")
    }

    suspend fun recordOutput(toolLabel: String, file: File, mimeType: String): HistoryEntry {
        val entry = HistoryEntry(
            id = UUID.randomUUID().toString(),
            toolLabel = toolLabel,
            outputFileName = file.name,
            outputPath = file.absolutePath,
            mimeType = mimeType,
            sizeBytes = file.length()
        )
        mutate { s -> s.copy(history = (listOf(entry) + s.history).take(80)) }
        return entry
    }

    suspend fun deleteHistory(id: String) = mutate { s ->
        s.history.firstOrNull { it.id == id }?.let { File(it.outputPath).delete() }
        s.copy(history = s.history.filterNot { it.id == id })
    }

    suspend fun setTheme(theme: NashiThemeMode) = mutate { it.copy(theme = theme) }

    fun shareFile(callerContext: Context, file: File, mimeType: String) {
        if (!file.exists()) { emitToast("Dosya bulunamadı"); return }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = mimeType
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        callerContext.startActivity(Intent.createChooser(intent, "Paylaş").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    suspend fun saveToDeviceStorage(file: File, mimeType: String): Boolean = withContext(Dispatchers.IO) {
        if (!file.exists()) return@withContext false
        try {
            val cr = context.contentResolver
            val (collection, relPath) = when {
                mimeType.startsWith("image/") -> MediaStore.Images.Media.EXTERNAL_CONTENT_URI to "${Environment.DIRECTORY_PICTURES}/Nashi"
                mimeType.startsWith("video/") -> MediaStore.Video.Media.EXTERNAL_CONTENT_URI to "${Environment.DIRECTORY_MOVIES}/Nashi"
                mimeType.startsWith("audio/") -> MediaStore.Audio.Media.EXTERNAL_CONTENT_URI to "${Environment.DIRECTORY_MUSIC}/Nashi"
                else -> MediaStore.Downloads.EXTERNAL_CONTENT_URI to "${Environment.DIRECTORY_DOWNLOADS}/Nashi"
            }
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, file.name)
                put(MediaStore.MediaColumns.MIME_TYPE, mimeType)
                put(MediaStore.MediaColumns.RELATIVE_PATH, relPath)
            }
            val destUri = cr.insert(collection, values) ?: return@withContext false
            cr.openOutputStream(destUri)?.use { out ->
                file.inputStream().use { input -> input.copyTo(out) }
            } ?: return@withContext false
            true
        } catch (_: Exception) {
            false
        }
    }

    suspend fun checkGitHubUpdate(): NashiUpdateInfo = withContext(Dispatchers.IO) {
        val current = BuildConfig.VERSION_NAME
        try {
            val conn = (URL("https://api.github.com/repos/cdokuro/nashi-app/releases/latest").openConnection() as HttpURLConnection).apply {
                connectTimeout = 8000; readTimeout = 8000
                setRequestProperty("Accept", "application/vnd.github+json")
                setRequestProperty("User-Agent", "Nashi-Android/$current")
            }
            if (conn.responseCode == 200) {
                val jsonObj = JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
                val tag = jsonObj.optString("tag_name", "").removePrefix("android-v").removePrefix("v")
                val url = jsonObj.optString("html_url", "https://github.com/cdokuro/nashi-app/releases")
                return@withContext NashiUpdateInfo(current, tag.ifBlank { current }, url, hasUpdate = false)
            }
            NashiUpdateInfo(current, current, "https://github.com/cdokuro/nashi-app/releases", false)
        } catch (e: Exception) {
            NashiUpdateInfo(current, error = e.message)
        }
    }
}

fun formatBytes(bytes: Long): String = when {
    bytes < 1024 -> "$bytes B"
    bytes < 1024 * 1024 -> String.format("%.1f KB", bytes / 1024.0)
    else -> String.format("%.2f MB", bytes / (1024.0 * 1024.0))
}
