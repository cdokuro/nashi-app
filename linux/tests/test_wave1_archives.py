"""Wave 1 / madde 4: RAR (unrar/7z/bsdtar), ZIP tarih+izin, güvenlik sınırları."""
import os
import stat
import struct
import tarfile
import time
import zipfile
import zlib
from unittest import mock

from wave1_common import TempDirTestCase, need

import engine  # noqa: E402


def make_rar4(path, files):
    """Writes a stored (uncompressed) RAR 4.x archive. files: [(name, bytes)]."""
    def block(head_type, flags, body):
        size = 7 + len(body)
        crc_part = struct.pack("<BHH", head_type, flags, size) + body
        return struct.pack("<H", zlib.crc32(crc_part) & 0xFFFF) + crc_part

    out = b"Rar!\x1a\x07\x00"
    out += block(0x73, 0, struct.pack("<HI", 0, 0))
    dos_time = (2024 - 1980) << 25 | 5 << 21 | 17 << 16 | 12 << 11 | 30 << 5 | 0
    for name, data in files:
        nb = name.encode("utf-8")
        body = struct.pack("<IIBIIBBHI", len(data), len(data), 3, zlib.crc32(data), dos_time,
                           20, 0x30, len(nb), 0o100644) + nb
        out += block(0x74, 0x8000, body) + data
    out += block(0x7B, 0x4000, b"")
    path.write_bytes(out)


class ZipFidelityTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.eng = engine.NashiEngine()

    def _zip(self, entries):
        arch = self.tmp / "paket.zip"
        with zipfile.ZipFile(arch, "w") as z:
            for name, data, mode, dt in entries:
                info = zipfile.ZipInfo(name, date_time=dt)
                info.create_system = 3
                info.external_attr = (mode & 0xFFFF) << 16
                z.writestr(info, data)
        return arch

    def test_restores_mtime_and_permissions(self):
        arch = self._zip([
            ("bin/", b"", stat.S_IFDIR | 0o755, (2021, 3, 4, 5, 6, 8)),
            ("bin/run.sh", b"#!/bin/sh\necho hi\n", stat.S_IFREG | 0o755, (2020, 1, 2, 3, 4, 6)),
            ("gizli.txt", b"x", stat.S_IFREG | 0o600, (2019, 12, 31, 23, 59, 58)),
        ])
        dest = self.tmp / "out"
        self.eng.extract_archive(str(arch), str(dest))
        run = dest / "bin" / "run.sh"
        self.assertEqual(stat.S_IMODE(run.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((dest / "gizli.txt").stat().st_mode), 0o600)
        self.assertEqual(time.localtime(run.stat().st_mtime)[:6], (2020, 1, 2, 3, 4, 6))
        self.assertEqual(time.localtime((dest / "bin").stat().st_mtime)[:6], (2021, 3, 4, 5, 6, 8))

    def test_windows_zip_without_modes_uses_defaults(self):
        arch = self.tmp / "win.zip"
        with zipfile.ZipFile(arch, "w") as z:
            info = zipfile.ZipInfo("a.txt", date_time=(2022, 6, 7, 8, 9, 10))
            info.create_system = 0
            z.writestr(info, b"a")
        dest = self.tmp / "out"
        self.eng.extract_archive(str(arch), str(dest))
        st = (dest / "a.txt").stat()
        self.assertTrue(st.st_mode & stat.S_IRUSR and st.st_mode & stat.S_IWUSR)
        self.assertEqual(time.localtime(st.st_mtime)[:6], (2022, 6, 7, 8, 9, 10))

    def test_rejects_path_traversal_and_absolute(self):
        for bad in ("../kacis.txt", "/etc/kacis.txt", "a/../../kacis.txt", "C:/kacis.txt"):
            arch = self.tmp / "kotu.zip"
            with zipfile.ZipFile(arch, "w") as z:
                z.writestr(bad, b"x")
            with self.assertRaises(ValueError, msg=bad):
                self.eng.extract_archive(str(arch), str(self.tmp / "out"))
            self.assertFalse((self.tmp / "kacis.txt").exists())

    def test_rejects_symlink_escape(self):
        arch = self.tmp / "link.zip"
        with zipfile.ZipFile(arch, "w") as z:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "/etc")
        with self.assertRaises(ValueError):
            self.eng.extract_archive(str(arch), str(self.tmp / "out"))

    def test_entry_count_limit(self):
        arch = self._zip([(f"f{i}.txt", b"", stat.S_IFREG | 0o644, (2020, 1, 1, 0, 0, 0)) for i in range(5)])
        with mock.patch.object(engine, "ARCHIVE_MAX_ENTRIES", 4):
            with self.assertRaises(ValueError):
                self.eng.extract_archive(str(arch), str(self.tmp / "out"))

    def test_expanded_size_limit(self):
        arch = self.tmp / "bomba.zip"
        with zipfile.ZipFile(arch, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("zero.bin", b"\0" * 200_000)
        with mock.patch.object(engine, "ARCHIVE_MAX_BYTES", 100_000):
            with self.assertRaises(ValueError):
                self.eng.extract_archive(str(arch), str(self.tmp / "out"))


class TarLimitTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.eng = engine.NashiEngine()

    def _tar(self, members):
        arch = self.tmp / "a.tar"
        with tarfile.open(arch, "w") as t:
            for m, data in members:
                t.addfile(m, None if data is None else __import__("io").BytesIO(data))
        return arch

    def test_hard_links_count_toward_size(self):
        f = tarfile.TarInfo("big.bin")
        f.size = 60_000
        links = []
        for i in range(3):
            ln = tarfile.TarInfo(f"link{i}")
            ln.type = tarfile.LNKTYPE
            ln.linkname = "big.bin"
            links.append((ln, None))
        arch = self._tar([(f, b"\0" * 60_000)] + links)
        with mock.patch.object(engine, "ARCHIVE_MAX_BYTES", 150_000):
            with self.assertRaises(ValueError):
                self.eng.extract_archive(str(arch), str(self.tmp / "out"))
        # without the limit it extracts fine
        out = self.eng.extract_archive(str(arch), str(self.tmp / "ok"))
        self.assertTrue((self.tmp / "ok" / "link2").exists())
        self.assertEqual(out, str((self.tmp / "ok").resolve()))

    def test_tar_traversal_rejected(self):
        m = tarfile.TarInfo("../kacis.txt")
        m.size = 1
        arch = self._tar([(m, b"x")])
        with self.assertRaises(Exception):
            self.eng.extract_archive(str(arch), str(self.tmp / "out"))
        self.assertFalse((self.tmp / "kacis.txt").exists())

    def test_tar_mtime_kept(self):
        m = tarfile.TarInfo("eski.txt")
        m.size = 1
        m.mtime = 1_000_000_000
        m.mode = 0o640
        arch = self._tar([(m, b"x")])
        self.eng.extract_archive(str(arch), str(self.tmp / "out"))
        st = (self.tmp / "out" / "eski.txt").stat()
        self.assertEqual(int(st.st_mtime), 1_000_000_000)
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)


class RarTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.eng = engine.NashiEngine()
        self.arch = self.tmp / "belge.rar"
        make_rar4(self.arch, [("merhaba.txt", b"Merhaba RAR\n"), ("alt/ikinci.txt", b"2\n")])

    def _check(self, tool):
        real_which = engine.shutil.which
        others = {"unrar", "7z", "bsdtar"} - {tool}
        with mock.patch("engine.shutil.which", side_effect=lambda n: None if n in others else real_which(n)):
            dest = self.tmp / f"out-{tool}"
            self.eng.extract_archive(str(self.arch), str(dest))
        self.assertEqual((dest / "merhaba.txt").read_bytes(), b"Merhaba RAR\n")
        self.assertEqual((dest / "alt" / "ikinci.txt").read_bytes(), b"2\n")
        self.assertEqual([p.name for p in dest.iterdir() if p.name.startswith(".nashi")], [])

    @need("unrar")
    def test_unrar(self):
        self._check("unrar")

    @need("7z")
    def test_7z(self):
        self._check("7z")

    @need("bsdtar")
    def test_bsdtar(self):
        self._check("bsdtar")

    def test_no_tool_gives_clear_error(self):
        with mock.patch("engine.shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as cm:
                self.eng.extract_archive(str(self.arch), str(self.tmp / "out"))
        msg = str(cm.exception)
        self.assertIn("unrar", msg)
        self.assertIn("7z", msg)

    @need("unrar")
    def test_rar_entry_limit(self):
        with mock.patch.object(engine, "ARCHIVE_MAX_ENTRIES", 1):
            with self.assertRaises(ValueError):
                self.eng.extract_archive(str(self.arch), str(self.tmp / "out"))

    @need("unrar")
    def test_rar_size_limit(self):
        with mock.patch.object(engine, "ARCHIVE_MAX_BYTES", 5):
            with self.assertRaises(ValueError):
                self.eng.extract_archive(str(self.arch), str(self.tmp / "out"))

    @need("unrar")
    def test_rar_to_zip_conversion(self):
        out = self.tmp / "belge.zip"
        self.eng.convert_archive(str(self.arch), "zip", str(out))
        with zipfile.ZipFile(out) as z:
            self.assertEqual(sorted(z.namelist()), ["alt/ikinci.txt", "merhaba.txt"])
