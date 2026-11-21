"""Ortak test yardımcıları (wave 1).

Canlı oturuma dokunmamak için Qt'den önce offscreen platform ve geçici
HOME / XDG_* dizinleri ayarlanır. Bu modül her test dosyasının en başında
içe aktarılmalıdır.
"""
import atexit
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_SANDBOX = Path(tempfile.mkdtemp(prefix="nashi-wave1-"))
atexit.register(shutil.rmtree, _SANDBOX, ignore_errors=True)
for _sub in ("home", "cfg", "data", "run"):
    (_SANDBOX / _sub).mkdir(mode=0o700, exist_ok=True)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HOME"] = str(_SANDBOX / "home")
os.environ["XDG_CONFIG_HOME"] = str(_SANDBOX / "cfg")
os.environ["XDG_DATA_HOME"] = str(_SANDBOX / "data")
os.environ["XDG_RUNTIME_DIR"] = str(_SANDBOX / "run")
for _var in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS"):
    os.environ.pop(_var, None)

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def need(*tools):
    """Skip the test (not fail) when a required CLI tool is missing."""
    missing = [t for t in tools if not shutil.which(t)]
    return unittest.skipIf(bool(missing), f"missing tool(s): {', '.join(missing)}")


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="case-", dir=_SANDBOX))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
