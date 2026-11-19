# AgroDrone CI/CD Pipeline Guide

AgroDrone uses GitHub Actions workflows located in `.github/workflows/`:

## 1. Continuous Integration (`.github/workflows/ci.yml`)
Triggered on `push` and `pull_request` to `main` and `develop`:
- **`backend` job:**
  - Installs dependencies with `uv sync --extra dev --extra s3`.
  - Runs `ruff check app tests`.
  - Verifies `alembic upgrade head`.
  - Runs full `pytest` suite (including migration, OpenAPI contract, RBAC, Phase 3–5 tests).
  - Runs `pip-audit` vulnerability scan.
- **`frontend` job:**
  - Installs dependencies with `npm ci`.
  - Runs `npm run typecheck`, `npm run lint`, `npm run test` (Vitest), and `npm run build` (Next.js production build).
  - Runs `npm audit --audit-level=high`.
- **`containers` job:**
  - Runs after `backend` and `frontend` pass.
  - Verifies Docker builds for `apps/api/Dockerfile`, `infra/docker/Dockerfile.worker`, and `apps/web/Dockerfile` with `push: false` (no registry push on CI).

## 2. Production Release (`.github/workflows/deploy.yml`)
- Triggered **manually only** via `workflow_dispatch` with an immutable `image_tag`.
- Protected by GitHub `environment: production` — configure **Required Reviewers** in repository Settings -> Environments so no release can proceed without explicit human approval.
- Never pushes to GitHub or provisions cloud infrastructure automatically.
