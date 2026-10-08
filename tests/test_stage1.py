"""Tests that need neither credentials nor network.

    pip install pytest
    pytest -q
"""
from __future__ import annotations

import pytest

from kct import prompts, storage
from kct.models import DocumentKind
from kct.services import summarize


def test_case_id_rejects_traversal():
    for bad in ["../etc", "case 001", "/abs", "CASE-001", "a"]:
        with pytest.raises(ValueError):
            storage.validate_case_id(bad)


def test_case_id_accepts_convention():
    assert storage.validate_case_id("case-001") == "case-001"


def test_fixture_case_present():
    assert "case-001" in storage.list_cases()


@pytest.mark.parametrize(
    "kind", [DocumentKind.CONTROL_DETAILS, DocumentKind.TEST_PLAN]
)
def test_source_files_are_pdfs(kind):
    files = storage.source_files("case-001", kind)
    assert files, f"no files for {kind.value}"
    for f in files:
        assert f.mime_type == "application/pdf"
        assert len(f.sha256) == 64
        assert f.size_bytes > 0


def test_source_files_are_sorted():
    files = storage.source_files("case-001", DocumentKind.CONTROL_DETAILS)
    assert [f.relative_path for f in files] == sorted(f.relative_path for f in files)


def test_manifest_reads():
    manifest = storage.read_manifest("case-001")
    assert manifest.case_id == "case-001"
    assert manifest.process_id == "PRC-IAM-014"


def test_prompts_exist_for_both_kinds():
    available = prompts.available()
    assert "summarize_control_details" in available
    assert "summarize_test_plan" in available


def test_prompt_version_pinning():
    latest = prompts.load("summarize_test_plan")
    pinned = prompts.load("summarize_test_plan", "v1")
    assert pinned.version == "v1"
    assert pinned.sha256 == latest.sha256 or latest.version != "v1"
    with pytest.raises(prompts.PromptNotFound):
        prompts.load("summarize_test_plan", "v99")


def test_evidence_is_not_a_stage1_kind():
    with pytest.raises(ValueError):
        summarize.run("case-001", DocumentKind.EVIDENCE)


def test_missing_case_raises():
    with pytest.raises(storage.CaseNotFound):
        storage.source_files("case-999", DocumentKind.TEST_PLAN)
