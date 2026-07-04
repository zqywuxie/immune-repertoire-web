# Pep Analysis Step and Viewer Refactor Plan

## Objective

Refactor Pep Analysis so its task progress matches the original `Pep_260213` script flow more closely, and so result images are not rendered as one long flat gallery. Results should be grouped and viewed through dropdown filters such as image category, group field, chain, and usage or plot type.

This plan is read-only design work for the current `$plan` request. Business code should be changed in a later implementation pass.

## Current Findings

### Backend Step Flow

Current Pep Analysis is implemented mainly in:

- `flask_app/services/pep_analysis_service.py`
- `flask_app/routes/api_script_hub/profile_analysis.py`
- `flask_app/routes/api_script_hub/_common.py`

The original reference scripts are under:

- `_reference/anal_pipeline/Pep_260213/2.Pep_shared.py`
- `_reference/anal_pipeline/Pep_260213/3.add_cate_shared.py`
- `_reference/anal_pipeline/Pep_260213/4.add_cate_usage.py`
- `_reference/anal_pipeline/Pep_260213/5.Heat_map_Thread.py`
- `_reference/anal_pipeline/Pep_260213/6.Pep_statistication.py`
- `_reference/anal_pipeline/Pep_260213/7.CDR3_arrage_heatmap_ver1.0.py`
- `_reference/anal_pipeline/Pep_260213/8.plot_heatmap.py`

The Flask service already ports most core outputs:

- Step 2 produces `Pep_shared/<chain>.csv` and usage matrices under `usage/{1Vusage,1Jusage,1VJusage,0Vusage,0Jusage,0VJusage}`.
- Step 3 adds group categories to shared matrices and writes `Pep_shared_cate`.
- Step 4 adds group categories to usage matrices and writes `usage_cate`.
- Step 5 generates differential usage heatmap CSVs and images.
- Step 6 generates `arrage_pep` and `prop_pep` outputs.
- Step 7 generates CDR3 arrangement heatmaps.
- Step 8 generates unique CDR3 heatmaps and summary heatmaps.

The main gap is not missing calculation coverage, but incomplete task semantics:

- The service header says it implements steps 2-7, while Step 8 also exists.
- Step 3 and Step 4 are currently exposed as a combined `Step 3+4` flow.
- Step 5 and Step 6 report coarse fixed percentages near the end, which can make the job look stuck around 96%-98%.
- Step 7 and Step 8 do not expose enough per-chain or per-output progress.
- Progress metadata lacks stable fields such as `script`, `step`, `group_field`, `chain`, `usage_type`, `processed`, and `total`.

### Current Result Output Behavior

Pep Analysis route result assembly currently produces several flat URL lists:

- `shared_matrix_urls`
- `usage_urls`
- `heatmap_image_urls`
- `heatmap_csv_urls`
- `classification_urls`
- `proportion_urls`
- `proportion_plot_urls`
- `arrange_heatmap_urls`
- `plot_heatmap_urls`
- `png_urls`

The generated viewer is written by `_write_pep_analysis_viewer()` in `flask_app/routes/api_script_hub/_common.py`.

It already has a basic `Image category` dropdown, but it still renders all cards in the selected image category. It does not let the user narrow by group field, chain, usage type, or plot type.

React result rendering also flattens outputs:

- `frontend/src/shared/api/scriptHub.ts` converts result URL lists into generic `JobOutput` items.
- `frontend/src/features/results/ResultViewer.tsx` renders output cards directly.
- `frontend/src/features/jobs/JobResultPanel.tsx` already has a better pattern with module/result dropdowns, but Pep output labels and categories are too generic because the backend does not return structured item metadata.

## Recommended Backend Step Refactor

### Files

- `flask_app/services/pep_analysis_service.py`
- `flask_app/routes/api_script_hub/profile_analysis.py`
- optional shared helpers in `flask_app/routes/api_script_hub/_common.py`

### Step Names

Expose Pep Analysis progress as a stable step list aligned to the reference scripts:

1. `step1_prepare_inputs`
   - Validate project assets, profile, PEP directory, selected chains, selected samples, group field, and group values.
   - This is the Flask wrapper equivalent of reference-side file preparation.

2. `step2_pep_shared`
   - Reference: `2.Pep_shared.py`
   - Sub-stages:
     - `step2_scan_pep_files`
     - `step2_read_files`
     - `step2_build_shared_matrix`
     - `step2_write_shared_csv`
     - `step2_build_usage_matrices`
     - `step2_write_usage_csv`

3. `step3_add_cate_shared`
   - Reference: `3.add_cate_shared.py`
   - Sub-stages:
     - `step3_load_profile_group`
     - `step3_sort_group_values`
     - `step3_write_shared_cate`

4. `step4_add_cate_usage`
   - Reference: `4.add_cate_usage.py`
   - Sub-stages:
     - `step4_load_usage_matrix`
     - `step4_attach_category`
     - `step4_sort_by_group`
     - `step4_write_usage_cate`

