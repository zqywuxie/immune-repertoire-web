"""
Matplotlib-based treemap renderer for immune repertoire clonotype visualization.

Two modes:
  - "qr": hierarchical rounded rectangles (V→J→CDR3), FancyBboxPatch
  - "tetris": same hierarchy, clones packed as tetromino shapes on a grid

Canvas: square 1000×1000, figure 10×10 inches, 300 DPI → 3000×3000 px output.
"""
from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
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

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

MOSAIC_REFERENCE_PALETTE = [
    "#981840",
    "#104008",
    "#a020b0",
    "#e8c040",
    "#f8e838",
    "#8098d0",
    "#e89080",
    "#e860d0",
    "#901098",
    "#70a0e8",
    "#a8f888",
    "#286028",
    "#58d000",
    "#d0b040",
    "#2818f0",
    "#c0f018",
    "#684820",
    "#685820",
    "#b088e0",
    "#988060",
    "#e06040",
    "#50d018",
    "#2058a0",
    "#b84858",
    "#10c8a8",
    "#a02080",
    "#c878c8",
    "#b858b8",
    "#d8e008",
    "#b80068",
    "#f86018",
    "#5848c8",
    "#582060",
    "#90d018",
    "#280018",
    "#10f0f8",
    "#40d830",
    "#006b4a",
    "#3ec4d1",
    "#ef0db8",
    "#80d9ab",
    "#0da12f",
    "#225bb7",
]


# ---------------------------------------------------------------------------
# Color utilities
# ---------------------------------------------------------------------------

