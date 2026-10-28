"""
Nashi Linux - Interactive Tool Editors (Crop, Photo Edit/Frame/Redact, Media Trim/Speed)
Ported from mac-crop.png, ToolEditor.swift, CropSelectionGeometry.swift & MediaTimeline.swift.
"""

import os
from typing import Optional, Dict, Any, Tuple
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QPen, QPixmap, QFont
)
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QSlider, QComboBox, QLineEdit, QFrame
)

from artwork import get_theme_palette


class InteractiveCropCanvas(QWidget):
    """Interactive image crop preview canvas with draggable handles and Shift ratio lock."""

    selection_changed = Signal(int, int, int, int)  # (x, y, w, h) in source image pixels

    def __init__(self, image_path: str, theme: str = "dark", parent=None):
        super().__init__(parent)
        self._theme = theme
        self._pixmap = QPixmap(image_path)
        self.img_w = max(1, self._pixmap.width())
        self.img_h = max(1, self._pixmap.height())

        # Selection in source image pixel coordinates
        self.sel_x = int(self.img_w * 0.1)
        self.sel_y = int(self.img_h * 0.1)
        self.sel_w = int(self.img_w * 0.8)
        self.sel_h = int(self.img_h * 0.8)

        self._aspect_ratio: Optional[Tuple[int, int]] = None
        self._dragging = False
        self._drag_mode = "new"  # 'new' or 'move'
        self._drag_start = QPointF()
        self._orig_sel = (0, 0, 0, 0)

        self.setMinimumSize(420, 320)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _image_rect_on_widget(self) -> QRectF:
        pad = 16.0
        avail_w = max(40.0, self.width() - pad * 2)
        avail_h = max(40.0, self.height() - pad * 2)
        scale = min(avail_w / self.img_w, avail_h / self.img_h)
        dw = self.img_w * scale
        dh = self.img_h * scale
        dx = (self.width() - dw) / 2.0
        dy = (self.height() - dh) / 2.0
        return QRectF(dx, dy, dw, dh)

    def _widget_to_image(self, pt: QPointF) -> Tuple[int, int]:
        ir = self._image_rect_on_widget()
        if ir.width() <= 0 or ir.height() <= 0:
            return 0, 0
        rx = (pt.x() - ir.left()) / ir.width()
        ry = (pt.y() - ir.top()) / ir.height()
        ix = int(round(max(0.0, min(1.0, rx)) * self.img_w))
        iy = int(round(max(0.0, min(1.0, ry)) * self.img_h))
        return ix, iy

    def _selection_rect_on_widget(self) -> QRectF:
        ir = self._image_rect_on_widget()
        sx = ir.left() + (self.sel_x / float(self.img_w)) * ir.width()
        sy = ir.top() + (self.sel_y / float(self.img_h)) * ir.height()
        sw = (self.sel_w / float(self.img_w)) * ir.width()
        sh = (self.sel_h / float(self.img_h)) * ir.height()
        return QRectF(sx, sy, sw, sh)

    def set_aspect_preset(self, ratio: Optional[Tuple[int, int]]):
        self._aspect_ratio = ratio
        if ratio is not None:
            aw, ah = ratio
            target = aw / float(ah)
            curr = self.img_w / float(self.img_h)
            if curr > target:
                self.sel_h = int(self.img_h * 0.85)
                self.sel_w = int(round(self.sel_h * target))
            else:
                self.sel_w = int(self.img_w * 0.85)
                self.sel_h = int(round(self.sel_w / target))
            self.sel_x = max(0, (self.img_w - self.sel_w) // 2)
            self.sel_y = max(0, (self.img_h - self.sel_h) // 2)
            self.selection_changed.emit(self.sel_x, self.sel_y, self.sel_w, self.sel_h)
            self.update()

    def select_all(self):
        self.sel_x, self.sel_y = 0, 0
        self.sel_w, self.sel_h = self.img_w, self.img_h
        self.selection_changed.emit(self.sel_x, self.sel_y, self.sel_w, self.sel_h)
        self.update()

    def set_selection_values(self, x: int, y: int, w: int, h: int):
        self.sel_x = max(0, min(x, self.img_w - 1))
        self.sel_y = max(0, min(y, self.img_h - 1))
        self.sel_w = max(1, min(w, self.img_w - self.sel_x))
        self.sel_h = max(1, min(h, self.img_h - self.sel_y))
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.position()
            sel_rect = self._selection_rect_on_widget()
            if sel_rect.contains(event.position()):
                self._drag_mode = "move"
                self._orig_sel = (self.sel_x, self.sel_y, self.sel_w, self.sel_h)
            else:
                self._drag_mode = "new"
                ix, iy = self._widget_to_image(event.position())
                self._orig_sel = (ix, iy, 1, 1)

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        ix, iy = self._widget_to_image(event.position())
        ox, oy, ow, oh = self._orig_sel

        if self._drag_mode == "move":
            sx, sy = self._widget_to_image(self._drag_start)
            dx = ix - sx
            dy = iy - sy
            self.sel_x = max(0, min(ox + dx, self.img_w - ow))
            self.sel_y = max(0, min(oy + dy, self.img_h - oh))
        else:
            x0, x1 = min(ox, ix), max(ox, ix)
            y0, y1 = min(oy, iy), max(oy, iy)
            w = max(8, x1 - x0)
            h = max(8, y1 - y0)

            ratio = self._aspect_ratio
            if ratio is None and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                ratio = (1, 1)
            if ratio is not None:
                aw, ah = ratio
                h = max(8, int(round(w * (ah / float(aw)))))
                if y0 + h > self.img_h:
                    h = self.img_h - y0
                    w = max(8, int(round(h * (aw / float(ah)))))

            self.sel_x = max(0, min(x0, self.img_w - w))
            self.sel_y = max(0, min(y0, self.img_h - h))
            self.sel_w = w
            self.sel_h = h

        self.selection_changed.emit(self.sel_x, self.sel_y, self.sel_w, self.sel_h)
        self.update()

    def mouseReleaseEvent(self, event):
        self._dragging = False
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        pal = get_theme_palette(self._theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Canvas backdrop
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 18, 18)
        painter.fillPath(bg_path, QColor(pal["inset"]))

        ir = self._image_rect_on_widget()
        if not self._pixmap.isNull():
            painter.drawPixmap(ir.toRect(), self._pixmap)

        # Darken outside crop selection
        sel_r = self._selection_rect_on_widget()
        outer_path = QPainterPath()
        outer_path.addRect(ir)
        inner_path = QPainterPath()
        inner_path.addRect(sel_r)
        scrim_path = outer_path.subtracted(inner_path)
        painter.fillPath(scrim_path, QColor(0, 0, 0, 135))

        # Gold crop border & 8 handles (matching mac-crop.png)
        gold = QColor(pal["gold"])
        painter.setPen(QPen(gold, 2.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(sel_r)

        painter.setBrush(gold)
        hs = 8.0
        handle_pts = [
            sel_r.topLeft(),
            sel_r.topRight(),
            sel_r.bottomLeft(),
            sel_r.bottomRight(),
            QPointF(sel_r.center().x(), sel_r.top()),
            QPointF(sel_r.center().x(), sel_r.bottom()),
            QPointF(sel_r.left(), sel_r.center().y()),
            QPointF(sel_r.right(), sel_r.center().y()),
        ]
        for hp in handle_pts:
            painter.drawRoundedRect(QRectF(hp.x() - hs / 2, hp.y() - hs / 2, hs, hs), 2, 2)

        painter.end()


class CropEditorDialog(QDialog):
    """
    Replica of Nashi's macOS Crop Image Editor (mac-crop.png):
    Left: Interactive preview with dimensions & filename
    Right: Aspect ratio segmented buttons (Free, 1:1, 16:9, 9:16, 4:3, 3:4), W/H/X/Y inputs, Select All
    Bottom: Reset, 'Original stays safe', and gold 'Save cropped copy' button.
    """

    def __init__(self, image_path: str, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self._theme = theme
        self._updating_spins = False

        self.setWindowTitle("Görseli Kırp — Nashi")
        self.resize(860, 560)
        self._init_ui()
        self._apply_theme()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        lbl_icon = QLabel("✂️")
        lbl_icon.setFixedSize(44, 44)
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setObjectName("EditorBadge")
        hdr.addWidget(lbl_icon)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.lbl_title = QLabel("Görseli Kırp (Crop Image)")
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: 800;")
        self.lbl_sub = QLabel("İyi kısmı koru. Oran kilitlemek için Shift basılı tut; kaydetmek için Enter'a bas.")
        self.lbl_sub.setStyleSheet("font-size: 12px;")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_sub)
        hdr.addLayout(title_col)
        hdr.addStretch()

        ext = os.path.splitext(self.image_path)[1].upper().lstrip(".") or "IMG"
        self.lbl_pill = QLabel(f"📄 {ext}")
        self.lbl_pill.setObjectName("FormatPill")
        hdr.addWidget(self.lbl_pill)
        root.addLayout(hdr)

        # Body (Left Preview + Right Controls)
        body = QHBoxLayout()
        body.setSpacing(24)

        # Left Preview Column
        left_col = QVBoxLayout()
        left_hdr = QHBoxLayout()
        self.lbl_prev_hdr = QLabel("ÖNİZLEME (PREVIEW)")
        self.lbl_prev_hdr.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        left_hdr.addWidget(self.lbl_prev_hdr)
        left_hdr.addStretch()
        self.canvas = InteractiveCropCanvas(self.image_path, theme=self._theme)
        self.lbl_dims = QLabel(f"{self.canvas.img_w} × {self.canvas.img_h} px")
        self.lbl_dims.setStyleSheet("font-size: 11px; font-family: monospace;")
        left_hdr.addWidget(self.lbl_dims)
        left_col.addLayout(left_hdr)

        left_col.addWidget(self.canvas, stretch=1)
        self.lbl_fname = QLabel(f"📄 {os.path.basename(self.image_path)}")
        self.lbl_fname.setStyleSheet("font-size: 11px;")
        left_col.addWidget(self.lbl_fname)
        body.addLayout(left_col, stretch=3)

        # Right Controls Column
        right_col = QVBoxLayout()
        right_col.setSpacing(14)

        lbl_make = QLabel("ÖZELLEŞTİR (MAKE IT YOURS)")
        lbl_make.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        right_col.addWidget(lbl_make)

        lbl_aspect = QLabel("En-Boy Oranı (Aspect ratio)")
        lbl_aspect.setStyleSheet("font-size: 12px; font-weight: 600;")
        right_col.addWidget(lbl_aspect)

        ratio_row = QHBoxLayout()
        ratio_row.setSpacing(6)
        presets = [
            ("Serbest", None),
            ("1:1", (1, 1)),
            ("16:9", (16, 9)),
            ("9:16", (9, 16)),
            ("4:3", (4, 3)),
            ("3:4", (3, 4)),
        ]
        self.ratio_btns = []
        for title, ratio in presets:
            b = QPushButton(title)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda checked=False, r=ratio: self.canvas.set_aspect_preset(r))
            ratio_row.addWidget(b)
            self.ratio_btns.append(b)
        right_col.addLayout(ratio_row)

        # W / H row
        wh_row = QHBoxLayout()
        wh_row.addWidget(QLabel("G (W):"))
        self.spin_w = QSpinBox()
        self.spin_w.setRange(1, self.canvas.img_w)
        self.spin_w.setValue(self.canvas.sel_w)
        wh_row.addWidget(self.spin_w, stretch=1)

        wh_row.addWidget(QLabel("Y (H):"))
        self.spin_h = QSpinBox()
        self.spin_h.setRange(1, self.canvas.img_h)
        self.spin_h.setValue(self.canvas.sel_h)
        wh_row.addWidget(self.spin_h, stretch=1)
        right_col.addLayout(wh_row)

        # X / Y row
        xy_row = QHBoxLayout()
        xy_row.addWidget(QLabel("X:"))
        self.spin_x = QSpinBox()
        self.spin_x.setRange(0, self.canvas.img_w)
        self.spin_x.setValue(self.canvas.sel_x)
        xy_row.addWidget(self.spin_x, stretch=1)

        xy_row.addWidget(QLabel("Y:"))
        self.spin_y = QSpinBox()
        self.spin_y.setRange(0, self.canvas.img_h)
        self.spin_y.setValue(self.canvas.sel_y)
        xy_row.addWidget(self.spin_y, stretch=1)
        right_col.addLayout(xy_row)

        for sp in (self.spin_w, self.spin_h, self.spin_x, self.spin_y):
            sp.valueChanged.connect(self._on_spin_changed)

        self.canvas.selection_changed.connect(self._on_canvas_selection)

        sel_btns = QHBoxLayout()
        self.btn_sel_all = QPushButton("Tümünü Seç")
        self.btn_sel_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sel_all.clicked.connect(self.canvas.select_all)
        sel_btns.addWidget(self.btn_sel_all)

        self.btn_center_sq = QPushButton("Merkez Kare (1:1)")
        self.btn_center_sq.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_center_sq.clicked.connect(lambda: self.canvas.set_aspect_preset((1, 1)))
        sel_btns.addWidget(self.btn_center_sq)
        right_col.addLayout(sel_btns)

        right_col.addStretch()
        body.addLayout(right_col, stretch=2)
        root.addLayout(body, stretch=1)

        # Footer
        ftr = QHBoxLayout()
        self.btn_reset = QPushButton("↺ Sıfırla")
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.clicked.connect(self.canvas.select_all)
        ftr.addWidget(self.btn_reset)

        ftr.addStretch()
        lbl_safe = QLabel("🔒 Orijinal dosya korunur")
        lbl_safe.setStyleSheet("font-size: 11px;")
        ftr.addWidget(lbl_safe)

        self.btn_cancel = QPushButton("İptal")
        self.btn_cancel.clicked.connect(self.reject)
        ftr.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("↗ Kırpılmış Kopyayı Kaydet")
        self.btn_save.setObjectName("PrimaryGoldBtn")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self.accept)
        ftr.addWidget(self.btn_save)
        root.addLayout(ftr)

    def _on_canvas_selection(self, x: int, y: int, w: int, h: int):
        self._updating_spins = True
        self.spin_x.setValue(x)
        self.spin_y.setValue(y)
        self.spin_w.setValue(w)
        self.spin_h.setValue(h)
        self._updating_spins = False

    def _on_spin_changed(self):
        if self._updating_spins:
            return
        self.canvas.set_selection_values(
            self.spin_x.value(),
            self.spin_y.value(),
            self.spin_w.value(),
            self.spin_h.value(),
        )

    def get_crop_params(self) -> Dict[str, Any]:
        return {
            "x": self.canvas.sel_x,
            "y": self.canvas.sel_y,
            "width": self.canvas.sel_w,
            "height": self.canvas.sel_h,
        }

    def _apply_theme(self):
        pal = get_theme_palette(self._theme)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {pal['paper']};
                color: {pal['ink']};
            }}
            QLabel {{
                color: {pal['ink']};
            }}
            #EditorBadge {{
                background-color: {pal['sand']};
                border-radius: 12px;
                font-size: 20px;
            }}
            #FormatPill {{
                background-color: {pal['inset']};
                color: {pal['gold']};
                border: 1px solid {pal['line']};
                border-radius: 10px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 700;
            }}
            QSpinBox {{
                background-color: {pal['surface']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            QPushButton {{
                background-color: {pal['surface']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 9px;
                padding: 7px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {pal['gold']};
            }}
            #PrimaryGoldBtn {{
                background-color: {pal['gold']};
                color: {pal['button_ink']};
                border: none;
                border-radius: 11px;
                padding: 9px 18px;
                font-size: 13px;
                font-weight: 800;
            }}
            #PrimaryGoldBtn:hover {{
                background-color: {pal['gold_end']};
            }}
        """)


class ImageEditDialog(QDialog):
    """Unified dialog for Edit Photo, Frame Image, Annotate Image, and Redact Image."""

    def __init__(self, tool_id: str, image_path: str, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.tool_id = tool_id
        self.image_path = image_path
        self._theme = theme

        titles = {
            "editImage": "Fotoğraf Düzenle (Döndür / Boyut / Işık)",
            "frameImage": "Arka Plan Çerçevesi Ekle (Add BG)",
            "annotateImage": "Görsel Üzerine Not / Etiket Ekle",
            "redactImage": "Görsel Bölgesi Gizle (Pixelate / Blur)",
        }
        self.setWindowTitle(titles.get(tool_id, "Görsel Aracı") + " — Nashi")
        self.resize(520, 380)
        self._init_ui()
        self._apply_theme()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        lbl_file = QLabel(f"📄 {os.path.basename(self.image_path)}")
        lbl_file.setStyleSheet("font-size: 13px; font-weight: 700;")
        layout.addWidget(lbl_file)

        if self.tool_id == "editImage":
            row_rot = QHBoxLayout()
            row_rot.addWidget(QLabel("Döndürme Açısı:"))
            self.cmb_rotate = QComboBox()
            self.cmb_rotate.addItems(["0° (Yok)", "90° Sağa", "180° Baş Aşağı", "270° Sola"])
            self.cmb_rotate.setCurrentIndex(1)
            row_rot.addWidget(self.cmb_rotate, stretch=1)
            layout.addLayout(row_rot)

            row_scale = QHBoxLayout()
            row_scale.addWidget(QLabel("Boyut Ölçeği (%):"))
            self.spin_scale = QSpinBox()
            self.spin_scale.setRange(10, 200)
            self.spin_scale.setValue(100)
            self.spin_scale.setSuffix(" %")
            row_scale.addWidget(self.spin_scale, stretch=1)
            layout.addLayout(row_scale)

            row_bc = QHBoxLayout()
            row_bc.addWidget(QLabel("Parlaklık (-50..+50):"))
            self.spin_bright = QSpinBox()
            self.spin_bright.setRange(-50, 50)
            self.spin_bright.setValue(0)
            row_bc.addWidget(self.spin_bright)

            row_bc.addWidget(QLabel("Kontrast:"))
            self.spin_contrast = QSpinBox()
            self.spin_contrast.setRange(-50, 50)
            self.spin_contrast.setValue(0)
            row_bc.addWidget(self.spin_contrast)
            layout.addLayout(row_bc)

        elif self.tool_id == "frameImage":
            row_pad = QHBoxLayout()
            row_pad.addWidget(QLabel("Çerçeve Kalınlığı (px):"))
            self.spin_pad = QSpinBox()
            self.spin_pad.setRange(8, 240)
            self.spin_pad.setValue(48)
            row_pad.addWidget(self.spin_pad, stretch=1)
            layout.addLayout(row_pad)

            row_col = QHBoxLayout()
            row_col.addWidget(QLabel("Arka Plan Rengi:"))
            self.cmb_bg = QComboBox()
            self.cmb_bg.addItems(["#F9F6ED (Nashi Krem)", "#111A14 (Koyu Orman)", "#E3B859 (Nashi Altın)", "#FFFFFF (Beyaz)", "#000000 (Siyah)"])
            row_col.addWidget(self.cmb_bg, stretch=1)
            layout.addLayout(row_col)

        elif self.tool_id == "annotateImage":
            row_txt = QHBoxLayout()
            row_txt.addWidget(QLabel("Görsel Notu / Başlık:"))
            self.inp_text = QLineEdit("Nashi ile düzenlendi")
            row_txt.addWidget(self.inp_text, stretch=1)
            layout.addLayout(row_txt)

        elif self.tool_id == "redactImage":
            row_mode = QHBoxLayout()
            row_mode.addWidget(QLabel("Gizleme Yöntemi:"))
            self.cmb_redact = QComboBox()
            self.cmb_redact.addItems(["pixelate (Mozaik / Piksel)", "blur (Bulanıklaştır)", "solid (Tam Karartma)"])
            row_mode.addWidget(self.cmb_redact, stretch=1)
            layout.addLayout(row_mode)

        layout.addStretch()

        ftr = QHBoxLayout()
        ftr.addStretch()
        btn_cancel = QPushButton("İptal")
        btn_cancel.clicked.connect(self.reject)
        ftr.addWidget(btn_cancel)

        btn_ok = QPushButton("↗ Yeni Kopyayı Kaydet")
        btn_ok.setObjectName("PrimaryGoldBtn")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        ftr.addWidget(btn_ok)
        layout.addLayout(ftr)

    def get_params(self) -> Dict[str, Any]:
        if self.tool_id == "editImage":
            rot_map = {0: 0, 1: 90, 2: 180, 3: 270}
            return {
                "rotate_deg": rot_map.get(self.cmb_rotate.currentIndex(), 90),
                "scale_percent": self.spin_scale.value(),
                "brightness": self.spin_bright.value(),
                "contrast": self.spin_contrast.value(),
            }
        if self.tool_id == "frameImage":
            raw_col = self.cmb_bg.currentText().split()[0]
            return {"padding": self.spin_pad.value(), "bg_color": raw_col}
        if self.tool_id == "annotateImage":
            return {"text": self.inp_text.text().strip() or "Nashi"}
        if self.tool_id == "redactImage":
            raw_mode = self.cmb_redact.currentText().split()[0]
            return {"mode": raw_mode}
        return {}

    def _apply_theme(self):
        pal = get_theme_palette(self._theme)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {pal['paper']}; color: {pal['ink']}; }}
            QLabel {{ color: {pal['ink']}; }}
            QSpinBox, QComboBox, QLineEdit {{
                background-color: {pal['surface']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 8px;
                padding: 6px 10px;
            }}
            QPushButton {{
                background-color: {pal['surface']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 9px;
                padding: 8px 14px;
                font-weight: 600;
            }}
            #PrimaryGoldBtn {{
                background-color: {pal['gold']};
                color: {pal['button_ink']};
                border: none;
                border-radius: 10px;
                padding: 9px 18px;
                font-weight: 800;
            }}
        """)


