"""Storage abstraction supporting local dev disk and private S3-compatible buckets (MinIO/AWS S3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError


@dataclass(frozen=True)
class StorageHealth:
    backend: str
    ready: bool
    detail: str


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    method: str
    headers: dict[str, str]
    expires_in_seconds: int


class StorageAdapter:
    """Secure media storage adapter enforcing canonical keys and private bucket access."""

    def __init__(self, settings: Settings, s3_client: Any | None = None) -> None:
        self._settings = settings
        self._s3_client = s3_client

    def build_storage_key(self, owner_id: str, safe_filename: str) -> str:
        """Build a non-guessable, path-traversal-proof object storage key."""
        now = datetime.now(UTC)
        clean_name = Path(safe_filename).name
        return f"media/{owner_id}/{now:%Y}/{now:%m}/{clean_name}"

    def _resolve_local_path(self, storage_key: str) -> Path:
        root = Path(self._settings.local_storage_path).resolve()
        candidate = (root / storage_key).resolve()
        if not candidate.is_relative_to(root):
            raise AppError(
                code="INVALID_STORAGE_KEY",
                message="Attempted path traversal outside storage root.",
                status_code=400,
            )
        return candidate

    def _get_s3_client(self) -> Any:
        if self._s3_client is not None:
            return self._s3_client
        try:
            import boto3  # type: ignore[import-not-found]
            from botocore.config import Config as BotoConfig  # type: ignore[import-not-found]
        except ImportError as exc:
            raise AppError(
                code="S3_DRIVER_MISSING",
                message="STORAGE_BACKEND=s3 requires optional dependency 'boto3' (`uv sync --extra s3`).",
                status_code=500,
            ) from exc

        self._s3_client = boto3.client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url or None,
            aws_access_key_id=self._settings.s3_access_key_id or None,
            aws_secret_access_key=self._settings.s3_secret_access_key or None,
            region_name=self._settings.s3_region,
            config=BotoConfig(signature_version="s3v4"),
        )
        return self._s3_client

    def check_health(self) -> StorageHealth:
        if self._settings.storage_backend == "local":
            root = Path(self._settings.local_storage_path)
            root.mkdir(parents=True, exist_ok=True)
            return StorageHealth(
                backend="local",
                ready=root.exists() and root.is_dir(),
                detail=f"Local filesystem storage active ({root.as_posix()}); private S3/MinIO supported via STORAGE_BACKEND=s3.",
            )

        configured = bool(
            self._settings.s3_endpoint_url
            and self._settings.s3_bucket_media
            and self._settings.s3_access_key_id
            and self._settings.s3_secret_access_key
        )
        return StorageHealth(
            backend="s3",
            ready=configured,
            detail=(
                f"Private S3-compatible bucket '{self._settings.s3_bucket_media}' configured at "
                f"{self._settings.s3_endpoint_url} with presigned access."
                if configured
                else "S3 backend selected but credentials or bucket are incomplete."
            ),
        )

    def put_bytes(self, storage_key: str, content: bytes, content_type: str) -> None:
        if self._settings.storage_backend == "local":
            target = self._resolve_local_path(storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return

        client = self._get_s3_client()
        client.put_object(
            Bucket=self._settings.s3_bucket_media,
            Key=storage_key,
            Body=content,
            ContentType=content_type,
        )

    def read_bytes(self, storage_key: str) -> bytes:
        if self._settings.storage_backend == "local":
            target = self._resolve_local_path(storage_key)
            if not target.exists():
                raise NotFoundError("Media binary")
            return target.read_bytes()

        client = self._get_s3_client()
        response = client.get_object(
            Bucket=self._settings.s3_bucket_media,
            Key=storage_key,
        )
        return bytes(response["Body"].read())

    def delete_object(self, storage_key: str) -> None:
        if self._settings.storage_backend == "local":
            target = self._resolve_local_path(storage_key)
            if target.exists():
                target.unlink()
            return

        client = self._get_s3_client()
        client.delete_object(
            Bucket=self._settings.s3_bucket_media,
            Key=storage_key,
        )

    def create_presigned_upload(
        self,
        *,
        storage_key: str,
        content_type: str,
        byte_size: int,
    ) -> PresignedUpload:
        """Create a time-limited presigned PUT URL for private S3/MinIO uploads."""
        if self._settings.storage_backend != "s3":
            raise AppError(
                code="PRESIGN_UNAVAILABLE_LOCAL",
                message="Direct S3 presigned uploads require STORAGE_BACKEND=s3; use multipart POST /api/v1/media/upload for local storage.",
                status_code=400,
            )

        client = self._get_s3_client()
        expires = self._settings.s3_presign_expire_seconds
        url = client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._settings.s3_bucket_media,
                "Key": storage_key,
                "ContentType": content_type,
                "ContentLength": byte_size,
            },
            ExpiresIn=expires,
        )
        return PresignedUpload(
            url=str(url),
            method="PUT",
            headers={"Content-Type": content_type},
            expires_in_seconds=expires,
        )

    def create_presigned_download_url(
        self,
        *,
        storage_key: str,
        filename: str,
        as_attachment: bool = False,
    ) -> tuple[str, int]:
        """Create a short-lived private S3/MinIO presigned GET URL."""
        client = self._get_s3_client()
        expires = self._settings.s3_presign_expire_seconds
        disposition = f'attachment; filename="{filename}"' if as_attachment else f'inline; filename="{filename}"'
        url = client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._settings.s3_bucket_media,
                "Key": storage_key,
                "ResponseContentDisposition": disposition,
            },
            ExpiresIn=expires,
        )
        return str(url), expires
