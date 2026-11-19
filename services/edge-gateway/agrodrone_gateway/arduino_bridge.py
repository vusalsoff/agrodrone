"""Reliable ESP32-CAM -> AgroDrone AI -> Arduino UNO USB Serial Bridge (COM15, 9600 baud)."""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
import serial
from serial import SerialException

from agrodrone_gateway.client import GatewayApiClient
from agrodrone_gateway.config import GatewayConfig

logger = logging.getLogger("agrodrone.arduino")

BridgeState = Literal["DETECTED", "CLEAR", "UNAVAILABLE"]

DEFAULT_TARGET_CLASSES: tuple[str, ...] = (
    "person",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
)


class SerialPortLockError(RuntimeError):
    """Raised when another process already holds the exclusive lock for the COM port."""


class SerialConnectionError(RuntimeError):
    """Raised when the USB serial connection is lost or cannot be opened."""


def parse_target_classes(raw: str | None) -> tuple[str, ...]:
    """Parse comma-separated COCO class names into normalized lowercase tuples."""
    if raw is None or not raw.strip():
        return DEFAULT_TARGET_CLASSES
    items = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return items or DEFAULT_TARGET_CLASSES


@dataclass(frozen=True)
class ArduinoBridgeConfig:
    api_base_url: str
    gateway_token: str
    serial_port: str = "COM15"
    baudrate: int = 9600
    target_classes: tuple[str, ...] = DEFAULT_TARGET_CLASSES
    confidence_threshold: float = 0.35
    model_id: str = "yolov8n-coco-general"
    heartbeat_interval_seconds: float = 0.5
    max_result_age_seconds: float = 5.0
    serial_reconnect_interval_seconds: float = 2.0
    esp32_capture_url: str | None = "http://192.168.4.1/capture"
    capture_interval_seconds: float = 1.0
    require_camera_healthy: bool = True
    connect_timeout_seconds: float = 3.0
    read_timeout_seconds: float = 5.0
    status_file: Path | None = Path("./data/arduino_bridge_status.json")
    lock_dir: Path = field(default_factory=lambda: Path(tempfile.gettempdir()))

    def __post_init__(self) -> None:
        if not 0.1 <= self.heartbeat_interval_seconds <= 1.0:
            raise ValueError("heartbeat_interval_seconds must be between 0.1 and 1.0s (>= 1 Hz).")
        if not 0.05 <= self.confidence_threshold <= 0.99:
            raise ValueError("confidence_threshold must be between 0.05 and 0.99.")
        if self.max_result_age_seconds <= 0:
            raise ValueError("max_result_age_seconds must be positive.")

    @classmethod
    def from_env(cls) -> ArduinoBridgeConfig:
        capture_raw = os.environ.get("ESP32_CAPTURE_URL", "http://192.168.4.1/capture").strip()
        status_raw = os.environ.get("ARDUINO_STATUS_FILE", "./data/arduino_bridge_status.json").strip()
        return cls(
            api_base_url=os.environ.get("AGRODRONE_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
            gateway_token=os.environ.get("AGRODRONE_GATEWAY_TOKEN", "").strip(),
            serial_port=os.environ.get("ARDUINO_SERIAL_PORT", "COM15").strip(),
            baudrate=int(os.environ.get("ARDUINO_BAUDRATE", "9600")),
            target_classes=parse_target_classes(os.environ.get("ARDUINO_TARGET_CLASSES")),
            confidence_threshold=float(os.environ.get("ARDUINO_CONFIDENCE_THRESHOLD", "0.35")),
            model_id=os.environ.get("ARDUINO_MODEL_ID", "yolov8n-coco-general").strip(),
            heartbeat_interval_seconds=min(
                1.0, max(0.1, float(os.environ.get("ARDUINO_HEARTBEAT_INTERVAL", "0.5")))
            ),
            max_result_age_seconds=max(
                1.0, float(os.environ.get("ARDUINO_MAX_RESULT_AGE_SECONDS", "5.0"))
            ),
            serial_reconnect_interval_seconds=max(
                0.5, float(os.environ.get("ARDUINO_SERIAL_RECONNECT_INTERVAL", "2.0"))
            ),
            esp32_capture_url=capture_raw or None,
            capture_interval_seconds=max(
                0.25, float(os.environ.get("ARDUINO_CAPTURE_INTERVAL", "1.0"))
            ),
            require_camera_healthy=os.environ.get("ARDUINO_REQUIRE_CAMERA_HEALTHY", "true").lower()
            in ("1", "true", "yes"),
            status_file=Path(status_raw) if status_raw else None,
        )


class SerialPortLock:
    """Exclusive OS-level lock preventing multiple processes from opening the same COM port."""

    def __init__(self, port: str, lock_dir: Path | None = None) -> None:
        safe_port = re.sub(r"[^A-Za-z0-9_.-]+", "_", port.upper())
        base_dir = lock_dir or Path(tempfile.gettempdir())
        base_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = base_dir / f"agrodrone_serial_{safe_port}.lock"
        self._fd: int | None = None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if sys.platform == "win32":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, f"{os.getpid()}\n".encode("ascii"))
            self._fd = fd
        except OSError as exc:
            os.close(fd)
            raise SerialPortLockError(
                f"Serial port lock '{self.lock_path}' is already held by another process."
            ) from exc

    def release(self) -> None:
        if self._fd is None:
            return
        fd = self._fd
        self._fd = None
        try:
            if sys.platform == "win32":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            os.close(fd)

    def __enter__(self) -> SerialPortLock:
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