class MediaTrimDialog(QDialog):
    """Interactive dialog for Video/Audio Trim and Video Speed changes."""

    def __init__(self, tool_id: str, media_path: str, duration: float = 10.0, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.tool_id = tool_id
        self.media_path = media_path
        self.duration = max(1.0, float(duration))
        self._theme = theme

        self.setWindowTitle("Medya Düzenleyici — Nashi")
        self.resize(520, 320)
        self._init_ui()
        self._apply_theme()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        lbl_file = QLabel(f"🎬 {os.path.basename(self.media_path)}  ({self.duration:.1f} sn)")
        lbl_file.setStyleSheet("font-size: 14px; font-weight: 800;")
        layout.addWidget(lbl_file)

        if self.tool_id == "changeVideoSpeed":
            row = QHBoxLayout()
            row.addWidget(QLabel("Oynatma Hızı Çarpanı:"))
            self.spin_speed = QDoubleSpinBox()
            self.spin_speed.setRange(0.5, 2.0)
            self.spin_speed.setSingleStep(0.25)
            self.spin_speed.setValue(1.5)
            self.spin_speed.setSuffix("x")
            row.addWidget(self.spin_speed, stretch=1)
            layout.addLayout(row)
        else:
            row_in = QHBoxLayout()
            row_in.addWidget(QLabel("Başlangıç Zamanı (In - sn):"))
            self.spin_start = QDoubleSpinBox()
            self.spin_start.setRange(0.0, max(0.0, self.duration - 0.5))
            self.spin_start.setSingleStep(0.5)
            self.spin_start.setValue(0.0)
            self.spin_start.setSuffix(" sn")
            row_in.addWidget(self.spin_start, stretch=1)
            layout.addLayout(row_in)

            row_out = QHBoxLayout()
            row_out.addWidget(QLabel("Bitiş Zamanı (Out - sn):"))
            self.spin_end = QDoubleSpinBox()
            self.spin_end.setRange(0.5, self.duration)
            self.spin_end.setSingleStep(0.5)
            self.spin_end.setValue(min(self.duration, max(1.0, self.duration * 0.75)))
            self.spin_end.setSuffix(" sn")
            row_out.addWidget(self.spin_end, stretch=1)
            layout.addLayout(row_out)

        layout.addStretch()

        ftr = QHBoxLayout()
        ftr.addStretch()
        btn_cancel = QPushButton("İptal")
        btn_cancel.clicked.connect(self.reject)
        ftr.addWidget(btn_cancel)

        btn_save = QPushButton("↗ Yeni Klibi Kaydet")
        btn_save.setObjectName("PrimaryGoldBtn")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self.accept)
        ftr.addWidget(btn_save)
        layout.addLayout(ftr)

    def get_params(self) -> Dict[str, Any]:
        if self.tool_id == "changeVideoSpeed":
            return {"speed": self.spin_speed.value()}
        st = self.spin_start.value()
        et = max(st + 0.2, self.spin_end.value())
        return {"start_time": f"{st:.2f}", "end_time": f"{et:.2f}"}

    def _apply_theme(self):
        pal = get_theme_palette(self._theme)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {pal['paper']}; color: {pal['ink']}; }}
            QLabel {{ color: {pal['ink']}; }}
            QDoubleSpinBox {{
                background-color: {pal['surface']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 8px;
                padding: 6px 10px;
            }}
            QPushButton {{
                background-color: {pal['surface']};
                color: {pal['ink']};
                border: 1px solid {pal['line']};
                border-radius: 9px;
                padding: 8px 14px;
                font-weight: 600;
            }}
            #PrimaryGoldBtn {{
                background-color: {pal['gold']};
                color: {pal['button_ink']};
                border: none;
                border-radius: 10px;
                padding: 9px 18px;
                font-weight: 800;
            }}
        """)
