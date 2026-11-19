# AgroDrone — Security Audit Report

## 1. Dependency Vulnerability Audit
- **Frontend (`npm audit`):** **0 vulnerabilities** (`docs/audit/final-verification/npm-audit.json`) after upgrading `maplibre-gl` (`5.24.1` → `6.19.0`), `next`/`eslint-config-next` (`15.5.29` → `16.4.6`), and `vitest` (`3.2.7` → `5.1.1`).
- **Python (`pip-audit`):** Not installed in local `.venv` (`pip_audit: False`); package inventory captured in `docs/audit/final-verification/python-packages.json`. CI workflow (`.github/workflows/ci.yml`) includes `uv tool run pip-audit`.

## 2. Penetration-Style Test Results (`test_ultimate_master_audit.py`)
All non-destructive penetration tests executed against local FastAPI `TestClient` **PASSED**:
- **Authentication & CSRF:** Invalid login returns `401`; cookie-authenticated `POST` without `X-CSRF-Token` returns `403`.
- **RBAC & IDOR Isolation:** `viewer` role rejected (`403`) on field/alert-rule creation; cross-user `GET`/`DELETE` on fields and `GET /api/v1/media/{id}/content` rejected (`403`).
- **SQLi & XSS Payload Handling:** SQLi/XSS strings (`'; DROP TABLE fields; -- <script>alert(1)</script>`) parameterized safely by SQLAlchemy without SQL errors.
- **Path Traversal & Spoofed Uploads:** `../../etc/passwd.jpg` sanitized to UUID `storage_key` without `..`; shell script spoofed as `image/jpeg` rejected (`422`).
- **CORS & Security Headers:** Disallowed `Origin` not echoed; `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, and `X-Request-ID` verified.
- **Gateway Replay Protection:** Reusing identical `X-Gateway-Timestamp` + `X-Gateway-Nonce` rejected (`401`).
- **Production Config Hardening:** Verified `Settings(environment="production")` rejects placeholder `JWT_SECRET_KEY`, wildcard `CORS_ORIGINS`, `ALLOW_DIRECT_LOCAL_CAMERA_PROBE=true`, and missing S3 credentials.

## 3. Remaining Security / Compliance Items
- **Ultralytics AGPL-3.0:** Commercial SaaS requires Ultralytics Enterprise License or permissive runtime replacement (`docs/AI_LICENSING.md`).
- **Python `pip-audit`:** Run in GitHub Actions CI or install `pip-audit` in a networked environment.
