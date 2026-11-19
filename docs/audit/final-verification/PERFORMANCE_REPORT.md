# AgroDrone — Performance & Reliability Report

**Test Environment:** Windows 11 (`10.0.26300`), 18 logical CPUs, 23.47 GB RAM, Python `3.12.2`, PyTorch `2.14.1+cpu`, SQLite local storage.

## Measured Benchmarks (Actual Observed Values)

| Metric | Measured Result | Source |
|---|---|---|
| **API `/api/v1/health` Latency (20 calls)** | `p50 = 3.79 ms`, `p95 = 6.30 ms` | `test_ultimate_master_audit.py` |
| **API `/api/v1/analytics/overview` Latency (20 calls)** | `p50 = 8.11 ms`, `p95 = 11.39 ms` | `test_ultimate_master_audit.py` |
| **16 Concurrent `/api/v1/health` Requests (8 threads)** | `66.09 ms` total (16/16 `200 OK`) | `test_phase7_e2e_and_performance.py` |
| **Media Upload (137 KB JPEG)** | `28.82 ms` | `test_phase7_e2e_and_performance.py` |
| **YOLOv8n CPU Inference (810×1080 JPEG)** | `2003 ms` (6 detections) | `test_phase7_e2e_and_performance.py` |
| **YOLOv8n CPU Inference (810×1080 PNG)** | `2489 ms` (6 detections) | `test_ultimate_master_audit.py` |
| **Process RSS Memory (Before → After YOLOv8n)** | `354.9 MB` → `502.6 MB` (`+147.7 MB`) | `test_ultimate_master_audit.py` |

## Reliability Verification
- **Restart Persistence:** Verified across full SQLAlchemy engine disposal and fresh FastAPI `create_app` instance on the same SQLite DB (`test_phase7_e2e_and_performance.py`).
- **Worker Recovery & Healthcheck:** Verified `recover_interrupted_jobs`, `--once`, and `--healthcheck` heartbeat staleness detection (`test_phase6_production_hardening.py`).
