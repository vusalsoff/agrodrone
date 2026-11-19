# AgroDrone Production Deployment Guide

AgroDrone uses a provider-independent containerized architecture with clear separation between the Next.js frontend, FastAPI control plane, independent AgroVision AI worker, managed PostgreSQL 16, private S3-compatible object storage, and the field-side ESP32-CAM Edge Gateway.

> **Important:** No cloud resources are provisioned automatically. Do not expose the ESP32-CAM (`192.168.4.1`) or local development defaults to the public internet.

---

## 1. Architecture Overview

```text
[Field: ESP32-CAM 192.168.4.1] --(Wi-Fi AP)--> [Field Laptop / Pi: agrodrone-gateway (Mode B)]
                                                           | Outbound HTTPS + SHA-256 Token + Replay Guard
                                                           v
[Browser Users] --HTTPS--> [Next.js Web (apps/web)] ---> [FastAPI Control Plane (apps/api)]
                                                           |               |
                                                           v               v
                                                  [PostgreSQL 16]   [Private S3 / MinIO]
                                                           ^               ^
                                                           |               |
                                                  [AgroVision AI Worker (app.worker)]
```

---

## 2. Hosting Options Comparison

| Component | Option A: Managed PaaS (Render / Railway / Fly.io) | Option B: AWS / GCP / Azure Containers (ECS / Cloud Run / AKS) | Option C: Self-Hosted VPS + Docker Compose |
|---|---|---|---|
| **Next.js (`apps/web`)** | Vercel or Container Service | Cloud Run / ECS Fargate | `agrodrone-web` behind Caddy / Nginx TLS |
| **FastAPI (`apps/api`)** | Web Service (Dockerfile) | ECS Fargate / Cloud Run | `agrodrone-api` behind reverse proxy |
| **AI Worker (`app.worker`)** | Background Worker (2+ GB RAM) | ECS Task / Compute Engine | `agrodrone-ai-worker` (CPU or GPU) |
| **PostgreSQL 16** | Managed Postgres (Neon / RDS / Render PG) | Amazon RDS / Cloud SQL | `postgres:16-alpine` + automated `pg_dump` |
| **Object Storage** | Cloudflare R2 / AWS S3 (Private) | Amazon S3 / GCS (Private) | MinIO with private TLS endpoint |

---

## 3. Windows-Friendly Local Production-Like Compose Setup

Once Docker Desktop is installed on Windows:

1. Copy `.env.example` to `.env.production` and set real secrets (see `ENVIRONMENT_VARIABLES.md`).
2. Start the full production-like stack:
   ```powershell
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d --build
   ```
3. Verify readiness & metrics:
   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
   Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready
   Invoke-RestMethod http://127.0.0.1:8000/api/v1/metrics
   ```

---

## 4. Database Migrations & Zero-Downtime Strategy

- Always take a PostgreSQL snapshot before applying schema changes (`BACKUP_RESTORE.md`).
- Run migrations once per release before rolling new API/worker containers:
  ```powershell
  alembic upgrade head
  ```
- Keep `AI_WORKER_MODE=external` in production so the API process never runs CPU-heavy YOLO inference on HTTP worker threads.

---

## 5. Edge Gateway Mode B (Cloud Bridging)

On a field laptop or Raspberry Pi with **two separate network interfaces** (one connected to Wi-Fi SSID `agroDrone` for `192.168.4.1`, and a second Ethernet/USB-tether/cellular interface for internet):

```powershell
agrodrone-gateway `
  --mode remote_cloud `
  --api-base-url https://api.your-domain.com `
  --gateway-id <GATEWAY_UUID> `
  --gateway-token <ONE_TIME_AGW_TOKEN>
```

The gateway initiates outbound HTTPS only and buffers captures in its local SQLite + disk spool if internet drops.
