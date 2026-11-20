"""The builtin Word engine: .docx to PDF with the standard library only."""
from __future__ import annotations

import importlib.util
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from services.evidences import docx_converter
from services.evidences.docx_builtin import sample_docx, to_pdf
from services.evidences.docx_converter import DocxConverter
from services.evidences.exceptions import ConversionError
from services.evidences.simple_pdf import SimplePdf, text_width, to_winansi

HAS_DOCX = importlib.util.find_spec("docx") is not None and importlib.util.find_spec("PIL") is not None
HAS_PYPDF = importlib.util.find_spec("pypdf") is not None


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    return "\n".join(page.extract_text() for page in PdfReader(str(path)).pages)


def png(width: int, height: int, color_type: int) -> bytes:
    channels = {0: 1, 2: 3, 6: 4}[color_type]
    rows = b"".join(b"\x01" + bytes([200, 30, 30, 255][:channels]) + bytes(channels) * (width - 1)
                    for _ in range(height))   # filter 1 (Sub) on every row

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


class BuiltinEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_sample_document(self) -> None:
        source = self.root / "s.docx"
        source.write_bytes(sample_docx(["First line", "Second (with brackets) and \\ backslash"]))
        pdf = DocxConverter("builtin").convert(source).pdf
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF-1.4"))
        if HAS_PYPDF:
            text = pdf_text(pdf)
            self.assertIn("First line", text)
            self.assertIn("Second (with brackets) and \\ backslash", text)

    @unittest.skipUnless(HAS_DOCX and HAS_PYPDF, "python-docx, Pillow and pypdf make the fake document")
    def test_fake_evidence_keeps_content(self) -> None:
        from factories.docx_factory import DocxFactory
        source = DocxFactory().create(self.root)
        text = pdf_text(DocxConverter("builtin").convert(source).pdf)
        for expected in ("EV-01 Service desk tickets", "1. Scope", "• Source system: ServiceNow SD",
                         "SD-104233", "AGT-0193", "4. Notes"):
            self.assertIn(expected, text)

    @unittest.skipUnless(HAS_DOCX and HAS_PYPDF, "python-docx and pypdf are needed")
    def test_long_text_wraps_and_breaks_pages(self) -> None:
        import docx
        document = docx.Document()
        for number in range(120):
            document.add_paragraph(f"Paragraph {number} " + "word " * 40)
        document.add_page_break()
        document.add_paragraph("After the break")
        source = self.root / "long.docx"
        document.save(source)
        from pypdf import PdfReader
        pdf = DocxConverter("builtin").convert(source).pdf
        pages = PdfReader(str(pdf)).pages
        self.assertGreater(len(pages), 5)
        self.assertIn("After the break", pages[-1].extract_text())
        self.assertNotIn("After the break", pages[-2].extract_text())

    def test_broken_file(self) -> None:
        source = self.root / "broken.docx"
        source.write_bytes(b"not a zip")
        with self.assertRaises(ConversionError):
            to_pdf(source, self.root / "x.pdf")

    def test_auto_uses_builtin_without_packages(self) -> None:
        source = self.root / "s.docx"
        source.write_bytes(sample_docx(["Hello"]))
        with mock.patch.object(docx_converter, "python_engine_installed", return_value=False), \
                mock.patch.object(docx_converter.libreoffice, "binary", return_value=None):
            self.assertEqual(DocxConverter().convert(source).engine, "builtin")


class SimplePdfTest(unittest.TestCase):
    def test_letters(self) -> None:
        self.assertEqual(to_winansi("café € Bühne"), "café € Bühne".encode("cp1252"))
        self.assertEqual(to_winansi("Čučoriedka"), b"Cucoriedka")
        self.assertEqual(to_winansi("日"), b"?")
        self.assertGreater(text_width("WWW", "bold", 10), text_width("iii", "regular", 10))

    def test_pictures(self) -> None:
        pdf = SimplePdf()
        for color_type in (0, 2, 6):
            image = pdf.add_image(png(4, 3, color_type))
            self.assertIsNotNone(image)
            self.assertEqual((image.width, image.height), (4, 3))
        self.assertIsNone(pdf.add_image(b"GIF89a....."))
        with tempfile.TemporaryDirectory() as folder:
            pdf.image(image, 10, 10, 40, 30)
            out = pdf.save(Path(folder) / "p.pdf")
            if HAS_PYPDF:
                from pypdf import PdfReader
                self.assertEqual(len(PdfReader(str(out)).pages), 1)


if __name__ == "__main__":
    unittest.main()
