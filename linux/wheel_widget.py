"""
Nashi Linux - Radial Petal Wheel Widget
Ported directly from WheelGeometry.swift & Wheel.swift:
- Rounded annular petal sectors with centroid-placed symbol + label
- Golden gradient hover highlight with subtle Omarchy neon/gold border glow
- Center hub displaying mode title, file count/type badge, and live shortcut hints
- Full keyboard navigation (Arrows, Tab, Home/End, Enter/Space, Esc, 1/2/3).
"""

import math
from typing import List, Optional, Dict, Any, Tuple
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QFont, QBrush,
    QLinearGradient, QRadialGradient
)
from PySide6.QtWidgets import QWidget

from artwork import get_theme_palette, NashiArtwork


class WheelItem:
    """Represents a single slice/petal in the Nashi radial wheel."""

    def __init__(
        self,
        item_id: str,
        title: str,
        symbol: str = "",
        kind: str = "convert",
    ):
        self.id = item_id
        self.title = title
        self.symbol = symbol
        self.kind = kind  # 'convert', 'tool', 'action', 'web'

    def __repr__(self) -> str:
        return f"WheelItem(id={self.id!r}, title={self.title!r}, symbol={self.symbol!r})"


class RadialWheelWidget(QWidget):
    """
    Renders Nashi's signature radial petal wheel with centroid label placement,
    hover & keyboard selection, and drag-over slice tracking.
    """

    slice_selected = Signal(str)       # Emits WheelItem.id (or title if legacy)
    item_chosen = Signal(object)       # Emits WheelItem
    mode_switch_requested = Signal(str)  # 'convert', 'tools', 'actions'
    cancelled = Signal()

    def __init__(self, items: Optional[List[Any]] = None, parent=None):
        super().__init__(parent)
        self._items: List[WheelItem] = []
        self._cached_paths: List[QPainterPath] = []
        self._cached_size: Optional[Tuple[float, float, int]] = None
        self.hovered_index: int = -1
        self._theme: str = "dark"
        self._finish: str = "glass"  # 'glass' or 'metallic'
        self._center_title: str = "DÖNÜŞTÜR"
        self._center_subtitle: str = "Bırak veya Seç"
        self._file_badge: str = ""

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(320, 320)

        if items:
            self.set_items(items)

    # ------------------------------------------------------------------
    # Configuration API
    # ------------------------------------------------------------------
    def set_items(self, items: List[Any]):
        normalized: List[WheelItem] = []
        for it in items:
            if isinstance(it, WheelItem):
                normalized.append(it)
            elif isinstance(it, dict):
                normalized.append(WheelItem(
                    item_id=str(it.get("id", it.get("title", ""))),
                    title=str(it.get("title", "")),
                    symbol=str(it.get("symbol", "")),
                    kind=str(it.get("kind", "convert")),
                ))
            else:
                s = str(it)
                normalized.append(WheelItem(item_id=s, title=s, symbol=""))
        self._items = normalized[:12]  # Cap at 12 petals like WheelWindow.cs
        self._cached_size = None
        self._cached_paths = []
        if self.hovered_index >= len(self._items):
            self.hovered_index = -1
        self.update()

    @property
    def items(self) -> List[str]:
        """Legacy string list property for compatibility."""
        return [it.title for it in self._items]

    @property
    def wheel_items(self) -> List[WheelItem]:
        return list(self._items)

    def set_theme(self, theme: str, finish: str = "glass"):
        self._theme = theme
        self._finish = finish
        self.update()

    def set_center_info(self, title: str, subtitle: str = "Bırak veya Seç", file_badge: str = ""):
        self._center_title = title
        self._center_subtitle = subtitle
        self._file_badge = file_badge
        self.update()

    # ------------------------------------------------------------------
    # Geometry (Ported from WheelGeometry.swift)
    # ------------------------------------------------------------------
    def _geometry_params(self):
        w, h = float(self.width()), float(self.height())
        size = min(w, h)
        scale = size / 340.0
        center = QPointF(w / 2.0, h / 2.0)
        outer_r = size * 0.455
        inner_r = outer_r * 0.405
        count = max(1, len(self._items))
        start_deg = 180.0 if count == 3 else 90.0
        return center, outer_r, inner_r, scale, count, start_deg

    def _rebuild_cache_if_needed(self):
        w, h = float(self.width()), float(self.height())
        count = max(1, len(self._items))
        key = (w, h, count)
        if self._cached_size == key and len(self._cached_paths) == count:
            return

        self._cached_paths = []
        center, outer_r, inner_r, scale, count, start_deg = self._geometry_params()
        delta = 360.0 / count
        gap = 1.3 if count > 1 else 0.0

        rect_out = QRectF(center.x() - outer_r, center.y() - outer_r, outer_r * 2, outer_r * 2)

        for i in range(count):
            mid = start_deg - i * delta
            a = mid - delta / 2.0 + gap
            b = mid + delta / 2.0 - gap

            path = QPainterPath()
            a_rad = math.radians(a)
            path.moveTo(
                center.x() + inner_r * math.cos(a_rad),
                center.y() - inner_r * math.sin(a_rad),
            )
            path.lineTo(
                center.x() + outer_r * math.cos(a_rad),
                center.y() - outer_r * math.sin(a_rad),
            )
            path.arcTo(rect_out, a, b - a)
            b_rad = math.radians(b)
            path.lineTo(
                center.x() + inner_r * math.cos(b_rad),
                center.y() - inner_r * math.sin(b_rad),
            )
            path.closeSubpath()
            self._cached_paths.append(path)

        self._cached_size = key

    def _petal_path(self, index: int) -> QPainterPath:
        self._rebuild_cache_if_needed()
        if 0 <= index < len(self._cached_paths):
            return self._cached_paths[index]

        center, outer_r, inner_r, scale, count, start_deg = self._geometry_params()
        delta = 360.0 / count
        gap = 1.3 if count > 1 else 0.0
        mid = start_deg - index * delta
        a = mid - delta / 2.0 + gap
        b = mid + delta / 2.0 - gap

        path = QPainterPath()
        rect_out = QRectF(center.x() - outer_r, center.y() - outer_r, outer_r * 2, outer_r * 2)
        rect_in = QRectF(center.x() - inner_r, center.y() - inner_r, inner_r * 2, inner_r * 2)

        a_rad = math.radians(a)
        path.moveTo(
            center.x() + inner_r * math.cos(a_rad),
            center.y() - inner_r * math.sin(a_rad),
        )
        path.lineTo(
            center.x() + outer_r * math.cos(a_rad),
            center.y() - outer_r * math.sin(a_rad),
        )
        path.arcTo(rect_out, a, b - a)
        b_rad = math.radians(b)
        path.lineTo(
            center.x() + inner_r * math.cos(b_rad),
            center.y() - inner_r * math.sin(b_rad),
        )
        path.arcTo(rect_in, b, -(b - a))
        path.closeSubpath()
        return path

    def _petal_centroid(self, index: int) -> QPointF:
        center, outer_r, inner_r, scale, count, start_deg = self._geometry_params()
        delta = 360.0 / count
        mid_deg = start_deg - index * delta
        mid_rad = math.radians(mid_deg)
        sweep = math.radians(max(10.0, delta - 2.4))
        if count > 1:
            r_c = (
                4.0 * math.sin(sweep / 2.0) * (outer_r ** 3 - inner_r ** 3)
                / (3.0 * sweep * (outer_r ** 2 - inner_r ** 2))
            )
        else:
            r_c = (outer_r + inner_r) / 2.0
        # Clamp within comfortable visual band
        r_c = max(inner_r + (outer_r - inner_r) * 0.46, min(r_c, inner_r + (outer_r - inner_r) * 0.60))
        return QPointF(
            center.x() + r_c * math.cos(mid_rad),
            center.y() - r_c * math.sin(mid_rad),
        )

    def update_hover_at(self, pos: QPointF) -> int:
        """Updates hovered slice index from widget-local coordinates and returns it."""
        if not self._items:
            self.hovered_index = -1
            self.update()
            return -1

        center, outer_r, inner_r, scale, count, start_deg = self._geometry_params()
        dx = pos.x() - center.x()
        dy = center.y() - pos.y()  # Mathematical Y-up to match Qt arcTo angles
        dist = math.hypot(dx, dy)

        if dist < inner_r * 0.88 or dist > outer_r * 1.12:
            if self.hovered_index != -1:
                self.hovered_index = -1
                self.update()
            return -1

        angle_deg = math.degrees(math.atan2(dy, dx)) % 360.0
        delta = 360.0 / count
        # Slice 0 is centered at start_deg, subsequent slices go clockwise (decreasing angle)
        rel = (start_deg - angle_deg + delta / 2.0) % 360.0
        idx = int(rel // delta) % count

        if idx != self.hovered_index:
            self.hovered_index = idx
            self.update()
        return idx

    def current_selected_item(self) -> Optional[WheelItem]:
        if 0 <= self.hovered_index < len(self._items):
            return self._items[self.hovered_index]
        return None

    # ------------------------------------------------------------------
    # Mouse & Keyboard Events
    # ------------------------------------------------------------------
    def mouseMoveEvent(self, event):
        self.update_hover_at(event.position())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.hovered_index != -1:
            self.hovered_index = -1
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self.update_hover_at(event.position())
            if 0 <= idx < len(self._items):
                item = self._items[idx]
                self.item_chosen.emit(item)
                self.slice_selected.emit(item.id)
                return
            # Click outside any petal (center hub or blank area) cancels and closes
            self.cancelled.emit()
            return
        elif event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self.cancelled.emit()
            return

    def keyPressEvent(self, event):
        key = event.key()
        count = len(self._items)
        if key == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        if key == Qt.Key.Key_1:
            self.mode_switch_requested.emit("convert")
            event.accept()
            return
        if key == Qt.Key.Key_2:
            self.mode_switch_requested.emit("tools")
            event.accept()
            return
        if key == Qt.Key.Key_3:
            self.mode_switch_requested.emit("actions")
            event.accept()
            return

        if count == 0:
            super().keyPressEvent(event)
            return

        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Tab):
            self.hovered_index = 0 if self.hovered_index < 0 else (self.hovered_index + 1) % count
            self.update()
            event.accept()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Backtab):
            self.hovered_index = (count - 1) if self.hovered_index < 0 else (self.hovered_index - 1 + count) % count
            self.update()
            event.accept()
        elif key == Qt.Key.Key_Home:
            self.hovered_index = 0
            self.update()
            event.accept()
        elif key == Qt.Key.Key_End:
            self.hovered_index = count - 1
            self.update()
            event.accept()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            idx = max(0, self.hovered_index)
            if 0 <= idx < count:
                item = self._items[idx]
                self.item_chosen.emit(item)
                self.slice_selected.emit(item.id)
            event.accept()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        pal = get_theme_palette(self._theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        center, outer_r, inner_r, scale, count, start_deg = self._geometry_params()

        # 1. Translucent outer glass halo with subtle neon/gold rim
        halo_r = outer_r + 10.0 * scale
        halo_grad = QRadialGradient(center, halo_r)
        halo_bg = QColor(pal["paper"])
        halo_bg.setAlpha(205 if self._finish == "glass" else 242)
        halo_grad.setColorAt(0.0, halo_bg)
        halo_grad.setColorAt(0.88, halo_bg)
        halo_edge = QColor(pal["glow"])
        halo_edge.setAlpha(75)
        halo_grad.setColorAt(1.0, halo_edge)

        painter.setBrush(QBrush(halo_grad))
        rim_pen = QPen(QColor(pal["gold"]), 1.2)
        rim_col = rim_pen.color()
        rim_col.setAlpha(110)
        rim_pen.setColor(rim_col)
        painter.setPen(rim_pen)
        painter.drawEllipse(center, halo_r, halo_r)

        # 2. Draw each petal slice
        for i, item in enumerate(self._items):
            is_hovered = (i == self.hovered_index)
            path = self._petal_path(i)

            if is_hovered:
                grad = QLinearGradient(
                    center.x() - outer_r, center.y() - outer_r,
                    center.x() + outer_r, center.y() + outer_r
                )
                grad.setColorAt(0.0, QColor(pal["gold"]))
                grad.setColorAt(1.0, QColor(pal["gold_end"]))
                painter.fillPath(path, QBrush(grad))
                painter.setPen(QPen(QColor(pal["ink"]), 1.8))
            else:
                slice_col = QColor(pal["surface"] if self._finish == "glass" else pal["inset"])
                slice_col.setAlpha(228 if self._finish == "glass" else 250)
                painter.fillPath(path, QBrush(slice_col))
                border_col = QColor(pal["line"])
                border_col.setAlpha(185)
                painter.setPen(QPen(border_col, 1.1))

            painter.drawPath(path)

            # Label + Symbol at petal centroid
            pt = self._petal_centroid(i)
            fg_col = QColor(pal["button_ink"] if is_hovered else pal["ink"])
            painter.setPen(fg_col)

            title_text = item.title
            if item.symbol:
                # Draw symbol on top, title below
                sym_font = QFont("Sans Serif", max(10, int(13 * scale)), QFont.Weight.Bold)
                painter.setFont(sym_font)
                sym_rect = QRectF(pt.x() - 42 * scale, pt.y() - 21 * scale, 84 * scale, 20 * scale)
                painter.drawText(sym_rect, Qt.AlignmentFlag.AlignCenter, item.symbol)

                lbl_font = QFont("Sans Serif", max(7, int(8.5 * scale)), QFont.Weight.Bold)
                painter.setFont(lbl_font)
                lbl_rect = QRectF(pt.x() - 46 * scale, pt.y() - 1 * scale, 92 * scale, 24 * scale)
                painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, title_text)
            else:
                lbl_font = QFont("Sans Serif", max(8, int(10.5 * scale)), QFont.Weight.ExtraBold)
                painter.setFont(lbl_font)
                lbl_rect = QRectF(pt.x() - 44 * scale, pt.y() - 14 * scale, 88 * scale, 28 * scale)
                painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, title_text)

        # 3. Center Hub Disc
        hub_r = inner_r - 5.0 * scale
        hub_col = QColor(pal["paper"])
        hub_col.setAlpha(248)
        painter.setBrush(QBrush(hub_col))
        hub_pen = QPen(QColor(pal["gold"]), 1.6)
        painter.setPen(hub_pen)
        painter.drawEllipse(center, hub_r, hub_r)

        # Small Nashi pear icon at top of center hub
        pear_s = 24.0 * scale
        NashiArtwork.draw(
            painter,
            QRectF(center.x() - pear_s / 2.0, center.y() - hub_r + 8.0 * scale, pear_s, pear_s),
            happy=(self.hovered_index >= 0),
        )

        # Center hub text
        if 0 <= self.hovered_index < len(self._items):
            active_title = self._items[self.hovered_index].title
            sub_text = "Bırak veya Enter"
        else:
            active_title = self._center_title
            sub_text = self._center_subtitle

        title_font = QFont("Sans Serif", max(8, int(10 * scale)), QFont.Weight.ExtraBold)
        painter.setFont(title_font)
        painter.setPen(QColor(pal["gold"]))
        painter.drawText(
            QRectF(center.x() - hub_r + 6, center.y() - 6 * scale, (hub_r - 6) * 2, 22 * scale),
            Qt.AlignmentFlag.AlignCenter,
            active_title,
        )

        sub_font = QFont("Sans Serif", max(6, int(7.5 * scale)), QFont.Weight.Medium)
        painter.setFont(sub_font)
        painter.setPen(QColor(pal["muted"]))
        badge_or_sub = self._file_badge if self._file_badge else sub_text
        painter.drawText(
            QRectF(center.x() - hub_r + 8, center.y() + 13 * scale, (hub_r - 8) * 2, 18 * scale),
            Qt.AlignmentFlag.AlignCenter,
            badge_or_sub,
        )

        painter.end()
