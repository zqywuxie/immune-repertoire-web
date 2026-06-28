# Platform Domain Model

This document freezes the first set of domain boundaries used by the
frontend/backend separation migration. It complements
`docs/api/openapi-draft.yaml` and the long-form refactor plan.

## Domains

### Project

Project is the top-level workspace owned by a user. It groups input assets,
sample metadata, group specifications, background jobs, and generated results.

Current source of truth:

- SQL table: `projects`
- ORM model: `flask_app.models.database.Project`
- API: `/api/projects`

### Asset

Asset is any input, cache, or generated output registered to a project. The
current model is `ProjectAsset`; the target model keeps compatibility while
introducing storage abstraction.

Current source of truth:

- SQL table: `project_assets`
- ORM model: `flask_app.models.database.ProjectAsset`
- API: `/api/projects/{project_id}/assets`

Target fields:

```text
id
project_id
asset_type
logical_name
storage_uri
legacy_storage_path
mime_type
size
checksum
status
created_by
created_at
updated_at
```

Migration rule:

- Read `storage_uri` first when present.
- Fall back to `storage_path` while legacy records exist.
- Keep heavy metadata out of list responses.

### Job

Job is the lifecycle record for long-running analysis work. Route-specific task
state should converge into this model before workers are split out.

Current source of truth:

- SQL table: `analysis_jobs`
- ORM model: `flask_app.models.database.AnalysisJob`
- API: `/api/jobs`

Target state machine:

```text
queued -> running -> completed
queued -> running -> failed
queued -> running -> cancelled
```

Worker migration rule:

- API creates the job and stores payload.
- Worker receives only `job_id`.
- Worker reads inputs, writes progress, registers assets, and stores result.

### Result

Result is a generated analysis output that can be previewed, downloaded, reused,
or registered back to a project.

Current source of truth:

- SQL assets with `asset_type = processed_result`
- Mongo result cache for reusable analysis outputs
- File system result directories under `data/results`

Target rule:

- Results should be represented as assets.
- Job result should store structured summary and asset IDs, not large payloads.
- Preview/download should go through API authorization.

## Stable Frontend Surface

The standalone frontend should depend only on these APIs during Phase 1:

```text
GET  /api/info
GET  /api/projects
GET  /api/projects/{project_id}
GET  /api/projects/{project_id}/assets
POST /api/projects/{project_id}/assets
GET  /api/projects/{project_id}/assets/{asset_id}/preview
GET  /api/projects/{project_id}/assets/{asset_id}/download
GET  /api/projects/{project_id}/results
GET  /api/jobs
POST /api/jobs
GET  /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
```

Module-specific endpoints may still exist, but new frontend code should wrap
them behind feature API modules instead of calling them from components.

## Naming Rules

- Backend fields remain snake_case in API JSON during the Flask bridge phase.
- Frontend domain types mirror API JSON to avoid lossy translation.
- Generated API clients may introduce camelCase later if the OpenAPI generator
  handles mapping consistently.

## Phase 1 Acceptance Checklist

- `frontend/` exists and can call the Flask API through `/api`.
- Project and job data are loaded through typed API modules.
- `docs/api/openapi-draft.yaml` covers the stable frontend surface.
- CORS or dev proxy supports a standalone frontend during local development.
- Existing Flask templates remain usable while pages migrate gradually.
