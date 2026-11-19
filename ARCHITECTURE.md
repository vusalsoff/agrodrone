# AgroDrone — System Architecture

This document defines the target production architecture for **AgroDrone** and specifies which components are active in **Phase 1 (Foundation)** versus scheduled in subsequent phases.

---

## 1. High-Level System Topology

```text
+-----------------------------------------------------------------------------------+
|                                FIELD / EDGE ZONE                                  |
|                                                                                   |
|  [ E88 Airframe + AI Thinker ESP32-CAM (OV2640) ]                                 |
|   • Isolated Wi-Fi Access Point (SSID: agroDrone, 192.168.4.1)                    |
|   • Dashboard: http://192.168.4.1   |   MJPEG: http://192.168.4.1:81/stream       |
|   • RGB imagery only (no GPS, no MAVLink, no battery telemetry)                   |
|                 |                                                                 |
|                 | Local Wi-Fi (192.168.4.x — NEVER directly reachable from cloud) |
|                 v                                                                 |
|  [ Operator Laptop / Phone / Raspberry Pi — Phase 4 Field Edge Gateway ]          |
|   • Dual-homed or store-and-forward (Wi-Fi -> ESP32-CAM; LTE/Wi-Fi -> Internet)   |
|   • Captures frames/clips, attaches operator-supplied field & GPS metadata        |
|   • Authenticates outbound over TLS 1.3 (short-lived device token / mTLS)         |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          | Outbound HTTPS / WSS / Presigned S3 PUT
                                          v
+-----------------------------------------------------------------------------------+
|                            APPLICATION / CLOUD ZONE                               |
|                                                                                   |
|  +---------------------------+        +----------------------------------------+  |
|  | Next.js Web Application   | HTTPS  | FastAPI Control Plane (apps/api)       |  |
|  | (apps/web)                +------->+  • REST API (/api/v1) + OpenAPI 3.1    |  |
|  |  • App Router + TS        |        |  • AuthN/AuthZ (JWT + Argon2id + RBAC) |  |
|  |  • Tailwind + shadcn/ui   |        |  • Domain Services & Validation        |  |
|  |  • MapLibre GL            |        |  • Structured JSON Logging (structlog) |  |
|  +---------------------------+        +-----+--------------------+-------------+  |
|                                             |                    |                |
|                             SQLAlchemy 2.0  |                    | Presigned URLs |
|                             + Alembic       v                    v                |
|                                    +-----------------+  +----------------------+  |
|                                    | PostgreSQL 16   |  | S3-Compatible Store  |  |
|                                    | (PostGIS ready) |  | (MinIO / AWS S3 / R2)|  |
|                                    +-----------------+  +----------+-----------+  |
|                                                                    |              |
|                                             Job Queue / Async      | Media Read   |
|                                             (Phase 3+)             v              |
|                                                         +----------------------+  |
|                                                         | AI Inference Worker  |  |
|                                                         | (services/ai-worker) |  |
|                                                         | • Ultralytics YOLO   |  |
|                                                         | • PyTorch + OpenCV   |  |
|                                                         | • Versioned Models   |  |
|                                                         +----------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 2. Core Architectural Principles

### 2.1 Clear Frontend / Backend Separation & Typed Contracts
- **`apps/web` (Next.js App Router + TypeScript)** is purely a presentation and workflow orchestration client. It contains zero database credentials, zero S3 secrets, and zero inference code.
- **`apps/api` (FastAPI + Pydantic v2)** owns all domain logic, validation, database persistence, authentication, and storage signing.
- **Typed Contract Pipeline:** FastAPI generates an OpenAPI 3.1 schema exported to `packages/contracts/openapi.json` via `apps/api/scripts/export_openapi.py`. Frontend TypeScript types in `apps/web/src/types/api.ts` strictly mirror these schemas and are verified in automated tests.

### 2.2 Isolated ESP32-CAM Access Point & Future Edge Gateway Design
Because the AI Thinker ESP32-CAM runs as an isolated Wi-Fi Access Point (`SSID: agroDrone`, static IP `192.168.4.1`, MJPEG stream on `:81/stream`):
1. **No Cloud-to-Device Inbound Access:** A cloud-hosted FastAPI server or remote browser on the internet **cannot** reach `192.168.4.1`. The backend enforces `ALLOW_DIRECT_LOCAL_CAMERA_PROBE=false` by default to prevent SSRF or misleading connection failures.
2. **Phase 3 Immediate Operational Workflow (Manual / Offline Capture Upload):** Operators capture still frames or video clips while connected to `agroDrone` (or from SD card), then reconnect to internet/LAN and upload media via AgroDrone's web UI directly into S3-compatible storage using short-lived presigned URLs for server-side AI analysis.
3. **Phase 4 Field Edge Gateway (`services/edge-gateway`):**
   - Runs on an operator laptop, ruggedized tablet, or Raspberry Pi Zero 2 W / Pi 4 / Pi 5 with dual network interfaces (e.g., WLAN0 connected to `agroDrone` AP + USB LTE modem or WLAN1 connected to internet), OR operates in **Store-and-Forward** mode (local SQLite queue + disk buffer while in the field, syncing automatically once uplink returns).
   - **Control Channel:** Outbound TLS 1.3 connection to FastAPI (`POST /api/v1/gateway/heartbeat`, `POST /api/v1/gateway/sessions`). Authenticated via provisioned per-gateway asymmetric key / scoped device token (rotatable, revocable).
   - **Media Upload Path:** Gateway pulls frames/MJPEG snapshots from `http://192.168.4.1:81/stream` locally, computes SHA-256 checksums, requests presigned S3 upload URLs from FastAPI, and uploads immutable raw frames without proxying binary payloads through the API server.
   - **Live Viewing Relay (Phase 4):** When uplink bandwidth permits, the gateway transcodes or relays low-FPS H.264/WebRTC or throttled JPEG snapshots (`1–5 FPS` suitable for cellular links and OV2640 bandwidth) to an authenticated media relay (e.g., MediaMTX / LiveKit) authorized by FastAPI session tokens. Never exposes raw unauthenticated MJPEG to the public internet.

