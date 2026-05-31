#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hierarchical rounded treemap for immune clone abundance.

This script is intentionally separate from treemap_group.py.  It keeps the
same input assumptions but follows the iRepertoire/iRweb tree map logic:

- Each rounded rectangle represents a unique V-J-uCDR3 entry.
- The whole plot is divided by V usage, then each V area is subdivided by
  J usage, then uCDR3 entries inside each V-J combination are drawn.
- Rectangle area is proportional to copy / total copy.
- The drawing fills the full canvas; no bbox_inches="tight" is used.
- Colors use a saturated reference-style palette with deterministic jitter.
"""

import colorsys
import hashlib
import math
import os
import random
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import freeze_support

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


# ============================================================
# Config
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Hard-coded batch settings. Put input CSV/TSV files in INPUT_DIR and run this
# script directly; no command-line parameters are required.
INPUT_DIR = "E:/Desktop/IndividualProject/immune/test"
OUTPUT_DIR = os.path.join(INPUT_DIR, "results", "portrait")

CDR3_COL = "CDR3(pep)"
V_COL = "V"
J_COL = "J"
COUNT_COL = "copy"
FILE_SUFFIX = (".csv", ".tsv", ".txt", ".csv.gz", ".tsv.gz", ".txt.gz")

# Number of files to render in parallel. Values > 1 use multiple processes.
N_WORKERS = 6
SKIP_EXISTING = False
TOP_N = 0
MIN_COUNT = 1
COLOR_MODE = "mosaic-reference"
ORDER_MODE = "input"
CLONE_ORDER_MODE = "input"

# Choose the output canvas shape. Use "square" for reference-style 1:1 images,
# or "portrait" for a vertical rectangle.
CANVAS_SHAPE = "portrait"
DPI = 300

if CANVAS_SHAPE == "portrait":
    FIG_W = 5.6
    FIG_H = 12
    CANVAS_W = 700.0
    CANVAS_H = 1500.0
else:
    FIG_W = 10
    FIG_H = 10
    CANVAS_W = 1000.0
    CANVAS_H = 1000.0

# Orientation transforms were tuned for square reference images.  Portrait mode
# should be laid out directly on the tall canvas so the treemap fills the full
# rectangle instead of looking like a square plot with extra space below.
if CANVAS_SHAPE == "portrait":
    FLIP_X = False
    FLIP_Y = False
    SWAP_XY = False
else:
    FLIP_X = True
    FLIP_Y = False
    SWAP_XY = True

# White lanes between rounded blocks, in canvas coordinate units.  Large blocks
# use this value, while tiny clones use much smaller adaptive gaps to preserve a
# dense mosaic-like texture.
GAP = 0.62
BG_COLOR = "white"

# Big blocks in the reference have soft pill-like corners, but very small
# blocks should not become circles.  These limits keep both cases controlled.
ROUND_RATIO = 0.28
MAX_ROUND = 36
TOP_RANK_COLORS = 64

RANDOM_SEED = 123
FAILED_LOG = os.path.join(OUTPUT_DIR, "failed_files.txt")

ANALYSIS_TEXT = """Analysis: Tree Map

