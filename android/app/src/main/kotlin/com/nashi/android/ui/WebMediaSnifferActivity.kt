package com.nashi.android.ui

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.webkit.CookieManager
import android.webkit.URLUtil
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.Movie
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.nashi.android.NashiApp
import com.nashi.android.engine.HlsDownloadEngine
import com.nashi.android.ui.theme.LocalNashiPalette
import com.nashi.android.ui.theme.NashiTheme
import kotlinx.coroutines.launch

data class DetectedStream(
    val url: String,
    val label: String,
    val isHls: Boolean,
    val mimeType: String,
    val referer: String
)

class WebMediaSnifferActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val initialUrl = intent.getStringExtra(EXTRA_URL).orEmpty().ifBlank { "https://www.google.com" }
        val repo = NashiApp.instance.repository

        setContent {
            val store by repo.store.collectAsState()
            NashiTheme(mode = store.theme) {
                WebMediaSnifferScreen(
                    initialUrl = initialUrl,
                    onClose = { finish() }
                )
            }
        }
    }

    companion object {
        private const val EXTRA_URL = "url"
        fun launch(context: Context, url: String) {
            val intent = Intent(context, WebMediaSnifferActivity::class.java).apply {
                putExtra(EXTRA_URL, url)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun WebMediaSnifferScreen(
    initialUrl: String,
    onClose: () -> Unit
) {
    val palette = LocalNashiPalette.current
    val scope = rememberCoroutineScope()
    val repo = NashiApp.instance.repository
    val context = androidx.compose.ui.platform.LocalContext.current

    var currentUrl by remember { mutableStateOf(initialUrl) }
    var pageTitle by remember { mutableStateOf("Medya Tarayıcı") }
    var loadProgress by remember { mutableFloatStateOf(0f) }
    var webViewRef by remember { mutableStateOf<WebView?>(null) }

    val detected = remember { mutableStateListOf<DetectedStream>() }
    val seenUrls = remember { mutableSetOf<String>() }
    var showStreamsDialog by remember { mutableStateOf(false) }

    var hlsBusy by remember { mutableStateOf(false) }
    var hlsProgress by remember { mutableFloatStateOf(0f) }
    var hlsStatus by remember { mutableStateOf("") }

    fun maybeRecordStream(url: String, referer: String) {
        val low = url.lowercase()
        val cleanPath = low.substringBefore('?')
        val isHls = cleanPath.endsWith(".m3u8") || low.contains(".m3u8?") || low.contains("playlist.m3u8") || low.contains("master.m3u8")
        val isDirectVideo = cleanPath.endsWith(".mp4") || cleanPath.endsWith(".mkv") || cleanPath.endsWith(".webm") || cleanPath.endsWith(".mov") ||
            (low.contains("mime=video") && !low.contains("range="))
        val isDirectAudio = cleanPath.endsWith(".mp3") || cleanPath.endsWith(".m4a") || cleanPath.endsWith(".aac")
        if (!isHls && !isDirectVideo && !isDirectAudio) return
        if (low.contains("doubleclick") || low.contains("googlesyndication") || low.contains("adserver") || low.contains("pixel.")) return
        if (!seenUrls.add(url)) return

        val label = when {
            isHls && low.contains("master") -> "HLS Master Akışı (.m3u8)"
            isHls -> "HLS Video Akışı (.m3u8)"
            cleanPath.endsWith(".mkv") -> "MKV Video"
            cleanPath.endsWith(".webm") -> "WebM Video"
            isDirectAudio -> "Ses Dosyası"
            else -> "MP4 Video"
        }
        val mime = when {
            isHls -> "application/vnd.apple.mpegurl"
            cleanPath.endsWith(".mkv") -> "video/x-matroska"
            cleanPath.endsWith(".webm") -> "video/webm"
            isDirectAudio -> "audio/mpeg"
            else -> "video/mp4"
        }
        detected.add(0, DetectedStream(url, label, isHls, mime, referer))
    }

    fun startStreamDownload(stream: DetectedStream) {
        val ua = webViewRef?.settings?.userAgentString
        val cookie = try { CookieManager.getInstance().getCookie(stream.url) ?: CookieManager.getInstance().getCookie(currentUrl) } catch (_: Exception) { null }
        val safeTitle = pageTitle.replace(Regex("[^a-zA-Z0-9._-]"), "_").take(32).ifBlank { "nashi_video" }

        if (!stream.isHls) {
            val ext = when {
                stream.mimeType.contains("matroska") -> "mkv"
                stream.mimeType.contains("webm") -> "webm"
                stream.mimeType.startsWith("audio/") -> "mp3"
                else -> "mp4"
            }
            val fileName = "${safeTitle}_${System.currentTimeMillis() % 10000}.$ext"
            HlsDownloadEngine.enqueueDirectDownload(context, stream.url, fileName, stream.mimeType, cookie, stream.referer, ua)
            Toast.makeText(context, "İndirme başladı: Downloads/Nashi/$fileName", Toast.LENGTH_LONG).show()
            showStreamsDialog = false
            return
        }

        // HLS (.m3u8) segment downloader
        showStreamsDialog = false
        hlsBusy = true
        hlsProgress = 0.02f
        hlsStatus = "HLS akışı analiz ediliyor…"
        scope.launch {
            val outFile = repo.newOutputFile(safeTitle, "ts")
            val ok = HlsDownloadEngine.downloadHlsToFile(
                m3u8Url = stream.url,
                outFile = outFile,
                cookie = cookie,
                referer = stream.referer,
                userAgent = ua
            ) { pct, msg ->
                hlsProgress = pct
                hlsStatus = msg
            }
            hlsBusy = false
            if (ok) {
                repo.recordOutput("HLS Video İndirme", outFile, "video/mp2t")
                val saved = repo.saveToDeviceStorage(outFile, "video/mp2t")
                Toast.makeText(
                    context,
                    if (saved) "Video kaydedildi: Movies/Nashi/${outFile.name}" else "Video Nashi Çıktılar'a kaydedildi",
                    Toast.LENGTH_LONG
                ).show()
            } else {
                Toast.makeText(context, "HLS akışı indirilemedi (şifreli veya süresi dolmuş olabilir)", Toast.LENGTH_LONG).show()
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(palette.bg)
            .statusBarsPadding()
            .navigationBarsPadding()
    ) {
        // Top browser bar
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(palette.surface)
                .padding(horizontal = 6.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = {
                val wv = webViewRef
                if (wv != null && wv.canGoBack()) wv.goBack() else onClose()
            }) {
                Icon(Icons.AutoMirrored.Rounded.ArrowBack, "Geri", tint = palette.textPrimary)
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(pageTitle, color = palette.textPrimary, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(currentUrl, color = palette.textSecondary, fontSize = 10.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            IconButton(onClick = { webViewRef?.reload() }) {
                Icon(Icons.Rounded.Refresh, "Yenile", tint = palette.textSecondary)
            }
            IconButton(onClick = onClose) {
                Icon(Icons.Rounded.Close, "Kapat", tint = palette.textPrimary)
            }
        }

        if (loadProgress in 0.01f..0.99f) {
            LinearProgressIndicator(progress = { loadProgress }, color = palette.pearGold, modifier = Modifier.fillMaxWidth().height(2.dp))
        }

        // Real interactive WebView (user plays video / clicks quality / completes any human check naturally)
        Box(modifier = Modifier.weight(1f).fillMaxWidth()) {
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { ctx ->
                    WebView(ctx).apply {
                        webViewRef = this
                        CookieManager.getInstance().setAcceptCookie(true)
                        CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        settings.mediaPlaybackRequiresUserGesture = false
                        settings.useWideViewPort = true
                        settings.loadWithOverviewMode = true
                        settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE

                        webChromeClient = object : WebChromeClient() {
                            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                                loadProgress = newProgress / 100f
                            }
                            override fun onReceivedTitle(view: WebView?, title: String?) {
                                if (!title.isNullOrBlank()) pageTitle = title
                            }
                        }

                        webViewClient = object : WebViewClient() {
                            override fun onPageFinished(view: WebView?, url: String?) {
                                if (!url.isNullOrBlank()) currentUrl = url
                            }

                            override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest?): WebResourceResponse? {
                                val u = request?.url?.toString()
                                if (!u.isNullOrBlank()) {
                                    val ref = request.requestHeaders?.get("Referer") ?: currentUrl
                                    post { maybeRecordStream(u, ref) }
                                }
                                return super.shouldInterceptRequest(view, request)
                            }
                        }

                        // Intercept ANY native download link click (e.g. 1.8 GB / 4 GB direct movie downloads!)
                        setDownloadListener { url, userAgent, contentDisposition, mimetype, _ ->
                            val cookie = try { CookieManager.getInstance().getCookie(url) ?: CookieManager.getInstance().getCookie(currentUrl) } catch (_: Exception) { null }
                            val guessedName = URLUtil.guessFileName(url, contentDisposition, mimetype)
                            HlsDownloadEngine.enqueueDirectDownload(ctx, url, guessedName, mimetype ?: "video/mp4", cookie, currentUrl, userAgent)
                            Toast.makeText(ctx, "İndirme başladı (Bildirim çubuğundan izle): $guessedName", Toast.LENGTH_LONG).show()
                        }

                        loadUrl(initialUrl)
                    }
                }
            )

            if (hlsBusy) {
                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = palette.surface.copy(alpha = 0.96f),
                    border = BorderStroke(1.dp, palette.pearGold),
                    modifier = Modifier.align(Alignment.Center).padding(24.dp)
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        CircularProgressIndicator(progress = { hlsProgress }, color = palette.pearGold)
                        Text("Video İndiriliyor", color = palette.textPrimary, fontWeight = FontWeight.Bold)
                        Text(hlsStatus, color = palette.textSecondary, fontSize = 12.5.sp)
                    }
                }
            }
        }

        // Bottom captured-media bar
        Surface(
            color = palette.surface,
            border = BorderStroke(1.dp, palette.border),
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    Icons.Rounded.Movie, null,
                    tint = if (detected.isNotEmpty()) palette.success else palette.textSecondary,
                    modifier = Modifier.size(20.dp)
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = if (detected.isEmpty()) "Videoyu oynat veya İndir butonuna tıkla — Nashi yakalar"
                    else "${detected.size} video akışı yakalandı!",
                    color = if (detected.isNotEmpty()) palette.success else palette.textSecondary,
                    fontSize = 12.sp,
                    modifier = Modifier.weight(1f)
                )
                if (detected.isNotEmpty()) {
                    Button(
                        onClick = { showStreamsDialog = true },
                        colors = ButtonDefaults.buttonColors(containerColor = palette.success, contentColor = Color(0xFF0A140F))
                    ) {
                        Icon(Icons.Rounded.Download, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(5.dp))
                        Text("İndir (${detected.size})", fontWeight = FontWeight.Bold, fontSize = 12.5.sp)
                    }
                }
            }
        }
    }

    if (showStreamsDialog) {
        AlertDialog(
            onDismissRequest = { showStreamsDialog = false },
            containerColor = palette.surface,
            title = { Text("Yakalanan Video Akışları", color = palette.textPrimary) },
            text = {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(detected) { stream ->
                        Surface(
                            onClick = { startStreamDownload(stream) },
                            shape = RoundedCornerShape(12.dp),
                            color = palette.bg,
                            border = BorderStroke(1.dp, palette.border),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(stream.label, color = palette.pearGold, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                                    Text(stream.url, color = palette.textSecondary, fontSize = 10.5.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                }
                                Spacer(Modifier.width(8.dp))
                                Icon(Icons.Rounded.Download, "İndir", tint = palette.success)
                            }
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { showStreamsDialog = false }) { Text("Kapat") } }
        )
    }
}