See [docs/hardware/esp32-cam-gateway-spec.md](./docs/hardware/esp32-cam-gateway-spec.md) for full protocol details.

### 2.3 Server-Side AI Detection Pipeline & Scientific Integrity
- **First Working AI Target (Phase 3):** Image upload → validation (MIME type, magic bytes, max size, resolution) → immutable storage in S3/local bucket → server-side object detection via Ultralytics YOLO + PyTorch + OpenCV → persisted `detection_jobs` + `detection_items` with bounding boxes, confidence scores, model ID, weights SHA-256, and human review workflow.
- **Explicit Model Capability Boundaries:**
  - Pre-trained generic YOLO weights (trained on MS COCO 80 classes) can detect broad baseline classes (e.g., `person`, `bird`, `dog`, `horse`, `sheep`, `cow`, `car`, `truck`).
  - Generic YOLO weights **cannot reliably detect** agricultural targets such as **snakes, hedgehogs, small insects, weeds, nutrient deficiencies, or specific crop diseases** without dedicated domain datasets, balanced annotations, resolution-aware tiling (critical for OV2640 aerial views), and recorded evaluation metrics (mAP@0.5, precision, recall, confusion matrix on held-out field imagery).
  - Every `DetectionJob` records `model_name`, `model_version`, `dataset_provenance`, and `capability_scope` so agronomists never mistake an experimental baseline for a validated clinical/pest diagnostic model.
- **Compute Separation:** FastAPI handles lightweight API I/O; heavy PyTorch/YOLO inference runs behind an abstract `InferenceService` interface that starts as an isolated background worker process in Phase 3 and scales cleanly to dedicated GPU/CPU worker containers (`services/ai-worker`) backed by a task queue (Redis/RQ or PostgreSQL `SKIP LOCKED` job table).

### 2.4 Hardware & Telemetry Honesty
- The E88 drone + ESP32-CAM stack does **not** provide MAVLink telemetry, GPS lock, IMU attitude, barometric altitude, or battery percentage over API.
- The `Device` model stores an explicit `connectivity_mode` (`isolated_ap`, `edge_gateway`, `manual_import`) and a `capabilities` manifest (`supports_gps`, `supports_battery_telemetry`, `supports_mavlink`, `supports_multispectral_nir`, `supports_live_stream`) — all truthfully `false` except local MJPEG streaming for the ESP32-CAM.
- Mission logs (`Mission`) accept **operator-entered metadata** (target field, flight notes, approximate altitude band, manual weather notes, start/end timestamps) instead of fabricating sensor streams.

---

## 3. Database Architecture & Migration Strategy

### 3.1 Engine & Portability
- **Primary Database:** PostgreSQL 16 (configured in `docker-compose.yml` and `.env.example`, ready for PostGIS spatial indexing in Phase 2+).
- **ORM & Migrations:** SQLAlchemy 2.0 declarative models + Alembic migrations (`apps/api/alembic`).
- **Cross-Dialect Foundation Types (`app/db/types.py`):** Uses portable `GUID` (native `UUID` on PostgreSQL, `CHAR(36)` on SQLite) and `JSONVariant` (`JSONB` on PostgreSQL, `JSON` on SQLite). This guarantees that:
  - Production and Docker run with PostgreSQL native `UUID` and `JSONB`.
  - Developers without local Docker/Postgres and fast CI unit/integration tests run the exact same Alembic migrations and SQLAlchemy queries against SQLite without mocks.

### 3.2 Core Domain Entities (Initialized in Migration `0001`)

