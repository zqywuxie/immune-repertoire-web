"""
Matplotlib-based treemap renderer for immune repertoire clonotype visualization.

Two modes:
  - "qr": hierarchical rounded rectangles (V→J→CDR3), FancyBboxPatch
  - "tetris": same hierarchy, each clone is one scaled I/O/T/S/Z/J/L tetromino

Canvas defaults to square 1000×1000.  Portrait mode follows the reference
treemap_group_vertical.py script: 700×1500 canvas, 5.6×12 inches, 300 DPI.
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
PALETTE_OFFSET = 123
ORDER_MODE = "copy"
FLIP_X = True
FLIP_Y = True
SWAP_XY = False

CANVAS_PRESETS: Dict[str, Dict[str, float]] = {
    "square": {"canvas_w": 1000.0, "canvas_h": 1000.0, "fig_w": 10.0, "fig_h": 10.0},
    "portrait": {"canvas_w": 700.0, "canvas_h": 1500.0, "fig_w": 5.6, "fig_h": 12.0},
}

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


def _rgb01_to_hex(color: Tuple[float, float, float]) -> str:
    """Convert an (r, g, b) tuple in [0,1] to a hex color string."""
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(round(float(color[0]) * 255)))),
        max(0, min(255, int(round(float(color[1]) * 255)))),
        max(0, min(255, int(round(float(color[2]) * 255)))),
    )


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
        key_seed = _stable_int(row["_entry_id"]) + PALETTE_OFFSET
        palette_idx = key_seed % palette_size
        colors.append(_hex_to_rgb01(MOSAIC_REFERENCE_PALETTE[palette_idx]))
    return colors


def _canvas_spec(canvas_shape: str = "square") -> Dict[str, float]:
    return CANVAS_PRESETS.get(str(canvas_shape or "square").strip().lower(), CANVAS_PRESETS["square"])


def _sort_usage_df(
    df: pd.DataFrame,
    keys: List[str],
    value_col: str,
    order_mode: str = ORDER_MODE,
) -> pd.DataFrame:
    """Sort usage rows the same way as the vertical reference script."""
    order_mode = str(order_mode or "copy").strip().lower()
    if order_mode == "input":
        return df.sort_values("_source_order", ascending=True).reset_index(drop=True)
    if order_mode == "name":
        return df.sort_values(keys, ascending=[True] * len(keys)).reset_index(drop=True)
    return df.sort_values([value_col, "_source_order"], ascending=[False, True]).reset_index(drop=True)


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

    plot_df = _sort_usage_df(plot_df, [v_col, j_col, cdr3_col], copy_col)

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
    plot_df["_rank"] = list(range(1, len(plot_df) + 1))
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

def _make_vj_rects(
    plot_df: pd.DataFrame,
    v_col: str,
    j_col: str,
    copy_col: str,
    canvas_w: float = CANVAS_W,
    canvas_h: float = CANVAS_H,
    order_mode: str = ORDER_MODE,
) -> List[Dict[str, Any]]:
    """Build squarified V→J hierarchy and return J-level rectangles."""
    v_df = plot_df.groupby(v_col, as_index=False, sort=False).agg(
        {copy_col: "sum", "_source_order": "min"}
    )
    v_df = _sort_usage_df(v_df, [v_col], copy_col, order_mode=order_mode)
    v_rects = _squarify_items(
        v_df.to_dict("records"), 0.0, 0.0, canvas_w, canvas_h, copy_col
    )

    j_level_rects: List[Dict[str, Any]] = []
    for v_rect in v_rects:
        v_value = v_rect[v_col]
        v_sub = plot_df[plot_df[v_col] == v_value].copy()
        if v_sub.empty:
            continue

        j_df = v_sub.groupby(j_col, as_index=False, sort=False).agg(
            {copy_col: "sum", "_source_order": "min"}
        )
        j_df = _sort_usage_df(j_df, [j_col], copy_col, order_mode=order_mode)
        j_rects = _squarify_items(
            j_df.to_dict("records"),
            v_rect["x"],
            v_rect["y"],
            v_rect["dx"],
            v_rect["dy"],
            copy_col,
        )
        for j_rect in j_rects:
            item = j_rect.copy()
            item["_v_value"] = v_value
            item["_j_value"] = j_rect[j_col]
            j_level_rects.append(item)

    return j_level_rects


def _make_hierarchy_rects(
    plot_df: pd.DataFrame,
    v_col: str,
    j_col: str,
    cdr3_col: str,
    copy_col: str,
    canvas_w: float = CANVAS_W,
    canvas_h: float = CANVAS_H,
    order_mode: str = ORDER_MODE,
) -> List[Dict[str, Any]]:
    """Build squarified V→J→CDR3 hierarchy. Returns leaf (CDR3) rects."""
    leaf_rects: List[Dict[str, Any]] = []

    for j_rect in _make_vj_rects(plot_df, v_col, j_col, copy_col, canvas_w, canvas_h, order_mode=order_mode):
        v_value = j_rect["_v_value"]
        j_value = j_rect["_j_value"]
        v_sub = plot_df[plot_df[v_col] == v_value].copy()
        if v_sub.empty:
            continue

        clone_df = v_sub[v_sub[j_col] == j_value].copy()
        if clone_df.empty:
            continue

        # CDR3-level within the J rect
        clone_df = _sort_usage_df(clone_df, [cdr3_col], copy_col, order_mode=order_mode)

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


def _transform_rects(
    rects: List[Dict[str, Any]],
    canvas_w: float,
    canvas_h: float,
    *,
    flip_x: bool = FLIP_X,
    flip_y: bool = FLIP_Y,
    swap_xy: bool = SWAP_XY,
) -> List[Dict[str, Any]]:
    """Apply the reference script's final orientation transform."""
    transformed: List[Dict[str, Any]] = []
    for rect in rects:
        item = rect.copy()
        x = float(item["x"])
        y = float(item["y"])
        dx = float(item["dx"])
        dy = float(item["dy"])

        if flip_x:
            x = canvas_w - x - dx
        if flip_y:
            y = canvas_h - y - dy
        if swap_xy:
            x, y, dx, dy = y, x, dy, dx

        item.update({"x": x, "y": y, "dx": dx, "dy": dy})
        transformed.append(item)
    return transformed


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
    canvas_w: float = CANVAS_W,
    canvas_h: float = CANVAS_H,
) -> None:
    """Add a rounded (pill-shaped) FancyBboxPatch to the axes."""
    gap, rounding = _block_style(dx, dy)

    # Halve gaps at canvas edges so rectangles don't pull away from borders.
    left_gap = 0.0 if x <= 0 else gap / 2
    top_gap = 0.0 if y <= 0 else gap / 2
    right_gap = 0.0 if x + dx >= canvas_w - 1e-6 else gap / 2
    bottom_gap = 0.0 if y + dy >= canvas_h - 1e-6 else gap / 2

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
    cdr3_col: str,
    copy_col: str,
    canvas_shape: str = "square",
) -> None:
    """Draw a single QR-mode (rounded-rectangle) treemap to *output_path* (PNG)."""
    spec = _canvas_spec(canvas_shape)
    canvas_w = spec["canvas_w"]
    canvas_h = spec["canvas_h"]
    rects = _make_hierarchy_rects(plot_df, v_col, j_col, cdr3_col, copy_col, canvas_w, canvas_h)
    rects = _transform_rects(rects, canvas_w, canvas_h)

    fig = plt.figure(figsize=(spec["fig_w"], spec["fig_h"]), dpi=DPI, frameon=False)
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
            canvas_w=canvas_w,
            canvas_h=canvas_h,
        )

    ax.set_xlim(0, canvas_w)
    ax.set_ylim(canvas_h, 0)
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
    idx = _stable_int(ident) % len(SHAPE_ORDER)
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
    seed: int = PALETTE_OFFSET,
) -> Optional[Tuple[List[Tuple[int, int]], int, int, int]]:
    """Try to place a tetromino. Returns (cells, scale, x, y) or None."""
    for scale in range(desired_scale, 0, -1):
        rng = random.Random(seed)
        rot_indices = list(range(len(rotations)))
        rng.shuffle(rot_indices)
        for ri in rot_indices:
            cells = rotations[ri]
            dims = _shape_dimensions(cells)
            w_px = dims["w"] * scale
            h_px = dims["h"] * scale

            # Deterministic first-fit keeps each V/J region compact.  Random
            # position scans leave large holes when clone counts are high.
            for py in range(rows - h_px + 1):
                row_range = range(cols - w_px + 1)
                if py % 2:
                    row_range = reversed(range(cols - w_px + 1))
                for px in row_range:
                    if _fits(occupancy, px, py, cells, scale):
                        return (cells, scale, px, py)
            # A second pass from the bottom improves fit in tall portrait strips.
            for py in range(rows - h_px, -1, -1):
                for px in range(cols - w_px + 1):
                    if _fits(occupancy, px, py, cells, scale):
                        return (cells, scale, px, py)
            for px in range(cols - w_px + 1):
                for py in range(rows - h_px + 1):
                    if _fits(occupancy, px, py, cells, scale):
                        return (cells, scale, px, py)
    return None


