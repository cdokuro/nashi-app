package com.nashi.android.engine

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Rect
import android.graphics.pdf.PdfDocument
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

object PdfEngine {

    suspend fun imagesToPdf(context: Context, imageUris: List<Uri>, outFile: File): Boolean = withContext(Dispatchers.IO) {
        if (imageUris.isEmpty()) return@withContext false
        val doc = PdfDocument()
        try {
            var pageNo = 1
            for (uri in imageUris) {
                val bmp = context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it) } ?: continue
                try {
                    val pageW = bmp.width.coerceAtMost(2400)
                    val scale = pageW.toFloat() / bmp.width.toFloat()
                    val pageH = (bmp.height * scale).toInt().coerceAtLeast(1)
                    val info = PdfDocument.PageInfo.Builder(pageW, pageH, pageNo++).create()
                    val page = doc.startPage(info)
                    page.canvas.drawColor(Color.WHITE)
                    page.canvas.drawBitmap(bmp, null, Rect(0, 0, pageW, pageH), null)
                    doc.finishPage(page)
                } finally {
                    bmp.recycle()
                }
            }
            if (pageNo == 1) return@withContext false
            FileOutputStream(outFile).use { doc.writeTo(it) }
            true
        } catch (_: Exception) {
            false
        } finally {
            doc.close()
        }
    }

    suspend fun pdfToImages(
        context: Context,
        pdfUri: Uri,
        outDir: File,
        baseName: String,
        asPng: Boolean = true,
        maxPages: Int = 30
    ): List<File> = withContext(Dispatchers.IO) {
        val results = mutableListOf<File>()
        val pfd = context.contentResolver.openFileDescriptor(pdfUri, "r") ?: return@withContext results
        try {
            PdfRenderer(pfd).use { renderer ->
                val count = minOf(renderer.pageCount, maxPages)
                for (i in 0 until count) {
                    renderer.openPage(i).use { page ->
                        val w = (page.width * 2).coerceAtMost(2400)
                        val h = (page.height * 2).coerceAtMost(3400)
                        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                        bmp.eraseColor(Color.WHITE)
                        page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                        val ext = if (asPng) "png" else "jpg"
                        val file = File(outDir, "${baseName}_s${i + 1}.$ext")
                        FileOutputStream(file).use { fos ->
                            bmp.compress(if (asPng) Bitmap.CompressFormat.PNG else Bitmap.CompressFormat.JPEG, 92, fos)
                        }
                        bmp.recycle()
                        results.add(file)
                    }
                }
            }
        } catch (_: Exception) {
        } finally {
            try { pfd.close() } catch (_: Exception) {}
        }
        results
    }

    suspend fun mergePdfs(context: Context, pdfUris: List<Uri>, outFile: File): Boolean = withContext(Dispatchers.IO) {
        if (pdfUris.size < 2) return@withContext false
        val doc = PdfDocument()
        var pageNo = 1
        try {
            for (uri in pdfUris) {
                val pfd = context.contentResolver.openFileDescriptor(uri, "r") ?: continue
                try {
                    PdfRenderer(pfd).use { renderer ->
                        for (i in 0 until renderer.pageCount) {
                            renderer.openPage(i).use { page ->
                                val w = (page.width * 2).coerceAtMost(2200)
                                val h = (page.height * 2).coerceAtMost(3100)
                                val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                                bmp.eraseColor(Color.WHITE)
                                page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                                val info = PdfDocument.PageInfo.Builder(page.width, page.height, pageNo++).create()
                                val outPage = doc.startPage(info)
                                outPage.canvas.drawBitmap(bmp, null, Rect(0, 0, page.width, page.height), null)
                                doc.finishPage(outPage)
                                bmp.recycle()
                            }
                        }
                    }
                } finally {
                    try { pfd.close() } catch (_: Exception) {}
                }
            }
            if (pageNo == 1) return@withContext false
            FileOutputStream(outFile).use { doc.writeTo(it) }
            true
        } catch (_: Exception) {
            false
        } finally {
            doc.close()
        }
    }

    suspend fun extractPageRange(
        context: Context,
        pdfUri: Uri,
        fromPage1Based: Int,
        toPage1Based: Int,
        outFile: File
    ): Boolean = withContext(Dispatchers.IO) {
        val pfd = context.contentResolver.openFileDescriptor(pdfUri, "r") ?: return@withContext false
        val doc = PdfDocument()
        try {
            PdfRenderer(pfd).use { renderer ->
                val start = (fromPage1Based - 1).coerceIn(0, renderer.pageCount - 1)
                val end = (toPage1Based - 1).coerceIn(start, renderer.pageCount - 1)
                var pageNo = 1
                for (i in start..end) {
                    renderer.openPage(i).use { page ->
                        val w = (page.width * 2).coerceAtMost(2200)
                        val h = (page.height * 2).coerceAtMost(3100)
                        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                        bmp.eraseColor(Color.WHITE)
                        page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                        val info = PdfDocument.PageInfo.Builder(page.width, page.height, pageNo++).create()
                        val outPage = doc.startPage(info)
                        outPage.canvas.drawBitmap(bmp, null, Rect(0, 0, page.width, page.height), null)
                        doc.finishPage(outPage)
                        bmp.recycle()
                    }
                }
            }
            FileOutputStream(outFile).use { doc.writeTo(it) }
            true
        } catch (_: Exception) {
            false
        } finally {
            doc.close()
            try { pfd.close() } catch (_: Exception) {}
        }
    }

    fun getPageCount(context: Context, pdfUri: Uri): Int {
        val pfd = context.contentResolver.openFileDescriptor(pdfUri, "r") ?: return 0
        return try {
            PdfRenderer(pfd).use { it.pageCount }
        } catch (_: Exception) {
            0
        } finally {
            try { pfd.close() } catch (_: Exception) {}
        }
    }
}