| Table | Purpose | Key Fields |
| --- | --- | --- |
| `users` | Platform operators & agronomists | `id`, `email` (unique), `full_name`, `password_hash` (Argon2id), `role` (`admin`, `agronomist`, `operator`, `viewer`), `is_active` |
| `fields` | Agricultural parcels / plots | `id`, `name`, `code`, `crop_type`, `area_hectares`, `boundary_geojson`, `centroid_lat`, `centroid_lng`, `notes` |
| `devices` | Drones, cameras, & edge gateways | `id`, `name`, `device_type`, `hardware_model`, `connectivity_mode`, `local_endpoint_url`, `capabilities`, `last_seen_at` |
| `missions` | Field survey & capture sessions | `id`, `field_id`, `device_id`, `operator_id`, `title`, `status`, `started_at`, `completed_at`, `operator_notes`, `metadata_json` |
| `media_assets` | Uploaded images / extracted frames | `id`, `mission_id`, `field_id`, `storage_key`, `original_filename`, `mime_type`, `byte_size`, `sha256`, `width_px`, `height_px`, `captured_at`, `geo_lat`, `geo_lng`, `geo_source` |
| `detection_jobs` | Server-side AI inference executions | `id`, `media_asset_id`, `status`, `model_name`, `model_version`, `dataset_scope`, `confidence_threshold`, `inference_ms`, `error_message` |
| `detection_items` | Individual detected bounding boxes | `id`, `job_id`, `label`, `confidence`, `bbox_x1`, `bbox_y1`, `bbox_x2`, `bbox_y2`, `review_status` (`unreviewed`, `confirmed`, `false_positive`) |
| `alerts` | Operational & validated detection alerts | `id`, `field_id`, `device_id`, `detection_job_id`, `severity`, `category`, `title`, `message`, `status`, `acknowledged_by`, `acknowledged_at` |

### 3.3 Migration Discipline
- Schema changes **always** ship as versioned Alembic revisions — never `create_all()` in production.
- Every revision must implement both `upgrade()` and `downgrade()`.
- Automated tests (`tests/test_migrations.py`) verify clean `upgrade head` → `downgrade base` → `upgrade head` cycles.

---

## 4. Security & Authentication Design

1. **Password Storage:** Argon2id hashing via `argon2-cffi` (memory-hard, resistant to GPU cracking). Plaintext passwords are never logged or returned.
2. **Session Tokens (Phase 2 Full Rollout, Primitives Active in Phase 1):**
   - Short-lived JWT access tokens (`30 min`, `HS256` / upgradeable to `RS256`/`EdDSA`) containing `sub`, `role`, `iat`, `exp`, `jti`, `type=access`.
   - Rotating refresh tokens stored hashed in PostgreSQL and delivered via `HttpOnly`, `Secure`, `SameSite=Lax` cookies.
3. **Role-Based Access Control (RBAC):**
   - `admin`: full system, user, device, and gateway credential management.
   - `agronomist`: field management, AI inference execution, detection review, reports, alert triage.
   - `operator`: mission creation, media upload, device pairing.
   - `viewer`: read-only access to dashboards, maps, and published reports.
4. **Object Storage Security:** Media buckets remain private; access uses time-limited presigned URLs validated against user permissions. Upload endpoints enforce file size limits, MIME/magic-byte verification, and SHA-256 deduplication/integrity checks.
5. **Gateway & Network Security:**
   - Cloud API rejects requests attempting to proxy arbitrary RFC-1918 / link-local URLs (SSRF prevention).
   - Edge gateways authenticate with scoped device tokens over TLS 1.3 and never require open inbound ports in the field.

---

## 5. Observability, Logging & Error Handling

- **Structured Logging (`structlog`):** Every HTTP request is assigned an `X-Request-ID` (propagated or generated UUIDv4), logging method, path, status code, latency (`duration_ms`), and error code as structured JSON in production (readable console format in local dev).
- **Consistent Error Envelope:** All API errors return a strict typed structure:
  ```json
  {
    "error": {
      "code": "FEATURE_NOT_ENABLED",
      "message": "Server-side AI inference is scheduled for Phase 3.",
      "details": null
    },
    "request_id": "a9d0...",
    "timestamp": "2026-11-19T13:50:00Z"
  }
  ```
- **Health & Readiness Endpoints:**
  - `GET /api/v1/health`: Fast liveness + database ping (`SELECT 1`) with measured DB latency.
  - `GET /api/v1/system/status`: Comprehensive subsystem state (DB dialect, storage mode, AI runtime state, edge gateway state, live record counts).
  - `GET /api/v1/system/capabilities`: Honest hardware, AI model, and module readiness manifest consumed by the frontend.

---

## 6. Frontend Design System & Application Shell

- **Framework:** Next.js App Router + React 19 + TypeScript (strict mode).
- **Styling:** Tailwind CSS v4 + custom obsidian/charcoal & emerald design tokens + Radix UI / shadcn/ui composable primitives.
- **Motion:** Framer Motion with understated, high-precision transitions (`180–240ms`, reduced-motion aware).
- **Geospatial:** MapLibre GL initialized client-side with a self-contained dark vector style (no mandatory third-party API key for local development), ready for GeoJSON field boundaries and parcel overlays in Phase 2.
- **Navigation Structure:** Persistent collapsible enterprise sidebar organized by operational workflow across all 11 platform modules, accompanied by a compact status topbar displaying live FastAPI connectivity, active environment badge, and hardware gateway state.