def _hex_to_rgb01(hex_color: str) -> Tuple[float, float, float]:
    """Convert a hex color string (e.g. '#3ec7cf') to an (r, g, b) tuple of floats in [0,1]."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _stable_int(value: Any) -> int:
    """Deterministic integer hash from any value, via MD5."""
    digest = hashlib.md5(str(value).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _assign_colors(
    plot_df: pd.DataFrame,
) -> List[Tuple[float, float, float]]:
    """Deterministic color assignment from MOSAIC_REFERENCE_PALETTE using _entry_id column.

    Each clone's _entry_id is hashed to pick a palette colour.  This is the
    ``mosaic-reference`` mode from the reference script.
    """
    palette_size = len(MOSAIC_REFERENCE_PALETTE)
    colors: List[Tuple[float, float, float]] = []
    for _, row in plot_df.reset_index(drop=True).iterrows():
        key_seed = _stable_int(row["_entry_id"]) + RANDOM_SEED
        palette_idx = key_seed % palette_size
        colors.append(_hex_to_rgb01(MOSAIC_REFERENCE_PALETTE[palette_idx]))
    return colors


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_plot_df(
    csv_path: Path,
    cdr3_col: str = "CDR3(pep)",
    copy_col: str = "copy",
    v_col: str = "V",
    j_col: str = "J",
    min_count: int = 1,
) -> pd.DataFrame:
    """Load and aggregate repertoire data for treemap plotting.

    Groups by V+J+CDR3, sums copy, assigns colours via ``_assign_colors``.
    Adds ``_entry_id`` (V|J|CDR3) and ``_color`` columns.
    Returns DataFrame or raises ValueError if no valid data remains after filtering.
    """
    csv_path_str = str(csv_path).lower()
    if csv_path_str.endswith(".csv") or csv_path_str.endswith(".csv.gz"):
        sep = ","
    else:
        sep = "\t"

    df = pd.read_csv(
        csv_path,
        sep=sep,
        usecols=[v_col, j_col, cdr3_col, copy_col],
        dtype={v_col: str, j_col: str, cdr3_col: str},
        compression="infer",
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

    # Aggregate: V-J-uCDR3 entry
    plot_df = plot_df.groupby(
        [v_col, j_col, cdr3_col], as_index=False, sort=False
    ).agg({copy_col: "sum", "_source_order": "min"})

    # Sort by copy descending, then source_order ascending
    plot_df = plot_df.sort_values(
        [copy_col, "_source_order"], ascending=[False, True]
    ).reset_index(drop=True)

    if plot_df.empty:
        raise ValueError("No valid data after filtering (empty CDR3, copy < min_count)")

    plot_df["_entry_id"] = (
        plot_df[v_col].astype(str)
        + "|"
        + plot_df[j_col].astype(str)
        + "|"
        + plot_df[cdr3_col].astype(str)
    )
    plot_df["_color"] = _assign_colors(plot_df)
    return plot_df


# ================================================================
# Squarified treemap layout algorithm
# (Bruls-Huizing-van Wijk)
# ================================================================

def _normalize_sizes(
    values: List[float], dx: float, dy: float
) -> List[float]:
    """Scale values so their area sum fills the rectangle (dx × dy)."""
    total = float(sum(values))
    if total <= 0:
        return []
    scale = (dx * dy) / total
    return [float(value) * scale for value in values]


def _worst_ratio(row: List[float], side: float) -> float:
    """Worst aspect ratio in a row."""
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
    x: float,
    y: float,
    dx: float,
    dy: float,
    prefer_vertical: bool = True,
) -> Tuple[List[Dict[str, Any]], float, float, float, float]:
    """Lay out one row of items. Returns (rects, new_x, new_y, new_dx, new_dy)."""
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

            rect = item.copy()
            rect.update(
                {
                    "x": x,
                    "y": cursor_y,
                    "dx": width,
                    "dy": height,
                    "_color": item.get("_color"),
                }
            )
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

        rect = item.copy()
        rect.update(
            {
                "x": cursor_x,
                "y": y,
                "dx": width,
                "dy": height,
                "_color": item.get("_color"),
            }
        )
        rects.append(rect)
        cursor_x += width

    return rects, x, y + height, dx, dy - height


def _squarify_items(
    items: List[Dict[str, Any]],
    x: float,
    y: float,
    dx: float,
    dy: float,
    value_key: str,
    prefer_vertical: bool = True,
) -> List[Dict[str, Any]]:
    """Bruls-Huizing-van Wijk squarified treemap layout."""
    values = [float(item[value_key]) for item in items]
    areas = _normalize_sizes(values, dx, dy)

    items = [item.copy() for item in items]
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

        laid_out, x, y, dx, dy = _layout_row(
            row, x, y, dx, dy, prefer_vertical=prefer_vertical
        )
        rects.extend(laid_out)
        row = []

    if row:
        laid_out, x, y, dx, dy = _layout_row(
            row, x, y, dx, dy, prefer_vertical=prefer_vertical
        )
        rects.extend(laid_out)

    return rects


# ================================================================
# Hierarchical rects: V → J → CDR3
# ================================================================

def _make_hierarchy_rects(
    plot_df: pd.DataFrame,
    v_col: str,
    j_col: str,
    copy_col: str,
) -> List[Dict[str, Any]]:
    """Build squarified V→J→CDR3 hierarchy. Returns leaf (CDR3) rects."""
    # V-level: group by V, squarify over full canvas
    v_df = plot_df.groupby(v_col, as_index=False, sort=False).agg(
        {copy_col: "sum", "_source_order": "min"}
    )
    v_df = v_df.sort_values("_source_order", ascending=True).reset_index(drop=True)
    v_rects = _squarify_items(
        v_df.to_dict("records"), 0.0, 0.0, CANVAS_W, CANVAS_H, copy_col
    )

    leaf_rects: List[Dict[str, Any]] = []

    for v_rect in v_rects:
        v_value = v_rect[v_col]
        v_sub = plot_df[plot_df[v_col] == v_value].copy()
        if v_sub.empty:
            continue

        # J-level within the V rect
        j_df = v_sub.groupby(j_col, as_index=False, sort=False).agg(
            {copy_col: "sum", "_source_order": "min"}
        )
        j_df = j_df.sort_values("_source_order", ascending=True).reset_index(drop=True)
        j_rects = _squarify_items(
            j_df.to_dict("records"),
            v_rect["x"],
            v_rect["y"],
            v_rect["dx"],
            v_rect["dy"],
            copy_col,
        )

        for j_rect in j_rects:
            j_value = j_rect[j_col]
            clone_df = v_sub[v_sub[j_col] == j_value].copy()
            if clone_df.empty:
                continue

            # CDR3-level within the J rect
            clone_df = clone_df.sort_values(
                [copy_col, "_source_order"], ascending=[False, True]
            ).reset_index(drop=True)

            clone_rects = _squarify_items(
                clone_df.to_dict("records"),
                j_rect["x"],
                j_rect["y"],
                j_rect["dx"],
                j_rect["dy"],
                copy_col,
            )
            leaf_rects.extend(clone_rects)

    return leaf_rects


# ================================================================
# QR mode — hierarchical rounded rectangles
# ================================================================

def _block_style(dx: float, dy: float) -> Tuple[float, float]:
    """Return (gap, rounding) for a block of the given dimensions.

    Larger blocks get bigger gaps and rounder corners so that the visual
    density is consistent across scales.
    """
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


def _add_round_rect(
    ax: plt.Axes,
    x: float,
    y: float,
    dx: float,
    dy: float,
    color: Tuple[float, float, float],
) -> None:
    """Add a rounded (pill-shaped) FancyBboxPatch to the axes."""
    gap, rounding = _block_style(dx, dy)

    # Halve gaps at canvas edges so rectangles don't pull away from borders.
    left_gap = 0.0 if x <= 0 else gap / 2
    top_gap = 0.0 if y <= 0 else gap / 2
    right_gap = 0.0 if x + dx >= CANVAS_W - 1e-6 else gap / 2
    bottom_gap = 0.0 if y + dy >= CANVAS_H - 1e-6 else gap / 2

    x_inner = x + left_gap
    y_inner = y + top_gap
    dx_inner = max(dx - left_gap - right_gap, 0.01)
    dy_inner = max(dy - top_gap - bottom_gap, 0.01)

    if dx_inner <= 0 or dy_inner <= 0:
        return

    rounding = min(rounding, min(dx_inner, dy_inner) / 2)

    patch = FancyBboxPatch(
        (x_inner, y_inner),
        dx_inner,
        dy_inner,
        boxstyle=f"round,pad=0,rounding_size={rounding}",
        linewidth=0,
        edgecolor=None,
        facecolor=color,
        antialiased=True,
    )
    ax.add_patch(patch)


def _draw_qr_treemap(
    plot_df: pd.DataFrame,
    output_path: Path,
    v_col: str,
    j_col: str,
    copy_col: str,
) -> None:
    """Draw a single QR-mode (rounded-rectangle) treemap to *output_path* (PNG)."""
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


# ================================================================
# Tetris mode — tetromino packing
# ================================================================

def _shape_key_for_record(
    record: Dict[str, Any],
    v_col: str,
    j_col: str,
    cdr3_col: str,
) -> str:
    """Deterministic shape name for a clone from its identity hash."""
    ident = f"{record[v_col]}|{record[j_col]}|{record[cdr3_col]}"
    idx = abs(hash(ident)) % len(SHAPE_ORDER)
    return SHAPE_ORDER[idx]


def _shape_dimensions(
    cells: List[Tuple[int, int]],
) -> Dict[str, int]:
    """Return {w, h} of a shape's bounding box."""
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return {"w": max(xs) - min(xs) + 1, "h": max(ys) - min(ys) + 1}


