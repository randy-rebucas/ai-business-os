"""Object storage boundary (ADR-011). Original documents are private; the API streams them after authorization.

- `local` (development): files under ABOS_STORAGE_DIR. Keys are generated server-side and validated, so no
  user-supplied name ever becomes part of a filesystem path.
- `s3` (production): any S3-compatible bucket via boto3 (install separately). Not exercised in tests yet —
  only the local adapter is verified (docs/STATUS.md).
"""

import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from abos.core.config import get_settings

_KEY = re.compile(r"^[0-9a-f-]{36}/([0-9a-f-]{36}/v\d+|exports/[0-9a-f-]{36}\.zip|branding/[0-9a-f-]{36}\.png)$")


def object_key(org_id: uuid.UUID, document_id: uuid.UUID, version_no: int) -> str:
    return f"{org_id}/{document_id}/v{version_no}"


def export_key(org_id: uuid.UUID, export_id: uuid.UUID) -> str:
    return f"{org_id}/exports/{export_id}.zip"


def branding_key(org_id: uuid.UUID, file_id: uuid.UUID) -> str:
    return f"{org_id}/branding/{file_id}.png"


class Storage(Protocol):
    name: str

    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    name = "local"

    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):
            raise ValueError("invalid storage key")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("storage key escapes the storage root")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    name = "s3"

    def __init__(self, bucket: str, endpoint_url: str | None, region: str | None):
        try:
            import boto3  # noqa: PLC0415 — optional dependency
        except ImportError as exc:  # pragma: no cover - configuration error
            raise RuntimeError("ABOS_STORAGE_BACKEND=s3 needs `pip install boto3`") from exc
        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                               ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def get_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "s3":
        if not s.s3_bucket:
            raise RuntimeError("ABOS_STORAGE_BACKEND=s3 needs ABOS_S3_BUCKET")
        return S3Storage(s.s3_bucket, s.s3_endpoint_url, s.s3_region)
    return LocalStorage(s.storage_dir)
