# Profile Boxplot Refactor Plan

## Goal

Optimize Profile analysis boxplots by importing the new reference summary-plot behavior, extracting shared boxplot rendering into a reusable backend layer, and redesigning the plot style/palette for consistent publication-quality output across Profile, BoxPlot, TopClone, and other Script Hub modules that generate boxplots.

## Current Findings

- Reference script:
  - `_reference/anal_pipeline/Profile_260213/BoxPlot_1120_Thread_Arrange.py`
  - Adds cross-chain summary plots for metrics named as either `CHAIN_metric` or `metric_CHAIN`.
  - Groups related chain-specific parameters into one metric summary, e.g. `TRA_ratio_VDJdb`, `TRB_ratio_VDJdb`, or `ratio_VDJdb_TRA`.
  - Renders summary as grouped bar charts by chain with group colors, SEM error bars, and significance brackets.
  - Has extra profile-specific logic for `*_uCDR3` to `*_uCDR3_ratio`.

- Current shared implementation:
  - `flask_app/services/boxplot_service.py`
  - Already used by Script Hub `boxplot`, Profile analysis route, and TopClone boxplot report integration.
  - Current renderer has duplicated grouped/ungrouped plot paths and existing styling helpers.
  - Current viewer already supports dropdown switching by parameter and class field.

- Current routing:
  - `flask_app/routes/api_script_hub/boxplot.py`
    - `_run_boxplot_task()` calls `BoxPlotService.generate_report()`.
  - `flask_app/routes/api_script_hub/profile_analysis.py`
    - imports `_run_boxplot_task` for Profile module reuse.
  - This means centralizing improvements in `BoxPlotService` will naturally update Profile and other shared consumers.

- Frontend:
  - `frontend/src/features/scripthub/modules/ProfileConfig.tsx`
  - Profile config already uses `GroupFieldMultiSelect`, `GroupOrderEditor`, `GroupValueSamplePicker`, and `RangeFields`.
  - No major frontend structural change is required for summary plots unless a UI toggle is added.

## Figure Contract

- Backend: Python only, matching the current Flask/matplotlib/seaborn workflow.
- Archetype: quantitative grid.
- Claim: boxplots and summary plots should make group-level differences across profile metrics and immune chains readable without forcing users to open hundreds of isolated PNGs.
- Evidence:
  - Per-metric boxplot: distribution and pairwise group significance for one profile feature.
  - Summary plot: chain-level comparison for a family of related metrics.
- Export contract:
  - Preserve current PNG outputs for compatibility.
  - Add SVG/PDF-ready style settings where practical, but avoid breaking existing viewer assumptions.
  - Keep text editable in SVG if SVG output is enabled later.

## Recommended Implementation

### 1. Extract Shared Boxplot Renderer

Modify `flask_app/services/boxplot_service.py`.

Create a lightweight internal rendering API:

- `BoxPlotStyle`
  - palette
  - point color
  - axis color
  - grid color
  - font sizes
  - dpi
  - background behavior

- `BoxPlotRenderer`
  - `draw_grouped_boxplot(...)`
  - `draw_ungrouped_boxplot(...)`
  - `draw_chain_metric_summary(...)`
  - `draw_significance_brackets(...)`
  - `save_figure(...)`

Keep public API compatible:

- `BoxPlotService.generate_report(...)` remains the main entry point.
- Existing `BoxPlotReport` fields stay intact.
- Existing `png_paths`, `csv_paths`, `pvalue_paths`, `significant_paths`, `viewer_path`, `zip_path`, and `metadata` remain.

### 2. Add Summary Plot Generation

In `BoxPlotService.generate_report()` add optional summary generation after grouped boxplots:

- Detect summary-capable metrics from `param_columns`.
- Support both naming forms:
  - `TRA_metric`
  - `metric_TRA`
- Chain order:
  - `TRA`, `TRB`, `TRD`, `TRG`, `IGH`, `IGK`, `IGL`
- Only generate a summary when at least two chains map to the same metric.
- Output layout:
  - `<output_base>/<class_field>/summary/<metric>_summary.png`
  - Optional corresponding summary CSV:
    - `<output_base>/<class_field>/summary/csvfiles/<metric>_summary.csv`

Metadata additions:

