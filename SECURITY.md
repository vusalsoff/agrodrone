# AgroDrone Security Architecture & Hardening

## 1. Authentication & Session Security
- **Password Hashing:** Argon2id (`argon2-cffi`) with minimum password length & complexity checks.
- **Tokens:** Short-lived JWT access tokens + rotating refresh tokens stored hashed in `refresh_tokens` with reuse detection and revocation on logout.
- **Cookies & CSRF:** HttpOnly, SameSite cookies (`COOKIE_SECURE=true` in production) with `X-CSRF-Token` validation on cookie-authenticated state-changing requests.
- **Rate Limiting:** Configurable auth endpoint rate limiting (`AUTH_RATE_LIMIT_REQUESTS` / `AUTH_RATE_LIMIT_WINDOW_SECONDS`).

## 2. Production Configuration Guards (`Settings.validate_production_hardening`)
When `ENVIRONMENT=production`, FastAPI refuses to start if:
- `JWT_SECRET_KEY` contains development placeholder markers (`local-dev-only`, `replace-with-`, `dev-only-change`, `change-me`).
- `CORS_ORIGINS` contains wildcard `"*"`.
- `ALLOW_DIRECT_LOCAL_CAMERA_PROBE` is `true` (prevents SSRF against private RFC1918 subnets).
- `STORAGE_BACKEND=s3` without credentials (unless `S3_USE_IAM_ROLE=true`).

## 3. HTTP Security Headers
Every FastAPI response sets:
- `X-Request-ID` (correlation)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`

Next.js sets `poweredByHeader: false`.

## 4. Media, CSV & Gateway Security
- **Private S3 Media:** `MediaAsset` files are never public; downloads use authorized RBAC checks and short-lived presigned URLs (`S3_PRESIGN_EXPIRE_SECONDS`).
- **Magic-Byte Validation:** Uploads validate actual file headers rather than trusting file extensions.
- **CSV Formula-Injection Protection:** Phase 5 CSV report exports neutralize leading `=`, `+`, `-`, `@`, `\t`, and `\r` characters.
- **Edge Gateway Replay Protection:** Per-gateway `agw_...` tokens are SHA-256 hashed at rest; gateway requests validate timestamp skew and nonce uniqueness via `GatewayReplayGuard`.

## 5. Non-Root Containers & Secret Hygiene
- `apps/api/Dockerfile`, `infra/docker/Dockerfile.worker`, and `apps/web/Dockerfile` all run as non-root users (`appuser` / `nextjs`).
- `.env` files are excluded by `.gitignore` and `.dockerignore`; no secrets are baked into images.
