# Treemap Matplotlib Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace D3.js HTML → headless-browser → PNG pipeline with matplotlib direct rendering, using `_reference/treemap/treemap_group_vertical.py` squarified layout algorithm.

**Architecture:** New `treemap_plotter.py` module handles all matplotlib rendering (QR rounded-rect mode + Tetris tetromino-grid mode on 1000×1000 canvas). `treemap_report_service.py` calls the plotter directly instead of building HTML and screenshooting via headless Edge/Chrome. `treemap_renderer.py` retains data utilities but drops the 2000-line HTML_TEMPLATE.

**Tech Stack:** Python 3, matplotlib, FancyBboxPatch, squarified treemap, concurrent.futures, PIL (for overview composition, retained)

---

## File Structure Map

| File | Action | Responsibility |
|------|--------|----------------|
| `flask_app/services/treemap_plotter.py` | **Create** | Matplotlib rendering: data load, color assign, squarify layout, QR/Tetris draw |
| `flask_app/services/treemap_renderer.py` | **Modify** | Remove HTML_TEMPLATE (lines 299–2294), `build_html()`, `main()`, `parse_args()`, `derive_output_path()` |
| `flask_app/services/treemap_report_service.py` | **Modify** | Remove browser/HTML methods; call plotter directly; simplify overview to image-based |
| `flask_app/templates/analysis/treemap.html` | **Modify** | Remove layout_mode/canvas_shape/style options no longer relevant |

---

### Task 1: Create `treemap_plotter.py` — core matplotlib rendering module

**Files:**
- Create: `flask_app/services/treemap_plotter.py`
- Reference: `_reference/treemap/treemap_group_vertical.py` (entire file for algorithm)

- [ ] **Step 1: Create module skeleton with constants and color palettes**

```python
"""
Matplotlib-based treemap renderer for immune repertoire clonotype visualization.

Two modes:
  - "qr": hierarchical rounded rectangles (V→J→CDR3), FancyBboxPatch
  - "tetris": same hierarchy, clones packed as tetromino shapes on a grid

Canvas: square 1000×1000, figure 10×10 inches, 300 DPI → 3000×3000 px output.
"""
from __future__ import annotations

import colorsys
import hashlib
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANVAS_W = 1000.0
CANVAS_H = 1000.0
FIG_W = 10.0
FIG_H = 10.0
DPI = 300

GAP = 0.62
BG_COLOR = "white"
ROUND_RATIO = 0.28
MAX_ROUND = 36
TOP_RANK_COLORS = 64
RANDOM_SEED = 123

# Tetromino shape definitions (cell coordinates)
SHAPES: Dict[str, List[Tuple[int, int]]] = {
    "I": [(0, 0), (1, 0), (2, 0), (3, 0)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "T": [(0, 0), (1, 0), (2, 0), (1, 1)],
    "S": [(1, 0), (2, 0), (0, 1), (1, 1)],
    "Z": [(0, 0), (1, 0), (1, 1), (2, 1)],
    "J": [(0, 0), (0, 1), (1, 1), (2, 1)],
    "L": [(2, 0), (0, 1), (1, 1), (2, 1)],
}
SHAPE_ORDER = ["I", "O", "T", "S", "Z", "J", "L"]
```

- [ ] **Step 2: Add color palettes and color utilities**

```python
MOSAIC_REFERENCE_PALETTE = [
    "#981840", "#104008", "#a020b0", "#e8c040", "#f8e838",
    "#8098d0", "#e89080", "#e860d0", "#901098", "#70a0e8",
    "#a8f888", "#286028", "#58d000", "#d0b040", "#2818f0",
    "#c0f018", "#684820", "#685820", "#b088e0", "#988060",
    "#e06040", "#50d018", "#2058a0", "#b84858", "#10c8a8",
    "#a02080", "#c878c8", "#b858b8", "#d8e008", "#b80068",
    "#f86018", "#5848c8", "#582060", "#90d018", "#280018",
    "#10f0f8", "#40d830", "#006b4a", "#3ec4d1", "#ef0db8",
    "#80d9ab", "#0da12f", "#225bb7",
]


def _hex_to_rgb01(hex_color: str) -> Tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _stable_int(value: Any) -> int:
    digest = hashlib.md5(str(value).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _assign_colors(plot_df) -> List[Tuple[float, float, float]]:
    """Assign deterministic colors from MOSAIC_REFERENCE_PALETTE via entry_id hash."""
    palette_size = len(MOSAIC_REFERENCE_PALETTE)
    colors = []
    for _, row in plot_df.iterrows():
        key_seed = _stable_int(row["_entry_id"]) + RANDOM_SEED
        palette_idx = key_seed % palette_size
        colors.append(_hex_to_rgb01(MOSAIC_REFERENCE_PALETTE[palette_idx]))
    return colors
```

- [ ] **Step 3: Add squarified treemap layout algorithm (from reference script)**