```json
{
  "summary_plot_paths": [],
  "summary_csv_paths": [],
  "summary_plot_count": 0,
  "summary_metrics": [
    {
      "class_col": "group_type",
      "metric": "ratio_VDJdb",
      "chains": ["TRA", "TRB"],
      "png_path": "...",
      "csv_path": "..."
    }
  ]
}
```

Add summary files to ZIP:

- `summary_plots/...`
- `summary_data/...`

### 3. Port Reference Summary Logic Conservatively

Port these behaviors from the reference script:

- `split_chain_metric(param)`
- `get_metric_param_groups(...)`
- grouped bar mean + SEM per chain/group
- significance lookup by `(group1, group2, param)`
- significance bracket per chain
- safe filename generation

Avoid importing or executing the reference script directly because it uses hard-coded paths and globals.

### 4. Add uCDR3 Ratio Support

Add optional preprocessing in `BoxPlotService`:

- If profile contains chain count columns like `IGH_uCDR3`, `IGK_uCDR3`, etc., create ratio columns:
  - `IGH_uCDR3_ratio = IGH_uCDR3 / total_uCDR3`
- Only include generated ratio columns in analysis if their source columns are within selected parameter range.
- Store in metadata:

```json
{
  "derived_columns": {
    "ucdr3_ratio": ["IGH_uCDR3_ratio", "IGK_uCDR3_ratio"]
  }
}
```

### 5. Redesign Boxplot Style and Palette

Use a restrained publication-style palette rather than high-saturation defaults:

- Base group palette:
  - blue `#4F78B8`
  - warm orange `#D98C56`
  - muted green `#62A86F`
  - violet `#8E79B8`
  - teal `#5BA6A6`
  - ochre `#C8A44D`
  - rose `#B76E79`
  - neutral `#7A7A7A`

Style changes:

- White background.
- Thin dark axis lines.
- Light horizontal grid only.
- Box fill alpha around `0.70`.
- Points small, neutral, jittered, low alpha.
- Median line dark and slightly heavier.
- Significance labels use stars or compact p labels consistently.
- Avoid red/green as the first contrast unless directionality is explicit.

### 6. Viewer Updates

Update the viewer generated in `BoxPlotService._build_viewer_html()`:

- Add a plot type selector:
  - `Boxplots`
  - `Summary`
- Keep current param/class dropdown behavior for normal boxplots.
- For summary plots, dropdown should use `metric` and `class_col`.
- Show summary plot count in stats.
- Empty state for no summary plots:
  - `No chain summary plots were generated for the selected profile features.`

Keep existing viewer URLs unchanged.

### 7. Route/API Compatibility

No breaking endpoint change required.

Optional new request flags:

```json
{
  "enable_summary_plots": true,
  "enable_ucdr3_ratio": true
}
```

Default should be `true` for Profile/BoxPlot unless performance becomes an issue.

If adding flags:

- Update `flask_app/routes/api_script_hub/boxplot.py`
- Pass options through `_run_boxplot_task()`
- Add fields to cache signature config so reruns are correctly cached.

### 8. Tests and Verification

Backend checks:

- `python -m py_compile flask_app/services/boxplot_service.py flask_app/routes/api_script_hub/boxplot.py flask_app/routes/api_script_hub/profile_analysis.py`
- Add or run a small synthetic test:
  - profile columns: `sample`, `group_type`, `TRA_ratio_VDJdb`, `TRB_ratio_VDJdb`, `IGH_ratio_VDJdb`
  - run `BoxPlotService.generate_report(...)`
  - assert:
    - normal boxplot PNG exists
    - summary PNG exists
    - summary metadata exists
    - ZIP includes summary files

Frontend checks:

- `cd frontend && npm run typecheck`

Manual verification:

- Run Profile analysis using a profile file with chain-prefixed metrics.
- Open `viewer.html`.
- Confirm:
  - per-feature boxplots still work
  - summary plots appear in a separate selector
  - group colors are consistent across normal and summary plots
  - downloaded ZIP contains boxplots, CSV, p-values, significant files, and summary plots

## Execution Order

1. Refactor style constants and shared renderer functions inside `BoxPlotService`.
2. Port metric-chain detection and summary plot generation.
3. Extend metadata and ZIP bundle.
4. Update viewer HTML for summary plot filtering.
5. Add optional route flags only if needed.
6. Run synthetic backend verification and frontend typecheck.

