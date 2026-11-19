# AgroDrone — AI-Powered Agricultural Intelligence Platform

AgroDrone is a modular, production-oriented agricultural field monitoring platform designed to ingest imagery from drone-mounted camera hardware, execute server-side computer vision pipelines, organize agricultural parcels and missions, and deliver decision-ready field intelligence.

> **Current Stage:** Phase 6 — Cloud Deployment, DevOps & Production Infrastructure *(Prepared & Validated Locally)*.  
> All Phase 1–5 application features plus multi-stage non-root Dockerfiles (`apps/api/Dockerfile`, `infra/docker/Dockerfile.worker`, `apps/web/Dockerfile`), `docker-compose.prod.yml`, PostgreSQL 16 connection pooling, `/api/v1/ready` & `/api/v1/metrics` probes, production config security guards, GitHub Actions CI/CD workflows (`.github/workflows/ci.yml`, `deploy.yml`), S3 private bucket/lifecycle policies, and operational runbooks (`DEPLOYMENT.md`, `SECURITY.md`, `BACKUP_RESTORE.md`, `PRODUCTION_CHECKLIST.md`, `ENVIRONMENT_VARIABLES.md`, `CI_CD.md`) are in place. See [DEPLOYMENT.md](./DEPLOYMENT.md) for deployment instructions.

---

## Hardware Reality & Technical Guardrails

AgroDrone is built around real physical hardware rather than simulated telemetry:

| Component | Role | Current Capability | Explicit Limitation |
| --- | --- | --- | --- |
| **E88 Dual-Camera Drone** | Airframe / aerial platform | Manual line-of-sight flight | No MAVLink, no programmatic GPS/RTK, no battery/altitude API, no autonomous waypoint engine |
| **AI Thinker ESP32-CAM (OV2640)** | Onboard RGB camera module | Wi-Fi AP (`agroDrone`), web UI (`http://192.168.4.1`), MJPEG stream (`http://192.168.4.1:81/stream`) | Isolated local AP; unreachable from public cloud servers; RGB sensor only (cannot compute true NIR NDVI) |
| **ESP32-CAM-MB Programmer** | USB-serial flashing & bench diagnostics | Firmware updates and serial debugging | Bench-only hardware |
| **Portable USB Power Source** | Onboard / bench camera power | Untethered power for ESP32-CAM | No digital battery state-of-charge telemetry |

### Engineering Principles
1. **No Fake Telemetry:** The platform never fabricates GPS coordinates, altitude, battery percentages, wind speeds, or MAVLink links.
2. **Isolated AP Boundary:** `192.168.4.1` is strictly a local Access Point address. Cloud deployments never assume direct access; Phase 4 introduces a dedicated outbound **Field Edge Gateway** (`services/edge-gateway`).
3. **AI Model Honesty:** Phase 3 launches with server-side image upload and baseline object detection. Generic pre-trained YOLO weights (e.g., COCO) are **not** claimed to detect snakes, hedgehogs, small insects, or specific crop diseases without curated domain datasets, class-balanced training, and validated precision/recall/mAP evaluation.
4. **RGB vs. Multispectral Integrity:** OV2640 produces RGB imagery only. Future vegetative analysis will clearly label RGB visual proxies (e.g., ExG, VARI) and never mislabel them as true NIR-band NDVI.

---

## Monorepo Structure

```text
agrodrone/
├── apps/
│   ├── web/                  # Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Framer Motion + MapLibre GL
│   └── api/                  # Python FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2 + structlog
├── services/
│   ├── ai-worker/            # Phase 3: Ultralytics YOLO + PyTorch + OpenCV inference worker
│   └── edge-gateway/         # Phase 4: Local Wi-Fi bridge (192.168.4.1 -> TLS outbound relay/upload)
├── packages/
│   └── contracts/            # Exported OpenAPI 3.1 contract (openapi.json) shared across stack
├── infra/
│   └── docker/               # MinIO bucket bootstrap & container support scripts
├── docs/
│   └── hardware/             # ESP32-CAM + Edge Gateway technical specification
├── scripts/
│   └── dev.ps1               # Windows PowerShell helper for local run, migrate, test, validate
├── docker-compose.yml        # PostgreSQL 16 + MinIO (S3) + FastAPI API + Next.js Web
├── Makefile                  # Unix/macOS/WSL task runner
├── ARCHITECTURE.md           # Full system architecture, data model, security & gateway design
├── ROADMAP.md                # Phased delivery roadmap
└── .env.example              # Environment configuration template
```

---

## Quick Start (Local Development)

### Prerequisites
- **Node.js** 20+ and **npm** 10+
- **Python** 3.12+ and **uv** (`pip install uv` or standalone installer)
- *(Optional)* **Docker Desktop** for running PostgreSQL 16 + MinIO S3 locally via `docker compose up --build`

### Option A: Zero-Docker Local Development (Fastest Start)

The FastAPI backend is PostgreSQL-first for production and Docker, and supports a cross-dialect SQLite local development database (`sqlite:///./data/agrodrone_dev.db`) using the exact same SQLAlchemy 2.0 models and Alembic migrations.

1. **Configure local environment files:**
   - Backend: `apps/api/.env` (copy from `apps/api/.env.example`)
   - Frontend: `apps/web/.env.local` (copy from `apps/web/.env.example`)

2. **Install & migrate backend (`apps/api`):**
   ```powershell
   cd apps/api
   uv sync --extra dev
   uv run alembic upgrade head
   uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   API docs will be available at `http://127.0.0.1:8000/docs` and health check at `http://127.0.0.1:8000/api/v1/health`.

3. **Install & run frontend (`apps/web`):**
   ```powershell
   cd apps/web
   npm install
   npm run dev
   ```
   Dashboard will be available at `http://localhost:3000`.

4. **Windows PowerShell helper:**
   ```powershell
   .\scripts\dev.ps1 -Action validate   # Lint, migrate, pytest, typecheck, Vitest, Next build
   .\scripts\dev.ps1 -Action api        # Migrate + run FastAPI on :8000
   .\scripts\dev.ps1 -Action web        # Run Next.js on :3000
   ```

### Option B: Full Stack with Docker Compose (PostgreSQL 16 + MinIO S3)

```bash
cp .env.example .env
docker compose up --build
```

Services:
- Web Dashboard: `http://localhost:3000`
- FastAPI Backend: `http://localhost:8000`
- PostgreSQL 16: `localhost:5432`
- MinIO S3 API / Console: `http://localhost:9000` / `http://localhost:9001`

---

## Testing & Validation

```powershell
# Backend linting, migrations, unit & integration tests
cd apps/api
uv run ruff check app tests alembic
uv run alembic upgrade head
uv run pytest -v

# Export OpenAPI contract
uv run python scripts/export_openapi.py

# Frontend typecheck, lint, unit/component tests, production build
cd apps/web
npm run typecheck
npm run lint
npm test
npm run build
```

---

## Documentation
- [ARCHITECTURE.md](./ARCHITECTURE.md) — Complete system architecture, security model, DB schema, AI pipeline, and ESP32-CAM Edge Gateway specification.
- [ROADMAP.md](./ROADMAP.md) — Phase-by-phase engineering plan and acceptance criteria.
- [docs/hardware/esp32-cam-gateway-spec.md](./docs/hardware/esp32-cam-gateway-spec.md) — Field hardware constraints and gateway protocol specification.
