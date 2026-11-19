"""Deterministic media fixtures for AgroVision tests (no network, no randomness)."""

from __future__ import annotations

import io
import struct
import tempfile
import zlib
from pathlib import Path

import numpy as np


def make_png(width: int = 64, height: int = 48, rgb: tuple[int, int, int] = (16, 185, 129)) -> bytes:
    def _chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width
    idat = zlib.compress(row * height)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def make_corrupt_png() -> bytes:
    """Valid PNG signature (passes upload magic-byte check) but undecodable body."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + b"\xff" * 64


def make_jpeg(width: int = 96, height: int = 64) -> bytes:
    from PIL import Image

    img = Image.new("RGB", (width, height), (40, 120, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def make_mp4(seconds: float = 3.0, fps: int = 10, width: int = 160, height: int = 120) -> bytes:
    """Encode a small deterministic MP4 (mp4v) with OpenCV; frame brightness encodes its index."""
    import cv2

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "clip.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        assert writer.isOpened(), "OpenCV VideoWriter (mp4v) unavailable"
        total = int(round(seconds * fps))
        for i in range(total):
            frame = np.full((height, width, 3), (i * 7) % 255, dtype=np.uint8)
            cv2.rectangle(frame, (10 + i, 10), (60 + i, 60), (16, 185, 129), -1)
            writer.write(frame)
        writer.release()
        return path.read_bytes()
