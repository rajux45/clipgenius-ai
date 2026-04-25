"""S3 storage service. Falls back to local filesystem if S3 isn't configured."""
from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.client import Config

from ..config import settings

log = logging.getLogger(__name__)

_LOCAL_ROOT = Path(os.environ.get("LOCAL_STORAGE_DIR", "/tmp/clipgenius_storage"))


class StorageBackend:
    """Abstracts away S3 vs local file storage so dev can run without AWS."""

    def __init__(self) -> None:
        self.bucket = settings.aws_s3_bucket
        self.use_s3 = bool(settings.aws_access_key_id and settings.aws_secret_access_key and self.bucket)
        if self.use_s3:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
                config=Config(signature_version="s3v4"),
            )
        else:
            _LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
            log.warning("S3 not configured; using local storage at %s", _LOCAL_ROOT)

    # --- key helpers ---
    @staticmethod
    def make_key(*parts: str, suffix: str = "") -> str:
        base = "/".join(p.strip("/") for p in parts if p)
        if suffix and not base.endswith(suffix):
            base = f"{base}{suffix}"
        return base

    @staticmethod
    def random_key(prefix: str, suffix: str = "") -> str:
        return f"{prefix.strip('/')}/{uuid.uuid4().hex}{suffix}"

    # --- upload / download ---
    def upload_file(self, local_path: str | Path, key: str, content_type: str | None = None) -> str:
        local_path = str(local_path)
        if self.use_s3:
            extra = {"ContentType": content_type} if content_type else {}
            self._client.upload_file(local_path, self.bucket, key, ExtraArgs=extra)
            return key
        dest = _LOCAL_ROOT / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, dest)
        return key

    def upload_fileobj(self, fileobj: BinaryIO, key: str, content_type: str | None = None) -> str:
        if self.use_s3:
            extra = {"ContentType": content_type} if content_type else {}
            self._client.upload_fileobj(fileobj, self.bucket, key, ExtraArgs=extra)
            return key
        dest = _LOCAL_ROOT / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as out:
            shutil.copyfileobj(fileobj, out)
        return key

    def download_file(self, key: str, local_path: str | Path) -> str:
        local_path = str(local_path)
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        if self.use_s3:
            self._client.download_file(self.bucket, key, local_path)
            return local_path
        src = _LOCAL_ROOT / key
        shutil.copyfile(src, local_path)
        return local_path

    def presigned_get_url(self, key: str, expires_in: int = 60 * 60) -> str:
        if self.use_s3:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        # In local dev, served via FastAPI route
        return f"/api/v1/files/{key}"

    def public_url(self, key: str) -> str:
        if settings.s3_public_base_url:
            return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
        return self.presigned_get_url(key)

    def local_path_for(self, key: str) -> Path:
        """For local backend only — returns the on-disk path."""
        return _LOCAL_ROOT / key


storage = StorageBackend()