```python
def _normalize_sizes(values: List[float], dx: float, dy: float) -> List[float]:
    total = float(sum(values))
    if total <= 0:
        return []
    scale = (dx * dy) / total
    return [float(v) * scale for v in values]


def _worst_ratio(row: List[float], side: float) -> float:
    if not row or side <= 0:
        return float("inf")
    row_sum = sum(row)
    row_min = min(row)
    row_max = max(row)
    if row_min <= 0 or row_sum <= 0:
        return float("inf")
    side_sq = side * side
    return max(
        side_sq * row_max / (row_sum * row_sum),
        (row_sum * row_sum) / (side_sq * row_min),
    )


def _layout_row(
    row_items: List[Dict[str, Any]],
    x: float, y: float, dx: float, dy: float,
    prefer_vertical: bool = True,
) -> Tuple[List[Dict[str, Any]], float, float, float, float]:
    row_sum = sum(item["_area"] for item in row_items)
    rects: List[Dict[str, Any]] = []
    if row_sum <= 0 or dx <= 0 or dy <= 0:
        return rects, x, y, dx, dy

    use_vertical = dx >= dy if prefer_vertical else dx > dy

    if use_vertical:
        width = row_sum / dy
        cursor_y = y
        for idx, item in enumerate(row_items):
            if idx == len(row_items) - 1:
                height = (y + dy) - cursor_y
            else:
                height = item["_area"] / width
            rect = dict(item)
            rect.update({"x": x, "y": cursor_y, "dx": width, "dy": height})
            rects.append(rect)
            cursor_y += height
        return rects, x + width, y, dx - width, dy

    height = row_sum / dx
    cursor_x = x
    for idx, item in enumerate(row_items):
        if idx == len(row_items) - 1:
            width = (x + dx) - cursor_x
        else:
            width = item["_area"] / height
        rect = dict(item)
        rect.update({"x": cursor_x, "y": y, "dx": width, "dy": height})
        rects.append(rect)
        cursor_x += width
    return rects, x, y + height, dx, dy - height


def _squarify_items(
    items: List[Dict[str, Any]],
    x: float, y: float, dx: float, dy: float,
    value_key: str,
    prefer_vertical: bool = True,
) -> List[Dict[str, Any]]:
    values = [float(item[value_key]) for item in items]
    areas = _normalize_sizes(values, dx, dy)
    items = [dict(item) for item in items]
    for item, area in zip(items, areas):
        item["_area"] = area

    row: List[Dict[str, Any]] = []
    rects: List[Dict[str, Any]] = []

    while items:
        item = items[0]
        side = min(dx, dy)
        if not row or _worst_ratio(
            [r["_area"] for r in row] + [item["_area"]], side
        ) <= _worst_ratio([r["_area"] for r in row], side):
            row.append(items.pop(0))
            continue
        laid_out, x, y, dx, dy = _layout_row(row, x, y, dx, dy, prefer_vertical=prefer_vertical)
        rects.extend(laid_out)
        row = []

    if row:
        laid_out, x, y, dx, dy = _layout_row(row, x, y, dx, dy, prefer_vertical=prefer_vertical)
        rects.extend(laid_out)

    return rects
```

- [ ] **Step 4: Add data loading function**

```python
import pandas as pd


def _load_plot_df(
    csv_path: Path,
    cdr3_col: str,
    copy_col: str,
    v_col: str,
    j_col: str,
    min_count: int = 1,
) -> "pd.DataFrame":
    """Load and aggregate repertoire data for treemap plotting."""
    sep = "\t" if csv_path.suffix.lower() in (".tsv", ".tsv.gz", ".txt", ".txt.gz") else ","
    compression = "infer" if csv_path.suffix.lower().endswith(".gz") else None

    df = pd.read_csv(
        str(csv_path),
        sep=sep,
        usecols=[v_col, j_col, cdr3_col, copy_col],
        dtype={v_col: str, j_col: str, cdr3_col: str},
        compression=compression,
        low_memory=False,
    )

    df[v_col] = df[v_col].fillna("Unknown_V").astype(str).str.strip()
    df[j_col] = df[j_col].fillna("Unknown_J").astype(str).str.strip()
    df[cdr3_col] = df[cdr3_col].astype(str).str.strip()
    df[copy_col] = pd.to_numeric(df[copy_col], errors="coerce").fillna(0)
    df.loc[df[v_col] == "", v_col] = "Unknown_V"
    df.loc[df[j_col] == "", j_col] = "Unknown_J"

    mask = (
        (df[cdr3_col] != "")
        & (df[cdr3_col].str.lower() != "nan")
        & (df[copy_col] >= min_count)
    )
    plot_df = df.loc[mask, [v_col, j_col, cdr3_col, copy_col]].copy()
    plot_df["_source_order"] = plot_df.index

    plot_df = plot_df.groupby(
        [v_col, j_col, cdr3_col], as_index=False, sort=False
    ).agg({copy_col: "sum", "_source_order": "min"})

    if plot_df.empty:
        raise ValueError("过滤后无有效数据")

    # Sort by copy desc then source order
    plot_df = plot_df.sort_values(
        [copy_col, "_source_order"], ascending=[False, True]
    ).reset_index(drop=True)

    plot_df["_entry_id"] = (
        plot_df[v_col].astype(str) + "|"
        + plot_df[j_col].astype(str) + "|"
        + plot_df[cdr3_col].astype(str)
    )
    plot_df["_color"] = _assign_colors(plot_df)
    return plot_df
```

