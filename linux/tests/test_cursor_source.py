#!/usr/bin/env python3
"""
Nashi XWayland (xcb) altında çalışır: imleç bir X11 penceresinin üzerinden
geçmedikçe QCursor.pos() donuk kalır (canlı ölçümde 40 örnek boyunca
(825,886) / DP-1 sabit kaldı, KWin aktif ekranı ise 12 kez DP-1<->DP-2 değişti).
KWin betiği gerçek konumu (workspace.cursorPos) D-Bus ile akıtır; raf, toast
ve CLI'den açılan çark konumu bu kaynaktan almalı.

Çalıştır: python3 tests/test_cursor_source.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" and not os.environ.get("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor, QGuiApplication

app = QApplication.instance() or QApplication(sys.argv)

import cursor_source  # noqa: E402


class _ScreenAtSpy:
    """QGuiApplication.screenAt'i kaydeder; birincil ekranı döndürüp akışı sürdürür."""
    def __init__(self):
        self.points = []

    def __call__(self, point):
        self.points.append(QPoint(point))
        return QGuiApplication.primaryScreen()


def _no_show(widget):
    # Testte gerçek ekranda pencere açılmasın
    for name in ("show", "raise_", "activateWindow", "setFocus"):
        if hasattr(widget, name):
            setattr(widget, name, lambda *a, **k: None)


class CursorSourceTests(unittest.TestCase):
    def setUp(self):
        cursor_source.reset()

    def test_falls_back_to_qcursor_without_kwin_stream(self):
        self.assertEqual(cursor_source.global_cursor_pos(), QCursor.pos())

    def test_returns_last_streamed_kwin_position(self):
        cursor_source.update(3001.6, 412.2)
        self.assertEqual(cursor_source.global_cursor_pos(), QPoint(3002, 412))

    def test_toast_positions_on_streamed_cursor_screen(self):
        from toast_hud import NashiToastHUD
        toast = NashiToastHUD()
        _no_show(toast)
        cursor_source.update(2700, 300)
        spy = _ScreenAtSpy()
        with mock.patch.object(QGuiApplication, "screenAt", spy):
            toast._position_on_screen()
        self.assertIn(QPoint(2700, 300), spy.points)

    def test_float_shelf_opens_at_streamed_cursor(self):
        from float_shelf import FloatShelfWindow
        shelf = FloatShelfWindow()
        _no_show(shelf)
        cursor_source.update(2650, 500)
        spy = _ScreenAtSpy()
        with tempfile.NamedTemporaryFile(suffix=".txt") as tmp, \
                mock.patch.object(QGuiApplication, "screenAt", spy):
            shelf.add_files([tmp.name], show_shelf=True)
        self.assertIn(QPoint(2650, 500), spy.points)

    def test_wheel_without_coords_uses_streamed_cursor(self):
        from engine import NashiEngine
        from store import NashiStore
        from floating_wheel import FloatingRadialWheel
        with tempfile.TemporaryDirectory() as tmp:
            store = NashiStore(data_dir=Path(tmp) / "data")  # kullanıcının gerçek verisine dokunma
            wheel = FloatingRadialWheel(engine=NashiEngine(), store=store)
            _no_show(wheel)
            cursor_source.update(2800, 600)
            spy = _ScreenAtSpy()
            with mock.patch.object(QGuiApplication, "screenAt", spy):
                wheel.pop_at_cursor(mode="convert", files=[], cursor_pos=None)
            self.assertIn(QPoint(2800, 600), spy.points)


if __name__ == "__main__":
    unittest.main(verbosity=2)