5. `step5_heatmap`
   - Reference: `5.Heat_map_Thread.py`
   - Sub-stages:
     - `step5_load_usage_cate`
     - `step5_compute_group_pairs`
     - `step5_compute_mwu`
     - `step5_build_heatmap_matrix`
     - `step5_write_heatmap_csv`
     - `step5_write_heatmap_png`

6. `step6_pep_statistication`
   - Reference: `6.Pep_statistication.py`
   - Sub-stages:
     - `step6_load_shared_cate`
     - `step6_count_combinations`
     - `step6_filter_by_threshold`
     - `step6_write_arrage_pep`
     - `step6_write_prop_pep`

7. `step7_cdr3_arrage_heatmap`
   - Reference: `7.CDR3_arrage_heatmap_ver1.0.py`
   - Sub-stages:
     - `step7_load_arrage_pep`
     - `step7_binarize_arrange_matrix`
     - `step7_plot_arrange_heatmap`
     - `step7_write_arrange_heatmap`

8. `step8_unique_cdr3_heatmap`
   - Reference: `8.plot_heatmap.py`
   - Sub-stages:
     - `step8_read_arrage_data`
     - `step8_build_sections`
     - `step8_plot_chain_heatmap`
     - `step8_plot_summary_heatmap`

9. `finalize_outputs`
   - Write metadata, normalize result payload, generate viewer HTML, and build ZIP.

### Progress Weighting

Replace the current coarse `current_step / total_steps` calculation and fixed 96%-98% callbacks with weighted phases.

Suggested weights:

- Prepare inputs: 0%-5%
- Step 2: 5%-35%
- Step 3: 35%-43%
- Step 4: 43%-52%
- Step 5: 52%-74%
- Step 6: 74%-86%
- Step 7: 86%-93%
- Step 8: 93%-98%
- Finalize: 98%-100%

For multiple group fields, chains, and usage folders, calculate phase progress by item count:

```text
phase_start + phase_weight * processed_items / total_items
```

Progress should be monotonic. If optional steps execute in parallel, centralize updates through a helper that clamps the new percentage to at least the last emitted percentage.

### Progress Metadata

Every progress callback should include a consistent metadata object:

```json
{
  "step": 5,
  "step_key": "step5_heatmap",
  "script": "5.Heat_map_Thread.py",
  "stage": "step5_compute_mwu",
  "group_field": "condition",
  "chain": "TRA",
  "usage_type": "1VJusage",
  "processed": 3,
  "total": 18
}
```

This lets the task/history UI show useful detail without parsing human-readable text.

### Metadata Summary

Add a `step_summary` section to the final Pep Analysis metadata:

```json
[
  {
    "step": 2,
    "script": "2.Pep_shared.py",
    "status": "completed",
    "output_counts": {
      "shared_csv": 2,
      "usage_csv": 12
    }
  }
]
```

Keep existing metadata fields such as `output_counts`, `optional_step_errors`, `chain_file_counts`, and `intermediate_paths` for backward compatibility.

## Recommended Viewer and Output Refactor

### Backend Structured Items

Add structured Pep output items while keeping the old flat URL arrays.

Recommended result fields:

```json
{
  "viewer_items": [
    {
      "url": "/api/script-hub/results/.../heatmap.png",
      "kind": "image",
      "section": "Differential heatmaps",
      "step": 5,
      "script": "5.Heat_map_Thread.py",
      "group_field": "condition",
      "chain": "TRA",
      "usage_type": "1VJusage",
      "plot_type": "heatmap_chunk",
      "title": "Step 5 - condition - TRA - 1VJusage"
    }
  ],
  "download_items": [
    {
      "url": "/api/script-hub/results/.../heatmap.csv",
      "kind": "csv",
      "section": "Differential heatmaps",
      "step": 5,
      "group_field": "condition",
      "chain": "TRA",
      "usage_type": "1VJusage",
      "title": "Step 5 CSV - condition - TRA - 1VJusage"
    }
  ]
}
```

Recommended sections:

- `Shared matrices`
- `Usage matrices`
- `Differential heatmaps`
- `CDR3 classification`
- `CDR3 arrangement heatmaps`
- `Unique CDR3 heatmaps`
- `Metadata`
- `Archive`

For images, classify by:

- `section`
- `group_field`
- `chain`
- `usage_type`
- `plot_type`

For CSV/download outputs, classify by:

- `section`
- `step`
- `group_field`
- `chain`
- `usage_type`

### Generated Viewer HTML

Update `_write_pep_analysis_viewer()` in `flask_app/routes/api_script_hub/_common.py`.

The viewer should render compact filters:

- Image category
- Group field
- Chain
- Usage or plot type

Each result card should include data attributes:

```html
data-section="Differential heatmaps"
data-group-field="condition"
data-chain="TRA"
data-usage-type="1VJusage"
data-plot-type="heatmap_chunk"
```

