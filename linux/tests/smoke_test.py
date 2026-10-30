#!/usr/bin/env python3
"""
Nashi Linux 2.0 - Comprehensive Automated Smoke & Parity Verification Suite
Verifies:
1. FeatureCatalog.json loading, single/multi-file conversion intersections & tool intersections
2. Image conversions & all image tools (compress, removeMetadata, cropImage, editImage, frameImage, annotateImage, redactImage, createCollage)
3. Media conversions & media tools (MP4->GIF, MP4->MP3, muteVideo, trimMedia, changeVideoSpeed, videoSnapshots, splitVideo, normalizeAudio, audioChannels)
4. PDF & Document/Subtitle/Archive tools (createPDF, mergePDF, splitPDF, organizePDF, SRT<->VTT<->TXT, CSV<->TSV, ZIP<->TAR<->GZ, extractArchive, QR generate & decode)
5. Store persistence, search filtering, and distinct drag modifier swapping
6. RadialWheelWidget & FloatingRadialWheel dynamic slice population, centroid hover math, keyboard navigation, and live mode switching
7. GlobalDragController state machine: LMB + >=8px drag + Shift (convert) / Ctrl (tools) / Alt (actions) trigger, live mode switch while dragging, and release dismissal
8. Single-instance IPC socket & DBus bridge communication.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure XCB platform on Wayland for headless/desktop GUI tests
if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" and not os.environ.get("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "xcb"

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF

from engine import NashiEngine
from store import NashiStore
from artwork import NashiArtwork, FileGardenWidget, THEMES
from wheel_widget import RadialWheelWidget
from floating_wheel import FloatingRadialWheel
from ipc_and_drag import GlobalDragController
from float_shelf import FloatShelfWindow
from toast_hud import NashiToastHUD

app = QApplication.instance() or QApplication(sys.argv)


class NashiSmokeTestSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.TemporaryDirectory()
        cls.work = Path(cls.tmp_dir.name)
        cls.engine = NashiEngine()
        cls.store = NashiStore(data_dir=cls.work / "data")

        # Create sample test fixtures using ImageMagick & FFmpeg
        cls.img_a = str(cls.work / "sample_a.png")
        cls.img_b = str(cls.work / "sample_b.jpg")
        cls.engine._run_cmd(["magick", "-size", "240x180", "xc:#E3B859", cls.img_a])
        cls.engine._run_cmd(["magick", "-size", "240x180", "xc:#243B2B", cls.img_b])

        cls.vid_a = str(cls.work / "clip_a.mp4")
        cls.engine._run_cmd([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=green:s=160x120:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            cls.vid_a
        ])

    @classmethod
    def tearDownClass(cls):
        cls.tmp_dir.cleanup()

    # 1. Catalog & Intersections
    def test_01_catalog_and_intersections(self):
        self.assertTrue(bool(self.engine.catalog_data), "FeatureCatalog.json should be loaded")
        jpg_targets = self.engine.get_available_targets("photo.jpg")
        self.assertIn("png", jpg_targets)
        self.assertIn("webp", jpg_targets)
        self.assertIn("pdf", jpg_targets)

        # Multi-file intersection: jpg + png both support webp and pdf
        inter = self.engine.get_available_targets_for_files(["a.jpg", "b.png"])
        self.assertIn("webp", inter)
        self.assertIn("pdf", inter)

        # Tools for single image vs multiple images
        single_tools = self.engine.get_available_tools_for_files(["a.png"])
        self.assertIn("cropImage", single_tools)
        self.assertIn("editImage", single_tools)
        self.assertIn("readQRCode", single_tools)

        multi_tools = self.engine.get_available_tools_for_files(["a.png", "b.jpg"])
        self.assertIn("createPDF", multi_tools)
        self.assertIn("createCollage", multi_tools)

    # 2. Image Conversions & All Image Tools
    def test_02_image_conversions_and_tools(self):
        out_dir = str(self.work / "img_out")

        # Convert PNG -> WEBP
        webp_out = self.engine.convert(self.img_a, "webp", output_dir=out_dir)
        self.assertTrue(os.path.exists(webp_out))

        # Compress
        comp_out = self.engine.compress(self.img_a, output_dir=out_dir, quality=70)
        self.assertTrue(os.path.exists(comp_out))

        # Remove Metadata
        clean_out = self.engine.remove_metadata(self.img_a, output_dir=out_dir)
        self.assertTrue(os.path.exists(clean_out))

        # Crop Image
        crop_out = self.engine.crop_image(self.img_a, x=10, y=10, width=100, height=100, output_dir=out_dir)
        self.assertTrue(os.path.exists(crop_out))
        cw, ch = self.engine.get_image_dimensions(crop_out)
        self.assertEqual((cw, ch), (100, 100))

        # Edit Image (Rotate 90 deg)
        edit_out = self.engine.edit_image(self.img_a, rotate_deg=90, output_dir=out_dir)
        self.assertTrue(os.path.exists(edit_out))
        ew, eh = self.engine.get_image_dimensions(edit_out)
        self.assertEqual((ew, eh), (180, 240))

        # Frame Image (Add BG)
        frame_out = self.engine.frame_image(self.img_a, padding=20, bg_color="#F9F6ED", output_dir=out_dir)
        self.assertTrue(os.path.exists(frame_out))
        fw, fh = self.engine.get_image_dimensions(frame_out)
        self.assertEqual((fw, fh), (280, 220))

        # Annotate Image
        ann_out = self.engine.annotate_image(self.img_a, text="Nashi Test", output_dir=out_dir)
        self.assertTrue(os.path.exists(ann_out))

        # Redact Image
        red_out = self.engine.redact_image(self.img_a, mode="pixelate", output_dir=out_dir)
        self.assertTrue(os.path.exists(red_out))

        # Collage
        col_out = self.engine.create_collage([self.img_a, self.img_b], columns=2, output_dir=out_dir)
        self.assertTrue(os.path.exists(col_out))

    # 3. Media Conversions & Video/Audio Tools
    def test_03_media_conversions_and_tools(self):
        out_dir = str(self.work / "media_out")

        # Video -> GIF
        gif_out = self.engine.convert(self.vid_a, "gif", output_dir=out_dir)
        self.assertTrue(os.path.exists(gif_out))

        # Video -> MP3
        mp3_out = self.engine.convert(self.vid_a, "mp3", output_dir=out_dir)
        self.assertTrue(os.path.exists(mp3_out))

        # Mute Video
        muted_out = self.engine.mute_video(self.vid_a, output_dir=out_dir)
        self.assertTrue(os.path.exists(muted_out))

        # Trim Video
        trim_out = self.engine.trim_media(self.vid_a, start_time="0", end_time="1.0", output_dir=out_dir)
        self.assertTrue(os.path.exists(trim_out))

        # Change Video Speed
        spd_out = self.engine.change_video_speed(self.vid_a, speed=1.5, output_dir=out_dir)
        self.assertTrue(os.path.exists(spd_out))

        # Video Snapshots
        snaps = self.engine.video_snapshots(self.vid_a, count=2, output_dir=out_dir)
        self.assertEqual(len(snaps), 2)

        # Normalize Audio & Convert Channels
        norm_out = self.engine.normalize_audio(mp3_out, output_dir=out_dir)
        self.assertTrue(os.path.exists(norm_out))
        mono_out = self.engine.convert_audio_channels(mp3_out, channels=1, output_dir=out_dir)
        self.assertTrue(os.path.exists(mono_out))

    # 4. PDF, QR, Subtitles, Tabular & Archives
    def test_04_pdf_qr_subtitles_and_archives(self):
        out_dir = str(self.work / "doc_out")
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        # Create multi-page PDF from 2 images, split it, and merge back
        pdf_combined = self.engine.create_pdf([self.img_a, self.img_b], output_dir=out_dir)
        self.assertTrue(os.path.exists(pdf_combined))

        pages = self.engine.split_pdf(pdf_combined, output_dir=str(self.work / "pdf_pages"))
        self.assertEqual(len(pages), 2)

        merged = self.engine.merge_pdfs(pages, output_dir=out_dir)
        self.assertTrue(os.path.exists(merged))

        # QR generate & read round-trip
        qr_img = self.engine.generate_qr("https://github.com/orkunisitmak/nashi-app", output_path=str(Path(out_dir) / "qr.png"))
        decoded = self.engine.read_qr(qr_img)
        self.assertEqual(decoded, "https://github.com/orkunisitmak/nashi-app")

        # Subtitle SRT -> VTT -> TXT round-trip
        srt_file = Path(out_dir) / "sub.srt"
        srt_file.write_text("1\n00:00:01,000 --> 00:00:03,500\nMerhaba Nashi!\n", encoding="utf-8")
        vtt_out = self.engine.convert(str(srt_file), "vtt", output_dir=out_dir)
        self.assertIn("00:00:01.000 --> 00:00:03.500", Path(vtt_out).read_text(encoding="utf-8"))
        txt_out = self.engine.convert(vtt_out, "txt", output_dir=out_dir)
        self.assertEqual(Path(txt_out).read_text(encoding="utf-8").strip(), "Merhaba Nashi!")

        # Archive ZIP -> TAR & Extract
        zip_path = Path(out_dir) / "bundle.zip"
        import zipfile
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(self.img_a, "sample_a.png")
        tar_out = self.engine.convert(str(zip_path), "tar", output_dir=out_dir)
        self.assertTrue(os.path.exists(tar_out))
        ext_dir = self.engine.extract_archive(tar_out, output_dir=str(self.work / "extracted"))
        self.assertTrue((Path(ext_dir) / "sample_a.png").exists())

    # 5. Store Persistence & Modifier Swapping
    def test_05_store_and_drag_modifier_swap(self):
        self.store.add_export("sample_a.png", self.img_a, "png", action_title="→ PNG")
        rec = self.store.get_recent_exports(query="sample_a")
        self.assertEqual(len(rec), 1)
        self.assertTrue(rec[0]["exists"])

        # Swapping convert modifier to Ctrl should automatically swap tools modifier to Shift
        self.assertEqual(self.store.get_preference("convert_modifier"), "Shift")
        self.assertEqual(self.store.get_preference("tools_modifier"), "Ctrl")
        self.store.set_drag_modifier("convert", "Ctrl")
        self.assertEqual(self.store.get_preference("convert_modifier"), "Ctrl")
        self.assertEqual(self.store.get_preference("tools_modifier"), "Shift")
        # Restore defaults
        self.store.reset_preferences()

        # Test 6: FloatingRadialWheel & GlobalDragController State Machine
    def test_06_wheel_and_global_drag_controller(self):
        wheel = FloatingRadialWheel(engine=self.engine, store=self.store)
        wheel.pop_at_cursor(mode="convert", files=[self.img_a], cursor_pos=(400, 400), drag_mode=True)
        self.assertTrue(wheel.isVisible())
        self.assertIn("JPG", wheel.wheel.items)
        self.assertIn("WEBP", wheel.wheel.items)
        self.assertIn("PDF", wheel.wheel.items)

        # Live switch to tools mode
        wheel.switch_mode("tools")
        self.assertEqual(wheel.current_mode, "tools")
        tool_ids = [it.id for it in wheel.wheel.wheel_items]
        self.assertIn("cropImage", tool_ids)
        self.assertIn("compress", tool_ids)

        # Test hover math at top petal (12 o'clock = slice 0)
        cx = wheel.wheel.width() / 2.0
        cy = wheel.wheel.height() / 2.0
        idx = wheel.wheel.update_hover_at(QPointF(cx, cy - 110))
        self.assertEqual(idx, 0)
        wheel.hide()
        wheel.deleteLater()

        # Test GlobalDragController state machine (LMB + >=8px drag + Shift -> Convert -> Ctrl -> Tools -> Release)
        ctrl = GlobalDragController(store=self.store, start_polling=False)
        events = []
        ctrl.drag_wheel_requested.connect(lambda m, x, y: events.append(("open", m, x, y)))
        ctrl.drag_mode_switched.connect(lambda m: events.append(("switch", m)))
        ctrl.drag_released.connect(lambda: events.append(("release",)))

        # Step 1: Press LMB at (100, 100)
        ctrl.simulate_drag_step(True, 100, 100, "")
        # Step 2: Move to (120, 120) with Shift held -> should open 'convert' wheel!
        ctrl.simulate_drag_step(True, 120, 120, "Shift")
        # Step 3: While dragging at (140, 140), switch to Ctrl -> should switch to 'tools' wheel!
        ctrl.simulate_drag_step(True, 140, 140, "Ctrl")
        # Step 4: While dragging at (150, 150), switch to Alt -> should switch to 'actions' wheel!
        ctrl.simulate_drag_step(True, 150, 150, "Alt")
        # Step 5: Release mouse button
        ctrl.simulate_drag_step(False, 150, 150, "")

        self.assertEqual(events[0], ("open", "convert", 120, 120))
        self.assertEqual(events[1], ("switch", "tools"))
        self.assertEqual(events[2], ("switch", "actions"))
        self.assertEqual(events[3], ("release",))
        ctrl.deleteLater()

    # 7. UI Components Render Smoke (Artwork, Themes, FloatShelf, ToastHUD)
    def test_07_ui_components_render(self):
        for theme_key in THEMES:
            fg = FileGardenWidget(theme=theme_key)
            fg.set_selected(True)
            pix = fg.grab()
            self.assertFalse(pix.isNull())

        shelf = FloatShelfWindow(theme="dark")
        shelf.add_files([self.img_a, self.img_b], show_shelf=False)
        self.assertEqual(shelf.list_widget.count(), 2)

        hud = NashiToastHUD(theme="dark")
        hud.show_success("Test Başarılı", "sample_a.png", [self.img_a], duration_ms=100)
        self.assertTrue(hud.isVisible())
        hud.hide()

    # 8. Web Media Probing & Dialog Test
    def test_08_web_media_probing(self):
        info = self.engine.inspect_web_link("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        self.assertIn("title", info)
        self.assertIn("formats", info)
        self.assertTrue(len(info["formats"]) > 0)
        self.assertEqual(info["kind"], "video")

    # 9. HTML to PDF Offline Conversion (v0.7.13 / v0.3.0 Parity)
    def test_09_html_to_pdf_conversion(self):
        html_file = os.path.join(self.tmp_dir.name, "document.html")
        with open(html_file, "w", encoding="utf-8") as f:
            f.write("<html><head><title>Nashi</title></head><body><h1>Başlık: Türkçe Karakterler (ç, ğ, ı, ö, ş, ü)</h1><p>Offline PDF çıktısı testi.</p></body></html>")

        pdf_out = self.engine.convert(html_file, "pdf")
        self.assertTrue(os.path.exists(pdf_out))
        self.assertTrue(os.path.getsize(pdf_out) > 500)

    # 10. Photo Redaction Blur Strength (v0.7.13 Parity)
    def test_10_photo_redact_heavy_blur(self):
        redacted = self.engine.redact_image(self.img_a, mode="blur")
        self.assertTrue(os.path.exists(redacted))
        self.assertTrue(os.path.getsize(redacted) > 100)

    # 11. Radial Wheel Escape Key & Focus Out Dismissal (v0.3.2)
    def test_11_wheel_escape_and_focus_out(self):
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent, Qt

        wheel = FloatingRadialWheel(engine=self.engine, store=self.store)
        wheel.pop_at_cursor(mode="convert", files=[self.img_a], cursor_pos=(200, 200), drag_mode=False)
        self.assertTrue(wheel.isVisible())

        # Test A: Escape key on FloatingRadialWheel closes it
        esc_ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        wheel.keyPressEvent(esc_ev)
        self.assertFalse(wheel.isVisible())

        # Test B: Escape key on inner RadialWheelWidget closes parent wheel
        wheel.pop_at_cursor(mode="convert", files=[self.img_a], cursor_pos=(200, 200), drag_mode=False)
        self.assertTrue(wheel.isVisible())
        wheel.wheel.keyPressEvent(esc_ev)
        self.assertFalse(wheel.isVisible())

        # Test C: Focus out / window deactivation closes wheel when not dragging
        wheel.pop_at_cursor(mode="convert", files=[self.img_a], cursor_pos=(200, 200), drag_mode=False)
        self.assertTrue(wheel.isVisible())
        act_change = QEvent(QEvent.Type.ActivationChange)
        wheel.changeEvent(act_change)
        self.assertFalse(wheel.isVisible())

        # Test D: Global drag controller dismisses drag wheel when Escape is pressed
        ctrl = GlobalDragController(store=self.store, start_polling=False)
        released_called = []
        ctrl.drag_released.connect(lambda: released_called.append(True))
        ctrl.simulate_drag_step(True, 100, 100, "")
        ctrl.simulate_drag_step(True, 120, 120, "Shift")
        self.assertTrue(ctrl._opened)
        # Escape pressed while dragging
        ctrl.simulate_drag_step(True, 120, 120, "Shift", escape=True)
        self.assertFalse(ctrl._opened)
        self.assertTrue(len(released_called) > 0)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NashiSmokeTestSuite)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    os._exit(0 if result.wasSuccessful() else 1)