def _build_rotations(
    cells: List[Tuple[int, int]],
) -> List[List[Tuple[int, int]]]:
    """Generate all unique 90° rotations of a shape."""
    seen: set = set()
    rotations: List[List[Tuple[int, int]]] = []
    current = cells
    for _ in range(4):
        # 90-degree rotation: (x, y) → (y, -x)
        rotated = [(cy, -cx) for cx, cy in current]
        # Normalize to non-negative coordinates
        min_x = min(c[0] for c in rotated)
        min_y = min(c[1] for c in rotated)
        normed = tuple(sorted((cx - min_x, cy - min_y) for cx, cy in rotated))
        if normed not in seen:
            seen.add(normed)
            rotations.append(list(normed))
        current = list(normed)
    return rotations


def _fits(
    occupancy: np.ndarray,
    ox: int,
    oy: int,
    cells: List[Tuple[int, int]],
    scale: int,
) -> bool:
    """Check whether tetromino cells at (ox,oy) with `scale` fit in the occupancy grid."""
    rows, cols = occupancy.shape
    for cx, cy in cells:
        for sx in range(scale):
            for sy in range(scale):
                px = ox + cx * scale + sx
                py = oy + cy * scale + sy
                if px < 0 or px >= cols or py < 0 or py >= rows:
                    return False
                if occupancy[py, px] != 0:
                    return False
    return True


