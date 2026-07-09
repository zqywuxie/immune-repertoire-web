# ScriptHub Frontend Refactor Plan

> Updated: 2026-07-01

## Goal

Refactor the React ScriptHub wizard so it follows the original single-machine
Flask/Jinja ScriptHub behavior while keeping the new project, asset-set, and job
monitor architecture.

The target behavior is:

1. Select a project and asset set.
2. Inspect the selected assets and show only real Profile and PEP head-5 preview
   tables.
3. Select one ScriptHub module.
4. Render module-specific configuration based on the original HTML UI and the
   backend script/route parameter contracts.
5. Submit through the correct legacy ScriptHub or worker job adapter.

## Reference Sources

Original UI and frontend logic:

- `flask_app/templates/analysis/script_hub.html`
- `flask_app/static/js/script_hub.js`

Backend module contracts:

- `flask_app/routes/api_script_hub/modules_config.py`
- `flask_app/routes/api_script_hub/db_alignment.py`
- `flask_app/routes/api_script_hub/profile_analysis.py`
- `flask_app/routes/api_script_hub/boxplot.py`
- `flask_app/routes/api_script_hub/pep_analysis.py`
- `flask_app/routes/api_script_hub/pgen_analysis.py`
- `flask_app/routes/api_script_hub/topclone.py`
- `flask_app/routes/api_script_hub/umap.py`
- `flask_app/routes/api_script_hub/enrichment.py`
- `flask_app/routes/api_script_hub/umapin.py`
- `flask_app/routes/api_script_hub/ml_analysis.py`
- `flask_app/routes/api_script_hub/mait_nkt.py`

Current React implementation:

- `frontend/src/pages/analysis/ScriptHubWizard.tsx`
- `frontend/src/features/scripthub/stages/Stage2SourceInspection.tsx`
- `frontend/src/features/scripthub/stages/Stage3ModuleConfig.tsx`
- `frontend/src/features/jobs/forms/LegacyScriptHubForm.tsx`
- `frontend/src/features/jobs/forms/index.ts`
- `frontend/src/shared/api/scriptHub.ts`

## Key Findings

The original ScriptHub is a five-stage flow:

1. Project selection
2. Project data selection
3. Inspection result
4. Module selection
5. Run configuration

The new React wizard can keep its current stage names, but the second visible
wizard step must behave like the original inspection result: after asset
selection, it should show real Profile and PEP preview tables, not synthetic
column summary cards.

The original inspection preview behavior is:

- Call `/api/script-hub/data-selection/inspect`.
- Inspect the selected Profile file.
- Read the first detected PEP example file through
  `/api/script-hub/read-table-preview`.
- Render the first five rows for Profile and PEP.

Current React gaps:

- Stage 2 shows summaries and detected-column cards, not actual file head rows.
- `ScriptHubWizard` does not send `project_id` to
  `/api/script-hub/data-selection/inspect`.
- Module configuration is partially migrated, but many controls are still generic
  or free-text.
- Field-like values such as group fields, sample columns, label columns,
  category columns, range begin/end columns, CDR3 columns, and copy/count columns
  must come from inspected files and be selected from dropdowns or multi-selects.
- The `charts` module appears in the legacy module catalog, but no matching
  `/charts/inspect` or `/charts/run` route was found in
  `flask_app/routes/api_script_hub/`. It needs either a dedicated backend bridge
  or must be hidden/marked unavailable until implemented.

## Refactor Plan

### Phase 1: Fix Stage 2 Asset Inspection

Files:

- `frontend/src/pages/analysis/ScriptHubWizard.tsx`
- `frontend/src/features/scripthub/stages/Stage2SourceInspection.tsx`
- `frontend/src/shared/api/scriptHub.ts`
- `flask_app/routes/api_script_hub/modules_config.py`

Tasks:

1. Include `project_id` in the `inspectScriptHubDataSelection()` payload.
2. Add typed preview support in `frontend/src/shared/api/scriptHub.ts`:
   - `readScriptHubTablePreview({ path })`
   - response: `{ columns: string[], rows: Record<string, unknown>[], total_rows?, path? }`
3. Prefer extending `/api/script-hub/data-selection/inspect` to return:
   - `profile_preview: { path, columns, rows }`
   - `pep_preview: { path, columns, rows }`
   - existing `profile_columns`, `group_fields`, `pep_columns`, `pep_files_preview`
