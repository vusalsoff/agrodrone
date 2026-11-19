"""Measure real YOLOv8n load time and inference latency on the current hardware.

Usage:
    python services/ai-worker/scripts/benchmark.py [--runs 20] [--image path.jpg]

Defaults to the Ultralytics-bundled bus.jpg sample. Reports wall-clock measurements only;
no accuracy is claimed.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agrovision_worker.engine import analyze_image_bytes, model_runtime_cache  # noqa: E402
from agrovision_worker.registry import GENERAL_MODEL_ID, build_model_registry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--image", type=str, default="")
    parser.add_argument("--conf", type=float, default=0.35)
    args = parser.parse_args()

    import torch
    from ultralytics.utils import ASSETS

    image_path = Path(args.image) if args.image else Path(ASSETS) / "bus.jpg"
    image_bytes = image_path.read_bytes()
    entry = next(e for e in build_model_registry() if e.model_id == GENERAL_MODEL_ID)
    if entry.status != "available":
        print(f"Model unavailable: {entry.status_reason}")
        return 1

    t0 = perf_counter()
    model_runtime_cache.get_or_load(entry)
    load_ms = (perf_counter() - t0) * 1000

    first = analyze_image_bytes(image_bytes, model_entry=entry, confidence_threshold=args.conf)
    latencies: list[float] = []
    end_to_end: list[float] = []
    for _ in range(args.runs):
        s = perf_counter()
        res = analyze_image_bytes(image_bytes, model_entry=entry, confidence_threshold=args.conf)
        end_to_end.append((perf_counter() - s) * 1000)
        latencies.append(res.inference_ms)

    q = statistics.quantiles(end_to_end, n=20) if len(end_to_end) >= 2 else end_to_end
    report = {
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "torch": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "torch_threads": torch.get_num_threads(),
            "device_used": first.device_used,
        },
        "image": {"path": image_path.name, "width": first.width_px, "height": first.height_px},
        "model_load_ms": round(load_ms, 1),
        "cold_first_inference_ms": first.inference_ms,
        "warm_runs": args.runs,
        "warm_inference_ms_mean": round(statistics.mean(latencies), 1),
        "warm_inference_ms_median": round(statistics.median(latencies), 1),
        "end_to_end_ms_mean": round(statistics.mean(end_to_end), 1),
        "end_to_end_ms_p95": round(q[-1], 1),
        "detections": first.class_counts,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
