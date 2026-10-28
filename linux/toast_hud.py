"""
Nashi Linux - Chrome-free HUD Toasts (ProgressToast & SuccessToast)
Ported from ProgressToast.swift and SuccessToast.swift.
Appears at the bottom center of the active screen without stealing focus,
offers quick 'Show in Folder' and 'Copy' buttons, and fades out automatically.
"""

import os
import subprocess
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QUrl, QMimeData
from PySide6.QtGui import QGuiApplication, QCursor, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QProgressBar, QApplication
)

from artwork import get_theme_palette, NashiMarkWidget


def reveal_in_file_manager(file_paths: List[str]):
    """Reveals the given file(s) in Dolphin or the system file manager."""
    if not file_paths:
        return
    first = str(Path(file_paths[0]).resolve())
    try:
        # Try org.freedesktop.FileManager1 DBus ShowItems first (highlights file in Dolphin!)
        uris = [QUrl.fromLocalFile(str(Path(p).resolve())).toString() for p in file_paths if os.path.exists(p)]
        if uris:
            subprocess.Popen(
                [
                    "qdbus6", "org.freedesktop.FileManager1",
                    "/org/freedesktop/FileManager1",
                    "org.freedesktop.FileManager1.ShowItems",
                    uris, "nashi"
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
    except Exception:
        pass

    target = first if os.path.isdir(first) else os.path.dirname(first)
    subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def copy_files_to_clipboard(file_paths: List[str]):
    """Copies file URIs and paths to the system clipboard so user can Ctrl+V in Dolphin/apps."""
    if not file_paths:
        return
    cb = QApplication.clipboard()
    mime = QMimeData()
    urls = [QUrl.fromLocalFile(str(Path(p).resolve())) for p in file_paths if os.path.exists(p)]
    if urls:
        mime.setUrls(urls)
        gnome_lines = ["copy"] + [u.toEncoded().data().decode("utf-8") for u in urls]
        mime.setData("x-special/gnome-copied-files", "\n".join(gnome_lines).encode("utf-8"))
    mime.setText("\n".join(file_paths))
    cb.setMimeData(mime)


class NashiToastHUD(QWidget):
    """Non-activating bottom-center floating HUD card for progress, success, and error notices."""

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self._theme = theme
        self._files: List[str] = []

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(520, 88)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._fade_out)

        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)
        self._fading_out = False

        self._init_ui()
        self.set_theme(theme)

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(14)

        self.mascot = NashiMarkWidget(size=40, happy=True)
        layout.addWidget(self.mascot)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        self.lbl_title = QLabel("İşlem tamamlandı")
        self.lbl_title.setStyleSheet("font-size: 13px; font-weight: 700;")
        text_col.addWidget(self.lbl_title)

        self.lbl_detail = QLabel("")
        self.lbl_detail.setStyleSheet("font-size: 11px;")
        text_col.addWidget(self.lbl_detail)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(5)
        self.progress.setTextVisible(False)
        self.progress.hide()
        text_col.addWidget(self.progress)

        layout.addLayout(text_col, stretch=1)

        self.btn_copy = QPushButton("Kopyala")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self._on_copy_clicked)
        layout.addWidget(self.btn_copy)

        self.btn_reveal = QPushButton("Klasörde Göster")
        self.btn_reveal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reveal.clicked.connect(self._on_reveal_clicked)
        layout.addWidget(self.btn_reveal)

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide)
        layout.addWidget(self.btn_close)

    def set_theme(self, theme: str):
        self._theme = theme
        pal = get_theme_palette(theme)
        self.lbl_title.setStyleSheet(f"color: {pal['ink']}; font-size: 13px; font-weight: 700; background: transparent;")
        self.lbl_detail.setStyleSheet(f"color: {pal['muted']}; font-size: 11px; background: transparent;")
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {pal['inset']};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {pal['gold']};
                border-radius: 2px;
            }}
        """)
        btn_style = f"""
            QPushButton {{
                background-color: {pal['inset']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {pal['gold']};
                color: {pal['button_ink']};
                border-color: {pal['gold']};
            }}
        """
        self.btn_copy.setStyleSheet(btn_style)
        self.btn_reveal.setStyleSheet(btn_style)
        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {pal['muted']};
                border: none;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ color: {pal['ink']}; }}
        """)
        self.update()

    def _position_on_screen(self):
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            x = avail.x() + (avail.width() - self.width()) // 2
            y = avail.y() + avail.height() - self.height() - 32
            self.move(x, y)

    def show_progress(self, title: str, detail: str = "Lütfen bekleyin…"):
        self._dismiss_timer.stop()
        self._fading_out = False
        self._files = []
        self.mascot.set_happy(False)
        self.lbl_title.setText(title)
        self.lbl_detail.setText(detail)
        self.progress.show()
        self.btn_copy.hide()
        self.btn_reveal.hide()
        self._position_on_screen()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()

    def show_success(self, title: str, detail: str, files: Optional[List[str]] = None, duration_ms: int = 3800):
        self._dismiss_timer.stop()
        self._fading_out = False
        self._files = list(files or [])
        self.mascot.set_happy(True)
        self.lbl_title.setText(title)
        self.lbl_detail.setText(detail)
        self.progress.hide()

        has_files = bool(self._files and any(os.path.exists(f) for f in self._files))
        self.btn_copy.setVisible(has_files)
        self.btn_reveal.setVisible(has_files)
        self.btn_copy.setText("Kopyala")

        self._position_on_screen()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        if duration_ms > 0:
            self._dismiss_timer.start(duration_ms)

    def show_error(self, title: str, detail: str, duration_ms: int = 5000):
        self._dismiss_timer.stop()
        self._fading_out = False
        self._files = []
        self.mascot.set_happy(False)
        self.lbl_title.setText(f"⚠️ {title}")
        self.lbl_detail.setText(detail[:90])
        self.progress.hide()
        self.btn_copy.hide()
        self.btn_reveal.hide()
        self._position_on_screen()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        if duration_ms > 0:
            self._dismiss_timer.start(duration_ms)

    def _on_copy_clicked(self):
        if self._files:
            copy_files_to_clipboard(self._files)
            self.btn_copy.setText("✓ Kopyalandı")

    def _on_reveal_clicked(self):
        if self._files:
            reveal_in_file_manager(self._files)
            self.hide()

    def _fade_out(self):
        self._fading_out = True
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_anim_finished(self):
        if self._fading_out:
            self.hide()
            self.setWindowOpacity(1.0)
            self._fading_out = False

    def paintEvent(self, event):
        pal = get_theme_palette(self._theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 22, 22)

        bg = QColor(pal["surface"])
        bg.setAlpha(245)
        painter.fillPath(path, bg)

        border = QColor(pal["gold"])
        border.setAlpha(150)
        painter.setPen(QPen(border, 1.5))
        painter.drawPath(path)
        painter.end()
