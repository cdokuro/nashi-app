"""Wave 1 / madde 5: süre okunamazsa sahte 10 sn yerine None; çağıranlar başa çıkar."""
import subprocess
from unittest import mock

from wave1_common import TempDirTestCase, need

import engine  # noqa: E402


class DurationUnknownTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.eng = engine.NashiEngine()

    def test_missing_ffprobe_returns_none(self):
        with mock.patch("engine.shutil.which", return_value=None):
            self.assertIsNone(self.eng.get_media_duration(str(self.tmp / "x.mp4")))

    def test_unreadable_file_returns_none(self):
        bad = self.tmp / "bozuk.mp4"
        bad.write_bytes(b"not a video")
        self.assertIsNone(self.eng.get_media_duration(str(bad)))

    def test_nan_and_na_are_unknown(self):
        for raw in ("N/A\n", "nan\n", "inf\n", "0\n", "\n"):
            fake = subprocess.CompletedProcess([], 0, stdout=raw, stderr="")
            with mock.patch("engine.subprocess.run", return_value=fake), \
                 mock.patch("engine.shutil.which", return_value="/usr/bin/ffprobe"):
                self.assertIsNone(self.eng.get_media_duration("x.mp4"), raw)

    def test_stream_duration_fallback(self):
        fake = subprocess.CompletedProcess([], 0, stdout="N/A\n3.5\n", stderr="")
        with mock.patch("engine.subprocess.run", return_value=fake), \
             mock.patch("engine.shutil.which", return_value="/usr/bin/ffprobe"):
            self.assertAlmostEqual(self.eng.get_media_duration("x.mp4"), 3.5)

    @need("ffmpeg", "ffprobe")
    def test_real_duration(self):
        v = self.tmp / "v.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v)], check=True, timeout=60)
        self.assertAlmostEqual(self.eng.get_media_duration(str(v)), 2.0, delta=0.2)

    def test_split_and_snapshots_refuse_unknown_duration(self):
        v = self.tmp / "v.mp4"
        v.write_bytes(b"x")
        with mock.patch.object(self.eng, "get_media_duration", return_value=None), \
             mock.patch.object(self.eng, "_run_cmd") as run:
            with self.assertRaises(RuntimeError) as cm:
                self.eng.split_video(str(v), parts=2, output_dir=str(self.tmp))
            self.assertIn("süre", str(cm.exception).lower())
            with self.assertRaises(RuntimeError):
                self.eng.video_snapshots(str(v), count=3, output_dir=str(self.tmp))
            run.assert_not_called()


class TrimDialogUnknownDurationTests(TempDirTestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_unknown_duration_dialog(self):
        import editors
        dlg = editors.MediaTrimDialog("trimVideo", str(self.tmp / "a.mp4"), duration=None)
        # no fake 10 s ceiling
        self.assertGreater(dlg.spin_start.maximum(), 10.0)
        self.assertGreater(dlg.spin_end.maximum(), 10.0)
        params = dlg.get_params()
        self.assertEqual(params["start_time"], "0.00")
        self.assertNotIn("end_time", params)  # default = until the end
        dlg.spin_start.setValue(12.0)
        dlg.spin_end.setValue(20.0)
        self.assertEqual(dlg.get_params(), {"start_time": "12.00", "end_time": "20.00"})

    def test_known_duration_dialog_unchanged(self):
        import editors
        dlg = editors.MediaTrimDialog("trimVideo", str(self.tmp / "a.mp4"), duration=8.0)
        self.assertAlmostEqual(dlg.spin_end.maximum(), 8.0)
        self.assertEqual(dlg.get_params(), {"start_time": "0.00", "end_time": "6.00"})
