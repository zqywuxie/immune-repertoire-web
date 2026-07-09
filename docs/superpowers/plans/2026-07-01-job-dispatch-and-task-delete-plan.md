# Job Dispatch And Task Delete Plan

## Goals

1. Make `/api/jobs` actually execute analysis work instead of leaving jobs in `queued`.
2. Add Tasks/Job Monitor support for deleting jobs, deleting attached results, and multi-select batch deletion.
3. Keep Flask legacy and React/FastAPI-era surfaces consistent while avoiding another split-brain job implementation.

## Root Cause Summary

- `JOB_QUEUE=redis` is set in `.env`, so Flask `POST /api/jobs` submits to `RedisJobQueue`. If no RQ worker is running, jobs remain `queued`.
- FastAPI `backend-api/app/api/jobs.py` has a separate job implementation that writes SQL directly and starts daemon threads. It bypasses Flask `get_job_queue()`, ignores `JOB_QUEUE`, and can use a different database from Flask workers.
- FastAPI `JobRepository` assumes an `analysis_jobs.job_id` column, but Flask ORM `AnalysisJob` uses `id` as the canonical job id and only exposes `job_id` in `to_dict()`.
- Some worker tasks call `BackgroundJobService.upsert_job()` incorrectly with keyword args instead of an updates dict, notably `analysis_workers/tasks/analysis.py`.
- Current delete endpoints delete only job records, not output assets, result directories, Mongo cached results, or linked child jobs/results in a complete way.

## Recommended Implementation

### 1. Stabilize Job Dispatch

Primary decision: use Flask `AnalysisJob.id` as the canonical job id everywhere. Do not require a physical `job_id` column.

Files:

- `backend-api/app/repositories/jobs.py`
- `backend-api/app/api/jobs.py`
- `backend-api/app/services/job_service.py`
- `flask_app/services/job_queue.py`
- `analysis_workers/tasks/analysis.py`
- `analysis_workers/tasks/heatmap.py`
- `analysis_workers/tasks/statistical.py`
- `analysis_workers/tasks/ppt.py`

Steps:

1. Rewrite FastAPI job repository SQL to use `id` only:
   - INSERT columns should not include `job_id`.
   - `get_by_id`, `update_status`, `delete`, `set_cancel_requested` should use `WHERE id = :jid`.
   - `_to_dict()` should return `job_id: id` for frontend compatibility.
2. In FastAPI `submit_job`, either:
   - Preferred: call the shared Flask `BackgroundJobService.create_job()` and `get_job_queue().submit(...)`, so FastAPI and Flask use the same queue behavior; or
   - Transitional: keep FastAPI SQL creation but replace daemon-thread dispatch with the same worker selection logic as `flask_app/services/job_queue.py`.
3. Make queue behavior safe for local development:
   - If `JOB_QUEUE=redis` but Redis/RQ enqueue fails, return a clear 503 with `"Worker queue unavailable"` rather than silently leaving queued.
   - Add a documented local fallback: `JOB_QUEUE=threadpool` for development, or introduce `JOB_QUEUE=auto` that uses Redis only when reachable.
   - Update startup docs or `.env.local.example`; avoid silently changing production `.env`.
4. Fix worker `upsert_job` calls:
   - Replace `service.upsert_job(job_id, status="running", progress=0, stage=stage)` with `service.upsert_job(job_id, {"status": "running", "progress": 0, "stage": stage})`.
   - Audit all `analysis_workers/tasks/*.py` for the same signature bug.
5. Add schema sanity checks:
   - Test that the repository works against the Flask ORM-created schema without `job_id`.
   - Optional `/api/health` detail or startup warning if `analysis_jobs` is missing required columns.

### 2. Add Delete With Attached Results

Backend should own all destructive behavior; frontend should only pass job ids and a `delete_results` flag.

Files:

- `backend-api/app/repositories/jobs.py`
- `backend-api/app/services/job_service.py`
- `backend-api/app/api/jobs.py`
- `backend-api/app/repositories/assets.py`
- `backend-api/app/services/asset_service.py`
- `flask_app/services/background_job_service.py`
- `flask_app/routes/api_jobs.py`
- `flask_app/services/project_asset_service.py` for reference
- `flask_app/services/mongo_service.py` if cache deletion helpers exist or need adding

API shape:

- `DELETE /api/jobs/{job_id}?delete_results=1`
- `POST /api/jobs/bulk-delete`

Bulk body:

```json
{
  "job_ids": ["job-a", "job-b"],
  "delete_results": true
}
```

