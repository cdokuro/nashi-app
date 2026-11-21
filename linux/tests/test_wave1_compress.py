"""Wave 1 / madde 3: sıkıştırma çıktısı küçük değilse orijinal korunur."""
import hashlib
import os
import subprocess

from wave1_common import TempDirTestCase, need

import engine  # noqa: E402


def tiny_pdf(path):
    content = "BT /F1 18 Tf 40 300 Td (Quarterly report) Tj ET\n"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 400] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = b"%PDF-1.7\n"
    offsets = []
    for i, obj in enumerate(objects):
        offsets.append(len(data))
        data += f"{i + 1} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(data)
    data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        data += f"{off:010d} 00000 n \n".encode()
    data += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(data)
    return data


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CompressKeepsOriginalTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.eng = engine.NashiEngine()

    def _assert_kept(self, src, before):
        out = self.eng.compress(str(src))
        self.assertEqual(os.path.realpath(out), os.path.realpath(src))
        self.assertEqual(digest(src), before)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), [src.name])
        self.assertTrue(self.eng.is_original_kept(str(src), out))

    @need("gs")
    def test_small_pdf_is_kept(self):
        src = self.tmp / "rapor.pdf"
        tiny_pdf(src)
        before = digest(src)
        # sanity: Ghostscript really writes a bigger file for this input
        probe = self.tmp / "probe" / "x.pdf"
        probe.parent.mkdir()
        subprocess.run(["gs", "-sDEVICE=pdfwrite", "-dPDFSETTINGS=/ebook", "-dNOPAUSE", "-dQUIET", "-dBATCH",
                        f"-sOutputFile={probe}", str(src)], check=True, timeout=60)
        self.assertGreaterEqual(probe.stat().st_size, src.stat().st_size)
        probe.unlink()
        probe.parent.rmdir()
        self._assert_kept(src, before)

    @need("magick")
    def test_already_small_jpeg_is_kept(self):
        src = self.tmp / "foto.jpg"
        subprocess.run(["magick", "-size", "200x200", "xc:gray", "+noise", "Random", "-blur", "0x6", "-strip", "-quality", "20", str(src)],
                       check=True, timeout=60)
        self._assert_kept(src, digest(src))

    @need("magick")
    def test_smaller_result_is_written(self):
        src = self.tmp / "buyuk.jpg"
        subprocess.run(["magick", "-size", "400x400", "xc:gray", "+noise", "Random", "-quality", "100", str(src)],
                       check=True, timeout=60)
        out = self.eng.compress(str(src), quality=40)
        self.assertNotEqual(os.path.realpath(out), os.path.realpath(src))
        self.assertLess(os.path.getsize(out), os.path.getsize(src))
        self.assertFalse(self.eng.is_original_kept(str(src), out))

    @need("ffmpeg")
    def test_audio_not_smaller_is_kept(self):
        src = self.tmp / "ses.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                        "-c:a", "libmp3lame", "-b:a", "32k", str(src)], check=True, timeout=60)
        self._assert_kept(src, digest(src))


@need("gs")
class CompressNoticeTests(TempDirTestCase):
    """The worker reports a kept original through the normal finished/toast path."""

    def test_worker_reports_kept_original(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])  # noqa: F841
        import main_window
        import store
        st = store.NashiStore(self.tmp / "data")
        src = self.tmp / "rapor.pdf"
        tiny_pdf(src)
        w = main_window.ConversionWorker(engine.NashiEngine(), st, "tools", "compress", [str(src)])
        got = []
        w.finished.connect(lambda *a: got.append(a))
        w.run()  # synchronous: the app runs this on the worker thread
        self.assertEqual(len(got), 1)
        ok, title, detail, outputs = got[0]
        self.assertTrue(ok)
        self.assertIn("orijinal korundu", title)
        self.assertIn("rapor.pdf", detail)
        self.assertEqual(outputs, [str(src)])
        self.assertEqual(st.get_recent_exports(), [])  # nothing new was made
        self.assertFalse(any(p.name.endswith("_compressed.pdf") for p in self.tmp.iterdir()))
