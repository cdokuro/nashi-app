package com.nashi.android.engine

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.net.Uri
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.common.InputImage
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import kotlin.coroutines.resume

object QrEngine {

    private val scanner by lazy { BarcodeScanning.getClient() }

    suspend fun scanFromUri(context: Context, uri: Uri): List<String> = withContext(Dispatchers.IO) {
        val bmp = context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it) }
            ?: return@withContext emptyList()
        try {
            suspendCancellableCoroutine { cont ->
                scanner.process(InputImage.fromBitmap(bmp, 0))
                    .addOnSuccessListener { list ->
                        val values = list.mapNotNull { it.rawValue?.takeIf(String::isNotBlank) }.distinct()
                        if (cont.isActive) cont.resume(values)
                    }
                    .addOnFailureListener {
                        if (cont.isActive) cont.resume(emptyList())
                    }
            }
        } finally {
            bmp.recycle()
        }
    }

    suspend fun generateQrPng(
        content: String,
        outFile: File,
        sizePx: Int = 1024,
        darkStyle: Boolean = false
    ): Boolean = withContext(Dispatchers.IO) {
        if (content.isBlank()) return@withContext false
        try {
            val hints = mapOf(
                EncodeHintType.CHARACTER_SET to "UTF-8",
                EncodeHintType.MARGIN to 2
            )
            val matrix = QRCodeWriter().encode(content, BarcodeFormat.QR_CODE, sizePx, sizePx, hints)
            val fg = if (darkStyle) Color.parseColor("#EDF0FA") else Color.parseColor("#14151C")
            val bg = if (darkStyle) Color.parseColor("#181A24") else Color.WHITE
            val pixels = IntArray(sizePx * sizePx)
            for (y in 0 until sizePx) {
                val offset = y * sizePx
                for (x in 0 until sizePx) {
                    pixels[offset + x] = if (matrix.get(x, y)) fg else bg
                }
            }
            val bmp = Bitmap.createBitmap(sizePx, sizePx, Bitmap.Config.ARGB_8888)
            bmp.setPixels(pixels, 0, sizePx, 0, 0, sizePx, sizePx)
            FileOutputStream(outFile).use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
            bmp.recycle()
            true
        } catch (_: Exception) {
            false
        }
    }
}
