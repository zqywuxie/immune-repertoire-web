from __future__ import annotations

import argparse
import math
import random
import re
import sys
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask_app.services.treemap_renderer import detect_columns, detect_dialect, open_text_file, read_repertoire
import csv


TCR_ORDER = ["TRA", "TRB", "TRD", "TRG"]
BCR_ORDER = ["IGH", "IGK", "IGL"]
ALL_CHAINS = TCR_ORDER + BCR_ORDER
FILENAME_RE = re.compile(r"^(?P<sample>.+?)__(?P<chain>IGH|IGK|IGL|TRA|TRB|TRD|TRG)\.csv\.gz$", re.IGNORECASE)
PALETTE = [
    "#f48cc8", "#d64f9d", "#62e51f", "#18b20f", "#fff04d", "#ffd23a", "#49e1db",
    "#30b2dd", "#4d8df3", "#2449d8", "#ff6f61", "#ff9550", "#a82cff", "#6b0dde",
    "#41b39e", "#2c8d73", "#ffb58f", "#c0d4ff", "#d5ff7d", "#7bd8ff", "#f5a6e6",
    "#a45b19", "#6a3d9a", "#245e2b", "#8f8f8f",
]


@dataclass
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def w(self) -> int:
        return max(0, self.x1 - self.x0)

    @property
    def h(self) -> int:
        return max(0, self.y1 - self.y0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a 7-chain montage PNG from repertoire CSV.GZ files.")
    parser.add_argument("input_dir", help="Directory containing files like SAMPLE__IGH.csv.gz ... SAMPLE__TRG.csv.gz")
    parser.add_argument("-o", "--output-dir", default="result", help="Output directory for montage PNGs")
    parser.add_argument("--width", type=int, default=1000, help="Output image width")
    parser.add_argument("--height", type=int, default=1000, help="Output image height")
    parser.add_argument("--panel-gap", type=int, default=4, help="Gap between chain panels")
    parser.add_argument("--outer-gap", type=int, default=0, help="Outer canvas padding")
    parser.add_argument("--min-copy", type=float, default=1.0, help="Minimum copy threshold")
    parser.add_argument("--save-panels", action="store_true", help="Also save individual chain panel PNGs")
    return parser.parse_args()


def discover_samples(input_dir: Path) -> dict[str, dict[str, Path]]:
    samples: dict[str, dict[str, Path]] = {}
    for path in sorted(input_dir.glob("*.csv.gz")):
        match = FILENAME_RE.match(path.name)
        if not match:
            continue
        sample = match.group("sample")
        chain = match.group("chain").upper()
        samples.setdefault(sample, {})[chain] = path
    return samples


def detect_columns_for_file(path: Path) -> dict[str, str | None]:
    with open_text_file(path) as handle:
        sample = handle.read(4096)
        handle.seek(0)
        reader = csv.DictReader(handle, dialect=detect_dialect(sample))
        fieldnames = reader.fieldnames or []
    if not fieldnames:
        raise ValueError(f"No header found in {path}")
    overrides = {"cdr3": None, "copy": None, "v": None, "j": None, "c": None, "chain": None, "cell_type": None}
    return detect_columns(fieldnames, overrides)


def load_chain_clones(path: Path, min_copy: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    columns = detect_columns_for_file(path)
    clones, summary = read_repertoire(path, columns)
    filtered = [clone for clone in clones if float(clone["copy"]) >= min_copy]
    return filtered, summary


def normalize_sizes(weights: list[float], span: int, min_size: int) -> list[int]:
    if not weights:
        return []
    total = sum(weights)
    if total <= 0:
        return [span // len(weights)] * len(weights)
    raw = [span * (weight / total) for weight in weights]
    sizes = [max(min_size, int(value)) for value in raw]
    diff = span - sum(sizes)
    order = sorted(range(len(weights)), key=lambda i: raw[i] - math.floor(raw[i]), reverse=(diff > 0))
    idx = 0
    while diff != 0 and order:
        target = order[idx % len(order)]
        if diff > 0:
            sizes[target] += 1
            diff -= 1
        elif sizes[target] > min_size:
            sizes[target] -= 1
            diff += 1
        idx += 1
        if idx > 10000:
            break
    if sum(sizes) != span:
        sizes[-1] += span - sum(sizes)
    return sizes


def split_rect_h(rect: Rect, sizes: list[int], gap: int) -> list[Rect]:
    result: list[Rect] = []
    x = rect.x0
    for i, size in enumerate(sizes):
        x1 = x + size
        result.append(Rect(x, rect.y0, x1, rect.y1))
        x = x1 + (gap if i < len(sizes) - 1 else 0)
    if result:
        result[-1] = Rect(result[-1].x0, result[-1].y0, rect.x1, result[-1].y1)
    return result


def treemap_binary(items: list[dict[str, Any]], rect: Rect) -> list[tuple[Rect, dict[str, Any]]]:
    if not items or rect.w <= 0 or rect.h <= 0:
        return []
    if len(items) == 1:
        return [(rect, items[0])]

    total = sum(max(0.0, float(item["copy"])) for item in items)
    if total <= 0:
        return []

    half = total / 2
    running = 0.0
    split_idx = 1
    best_delta = float("inf")
    for idx in range(1, len(items)):
        running += max(0.0, float(items[idx - 1]["copy"]))
        delta = abs(half - running)
        if delta <= best_delta:
            best_delta = delta
            split_idx = idx
        else:
            break

    left_items = items[:split_idx]
    right_items = items[split_idx:]
    left_total = sum(float(item["copy"]) for item in left_items)

    if rect.w >= rect.h:
        cut = rect.x0 + int(round(rect.w * (left_total / total)))
        cut = max(rect.x0 + 1, min(rect.x1 - 1, cut))
        left_rect = Rect(rect.x0, rect.y0, cut, rect.y1)
        right_rect = Rect(cut, rect.y0, rect.x1, rect.y1)
    else:
        cut = rect.y0 + int(round(rect.h * (left_total / total)))
        cut = max(rect.y0 + 1, min(rect.y1 - 1, cut))
        left_rect = Rect(rect.x0, rect.y0, rect.x1, cut)
        right_rect = Rect(rect.x0, cut, rect.x1, rect.y1)

    return treemap_binary(left_items, left_rect) + treemap_binary(right_items, right_rect)


def color_for_clone(chain: str, clone: dict[str, Any]) -> tuple[int, int, int]:
    key = f"{chain}|{clone.get('v','')}|{clone.get('j','')}|{clone.get('cdr3','')}"
    seed = int.from_bytes(hashlib.md5(key.encode("utf-8")).digest()[:8], "big")
    base = PALETTE[seed % len(PALETTE)]
    r = int(base[1:3], 16)
    g = int(base[3:5], 16)
    b = int(base[5:7], 16)
    jitter = random.Random(seed)
    r = max(0, min(255, r + jitter.randint(-14, 14)))
    g = max(0, min(255, g + jitter.randint(-14, 14)))
    b = max(0, min(255, b + jitter.randint(-14, 14)))
    return r, g, b


def draw_clone_panel(draw: ImageDraw.ImageDraw, rect: Rect, chain: str, clones: list[dict[str, Any]]) -> None:
    draw.rectangle([rect.x0, rect.y0, rect.x1 - 1, rect.y1 - 1], fill="white")
    if not clones:
        return

    placements = treemap_binary(clones, rect)
    for clone_rect, clone in placements:
        if clone_rect.w <= 0 or clone_rect.h <= 0:
            continue
        fill = color_for_clone(chain, clone)
        radius = max(0, min(18, min(clone_rect.w, clone_rect.h) // 5))
        box = [clone_rect.x0, clone_rect.y0, clone_rect.x1 - 1, clone_rect.y1 - 1]
        if clone_rect.w <= 2 or clone_rect.h <= 2 or radius <= 1:
            draw.rectangle(box, fill=fill)
        else:
            draw.rounded_rectangle(box, radius=radius, fill=fill)


def build_chain_panels(sample_files: dict[str, Path], min_copy: float) -> dict[str, tuple[list[dict[str, Any]], dict[str, Any]]]:
    panels: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    for chain in ALL_CHAINS:
        path = sample_files.get(chain)
        if not path:
            panels[chain] = ([], {"total_copy": 0.0, "total_clones": 0})
            continue
        clones, summary = load_chain_clones(path, min_copy)
        panels[chain] = (clones, summary)
    return panels


def compose_sample(sample: str, panels: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]], width: int, height: int, panel_gap: int, outer_gap: int, save_panels: bool, output_dir: Path) -> Path:
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)

    tcr_weights = [float(panels[chain][1].get("total_copy", 0.0)) or 1.0 for chain in TCR_ORDER]
    bcr_weights = [float(panels[chain][1].get("total_copy", 0.0)) or 1.0 for chain in BCR_ORDER]
    top_total = sum(tcr_weights)
    bottom_total = sum(bcr_weights)
    total = max(1.0, top_total + bottom_total)

    inner = Rect(outer_gap, outer_gap, width - outer_gap, height - outer_gap)
    row_gap = panel_gap
    usable_h = inner.h - row_gap
    top_h = int(round(usable_h * (top_total / total)))
    top_h = max(int(height * 0.22), min(int(height * 0.55), top_h))
    bottom_h = usable_h - top_h

    top_rect = Rect(inner.x0, inner.y0, inner.x1, inner.y0 + top_h)
    bottom_rect = Rect(inner.x0, top_rect.y1 + row_gap, inner.x1, inner.y1)

    top_sizes = normalize_sizes(tcr_weights, top_rect.w - panel_gap * (len(TCR_ORDER) - 1), min_size=36)
    bottom_sizes = normalize_sizes(bcr_weights, bottom_rect.w - panel_gap * (len(BCR_ORDER) - 1), min_size=48)
    top_panels = split_rect_h(top_rect, top_sizes, panel_gap)
    bottom_panels = split_rect_h(bottom_rect, bottom_sizes, panel_gap)

    for chain, rect in zip(TCR_ORDER, top_panels):
        draw_clone_panel(draw, rect, chain, panels[chain][0])
        draw.rectangle([rect.x0, rect.y0, rect.x1 - 1, rect.y1 - 1], outline="black", width=2)
        if save_panels:
            panel_img = canvas.crop((rect.x0, rect.y0, rect.x1, rect.y1))
            panel_img.save(output_dir / f"{sample}__{chain}.png")

    for chain, rect in zip(BCR_ORDER, bottom_panels):
        draw_clone_panel(draw, rect, chain, panels[chain][0])
        draw.rectangle([rect.x0, rect.y0, rect.x1 - 1, rect.y1 - 1], outline="black", width=2)
        if save_panels:
            panel_img = canvas.crop((rect.x0, rect.y0, rect.x1, rect.y1))
            panel_img.save(output_dir / f"{sample}__{chain}.png")

    output_path = output_dir / f"{sample}.png"
    canvas.save(output_path)
    return output_path


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}", file=sys.stderr)
        return 1

    samples = discover_samples(input_dir)
    if not samples:
        print(f"No chain files found in {input_dir}", file=sys.stderr)
        return 1

    for sample, sample_files in sorted(samples.items()):
        panels = build_chain_panels(sample_files, args.min_copy)
        output_path = compose_sample(
            sample=sample,
            panels=panels,
            width=args.width,
            height=args.height,
            panel_gap=args.panel_gap,
            outer_gap=args.outer_gap,
            save_panels=args.save_panels,
            output_dir=output_dir,
        )
        print(f"Montage generated: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