- [ ] **Step 5: Add QR mode — hierarchical rounded rectangle layout and drawing**

```python
def _make_hierarchy_rects(plot_df, v_col: str, j_col: str, copy_col: str) -> List[Dict[str, Any]]:
    """V → J → CDR3 three-level squarified layout, returning leaf rects."""
    # V-level grouping
    v_df = plot_df.groupby(v_col, as_index=False, sort=False).agg(
        {copy_col: "sum", "_source_order": "min"}
    )
    v_df = v_df.sort_values(copy_col, ascending=False).reset_index(drop=True)
    v_records = v_df.to_dict("records")
    v_rects = _squarify_items(v_records, 0.0, 0.0, CANVAS_W, CANVAS_H, copy_col)

    leaf_rects: List[Dict[str, Any]] = []

    for v_rect in v_rects:
        v_value = v_rect[v_col]
        v_sub = plot_df[plot_df[v_col] == v_value].copy()
        if v_sub.empty:
            continue

        j_df = v_sub.groupby(j_col, as_index=False, sort=False).agg(
            {copy_col: "sum", "_source_order": "min"}
        )
        j_df = j_df.sort_values(copy_col, ascending=False).reset_index(drop=True)
        j_records = j_df.to_dict("records")
        j_rects = _squarify_items(
            j_records, v_rect["x"], v_rect["y"], v_rect["dx"], v_rect["dy"], copy_col
        )

        for j_rect in j_rects:
            j_value = j_rect[j_col]
            clone_df = v_sub[v_sub[j_col] == j_value].copy()
            if clone_df.empty:
                continue
            clone_records = clone_df.to_dict("records")
            clone_rects = _squarify_items(
                clone_records, j_rect["x"], j_rect["y"], j_rect["dx"], j_rect["dy"], copy_col
            )
            leaf_rects.extend(clone_rects)

    return leaf_rects


def _block_style(dx: float, dy: float) -> Tuple[float, float]:
    """Determine gap and corner rounding based on block size."""
    side = min(dx, dy)
    if side < 2.0:
        return 0.02, 0.08
    if side < 3.5:
        return 0.04, 0.16
    if side < 6.0:
        return 0.07, min(side * 0.06, 0.28)
    if side < 10.0:
        return 0.12, min(side * 0.08, 0.65)
    if side < 18.0:
        return 0.20, min(side * 0.12, 1.6)
    if side < 36.0:
        return 0.32, min(side * 0.18, 4.5)
    return GAP, min(side * ROUND_RATIO, MAX_ROUND)


def _add_round_rect(ax, x: float, y: float, dx: float, dy: float, color: Tuple[float, float, float]) -> None:
    """Add a single FancyBboxPatch to the axes."""
    gap, rounding = _block_style(dx, dy)

    left_gap = 0.0 if x <= 0 else gap / 2
    top_gap = 0.0 if y <= 0 else gap / 2
    right_gap = 0.0 if x + dx >= CANVAS_W - 1e-6 else gap / 2
    bottom_gap = 0.0 if y + dy >= CANVAS_H - 1e-6 else gap / 2

    x += left_gap
    y += top_gap
    dx = max(dx - left_gap - right_gap, 0.01)
    dy = max(dy - top_gap - bottom_gap, 0.01)

    if dx <= 0 or dy <= 0:
        return

    rounding = min(rounding, min(dx, dy) / 2)

    patch = FancyBboxPatch(
        (x, y), dx, dy,
        boxstyle=f"round,pad=0,rounding_size={rounding}",
        linewidth=0,
        edgecolor=None,
        facecolor=color,
        antialiased=True,
    )
    ax.add_patch(patch)


def _draw_qr_treemap(plot_df, output_path: Path, v_col: str, j_col: str, copy_col: str) -> None:
    """Render QR-style hierarchical treemap with rounded rectangles."""
    rects = _make_hierarchy_rects(plot_df, v_col, j_col, copy_col)

    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI, frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    for rect in rects:
        _add_round_rect(
            ax=ax,
            x=rect["x"],
            y=rect["y"],
            dx=rect["dx"],
            dy=rect["dy"],
            color=rect["_color"],
        )

    ax.set_xlim(0, CANVAS_W)
    ax.set_ylim(CANVAS_H, 0)
    ax.set_aspect("equal", adjustable="box")
    ax.margins(0, 0)
    ax.axis("off")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=DPI, facecolor=BG_COLOR, pad_inches=0)
    plt.close(fig)
```

- [ ] **Step 6: Add Tetris mode — tetromino packing within squarified hierarchy**

