# AgroDrone Phase 7 Production Release Checklist

Only items backed by direct evidence in this repository are marked `[x]`. Items marked `[ ]` require target-environment execution before production go-live.

## Application, Security & Quality
- [x] Backend lint (`ruff check`), Alembic migrations (`0001`–`0005`), and `pytest` suite passing locally.
- [x] Frontend `tsc --noEmit`, `eslint .`, Vitest suite, and `next build` production bundle passing locally.
- [x] Production `Settings` validator rejects dev placeholder `JWT_SECRET_KEY`, wildcard `CORS_ORIGINS`, SSRF probing, and missing S3 credentials.
- [x] Argon2id password hashing, JWT + rotating refresh tokens, HttpOnly cookies + CSRF protection, RBAC, and cross-user isolation tested.
- [x] CSV formula-injection protection and private media download authorization tested.
- [ ] Resolve or mitigate `npm audit` advisories (`maplibre-gl <=6.4.0` critical XSS sanitizer advisory, `next`/`postcss` high advisory) prior to public release.

## Infrastructure, Database & Storage
- [x] Multi-stage non-root Dockerfiles (`apps/api/Dockerfile`, `infra/docker/Dockerfile.worker`, `apps/web/Dockerfile`) and `docker-compose.prod.yml` authored.
- [x] PostgreSQL 16 connection pooling configured (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`) and SQLite dev compatibility verified.
- [x] Readiness (`/api/v1/ready`), health (`/api/v1/health`), metrics (`/api/v1/metrics`), and worker `--healthcheck` implemented & tested.
- [x] Private S3 bucket & lifecycle policy templates (`infra/s3/`) and backup/restore runbook (`BACKUP_RESTORE.md`) created.
- [ ] Execute `docker compose build` and live PostgreSQL 16 + MinIO integration tests in a Docker-enabled host or GitHub Actions CI.
- [ ] Configure HTTPS TLS termination, production DNS domain, and managed PostgreSQL PITR backups.

## AI Licensing, Privacy & Hardware
- [x] YOLOv8n checksum verification, CPU inference, sampled video processing, and human review verified.
- [ ] **Ultralytics AGPL-3.0 / Commercial License Review:** Ultralytics YOLOv8 (`ultralytics` package) is licensed under AGPL-3.0 unless a commercial Ultralytics Enterprise License is purchased. Legal/commercial clearance is required before proprietary SaaS distribution.
- [ ] Physical ESP32-CAM (`agroDrone` @ `192.168.4.1`) end-to-end hardware test on Windows field laptop (`docs/hardware/esp32-cam-windows-verification.md`).
