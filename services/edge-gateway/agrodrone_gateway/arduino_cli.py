"""CLI entry point for the AgroDrone Arduino UNO USB Serial alert bridge."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace

from agrodrone_gateway.arduino_bridge import (
    ArduinoBridgeConfig,
    ArduinoBridgeRunner,
    SerialPortLockError,
    parse_target_classes,
)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key in (
            "port",
            "baudrate",
            "previous_state",
            "new_state",
            "reason",
            "matched_count",
            "target_classes",
            "confidence_threshold",
            "heartbeat_interval_seconds",
            "max_result_age_seconds",
            "attempt",
            "error",
        ):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        return json.dumps(payload, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AgroDrone ESP32-CAM -> AI -> Arduino UNO Serial Bridge")
    parser.add_argument("--port", default=None, help="Serial port (default: COM15 or ARDUINO_SERIAL_PORT)")
    parser.add_argument("--baud", type=int, default=None, help="Serial baudrate (default: 9600)")
    parser.add_argument("--classes", default=None, help="Comma-separated COCO classes (or '*' for any)")
    parser.add_argument("--confidence", type=float, default=None, help="Confidence threshold (0.05-0.99)")
    parser.add_argument("--model-id", default=None, help="YOLO model ID (default: yolov8n-coco-general)")
    parser.add_argument("--heartbeat", type=float, default=None, help="Heartbeat interval in seconds (0.1-1.0)")
    parser.add_argument("--max-age", type=float, default=None, help="Max detection age in seconds before stale")
    parser.add_argument(
        "--poll-only",
        action="store_true",
        help="Do not capture directly from ESP32-CAM; only poll latest backend YOLO results.",
    )
    args = parser.parse_args(argv)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger("agrodrone.arduino")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    cfg = ArduinoBridgeConfig.from_env()
    if args.port:
        cfg = replace(cfg, serial_port=args.port)
    if args.baud:
        cfg = replace(cfg, baudrate=args.baud)
    if args.classes:
        cfg = replace(cfg, target_classes=parse_target_classes(args.classes))
    if args.confidence is not None:
        cfg = replace(cfg, confidence_threshold=args.confidence)
    if args.model_id:
        cfg = replace(cfg, model_id=args.model_id)
    if args.heartbeat is not None:
        cfg = replace(cfg, heartbeat_interval_seconds=args.heartbeat)
    if args.max_age is not None:
        cfg = replace(cfg, max_result_age_seconds=args.max_age)
    if args.poll_only:
        cfg = replace(cfg, esp32_capture_url=None)

    try:
        runner = ArduinoBridgeRunner(cfg)
        runner.run_forever()
    except (ValueError, SerialPortLockError) as exc:
        root.error("arduino_bridge_startup_failed", extra={"error": str(exc), "port": cfg.serial_port})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
