"""The clickable Jupyter app, driven from code (the buttons call the same methods)."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

if importlib.util.find_spec("ipywidgets") is None or importlib.util.find_spec("IPython") is None:
    raise unittest.SkipTest("ipywidgets is not installed (Step 3 of 01_setup installs it)")

if "KCT_STORAGE_ROOT" not in os.environ:      # run on its own: own settings (test_api may have set them first)
    for _key in [k for k in os.environ if k.startswith("KCT_")]:
        del os.environ[_key]
    os.environ.update(KCT_ENV_FILE="", KCT_AI_PROVIDER="fake",
                      KCT_STORAGE_ROOT=str(Path(tempfile.mkdtemp(prefix="kct-app-"))))

from services.app import boot  # noqa: E402
from services.presentation.app import KctApp, _uploads  # noqa: E402

PDF = b"%PDF-1.4\n% sample document\n%%EOF\n"


def new_case(app, prefix: str = "Control") -> str:
    """A case with a unique name and the two sample documents, as the app's tab 1 makes it."""
    import uuid

    case = app.create_case(f"{prefix} {uuid.uuid4().hex[:8]}")
    app.set_documents(("control details.pdf", PDF), ("test plan.pdf", PDF))
    return case


class FakeDelayTest(unittest.TestCase):
    def test_fake_ai_waits_only_when_asked(self) -> None:
        import time
        from unittest import mock

        from services.ai.providers.fake import FakeProvider

        with mock.patch.dict(os.environ, {"KCT_FAKE_DELAY": "0.05-0.1"}):
            start = time.monotonic()
            FakeProvider._pause()
            self.assertGreaterEqual(time.monotonic() - start, 0.05)
        with mock.patch.dict(os.environ, {"KCT_FAKE_DELAY": ""}), mock.patch("time.sleep") as sleep:
            FakeProvider._pause()
            sleep.assert_not_called()


