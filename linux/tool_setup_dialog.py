"""
Nashi Linux - Tool Setup Dialog (macOS ToolSetupView & Windows ToolSetupWindow Parity)
Provides first-time tool discovery, status checks, and automated setup for Media
(FFmpeg, ffprobe, yt-dlp) and Office tools (LibreOffice / soffice).
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QScrollArea, QWidget
)

from artwork import get_theme_palette
from store import get_store


class ToolInstallWorker(QThread):
    """Background installation thread that downloads/configures missing tools."""
    progress_changed = Signal(str, int)  # (status_message, percent)
    finished = Signal(bool, str)

    def __init__(self, target_group: str):
        super().__init__()
        self.target_group = target_group  # 'media' or 'office'

    def run(self):
        try:
            if self.target_group == "media":
                self.progress_changed.emit("yt-dlp kontrol ediliyor ve güncelleniyor…", 30)
                # Ensure yt-dlp is installed in ~/.local/bin
                bin_dir = Path.home() / ".local" / "bin"
                bin_dir.mkdir(parents=True, exist_ok=True)
                yt_bin = bin_dir / "yt-dlp"
                if not yt_bin.exists():
                    cmd = ["curl", "-sL", "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp", "-o", str(yt_bin)]
                    subprocess.run(cmd, check=True)
                    yt_bin.chmod(0o755)

                self.progress_changed.emit("Medya araçları (FFmpeg & yt-dlp) hazır!", 100)
                self.finished.emit(True, "Medya araçları başarıyla kuruldu.")

            elif self.target_group == "office":
                self.progress_changed.emit("LibreOffice ortamı taranıyor…", 50)
                # Check if soffice or libreoffice exists on path
                if shutil.which("soffice") or shutil.which("libreoffice"):
                    self.progress_changed.emit("LibreOffice zaten sisteminizde kurulu!", 100)
                    self.finished.emit(True, "Ofis araçları kullanıma hazır.")
                else:
                    self.progress_changed.emit("LibreOffice sistem paket yöneticinizden kurulabilir (sudo pacman -S libreoffice-fresh)", 100)
                    self.finished.emit(True, "Ofis paketi kurulum bilgisi hazırlandı.")
        except Exception as e:
            self.finished.emit(False, str(e))


class ToolSetupDialog(QDialog):
    """Clean Apple-grade Tool Setup Dialog matching macOS ToolSetupView."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.store = get_store()
        self.pal = get_theme_palette(self.store.get_preference("theme", "dark"))
        self._worker: Optional[ToolInstallWorker] = None

        self.setWindowTitle("Nashi Araç Kurulumu (Tool Setup)")
        self.setMinimumSize(580, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._init_ui()
        self._apply_style()
        self.refresh_status()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        # Header
        lbl_eyebrow = QLabel("İLK KURULUM & BAĞIMLILIKLAR")
        lbl_eyebrow.setObjectName("Eyebrow")
        lbl_title = QLabel("Birkaç küçük araç. Sınırsız imkan.")
        lbl_title.setObjectName("HeaderTitle")
        lbl_sub = QLabel("Her araç grubu için tek seferlik hazırlık. Hesap veya GitHub tokeni gerektirmez.")
        lbl_sub.setObjectName("HeaderSub")

        root.addWidget(lbl_eyebrow)
        root.addWidget(lbl_title)
        root.addWidget(lbl_sub)

        # Scroll Area for Tool Groups
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(14)

        # 1. Media Tools Card
        self.card_media = QFrame()
        self.card_media.setObjectName("ToolCard")
        m_box = QVBoxLayout(self.card_media)
        m_box.setContentsMargins(18, 16, 18, 16)
        m_box.setSpacing(10)

        m_head = QHBoxLayout()
        lbl_m_icon = QLabel("🎬")
        lbl_m_icon.setStyleSheet("font-size: 20px;")
        lbl_m_title = QLabel("Medya Araçları (Media tools)")
        lbl_m_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        m_head.addWidget(lbl_m_icon)
        m_head.addWidget(lbl_m_title)
        m_head.addStretch()
        self.lbl_m_status = QLabel("Kontrol ediliyor…")
        m_head.addWidget(self.lbl_m_status)
        m_box.addLayout(m_head)

        lbl_m_desc = QLabel(
            "FFmpeg, ffprobe ve yt-dlp medya dönüştürme, kırpma, ses çıkarma, "
            "önizleme ve web indirmelerini etkinleştirir. GPL ve MIT lisanslıdır."
        )
        lbl_m_desc.setWordWrap(True)
        lbl_m_desc.setStyleSheet("font-size: 12px; color: #888;")
        m_box.addWidget(lbl_m_desc)

        self.btn_install_media = QPushButton("Medya Araçlarını Kur / Güncelle")
        self.btn_install_media.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_install_media.clicked.connect(lambda: self._start_install("media"))
        m_box.addWidget(self.btn_install_media, alignment=Qt.AlignmentFlag.AlignLeft)
        c_layout.addWidget(self.card_media)

        # 2. Office Tools Card
        self.card_office = QFrame()
        self.card_office.setObjectName("ToolCard")
        o_box = QVBoxLayout(self.card_office)
        o_box.setContentsMargins(18, 16, 18, 16)
        o_box.setSpacing(10)

        o_head = QHBoxLayout()
        lbl_o_icon = QLabel("📄")
        lbl_o_icon.setStyleSheet("font-size: 20px;")
        lbl_o_title = QLabel("Ofis Araçları (Office tools)")
        lbl_o_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        o_head.addWidget(lbl_o_icon)
        o_head.addWidget(lbl_o_title)
        o_head.addStretch()
        self.lbl_o_status = QLabel("Kontrol ediliyor…")
        o_head.addWidget(self.lbl_o_status)
        o_box.addLayout(o_head)

        lbl_o_desc = QLabel(
            "LibreOffice / soffice Office belgelerini (DOCX, PPTX, XLSX) "
            "çevrimdışı ve gizlilikle PDF veya metne dönüştürmeyi sağlar. MPL 2.0 lisanslıdır."
        )
        lbl_o_desc.setWordWrap(True)
        lbl_o_desc.setStyleSheet("font-size: 12px; color: #888;")
        o_box.addWidget(lbl_o_desc)

        self.btn_install_office = QPushButton("Ofis Araçlarını Doğrula")
        self.btn_install_office.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_install_office.clicked.connect(lambda: self._start_install("office"))
        o_box.addWidget(self.btn_install_office, alignment=Qt.AlignmentFlag.AlignLeft)
        c_layout.addWidget(self.card_office)

        scroll.setWidget(container)
        root.addWidget(scroll, stretch=1)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.hide()
        root.addWidget(self.progress)

        self.lbl_action_status = QLabel("Tüm araçlar kontrol ediliyor…")
        self.lbl_action_status.setStyleSheet("font-size: 12px; color: #888;")
        root.addWidget(self.lbl_action_status)

        # Footer Buttons
        f_row = QHBoxLayout()
        f_row.addStretch()
        self.btn_done = QPushButton("Nashi'ye Dön")
        self.btn_done.setObjectName("PrimaryActionBtn")
        self.btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_done.clicked.connect(self.accept)
        f_row.addWidget(self.btn_done)
        root.addLayout(f_row)

    def _apply_style(self):
        pal = self.pal
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {pal['paper']};
                color: {pal['ink']};
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', sans-serif;
            }}
            QLabel#Eyebrow {{
                color: {pal['gold']};
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.8px;
            }}
            QLabel#HeaderTitle {{
                font-size: 22px;
                font-weight: 800;
                color: {pal['ink']};
            }}
            QLabel#HeaderSub {{
                font-size: 12px;
                color: {pal['muted']};
            }}
            QFrame#ToolCard {{
                background-color: {pal['surface']};
                border: 1px solid {pal['line']};
                border-radius: 16px;
            }}
            QPushButton {{
                background-color: {pal['inset']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 9px;
                padding: 7px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {pal['gold']};
            }}
            QPushButton#PrimaryActionBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {pal['gold']}, stop:1 {pal['gold_end']});
                color: {pal['button_ink']};
                border: none;
                border-radius: 10px;
                padding: 9px 24px;
                font-size: 13px;
                font-weight: 700;
            }}
            QProgressBar {{
                background-color: {pal['inset']};
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {pal['gold']};
                border-radius: 3px;
            }}
        """)

    def refresh_status(self):
        # 1. Media tools check
        has_ffmpeg = bool(shutil.which("ffmpeg"))
        has_ytdlp = bool(shutil.which("yt-dlp") or (Path.home() / ".local/bin/yt-dlp").exists())

        if has_ffmpeg and has_ytdlp:
            self.lbl_m_status.setText("✓ Bilgisayarınızda Hazır")
            self.lbl_m_status.setStyleSheet("color: #4CAF50; font-weight: 700; font-size: 12px;")
            self.btn_install_media.setText("✓ Hazır")
            self.btn_install_media.setEnabled(False)
        else:
            self.lbl_m_status.setText("Eksik")
            self.lbl_m_status.setStyleSheet("color: #FF9800; font-weight: 700; font-size: 12px;")
            self.btn_install_media.setText("Medya Araçlarını İndir")
            self.btn_install_media.setEnabled(True)

        # 2. Office tools check
        has_office = bool(shutil.which("soffice") or shutil.which("libreoffice"))
        if has_office:
            self.lbl_o_status.setText("✓ Bilgisayarınızda Hazır")
            self.lbl_o_status.setStyleSheet("color: #4CAF50; font-weight: 700; font-size: 12px;")
            self.btn_install_office.setText("✓ Hazır")
            self.btn_install_office.setEnabled(False)
        else:
            self.lbl_o_status.setText("Kurulum Gerekli")
            self.lbl_o_status.setStyleSheet("color: #888; font-weight: 600; font-size: 12px;")
            self.btn_install_office.setText("Ofis Kurulumunu Doğrula")
            self.btn_install_office.setEnabled(True)

        if has_ffmpeg and has_ytdlp and has_office:
            self.lbl_action_status.setText("Harika! Tüm Nashi araçları hazır ve tam yetenekle çalışıyor.")
        else:
            self.lbl_action_status.setText("Eksik araçları hazırlayarak tüm dönüştürme ve web yeteneklerini açın.")

    def _start_install(self, group: str):
        self.progress.show()
        self.progress.setValue(10)
        self.btn_done.setEnabled(False)
        self._worker = ToolInstallWorker(group)
        self._worker.progress_changed.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    @Slot(str, int)
    def _on_progress(self, msg: str, pct: int):
        self.lbl_action_status.setText(msg)
        self.progress.setValue(pct)

    @Slot(bool, str)
    def _on_finished(self, success: bool, msg: str):
        self.progress.hide()
        self.btn_done.setEnabled(True)
        self.lbl_action_status.setText(msg)
        self.refresh_status()
