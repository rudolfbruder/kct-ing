"""What every file storage disk must offer (Laravel: Storage::disk()).

Paths are relative and use "/" (uploads/case-001/test_plan/tp.pdf), so the
same FileService code works on the workbench disk and in a GCS bucket.
"""
from __future__ import annotations

from typing import List, Protocol


class Disk(Protocol):
    def put(self, path: str, data: bytes, only_if_missing: bool = False) -> bool:
        """Writes the file. With only_if_missing, returns False instead of overwriting."""
        ...

    def get(self, path: str) -> bytes:
        """Raises FileNotFoundError when the file does not exist."""
        ...

    def files(self, directory: str) -> List[str]:
        """Names of the files directly in a directory, sorted. Empty when it does not exist."""
        ...

    def directories(self, directory: str) -> List[str]:
        """Names of the subdirectories of a directory, sorted."""
        ...