class AppTest(unittest.TestCase):
    def test_tabs_of_this_release(self) -> None:
        app = KctApp(boot())
        self.assertEqual([t.split(" · ")[0] for t in app.titles],
                         ["1 Case", "2 Test steps", "3 Evidence", "4 Assess", "5 Result", "History"])
        self.assertEqual(app.available, ["1 Case", "2 Test steps", "3 Evidence"])
        self.assertEqual([t for t in app.titles if t.endswith("· soon")], app.titles[len(app.available):-1])
        self.assertEqual(len(app.next_buttons), len(app.available) - 1)   # no "Next" into a tab that is not there
        soon = [b for b in app.header.children[-1].children if getattr(b, "disabled", False)]
        self.assertTrue(soon and all("soon" in b.description for b in soon))   # Run all: greyed out

    def test_case_from_two_documents_then_test_steps(self) -> None:
        app = KctApp(boot())
        case = new_case(app)
        self.assertEqual(app.case, case)
        self.assertEqual(app.case_picker.value, case)
        interpretation = app.new_run()                                        # tab 1: Make test steps
        self.assertEqual(app.tabs.selected_index, 1)
        self.assertEqual(len(app.step_picker.options), len(interpretation.test_steps))
        self.assertEqual(app.step_picker.value, interpretation.test_steps[0].id)   # first step shown
        self.assertEqual(app.step_picker.style.description_width, "initial")      # label not pushed right
        self.assertIsNotNone(app.show_steps())

    def test_evidence(self) -> None:
        app = KctApp(boot())
        new_case(app)
        app.upload_evidence([("extra note.txt", b"Reviewed on 2026-03-31.")], folder="notes")
        self.assertIn(Path("notes/extra note.txt"), app.show_evidence())
        self.assertGreaterEqual(len(app.show_parts()), 1)

    def test_each_upload_is_a_new_run(self) -> None:
        app = KctApp(boot())
        interpreted = new_case(app)
        app.interpret()
        self.assertTrue(app.step_picker.options)
        new_case(app)
        self.assertIsNone(app.step_picker.value)                       # no steps of the earlier run
        self.assertIsNone(app.interpretation_id)
        reopened = KctApp(boot())                                      # the app opened again: clean as well
        reopened.case_picker.value = interpreted                       # a case picked at the top: clean too
        self.assertIsNone(reopened.step_picker.value)
        self.assertIsNotNone(reopened.show_steps())                    # the saved steps on request ('Show latest')

    def test_a_case_is_a_name_and_each_run_brings_its_documents(self) -> None:
        import uuid

        from services.presentation.app import NEW_CASE

        app = KctApp(boot())
        self.assertIsNone(app.case_picker.value)                          # "Click here and select a case …"
        app.case_picker.value = NEW_CASE                                  # + New case: only a name
        self.assertEqual((app.new_box.layout.display, app.case_box.layout.display), ("", "none"))
        name = f"Name only {uuid.uuid4().hex[:6]}"
        case = app.create_case(name)
        self.assertEqual(app.kct.files.case_name(case), name)
        self.assertEqual((app.new_box.layout.display, app.case_box.layout.display), ("none", ""))
        self.assertIsNone(app._safe(app.case_out, app.new_run))           # no documents yet: a message
        with self.assertRaises(Exception):
            app.kct.files.create_case(name)                               # the same name twice: refused

        cases = len(app.kct.files.case_ids())
        first = app.new_run(("CD v1.pdf", PDF + b"1"), ("TP v1.pdf", PDF + b"1")).metadata.case_interpretation_id
        second = app.new_run(("CD v2.pdf", PDF + b"2"), ("TP v2.pdf", PDF + b"2")).metadata.case_interpretation_id
        third = app.new_run().metadata.case_interpretation_id             # no files: the last run's documents
        self.assertEqual(len({first, second, third}), 3)                  # three runs of the same case
        self.assertEqual(len(app.kct.files.case_ids()), cases)            # and no new case
        self.assertEqual([d["name"] for d in app.kct.files.run_documents(case, first)], ["CD v1.pdf", "TP v1.pdf"])
        self.assertEqual([d["name"] for d in app.kct.files.run_documents(case, third)], ["CD v2.pdf", "TP v2.pdf"])
        self.assertEqual(app.tabs.selected_index, 1)

    def test_history_shows_earlier_runs_and_continues_with_them(self) -> None:
        app = KctApp(boot())
        case = new_case(app)
        interpretation = app.interpret()
        run = interpretation.metadata.case_interpretation_id
        self.assertIn(run, [value for _, value in app.history_picker.options])
        self.assertEqual(app.show_history(run).metadata.case_interpretation_id, run)
        self.assertEqual(app.history_step_picker.value, interpretation.test_steps[0].id)

        new_case(app, "Other")                                                     # another case
        self.assertNotIn(run, [value for _, value in app.history_picker.options])   # only this case's runs
        app.history_all.value = True
        self.assertIn(run, [value for _, value in app.history_picker.options])      # all cases
        app.use_run(run)                                                           # back, without the AI
        self.assertEqual((app.case, app.interpretation_id), (case, run))
        self.assertEqual(app.tabs.selected_index, 1)
        self.assertEqual(len(app.step_picker.options), len(interpretation.test_steps))

    def test_styled_like_flowbite(self) -> None:
        app = KctApp(boot())
        self.assertIn("kct-app", app.widget._dom_classes)
        self.assertIn("kct-tabs", app.tabs._dom_classes)
        self.assertIn("kct-btn-primary", app.interpret_button._dom_classes)
        self.assertIn("kct-select", app.case_picker._dom_classes)
        self.assertIn("kct-btn-next", app.next_buttons[0]._dom_classes)
        self.assertIn("border-radius", app.header.children[0].value)      # the style sheet is in the app

    def test_busy_buttons_get_a_spinner_and_come_back(self) -> None:
        from services.presentation import notebook as show

        app = KctApp(boot())
        with app._busy(app.steps_out, "Working …", app.interpret_button):
            self.assertTrue(app.interpret_button.disabled)
            self.assertIn("spinner", app.interpret_button.icon)
        self.assertFalse(app.interpret_button.disabled)
        self.assertEqual(app.interpret_button.icon, "list")
        self.assertIn("kct-skeleton", show.loading("Working …").data)

    def test_errors_are_shown_not_raised(self) -> None:
        app = KctApp(boot())
        app.case = None
        self.assertIsNone(app._safe(app.steps_out, app.interpret))     # no case chosen: a message, no traceback

    def test_upload_formats_of_ipywidgets_7_and_8(self) -> None:
        self.assertEqual(_uploads({"a.zip": {"content": b"x"}}), [("a.zip", b"x")])
        self.assertEqual(_uploads(({"name": "a.zip", "content": memoryview(b"x")},)), [("a.zip", b"x")])
        self.assertEqual(_uploads(()), [])


if __name__ == "__main__":
    unittest.main()
