"""
Nashi Linux - FloatShelf (Floating File Shelf)
Ported from FloatShelf.swift & FloatShelf.cs.
Keeps files in a compact floating shelf on top of the screen:
- Accept dragged files to add to the shelf
- Drag files out of the shelf into any application
- Collapse/expand, snap to screen edges, copy all, or reveal in folder.
"""

import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QUrl, QMimeData, QPoint, QSize, Signal
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QDrag, QCursor, QGuiApplication, QPixmap
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView
)

from artwork import get_theme_palette, NashiArtwork
from toast_hud import reveal_in_file_manager, copy_files_to_clipboard


class DraggableShelfList(QListWidget):
    """List widget that initiates a native file URI drag when items are dragged out."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSpacing(4)

    def startDrag(self, supportedActions):
        items = self.selectedItems()
        if not items:
            return
        paths = [it.data(Qt.ItemDataRole.UserRole) for it in items if it.data(Qt.ItemDataRole.UserRole)]
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            return

        mime = QMimeData()
        urls = [QUrl.fromLocalFile(str(Path(p).resolve())) for p in paths]
        mime.setUrls(urls)
        mime.setText("\n".join(paths))

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(NashiArtwork.pixmap(36, happy=True))
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)


class FloatShelfWindow(QWidget):
    """Floating file shelf matching Nashi's Float action."""

    files_sent_to_wheel = Signal(list, str)  # (file_paths, mode)

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self._theme = theme
        self._files: List[str] = []
        self._collapsed = False
        self._drag_offset: Optional[QPoint] = None

        self.setWindowTitle("Nashi Float")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.resize(290, 310)

        self._init_ui()
        self.set_theme(theme)

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 12, 14, 14)
        self.main_layout.setSpacing(8)

        # Header (draggable handle)
        header = QHBoxLayout()
        header.setSpacing(6)

        self.lbl_badge = QLabel("📎 Float Rafı (0)")
        self.lbl_badge.setStyleSheet("font-size: 13px; font-weight: 700;")
        header.addWidget(self.lbl_badge)

        header.addStretch()

        self.btn_collapse = QPushButton("—")
        self.btn_collapse.setFixedSize(24, 24)
        self.btn_collapse.setToolTip("Daralt / Genişlet")
        self.btn_collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_collapse.clicked.connect(self.toggle_collapse)
        header.addWidget(self.btn_collapse)

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setToolTip("Rafı Kapat (Dosyalar silinmez)")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide)
        header.addWidget(self.btn_close)

        self.main_layout.addLayout(header)

        # Body container
        self.body_widget = QWidget()
        body_layout = QVBoxLayout(self.body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)

        self.lbl_hint = QLabel("Dosyaları başka uygulamalara sürükleyin veya buraya yeni dosya bırakın.")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("font-size: 10px;")
        body_layout.addWidget(self.lbl_hint)

        self.list_widget = DraggableShelfList()
        body_layout.addWidget(self.list_widget, stretch=1)

        # Quick action row
        act_row = QHBoxLayout()
        act_row.setSpacing(6)

        self.btn_convert = QPushButton("Dönüştür")
        self.btn_convert.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_convert.clicked.connect(lambda: self._emit_to_wheel("convert"))
        act_row.addWidget(self.btn_convert)

        self.btn_tools = QPushButton("Araçlar")
        self.btn_tools.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tools.clicked.connect(lambda: self._emit_to_wheel("tools"))
        act_row.addWidget(self.btn_tools)

        self.btn_copy = QPushButton("Kopyala")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self._copy_all)
        act_row.addWidget(self.btn_copy)

        self.btn_clear = QPushButton("Temizle")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self.clear_files)
        act_row.addWidget(self.btn_clear)

        body_layout.addLayout(act_row)
        self.main_layout.addWidget(self.body_widget, stretch=1)

    def set_theme(self, theme: str):
        self._theme = theme
        pal = get_theme_palette(theme)
        self.lbl_badge.setStyleSheet(f"color: {pal['gold']}; font-size: 13px; font-weight: 800; background: transparent;")
        self.lbl_hint.setStyleSheet(f"color: {pal['muted']}; font-size: 10px; background: transparent;")
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {pal['inset']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 12px;
                padding: 6px;
                font-size: 12px;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-radius: 8px;
            }}
            QListWidget::item:selected {{
                background-color: {pal['sage']};
                color: {pal['gold']};
            }}
        """)
        btn_style = f"""
            QPushButton {{
                background-color: {pal['inset']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 8px;
                padding: 5px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {pal['gold']};
                color: {pal['button_ink']};
                border-color: {pal['gold']};
            }}
        """
        for b in (self.btn_convert, self.btn_tools, self.btn_copy, self.btn_clear, self.btn_collapse, self.btn_close):
            b.setStyleSheet(btn_style)
        self.update()

    def add_files(self, file_paths: List[str], show_shelf: bool = True):
        added = False
        for fp in file_paths:
            if not fp or not os.path.exists(fp):
                continue
            resolved = str(Path(fp).resolve())
            if resolved not in self._files:
                self._files.append(resolved)
                added = True
        self._refresh_list()
        if show_shelf:
            if not self.isVisible():
                pos = QCursor.pos()
                screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
                if screen:
                    avail = screen.availableGeometry()
                    x = max(avail.x() + 16, min(pos.x() + 24, avail.right() - self.width() - 16))
                    y = max(avail.y() + 16, min(pos.y() - 60, avail.bottom() - self.height() - 16))
                    self.move(x, y)
            self.show()
            self.raise_()

    def clear_files(self):
        self._files.clear()
        self._refresh_list()

    def _refresh_list(self):
        self.list_widget.clear()
        for fp in self._files:
            name = os.path.basename(fp)
            ext = os.path.splitext(name)[1].upper().lstrip(".") or "DOSYA"
            item = QListWidgetItem(f"[{ext}]  {name}")
            item.setData(Qt.ItemDataRole.UserRole, fp)
            item.setToolTip(fp)
            self.list_widget.addItem(item)
        self.lbl_badge.setText(f"📎 Float Rafı ({len(self._files)})")

    def toggle_collapse(self):
        self._collapsed = not self._collapsed
        self.body_widget.setVisible(not self._collapsed)
        self.btn_collapse.setText("+" if self._collapsed else "—")
        self.setFixedHeight(52 if self._collapsed else 310)

    def _copy_all(self):
        selected = [it.data(Qt.ItemDataRole.UserRole) for it in self.list_widget.selectedItems()]
        targets = selected if selected else self._files
        if targets:
            copy_files_to_clipboard(targets)
            self.btn_copy.setText("✓ Kopyalandı")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.btn_copy.setText("Kopyala"))

    def _emit_to_wheel(self, mode: str):
        selected = [it.data(Qt.ItemDataRole.UserRole) for it in self.list_widget.selectedItems()]
        targets = selected if selected else self._files
        if targets:
            self.files_sent_to_wheel.emit(list(targets), mode)

    # Drag & drop into shelf
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        files = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if files:
            self.add_files(files, show_shelf=False)
            event.acceptProposedAction()

    # Window dragging + edge snapping
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            screen = QGuiApplication.screenAt(event.globalPosition().toPoint()) or QGuiApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                # Edge snap within 20px
                if abs(new_pos.x() - avail.left()) < 20:
                    new_pos.setX(avail.left() + 8)
                elif abs((new_pos.x() + self.width()) - avail.right()) < 20:
                    new_pos.setX(avail.right() - self.width() - 8)
                if abs(new_pos.y() - avail.top()) < 20:
                    new_pos.setY(avail.top() + 8)
                elif abs((new_pos.y() + self.height()) - avail.bottom()) < 20:
                    new_pos.setY(avail.bottom() - self.height() - 8)
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        pal = get_theme_palette(self._theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)

        bg = QColor(pal["surface"])
        bg.setAlpha(242)
        painter.fillPath(path, bg)

        pen = QPen(QColor(pal["gold"]), 1.5)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()
