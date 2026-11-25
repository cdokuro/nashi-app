package com.nashi.android.engine

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMetadataRetriever
import android.media.MediaMuxer
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer

data class MediaInfo(
    val durationMs: Long,
    val width: Int,
    val height: Int,
    val rotation: Int
)

object MediaEngine {

    fun probe(context: Context, uri: Uri): MediaInfo {
        val mmr = MediaMetadataRetriever()
        return try {
            mmr.setDataSource(context, uri)
            val dur = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
            val w = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0
            val h = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0
            val rot = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0
            MediaInfo(dur, w, h, rot)
        } catch (_: Exception) {
            MediaInfo(0L, 0, 0, 0)
        } finally {
            try { mmr.release() } catch (_: Exception) {}
        }
    }

    suspend fun extractFrame(context: Context, uri: Uri, timeMs: Long, outFile: File): Boolean = withContext(Dispatchers.IO) {
        val mmr = MediaMetadataRetriever()
        try {
            mmr.setDataSource(context, uri)
            val bmp = mmr.getFrameAtTime(timeMs * 1000L, MediaMetadataRetriever.OPTION_CLOSEST_SYNC) ?: return@withContext false
            FileOutputStream(outFile).use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
            bmp.recycle()
            true
        } catch (_: Exception) {
            false
        } finally {
            try { mmr.release() } catch (_: Exception) {}
        }
    }

    /**
     * Lossless instant MediaExtractor + MediaMuxer processor:
     * - keepVideo=true, keepAudio=true -> Trim video
     * - keepVideo=false, keepAudio=true -> Extract audio (M4A)
     * - keepVideo=true, keepAudio=false -> Mute video (MP4)
     */
    suspend fun remux(
        context: Context,
        uri: Uri,
        outFile: File,
        startMs: Long = 0L,
        endMs: Long = Long.MAX_VALUE,
        keepVideo: Boolean = true,
        keepAudio: Boolean = true
    ): Boolean = withContext(Dispatchers.IO) {
        val extractor = MediaExtractor()
        var muxer: MediaMuxer? = null
        try {
            extractor.setDataSource(context, uri, null)
            val trackMap = mutableMapOf<Int, Int>()
            muxer = MediaMuxer(outFile.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)

            val info = probe(context, uri)
            if (keepVideo && info.rotation != 0) {
                muxer.setOrientationHint(info.rotation)
            }

            var maxBufferSize = 256 * 1024
            for (i in 0 until extractor.trackCount) {
                val fmt = extractor.getTrackFormat(i)
                val mime = fmt.getString(MediaFormat.KEY_MIME) ?: continue
                val use = (keepVideo && mime.startsWith("video/")) || (keepAudio && mime.startsWith("audio/"))
                if (use) {
                    extractor.selectTrack(i)
                    val dstTrack = muxer.addTrack(fmt)
                    trackMap[i] = dstTrack
                    if (fmt.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) {
                        maxBufferSize = maxOf(maxBufferSize, fmt.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE))
                    }
                }
            }
            if (trackMap.isEmpty()) return@withContext false

            muxer.start()
            val startUs = startMs.coerceAtLeast(0L) * 1000L
            val endUs = if (endMs == Long.MAX_VALUE) Long.MAX_VALUE else endMs * 1000L
            if (startUs > 0) {
                extractor.seekTo(startUs, MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
            }

            val buffer = ByteBuffer.allocate(maxBufferSize.coerceAtLeast(512 * 1024))
            val bufferInfo = MediaCodec.BufferInfo()
            val basePts = mutableMapOf<Int, Long>()

            while (true) {
                bufferInfo.offset = 0
                bufferInfo.size = extractor.readSampleData(buffer, 0)
                if (bufferInfo.size < 0) break
                val pts = extractor.sampleTime
                if (pts > endUs) break
                val srcTrack = extractor.sampleTrackIndex
                val dstTrack = trackMap[srcTrack]
                if (dstTrack != null && pts >= startUs) {
                    val offsetPts = basePts.getOrPut(srcTrack) { pts }
                    bufferInfo.presentationTimeUs = (pts - offsetPts).coerceAtLeast(0L)
                    bufferInfo.flags = extractor.sampleFlags
                    muxer.writeSampleData(dstTrack, buffer, bufferInfo)
                }
                extractor.advance()
            }
            muxer.stop()
            true
        } catch (_: Exception) {
            try { outFile.delete() } catch (_: Exception) {}
            false
        } finally {
            try { muxer?.release() } catch (_: Exception) {}
            try { extractor.release() } catch (_: Exception) {}
        }
    }
}
