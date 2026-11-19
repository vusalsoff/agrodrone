# AgroDrone API Contracts (`packages/contracts`)

This directory stores the machine-readable OpenAPI 3.1 specification exported from `apps/api`.

## Regenerating the Contract

```powershell
cd apps/api
uv run python scripts/export_openapi.py
```

The exported `openapi.json` serves as the single source of truth for typed client models in `apps/web/src/types/api.ts` and future Edge Gateway / AI Worker clients.