```python
def _shape_key_for_record(record: Dict[str, Any], v_col: str, j_col: str, cdr3_col: str) -> str:
    """Deterministic shape assignment based on clone identity."""
    key = f"{record.get(cdr3_col, '')}|{record.get(v_col, '')}|{record.get(j_col, '')}"
    h = abs(hash(key)) % len(SHAPE_ORDER)
    return SHAPE_ORDER[h]


def _shape_dimensions(cells: List[Tuple[int, int]]) -> Dict[str, int]:
    max_x = max(c[0] for c in cells) + 1
    max_y = max(c[1] for c in cells) + 1
    return {"w": max_x, "h": max_y}


def _build_rotations(cells: List[Tuple[int, int]]) -> List[List[Tuple[int, int]]]:
    """Generate all unique rotations of a shape."""
    seen = set()
    result = []
    current = list(cells)
    for _ in range(4):
        # Normalize to origin
        min_x = min(c[0] for c in current)
        min_y = min(c[1] for c in current)
        normalized = tuple(sorted((x - min_x, y - min_y) for x, y in current))
        if normalized not in seen:
            seen.add(normalized)
            result.append(list(normalized))
        # Rotate 90°
        current = [(y, -x) for x, y in current]
    return result


def _pack_tetrominos(
    items: List[Dict[str, Any]],
    rect: Dict[str, Any],
    v_col: str, j_col: str, cdr3_col: str,
) -> List[Dict[str, Any]]:
    """Pack clones as tetromino shapes into a rectangular region."""
    if not items or rect["dx"] <= 2 or rect["dy"] <= 2:
        return []

    items = sorted(items, key=lambda it: -float(it.get("copy", 0)))
    shape_rots = {s: _build_rotations(SHAPES[s]) for s in SHAPE_ORDER}

    # Try different cell sizes to minimize omissions
    start_cell = max(2, min(16, int(math.sqrt(rect["dx"] * rect["dy"] / max(1, len(items))) * 0.7)))
    best = {"cellSize": 2, "placed": [], "omitted": float("inf"), "cols": 0, "rows": 0}

    for cell_size in range(start_cell, 1, -1):
        cols = max(1, int(rect["dx"] / cell_size))
        rows = max(1, int(rect["dy"] / cell_size))
        if cols < 2 or rows < 2:
            continue

        occupancy: List[List[int]] = [[0] * cols for _ in range(rows)]
        placed: List[Dict[str, Any]] = []
        omitted = 0

        for item in items:
            shape_name = _shape_key_for_record(item, v_col, j_col, cdr3_col)
            rotations = shape_rots.get(shape_name, [SHAPES["O"]])
            # Scale based on copy proportion
            desired_scale = max(1, int(item.get("copy", 0) / max(1, items[0].get("copy", 1)) * 4))

            result = _place_tetromino(occupancy, cols, rows, rotations, desired_scale)
            if result:
                cells, scale, px, py = result
                placed.append({
                    **item,
                    "shape": shape_name,
                    "cells": cells,
                    "scale": scale,
                    "x": rect["x"] + px * cell_size,
                    "y": rect["y"] + py * cell_size,
                    "cellSize": cell_size,
                })
            else:
                omitted += 1

        if omitted < best["omitted"] or (omitted == best["omitted"] and cell_size > best["cellSize"]):
            best = {"cellSize": cell_size, "placed": placed, "omitted": omitted, "cols": cols, "rows": rows}
        if omitted == 0:
            break

    return best["placed"]


def _place_tetromino(
    occupancy: List[List[int]], cols: int, rows: int,
    rotations: List[List[Tuple[int, int]]], desired_scale: int,
) -> Optional[Tuple[List[Tuple[int, int]], int, int, int]]:
    """Try to place a tetromino; return (cells, scale, x, y) or None."""
    for scale in range(desired_scale, 0, -1):
        for cells in rotations:
            dims = _shape_dimensions(cells)
            w = dims["w"] * scale
            h = dims["h"] * scale
            if w > cols or h > rows:
                continue
            for y in range(rows - h + 1):
                for x in range(cols - w + 1):
                    if _fits(occupancy, x, y, cells, scale):
                        _stamp(occupancy, x, y, cells, scale)
                        return (cells, scale, x, y)
    return None


def _fits(occupancy, ox, oy, cells, scale) -> bool:
    for cx, cy in cells:
        for sy in range(scale):
            for sx in range(scale):
                if occupancy[oy + cy * scale + sy][ox + cx * scale + sx]:
                    return False
    return True


def _stamp(occupancy, ox, oy, cells, scale) -> None:
    for cx, cy in cells:
        for sy in range(scale):
            for sx in range(scale):
                occupancy[oy + cy * scale + sy][ox + cx * scale + sx] = 1


def _draw_tetris_treemap(plot_df, output_path: Path, v_col: str, j_col: str, copy_col: str, cdr3_col: str) -> None:
    """Render Tetris-style treemap with tetromino-packed clones."""
    # V → J hierarchy
    v_df = plot_df.groupby(v_col, as_index=False, sort=False).agg(
        {copy_col: "sum", "_source_order": "min"}
    )
    v_df = v_df.sort_values(copy_col, ascending=False).reset_index(drop=True)
    v_rects = _squarify_items(v_df.to_dict("records"), 0.0, 0.0, CANVAS_W, CANVAS_H, copy_col)

    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI, frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    for v_rect in v_rects:
        v_value = v_rect[v_col]
        v_sub = plot_df[plot_df[v_col] == v_value].copy()
        if v_sub.empty:
            continue

        j_df = v_sub.groupby(j_col, as_index=False, sort=False).agg(
            {copy_col: "sum", "_source_order": "min"}
        )
        j_df = j_df.sort_values(copy_col, ascending=False).reset_index(drop=True)
        j_rects = _squarify_items(
            j_df.to_dict("records"), v_rect["x"], v_rect["y"], v_rect["dx"], v_rect["dy"], copy_col
        )

        for j_rect in j_rects:
            j_value = j_rect[j_col]
            clone_df = v_sub[v_sub[j_col] == j_value].copy()
            if clone_df.empty:
                continue
            clones = clone_df.to_dict("records")
            pieces = _pack_tetrominos(clones, j_rect, v_col, j_col, cdr3_col)

            for piece in pieces:
                cells = piece.get("cells", [(0, 0)])
                scale = piece.get("scale", 1)
                piece_x = piece["x"]
                piece_y = piece["y"]
                color = piece.get("_color", (0.5, 0.5, 0.5))

                for cx, cy in cells:
                    for sy in range(scale):
                        for sx in range(scale):
                            px = piece_x + (cx * scale + sx) * piece.get("cellSize", 2)
                            py = piece_y + (cy * scale + sy) * piece.get("cellSize", 2)
                            rect = Rectangle(
                                (px, py), piece.get("cellSize", 2), piece.get("cellSize", 2),
                                linewidth=0.3,
                                edgecolor="white",
                                facecolor=color,
                                antialiased=True,
                            )
                            ax.add_patch(rect)

    ax.set_xlim(0, CANVAS_W)
    ax.set_ylim(CANVAS_H, 0)
    ax.set_aspect("equal", adjustable="box")
    ax.margins(0, 0)
    ax.axis("off")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=DPI, facecolor=BG_COLOR, pad_inches=0)
    plt.close(fig)
```

