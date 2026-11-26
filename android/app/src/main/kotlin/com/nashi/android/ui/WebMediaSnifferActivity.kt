package com.nashi.android.ui

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
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
import androidx.compose.material.icons.rounded.Radar
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Collections

data class DetectedStream(
    val url: String,
    val label: String,
    val isHls: Boolean,
    val mimeType: String,
    val referer: String,
    val origin: String = "",
    val sizeLabel: String = ""
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

private const val JS_SNIFFER_SCRIPT = """
(function(){
  if (window.__nashiHooked) {
    if (window.__nashiScanDom) window.__nashiScanDom();
    return;
  }
  window.__nashiHooked = true;
  function rep(u, k) {
    try {
      if (!u || typeof u !== 'string') return;
      if (u.startsWith('blob:') || u.startsWith('data:')) return;
      var abs = new URL(u, location.href).href;
      if (window.NashiBridge && window.NashiBridge.reportMedia) {
        window.NashiBridge.reportMedia(abs, k || '', location.href);
      }
    } catch(e) {}
  }
  window.__nashiScanDom = function() {
    try {
      document.querySelectorAll('video, audio, source').forEach(function(el) {
        if (el.currentSrc) rep(el.currentSrc, 'dom-video');
        if (el.src) rep(el.src, 'dom-video');
      });
      if (performance && performance.getEntriesByType) {
        performance.getEntriesByType('resource').forEach(function(r) {
          var n = (r && r.name) || '';
          if (/(\.m3u8|\.mp4|\.mkv|\.webm|master\.txt|playlist|videoplayback)/i.test(n)) {
            rep(n, 'perf');
          }
        });
      }
    } catch(e) {}
  };
  try {
    var origFetch = window.fetch;
    if (origFetch) {
      window.fetch = function(input, init) {
        var reqUrl = (typeof input === 'string') ? input : (input && input.url) || '';
        return origFetch.apply(this, arguments).then(function(res) {
          try {
            var ct = (res.headers.get('content-type') || '').toLowerCase();
            if (ct.indexOf('mpegurl') >= 0 || ct.indexOf('video/') === 0) {
              rep(res.url || reqUrl, ct.indexOf('mpegurl') >= 0 ? 'hls' : 'video');
            } else if (/m3u8|master|playlist|hls|manifest|stream/i.test(res.url || reqUrl)) {
              res.clone().text().then(function(t) {
                if (t && t.trim().indexOf('#EXTM3U') === 0) rep(res.url || reqUrl, 'hls');
              }).catch(function(){});
            }
          } catch(e) {}
          return res;
        });
      };
    }
  } catch(e) {}
  try {
    var origOpen = XMLHttpRequest.prototype.open;
    var origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(m, u) {
      this.__nashiUrl = u;
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
      this.addEventListener('load', function() {
        try {
          var u = this.responseURL || this.__nashiUrl || '';
          var ct = (this.getResponseHeader('content-type') || '').toLowerCase();
          if (ct.indexOf('mpegurl') >= 0 || ct.indexOf('video/') === 0) {
            rep(u, ct.indexOf('mpegurl') >= 0 ? 'hls' : 'video');
          } else if (this.responseType === '' || this.responseType === 'text') {
            var txt = (this.responseText || '').slice(0, 64).trim();
            if (txt.indexOf('#EXTM3U') === 0) rep(u, 'hls');
          }
        } catch(e) {}
      });
      return origSend.apply(this, arguments);
    };
  } catch(e) {}
  window.__nashiScanDom();
})();
"""

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
    val seenUrls = remember { Collections.synchronizedSet(mutableSetOf<String>()) }
    val probedUrls = remember { Collections.synchronizedSet(mutableSetOf<String>()) }
    var showStreamsDialog by remember { mutableStateOf(false) }

    var hlsBusy by remember { mutableStateOf(false) }
    var hlsProgress by remember { mutableFloatStateOf(0f) }
    var hlsStatus by remember { mutableStateOf("") }

    fun formatSize(bytes: Long): String {
        if (bytes <= 0L) return ""
        val mb = bytes / (1024.0 * 1024.0)
        return if (mb >= 1024.0) String.format("%.2f GB", mb / 1024.0) else String.format("%.1f MB", mb)
    }

    fun isNoiseUrl(low: String): Boolean {
        return low.contains("doubleclick") ||
            low.contains("googlesyndication") ||
            low.contains("google-analytics") ||
            low.contains("googletagmanager") ||
            low.contains("adserver") ||
            low.contains("facebook.com/tr") ||
            low.contains("cloudflareinsights") ||
            low.contains("pixel.") ||
            low.contains("/favicon")
    }

    fun addStream(url: String, isHls: Boolean, mime: String, referer: String, origin: String, sizeBytes: Long = -1L) {
        val low = url.lowercase()
        if (isNoiseUrl(low)) return
        if (!seenUrls.add(url)) return

        val cleanPath = low.substringBefore('?')
        val sizeStr = formatSize(sizeBytes)
        val baseLabel = when {
            isHls && (low.contains("master") || low.contains("index")) -> "HLS Master Akışı (.m3u8)"
            isHls -> "HLS Video Akışı (.m3u8)"
            mime.contains("matroska") || cleanPath.endsWith(".mkv") -> "MKV Video"
            mime.contains("webm") || cleanPath.endsWith(".webm") -> "WebM Video"
            mime.startsWith("audio/") -> "Ses Dosyası"
            else -> "MP4 Video"
        }
        val label = if (sizeStr.isNotEmpty()) "$baseLabel · $sizeStr" else baseLabel
        val stream = DetectedStream(url, label, isHls, mime, referer, origin, sizeStr)
        // Put Master HLS and direct MP4 at top of list
        if (isHls && low.contains("master")) {
            detected.add(0, stream)
        } else {
            detected.add(0, stream)
        }
    }

    fun inspectRequest(url: String, headers: Map<String, String>?, fallbackReferer: String, ua: String?) {
        val low = url.lowercase()
        if (!low.startsWith("http://") && !low.startsWith("https://")) return
        if (isNoiseUrl(low)) return

        val cleanPath = low.substringBefore('?')
        val referer = headers?.entries?.firstOrNull { it.key.equals("Referer", true) }?.value ?: fallbackReferer
        val origin = headers?.entries?.firstOrNull { it.key.equals("Origin", true) }?.value.orEmpty()
        val accept = headers?.entries?.firstOrNull { it.key.equals("Accept", true) }?.value?.lowercase().orEmpty()
        val hasRange = headers?.keys?.any { it.equals("Range", true) } == true

        // 1) Direct extension / obvious URL match
        val isExplicitHls = cleanPath.endsWith(".m3u8") || low.contains(".m3u8?") ||
            low.contains("playlist.m3u8") || low.contains("master.m3u8") ||
            cleanPath.endsWith("/master.txt") || cleanPath.endsWith("/index.m3u")
        val isExplicitVideo = cleanPath.endsWith(".mp4") || cleanPath.endsWith(".mkv") ||
            cleanPath.endsWith(".webm") || cleanPath.endsWith(".mov") ||
            (low.contains("videoplayback") && low.contains("mime=video"))
        val isExplicitAudio = cleanPath.endsWith(".mp3") || cleanPath.endsWith(".m4a") || cleanPath.endsWith(".aac")

        if (isExplicitHls) {
            addStream(url, true, "application/vnd.apple.mpegurl", referer, origin)
            return
        }
        if (isExplicitVideo) {
            val mime = when {
                cleanPath.endsWith(".mkv") -> "video/x-matroska"
                cleanPath.endsWith(".webm") -> "video/webm"
                else -> "video/mp4"
            }
            addStream(url, false, mime, referer, origin)
            return
        }
        if (isExplicitAudio) {
            addStream(url, false, "audio/mpeg", referer, origin)
            return
        }

        // 2) Skip obvious static non-media assets before probing
        val staticSkip = cleanPath.endsWith(".js") || cleanPath.endsWith(".css") ||
            cleanPath.endsWith(".woff") || cleanPath.endsWith(".woff2") || cleanPath.endsWith(".ttf") ||
            cleanPath.endsWith(".svg") || cleanPath.endsWith(".ico") || cleanPath.endsWith(".webp") ||
            cleanPath.endsWith(".gif") || cleanPath.endsWith(".vtt") || cleanPath.endsWith(".srt") ||
            cleanPath.endsWith(".ts") || cleanPath.endsWith(".m4s")
        if (staticSkip) return

        // 3) Probe disguised / extensionless streaming URLs (common on hdfilmcehennemi, rapidrame, closeload, vidmoly, etc.)
        val looksLikeStreamCandidate = hasRange ||
            accept.contains("video/") ||
            accept.contains("mpegurl") ||
            low.contains("m3u8") || low.contains("/hls/") || low.contains("master") ||
            low.contains("playlist") || low.contains("manifest") || low.contains("stream") ||
            low.contains("video") || low.contains("get_file") || low.contains("play/") ||
            cleanPath.endsWith(".txt")

        if (!looksLikeStreamCandidate) return
        if (probedUrls.size >= 80 || !probedUrls.add(url)) return

        val cookie = try {
            CookieManager.getInstance().getCookie(url) ?: CookieManager.getInstance().getCookie(referer)
        } catch (_: Exception) { null }

        scope.launch {
            val res = HlsDownloadEngine.probeMediaUrl(url, cookie, referer, origin, ua)
            if (res != null) {
                withContext(Dispatchers.Main) {
                    addStream(url, res.isHls, res.mimeType, referer, origin, res.totalBytes)
                }
            }
        }
    }

    fun startStreamDownload(stream: DetectedStream) {
        val ua = webViewRef?.settings?.userAgentString
        val cookie = try {
            CookieManager.getInstance().getCookie(stream.url)
                ?: CookieManager.getInstance().getCookie(stream.referer)
                ?: CookieManager.getInstance().getCookie(currentUrl)
        } catch (_: Exception) { null }
        val safeTitle = pageTitle.replace(Regex("[^a-zA-Z0-9._-]"), "_").take(32).ifBlank { "nashi_video" }

        if (!stream.isHls) {
            val ext = when {
                stream.mimeType.contains("matroska") -> "mkv"
                stream.mimeType.contains("webm") -> "webm"
                stream.mimeType.startsWith("audio/") -> "mp3"
                else -> "mp4"
            }
            val fileName = "${safeTitle}_${System.currentTimeMillis() % 10000}.$ext"
            HlsDownloadEngine.enqueueDirectDownload(context, stream.url, fileName, stream.mimeType, cookie, stream.referer, ua, stream.origin)
            Toast.makeText(context, "İndirme başladı: Downloads/Nashi/$fileName", Toast.LENGTH_LONG).show()
            showStreamsDialog = false
            return
        }

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
                userAgent = ua,
                origin = stream.origin
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
            IconButton(onClick = {
                webViewRef?.evaluateJavascript(JS_SNIFFER_SCRIPT, null)
                Toast.makeText(context, "Sayfadaki videolar taranıyor…", Toast.LENGTH_SHORT).show()
            }) {
                Icon(Icons.Rounded.Radar, "Videoları Tara", tint = palette.pearGold)
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

        // Interactive WebView with Chrome UA + JS sniffer + Network Content-Type/Magic-byte sniffer
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
                        settings.setSupportMultipleWindows(false)
                        settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
                        // Remove "; wv" WebView marker so streaming hosts treat this as normal Mobile Chrome
                        val cleanUa = settings.userAgentString.replace("; wv", "")
                        settings.userAgentString = cleanUa

                        addJavascriptInterface(object {
                            @JavascriptInterface
                            fun reportMedia(url: String, kind: String, pageRef: String) {
                                post {
                                    val ref = pageRef.ifBlank { currentUrl }
                                    when (kind) {
                                        "hls" -> addStream(url, true, "application/vnd.apple.mpegurl", ref, "")
                                        "video" -> addStream(url, false, "video/mp4", ref, "")
                                        else -> inspectRequest(url, null, ref, cleanUa)
                                    }
                                }
                            }
                        }, "NashiBridge")

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
                                view?.evaluateJavascript(JS_SNIFFER_SCRIPT, null)
                            }

                            override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest?): WebResourceResponse? {
                                val u = request?.url?.toString()
                                if (!u.isNullOrBlank()) {
                                    val hdrs = request.requestHeaders
                                    post { inspectRequest(u, hdrs, currentUrl, cleanUa) }
                                }
                                return super.shouldInterceptRequest(view, request)
                            }
                        }

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
                    text = if (detected.isEmpty()) "Videoyu oynat (veya üstteki radar simgesine bas) — Nashi yakalar"
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
