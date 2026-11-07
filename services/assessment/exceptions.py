from __future__ import annotations


class AssessmentFailedError(Exception):
    """An assessment could not run, or ended as failed (the reason is stored with it)."""
