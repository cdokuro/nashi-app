package com.nashi.android.data

import android.net.Uri
import kotlinx.serialization.Serializable

@Serializable
enum class NashiFileKind {
    IMAGE, VIDEO, AUDIO, PDF, OTHER
}

@Serializable
enum class NashiThemeMode {
    EDNA, WARM, NEUTRAL
}

data class StagedInput(
    val uri: Uri,
    val name: String,
    val mimeType: String,
    val sizeBytes: Long,
    val kind: NashiFileKind
)

@Serializable
data class HistoryEntry(
    val id: String,
    val toolLabel: String,
    val outputFileName: String,
    val outputPath: String,
    val mimeType: String,
    val sizeBytes: Long,
    val createdAt: Long = System.currentTimeMillis()
)

@Serializable
data class NashiStore(
    val theme: NashiThemeMode = NashiThemeMode.EDNA,
    val history: List<HistoryEntry> = emptyList()
)

data class NashiUpdateInfo(
    val currentVersion: String,
    val latestVersion: String? = null,
    val releaseUrl: String? = null,
    val hasUpdate: Boolean = false,
    val checking: Boolean = false,
    val error: String? = null
)
