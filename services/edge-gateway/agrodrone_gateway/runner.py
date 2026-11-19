"""Main Field Edge Gateway runner: MJPEG ingestion, exponential backoff, relay, and spool drain."""

from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Any

import httpx

from agrodrone_gateway.client import GatewayApiClient
from agrodrone_gateway.config import GatewayConfig
from agrodrone_gateway.mjpeg import iter_mjpeg_frames
from agrodrone_gateway.network import inspect_network_state
from agrodrone_gateway.spool import OfflineSnapshotSpool

logger = logging.getLogger("agrodrone.gateway")


class EdgeGatewayRunner:
    """Bounded, resilient ESP32-CAM bridge supporting offline spooling and throttled live relay."""

    def __init__(
        self,
        config: GatewayConfig,
        *,
        api_client: GatewayApiClient | None = None,
        camera_transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not config.gateway_token:
            raise ValueError("AGRODRONE_GATEWAY_TOKEN is required to run the Edge Gateway.")
        self.config = config
        self.api = api_client or GatewayApiClient(config)
        self.spool = OfflineSnapshotSpool(config.offline_spool_dir, config.offline_quota_bytes)
        self._camera_transport = camera_transport

        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self.camera_reachable = False
        self.stream_active = False
        self.target_fps = config.target_fps
        self.observed_fps: float | None = None
        self.dropped_frames = 0
        self.sequence = 0

    def request_stop(self) -> None:
        self._stop_event.set()

    def _drain_spool(self) -> None:
        pending = self.spool.list_pending(max_attempts=self.config.upload_retry_limit, limit=10)
        for snap in pending:
            if self._stop_event.is_set():
                break
            try:
                jpeg_bytes = snap.file_path.read_bytes()
                self.api.upload_snapshot(
                    jpeg_bytes,
                    filename=snap.filename,
                    notes=snap.notes,
                    analyze=False,
                )
                self.spool.mark_uploaded(snap.id)
                logger.info("spooled_snapshot_uploaded", extra={"id": snap.id, "bytes": snap.byte_size})
            except Exception as exc:
                self.spool.record_failure(snap.id, str(exc))
                logger.warning("spool_upload_failed", extra={"id": snap.id, "error": str(exc)})
                break

    def _send_heartbeat(self) -> None:
        diag = inspect_network_state(
            esp32_stream_url=self.config.esp32_stream_url,
            api_base_url=self.config.api_base_url,
            deployment_mode=self.config.deployment_mode,
        )
        queue_depth, queue_bytes = self.spool.stats()
        with self._state_lock:
            cam_ok = self.camera_reachable
            fps = self.observed_fps
            dropped = self.dropped_frames

        payload: dict[str, Any] = {
            "camera_reachable": cam_ok,
            "camera_fps": round(fps, 2) if fps is not None else None,
            "dropped_frames": dropped,
            "queue_depth": queue_depth,
            "queue_bytes": queue_bytes,
            "internet_reachable": diag.internet_reachable,
            "deployment_mode": self.config.deployment_mode,
            "local_interface": self.config.local_interface,
            "uplink_interface": self.config.uplink_interface,
            "diagnostics": {
                "camera_host_reachable": diag.camera_host_reachable,
                "api_host_reachable": diag.api_host_reachable,
                "single_wifi_warning": diag.single_wifi_warning,
            },
        }
        try:
            resp = self.api.send_heartbeat(payload)
            with self._state_lock:
                self.stream_active = bool(resp.get("stream_active", False))
                sess = resp.get("active_session")
                if isinstance(sess, dict) and sess.get("target_fps"):
                    self.target_fps = max(0.2, min(5.0, float(sess["target_fps"])))
            self._drain_spool()
        except Exception as exc:
            logger.warning("heartbeat_failed", extra={"error": str(exc)})

    def capture_or_spool_snapshot(self, jpeg_bytes: bytes, *, notes: str | None = None) -> bool:
        """Upload a snapshot immediately, or spool locally if backend is unreachable.

        Returns True if uploaded immediately, False if spooled offline.
        """
        try:
            self.api.upload_snapshot(jpeg_bytes, notes=notes, analyze=False)
            return True
        except Exception as exc:
            self.spool.enqueue(jpeg_bytes, notes=notes)
            logger.info("snapshot_spooled_offline", extra={"error": str(exc)})
            return False

    def run_once_from_stream(self, *, max_frames: int = 1, save_snapshot: bool = True) -> int:
        """Read up to `max_frames` from the ESP32-CAM MJPEG stream and relay/upload them."""
        processed = 0
        last_relay_ts = 0.0
        cam_client = httpx.Client(
            timeout=httpx.Timeout(
                connect=self.config.connect_timeout_seconds,
                read=self.config.read_timeout_seconds,
                write=self.config.connect_timeout_seconds,
                pool=self.config.connect_timeout_seconds,
            ),
            transport=self._camera_transport,
        )

        try:
            with cam_client.stream("GET", self.config.esp32_stream_url) as stream_res:
                stream_res.raise_for_status()
                with self._state_lock:
                    self.camera_reachable = True

                for jpeg_bytes in iter_mjpeg_frames(
                    stream_res.iter_bytes(chunk_size=16384),
                    max_frame_bytes=self.config.max_frame_bytes,
                ):
                    if self._stop_event.is_set():
                        break

                    now = time.monotonic()
                    self.sequence += 1
                    processed += 1

                    if save_snapshot and processed == 1:
                        self.capture_or_spool_snapshot(jpeg_bytes, notes="Captured via Edge Gateway")

                    with self._state_lock:
                        relay_on = self.stream_active
                        min_interval = 1.0 / max(0.2, self.target_fps)

                    if relay_on and (now - last_relay_ts) >= min_interval:
                        try:
                            self.api.push_stream_frame(jpeg_bytes, sequence=self.sequence)
                            last_relay_ts = now
                        except Exception:
                            with self._state_lock:
                                self.dropped_frames += 1

                    if processed >= max_frames:
                        break
        finally:
            cam_client.close()

        return processed

    def run_forever(self) -> None:
        """Main resilient gateway loop with heartbeat thread and exponential backoff."""
        signal.signal(signal.SIGINT, lambda *_: self.request_stop())
        signal.signal(signal.SIGTERM, lambda *_: self.request_stop())

        def _hb_loop() -> None:
            while not self._stop_event.is_set():
                self._send_heartbeat()
                self._stop_event.wait(self.config.heartbeat_interval_seconds)

        hb_thread = threading.Thread(target=_hb_loop, name="gateway-heartbeat", daemon=True)
        hb_thread.start()

        backoff = self.config.backoff_initial_seconds
        last_snapshot_ts = 0.0

        while not self._stop_event.is_set():
            try:
                cam_client = httpx.Client(
                    timeout=httpx.Timeout(
                        connect=self.config.connect_timeout_seconds,
                        read=self.config.read_timeout_seconds,
                        write=self.config.connect_timeout_seconds,
                        pool=self.config.connect_timeout_seconds,
                    ),
                    transport=self._camera_transport,
                )
                try:
                    with cam_client.stream("GET", self.config.esp32_stream_url) as stream_res:
                        stream_res.raise_for_status()
                        with self._state_lock:
                            self.camera_reachable = True
                        backoff = self.config.backoff_initial_seconds
                        frame_window_start = time.monotonic()
                        frames_in_window = 0
                        last_relay_ts = 0.0

                        for jpeg_bytes in iter_mjpeg_frames(
                            stream_res.iter_bytes(chunk_size=16384),
                            max_frame_bytes=self.config.max_frame_bytes,
                        ):
                            if self._stop_event.is_set():
                                break

                            now = time.monotonic()
                            self.sequence += 1
                            frames_in_window += 1
                            elapsed = now - frame_window_start
                            if elapsed >= 2.0:
                                with self._state_lock:
                                    self.observed_fps = frames_in_window / elapsed
                                frame_window_start = now
                                frames_in_window = 0

                            if (
                                self.config.snapshot_interval_seconds > 0
                                and (now - last_snapshot_ts) >= self.config.snapshot_interval_seconds
                            ):
                                self.capture_or_spool_snapshot(jpeg_bytes)
                                last_snapshot_ts = now

                            with self._state_lock:
                                relay_on = self.stream_active
                                min_interval = 1.0 / max(0.2, self.target_fps)

                            if relay_on and (now - last_relay_ts) >= min_interval:
                                try:
                                    self.api.push_stream_frame(jpeg_bytes, sequence=self.sequence)
                                    last_relay_ts = now
                                except Exception:
                                    with self._state_lock:
                                        self.dropped_frames += 1
                finally:
                    cam_client.close()
            except Exception as exc:
                with self._state_lock:
                    self.camera_reachable = False
                    self.observed_fps = None
                logger.warning(
                    "camera_stream_reconnecting",
                    extra={"retry_in_seconds": backoff, "error": str(exc)},
                )
                self._stop_event.wait(backoff)
                backoff = min(self.config.backoff_max_seconds, backoff * 2.0)

        self.api.close()
