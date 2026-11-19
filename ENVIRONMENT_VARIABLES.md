# AgroDrone Environment Variables Reference

All runtime behavior is controlled via environment variables (see `.env.example` and `apps/api/.env.example`). Never commit real secrets.

| Variable | Default (Dev) | Production Requirement |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` |
| `LOG_LEVEL` | `INFO` | `INFO` or `WARNING` |
| `LOG_FORMAT` | `console` | `json` |
| `DATABASE_URL` | `sqlite:///./data/agrodrone_dev.db` | `postgresql+psycopg://user:pass@host:5432/agrodrone?sslmode=require` |
| `DB_POOL_SIZE` | `10` | Tune per API worker count (e.g. `10`) |
| `DB_MAX_OVERFLOW` | `20` | `20` |
| `DB_POOL_TIMEOUT` | `30` | `30` |
| `DB_POOL_RECYCLE` | `1800` | `1800` |
| `JWT_SECRET_KEY` | Dev placeholder | **Required** >=32 random chars (no dev markers) |
| `COOKIE_SECURE` | `false` | `true` (HTTPS only) |
| `COOKIE_SAMESITE` | `lax` | `strict` or `lax` |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Exact HTTPS frontend origins (no `*`) |
| `STORAGE_BACKEND` | `local` | `s3` |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | Private S3 / R2 / MinIO HTTPS endpoint |
| `S3_ACCESS_KEY_ID` | `""` | Required unless `S3_USE_IAM_ROLE=true` |
| `S3_SECRET_ACCESS_KEY` | `""` | Required unless `S3_USE_IAM_ROLE=true` |
| `S3_USE_IAM_ROLE` | `false` | `true` on AWS ECS/EKS with IAM task role |
| `S3_BUCKET_MEDIA` | `agrodrone-media` | Private bucket name |
| `AI_INFERENCE_ENABLED` | `true` | `true` |
| `AI_WORKER_MODE` | `inline_thread` | `external` (run `python -m app.worker`) |
| `AI_DEVICE` | `cpu` | `cpu` or `cuda:0` (if GPU attached) |
| `AI_WORKER_CONCURRENCY` | `1` | `1`–`4` based on CPU/RAM |
| `ALLOW_DIRECT_LOCAL_CAMERA_PROBE` | `false` | Must remain `false` (SSRF protection) |
| `EDGE_GATEWAY_ENABLED` | `true` | `true` |
| `GATEWAY_HEARTBEAT_TTL_SECONDS` | `30` | `30`–`60` |
| `SMTP_HOST` / `SMTP_FROM_EMAIL` | `""` | Optional; email alerts unavailable until set |
| `SENTRY_DSN` | `""` | Optional error reporting hook |
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | Public HTTPS API URL |
