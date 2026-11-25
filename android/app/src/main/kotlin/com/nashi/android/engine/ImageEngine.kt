package com.nashi.android.engine

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.RectF
import android.net.Uri
import android.os.Build
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import kotlin.math.roundToInt

enum class ImageFormatTarget(val ext: String, val mime: String, val label: String) {
    JPG("jpg", "image/jpeg", "JPG"),
    PNG("png", "image/png", "PNG"),
    WEBP("webp", "image/webp", "WebP"),
    WEBP_LOSSLESS("webp", "image/webp", "WebP Kayıpsız")
}

object ImageEngine {

    private fun decodeUri(context: Context, uri: Uri): Bitmap? {
        return context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it) }
    }

    private fun saveBitmap(bmp: Bitmap, outFile: File, target: ImageFormatTarget, quality: Int) {
        val fmt = when (target) {
            ImageFormatTarget.JPG -> Bitmap.CompressFormat.JPEG
            ImageFormatTarget.PNG -> Bitmap.CompressFormat.PNG
            ImageFormatTarget.WEBP -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) Bitmap.CompressFormat.WEBP_LOSSY else @Suppress("DEPRECATION") Bitmap.CompressFormat.WEBP
            ImageFormatTarget.WEBP_LOSSLESS -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) Bitmap.CompressFormat.WEBP_LOSSLESS else @Suppress("DEPRECATION") Bitmap.CompressFormat.WEBP
        }
        FileOutputStream(outFile).use { fos ->
            bmp.compress(fmt, quality.coerceIn(10, 100), fos)
        }
    }

    suspend fun convert(
        context: Context,
        uri: Uri,
        outFile: File,
        target: ImageFormatTarget,
        quality: Int = 88,
        maxEdge: Int? = null,
        rotateDegrees: Float = 0f,
        flipHorizontal: Boolean = false,
        grayscale: Boolean = false,
        cropFraction: RectF? = null
    ): Boolean = withContext(Dispatchers.IO) {
        var bmp = decodeUri(context, uri) ?: return@withContext false
        try {
            if (cropFraction != null && cropFraction.width() > 0.02f && cropFraction.height() > 0.02f) {
                val x = (cropFraction.left * bmp.width).roundToInt().coerceIn(0, bmp.width - 1)
                val y = (cropFraction.top * bmp.height).roundToInt().coerceIn(0, bmp.height - 1)
                val w = (cropFraction.width() * bmp.width).roundToInt().coerceIn(1, bmp.width - x)
                val h = (cropFraction.height() * bmp.height).roundToInt().coerceIn(1, bmp.height - y)
                val cropped = Bitmap.createBitmap(bmp, x, y, w, h)
                bmp.recycle()
                bmp = cropped
            }

            if (rotateDegrees != 0f || flipHorizontal) {
                val m = Matrix().apply {
                    if (rotateDegrees != 0f) postRotate(rotateDegrees)
                    if (flipHorizontal) postScale(-1f, 1f)
                }
                val transformed = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, m, true)
                bmp.recycle()
                bmp = transformed
            }

            if (maxEdge != null && maxEdge > 0) {
                val maxDim = maxOf(bmp.width, bmp.height)
                if (maxDim > maxEdge) {
                    val ratio = maxEdge.toFloat() / maxDim.toFloat()
                    val nw = maxOf(1, (bmp.width * ratio).roundToInt())
                    val nh = maxOf(1, (bmp.height * ratio).roundToInt())
                    val scaled = Bitmap.createScaledBitmap(bmp, nw, nh, true)
                    bmp.recycle()
                    bmp = scaled
                }
            }

            if (grayscale) {
                val gray = Bitmap.createBitmap(bmp.width, bmp.height, Bitmap.Config.ARGB_8888)
                val canvas = Canvas(gray)
                val paint = Paint().apply {
                    colorFilter = ColorMatrixColorFilter(ColorMatrix().apply { setSaturation(0f) })
                }
                canvas.drawBitmap(bmp, 0f, 0f, paint)
                bmp.recycle()
                bmp = gray
            }

            saveBitmap(bmp, outFile, target, quality)
            true
        } catch (_: Exception) {
            false
        } finally {
            if (!bmp.isRecycled) bmp.recycle()
        }
    }
}
