# Treemap Matplotlib Redesign

**Date:** 2026-06-21
**Status:** approved

## Goal

Replace the D3.js HTML → headless-browser screenshot → PNG render pipeline with matplotlib direct rendering, using `_reference/treemap/treemap_group_vertical.py` as the reference implementation. Two visual modes:

- **QR (二维码):** Hierarchical rounded rectangles via `FancyBboxPatch`, V→J→CDR3 three-level squarified layout
- **Tetris (俄罗斯方块):** Same hierarchical layout, but clones within each J region are packed as tetromino shapes on a grid

## Canvas

- **Shape:** square only (1000×1000 canvas, 10×10 figure, DPI 300)
- Colors: `MOSAIC_REFERENCE_PALETTE` from reference script

## New file

### `flask_app/services/treemap_plotter.py`

Core matplotlib rendering module:

```
class TreemapPlotter:
    CANVAS_W, CANVAS_H = 1000.0, 1000.0
    FIG_W, FIG_H = 10, 10
    DPI = 300

    load_data(csv_path, columns) → DataFrame
    assign_colors(plot_df) → [(r,g,b), ...]
    squarify_items(items, x, y, dx, dy) → rects
    make_hierarchy_rects(plot_df) → leaf_rects     # QR mode
    make_hierarchy_tetris(plot_df) → tetris_pieces  # Tetris mode
    draw_qr(plot_df, output_path)                   # rounded rects
    draw_tetris(plot_df, output_path)               # tetromino grid
    generate(plot_df, output_path, mode)            # dispatch
```

Algorithm flow (from reference):
1. Load CSV → group by V+J+CDR3 → sort → assign colors
2. V-level squarify over full canvas
3. For each V rect → J-level squarify within V bounds
4. For each J rect → CDR3-level:
   - QR: squarify into rounded rects
   - Tetris: pack into grid cells with tetromino shapes

Key parameters:
- `GAP = 0.62` (white lanes between blocks)
- `ROUND_RATIO = 0.28`, `MAX_ROUND = 36`
- `BG_COLOR = "white"`

## Modified files

### `treemap_renderer.py`
- Keep: data reading utilities (`detect_columns`, `read_repertoire_rows`, etc.)
- Remove: `HTML_TEMPLATE` (the entire D3.js inline HTML/JS)

### `treemap_report_service.py`
- Remove: `_render_html_to_png()`, `_get_browser_path()`, headless browser call
- Change: `_render_single_chain_html()` → `_render_single_chain_png()` calling `TreemapPlotter.generate()`
- Remove: `_trim_white_border()` (matplotlib produces clean output directly)
- Keep: overview composition, ZIP bundling, viewer.html generation
- Import from `treemap_plotter` instead of `HTML_TEMPLATE`

### `api_treemap.py`
- Minor: ensure `layout_mode` parameter flows through to plotter

### `script_hub.js` (frontend)
- No functional changes — the "treemap" checkbox in charts section still delegates to `/api/treemap/generate`
- Optionally update UI labels if layout mode descriptions change

## What stays unchanged

- API endpoints (`/api/treemap/generate`, task polling, result serving)
- `charts.combined` background job orchestration in `api_jobs.py`
- Script Hub UI (chain selection, field mapping, module checkboxes)
- TopClone CSV export
- Overview (7-chain) composition
- ZIP bundling and viewer.html

## Testing

- Unit test: `TreemapPlotter` with synthetic data
- Integration: end-to-end via Script Hub charts workflow
- Verify: PNG output dimensions (3000×3000 at DPI 300), no white border, correct V→J→CDR3 hierarchy
