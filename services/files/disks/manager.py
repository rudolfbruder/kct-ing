"""Builds the disk for KCT_FILES_DRIVER: "local" or "gcs".

The GCS driver is imported only when used, so local mode does not need
google-cloud-storage installed.
"""
from __future__ import annotations

from typing import Optional

from services.config import Settings, settings
from services.files.disks.base import Disk
from services.files.exceptions import FilesConfigurationError


def disk(config: Optional[Settings] = None) -> Disk:
    config = config or settings()
    if config.files_driver == "local":
        from services.files.disks.local import LocalDisk

        return LocalDisk(config.storage_root)
    if config.files_driver == "gcs":
        if not config.gcs_bucket:
            raise FilesConfigurationError("KCT_FILES_DRIVER=gcs needs KCT_GCS_BUCKET")
        from services.files.disks.gcs import GcsDisk

        return GcsDisk(config.gcs_bucket, config.gcs_prefix, config.gcp_project)
    raise FilesConfigurationError(f"Unknown files driver {config.files_driver!r}")
