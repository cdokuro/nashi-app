"""
Nashi Linux - Download Progress Dialog
Small dedicated window that displays live media download progress, percentage,
and completion actions (Reveal in folder, Copy file).
"""

import os
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QWidget, QFrame, QApplication
)

from artwork import get_theme_palette, NashiMarkWidget
from store import get_store
from toast_hud import reveal_in_file_manager, copy_files_to_clipboard


class DownloadProgressDialog(QDialog):
    """Small dedicated window showing live download progress with percentage and completion actions."""

    canceled = Signal()

    def __init__(self, title: str = "Web Medyası", url: str = "", dest_dir: str = "", parent=None):
        super().__init__(parent)
        self.store = get_store()
        self._theme = self.store.get_preference("theme", "dark")
        self.pal = get_theme_palette(self._theme)
        self._outputs: List[str] = []
        self._is_completed = False

        self.setWindowTitle("İndirme Durumu — Nashi")
        self.setFixedSize(500, 210)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._init_ui(title, url, dest_dir)
        self._apply_style()

    def _init_ui(self, title: str, url: str, dest_dir: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        # Header Row: Mascot + Titles
        h_row = QHBoxLayout()
        h_row.setSpacing(14)

        self.mascot = NashiMarkWidget(size=42, happy=False)
        h_row.addWidget(self.mascot)

        t_col = QVBoxLayout()
        t_col.setSpacing(3)

        display_title = title if title and title != "Web Medyası" else (os.path.basename(url) or "Web Medyası İndiriliyor")
        self.lbl_title = QLabel(display_title)
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: 800;")
        self.lbl_title.setWordWrap(False)
        t_col.addWidget(self.lbl_title)

        self.lbl_status = QLabel("İndirme başlatılıyor… %0")
        self.lbl_status.setStyleSheet("font-size: 12px;")
        t_col.addWidget(self.lbl_status)
        h_row.addLayout(t_col, stretch=1)
        layout.addLayout(h_row)

        # Progress Row
        p_row = QHBoxLayout()
        p_row.setSpacing(12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        p_row.addWidget(self.progress_bar, stretch=1)

        self.lbl_percent = QLabel("%0")
        self.lbl_percent.setFixedWidth(50)
        self.lbl_percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_percent.setStyleSheet("font-size: 14px; font-weight: 800;")
        p_row.addWidget(self.lbl_percent)
        layout.addLayout(p_row)

        # Destination info
        out_info = dest_dir or str(Path.home() / "Downloads")
        self.lbl_dest = QLabel(f"Hedef: {out_info}")
        self.lbl_dest.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.lbl_dest)

        # Buttons Row
        self.btn_row = QHBoxLayout()
        self.btn_row.setSpacing(10)

        # In-progress actions
        self.btn_background = QPushButton("Arka Plana Al")
        self.btn_background.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_background.clicked.connect(self.hide)
        self.btn_row.addWidget(self.btn_background)

        self.btn_cancel = QPushButton("İptal Et")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_row.addWidget(self.btn_cancel)

        # Completed actions (hidden initially)
        self.btn_reveal = QPushButton("📂 Klasörde Göster")
        self.btn_reveal.setObjectName("PrimaryGoldBtn")
        self.btn_reveal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reveal.clicked.connect(self._on_reveal_clicked)
        self.btn_reveal.hide()
        self.btn_row.addWidget(self.btn_reveal)

        self.btn_copy = QPushButton("📋 Dosyayı Kopyala")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self._on_copy_clicked)
        self.btn_copy.hide()
        self.btn_row.addWidget(self.btn_copy)

        self.btn_close = QPushButton("Kapat")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        self.btn_close.hide()
        self.btn_row.addWidget(self.btn_close)

        self.btn_row.addStretch()
        layout.addLayout(self.btn_row)

    def _apply_style(self):
        pal = self.pal
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {pal['paper']};
                color: {pal['ink']};
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Noto Sans', sans-serif;
            }}
            QLabel {{
                background: transparent;
                color: {pal['ink']};
            }}
            QLabel#StatusLabel {{
                color: {pal['muted']};
            }}
            QProgressBar {{
                background-color: {pal['inset']};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {pal['gold']}, stop:1 {pal['gold_end']});
                border-radius: 4px;
            }}
            QPushButton {{
                background-color: {pal['inset']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 10px;
                padding: 7px 15px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {pal['gold']};
                color: {pal['gold']};
            }}
            QPushButton#PrimaryGoldBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {pal['gold']}, stop:1 {pal['gold_end']});
                color: {pal['button_ink']};
                border: none;
                font-weight: 700;
            }}
            QPushButton#PrimaryGoldBtn:hover {{
                background: {pal['gold_end']};
            }}
        """)
        self.lbl_percent.setStyleSheet(f"color: {pal['gold']}; font-size: 15px; font-weight: 800; background: transparent;")

    @Slot(str, str, int)
    def update_progress(self, title: str, detail: str, percent: int):
        if self._is_completed:
            return
        pct = max(0, min(100, int(percent)))
        self.progress_bar.setValue(pct)
        self.lbl_percent.setText(f"%{pct}")
        if detail:
            self.lbl_status.setText(detail)

    @Slot(bool, str, str, list)
    def set_completed(self, success: bool, title: str, detail: str, outputs: list):
        self._is_completed = True
        self._outputs = list(outputs or [])

        # Switch buttons
        self.btn_background.hide()
        self.btn_cancel.hide()
        self.btn_close.show()

        if success:
            self.mascot.set_happy(True)
            self.progress_bar.setValue(100)
            self.lbl_percent.setText("%100")
            self.lbl_status.setText("✓ İndirme başarıyla tamamlandı!")
            self.lbl_status.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: 700;")

            if self._outputs:
                first_out = self._outputs[0]
                self.lbl_title.setText(os.path.basename(first_out))
                self.lbl_dest.setText(f"Kayıt Yeri: {first_out}")
                self.btn_reveal.show()
                self.btn_copy.show()
        else:
            self.mascot.set_happy(False)
            self.lbl_status.setText(f"⚠️ {title}: {detail[:80]}")
            self.lbl_status.setStyleSheet("color: #FF5252; font-size: 12px; font-weight: 700;")

        self.raise_()
        self.activateWindow()

    def _on_reveal_clicked(self):
        if self._outputs:
            reveal_in_file_manager(self._outputs)

    def _on_copy_clicked(self):
        if self._outputs:
            copy_files_to_clipboard(self._outputs)
            self.btn_copy.setText("✓ Kopyalandı")

    def _on_cancel(self):
        self.canceled.emit()
        self.reject()
