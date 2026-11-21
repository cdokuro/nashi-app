"""Wave 1 / madde 4: RAR (unrar/7z/bsdtar), ZIP tarih+izin, güvenlik sınırları."""
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # standalone runs

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
    """Writes a stored (uncompressed) RAR 4.x archive.
    files: [(name, bytes)] or [(name, bytes, unix_mode)]; a S_IFDIR mode makes a folder entry."""
    def block(head_type, flags, body):
        size = 7 + len(body)
        crc_part = struct.pack("<BHH", head_type, flags, size) + body
        return struct.pack("<H", zlib.crc32(crc_part) & 0xFFFF) + crc_part

    out = b"Rar!\x1a\x07\x00"
    out += block(0x73, 0, struct.pack("<HI", 0, 0))
    dos_time = (2024 - 1980) << 25 | 5 << 21 | 17 << 16 | 12 << 11 | 30 << 5 | 0
    for entry in files:
        name, data = entry[0], entry[1]
        mode = entry[2] if len(entry) > 2 else 0o100644
        is_dir = stat.S_ISDIR(mode)
        nb = name.encode("utf-8")
        body = struct.pack("<IIBIIBBHI", len(data), len(data), 3, zlib.crc32(data), dos_time,
                           20, 0x30, len(nb), mode) + nb
        out += block(0x74, 0x8000 | (0xE0 if is_dir else 0), body) + data
    out += block(0x7B, 0x4000, b"")
    path.write_bytes(out)


def _only_tool(tool):
    """Patch which() so that only `tool` (of the three RAR tools) is installed."""
    real_which = engine.shutil.which
    others = {"unrar", "7z", "bsdtar"} - {tool}
    return mock.patch("engine.shutil.which", side_effect=lambda n: None if n in others else real_which(n))


