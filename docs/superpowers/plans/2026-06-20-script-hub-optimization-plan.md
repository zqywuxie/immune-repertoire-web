# Script Hub Optimization Plan

## Objective

Optimize Script Hub so it has a unified module UI, supports multiple background analyses, keeps progress/results visible per job, and can safely absorb remaining `_reference/anal_pipeline` modules without continuing to grow one monolithic frontend/backend file.

## Current Findings

- Frontend Script Hub is centered on one large template and one singleton JS object:
  - `flask_app/templates/analysis/script_hub.html`
  - `flask_app/static/js/script_hub.js`
- Current frontend state is single-active-task oriented: `activeModule`, `inspectData`, `result`, `activeTaskId`, `taskPollTimer`.
- Backend Script Hub uses process-local execution state:
  - `flask_app/routes/api_script_hub.py`
  - `_script_executor = ThreadPoolExecutor(max_workers=2)`
  - `_script_tasks` in memory
- Completed Script Hub results already have useful persistence/reuse pieces through MongoDB/project assets:
  - `flask_app/services/mongo_service.py`
  - `flask_app/services/project_asset_service.py`
- Existing SQL models can inform the durable job shape, but Script Hub should get a dedicated job service instead of forcing all behavior into the older `AnalysisService` path:
  - `flask_app/models/database.py`
  - `flask_app/services/analysis_service.py`

## Recommended Architecture

Build Script Hub around three layers:

1. Module registry
   - A central catalog defines module id, label, description, inputs, parameters, inspect endpoint, run endpoint, result behavior, and artifact types.
   - Existing modules are wrapped first; new modules are added only after the registry is stable.

2. Job service
   - A backend service creates, lists, updates, and completes jobs.
   - The current `_script_tasks` dict can remain temporarily as live execution state, but SQL/Mongo-backed job records become the source of truth for page reload and completed results.

3. Frontend task center
   - The page no longer treats one run as the global result.
   - Jobs are shown by module and status: queued, running, completed, failed, cancelled.
   - Selecting a job displays its progress history or result artifacts.

## Phase 1: Frontend Stabilization

Goal: make the existing UI internally module-aware without changing backend behavior.

Files:
- `flask_app/static/js/script_hub.js`
- `flask_app/templates/analysis/script_hub.html`
- optional: `flask_app/static/css/script_hub.css`

Tasks:
- Add a JS module catalog mirroring the current backend module list.
- Move module labels, run labels, inspect labels, result summary labels, and endpoint metadata into that catalog.
- Convert singleton fields toward per-module state:
  - `inspectDataByModule`
  - `selectedJobByModule`
  - `jobs`
  - `pollTimersByJob`
- Keep current form IDs, `data-module` sections, endpoints, and payloads.
- Move large inline Script Hub CSS out of the template into `static/css/script_hub.css`.

Acceptance:
- Existing inspect/run/result flows still work exactly as before.
- Switching modules no longer clears unrelated module state.

## Phase 2: Multi-Job Frontend

Goal: allow the UI to track more than one running/completed job.

Files:
- `flask_app/static/js/script_hub.js`
- `flask_app/templates/analysis/script_hub.html`
- `flask_app/static/css/script_hub.css`

Tasks:
- Add a job panel to the Script Hub page.
- Store jobs client-side by `task_id/job_id`.
- When a run starts, add a job card instead of replacing the single global progress/result area.
- Poll each running job independently.
- Let users select any completed job to render its result.
- Keep the current result buttons, but bind them to the selected job result.

Acceptance:
- Start job A, switch module, start job B, both continue polling.
- Completed job A remains selectable after job B starts.
- Failed jobs remain visible with error details.

## Phase 3: Backend Job API Compatibility Layer

Goal: add generic job APIs while keeping existing module-specific endpoints stable.

Files:
- `flask_app/routes/api_script_hub.py`
- `flask_app/services/script_hub_job_service.py`
- `flask_app/tests/test_script_hub_api.py`

New endpoints:
- `GET /api/script-hub/jobs`
- `GET /api/script-hub/jobs/<job_id>`
- `POST /api/script-hub/jobs`
- `POST /api/script-hub/jobs/<job_id>/cancel`

Compatibility:
- Keep existing endpoints:
  - `POST /api/script-hub/<module>/inspect`
  - `POST /api/script-hub/<module>/run`
  - `GET /api/script-hub/task/<task_id>`
- Existing `/run` responses should include both `task_id` and `job_id` when job persistence is enabled.

Tasks:
- Extract task state helpers from `api_script_hub.py` into `script_hub_job_service.py`.
- Add job listing and status lookup.
- Keep existing result serving path and traversal protection.
- Preserve current signature reuse behavior.

Acceptance:
- Existing tests pass.
- New tests cover multiple queued jobs, job listing, status polling, and failed job error preservation.

## Phase 4: Durable Job Store

Goal: page reload should recover completed/running/failed job records.

