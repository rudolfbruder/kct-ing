"""End-to-end tests with the fake AI provider. Run: python -m unittest discover tests"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

# Settings are read once, so set them before importing the app.
STORAGE = Path(tempfile.mkdtemp(prefix="kct-test-"))
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
        case_id = body["case_id"]

        self.assertEqual(set(body["summaries"]), {"control_details", "test_plan"})
        steps = body["test_steps"]
        self.assertTrue(steps)
        for step in steps:
            self.assertEqual(step["status"], "pending")
            self.assertTrue(step["acceptance_criteria"])
            self.assertTrue(step["refusal_criteria"])

        self.assertTrue((STORAGE / "uploads" / case_id / "control_details" / "cd.pdf").is_file())
        outputs = STORAGE / "outputs" / case_id
        self.assertEqual(json.loads((outputs / "test_steps.json").read_text()), steps)
        self.assertTrue((outputs / "control_details_summary.md").is_file())
        self.assertTrue((outputs / "test_plan_summary.md").is_file())

        calls = [json.loads(line) for line in (STORAGE / "logs" / "agents.log").read_text().splitlines()]
        self.assertIn("test_steps", {c["agent"] for c in calls})
        self.assertTrue(all(c["provider"] == "fake" for c in calls))

        self.assertEqual(self.client.get(f"/api/v1/cases/{case_id}/test-steps").json(), steps)

    def test_regenerates_for_a_stored_case(self) -> None:
        case_id = upload(self.client).json()["case_id"]
        response = self.client.post(f"/api/v1/cases/{case_id}/test-steps")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["case_id"], case_id)

    def test_each_upload_gets_a_new_case(self) -> None:
        self.assertNotEqual(upload(self.client).json()["case_id"], upload(self.client).json()["case_id"])

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

    def test_invalid_model_output_is_502_and_keeps_the_case(self) -> None:
        TestStepsAgent.fake(['{"steps": [{"id": "only an id"}]}'])
        try:
            response = upload(self.client)
        finally:
            TestStepsAgent.stop_faking()
        self.assertEqual(response.status_code, 502)
        self.assertTrue(response.json()["detail"].startswith("case-"))

    def test_summary_endpoint(self) -> None:
        case_id = upload(self.client).json()["case_id"]
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


if __name__ == "__main__":
    unittest.main()
