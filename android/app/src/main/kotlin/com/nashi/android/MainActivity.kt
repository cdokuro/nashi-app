package com.nashi.android

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AddPhotoAlternate
import androidx.compose.material.icons.rounded.AudioFile
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Compress
import androidx.compose.material.icons.rounded.ContentCut
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Download
import androidx.compose.material.icons.rounded.FilterBAndW
import androidx.compose.material.icons.rounded.FolderOpen
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.Image
import androidx.compose.material.icons.rounded.Link
import androidx.compose.material.icons.rounded.PhotoCamera
import androidx.compose.material.icons.rounded.PhotoSizeSelectLarge
import androidx.compose.material.icons.rounded.PictureAsPdf
import androidx.compose.material.icons.rounded.PrivacyTip
import androidx.compose.material.icons.rounded.QrCode2
import androidx.compose.material.icons.rounded.QrCodeScanner
import androidx.compose.material.icons.rounded.Rotate90DegreesCw
import androidx.compose.material.icons.rounded.SaveAlt
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Share
import androidx.compose.material.icons.rounded.SystemUpdate
import androidx.compose.material.icons.rounded.Transform
import androidx.compose.material.icons.rounded.VideoFile
import androidx.compose.material.icons.rounded.VolumeOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RangeSlider
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.nashi.android.data.HistoryEntry
import com.nashi.android.data.NashiFileKind
import com.nashi.android.data.NashiRepository
import com.nashi.android.data.NashiStore
import com.nashi.android.data.NashiThemeMode
import com.nashi.android.data.NashiUpdateInfo
import com.nashi.android.data.StagedInput
import com.nashi.android.data.formatBytes
import com.nashi.android.engine.ImageEngine
import com.nashi.android.engine.ImageFormatTarget
import com.nashi.android.engine.MediaEngine
import com.nashi.android.engine.PdfEngine
import com.nashi.android.engine.QrEngine
import com.nashi.android.engine.WebDownloadEngine
import com.nashi.android.ui.components.RadialConversionWheel
import com.nashi.android.ui.components.WheelAction
import com.nashi.android.ui.theme.LocalNashiPalette
import com.nashi.android.ui.theme.NashiTheme
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import java.io.File

class MainActivity : ComponentActivity() {

    private val incomingInputs = MutableStateFlow<List<StagedInput>>(emptyList())
    private val incomingUrl = MutableStateFlow<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        handleIncomingIntent(intent)

        val repo = NashiApp.instance.repository

        setContent {
            val store by repo.store.collectAsState()
            val sharedFiles by incomingInputs.collectAsState()
            val sharedUrl by incomingUrl.collectAsState()

            LaunchedEffect(Unit) {
                repo.toasts.collect { msg ->
                    Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                }
            }

            NashiTheme(mode = store.theme) {
                NashiMainShell(
                    store = store,
                    repository = repo,
                    stagedInputs = sharedFiles,
                    onStageInputs = { incomingInputs.value = it },
                    pendingWebUrl = sharedUrl,
                    onConsumeWebUrl = { incomingUrl.value = null }
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIncomingIntent(intent)
    }

    private fun handleIncomingIntent(intent: Intent?) {
        if (intent == null) return
        val repo = NashiApp.instance.repository
        when (intent.action) {
            Intent.ACTION_SEND -> {
                val type = intent.type ?: ""
                if (type == "text/plain") {
                    val txt = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()
                    if (!txt.isNullOrBlank() && (txt.startsWith("http://", true) || txt.startsWith("https://", true))) {
                        incomingUrl.value = txt
                    }
                } else {
                    val uri = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
                    } else {
                        @Suppress("DEPRECATION")
                        intent.getParcelableExtra(Intent.EXTRA_STREAM)
                    }
                    if (uri != null) incomingInputs.value = listOf(repo.inspectUri(uri))
                }
            }
            Intent.ACTION_SEND_MULTIPLE -> {
                val uris = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM)
                }
                if (!uris.isNullOrEmpty()) {
                    incomingInputs.value = uris.map { repo.inspectUri(it) }
                }
            }
        }
    }
}

