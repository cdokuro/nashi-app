"""
Nashi Linux - Web Media Probing & Quality Picker Dialog (IDM / macOS WebDownloadView Parity)
Provides live URL inspection, thumbnail previews, format & resolution selection,
and direct download execution into the user's chosen folder.
"""

import os
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QPixmap, QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QFrame, QProgressBar, QStackedWidget,
    QApplication, QGraphicsDropShadowEffect
)

from artwork import get_theme_palette
from store import get_store


class InspectWorker(QThread):
    """Background inspection thread so GUI remains responsive while probing media URLs."""
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, engine, url: str):
        super().__init__()
        self.engine = engine
        self.url = url

    def run(self):
        try:
            info = self.engine.inspect_web_link(self.url)
            self.finished.emit(info)
        except Exception as e:
            self.failed.emit(str(e))


class WebDownloadDialog(QDialog):
    """Interactive IDM-style download dialog with media probing and quality options."""
    download_requested = Signal(str, str, int, str, str)  # (url, mode, max_height, format_id, out_dir)

    def __init__(self, engine, parent=None, initial_url: str = ""):
        super().__init__(parent)
        self.engine = engine
        self.store = get_store()
        self.theme_pal = get_theme_palette(self.store.get_preference("theme", "warm_sand"))
        self._current_info: Optional[Dict[str, Any]] = None
        self._worker: Optional[InspectWorker] = None

        self.setWindowTitle("Web Medyası İndir — Nashi")
        self.setMinimumWidth(520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._init_ui()
        self._apply_style()

        if initial_url.strip():
            self.inp_url.setText(initial_url.strip())
            QTimer.singleShot(100, self.start_inspection)
        else:
            # Check clipboard for valid media URL
            cb = QApplication.clipboard().text().strip()
            if cb and self.engine.is_web_url(cb):
                self.inp_url.setText(cb)
                QTimer.singleShot(100, self.start_inspection)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(16)

        # Header
        h_row = QHBoxLayout()
        h_icon = QLabel("🎬")
        h_icon.setStyleSheet("font-size: 26px;")
        h_row.addWidget(h_icon)

        v_titles = QVBoxLayout()
        lbl_title = QLabel("Web Medyası & Video İndirici")
        lbl_title.setStyleSheet("font-size: 17px; font-weight: 800;")
        lbl_sub = QLabel("Bağlantıyı analiz et, çözünürlüğü seç ve doğrudan indir.")
        lbl_sub.setStyleSheet("font-size: 12px; color: #888;")
        v_titles.addWidget(lbl_title)
        v_titles.addWidget(lbl_sub)
        h_row.addLayout(v_titles)
        h_row.addStretch()
        root.addLayout(h_row)

        # URL Input Row
        url_frame = QFrame()
        url_frame.setObjectName("UrlBox")
        u_box = QHBoxLayout(url_frame)
        u_box.setContentsMargins(10, 6, 10, 6)
        u_box.setSpacing(8)

        self.inp_url = QLineEdit()
        self.inp_url.setPlaceholderText("YouTube, video veya web medya bağlantısını buraya yapıştırın…")
        self.inp_url.setStyleSheet("border: none; background: transparent; font-size: 13px;")
        self.inp_url.returnPressed.connect(self.start_inspection)
        u_box.addWidget(self.inp_url, stretch=1)

        btn_paste = QPushButton("Yapıştır")
        btn_paste.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_paste.clicked.connect(self._paste_clipboard)
        u_box.addWidget(btn_paste)

        self.btn_inspect = QPushButton("Analiz Et")
        self.btn_inspect.setObjectName("PrimaryButton")
        self.btn_inspect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_inspect.clicked.connect(self.start_inspection)
        u_box.addWidget(self.btn_inspect)
        root.addWidget(url_frame)

        # Inspection Progress Bar (Indeterminate)
        self.prog_inspect = QProgressBar()
        self.prog_inspect.setRange(0, 0)
        self.prog_inspect.setFixedHeight(4)
        self.prog_inspect.setTextVisible(False)
        self.prog_inspect.hide()
        root.addWidget(self.prog_inspect)

        # Media Details Card (Card Frame)
        self.card_details = QFrame()
        self.card_details.setObjectName("MediaCard")
        cd_layout = QVBoxLayout(self.card_details)
        cd_layout.setContentsMargins(16, 14, 16, 14)
        cd_layout.setSpacing(12)

        # Media Title & Site Badge
        info_row = QHBoxLayout()
        self.lbl_media_icon = QLabel("📹")
        self.lbl_media_icon.setStyleSheet("font-size: 32px;")
        info_row.addWidget(self.lbl_media_icon)

        v_media_info = QVBoxLayout()
        v_media_info.setSpacing(4)
        self.lbl_media_title = QLabel("Medya bekleniyor…")
        self.lbl_media_title.setWordWrap(True)
        self.lbl_media_title.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.lbl_site_badge = QLabel("Henüz bir bağlantı taranmadı")
        self.lbl_site_badge.setStyleSheet("font-size: 11px; color: #888;")
        v_media_info.addWidget(self.lbl_media_title)
        v_media_info.addWidget(self.lbl_site_badge)
        info_row.addLayout(v_media_info, stretch=1)
        cd_layout.addLayout(info_row)

        # Quality & Mode Selection
        row_qual = QHBoxLayout()
        row_qual.addWidget(QLabel("İndirme Formatı / Kalitesi:"))
        self.cmb_quality = QComboBox()
        self.cmb_quality.setMinimumWidth(220)
        self.cmb_quality.setCursor(Qt.CursorShape.PointingHandCursor)
        row_qual.addWidget(self.cmb_quality, stretch=1)
        cd_layout.addLayout(row_qual)

        # Output Folder Selection
        row_dir = QHBoxLayout()
        row_dir.addWidget(QLabel("Kaydedilecek Yer:"))
        dl_dir = self.store.get_preference("download_dir", str(Path.home() / "Downloads"))
        self.lbl_dest_dir = QLabel(dl_dir)
        self.lbl_dest_dir.setStyleSheet("font-size: 12px; color: #666;")
        row_dir.addWidget(self.lbl_dest_dir, stretch=1)

        btn_ch_dir = QPushButton("Değiştir…")
        btn_ch_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ch_dir.clicked.connect(self._choose_dest_dir)
        row_dir.addWidget(btn_ch_dir)
        cd_layout.addLayout(row_dir)

        root.addWidget(self.card_details)

        # Action Buttons (Cancel / Download)
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Vazgeç")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        self.btn_download = QPushButton("Hemen İndir")
        self.btn_download.setObjectName("AccentDownloadButton")
        self.btn_download.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download.clicked.connect(self._on_download_clicked)
        self.btn_download.setEnabled(False)
        btn_row.addWidget(self.btn_download)

        root.addLayout(btn_row)

    def _apply_style(self):
        pal = self.theme_pal
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {pal['bg']};
                color: {pal['text']};
            }}
            QFrame#UrlBox {{
                background-color: {pal['card_bg']};
                border: 1.5px solid {pal['card_border']};
                border-radius: 10px;
            }}
            QFrame#MediaCard {{
                background-color: {pal['card_bg']};
                border: 1px solid {pal['card_border']};
                border-radius: 12px;
            }}
            QPushButton {{
                background-color: {pal['card_bg']};
                color: {pal['text']};
                border: 1px solid {pal['card_border']};
                border-radius: 7px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {pal['gold']};
            }}
            QPushButton#PrimaryButton {{
                background-color: {pal['gold']};
                color: #1A1D1A;
                border: none;
            }}
            QPushButton#PrimaryButton:hover {{
                background-color: {pal['gold_hover']};
            }}
            QPushButton#AccentDownloadButton {{
                background-color: {pal['gold']};
                color: #1A1D1A;
                border: none;
                padding: 8px 22px;
                font-size: 13px;
                font-weight: 800;
                border-radius: 8px;
            }}
            QPushButton#AccentDownloadButton:hover {{
                background-color: {pal['gold_hover']};
            }}
            QPushButton#AccentDownloadButton:disabled {{
                background-color: #555555;
                color: #888888;
            }}
            QComboBox {{
                background-color: {pal['bg']};
                color: {pal['text']};
                border: 1px solid {pal['card_border']};
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
            }}
            QProgressBar {{
                background-color: {pal['card_border']};
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {pal['gold']};
            }}
        """)

    def _paste_clipboard(self):
        txt = QApplication.clipboard().text().strip()
        if txt:
            self.inp_url.setText(txt)
            self.start_inspection()

    def _choose_dest_dir(self):
        chosen = QFileDialog.getExistingDirectory(
            self,
            "İndirme Konumunu Seç — Nashi",
            self.lbl_dest_dir.text(),
        )
        if chosen:
            self.lbl_dest_dir.setText(chosen)
            self.store.set_preference("download_dir", chosen)

    def start_inspection(self):
        url = self.inp_url.text().strip()
        if not url:
            return

        self.btn_inspect.setEnabled(False)
        self.btn_download.setEnabled(False)
        self.prog_inspect.show()
        self.lbl_media_title.setText("Medya ve mevcut çözünürlükler taranıyor…")
        self.lbl_site_badge.setText("Lütfen bekleyin…")
        self.cmb_quality.clear()

        self._worker = InspectWorker(self.engine, url)
        self._worker.finished.connect(self._on_inspect_success)
        self._worker.failed.connect(self._on_inspect_failed)
        self._worker.start()

    @Slot(dict)
    def _on_inspect_success(self, info: Dict[str, Any]):
        self._current_info = info
        self.prog_inspect.hide()
        self.btn_inspect.setEnabled(True)
        self.btn_download.setEnabled(True)

        self.lbl_media_title.setText(info.get("title", "Web Medyası"))
        site = info.get("site", "Web")
        dur = info.get("duration")
        dur_str = f" • {int(dur // 60)}:{int(dur % 60):02d}" if dur else ""
        self.lbl_site_badge.setText(f"Kaynak: {site}{dur_str}")

        # Populate quality options
        self.cmb_quality.clear()
        formats = info.get("formats", [])

        # Default standard options
        self.cmb_quality.addItem("🎬 En Yüksek Kalite (Otomatik MP4)", userData={"mode": "video", "height": 0, "fid": "best"})
        
        for f in formats:
            h = f.get("height", 0)
            fid = f.get("format_id")
            size_mb = f"{f['filesize'] / (1024*1024):.1f} MB" if f.get("filesize") else ""
            size_text = f" (~{size_mb})" if size_mb else ""
            label = f"🎥 {f.get('label', f'{h}p')}{size_text}"
            self.cmb_quality.addItem(label, userData={"mode": "video", "height": h, "fid": fid})

        # Audio options
        if info.get("has_audio", True):
            self.cmb_quality.addItem("🎵 Ses Dosyası (MP3 Formatında Çıkar)", userData={"mode": "audio", "height": 0, "fid": "audio"})
            self.cmb_quality.addItem("🖼️ Kapak / Küçük Resim (Thumbnail)", userData={"mode": "thumbnail", "height": 0, "fid": "thumb"})

    @Slot(str)
    def _on_inspect_failed(self, err: str):
        self.prog_inspect.hide()
        self.btn_inspect.setEnabled(True)
        self.lbl_media_title.setText("Medya taranamadı veya korumalı içerik.")
        self.lbl_site_badge.setText(f"Hata: {err[:80]}")
        # Allow fallback direct download anyway
        self.cmb_quality.addItem("🎬 En Yüksek Kalitede İndirmeyi Dene", userData={"mode": "video", "height": 0, "fid": "best"})
        self.btn_download.setEnabled(True)

    def _on_download_clicked(self):
        url = self.inp_url.text().strip()
        if not url:
            return

        selected_data = self.cmb_quality.currentData() or {"mode": "video", "height": 0, "fid": "best"}
        mode = selected_data.get("mode", "video")
        max_height = selected_data.get("height", 0)
        format_id = selected_data.get("fid", "best")
        out_dir = self.lbl_dest_dir.text()

        self.download_requested.emit(url, mode, max_height, format_id, out_dir)
        self.accept()