The tree map is another illustrative approach to show diversity. In a tree map, each rounded rectangle represents a unique entry: V-J-uCDR3, where the size of a spot denotes the relative frequency. The entire plot area is divided into sub-areas according to V-usage, which is then subdivided according to J-usage, and then each uCDR3 within a given V-J- combination is subsequently represented by a rounded rectangle (sized by frequency). The unevenness of squares reflects areas of clonal expansion within the immune repertoire sampled.
"""


# ============================================================
# Reference-style color palette
# ============================================================

REFERENCE_PALETTE = [
    "#3ec7cf",  # cyan
    "#ed12a9",  # magenta
    "#7dd5a6",  # mint
    "#0aa33a",  # green
    "#285fb8",  # blue
    "#8475ee",  # lavender
    "#f1904f",  # orange
    "#ddcc3d",  # yellow
    "#9fd30a",  # lime
    "#16c93a",  # bright green
    "#48d993",  # seafoam
    "#47bfd0",  # teal
    "#1296db",  # sky blue
    "#12208d",  # deep blue
    "#4217c8",  # violet
    "#7b13df",  # purple
    "#e553bc",  # pink
    "#f2442d",  # red orange
    "#922431",  # wine
    "#006f43",  # dark green
    "#0d6f6b",  # deep teal
    "#172936",  # blue black
    "#657fa3",  # slate blue
    "#b9b9c9",  # cool gray
    "#d9e8d8",  # pale green
    "#b5a2d6",  # soft violet
    "#b15a48",  # clay
    "#8b7b48",  # olive brown
    "#aeb78a",  # sage
    "#4aa349",  # grass
]

# Exact high-frequency colors sampled from HL_FP2__TRG.png.  This mode is
# useful when reproducing the visual style of that reference image: the largest
# clone receives the first color, the second largest receives the second color,
# and so on.
REFERENCE_RANK_PALETTE = [
    "#3ec4d1",
    "#ef0db8",
    "#80d9ab",
    "#0da12f",
    "#a3cc19",
    "#225bb7",
    "#dcc53f",
    "#75b78b",
    "#5538d8",
    "#77837b",
    "#ee9052",
    "#bbb6ce",
    "#66ce9d",
    "#837cfb",
    "#5d7da2",
    "#c29445",
    "#46a748",
    "#037045",
    "#4009c1",
    "#2f7bbd",
    "#e6201d",
    "#12c83f",
    "#e34bb2",
    "#55c3d1",
]

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


# ============================================================
# Helpers
# ============================================================


def detect_sep(file_path):
    file_path = file_path.lower()
    if file_path.endswith(".csv") or file_path.endswith(".csv.gz"):
        return ","
    return "\t"


def safe_name(name):
    return (
        str(name)
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace("*", "_")
        .replace("?", "_")
        .replace('"', "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace("|", "_")
        .replace(" ", "_")
    )


def strip_compressed_suffix(filename):
    name = os.path.basename(filename)
    for suffix in [".csv.gz", ".tsv.gz", ".txt.gz", ".csv", ".tsv", ".txt"]:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return os.path.splitext(name)[0]


def parse_sample_chain_from_filename(input_file):
    name = strip_compressed_suffix(input_file)
    parts = [part for part in name.split("_") if part]

    if len(parts) >= 2:
        sample = "_".join(parts[:-1])
        chain = parts[-1]
    else:
        sample = name
        chain = "unknown"

    return safe_name(sample), safe_name(chain)


def hex_to_rgb01(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))


def stable_int(value):
    digest = hashlib.md5(str(value).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def jitter_color(hex_color, seed):
    rnd = random.Random(seed)
    rgb = hex_to_rgb01(hex_color)
    h, s, v = colorsys.rgb_to_hsv(*rgb)

    h = (h + rnd.uniform(-0.025, 0.025)) % 1.0
    s = max(0.58, min(0.98, s + rnd.uniform(-0.07, 0.06)))
    v = max(0.38, min(0.92, v + rnd.uniform(-0.04, 0.04)))

    return colorsys.hsv_to_rgb(h, s, v)


def assign_colors(plot_df, color_mode=COLOR_MODE):
    colors = []

    if color_mode == "reference-rank":
        palette_size = len(REFERENCE_RANK_PALETTE)
        for _, row in plot_df.reset_index(drop=True).iterrows():
            rank = int(row.get("_abundance_rank", row.name))
            colors.append(hex_to_rgb01(REFERENCE_RANK_PALETTE[rank % palette_size]))
        return colors

    if color_mode == "hybrid-reference":
        rank_palette_size = len(REFERENCE_RANK_PALETTE)
        tail_palette = REFERENCE_RANK_PALETTE + REFERENCE_PALETTE
        tail_palette_size = len(tail_palette)

        for _, row in plot_df.reset_index(drop=True).iterrows():
            rank = int(row.get("_abundance_rank", row.name))
            if rank < TOP_RANK_COLORS:
                colors.append(
                    hex_to_rgb01(REFERENCE_RANK_PALETTE[rank % rank_palette_size])
                )
                continue

            key_seed = stable_int(row["_entry_id"]) + RANDOM_SEED
            palette_idx = key_seed % tail_palette_size
            colors.append(jitter_color(tail_palette[palette_idx], key_seed))

        return colors

    if color_mode == "mosaic-reference":
        palette_size = len(MOSAIC_REFERENCE_PALETTE)
        for _, row in plot_df.reset_index(drop=True).iterrows():
            key_seed = stable_int(row["_entry_id"]) + RANDOM_SEED
            palette_idx = key_seed % palette_size
            colors.append(hex_to_rgb01(MOSAIC_REFERENCE_PALETTE[palette_idx]))

        return colors

    palette_size = len(REFERENCE_PALETTE)

    for idx, row in plot_df.reset_index(drop=True).iterrows():
        key_seed = stable_int(row["_entry_id"]) + RANDOM_SEED
        palette_idx = (idx * 7 + key_seed) % palette_size
        colors.append(jitter_color(REFERENCE_PALETTE[palette_idx], key_seed))

    return colors


def sort_usage_df(df, keys, order_mode=ORDER_MODE):
    if order_mode == "input":
        return df.sort_values("_source_order", ascending=True)
    if order_mode == "name":
        return df.sort_values(keys, ascending=True)
    return df.sort_values([COUNT_COL, "_source_order"], ascending=[False, True])


# ============================================================
# Data
# ============================================================


def load_plot_df(
    input_file,
    top_n=TOP_N,
    min_count=MIN_COUNT,
    color_mode=COLOR_MODE,
    order_mode=ORDER_MODE,
):
    sep = detect_sep(input_file)

    df = pd.read_csv(
        input_file,
        sep=sep,
        usecols=[V_COL, J_COL, CDR3_COL, COUNT_COL],
        dtype={V_COL: str, J_COL: str, CDR3_COL: str},
        compression="infer",
        low_memory=False,
    )

    df[V_COL] = df[V_COL].fillna("Unknown_V").astype(str).str.strip()
    df[J_COL] = df[J_COL].fillna("Unknown_J").astype(str).str.strip()
    df[CDR3_COL] = df[CDR3_COL].astype(str).str.strip()
    df[COUNT_COL] = pd.to_numeric(df[COUNT_COL], errors="coerce").fillna(0)
    df.loc[df[V_COL] == "", V_COL] = "Unknown_V"
    df.loc[df[J_COL] == "", J_COL] = "Unknown_J"

    mask = (
        (df[CDR3_COL] != "")
        & (df[CDR3_COL].str.lower() != "nan")
        & (df[COUNT_COL] >= min_count)
    )
    plot_df = df.loc[mask, [V_COL, J_COL, CDR3_COL, COUNT_COL]].copy()
    plot_df["_source_order"] = plot_df.index

    # Official tree-map entry: V-J-uCDR3.
    plot_df = plot_df.groupby([V_COL, J_COL, CDR3_COL], as_index=False, sort=False).agg(
        {COUNT_COL: "sum", "_source_order": "min"}
    )

    abundance_order = plot_df.sort_values(
        [COUNT_COL, "_source_order"], ascending=[False, True]
    ).index
    abundance_rank = {idx: rank for rank, idx in enumerate(abundance_order)}
    plot_df["_abundance_rank"] = plot_df.index.map(abundance_rank)

    if top_n > 0:
        keep_idx = abundance_order[:top_n]
        plot_df = plot_df.loc[keep_idx].copy()

    plot_df = sort_usage_df(
        plot_df,
        keys=[V_COL, J_COL, CDR3_COL],
        order_mode=order_mode,
    ).reset_index(drop=True)

    if plot_df.empty:
        raise ValueError("过滤后无有效数据")

    plot_df["_rank"] = plot_df.index
    plot_df["_entry_id"] = (
        plot_df[V_COL].astype(str)
        + "|"
        + plot_df[J_COL].astype(str)
        + "|"
        + plot_df[CDR3_COL].astype(str)
    )
    plot_df["_hash_order"] = plot_df["_entry_id"].map(stable_int)
    plot_df["_color"] = assign_colors(plot_df, color_mode=color_mode)
    return plot_df


# ============================================================
# Compact vertical treemap layout
# ============================================================


def normalize_sizes(values, dx, dy):
    total = float(sum(values))
    if total <= 0:
        return []
    scale = (dx * dy) / total
    return [float(value) * scale for value in values]


def worst_ratio(row, side):
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


def layout_row(row_items, x, y, dx, dy, prefer_vertical=True):
    row_sum = sum(item["_area"] for item in row_items)
    rects = []

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


def squarify_items(items, x, y, dx, dy, value_key, prefer_vertical=True):
    values = [float(item[value_key]) for item in items]
    areas = normalize_sizes(values, dx, dy)

    items = [item.copy() for item in items]
    for item, area in zip(items, areas):
        item["_area"] = area

    row = []
    rects = []

    while items:
        item = items[0]
        side = min(dx, dy)

        if not row or worst_ratio(
            [r["_area"] for r in row] + [item["_area"]], side
        ) <= worst_ratio([r["_area"] for r in row], side):
            row.append(items.pop(0))
            continue

        laid_out, x, y, dx, dy = layout_row(
            row, x, y, dx, dy, prefer_vertical=prefer_vertical
        )
        rects.extend(laid_out)
        row = []

    if row:
        laid_out, x, y, dx, dy = layout_row(
            row, x, y, dx, dy, prefer_vertical=prefer_vertical
        )
        rects.extend(laid_out)

    return rects


def make_hierarchical_vj_ucdr3_rects(plot_df, order_mode=ORDER_MODE):
    """
    Official hierarchy:
        full canvas -> V usage -> J usage -> unique V-J-uCDR3 entries.

    Only terminal uCDR3 rectangles are returned for drawing. The nested V/J
    layout controls where each uCDR3 appears and how much area each parent
    group receives.
    """
    v_df = plot_df.groupby(V_COL, as_index=False, sort=False).agg(
        {COUNT_COL: "sum", "_source_order": "min"}
    )
    v_df = sort_usage_df(v_df, keys=[V_COL], order_mode=order_mode).reset_index(
        drop=True
    )
    v_rects = squarify_items(
        v_df.to_dict("records"), 0.0, 0.0, CANVAS_W, CANVAS_H, COUNT_COL
    )

    leaf_rects = []

    for v_rect in v_rects:
        v_value = v_rect[V_COL]
        v_sub = plot_df[plot_df[V_COL] == v_value].copy()
        if v_sub.empty:
            continue

        j_df = v_sub.groupby(J_COL, as_index=False, sort=False).agg(
            {COUNT_COL: "sum", "_source_order": "min"}
        )
        j_df = sort_usage_df(j_df, keys=[J_COL], order_mode=order_mode).reset_index(
            drop=True
        )
        j_rects = squarify_items(
            j_df.to_dict("records"),
            v_rect["x"],
            v_rect["y"],
            v_rect["dx"],
            v_rect["dy"],
            COUNT_COL,
        )

        for j_rect in j_rects:
            j_value = j_rect[J_COL]
            clone_df = v_sub[v_sub[J_COL] == j_value].copy()
            if clone_df.empty:
                continue
            if CLONE_ORDER_MODE == "hash":
                clone_df["_clone_order_group"] = (
                    clone_df["_abundance_rank"] >= TOP_RANK_COLORS
                ).astype(int)
                clone_df["_clone_rank_order"] = clone_df["_abundance_rank"].where(
                    clone_df["_clone_order_group"] == 0, 0
                )
                clone_df["_clone_hash_order"] = clone_df["_hash_order"].where(
                    clone_df["_clone_order_group"] == 1, 0
                )
                clone_df = clone_df.sort_values(
                    ["_clone_order_group", "_clone_rank_order", "_clone_hash_order"],
                    ascending=[True, True, True],
                ).reset_index(drop=True)
            elif CLONE_ORDER_MODE == "copy":
                clone_df = clone_df.sort_values(
                    [COUNT_COL, "_source_order"], ascending=[False, True]
                ).reset_index(drop=True)

            clone_rects = squarify_items(
                clone_df.to_dict("records"),
                j_rect["x"],
                j_rect["y"],
                j_rect["dx"],
                j_rect["dy"],
                COUNT_COL,
            )
            leaf_rects.extend(clone_rects)

    return leaf_rects


# ============================================================
# Drawing
# ============================================================


def block_style(dx, dy):
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


def add_round_rect(ax, x, y, dx, dy, color):
    gap, rounding = block_style(dx, dy)

    left_gap = 0 if x <= 0 else gap / 2
    top_gap = 0 if y <= 0 else gap / 2
    right_gap = 0 if x + dx >= CANVAS_W - 1e-6 else gap / 2
    bottom_gap = 0 if y + dy >= CANVAS_H - 1e-6 else gap / 2

    x += left_gap
    y += top_gap
    dx = max(dx - left_gap - right_gap, 0.01)
    dy = max(dy - top_gap - bottom_gap, 0.01)

    if dx <= 0 or dy <= 0:
        return

    rounding = min(rounding, min(dx, dy) / 2)

    patch = FancyBboxPatch(
        (x, y),
        dx,
        dy,
        boxstyle=f"round,pad=0,rounding_size={rounding}",
        linewidth=0,
        edgecolor=None,
        facecolor=color,
        antialiased=True,
    )
    ax.add_patch(patch)


def transform_rects(rects, flip_x=False, flip_y=False, swap_xy=False):
    transformed = []
    transform_w = CANVAS_H if swap_xy else CANVAS_W
    transform_h = CANVAS_W if swap_xy else CANVAS_H
    scale_x = CANVAS_W / transform_w
    scale_y = CANVAS_H / transform_h

    for rect in rects:
        item = rect.copy()
        x = item["x"]
        y = item["y"]
        dx = item["dx"]
        dy = item["dy"]

        if swap_xy:
            x, y, dx, dy = y, x, dy, dx
        if flip_x:
            x = transform_w - x - dx
        if flip_y:
            y = transform_h - y - dy

        if swap_xy and (scale_x != 1.0 or scale_y != 1.0):
            x *= scale_x
            dx *= scale_x
            y *= scale_y
            dy *= scale_y

        item.update({"x": x, "y": y, "dx": dx, "dy": dy})
        transformed.append(item)

    return transformed


def draw_vertical_treemap(
    plot_df,
    output_file,
    order_mode=ORDER_MODE,
    flip_x=FLIP_X,
    flip_y=FLIP_Y,
    swap_xy=SWAP_XY,
):
    rects = make_hierarchical_vj_ucdr3_rects(plot_df, order_mode=order_mode)
    rects = transform_rects(rects, flip_x=flip_x, flip_y=flip_y, swap_xy=swap_xy)

    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI, frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    for rect in rects:
        add_round_rect(
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

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    fig.savefig(output_file, dpi=DPI, facecolor=BG_COLOR, pad_inches=0)
    plt.close(fig)


# ============================================================
# Batch
# ============================================================


def iter_input_files(input_dir):
    files = []
    for filename in os.listdir(input_dir):
        file_path = os.path.join(input_dir, filename)
        if os.path.isfile(file_path) and filename.lower().endswith(FILE_SUFFIX):
            files.append(file_path)
    return sorted(files)


def output_path_for(input_file, output_dir):
    sample_name, _ = parse_sample_chain_from_filename(input_file)
    sample_output_dir = os.path.join(output_dir, sample_name)
    output_name = f"{strip_compressed_suffix(input_file)}.png"
    return os.path.join(sample_output_dir, output_name)


def top20_clone_path_for(input_file, output_dir):
    sample_name, _ = parse_sample_chain_from_filename(input_file)
    sample_output_dir = os.path.join(output_dir, sample_name)
    output_name = f"{strip_compressed_suffix(input_file)}.csv"
    return os.path.join(sample_output_dir, output_name)


def write_top20_clone_csv(plot_df, input_file, output_dir):
    top20_file = top20_clone_path_for(input_file, output_dir)
    os.makedirs(os.path.dirname(top20_file), exist_ok=True)

    top20_df = (
        plot_df.sort_values([COUNT_COL, "_source_order"], ascending=[False, True])
        .head(20)
        .loc[:, [CDR3_COL, V_COL, J_COL, COUNT_COL]]
        .copy()
    )
    top20_df.to_csv(top20_file, index=False, encoding="utf-8-sig")
    return top20_file


def write_analysis_text(output_dir):
    analysis_file = os.path.join(output_dir, "analysis_tree_map.txt")
    with open(analysis_file, "w", encoding="utf-8") as f:
        f.write(ANALYSIS_TEXT)
        f.write("\n")
    return analysis_file


def process_one_file(
    input_file,
    output_dir=OUTPUT_DIR,
    skip_existing=SKIP_EXISTING,
    top_n=TOP_N,
    min_count=MIN_COUNT,
    color_mode=COLOR_MODE,
    order_mode=ORDER_MODE,
    flip_x=FLIP_X,
    flip_y=FLIP_Y,
    swap_xy=SWAP_XY,
):
    output_file = output_path_for(input_file, output_dir)

    if (
        skip_existing
        and os.path.exists(output_file)
        and os.path.getsize(output_file) > 0
    ):
        return {
            "status": "skip",
            "input": input_file,
            "output": output_file,
            "top20": top20_clone_path_for(input_file, output_dir),
            "rows": 0,
            "total": 0,
            "error": None,
        }

    plot_df = load_plot_df(
        input_file,
        top_n=top_n,
        min_count=min_count,
        color_mode=color_mode,
        order_mode=order_mode,
    )
    top20_file = write_top20_clone_csv(plot_df, input_file, output_dir)
    draw_vertical_treemap(
        plot_df,
        output_file,
        order_mode=order_mode,
        flip_x=flip_x,
        flip_y=flip_y,
        swap_xy=swap_xy,
    )

    return {
        "status": "done",
        "input": input_file,
        "output": output_file,
        "top20": top20_file,
        "rows": len(plot_df),
        "total": plot_df[COUNT_COL].sum(),
        "error": None,
    }


def main():
    input_dir = INPUT_DIR
    output_dir = OUTPUT_DIR
    skip_existing = SKIP_EXISTING

    os.makedirs(output_dir, exist_ok=True)
    analysis_file = write_analysis_text(output_dir)
    failed_log = os.path.join(output_dir, "failed_files.txt")

    files = iter_input_files(input_dir)

    if not files:
        print(f"未找到输入文件: {input_dir}")
        return

    active_workers = min(max(int(N_WORKERS), 1), len(files))

    print("=" * 80)
    print("V-J-uCDR3 hierarchical treemap plotting")
    print("=" * 80)
    print(f"Input dir: {input_dir}")
    print(f"Output dir: {output_dir}")
    print(f"Analysis text: {analysis_file}")
    print(f"Found files: {len(files)}")
    print(f"N workers: {N_WORKERS}")
    print(f"Active workers: {active_workers}")
    print("Layout: official V -> J -> V-J-uCDR3")
    print(
        f"Canvas: {CANVAS_SHAPE} "
        f"({int(CANVAS_W)}x{int(CANVAS_H)}, fig={FIG_W}x{FIG_H}, dpi={DPI})"
    )
    print(f"Top N: {TOP_N}")
    print(f"Min count: {MIN_COUNT}")
    print(f"Color mode: {COLOR_MODE}")
    print(f"Order mode: {ORDER_MODE}")
    print(f"Transform: flip_x={FLIP_X}, flip_y={FLIP_Y}, swap_xy={SWAP_XY}")
    print("=" * 80)

    done_n = 0
    skip_n = 0
    error_n = 0
    failed_records = []

    with open(failed_log, "w", encoding="utf-8") as f:
        f.write("Failed files\n")
        f.write("filename\treason\n")

    if active_workers <= 1:
        for i, file_path in enumerate(files, 1):
            try:
                result = process_one_file(
                    file_path,
                    output_dir,
                    skip_existing,
                    TOP_N,
                    MIN_COUNT,
                    COLOR_MODE,
                    ORDER_MODE,
                    FLIP_X,
                    FLIP_Y,
                    SWAP_XY,
                )
                if result["status"] == "skip":
                    skip_n += 1
                    print(f"[Skip] ({i}/{len(files)}) {result['output']}")
                else:
                    done_n += 1
                    print(
                        f"[Done] ({i}/{len(files)}) "
                        f"{result['input']} -> {result['output']}"
                    )
            except Exception as e:
                error_n += 1
                error_text = str(e)
                failed_records.append({"file": file_path, "error": error_text})
                print(f"[Error] ({i}/{len(files)}) {os.path.basename(file_path)}: {error_text}")
    else:
        with ProcessPoolExecutor(max_workers=active_workers) as executor:
            future_to_file = {
                executor.submit(
                    process_one_file,
                    file_path,
                    output_dir,
                    skip_existing,
                    TOP_N,
                    MIN_COUNT,
                    COLOR_MODE,
                    ORDER_MODE,
                    FLIP_X,
                    FLIP_Y,
                    SWAP_XY,
                ): file_path
                for file_path in files
            }

            for i, future in enumerate(as_completed(future_to_file), 1):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    if result["status"] == "skip":
                        skip_n += 1
                        print(f"[Skip] ({i}/{len(files)}) {result['output']}")
                    else:
                        done_n += 1
                        print(
                            f"[Done] ({i}/{len(files)}) "
                            f"{result['input']} -> {result['output']}"
                        )
                except Exception as e:
                    error_n += 1
                    error_text = str(e)
                    failed_records.append({"file": file_path, "error": error_text})
                    print(f"[Error] ({i}/{len(files)}) {os.path.basename(file_path)}: {error_text}")

    if failed_records:
        with open(failed_log, "a", encoding="utf-8") as f:
            for idx, rec in enumerate(failed_records, 1):
                f.write(
                    f"{idx}. {os.path.basename(rec['file'])}\t{rec['error']}\n"
                )

    print("=" * 80)
    print("All done.")
    print(f"Done: {done_n}")
    print(f"Skipped: {skip_n}")
    print(f"Errors: {error_n}")
    print(f"Failed log: {failed_log}")
    print("=" * 80)


if __name__ == "__main__":
    freeze_support()
    main()
