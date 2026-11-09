"""The report carries the brand: logo when the file is there, wordmark otherwise."""
from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.assessment.data import Assessment, AssessmentMetadata, StepVerdict
from services.assessment.report import AssessmentReport
from services.branding import brand
from services.config import settings
from services.control_testing.data import CaseInterpretation, CaseInterpretationMetadata, TestStep


def sample():
    meta = AssessmentMetadata(assessment_id="a", case_id="c", case_reference="case-1", case_interpretation_id="i",
                              status="completed", provider="fake", model="fake", created_at="2026-11-07T00:00:00+00:00")
    step = TestStep(id="s", case_interpretation_id="i", case_id="c", reference="0472-01", title="T", description="D",
                    acceptance_criteria=["ok"], refusal_criteria=["not ok"], status="effective")
    interpretation = CaseInterpretation(
        metadata=CaseInterpretationMetadata(case_interpretation_id="i", case_id="c", case_reference="case-1",
                                            provider="fake", model="fake", created_at="2026-11-07", step_count=1),
        summaries={}, test_steps=[step])
    verdict = StepVerdict(id="v", test_step_id="s", step_reference="0472-01", title="T", verdict="effective",
                          no_evidence=False, reason="R")
    return Assessment(metadata=meta, verdicts=[verdict]), interpretation


def placeholder_logo() -> Path:
    from PIL import Image

    path = Path(tempfile.mkdtemp(prefix="kct-brand-")) / "logo.png"
    Image.new("RGBA", (300, 90), (255, 98, 0, 255)).save(path)
    return path


class BrandingTest(unittest.TestCase):
    def with_logo(self, logo: Path):
        config = dataclasses.replace(settings(), brand_logo=logo)
        return mock.patch("services.branding.settings", return_value=config)

    def test_brand_colours_and_missing_logo(self) -> None:
        with self.with_logo(Path("/nowhere/logo.png")):
            b = brand()
        self.assertEqual((b.orange, b.navy), ("#FF6200", "#000066"))
        self.assertIsNone(b.logo)

    def test_report_uses_the_logo_when_it_is_there(self) -> None:
        assessment, interpretation = sample()
        with self.with_logo(Path("/nowhere/logo.png")):
            without = AssessmentReport(assessment, interpretation).build()
        with self.with_logo(placeholder_logo()):
            with_logo = AssessmentReport(assessment, interpretation).build()
        self.assertTrue(without.startswith(b"%PDF") and with_logo.startswith(b"%PDF"))
        self.assertGreater(with_logo.count(b"/Subtype /Image"), without.count(b"/Subtype /Image"))


if __name__ == "__main__":
    unittest.main()