def _compute_tetromino_scales(
    items: List[Dict[str, Any]],
    cols: int,
    rows: int,
    fill_ratio: float = 0.94,
) -> List[int]:
    """Scale clones so tetromino cell area attempts to fill the local grid."""
    if not items:
        return []
    target_cells = max(len(items) * 4, int(cols * rows * fill_ratio))
    total_copy = sum(float(item.get("_copy_val", 0) or 0) for item in items) or 1.0
    max_scale = max(1, min(8, int(max(1, min(cols, rows)) / 4)))
    adjust = target_cells / total_copy
    scales = [
        max(1, min(max_scale, int(round(math.sqrt((float(item.get("_copy_val", 0) or 0) * adjust) / 4)))))
        for item in items
    ]
    for _ in range(12):
        occupied = sum(4 * scale * scale for scale in scales)
        if occupied <= target_cells * 1.03:
            break
        adjust *= target_cells / max(occupied, 1)
        scales = [
            max(1, min(max_scale, int(round(math.sqrt((float(item.get("_copy_val", 0) or 0) * adjust) / 4)))))
            for item in items
        ]
    return scales


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

    initial_cell = max(1.6, math.sqrt(region_area / max(n_clones * 4, 1)) * 0.72)
    cols = max(1, int(rdx / initial_cell))
    rows = max(1, int(rdy / initial_cell))
    cell_size = min(rdx / cols, rdy / rows)

    best_result: List[Dict[str, Any]] = []
    best_placed = 0

    # Try progressively smaller cell sizes (more grid cells = more precision)
    cell_sizes_to_try: List[float] = []
    current_cs = cell_size
    min_cell = max(0.9, min(rdx, rdy) / 220)
    while current_cs >= min_cell:
        cell_sizes_to_try.append(current_cs)
        current_cs *= 0.82
    if not cell_sizes_to_try:
        cell_sizes_to_try = [cell_size]

    for cell_sz in cell_sizes_to_try:
        cols = max(1, int(rdx / cell_sz))
        rows = max(1, int(rdy / cell_sz))
        if cols < 2 or rows < 2:
            continue
        occupancy = np.zeros((rows, cols), dtype=np.int32)
        placed: List[Dict[str, Any]] = []
        scales = _compute_tetromino_scales(sorted_items, cols, rows, fill_ratio=0.94)

        for item, desired_scale in zip(sorted_items, scales):
            shape_name = _shape_key_for_record(item, v_col, j_col, cdr3_col)
            cells = SHAPES.get(shape_name, SHAPES["O"])
            rotations = _build_rotations(cells)

            item_seed = _stable_int(item.get(cdr3_col, "")) ^ PALETTE_OFFSET
            result = _place_tetromino(occupancy, cols, rows, rotations, desired_scale, seed=item_seed)
            if result is None:
                continue

            cells_used, scale, px, py = result
            _stamp(occupancy, px, py, cells_used, scale)

            # Convert grid coords back to canvas coords
            dims = _shape_dimensions(cells_used)
            placed_item = item.copy()
            placed_item.update({
                "x": rx + px * cell_sz,
                "y": ry + py * cell_sz,
                "dx": dims["w"] * scale * cell_sz,
                "dy": dims["h"] * scale * cell_sz,
                "_color": item.get("_color"),
                "cells": cells_used,
                "scale": scale,
                "cell_size": cell_sz,
            })
            placed.append(placed_item)

        occupied_cells = int(np.count_nonzero(occupancy))
        best_cells = sum(
            4 * int(item.get("scale", 1)) * int(item.get("scale", 1))
            for item in best_result
        )
        if len(placed) > best_placed or (len(placed) == best_placed and occupied_cells > best_cells):
            best_placed = len(placed)
            best_result = placed

    return best_result


