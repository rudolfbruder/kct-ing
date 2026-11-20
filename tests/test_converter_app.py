"""ConverterApp: Word to PDF in the Jupyter converter app, without a screen."""
from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

from services.presentation.converter_app import ConverterApp, _safe

HAS_DOCX = all(importlib.util.find_spec(m) for m in ("docx", "reportlab"))
HAS_WIDGETS = importlib.util.find_spec("ipywidgets") is not None


def fake_docx() -> bytes:
    import docx

    document = docx.Document()
    document.add_heading("Fake evidence", 1)
    document.add_paragraph("Access review approved by a fake reviewer.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "User", "Role"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class ConverterAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = ConverterApp(output_root=self.root, engine="python", show=False)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @unittest.skipUnless(HAS_DOCX, "python-docx and reportlab are needed")
    def test_word_becomes_pdf(self) -> None:
        result = self.app.convert_file("Evidence 01.docx", fake_docx())
        self.assertTrue(result.ok)
        self.assertEqual(result.engine, "python")
        self.assertTrue(result.pdf.is_file())
        self.assertTrue(result.pdf.read_bytes().startswith(b"%PDF"))
        self.assertTrue(str(result.pdf).startswith(str(self.root.resolve())))
        html = ConverterApp.render([result])
        self.assertIn(str(result.pdf), html)
        self.assertIn("data:application/pdf;base64,", html)

    def test_other_formats_are_not_supported_yet(self) -> None:
        for name in ("a.pdf", "b.xlsx", "c.msg", "d.doc"):
            result = self.app.convert_file(name, b"anything")
            self.assertFalse(result.ok)
            self.assertFalse(result.supported)
            self.assertIn("not supported yet", result.error)
        self.assertEqual(list(self.root.iterdir()), [])   # nothing saved for them

    def test_broken_word_file_is_an_error_not_a_crash(self) -> None:
        result = self.app.convert_file("broken.docx", b"not a word file")
        self.assertFalse(result.ok)
        self.assertTrue(result.supported)
        self.assertTrue(result.error)
        self.assertIn("failed", ConverterApp.render([result]))

    @unittest.skipUnless(HAS_DOCX, "python-docx and reportlab are needed")
    def test_one_folder_per_click(self) -> None:
        results = self.app.convert_uploads([("a.docx", fake_docx()), ("b.xlsx", b"x"), ("c.docx", fake_docx())])
        self.assertEqual([r.ok for r in results], [True, False, True])
        self.assertEqual(results[0].pdf.parent, results[2].pdf.parent)

    def test_safe_names(self) -> None:
        self.assertEqual(_safe("../../etc/passwd.docx"), "passwd.docx")
        self.assertEqual(_safe("a/b:c?.docx"), "b_c_.docx")

    @unittest.skipUnless(HAS_WIDGETS, "ipywidgets is needed")
    def test_screen_builds(self) -> None:
        app = ConverterApp(output_root=self.root, show=True)
        self.assertIn("Only Word (.docx) works for now", app.box.children[0].value)
        app.start()   # nothing chosen
        self.assertIn("Choose a file first", app.status.value)


if __name__ == "__main__":
    unittest.main()
