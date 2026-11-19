.PHONY: help api-install api-migrate api-dev api-test api-lint web-install web-dev web-build web-test web-typecheck contracts docker-up docker-down

help:
	@echo "AgroDrone Monorepo Commands"
	@echo "  make api-install     Install FastAPI backend dependencies via uv"
	@echo "  make api-migrate     Run Alembic migrations to head"
	@echo "  make api-dev         Run FastAPI backend locally on :8000"
	@echo "  make api-test        Run backend pytest suite"
	@echo "  make api-lint        Run ruff linter on backend"
	@echo "  make web-install     Install Next.js frontend dependencies via npm"
	@echo "  make web-dev         Run Next.js frontend locally on :3000"
	@echo "  make web-build       Run production build for frontend"
	@echo "  make web-test        Run frontend Vitest suite"
	@echo "  make web-typecheck   Run TypeScript typecheck"
	@echo "  make contracts       Export OpenAPI JSON schema to packages/contracts/openapi.json"
	@echo "  make docker-up       Start full stack with Docker Compose"
	@echo "  make docker-down     Stop Docker Compose stack"

api-install:
	cd apps/api && uv sync --extra dev

api-migrate:
	cd apps/api && uv run alembic upgrade head

api-dev:
	cd apps/api && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

api-test:
	cd apps/api && uv run pytest -v

api-lint:
	cd apps/api && uv run ruff check app tests alembic

web-install:
	cd apps/web && npm install

web-dev:
	cd apps/web && npm run dev

web-build:
	cd apps/web && npm run build

web-test:
	cd apps/web && npm test

web-typecheck:
	cd apps/web && npm run typecheck

contracts:
	cd apps/api && uv run python scripts/export_openapi.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down
