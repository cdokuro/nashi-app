"""
Nashi Linux 2.0 - Main Window, Background Worker, Tray & Global Drag Integration
Ported from HomeView.swift, Views.swift, AppState.swift & MainWindow.cs.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any

# Ensure XCB platform on Wayland before Qt initializes
if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" and not os.environ.get("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import (
    QFont, QKeySequence, QShortcut, QAction, QCursor, QDesktopServices,
    QColor, QPalette
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFileDialog, QFrame,
    QListWidget, QListWidgetItem, QComboBox, QLineEdit, QSystemTrayIcon,
    QMenu, QScrollArea, QCheckBox, QInputDialog
)

from version import __version__
from engine import NashiEngine
from store import get_store, NashiStore
from floating_wheel import FloatingRadialWheel
from artwork import get_theme_palette, NashiArtwork, NashiMarkWidget, FileGardenWidget, THEMES
from toast_hud import NashiToastHUD, reveal_in_file_manager, copy_files_to_clipboard
from float_shelf import FloatShelfWindow
from editors import CropEditorDialog, ImageEditDialog, MediaTrimDialog
from web_download_dialog import WebDownloadDialog
from download_progress_dialog import DownloadProgressDialog
from tool_setup_dialog import ToolSetupDialog
from ipc_and_drag import (
    send_ipc_command,
    ensure_kde_xwayland_eavesdrop,
    register_kde_global_shortcuts,
    GlobalDragController,
    NashiIPCServer,
)


class ConversionWorker(QThread):
    """Background worker executing file conversions, 27 tools, and web downloads."""

    progress_updated = Signal(str, str, int)  # (title, detail, percent)
    finished = Signal(bool, str, str, list)  # (success, title, detail, output_paths)

    def __init__(
        self,
        engine: NashiEngine,
        store: NashiStore,
        mode: str,
        item_id: str,
        files: List[str],
        params: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.engine = engine
        self.store = store
        self.mode = mode
        self.item_id = item_id
        self.files = list(files)
        self.params = params or {}

    def run(self):
        out_dir = self.store.get_preference("default_output_dir", "")
        out_dir_opt = out_dir if (out_dir and str(out_dir).strip()) else None
        outputs: List[str] = []

        try:
            # 1. Web link actions
            if self.item_id.startswith("web:") or (self.files and self.engine.is_web_url(self.files[0])):
                url = self.files[0]
                sub_action = self.item_id.split(":", 1)[1] if ":" in self.item_id else "video"
                dl_dir = self.params.get("output_dir") or self.store.get_preference("download_dir", str(Path.home() / "Downloads"))
                max_h = self.params.get("max_height")
                fid = self.params.get("format_id")
                ref = self.params.get("referer")
                friendly_action = "MP3 İndiriliyor" if sub_action == "audio" else ("Görsel İndiriliyor" if sub_action == "thumbnail" else "Video İndiriliyor")
                out_file = self.engine.download_web_link(
                    url,
                    mode=sub_action,
                    max_height=max_h,
                    format_id=fid,
                    output_dir=dl_dir,
                    referer=ref,
                    progress_callback=lambda pct, msg: self.progress_updated.emit(friendly_action, msg, pct),
                )
                outputs.append(out_file)
                self.store.add_export(url, out_file, os.path.splitext(out_file)[1], action_title="Web İndirme")
                self.finished.emit(True, "Harika! Web medyası indirildi.", os.path.basename(out_file), outputs)
                return

            # 2. Format Conversions
            if self.mode == "convert":
                target_fmt = self.item_id.lower()
                total = len(self.files)
                for idx, fp in enumerate(self.files):
                    if not os.path.exists(fp):
                        continue
                    pct = int((idx + 1) * 100 / max(1, total))
                    self.progress_updated.emit(f"{target_fmt.upper()} Dönüştürülüyor…", os.path.basename(fp), pct)
                    out = self.engine.convert(fp, target_fmt, output_dir=out_dir_opt)
                    outputs.append(out)
                    self.store.add_export(
                        os.path.basename(fp),
                        out,
                        target_fmt,
                        action_title=f"→ {target_fmt.upper()}",
                    )
                if outputs:
                    title = f"Harika! {len(outputs)} dosya {target_fmt.upper()} formatına dönüştürüldü."
                    detail = os.path.basename(outputs[0]) if len(outputs) == 1 else f"{len(outputs)} dosya hazır"
                    self.finished.emit(True, title, detail, outputs)
                else:
                    self.finished.emit(False, "Dönüştürme yapılamadı", "Geçerli dosya bulunamadı.", [])
                return

            # 3. Tools (27 FeatureCatalog Tools)
            if self.mode == "tools":
                tool_id = self.item_id
                if tool_id == "readQRCode":
                    decoded_list = []
                    for fp in self.files:
                        decoded_list.append(self.engine.read_qr(fp))
                    joined = " | ".join(decoded_list)
                    self.finished.emit(True, "QR Kod Okundu (Panoya Kopyalandı)", joined, [])
                    return

                outputs = self.engine.execute_tool(
                    tool_id,
                    self.files,
                    output_dir=out_dir_opt,
                    params=self.params,
                )
                tool_title = self.engine.get_tool_name(tool_id, lang=self.store.get_preference("language", "tr"))
                for out in outputs:
                    src_label = os.path.basename(self.files[0]) if self.files else "Dosya"
                    ext = os.path.splitext(out)[1].lstrip(".") or "dir"
                    self.store.add_export(src_label, out, ext, action_title=tool_title)

                if outputs:
                    title = f"{tool_title} tamamlandı ({len(outputs)} çıktı)."
                    detail = os.path.basename(outputs[0])
                    self.finished.emit(True, title, detail, outputs)
                else:
                    self.finished.emit(False, f"{tool_title} başarısız", "Çıktı üretilemedi.", [])
                return

        except Exception as e:
            self.finished.emit(False, "İşlem Hatası", str(e), [])


class DropGardenCard(QFrame):
    """Interactive drop zone card on Home screen hosting FileGarden and selected file chips."""

    files_dropped = Signal(list)
    drag_modifier_triggered = Signal(str, list)  # (mode, files)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropGardenCard")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        files = []
        mime = event.mimeData()
        if mime.hasUrls():
            for u in mime.urls():
                if u.isLocalFile() and os.path.exists(u.toLocalFile()):
                    files.append(str(Path(u.toLocalFile()).resolve()))
        if files:
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self.drag_modifier_triggered.emit("convert", files)
            elif mods & Qt.KeyboardModifier.ControlModifier:
                self.drag_modifier_triggered.emit("tools", files)
            elif mods & Qt.KeyboardModifier.AltModifier:
                self.drag_modifier_triggered.emit("actions", files)
            else:
                self.files_dropped.emit(files)
            event.acceptProposedAction()


class NashiMainWindow(QMainWindow):
    """
    Main Nashi Desktop Window:
    - Top Navigation Bar (Nashi Mascot, Title, Home / Library pills, 'On your PC' privacy badge, Settings button)
    - Home Page: Hero header, DropGardenCard with selected-file chips, quick format/tool chips,
      Wheel trigger buttons (Shift Convert, Ctrl Tools, Alt File actions), Download a Link card,
      and 'Freshly made' recent exports section.
    - Library Page: Searchable 50-item history with Preview, Reuse, Copy, and Show in Folder.
    - Settings Page: 4 Themes, Wheel Finish & Scale, Drag Chords, Output Folder, Sound/Animations.
    """

    def __init__(self, start_hidden: bool = False):
        super().__init__()
        self.engine = NashiEngine()
        self.store = get_store()
        self.selected_files: List[str] = []
        self._active_worker: Optional[ConversionWorker] = None
        self._download_dlg: Optional[DownloadProgressDialog] = None

        self.setWindowTitle("Nashi")
        self.setWindowIcon(NashiArtwork.icon(64, happy=False))
        self.setMinimumSize(860, 640)
        self.resize(920, 700)

        # Floating modules
        self.floating_wheel = FloatingRadialWheel(engine=self.engine, store=self.store)
        self.floating_wheel.action_triggered.connect(self.handle_wheel_action)

        self.toast_hud = NashiToastHUD(theme=self.store.get_preference("theme", "dark"))
        self.float_shelf = FloatShelfWindow(theme=self.store.get_preference("theme", "dark"))
        self.float_shelf.files_sent_to_wheel.connect(self._on_shelf_send_to_wheel)

        # Dismiss timer after drag release so dropEvent can fire first
        self._drag_release_timer = QTimer(self)
        self._drag_release_timer.setSingleShot(True)
        self._drag_release_timer.setInterval(200)
        self._drag_release_timer.timeout.connect(self._on_drag_release_timeout)

        # Global Drag Controller & IPC Server
        self.drag_controller = GlobalDragController(store=self.store, parent=self)
        self.drag_controller.drag_wheel_requested.connect(self._on_global_drag_wheel)
        self.drag_controller.drag_mode_switched.connect(self._on_global_drag_mode_switched)
        self.drag_controller.drag_cursor_moved.connect(self._on_global_drag_cursor_moved)
        self.drag_controller.drag_released.connect(self._on_global_drag_released)

        self.ipc_server = NashiIPCServer(parent=self)
        self.ipc_server.command_received.connect(self._on_ipc_command)
        self.ipc_server.cursor_updated.connect(self.drag_controller.update_wayland_cursor)
        self.ipc_server.start()

        self._init_ui()
        self._init_shortcuts()
        self._init_tray()
        self.apply_theme(self.store.get_preference("theme", "dark"))
        self._refresh_home_selection()
        self._refresh_recent_exports()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(32, 22, 32, 18)
        root_layout.setSpacing(16)

        # 1. Top Navigation Bar (matching mac-home.png & windows-home-preview.png)
        nav = QHBoxLayout()
        nav.setSpacing(10)

        self.nav_mascot = NashiMarkWidget(size=38, happy=False)
        nav.addWidget(self.nav_mascot)

        self.lbl_brand = QLabel("Nashi")
        self.lbl_brand.setStyleSheet("font-size: 20px; font-weight: 800; letter-spacing: -0.5px;")
        nav.addWidget(self.lbl_brand)

        nav.addStretch()

        self.btn_nav_home = QPushButton("Ana Ekran")
        self.btn_nav_home.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_home.clicked.connect(lambda: self.switch_page(0))
        nav.addWidget(self.btn_nav_home)

        self.btn_nav_lib = QPushButton("Kütüphane")
        self.btn_nav_lib.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_lib.clicked.connect(lambda: self.switch_page(1))
        nav.addWidget(self.btn_nav_lib)

        self.lbl_privacy = QLabel("🔒 Bilgisayarında")
        self.lbl_privacy.setObjectName("PrivacyPill")
        nav.addWidget(self.lbl_privacy)

        self.btn_nav_settings = QPushButton("⚙ Ayarlar")
        self.btn_nav_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_settings.clicked.connect(lambda: self.switch_page(2))
        nav.addWidget(self.btn_nav_settings)

        root_layout.addLayout(nav)

        # 2. Stacked Pages (0: Home, 1: Library, 2: Settings)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_home_page())
        self.pages.addWidget(self._build_library_page())
        self.pages.addWidget(self._build_settings_page())
        root_layout.addWidget(self.pages, stretch=1)

        # 3. Subtle Footer
        footer = QHBoxLayout()
        self.lbl_footer_left = QLabel("🍃 Dosyaların için tatlı bir kolaylık. Akışını bozmadan.")
        self.lbl_footer_left.setStyleSheet("font-size: 11px;")
        footer.addWidget(self.lbl_footer_left)
        footer.addStretch()
        self.lbl_footer_right = QLabel("Dosyalar bilgisayarından dışarı çıkmaz · Yerel motor")
        self.lbl_footer_right.setStyleSheet("font-size: 11px;")
        footer.addWidget(self.lbl_footer_right)
        root_layout.addLayout(footer)

    def _build_home_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 4, 8)
        layout.setSpacing(18)

        # Hero Title
        hero_col = QVBoxLayout()
        hero_col.setSpacing(4)
        self.lbl_hero_title = QLabel("Dosyaların. Bir sonraki halleri.")
        self.lbl_hero_title.setStyleSheet("font-size: 28px; font-weight: 800; letter-spacing: -0.8px;")
        self.lbl_hero_sub = QLabel("Dönüştür, ince ayar yap ve yoluna devam et.")
        self.lbl_hero_sub.setStyleSheet("font-size: 13px;")
        hero_col.addWidget(self.lbl_hero_title)
        hero_col.addWidget(self.lbl_hero_sub)
        layout.addLayout(hero_col)

        # Main Drop Garden Card
        self.drop_card = DropGardenCard()
        self.drop_card.files_dropped.connect(self.set_selected_files)
        self.drop_card.drag_modifier_triggered.connect(self._on_drop_card_modifier)

        card_layout = QHBoxLayout(self.drop_card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(24)

        # Left column inside Drop Card
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        self.lbl_start_badge = QLabel("✦ BURADAN BAŞLA")
        self.lbl_start_badge.setObjectName("StartBadge")
        self.lbl_start_badge.setFixedWidth(135)
        left_col.addWidget(self.lbl_start_badge)

        self.lbl_drop_heading = QLabel("Güzel bir şey bırak.")
        self.lbl_drop_heading.setStyleSheet("font-size: 22px; font-weight: 800;")
        left_col.addWidget(self.lbl_drop_heading)

        self.lbl_drop_desc = QLabel("Görseller, videolar, belgeler, sesler ve aradaki her şey.")
        self.lbl_drop_desc.setStyleSheet("font-size: 13px;")
        self.lbl_drop_desc.setWordWrap(True)
        left_col.addWidget(self.lbl_drop_desc)

        # Selected files chip bar (visible when files are selected)
        self.chips_container = QWidget()
        self.chips_layout = QHBoxLayout(self.chips_container)
        self.chips_layout.setContentsMargins(0, 2, 0, 2)
        self.chips_layout.setSpacing(6)
        self.chips_container.hide()
        left_col.addWidget(self.chips_container)

        # Quick Formats & Tools bar (visible when files are selected)
        self.quick_picks_container = QWidget()
        self.quick_picks_layout = QHBoxLayout(self.quick_picks_container)
        self.quick_picks_layout.setContentsMargins(0, 2, 0, 2)
        self.quick_picks_layout.setSpacing(6)
        self.quick_picks_container.hide()
        left_col.addWidget(self.quick_picks_container)

        # Primary Action Buttons Row (Choose files + Paste + Clear)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_choose = QPushButton("＋ Dosya Seç")
        self.btn_choose.setObjectName("PrimaryGoldBtn")
        self.btn_choose.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_choose.clicked.connect(self.open_file_dialog)
        btn_row.addWidget(self.btn_choose)

        self.btn_paste = QPushButton("Yapıştır (Ctrl+V)")
        self.btn_paste.setObjectName("SecondaryCardBtn")
        self.btn_paste.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_paste.clicked.connect(self.paste_from_clipboard)
        btn_row.addWidget(self.btn_paste)

        self.btn_clear_sel = QPushButton("Temizle")
        self.btn_clear_sel.setObjectName("SecondaryCardBtn")
        self.btn_clear_sel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_sel.clicked.connect(lambda: self.set_selected_files([]))
        self.btn_clear_sel.hide()
        btn_row.addWidget(self.btn_clear_sel)

        btn_row.addStretch()
        left_col.addLayout(btn_row)

        # 3 Chord Pills Row (Shift Convert, Ctrl Tools, Alt File actions)
        chord_row = QHBoxLayout()
        chord_row.setSpacing(8)

        self.btn_chord_convert = QPushButton("⇧ Shift  Dönüştür")
        self.btn_chord_convert.setObjectName("ChordPillBtn")
        self.btn_chord_convert.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_chord_convert.clicked.connect(lambda: self.summon_wheel("convert"))
        chord_row.addWidget(self.btn_chord_convert)

        self.btn_chord_tools = QPushButton("⌃ Ctrl  Araçlar")
        self.btn_chord_tools.setObjectName("ChordPillBtn")
        self.btn_chord_tools.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_chord_tools.clicked.connect(lambda: self.summon_wheel("tools"))
        chord_row.addWidget(self.btn_chord_tools)

        self.btn_chord_actions = QPushButton("⌥ Alt  Dosya İşlemleri")
        self.btn_chord_actions.setObjectName("ChordPillBtn")
        self.btn_chord_actions.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_chord_actions.clicked.connect(lambda: self.summon_wheel("actions"))
        chord_row.addWidget(self.btn_chord_actions)

        chord_row.addStretch()
        left_col.addLayout(chord_row)
        card_layout.addLayout(left_col, stretch=3)

        # Right column inside Drop Card: FileGarden vector artwork + hint
        right_col = QVBoxLayout()
        right_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_col.setSpacing(6)

        self.file_garden = FileGardenWidget(theme=self.store.get_preference("theme", "dark"))
        right_col.addWidget(self.file_garden, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_garden_hint = QLabel("Dosya sürüklerken Shift/Ctrl/Alt basılı tut")
        self.lbl_garden_hint.setStyleSheet("font-size: 11px;")
        self.lbl_garden_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_col.addWidget(self.lbl_garden_hint)
        card_layout.addLayout(right_col, stretch=1)

        layout.addWidget(self.drop_card)

        # Download a Link Card (matching mac-home.png & windows-home-preview.png)
        self.link_card = QFrame()
        self.link_card.setObjectName("LinkCard")
        link_layout = QHBoxLayout(self.link_card)
        link_layout.setContentsMargins(20, 14, 20, 14)
        link_layout.setSpacing(14)

        lbl_dl_icon = QLabel("↓")
        lbl_dl_icon.setFixedSize(34, 34)
        lbl_dl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_dl_icon.setObjectName("GoldCircleIcon")
        link_layout.addWidget(lbl_dl_icon)

        dl_text_col = QVBoxLayout()
        dl_text_col.setSpacing(2)
        lbl_dl_title = QLabel("Bağlantıdan İndir (Download a link) & QR Oluştur")
        lbl_dl_title.setStyleSheet("font-size: 14px; font-weight: 700;")
        lbl_dl_sub = QLabel("Video, ses, görsel bağlantısı indir veya metinden anında QR kod üret.")
        lbl_dl_sub.setStyleSheet("font-size: 11px;")
        dl_text_col.addWidget(lbl_dl_title)
        dl_text_col.addWidget(lbl_dl_sub)
        link_layout.addLayout(dl_text_col, stretch=1)

        self.btn_qr_gen = QPushButton("🏁 QR Üret")
        self.btn_qr_gen.setObjectName("SecondaryCardBtn")
        self.btn_qr_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qr_gen.clicked.connect(self.prompt_generate_qr)
        link_layout.addWidget(self.btn_qr_gen)

        self.btn_dl_link = QPushButton("Bağlantı İndir (Ctrl+Shift+D)")
        self.btn_dl_link.setObjectName("SecondaryCardBtn")
        self.btn_dl_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dl_link.clicked.connect(self.prompt_download_link)
        link_layout.addWidget(self.btn_dl_link)

        layout.addWidget(self.link_card)

        # Freshly Made (Recent Exports preview on Home)
        fresh_hdr = QHBoxLayout()
        self.lbl_fresh_title = QLabel("Taze Çıktılar (Freshly made)")
        self.lbl_fresh_title.setStyleSheet("font-size: 17px; font-weight: 800;")
        fresh_hdr.addWidget(self.lbl_fresh_title)
        fresh_hdr.addStretch()

        self.btn_see_all = QPushButton("Tümünü Gör ↗")
        self.btn_see_all.setObjectName("SecondaryCardBtn")
        self.btn_see_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_see_all.clicked.connect(lambda: self.switch_page(1))
        fresh_hdr.addWidget(self.btn_see_all)
        layout.addLayout(fresh_hdr)

        self.home_recent_list = QListWidget()
        self.home_recent_list.setObjectName("RecentList")
        self.home_recent_list.setFixedHeight(130)
        self.home_recent_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.home_recent_list.itemDoubleClicked.connect(self._on_history_item_double_clicked)
        layout.addWidget(self.home_recent_list)

        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(14)

        hdr = QHBoxLayout()
        title_col = QVBoxLayout()
        lbl_t = QLabel("Nashi Kütüphanesi (Library)")
        lbl_t.setStyleSheet("font-size: 24px; font-weight: 800;")
        lbl_s = QLabel("Son 50 dışa aktarım ve araç işlemi. Çift tıklayarak açabilir veya yeniden kullanabilirsin.")
        lbl_s.setStyleSheet("font-size: 12px;")
        title_col.addWidget(lbl_t)
        title_col.addWidget(lbl_s)
        hdr.addLayout(title_col)
        hdr.addStretch()

        self.inp_lib_search = QLineEdit()
        self.inp_lib_search.setPlaceholderText("🔍 Kütüphanede ara (Ctrl+F)…")
        self.inp_lib_search.setFixedWidth(240)
        self.inp_lib_search.textChanged.connect(self._refresh_recent_exports)
        hdr.addWidget(self.inp_lib_search)
        layout.addLayout(hdr)

        self.lib_list = QListWidget()
        self.lib_list.setObjectName("RecentList")
        self.lib_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lib_list.itemDoubleClicked.connect(self._on_history_item_double_clicked)
        layout.addWidget(self.lib_list, stretch=1)

        act_row = QHBoxLayout()
        btn_reuse = QPushButton("↻ Seçili Dosyayı Ana Ekrana Al")
        btn_reuse.setObjectName("PrimaryGoldBtn")
        btn_reuse.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reuse.clicked.connect(self._reuse_selected_library_item)
        act_row.addWidget(btn_reuse)

        btn_reveal = QPushButton("📂 Klasörde Göster")
        btn_reveal.setObjectName("SecondaryCardBtn")
        btn_reveal.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reveal.clicked.connect(self._reveal_selected_library_item)
        act_row.addWidget(btn_reveal)

        btn_copy = QPushButton("📋 Dosyayı Kopyala")
        btn_copy.setObjectName("SecondaryCardBtn")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.clicked.connect(self._copy_selected_library_item)
        act_row.addWidget(btn_copy)

        btn_float = QPushButton("📎 Float Rafına Gönder")
        btn_float.setObjectName("SecondaryCardBtn")
        btn_float.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_float.clicked.connect(self._float_selected_library_item)
        act_row.addWidget(btn_float)

        act_row.addStretch()

        btn_clear = QPushButton("🗑 Geçmişi Temizle")
        btn_clear.setObjectName("SecondaryCardBtn")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_library_history)
        act_row.addWidget(btn_clear)

        layout.addLayout(act_row)
        return page

    def _build_settings_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 8, 8)
        layout.setSpacing(16)

        lbl_t = QLabel("Ayarlar & Kısayollar")
        lbl_t.setStyleSheet("font-size: 24px; font-weight: 800;")
        lbl_s = QLabel("Birkaç küçük tercih. Çok daha akıcı bir deneyim.")
        lbl_s.setStyleSheet("font-size: 12px;")
        layout.addWidget(lbl_t)
        layout.addWidget(lbl_s)

        # Appearance & Wheel Card
        card_app = QFrame()
        card_app.setObjectName("SettingsCard")
        c1 = QVBoxLayout(card_app)
        c1.setContentsMargins(20, 18, 20, 18)
        c1.setSpacing(12)

        row_theme = QHBoxLayout()
        row_theme.addWidget(QLabel("Görünüm Teması:"))
        self.cmb_theme = QComboBox()
        for t_key, t_data in THEMES.items():
            self.cmb_theme.addItem(t_data["name"], userData=t_key)
        cur_t = self.store.get_preference("theme", "dark")
        idx_t = max(0, self.cmb_theme.findData(cur_t))
        self.cmb_theme.setCurrentIndex(idx_t)
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_combo_changed)
        row_theme.addWidget(self.cmb_theme, stretch=1)
        c1.addLayout(row_theme)

        row_finish = QHBoxLayout()
        row_finish.addWidget(QLabel("Çark Yüzeyi (Wheel finish):"))
        self.cmb_finish = QComboBox()
        self.cmb_finish.addItem("Cam (Glass - Yarı Saydam)", userData="glass")
        self.cmb_finish.addItem("Metalik / Katı (Solid)", userData="metallic")
        cur_f = self.store.get_preference("wheel_finish", "glass")
        self.cmb_finish.setCurrentIndex(max(0, self.cmb_finish.findData(cur_f)))
        self.cmb_finish.currentIndexChanged.connect(
            lambda: self.store.set_preference("wheel_finish", self.cmb_finish.currentData())
        )
        row_finish.addWidget(self.cmb_finish, stretch=1)
        c1.addLayout(row_finish)

        row_scale = QHBoxLayout()
        row_scale.addWidget(QLabel("Çark Boyutu:"))
        self.cmb_scale = QComboBox()
        self.cmb_scale.addItem("Kompakt (300px)", userData=0.85)
        self.cmb_scale.addItem("Standart (350px - Önerilen)", userData=1.0)
        self.cmb_scale.addItem("Geniş (400px)", userData=1.15)
        self.cmb_scale.setCurrentIndex(1)
        self.cmb_scale.currentIndexChanged.connect(
            lambda: self.store.set_preference("wheel_scale", float(self.cmb_scale.currentData()))
        )
        row_scale.addWidget(self.cmb_scale, stretch=1)
        c1.addLayout(row_scale)

        layout.addWidget(card_app)

        # Drag Chords & Global Shortcuts Card
        card_sc = QFrame()
        card_sc.setObjectName("SettingsCard")
        c2 = QVBoxLayout(card_sc)
        c2.setContentsMargins(20, 18, 20, 18)
        c2.setSpacing(12)

        lbl_sc_hdr = QLabel("Sürükleme Tuşları (Drag Modifiers) & Global Kısayollar")
        lbl_sc_hdr.setStyleSheet("font-size: 15px; font-weight: 800;")
        c2.addWidget(lbl_sc_hdr)

        self.chk_drag_wheel = QCheckBox("Dosya sürüklerken tuşa basıldığında (Shift / Ctrl / Alt) yüzen çarkı otomatik aç")
        self.chk_drag_wheel.setChecked(bool(self.store.get_preference("drag_wheel_enabled", True)))
        self.chk_drag_wheel.toggled.connect(lambda v: self.store.set_preference("drag_wheel_enabled", bool(v)))
        c2.addWidget(self.chk_drag_wheel)

        mod_choices = ["Shift", "Ctrl", "Alt"]

        row_m1 = QHBoxLayout()
        row_m1.addWidget(QLabel("Dönüştürme Çarkı (Convert Wheel) Sürükleme Tuşu:"))
        self.cmb_mod_conv = QComboBox()
        self.cmb_mod_conv.addItems(mod_choices)
        self.cmb_mod_conv.setCurrentText(self.store.get_preference("convert_modifier", "Shift"))
        self.cmb_mod_conv.currentTextChanged.connect(lambda v: self._update_modifier("convert", v))
        row_m1.addWidget(self.cmb_mod_conv)
        c2.addLayout(row_m1)

        row_m2 = QHBoxLayout()
        row_m2.addWidget(QLabel("Araçlar Çarkı (Tools Wheel) Sürükleme Tuşu:"))
        self.cmb_mod_tools = QComboBox()
        self.cmb_mod_tools.addItems(mod_choices)
        self.cmb_mod_tools.setCurrentText(self.store.get_preference("tools_modifier", "Ctrl"))
        self.cmb_mod_tools.currentTextChanged.connect(lambda v: self._update_modifier("tools", v))
        row_m2.addWidget(self.cmb_mod_tools)
        c2.addLayout(row_m2)

        row_m3 = QHBoxLayout()
        row_m3.addWidget(QLabel("Dosya İşlemleri Çarkı (Actions Wheel) Sürükleme Tuşu:"))
        self.cmb_mod_act = QComboBox()
        self.cmb_mod_act.addItems(mod_choices)
        self.cmb_mod_act.setCurrentText(self.store.get_preference("actions_modifier", "Alt"))
        self.cmb_mod_act.currentTextChanged.connect(lambda v: self._update_modifier("actions", v))
        row_m3.addWidget(self.cmb_mod_act)
        c2.addLayout(row_m3)

        lbl_global_info = QLabel(
            "• Global Kısayollar (Her Yerde Çalışır):\n"
            "  - Shift+Space veya Alt+Shift+C  →  Dönüştürme Çarkı\n"
            "  - Ctrl+Space veya Alt+Shift+T   →  Araçlar Çarkı\n"
            "  - Alt+Space veya Alt+Shift+A    →  Dosya İşlemleri Çarkı\n"
            "  - Ctrl+Shift+D                  →  Kopyalanmış Bağlantıyı İndir\n"
            "  - Alt+Shift+N veya Meta+Space   →  Nashi Ana Pencere Aç/Gizle"
        )
        lbl_global_info.setStyleSheet("font-size: 12px; line-height: 1.5;")
        c2.addWidget(lbl_global_info)
        layout.addWidget(card_sc)

        # Output Location Card
        card_out = QFrame()
        card_out.setObjectName("SettingsCard")
        c3 = QVBoxLayout(card_out)
        c3.setContentsMargins(20, 18, 20, 18)
        c3.setSpacing(10)

        lbl_out_t = QLabel("Çıktı Klasörü")
        lbl_out_t.setStyleSheet("font-size: 15px; font-weight: 800;")
        c3.addWidget(lbl_out_t)

        out_row = QHBoxLayout()
        cur_out = self.store.get_preference("default_output_dir", "")
        self.lbl_out_dir = QLabel(cur_out if cur_out else "Orijinal dosyanın yanına kaydet (Tangerine / Nashi Varsayılanı)")
        out_row.addWidget(self.lbl_out_dir, stretch=1)

        btn_same_dir = QPushButton("Orijinalin Yanı")
        btn_same_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_same_dir.clicked.connect(self._set_output_same_as_source)
        out_row.addWidget(btn_same_dir)

        btn_pick_dir = QPushButton("Klasör Seç…")
        btn_pick_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pick_dir.clicked.connect(self._pick_output_dir)
        out_row.addWidget(btn_pick_dir)
        c3.addLayout(out_row)

        layout.addWidget(card_out)

        # Version & Parity Info Card
        card_ver = QFrame()
        card_ver.setObjectName("SettingsCard")
        c_ver = QVBoxLayout(card_ver)
        c_ver.setContentsMargins(20, 16, 20, 16)
        c_ver.setSpacing(10)
        lbl_v_title = QLabel(f"Nashi v{__version__} (Linux Native Port)")
        lbl_v_title.setStyleSheet("font-size: 14px; font-weight: 800;")
        lbl_v_desc = QLabel("macOS Nashi 2.0 & Tangerine ile %100 işlevsel ve görsel parite. Wayland/KWin desteği devrede.")
        lbl_v_desc.setStyleSheet("font-size: 12px; color: #888;")
        c_ver.addWidget(lbl_v_title)
        c_ver.addWidget(lbl_v_desc)

        btn_tools = QPushButton("🛠️ Araç Kurulumu & Bağımlılıklar (Tool Setup)…")
        btn_tools.setObjectName("SecondaryCardBtn")
        btn_tools.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_tools.clicked.connect(self.prompt_tool_setup)
        c_ver.addWidget(btn_tools, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(card_ver)

        layout.addStretch()

        scroll.setWidget(page)
        return scroll

    # ------------------------------------------------------------------
    # Shortcuts & System Tray
    # ------------------------------------------------------------------
    def _init_shortcuts(self):
        # Local window shortcuts matching DESKTOP-PARITY.md
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.open_file_dialog)
        QShortcut(QKeySequence("Ctrl+V"), self).activated.connect(self.paste_from_clipboard)
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(lambda: self.switch_page(0))
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(lambda: self.switch_page(1))
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(lambda: self.switch_page(2))
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_library_search)
        QShortcut(QKeySequence("Ctrl+Shift+D"), self).activated.connect(self.prompt_download_link)

        QShortcut(QKeySequence("Shift+Space"), self).activated.connect(lambda: self.summon_wheel("convert"))
        QShortcut(QKeySequence("Ctrl+Space"), self).activated.connect(lambda: self.summon_wheel("tools"))
        QShortcut(QKeySequence("Alt+Space"), self).activated.connect(lambda: self.summon_wheel("actions"))
        QShortcut(QKeySequence("Return"), self).activated.connect(lambda: self.summon_wheel("tools"))
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._on_escape_pressed)

    def _on_escape_pressed(self):
        if hasattr(self, "floating_wheel") and self.floating_wheel.isVisible():
            self.floating_wheel.drag_session_active = False
            self.floating_wheel.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if hasattr(self, "floating_wheel") and self.floating_wheel.isVisible():
                self.floating_wheel.drag_session_active = False
                self.floating_wheel.hide()
                event.accept()
                return
        super().keyPressEvent(event)

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(NashiArtwork.icon(64, happy=True))
        self.tray.setToolTip("Nashi — Dosyaların için tatlı bir kolaylık")

        menu = QMenu()
        act_open = QAction("🍐 Nashi Ana Pencere", self)
        act_open.triggered.connect(self.bring_to_front)
        menu.addAction(act_open)

        menu.addSeparator()

        act_conv = QAction("⇧ Dönüştürme Çarkı (Shift+Space)", self)
        act_conv.triggered.connect(lambda: self.summon_wheel("convert"))
        menu.addAction(act_conv)

        act_tools = QAction("⌃ Araçlar Çarkı (Ctrl+Space)", self)
        act_tools.triggered.connect(lambda: self.summon_wheel("tools"))
        menu.addAction(act_tools)

        act_actions = QAction("⌥ Dosya İşlemleri Çarkı (Alt+Space)", self)
        act_actions.triggered.connect(lambda: self.summon_wheel("actions"))
        menu.addAction(act_actions)

        act_float = QAction("📎 Yüzen Rafı (Float) Aç", self)
        act_float.triggered.connect(lambda: self.float_shelf.add_files(self.selected_files, show_shelf=True))
        menu.addAction(act_float)

        menu.addSeparator()
        act_quit = QAction("Çıkış", self)
        act_quit.triggered.connect(QApplication.instance().quit)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible() and self.isActiveWindow():
                self.hide()
            else:
                self.bring_to_front()

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()

    # ------------------------------------------------------------------
    # Global Drag Controller & IPC Callbacks
    # ------------------------------------------------------------------
    def _on_global_drag_wheel(self, mode: str, x: int, y: int):
        print(f"[NashiMain] _on_global_drag_wheel received: mode={mode} at ({x}, {y})", flush=True)
        self._drag_release_timer.stop()
        self.floating_wheel.pop_at_cursor(
            mode=mode,
            files=self.selected_files if self.selected_files else None,
            cursor_pos=(x, y),
            drag_mode=True,
        )

    def _on_global_drag_mode_switched(self, new_mode: str):
        if self.floating_wheel.isVisible():
            self.floating_wheel.switch_mode(new_mode)

    def _on_global_drag_cursor_moved(self, x: int, y: int):
        if self.floating_wheel.isVisible() and not self.floating_wheel.drag_session_active:
            self.floating_wheel.update_external_cursor(x, y)

    def _on_global_drag_released(self):
        # Give X11/XDND dropEvent 200ms to deliver the dropped file payload;
        # if the user released outside the wheel, auto-close it cleanly.
        self._drag_release_timer.start(200)

    def _on_drag_release_timeout(self):
        if self.floating_wheel.isVisible() and self.floating_wheel.drag_session_active:
            self.floating_wheel.drag_session_active = False
            self.floating_wheel.hide()

    def _on_ipc_command(self, cmd: str, mode: str, files: list, cursor_pos: object):
        if files:
            valid = [str(Path(f).resolve()) for f in files if os.path.exists(f)]
            if valid:
                self.set_selected_files(valid)

        coords = cursor_pos if isinstance(cursor_pos, tuple) else None

        if cmd == "toggle":
            if self.isVisible() and self.isActiveWindow():
                self.hide()
            else:
                self.bring_to_front()
        elif cmd == "download_link":
            self.bring_to_front()
            self.prompt_download_link()
        elif cmd == "float":
            self.float_shelf.add_files(self.selected_files, show_shelf=True)
        else:
            wheel_mode = mode if mode in ("convert", "tools", "actions") else "convert"
            self.summon_wheel(wheel_mode, cursor_pos=coords)

    # ------------------------------------------------------------------
    # Selection, Clipboard Paste & Quick Actions
    # ------------------------------------------------------------------
    def set_selected_files(self, file_paths: List[str]):
        valid = []
        for fp in file_paths:
            if fp and os.path.exists(fp):
                r = str(Path(fp).resolve())
                if r not in valid:
                    valid.append(r)
        self.selected_files = valid
        self.floating_wheel.current_files = list(valid)
        self._refresh_home_selection()

    def remove_selected_file(self, path_to_remove: str):
        self.selected_files = [p for p in self.selected_files if p != path_to_remove]
        self.floating_wheel.current_files = list(self.selected_files)
        self._refresh_home_selection()

    def _refresh_home_selection(self):
        has_sel = bool(self.selected_files)
        self.nav_mascot.set_happy(has_sel)
        self.file_garden.set_selected(has_sel)
        self.btn_clear_sel.setVisible(has_sel)

        # Clear existing chips
        while self.chips_layout.count():
            item = self.chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        while self.quick_picks_layout.count():
            item = self.quick_picks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not has_sel:
            self.lbl_hero_title.setText("Dosyaların. Bir sonraki halleri.")
            self.lbl_drop_heading.setText("Güzel bir şey bırak.")
            self.lbl_drop_desc.setText("Görseller, videolar, belgeler, sesler ve aradaki her şey.")
            self.chips_container.hide()
            self.quick_picks_container.hide()
            return

        self.lbl_hero_title.setText("Harika, şimdi şekillendirelim.")
        if len(self.selected_files) == 1:
            self.lbl_drop_heading.setText(os.path.basename(self.selected_files[0]))
        else:
            self.lbl_drop_heading.setText(f"{len(self.selected_files)} dosya seçildi")
        self.lbl_drop_desc.setText("Aşağıdan hızlı bir dönüşüm/araç seç veya çarkı aç.")

        # Build file chips (up to 4 shown + counter)
        for fp in self.selected_files[:4]:
            chip = QPushButton(f"📄 {os.path.basename(fp)[:20]}  ✕")
            chip.setObjectName("FileChipBtn")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(f"Kaldır: {fp}")
            chip.clicked.connect(lambda checked=False, p=fp: self.remove_selected_file(p))
            self.chips_layout.addWidget(chip)
        if len(self.selected_files) > 4:
            more_lbl = QLabel(f"+{len(self.selected_files) - 4} daha")
            more_lbl.setStyleSheet("font-size: 11px; font-weight: 600;")
            self.chips_layout.addWidget(more_lbl)
        self.chips_layout.addStretch()
        self.chips_container.show()

        # Build quick format & tool pick buttons right inside the card!
        targets = self.engine.get_available_targets_for_files(self.selected_files)[:5]
        tools = self.engine.get_available_tools_for_files(self.selected_files)[:3]

        for fmt in targets:
            b = QPushButton(f"→ {fmt.upper()}")
            b.setObjectName("QuickFormatBtn")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda checked=False, f=fmt: self.handle_wheel_action("convert", f, self.selected_files))
            self.quick_picks_layout.addWidget(b)

        for tid in tools:
            tname = self.engine.get_tool_name(tid)
            tsym = self.engine.get_tool_symbol(tid)
            b = QPushButton(f"{tsym} {tname}")
            b.setObjectName("QuickToolBtn")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda checked=False, t=tid: self.handle_wheel_action("tools", t, self.selected_files))
            self.quick_picks_layout.addWidget(b)

        self.quick_picks_layout.addStretch()
        self.quick_picks_container.show()

    def open_file_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Dosyaları Seç — Nashi",
            str(Path.home()),
            "Tüm Dosyalar (*.*)",
        )
        if files:
            self.set_selected_files(files)

    def paste_from_clipboard(self):
        """Matches Nashi's ClipboardImport.swift: imports copied files, images, text, or web links."""
        cb = QApplication.clipboard()
        mime = cb.mimeData()
        if not mime:
            return

        # 1. File URLs
        if mime.hasUrls():
            local_files = [u.toLocalFile() for u in mime.urls() if u.isLocalFile() and os.path.exists(u.toLocalFile())]
            if local_files:
                self.set_selected_files(local_files)
                self.toast_hud.show_success("Panodan dosya alındı", f"{len(local_files)} dosya seçildi", local_files, 2200)
                return

        # 2. Image in clipboard -> save lossless PNG in data_dir/imports
        if mime.hasImage():
            img = cb.image()
            if not img.isNull():
                imp_dir = self.store.data_dir / "imports"
                imp_dir.mkdir(parents=True, exist_ok=True)
                out_png = str(imp_dir / "clipboard_image.png")
                counter = 2
                while os.path.exists(out_png):
                    out_png = str(imp_dir / f"clipboard_image_{counter}.png")
                    counter += 1
                img.save(out_png, "PNG")
                self.set_selected_files([out_png])
                self.toast_hud.show_success("Panodan görsel aktarıldı", os.path.basename(out_png), [out_png], 2500)
                return

        # 3. Text or Web URL in clipboard
        if mime.hasText():
            txt = mime.text().strip()
            if not txt:
                return
            if self.engine.is_web_url(txt):
                self.prompt_download_link(initial_url=txt)
                return
            imp_dir = self.store.data_dir / "imports"
            imp_dir.mkdir(parents=True, exist_ok=True)
            out_txt = str(imp_dir / "clipboard_note.txt")
            counter = 2
            while os.path.exists(out_txt):
                out_txt = str(imp_dir / f"clipboard_note_{counter}.txt")
                counter += 1
            Path(out_txt).write_text(txt, encoding="utf-8")
            self.set_selected_files([out_txt])
            self.toast_hud.show_success("Panodan metin aktarıldı", os.path.basename(out_txt), [out_txt], 2500)

    def summon_wheel(self, mode: str = "convert", cursor_pos: Optional[tuple] = None):
        self.floating_wheel.pop_at_cursor(
            mode=mode,
            files=self.selected_files if self.selected_files else None,
            cursor_pos=cursor_pos,
            drag_mode=False,
        )

    def _on_drop_card_modifier(self, mode: str, files: List[str]):
        self.set_selected_files(files)
        self.summon_wheel(mode)

    def _on_shelf_send_to_wheel(self, files: List[str], mode: str):
        self.set_selected_files(files)
        self.summon_wheel(mode)

    # ------------------------------------------------------------------
    # Wheel Action & Tool Execution Handler
    # ------------------------------------------------------------------
    def handle_wheel_action(self, mode: str, item_id: str, payload_files: List[str]):
        files = payload_files if payload_files else list(self.selected_files)

        # Web actions
        if item_id.startswith("web:"):
            url = files[0] if files else ""
            if item_id == "web:copy":
                QApplication.clipboard().setText(url)
                self.toast_hud.show_success("Bağlantı kopyalandı", url, [], 2200)
                return
            if item_id == "web:open":
                QDesktopServices.openUrl(QUrl(url))
                return
            # Open interactive quality picker modal
            self.prompt_download_link(initial_url=url)
            return

        # Ensure we have files; if none, open file picker first
        if not files:
            picked, _ = QFileDialog.getOpenFileNames(
                self,
                f"İşlem İçin Dosya Seç ({item_id.upper()}) — Nashi",
                str(Path.home()),
                "Tüm Dosyalar (*.*)",
            )
            if not picked:
                return
            files = picked
            self.set_selected_files(files)
        else:
            self.set_selected_files(files)

        # 1. File Actions ('float', 'copy', 'move', 'copyPath', 'terminal', 'share')
        if mode == "actions":
            self._execute_file_action(item_id, files)
            return

        # 2. Interactive Editor Tools (open rich editor dialog first if single file)
        theme = self.store.get_preference("theme", "dark")
        params: Dict[str, Any] = {}

        if mode == "tools":
            if item_id == "cropImage" and len(files) >= 1:
                dlg = CropEditorDialog(files[0], theme=theme, parent=self)
                if dlg.exec() != CropEditorDialog.DialogCode.Accepted:
                    return
                params = dlg.get_crop_params()
            elif item_id in ("editImage", "frameImage", "annotateImage", "redactImage") and len(files) >= 1:
                dlg = ImageEditDialog(item_id, files[0], theme=theme, parent=self)
                if dlg.exec() != ImageEditDialog.DialogCode.Accepted:
                    return
                params = dlg.get_params()
            elif item_id in ("trimVideo", "trimAudio", "changeVideoSpeed") and len(files) >= 1:
                dur = self.engine.get_media_duration(files[0])
                dlg = MediaTrimDialog(item_id, files[0], duration=dur, theme=theme, parent=self)
                if dlg.exec() != MediaTrimDialog.DialogCode.Accepted:
                    return
                params = dlg.get_params()

        # 3. Start background conversion / tool worker with non-blocking ProgressToast
        self._start_worker(mode, item_id, files, params=params)

    def _execute_file_action(self, action_id: str, files: List[str]):
        if action_id == "float":
            self.float_shelf.add_files(files, show_shelf=True)
            self.toast_hud.show_success("Dosyalar Float Rafına eklendi", f"{len(files)} dosya rafta hazır", files, 2500)
            return

        if action_id == "copy":
            copy_files_to_clipboard(files)
            self.toast_hud.show_success("Panoya kopyalandı", f"{len(files)} dosya yapıştırmaya hazır (Ctrl+V)", files, 2800)
            return

        if action_id == "copyPath":
            QApplication.clipboard().setText("\n".join(files))
            self.toast_hud.show_success("Dosya yolu kopyalandı", files[0], files, 2500)
            return

        if action_id == "share":
            reveal_in_file_manager(files)
            return

        if action_id == "terminal":
            folder = files[0] if os.path.isdir(files[0]) else os.path.dirname(files[0])
            for term in ("konsole", "kitty", "alacritty", "gnome-terminal", "xterm"):
                if shutil.which(term):
                    subprocess.Popen([term, "--workdir", folder] if term == "konsole" else [term], cwd=folder)
                    self.toast_hud.show_success("Terminal açıldı", folder, [], 2200)
                    return
            subprocess.Popen(["xdg-open", folder])
            return

        if action_id == "move":
            dest_dir = QFileDialog.getExistingDirectory(self, "Dosyaları Taşıyacağınız Klasörü Seçin", str(Path.home()))
            if not dest_dir:
                return
            moved = []
            for fp in files:
                target = Path(dest_dir) / os.path.basename(fp)
                counter = 2
                while target.exists():
                    stem, ext = os.path.splitext(os.path.basename(fp))
                    target = Path(dest_dir) / f"{stem}_{counter}{ext}"
                    counter += 1
                shutil.move(fp, str(target))
                moved.append(str(target))
            self.set_selected_files(moved)
            self.toast_hud.show_success("Dosyalar taşındı", dest_dir, moved, 3200)

    def _start_worker(self, mode: str, item_id: str, files: List[str], params: Optional[Dict[str, Any]] = None):
        friendly_map = {
            "web:video": "Video İndirme",
            "web:audio": "MP3 Ses İndirme",
            "web:thumbnail": "Kapak Görseli İndirme",
            "web:copy": "Bağlantı Kopyalama",
            "web:open": "Tarayıcıda Açma",
        }
        if item_id in friendly_map:
            label = friendly_map[item_id]
        elif mode == "convert":
            label = f"{item_id.upper()} Dönüştürme"
        else:
            label = self.engine.get_tool_name(item_id, lang=self.store.get_preference("language", "tr"))

        detail_txt = ""
        if files:
            first_f = files[0]
            if self.engine.is_web_url(first_f):
                parsed = urllib.parse.urlparse(first_f)
                name = os.path.basename(parsed.path) or parsed.netloc
                detail_txt = f"{name[:28]}…" if len(name) > 28 else name
            else:
                detail_txt = os.path.basename(first_f)

        self.toast_hud.show_progress(
            f"Nashi çalışıyor: {label}…",
            detail_txt,
            percent=0,
        )
        self._active_worker = ConversionWorker(
            self.engine,
            self.store,
            mode=mode,
            item_id=item_id,
            files=files,
            params=params,
        )
        self._active_worker.progress_updated.connect(
            lambda title, detail, pct: self.toast_hud.show_progress(title, detail, percent=pct)
        )

        if mode == "web" or item_id.startswith("web:"):
            if not self._download_dlg or not self._download_dlg.isVisible():
                first_url = files[0] if files else ""
                out_d = (params or {}).get("output_dir", "")
                self._download_dlg = DownloadProgressDialog(
                    title=label,
                    url=first_url,
                    dest_dir=out_d,
                    parent=self,
                )
                self._download_dlg.show()
                self._download_dlg.raise_()

        if self._download_dlg:
            self._active_worker.progress_updated.connect(self._download_dlg.update_progress)
            self._download_dlg.canceled.connect(self._cancel_active_worker)

        self._active_worker.finished.connect(self._on_worker_finished)
        self._active_worker.start()

    def _cancel_active_worker(self):
        if self._active_worker and self._active_worker.isRunning():
            try:
                self._active_worker.terminate()
            except Exception:
                pass
            self.toast_hud.show_error("İptal Edildi", "İndirme kullanıcı tarafından durduruldu.", duration_ms=2500)

    def _on_worker_finished(self, success: bool, title: str, detail: str, outputs: list):
        if self._download_dlg:
            self._download_dlg.set_completed(success, title, detail, outputs)

        if success:
            if not outputs and detail:
                # e.g., QR code decoded text
                QApplication.clipboard().setText(detail)
            self.toast_hud.show_success(title, detail, files=outputs, duration_ms=4200)
            self._refresh_recent_exports()
        else:
            self.toast_hud.show_error(title, detail, duration_ms=5200)

    def prompt_tool_setup(self):
        dlg = ToolSetupDialog(self.engine, parent=self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Link Download & QR Generation Prompts
    # ------------------------------------------------------------------
    def prompt_download_link(self, initial_url: str = ""):
        cb_text = QApplication.clipboard().text().strip()
        url = initial_url or (cb_text if self.engine.is_web_url(cb_text) else "")
        dlg = WebDownloadDialog(self.engine, parent=self, initial_url=url)
        dlg.download_requested.connect(self._on_web_download_requested)
        dlg.exec()

    def _on_web_download_requested(self, url: str, mode: str, max_height: int, format_id: str, out_dir: str):
        item_id = f"web:{mode}"
        params = {
            "output_dir": out_dir,
            "max_height": max_height if max_height > 0 else None,
            "format_id": format_id if format_id not in ("best", "direct") else None,
        }
        # Check if the active dialog resolved an internal stream URL & referer
        active_dlg = self.findChild(WebDownloadDialog)
        title_hint = "Web Medyası"
        if active_dlg and active_dlg._current_info:
            stream_url = active_dlg._current_info.get("url")
            ref = active_dlg._current_info.get("referer")
            title_hint = active_dlg._current_info.get("title") or title_hint
            is_portal = any(d in url.lower() for d in [
                "youtube.com", "youtu.be", "twitter.com", "x.com",
                "instagram.com", "tiktok.com", "reddit.com", "vimeo.com", "twitch.tv"
            ])
            if stream_url and stream_url.startswith("http") and not is_portal:
                url = stream_url
            if ref:
                params["referer"] = ref

        # Small dedicated download window
        self._download_dlg = DownloadProgressDialog(
            title=title_hint,
            url=url,
            dest_dir=out_dir,
            parent=self,
        )
        self._download_dlg.show()
        self._download_dlg.raise_()

        self._start_worker("web", item_id, [url], params=params)

    def prompt_generate_qr(self):
        cb_text = QApplication.clipboard().text().strip()
        text, ok = QInputDialog.getText(
            self,
            "QR Kod Oluştur — Nashi",
            "QR koda dönüştürülecek metin veya URL:",
            QLineEdit.EchoMode.Normal,
            cb_text[:200],
        )
        if ok and text.strip():
            out_dir = self.store.get_preference("default_output_dir", "") or str(Path.home() / "Downloads")
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            out_path = str(Path(out_dir) / "nashi_qr.png")
            counter = 2
            while os.path.exists(out_path):
                out_path = str(Path(out_dir) / f"nashi_qr_{counter}.png")
                counter += 1
            try:
                generated = self.engine.generate_qr(text.strip(), output_path=out_path)
                self.store.add_export("QR Kod", generated, "png", action_title="QR Kod Üret")
                self._refresh_recent_exports()
                self.toast_hud.show_success("QR Kod oluşturuldu!", os.path.basename(generated), [generated], 4000)
            except Exception as e:
                self.toast_hud.show_error("QR Hatası", str(e))

    # ------------------------------------------------------------------
    # Library & History Management
    # ------------------------------------------------------------------
    def _refresh_recent_exports(self):
        query = self.inp_lib_search.text().strip() if hasattr(self, "inp_lib_search") else ""
        all_exports = self.store.get_recent_exports(query=query)

        # Populate Home recent list (top 4)
        self.home_recent_list.clear()
        for exp in all_exports[:4]:
            self.home_recent_list.addItem(self._make_history_list_item(exp))
        if not all_exports:
            empty_it = QListWidgetItem("Henüz işlem yapılmadı. Yukarıya bir dosya bırakarak başlayın.")
            self.home_recent_list.addItem(empty_it)

        # Populate Library full list (up to 50)
        self.lib_list.clear()
        for exp in all_exports:
            self.lib_list.addItem(self._make_history_list_item(exp))
        self.lbl_fresh_title.setText(f"Taze Çıktılar (Freshly made) · {len(all_exports)}")

    def _make_history_list_item(self, exp: Dict[str, Any]) -> QListWidgetItem:
        src = exp.get("source_name", "Dosya")
        out_path = exp.get("output_path", "")
        out_name = os.path.basename(out_path) if out_path else ""
        act = exp.get("action_title") or f"→ {exp.get('format', '').upper()}"
        size_kb = max(1, int(exp.get("file_size", 0)) // 1024)
        exists = exp.get("exists", os.path.exists(out_path))
        status = "✓ Hazır" if exists else "⚠ Dosya Taşınmış/Silinmiş"

        text = f"🍐  {src}   [{act}]   →   {out_name}   ({size_kb} KB · {status})"
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, out_path)
        item.setToolTip(out_path)
        return item

    def _on_history_item_double_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _selected_library_path(self) -> Optional[str]:
        item = self.lib_list.currentItem()
        if not item:
            return None
        path = item.data(Qt.ItemDataRole.UserRole)
        return path if (path and os.path.exists(path)) else None

    def _reuse_selected_library_item(self):
        p = self._selected_library_path()
        if p:
            self.set_selected_files([p])
            self.switch_page(0)

    def _reveal_selected_library_item(self):
        p = self._selected_library_path()
        if p:
            reveal_in_file_manager([p])

    def _copy_selected_library_item(self):
        p = self._selected_library_path()
        if p:
            copy_files_to_clipboard([p])
            self.toast_hud.show_success("Panoya kopyalandı", os.path.basename(p), [p], 2200)

    def _float_selected_library_item(self):
        p = self._selected_library_path()
        if p:
            self.float_shelf.add_files([p], show_shelf=True)

    def _clear_library_history(self):
        self.store.clear_history()
        self._refresh_recent_exports()

    def _focus_library_search(self):
        self.switch_page(1)
        self.inp_lib_search.setFocus()

    # ------------------------------------------------------------------
    # Navigation, Settings & Theme Styling
    # ------------------------------------------------------------------
    def switch_page(self, idx: int):
        self.pages.setCurrentIndex(idx)
        pal = get_theme_palette(self.store.get_preference("theme", "dark"))
        for i, btn in enumerate((self.btn_nav_home, self.btn_nav_lib, self.btn_nav_settings)):
            if i == idx:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {pal['sage']};
                        color: {pal['gold']};
                        border: 1px solid {pal['gold']};
                        border-radius: 12px;
                        padding: 6px 14px;
                        font-size: 12px;
                        font-weight: 800;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {pal['surface']};
                        color: {pal['ink']};
                        border: 1px solid {pal['line']};
                        border-radius: 12px;
                        padding: 6px 14px;
                        font-size: 12px;
                        font-weight: 600;
                    }}
                    QPushButton:hover {{ border-color: {pal['gold']}; }}
                """)

    def _on_theme_combo_changed(self):
        t_key = self.cmb_theme.currentData()
        if t_key:
            self.store.set_preference("theme", t_key)
            self.apply_theme(t_key)

    def _update_modifier(self, wheel_kind: str, mod: str):
        self.store.set_drag_modifier(wheel_kind, mod)
        # Refresh combos to reflect any automatic swap
        self.cmb_mod_conv.blockSignals(True)
        self.cmb_mod_tools.blockSignals(True)
        self.cmb_mod_act.blockSignals(True)
        self.cmb_mod_conv.setCurrentText(self.store.get_preference("convert_modifier", "Shift"))
        self.cmb_mod_tools.setCurrentText(self.store.get_preference("tools_modifier", "Ctrl"))
        self.cmb_mod_act.setCurrentText(self.store.get_preference("actions_modifier", "Alt"))
        self.cmb_mod_conv.blockSignals(False)
        self.cmb_mod_tools.blockSignals(False)
        self.cmb_mod_act.blockSignals(False)

        c_m = self.store.get_preference("convert_modifier", "Shift")
        t_m = self.store.get_preference("tools_modifier", "Ctrl")
        a_m = self.store.get_preference("actions_modifier", "Alt")
        self.btn_chord_convert.setText(f"{c_m}  Dönüştür")
        self.btn_chord_tools.setText(f"{t_m}  Araçlar")
        self.btn_chord_actions.setText(f"{a_m}  Dosya İşlemleri")

    def _set_output_same_as_source(self):
        self.store.set_preference("default_output_dir", "")
        self.lbl_out_dir.setText("Orijinal dosyanın yanına kaydet (Tangerine / Nashi Varsayılanı)")

    def _pick_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Varsayılan Çıktı Klasörü Seç", str(Path.home()))
        if folder:
            self.store.set_preference("default_output_dir", folder)
            self.lbl_out_dir.setText(folder)

    def apply_theme(self, theme_name: str):
        pal = get_theme_palette(theme_name)
        self.file_garden.set_theme(theme_name)
        self.toast_hud.set_theme(theme_name)
        self.float_shelf.set_theme(theme_name)
        self.floating_wheel.wheel.set_theme(theme_name, finish=self.store.get_preference("wheel_finish", "glass"))

        # Match title bar / frame color with app background for KWin / Wayland / X11 window managers
        qpal = self.palette()
        bg_col = QColor(pal['paper'])
        qpal.setColor(QPalette.ColorRole.Window, bg_col)
        qpal.setColor(QPalette.ColorRole.Base, bg_col)
        qpal.setColor(QPalette.ColorRole.WindowText, QColor(pal['ink']))
        self.setPalette(qpal)
        app_inst = QApplication.instance()
        if app_inst:
            app_inst.setPalette(qpal)

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {pal['paper']};
                color: {pal['ink']};
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Noto Sans', sans-serif;
            }}
            /* Apple-grade soft minimalist scrollbars */
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.18);
                min-height: 28px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {pal['gold']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
                border: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}

            QScrollBar:horizontal {{
                border: none;
                background: transparent;
                height: 6px;
                margin: 0px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal {{
                background: rgba(255, 255, 255, 0.18);
                min-width: 28px;
                border-radius: 3px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {pal['gold']};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: none;
                border: none;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}
            QLabel {{
                background: transparent;
                color: {pal['ink']};
            }}
            #PrivacyPill {{
                background-color: {pal['inset']};
                color: {pal['muted']};
                border: 1px solid {pal['line']};
                border-radius: 14px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.2px;
            }}
            #DropGardenCard, #LinkCard, #SettingsCard {{
                background-color: {pal['surface']};
                border: 1px solid {pal['line']};
                border-radius: 20px;
            }}
            #StartBadge {{
                background-color: {pal['sand']};
                color: {pal['gold']};
                border-radius: 8px;
                padding: 4px 9px;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.8px;
            }}
            #PrimaryGoldBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {pal['gold']}, stop:1 {pal['gold_end']});
                color: {pal['button_ink']};
                border: none;
                border-radius: 12px;
                padding: 10px 22px;
                font-size: 13px;
                font-weight: 700;
            }}
            #PrimaryGoldBtn:hover {{
                background: {pal['gold_end']};
            }}
            #SecondaryCardBtn {{
                background-color: {pal['inset']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 11px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            #SecondaryCardBtn:hover {{
                border-color: {pal['gold']};
                color: {pal['gold']};
                background-color: {pal['surface']};
            }}
            #ChordPillBtn {{
                background-color: {pal['sage']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 11px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 700;
            }}
            #ChordPillBtn:hover {{
                background-color: {pal['gold']};
                color: {pal['button_ink']};
                border-color: {pal['gold']};
            }}
            #FileChipBtn {{
                background-color: {pal['inset']};
                color: {pal['gold']};
                border: 1px solid {pal['gold']};
                border-radius: 10px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }}
            #QuickFormatBtn {{
                background-color: {pal['sand']};
                color: {pal['gold']};
                border: 1px solid {pal['gold']};
                border-radius: 9px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 800;
            }}
            #QuickFormatBtn:hover {{
                background-color: {pal['gold']};
                color: {pal['button_ink']};
            }}
            #QuickToolBtn {{
                background-color: {pal['sage']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 9px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 700;
            }}
            #QuickToolBtn:hover {{
                border-color: {pal['gold']};
                color: {pal['gold']};
            }}
            #GoldCircleIcon {{
                background-color: {pal['gold']};
                color: {pal['button_ink']};
                border-radius: 17px;
                font-size: 16px;
                font-weight: 900;
            }}
            #RecentList {{
                background-color: {pal['surface']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 16px;
                padding: 8px;
                font-size: 12px;
            }}
            #RecentList::item {{
                padding: 9px 12px;
                border-radius: 10px;
                margin-bottom: 3px;
            }}
            #RecentList::item:selected, #RecentList::item:hover {{
                background-color: {pal['sage']};
                color: {pal['gold']};
            }}
            QLineEdit, QComboBox {{
                background-color: {pal['inset']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 10px;
                padding: 7px 12px;
                font-size: 12px;
            }}
            QCheckBox {{
                color: {pal['ink']};
                font-size: 13px;
                spacing: 8px;
            }}
        """)
        self.switch_page(self.pages.currentIndex())