- [ ] **Step 7: Add public `generate()` entry point**

```python
def generate_treemap(
    csv_path: Path,
    output_path: Path,
    mode: str = "tetris",
    cdr3_col: str = "CDR3(pep)",
    copy_col: str = "copy",
    v_col: str = "V",
    j_col: str = "J",
    min_count: int = 1,
) -> Path:
    """
    Generate a treemap PNG from a repertoire CSV/TSV file.

    Args:
        csv_path: Path to input CSV/TSV file.
        output_path: Path for output PNG (will be created).
        mode: "tetris" or "qr".
        cdr3_col, copy_col, v_col, j_col: Column names.
        min_count: Minimum copy threshold.

    Returns:
        Path to the generated PNG.
    """
    mode = str(mode).strip().lower()
    if mode not in ("tetris", "qr"):
        raise ValueError(f"Unknown treemap mode: {mode}")

    plot_df = _load_plot_df(
        Path(csv_path),
        cdr3_col=cdr3_col,
        copy_col=copy_col,
        v_col=v_col,
        j_col=j_col,
        min_count=min_count,
    )

    output_path = Path(output_path)
    if mode == "qr":
        _draw_qr_treemap(plot_df, output_path, v_col, j_col, copy_col)
    else:
        _draw_tetris_treemap(plot_df, output_path, v_col, j_col, copy_col, cdr3_col)

    return output_path
```

- [ ] **Step 8: Commit**

```bash
git add flask_app/services/treemap_plotter.py
git commit -m "feat: add matplotlib-based treemap plotter with QR and Tetris modes"
```

---

### Task 2: Strip `HTML_TEMPLATE` from `treemap_renderer.py`

**Files:**
- Modify: `flask_app/services/treemap_renderer.py`

- [ ] **Step 1: Remove `HTML_TEMPLATE` (lines 299–2294)**

The HTML_TEMPLATE is the ~2000-line inline D3.js HTML string. Remove it entirely. Keep all Python functions before it and after it.

The functions to **keep** (before line 299):
- `normalize_header`, `open_text_file`, `detect_dialect`, `detect_columns`, `parse_copy`, `clean_text`, `infer_chain`, `infer_cell_type`, `vj_pair_name`, `make_title`, `_normalize_copy_value`, `read_repertoire_rows`, `read_repertoire` (ends ~line 285)
- `D3_CDN_URL`, `HEADER_ALIASES`, `CHAIN_CELL_MAP`

The functions to **keep** (after line 2294):
- `escape_html_text` — used by report service for viewer.html generation
- `load_d3_script_tag` — no longer needed but keep for now (used by chord_report_service.py)
- `build_html` — remove (only used by HTML_TEMPLATE)
- `parse_args`, `derive_output_path`, `main` — remove (CLI entry points)

Confirm: `chord_report_service.py` imports `detect_dialect` and `open_text_file` from this module — both will stay.

- [ ] **Step 2: Remove `build_html()`, `parse_args()`, `derive_output_path()`, `main()` (lines 2297–2400)**

Delete everything from `def build_html(` through the end of the file.

- [ ] **Step 3: Remove unused imports at top of file**

Remove `argparse`, `json`, `math`, `sys`, `urllib.request` (only used by HTML_TEMPLATE/build_html/main). Keep `csv`, `gzip`, `re`, `typing` which are used by the data utilities.

- [ ] **Step 4: Verify the file still imports cleanly**