def _draw_tetromino_cells(ax: plt.Axes, tetro: Dict[str, Any]) -> None:
    """Draw one placed tetromino as its component cells with a tiny gap."""
    cell_size = float(tetro.get("cell_size") or 1.0)
    scale = int(tetro.get("scale") or 1)
    color = tetro.get("_color")
    gap = min(cell_size * 0.045, 0.28)
    block_size = max(scale * cell_size - gap, 0.01)
    for cx, cy in tetro.get("cells") or []:
        x = float(tetro["x"]) + cx * scale * cell_size + gap / 2
        y = float(tetro["y"]) + cy * scale * cell_size + gap / 2
        rect = Rectangle(
            (x, y),
            block_size,
            block_size,
            linewidth=0,
            edgecolor=None,
            facecolor=color,
            antialiased=False,
        )
        ax.add_patch(rect)


def _add_square_block(
    ax: plt.Axes,
    x: float,
    y: float,
    dx: float,
    dy: float,
    color: Tuple[float, float, float],
    canvas_w: float,
    canvas_h: float,
) -> None:
    """Draw a dense, hard-edged block for tetris mode."""
    gap, _ = _block_style(dx, dy)
    gap = min(gap, 0.18)
    left_gap = 0.0 if x <= 0 else gap / 2
    top_gap = 0.0 if y <= 0 else gap / 2
    right_gap = 0.0 if x + dx >= canvas_w - 1e-6 else gap / 2
    bottom_gap = 0.0 if y + dy >= canvas_h - 1e-6 else gap / 2
    x_inner = x + left_gap
    y_inner = y + top_gap
    dx_inner = max(dx - left_gap - right_gap, 0.01)
    dy_inner = max(dy - top_gap - bottom_gap, 0.01)
    ax.add_patch(
        Rectangle(
            (x_inner, y_inner),
            dx_inner,
            dy_inner,
            linewidth=0,
            edgecolor=None,
            facecolor=color,
            antialiased=False,
        )
    )