Rules:

1. Only terminal jobs can be deleted: `completed`, `failed`, `cancelled`, `interrupted`.
2. Running/queued jobs return `409` for single delete and per-item skipped/error records for bulk delete.
3. Deleting a parent job should delete hidden child jobs as current Flask behavior already does.
4. When `delete_results=false`, delete only job records and child job records.
5. When `delete_results=true`, also delete:
   - `project_assets` rows where `asset_type='processed_result'` and metadata has `job_id`, `task_id`, or lineage matching the job.
   - `job_assets` lineage rows if table exists.
   - Output files/dirs from registered assets.
   - Result directories from `job.result.output_base`, `chart_results[*].output_base`, and safe URLs that map under the configured results root.
   - Mongo cached results for the job/signature where supported.
6. Path deletion must be guarded:
   - Resolve paths before deletion.
   - Only delete under allowed roots such as `flask_app/data/results`, `data/results`, or managed project result directories.
   - Delete directories only when they are job-specific result directories, not arbitrary parents.

Response shape:

```json
{
  "success": true,
  "deleted_job": {...},
  "deleted_children": 2,
  "deleted_assets": ["asset-id"],
  "deleted_paths": ["..."],
  "skipped_paths": ["..."],
  "errors": []
}
```

Bulk response:

```json
{
  "success": true,
  "results": [
    {"job_id": "job-a", "success": true, "deleted_assets": []},
    {"job_id": "job-b", "success": false, "error": "JOB_NOT_TERMINAL"}
  ]
}
```

### 3. Add Multi-Select Delete In Tasks UI

Main React path:

- `frontend/src/pages/analysis/JobMonitor.tsx`
- `frontend/src/features/jobs/JobRow.tsx`
- `frontend/src/features/jobs/JobList.tsx`
- `frontend/src/shared/api/jobs.ts`

Legacy Flask path if still reachable:

- `flask_app/templates/analysis/script_hub_jobs.html`
- `flask_app/static/js/script_hub_jobs.js`
- `flask_app/static/css/script_hub_jobs.css`

React UI behavior:

1. Add checkbox selection to each visible job row.
2. Add toolbar above the list:
   - selected count
   - select all visible
   - clear selection
   - checkbox/toggle: "Delete attached results"
   - delete selected button
3. Keep row click for job details; checkbox clicks must stop propagation.
4. Disable delete for active jobs or allow selection but report skipped active jobs in confirmation.
5. Confirmation text should show:
   - total selected
   - terminal jobs that will be deleted
   - running/queued jobs that will be skipped
   - whether result files/assets will be deleted
6. After delete:
   - invalidate job list cache
   - refresh polling immediately
   - clear deleted selected ids
   - clear detail panel if the selected job was deleted

API client additions:

- `deleteJob(jobId, { deleteResults })`
- `bulkDeleteJobs(jobIds, { deleteResults })`

### 4. Verification

Backend tests:

1. Repository test: insert/create job without `job_id` column assumption; `job_id` in response equals `id`.
2. Worker dispatch test: submit a mock-supported module, assert status transitions to `running` then terminal.
3. Failure test: worker returns `success: false`; job becomes `failed`, not stuck `queued`.
4. Analysis worker test: `analysis.execute*` no longer raises `upsert_job()` signature `TypeError`.
5. Delete tests:
   - terminal job record only
   - active job returns/skips `409`
   - delete with result asset removes `project_assets` row and safe file
   - bulk delete mixed success/failure

Frontend tests/build:

1. Add or update JobMonitor tests for multi-select toolbar and delete API calls.
2. Run:

```bash
python -m pytest backend-api/tests/
npm run typecheck
npm run build
```

Manual end-to-end:

1. Start local dev with `JOB_QUEUE=threadpool`, or start Redis plus an RQ worker if `JOB_QUEUE=redis`.
2. Submit a `charts.combined` job from ScriptHub.
3. Confirm status changes: `queued -> running -> completed/failed` with visible error if failed.
4. Open Job Monitor, select the job, inspect payload/details.
5. Delete only job record; confirm result assets remain.
6. Submit another job, delete with attached results; confirm Job Monitor, project Results, asset preview/download, and result directory are removed.

## Execution Order

1. Fix backend job schema/dispatch and worker signature bugs first.
2. Add backend delete service and API support.
3. Add React Job Monitor multi-select UI and API client methods.
4. Optionally align legacy Flask Tasks UI.
5. Add tests and run full verification.
