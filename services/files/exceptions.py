from __future__ import annotations


class InvalidUploadError(ValueError):
    """An uploaded file is missing or is not a PDF."""


class CaseNotFoundError(LookupError):
    """The case, or the file asked for within it, does not exist."""