def _draw_tetris_treemap(
    plot_df: pd.DataFrame,
    output_path: Path,
    v_col: str,
    j_col: str,
    copy_col: str,
    cdr3_col: str,
    canvas_shape: str = "square",
) -> None:
    """Draw a dense hard-edged treemap to *output_path* (PNG).

    It keeps the "tetris" visual direction as sharp mosaic blocks, but uses
    the reference script's area-preserving V→J→CDR3 hierarchy to avoid the
    large empty gaps created by free tetromino packing.
    """
    spec = _canvas_spec(canvas_shape)
    canvas_w = spec["canvas_w"]
    canvas_h = spec["canvas_h"]

    rects = _make_hierarchy_rects(plot_df, v_col, j_col, cdr3_col, copy_col, canvas_w, canvas_h)
    rects = _transform_rects(rects, canvas_w, canvas_h)

    fig = plt.figure(figsize=(spec["fig_w"], spec["fig_h"]), dpi=DPI, frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    for rect in rects:
        _add_square_block(
            ax=ax,
            x=rect["x"],
            y=rect["y"],
            dx=rect["dx"],
            dy=rect["dy"],
            color=rect["_color"],
            canvas_w=canvas_w,
            canvas_h=canvas_h,
        )

    ax.set_xlim(0, canvas_w)
    ax.set_ylim(canvas_h, 0)
    ax.set_aspect("equal", adjustable="box")
    ax.margins(0, 0)
    ax.axis("off")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=DPI, facecolor=BG_COLOR, pad_inches=0)
    plt.close(fig)


def _copy_value(value: Any) -> Any:
    number = float(value or 0)
    return int(number) if number.is_integer() else number


def _clone_payload(
    record: Dict[str, Any],
    mode: str,
    v_col: str,
    j_col: str,
    cdr3_col: str,
    copy_col: str,
) -> Dict[str, Any]:
    clone_id = str(record.get("_entry_id") or f"{record.get(v_col, '')}|{record.get(j_col, '')}|{record.get(cdr3_col, '')}")
    color = record.get("_color") or (0.0, 0.0, 0.0)
    return {
        "clone_id": clone_id,
        "rank": int(record.get("_rank") or 0),
        "cdr3": str(record.get(cdr3_col, "")),
        "v": str(record.get(v_col, "")),
        "j": str(record.get(j_col, "")),
        "copy": _copy_value(record.get(copy_col, 0)),
        "color": _rgb01_to_hex(color),
        "mode": mode,
    }


def _cell_rect(
    x: float,
    y: float,
    cell_w: float,
    cell_h: float,
    outer_gap: float,
    inner_gap: float,
    is_left: bool,
    is_right: bool,
    is_top: bool,
    is_bottom: bool,
) -> Dict[str, float]:
    left_gap = outer_gap if is_left else inner_gap / 2
    right_gap = outer_gap if is_right else inner_gap / 2
    top_gap = outer_gap if is_top else inner_gap / 2
    bottom_gap = outer_gap if is_bottom else inner_gap / 2
    return {
        "x": x + left_gap,
        "y": y + top_gap,
        "dx": max(cell_w - left_gap - right_gap, 0.01),
        "dy": max(cell_h - top_gap - bottom_gap, 0.01),
    }


