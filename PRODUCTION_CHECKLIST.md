# AgroDrone Production Readiness Checklist

Complete every item before switching `ENVIRONMENT=production` or routing real user traffic:

## Secrets & Authentication
- [ ] `JWT_SECRET_KEY` generated with `python -c "import secrets; print(secrets.token_urlsafe(48))"` (never a dev placeholder).
- [ ] `COOKIE_SECURE=true` and `COOKIE_SAMESITE=strict` (or `lax` if cross-subdomain) over HTTPS only.
- [ ] `CORS_ORIGINS` restricted to exact HTTPS frontend origins (no `*`).
- [ ] First admin account bootstrapped and strong password policy verified.

## Database & Storage
- [ ] PostgreSQL 16 provisioned with TLS (`sslmode=require`) and connection pooling (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`).
- [ ] Automated daily PostgreSQL backups verified with a test restore (`BACKUP_RESTORE.md`).
- [ ] `alembic upgrade head` executed and `GET /api/v1/ready` returns `200 OK`.
- [ ] Private S3 bucket configured with `infra/s3/bucket-policy-example.json` (public access blocked) and `infra/s3/lifecycle-policy-example.json`.

## AI Worker & Edge Gateway
- [ ] `AI_WORKER_MODE=external` on the API; dedicated `app.worker` service running with `>= 2 GB` RAM.
- [ ] `ALLOW_DIRECT_LOCAL_CAMERA_PROBE=false` enforced in API configuration (SSRF guard).
- [ ] ESP32-CAM gateway tokens enrolled per device, stored only as SHA-256 hashes, and tested over Mode B HTTPS.

## Observability & CI/CD
- [ ] `LOG_FORMAT=json` enabled; reverse proxy preserves `X-Request-ID`.
- [ ] Optional `SENTRY_DSN` and `SMTP_HOST`/`SMTP_FROM_EMAIL` configured if error tracking or email alerts are desired.
- [ ] GitHub `production` environment configured with Required Reviewers before using `.github/workflows/deploy.yml`.