class SerialTransport(Protocol):
    @property
    def is_open(self) -> bool: ...
    def open(self) -> None: ...
    def close(self) -> None: ...
    def write_command(self, cmd: bytes) -> None: ...


class PySerialTransport:
    """pyserial-backed USB Serial transport for Arduino UNO (9600 baud)."""

    def __init__(self, port: str, baudrate: int = 9600, write_timeout: float = 1.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.write_timeout = write_timeout
        self._serial: serial.Serial | None = None

    @property
    def is_open(self) -> bool:
        return bool(self._serial is not None and self._serial.is_open)

    def open(self) -> None:
        if self.is_open:
            return
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1.0,
                write_timeout=self.write_timeout,
            )
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
        except (SerialException, OSError) as exc:
            self._serial = None
            raise SerialConnectionError(f"Failed to open serial port {self.port}: {exc}") from exc

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except (SerialException, OSError):
                pass
            finally:
                self._serial = None

    def write_command(self, cmd: bytes) -> None:
        if not self.is_open or self._serial is None:
            raise SerialConnectionError(f"Serial port {self.port} is not open.")
        try:
            self._serial.write(cmd)
            self._serial.flush()
        except (SerialException, OSError) as exc:
            self.close()
            raise SerialConnectionError(f"Serial write failed on {self.port}: {exc}") from exc


@dataclass
class ArduinoBridgeStatus:
    serial_port: str
    baudrate: int
    serial_connected: bool
    pipeline_healthy: bool
    camera_healthy: bool
    current_state: BridgeState
    reason: str
    last_command: str | None = None
    last_command_at: str | None = None
    last_job_id: str | None = None
    last_job_age_seconds: float | None = None
    matched_detections: list[dict[str, Any]] = field(default_factory=list)
    total_commands_sent: int = 0
    reconnect_attempts: int = 0
    last_error: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_detection_decision(
    latest: dict[str, Any] | None,
    *,
    pipeline_healthy: bool,
    camera_healthy: bool,
    require_camera_healthy: bool,
    target_classes: tuple[str, ...],
    confidence_threshold: float,
    max_result_age_seconds: float,
) -> tuple[BridgeState, bytes | None, list[dict[str, Any]], str]:
    """Decide whether to send '1', '0', or halt transmission (3s Arduino timeout safety).

    Never treats an unprocessed frame, stale result, or network/camera failure as '0'.
    """
    if not pipeline_healthy or latest is None:
        return ("UNAVAILABLE", None, [], "pipeline_unavailable")

    if not latest.get("ai_inference_enabled", False):
        return ("UNAVAILABLE", None, [], "ai_inference_disabled")

    if require_camera_healthy and not camera_healthy:
        return ("UNAVAILABLE", None, [], "camera_unavailable")

    if not latest.get("has_result", False):
        return ("UNAVAILABLE", None, [], "no_detection_job_yet")

    job_status = latest.get("status")
    if job_status != "completed":
        return ("UNAVAILABLE", None, [], f"frame_not_completed:{job_status}")

    age = latest.get("age_seconds")
    if age is None or float(age) > max_result_age_seconds:
        return ("UNAVAILABLE", None, [], f"stale_result:{age}")

    target_set = {c.lower() for c in target_classes}
    wildcard = "*" in target_set
    matched: list[dict[str, Any]] = []
    for item in latest.get("detections", []):
        label = str(item.get("label", "")).strip()
        conf = float(item.get("confidence", 0.0))
        if conf >= confidence_threshold and (wildcard or label.lower() in target_set):
            matched.append({"label": label, "confidence": round(conf, 4)})

    if matched:
        return ("DETECTED", b"1", matched, "target_detected")
    return ("CLEAR", b"0", [], "verified_no_target")