4. If the backend extension is too large, call the existing
   `/api/script-hub/read-table-preview` endpoint from Stage 2 for:
   - selected `profile_path`
   - first `pep_files_preview[0].path`
5. Replace Stage 2 summary cards with two preview sections:
   - Profile head-5 table
   - PEP head-5 table
6. Keep only compact metadata above each table:
   - file path/name
   - row count if available
   - column count
7. Do not show every detected field as primary content in Stage 2. Columns are
   data for Stage 3 dropdowns, not the main UI.

Acceptance:

- After inspection, Stage 2 shows exactly the selected Profile head-5 table and
  one PEP example head-5 table.
- Rows are actual file rows, not mock values or generated field-role rows.
- Wide tables scroll horizontally without breaking layout.

### Phase 2: Build a Column-Driven Source Context

Files:

- `frontend/src/pages/analysis/ScriptHubWizard.tsx`
- `frontend/src/features/jobs/forms/index.ts`
- `frontend/src/shared/api/scriptHub.ts`

Tasks:

1. Expand `ScriptHubSourceContext` to include:
   - `projectId`
   - `assetSetId`
   - `profilePath`
   - `pepPaths`
   - `transcriptomePath`
   - `profileFields`
   - `groupFields`
   - `pepColumns`
   - `chains`
   - `profilePreview`
   - `pepPreview`
2. Normalize candidate fields once in the wizard:
   - group candidates from `group_fields`
   - fallback group candidates from Profile columns excluding sample identifiers
   - PEP mapping candidates from `pep_columns`
3. Pass the same source context to all module config forms.
4. Avoid recomputing field lists independently in each form unless the module
   inspect endpoint returns a more precise set.

Acceptance:

- Stage 3 forms can render dropdowns immediately after Stage 2 inspection.
- Project asset-set context is preserved into the final run payload.

### Phase 3: Replace Generic Module Config With Legacy-Compatible Forms

Files:

- `frontend/src/features/jobs/forms/LegacyScriptHubForm.tsx`
- new folder: `frontend/src/features/scripthub/modules/`
- `frontend/src/features/scripthub/stages/Stage3ModuleConfig.tsx`
- `frontend/src/shared/api/scriptHub.ts`

Recommended structure:

- `DbAlignmentConfig.tsx`
- `ProfileConfig.tsx`
- `PepAnalysisConfig.tsx`
- `PgenAnalysisConfig.tsx`
- `TopCloneConfig.tsx`
- `UmapConfig.tsx`
- `VolcanoConfig.tsx`
- `GoKeggConfig.tsx`
- `UmapinConfig.tsx`
- `MlAnalysisConfig.tsx`
- `MaitNktConfig.tsx`
- `shared/ColumnSelect.tsx`
- `shared/ColumnMultiSelect.tsx`
- `shared/RangeColumnSelect.tsx`
- `shared/ChainPicker.tsx`
- `shared/ModuleInspectPanel.tsx`

Tasks:

1. Keep `LegacyScriptHubForm` only as a temporary fallback.
2. Route each module key to a dedicated component.
3. Use module-specific inspect endpoints where available.
4. Store selected config in the same shape expected by the run endpoint.
5. For all file-derived fields, use select controls instead of free-text inputs.
6. Render only controls relevant to the active module, matching the original
   `data-module` behavior from the old HTML.

Acceptance:

- Switching modules changes the config form completely.
- The form for each module follows the original HTML grouping and backend
  parameter names.
- No module shows a large flat list of every detected field.

### Phase 4: Module-Specific Configuration Contracts

#### db-alignment

Inspect:

- `POST /api/script-hub/db-alignment/inspect`

Run:

- `POST /api/script-hub/db-alignment/run`

UI:

- PEP path summary
- CDR3 column select from PEP columns
- Copy/count column select from PEP columns
- optional Profile path
- category multi-select from Profile columns
- pathology value selector after category inspection

Payload:

- `base_path` or `pep_paths[0]`
- `field_mapping.cdr3_column`
- `field_mapping.copy_column`
- `profile_path`
- `categories`
- `pathology_values`

#### profile

Inspect:

- `POST /api/script-hub/profile/inspect`

Run:

- `POST /api/script-hub/profile/run`

UI:

- Profile/datapoint path
- parameter range begin select from Profile columns
- parameter range over select from Profile columns
- optional grouping range begin/over selects
- group type multi-select from Profile group candidates
- p-value threshold

Payload:

