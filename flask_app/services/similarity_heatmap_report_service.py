"""
Similarity heatmap HTML report service.

Builds a lightweight report from already generated heatmap API results and
stores report assets under:
<results_root>/similarity_heatmap_report/<job_id>/shared_analysis/
"""

from __future__ import annotations

import base64
import csv
import html
import json
import logging
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask_app.exceptions import ValidationError

logger = logging.getLogger(__name__)


METRIC_LABELS: Dict[str, str] = {
    "expression_sharing": "Expression Sharing",
    "morisita_horn": "Morisita-Horn Index",
    "cdr3_sharing": "Unique CDR3 Sharing",
    "r2_inner": "R2 Inner",
    "r2_outer": "R2 Outer",
    "sorensen": "Sorensen-Dice Index",
}


@dataclass
class SimilarityHeatmapReportResult:
    """Generated similarity heatmap report metadata."""

    job_id: str
    output_base: Path
    metadata_path: Path
    report_path: Path
    metadata: Dict[str, Any]


class SimilarityHeatmapReportService:
    """Generate and serve HTML reports for similarity heatmap results."""

    _RESULT_DIR = "similarity_heatmap_report"
    _REPORT_FILE_NAME = "similarity_heatmap_report.html"

    def __init__(self, results_root: Path):
        self.results_root = Path(results_root).resolve()
        self.results_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    @staticmethod
    def _sanitize_job_id(raw_name: Optional[str]) -> str:
        if raw_name:
            candidate = re.sub(r"[^A-Za-z0-9_-]+", "_", str(raw_name).strip())
            candidate = candidate.strip("_")
            if candidate:
                return candidate
        return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

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
    def _ordered_metric_keys(metrics_map: Dict[str, Any]) -> List[str]:
        known = [k for k in METRIC_LABELS.keys() if k in metrics_map]
        extra = sorted([k for k in metrics_map.keys() if k not in METRIC_LABELS])
        return known + extra

    @staticmethod
    def _decode_base64_image(image_base64: str) -> bytes:
        if not image_base64 or not isinstance(image_base64, str):
            raise ValidationError(message="Invalid heatmap image data.")

        payload = image_base64
        if "," in payload:
            payload = payload.split(",", 1)[1]

        try:
            return base64.b64decode(payload, validate=True)
        except Exception as exc:
            raise ValidationError(message="Failed to decode heatmap image data.") from exc

    @staticmethod
    def _safe_text(value: Any) -> str:
        return html.escape("" if value is None else str(value))

    @staticmethod
    def _format_value_for_table(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    def _build_table_data(self, metric_info: Dict[str, Any]) -> Dict[str, List[Any]]:
        table_data = metric_info.get("table_data")
        if isinstance(table_data, dict):
            columns = table_data.get("columns")
            rows = table_data.get("rows")
            if isinstance(columns, list) and isinstance(rows, list):
                return {
                    "columns": columns,
                    "rows": rows,
                }

        matrix_data = metric_info.get("matrix_data")
        if not isinstance(matrix_data, dict):
            raise ValidationError(message="Metric table/matrix data is missing.")

        col_labels = matrix_data.get("columns")
        if not isinstance(col_labels, list) or not col_labels:
            col_labels = matrix_data.get("samples") or matrix_data.get("groups") or []
        row_labels = matrix_data.get("samples") or matrix_data.get("groups") or col_labels
        values = matrix_data.get("values") or []

        if not isinstance(row_labels, list) or not isinstance(values, list):
            raise ValidationError(message="Invalid matrix_data payload.")

        rows: List[List[Any]] = []
        for idx, row_values in enumerate(values):
            if not isinstance(row_values, list):
                row_values = []
            row_name = row_labels[idx] if idx < len(row_labels) else f"row_{idx + 1}"
            rows.append([row_name] + row_values)

        header_name = "Sample"
        if "groups" in matrix_data and isinstance(matrix_data.get("groups"), list):
            header_name = "Group"

        return {
            "columns": [header_name] + list(col_labels),
            "rows": rows,
        }

    def _write_matrix_csv(self, matrix_data: Dict[str, Any], csv_path: Path) -> None:
        if not isinstance(matrix_data, dict):
            raise ValidationError(message="matrix_data is required to write CSV.")

        col_labels = matrix_data.get("columns")
        if not isinstance(col_labels, list) or not col_labels:
            col_labels = matrix_data.get("samples") or matrix_data.get("groups") or []
        row_labels = matrix_data.get("samples") or matrix_data.get("groups") or col_labels
        values = matrix_data.get("values")

        if not isinstance(row_labels, list) or not isinstance(values, list):
            raise ValidationError(message="Invalid matrix_data structure.")

        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", encoding="utf-8", newline="") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerow([""] + list(col_labels))
            for idx, row_values in enumerate(values):
                if not isinstance(row_values, list):
                    row_values = []
                row_name = row_labels[idx] if idx < len(row_labels) else f"row_{idx + 1}"
                writer.writerow([row_name] + row_values)

    def _write_metric_assets(
        self,
        metric_name: str,
        metric_info: Dict[str, Any],
        image_base64: Optional[str],
        image_path: Path,
        csv_path: Path,
        output_base: Path,
        embed_images: bool,
    ) -> Dict[str, Any]:
        matrix_data = metric_info.get("matrix_data")
        if not isinstance(matrix_data, dict):
            raise ValidationError(message=f"matrix_data is missing for metric: {metric_name}")

        self._write_matrix_csv(matrix_data, csv_path)
        csv_rel_path = csv_path.relative_to(output_base).as_posix()

        image_src = ""
        image_rel_path: Optional[str] = None
        if image_base64:
            image_bytes = self._decode_base64_image(image_base64)
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(image_bytes)
            image_rel_path = image_path.relative_to(output_base).as_posix()
            if embed_images:
                image_src = f"data:image/png;base64,{image_base64.split(',', 1)[-1]}"
            else:
                image_src = image_rel_path

        table_data = self._build_table_data(metric_info)
        return {
            "metric_name": metric_name,
            "metric_label": METRIC_LABELS.get(metric_name, metric_name),
            "image_src": image_src,
            "image_rel_path": image_rel_path,
            "csv_rel_path": csv_rel_path,
            "table_columns": table_data.get("columns", []),
            "table_rows": table_data.get("rows", []),
        }

    def _render_table_html(self, columns: List[Any], rows: List[Any]) -> str:
        if not columns or not rows:
            return '<p class="empty-note">No table data available.</p>'

        header_html = "".join(f"<th>{self._safe_text(col)}</th>" for col in columns)
        body_lines: List[str] = []
        for row in rows:
            if not isinstance(row, list):
                continue
            cells = "".join(
                f"<td>{self._safe_text(self._format_value_for_table(cell))}</td>"
                for cell in row
            )
            body_lines.append(f"<tr>{cells}</tr>")

        if not body_lines:
            return '<p class="empty-note">No table rows available.</p>'

        return (
            '<div class="table-wrap"><table class="metric-table">'
            f"<thead><tr>{header_html}</tr></thead>"
            f"<tbody>{''.join(body_lines)}</tbody>"
            "</table></div>"
        )

    def _render_section_html(self, section_id: str, section_title: str, entries: List[Dict[str, Any]]) -> str:
        if not entries:
            return ""

        tab_buttons: List[str] = []
        tab_panels: List[str] = []

        for idx, entry in enumerate(entries):
            metric_key = entry["metric_name"]
            metric_label = entry["metric_label"]
            panel_id = f"{section_id}_{metric_key}"
            is_active = idx == 0
            active_class = " active" if is_active else ""

            tab_buttons.append(
                "<button class=\"metric-tab-btn{active}\" data-target=\"{panel}\">{label}</button>".format(
                    active=active_class,
                    panel=self._safe_text(panel_id),
                    label=self._safe_text(metric_label),
                )
            )

            image_html = '<p class="empty-note">Heatmap image is not available.</p>'
            if entry.get("image_src"):
                image_html = (
                    f'<img src="{self._safe_text(entry["image_src"])}" '
                    f'alt="{self._safe_text(metric_label)} heatmap" class="heatmap-image">'
                )

            csv_rel_path = entry.get("csv_rel_path")
            csv_link_html = ""
            if csv_rel_path:
                csv_link_html = (
                    f'<a class="download-link" href="{self._safe_text(csv_rel_path)}" download>'
                    "Download CSV</a>"
                )

            table_html = self._render_table_html(
                entry.get("table_columns", []),
                entry.get("table_rows", []),
            )
            tab_panels.append(
                "<section id=\"{panel}\" class=\"metric-panel{active}\">"
                "<div class=\"metric-meta\">{csv_link}</div>"
                "<div class=\"image-wrap\">{image_html}</div>"
                "<div class=\"table-card\"><h4>Related Table Data</h4>{table_html}</div>"
                "</section>".format(
                    panel=self._safe_text(panel_id),
                    active=active_class,
                    csv_link=csv_link_html,
                    image_html=image_html,
                    table_html=table_html,
                )
            )

        return (
            "<section class=\"report-section\">"
            f"<h2>{self._safe_text(section_title)}</h2>"
            f"<div class=\"metric-tabs\">{''.join(tab_buttons)}</div>"
            f"<div>{''.join(tab_panels)}</div>"
            "</section>"
        )

    def _build_report_html(
        self,
        job_id: str,
        sections: List[Dict[str, Any]],
        metadata: Dict[str, Any],
    ) -> str:
        generated_at = metadata.get("generated_at", "")
        mode = metadata.get("mode", "")
        summary_items = [
            f"<li><strong>Job ID:</strong> {self._safe_text(job_id)}</li>",
            f"<li><strong>Generated At:</strong> {self._safe_text(generated_at)}</li>",
            f"<li><strong>Mode:</strong> {self._safe_text(mode)}</li>",
        ]
        context = metadata.get("context")
        if isinstance(context, dict):
            base_path = context.get("base_path")
            if base_path:
                summary_items.append(
                    f"<li><strong>Source Folder:</strong> {self._safe_text(base_path)}</li>"
                )
        renderable_sections = [
            section
            for section in sections
            if section.get("entries")
        ]
        rendered_sections: List[Dict[str, str]] = []
        for section in renderable_sections:
            rendered_html = self._render_section_html(
                section_id=section["id"],
                section_title=section["title"],
                entries=section["entries"],
            )
            if not rendered_html:
                continue
            rendered_sections.append(
                {
                    "id": str(section["id"]),
                    "title": str(section["title"]),
                    "html": rendered_html,
                }
            )

        use_chain_tabs = mode == "chain" and len(rendered_sections) > 1
        if use_chain_tabs:
            chain_tab_buttons: List[str] = []
            chain_tab_panels: List[str] = []
            for idx, section in enumerate(rendered_sections):
                panel_id = f"chain_panel_{section['id']}"
                is_active = idx == 0
                active_class = " active" if is_active else ""
                section_title = section["title"]
                chain_label = (
                    section_title.split(":", 1)[1].strip()
                    if section_title.lower().startswith("chain:")
                    else section_title
                )
                chain_tab_buttons.append(
                    "<button class=\"chain-tab-btn{active}\" data-target=\"{panel}\">{label}</button>".format(
                        active=active_class,
                        panel=self._safe_text(panel_id),
                        label=self._safe_text(chain_label),
                    )
                )
                chain_tab_panels.append(
                    "<div id=\"{panel}\" class=\"chain-panel{active}\">{content}</div>".format(
                        panel=self._safe_text(panel_id),
                        active=active_class,
                        content=section["html"],
                    )
                )
            section_html = (
                "<section class=\"chain-tab-shell\">"
                "<h2>Chains</h2>"
                f"<div class=\"chain-tabs\">{''.join(chain_tab_buttons)}</div>"
                f"<div class=\"chain-panels\">{''.join(chain_tab_panels)}</div>"
                "</section>"
            )
        else:
            section_html = "".join(section["html"] for section in rendered_sections)

        return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Similarity Heatmap Report</title>
  <style>
    :root {{
      --bg: #f2f5f8;
      --panel: #ffffff;
      --ink: #1d2433;
      --muted: #60708a;
      --line: #d9e1ea;
      --accent: #1f6feb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 28px;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background: linear-gradient(180deg, #f6f8fb, #eef3f8 45%, #e8eff7);
    }}
    .page {{
      max-width: 1360px;
      margin: 0 auto;
    }}
    .hero {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 22px;
      margin-bottom: 18px;
      box-shadow: 0 8px 30px rgba(27, 39, 74, 0.06);
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-size: 26px;
    }}
    .summary {{
      margin: 0;
      padding-left: 20px;
      color: var(--muted);
    }}
    .report-section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 16px;
      box-shadow: 0 8px 30px rgba(27, 39, 74, 0.04);
    }}
    .report-section h2 {{
      margin: 0 0 14px;
      font-size: 20px;
    }}
    .chain-tab-shell {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 16px;
      box-shadow: 0 8px 30px rgba(27, 39, 74, 0.04);
    }}
    .chain-tab-shell h2 {{
      margin: 0 0 14px;
      font-size: 20px;
    }}
    .chain-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }}
    .chain-tab-btn {{
      border: 1px solid var(--line);
      background: #f8fbff;
      color: #3c4e66;
      border-radius: 999px;
      padding: 6px 12px;
      cursor: pointer;
      font-size: 13px;
      transition: all .12s ease;
    }}
    .chain-tab-btn.active {{
      background: #0f6c5a;
      border-color: #0f6c5a;
      color: #fff;
    }}
    .chain-panel {{
      display: none;
    }}
    .chain-panel.active {{
      display: block;
    }}
    .chain-panel .report-section {{
      margin-bottom: 0;
      box-shadow: none;
    }}
    .metric-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }}
    .metric-tab-btn {{
      border: 1px solid var(--line);
      background: #f8fbff;
      color: #3c4e66;
      border-radius: 999px;
      padding: 6px 12px;
      cursor: pointer;
      font-size: 13px;
      transition: all .12s ease;
    }}
    .metric-tab-btn.active {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}
    .metric-panel {{
      display: none;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      background: #fcfdff;
    }}
    .metric-panel.active {{
      display: block;
    }}
    .metric-meta {{
      display: flex;
      justify-content: flex-end;
      margin-bottom: 8px;
    }}
    .download-link {{
      color: var(--accent);
      font-size: 13px;
      text-decoration: none;
      border: 1px solid #b9d4ff;
      padding: 4px 10px;
      border-radius: 999px;
      background: #f3f8ff;
    }}
    .image-wrap {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
      padding: 8px;
      margin-bottom: 12px;
    }}
    .heatmap-image {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 0 auto;
    }}
    .table-card h4 {{
      margin: 0 0 8px;
      font-size: 15px;
      color: #334257;
    }}
    .table-wrap {{
      max-height: 420px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
    }}
    .metric-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }}
    .metric-table th,
    .metric-table td {{
      border: 1px solid #e2e8f0;
      padding: 6px 8px;
      text-align: center;
      white-space: nowrap;
    }}
    .metric-table th {{
      background: #f1f5fa;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    .empty-note {{
      margin: 10px 0;
      color: #7d8da5;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>Similarity Heatmap Web Report</h1>
      <ul class="summary">{summary_items}</ul>
    </section>
    {section_html}
  </main>
  <script>
    (function() {{
      const chainButtons = document.querySelectorAll('.chain-tab-btn');
      if (chainButtons.length > 0) {{
        const chainPanels = document.querySelectorAll('.chain-panel');
        chainButtons.forEach((btn) => {{
          btn.addEventListener('click', () => {{
            const targetId = btn.getAttribute('data-target');
            chainButtons.forEach((x) => x.classList.remove('active'));
            chainPanels.forEach((x) => x.classList.remove('active'));
            btn.classList.add('active');
            const panel = document.getElementById(targetId);
            if (panel) panel.classList.add('active');
          }});
        }});
      }}
      const sectionNodes = document.querySelectorAll('.report-section');
      sectionNodes.forEach((section) => {{
        const buttons = section.querySelectorAll('.metric-tab-btn');
        const panels = section.querySelectorAll('.metric-panel');
        buttons.forEach((btn) => {{
          btn.addEventListener('click', () => {{
            const targetId = btn.getAttribute('data-target');
            buttons.forEach((x) => x.classList.remove('active'));
            panels.forEach((x) => x.classList.remove('active'));
            btn.classList.add('active');
            const panel = section.querySelector('#' + CSS.escape(targetId));
            if (panel) panel.classList.add('active');
          }});
        }});
      }});
    }})();
  </script>
</body>
</html>""".format(
            summary_items="".join(summary_items),
            section_html=section_html,
        )

    def generate_report(
        self,
        heatmap_result: Dict[str, Any],
        output_name: Optional[str] = None,
        embed_images: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> SimilarityHeatmapReportResult:
        """
        Generate a report from existing heatmap response data.
        """
        if not isinstance(heatmap_result, dict):
            raise ValidationError(message="heatmap_result must be an object.")

        mode = str(heatmap_result.get("mode") or "traditional").strip().lower()
        embed_images = self._normalize_bool(embed_images, False)
        context = context if isinstance(context, dict) else {}

        job_id = self._allocate_job_id(output_name)
        run_root = self.results_root / self._RESULT_DIR / job_id
        output_base = run_root / "shared_analysis"
        output_base.mkdir(parents=True, exist_ok=True)

        sections: List[Dict[str, Any]] = []
        metric_count = 0
        image_count = 0

        if mode == "chain":
            chains_data = heatmap_result.get("chains")
            if not isinstance(chains_data, dict) or not chains_data:
                raise ValidationError(message="No chain heatmap results were provided.")

            for chain_name in sorted(chains_data.keys()):
                chain_payload = chains_data.get(chain_name) or {}
                metrics_map = chain_payload.get("metrics")
                images_map = chain_payload.get("images") or {}
                if not isinstance(metrics_map, dict) or not metrics_map:
                    continue

                section_entries: List[Dict[str, Any]] = []
                for metric_name in self._ordered_metric_keys(metrics_map):
                    metric_info = metrics_map.get(metric_name)
                    if not isinstance(metric_info, dict):
                        continue
                    entry = self._write_metric_assets(
                        metric_name=metric_name,
                        metric_info=metric_info,
                        image_base64=images_map.get(metric_name),
                        image_path=output_base / "heatmap" / chain_name / f"{metric_name}.png",
                        csv_path=output_base / "metric" / chain_name / f"{metric_name}.csv",
                        output_base=output_base,
                        embed_images=embed_images,
                    )
                    section_entries.append(entry)
                    metric_count += 1
                    if entry.get("image_rel_path"):
                        image_count += 1

                if section_entries:
                    sections.append(
                        {
                            "id": f"chain_{re.sub(r'[^A-Za-z0-9_-]+', '_', chain_name)}",
                            "title": f"Chain: {chain_name}",
                            "entries": section_entries,
                        }
                    )
        else:
            metrics_map = heatmap_result.get("metrics")
            images_map = heatmap_result.get("images") or {}
            if isinstance(metrics_map, dict) and metrics_map:
                original_entries: List[Dict[str, Any]] = []
                for metric_name in self._ordered_metric_keys(metrics_map):
                    metric_info = metrics_map.get(metric_name)
                    if not isinstance(metric_info, dict):
                        continue
                    entry = self._write_metric_assets(
                        metric_name=metric_name,
                        metric_info=metric_info,
                        image_base64=images_map.get(metric_name),
                        image_path=output_base / "heatmap" / "single_sample" / f"{metric_name}.png",
                        csv_path=output_base / "metric" / "single_sample" / f"{metric_name}.csv",
                        output_base=output_base,
                        embed_images=embed_images,
                    )
                    original_entries.append(entry)
                    metric_count += 1
                    if entry.get("image_rel_path"):
                        image_count += 1

                if original_entries:
                    sections.append(
                        {
                            "id": "original",
                            "title": "Original Sample Heatmaps",
                            "entries": original_entries,
                        }
                    )

            grouped_metrics_map = heatmap_result.get("grouped_metrics")
            grouped_images_map = heatmap_result.get("grouped_images") or {}
            if isinstance(grouped_metrics_map, dict) and grouped_metrics_map:
                grouped_entries: List[Dict[str, Any]] = []
                for metric_name in self._ordered_metric_keys(grouped_metrics_map):
                    metric_info = grouped_metrics_map.get(metric_name)
                    if not isinstance(metric_info, dict):
                        continue
                    entry = self._write_metric_assets(
                        metric_name=metric_name,
                        metric_info=metric_info,
                        image_base64=grouped_images_map.get(metric_name),
                        image_path=output_base / "heatmap" / "grouped" / f"{metric_name}.png",
                        csv_path=output_base / "metric" / "grouped" / f"{metric_name}.csv",
                        output_base=output_base,
                        embed_images=embed_images,
                    )
                    grouped_entries.append(entry)
                    metric_count += 1
                    if entry.get("image_rel_path"):
                        image_count += 1

                if grouped_entries:
                    sections.append(
                        {
                            "id": "grouped",
                            "title": "Grouped Average Heatmaps",
                            "entries": grouped_entries,
                        }
                    )

        if not sections:
            raise ValidationError(message="No heatmap/table data was found for report generation.")

        metadata: Dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "job_id": job_id,
            "mode": mode,
            "sections": [section["title"] for section in sections],
            "metrics_count": metric_count,
            "images_count": image_count,
            "embed_images": embed_images,
            "context": context,
        }

        metadata_path = output_base / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as file_obj:
            json.dump(metadata, file_obj, ensure_ascii=False, indent=2)

        report_html = self._build_report_html(
            job_id=job_id,
            sections=sections,
            metadata=metadata,
        )
        report_path = output_base / self._REPORT_FILE_NAME
        report_path.write_text(report_html, encoding="utf-8")

        return SimilarityHeatmapReportResult(
            job_id=job_id,
            output_base=output_base,
            metadata_path=metadata_path,
            report_path=report_path,
            metadata=metadata,
        )

    def resolve_result_file(self, job_id: str, relative_path: str) -> Path:
        """Resolve generated report assets with traversal protection."""
        if not job_id:
            raise ValidationError(message="job_id is required.")
        if not relative_path:
            raise ValidationError(message="relative_path is required.")

        base_dir = (self.results_root / self._RESULT_DIR / job_id / "shared_analysis").resolve()
        if not base_dir.exists() or not base_dir.is_dir():
            raise FileNotFoundError(f"Report job not found: {job_id}")

        target_path = (base_dir / relative_path).resolve()
        try:
            target_path.relative_to(base_dir)
        except ValueError as exc:
            raise ValidationError(
                message="Invalid path.",
                details={"relative_path": relative_path},
            ) from exc

        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"Result file not found: {relative_path}")
        return target_path

    def create_archive(self, job_id: str, archive_name: str = "shared_analysis.zip") -> Path:
        """Create a ZIP archive from the shared_analysis directory contents."""
        output_base = (self.results_root / self._RESULT_DIR / job_id / "shared_analysis").resolve()
        if not output_base.exists() or not output_base.is_dir():
            raise FileNotFoundError(f"Report job not found: {job_id}")

        archive_path = output_base / archive_name
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in sorted(output_base.rglob("*")):
                if not file_path.is_file():
                    continue
                if file_path.resolve() == archive_path.resolve():
                    continue
                zip_file.write(file_path, arcname=str(Path(output_base.name) / file_path.relative_to(output_base)))

        return archive_path


_similarity_heatmap_report_service: Optional[SimilarityHeatmapReportService] = None


def get_similarity_heatmap_report_service(
    results_root: Optional[Path] = None,
) -> SimilarityHeatmapReportService:
    """Get or create global similarity heatmap report service."""
    global _similarity_heatmap_report_service

    if results_root is None:
        results_root = Path(__file__).resolve().parents[1] / "data" / "results"
    resolved_root = Path(results_root).resolve()

    if (
        _similarity_heatmap_report_service is None
        or _similarity_heatmap_report_service.results_root != resolved_root
    ):
        _similarity_heatmap_report_service = SimilarityHeatmapReportService(resolved_root)
    return _similarity_heatmap_report_service
