"""Real Ultralytics YOLO + PyTorch + OpenCV + Pillow + NumPy inference engine for images & videos."""

from __future__ import annotations

import io
import os
import tempfile
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from agrovision_worker.registry import ModelRegistryEntry, compute_file_sha256

# Guard against decompression bomb attacks when decoding uploaded images.
Image.MAX_IMAGE_PIXELS = 40_000_000


class InferenceEngineError(Exception):
    """Structured error raised during media decoding or YOLO inference."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RawDetectionBox:
    class_id: int
    label: str
    confidence: float
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    frame_index: int = 0
    timestamp_ms: int | None = None


@dataclass(frozen=True)
class ImageInferenceResult:
    detections: list[RawDetectionBox]
    annotated_jpeg_bytes: bytes
    width_px: int
    height_px: int
    inference_ms: int
    model_checksum: str
    device_used: str
    class_counts: dict[str, int]
    supported_classes: list[str]


@dataclass(frozen=True)
class SampledFrameOutput:
    sampled_index: int
    raw_frame_index: int
    timestamp_ms: int
    detections: list[RawDetectionBox]
    annotated_jpeg_bytes: bytes


@dataclass(frozen=True)
class VideoInferenceResult:
    detections: list[RawDetectionBox]
    sampled_frames: list[SampledFrameOutput]
    primary_annotated_jpeg_bytes: bytes
    width_px: int
    height_px: int
    video_duration_ms: int
    total_video_frames: int
    total_frames_sampled: int
    frame_sample_interval_ms: int
    inference_ms: int
    model_checksum: str
    device_used: str
    class_counts: dict[str, int]


class _LoadedModelHandle:
    def __init__(self, model: Any, checksum: str, device: str, class_names: dict[int, str]) -> None:
        self.model = model
        self.checksum = checksum
        self.device = device
        self.class_names = class_names
        self.infer_lock = threading.Lock()


class ModelRuntimeCache:
    """Thread-safe cache for loaded Ultralytics YOLO PyTorch checkpoints."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handles: dict[str, _LoadedModelHandle] = {}

    def resolve_device(self, requested: str = "cpu") -> str:
        try:
            import torch

            if requested.startswith("cuda") and torch.cuda.is_available():
                return requested
        except Exception:
            pass
        return "cpu"

    def get_or_load(self, entry: ModelRegistryEntry, requested_device: str = "cpu") -> _LoadedModelHandle:
        if entry.status != "available" or not entry.weights_path:
            raise InferenceEngineError("MODEL_NOT_AVAILABLE", entry.status_reason)

        weights_file = Path(entry.weights_path)
        if not weights_file.exists():
            raise InferenceEngineError(
                "MODEL_WEIGHTS_MISSING",
                f"Model weights file not found at {weights_file.as_posix()}.",
            )

        with self._lock:
            cached = self._handles.get(entry.model_id)
            if cached is not None:
                return cached

            actual_sha = compute_file_sha256(weights_file)
            if entry.expected_sha256 and actual_sha != entry.expected_sha256:
                raise InferenceEngineError(
                    "MODEL_CHECKSUM_MISMATCH",
                    f"Weights checksum mismatch for {entry.model_id}: expected {entry.expected_sha256}, got {actual_sha}.",
                )

            try:
                from ultralytics import YOLO  # type: ignore[import-not-found]
            except ImportError as exc:
                raise InferenceEngineError(
                    "AI_RUNTIME_UNAVAILABLE",
                    "Ultralytics YOLO runtime is not installed in the Python environment.",
                ) from exc

            device = self.resolve_device(requested_device)
            yolo_model = YOLO(weights_file.as_posix())
            raw_names = getattr(yolo_model, "names", {}) or {}
            class_names = {int(k): str(v) for k, v in raw_names.items()}

            handle = _LoadedModelHandle(
                model=yolo_model,
                checksum=actual_sha,
                device=device,
                class_names=class_names,
            )
            self._handles[entry.model_id] = handle
            return handle

    def get_loaded_class_names(self, entry: ModelRegistryEntry) -> list[str] | None:
        try:
            handle = self.get_or_load(entry)
            return [handle.class_names[k] for k in sorted(handle.class_names.keys())]
        except Exception:
            return None


model_runtime_cache = ModelRuntimeCache()


