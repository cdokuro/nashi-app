"""Wave 1 / madde 8: CSV/TSV/altyazı girdilerinde metin kodlaması algılama."""
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # standalone runs

import csv

from wave1_common import TempDirTestCase

import engine  # noqa: E402

TEXT = "ad,şehir\nAyşe,İstanbul\nIşık,Çanakkale\n"


class DecodeTextTests(TempDirTestCase):
    def test_decode_variants(self):
        cases = {
            "utf8": TEXT.encode("utf-8"),
            "utf8bom": b"\xef\xbb\xbf" + TEXT.encode("utf-8"),
            "utf16le": b"\xff\xfe" + TEXT.encode("utf-16-le"),
            "utf16be": b"\xfe\xff" + TEXT.encode("utf-16-be"),
            "utf16le_nobom": TEXT.encode("utf-16-le"),
            "utf32le": b"\xff\xfe\x00\x00" + TEXT.encode("utf-32-le"),
            "utf32be": b"\x00\x00\xfe\xff" + TEXT.encode("utf-32-be"),
            "cp1254": TEXT.encode("cp1254"),
        }
        for label, data in cases.items():
            self.assertEqual(engine.decode_text_bytes(data), TEXT, label)

    def test_empty(self):
        self.assertEqual(engine.decode_text_bytes(b""), "")


class TabularAndSubtitleTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.eng = engine.NashiEngine()

    def test_cp1254_csv_to_tsv(self):
        src = self.tmp / "liste.csv"
        src.write_bytes(TEXT.replace("\n", "\r\n").encode("cp1254"))
        out = self.eng.convert(str(src), "tsv")
        with open(out, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f, delimiter="\t"))
        self.assertEqual(rows, [["ad", "şehir"], ["Ayşe", "İstanbul"], ["Işık", "Çanakkale"]])

    def test_utf16_tsv_to_csv(self):
        src = self.tmp / "liste.tsv"
        src.write_bytes(b"\xff\xfe" + TEXT.replace(",", "\t").encode("utf-16-le"))
        out = self.eng.convert(str(src), "csv")
        with open(out, encoding="utf-8", newline="") as f:
            self.assertEqual(list(csv.reader(f))[1], ["Ayşe", "İstanbul"])

    def test_bom_csv_header_has_no_bom(self):
        src = self.tmp / "bom.csv"
        src.write_bytes(b"\xef\xbb\xbf" + TEXT.encode("utf-8"))
        out = self.eng.convert(str(src), "tsv")
        with open(out, encoding="utf-8") as f:
            self.assertTrue(f.read().startswith("ad\tşehir"))

    def test_cp1254_srt_to_vtt(self):
        src = self.tmp / "film.srt"
        src.write_bytes("1\r\n00:00:01,000 --> 00:00:02,500\r\nGüneş ışığı\r\n".encode("cp1254"))
        out = self.eng.convert(str(src), "vtt")
        with open(out, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("Güneş ışığı", body)
        self.assertIn("00:00:01.000 --> 00:00:02.500", body)

    def test_utf16_vtt_to_srt(self):
        src = self.tmp / "film.vtt"
        src.write_bytes(b"\xff\xfe" + "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nİyi akşamlar\n".encode("utf-16-le"))
        out = self.eng.convert(str(src), "srt")
        with open(out, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("İyi akşamlar", body)
        self.assertIn("00:00:01,000 --> 00:00:02,000", body)
