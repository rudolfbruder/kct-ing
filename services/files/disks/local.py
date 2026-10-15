"""Files on the local disk, under KCT_STORAGE_ROOT."""
from __future__ import annotations

from pathlib import Path
from typing import List


class LocalDisk:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def put(self, path: str, data: bytes, only_if_missing: bool = False) -> bool:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(target, "xb" if only_if_missing else "wb") as file:
                file.write(data)
        except FileExistsError:
            return False
        return True

    def get(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    def files(self, directory: str) -> List[str]:
        folder = self.root / directory
        if not folder.is_dir():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_file())

    def directories(self, directory: str) -> List[str]:
        folder = self.root / directory
        if not folder.is_dir():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_dir())