def decode_image_safely(image_bytes: bytes, max_dimension_px: int = 8192) -> np.ndarray:
    """Safely decode raw image bytes into a RGB NumPy array using Pillow."""
    if not image_bytes:
        raise InferenceEngineError("EMPTY_IMAGE", "Image payload is empty.")
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.format not in {"JPEG", "PNG", "WEBP"}:
                raise InferenceEngineError(
                    "UNSUPPORTED_IMAGE_FORMAT",
                    f"Decoded image format '{img.format}' is not permitted for analysis.",
                )
            # Header-only size check BEFORE pixel decoding (decompression-bomb guard).
            width, height = img.size
            if width <= 0 or height <= 0:
                raise InferenceEngineError("INVALID_IMAGE_DIMENSIONS", "Image has invalid dimensions.")
            if width > max_dimension_px or height > max_dimension_px:
                raise InferenceEngineError(
                    "IMAGE_RESOLUTION_EXCEEDED",
                    f"Image dimensions ({width}x{height}) exceed maximum allowed {max_dimension_px}px.",
                )
            if width * height > Image.MAX_IMAGE_PIXELS:
                raise InferenceEngineError(
                    "IMAGE_PIXEL_BUDGET_EXCEEDED",
                    f"Image pixel count {width * height} exceeds limit {Image.MAX_IMAGE_PIXELS}.",
                )
            img.load()
            transposed = ImageOps.exif_transpose(img)
            rgb = transposed.convert("RGB")
            return np.asarray(rgb, dtype=np.uint8)
    except InferenceEngineError:
        raise
    except Exception as exc:
        raise InferenceEngineError(
            "IMAGE_DECODE_FAILED",
            f"Unable to decode image binary safely: {exc}",
        ) from exc


