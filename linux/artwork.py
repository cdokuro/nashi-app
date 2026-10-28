"""
Nashi Linux - Vector Artwork, FileGarden Illustration & Theme Palettes
Ported directly from NashiArtwork.swift, FileGarden.cs, and Theme.cs,
plus Omarchy-inspired Catppuccin and Rose Pine themes.
"""

from typing import Dict, Any
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QBrush, QLinearGradient,
    QFont, QPixmap, QIcon
)
from PySide6.QtWidgets import QWidget


THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "name": "Forest Dark (Nashi)",
        "paper": "#111A14",
        "surface": "#1C281F",
        "inset": "#151F18",
        "ink": "#E7EBE6",
        "muted": "#A9B5A8",
        "line": "#344237",
        "sage": "#243928",
        "sand": "#3C3421",
        "gold": "#E3B859",
        "gold_end": "#F5D17D",
        "button_ink": "#1A2112",
        "glow": "#E3B859",
    },
    "light": {
        "name": "Warm Paper (Nashi)",
        "paper": "#F9F6ED",
        "surface": "#FFFEF7",
        "inset": "#F1EDE0",
        "ink": "#243B2B",
        "muted": "#596650",
        "line": "#DCDDD1",
        "sage": "#E0EBD2",
        "sand": "#F6E7BE",
        "gold": "#E3B859",
        "gold_end": "#F5D17D",
        "button_ink": "#2B351C",
        "glow": "#D4A338",
    },
    "catppuccin": {
        "name": "Catppuccin Mocha",
        "paper": "#181825",
        "surface": "#1E1E2E",
        "inset": "#11111B",
        "ink": "#CDD6F4",
        "muted": "#A6ADC8",
        "line": "#313244",
        "sage": "#292B3D",
        "sand": "#352F44",
        "gold": "#F9E2AF",
        "gold_end": "#FAB387",
        "button_ink": "#11111B",
        "glow": "#CBA6F7",
    },
    "rosepine": {
        "name": "Rose Pine",
        "paper": "#191724",
        "surface": "#1F1D2E",
        "inset": "#14121D",
        "ink": "#E0DEF4",
        "muted": "#908CAA",
        "line": "#2A273F",
        "sage": "#26233A",
        "sand": "#393040",
        "gold": "#F6C177",
        "gold_end": "#EBBCBA",
        "button_ink": "#191724",
        "glow": "#EBBCBA",
    },
}


def get_theme_palette(theme_name: str = "dark") -> Dict[str, str]:
    return THEMES.get(theme_name, THEMES["dark"])


