"""ConverterApp: Word to PDF in the Jupyter converter app, without a screen."""
from __future__ import annotations

import datetime
import importlib.util
import tempfile
import unittest
from pathlib import Path

from services.evidences.bucket import safe_name
from services.evidences.docx_builtin import sample_docx
from services.presentation.converter_app import UNSUPPORTED, ConverterApp

HAS_WIDGETS = importlib.util.find_spec("ipywidgets") is not None


class ConverterAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = ConverterApp(output_root=self.root, engine="builtin", show=False)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_word_becomes_a_bucket_with_pdf(self) -> None:
        item = self.app.convert_file("Evidence 01.docx", sample_docx(["Hello"]))
        self.assertEqual(item.status, "converted")
        self.assertEqual(item.engine, "builtin")
        self.assertTrue(item.pdf.read_bytes().startswith(b"%PDF"))
        self.assertEqual(item.pdf.parent, item.folder)
        self.assertEqual(item.folder.name, "Evidence 01")
        self.assertTrue((item.folder / "source" / "Evidence 01.docx").is_file())
        self.assertTrue((item.folder / "manifest.json").is_file())
        html = ConverterApp.render([item])
        self.assertIn(str(item.pdf), html)
        self.assertIn(str(item.folder), html)
        self.assertIn("data:application/pdf;base64,", html)
        self.assertIn("No embedded files", html)

    def test_other_formats_are_not_supported_yet(self) -> None:
        for name in ("a.pdf", "b.xlsx", "c.msg", "d.doc"):
            item = self.app.convert_file(name, b"anything")
            self.assertEqual(item.status, UNSUPPORTED)
            self.assertIn("not supported yet", item.error)
        self.assertEqual(list(self.root.iterdir()), [])   # nothing saved for them

    def test_broken_word_file_is_an_error_not_a_crash(self) -> None:
        item = self.app.convert_file("broken.docx", b"not a word file")
        self.assertEqual(item.status, "failed")
        self.assertTrue(item.error)
        self.assertIn("failed", ConverterApp.render([item]))

    def test_one_folder_per_click(self) -> None:
        items = self.app.convert_uploads([("a.docx", sample_docx(["a"])), ("b.xlsx", b"x"),
                                          ("a.docx", sample_docx(["again"]))])
        self.assertEqual([i.status for i in items], ["converted", UNSUPPORTED, "converted"])
        self.assertEqual(items[0].folder.parent, items[2].folder.parent)
        self.assertEqual(items[2].folder.name, "a_2")       # same name, own bucket

    def test_safe_names(self) -> None:
        self.assertEqual(safe_name("../../etc/passwd.docx"), "passwd.docx")
        self.assertEqual(safe_name("C:\\Users\\x\\b:c?.docx"), "b_c_.docx")

    @unittest.skipUnless(HAS_WIDGETS, "ipywidgets is needed")
    def test_screen_click(self) -> None:
        app = ConverterApp(output_root=self.root, engine="builtin", show=True)
        self.assertIn("Only Word (.docx) works for now", app.box.children[0].value)
        app.start()   # nothing chosen
        self.assertIn("Choose a file first", app.status.value)
        app.upload.value = ({"name": "ev.docx", "type": "", "size": 1, "content": memoryview(sample_docx(["x"])),
                             "last_modified": datetime.datetime.now()},)
        app.start()
        self.assertIn("kct-spinner", app.status.value)
        app._worker.join(timeout=60)
        self.assertIn("converted", app.status.value)
        self.assertFalse(app.convert_button.disabled)


if __name__ == "__main__":
    unittest.main()