- `datapoint_path` or `profile_path`
- `param_begin`
- `param_over`
- `grouping_begin`
- `grouping_over`
- `grouptype_fields`
- `pvalue_threshold`

#### pep-analysis

Inspect:

- `POST /api/script-hub/pep-analysis/inspect`

Run:

- `POST /api/script-hub/pep-analysis/run`

UI:

- PEP data directory/path summary
- Profile path summary
- chain picker from detected chains
- group field multi-select from Profile group candidates
- group value preview
- p-value threshold
- minimum sample threshold
- pipeline step selector:
  - mandatory: step 2
  - mandatory: steps 3 and 4
  - optional: steps 5 to 8

Payload:

- `pep_data_dir` or `base_path`
- `profile_path`
- `selected_chains`
- `group_fields`
- `pvalue_threshold`
- `min_sample_threshold`
- `optional_steps`

#### pgen-analysis

Inspect:

- `POST /api/script-hub/pgen-analysis/inspect`

Run:

- `POST /api/script-hub/pgen-analysis/run`

UI:

- PEP data path summary
- Profile path summary
- runnable chain picker
- species select
- sample column select from Profile columns
- distribution category column select from Profile columns

Payload:

- `pep_data_dir` or `base_path`
- `profile_path`
- `selected_chains`
- `species`
- `sample_col`
- `distribution_category_col`

#### topclone

Inspect:

- `POST /api/script-hub/topclone/inspect`

Run:

- `POST /api/script-hub/topclone/run`

UI:

- mode select: trace or per-sample
- PEP path summary
- Profile path summary when trace mode
- top N number input
- chain picker from detected chains
- group field select from Profile group candidates
- group order selector/value editor based on inspected group values
- p-value threshold

Payload:

- `pep_data_path` or `base_path`
- `datapoint_path` or `profile_path`
- `mode`
- `top_n`
- `selected_chains`
- `group_field`
- `group_order`
- `pvalue_threshold`

#### umap

Inspect:

- `POST /api/script-hub/umap/inspect`

Run:

- `POST /api/script-hub/umap/run`

UI:

- Profile path summary
- classification begin select from Profile columns
- classification over select from Profile columns
- parameter begin select from Profile columns
- parameter over select from Profile columns
- p-value threshold
- n-neighbors numeric input
- min-dist numeric input

Payload:

- `datapoint_path` or `profile_path`
- `classification_begin`
- `classification_over`
- `param_begin`
- `param_over`
- `pvalue_threshold`
- `n_neighbors`
- `min_dist`

#### volcano

Inspect:

- `POST /api/script-hub/volcano/inspect`

Run:

- `POST /api/script-hub/volcano/run`

UI:

- input mode select: usage or expression
- usage mode:
  - cached usage/data directory status
  - no manual feature range fields unless a usage table is explicitly selected
- expression mode:
  - transcriptome path summary
  - group prefix input, default `tpm_`
  - comparison selector from inspected suggested comparisons
- p-value threshold
- log2 fold-change cutoff

Payload:

- `input_mode`
- `data_dir` or cached usage context
- `expression_path` or `transcriptome_path`
- `group_prefix`
- `comparisons`
- `pvalue_threshold`
- `logfc_cutoff`

#### go-kegg-enrichment

Inspect:

- `POST /api/script-hub/go-kegg-enrichment/inspect`

Run:

- `POST /api/script-hub/go-kegg-enrichment/run`

UI:

- transcriptome path summary
- group prefix input, default `tpm_`
- comparison selector from inspected suggested comparisons
- p-value threshold
- log2 fold-change cutoff
- enrichment p-value cutoff
- p-adjust method select
- show category numeric input
- simplify GO toggle
- GSEA toggle

Payload:

- `expression_path` or `transcriptome_path`
- `group_prefix`
- `comparisons`
- `pvalue_threshold`
- `logfc_cutoff`
- `enrich_pvalue_cutoff`
- `p_adjust_method`
- `show_category`
- `simplify_go`
- `do_gsea`

#### umapin

Inspect:

- `POST /api/script-hub/umapin/inspect`

Run:

- `POST /api/script-hub/umapin/run`

UI:

- data path or cached usage selector
- category column select from usage CSV columns
- parameter begin select from usage CSV columns
- parameter over select from usage CSV columns
- n-neighbors numeric input
- min-dist numeric input
- FDR toggle

Payload:

- `data_path` or cached usage context
- `category_col`
- `param_begin`
- `param_over`
- `n_neighbors`
- `min_dist`
- `do_fdr`

