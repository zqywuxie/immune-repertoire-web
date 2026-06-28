# Immune Repertoire Frontend

Standalone frontend shell for the frontend/backend separation migration.

## Development

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to the Flask backend. By default it targets:

```text
http://127.0.0.1:5000
```

Override it with:

```bash
VITE_API_TARGET=http://127.0.0.1:5000 npm run dev
```

For a deployment where the frontend calls Flask cross-origin directly, set the
backend environment variable:

```bash
FRONTEND_ORIGINS=http://localhost:5173
```

## Migration Scope

Phase 1 keeps Flask as the backend and uses this app as the new frontend shell
for project, asset, job, and result workflows. New UI code should call API
modules under `src/shared/api` instead of calling `fetch` from components.