Run: `python -c "from flask_app.services.treemap_renderer import detect_columns, read_repertoire_rows, open_text_file, detect_dialect, read_repertoire"`

- [ ] **Step 5: Commit**

```bash
git add flask_app/services/treemap_renderer.py
git commit -m "refactor: remove D3.js HTML_TEMPLATE from treemap_renderer, keep data utilities"
```

---

### Task 3: Update `treemap_report_service.py` to use matplotlib plotter

**Files:**
- Modify: `flask_app/services/treemap_report_service.py`

This is the main integration change. The service currently:
1. Builds HTML per chain via `_build_html_cached()` → `HTML_TEMPLATE`
2. Screenshots HTML to PNG via `_render_html_to_png()` (headless browser)
3. Trims white border from PNGs via `_trim_white_border()`
4. Composes overview PNG from individual PNGs via PIL

After this change:
1. Generates PNG per chain directly via `treemap_plotter.generate_treemap()`
2. No browser needed, no HTML→PNG conversion, no white-border trimming
3. Overview composition stays PIL-based

- [ ] **Step 1: Update imports**

Replace:
```python
from flask_app.services.treemap_renderer import (
    detect_columns,
    detect_dialect,
    escape_html_text,
    HTML_TEMPLATE,
    load_d3_script_tag,
    make_title,
    open_text_file,
    read_repertoire,
    read_repertoire_rows,
)
```

With:
```python
from flask_app.services.treemap_renderer import (
    detect_columns,
    detect_dialect,
    escape_html_text,
    make_title,
    open_text_file,
    read_repertoire,
    read_repertoire_rows,
)
from flask_app.services.treemap_plotter import generate_treemap
```

> Note: `escape_html_text` is still used in `_build_static_viewer_html()`.

- [ ] **Step 2: Remove `_get_browser_path()` method (lines 392–406)**

Delete the entire method — no more headless browser.

- [ ] **Step 3: Remove `_get_d3_script_tag()` method (lines 408–411)**

Delete the entire method.

- [ ] **Step 4: Remove `_render_html_to_png()` method (lines 448–473)**

Delete the entire method that calls headless Edge/Chrome.

- [ ] **Step 5: Remove `_build_html_cached()` method (lines 413–446)**

Delete the method that populates `HTML_TEMPLATE` with data. Replaced by direct `generate_treemap()` call.

- [ ] **Step 6: Remove `_build_overview_html()` method (lines 269–307)**

The overview HTML was built with iframes referencing individual chain HTML files. With matplotlib, individual chain HTMLs no longer exist — only PNGs. This method and the `OVERVIEW_TEMPLATE` (lines 69–267) are removed. The `_compose_overview_png_from_individuals` PIL-based method still works.

Delete `OVERVIEW_TEMPLATE` (lines 69–267) and `_build_overview_html()` (lines 269–307).

- [ ] **Step 7: Remove `_build_overview_export_html()` method (lines 309–352)**

Delete this static method — it was also HTML/iframe based for PNG export, no longer needed.

- [ ] **Step 8: Remove `_trim_white_border()` method (lines 476–505)**

Delete — matplotlib produces clean output directly, no white border trimming needed.

- [ ] **Step 9: Remove `_compose_overview_png_from_individuals()` static method (lines 507–549)**

No — KEEP this method. It composes the 7-chain overview PNG from individual chain PNGs using PIL. This is still needed because matplotlib generates one PNG per chain and we compose them into one overview image. The PIL logic is independent of the rendering backend.

Wait — actually re-reading the code, `_compose_overview_png_from_individuals` uses `OVERVIEW_ORDER_TCR`, `OVERVIEW_ORDER_BCR`, `TOP_CHAIN_WEIGHTS`, `BOTTOM_CHAIN_WEIGHTS` constants and `_weighted_boxes` from the class. Let me verify these are still present...

They're class-level constants and static methods, defined at lines 53–61 and elsewhere. These stay. Keep the method.

- [ ] **Step 10: Remove `_trim_white_border` references in `generate_report()` (lines 1167–1174)**

Remove the `trim_size` block and the trimming loop:

```python
# DELETE this block (lines ~1167–1174):
# trim_size = (1260, 2700) if canvas_shape == "portrait" else (1800, 1800)
# for chain_name, png_path in list(rendered_png_paths.items()):
#     try:
#         self._trim_white_border(png_path, output_size=trim_size)
#     except Exception as exc: ...
```

- [ ] **Step 11: Rewrite the chain PNG generation section in `generate_report()` (lines 1053–1097)**

Replace the HTML-then-screenshot flow with direct matplotlib PNG generation. In `generate_report()`, the section starting at line ~1053 (`if not topclone_only:`) currently:
1. Reads clones via `read_repertoire()`
2. Builds HTML via `_build_html_cached()`
3. Writes HTML file
4. Later screenshots to PNG via ThreadPool

Replace steps 2–4 with a single `generate_treemap()` call that writes the PNG directly:

