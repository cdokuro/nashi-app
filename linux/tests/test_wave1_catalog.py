"""Wave 1 / madde 1: katalog html→pdf + video→ses rotaları, extract_audio ogg/opus."""
import json
import subprocess
import threading

from wave1_common import ROOT_DIR, TempDirTestCase, need  # noqa: F401  (env first)

import engine  # noqa: E402

VIDEO_SOURCES = ["mp4", "mov", "mkv", "webm", "avi", "wmv"]
NEW_AUDIO = ["m4a", "wav", "flac", "ogg"]


def _codec(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, timeout=30)
    return out.stdout.strip()


class CatalogRoutesTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.catalog_path = ROOT_DIR / "assets" / "FeatureCatalog.json"
        self.catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))

    def test_html_to_pdf_route(self):
        self.assertEqual(self.catalog["conversionMatrix"].get("html"), ["pdf"])
        eng = engine.NashiEngine(str(self.catalog_path))
        self.assertEqual(eng.get_available_targets("page.html"), ["pdf"])
        self.assertEqual(eng.get_available_targets("page.htm"), ["pdf"])

    def test_video_to_audio_routes(self):
        matrix = self.catalog["conversionMatrix"]
        added = 0
        for src in VIDEO_SOURCES:
            targets = matrix[src]
            for fmt in ["mp3"] + NEW_AUDIO:
                self.assertIn(fmt, targets, f"{src} -> {fmt}")
            added += len(NEW_AUDIO)
            # existing items keep their order; audio goes after them
            self.assertEqual(targets[:7][-2:], ["gif", "mp3"])
        self.assertEqual(added, 24)

    def test_catalog_is_valid_json_with_same_sections(self):
        self.assertEqual(
            list(self.catalog), ["conversionMatrix", "singleTools", "multipleTools", "toolNames", "fileActions"])


@need("ffmpeg", "ffprobe")
class ExtractAudioTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.video = self.tmp / "clip.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(self.video)],
            check=True, timeout=60)
        self.eng = engine.NashiEngine()

    def test_every_new_route_converts(self):
        expected = {"m4a": "aac", "wav": "pcm_s16le", "flac": "flac", "ogg": "vorbis"}
        for fmt, codec in expected.items():
            out = self.eng.convert(str(self.video), fmt, output_dir=str(self.tmp / fmt))
            self.assertTrue(out.endswith("." + fmt))
            self.assertEqual(_codec(out), codec, fmt)

    def test_extract_audio_opus(self):
        out = self.eng.extract_audio(str(self.video), "opus", output_dir=str(self.tmp))
        self.assertEqual(_codec(out), "opus")


class HtmlToPdfTests(TempDirTestCase):
    def test_html_converts_to_pdf_off_gui_thread(self):
        from PySide6.QtWidgets import QApplication  # one app type for the whole run
        app = QApplication.instance() or QApplication([])  # noqa: F841
        src = self.tmp / "sayfa.html"
        src.write_text("<html><body><h1>Merhaba İstanbul</h1></body></html>", encoding="utf-8")
        eng = engine.NashiEngine()
        result = {}

        def work():  # conversions run on the worker thread in the app
            try:
                result["out"] = eng.convert(str(src), "pdf")
            except Exception as e:  # pragma: no cover
                result["err"] = e

        t = threading.Thread(target=work)
        t.start()
        t.join(60)
        self.assertNotIn("err", result, result.get("err"))
        with open(result["out"], "rb") as f:
            self.assertEqual(f.read(5), b"%PDF-")