def _stamp(
    occupancy: np.ndarray,
    ox: int,
    oy: int,
    cells: List[Tuple[int, int]],
    scale: int,
    value: int = 1,
) -> None:
    """Mark tetromino cells in the occupancy grid."""
    for cx, cy in cells:
        for sx in range(scale):
            for sy in range(scale):
                px = ox + cx * scale + sx
                py = oy + cy * scale + sy
                occupancy[py, px] = value


def _place_tetromino(
    occupancy: np.ndarray,
    cols: int,
    rows: int,
    rotations: List[List[Tuple[int, int]]],
    desired_scale: int,
) -> Optional[Tuple[List[Tuple[int, int]], int, int, int]]:
    """Try to place a tetromino. Returns (cells, scale, x, y) or None."""
    for scale in range(desired_scale, 0, -1):
        # Try each rotation
        rng = random.Random(RANDOM_SEED)
        rot_indices = list(range(len(rotations)))
        rng.shuffle(rot_indices)
        for ri in rot_indices:
            cells = rotations[ri]
            dims = _shape_dimensions(cells)
            w_px = dims["w"] * scale
            h_px = dims["h"] * scale

            # Generate scan positions in shuffled order for variety
            positions = [(px, py) for py in range(rows - h_px + 1) for px in range(cols - w_px + 1)]
            rng.shuffle(positions)

            for px, py in positions:
                if _fits(occupancy, px, py, cells, scale):
                    return (cells, scale, px, py)
    return None


def _pack_tetrominos(
    items: List[Dict[str, Any]],
    rect: Dict[str, Any],
    v_col: str,
    j_col: str,
    cdr3_col: str,
) -> List[Dict[str, Any]]:
    """Pack clones as tetrominoes inside a J-level rectangle.

    Returns list of placed tetromino dicts with keys: x, y, dx, dy, _color, cells, scale.
    """
    rx, ry, rdx, rdy = rect["x"], rect["y"], rect["dx"], rect["dy"]
    region_area = rdx * rdy
    if region_area <= 0:
        return []

    # Sort clones by copy descending
    sorted_items = sorted(items, key=lambda it: it["_copy_val"], reverse=True)

    # Determine grid resolution: start with a cell size that gives a reasonable
    # number of cells for the number of clones to pack.
    n_clones = len(sorted_items)
    if n_clones == 0:
        return []

    initial_cell = max(2.0, math.sqrt(region_area / (n_clones * 4)) * 0.7)
    cols = max(1, int(rdx / initial_cell))
    rows = max(1, int(rdy / initial_cell))
    cell_size = min(rdx / cols, rdy / rows)

    best_result: List[Dict[str, Any]] = []
    best_placed = 0

    # Try progressively smaller cell sizes (more grid cells = more precision)
    cell_sizes_to_try: List[float] = []
    current_cs = cell_size
    while current_cs >= 2.0:
        cell_sizes_to_try.append(current_cs)
        current_cs *= 0.85
    if not cell_sizes_to_try:
        cell_sizes_to_try = [cell_size]

    for cell_sz in cell_sizes_to_try:
        cols = max(1, int(rdx / cell_sz))
        rows = max(1, int(rdy / cell_sz))
        occupancy = np.zeros((rows, cols), dtype=np.int32)
        placed: List[Dict[str, Any]] = []

        # Compute copy range for scaling
        copies = [it["_copy_val"] for it in sorted_items]
        max_copy = max(copies) if copies else 1
        min_copy = min(copies) if copies else 1
        copy_range = max_copy - min_copy if max_copy > min_copy else 1

        for item in sorted_items:
            shape_name = _shape_key_for_record(item, v_col, j_col, cdr3_col)
            cells = SHAPES.get(shape_name, SHAPES["O"])
            rotations = _build_rotations(cells)

            # Scale from 1 to 4 proportional to copy count
            copy_val = item["_copy_val"]
            desired_scale = max(1, min(4, int(1 + 3 * (copy_val - min_copy) / copy_range)))

            result = _place_tetromino(occupancy, cols, rows, rotations, desired_scale)
            if result is None:
                continue

            cells_used, scale, px, py = result
            _stamp(occupancy, px, py, cells_used, scale)

            # Convert grid coords back to canvas coords
            dims = _shape_dimensions(cells_used)
            placed.append({
                "x": rx + px * cell_sz,
                "y": ry + py * cell_sz,
                "dx": dims["w"] * scale * cell_sz,
                "dy": dims["h"] * scale * cell_sz,
                "_color": item.get("_color"),
                "cells": cells_used,
                "scale": scale,
            })

        if len(placed) > best_placed:
            best_placed = len(placed)
            best_result = placed

        if len(placed) == len(sorted_items):
            break  # all packed, no need to try smaller cells

    return best_result


