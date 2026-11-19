"""Download YOLOv8n baseline weights from the official Ultralytics GitHub release and verify SHA-256.

Usage:
    python services/ai-worker/scripts/fetch_weights.py

The file is only installed if its SHA-256 matches the pinned checksum in
agrovision_worker/registry.py (or AI_YOLOV8N_SHA256). Mismatches are rejected.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agrovision_worker.registry import (  # noqa: E402
    OFFICIAL_YOLOV8N_URL,
    PINNED_YOLOV8N_SHA256,
    default_weights_dir,
)


def main() -> int:
    target_dir = default_weights_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "yolov8n.pt"

    if target.exists():
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest == PINNED_YOLOV8N_SHA256:
            print(f"Already present and verified: {target} ({digest})")
            return 0
        print(f"Existing file checksum mismatch ({digest}); re-downloading.")

    print(f"Downloading {OFFICIAL_YOLOV8N_URL}")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pt") as tmp:
        tmp_path = Path(tmp.name)
    try:
        urllib.request.urlretrieve(OFFICIAL_YOLOV8N_URL, tmp_path)  # noqa: S310 - fixed trusted HTTPS URL
        digest = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
        if digest != PINNED_YOLOV8N_SHA256:
            print(f"REJECTED: checksum {digest} != pinned {PINNED_YOLOV8N_SHA256}")
            return 2
        tmp_path.replace(target)
        print(f"Installed verified weights: {target} ({digest})")
        return 0
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
