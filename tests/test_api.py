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
        saved = json.loads((outputs / f"case_interpretation_{interpretation_id}.json").read_text())
        self.assertEqual(saved, body)
        self.assertTrue((outputs / "control_details_summary.md").is_file())
        self.assertTrue((outputs / "test_plan_summary.md").is_file())
        self.assertTrue((STORAGE / "database.sqlite").is_file())

        calls = [json.loads(line) for line in (STORAGE / "logs" / "agents.log").read_text().splitlines()]
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


if __name__ == "__main__":
    unittest.main()
