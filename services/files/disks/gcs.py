"""Files in a Google Cloud Storage bucket, under an optional prefix.

GCS has no real folders: "directories" are the shared prefixes of object
names, the way the Cloud Console shows them.
"""
from __future__ import annotations

from typing import List

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage


class GcsDisk:
    def __init__(self, bucket: str, prefix: str = "", project: str = "") -> None:
        self.client = storage.Client(project=project or None)
        self.bucket = self.client.bucket(bucket)
        self.prefix = prefix.strip("/")

    def put(self, path: str, data: bytes, only_if_missing: bool = False) -> bool:
        blob = self.bucket.blob(self._key(path))
        try:
            # if_generation_match=0: the write succeeds only if no object exists yet.
            blob.upload_from_string(data, if_generation_match=0 if only_if_missing else None)
        except PreconditionFailed:
            return False
        return True

    def get(self, path: str) -> bytes:
        try:
            return self.bucket.blob(self._key(path)).download_as_bytes()
        except NotFound as exc:
            raise FileNotFoundError(path) from exc

    def files(self, directory: str) -> List[str]:
        prefix = self._key(directory) + "/"
        blobs = self.client.list_blobs(self.bucket, prefix=prefix, delimiter="/")
        return sorted(b.name[len(prefix):] for b in blobs if b.name != prefix)

    def directories(self, directory: str) -> List[str]:
        prefix = self._key(directory) + "/"
        blobs = self.client.list_blobs(self.bucket, prefix=prefix, delimiter="/")
        for _ in blobs:  # prefixes are filled in while the listing is read
            pass
        return sorted(p[len(prefix):].rstrip("/") for p in blobs.prefixes)

    def _key(self, path: str) -> str:
        path = path.strip("/")
        return f"{self.prefix}/{path}" if self.prefix else path
