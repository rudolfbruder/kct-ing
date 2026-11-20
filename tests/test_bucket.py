"""Buckets: a Word document's PDF plus every file embedded in it (also nested)."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from services.evidences.bucket import BucketConverter
from services.evidences.docx_attachments import embedded_files, make_ole10native, parse_ole10native
from services.evidences.docx_converter import DocxConverter

HAS_FACTORY = all(importlib.util.find_spec(m) for m in ("docx", "openpyxl", "PIL", "extract_msg", "reportlab"))


class Ole10NativeTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        self.assertEqual(parse_ole10native(make_ole10native("Signed review.pdf", b"%PDF-1.4 x")),
                         ("Signed review.pdf", b"%PDF-1.4 x"))

    def test_broken(self) -> None:
        self.assertIsNone(parse_ole10native(b"\x00\x01"))


@unittest.skipUnless(HAS_FACTORY, "the fake document needs python-docx, openpyxl, Pillow, extract-msg, reportlab")
class BucketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from factories.docx_attachments_factory import DocxAttachmentsFactory
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = DocxAttachmentsFactory().create(cls.root / "in")
        cls.item = BucketConverter(DocxConverter("builtin")).convert(cls.source, cls.root / "out")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_embedded_files_in_document_order(self) -> None:
        files = embedded_files(self.source)
        self.assertEqual([f.name for f in files], ["Microsoft_Excel_Worksheet.xlsx", "Signed review Q1.pdf",
                                                   "Approval access review.msg", "Microsoft_Word_Document.docx"])
        self.assertEqual([f.kind for f in files], ["package", "ole-native", "ole-native", "package"])
        self.assertTrue(files[1].data.startswith(b"%PDF"))
        self.assertTrue(files[2].data.startswith(b"\xd0\xcf\x11\xe0"))

    def test_bucket_layout(self) -> None:
        item, folder = self.item, self.item.folder
        self.assertEqual(folder.name, self.source.stem)
        self.assertTrue((folder / f"{self.source.stem}.pdf").is_file())
        self.assertTrue((folder / "source" / self.source.name).is_file())
        names = sorted(p.name for p in (folder / "attachments").iterdir())
        self.assertEqual(names, ["01_Microsoft_Excel_Worksheet.xlsx", "02_Signed review Q1.pdf",
                                 "03_Approval access review.msg", "04_Microsoft_Word_Document"])
        self.assertEqual([c.status for c in item.children], ["saved", "pdf", "saved", "converted"])

    def test_nested_word_has_its_own_bucket(self) -> None:
        nested = self.item.children[3]
        self.assertEqual(nested.folder, self.item.folder / "attachments" / "04_Microsoft_Word_Document")
        self.assertTrue(nested.pdf.is_file())
        self.assertEqual([c.name for c in nested.children], ["checklist.txt"])
        self.assertEqual(nested.children[0].source.read_bytes()[:8], b"1. List ")
        self.assertEqual(len(list(self.item.walk())), 6)

    def test_manifest(self) -> None:
        manifest = json.loads((self.item.folder / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "converted")
        self.assertEqual(manifest["attachments"][1]["source"], "attachments/02_Signed review Q1.pdf")
        self.assertEqual(manifest["attachments"][3]["attachments"][0]["name"], "checklist.txt")


if __name__ == "__main__":
    unittest.main()