```python
if not topclone_only:
    clones, summary = read_repertoire(input_path, columns)
    if not clones:
        logger.warning("Treemap input file has no usable clones after aggregation: %s", input_path)
        generated_chains.pop()
        continue

    derived_cell_type = CHAIN_CELL_MAP.get(chain, "Unknown")
    for clone in clones:
        clone["chain"] = chain
        clone["cell_type"] = derived_cell_type

    png_filename = f"{sample_safe_name}__{chain}_treemap.png"
    png_path = sample_dirs["individual_png"] / png_filename

    advance(
        "生成单链 PNG",
        f"{display_name} | {chain} ({chain_index}/{len(ordered_sample_chains)})",
        phase="individual_png",
        sample_name=display_name,
        sample_index=sample_index,
        chain_name=chain,
        chain_index=chain_index,
        chain_total=len(ordered_sample_chains),
        input_file=input_path.name,
        output_file=png_filename,
    )

    generate_treemap(
        csv_path=input_path,
        output_path=png_path,
        mode=layout_mode,
        cdr3_col=columns.get("cdr3", "CDR3(pep)"),
        copy_col=columns.get("copy", "copy"),
        v_col=columns.get("v", "V"),
        j_col=columns.get("j", "J"),
    )

    overview_source_paths[chain] = png_path
    chain_output["png"] = str(png_path.relative_to(output_base)).replace("\\", "/")

chain_outputs[chain] = chain_output
```

- [ ] **Step 12: Remove the PNG rendering ThreadPool section (lines 1124–1165)**

The `png_tasks` block that calls `_render_html_to_png` in a ThreadPool is no longer needed — PNGs are generated inline above. Replace the entire block (from `png_tasks: List[...]` through the `advance("导出单链 PNG", ...)` loop) with:

```python
# Collect already-generated individual PNG paths
rendered_png_paths: Dict[str, Path] = {}
for chain in generated_chains:
    png_path = sample_dirs["individual_png"] / f"{sample_safe_name}__{chain}_treemap.png"
    if png_path.exists() and png_path.is_file():
        rendered_png_paths[chain] = png_path
```

- [ ] **Step 13: Update `_build_static_viewer_html()` to display PNG instead of HTML iframe**

The viewer.html currently shows treemap HTML in an iframe. Change to show PNG in an `<img>` tag. In `_build_static_viewer_html()`:

Replace the iframe element:
```html
<iframe id="viewerFrame" title="treemap viewer"></iframe>
```
With:
```html
<div style="display:flex;align-items:center;justify-content:center;min-height:100vh;background:#fff">
  <img id="viewerImage" alt="treemap" style="max-width:100%;max-height:100vh;object-fit:contain" />
</div>
```

And in the JavaScript, replace all iframe-related logic (`frame.src = ...`) with image logic (`viewerImage.src = entry.png`).

- [ ] **Step 14: Commit**

```bash
git add flask_app/services/treemap_report_service.py
git commit -m "refactor: replace D3.js HTML/headless-browser pipeline with matplotlib direct rendering"
```

---

### Task 4: Update `treemap.html` template — simplify options

**Files:**
- Modify: `flask_app/templates/analysis/treemap.html`
- Modify: `flask_app/static/js/treemap_analysis.js` (if needed)

- [ ] **Step 1: Remove now-irrelevant UI controls**

In the standalone treemap page (`treemap.html`), check if there are layout_mode/style/canvas_shape selectors that referenced D3.js-specific options. The `layout_mode` still makes sense (tetris vs qr), but remove:
- `style` selector (classic/minimal — D3.js specific)

Keep:
- `layoutModeSelect` (tetris / qr)
- `canvasShapeSelect` can be removed (we only support square now) or simplified

Do NOT change anything in `script_hub.html` for the charts section — the Script Hub charts module delegates to the treemap API and doesn't expose treemap-specific config.

- [ ] **Step 2: Commit**

```bash
git add flask_app/templates/analysis/treemap.html flask_app/static/js/treemap_analysis.js
git commit -m "refactor: simplify treemap standalone page options after matplotlib migration"
```

---

### Task 5: Integration test and verification

**Files:**
- Create: `flask_app/tests/test_treemap_plotter.py`

- [ ] **Step 1: Write unit test for the plotter**

