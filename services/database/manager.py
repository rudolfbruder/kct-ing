"""Builds the repository for KCT_DB_DRIVER (Laravel: DatabaseManager).

Drivers are imported only when used, so SQLite runs without
google-cloud-bigquery installed.
"""
from __future__ import annotations

from typing import Optional

from services.config import Settings, settings
from services.database.contracts import CaseInterpretationRepository
from services.database.exceptions import DatabaseConfigurationError


def repository(config: Optional[Settings] = None) -> CaseInterpretationRepository:
    config = config or settings()
    if config.db_driver == "sqlite":
        from services.database.drivers.sqlite import SqliteRepository

        return SqliteRepository(config.db_path)
    if config.db_driver == "bigquery":
        from services.database.drivers.bigquery import BigQueryRepository

        return BigQueryRepository(config.bq_dataset, config.gcp_project, config.bq_location)
    raise DatabaseConfigurationError(f"Unknown database driver {config.db_driver!r}")