class NashiArtwork:
    """Draws the official Nashi Asian pear mascot with stem, leaf, speckles, and smile."""

    GOLD = QColor(227, 184, 89)
    GOLD_LIGHT = QColor(250, 219, 148)
    INK = QColor(51, 64, 36)
    LEAF = QColor(125, 158, 92)
    STEM = QColor(97, 74, 38)

    @staticmethod
    def body_path() -> QPainterPath:
        p = QPainterPath()
        p.moveTo(0.50, 0.235)
        p.cubicTo(0.60, 0.17, 0.79, 0.23, 0.865, 0.36)
        p.cubicTo(0.99, 0.56, 0.85, 0.85, 0.66, 0.905)
        p.cubicTo(0.43, 0.99, 0.16, 0.88, 0.13, 0.64)
        p.cubicTo(0.08, 0.39, 0.26, 0.18, 0.43, 0.228)
        p.quadTo(0.468, 0.25, 0.50, 0.235)
        p.closeSubpath()
        return p

    @staticmethod
    def leaf_path() -> QPainterPath:
        p = QPainterPath()
        p.moveTo(0.49, 0.17)
        p.cubicTo(0.53, 0.03, 0.73, 0.065, 0.74, 0.115)
        p.cubicTo(0.66, 0.24, 0.56, 0.23, 0.49, 0.17)
        p.closeSubpath()
        return p

    @classmethod
    def draw(cls, painter: QPainter, rect: QRectF, happy: bool = False):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.translate(rect.left(), rect.top())
        painter.scale(rect.width(), rect.height())

        # 1. Pear body with warm golden gradient
        body = cls.body_path()
        grad = QLinearGradient(QPointF(0.2, 0.25), QPointF(0.85, 0.95))
        grad.setColorAt(0.0, cls.GOLD_LIGHT)
        grad.setColorAt(1.0, cls.GOLD)
        painter.fillPath(body, QBrush(grad))

        # 2. Leaf
        leaf = cls.leaf_path()
        painter.fillPath(leaf, QBrush(cls.LEAF))

        # 3. Highlight sheen
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 62))
        painter.drawEllipse(QRectF(0.24, 0.32, 0.085, 0.16))

        # 4. Pear speckles
        speckle_color = QColor(cls.INK)
        speckle_color.setAlpha(48)
        painter.setBrush(speckle_color)
        speckles = [
            (0.27, 0.48), (0.65, 0.37), (0.34, 0.75),
            (0.72, 0.69), (0.21, 0.61), (0.77, 0.50),
            (0.57, 0.82), (0.68, 0.77), (0.38, 0.34),
        ]
        for sx, sy in speckles:
            painter.drawEllipse(QRectF(sx, sy, 0.018, 0.018))

        # 5. Eyes
        painter.setBrush(cls.INK)
        eye_h = 0.038 if happy else 0.065
        for ex in (0.39, 0.59):
            eye_path = QPainterPath()
            eye_path.addRoundedRect(QRectF(ex, 0.51, 0.045, eye_h), 0.0225, 0.0225)
            painter.fillPath(eye_path, cls.INK)

        # 6. Smile
        smile_pen = QPen(cls.INK, 0.028, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(smile_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        smile = QPainterPath()
        smile.moveTo(0.45, 0.64)
        smile.quadTo(0.50, 0.72 if happy else 0.70, 0.55, 0.64)
        painter.drawPath(smile)

        # 7. Stem
        stem_pen = QPen(cls.STEM, 0.035, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(stem_pen)
        stem = QPainterPath()
        stem.moveTo(0.49, 0.24)
        stem.quadTo(0.455, 0.18, 0.47, 0.12)
        painter.drawPath(stem)

        painter.restore()

    @classmethod
    def pixmap(cls, size: int = 64, happy: bool = False) -> QPixmap:
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        cls.draw(p, QRectF(0, 0, size, size), happy=happy)
        p.end()
        return pix

    @classmethod
    def icon(cls, size: int = 64, happy: bool = False) -> QIcon:
        return QIcon(cls.pixmap(size=size, happy=happy))


class NashiMarkWidget(QWidget):
    """Reusable vector Nashi pear mascot widget."""

    def __init__(self, size: int = 40, happy: bool = False, parent=None):
        super().__init__(parent)
        self._size = size
        self._happy = happy
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_happy(self, happy: bool):
        if self._happy != happy:
            self._happy = happy
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        NashiArtwork.draw(painter, QRectF(0, 0, self.width(), self.height()), happy=self._happy)
        painter.end()


class FileGardenWidget(QWidget):
    """
    Port of Nashi's FileGarden illustration (FileGarden.cs / HomeView.swift):
    Sand-colored circle backdrop, tilted PDF and PNG cards, and Nashi pear mascot in front.
    """

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self._theme = theme
        self._happy = False
        self.setFixedSize(176, 156)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_theme(self, theme: str):
        self._theme = theme
        self.update()

    def set_selected(self, selected: bool):
        if self._happy != selected:
            self._happy = selected
            self.update()

    def _draw_card(
        self,
        painter: QPainter,
        label: str,
        angle: float,
        dx: float,
        dy: float,
        accent: QColor,
        surface: QColor,
        border: QColor,
    ):
        painter.save()
        cx, cy = self.width() / 2.0 + dx, self.height() / 2.0 + dy
        painter.translate(cx, cy)
        painter.rotate(angle)

        w, h = 78.0, 102.0
        card_rect = QRectF(-w / 2.0, -h / 2.0, w, h)

        # Subtle shadow
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(card_rect.translated(0, 4), 15, 15)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 38))

        # Card surface
        path = QPainterPath()
        path.addRoundedRect(card_rect, 15, 15)
        painter.fillPath(path, surface)
        painter.setPen(QPen(border, 1.2))
        painter.drawPath(path)

        # Inner content origin
        ix, iy = -w / 2.0 + 13.0, -h / 2.0 + 13.0
        icon_pen = QPen(accent, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(icon_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if label == "PDF":
            doc = QPainterPath()
            doc.moveTo(ix + 3, iy + 1)
            doc.lineTo(ix + 18, iy + 1)
            doc.lineTo(ix + 25, iy + 8)
            doc.lineTo(ix + 25, iy + 27)
            doc.lineTo(ix + 3, iy + 27)
            doc.closeSubpath()
            doc.moveTo(ix + 18, iy + 1)
            doc.lineTo(ix + 18, iy + 8)
            doc.lineTo(ix + 25, iy + 8)
            doc.moveTo(ix + 8, iy + 13)
            doc.lineTo(ix + 20, iy + 13)
            doc.moveTo(ix + 8, iy + 18)
            doc.lineTo(ix + 20, iy + 18)
            doc.moveTo(ix + 8, iy + 23)
            doc.lineTo(ix + 16, iy + 23)
            painter.drawPath(doc)
        else:
            img = QPainterPath()
            img.addRoundedRect(QRectF(ix + 1, iy + 3, 26, 22), 3, 3)
            img.moveTo(ix + 2, iy + 23)
            img.lineTo(ix + 10, iy + 14)
            img.lineTo(ix + 16, iy + 19)
            img.lineTo(ix + 21, iy + 13)
            img.lineTo(ix + 27, iy + 21)
            painter.drawPath(img)
            painter.drawEllipse(QRectF(ix + 6, iy + 7, 4, 4))

        # Label
        font = QFont("Sans Serif", 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(accent)
        painter.drawText(QRectF(ix, iy + 35, 50, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

        # Decorative bar
        bar_color = QColor(accent)
        bar_color.setAlpha(48)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bar_color)
        painter.drawRoundedRect(QRectF(ix, iy + 56, 36, 4), 2, 2)

        painter.restore()

    def paintEvent(self, event):
        pal = get_theme_palette(self._theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Sand circle backdrop
        sand_color = QColor(pal["sand"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(sand_color)
        circle_r = 142.0
        painter.drawEllipse(QRectF(
            (self.width() - circle_r) / 2.0,
            (self.height() - circle_r) / 2.0,
            circle_r,
            circle_r,
        ))

        surface_col = QColor(pal["surface"])
        line_col = QColor(pal["line"])
        muted_col = QColor(pal["muted"])
        gold_col = QColor(pal["gold"])

        # 2. Tilted PDF & PNG cards
        self._draw_card(painter, "PDF", -16.0, -32.0, 4.0, muted_col, surface_col, line_col)
        self._draw_card(painter, "PNG", 7.0, 29.0, -8.0, gold_col, surface_col, line_col)

        # 3. Foreground Nashi mascot
        pear_size = 68.0
        pear_rect = QRectF(
            (self.width() - pear_size) / 2.0,
            self.height() - pear_size - 4.0,
            pear_size,
            pear_size,
        )
        NashiArtwork.draw(painter, pear_rect, happy=self._happy)
        painter.end()
