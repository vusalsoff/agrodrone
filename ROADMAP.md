# AgroDrone — Engineering Roadmap

AgroDrone is delivered in disciplined, verifiable phases so every capability is backed by real infrastructure, automated tests, and honest hardware/AI boundaries.

---

## Phase 1: Architecture & Foundation *(Current — Complete)*
**Objective:** Establish a production-grade monorepo, database foundation, typed API contracts, enterprise design system, and locally runnable application shell.

- [x] Monorepo structure (`apps/web`, `apps/api`, `services/`, `packages/contracts`, `infra/`, `docs/`)
- [x] Complete system architecture & isolated ESP32-CAM Edge Gateway specification
- [x] FastAPI backend with Pydantic v2 settings, `structlog` JSON logging, request-ID middleware, standardized error handling
- [x] SQLAlchemy 2.0 core models (`users`, `fields`, `devices`, `missions`, `media_assets`, `detection_jobs`, `detection_items`, `alerts`) + Alembic migration `0001`
- [x] Security primitives (Argon2id password hashing, JWT token lifecycle) + unit tests
- [x] Live health, system status, hardware capability manifest, and paginated read endpoints
- [x] Exported OpenAPI 3.1 contract (`packages/contracts/openapi.json`) + typed frontend API client
- [x] Next.js + TypeScript + Tailwind + shadcn/ui + Framer Motion + MapLibre GL enterprise shell covering all 11 modules
- [x] Docker Compose stack (PostgreSQL 16 + MinIO S3 + FastAPI + Next.js) and zero-Docker local dev workflow
- [x] Automated backend (`pytest`, `ruff`, Alembic upgrade/downgrade) and frontend (`tsc`, `eslint`, `vitest`, `next build`) verification

---

## Phase 2: Authentication, Core Domain CRUD & Geospatial Parcels *(Current — Complete)*
**Objective:** Make user sessions, field management, interactive GeoJSON parcel mapping, device registry, mission logging, and secure media management fully operational end-to-end.

- [x] Full AuthN/AuthZ flow: registration (first-user Admin bootstrap), login/logout, Argon2id, JWT + HttpOnly rotating refresh tokens with reuse-detection family revocation, double-submit CSRF protection, sliding-window rate limiting, RBAC middleware (`admin`, `agronomist`, `operator`, `viewer`), and immutable audit logging
- [x] Field Management CRUD (`GET/POST/PATCH/DELETE /api/v1/fields`) with ownership enforcement, search/filter, WGS-84 geodesic GeoJSON polygon validation & area calculation
- [x] Interactive Field Maps: draw/edit/delete parcel polygons directly in MapLibre GL, draggable vertex handles, saved field display, offline vector grid + opt-in satellite raster basemap
- [x] Device Management CRUD with explicit hardware capability profiles (`E88`, `ESP32-CAM OV2640`, future gateways), isolated-AP safeguards, and no fabricated online presence
- [x] Mission Management CRUD & strict lifecycle transitions (`draft`, `planned`, `in_progress`, `completed`, `cancelled`), manual operator observations, and attached mission media
- [x] Secure Media Management: magic-byte signature verification, MIME & size limits, safe UUID storage keys, local disk + private S3/MinIO presigned upload/download support, gallery with authorized lightbox previews & downloads

---

## Phase 3: Server-Side Image & Video AI Object Detection *(Current — Complete)*
**Objective:** Deliver a real, production-oriented computer vision pipeline using Ultralytics YOLO, PyTorch, OpenCV, Pillow, and NumPy.