def _build_tetris_clone_shape(
    rect: Dict[str, Any],
    v_col: str,
    j_col: str,
    cdr3_col: str,
) -> Dict[str, Any]:
    """Fit one clone as one scaled tetromino inside its target rectangle."""
    x = float(rect.get("x", 0))
    y = float(rect.get("y", 0))
    dx = max(float(rect.get("dx", 0)), 0.0)
    dy = max(float(rect.get("dy", 0)), 0.0)
    if dx <= 0 or dy <= 0:
        return {"shape": "O", "rotation": 0, "rect": {"x": x, "y": y, "dx": 0.0, "dy": 0.0}, "cells": []}

    seed = _stable_int(f"{rect.get(v_col, '')}|{rect.get(j_col, '')}|{rect.get(cdr3_col, '')}")
    shape_key = SHAPE_ORDER[seed % len(SHAPE_ORDER)]
    rotations = _build_rotations(SHAPES[shape_key])

    best_rotation_index = 0
    best_rotation = rotations[0]
    best_cell_size = 0.0
    for rotation_index, rotation in enumerate(rotations):
        dims = _shape_dimensions(rotation)
        cell_size = min(dx / max(dims["w"], 1), dy / max(dims["h"], 1))
        if cell_size > best_cell_size:
            best_cell_size = cell_size
            best_rotation_index = rotation_index
            best_rotation = rotation

    dims = _shape_dimensions(best_rotation)
    cell_size = max(best_cell_size * 0.92, 0.01)
    shape_w = dims["w"] * cell_size
    shape_h = dims["h"] * cell_size
    origin_x = x + (dx - shape_w) / 2
    origin_y = y + (dy - shape_h) / 2
    visual_cell = max(cell_size, 0.01)
    outer_gap = min(visual_cell * 0.055, 0.55)
    inner_gap = min(visual_cell * 0.025, 0.2)

    cells: List[Dict[str, float]] = []
    max_cx = max(cx for cx, _ in best_rotation)
    max_cy = max(cy for _, cy in best_rotation)
    for cx, cy in best_rotation:
        cells.append(
            _cell_rect(
                x=origin_x + cx * cell_size,
                y=origin_y + cy * cell_size,
                cell_w=cell_size,
                cell_h=cell_size,
                outer_gap=outer_gap,
                inner_gap=inner_gap,
                is_left=cx == 0,
                is_right=cx == max_cx,
                is_top=cy == 0,
                is_bottom=cy == max_cy,
            )
        )

    return {
        "shape": shape_key,
        "rotation": best_rotation_index,
        "rect": {"x": origin_x, "y": origin_y, "dx": shape_w, "dy": shape_h},
        "cells": cells,
    }


