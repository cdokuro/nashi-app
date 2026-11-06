#!/usr/bin/env python3
"""
Açılışta (QApplication'dan önce) KWin/kconfig'e yapılan subprocess çağrıları
zaman aşımı olmadan çalışıyordu: KWin veya qdbus6 takılırsa Nashi hiç açılmaz,
tepsiye de gelmez. Her çağrı sınırlı olmalı; zaman aşımı açılışı durdurmamalı.

Çalıştır: python3 tests/test_startup_timeouts.py
Gerçek KWin/kconfig'e ve kullanıcının dosyalarına dokunmaz (subprocess,
Path.home ve soket yolu sahtelenir).
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import ipc_and_drag  # noqa: E402

MAX_TIMEOUT_S = 3


class _Recorder:
    def __init__(self, hang_on=None):
        self.calls = []
        self.hang_on = hang_on

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append((list(cmd), kwargs))
        if self.hang_on and self.hang_on in cmd:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


class StartupTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = Path(self.tmp.name)
        self.patches = [
            mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland"}),
            mock.patch.object(Path, "home", return_value=home),
            mock.patch.object(ipc_and_drag, "get_ipc_socket_path", return_value=str(home / "run" / "nashi-ipc.sock")),
        ]
        (home / "run").mkdir()
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def assert_all_bounded(self, rec):
        self.assertTrue(rec.calls, "expected subprocess calls")
        for cmd, kwargs in rec.calls:
            t = kwargs.get("timeout")
            self.assertIsNotNone(t, f"no timeout: {' '.join(cmd)}")
            self.assertLessEqual(t, MAX_TIMEOUT_S, f"timeout {t}s too long: {' '.join(cmd)}")

    def test_eavesdrop_config_calls_are_bounded(self):
        rec = _Recorder()
        with mock.patch.object(ipc_and_drag.subprocess, "run", rec):
            ipc_and_drag.ensure_kde_xwayland_eavesdrop()
        self.assert_all_bounded(rec)

    def test_kwin_script_registration_calls_are_bounded(self):
        rec = _Recorder()
        with mock.patch.object(ipc_and_drag.subprocess, "run", rec):
            ipc_and_drag.register_kde_global_shortcuts(str(ROOT_DIR / "nashi"))
        self.assert_all_bounded(rec)

    def test_hanging_kwin_does_not_abort_startup(self):
        rec = _Recorder(hang_on="qdbus6")
        with mock.patch.object(ipc_and_drag.subprocess, "run", rec):
            ipc_and_drag.ensure_kde_xwayland_eavesdrop()
            ipc_and_drag.register_kde_global_shortcuts(str(ROOT_DIR / "nashi"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
