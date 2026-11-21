"""Wave 1 / madde 6: Kütüphane araması Türkçe İ/ı/I/i ve aksan duyarsız."""
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # standalone runs

import unicodedata

from wave1_common import TempDirTestCase

import store  # noqa: E402


class LibrarySearchTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.st = store.NashiStore(self.tmp / "data")
        for name in ("İstanbul.pdf", "Işık.png", "café.jpg", "rapor.txt",
                     unicodedata.normalize("NFD", "İzmir.mp4"), "IMAGE.png"):
            out = self.tmp / name
            out.write_text("x")
            self.st.add_export(name, str(out), out.suffix.lstrip("."), action_title="→ PDF")

    def names(self, q):
        return sorted(unicodedata.normalize("NFC", e["source_name"]) for e in self.st.get_recent_exports(q))

    def test_dotted_capital_i(self):
        self.assertEqual(self.names("istanbul"), ["İstanbul.pdf"])
        self.assertEqual(self.names("İSTANBUL"), ["İstanbul.pdf"])

    def test_dotless_i(self):
        self.assertEqual(self.names("ışık"), ["Işık.png"])
        self.assertEqual(self.names("isik"), ["Işık.png"])
        self.assertEqual(self.names("IŞIK"), ["Işık.png"])

    def test_decomposed_names(self):
        self.assertEqual(self.names("izmir"), ["İzmir.mp4"])
        self.assertEqual(self.names(unicodedata.normalize("NFD", "İzmir")), ["İzmir.mp4"])

    def test_accents_and_plain_ascii(self):
        self.assertEqual(self.names("cafe"), ["café.jpg"])
        self.assertEqual(self.names("CAFÉ"), ["café.jpg"])
        self.assertEqual(self.names("image"), ["IMAGE.png"])

    def test_blank_query_returns_all(self):
        self.assertEqual(len(self.st.get_recent_exports("   ")), 6)
        self.assertEqual(self.names("yok-boyle-bir-sey"), [])

    def test_fold_helper(self):
        self.assertEqual(store.search_fold("İıIiÇŞĞÜÖ"), "iiiicsguo")