def _flatten_block_cells(blocks: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    cells: List[Dict[str, float]] = []
    for block in blocks:
        cells.extend(block.get("cells") or [])
    return cells


def build_treemap_layout_from_df(
    plot_df: pd.DataFrame,
    mode: str,
    v_col: str,
    j_col: str,
    cdr3_col: str,
    copy_col: str,
    canvas_shape: str = "square",
) -> Dict[str, Any]:
    """Build a JSON-serializable layout used by both PNG and interactive viewer."""
    mode = str(mode or "tetris").strip().lower()
    if mode not in {"tetris", "qr"}:
        raise ValueError(f"Unsupported mode: {mode!r}. Use 'tetris' or 'qr'.")

    spec = _canvas_spec(canvas_shape)
    canvas_w = spec["canvas_w"]
    canvas_h = spec["canvas_h"]
    items: List[Dict[str, Any]] = []

    if mode == "qr":
        rects = _make_hierarchy_rects(plot_df, v_col, j_col, cdr3_col, copy_col, canvas_w, canvas_h)
        rects = _transform_rects(rects, canvas_w, canvas_h)
        for rect in rects:
            item = _clone_payload(rect, mode, v_col, j_col, cdr3_col, copy_col)
            item_rect = {
                "x": float(rect["x"]),
                "y": float(rect["y"]),
                "dx": float(rect["dx"]),
                "dy": float(rect["dy"]),
            }
            item["rect"] = item_rect
            item["cells"] = [item_rect.copy()]
            items.append(item)
    else:
        rects = _make_hierarchy_rects(plot_df, v_col, j_col, cdr3_col, copy_col, canvas_w, canvas_h)
        rects = _transform_rects(rects, canvas_w, canvas_h)
        for rect in rects:
            item = _clone_payload(rect, mode, v_col, j_col, cdr3_col, copy_col)
            shape_layout = _build_tetris_clone_shape(rect, v_col, j_col, cdr3_col)
            item["shape"] = shape_layout["shape"]
            item["rotation"] = shape_layout["rotation"]
            item["rect"] = shape_layout["rect"]
            item["target_rect"] = {
                "x": float(rect["x"]),
                "y": float(rect["y"]),
                "dx": float(rect["dx"]),
                "dy": float(rect["dy"]),
            }
            item["cells"] = shape_layout["cells"]
            if item["cells"]:
                items.append(item)

    return {
        "mode": mode,
        "canvas_shape": canvas_shape,
        "canvas": {
            "width": canvas_w,
            "height": canvas_h,
            "fig_width": spec["fig_w"],
            "fig_height": spec["fig_h"],
            "dpi": DPI,
        },
        "items": items,
    }


def render_treemap_layout(layout: Dict[str, Any], output_path: Path) -> Path:
    """Render a layout generated by build_treemap_layout* to a PNG file."""
    canvas = layout.get("canvas") or {}
    canvas_w = float(canvas.get("width") or CANVAS_W)
    canvas_h = float(canvas.get("height") or CANVAS_H)
    fig_w = float(canvas.get("fig_width") or FIG_W)
    fig_h = float(canvas.get("fig_height") or FIG_H)
    mode = str(layout.get("mode") or "tetris").lower()

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=DPI, frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    for item in layout.get("items") or []:
        color = _hex_to_rgb01(str(item.get("color") or "#000000"))
        if mode == "qr":
            rect = item.get("rect") or {}
            _add_round_rect(
                ax=ax,
                x=float(rect.get("x", 0)),
                y=float(rect.get("y", 0)),
                dx=float(rect.get("dx", 0)),
                dy=float(rect.get("dy", 0)),
                color=color,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
            )
            continue

        block_cells = item.get("cells") or _flatten_block_cells(item.get("blocks") or [])
        for cell in block_cells:
            ax.add_patch(
                Rectangle(
                    (float(cell.get("x", 0)), float(cell.get("y", 0))),
                    float(cell.get("dx", 0)),
                    float(cell.get("dy", 0)),
                    linewidth=0,
                    edgecolor=None,
                    facecolor=color,
                    antialiased=False,
                )
            )

    ax.set_xlim(0, canvas_w)
    ax.set_ylim(canvas_h, 0)
    ax.set_aspect("equal", adjustable="box")
    ax.margins(0, 0)
    ax.axis("off")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=DPI, facecolor=BG_COLOR, pad_inches=0)
    plt.close(fig)
    return output_path


def build_treemap_layout(
    csv_path: Path,
    mode: str = "tetris",
    canvas_shape: str = "square",
    cdr3_col: str = "CDR3(pep)",
    copy_col: str = "copy",
    v_col: str = "V",
    j_col: str = "J",
    min_count: int = 1,
) -> Dict[str, Any]:
    """Build an interactive treemap layout from a repertoire CSV/TSV file."""
    plot_df = _load_plot_df(
        Path(csv_path),
        cdr3_col=cdr3_col,
        copy_col=copy_col,
        v_col=v_col,
        j_col=j_col,
        min_count=min_count,
    )
    return build_treemap_layout_from_df(
        plot_df,
        mode=mode,
        v_col=v_col,
        j_col=j_col,
        cdr3_col=cdr3_col,
        copy_col=copy_col,
        canvas_shape=canvas_shape,
    )


# ================================================================
# Public API
# ================================================================

def generate_treemap(
    csv_path: Path,
    output_path: Path,
    mode: str = "tetris",
    canvas_shape: str = "square",
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
        ``"tetris"`` for hard-edged mosaic mode, ``"qr"`` for rounded-rectangle mode.
    canvas_shape : str
        ``"square"`` or ``"portrait"``.  Portrait follows treemap_group_vertical.py.
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

    layout = build_treemap_layout(
        csv_path,
        mode=mode,
        canvas_shape=canvas_shape,
        cdr3_col=cdr3_col,
        copy_col=copy_col,
        v_col=v_col,
        j_col=j_col,
        min_count=min_count,
    )
    return render_treemap_layout(layout, output_path)