```python
"""Tests for treemap_plotter module."""
import tempfile
from pathlib import Path

import pytest

from flask_app.services.treemap_plotter import (
    generate_treemap,
    _load_plot_df,
    _make_hierarchy_rects,
    _pack_tetrominos,
    _squarify_items,
    _normalize_sizes,
    CANVAS_W,
    CANVAS_H,
)


def test_normalize_sizes():
    result = _normalize_sizes([10.0, 20.0, 30.0], 100, 100)
    total = sum(result)
    assert abs(total - 10000) < 1.0  # dx * dy
    # Proportions preserved
    ratios = [r / total for r in result]
    assert abs(ratios[0] - 10/60) < 0.01
    assert abs(ratios[1] - 20/60) < 0.01
    assert abs(ratios[2] - 30/60) < 0.01


def test_squarify_items_basic():
    items = [
        {"name": "A", "value": 10},
        {"name": "B", "value": 20},
    ]
    rects = _squarify_items(items, 0, 0, 100, 100, "value")
    assert len(rects) == 2
    # All rects should be within canvas bounds
    for r in rects:
        assert 0 <= r["x"] <= CANVAS_W
        assert 0 <= r["y"] <= CANVAS_H
        assert r["dx"] > 0
        assert r["dy"] > 0


def test_generate_treemap_tetris(tmp_path):
    """Integration test: generate a Tetris treemap from a small CSV."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text("V,J,CDR3(pep),copy\nTRBV1,TRBJ1,CASSA,100\nTRBV1,TRBJ1,CASSB,50\nTRBV2,TRBJ2,CASSC,25\n")

    output_path = tmp_path / "output.png"
    result = generate_treemap(csv_path, output_path, mode="tetris")
    assert result.exists()
    assert result.stat().st_size > 1000  # should be a real image


def test_generate_treemap_qr(tmp_path):
    """Integration test: generate a QR treemap from a small CSV."""
    csv_path = tmp_path / "test_qr.csv"
    csv_path.write_text("V,J,CDR3(pep),copy\nTRBV1,TRBJ1,CASSA,100\nTRBV1,TRBJ1,CASSB,50\n")

    output_path = tmp_path / "output_qr.png"
    result = generate_treemap(csv_path, output_path, mode="qr")
    assert result.exists()
    assert result.stat().st_size > 1000


def test_load_plot_df_min_count(tmp_path):
    csv_path = tmp_path / "test_min.csv"
    csv_path.write_text("V,J,CDR3(pep),copy\nTRBV1,TRBJ1,CASSA,100\nTRBV1,TRBJ1,CASSB,0\n")

    df = _load_plot_df(csv_path, "CDR3(pep)", "copy", "V", "J", min_count=1)
    # The row with copy=0 should be filtered out
    assert len(df) == 1
    assert df.iloc[0]["copy"] == 100
```

- [ ] **Step 2: Run tests**

Run: `pytest flask_app/tests/test_treemap_plotter.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 3: Verify existing tests still pass**

Run: `pytest flask_app/tests/ -v --ignore=flask_app/tests/test_treemap_plotter.py -x`
Expected: No regressions from the changes.

- [ ] **Step 4: Verify import chain**

Run:
```bash
python -c "from flask_app.services.treemap_plotter import generate_treemap; print('OK')"
python -c "from flask_app.services.treemap_renderer import detect_columns, read_repertoire_rows, open_text_file; print('OK')"
python -c "from flask_app.services.treemap_report_service import get_treemap_report_service; print('OK')"
python -c "from flask_app.services.chord_report_service import ChordReportService; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add flask_app/tests/test_treemap_plotter.py
git commit -m "test: add unit tests for matplotlib treemap plotter"
```

---

### Task 6: Manual verification — launch app and run through Script Hub charts workflow

**Files:** None (verification only)

- [ ] **Step 1: Start the Flask dev server**

```bash
python -m flask --app flask_app.app run --debug
```

- [ ] **Step 2: Navigate to Script Hub → Charts section**

Open `http://127.0.0.1:5000/analysis/script-hub` in a browser.

- [ ] **Step 3: Complete the charts workflow**

1. Select a PEP path with repertoire data
2. Pick chains (TRA, TRB, etc.)
3. Select samples
4. Map CDR3/Copy/V/J fields
5. Ensure "Treemap" checkbox is checked
6. Click "生成综合图表"

- [ ] **Step 4: Verify results**

After the job completes:
1. Open the viewer.html link
2. Verify treemap PNG displays correctly
3. Download the ZIP and verify it contains:
   - Per-chain PNG files in `<sample>/individual_treemaps/PNG/`
   - TopClone CSVs in `<sample>/topclone/CSV/`
   - 7-chain overview PNG in `<sample>/7chain_treemaps/PNG/`
   - No empty HTML directories

- [ ] **Step 5: Verify both modes**

Run twice — once with Tetris mode, once with QR mode — and verify the visual output differs appropriately:
- QR: rounded rectangles with visible gaps
- Tetris: grid of tetromino blocks

---

### Task 7: Cleanup — remove unused imports and dead code

**Files:**
- Modify: `flask_app/services/treemap_renderer.py`
- Modify: `flask_app/services/treemap_report_service.py`

- [ ] **Step 1: Remove `subprocess` import from treemap_report_service.py**

The `subprocess` import was only used for headless browser calls. Remove it.

- [ ] **Step 2: Remove `load_d3_script_tag` from treemap_renderer.py**

If nothing else imports `load_d3_script_tag`, remove it. Check first:
```bash
grep -r "load_d3_script_tag" flask_app/
```
If only defined and not imported elsewhere, delete the function and remove `urllib.request` import.

- [ ] **Step 3: Remove `read_repertoire` import if no longer used**

Check if `read_repertoire` is still used in treemap_report_service.py after the refactor. The `read_repertoire_rows` is still used for topclone CSV. `read_repertoire` returns aggregated clones (different from `read_repertoire_rows`). Check usage and clean up.

- [ ] **Step 4: Run full test suite one more time**

```bash
pytest flask_app/tests/ -v
```

- [ ] **Step 5: Final commit**

```bash
git add flask_app/services/treemap_renderer.py flask_app/services/treemap_report_service.py
git commit -m "chore: remove unused imports and dead code after treemap matplotlib migration"
```