def _leftovers(dest):
    return [p.name for p in dest.iterdir() if p.name.startswith(".nashi")] if dest.exists() else []


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

    def test_read_only_folder_and_zero_mode_file(self):
        arch = self._zip([
            ("kilitli/", b"", stat.S_IFDIR | 0o555, (2021, 3, 4, 5, 6, 8)),
            ("kilitli/a.txt", b"a", stat.S_IFREG | 0o444, (2021, 3, 4, 5, 6, 8)),
            ("sifir.txt", b"z", stat.S_IFREG | 0o000, (2021, 3, 4, 5, 6, 8)),
        ])
        dest = self.tmp / "out"
        try:
            self.eng.extract_archive(str(arch), str(dest))
            self.assertEqual((dest / "kilitli" / "a.txt").read_bytes(), b"a")
            self.assertEqual(stat.S_IMODE((dest / "kilitli").stat().st_mode), 0o755)  # 0o555 stored, owner keeps rwx
            # a stored 000 file mode means "not set" (upstream): the file stays readable
            self.assertTrue(stat.S_IMODE((dest / "sifir.txt").stat().st_mode) & stat.S_IRUSR)
            self.assertEqual((dest / "sifir.txt").read_bytes(), b"z")
            tar_out = self.tmp / "donusum.tar"
            self.eng.convert_archive(str(arch), "tar", str(tar_out))
            with tarfile.open(tar_out) as t:
                self.assertIn("sifir.txt", [m.name.lstrip("./") for m in t.getmembers()])
        finally:
            for p in (dest / "sifir.txt", dest / "kilitli"):
                if p.exists():
                    os.chmod(p, 0o700)

    def test_duplicate_symlink_entries_give_clear_error(self):
        arch = self.tmp / "iki-link.zip"
        with zipfile.ZipFile(arch, "w") as z:
            for _ in range(2):
                info = zipfile.ZipInfo("link")
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, "hedef.txt")
            z.writestr("hedef.txt", b"x")
        with self.assertRaises(ValueError) as cm:
            self.eng.extract_archive(str(arch), str(self.tmp / "out"))
        self.assertIn("iki kez", str(cm.exception))

    def test_reextract_over_existing_symlink(self):
        arch = self.tmp / "link-ok.zip"
        with zipfile.ZipFile(arch, "w") as z:
            z.writestr("hedef.txt", b"x")
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "hedef.txt")
        dest = self.tmp / "out"
        self.eng.extract_archive(str(arch), str(dest))
        self.eng.extract_archive(str(arch), str(dest))  # same folder again
        self.assertEqual(os.readlink(dest / "link"), "hedef.txt")

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
        with _only_tool(tool):
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

    def _ro_rar(self):
        arch = self.tmp / "kilitli.rar"
        make_rar4(arch, [("kilitli", b"", stat.S_IFDIR | 0o555), ("kilitli/a.txt", b"a\n")])
        return arch

    def _cleanup_modes(self, dest):
        for dirpath, dirnames, _ in os.walk(dest):
            for d in dirnames:
                os.chmod(os.path.join(dirpath, d), 0o700)

    @need("unrar", "7z", "bsdtar")
    def test_read_only_folder_any_tool(self):
        arch = self._ro_rar()
        dest = self.tmp / "out"
        dest.mkdir()
        try:
            self.eng.extract_archive(str(arch), str(dest))
            self.assertEqual((dest / "kilitli" / "a.txt").read_bytes(), b"a\n")
            self.assertEqual(_leftovers(dest), [])
        finally:
            self._cleanup_modes(dest)

    def test_read_only_folder_each_tool_leaves_no_staging(self):
        for tool in ("unrar", "7z", "bsdtar"):
            if not engine.shutil.which(tool):
                continue
            dest = self.tmp / f"ro-{tool}"
            dest.mkdir()
            (dest / "kilitli").mkdir()  # existing folder in the destination: merged into
            try:
                with _only_tool(tool):
                    try:
                        self.eng.extract_archive(str(self._ro_rar()), str(dest))
                        self.assertEqual((dest / "kilitli" / "a.txt").read_bytes(), b"a\n", tool)
                    except RuntimeError:
                        pass  # a tool may refuse; it must still clean up after itself
                self.assertEqual(_leftovers(dest), [], tool)
            finally:
                self._cleanup_modes(dest)

    def test_existing_destination_folder_keeps_its_attributes(self):
        for tool in ("unrar", "7z", "bsdtar"):
            if not engine.shutil.which(tool):
                continue
            dest = self.tmp / f"keep-{tool}"
            (dest / "alt").mkdir(parents=True)
            os.chmod(dest / "alt", 0o750)
            os.utime(dest / "alt", (1_000_000_000, 1_000_000_000))
            with _only_tool(tool):
                self.eng.extract_archive(str(self.arch), str(dest))
            st = (dest / "alt").stat()
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o750, tool)
            self.assertTrue((dest / "alt" / "ikinci.txt").exists(), tool)

    def test_traversal_names_rejected_before_extracting(self):
        evil = self.tmp / "kotu.rar"
        make_rar4(evil, [("../kacis.txt", b"x"), ("ok.txt", b"y")])
        for tool in ("unrar", "7z", "bsdtar"):
            if not engine.shutil.which(tool):
                continue
            dest = self.tmp / f"ev-{tool}"
            with _only_tool(tool), mock.patch.object(engine.subprocess, "run", wraps=engine.subprocess.run) as run:
                with self.assertRaises(ValueError, msg=tool):
                    self.eng.extract_archive(str(evil), str(dest))
            self.assertEqual(len(run.call_args_list), 1, f"{tool}: only the listing may run")
            self.assertFalse((dest / "kacis.txt").exists())
            self.assertFalse((dest / "ok.txt").exists())
            self.assertFalse((self.tmp / "kacis.txt").exists())

    @need("unrar", "7z", "bsdtar")
    def test_all_tools_failing_reports_every_error(self):
        real_run = engine.subprocess.run

        def fake(cmd, *a, **kw):
            if cmd[:2] in (["unrar", "x"], ["7z", "x"]) or cmd[:2] == ["bsdtar", "-xf"]:
                return engine.subprocess.CompletedProcess(cmd, 2, stdout="", stderr=f"bozuk-{cmd[0]}")
            return real_run(cmd, *a, **kw)

        with mock.patch.object(engine.subprocess, "run", side_effect=fake):
            with self.assertRaises(RuntimeError) as cm:
                self.eng.extract_archive(str(self.arch), str(self.tmp / "out"))
        msg = str(cm.exception)
        for tool in ("unrar", "7z", "bsdtar"):
            self.assertIn(f"{tool}: bozuk-{tool}", msg)
        self.assertEqual(_leftovers(self.tmp / "out"), [])

    @need("unrar", "7z")
    def test_listing_falls_back_to_next_tool(self):
        real_run = engine.subprocess.run

        def fake(cmd, *a, **kw):
            if cmd[:2] == ["unrar", "lt"]:
                return engine.subprocess.CompletedProcess(cmd, 3, stdout="", stderr="liste-yok")
            return real_run(cmd, *a, **kw)

        dest = self.tmp / "out"
        with mock.patch.object(engine.subprocess, "run", side_effect=fake):
            self.eng.extract_archive(str(self.arch), str(dest))
        self.assertEqual((dest / "merhaba.txt").read_bytes(), b"Merhaba RAR\n")

    @need("unrar")
    def test_listing_failure_with_every_tool_reports_all(self):
        def fake(cmd, *a, **kw):
            return engine.subprocess.CompletedProcess(cmd, 3, stdout="", stderr=f"liste-yok-{cmd[0]}")

        with _only_tool("unrar"), mock.patch.object(engine.subprocess, "run", side_effect=fake):
            with self.assertRaises(RuntimeError) as cm:
                self.eng.extract_archive(str(self.arch), str(self.tmp / "out"))
        self.assertIn("unrar: liste-yok-unrar", str(cm.exception))

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
