"""Tests for media upload security: magic bytes, size limits, ownership, headers, and S3 presign."""

from __future__ import annotations

import struct
import zlib
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.services.storage import StorageAdapter


def _make_valid_png(width: int = 8, height: int = 6) -> bytes:
    """Create a minimal valid PNG binary with exact header signature and dimensions."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw_scanlines = b"".join(b"\x00" + (b"\x10\xb9\x81" * width) for _ in range(height))
    idat = zlib.compress(raw_scanlines)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _make_minimal_mp4() -> bytes:
    """Minimal ISO BMFF MP4 header with valid ftyp signature."""
    return b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + (b"\x00" * 32)


def test_secure_media_upload_preview_download_and_cross_user_isolation(
    client: TestClient, register_user: Callable[..., dict[str, Any]]
) -> None:
    _admin = register_user("admin@agrodrone.dev")
    owner = register_user("owner@agrodrone.dev", role="agronomist")
    other = register_user("other@agrodrone.dev", role="operator")
    viewer = register_user("viewer@agrodrone.dev", role="viewer")

    png_bytes = _make_valid_png(16, 12)

    # Viewer forbidden from uploading
    viewer_upload = client.post(
        "/api/v1/media/upload",
        headers=viewer["headers"],
        files={"file": ("field.png", png_bytes, "image/png")},
    )
    assert viewer_upload.status_code == 403

    # Owner uploads valid PNG with path-traversal filename attempt -> safely sanitized & UUID keyed
    upload = client.post(
        "/api/v1/media/upload",
        headers=owner["headers"],
        files={"file": ("../../malicious/../crop_row.png", png_bytes, "image/png")},
        data={"notes": "Row 4 inspection"},
    )
    assert upload.status_code == 201
    asset = upload.json()
    assert asset["media_type"] == "image"
    assert asset["mime_type"] == "image/png"
    assert asset["width_px"] == 16
    assert asset["height_px"] == 12
    assert asset["original_filename"] == "crop_row.png"
    assert ".." not in asset["storage_key"]
    assert asset["safe_filename"].endswith(".png")
    assert len(asset["sha256"]) == 64

    media_id = asset["id"]

    # Owner streams binary with strict non-executing security headers
    content_res = client.get(f"/api/v1/media/{media_id}/content", headers=owner["headers"])
    assert content_res.status_code == 200
    assert content_res.content == png_bytes
    assert content_res.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in content_res.headers["Content-Security-Policy"]
    assert "inline;" in content_res.headers["Content-Disposition"]

    dl_url = client.get(
        f"/api/v1/media/{media_id}/download-url?download=true",
        headers=owner["headers"],
    )
    assert dl_url.status_code == 200
    assert dl_url.json()["url"].endswith("?download=true")

    # Cross-user access strictly rejected
    assert client.get(f"/api/v1/media/{media_id}", headers=other["headers"]).status_code == 403
    assert client.get(f"/api/v1/media/{media_id}/content", headers=other["headers"]).status_code == 403
    assert client.get(f"/api/v1/media/{media_id}/download-url", headers=other["headers"]).status_code == 403
    assert client.delete(f"/api/v1/media/{media_id}", headers=other["headers"]).status_code == 403

    # MP4 video upload works too
    mp4_upload = client.post(
        "/api/v1/media/upload",
        headers=owner["headers"],
        files={"file": ("pass01.mp4", _make_minimal_mp4(), "video/mp4")},
    )
    assert mp4_upload.status_code == 201
    assert mp4_upload.json()["media_type"] == "video"

    # Delete removes DB row & binary cleanly
    deleted = client.delete(f"/api/v1/media/{media_id}", headers=owner["headers"])
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/media/{media_id}/content", headers=owner["headers"]).status_code == 404


def test_media_upload_rejects_spoofed_magic_bytes_disallowed_types_and_oversize(
    client: TestClient,
    test_settings: Settings,
    register_user: Callable[..., dict[str, Any]],
) -> None:
    admin = register_user("sec-admin@agrodrone.dev")

    # Spoofed HTML/script claiming to be PNG -> rejected by magic-byte check
    spoofed = client.post(
        "/api/v1/media/upload",
        headers=admin["headers"],
        files={"file": ("evil.png", b"<html><script>alert(1)</script></html>", "image/png")},
    )
    assert spoofed.status_code == 422
    assert "signature" in spoofed.json()["error"]["message"].lower()

    # SVG disallowed (XSS risk)
    svg = client.post(
        "/api/v1/media/upload",
        headers=admin["headers"],
        files={"file": ("vector.svg", b"<svg onload=alert(1)></svg>", "image/svg+xml")},
    )
    assert svg.status_code == 422

    # Oversized file rejected with 413
    test_settings.max_image_upload_bytes = 2048
    big_png = _make_valid_png(8, 8) + (b"\x00" * 4096)
    too_big = client.post(
        "/api/v1/media/upload",
        headers=admin["headers"],
        files={"file": ("huge.png", big_png, "image/png")},
    )
    assert too_big.status_code == 413
    assert too_big.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_s3_presigned_upload_and_download_adapter(test_settings: Settings) -> None:
    class _FakeS3Client:
        def generate_presigned_url(self, operation: str, Params: dict[str, Any], ExpiresIn: int) -> str:
            return f"https://minio.local/{Params['Bucket']}/{Params['Key']}?op={operation}&exp={ExpiresIn}"

    s3_settings = test_settings.model_copy(
        update={
            "storage_backend": "s3",
            "s3_endpoint_url": "http://minio:9000",
            "s3_access_key_id": "test-key",
            "s3_secret_access_key": "test-secret",
            "s3_bucket_media": "agrodrone-private",
        }
    )
    adapter = StorageAdapter(s3_settings, s3_client=_FakeS3Client())
    assert adapter.check_health().ready is True

    presigned_put = adapter.create_presigned_upload(
        storage_key="media/user-1/2026/11/abc.jpg",
        content_type="image/jpeg",
        byte_size=4096,
    )
    assert presigned_put.method == "PUT"
    assert "op=put_object" in presigned_put.url

    presigned_get, ttl = adapter.create_presigned_download_url(
        storage_key="media/user-1/2026/11/abc.jpg",
        filename="crop.jpg",
        as_attachment=True,
    )
    assert "op=get_object" in presigned_get
    assert ttl == s3_settings.s3_presign_expire_seconds
