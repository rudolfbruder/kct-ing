from __future__ import annotations


class ConversionError(Exception):
    """An evidence file could not be converted for the AI."""


class InvalidEvidenceError(ConversionError):
    """An uploaded evidence file is empty, of a type that is not accepted, or badly named."""