Files:
- `flask_app/models/database.py`
- `flask_app/services/script_hub_job_service.py`
- `flask_app/routes/api_script_hub.py`
- `flask_app/services/mongo_service.py`
- `flask_app/services/project_asset_service.py`

Recommended model approach:
- Prefer a dedicated `ScriptHubJob` SQLAlchemy model if schema change is acceptable.
- If avoiding a new table, use `Analysis` carefully with `type = "script_hub:<module>"`, but this is less clean because Script Hub jobs are not always file-upload analyses.

Minimum durable fields:
- `id`
- `module`
- `project_id`
- `status`
- `progress`
- `stage`
- `detail`
- `history`
- `input_assets`
- `config_json`
- `analysis_signature`
- `result`
- `output_base`
- `created_at`
- `started_at`
- `completed_at`
- `error_message`

Tasks:
- Create job records before submitting executor work.
- Update durable progress during `_record_stage`.
- Persist completed/failed state in `_complete_script_task`.
- On app startup or first job listing, mark stale `running` jobs as `interrupted` if they have no live in-memory task.

Acceptance:
- Refreshing the page keeps completed and failed jobs visible.
- Reused cached results appear as completed jobs.
- Restarted server does not show orphaned jobs as actively running.

## Phase 5: Backend Module Registry

Goal: stop adding new module logic directly into `api_script_hub.py`.

New package:
- `flask_app/services/script_hub_modules/__init__.py`
- `flask_app/services/script_hub_modules/base.py`
- `flask_app/services/script_hub_modules/registry.py`
- wrappers for existing modules:
  - `db_alignment.py`
  - `profile.py`
  - `pep_analysis.py`
  - `pgen_analysis.py`
  - `topclone.py`
  - `umap.py`
  - `umapin.py`
  - `volcano.py`
  - `ml.py`
  - `mait_nkt.py`

Module contract:
- `id`
- `label`
- `description`
- `category`
- `input_schema`
- `parameter_schema`
- `inspect(payload)`
- `run(payload, progress_callback)`
- `normalize_result(result)`
- `artifact_types`

Tasks:
- Start by wrapping one low-risk module, then migrate the rest gradually.
- `GET /api/script-hub/modules` should read from the registry.
- Keep route-level compatibility wrappers until all frontend code is migrated.

Acceptance:
- Adding a new module no longer requires editing many hard-coded frontend/backend switches.

## Phase 6: Integrate Remaining Reference Modules

Priority:

1. Cibersort / Box_Deconv preset
   - Paths:
     - `_reference/anal_pipeline/Cibersort_260308/`
     - `_reference/anal_pipeline/Box_Deconv_260301/`
   - Reuse existing boxplot service as a preset.
   - Lowest risk and useful for validating the registry.

2. Deconv
   - Paths:
     - `_reference/anal_pipeline/Deconv_250301/run_DCTD.py`
     - `_reference/anal_pipeline/Deconv_250301/prediction_DAISM.py`
   - Add module id: `deconv`
   - Inputs: expression matrix, mode/coarse/fine, model path, scale, dataset name.
   - Outputs: prediction table, optional grouped boxplots, ZIP.

3. GeneLink
   - Path:
     - `_reference/anal_pipeline/GeneLink_260301/make_cell_gene_link_plot.py`
   - Add module id: `genelink`
   - Inputs: cell fraction table, expression matrix.
   - Parameters: top variable genes, FDR toggle, correlation thresholds.
   - Outputs: PNG/PDF link plot, correlation tables, ZIP.

4. ML_260526 enhancement
   - Paths:
     - `_reference/anal_pipeline/ML_260526/`
   - Extend existing `ml-analysis` instead of adding a separate module.
   - Add usage-folder traversal and cross-group mode after the job UI is stable.

Already-covered reference modules should remain folded into existing modules:
- DB
- Profile/BoxPlot
- Pep
- Pgen
- TopClone
- UMAP
- UMAPin
- Volcano
- MAIT/NKT

## Verification

Backend:
- `pytest flask_app/tests/test_script_hub_api.py`
- `pytest flask_app/tests/test_script_hub_json_safety.py`
- `pytest flask_app/tests/test_project_asset_service.py`
- Add new tests for:
  - `POST /api/script-hub/jobs`
  - `GET /api/script-hub/jobs`
  - concurrent job status tracking
  - signature reuse as completed job
  - failed job status and error detail
  - stale running job recovery

Frontend/manual:
- Run Flask locally and test Script Hub in browser.
- For at least two existing modules, start one job, switch modules, start another job, and verify both progress cards update.
- Verify completed job selection renders correct viewer/ZIP actions.
- Verify long paths and dense parameter panels remain readable on desktop and tablet widths.
- Use Playwright screenshots after UI changes for desktop and mobile/tablet regression.

## Execution Order

1. Frontend module catalog and per-module state.
2. Multi-job frontend panel over current task API.
3. Backend job service and generic job endpoints.
4. Durable job persistence.
5. Backend module registry.
6. Add Cibersort/Box_Deconv preset.
7. Add Deconv.
8. Add GeneLink.
9. Extend ML_260526 behavior.
