"""
Nashi Linux - Tool Setup Dialog (macOS ToolSetupView & Windows ToolSetupWindow Parity)
Provides first-time tool discovery, status checks, and automated setup for Media
(FFmpeg, ffprobe, yt-dlp) and Office tools (LibreOffice / soffice).
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QScrollArea, QWidget, QApplication
)

from artwork import get_theme_palette
from store import get_store


class ToolInstallWorker(QThread):
    """Background installation thread that downloads, tests, and verifies tools."""
    progress_changed = Signal(str, int)  # (status_message, percent)
    finished = Signal(bool, str)

    def __init__(self, target_group: str, engine=None):
        super().__init__()
        self.target_group = target_group  # 'media', 'office_verify', 'office_flatpak_install'
        self.engine = engine

    def run(self):
        try:
            if self.target_group == "media":
                self.progress_changed.emit("FFmpeg ve ffprobe çalıştırılıp test ediliyor…", 30)
                res = self.engine.verify_media_tools() if self.engine else {}

                if not res.get("ytdlp"):
                    self.progress_changed.emit("yt-dlp indiriliyor ve ~/.local/bin dizinine kuruluyor…", 60)
                    bin_dir = Path.home() / ".local" / "bin"
                    bin_dir.mkdir(parents=True, exist_ok=True)
                    yt_bin = bin_dir / "yt-dlp"
                    cmd = ["curl", "-sL", "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp", "-o", str(yt_bin)]
                    subprocess.run(cmd, check=True, timeout=30)
                    yt_bin.chmod(0o755)
                    res = self.engine.verify_media_tools() if self.engine else {}

                if res.get("all_ready"):
                    ff_v = res.get("ffmpeg_version", "FFmpeg")
                    yt_v = res.get("ytdlp_version", "yt-dlp")
                    self.progress_changed.emit("✓ Tüm medya araçları başarıyla doğrulandı!", 100)
                    self.finished.emit(True, f"Medya araçları doğrulandı: {ff_v} · {yt_v}")
                else:
                    missing = []
                    if not res.get("ffmpeg"):
                        missing.append("FFmpeg")
                    if not res.get("ytdlp"):
                        missing.append("yt-dlp")
                    self.finished.emit(False, f"Eksik medya araçları: {', '.join(missing)}. Lütfen paket yöneticinizden kurun.")

            elif self.target_group in ("office", "office_verify"):
                self.progress_changed.emit("Sistem taranıyor (PATH, Flatpak, Snap, ~/.local/bin)…", 40)
                office_cmd = self.engine.find_office_command() if self.engine else None
                office_ver = self.engine.get_office_version() if self.engine else None

                if office_cmd and office_ver:
                    self.progress_changed.emit(f"✓ LibreOffice tespit edildi: {office_ver}", 100)
                    self.finished.emit(True, f"✓ Ofis araçları kullanıma hazır ({office_ver})")
                else:
                    self.progress_changed.emit("LibreOffice bulunamadı.", 100)
                    self.finished.emit(
                        False,
                        "Sisteminizde LibreOffice bulunamadı. Lütfen aşağıdaki seçeneklerden birini kullanarak kurun."
                    )

            elif self.target_group == "office_flatpak_install":
                self.progress_changed.emit("Flatpak ile LibreOffice hazırlanıyor…", 15)
                cmd = ["flatpak", "--user", "install", "-y", "flathub", "org.libreoffice.LibreOffice"]
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

                for line in proc.stdout:
                    line = line.strip()
                    m = re.search(r"(\d+)%", line)
                    if m:
                        pct = int(m.group(1))
                        self.progress_changed.emit(f"LibreOffice indiriliyor: %{pct}", pct)

                proc.wait()
                office_ver = self.engine.get_office_version() if self.engine else None
                if office_ver or proc.returncode == 0:
                    self.progress_changed.emit("✓ LibreOffice başarıyla kuruldu!", 100)
                    self.finished.emit(True, f"LibreOffice başarıyla kuruldu: {office_ver or '26.8'}")
                else:
                    self.finished.emit(False, "Flatpak kurulumu tamamlanamadı. Lütfen terminalden pacman deneyin.")
        except Exception as e:
            self.finished.emit(False, f"İşlem sırasında hata: {e}")


class ToolSetupDialog(QDialog):
    """Clean Apple-grade Tool Setup Dialog matching macOS ToolSetupView."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.store = get_store()
        self.pal = get_theme_palette(self.store.get_preference("theme", "dark"))
        self._worker: Optional[ToolInstallWorker] = None

        self.setWindowTitle("Nashi Araç Kurulumu (Tool Setup)")
        self.setMinimumSize(600, 560)
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

        self.btn_install_media = QPushButton("Medya Araçlarını Doğrula / Yeniden Test Et")
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

        o_btn_row = QHBoxLayout()
        self.btn_install_office = QPushButton("Ofis Kurulumunu Doğrula")
        self.btn_install_office.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_install_office.clicked.connect(lambda: self._start_install("office_verify"))
        o_btn_row.addWidget(self.btn_install_office)
        o_btn_row.addStretch()
        o_box.addLayout(o_btn_row)

        # Office Helper Actions Frame (visible when office is not installed)
        self.office_actions_frame = QFrame()
        self.office_actions_frame.setObjectName("HelperCard")
        oa_box = QVBoxLayout(self.office_actions_frame)
        oa_box.setContentsMargins(14, 12, 14, 12)
        oa_box.setSpacing(8)

        lbl_helper_title = QLabel("KURULUM SEÇENEKLERİ:")
        lbl_helper_title.setStyleSheet("font-size: 11px; font-weight: 800; color: #E5A93C; letter-spacing: 0.5px;")
        oa_box.addWidget(lbl_helper_title)

        # Pacman Option
        pacman_row = QHBoxLayout()
        lbl_p_info = QLabel("Arch Linux (Tavsiye Edilen):")
        lbl_p_info.setStyleSheet("font-size: 12px; font-weight: 600;")
        pacman_row.addWidget(lbl_p_info)
        self.btn_copy_pacman = QPushButton("📋 sudo pacman -S libreoffice-fresh Kopyala")
        self.btn_copy_pacman.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_pacman.clicked.connect(self._copy_pacman_command)
        pacman_row.addWidget(self.btn_copy_pacman)
        pacman_row.addStretch()
        oa_box.addLayout(pacman_row)

        # Flatpak Option
        flatpak_row = QHBoxLayout()
        lbl_f_info = QLabel("Flatpak (Şifresiz Kullanıcı Kurulumu):")
        lbl_f_info.setStyleSheet("font-size: 12px; font-weight: 600;")
        flatpak_row.addWidget(lbl_f_info)
        self.btn_flatpak_install = QPushButton("📦 Flatpak ile Otomatik İndir ve Kur")
        self.btn_flatpak_install.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_flatpak_install.clicked.connect(lambda: self._start_install("office_flatpak_install"))
        flatpak_row.addWidget(self.btn_flatpak_install)
        flatpak_row.addStretch()
        oa_box.addLayout(flatpak_row)

        o_box.addWidget(self.office_actions_frame)
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
        self.lbl_action_status.setWordWrap(True)
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
            QFrame#HelperCard {{
                background-color: {pal['inset']};
                border: 1px dashed {pal['gold']};
                border-radius: 12px;
                margin-top: 6px;
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

    def _copy_pacman_command(self):
        cb = QApplication.clipboard()
        if cb:
            cb.setText("sudo pacman -S --noconfirm libreoffice-fresh")
            self.btn_copy_pacman.setText("✓ Komut Kopyalandı!")
            self.lbl_action_status.setText(
                "✓ Komut panoya kopyalandı! Terminali açıp yapıştırabilirsiniz: sudo pacman -S libreoffice-fresh"
            )
            QTimer.singleShot(3000, lambda: self.btn_copy_pacman.setText("📋 sudo pacman -S libreoffice-fresh Kopyala"))

    def refresh_status(self, custom_msg: Optional[str] = None):
        # 1. Media tools check
        media_res = self.engine.verify_media_tools() if self.engine else {}
        has_media = media_res.get("all_ready", False)

        if has_media:
            ff_part = media_res.get("ffmpeg_version", "FFmpeg").replace("ffmpeg version ", "")
            yt_part = media_res.get("ytdlp_version", "yt-dlp").replace("yt-dlp ", "")
            ff_tag = ff_part.split()[0] if ff_part else "Hazır"
            self.lbl_m_status.setText(f"✓ Bilgisayarınızda Hazır ({ff_tag} · yt-dlp)")
            self.lbl_m_status.setStyleSheet("color: #4CAF50; font-weight: 700; font-size: 12px;")
            self.btn_install_media.setText("✓ Doğrulandı (Yeniden Test Et)")
            self.btn_install_media.setEnabled(True)
        else:
            self.lbl_m_status.setText("Eksik")
            self.lbl_m_status.setStyleSheet("color: #FF9800; font-weight: 700; font-size: 12px;")
            self.btn_install_media.setText("Medya Araçlarını İndir / Doğrula")
            self.btn_install_media.setEnabled(True)

        # 2. Office tools check
        office_ver = self.engine.get_office_version() if self.engine else None
        has_office = bool(office_ver)

        if has_office:
            parts = office_ver.split()
            v_short = f"{parts[0]} {parts[1]}" if len(parts) > 1 else office_ver
            self.lbl_o_status.setText(f"✓ Bilgisayarınızda Hazır ({v_short})")
            self.lbl_o_status.setStyleSheet("color: #4CAF50; font-weight: 700; font-size: 12px;")
            self.btn_install_office.setText("✓ Doğrulandı (Yeniden Doğrula)")
            self.btn_install_office.setEnabled(True)
            self.office_actions_frame.hide()
        else:
            self.lbl_o_status.setText("Kurulum Gerekli")
            self.lbl_o_status.setStyleSheet("color: #FF9800; font-weight: 700; font-size: 12px;")
            self.btn_install_office.setText("Ofis Kurulumunu Doğrula")
            self.btn_install_office.setEnabled(True)
            self.office_actions_frame.show()

        if custom_msg:
            self.lbl_action_status.setText(custom_msg)
        elif has_media and has_office:
            self.lbl_action_status.setText("Harika! Tüm Nashi araçları hazır ve tam yetenekle çalışıyor.")
        elif not has_office:
            self.lbl_action_status.setText("LibreOffice henüz kurulu değil. Seçeneklerden birini uygulayıp 'Doğrula'ya basabilirsiniz.")
        else:
            self.lbl_action_status.setText("Eksik araçları hazırlayarak tüm dönüştürme ve web yeteneklerini açın.")

    def _start_install(self, group: str):
        self.progress.show()
        self.progress.setValue(15)
        self.btn_done.setEnabled(False)
        self.lbl_action_status.setText("İşlem başlatılıyor…")

        self._worker = ToolInstallWorker(group, engine=self.engine)
        self._worker.progress_changed.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    @Slot(str, int)
    def _on_progress(self, msg: str, pct: int):
        self.lbl_action_status.setText(msg)
        self.progress.setValue(pct)

    @Slot(bool, str)
    def _on_finished(self, success: bool, msg: str):
        self.btn_done.setEnabled(True)
        self.refresh_status(custom_msg=msg)
        if success:
            self.progress.setValue(100)
            QTimer.singleShot(1500, self.progress.hide)
        else:
            self.progress.hide()
