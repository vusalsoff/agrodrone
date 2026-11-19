# AgroDrone — Bug Fix & Remediation Summary

1. **Dead Code Removed:** Deleted unused `apps/api/app/api/v1/endpoints/resources.py` (superseded by `alerts.py` in Phase 5).
2. **Frontend Critical/High Dependency Vulnerabilities Remediated (`npm audit`: 6 → 0):**
   - Upgraded `maplibre-gl` `5.24.1` → `^6.19.0` (fixes `GHSA-jrc7-96c5-q579`).
   - Upgraded `next` & `eslint-config-next` `15.5.29` → `^16.4.6` (fixes `postcss` `GHSA-qx2v-qp2m-jg93` & related advisories).
   - Upgraded `vitest` `3.2.7` → `^5.1.1` (fixes `@vitest/mocker` & `tinypool` advisories).
3. **MapLibre GL 6.19.0 + Next.js 16 Turbopack WebWorker Fix:**
   - Playwright live browser testing caught `Error: Worker failed to load` in MapLibre GL 6.19.0 under Next.js 16 Turbopack.
   - Copied `maplibre-gl-worker.mjs` to `apps/web/public/maplibre-gl-worker.mjs`, configured `maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs")` in `map-viewport.tsx`, and copied `public/` in `apps/web/Dockerfile`.
4. **React 19 / ESLint 9 Hooks Compliance (`map-viewport.tsx`, `eslint.config.mjs`):**
   - Moved ref updates out of render into `React.useEffect` to satisfy `react-hooks/refs`.
   - Migrated `eslint.config.mjs` to Next 16 native flat config with `0` errors and `0` warnings.
