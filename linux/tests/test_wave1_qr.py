"""Wave 1 / madde 2: QR okuma saydam arka planı beyaza düzleştirir."""
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # standalone runs

import subprocess

from wave1_common import TempDirTestCase, need

import engine  # noqa: E402


@need("qrencode", "magick", "zbarimg")
class ReadQrTransparencyTests(TempDirTestCase):
    def _make(self, name, extra):
        base = self.tmp / "base.png"
        subprocess.run(["qrencode", "-o", str(base), "-s", "8", "-m", "4", "nashi-dalga-1"], check=True, timeout=30)
        out = self.tmp / name
        subprocess.run(["magick", str(base), *extra, str(out)], check=True, timeout=30)
        return out

    def test_transparent_png(self):
        # every pixel black, background fully transparent: a raw reader sees an all-black image
        img = self._make("t.png", ["(", "+clone", "-negate", ")", "-alpha", "off", "-compose", "CopyOpacity",
                                   "-composite", "-fill", "black", "-colorize", "100"])
        img.rename(self.tmp / "t.tmp")
        subprocess.run(["magick", str(self.tmp / "t.tmp"), f"PNG32:{img}"], check=True, timeout=30)
        raw = subprocess.run(["zbarimg", "--quiet", "--raw", str(img)], capture_output=True, text=True)
        self.assertNotIn("nashi-dalga-1", raw.stdout, "fixture must defeat the raw reader")
        self.assertEqual(engine.NashiEngine().read_qr(str(img)), "nashi-dalga-1")

    def test_transparent_gif(self):
        img = self._make("t.gif", ["(", "+clone", "-negate", ")", "-alpha", "off", "-compose", "CopyOpacity",
                                   "-composite", "-fill", "black", "-colorize", "100"])
        self.assertEqual(engine.NashiEngine().read_qr(str(img)), "nashi-dalga-1")

    def test_plain_png_still_works(self):
        img = self._make("p.png", [])
        self.assertEqual(engine.NashiEngine().read_qr(str(img)), "nashi-dalga-1")

    def test_qr_on_second_pdf_page(self):
        qr = self._make("q.png", [])
        blank = self.tmp / "bos.png"
        subprocess.run(["magick", "-size", "300x300", "xc:white", str(blank)], check=True, timeout=30)
        pdf = self.tmp / "iki.pdf"
        subprocess.run(["magick", str(blank), str(qr), str(pdf)], check=True, timeout=60)
        self.assertEqual(engine.NashiEngine().read_qr(str(pdf)), "nashi-dalga-1")

    def test_no_code_raises(self):
        img = self.tmp / "empty.png"
        subprocess.run(["magick", "-size", "64x64", "xc:white", str(img)], check=True, timeout=30)
        with self.assertRaises(ValueError):
            engine.NashiEngine().read_qr(str(img))