def _draw_tetris_treemap(
    plot_df: pd.DataFrame,
    output_path: Path,
    v_col: str,
    j_col: str,
    copy_col: str,
    cdr3_col: str,
) -> None:
    """Draw a tetromino-grid treemap to *output_path* (PNG).

    Each V→J region is filled with tetromino-shaped clone blocks.
    """
    # 1) V-level layout
    v_df = plot_df.groupby(v_col, as_index=False, sort=False).agg(
        {copy_col: "sum", "_source_order": "min"}
    )
    v_df = v_df.sort_values("_source_order", ascending=True).reset_index(drop=True)
    v_rects = _squarify_items(
        v_df.to_dict("records"), 0.0, 0.0, CANVAS_W, CANVAS_H, copy_col
    )

    # 2) Draw figure
    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI, frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    for v_rect in v_rects:
        v_value = v_rect[v_col]
        v_sub = plot_df[plot_df[v_col] == v_value].copy()
        if v_sub.empty:
            continue

        # J-level within V
        j_df = v_sub.groupby(j_col, as_index=False, sort=False).agg(
            {copy_col: "sum", "_source_order": "min"}
        )
        j_df = j_df.sort_values("_source_order", ascending=True).reset_index(drop=True)
        j_rects = _squarify_items(
            j_df.to_dict("records"),
            v_rect["x"],
            v_rect["y"],
            v_rect["dx"],
            v_rect["dy"],
            copy_col,
        )

        for j_rect in j_rects:
            j_value = j_rect[j_col]
            clone_df = v_sub[v_sub[j_col] == j_value].copy()
            if clone_df.empty:
                continue

            # Prepare clone list with copy values
            clone_records = clone_df.to_dict("records")
            for rec in clone_records:
                rec["_copy_val"] = float(rec[copy_col])

            # Pack tetrominos into J rect
            tetrominos = _pack_tetrominos(
                clone_records, j_rect, v_col, j_col, cdr3_col
            )

            for tetro in tetrominos:
                rect = Rectangle(
                    (tetro["x"], tetro["y"]),
                    tetro["dx"],
                    tetro["dy"],
                    linewidth=0.3,
                    edgecolor="white",
                    facecolor=tetro["_color"],
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


# ================================================================
# Public API
# ================================================================

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
    """Generate a treemap PNG.

    Parameters
    ----------
    csv_path : Path
        Path to the repertoire CSV/TSV file (may be .gz compressed).
    output_path : Path
        Destination path for the PNG output.
    mode : str
        ``"tetris"`` for tetromino-grid mode, ``"qr"`` for rounded-rectangle mode.
    cdr3_col, copy_col, v_col, j_col : str
        Column names to use for CDR3, copy count, V gene, and J gene.
    min_count : int
        Minimum copy count to include a clone (default 1).

    Returns
    -------
    Path
        The *output_path* (convenience so callers can chain).
    """
    csv_path = Path(csv_path)
    output_path = Path(output_path)

    plot_df = _load_plot_df(
        csv_path,
        cdr3_col=cdr3_col,
        copy_col=copy_col,
        v_col=v_col,
        j_col=j_col,
        min_count=min_count,
    )

    if mode == "qr":
        _draw_qr_treemap(plot_df, output_path, v_col, j_col, copy_col)
    elif mode == "tetris":
        _draw_tetris_treemap(plot_df, output_path, v_col, j_col, copy_col, cdr3_col)
    else:
        raise ValueError(f"Unsupported mode: {mode!r}. Use 'tetris' or 'qr'.")

    return output_path