class ArduinoBridgeRunner:
    """Coordinates ESP32-CAM capture/poll -> AgroDrone AI -> COM15 Arduino UNO heartbeat."""

    def __init__(
        self,
        config: ArduinoBridgeConfig,
        *,
        api_client: GatewayApiClient | None = None,
        serial_transport: SerialTransport | None = None,
        camera_transport: httpx.BaseTransport | None = None,
        port_lock: SerialPortLock | None = None,
    ) -> None:
        if not config.gateway_token:
            raise ValueError("AGRODRONE_GATEWAY_TOKEN is required for the Arduino bridge.")
        self.config = config
        if api_client is not None:
            self.api = api_client
        else:
            gw_cfg = GatewayConfig(
                api_base_url=config.api_base_url,
                gateway_token=config.gateway_token,
                connect_timeout_seconds=config.connect_timeout_seconds,
                read_timeout_seconds=config.read_timeout_seconds,
            )
            self.api = GatewayApiClient(gw_cfg)

        self.serial = serial_transport or PySerialTransport(config.serial_port, config.baudrate)
        self.port_lock = port_lock or SerialPortLock(config.serial_port, config.lock_dir)
        self._cam_client = (
            httpx.Client(
                timeout=httpx.Timeout(
                    connect=config.connect_timeout_seconds,
                    read=config.read_timeout_seconds,
                    write=config.connect_timeout_seconds,
                    pool=config.connect_timeout_seconds,
                ),
                transport=camera_transport,
            )
            if config.esp32_capture_url
            else None
        )

        self._stop_event = threading.Event()
        self._last_capture_ts = 0.0
        self._last_capture_ok: bool | None = None
        self._last_reconnect_ts = 0.0
        self._prev_state: BridgeState | None = None
        self.status = ArduinoBridgeStatus(
            serial_port=config.serial_port,
            baudrate=config.baudrate,
            serial_connected=False,
            pipeline_healthy=False,
            camera_healthy=False,
            current_state="UNAVAILABLE",
            reason="initializing",
        )

    def request_stop(self) -> None:
        self._stop_event.set()

    def _capture_and_submit_frame(self, now_mono: float) -> None:
        if not self._cam_client or not self.config.esp32_capture_url:
            return
        if now_mono - self._last_capture_ts < self.config.capture_interval_seconds:
            return
        self._last_capture_ts = now_mono
        try:
            resp = self._cam_client.get(self.config.esp32_capture_url)
            resp.raise_for_status()
            jpeg = resp.content
            if not jpeg or not jpeg.startswith(b"\xff\xd8"):
                raise ValueError("ESP32-CAM did not return valid JPEG bytes.")
            self.api.upload_snapshot(
                jpeg,
                filename="esp32_arduino_live.jpg",
                notes="Arduino bridge live capture",
                analyze=True,
                model_id=self.config.model_id,
                confidence_threshold=self.config.confidence_threshold,
            )
            self._last_capture_ok = True
        except Exception as exc:
            self._last_capture_ok = False
            self.status.last_error = f"camera_capture_error: {exc}"
            logger.warning("esp32_capture_failed", extra={"error": str(exc)})

    def _ensure_serial_connected(self, now_mono: float) -> bool:
        if self.serial.is_open:
            self.status.serial_connected = True
            return True
        if now_mono - self._last_reconnect_ts < self.config.serial_reconnect_interval_seconds:
            self.status.serial_connected = False
            return False
        self._last_reconnect_ts = now_mono
        self.status.reconnect_attempts += 1
        try:
            self.serial.open()
            self.status.serial_connected = True
            self.status.last_error = None
            logger.info(
                "arduino_serial_connected",
                extra={"port": self.config.serial_port, "baudrate": self.config.baudrate},
            )
            return True
        except SerialConnectionError as exc:
            self.status.serial_connected = False
            self.status.last_error = str(exc)
            logger.warning(
                "arduino_serial_reconnect_failed",
                extra={"port": self.config.serial_port, "attempt": self.status.reconnect_attempts, "error": str(exc)},
            )
            return False

    def _write_status_file(self) -> None:
        if not self.config.status_file:
            return
        try:
            self.config.status_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.config.status_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.status.to_dict(), indent=2), encoding="utf-8")
            tmp.replace(self.config.status_file)
        except OSError as exc:
            logger.warning("arduino_status_write_failed", extra={"error": str(exc)})

    def step(self, *, now_mono: float | None = None) -> ArduinoBridgeStatus:
        """Execute one deterministic poll/capture + evaluate + serial heartbeat cycle."""
        mono = time.monotonic() if now_mono is None else now_mono

        # 1. Optional active capture from ESP32-CAM -> POST /snapshots?analyze=true
        self._capture_and_submit_frame(mono)

        # 2. Poll fresh YOLO detection state from AgroDrone backend
        latest: dict[str, Any] | None = None
        pipeline_healthy = False
        try:
            latest = self.api.get_latest_detection(model_id=self.config.model_id)
            pipeline_healthy = True
        except Exception as exc:
            self.status.last_error = f"api_poll_error: {exc}"
            logger.warning("arduino_api_poll_failed", extra={"error": str(exc)})

        if self._cam_client is not None:
            camera_healthy = bool(self._last_capture_ok)
        else:
            camera_healthy = bool(latest.get("camera_reachable", False)) if latest else False

        state, cmd, matched, reason = evaluate_detection_decision(
            latest,
            pipeline_healthy=pipeline_healthy,
            camera_healthy=camera_healthy,
            require_camera_healthy=self.config.require_camera_healthy,
            target_classes=self.config.target_classes,
            confidence_threshold=self.config.confidence_threshold,
            max_result_age_seconds=self.config.max_result_age_seconds,
        )

        # 3. Ensure serial connection & send heartbeat only when state is verified (DETECTED or CLEAR)
        serial_ok = self._ensure_serial_connected(mono)
        if serial_ok and cmd is not None:
            try:
                self.serial.write_command(cmd)
                self.status.last_command = cmd.decode("ascii")
                self.status.last_command_at = datetime.now(UTC).isoformat()
                self.status.total_commands_sent += 1
            except SerialConnectionError as exc:
                serial_ok = False
                self.status.last_error = str(exc)
                logger.warning("arduino_serial_disconnected", extra={"port": self.config.serial_port, "error": str(exc)})

        # If serial is disconnected, effective hardware state is UNAVAILABLE
        effective_state: BridgeState = state if serial_ok else "UNAVAILABLE"
        effective_reason = reason if serial_ok else "serial_disconnected"

        self.status.serial_connected = serial_ok
        self.status.pipeline_healthy = pipeline_healthy
        self.status.camera_healthy = camera_healthy
        self.status.current_state = effective_state
        self.status.reason = effective_reason
        self.status.last_job_id = str(latest["job_id"]) if latest and latest.get("job_id") else None
        self.status.last_job_age_seconds = latest.get("age_seconds") if latest else None
        self.status.matched_detections = matched
        self.status.updated_at = datetime.now(UTC).isoformat()

        if effective_state != self._prev_state:
            logger.info(
                "arduino_state_changed",
                extra={
                    "previous_state": self._prev_state,
                    "new_state": effective_state,
                    "reason": effective_reason,
                    "matched_count": len(matched),
                    "port": self.config.serial_port,
                },
            )
            self._prev_state = effective_state

        self._write_status_file()
        return self.status

    def run_forever(self) -> None:
        """Acquire exclusive COM port lock and run heartbeat loop until stopped."""
        def _handle_sig(_signum: int, _frame: Any) -> None:
            self.request_stop()

        try:
            signal.signal(signal.SIGINT, _handle_sig)
            signal.signal(signal.SIGTERM, _handle_sig)
        except ValueError:
            pass

        with self.port_lock:
            logger.info(
                "arduino_bridge_started",
                extra={
                    "port": self.config.serial_port,
                    "baudrate": self.config.baudrate,
                    "target_classes": list(self.config.target_classes),
                    "confidence_threshold": self.config.confidence_threshold,
                    "heartbeat_interval_seconds": self.config.heartbeat_interval_seconds,
                    "max_result_age_seconds": self.config.max_result_age_seconds,
                },
            )
            try:
                while not self._stop_event.is_set():
                    started = time.monotonic()
                    self.step(now_mono=started)
                    elapsed = time.monotonic() - started
                    wait_for = max(0.05, self.config.heartbeat_interval_seconds - elapsed)
                    self._stop_event.wait(wait_for)
            finally:
                self.serial.close()
                if self._cam_client is not None:
                    self._cam_client.close()
                self.api.close()
                logger.info("arduino_bridge_stopped", extra={"port": self.config.serial_port})
