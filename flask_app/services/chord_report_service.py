"""
Chord diagram report service.

Generates V/J frequency tables and chord-style diagrams under:
<results_root>/chord_report/<job_id>/
  metadata.json
  viewer.html
  samples/<sample>/<sample>__<chain>.vj_freq.csv
  samples/<sample>/<sample>__<chain>.png
  samples/<sample>/<sample>__<chain>.pdf
"""

from __future__ import annotations

import csv
import html
import io
import json
import logging
import math
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Wedge

from flask_app.exceptions import ValidationError
from flask_app.services.result_path_resolver import candidate_job_roots
from flask_app.services.auto_heatmap_service import get_auto_heatmap_service
from flask_app.services.treemap_renderer import detect_dialect, open_text_file

logger = logging.getLogger(__name__)

CHORD_CHAIN_ORDER = ["TRA", "TRB", "TRD", "TRG", "IGH", "IGK", "IGL"]


@dataclass
class ChordReportResult:
    job_id: str
    output_base: Path
    metadata_path: Path
    metadata: Dict[str, Any]


class ChordReportService:
    _RESULT_DIR = "chord_report"
    _METADATA_FILE_NAME = "metadata.json"
    _VIEWER_FILE_NAME = "viewer.html"

    def __init__(self, results_root: Path):
        self.results_root = Path(results_root).resolve()
        self.results_root.mkdir(parents=True, exist_ok=True)
        self.auto_heatmap_service = get_auto_heatmap_service()

    @staticmethod
    def _sanitize_job_id(raw_name: Optional[str]) -> str:
        if raw_name:
            candidate = re.sub(r"[^A-Za-z0-9_-]+", "_", str(raw_name).strip())
            candidate = candidate.strip("_")
            if candidate:
                return candidate
        return f"chord_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def _allocate_job_id(self, requested_name: Optional[str]) -> str:
        base_id = self._sanitize_job_id(requested_name)
        run_root = self.results_root / self._RESULT_DIR
        run_root.mkdir(parents=True, exist_ok=True)

        candidate = base_id
        suffix = 1
        while (run_root / candidate).exists():
            candidate = f"{base_id}_{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def _sanitize_file_stem(raw_name: str) -> str:
        candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(raw_name).strip())
        candidate = re.sub(r"\s+", "_", candidate)
        candidate = candidate.strip("._")
        return candidate or "sample"

    @staticmethod
    def _normalize_chain(chain: Any) -> Optional[str]:
        if chain is None:
            return None
        normalized = str(chain).strip().upper()
        return normalized if normalized in CHORD_CHAIN_ORDER else None

    def _extract_sample_chain_files(
        self,
        sample: Dict[str, Any],
        selected_chains: List[str],
    ) -> Dict[str, str]:
        selected = set(selected_chains)
        chain_files: Dict[str, str] = {}
        for file_info in sample.get("data_files", []):
            filename = str(file_info.get("filename", ""))
            filepath = str(file_info.get("filepath", ""))
            chain = self.auto_heatmap_service._extract_chain_from_filename(filename)
            chain = self._normalize_chain(chain)
            if chain and filepath and chain in selected and chain not in chain_files:
                chain_files[chain] = filepath
        return chain_files

    @staticmethod
    def _history_entry(
        progress: float,
        stage: str,
        detail: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "progress": round(progress, 2),
            "stage": stage,
            "detail": detail,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "meta": meta or {},
        }

    @staticmethod
    def _format_count(count: float, count_mode: str) -> str:
        if count_mode == "rows":
            return str(int(round(count)))
        if float(count).is_integer():
            return str(int(count))
        return f"{count:.6f}"

    @staticmethod
    def _parse_weight(value: Any) -> Optional[float]:
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _build_vj_table_from_file(
        self,
        path: Path,
        *,
        v_column: str,
        j_column: str,
        copy_column: Optional[str],
        count_mode: str,
    ) -> Tuple[List[Dict[str, Any]], float]:
        counts: Dict[Tuple[str, str], float] = {}
        total = 0.0

        with open_text_file(path) as handle:
            sample = handle.read(4096)
            handle.seek(0)
            reader = csv.DictReader(handle, dialect=detect_dialect(sample))
            fieldnames = reader.fieldnames or []

            missing_columns = [name for name in (v_column, j_column) if name not in fieldnames]
            if missing_columns:
                raise ValidationError(
                    message=f"文件 {path.name} 缺少必需列: {', '.join(missing_columns)}"
                )
            if count_mode == "copy" and copy_column and copy_column not in fieldnames:
                raise ValidationError(message=f"文件 {path.name} 缺少 copy 列: {copy_column}")

            for row in reader:
                v_gene = str(row.get(v_column) or "").strip()
                j_gene = str(row.get(j_column) or "").strip()
                if not v_gene or not j_gene:
                    continue

                if count_mode == "copy":
                    weight = self._parse_weight(row.get(copy_column)) if copy_column else None
                    if weight is None:
                        continue
                else:
                    weight = 1.0

                if weight <= 0:
                    continue

                key = (v_gene, j_gene)
                counts[key] = counts.get(key, 0.0) + weight
                total += weight

        if total <= 0:
            raise ValidationError(message=f"文件 {path.name} 中没有可用于绘图的有效 V/J 数据。")

        rows: List[Dict[str, Any]] = []
        for (v_gene, j_gene), count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            freq_value = count / total if total else 0.0
            rows.append(
                {
                    "V": v_gene,
                    "J": j_gene,
                    "freq": f"{freq_value:.10f}",
                    "count": self._format_count(count, count_mode),
                    "_freq_value": freq_value,
                    "_count_value": count,
                }
            )
        return rows, total

    @staticmethod
    def _write_table(rows: List[Dict[str, Any]], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["V", "J", "freq", "count"])
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "V": row["V"],
                        "J": row["J"],
                        "freq": row["freq"],
                        "count": row["count"],
                    }
                )

    @staticmethod
    def _sample_arc(radius: float, start_deg: float, end_deg: float, steps: int = 8) -> List[Tuple[float, float]]:
        if steps < 2:
            steps = 2
        points: List[Tuple[float, float]] = []
        for idx in range(steps):
            angle_deg = start_deg + (end_deg - start_deg) * (idx / (steps - 1))
            angle_rad = math.radians(angle_deg)
            points.append((radius * math.cos(angle_rad), radius * math.sin(angle_rad)))
        return points

    @staticmethod
    def _polar_point(radius: float, angle_deg: float) -> Tuple[float, float]:
        angle_rad = math.radians(angle_deg)
        return radius * math.cos(angle_rad), radius * math.sin(angle_rad)

    @staticmethod
    def _build_sector_layout(
        items: List[Tuple[str, float]],
        start_deg: float,
        end_deg: float,
        gap_deg: float,
    ) -> Dict[str, Dict[str, float]]:
        if not items:
            return {}

        total_value = sum(max(value, 0.0) for _, value in items) or 1.0
        usable_span = max((end_deg - start_deg) - gap_deg * max(len(items) - 1, 0), 1.0)
        cursor = start_deg
        layout: Dict[str, Dict[str, float]] = {}
        for index, (name, value) in enumerate(items):
            span = usable_span * (max(value, 0.0) / total_value)
            if index == len(items) - 1:
                sector_end = end_deg
            else:
                sector_end = cursor + span
            layout[name] = {
                "start": cursor,
                "end": sector_end,
                "value": value,
            }
            cursor = sector_end + gap_deg
        return layout

    @staticmethod
    def _build_link_slots(
        ordered_pairs: List[Dict[str, Any]],
        layout: Dict[str, Dict[str, float]],
        item_key: str,
        partner_key: str,
    ) -> Dict[Tuple[str, str], Tuple[float, float]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in ordered_pairs:
            grouped.setdefault(str(row[item_key]), []).append(row)

        slots: Dict[Tuple[str, str], Tuple[float, float]] = {}
        for name, rows in grouped.items():
            sector = layout.get(name)
            if not sector:
                continue
            total_value = sum(float(row["_count_value"]) for row in rows) or 1.0
            cursor = sector["start"]
            sector_span = sector["end"] - sector["start"]
            for index, row in enumerate(rows):
                value = float(row["_count_value"])
                span = sector_span * (value / total_value)
                if index == len(rows) - 1:
                    slot_end = sector["end"]
                else:
                    slot_end = cursor + span
                slots[(str(row[item_key]), str(row[partner_key]))] = (cursor, slot_end)
                cursor = slot_end
        return slots

    @staticmethod
    def _label_rotation(angle_deg: float) -> Tuple[float, str]:
        if 90 < angle_deg < 270:
            return angle_deg + 180, "right"
        return angle_deg, "left"

    def _load_vj_table(self, csv_path: Path) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                v_gene = str(row.get("V") or "").strip()
                j_gene = str(row.get("J") or "").strip()
                freq_text = str(row.get("freq") or "").strip()
                count_text = str(row.get("count") or "").strip()
                if not v_gene or not j_gene or not freq_text:
                    continue
                try:
                    freq_value = float(freq_text)
                except ValueError:
                    continue
                count_value = self._parse_weight(count_text)
                if count_value is None or count_value <= 0:
                    continue
                rows.append(
                    {
                        "V": v_gene,
                        "J": j_gene,
                        "freq": f"{freq_value:.10f}",
                        "count": count_text,
                        "_freq_value": freq_value,
                        "_count_value": count_value,
                    }
                )
        if not rows:
            raise ValidationError(message=f"频率表 {csv_path.name} 中没有可用于绘图的有效记录。")
        return rows

    @staticmethod
    def _viewer_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "V": str(row["V"]),
                "J": str(row["J"]),
                "freq": str(row["freq"]),
                "count": str(row["count"]),
            }
            for row in rows
        ]

    def _draw_chord_diagram(
        self,
        rows: List[Dict[str, Any]],
        *,
        title: str,
        count_mode: str,
        pdf_path: Path,
    ) -> None:
        if not rows:
            raise ValidationError(message="没有可用于生成 chord 图的数据。")

        ordered_rows = sorted(
            rows,
            key=lambda item: (
                -float(item["_count_value"]),
                str(item["V"]),
                str(item["J"]),
            ),
        )
        v_totals: Dict[str, float] = {}
        j_totals: Dict[str, float] = {}
        for row in ordered_rows:
            count_value = float(row["_count_value"])
            v_totals[str(row["V"])] = v_totals.get(str(row["V"]), 0.0) + count_value
            j_totals[str(row["J"])] = j_totals.get(str(row["J"]), 0.0) + count_value

        v_items = sorted(v_totals.items(), key=lambda item: (-item[1], item[0]))
        j_items = sorted(j_totals.items(), key=lambda item: (-item[1], item[0]))

        v_layout = self._build_sector_layout(v_items, 110.0, 250.0, 2.0)
        j_layout = self._build_sector_layout(j_items, -70.0, 70.0, 2.0)
        v_slots = self._build_link_slots(ordered_rows, v_layout, "V", "J")
        j_slots = self._build_link_slots(ordered_rows, j_layout, "J", "V")

        v_cmap = plt.get_cmap("tab20")
        j_cmap = plt.get_cmap("Set3")
        v_colors = {
            name: v_cmap(index % max(v_cmap.N, 1))
            for index, (name, _) in enumerate(v_items)
        }
        j_colors = {
            name: j_cmap(index % max(j_cmap.N, 1))
            for index, (name, _) in enumerate(j_items)
        }

        fig, ax = plt.subplots(figsize=(10.8, 10.8), facecolor="white")
        ax.set_aspect("equal")
        ax.axis("off")

        outer_radius = 1.0
        inner_radius = 0.83
        control_radius = 0.14

        for name, sector in v_layout.items():
            ax.add_patch(
                Wedge(
                    (0, 0),
                    outer_radius,
                    sector["start"],
                    sector["end"],
                    width=outer_radius - inner_radius,
                    facecolor=v_colors[name],
                    edgecolor="white",
                    linewidth=1.0,
                )
            )
        for name, sector in j_layout.items():
            ax.add_patch(
                Wedge(
                    (0, 0),
                    outer_radius,
                    sector["start"],
                    sector["end"],
                    width=outer_radius - inner_radius,
                    facecolor=j_colors[name],
                    edgecolor="white",
                    linewidth=1.0,
                )
            )

        max_pair = max(float(row["_count_value"]) for row in ordered_rows) or 1.0
        for row in ordered_rows:
            v_name = str(row["V"])
            j_name = str(row["J"])
            v_slot = v_slots.get((v_name, j_name))
            j_slot = j_slots.get((j_name, v_name))
            if not v_slot or not j_slot:
                continue

            s_start, s_end = v_slot
            d_start, d_end = j_slot
            source_arc = self._sample_arc(inner_radius, s_start, s_end, steps=8)
            dest_arc = self._sample_arc(inner_radius, d_start, d_end, steps=8)
            c1 = self._polar_point(control_radius, s_end)
            c2 = self._polar_point(control_radius, d_start)
            c3 = self._polar_point(control_radius, d_end)
            c4 = self._polar_point(control_radius, s_start)

            vertices: List[Tuple[float, float]] = [source_arc[0]]
            codes: List[int] = [MplPath.MOVETO]
            for point in source_arc[1:]:
                vertices.append(point)
                codes.append(MplPath.LINETO)

            vertices.extend([c1, c2, dest_arc[0]])
            codes.extend([MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4])

            for point in dest_arc[1:]:
                vertices.append(point)
                codes.append(MplPath.LINETO)

            vertices.extend([c3, c4, source_arc[0]])
            codes.extend([MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4])

            color = to_rgba(v_colors.get(v_name, "#4f46e5"), alpha=0.56)
            patch = PathPatch(
                MplPath(vertices, codes),
                facecolor=color,
                edgecolor=(1, 1, 1, 0.18),
                linewidth=0.45 + 0.8 * (float(row["_count_value"]) / max_pair),
            )
            ax.add_patch(patch)

        for name, sector in v_layout.items():
            angle = (sector["start"] + sector["end"]) / 2
            x, y = self._polar_point(1.12, angle)
            rotation, ha = self._label_rotation(angle)
            ax.text(
                x,
                y,
                name,
                ha=ha,
                va="center",
                rotation=rotation,
                rotation_mode="anchor",
                fontsize=9,
                color="#1f2937",
                fontweight="semibold",
            )

        for name, sector in j_layout.items():
            angle = (sector["start"] + sector["end"]) / 2
            x, y = self._polar_point(1.12, angle)
            rotation, ha = self._label_rotation(angle)
            ax.text(
                x,
                y,
                name,
                ha=ha,
                va="center",
                rotation=rotation,
                rotation_mode="anchor",
                fontsize=9,
                color="#1f2937",
                fontweight="semibold",
            )

        total_pairs = len(ordered_rows)
        total_weight = sum(float(row["_count_value"]) for row in ordered_rows)
        ax.text(0, 1.28, title, ha="center", va="center", fontsize=18, fontweight="bold", color="#111827")
        ax.text(
            1.22,
            1.17,
            f"V: {len(v_items)}   J: {len(j_items)}   VJ pairs: {total_pairs}",
            ha="right",
            va="center",
            fontsize=10,
            color="#4b5563",
        )
        ax.text(
            0,
            -1.22,
            f"Total weight: {self._format_count(total_weight, count_mode)}",
            ha="center",
            va="center",
            fontsize=10,
            color="#6b7280",
        )
        ax.set_xlim(-1.35, 1.35)
        ax.set_ylim(-1.35, 1.35)

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(pdf_path, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    @staticmethod
    def _path_to_href(target_path: Path, base_dir: Path) -> str:
        return target_path.relative_to(base_dir).as_posix()

    def _build_viewer_html(self, metadata: Dict[str, Any], output_base: Path) -> str:
        del output_base
        created_at = html.escape(str(metadata.get("created_at", "")))
        selected_chains = ", ".join(metadata.get("selected_chains", []))
        zip_href = f"/api/chord/export-zip/{html.escape(str(metadata.get('job_id', '')))}"
        metadata_json = json.dumps(metadata, ensure_ascii=False)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Chord Diagram Results</title>
  <style>
    :root {{
      --bg: #f4f6fb;
      --panel: #ffffff;
      --line: #dbe2ea;
      --text: #17212b;
      --muted: #667085;
      --accent: #2563eb;
      --accent-soft: #dbeafe;
      --shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(37, 99, 235, 0.08), transparent 28%),
        linear-gradient(180deg, #f8fafc 0%, var(--bg) 100%);
      color: var(--text);
    }}
    .page {{
      max-width: 1380px;
      margin: 0 auto;
      padding: 28px 24px 48px;
    }}
    .hero {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-start;
      padding: 24px 28px;
      border: 1px solid rgba(37, 99, 235, 0.12);
      border-radius: 24px;
      background: rgba(255, 255, 255, 0.9);
      backdrop-filter: blur(8px);
      box-shadow: var(--shadow);
      margin-bottom: 24px;
    }}
    .hero h1 {{ margin: 0 0 10px; font-size: 30px; line-height: 1.15; }}
    .hero p {{ margin: 0; color: var(--muted); }}
    .hero-meta {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }}
    .hero-meta span {{
      padding: 8px 12px; border-radius: 999px; background: #eef2ff; color: #334155;
      font-size: 13px; border: 1px solid #dbeafe;
    }}
    .hero-actions {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .hero-actions a {{
      text-decoration: none; padding: 11px 16px; border-radius: 12px; font-weight: 600;
      border: 1px solid transparent;
    }}
    .hero-actions .primary {{ background: var(--accent); color: #fff; }}
    .viewer-layout {{
      display:grid; grid-template-columns:minmax(0,1.7fr) minmax(320px,0.9fr); gap:20px;
    }}
    .viz-panel, .side-panel {{
      background:var(--panel); border-radius:24px; border:1px solid rgba(148,163,184,.2);
      box-shadow:0 16px 36px rgba(148,163,184,.12);
    }}
    .viz-panel {{ padding:20px; }}
    .side-panel {{ padding:20px; display:flex; flex-direction:column; gap:16px; }}
    .toolbar {{
      display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:12px; margin-bottom:14px;
    }}
    .toolbar label {{ display:block; font-size:13px; color:var(--muted); margin-bottom:6px; font-weight:600; }}
    .toolbar select {{
      width:100%; border:1px solid #dbe2ea; border-radius:12px; padding:10px 12px; background:#fff;
      color:var(--text); font-size:14px;
    }}
    .stats {{ display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:12px; margin-bottom:14px; }}
    .stat {{
      border:1px solid var(--line); border-radius:16px; background:#f8fafc; padding:12px 14px;
    }}
    .stat .label {{ font-size:12px; color:var(--muted); margin-bottom:6px; }}
    .stat .value {{ font-size:18px; font-weight:700; color:#0f172a; }}
    #chartWrap {{
      position:relative; min-height:760px; border-radius:20px; border:1px solid #e5e7eb;
      background:radial-gradient(circle at top, rgba(219,234,254,.4), transparent 32%), #fff;
      overflow:hidden;
    }}
    #chartSvg {{ width:100%; height:760px; display:block; }}
    .tooltip {{
      position:absolute; min-width:180px; padding:10px 12px; border-radius:12px; background:rgba(15,23,42,.92);
      color:#fff; font-size:13px; line-height:1.5; box-shadow:0 10px 30px rgba(15,23,42,.24);
      pointer-events:none; opacity:0; transform:translateY(6px); transition:opacity .12s ease, transform .12s ease;
    }}
    .tooltip.show {{ opacity:1; transform:translateY(0); }}
    .section-title {{ margin:0 0 8px; font-size:18px; }}
    .muted {{ margin:0; color:var(--muted); font-size:14px; line-height:1.6; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; }}
    .actions a {{
      text-decoration:none; padding:10px 14px; border-radius:12px; background:#fff;
      border:1px solid #dbe2ea; color:#1d4ed8; font-size:13px; font-weight:700;
    }}
    .gene-list {{ display:flex; flex-direction:column; gap:10px; }}
    .gene-columns {{ display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:12px; }}
    .gene-box {{
      border:1px solid var(--line); border-radius:16px; background:#f8fafc; padding:12px 14px; min-height:180px;
    }}
    .gene-box h3 {{ margin:0 0 8px; font-size:15px; }}
    .gene-box ul {{ margin:0; padding-left:18px; color:#334155; font-size:13px; line-height:1.6; }}
    .pair-table-wrap {{
      border:1px solid var(--line); border-radius:16px; overflow:auto; max-height:280px; background:#fff;
    }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ padding:10px 12px; border-bottom:1px solid #eef2f7; text-align:left; }}
    th {{ position:sticky; top:0; background:#f8fafc; color:#475569; font-weight:700; }}
    tr:hover td {{ background:#f8fbff; }}
    @media (max-width: 900px) {{
      .hero, .viewer-layout {{ display:block; }}
      .viz-panel {{ margin-bottom:18px; }}
      .toolbar, .stats, .gene-columns {{ grid-template-columns:1fr; }}
      #chartWrap, #chartSvg {{ min-height:520px; height:520px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div>
        <h1>Chord Diagram Results</h1>
        <p>Batch V/J frequency tables and chord-style diagrams generated from repertoire files.</p>
        <div class="hero-meta">
          <span>Created: {created_at}</span>
          <span>Chains: {html.escape(selected_chains)}</span>
          <span>Samples: {len(metadata.get("samples", []))}</span>
        </div>
      </div>
      <div class="hero-actions">
        <a class="primary" href="{zip_href}">Download ZIP</a>
      </div>
    </section>
    <div class="viewer-layout">
      <section class="viz-panel">
        <div class="toolbar">
          <div>
            <label for="sampleSelect">Sample</label>
            <select id="sampleSelect"></select>
          </div>
          <div>
            <label for="chainSelect">Chain</label>
            <select id="chainSelect"></select>
          </div>
        </div>
        <div class="stats">
          <div class="stat"><div class="label">VJ Pairs</div><div class="value" id="statPairs">-</div></div>
          <div class="stat"><div class="label">V Genes</div><div class="value" id="statV">-</div></div>
          <div class="stat"><div class="label">J Genes</div><div class="value" id="statJ">-</div></div>
        </div>
        <div id="chartWrap">
          <svg id="chartSvg" viewBox="-540 -540 1080 1080" preserveAspectRatio="xMidYMid meet"></svg>
          <div id="chartTooltip" class="tooltip"></div>
        </div>
      </section>
      <aside class="side-panel">
        <div>
          <h2 class="section-title" id="selectionTitle">-</h2>
          <p class="muted" id="selectionDesc">Switch sample and chain to view the chord diagram.</p>
        </div>
        <div class="actions">
          <a id="downloadCsvLink" href="#" target="_blank" rel="noopener">VJ CSV</a>
          <a id="downloadPdfLink" href="#" target="_blank" rel="noopener">PDF</a>
        </div>
        <div class="gene-columns">
          <div class="gene-box">
            <h3>Top V Genes</h3>
            <ul id="vGeneList"></ul>
          </div>
          <div class="gene-box">
            <h3>Top J Genes</h3>
            <ul id="jGeneList"></ul>
          </div>
        </div>
        <div class="pair-table-wrap">
          <table>
            <thead><tr><th>V</th><th>J</th><th>Freq</th><th>Count</th></tr></thead>
            <tbody id="pairTableBody"></tbody>
          </table>
        </div>
      </aside>
    </div>
  </div>
  <script>
    const CHORD_METADATA = {metadata_json};

    function polarPoint(radius, angleDeg) {{
      const angle = angleDeg * Math.PI / 180;
      return [radius * Math.cos(angle), radius * Math.sin(angle)];
    }}

    function sampleArc(radius, startDeg, endDeg, steps = 8) {{
      const points = [];
      const count = Math.max(steps, 2);
      for (let i = 0; i < count; i += 1) {{
        const angle = startDeg + ((endDeg - startDeg) * i / (count - 1));
        points.push(polarPoint(radius, angle));
      }}
      return points;
    }}

    function buildSectorLayout(items, startDeg, endDeg, gapDeg) {{
      if (!items.length) return {{}};
      const total = items.reduce((sum, item) => sum + Math.max(item.value, 0), 0) || 1;
      const usable = Math.max((endDeg - startDeg) - gapDeg * Math.max(items.length - 1, 0), 1);
      let cursor = startDeg;
      const layout = {{}};
      items.forEach((item, index) => {{
        const span = usable * (Math.max(item.value, 0) / total);
        const sectorEnd = index === items.length - 1 ? endDeg : cursor + span;
        layout[item.name] = {{ start: cursor, end: sectorEnd, value: item.value }};
        cursor = sectorEnd + gapDeg;
      }});
      return layout;
    }}

    function buildLinkSlots(rows, layout, itemKey, partnerKey) {{
      const grouped = new Map();
      rows.forEach((row) => {{
        const key = row[itemKey];
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(row);
      }});
      const slots = new Map();
      grouped.forEach((groupRows, name) => {{
        const sector = layout[name];
        if (!sector) return;
        const total = groupRows.reduce((sum, row) => sum + row.countValue, 0) || 1;
        let cursor = sector.start;
        const span = sector.end - sector.start;
        groupRows.forEach((row, index) => {{
          const width = span * (row.countValue / total);
          const slotEnd = index === groupRows.length - 1 ? sector.end : cursor + width;
          slots.set(`${{row[itemKey]}}|||${{row[partnerKey]}}`, [cursor, slotEnd]);
          cursor = slotEnd;
        }});
      }});
      return slots;
    }}

    function labelRotation(angleDeg) {{
      if (angleDeg > 90 && angleDeg < 270) return [angleDeg + 180, 'end'];
      return [angleDeg, 'start'];
    }}

    function svgEl(name, attrs = {{}}, text = '') {{
      const node = document.createElementNS('http://www.w3.org/2000/svg', name);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
      if (text) node.textContent = text;
      return node;
    }}

    function rgba(color, alpha) {{
      const temp = document.createElement('div');
      temp.style.color = color;
      document.body.appendChild(temp);
      const computed = getComputedStyle(temp).color;
      document.body.removeChild(temp);
      const match = computed.match(/(\\d+),\\s*(\\d+),\\s*(\\d+)/);
      if (!match) return color;
      return `rgba(${{match[1]}}, ${{match[2]}}, ${{match[3]}}, ${{alpha}})`;
    }}

    const paletteV = ['#2563eb', '#0f766e', '#7c3aed', '#d97706', '#dc2626', '#0891b2', '#4f46e5', '#059669', '#be185d', '#9333ea'];
    const paletteJ = ['#f59e0b', '#14b8a6', '#ec4899', '#8b5cf6', '#ef4444', '#22c55e', '#06b6d4', '#fb7185', '#84cc16', '#6366f1'];

    function buildCurrentData(sampleName, chainName) {{
      const sample = (CHORD_METADATA.samples || []).find((item) => item.display_name === sampleName) || CHORD_METADATA.samples?.[0];
      if (!sample) return null;
      const output = sample.outputs?.[chainName];
      if (!output) return null;
      const rows = (output.rows || []).map((row) => {{
        const freqValue = Number(row.freq || 0);
        const countValue = Number(String(row.count || '0').replace(/,/g, ''));
        return {{ ...row, freqValue, countValue }};
      }}).filter((row) => row.countValue > 0);
      return {{ sample, output, rows }};
    }}

    function renderGeneList(targetId, items) {{
      const list = document.getElementById(targetId);
      list.innerHTML = '';
      items.slice(0, 12).forEach((item) => {{
        const li = document.createElement('li');
        li.textContent = `${{item.name}} (${{item.value.toFixed(0)}})`;
        list.appendChild(li);
      }});
    }}

    function renderPairTable(rows) {{
      const tbody = document.getElementById('pairTableBody');
      tbody.innerHTML = '';
      rows.slice(0, 80).forEach((row) => {{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${{row.V}}</td><td>${{row.J}}</td><td>${{Number(row.freqValue).toFixed(4)}}</td><td>${{row.count}}</td>`;
        tbody.appendChild(tr);
      }});
    }}

    function showTooltip(evt, htmlText) {{
      const wrap = document.getElementById('chartWrap');
      const tooltip = document.getElementById('chartTooltip');
      const rect = wrap.getBoundingClientRect();
      tooltip.innerHTML = htmlText;
      tooltip.style.left = `${{evt.clientX - rect.left + 14}}px`;
      tooltip.style.top = `${{evt.clientY - rect.top + 14}}px`;
      tooltip.classList.add('show');
    }}

    function hideTooltip() {{
      document.getElementById('chartTooltip').classList.remove('show');
    }}

    function renderChart(sampleName, chainName) {{
      const current = buildCurrentData(sampleName, chainName);
      const svg = document.getElementById('chartSvg');
      svg.innerHTML = '';
      if (!current) return;

      const rows = [...current.rows].sort((a, b) => b.countValue - a.countValue || a.V.localeCompare(b.V) || a.J.localeCompare(b.J));
      const vTotals = new Map();
      const jTotals = new Map();
      rows.forEach((row) => {{
        vTotals.set(row.V, (vTotals.get(row.V) || 0) + row.countValue);
        jTotals.set(row.J, (jTotals.get(row.J) || 0) + row.countValue);
      }});

      const vItems = [...vTotals.entries()].map(([name, value]) => ({{ name, value }})).sort((a, b) => b.value - a.value || a.name.localeCompare(b.name));
      const jItems = [...jTotals.entries()].map(([name, value]) => ({{ name, value }})).sort((a, b) => b.value - a.value || a.name.localeCompare(b.name));
      const vLayout = buildSectorLayout(vItems, 110, 250, 2);
      const jLayout = buildSectorLayout(jItems, -70, 70, 2);
      const vSlots = buildLinkSlots(rows, vLayout, 'V', 'J');
      const jSlots = buildLinkSlots(rows, jLayout, 'J', 'V');

      const outerRadius = 410;
      const innerRadius = 335;
      const controlRadius = 110;
      const maxPair = Math.max(...rows.map((row) => row.countValue), 1);

      const arcGroup = svgEl('g');
      const chordGroup = svgEl('g');
      const labelGroup = svgEl('g');
      svg.append(arcGroup, chordGroup, labelGroup);

      function arcPath(start, end, outerR, innerR) {{
        const [x1, y1] = polarPoint(outerR, start);
        const [x2, y2] = polarPoint(outerR, end);
        const [x3, y3] = polarPoint(innerR, end);
        const [x4, y4] = polarPoint(innerR, start);
        const large = Math.abs(end - start) > 180 ? 1 : 0;
        return [
          `M ${{x1}} ${{y1}}`,
          `A ${{outerR}} ${{outerR}} 0 ${{large}} 1 ${{x2}} ${{y2}}`,
          `L ${{x3}} ${{y3}}`,
          `A ${{innerR}} ${{innerR}} 0 ${{large}} 0 ${{x4}} ${{y4}}`,
          'Z'
        ].join(' ');
      }}

      const vColorMap = new Map(vItems.map((item, idx) => [item.name, paletteV[idx % paletteV.length]]));
      const jColorMap = new Map(jItems.map((item, idx) => [item.name, paletteJ[idx % paletteJ.length]]));

      vItems.forEach((item) => {{
        const sector = vLayout[item.name];
        const path = svgEl('path', {{
          d: arcPath(sector.start, sector.end, outerRadius, innerRadius),
          fill: vColorMap.get(item.name),
          stroke: '#fff',
          'stroke-width': 1
        }});
        path.addEventListener('mousemove', (evt) => showTooltip(evt, `<strong>V gene</strong><br>${{item.name}}<br>Count: ${{item.value.toFixed(0)}}`));
        path.addEventListener('mouseleave', hideTooltip);
        arcGroup.appendChild(path);
      }});

      jItems.forEach((item) => {{
        const sector = jLayout[item.name];
        const path = svgEl('path', {{
          d: arcPath(sector.start, sector.end, outerRadius, innerRadius),
          fill: jColorMap.get(item.name),
          stroke: '#fff',
          'stroke-width': 1
        }});
        path.addEventListener('mousemove', (evt) => showTooltip(evt, `<strong>J gene</strong><br>${{item.name}}<br>Count: ${{item.value.toFixed(0)}}`));
        path.addEventListener('mouseleave', hideTooltip);
        arcGroup.appendChild(path);
      }});

      rows.forEach((row) => {{
        const vSlot = vSlots.get(`${{row.V}}|||${{row.J}}`);
        const jSlot = jSlots.get(`${{row.J}}|||${{row.V}}`);
        if (!vSlot || !jSlot) return;
        const [sStart, sEnd] = vSlot;
        const [dStart, dEnd] = jSlot;
        const sourceArc = sampleArc(innerRadius, sStart, sEnd, 8);
        const destArc = sampleArc(innerRadius, dStart, dEnd, 8);
        const c1 = polarPoint(controlRadius, sEnd);
        const c2 = polarPoint(controlRadius, dStart);
        const c3 = polarPoint(controlRadius, dEnd);
        const c4 = polarPoint(controlRadius, sStart);
        const d = [
          `M ${{sourceArc[0][0]}} ${{sourceArc[0][1]}}`,
          ...sourceArc.slice(1).map((point) => `L ${{point[0]}} ${{point[1]}}`),
          `C ${{c1[0]}} ${{c1[1]}}, ${{c2[0]}} ${{c2[1]}}, ${{destArc[0][0]}} ${{destArc[0][1]}}`,
          ...destArc.slice(1).map((point) => `L ${{point[0]}} ${{point[1]}}`),
          `C ${{c3[0]}} ${{c3[1]}}, ${{c4[0]}} ${{c4[1]}}, ${{sourceArc[0][0]}} ${{sourceArc[0][1]}}`,
          'Z'
        ].join(' ');
        const path = svgEl('path', {{
          d,
          fill: rgba(vColorMap.get(row.V) || '#4f46e5', 0.58),
          stroke: 'rgba(255,255,255,0.24)',
          'stroke-width': 0.5 + 0.8 * (row.countValue / maxPair)
        }});
        path.addEventListener('mousemove', (evt) => showTooltip(
          evt,
          `<strong>${{row.V}} → ${{row.J}}</strong><br>Freq: ${{row.freq}}<br>Count: ${{row.count}}`
        ));
        path.addEventListener('mouseleave', hideTooltip);
        chordGroup.appendChild(path);
      }});

      function addLabels(items, layout) {{
        items.forEach((item) => {{
          const sector = layout[item.name];
          const angle = (sector.start + sector.end) / 2;
          const point = polarPoint(455, angle);
          const [rotate, anchor] = labelRotation(angle);
          const text = svgEl('text', {{
            x: point[0],
            y: point[1],
            fill: '#1f2937',
            'font-size': 13,
            'font-weight': 600,
            'text-anchor': anchor,
            transform: `rotate(${{rotate}} ${{point[0]}} ${{point[1]}})`
          }}, item.name);
          labelGroup.appendChild(text);
        }});
      }}

      addLabels(vItems, vLayout);
      addLabels(jItems, jLayout);
      labelGroup.appendChild(svgEl('text', {{ x: 0, y: -470, 'text-anchor': 'middle', fill: '#0f172a', 'font-size': 28, 'font-weight': 700 }}, `${{current.sample.display_name}} · ${{chainName}}`));
      labelGroup.appendChild(svgEl('text', {{ x: 470, y: -438, 'text-anchor': 'end', fill: '#475569', 'font-size': 15, 'font-weight': 700 }}, `V: ${{vItems.length}}   J: ${{jItems.length}}   VJ pairs: ${{rows.length}}`));

      document.getElementById('statPairs').textContent = rows.length;
      document.getElementById('statV').textContent = vItems.length;
      document.getElementById('statJ').textContent = jItems.length;
      document.getElementById('selectionTitle').textContent = `${{current.sample.display_name}} / ${{chainName}}`;
      document.getElementById('selectionDesc').textContent = current.output.input_file || '';
      document.getElementById('downloadCsvLink').href = current.output.csv || '#';
      document.getElementById('downloadPdfLink').href = current.output.pdf || '#';
      renderGeneList('vGeneList', vItems);
      renderGeneList('jGeneList', jItems);
      renderPairTable(rows);
    }}

    function updateChainOptions() {{
      const sampleName = document.getElementById('sampleSelect').value;
      const chainSelect = document.getElementById('chainSelect');
      const sample = (CHORD_METADATA.samples || []).find((item) => item.display_name === sampleName) || CHORD_METADATA.samples?.[0];
      chainSelect.innerHTML = '';
      (sample?.chains || []).forEach((chain) => {{
        const option = document.createElement('option');
        option.value = chain;
        option.textContent = chain;
        chainSelect.appendChild(option);
      }});
      renderChart(sample?.display_name, chainSelect.value);
    }}

    function initViewer() {{
      const samples = CHORD_METADATA.samples || [];
      const sampleSelect = document.getElementById('sampleSelect');
      const chainSelect = document.getElementById('chainSelect');
      sampleSelect.innerHTML = '';
      samples.forEach((sample) => {{
        const option = document.createElement('option');
        option.value = sample.display_name;
        option.textContent = sample.display_name;
        sampleSelect.appendChild(option);
      }});
      sampleSelect.addEventListener('change', updateChainOptions);
      chainSelect.addEventListener('change', () => renderChart(sampleSelect.value, chainSelect.value));
      if (samples.length) {{
        updateChainOptions();
      }}
    }}

    initViewer();
  </script>
</body>
</html>
"""

    def _write_viewer(self, metadata: Dict[str, Any], output_base: Path) -> Path:
        viewer_path = output_base / self._VIEWER_FILE_NAME
        viewer_path.write_text(self._build_viewer_html(metadata, output_base), encoding="utf-8")
        return viewer_path

    @staticmethod
    def _progress_value(index: int, total: int, start: float = 8.0, end: float = 92.0) -> float:
        if total <= 0:
            return end
        return start + (end - start) * (index / total)

    def generate_report(
        self,
        *,
        samples: List[Dict[str, Any]],
        selected_chains: List[str],
        field_mapping: Dict[str, Any],
        output_name: Optional[str],
        count_mode: str = "rows",
        progress_callback: Optional[Callable[[float, str, str, Dict[str, Any]], None]] = None,
    ) -> ChordReportResult:
        count_mode = "rows"

        job_id = self._allocate_job_id(output_name)
        output_base = self.results_root / self._RESULT_DIR / job_id
        output_base.mkdir(parents=True, exist_ok=True)
        artifact_root = output_base / "chord_diagram"
        artifact_root.mkdir(parents=True, exist_ok=True)

        tasks: List[Dict[str, Any]] = []
        sample_records: Dict[str, Dict[str, Any]] = {}
        for sample in samples:
            display_name = str(sample.get("display_name") or sample.get("original_name") or "sample")
            sample_name = str(sample.get("original_name") or display_name)
            chain_files = self._extract_sample_chain_files(sample, selected_chains)
            if not chain_files:
                continue
            sample_record = sample_records.setdefault(
                display_name,
                {
                    "sample_name": sample_name,
                    "display_name": display_name,
                    "chains": [],
                    "outputs": {},
                },
            )
            for chain in selected_chains:
                filepath = chain_files.get(chain)
                if not filepath:
                    continue
                sample_record["chains"].append(chain)
                tasks.append(
                    {
                        "sample_name": sample_name,
                        "display_name": display_name,
                        "chain": chain,
                        "filepath": filepath,
                    }
                )

        if not tasks:
            raise ValidationError(message="未找到与所选样本/链匹配的输入文件。")

        def emit(progress: float, stage: str, detail: str, meta: Optional[Dict[str, Any]] = None) -> None:
            if progress_callback:
                progress_callback(progress, stage, detail, meta or {})

        emit(
            0.0,
            "任务已创建",
            "正在准备 chord diagram 任务。",
            {
                "phase": "queued",
                "total_samples": len(sample_records),
                "selected_chain_count": len(selected_chains),
                "selected_chains": list(selected_chains),
                "total_units": len(tasks),
                "completed_units": 0,
            },
        )

        for index, task in enumerate(tasks, start=1):
            sample_safe = self._sanitize_file_stem(str(task["display_name"]))
            sample_dir = artifact_root / sample_safe
            sample_dir.mkdir(parents=True, exist_ok=True)

            base_name = f"{sample_safe}__{task['chain']}"
            csv_path = sample_dir / f"{base_name}.vj_freq.csv"
            pdf_path = sample_dir / f"{base_name}.pdf"

            input_path = Path(str(task["filepath"])).expanduser().resolve()
            emit(
                self._progress_value(index - 1, len(tasks)),
                "生成中",
                f"{task['display_name']} | {task['chain']} | 读取输入文件",
                {
                    "phase": "read_input",
                    "current_sample": task["display_name"],
                    "current_sample_index": index,
                    "total_units": len(tasks),
                    "completed_units": index - 1,
                    "current_chain": task["chain"],
                    "current_input_file": input_path.name,
                },
            )

            source_rows, total_weight = self._build_vj_table_from_file(
                input_path,
                v_column=str(field_mapping.get("v_column") or ""),
                j_column=str(field_mapping.get("j_column") or ""),
                copy_column=str(field_mapping.get("copy_column") or "") or None,
                count_mode=count_mode,
            )
            self._write_table(source_rows, csv_path)
            rows = self._load_vj_table(csv_path)

            emit(
                self._progress_value(index - 0.45, len(tasks)),
                "生成中",
                f"{task['display_name']} | {task['chain']} | 基于频率表绘制 PDF",
                {
                    "phase": "render_plot",
                    "current_sample": task["display_name"],
                    "current_sample_index": index,
                    "total_units": len(tasks),
                    "completed_units": index - 1,
                    "current_chain": task["chain"],
                    "current_input_file": input_path.name,
                    "current_output_file": pdf_path.name,
                },
            )

            title = f"{task['display_name']} {task['chain']}"
            self._draw_chord_diagram(
                rows,
                title=title,
                count_mode=count_mode,
                pdf_path=pdf_path,
            )

            sample_record = sample_records[str(task["display_name"])]
            sample_record["outputs"][str(task["chain"])] = {
                "csv": self._path_to_href(csv_path, output_base),
                "pdf": self._path_to_href(pdf_path, output_base),
                "input_file": input_path.name,
                "pair_count": len(rows),
                "total_weight": self._format_count(total_weight, count_mode),
                "rows": self._viewer_rows(rows),
            }

        metadata_samples = []
        for sample_record in sample_records.values():
            chains = [chain for chain in selected_chains if chain in sample_record["outputs"]]
            if not chains:
                continue
            sample_record["chains"] = chains
            metadata_samples.append(sample_record)

        metadata = {
            "job_id": job_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "selected_chains": list(selected_chains),
            "sample_count": len(metadata_samples),
            "total_outputs": len(tasks),
            "artifact_root": "chord_diagram",
            "samples": metadata_samples,
        }

        viewer_path = self._write_viewer(metadata, output_base)
        metadata["viewer"] = self._path_to_href(viewer_path, output_base)

        metadata_path = output_base / self._METADATA_FILE_NAME
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        emit(
            100.0,
            "任务完成",
            f"共生成 {len(tasks)} 个 chord 图结果。",
            {
                "phase": "completed",
                "total_samples": len(metadata_samples),
                "selected_chain_count": len(selected_chains),
                "selected_chains": list(selected_chains),
                "total_units": len(tasks),
                "completed_units": len(tasks),
            },
        )

        return ChordReportResult(
            job_id=job_id,
            output_base=output_base,
            metadata_path=metadata_path,
            metadata=metadata,
        )

    def read_metadata(self, job_id: str) -> Dict[str, Any]:
        metadata_path = self._resolve_job_root(job_id) / self._METADATA_FILE_NAME
        if not metadata_path.exists():
            raise FileNotFoundError(f"Chord metadata not found: {job_id}")
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def _resolve_job_root(self, job_id: str) -> Path:
        safe_job_id = self._sanitize_job_id(job_id)
        for job_root in candidate_job_roots(self.results_root, self._RESULT_DIR, safe_job_id):
            if job_root.exists() and job_root.is_dir():
                return job_root
        raise FileNotFoundError(f"Chord result directory not found: {job_id}")

    def resolve_result_path(self, job_id: str, relative_path: str) -> Path:
        base_dir = self._resolve_job_root(job_id)
        target_path = (base_dir / relative_path).resolve()
        if not str(target_path).startswith(str(base_dir)):
            raise ValidationError(message="非法结果文件路径。")
        if not target_path.exists():
            raise FileNotFoundError(f"Chord result file not found: {relative_path}")
        return target_path

    def build_zip_archive(self, job_id: str) -> Tuple[io.BytesIO, str]:
        base_dir = self._resolve_job_root(job_id)
        artifact_root = (base_dir / "chord_diagram").resolve()
        if not artifact_root.exists():
            raise FileNotFoundError(f"Chord artifact directory not found: {job_id}")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for path in artifact_root.rglob("*"):
                if path.is_file():
                    archive_name = path.relative_to(base_dir).as_posix()
                    zip_file.write(path, archive_name)
        buffer.seek(0)
        return buffer, f"{job_id}_chord_diagram.zip"


_chord_report_service: Optional[ChordReportService] = None


def get_chord_report_service(results_root: Optional[Path] = None) -> ChordReportService:
    global _chord_report_service
    resolved_root = Path(results_root or Path.cwd() / "data" / "results").resolve()
    if _chord_report_service is None or _chord_report_service.results_root != resolved_root:
        _chord_report_service = ChordReportService(results_root=resolved_root)
    return _chord_report_service