def main():
    args = sys.argv[1:]
    if "--version" in args or "-v" in args:
        print(f"Nashi v{__version__} (Linux Native Port)")
        return
    file_args = [str(Path(a).resolve()) for a in args if not a.startswith("-") and os.path.exists(a)]

    # Determine requested mode from CLI flags
    req_cmd = ""
    req_mode = "convert"
    if "--convert" in args or "--wheel" in args:
        req_cmd = "wheel"
        req_mode = "convert"
    elif "--tools" in args:
        req_cmd = "wheel"
        req_mode = "tools"
    elif "--actions" in args:
        req_cmd = "wheel"
        req_mode = "actions"
    elif "--toggle" in args:
        req_cmd = "toggle"
    elif "--float" in args:
        req_cmd = "float"
    elif "--download-link" in args:
        req_cmd = "download_link"

    # If an instance of Nashi is already running, forward the command over IPC socket and exit immediately!
    if req_cmd and send_ipc_command(req_cmd, mode=req_mode, files=file_args):
        return
    if not req_cmd and file_args and send_ipc_command("wheel", mode="convert", files=file_args):
        return

    # Configure KDE Wayland XWayland eavesdrop & global shortcuts
    nashi_bin = str((Path(__file__).resolve().parent / "nashi").resolve())
    ensure_kde_xwayland_eavesdrop()
    register_kde_global_shortcuts(nashi_bin)

    app = QApplication(sys.argv)
    app.setApplicationName("Nashi")
    app.setQuitOnLastWindowClosed(False)

    start_hidden = ("--daemon" in args) or bool(req_cmd == "wheel")
    window = NashiMainWindow(start_hidden=start_hidden)
    if file_args:
        window.set_selected_files(file_args)

    if req_cmd == "wheel":
        window.hide()
        QTimer.singleShot(80, lambda: window.summon_wheel(req_mode))
    elif req_cmd == "float":
        window.hide()
        QTimer.singleShot(80, lambda: window.float_shelf.add_files(file_args, show_shelf=True))
    elif "--daemon" in args:
        window.hide()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
