# AgroDrone — Infrastructure Verification Report

## 1. Local Infrastructure Availability
- **Docker:** `NOT INSTALLED` (`DOCKER_NOT_INSTALLED`).
- **PostgreSQL (`psql`):** `NOT INSTALLED` locally.
- **MinIO:** Not running locally (no Docker).

## 2. Verification Status
- **Dockerfiles (`apps/api/Dockerfile`, `infra/docker/Dockerfile.worker`, `apps/web/Dockerfile`):** `BLOCKED` (authored with multi-stage builds, non-root users, `SIGTERM`, healthchecks, and `public/maplibre-gl-worker.mjs`, but container image builds were **not executed** locally).
- **PostgreSQL 16 & Alembic (`0001`–`0005`):** `PARTIALLY VERIFIED` (full `upgrade` / `downgrade` / `upgrade` verified on SQLite; PostgreSQL pooling configured in `session.py`, live PostgreSQL 16 execution `BLOCKED` without Docker/PG).
- **S3 / MinIO Adapter:** `PARTIALLY VERIFIED` (boto3 presign unit-tested in `test_s3_presigned_upload_and_download_adapter`; live MinIO bucket integration `BLOCKED` without Docker).
- **CI/CD Workflows (`.github/workflows/ci.yml`, `deploy.yml`):** `PARTIALLY VERIFIED` (authored with approval-gated `environment: production`; not pushed to GitHub).

## 3. Windows Docker Desktop + WSL 2 Setup Instructions
1. Enable WSL 2: `wsl --install` (run as Administrator, reboot if prompted).
2. Install Docker Desktop for Windows: `winget install Docker.DockerDesktop`.
3. Start Docker Desktop, then build and verify the production-like stack:
   ```powershell
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d --build
   ```
