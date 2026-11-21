"""Wave 1 / madde 7: bring_to_front büyütülmüş pencereyi bozmaz; tepside sürükleme kısayolu anahtarı."""
from wave1_common import TempDirTestCase

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox  # noqa: E402

import ipc_and_drag  # noqa: E402
import main_window  # noqa: E402
import store  # noqa: E402

Win = main_window.NashiMainWindow


class _FakeWindow:
    def __init__(self, minimized):
        self.minimized = minimized
        self.calls = []

    def isMinimized(self):
        return self.minimized

    def __getattr__(self, name):
        if name in ("showNormal", "show", "raise_", "activateWindow", "showMaximized"):
            return lambda: self.calls.append(name)
        raise AttributeError(name)


class BringToFrontTests(TempDirTestCase):
    def test_minimized_window_is_restored(self):
        w = _FakeWindow(minimized=True)
        Win.bring_to_front(w)
        self.assertEqual(w.calls[0], "showNormal")
        self.assertIn("activateWindow", w.calls)

    def test_not_minimized_keeps_state(self):
        w = _FakeWindow(minimized=False)
        Win.bring_to_front(w)
        self.assertNotIn("showNormal", w.calls)
        self.assertEqual(w.calls, ["show", "raise_", "activateWindow"])


class _Host(QObject):
    """Stand-in for the main window: borrows the real methods, no IPC/KWin/tray startup."""
    _set_drag_shortcuts_enabled = Win._set_drag_shortcuts_enabled
    _build_drag_toggle_action = Win._build_drag_toggle_action


class TrayDragToggleTests(TempDirTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _host(self, lang="tr"):
        h = _Host()
        h.store = store.NashiStore(self.tmp / "data")
        h.store.set_preference("language", lang)
        h.chk_drag_wheel = QCheckBox()
        h.chk_drag_wheel.setChecked(True)
        h.chk_drag_wheel.toggled.connect(h._set_drag_shortcuts_enabled)
        h.drag_controller = ipc_and_drag.GlobalDragController(store=h.store, start_polling=False)
        return h

    def _opens(self, h):
        got = []
        dc = h.drag_controller
        dc.drag_wheel_requested.connect(lambda *a: got.append(a))
        dc.simulate_drag_step(True, 0, 0, "")
        dc.simulate_drag_step(True, 40, 40, "Shift")
        dc.simulate_drag_step(False, 40, 40, "")
        return bool(got)

    def test_labels(self):
        h = self._host("tr")
        self.assertEqual(Win._build_drag_toggle_action(h).text(), "Sürükleme Kısayollarını Etkinleştir")
        h2 = self._host("en")
        self.assertEqual(Win._build_drag_toggle_action(h2).text(), "Enable Drag Shortcuts")

    def test_toggle_persists_syncs_and_applies_live(self):
        h = self._host()
        act = Win._build_drag_toggle_action(h)
        h.act_drag_toggle = act
        self.assertTrue(act.isCheckable())
        self.assertTrue(act.isChecked())
        self.assertTrue(self._opens(h))

        act.trigger()  # user unticks it in the tray
        self.assertFalse(act.isChecked())
        self.assertFalse(h.store.get_preference("drag_wheel_enabled"))
        self.assertFalse(h.chk_drag_wheel.isChecked())
        self.assertFalse(store.NashiStore(self.tmp / "data").get_preference("drag_wheel_enabled"))
        self.assertFalse(self._opens(h))

        h.chk_drag_wheel.setChecked(True)  # Settings page turns it back on
        self.assertTrue(act.isChecked())
        self.assertTrue(store.NashiStore(self.tmp / "data").get_preference("drag_wheel_enabled"))
        self.assertTrue(self._opens(h))

    def test_initial_state_follows_setting(self):
        h = self._host()
        h.store.set_preference("drag_wheel_enabled", False)
        self.assertFalse(Win._build_drag_toggle_action(h).isChecked())