- [x] Image upload & selection workflow in `/detection` linked to existing `MediaAsset` records
- [x] Server-side Ultralytics YOLOv8n + PyTorch + OpenCV + Pillow + NumPy inference service (`services/ai-worker`) with SHA-256 checksum verification
- [x] Durable asynchronous job execution (`queued` → `processing` → `completed` / `failed` / `cancelled`) with compare-and-set claiming, crash recovery, and standalone worker CLI (`python -m app.worker`)
- [x] Sampled-frame video analysis with configurable interval, timestamp recording, per-frame annotated previews, and explicit non-full-frame notices
- [x] Interactive `DetectionInspector` in `/detection` & `/history/[jobId]` with before/after split comparison, bounding-box highlight, confidence slider, and JSON/annotated exports
- [x] Detection History (`/history`) with search, filtering (status, model, review state, date), sorting, and human review (`confirmed` / `rejected` / `uncertain` + notes) preserving original machine predictions
- [x] Modular model registry explicitly distinguishing baseline COCO weights from unavailable specialized agricultural modes (`wildlife`, `pest`, `disease`) and dataset registration (`POST /api/v1/detections/datasets`)

---

## Phase 4: Field Edge Gateway & Controlled Camera Bridging *(Complete)*
**Objective:** Safely bridge the isolated `agroDrone` ESP32-CAM Wi-Fi AP (`192.168.4.1`) to the AgroDrone platform without exposing local devices to the public internet.

- [x] `services/edge-gateway` companion daemon (standalone Python CLI `agrodrone-gateway` runnable on Windows field laptop or Raspberry Pi)
- [x] Outbound per-gateway credential authentication (SHA-256 hashed, replay-guarded), heartbeat reporting, and gateway enrollment/rotation/revocation
- [x] Store-and-forward frame capture from `http://192.168.4.1:81/stream` with local SQLite + disk offline spool and automatic upload upon uplink recovery
- [x] Controlled live monitoring relay (bounded latest-frame `StreamSession` relay) integrated into `/monitoring` with snapshot capture and YOLOv8n analysis
- [x] Honest local link diagnostics (camera FPS, frame drops, Wi-Fi SSID/RSSI, Mode A `local_dev` / Mode B `remote_cloud` connectivity — never fabricated airframe telemetry)

---

## Phase 5: Smart Analytics, Intelligent Alerts & Professional Reporting *(Complete)*
**Objective:** Transform real AgroVision detections, fields, missions, and ESP32-CAM gateway events into actionable analytics, alerts, notifications, and downloadable reports.

- [x] Real database-backed Smart Analytics Engine (`/api/v1/analytics/overview`, `/api/v1/analytics/map-summary`) with sampled-video deduplication
- [x] Configurable Alert Rules Engine (`/api/v1/alert-rules`, `/api/v1/alerts`) with YOLO class validation, deduplication, cooldowns, and gateway offline TTL evaluation
- [x] Persistent In-App Notification Center (`/api/v1/notifications`, topbar bell, `/alerts`) with honest SMTP unavailable reporting
- [x] Exportable Field, Mission, AI Detection, Device Activity & Alert History Reports (PDF, CSV with formula-injection protection, JSON) in `/reports`
- [x] Map-based analytics in `/maps` with verified geotagged media points only (never fabricated GPS)

---

## Phase 6: Cloud Deployment, DevOps & Production Infrastructure *(Prepared)*
**Objective:** Prepare AgroDrone for secure, containerized, provider-independent cloud deployment without exposing development defaults or auto-provisioning resources.

- [x] Multi-stage non-root Dockerfiles for `web`, `api`, and dedicated `ai-worker` (`infra/docker/Dockerfile.worker`) + `docker-compose.prod.yml`
- [x] PostgreSQL 16 connection pooling (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`), `/api/v1/ready` & `/api/v1/metrics` probes, and worker `--healthcheck`
- [x] Production `Settings` security validator (rejects placeholder JWT secrets, wildcard CORS, SSRF probing, or missing S3 credentials) + HTTP security headers
- [x] Private S3 bucket & lifecycle policy templates (`infra/s3/`)
- [x] GitHub Actions CI (`.github/workflows/ci.yml`) and manual approval-gated production release workflow (`.github/workflows/deploy.yml`)
- [x] Operational runbooks: `DEPLOYMENT.md`, `PRODUCTION_CHECKLIST.md`, `SECURITY.md`, `BACKUP_RESTORE.md`, `ENVIRONMENT_VARIABLES.md`, `CI_CD.md`