@Composable
private fun NashiMainShell(
    store: NashiStore,
    repository: NashiRepository,
    stagedInputs: List<StagedInput>,
    onStageInputs: (List<StagedInput>) -> Unit,
    pendingWebUrl: String?,
    onConsumeWebUrl: () -> Unit
) {
    val palette = LocalNashiPalette.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var selectedTab by remember { mutableIntStateOf(0) }
    var busy by remember { mutableStateOf(false) }
    var progress by remember { mutableStateOf<Float?>(null) }

    // Dialog states
    var showWebDialog by remember { mutableStateOf(false) }
    var webUrlInput by remember { mutableStateOf("") }
    var showQrGenDialog by remember { mutableStateOf(false) }
    var qrGenText by remember { mutableStateOf("") }
    var qrGenDark by remember { mutableStateOf(true) }
    var qrScanResults by remember { mutableStateOf<List<String>?>(null) }

    // Trim dialog state (for video or audio)
    var trimTarget by remember { mutableStateOf<StagedInput?>(null) }
    var trimDurationMs by remember { mutableStateOf(0L) }
    var trimRange by remember { mutableStateOf(0f..1f) }

    // PDF split dialog state
    var splitPdfTarget by remember { mutableStateOf<StagedInput?>(null) }
    var splitPageCount by remember { mutableIntStateOf(1) }
    var splitFrom by remember { mutableStateOf("1") }
    var splitTo by remember { mutableStateOf("1") }

    // Latest result highlight banner
    var latestResult by remember { mutableStateOf<HistoryEntry?>(null) }

    LaunchedEffect(pendingWebUrl) {
        if (!pendingWebUrl.isNullOrBlank()) {
            webUrlInput = pendingWebUrl
            showWebDialog = true
            onConsumeWebUrl()
        }
    }

    val multiFilePicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments()
    ) { uris ->
        if (uris.isNotEmpty()) {
            onStageInputs(uris.map { repository.inspectUri(it) })
            selectedTab = 0
        }
    }

    val qrImagePicker = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        if (uri != null) {
            busy = true
            scope.launch {
                val codes = QrEngine.scanFromUri(context, uri)
                busy = false
                if (codes.isEmpty()) repository.emitToast("Görselde QR veya barkod bulunamadı")
                else qrScanResults = codes
            }
        }
    }

    val imagesToPdfPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments()
    ) { uris ->
        if (uris.isNotEmpty()) {
            busy = true
            scope.launch {
                val out = repository.newOutputFile("nashi_belge", "pdf")
                val ok = PdfEngine.imagesToPdf(context, uris, out)
                busy = false
                if (ok) {
                    latestResult = repository.recordOutput("Görseller → PDF (${uris.size} sayfa)", out, "application/pdf")
                    repository.emitToast("PDF oluşturuldu!")
                } else repository.emitToast("PDF oluşturulamadı")
            }
        }
    }

    fun executeWheelAction(action: WheelAction) {
        val inputs = stagedInputs
        if (inputs.isEmpty()) return
        val first = inputs.first()

        if (action.id == "trim_media") {
            val info = MediaEngine.probe(context, first.uri)
            trimTarget = first
            trimDurationMs = info.durationMs.coerceAtLeast(1000L)
            trimRange = 0f..1f
            return
        }
        if (action.id == "pdf_split") {
            val count = PdfEngine.getPageCount(context, first.uri).coerceAtLeast(1)
            splitPdfTarget = first
            splitPageCount = count
            splitFrom = "1"
            splitTo = count.toString()
            return
        }

        busy = true
        progress = null
        scope.launch {
            try {
                when (action.id) {
                    "img_jpg", "img_png", "img_webp", "img_compress", "img_1080", "img_exif", "img_rot90", "img_gray" -> {
                        val fmt = when (action.id) {
                            "img_png" -> ImageFormatTarget.PNG
                            "img_webp" -> ImageFormatTarget.WEBP
                            else -> ImageFormatTarget.JPG
                        }
                        val quality = if (action.id == "img_compress") 68 else 90
                        val maxEdge = if (action.id == "img_1080") 1080 else null
                        val rot = if (action.id == "img_rot90") 90f else 0f
                        val gray = action.id == "img_gray"
                        var last: HistoryEntry? = null
                        inputs.filter { it.kind == NashiFileKind.IMAGE }.forEachIndexed { i, inp ->
                            progress = (i + 1f) / inputs.size.toFloat()
                            val out = repository.newOutputFile(inp.name, fmt.ext)
                            val ok = ImageEngine.convert(context, inp.uri, out, fmt, quality, maxEdge, rot, false, gray)
                            if (ok) last = repository.recordOutput(action.label, out, fmt.mime)
                        }
                        if (last != null) {
                            latestResult = last
                            repository.emitToast("${action.label} tamamlandı!")
                        } else repository.emitToast("İşlem başarısız")
                    }
                    "img_pdf" -> {
                        val out = repository.newOutputFile(first.name, "pdf")
                        val ok = PdfEngine.imagesToPdf(context, inputs.filter { it.kind == NashiFileKind.IMAGE }.map { it.uri }, out)
                        if (ok) {
                            latestResult = repository.recordOutput("Görsel → PDF", out, "application/pdf")
                            repository.emitToast("PDF oluşturuldu!")
                        } else repository.emitToast("PDF oluşturulamadı")
                    }
                    "img_qr" -> {
                        val codes = QrEngine.scanFromUri(context, first.uri)
                        if (codes.isEmpty()) repository.emitToast("QR kod bulunamadı")
                        else qrScanResults = codes
                    }
                    "vid_audio" -> {
                        val out = repository.newOutputFile(first.name, "m4a")
                        val ok = MediaEngine.remux(context, first.uri, out, keepVideo = false, keepAudio = true)
                        if (ok) {
                            latestResult = repository.recordOutput("Ses Ayır (M4A)", out, "audio/mp4")
                            repository.emitToast("Ses ayırıldı (M4A)!")
                        } else repository.emitToast("Bu videoda uyumlu ses kanalı bulunamadı")
                    }
                    "vid_mute" -> {
                        val out = repository.newOutputFile("${first.name}_sessiz", "mp4")
                        val ok = MediaEngine.remux(context, first.uri, out, keepVideo = true, keepAudio = false)
                        if (ok) {
                            latestResult = repository.recordOutput("Sessize Al (MP4)", out, "video/mp4")
                            repository.emitToast("Video sessize alındı!")
                        } else repository.emitToast("Video işlenemedi")
                    }
                    "vid_frame" -> {
                        val info = MediaEngine.probe(context, first.uri)
                        val out = repository.newOutputFile("${first.name}_kare", "png")
                        val ok = MediaEngine.extractFrame(context, first.uri, info.durationMs / 2L, out)
                        if (ok) {
                            latestResult = repository.recordOutput("Videodan Kare (PNG)", out, "image/png")
                            repository.emitToast("Kare yakalandı!")
                        } else repository.emitToast("Kare alınamadı")
                    }
                    "pdf_png", "pdf_jpg" -> {
                        val asPng = action.id == "pdf_png"
                        val base = first.name.substringBeforeLast('.').take(24).ifBlank { "pdf" }
                        val files = PdfEngine.pdfToImages(context, first.uri, repository.outputsDir, "${base}_${System.currentTimeMillis() % 10000}", asPng)
                        if (files.isNotEmpty()) {
                            var last: HistoryEntry? = null
                            files.forEach { f ->
                                last = repository.recordOutput(if (asPng) "PDF → PNG" else "PDF → JPG", f, if (asPng) "image/png" else "image/jpeg")
                            }
                            latestResult = last
                            repository.emitToast("${files.size} sayfa görsele dönüştürüldü!")
                        } else repository.emitToast("PDF okunamadı")
                    }
                    "pdf_merge" -> {
                        val out = repository.newOutputFile("birlesik", "pdf")
                        val ok = PdfEngine.mergePdfs(context, inputs.filter { it.kind == NashiFileKind.PDF }.map { it.uri }, out)
                        if (ok) {
                            latestResult = repository.recordOutput("PDF Birleştir", out, "application/pdf")
                            repository.emitToast("PDF dosyaları birleştirildi!")
                        } else repository.emitToast("PDF birleştirilemedi")
                    }
                }
            } finally {
                busy = false
                progress = null
            }
        }
    }

    Scaffold(
        containerColor = palette.bg,
        bottomBar = {
            NavigationBar(containerColor = palette.surface, tonalElevation = 0.dp) {
                val colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = palette.pearGold,
                    selectedTextColor = palette.pearGold,
                    indicatorColor = palette.pearGold.copy(alpha = 0.16f),
                    unselectedIconColor = palette.textSecondary,
                    unselectedTextColor = palette.textSecondary
                )
                NavigationBarItem(
                    selected = selectedTab == 0, onClick = { selectedTab = 0 },
                    icon = { Icon(Icons.Rounded.Transform, "Çark") }, label = { Text("Çark") }, colors = colors
                )
                NavigationBarItem(
                    selected = selectedTab == 1, onClick = { selectedTab = 1 },
                    icon = { Icon(Icons.Rounded.History, "Çıktılar") }, label = { Text("Çıktılar") }, colors = colors
                )
                NavigationBarItem(
                    selected = selectedTab == 2, onClick = { selectedTab = 2 },
                    icon = { Icon(Icons.Rounded.Settings, "Ayarlar") }, label = { Text("Ayarlar") }, colors = colors
                )
            }
        }
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            when (selectedTab) {
                0 -> NashiWheelHome(
                    stagedInputs = stagedInputs,
                    busy = busy,
                    progress = progress,
                    latestResult = latestResult,
                    repository = repository,
                    onPickFiles = { multiFilePicker.launch(arrayOf("*/*")) },
                    onClearInputs = { onStageInputs(emptyList()) },
                    onAction = ::executeWheelAction,
                    onOpenWebDownload = { showWebDialog = true },
                    onScanQr = { qrImagePicker.launch("image/*") },
                    onOpenQrGen = { showQrGenDialog = true },
                    onImagesToPdf = { imagesToPdfPicker.launch(arrayOf("image/*")) },
                    onDismissResult = { latestResult = null }
                )
                1 -> NashiHistoryScreen(store = store, repository = repository)
                else -> NashiSettingsScreen(store = store, repository = repository)
            }
        }
    }

    // Web Download Dialog
    if (showWebDialog) {
        AlertDialog(
            onDismissRequest = { if (!busy) showWebDialog = false },
            containerColor = palette.surface,
            title = { Text("Linkten Medya / Dosya İndir", color = palette.textPrimary) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Doğrudan görsel, video, ses, PDF veya herkese açık sayfa bağlantısını yapıştır:", color = palette.textSecondary, fontSize = 12.5.sp)
                    OutlinedTextField(
                        value = webUrlInput,
                        onValueChange = { webUrlInput = it },
                        placeholder = { Text("https://…") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                Button(
                    enabled = webUrlInput.isNotBlank() && !busy,
                    onClick = {
                        val url = webUrlInput.trim()
                        showWebDialog = false
                        busy = true
                        progress = 0.05f
                        scope.launch {
                            val res = WebDownloadEngine.downloadMedia(url, repository.outputsDir) { p -> progress = p }
                            busy = false
                            progress = null
                            if (res != null) {
                                latestResult = repository.recordOutput("Web İndirme", res.file, res.mimeType)
                                repository.emitToast("İndirildi: ${res.file.name}")
                            } else {
                                repository.emitToast("Bağlantıdan medya indirilemedi")
                            }
                        }
                    }
                ) { Text("İndir") }
            },
            dismissButton = { TextButton(onClick = { showWebDialog = false }) { Text("İptal") } }
        )
    }

    // QR Generator Dialog
    if (showQrGenDialog) {
        AlertDialog(
            onDismissRequest = { showQrGenDialog = false },
            containerColor = palette.surface,
            title = { Text("QR Kod Üret", color = palette.textPrimary) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(
                        value = qrGenText,
                        onValueChange = { qrGenText = it },
                        placeholder = { Text("URL, metin veya Wi-Fi bilgisi…") },
                        minLines = 2,
                        maxLines = 4,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(selected = qrGenDark, onClick = { qrGenDark = true }, label = { Text("Edna Dark") })
                        FilterChip(selected = !qrGenDark, onClick = { qrGenDark = false }, label = { Text("Klasik Beyaz") })
                    }
                }
            },
            confirmButton = {
                Button(
                    enabled = qrGenText.isNotBlank(),
                    onClick = {
                        val content = qrGenText.trim()
                        val dark = qrGenDark
                        showQrGenDialog = false
                        busy = true
                        scope.launch {
                            val out = repository.newOutputFile("nashi_qr", "png")
                            val ok = QrEngine.generateQrPng(content, out, 1024, dark)
                            busy = false
                            if (ok) {
                                latestResult = repository.recordOutput("QR Kod Üret", out, "image/png")
                                repository.emitToast("QR kod oluşturuldu!")
                            }
                        }
                    }
                ) { Text("Üret") }
            },
            dismissButton = { TextButton(onClick = { showQrGenDialog = false }) { Text("İptal") } }
        )
    }

    // QR Scan Results Dialog
    if (qrScanResults != null) {
        val codes = qrScanResults.orEmpty()
        AlertDialog(
            onDismissRequest = { qrScanResults = null },
            containerColor = palette.surface,
            title = { Text("QR / Barkod Bulundu", color = palette.success) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    codes.forEach { code ->
                        Surface(
                            shape = RoundedCornerShape(10.dp),
                            color = palette.bg,
                            border = BorderStroke(1.dp, palette.border),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(code, color = palette.textPrimary, fontSize = 13.5.sp, modifier = Modifier.padding(12.dp))
                        }
                    }
                }
            },
            confirmButton = {
                Button(onClick = {
                    val firstCode = codes.firstOrNull().orEmpty()
                    val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    cm.setPrimaryClip(ClipData.newPlainText("Nashi QR", firstCode))
                    repository.emitToast("QR metni kopyalandı")
                    qrScanResults = null
                }) { Text("Kopyala") }
            },
            dismissButton = {
                val firstCode = codes.firstOrNull().orEmpty()
                if (firstCode.startsWith("http://", true) || firstCode.startsWith("https://", true)) {
                    TextButton(onClick = {
                        qrScanResults = null
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(firstCode)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    }) { Text("Linki Aç") }
                } else {
                    TextButton(onClick = { qrScanResults = null }) { Text("Kapat") }
                }
            }
        )
    }

    // Video / Audio In-Out Trim Dialog
    if (trimTarget != null) {
        val target = trimTarget!!
        val startMs = (trimRange.start * trimDurationMs).toLong()
        val endMs = (trimRange.endInclusive * trimDurationMs).toLong()
        AlertDialog(
            onDismissRequest = { trimTarget = null },
            containerColor = palette.surface,
            title = { Text(if (target.kind == NashiFileKind.AUDIO) "Ses Kes (In / Out)" else "Video Kes (Kayıpsız)", color = palette.textPrimary) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(target.name, color = palette.textSecondary, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("Aralık: ${fmtMs(startMs)} — ${fmtMs(endMs)} (Toplam: ${fmtMs(trimDurationMs)})", color = palette.pearGold, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    RangeSlider(
                        value = trimRange,
                        onValueChange = { if (it.endInclusive - it.start >= 0.02f) trimRange = it }
                    )
                }
            },
            confirmButton = {
                Button(onClick = {
                    trimTarget = null
                    busy = true
                    scope.launch {
                        val isAudio = target.kind == NashiFileKind.AUDIO
                        val out = repository.newOutputFile("${target.name}_kesik", if (isAudio) "m4a" else "mp4")
                        val ok = MediaEngine.remux(
                            context, target.uri, out,
                            startMs = startMs, endMs = endMs,
                            keepVideo = !isAudio, keepAudio = true
                        )
                        busy = false
                        if (ok) {
                            latestResult = repository.recordOutput(if (isAudio) "Ses Kes" else "Video Kes", out, if (isAudio) "audio/mp4" else "video/mp4")
                            repository.emitToast("Kayıpsız kesim tamamlandı!")
                        } else repository.emitToast("Kesim yapılamadı")
                    }
                }) { Text("Kes ve Kaydet") }
            },
            dismissButton = { TextButton(onClick = { trimTarget = null }) { Text("İptal") } }
        )
    }

    // PDF Split Page Range Dialog
    if (splitPdfTarget != null) {
        val target = splitPdfTarget!!
        AlertDialog(
            onDismissRequest = { splitPdfTarget = null },
            containerColor = palette.surface,
            title = { Text("PDF Sayfa Aralığı Böl ($splitPageCount sayfa)", color = palette.textPrimary) },
            text = {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(value = splitFrom, onValueChange = { splitFrom = it.filter(Char::isDigit) }, label = { Text("Başlangıç") }, singleLine = true, modifier = Modifier.weight(1f))
                    OutlinedTextField(value = splitTo, onValueChange = { splitTo = it.filter(Char::isDigit) }, label = { Text("Bitiş") }, singleLine = true, modifier = Modifier.weight(1f))
                }
            },
            confirmButton = {
                Button(onClick = {
                    val f = splitFrom.toIntOrNull() ?: 1
                    val t = splitTo.toIntOrNull() ?: splitPageCount
                    splitPdfTarget = null
                    busy = true
                    scope.launch {
                        val out = repository.newOutputFile("${target.name}_s${f}_${t}", "pdf")
                        val ok = PdfEngine.extractPageRange(context, target.uri, f, t, out)
                        busy = false
                        if (ok) {
                            latestResult = repository.recordOutput("PDF Böl ($f-$t)", out, "application/pdf")
                            repository.emitToast("PDF bölündü!")
                        } else repository.emitToast("PDF bölünemedi")
                    }
                }) { Text("Böl") }
            },
            dismissButton = { TextButton(onClick = { splitPdfTarget = null }) { Text("İptal") } }
        )
    }
}