#### ml-analysis

Inspect:

- `POST /api/script-hub/ml-analysis/inspect`

Run:

- `POST /api/script-hub/ml-analysis/run`

UI:

- mode select: profile or V/J usage
- Profile mode:
  - label column select from Profile columns
  - sample column select from Profile columns
  - optional filter column select from Profile columns
  - optional filter value selector based on selected filter column
  - parameter begin/over selects from Profile columns
  - optional explicit feature multi-select
- V/J usage mode:
  - usage path/cached usage selector
  - usage feature multi-select or begin/over range from usage CSV columns
- custom threshold numeric input
- CV split numeric input
- ROC CV split numeric input

Payload:

- `mode`
- `profile_path`
- `label_col`
- `sample_col`
- `filter_col`
- `filter_value`
- `param_begin`
- `param_over`
- `feature_cols`
- `usage_path`
- `usage_feature_cols`
- `custom_threshold`
- `cv_splits`
- `roc_cv_splits`

#### mait-nkt

Inspect:

- `POST /api/script-hub/mait-nkt/inspect`

Run:

- `POST /api/script-hub/mait-nkt/run`

UI:

- Profile path summary
- TRA source select: upload/path or source job
- TRA path selector or source job selector
- group field select from Profile columns
- group order selector/value editor from inspected group values

Payload:

- `profile_path`
- `tra_source`
- `tra_path`
- `source_job_id`
- `group_field`
- `group_order`

## Dropdown Rules

These fields must not be plain free-text inputs:

- `group_field`
- `group_fields`
- `grouptype_fields`
- `sample_col`
- `label_col`
- `filter_col`
- `category_col`
- `distribution_category_col`
- `classification_begin`
- `classification_over`
- `param_begin`
- `param_over`
- `grouping_begin`
- `grouping_over`
- `field_mapping.cdr3_column`
- `field_mapping.copy_column`
- usage feature columns when a usage CSV has been inspected

Allowed text inputs:

- output name
- group prefix
- numeric thresholds
- numeric algorithm parameters
- free-form comparison text only when no suggested comparison list exists
- external path or source job id only when no project/asset picker is available

## Charts Module Decision

`charts` is present in the legacy module catalog and old HTML, but current Flask
routes do not expose `/api/script-hub/charts/inspect` or
`/api/script-hub/charts/run`.

Implementation options:

1. Add a backend compatibility route that dispatches the old charts workflow.
2. Map charts to existing heatmap/treemap/chord worker jobs.
3. Hide or disable charts in the React ScriptHub module list with a clear
   unavailable status until the backend bridge exists.

Recommended first pass: disable charts with an unavailable state so the user
does not reach a form that cannot run.

## Execution Payload Rules

Every run payload should include:

- `project_id`
- `asset_set_id`
- selected source paths
- module-specific config
- `force_rerun` when the UI exposes it
- `output_name` when configured

Legacy ScriptHub modules should continue through:

- `POST /api/script-hub/jobs`
- polling `GET /api/script-hub/task/<task_id>`

Worker-native modules can continue through:

- `POST /api/jobs`
- job monitor polling

## Verification Plan

Automated:

- `npm run typecheck`
- `npx vitest run --pool=threads`
- `python -m pytest backend-api/tests -q`
- add frontend tests for:
  - Stage 2 renders Profile/PEP head-5 tables
  - Stage 3 field controls render as selects from source context
  - module config payloads preserve expected backend parameter names

Manual browser smoke test:

1. Open ScriptHub.
2. Select project.
3. Select an existing asset set.
4. Run inspection.
5. Confirm Stage 2 shows Profile head-5 and PEP head-5 tables.
6. Select `pep-analysis`.
7. Confirm chains and group fields are selected from dropdowns/multi-selects.
8. Select `umap`.
9. Confirm begin/over fields come from Profile column dropdowns.
10. Submit a small job and confirm the job monitor can filter by project and
    dataset/asset set.

## Implementation Order

1. Stage 2 preview API typing and UI replacement.
2. Source context expansion and `project_id` propagation.
3. Shared select/range/chain components.
4. Dedicated forms for `db-alignment`, `pep-analysis`, `profile`, `topclone`,
   and `umap`.
5. Dedicated forms for `volcano`, `go-kegg-enrichment`, `umapin`,
   `ml-analysis`, `pgen-analysis`, and `mait-nkt`.
6. Charts availability decision.
7. Payload validation and tests.
