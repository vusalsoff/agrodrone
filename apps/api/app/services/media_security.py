"""Upload security validation: allow-list, magic-byte signatures, safe filenames, dimensions."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.core.exceptions import PayloadTooLargeError, ValidationAppError

ALLOWED_MEDIA_SPECS: dict[str, dict[str, object]] = {
    "image/jpeg": {"media_type": "image", "ext": ".jpg", "aliases": {".jpg", ".jpeg"}},
    "image/png": {"media_type": "image", "ext": ".png", "aliases": {".png"}},
    "image/webp": {"media_type": "image", "ext": ".webp", "aliases": {".webp"}},
    "video/mp4": {"media_type": "video", "ext": ".mp4", "aliases": {".mp4"}},
    "video/webm": {"media_type": "video", "ext": ".webm", "aliases": {".webm"}},
    "video/quicktime": {"media_type": "video", "ext": ".mov", "aliases": {".mov"}},
}

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ValidatedUploadMeta:
    media_type: str
    mime_type: str
    canonical_extension: str
    safe_filename: str
    sanitized_original_name: str
    width_px: int | None
    height_px: int | None


def sanitize_original_filename(filename: str | None) -> str:
    """Strip directory components and unsafe control characters for display metadata."""
    base = Path(filename or "upload.bin").name
    cleaned = _FILENAME_SAFE_RE.sub("_", base).strip("._")
    return (cleaned or "upload")[:180]


def detect_mime_from_magic_bytes(header: bytes) -> str | None:
    """Verify actual binary file signature from leading header bytes."""
    if len(header) < 12:
        return None

    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    # JPEG: FF D8 FF
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    # WebP: RIFF....WEBP
    if header[0:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"

    # WebM / Matroska EBML header: 1A 45 DF A3
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"

    # ISO Base Media File Format (MP4 / QuickTime MOV): ....ftyp<brand>
    if header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand == b"qt  ":
            return "video/quicktime"
        return "video/mp4"

    return None


def extract_image_dimensions(mime_type: str, data: bytes) -> tuple[int | None, int | None]:
    """Safely parse pixel dimensions from PNG/JPEG/WebP headers without executing decoders."""
    try:
        if mime_type == "image/png" and len(data) >= 24:
            width, height = struct.unpack(">II", data[16:24])
            return int(width), int(height)

        if mime_type == "image/jpeg" and data.startswith(b"\xff\xd8"):
            idx = 2
            length = len(data)
            while idx + 4 < length:
                if data[idx] != 0xFF:
                    idx += 1
                    continue
                marker = data[idx + 1]
                idx += 2
                if marker in (0xD8, 0xD9, 0x01) or (0xD0 <= marker <= 0xD7):
                    continue
                if idx + 2 > length:
                    break
                seg_len = struct.unpack(">H", data[idx : idx + 2])[0]
                if seg_len < 2 or idx + seg_len > length:
                    break
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
                    if idx + 7 <= length:
                        height, width = struct.unpack(">HH", data[idx + 3 : idx + 7])
                        return int(width), int(height)
                    break
                idx += seg_len

        if mime_type == "image/webp" and len(data) >= 30:
            chunk_type = data[12:16]
            if chunk_type == b"VP8X":
                w = 1 + int.from_bytes(data[24:27], "little")
                h = 1 + int.from_bytes(data[27:30], "little")
                return w, h
            if chunk_type == b"VP8 " and len(data) >= 30:
                w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
                h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
                return int(w), int(h)
            if chunk_type == b"VP8L" and len(data) >= 25:
                bits = struct.unpack("<I", data[21:25])[0]
                w = (bits & 0x3FFF) + 1
                h = ((bits >> 14) & 0x3FFF) + 1
                return int(w), int(h)
    except Exception:
        return None, None
    return None, None


def validate_declared_upload(
    *,
    filename: str | None,
    declared_mime: str | None,
    byte_size: int | None,
    settings: Settings,
) -> tuple[str, str, str]:
    """Validate filename extension, declared MIME type, and size limit prior to presign/upload."""
    normalized_mime = (declared_mime or "").split(";")[0].strip().lower()
    if normalized_mime not in ALLOWED_MEDIA_SPECS:
        raise ValidationAppError(
            f"Unsupported media type '{normalized_mime or 'unknown'}'. "
            f"Allowed types: {', '.join(sorted(ALLOWED_MEDIA_SPECS.keys()))}."
        )

    spec = ALLOWED_MEDIA_SPECS[normalized_mime]
    media_type = str(spec["media_type"])
    canonical_ext = str(spec["ext"])
    allowed_exts = spec["aliases"]
    assert isinstance(allowed_exts, set)

    ext = Path(filename or "").suffix.lower()
    if ext and ext not in allowed_exts:
        raise ValidationAppError(
            f"File extension '{ext}' does not match declared content type '{normalized_mime}'."
        )

    max_bytes = (
        settings.max_image_upload_bytes
        if media_type == "image"
        else settings.max_video_upload_bytes
    )
    if byte_size is not None:
        if byte_size <= 0:
            raise ValidationAppError("Uploaded file must not be empty.")
        if byte_size > max_bytes:
            raise PayloadTooLargeError(
                f"File exceeds the maximum allowed size for {media_type} uploads ({max_bytes} bytes)."
            )

    return media_type, normalized_mime, canonical_ext


def validate_uploaded_bytes(
    *,
    filename: str | None,
    declared_mime: str | None,
    content: bytes,
    settings: Settings,
) -> ValidatedUploadMeta:
    """Validate binary magic-bytes, declared MIME alignment, size limits, and safe filename."""
    media_type, normalized_mime, canonical_ext = validate_declared_upload(
        filename=filename,
        declared_mime=declared_mime,
        byte_size=len(content),
        settings=settings,
    )

    detected_mime = detect_mime_from_magic_bytes(content[:32])
    if detected_mime is None:
        raise ValidationAppError(
            "File signature verification failed: unrecognized or potentially unsafe binary header."
        )

    # Allow MP4/MOV ISO container family interchangeability while blocking cross-type spoofing.
    iso_video_pair = {"video/mp4", "video/quicktime"}
    if detected_mime != normalized_mime and not (
        detected_mime in iso_video_pair and normalized_mime in iso_video_pair
    ):
        raise ValidationAppError(
            f"File signature mismatch: declared '{normalized_mime}' but binary content is '{detected_mime}'."
        )

    canonical_mime = detected_mime
    canonical_spec = ALLOWED_MEDIA_SPECS[canonical_mime]
    canonical_ext = str(canonical_spec["ext"])
    media_type = str(canonical_spec["media_type"])

    safe_name = f"{uuid4().hex}{canonical_ext}"
    width_px, height_px = (
        extract_image_dimensions(canonical_mime, content)
        if media_type == "image"
        else (None, None)
    )

    return ValidatedUploadMeta(
        media_type=media_type,
        mime_type=canonical_mime,
        canonical_extension=canonical_ext,
        safe_filename=safe_name,
        sanitized_original_name=sanitize_original_filename(filename),
        width_px=width_px,
        height_px=height_px,
    )
