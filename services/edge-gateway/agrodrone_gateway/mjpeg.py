"""Bounded streaming MJPEG frame parser & JPEG validator for ESP32-CAM OV2640."""

from __future__ import annotations

from collections.abc import Iterator

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


class FrameValidationError(Exception):
    """Raised when an incoming stream frame violates JPEG structure or size limits."""


def validate_jpeg_frame(frame: bytes, *, max_frame_bytes: int) -> bytes:
    """Verify JPEG SOI/EOI markers and enforce bounded frame size."""
    if not frame:
        raise FrameValidationError("Empty frame.")
    if len(frame) > max_frame_bytes:
        raise FrameValidationError(
            f"Frame size ({len(frame)} bytes) exceeds max_frame_bytes ({max_frame_bytes})."
        )
    if not frame.startswith(b"\xff\xd8\xff"):
        raise FrameValidationError("Frame missing valid JPEG SOI signature.")
    if not frame.endswith(JPEG_EOI):
        raise FrameValidationError("Frame missing valid JPEG EOI marker.")
    return frame


def iter_mjpeg_frames(
    chunks: Iterator[bytes],
    *,
    max_frame_bytes: int = 512 * 1024,
) -> Iterator[bytes]:
    """Extract validated JPEG frames from a raw MJPEG byte stream with bounded buffering."""
    buf = bytearray()
    max_buf_bytes = max_frame_bytes * 2

    for chunk in chunks:
        if not chunk:
            continue
        buf.extend(chunk)

        if len(buf) > max_buf_bytes:
            # Drop stale bytes before the latest SOI marker to prevent unbounded memory growth.
            last_soi = buf.rfind(JPEG_SOI)
            if last_soi > 0:
                del buf[:last_soi]
            else:
                buf.clear()
                continue

        while True:
            soi = buf.find(JPEG_SOI)
            if soi == -1:
                # Keep at most 1 byte in case SOI spans chunk boundary.
                if len(buf) > 1:
                    del buf[:-1]
                break

            if soi > 0:
                del buf[:soi]

            eoi = buf.find(JPEG_EOI, 2)
            if eoi == -1:
                if len(buf) > max_frame_bytes:
                    # Corrupted oversized frame without EOI: discard SOI and resync.
                    del buf[:2]
                    continue
                break

            candidate = bytes(buf[: eoi + 2])
            del buf[: eoi + 2]

            try:
                yield validate_jpeg_frame(candidate, max_frame_bytes=max_frame_bytes)
            except FrameValidationError:
                continue
