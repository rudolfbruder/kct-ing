from __future__ import annotations


class DatabaseConfigurationError(Exception):
    """KCT_DB_DRIVER is unknown, or the driver is missing its settings."""


class RecordNotFoundError(LookupError):
    """The record asked for does not exist."""