The viewer JavaScript should:

- Hide cards that do not match the active dropdown filters.
- Show a visible count.
- Show an empty state when no cards match.
- Default to a useful first category, not to rendering every image at once.
- Preserve direct image links and download links.

This keeps the standalone viewer useful even outside the React frontend.

### React Result Output Mapping

Update `frontend/src/shared/api/scriptHub.ts`:

- Prefer `result.viewer_items` when present.
- Convert each structured item into a `JobOutput` with meaningful `module`, `category`, and `label`.
- Avoid adding duplicate generic `png_urls` outputs when the same URL already appears in `viewer_items`.
- Keep old flat URL handling as fallback for historical results.

Suggested labels:

- `Step 5 - condition - TRA - 1VJusage`
- `Step 7 - condition - TRB - arrangement heatmap`
- `Step 8 - condition - ALL - unique CDR3 summary`

Update `frontend/src/features/results/ResultViewer.tsx` only if Pep results are still rendered as a full flat grid after `scriptHub.ts` normalization.

If needed, add a generic filtered mode:

- Trigger when outputs contain structured Pep metadata or when image output count exceeds a threshold.
- Render dropdown filters and only the selected category or selected output.
- Keep current direct-card behavior for small result sets and non-Pep modules.

`frontend/src/features/jobs/JobResultPanel.tsx` can likely remain mostly unchanged because it already supports dropdown-based output selection. The main improvement is feeding it structured labels/categories.

## Backward Compatibility

Do not remove existing fields:

- `png_urls`
- `heatmap_image_urls`
- `proportion_plot_urls`
- `arrange_heatmap_urls`
- `plot_heatmap_urls`
- `heatmap_csv_urls`
- `classification_urls`
- `proportion_urls`
- `usage_urls`
- `shared_matrix_urls`

Add `viewer_items` and `download_items` as preferred structured fields. Old completed jobs and old frontend code should continue to work.

Do not change existing result file paths unless necessary. Downstream modules such as Volcano, UMAPin, and MAIT/NKT depend on Pep cache directories.

## Implementation Order

1. Add a small progress helper in `flask_app/services/pep_analysis_service.py`.
   - Centralize monotonic percentage calculation.
   - Add stable `step_key`, `script`, `stage`, and item count metadata.

2. Split coarse Pep stages into the named steps listed above.
   - Keep calculations unchanged first.
   - Only improve progress messages and metadata.

3. Add `step_summary` to Pep metadata.
   - Count outputs by step and type.
   - Include optional step errors per step.

4. Add backend structured output item generation.
   - Prefer path-aware parsing from known result lists instead of fragile generic filename parsing.
   - Include group field, chain, usage type, and plot type where known.

5. Rewrite the generated Pep viewer filters.
   - Keep the existing standalone `viewer.html` route.
   - Add dropdowns for category, group field, chain, and usage or plot type.
   - Do not show all images by default.

6. Update React output normalization.
   - Prefer structured items.
   - Deduplicate old flat image outputs.
   - Preserve fallback for historical results.

7. Run verification and manual checks.

## Verification Plan

Backend syntax:

```bash
python -m py_compile flask_app/services/pep_analysis_service.py flask_app/routes/api_script_hub/profile_analysis.py flask_app/routes/api_script_hub/_common.py
```

Frontend type check:

```bash
cd frontend
npm run typecheck
```

Manual Pep Analysis smoke test:

1. Select one project and one asset set.
2. Select one group field and two group values.
3. Select a small number of samples from each group.
4. Select one or two chains, such as `TRA` and `TRB`.
5. Run Pep Analysis with optional steps 5-8 enabled.
6. Confirm progress history shows Step 2 through Step 8 with group field, chain, and usage details.
7. Confirm progress does not appear stuck at 96%-98%.
8. Open the standalone viewer.
9. Confirm dropdown filters can narrow images by category, group field, chain, and usage or plot type.
10. Confirm React result panel does not show every image as a long flat gallery.
11. Confirm ZIP download still includes all outputs.
12. Confirm downstream Pep cache selection still works for Volcano, UMAPin, and MAIT/NKT.

Regression checks:

- Historical Pep result payloads without `viewer_items` still render through flat URL fallback.
- Other Script Hub modules still render outputs normally.
- Failed optional steps remain visible in metadata and task history.
- Existing result URLs remain valid and traversal protection is unchanged.

## Open Questions

1. Should the generated viewer default to `Differential heatmaps` or to the first section with image results?
2. Should CSV outputs also get dropdown filtering in the standalone viewer, or should they stay under ZIP/metadata downloads only?
3. Should Step 1 be visible to the user as a formal Pep Analysis step, or only as internal preparation metadata?

Recommended default decisions:

- Default viewer category: first image section with results.
- CSV output display: keep CSVs downloadable but do not render long CSV lists in the viewer by default.
- Step 1: show as `Preparing inputs` in task history so the user can diagnose profile/sample/group validation problems.