@Composable
private fun NashiWheelHome(
    stagedInputs: List<StagedInput>,
    busy: Boolean,
    progress: Float?,
    latestResult: HistoryEntry?,
    repository: NashiRepository,
    onPickFiles: () -> Unit,
    onClearInputs: () -> Unit,
    onAction: (WheelAction) -> Unit,
    onOpenWebDownload: () -> Unit,
    onScanQr: () -> Unit,
    onOpenQrGen: () -> Unit,
    onImagesToPdf: () -> Unit,
    onDismissResult: () -> Unit
) {
    val palette = LocalNashiPalette.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        // Brand Header
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.weight(1f)) {
                Text("Nashi", color = palette.textPrimary, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                Text("Dosyaların için tatlı hız · Çarkla dönüştür", color = palette.textSecondary, fontSize = 12.5.sp)
            }
            if (stagedInputs.isNotEmpty()) {
                IconButton(onClick = onClearInputs) {
                    Icon(Icons.Rounded.Close, "Temizle", tint = palette.textSecondary)
                }
            }
        }

        // Latest Output Result Banner
        if (latestResult != null) {
            val file = File(latestResult.outputPath)
            Surface(
                shape = RoundedCornerShape(16.dp),
                color = palette.surface,
                border = BorderStroke(1.2.dp, palette.success.copy(alpha = 0.55f)),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("Hazır · ${latestResult.toolLabel}", color = palette.success, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            Text("${latestResult.outputFileName} (${formatBytes(latestResult.sizeBytes)})", color = palette.textPrimary, fontSize = 13.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        IconButton(onClick = onDismissResult, modifier = Modifier.size(28.dp)) {
                            Icon(Icons.Rounded.Close, "Kapat", tint = palette.textSecondary, modifier = Modifier.size(16.dp))
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = {
                                scope.launch {
                                    val saved = repository.saveToDeviceStorage(file, latestResult.mimeType)
                                    repository.emitToast(if (saved) "Galeri / İndirilenler'e kaydedildi!" else "Kaydedilemedi")
                                }
                            },
                            modifier = Modifier.weight(1f)
                        ) {
                            Icon(Icons.Rounded.SaveAlt, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Kaydet", fontSize = 12.5.sp)
                        }
                        OutlinedButton(
                            onClick = { repository.shareFile(context, file, latestResult.mimeType) },
                            modifier = Modifier.weight(1f)
                        ) {
                            Icon(Icons.Rounded.Share, null, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Paylaş", fontSize = 12.5.sp)
                        }
                    }
                }
            }
        }

        // Active Radial Conversion Wheel OR Pick File Hero
        if (stagedInputs.isNotEmpty()) {
            val first = stagedInputs.first()
            val actions = buildWheelActions(stagedInputs, palette)
            val centerTitle = if (stagedInputs.size == 1) first.name else "${stagedInputs.size} dosya seçildi"
            val centerSub = if (stagedInputs.size == 1 && first.sizeBytes > 0) formatBytes(first.sizeBytes) else first.kind.name

            Surface(
                shape = RoundedCornerShape(22.dp),
                color = palette.surface.copy(alpha = 0.65f),
                border = BorderStroke(1.dp, palette.border),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(vertical = 12.dp, horizontal = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text("Hedef işlemi seç", color = palette.pearGold, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    RadialConversionWheel(
                        centerTitle = centerTitle,
                        centerSubtitle = centerSub,
                        actions = actions,
                        busy = busy,
                        progress = progress,
                        onSelect = onAction
                    )
                    OutlinedButton(onClick = onPickFiles) {
                        Icon(Icons.Rounded.FolderOpen, null, modifier = Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Başka Dosya Seç")
                    }
                }
            }
        } else {
            Surface(
                onClick = onPickFiles,
                shape = RoundedCornerShape(22.dp),
                color = palette.surface,
                border = BorderStroke(1.5.dp, palette.pearGold.copy(alpha = 0.45f)),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 28.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Surface(shape = RoundedCornerShape(16.dp), color = palette.pearGold.copy(alpha = 0.16f)) {
                        Icon(Icons.Rounded.FolderOpen, null, tint = palette.pearGold, modifier = Modifier.padding(14.dp).size(34.dp))
                    }
                    Text("Dosya Seç veya Buraya Paylaş", color = palette.textPrimary, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                    Text(
                        "Görsel, video, ses veya PDF seç — Nashi çarkı anında açılsın. Herhangi bir uygulamadan \"Paylaş → Nashi\" de kullanabilirsin.",
                        color = palette.textSecondary,
                        fontSize = 12.5.sp,
                        lineHeight = 18.sp
                    )
                }
            }
        }

        // 4 Quick Tool Tiles
        Text("Hızlı Araçlar", color = palette.textSecondary, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            QuickTile(Icons.Rounded.Download, "Link İndir", "Görsel/Video/PDF", palette.accent, onOpenWebDownload, Modifier.weight(1f))
            QuickTile(Icons.Rounded.QrCodeScanner, "QR Oku", "Görselden tara", palette.success, onScanQr, Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            QuickTile(Icons.Rounded.QrCode2, "QR Üret", "1024px PNG", palette.pearGold, onOpenQrGen, Modifier.weight(1f))
            QuickTile(Icons.Rounded.PictureAsPdf, "Görsel → PDF", "Çoklu fotoğraf", palette.violet, onImagesToPdf, Modifier.weight(1f))
        }
    }
}

@Composable
private fun QuickTile(
    icon: ImageVector,
    title: String,
    subtitle: String,
    tint: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val palette = LocalNashiPalette.current
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(16.dp),
        color = palette.surface,
        border = BorderStroke(1.dp, palette.border),
        modifier = modifier
    ) {
        Row(modifier = Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(shape = RoundedCornerShape(11.dp), color = tint.copy(alpha = 0.16f)) {
                Icon(icon, title, tint = tint, modifier = Modifier.padding(9.dp).size(20.dp))
            }
            Spacer(Modifier.width(10.dp))
            Column {
                Text(title, color = palette.textPrimary, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold)
                Text(subtitle, color = palette.textSecondary, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun NashiHistoryScreen(store: NashiStore, repository: NashiRepository) {
    val palette = LocalNashiPalette.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text("Çıktılar", color = palette.textPrimary, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text("${store.history.size} işlenmiş dosya", color = palette.textSecondary, fontSize = 12.sp)
        Spacer(Modifier.height(12.dp))

        if (store.history.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Henüz dönüştürülmüş dosya yok.", color = palette.textSecondary)
            }
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp), contentPadding = PaddingValues(bottom = 16.dp)) {
                items(store.history, key = { it.id }) { entry ->
                    val file = File(entry.outputPath)
                    Surface(
                        shape = RoundedCornerShape(14.dp),
                        color = palette.surface,
                        border = BorderStroke(1.dp, palette.border),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(modifier = Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier.size(50.dp).clip(RoundedCornerShape(10.dp)).background(palette.elevated),
                                contentAlignment = Alignment.Center
                            ) {
                                if (entry.mimeType.startsWith("image/") && file.exists()) {
                                    AsyncImage(model = file, contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
                                } else {
                                    val ic = when {
                                        entry.mimeType.startsWith("video/") -> Icons.Rounded.VideoFile
                                        entry.mimeType.startsWith("audio/") -> Icons.Rounded.AudioFile
                                        entry.mimeType.contains("pdf") -> Icons.Rounded.PictureAsPdf
                                        else -> Icons.Rounded.Image
                                    }
                                    Icon(ic, null, tint = palette.pearGold)
                                }
                            }
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(entry.outputFileName, color = palette.textPrimary, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text("${entry.toolLabel} · ${formatBytes(entry.sizeBytes)}", color = palette.textSecondary, fontSize = 11.5.sp)
                            }
                            IconButton(onClick = {
                                scope.launch {
                                    val ok = repository.saveToDeviceStorage(file, entry.mimeType)
                                    repository.emitToast(if (ok) "Cihaza kaydedildi!" else "Kaydedilemedi")
                                }
                            }) {
                                Icon(Icons.Rounded.SaveAlt, "Kaydet", tint = palette.success)
                            }
                            IconButton(onClick = { repository.shareFile(context, file, entry.mimeType) }) {
                                Icon(Icons.Rounded.Share, "Paylaş", tint = palette.accent)
                            }
                            IconButton(onClick = { scope.launch { repository.deleteHistory(entry.id) } }) {
                                Icon(Icons.Rounded.Delete, "Sil", tint = palette.danger)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun NashiSettingsScreen(store: NashiStore, repository: NashiRepository) {
    val palette = LocalNashiPalette.current
    val scope = rememberCoroutineScope()
    var upd by remember { mutableStateOf(NashiUpdateInfo(BuildConfig.VERSION_NAME)) }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Ayarlar", color = palette.textPrimary, fontSize = 22.sp, fontWeight = FontWeight.Bold)

        Surface(shape = RoundedCornerShape(16.dp), color = palette.surface, border = BorderStroke(1.dp, palette.border), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Tema", color = palette.pearGold, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = store.theme == NashiThemeMode.EDNA, onClick = { scope.launch { repository.setTheme(NashiThemeMode.EDNA) } }, label = { Text("Edna Dark") })
                    FilterChip(selected = store.theme == NashiThemeMode.WARM, onClick = { scope.launch { repository.setTheme(NashiThemeMode.WARM) } }, label = { Text("Nashi Warm") })
                    FilterChip(selected = store.theme == NashiThemeMode.NEUTRAL, onClick = { scope.launch { repository.setTheme(NashiThemeMode.NEUTRAL) } }, label = { Text("Neutral") })
                }
            }
        }

        Surface(shape = RoundedCornerShape(16.dp), color = palette.surface, border = BorderStroke(1.dp, palette.border), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.SystemUpdate, null, tint = palette.accent)
                    Spacer(Modifier.width(10.dp))
                    Column {
                        Text("Nashi Android v${BuildConfig.VERSION_NAME}", color = palette.textPrimary, fontWeight = FontWeight.SemiBold)
                        Text(
                            when {
                                upd.checking -> "GitHub kontrol ediliyor…"
                                upd.error != null -> "Hata: ${upd.error}"
                                upd.latestVersion != null -> "Güncel (cdokuro/nashi-app)"
                                else -> "cdokuro/nashi-app"
                            },
                            color = palette.textSecondary, fontSize = 12.sp
                        )
                    }
                }
                OutlinedButton(
                    enabled = !upd.checking,
                    onClick = {
                        upd = upd.copy(checking = true, error = null)
                        scope.launch { upd = repository.checkGitHubUpdate() }
                    }
                ) {
                    if (upd.checking) {
                        CircularProgressIndicator(Modifier.size(15.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.width(6.dp))
                    }
                    Text("Güncellemeleri Denetle")
                }
            }
        }
    }
}

private fun buildWheelActions(inputs: List<StagedInput>, p: com.nashi.android.ui.theme.NashiPalette): List<WheelAction> {
    val first = inputs.first()
    return when (first.kind) {
        NashiFileKind.IMAGE -> listOf(
            WheelAction("img_jpg", "JPG", "", Icons.Rounded.Image, p.pearGold),
            WheelAction("img_png", "PNG", "", Icons.Rounded.AddPhotoAlternate, p.accent),
            WheelAction("img_webp", "WebP", "", Icons.Rounded.Transform, p.success),
            WheelAction("img_compress", "Sıkıştır", "", Icons.Rounded.Compress, p.danger),
            WheelAction("img_1080", "1080p", "", Icons.Rounded.PhotoSizeSelectLarge, p.violet),
            WheelAction("img_exif", "EXIF Sil", "", Icons.Rounded.PrivacyTip, p.success),
            WheelAction("img_rot90", "90° Döndür", "", Icons.Rounded.Rotate90DegreesCw, p.accent),
            WheelAction("img_pdf", "PDF Yap", "", Icons.Rounded.PictureAsPdf, p.pearGold),
            WheelAction("img_qr", "QR Oku", "", Icons.Rounded.QrCodeScanner, p.violet),
            WheelAction("img_gray", "Siyah-Beyaz", "", Icons.Rounded.FilterBAndW, p.textSecondary)
        )
        NashiFileKind.VIDEO -> listOf(
            WheelAction("trim_media", "Video Kes", "", Icons.Rounded.ContentCut, p.pearGold),
            WheelAction("vid_audio", "Ses Ayır", "", Icons.Rounded.AudioFile, p.success),
            WheelAction("vid_mute", "Sessize Al", "", Icons.Rounded.VolumeOff, p.danger),
            WheelAction("vid_frame", "Kare Al", "", Icons.Rounded.PhotoCamera, p.accent)
        )
        NashiFileKind.AUDIO -> listOf(
            WheelAction("trim_media", "Ses Kes", "", Icons.Rounded.ContentCut, p.pearGold)
        )
        NashiFileKind.PDF -> buildList {
            add(WheelAction("pdf_png", "PDF → PNG", "", Icons.Rounded.Image, p.success))
            add(WheelAction("pdf_jpg", "PDF → JPG", "", Icons.Rounded.AddPhotoAlternate, p.pearGold))
            add(WheelAction("pdf_split", "Sayfa Böl", "", Icons.Rounded.ContentCut, p.accent))
            if (inputs.count { it.kind == NashiFileKind.PDF } >= 2) {
                add(WheelAction("pdf_merge", "Birleştir", "", Icons.Rounded.PictureAsPdf, p.violet))
            }
        }
        else -> listOf(
            WheelAction("img_qr", "QR Oku", "", Icons.Rounded.QrCodeScanner, p.success)
        )
    }
}

private fun fmtMs(ms: Long): String {
    val totalSec = (ms / 1000L).coerceAtLeast(0L)
    val m = totalSec / 60
    val s = totalSec % 60
    return "%02d:%02d".format(m, s)
}
