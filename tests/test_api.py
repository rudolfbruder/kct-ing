"""End-to-end tests with the fake AI provider. Run: python -m unittest discover tests"""
from __future__ import annotations

import json
import os
import tempfile
import importlib.util
import unittest
from pathlib import Path

if not all(importlib.util.find_spec(m) for m in ("fastapi", "httpx", "multipart")):
    raise unittest.SkipTest("API packages not installed: fastapi, httpx, python-multipart")

# Settings are read once, so set them before importing the app. Settings of whoever runs the
# tests (.env, a notebook's Step 1, the shell) must not change the tests: drop them all first.
for _key in [k for k in os.environ if k.startswith("KCT_")]:
    del os.environ[_key]
STORAGE = Path(tempfile.mkdtemp(prefix="kct-test-"))
os.environ["KCT_ENV_FILE"] = ""  # never read the developer's .env
os.environ["KCT_AI_PROVIDER"] = "fake"
os.environ["KCT_STORAGE_ROOT"] = str(STORAGE)

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from services.ai.agent import Agent  # noqa: E402
from services.ai.exceptions import AiOutputTruncatedError  # noqa: E402
from services.control_testing.agents.test_steps_agent import TestStepsAgent  # noqa: E402

PDF = b"%PDF-1.4\n% fake document for tests\n%%EOF\n"


def upload(client: TestClient, control: bytes = PDF, plan: bytes = PDF):
    return client.post(
        "/api/v1/test-steps",
        files=[
            ("control_details", ("cd.pdf", control, "application/pdf")),
            ("test_plan", ("tp.pdf", plan, "application/pdf")),
        ],
    )


class TestStepsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_generates_stores_and_logs_steps(self) -> None:
        response = upload(self.client)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        meta = body["metadata"]
        case_id = meta["case_reference"]
        interpretation_id = meta["case_interpretation_id"]

        self.assertEqual(meta["provider"], "fake")
        self.assertEqual(set(body["summaries"]), {"control_details", "test_plan"})
        steps = body["test_steps"]
        self.assertEqual(meta["step_count"], len(steps))
        self.assertEqual(steps[0]["reference"], "0472-01")
        ids = [step["id"] for step in steps]
        self.assertEqual(len(set(ids)), len(ids))
        for step in steps:
            self.assertEqual(len(step["id"]), 36)  # UUID
            self.assertEqual(step["case_interpretation_id"], interpretation_id)
            self.assertEqual(step["case_id"], meta["case_id"])
            self.assertEqual(step["status"], "pending")
            self.assertTrue(step["acceptance_criteria"])
            self.assertTrue(step["refusal_criteria"])

        self.assertTrue((STORAGE / "uploads" / case_id / "control_details" / "cd.pdf").is_file())
        outputs = STORAGE / "outputs" / case_id
        saved = json.loads((outputs / f"case_interpretation_{interpretation_id}.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, body)
        self.assertTrue((outputs / "control_details_summary.md").is_file())
        self.assertTrue((outputs / "test_plan_summary.md").is_file())
        self.assertFalse((STORAGE / "database.sqlite").exists())  # memory driver by default

        calls = [json.loads(line) for line in (STORAGE / "logs" / "agents.log").read_text(encoding="utf-8").splitlines()]
        self.assertIn("test_steps", {c["agent"] for c in calls})
        self.assertTrue(all(c["provider"] == "fake" for c in calls))

        self.assertEqual(self.client.get(f"/api/v1/cases/{case_id}/test-steps").json(), body)
        self.assertEqual(
            self.client.get(f"/api/v1/case-interpretations/{interpretation_id}").json(), body
        )

    def test_rerun_creates_a_new_interpretation_with_new_step_ids(self) -> None:
        first = upload(self.client).json()
        case_id = first["metadata"]["case_reference"]
        response = self.client.post(f"/api/v1/cases/{case_id}/test-steps")
        self.assertEqual(response.status_code, 200, response.text)
        second = response.json()

        self.assertEqual(second["metadata"]["case_reference"], case_id)
        self.assertEqual(second["metadata"]["case_id"], first["metadata"]["case_id"])
        self.assertNotEqual(
            second["metadata"]["case_interpretation_id"], first["metadata"]["case_interpretation_id"]
        )
        self.assertFalse({s["id"] for s in first["test_steps"]} & {s["id"] for s in second["test_steps"]})

        # The case endpoint returns the newest interpretation; the list has both.
        latest = self.client.get(f"/api/v1/cases/{case_id}/test-steps").json()
        self.assertEqual(latest["metadata"], second["metadata"])
        listed = self.client.get("/api/v1/case-interpretations", params={"case_id": case_id}).json()
        self.assertEqual(
            [m["case_interpretation_id"] for m in listed],
            [second["metadata"]["case_interpretation_id"], first["metadata"]["case_interpretation_id"]],
        )

    def test_each_upload_gets_a_new_case(self) -> None:
        first, second = upload(self.client).json(), upload(self.client).json()
        self.assertNotEqual(first["metadata"]["case_reference"], second["metadata"]["case_reference"])
        self.assertNotEqual(first["metadata"]["case_id"], second["metadata"]["case_id"])

    def test_rejects_non_pdf(self) -> None:
        self.assertEqual(upload(self.client, control=b"not a pdf").status_code, 400)

    def test_missing_file_is_422(self) -> None:
        response = self.client.post(
            "/api/v1/test-steps",
            files=[("control_details", ("cd.pdf", PDF, "application/pdf"))],
        )
        self.assertEqual(response.status_code, 422)

    def test_unknown_case_is_404(self) -> None:
        self.assertEqual(self.client.get("/api/v1/cases/nope/test-steps").status_code, 404)
        self.assertEqual(self.client.post("/api/v1/cases/nope/test-steps").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/case-interpretations/no-such-id").status_code, 404)

    def test_invalid_model_output_is_502_and_keeps_the_case(self) -> None:
        TestStepsAgent.fake(['{"steps": [{"reference": "only a reference"}]}'])
        try:
            response = upload(self.client)
        finally:
            TestStepsAgent.stop_faking()
        self.assertEqual(response.status_code, 502)
        self.assertTrue(response.json()["detail"].startswith("case-"))

    def test_summary_endpoint(self) -> None:
        case_id = upload(self.client).json()["metadata"]["case_reference"]
        response = self.client.post(
            "/api/v1/summarize", json={"case_id": case_id, "kind": "test_plan"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["summary"].startswith("# Test Plan Summary"))


class AgentTest(unittest.TestCase):
    def test_answer_over_max_tokens_raises(self) -> None:
        class TinyStepsAgent(TestStepsAgent):
            max_tokens = 100

        with self.assertRaises(AiOutputTruncatedError):
            TinyStepsAgent().prompt("Produce the test steps.")

    def test_fake_answers_are_returned_in_order(self) -> None:
        class EchoAgent(Agent):
            name = "echo"

            def instructions(self) -> str:
                return "Repeat."

        EchoAgent.fake(["one", "two"])
        try:
            self.assertEqual(EchoAgent().prompt("x").text, "one")
            self.assertEqual(EchoAgent().prompt("x").text, "two")
        finally:
            EchoAgent.stop_faking()


class AskTest(unittest.TestCase):
    def test_api_and_service_give_the_same_answer(self) -> None:
        from services.app import boot

        body = TestClient(app).post("/api/v1/ask", json={"question": "What is 5+2?"}).json()
        self.assertEqual(body["answer"], "5 + 2 = 7.")
        self.assertEqual(body["provider"], "fake")

        result = boot().ask.ask("What is 5+2?")
        self.assertEqual(result.answer, body["answer"])



class EvidenceApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.case = upload(self.client).json()["metadata"]["case_reference"]

    def post(self, *files, folder=None, case=None):
        data = {"folder": folder} if folder else None
        return self.client.post(f"/api/v1/cases/{case or self.case}/evidences",
                                files=[("files", f) for f in files], data=data)

    def test_upload_list_and_parts(self) -> None:
        from factories import DocxFactory

        response = self.post((DocxFactory.name, DocxFactory().make(), "application/octet-stream"),
                             ("log.txt", b"line 1\nline 2", "text/plain"), folder="tickets/q1")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["evidence_count"], 2)
        self.assertEqual({s["path"] for s in body["stored"]},
                         {f"tickets/q1/{DocxFactory.name}", "tickets/q1/log.txt"})
        self.assertTrue((STORAGE / "evidences" / self.case / "tickets" / "q1" / "log.txt").is_file())

        listed = self.client.get(f"/api/v1/cases/{self.case}/evidences").json()
        self.assertEqual({e["kind"] for e in listed}, {"word", "text"})

        parts = self.client.get(f"/api/v1/cases/{self.case}/evidences/parts").json()
        self.assertEqual(len(parts), 2)
        word = next(p for p in parts if p["unit"].endswith(".docx"))
        self.assertTrue(word["documents"][0].endswith(".pdf"))     # converted for the AI
        # the converted PDF is not listed as evidence of its own
        self.assertEqual(len(self.client.get(f"/api/v1/cases/{self.case}/evidences").json()), 2)

    def test_same_name_replaces(self) -> None:
        self.post(("a.txt", b"one", "text/plain"))
        second = self.post(("a.txt", b"two", "text/plain")).json()
        self.assertTrue(second["stored"][0]["replaced"])
        self.assertEqual((STORAGE / "evidences" / self.case / "a.txt").read_text(encoding="utf-8"), "two")

    def test_rejects_unknown_types_and_cases(self) -> None:
        self.assertEqual(self.post(("tool.exe", b"MZ", "application/octet-stream")).status_code, 400)
        self.assertEqual(self.post(("empty.pdf", b"", "application/pdf")).status_code, 400)
        self.assertEqual(self.post(("a.txt", b"x", "text/plain"), case="case-999").status_code, 404)

    def test_names_cannot_leave_the_case_folder(self) -> None:
        response = self.post(("../../escape.txt", b"x", "text/plain"), folder="../../up")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["stored"][0]["path"], "up/escape.txt")
        self.assertTrue((STORAGE / "evidences" / self.case / "up" / "escape.txt").is_file())



class AssessmentApiTest(unittest.TestCase):
    """The assessment through the API with the fake AI. TestClient runs background tasks before returning."""

    def setUp(self) -> None:
        from factories import DocxFactory, ExcelFactory, MsgFactory

        self.client = TestClient(app)
        self.case = upload(self.client).json()["metadata"]["case_reference"]
        self.files = [(DocxFactory.name, DocxFactory().make()), (ExcelFactory.name, ExcelFactory(rows=20).make()),
                      (MsgFactory.name, MsgFactory(history=1).make())]

    def add_evidence(self) -> None:
        response = self.client.post(f"/api/v1/cases/{self.case}/evidences",
                                    files=[("files", (n, d, "application/octet-stream")) for n, d in self.files])
        self.assertEqual(response.status_code, 200, response.text)

    def start(self):
        response = self.client.post(f"/api/v1/cases/{self.case}/assessments")
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()["status"], "queued")
        return response.json()["assessment_id"]

    def test_runs_in_the_background_and_writes_a_read_only_report(self) -> None:
        self.add_evidence()
        assessment_id = self.start()
        body = self.client.get(f"/api/v1/assessments/{assessment_id}").json()
        meta = body["metadata"]
        self.assertEqual(meta["status"], "completed", meta["error"])
        self.assertEqual(meta["parts_total"], 3)
        self.assertEqual((meta["parts_done"], meta["parts_failed"]), (3, 0))
        self.assertEqual(len(body["verdicts"]), 17)
        verdict = next(v for v in body["verdicts"] if v["step_reference"] == "0472-04")
        self.assertEqual(verdict["verdict"], "not_effective")
        self.assertEqual(verdict["exceptions"][0]["item"], "SD-105112")
        self.assertTrue(all(len(p["unit_sha256"]) == 64 for p in body["parts"]))

        pdf = self.client.get(f"/api/v1/assessments/{assessment_id}/report.pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertIn(b"/Encrypt", pdf.content)                                   # read-only permissions
        import hashlib
        self.assertEqual(hashlib.sha256(pdf.content).hexdigest(), meta["report_sha256"])

        steps = self.client.get(f"/api/v1/cases/{self.case}/test-steps").json()["test_steps"]
        self.assertEqual({s["status"] for s in steps}, {"effective", "not_effective"})   # statuses follow
        listed = self.client.get(f"/api/v1/cases/{self.case}/assessments").json()
        self.assertEqual([a["assessment_id"] for a in listed], [assessment_id])

    def test_a_failing_part_is_recorded_and_the_run_goes_on(self) -> None:
        from services.assessment.agents.evidence_assessment_agent import EvidenceAssessmentAgent

        self.add_evidence()
        fixture = json.loads((Path(__file__).parent / "fixtures" / "fake_ai" / "evidence_assessment.json").read_text(encoding="utf-8"))
        good = json.dumps(fixture["_match"][0]["answer"])
        EvidenceAssessmentAgent.fake([good, '{"findings": "not a list"}', good])
        try:
            assessment_id = self.start()
        finally:
            EvidenceAssessmentAgent.stop_faking()
        body = self.client.get(f"/api/v1/assessments/{assessment_id}").json()
        self.assertEqual(body["metadata"]["status"], "completed")
        self.assertEqual((body["metadata"]["parts_done"], body["metadata"]["parts_failed"]), (2, 1))
        failed = [p for p in body["parts"] if p["status"] == "failed"]
        self.assertIn("AiInvalidOutputError", failed[0]["error"])

    def test_no_evidence_means_not_effective_without_calling_the_model(self) -> None:
        assessment_id = self.start()
        body = self.client.get(f"/api/v1/assessments/{assessment_id}").json()
        self.assertEqual(body["metadata"]["status"], "completed")
        self.assertTrue(all(v["verdict"] == "not_effective" and v["no_evidence"] and v["fallback"]
                            for v in body["verdicts"]))

    def test_missing_verdicts_fall_back_and_history_is_kept(self) -> None:
        from services.assessment.agents.verdict_agent import VerdictAgent

        self.add_evidence()
        first = self.start()
        VerdictAgent.fake(['{"verdicts": [{"step_reference": "0472-01", "verdict": "effective", '
                           '"no_evidence": false, "reason": "ok"}]}'])
        try:
            second = self.start()
        finally:
            VerdictAgent.stop_faking()
        body = self.client.get(f"/api/v1/assessments/{second}").json()
        fallback = [v for v in body["verdicts"] if v["fallback"]]
        self.assertEqual(len(fallback), 16)
        self.assertTrue(all(v["verdict"] == "not_effective" for v in fallback))
        listed = [a["assessment_id"] for a in self.client.get(f"/api/v1/cases/{self.case}/assessments").json()]
        self.assertEqual(set(listed), {first, second})

    def test_errors(self) -> None:
        self.assertEqual(self.client.post("/api/v1/cases/case-999/assessments").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/assessments/nope").status_code, 404)



class ImportApiTest(unittest.TestCase):
    def test_import_is_off_without_import_root_and_works_inside_it(self) -> None:
        from unittest import mock

        from factories import ControlFolderFactory
        from services.config import settings

        client = TestClient(app)
        root = STORAGE / "sharepoint"
        source = ControlFolderFactory(excel_rows=5, pdf_pages=2).create(root)
        off = client.post("/api/v1/cases/import", json={"path": str(source)})
        self.assertEqual(off.status_code, 422)
        self.assertIn("KCT_IMPORT_ROOT", off.json()["detail"])

        config = settings()
        with mock.patch("controllers.imports_controller.settings",
                        return_value=type(config)(**{**config.__dict__, "import_root": str(root)})):
            outside = client.post("/api/v1/cases/import", json={"path": str(STORAGE)})
            self.assertEqual(outside.status_code, 422)
            done = client.post("/api/v1/cases/import", json={"path": str(source), "assess": True})
        self.assertEqual(done.status_code, 200, done.text)
        body = done.json()
        self.assertTrue(body["case_interpretation_id"])
        assessment = client.get(f"/api/v1/assessments/{body['assessment_id']}").json()
        self.assertEqual(assessment["metadata"]["status"], "completed")
        self.assertIn(body["case_id"], client.get("/api/v1/cases").json())


    def test_zip_upload(self) -> None:
        from factories import ControlFolderFactory

        client = TestClient(app)
        data = ControlFolderFactory(excel_rows=5, pdf_pages=2).zip()
        response = client.post("/api/v1/cases/import-zip", files={"file": ("control.zip", data, "application/zip")},
                               data={"interpret": "true"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["case_interpretation_id"])
        self.assertTrue(Path(body["source_zip"]).is_file())
        self.assertTrue((Path(body["sorted_folder"]) / "import.json").is_file())


if __name__ == "__main__":
    unittest.main()
