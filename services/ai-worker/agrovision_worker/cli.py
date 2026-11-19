"""Standalone CLI entrypoint for the AgroVision AI Worker service."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from agrovision_worker.engine import model_runtime_cache
from agrovision_worker.registry import build_model_registry


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agrovision-worker",
        description="AgroDrone Phase 3 AgroVision AI Worker — Model Registry & Self-Test CLI",
    )
    parser.add_argument(
        "--inspect-models",
        action="store_true",
        help="Print the active model registry and verify weights SHA-256 digests.",
    )
    parser.add_argument(
        "--warm-general",
        action="store_true",
        help="Load and warm the general YOLOv8n checkpoint into memory.",
    )
    args = parser.parse_args()

    entries = build_model_registry()
    if args.warm_general:
        general = next((e for e in entries if e.model_id == "yolov8n-coco-general"), None)
        if general and general.status == "available":
            classes = model_runtime_cache.get_loaded_class_names(general) or []
            entries = build_model_registry(
                dynamic_class_names={"yolov8n-coco-general": classes}
            )

    if args.inspect_models or args.warm_general:
        print(json.dumps([asdict(entry) for entry in entries], indent=2))


if __name__ == "__main__":
    main()
