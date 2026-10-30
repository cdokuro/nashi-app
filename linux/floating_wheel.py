"""
Nashi Linux - Dynamic Context-Aware Floating Radial Wheel
Ported from Wheel.swift and GlobalDragController.cs (GlobalDropWheel):
- Dynamically populates slices from FeatureCatalog.json based on dragged/selected files or web URLs
- Supports live mode switching (Shift: Convert, Ctrl: Tools, Alt: Actions, or 1/2/3 keys)
- Accepts real drag-and-drop from Dolphin / Desktop / browsers without losing hover tracking
- Works both during an active global mouse drag and when invoked via keyboard shortcuts.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple
from PySide6.QtCore import Qt, QPoint, QPointF, QTimer, Signal, QEvent
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QWidget, QVBoxLayout, QApplication

from wheel_widget import RadialWheelWidget, WheelItem
from engine import NashiEngine
from store import NashiStore, get_store


class FloatingRadialWheel(QWidget):
    """
    Frameless, always-on-top radial overlay window that appears centered at the cursor.
    Supports both drag-and-drop release (`dropEvent`) and click/keyboard selection.
    """

    action_triggered = Signal(str, str, list)  # (mode, item_id, file_paths)

    def __init__(
        self,
        engine: Optional[NashiEngine] = None,
        store: Optional[NashiStore] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.engine = engine or NashiEngine()
        self.store = store or get_store()

        self.current_mode: str = "convert"  # 'convert', 'tools', 'actions'
        self.current_files: List[str] = []
        self.current_web_url: Optional[str] = None
        self.drag_session_active: bool = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)

        self._base_diameter = 350
        self.setFixedSize(self._base_diameter, self._base_diameter)
        self._filter_installed: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.wheel = RadialWheelWidget(parent=self)
        self.wheel.item_chosen.connect(self._on_item_chosen)
        self.wheel.mode_switch_requested.connect(self.switch_mode)
        self.wheel.cancelled.connect(self._on_cancelled)
        layout.addWidget(self.wheel)

    # ------------------------------------------------------------------
    # Dynamic Slice Computation (FeatureCatalog.json)
    # ------------------------------------------------------------------
    def _build_items_for_context(self, mode: str, files: List[str], web_url: Optional[str] = None) -> List[WheelItem]:
        lang = self.store.get_preference("language", "tr")

        if web_url:
            return [
                WheelItem("web:video", "Video İndir", "🎬", "web"),
                WheelItem("web:audio", "MP3 Ses İndir", "🎵", "web"),
                WheelItem("web:thumbnail", "Kapak Görseli", "🖼️", "web"),
                WheelItem("web:copy", "Linki Kopyala", "🔗", "web"),
                WheelItem("web:open", "Tarayıcıda Aç", "🌐", "web"),
            ]

        if mode == "convert":
            targets = self.engine.get_available_targets_for_files(files)
            if not targets:
                targets = ["png", "jpg", "webp", "pdf", "mp4", "mp3", "gif", "zip"]
            items = []
            for fmt in targets[:10]:
                label = "GZIP" if fmt == "gz" else fmt.upper()
                items.append(WheelItem(fmt, label, "", "convert"))
            return items

        if mode == "tools":
            tool_ids = self.engine.get_available_tools_for_files(files)
            items = []
            for tid in tool_ids[:10]:
                title = self.engine.get_tool_name(tid, lang=lang)
                sym = self.engine.get_tool_symbol(tid)
                items.append(WheelItem(tid, title, sym, "tool"))
            return items

        # mode == 'actions'
        actions = self.engine.get_file_actions(lang=lang)
        return [
            WheelItem(a["id"], a["title"], a["symbol"], "action")
            for a in actions
        ]

    def _compute_badge_text(self, files: List[str], web_url: Optional[str]) -> str:
        if web_url:
            return "WEB BAĞLANTISI"
        if not files:
            return "Shift · Ctrl · Alt"
        if len(files) == 1:
            ext = self.engine.normalize_extension(files[0]).upper() or "DOSYA"
            name = os.path.basename(files[0])
            if len(name) > 16:
                name = name[:13] + "…"
            return f"{ext} · {name}"
        return f"{len(files)} DOSYA SEÇİLİ"

    def _refresh_wheel(self):
        theme = self.store.get_preference("theme", "dark")
        finish = self.store.get_preference("wheel_finish", "glass")
        scale = float(self.store.get_preference("wheel_scale", 1.0))
        diameter = int(round(350 * max(0.8, min(1.3, scale))))
        if self.width() != diameter:
            self.setFixedSize(diameter, diameter)

        self.wheel.set_theme(theme, finish=finish)
        items = self._build_items_for_context(self.current_mode, self.current_files, self.current_web_url)
        self.wheel.set_items(items)

        mode_titles = {
            "convert": "DÖNÜŞTÜR",
            "tools": "ARAÇLAR",
            "actions": "İŞLEMLER",
        }
        badge = self._compute_badge_text(self.current_files, self.current_web_url)
        self.wheel.set_center_info(
            title=mode_titles.get(self.current_mode, "NASHI"),
            subtitle="Bırak veya Seç",
            file_badge=badge,
        )

    # ------------------------------------------------------------------
    # Public Show & Switch Methods
    # ------------------------------------------------------------------
    def pop_at_cursor(
        self,
        mode: str = "convert",
        files: Optional[List[str]] = None,
        cursor_pos: Optional[Tuple[int, int]] = None,
        drag_mode: bool = False,
    ):
        """Shows the radial wheel centered at the given (x, y) or current cursor."""
        self.current_mode = mode if mode in ("convert", "tools", "actions") else "convert"
        self.drag_session_active = drag_mode

        if files is not None:
            self.current_files = [f for f in files if f and os.path.exists(f)]
            self.current_web_url = None
        elif not self.current_files:
            # Try inspecting clipboard for copied files or web link if opened via shortcut
            self._inspect_clipboard_fallback()

        self._refresh_wheel()

        if cursor_pos is not None:
            cx, cy = cursor_pos
            pos = QPoint(int(cx), int(cy))
        else:
            pos = QCursor.pos()

        # Clamp within screen bounds so the wheel is never cut off
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        half = self.width() // 2
        target_x = pos.x() - half
        target_y = pos.y() - half
        if screen:
            avail = screen.availableGeometry()
            target_x = max(avail.left() + 8, min(target_x, avail.right() - self.width() - 8))
            target_y = max(avail.top() + 8, min(target_y, avail.bottom() - self.height() - 8))

        self.move(target_x, target_y)

        if drag_mode:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.show()
            self.raise_()
            self.move(target_x, target_y)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            self.show()
            self.raise_()
            self.move(target_x, target_y)
            self.activateWindow()
            self.setFocus()
            self.wheel.setFocus()
            if self.wheel.wheel_items and self.wheel.hovered_index < 0:
                self.wheel.hovered_index = 0
                self.wheel.update()

    def switch_mode(self, new_mode: str):
        """Live switches between 'convert', 'tools', and 'actions' without closing the wheel."""
        if new_mode in ("convert", "tools", "actions") and new_mode != self.current_mode:
            self.current_mode = new_mode
            self._refresh_wheel()

    def update_external_cursor(self, global_x: int, global_y: int):
        """Called by GlobalDragController. Ignored during active Qt drag session to prevent jitter."""
        if not self.isVisible() or self.drag_session_active:
            return
        local_pt = self.wheel.mapFromGlobal(QPoint(int(global_x), int(global_y)))
        self.wheel.update_hover_at(QPointF(local_pt))

    def _inspect_clipboard_fallback(self):
        cb = QApplication.clipboard()
        mime = cb.mimeData()
        if not mime:
            return
        if mime.hasUrls():
            local_files = [u.toLocalFile() for u in mime.urls() if u.isLocalFile() and os.path.exists(u.toLocalFile())]
            if local_files:
                self.current_files = local_files
                self.current_web_url = None
                return
        text = mime.text().strip() if mime.hasText() else ""
        if self.engine.is_web_url(text):
            self.current_web_url = text

    # ------------------------------------------------------------------
    # Drag & Drop Events (Dropping files from Dolphin / Desktop onto Wheel)
    # ------------------------------------------------------------------
    def _extract_mime_payload(self, mime) -> Tuple[List[str], Optional[str]]:
        files: List[str] = []
        web_url: Optional[str] = None
        if mime.hasUrls():
            for u in mime.urls():
                if u.isLocalFile():
                    lf = u.toLocalFile()
                    if lf and os.path.exists(lf):
                        files.append(str(Path(lf).resolve()))
                else:
                    s = u.toString()
                    if self.engine.is_web_url(s):
                        web_url = s
        if not files and not web_url and mime.hasText():
            txt = mime.text().strip()
            if self.engine.is_web_url(txt):
                web_url = txt
            else:
                for line in txt.splitlines():
                    line = line.strip()
                    if line.startswith("file://"):
                        from PySide6.QtCore import QUrl
                        lf = QUrl(line).toLocalFile()
                        if lf and os.path.exists(lf):
                            files.append(str(Path(lf).resolve()))
                    elif os.path.exists(line):
                        files.append(str(Path(line).resolve()))
        return files, web_url

    def dragEnterEvent(self, event):
        files, web_url = self._extract_mime_payload(event.mimeData())
        if files or web_url:
            if files != self.current_files or web_url != self.current_web_url:
                self.current_files = files
                self.current_web_url = web_url
                self._refresh_wheel()
            self.wheel.update_hover_at(event.position())
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        # Allow live modifier switching during dragMoveEvent as well
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier and self.current_mode != "tools":
            self.switch_mode("tools")
        elif mods & Qt.KeyboardModifier.AltModifier and self.current_mode != "actions":
            self.switch_mode("actions")
        elif mods & Qt.KeyboardModifier.ShiftModifier and self.current_mode != "convert":
            self.switch_mode("convert")

        idx = self.wheel.update_hover_at(event.position())
        if idx >= 0:
            event.acceptProposedAction()
        else:
            event.accept()

    def dragLeaveEvent(self, event):
        self.wheel.hovered_index = -1
        self.wheel.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        files, web_url = self._extract_mime_payload(event.mimeData())
        if files:
            self.current_files = files
        if web_url:
            self.current_web_url = web_url

        idx = self.wheel.update_hover_at(event.position())
        selected = self.wheel.current_selected_item()
        if selected is None and self.wheel.wheel_items and idx >= 0:
            selected = self.wheel.wheel_items[idx]

        self.drag_session_active = False
        self.hide()

        if selected is not None:
            payload = [self.current_web_url] if self.current_web_url else list(self.current_files)
            self.action_triggered.emit(self.current_mode, selected.id, payload)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ------------------------------------------------------------------
    # Click / Keyboard Selection
    # ------------------------------------------------------------------
    def _on_item_chosen(self, item: WheelItem):
        self.drag_session_active = False
        self.hide()
        payload = [self.current_web_url] if self.current_web_url else list(self.current_files)
        self.action_triggered.emit(self.current_mode, item.id, payload)

    def _on_cancelled(self):
        self.drag_session_active = False
        self.hide()

    # ------------------------------------------------------------------
    # Dismissal on Escape, Focus Loss & Click Outside
    # ------------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.drag_session_active = False
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow() and not self.drag_session_active:
                self.hide()
        super().changeEvent(event)

    def focusOutEvent(self, event):
        if not self.drag_session_active and not self.isActiveWindow():
            self.hide()
        super().focusOutEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        app = QApplication.instance()
        if app and not self._filter_installed:
            app.installEventFilter(self)
            self._filter_installed = True

    def hideEvent(self, event):
        app = QApplication.instance()
        if app and self._filter_installed:
            app.removeEventFilter(self)
            self._filter_installed = False
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if self.isVisible():
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                self.drag_session_active = False
                self.hide()
                return True
            if event.type() == QEvent.Type.MouseButtonPress and not self.drag_session_active:
                if hasattr(event, "globalPosition"):
                    gpos = event.globalPosition().toPoint()
                else:
                    gpos = QCursor.pos()
                if not self.geometry().contains(gpos):
                    self.hide()
        return super().eventFilter(watched, event)