def render_annotated_jpeg(
    rgb_array: np.ndarray,
    detections: list[RawDetectionBox],
    *,
    quality: int = 90,
) -> bytes:
    """Draw emerald bounding boxes and confidence labels onto an RGB array and encode as JPEG."""
    import cv2

    bgr = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
    height, width = bgr.shape[:2]
    line_thickness = max(2, int(round(min(width, height) / 320)))
    font_scale = max(0.45, min(width, height) / 1100.0)

    # Emerald color in BGR: #10B981 -> (129, 185, 16)
    box_color = (129, 185, 16)
    text_bg_color = (17, 24, 20)
    text_color = (240, 253, 244)

    for det in detections:
        x1 = max(0, min(width - 1, int(round(det.bbox_x1))))
        y1 = max(0, min(height - 1, int(round(det.bbox_y1))))
        x2 = max(x1 + 1, min(width, int(round(det.bbox_x2))))
        y2 = max(y1 + 1, min(height, int(round(det.bbox_y2))))

        cv2.rectangle(bgr, (x1, y1), (x2, y2), box_color, line_thickness)

        caption = f"{det.label} {int(round(det.confidence * 100))}%"
        (tw, th), baseline = cv2.getTextSize(
            caption, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1
        )
        pill_top = max(0, y1 - th - baseline - 8)
        pill_bottom = pill_top + th + baseline + 8
        pill_right = min(width, x1 + tw + 12)

        cv2.rectangle(bgr, (x1, pill_top), (pill_right, pill_bottom), text_bg_color, -1)
        cv2.rectangle(bgr, (x1, pill_top), (pill_right, pill_bottom), box_color, 1)
        cv2.putText(
            bgr,
            caption,
            (x1 + 6, pill_bottom - baseline - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            text_color,
            1,
            cv2.LINE_AA,
        )

    ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise InferenceEngineError("ANNOTATED_ENCODE_FAILED", "Failed to encode annotated JPEG frame.")
    return bytes(encoded.tobytes())


def _predict_on_rgb_array(
    rgb_array: np.ndarray,
    *,
    handle: _LoadedModelHandle,
    confidence_threshold: float,
    frame_index: int = 0,
    timestamp_ms: int | None = None,
) -> list[RawDetectionBox]:
    import cv2

    height, width = rgb_array.shape[:2]
    bgr = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)

    with handle.infer_lock:
        results = handle.model.predict(
            source=bgr,
            conf=confidence_threshold,
            device=handle.device,
            verbose=False,
        )

    boxes_out: list[RawDetectionBox] = []
    if not results:
        return boxes_out

    first = results[0]
    boxes = getattr(first, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return boxes_out

    xyxy_list = boxes.xyxy.cpu().numpy().tolist()
    conf_list = boxes.conf.cpu().numpy().tolist()
    cls_list = boxes.cls.cpu().numpy().tolist()

    for xyxy, conf_val, cls_val in zip(xyxy_list, conf_list, cls_list, strict=False):
        class_id = int(round(float(cls_val)))
        conf = round(max(0.0, min(1.0, float(conf_val))), 4)
        if conf < confidence_threshold:
            continue

        x1 = round(max(0.0, min(float(width), float(xyxy[0]))), 2)
        y1 = round(max(0.0, min(float(height), float(xyxy[1]))), 2)
        x2 = round(max(x1, min(float(width), float(xyxy[2]))), 2)
        y2 = round(max(y1, min(float(height), float(xyxy[3]))), 2)
        if x2 <= x1 or y2 <= y1:
            continue

        label = handle.class_names.get(class_id, f"class_{class_id}")
        boxes_out.append(
            RawDetectionBox(
                class_id=class_id,
                label=label,
                confidence=conf,
                bbox_x1=x1,
                bbox_y1=y1,
                bbox_x2=x2,
                bbox_y2=y2,
                frame_index=frame_index,
                timestamp_ms=timestamp_ms,
            )
        )

    return boxes_out


def analyze_image_bytes(
    image_bytes: bytes,
    *,
    model_entry: ModelRegistryEntry,
    confidence_threshold: float = 0.35,
    requested_device: str = "cpu",
    custom_predictor: Callable[[np.ndarray, float], list[RawDetectionBox]] | None = None,
) -> ImageInferenceResult:
    """Decode an image, execute real YOLO inference, and generate an annotated JPEG."""
    if not (0.05 <= confidence_threshold <= 0.99):
        raise InferenceEngineError(
            "INVALID_CONFIDENCE_THRESHOLD",
            "Confidence threshold must be between 0.05 and 0.99.",
        )

    rgb = decode_image_safely(image_bytes)
    height_px, width_px = int(rgb.shape[0]), int(rgb.shape[1])

    started = perf_counter()
    if custom_predictor is not None:
        if model_entry.status != "available":
            raise InferenceEngineError("MODEL_NOT_AVAILABLE", model_entry.status_reason)
        detections = custom_predictor(rgb, confidence_threshold)
        checksum = model_entry.actual_sha256 or model_entry.expected_sha256 or "test-checksum"
        device_used = "cpu"
        supported_classes = list(model_entry.supported_classes)
    else:
        handle = model_runtime_cache.get_or_load(model_entry, requested_device=requested_device)
        detections = _predict_on_rgb_array(
            rgb,
            handle=handle,
            confidence_threshold=confidence_threshold,
            frame_index=0,
            timestamp_ms=None,
        )
        checksum = handle.checksum
        device_used = handle.device
        supported_classes = [handle.class_names[k] for k in sorted(handle.class_names.keys())]

    inference_ms = max(1, int(round((perf_counter() - started) * 1000)))
    annotated_jpeg = render_annotated_jpeg(rgb, detections)
    counts = dict(Counter(d.label for d in detections))

    return ImageInferenceResult(
        detections=detections,
        annotated_jpeg_bytes=annotated_jpeg,
        width_px=width_px,
        height_px=height_px,
        inference_ms=inference_ms,
        model_checksum=checksum,
        device_used=device_used,
        class_counts=counts,
        supported_classes=supported_classes,
    )


def analyze_video_bytes(
    video_bytes: bytes,
    *,
    file_suffix: str = ".mp4",
    model_entry: ModelRegistryEntry,
    confidence_threshold: float = 0.35,
    requested_device: str = "cpu",
    frame_sample_interval_ms: int = 1000,
    max_frames: int = 30,
    max_duration_seconds: int = 120,
    max_dimension_px: int = 3840,
    progress_callback: Callable[[int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    custom_predictor: Callable[[np.ndarray, float, int, int], list[RawDetectionBox]] | None = None,
) -> VideoInferenceResult:
    """Safely decode a video, sample frames at configurable intervals, and run YOLO detection."""
    import cv2

    if not video_bytes:
        raise InferenceEngineError("EMPTY_VIDEO", "Video payload is empty.")
    if not (200 <= frame_sample_interval_ms <= 10_000):
        raise InferenceEngineError(
            "INVALID_SAMPLE_INTERVAL",
            "frame_sample_interval_ms must be between 200 ms and 10000 ms.",
        )
    if not (1 <= max_frames <= 120):
        raise InferenceEngineError(
            "INVALID_MAX_FRAMES",
            "max_frames must be between 1 and 120 sampled frames.",
        )

    handle: _LoadedModelHandle | None = None
    if custom_predictor is None:
        handle = model_runtime_cache.get_or_load(model_entry, requested_device=requested_device)
    elif model_entry.status != "available":
        raise InferenceEngineError("MODEL_NOT_AVAILABLE", model_entry.status_reason)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=file_suffix or ".mp4", prefix="agrovision_vid_")
    os.close(tmp_fd)
    cap: Any | None = None

    try:
        Path(tmp_path).write_bytes(video_bytes)
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise InferenceEngineError("VIDEO_DECODE_FAILED", "OpenCV could not open video stream.")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps <= 0.1 or fps > 240.0 or not np.isfinite(fps):
            fps = 25.0

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width_px = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height_px = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        if width_px <= 0 or height_px <= 0:
            raise InferenceEngineError(
                "VIDEO_DECODE_FAILED",
                "Video stream reported invalid frame dimensions.",
            )
        if width_px > max_dimension_px or height_px > max_dimension_px:
            raise InferenceEngineError(
                "VIDEO_RESOLUTION_EXCEEDED",
                f"Video resolution ({width_px}x{height_px}) exceeds maximum {max_dimension_px}px.",
            )

        duration_sec = (total_frames / fps) if total_frames > 0 else 0.0
        if duration_sec > max_duration_seconds:
            raise InferenceEngineError(
                "VIDEO_DURATION_EXCEEDED",
                f"Video duration ({duration_sec:.1f}s) exceeds limit of {max_duration_seconds}s.",
            )

        step_frames = max(1, int(round((frame_sample_interval_ms / 1000.0) * fps)))
        all_detections: list[RawDetectionBox] = []
        sampled_outputs: list[SampledFrameOutput] = []

        started = perf_counter()
        raw_idx = 0
        sampled_idx = 0

        while sampled_idx < max_frames:
            if cancel_check and cancel_check():
                raise InferenceEngineError("JOB_CANCELLED", "Video analysis was cancelled.")

            if total_frames > 0 and raw_idx >= total_frames:
                break

            cap.set(cv2.CAP_PROP_POS_FRAMES, raw_idx)
            ok, frame_bgr = cap.read()
            if not ok or frame_bgr is None:
                break

            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            timestamp_ms = int(round((raw_idx / fps) * 1000))

            if custom_predictor is not None:
                frame_dets = custom_predictor(rgb, confidence_threshold, sampled_idx, timestamp_ms)
            else:
                assert handle is not None
                frame_dets = _predict_on_rgb_array(
                    rgb,
                    handle=handle,
                    confidence_threshold=confidence_threshold,
                    frame_index=sampled_idx,
                    timestamp_ms=timestamp_ms,
                )

            annotated_bytes = render_annotated_jpeg(rgb, frame_dets)
            sampled_outputs.append(
                SampledFrameOutput(
                    sampled_index=sampled_idx,
                    raw_frame_index=raw_idx,
                    timestamp_ms=timestamp_ms,
                    detections=frame_dets,
                    annotated_jpeg_bytes=annotated_bytes,
                )
            )
            all_detections.extend(frame_dets)

            sampled_idx += 1
            raw_idx += step_frames

            if progress_callback:
                expected_samples = (
                    min(max_frames, max(1, (total_frames + step_frames - 1) // step_frames))
                    if total_frames > 0
                    else max_frames
                )
                pct = min(95, max(5, int(round((sampled_idx / expected_samples) * 90))))
                progress_callback(pct)

        if not sampled_outputs:
            raise InferenceEngineError(
                "VIDEO_NO_READABLE_FRAMES",
                "No decodable video frames could be extracted from the uploaded video.",
            )

        inference_ms = max(1, int(round((perf_counter() - started) * 1000)))
        best_frame = max(sampled_outputs, key=lambda item: len(item.detections))
        counts = dict(Counter(d.label for d in all_detections))
        video_duration_ms = (
            int(round(duration_sec * 1000))
            if duration_sec > 0
            else sampled_outputs[-1].timestamp_ms
        )

        checksum = (
            handle.checksum
            if handle is not None
            else (model_entry.actual_sha256 or model_entry.expected_sha256 or "test-checksum")
        )
        device_used = handle.device if handle is not None else "cpu"

        return VideoInferenceResult(
            detections=all_detections,
            sampled_frames=sampled_outputs,
            primary_annotated_jpeg_bytes=best_frame.annotated_jpeg_bytes,
            width_px=width_px,
            height_px=height_px,
            video_duration_ms=video_duration_ms,
            total_video_frames=max(total_frames, sampled_idx),
            total_frames_sampled=len(sampled_outputs),
            frame_sample_interval_ms=frame_sample_interval_ms,
            inference_ms=inference_ms,
            model_checksum=checksum,
            device_used=device_used,
            class_counts=counts,
        )
    finally:
        if cap is not None:
            cap.release()
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
