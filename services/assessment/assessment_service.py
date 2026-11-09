"""AssessmentService: judge a case's evidence against its test steps.

    kct.assessments.assess("case-002")                 run now, wait (notebooks)
    meta = kct.assessments.start("case-002")           API: create the run ...
    kct.assessments.run(meta.assessment_id)            ... and run it in the background
    kct.assessments.find(assessment_id)                progress while running, everything after

A run:
    1. takes the case's newest interpretation (or a chosen one): its test steps;
    2. converts and splits the case's evidence into parts (EvidenceService);
    3. LOOP: one EvidenceAssessmentAgent call per part, with the control details and
       test plan PDFs, all test steps and the part. Findings are checked against the
       evidence sent (ReferenceChecker) and saved after every part, so progress
       shows while it runs. A failing part is recorded and the loop goes on;
    4. one VerdictAgent call combines all findings into effective / not_effective per
       test step; a step the model leaves out gets not_effective, flagged as fallback;
    5. saves the verdicts (and each test step's status) and writes the read-only PDF
       report to outputs/<case>/assessment_<id>.pdf, with its SHA-256 in the database.

Each run is a new assessment; earlier runs stay.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional

from services.ai.agent import Agent
from services.ai.exceptions import AiError
from services.assessment.agents.evidence_assessment_agent import EvidenceAssessmentAgent
from services.assessment.agents.verdict_agent import VerdictAgent
from services.assessment.data import (
    AssessedPart,
    Assessment,
    AssessmentMetadata,
    CheckedStepFinding,
    StepVerdict,
)
from services.assessment.exceptions import AssessmentFailedError
from services.assessment.references import ReferenceChecker, check_all
from services.assessment.report import AssessmentReport
from services.config import settings
from services.control_testing.data import CaseInterpretation, DocumentKind, TestStep
from services.evidences.evidence_service import EvidenceService
from services.files.exceptions import CaseNotFoundError
from services.files.file_service import FileService

log = logging.getLogger("kct")

Progress = Optional[Callable[[str], None]]


class AssessmentService:
    def __init__(self, files: FileService, database, evidences: EvidenceService) -> None:
        self.files = files
        self.database = database
        self.evidences = evidences

    # --- public ----------------------------------------------------------------------

    def start(self, case_id: str, case_interpretation_id: Optional[str] = None) -> AssessmentMetadata:
        """Create a queued assessment for the case. Nothing is sent to the model yet."""
        if case_id not in self.files.case_ids():
            raise CaseNotFoundError(f"Unknown case {case_id}")
        interpretation = (self.database.find_interpretation(case_interpretation_id) if case_interpretation_id
                          else self.database.latest_interpretation(case_id))
        if interpretation.metadata.case_reference != case_id:
            raise CaseNotFoundError(f"Interpretation {case_interpretation_id} does not belong to {case_id}")
        config = settings()
        metadata = AssessmentMetadata(
            assessment_id=str(uuid.uuid4()),
            case_id=interpretation.metadata.case_id,
            case_reference=case_id,
            case_interpretation_id=interpretation.metadata.case_interpretation_id,
            status="queued",
            provider=EvidenceAssessmentAgent.provider or config.ai_provider,
            model=EvidenceAssessmentAgent.model or Agent._default_model(config.ai_provider),
            created_at=_now(),
        )
        self.database.create_assessment(metadata)
        log.info("%s: assessment %s queued", case_id, metadata.assessment_id)
        return metadata

    def run(self, assessment_id: str, progress: Progress = None) -> Assessment:
        """Run a queued assessment to the end. Never raises for a failed run: it is stored as failed."""
        say = progress or (lambda message: None)
        metadata = self.database.find_assessment(assessment_id).metadata
        if metadata.status != "queued":
            raise AssessmentFailedError(f"Assessment {assessment_id} is {metadata.status}, not queued")
        self.database.update_assessment(assessment_id, status="running")
        try:
            self._run(metadata, say)
        except Exception as exc:  # stored, so the API and the notebook can show it
            log.exception("%s: assessment %s failed", metadata.case_reference, assessment_id)
            self.database.update_assessment(assessment_id, status="failed", finished_at=_now(),
                                            error=f"{type(exc).__name__}: {exc}")
            say(f"❌ failed: {exc}")
        return self.database.find_assessment(assessment_id)

    def assess(self, case_id: str, case_interpretation_id: Optional[str] = None, progress: Progress = None) -> Assessment:
        """start() and run() in one go; raises AssessmentFailedError when the run fails."""
        result = self.run(self.start(case_id, case_interpretation_id).assessment_id, progress)
        if result.metadata.status == "failed":
            raise AssessmentFailedError(result.metadata.error or "assessment failed")
        return result

    def find(self, assessment_id: str) -> Assessment:
        return self.database.find_assessment(assessment_id)

    def index(self, case_id: Optional[str] = None) -> List[AssessmentMetadata]:
        return self.database.assessments(case_id)

    def report(self, assessment_id: str) -> bytes:
        metadata = self.find(assessment_id).metadata
        if metadata.status != "completed" or not metadata.report_path:
            raise CaseNotFoundError(f"Assessment {assessment_id} has no report yet (status {metadata.status})")
        return self.files.read(metadata.report_path)

    # --- the run -----------------------------------------------------------------------

    def _run(self, metadata: AssessmentMetadata, say) -> None:
        case = metadata.case_reference
        interpretation = self.database.find_interpretation(metadata.case_interpretation_id)
        steps = interpretation.test_steps
        context = (self.files.documents(case, DocumentKind.CONTROL_DETAILS)
                   + self.files.documents(case, DocumentKind.TEST_PLAN))
        evidence = self.evidences.case(case)

        say(f"{case}: {len(steps)} test steps; converting and splitting the evidence ...")
        units = evidence.units()
        parts = evidence.parts(units)
        hashes = {str(u.path): _sha256(evidence.path(u.path).read_bytes()) for u in units}
        self.database.update_assessment(metadata.assessment_id, parts_total=len(parts))
        say(f"{len(units)} evidence file(s), {len(parts)} part(s) to assess")

        steps_json = json.dumps([_step_for_prompt(s) for s in steps], ensure_ascii=False, indent=1)
        known = {s.reference for s in steps}
        assessed: List[AssessedPart] = []
        self._sent_documents = [p.documents for p in parts]   # for checking the verdicts' references
        done = failed = 0
        for position, part in enumerate(parts, start=1):
            say(f"[{position}/{len(parts)}] {part.label} (~{part.estimated_tokens:,} tokens) ...")
            record = AssessedPart(
                id=str(uuid.uuid4()), position=position, unit=part.unit, unit_sha256=hashes.get(part.unit, ""),
                part_number=part.number, part_total=part.total, label=part.label,
                documents=[d.title for d in part.documents], estimated_tokens=part.estimated_tokens,
                status="assessed",
            )
            try:
                response = EvidenceAssessmentAgent().prompt(
                    _part_prompt(case, part, steps_json), attachments=context + part.documents)
                findings = [f for f in response.structured.findings if f.step_reference in known]
                unknown = {f.step_reference for f in response.structured.findings} - known
                if unknown:
                    log.warning("%s: %s named unknown test steps %s", case, part.label, sorted(unknown))
                record.findings = check_all(findings, part.documents)
                record.input_tokens = response.usage.input_tokens
                record.output_tokens = response.usage.output_tokens
                done += 1
                problems = sum(len(f.reference_problems) for f in record.findings)
                say(f"    ✅ {sum(f.relevance != 'not_relevant' for f in record.findings)} relevant step(s)"
                    + (f", {problems} reference problem(s)" if problems else ""))
            except AiError as exc:
                record.status, record.error = "failed", f"{type(exc).__name__}: {exc}"
                failed += 1
                say(f"    ❌ {record.error}")
            self.database.save_part(metadata.assessment_id, record)
            self.database.update_assessment(metadata.assessment_id, parts_done=done, parts_failed=failed)
            assessed.append(record)

        say("Combining the findings into one verdict per test step ...")
        verdicts = self._verdicts(steps, assessed)
        self.database.save_verdicts(metadata.assessment_id, verdicts)

        result = self.database.find_assessment(metadata.assessment_id)
        result.metadata.finished_at = _now()
        pdf = AssessmentReport(result, interpretation, self.files.case_name(case)).build()
        path = self.files.save_output(case, f"assessment_{metadata.assessment_id}.pdf", pdf)
        self.database.update_assessment(metadata.assessment_id, status="completed", finished_at=result.metadata.finished_at,
                                        report_path=path, report_sha256=_sha256(pdf))
        effective = sum(v.verdict == "effective" for v in verdicts)
        say(f"✅ {effective} effective, {len(verdicts) - effective} not effective; report: {path}")
        log.info("%s: assessment %s completed: %d effective, %d not effective, %d part(s) failed",
                 case, metadata.assessment_id, effective, len(verdicts) - effective, failed)

    def _verdicts(self, steps: List[TestStep], parts: List[AssessedPart]) -> List[StepVerdict]:
        assessed = [p for p in parts if p.status == "assessed"]
        if not assessed:
            reason = ("No evidence files are uploaded for this case." if not parts else
                      "None of the evidence could be assessed (see the failed parts).")
            return [_fallback(s, reason, no_evidence=not parts) for s in steps]

        answer = VerdictAgent().prompt(_verdict_prompt(steps, parts)).structured
        by_reference = {v.step_reference: v for v in answer.verdicts}
        checker = ReferenceChecker([d for p in self._sent_documents for d in p])
        verdicts = []
        for step in steps:
            given = by_reference.get(step.reference)
            if given is None:
                relevant = any(f.step_reference == step.reference and f.relevance != "not_relevant"
                               for p in assessed for f in p.findings)
                verdicts.append(_fallback(step, "The model gave no verdict for this step.", no_evidence=not relevant))
                continue
            refs = list(given.references) + [e.reference for e in given.exceptions if e.reference]
            problems = list(dict.fromkeys(p for p in (checker.problem(r) for r in refs) if p))
            verdicts.append(StepVerdict(
                id=str(uuid.uuid4()), test_step_id=step.id, step_reference=step.reference, title=step.title,
                verdict=given.verdict, no_evidence=given.no_evidence, reason=given.reason,
                exceptions=given.exceptions, references=given.references, reference_problems=problems,
            ))
        return verdicts


# --- prompts -----------------------------------------------------------------------------

def _step_for_prompt(step: TestStep) -> dict:
    return {"reference": step.reference, "title": step.title, "description": step.description,
            "acceptance_criteria": step.acceptance_criteria, "refusal_criteria": step.refusal_criteria}


def _part_prompt(case: str, part, steps_json: str) -> str:
    documents = "\n".join(f"- {d.title}" for d in part.documents)
    return (
        f"Case: {case}\n"
        f"Evidence: {part.label}\n"
        f"Evidence documents in this request (cite these titles exactly):\n{documents}\n\n"
        f"Test steps (JSON):\n{steps_json}\n\n"
        "Record what this evidence shows for every test step."
    )


def _verdict_prompt(steps: List[TestStep], parts: List[AssessedPart]) -> str:
    findings = [
        {"evidence": p.label, "status": p.status, "error": p.error,
         "findings": [f.model_dump(exclude_defaults=False) for f in p.findings]}
        for p in parts
    ]
    return (
        f"Test steps (JSON):\n{json.dumps([_step_for_prompt(s) for s in steps], ensure_ascii=False, indent=1)}\n\n"
        f"Findings per evidence part (JSON):\n{json.dumps(findings, ensure_ascii=False, indent=1)}\n\n"
        "Decide every test step."
    )


# --- helpers -----------------------------------------------------------------------------

def _fallback(step: TestStep, reason: str, no_evidence: bool) -> StepVerdict:
    return StepVerdict(id=str(uuid.uuid4()), test_step_id=step.id, step_reference=step.reference, title=step.title,
                       verdict="not_effective", no_evidence=no_evidence, reason=reason, fallback=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
