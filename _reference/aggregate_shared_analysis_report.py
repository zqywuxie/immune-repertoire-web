#!/usr/bin/env python3
"""
Aggregate multiple shared_analysis directories into one HTML report.

Usage:
    python aggregate_shared_analysis_report.py --root <root_dir>
"""

from __future__ import annotations

import argparse
import csv
import html
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    import pandas as pd
except Exception:  # pragma: no cover - preview falls back when pandas/openpyxl is unavailable
    pd = None


METRIC_NAMES: Dict[str, str] = {
    "expression_sharing": "Expression Sharing",
    "morisita_horn": "Morisita-Horn Index",
    "cdr3_sharing": "Unique CDR3 Sharing",
    "r2_inner": "R2 Inner",
    "r2_outer": "R2 Outer",
    "sorensen": "Sorensen-Dice Index",
}

# Default hidden table files (suffix match against normalized absolute path).
DEFAULT_EXCLUDED_TABLE_PATH_PATTERNS: Set[str] = {
    "G3_part01_CZYY_LH/output/shared_analysis/CDR3_Shared/TRB/Abundance_Union_Full.xlsx",
    "G3_part01_CZYY_LH/shared_analysis/CDR3_Shared/TRB/Abundance_Union_Full.xlsx",
}


def detect_metric_key(file_stem: str) -> str:
    lower = file_stem.lower()
    for key in METRIC_NAMES:
        if key in lower:
            return key
    return file_stem


def slugify(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "item"


def humanize_token(text: str) -> str:
    cleaned = re.sub(r"[_\-]+", " ", str(text)).strip()
    if not cleaned:
        return ""
    return cleaned.title()


def normalize_path_for_matching(path_text: str) -> str:
    return str(path_text).replace("\\", "/").strip().lower().lstrip("/")


def should_exclude_table_file(file_path: Path, excluded_patterns: Set[str]) -> bool:
    if not excluded_patterns:
        return False
    normalized_abs = normalize_path_for_matching(str(file_path.resolve()))
    for pattern in excluded_patterns:
        normalized_pattern = normalize_path_for_matching(pattern)
        if not normalized_pattern:
            continue
        if normalized_abs == normalized_pattern:
            return True
        if normalized_abs.endswith(normalized_pattern):
            return True
    return False


def rel_href(target_path: Path, report_dir: Path) -> str:
    try:
        return target_path.relative_to(report_dir).as_posix()
    except ValueError:
        return Path(Path().joinpath(Path.cwd(), target_path).resolve()).as_posix()


def discover_modules(scan_root: Path) -> List[Dict[str, Path]]:
    def derive_module_name(shared_dir: Path, fallback_index: int) -> str:
        if shared_dir.parent.name.lower() == "output":
            module_name = shared_dir.parent.parent.name
        else:
            module_name = shared_dir.parent.name
        return module_name or f"module_{fallback_index}"

    modules: List[Dict[str, Path]] = []
    seen: set[Path] = set()

    if scan_root.is_dir() and scan_root.name.lower() == "shared_analysis":
        resolved = scan_root.resolve()
        module_name = derive_module_name(scan_root, 1)
        modules.append({"name": module_name or "module_1", "shared_dir": resolved})
        seen.add(resolved)

    for shared_dir in scan_root.rglob("shared_analysis"):
        if not shared_dir.is_dir():
            continue

        resolved = shared_dir.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        module_name = derive_module_name(shared_dir, len(modules) + 1)
        modules.append({"name": module_name, "shared_dir": resolved})

    modules.sort(key=lambda x: x["name"].lower())
    return modules


def read_csv_preview(csv_path: Path, max_rows: int, max_cols: int, delimiter: Optional[str] = None) -> Tuple[List[str], List[List[str]]]:
    columns: List[str] = []
    rows: List[List[str]] = []

    sep = delimiter
    if sep is None:
        if csv_path.suffix.lower() in {".tsv"}:
            sep = "\t"
        elif csv_path.suffix.lower() in {".txt"}:
            sep = "\t"
        else:
            sep = ","

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter=sep)
            for idx, row in enumerate(reader):
                if idx == 0:
                    columns = row if max_cols <= 0 else row[:max_cols]
                    continue
                if max_rows > 0 and idx > max_rows:
                    break
                rows.append(row if max_cols <= 0 else row[:max_cols])
    except UnicodeDecodeError:
        with csv_path.open("r", encoding="gbk", errors="replace", newline="") as f:
            reader = csv.reader(f, delimiter=sep)
            for idx, row in enumerate(reader):
                if idx == 0:
                    columns = row if max_cols <= 0 else row[:max_cols]
                    continue
                if max_rows > 0 and idx > max_rows:
                    break
                rows.append(row if max_cols <= 0 else row[:max_cols])
    except Exception:
        return [], []

    return columns, rows


def dataframe_to_preview(df: "pd.DataFrame", max_rows: int, max_cols: int) -> Tuple[List[str], List[List[str]]]:
    if df is None:
        return [], []
    if max_cols > 0:
        df_view = df.iloc[:, :max_cols]
    else:
        df_view = df
    cols = [str(c) for c in df_view.columns]
    rows: List[List[str]] = []
    row_iter = df_view.iloc[:max_rows, :].iterrows() if max_rows > 0 else df_view.iterrows()
    for _, row in row_iter:
        rows.append(["" if x is None else str(x) for x in row.tolist()])
    return cols, rows


def read_xlsx_sheet_previews(file_path: Path, max_rows: int, max_cols: int) -> List[Dict]:
    if pd is None:
        return []
    try:
        excel = pd.ExcelFile(file_path)
    except Exception:
        return []

    previews: List[Dict] = []
    for sheet_name in excel.sheet_names:
        try:
            nrows = max_rows if max_rows > 0 else None
            df = pd.read_excel(excel, sheet_name=sheet_name, nrows=nrows)
        except Exception:
            cols, rows = [], []
        else:
            cols, rows = dataframe_to_preview(df, max_rows=max_rows, max_cols=max_cols)
        previews.append({"name": str(sheet_name), "columns": cols, "rows": rows})
    return previews


def read_table_file_previews(file_path: Path, max_rows: int, max_cols: int) -> List[Dict]:
    suffix = file_path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        cols, rows = read_csv_preview(file_path, max_rows=max_rows, max_cols=max_cols)
        return [{"name": file_path.stem, "columns": cols, "rows": rows}]

    if suffix == ".xlsx":
        return read_xlsx_sheet_previews(file_path, max_rows=max_rows, max_cols=max_cols)

    return []


def resolve_heatmap_image_path(metric_csv_path: Path, metric_root: Path, heatmap_root: Path, metric_key: str) -> Optional[Path]:
    rel_csv = metric_csv_path.relative_to(metric_root)
    candidates = [
        heatmap_root / rel_csv.with_suffix(".png"),
        heatmap_root / rel_csv.parent / rel_csv.name.replace("_heatmap.csv", "_heatmap.png"),
        heatmap_root / rel_csv.parent / f"{metric_key}_heatmap.png",
        heatmap_root / rel_csv.parent / f"{metric_key}.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    search_dir = heatmap_root / rel_csv.parent
    if search_dir.exists():
        matches = sorted(search_dir.glob(f"*{metric_key}*.png"))
        if matches:
            return matches[0]
    return None


def build_module_sections(shared_dir: Path, report_dir: Path, max_rows: int, max_cols: int) -> List[Dict]:
    metric_root = shared_dir / "metric"
    heatmap_root = shared_dir / "heatmap"
    if not metric_root.exists():
        return []

    section_map: Dict[str, List[Dict]] = {}
    for csv_path in sorted(metric_root.rglob("*.csv")):
        rel_parent = csv_path.parent.relative_to(metric_root).as_posix()
        section_key = rel_parent if rel_parent != "." else "overview"
        metric_key = detect_metric_key(csv_path.stem)
        metric_label = METRIC_NAMES.get(metric_key, csv_path.stem)

        image_path = None
        if heatmap_root.exists():
            image_path = resolve_heatmap_image_path(
                metric_csv_path=csv_path,
                metric_root=metric_root,
                heatmap_root=heatmap_root,
                metric_key=metric_key,
            )

        section_map.setdefault(section_key, []).append(
            {
                "metric_key": metric_key,
                "metric_label": metric_label,
                "image_href": rel_href(image_path, report_dir) if image_path else "",
                "csv_href": rel_href(csv_path, report_dir),
            }
        )

    sections: List[Dict] = []
    for section_key in sorted(section_map.keys()):
        section_title = "Overview" if section_key == "overview" else section_key.replace("/", " / ")
        sections.append(
            {
                "id": slugify(section_key),
                "title": section_title,
                "entries": section_map[section_key],
            }
        )
    return sections


def build_cdr3_table_entries(
    shared_dir: Path,
    report_dir: Path,
    max_rows: int,
    max_cols: int,
    excluded_table_patterns: Optional[Set[str]] = None,
) -> List[Dict]:
    cdr3_root = shared_dir / "CDR3_Shared"
    if not cdr3_root.exists():
        return []

    excluded_patterns = set(DEFAULT_EXCLUDED_TABLE_PATH_PATTERNS)
    if excluded_table_patterns:
        excluded_patterns.update(excluded_table_patterns)

    files: List[Dict] = []
    for file_path in sorted(cdr3_root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".xlsx", ".csv", ".tsv", ".txt"}:
            continue
        if should_exclude_table_file(file_path, excluded_patterns):
            continue
        sheets = read_table_file_previews(file_path, max_rows=max_rows, max_cols=max_cols)
        if not sheets:
            sheets = [{"name": "Sheet1", "columns": [], "rows": []}]
        rel = file_path.relative_to(cdr3_root).as_posix()
        rel_parts = Path(rel).parts
        chain = rel_parts[0] if len(rel_parts) > 1 else ""
        target = chain if chain else "overview"
        target_label = chain if chain else "Overview"
        file_type = file_path.stem
        file_type_label = humanize_token(file_path.stem)
        files.append(
            {
                "name": file_path.name,
                "href": rel_href(file_path, report_dir),
                "rel": rel,
                "mode": "cdr3_shared",
                "mode_label": "CDR3 Shared Analysis",
                "target": target,
                "target_label": target_label,
                "file_type": file_type,
                "file_type_label": file_type_label or file_path.stem,
                "chain": chain,
                "sheets": sheets,
            }
        )
    return files


def render_table_html(columns: List[str], rows: List[List[str]]) -> str:
    if not columns:
        return "<div class='empty-note'>No table preview available.</div>"

    head_cells = "<th>序号</th>" + "".join(f"<th>{html.escape(str(col))}</th>" for col in columns)
    body_rows: List[str] = []
    for idx, row in enumerate(rows, start=1):
        padded = row + [""] * (len(columns) - len(row))
        row_html = f"<td>{idx}</td>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in padded[: len(columns)])
        body_rows.append(f"<tr>{row_html}</tr>")

    return (
        "<div class='table-wrap'>"
        "<table>"
        f"<thead><tr>{head_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
        "</div>"
    )


def render_report_html(
    title: str,
    modules: List[Dict],
    report_dir: Path,
    include_tables: bool = True,
) -> str:
    option_html: List[str] = []
    panels_html: List[str] = []

    for idx, module in enumerate(modules):
        module_name = str(module["name"])
        shared_dir = Path(module["shared_dir"])
        module_id = f"module_{idx + 1}"
        module_active_cls = " active" if idx == 0 else ""

        sections = module["sections"]
        cdr3_tables = module.get("cdr3_table_entries", []) if include_tables else []

        option_html.append(f"<option value='{html.escape(module_id)}'>{html.escape(module_name)}</option>")

        heatmap_blocks: List[str] = []
        for section in sections:
            section_id = f"{module_id}_{section['id']}"
            entries = section.get("entries", [])
            tab_btns: List[str] = []
            image_panels: List[str] = []

            for m_idx, entry in enumerate(entries):
                metric_panel_id = f"{section_id}_metric_{m_idx + 1}"
                metric_active = " active" if m_idx == 0 else ""
                tab_btns.append(
                    (
                        f"<button class='pill-btn{metric_active}' data-target='{html.escape(metric_panel_id)}'>"
                        f"{html.escape(entry['metric_label'])}"
                        "</button>"
                    )
                )

                image_html = (
                    f"<img src='{html.escape(entry['image_href'])}' alt='{html.escape(entry['metric_label'])}' />"
                    if entry["image_href"]
                    else "<div class='empty-note'>No image found for this metric.</div>"
                )

                links_html = (
                    f"<a href='{html.escape(entry['csv_href'])}' target='_blank' rel='noopener'>Open CSV</a>"
                    + (
                        f"<a href='{html.escape(entry['image_href'])}' target='_blank' rel='noopener'>Open Image</a>"
                        if entry["image_href"]
                        else ""
                    )
                )
                image_panels.append(
                    (
                        f"<div id='{html.escape(metric_panel_id)}' class='sub-content{metric_active}'>"
                        f"<div class='inline-tools'>{links_html}</div>"
                        f"<div class='preview'>{image_html}</div>"
                        "</div>"
                    )
                )

            heatmap_blocks.append(
                (
                    f"<section id='{html.escape(section_id)}' class='report-section'>"
                    f"<h2>{html.escape(section['title'])}</h2>"
                    f"<div class='sub-tabs'>{''.join(tab_btns)}</div>"
                    f"{''.join(image_panels)}"
                    "</section>"
                )
            )

        if not heatmap_blocks:
            heatmap_blocks = ["<div class='empty-note'>No heatmap entries.</div>"]

        table_block = "<div class='empty-note'>No table files found in CDR3_Shared.</div>"
        if include_tables and cdr3_tables:
            table_entry_panels: List[str] = []
            first_entry_set = False
            for t_idx, table_item in enumerate(cdr3_tables):
                sheets = table_item.get("sheets", [])
                for s_idx, sheet_item in enumerate(sheets):
                    sheet_name = str(sheet_item.get("name", f"Sheet{s_idx + 1}"))
                    sheet_panel_id = f"{module_id}_table_entry_{t_idx + 1}_{s_idx + 1}_{slugify(sheet_name)}"
                    sheet_active_cls = " active" if not first_entry_set else ""
                    first_entry_set = True
                    table_html = render_table_html(sheet_item.get("columns", []), sheet_item.get("rows", []))
                    row_count = len(sheet_item.get("rows", []))
                    col_count = len(sheet_item.get("columns", []))
                    chain = str(table_item.get("chain", ""))
                    target = str(table_item.get("target", ""))
                    mode = str(table_item.get("mode", "cdr3_shared"))
                    file_type = str(table_item.get("file_type", table_item.get("name", "")))
                    mode_label = str(table_item.get("mode_label", "CDR3 Shared Analysis"))
                    target_label = str(table_item.get("target_label", target or "Overview"))
                    file_type_label = str(table_item.get("file_type_label", file_type))
                    shape = f"{row_count} x {col_count}"
                    meta_text = (
                        f"{mode_label} | Target: {target_label} | File Type: {file_type_label} | "
                        f"Chain: {chain or 'All'} | Sheet: {sheet_name} | Shape: {shape}"
                    )
                    table_entry_panels.append(
                        (
                            f"<div id='{html.escape(sheet_panel_id)}' class='table-entry-pane{sheet_active_cls}' "
                            f"data-mode='{html.escape(mode)}' "
                            f"data-mode-label='{html.escape(mode_label)}' "
                            f"data-target='{html.escape(target)}' "
                            f"data-target-label='{html.escape(target_label)}' "
                            f"data-file-type='{html.escape(file_type)}' "
                            f"data-file-type-label='{html.escape(file_type_label)}' "
                            f"data-chain='{html.escape(chain)}' "
                            f"data-sheet='{html.escape(sheet_name)}' "
                            f"data-source='{html.escape(table_item['rel'])}' "
                            f"data-shape='{html.escape(shape)}' "
                            f"data-meta='{html.escape(meta_text)}'>"
                            "<div class='inline-tools'>"
                            f"<a href='{html.escape(table_item['href'])}' target='_blank' rel='noopener'>Open Table File</a>"
                            f"<span class='hint'>{html.escape(table_item['rel'])}</span>"
                            "</div>"
                            f"{table_html}"
                            "</div>"
                        )
                    )
            table_block = (
                "<section class='report-section table-control-panel'>"
                "<h2>Tables</h2>"
                "<div class='table-controls'>"
                "<label>Table Group <select class='tb-mode'></select></label>"
                "<label>Target <select class='tb-target'></select></label>"
                "<label>File Type <select class='tb-filetype'></select></label>"
                "<label>Chain <select class='tb-chain'></select></label>"
                "<label>Sheet <select class='tb-sheet'></select></label>"
                "</div>"
                "<div class='card tb-card'>"
                "<div class='meta tb-meta'></div>"
                f"{''.join(table_entry_panels)}"
                "</div>"
                "<div class='empty-note tb-empty' style='display:none;'>No table under current filters.</div>"
                "</section>"
            )

        if include_tables:
            panels_html.append(
                (
                    f"<section id='{html.escape(module_id)}' class='main-content{module_active_cls}'>"
                    "<div class='panel'>"
                    "<div class='main-tabs'>"
                    f"<button class='tab-btn active' data-target='{module_id}_heatmap'>Heatmap</button>"
                    f"<button class='tab-btn' data-target='{module_id}_table'>Table</button>"
                    "</div>"
                    f"<div id='{module_id}_heatmap' class='main-pane active'>{''.join(heatmap_blocks)}</div>"
                    f"<div id='{module_id}_table' class='main-pane'>{table_block}</div>"
                    "</div>"
                    "</section>"
                )
            )
        else:
            panels_html.append(
                (
                    f"<section id='{html.escape(module_id)}' class='main-content{module_active_cls}'>"
                    "<div class='panel'>"
                    f"<div id='{module_id}_heatmap' class='main-pane active'>{''.join(heatmap_blocks)}</div>"
                    "</div>"
                    "</section>"
                )
            )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #f1f5f9;
      --card: #ffffff;
      --text: #17212b;
      --muted: #5a6878;
      --line: #d5dee7;
      --primary: #16537e;
      --shadow: 0 12px 28px rgba(27, 43, 62, 0.08);
      --chip: #edf4fb;
      --chip-border: #c7daee;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--text);
      font-family: "IBM Plex Sans", "Noto Sans", sans-serif;
      min-height: 100vh;
      background:
        radial-gradient(circle at 0 0, #e9f2fb 0%, transparent 34%),
        radial-gradient(circle at 100% 0, #f8fafc 0%, transparent 30%),
        var(--bg);
    }}
    .container {{
      width: min(1240px, 94vw);
      margin: 24px auto 30px;
    }}
    .header {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--card);
      box-shadow: var(--shadow);
      padding: 16px 18px;
      margin-bottom: 16px;
      position: relative;
    }}
    .title {{
      margin: 0 0 6px;
      font-size: 1.36rem;
      font-weight: 700;
      letter-spacing: 0.01em;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.5;
    }}
    .selector {{
      position: absolute;
      top: 16px;
      right: 18px;
      display: flex;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 0.85rem;
    }}
    .selector select {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
      padding: 8px 10px;
      font-size: 0.92rem;
      min-width: 260px;
    }}
    .main-content {{ display: none; }}
    .main-content.active {{ display: block; }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--card);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .main-tabs,
    .sub-tabs {{
      display: flex;
      gap: 8px;
      padding: 10px 12px 0;
      border-bottom: 1px solid var(--line);
      background: #fbfdff;
      flex-wrap: wrap;
    }}
    .sub-tabs {{
      padding-top: 0;
      border-bottom: none;
      margin-bottom: 10px;
      background: transparent;
    }}
    .tab-btn {{
      border: 1px solid var(--line);
      border-bottom: none;
      border-radius: 10px 10px 0 0;
      background: #f4f8fc;
      color: var(--muted);
      font-weight: 600;
      padding: 7px 14px;
      cursor: pointer;
    }}
    .tab-btn.active {{
      background: var(--card);
      color: var(--primary);
      border-color: var(--line);
    }}
    .main-pane {{
      display: none;
      padding: 12px;
    }}
    .main-pane.active {{ display: block; }}
    .meta {{
      color: var(--muted);
      font-size: 0.84rem;
      margin-bottom: 8px;
      word-break: break-word;
    }}
    .report-section {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--card);
      box-shadow: var(--shadow);
      padding: 12px;
      margin-bottom: 12px;
    }}
    .report-section h2 {{
      margin: 0 0 10px;
      font-size: 1.06rem;
    }}
    .sub-tabs {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }}
    .pill-btn {{
      border: 1px solid var(--chip-border);
      border-radius: 999px;
      background: var(--chip);
      color: #315777;
      font-weight: 600;
      padding: 6px 12px;
      cursor: pointer;
    }}
    .pill-btn.active {{
      background: #dcecff;
      border-color: #9dc0e4;
      color: #0f3f65;
    }}
    .table-controls {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 10px;
      align-items: end;
    }}
    .table-controls label {{
      color: var(--muted);
      font-size: 0.84rem;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .table-controls select {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
      padding: 6px 8px;
      min-width: 180px;
    }}
    .sub-content {{ display: none; }}
    .sub-content.active {{ display: block; }}
    .table-entry-pane {{ display: none; }}
    .table-entry-pane.active {{ display: block; }}
    .inline-tools {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 8px;
      font-size: 0.84rem;
      align-items: center;
    }}
    .inline-tools a {{
      color: var(--primary);
      text-decoration: none;
    }}
    .inline-tools a:hover {{
      text-decoration: underline;
    }}
    .inline-tools .hint {{
      margin-left: auto;
      color: var(--muted);
      font-size: 0.8rem;
      word-break: break-all;
    }}
    .preview {{
      min-height: 240px;
      border: 1px solid #dbe5ef;
      border-radius: 10px;
      background: linear-gradient(145deg, #f7fbff 0%, #f1f6fb 100%);
      padding: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 10px;
    }}
    .preview img {{
      width: min(100%, 920px);
      max-height: 500px;
      object-fit: contain;
      border-radius: 6px;
      border: 1px solid #d5dfeb;
      background: #fff;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fff;
      padding: 10px;
    }}
    .table-wrap {{
      border: 1px solid var(--line);
      border-radius: 10px;
      max-height: 560px;
      overflow: auto;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 12px;
    }}
    th, td {{
      border: 1px solid #e2e8f0;
      padding: 4px 6px;
      white-space: nowrap;
      text-align: center;
    }}
    th {{
      background: #f1f5f9;
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    .empty-note {{
      color: var(--muted);
      font-size: 0.9rem;
      text-align: center;
      padding: 16px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header class="header">
      <h1 class="title">{html.escape(title)}</h1>
      <div class="selector">
        <label for="moduleSelector">Directory</label>
        <select id="moduleSelector">
          {''.join(option_html)}
        </select>
      </div>
    </header>
    {''.join(panels_html)}
  </div>
  <script>
    (function() {{
      const moduleSelector = document.getElementById('moduleSelector');
      const modulePanels = document.querySelectorAll('.main-content');
      const activateModule = (id) => {{
        modulePanels.forEach((panel) => panel.classList.toggle('active', panel.id === id));
      }};
      if (moduleSelector) {{
        activateModule(moduleSelector.value);
        moduleSelector.addEventListener('change', () => activateModule(moduleSelector.value));
      }}

      document.querySelectorAll('.main-content').forEach((modulePanel) => {{
        const tabButtons = modulePanel.querySelectorAll('.main-tabs .tab-btn');
        const tabPanes = modulePanel.querySelectorAll('.main-pane');
        tabButtons.forEach((btn) => {{
          btn.addEventListener('click', () => {{
            const target = btn.getAttribute('data-target');
            tabButtons.forEach((b) => b.classList.remove('active'));
            tabPanes.forEach((p) => p.classList.remove('active'));
            btn.classList.add('active');
            const pane = modulePanel.querySelector('#' + CSS.escape(target));
            if (pane) pane.classList.add('active');
          }});
        }});
      }});

      document.querySelectorAll('.report-section').forEach((section) => {{
        const buttons = section.querySelectorAll('.pill-btn');
        const panes = section.querySelectorAll('.sub-content');
        buttons.forEach((btn) => {{
          btn.addEventListener('click', () => {{
            const target = btn.getAttribute('data-target');
            buttons.forEach((b) => b.classList.remove('active'));
            panes.forEach((p) => p.classList.remove('active'));
            btn.classList.add('active');
            const pane = section.querySelector('#' + CSS.escape(target));
            if (pane) pane.classList.add('active');
          }});
        }});
      }});

      const uniqueOptions = (items, valueKey, labelKey) => {{
        const mapping = new Map();
        items.forEach((item) => {{
          const value = item[valueKey] || '';
          if (!mapping.has(value)) {{
            const label = item[labelKey] || value || 'All';
            mapping.set(value, label);
          }}
        }});
        return Array.from(mapping.entries()).map(([value, label]) => ({{ value, label }}));
      }};

      const setSelectOptions = (selectEl, options, preferredValue) => {{
        const previous = preferredValue !== undefined ? preferredValue : selectEl.value;
        selectEl.innerHTML = options
          .map((opt) => `<option value="${{String(opt.value).replace(/"/g, '&quot;')}}">${{opt.label}}</option>`)
          .join('');
        if (!options.length) return;
        const hasPrevious = options.some((opt) => opt.value === previous);
        selectEl.value = hasPrevious ? previous : options[0].value;
      }};

      document.querySelectorAll('.table-control-panel').forEach((tablePanel) => {{
        const modeSel = tablePanel.querySelector('.tb-mode');
        const targetSel = tablePanel.querySelector('.tb-target');
        const fileTypeSel = tablePanel.querySelector('.tb-filetype');
        const chainSel = tablePanel.querySelector('.tb-chain');
        const sheetSel = tablePanel.querySelector('.tb-sheet');
        const metaEl = tablePanel.querySelector('.tb-meta');
        const cardEl = tablePanel.querySelector('.tb-card');
        const emptyEl = tablePanel.querySelector('.tb-empty');
        const panes = Array.from(tablePanel.querySelectorAll('.table-entry-pane'));
        if (!modeSel || !targetSel || !fileTypeSel || !chainSel || !sheetSel || panes.length === 0) return;

        const entries = panes.map((pane) => ({{
          pane,
          mode: pane.dataset.mode || '',
          modeLabel: pane.dataset.modeLabel || pane.dataset.mode || '',
          target: pane.dataset.target || '',
          targetLabel: pane.dataset.targetLabel || pane.dataset.target || '',
          fileType: pane.dataset.fileType || '',
          fileTypeLabel: pane.dataset.fileTypeLabel || pane.dataset.fileType || '',
          chain: pane.dataset.chain || '',
          sheet: pane.dataset.sheet || '',
          meta: pane.dataset.meta || '',
        }}));

        const renderSelected = () => {{
          const selected = entries.find((entry) => {{
            const chainMatch = chainSel.value === '__all__' || entry.chain === chainSel.value;
            return (
              entry.mode === modeSel.value &&
              entry.target === targetSel.value &&
              entry.fileType === fileTypeSel.value &&
              chainMatch &&
              entry.sheet === sheetSel.value
            );
          }});

          panes.forEach((pane) => pane.classList.remove('active'));
          if (!selected) {{
            cardEl.style.display = 'none';
            emptyEl.style.display = 'block';
            metaEl.textContent = '';
            return;
          }}

          selected.pane.classList.add('active');
          cardEl.style.display = 'block';
          emptyEl.style.display = 'none';
          metaEl.textContent = selected.meta;
        }};

        const refreshSheets = () => {{
          const candidates = entries.filter((entry) => {{
            const chainMatch = chainSel.value === '__all__' || entry.chain === chainSel.value;
            return (
              entry.mode === modeSel.value &&
              entry.target === targetSel.value &&
              entry.fileType === fileTypeSel.value &&
              chainMatch
            );
          }});
          const options = uniqueOptions(candidates, 'sheet', 'sheet');
          setSelectOptions(sheetSel, options);
          renderSelected();
        }};

        const refreshChains = () => {{
          const candidates = entries.filter((entry) => (
            entry.mode === modeSel.value &&
            entry.target === targetSel.value &&
            entry.fileType === fileTypeSel.value
          ));
          const chainOptions = uniqueOptions(candidates.filter((entry) => entry.chain), 'chain', 'chain');
          if (chainOptions.length === 0) {{
            setSelectOptions(chainSel, [{{ value: '__all__', label: 'All' }}], '__all__');
          }} else {{
            setSelectOptions(chainSel, chainOptions);
          }}
          refreshSheets();
        }};

        const refreshFileTypes = () => {{
          const candidates = entries.filter((entry) => (
            entry.mode === modeSel.value &&
            entry.target === targetSel.value
          ));
          const options = uniqueOptions(candidates, 'fileType', 'fileTypeLabel');
          setSelectOptions(fileTypeSel, options);
          refreshChains();
        }};

        const refreshTargets = () => {{
          const candidates = entries.filter((entry) => entry.mode === modeSel.value);
          const options = uniqueOptions(candidates, 'target', 'targetLabel');
          setSelectOptions(targetSel, options);
          refreshFileTypes();
        }};

        const refreshModes = () => {{
          const options = uniqueOptions(entries, 'mode', 'modeLabel');
          setSelectOptions(modeSel, options);
          refreshTargets();
        }};

        modeSel.addEventListener('change', refreshTargets);
        targetSel.addEventListener('change', refreshFileTypes);
        fileTypeSel.addEventListener('change', refreshChains);
        chainSel.addEventListener('change', refreshSheets);
        sheetSel.addEventListener('change', renderSelected);
        refreshModes();
      }});
    }})();
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate shared_analysis directories into one HTML report.",
    )
    parser.add_argument("--root", required=True, help="Root directory that contains module subdirectories.")
    parser.add_argument(
        "--output",
        default=None,
        help="Output HTML path (default: <root>/pipeline_comparison_report.html).",
    )
    parser.add_argument("--title", default="Pipeline Comparison Report", help="Report title.")
    parser.add_argument("--max-rows", type=int, default=0, help="Max table preview rows (0 means no limit).")
    parser.add_argument("--max-cols", type=int, default=0, help="Max table preview columns (0 means no limit).")
    parser.add_argument(
        "--exclude-table",
        action="append",
        default=[],
        help="Exclude table file by absolute path or relative suffix (can be repeated).",
    )
    parser.add_argument(
        "--figures-only",
        action="store_true",
        help="Only render heatmap/image sections and skip all table previews.",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"[ERROR] root directory not found: {root}")
        return 1

    output_path = Path(args.output).expanduser().resolve() if args.output else root / "pipeline_comparison_report.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    modules = discover_modules(root)
    if not modules:
        print(f"[ERROR] no shared_analysis modules found under: {root}")
        return 1

    report_dir = output_path.parent.resolve()
    excluded_table_patterns = set(DEFAULT_EXCLUDED_TABLE_PATH_PATTERNS)
    excluded_table_patterns.update({p for p in args.exclude_table if p})
    include_tables = not args.figures_only
    for module in modules:
        shared_dir = Path(module["shared_dir"])
        module["sections"] = build_module_sections(shared_dir, report_dir, args.max_rows, args.max_cols)
        if include_tables:
            module["cdr3_table_entries"] = build_cdr3_table_entries(
                shared_dir=shared_dir,
                report_dir=report_dir,
                max_rows=args.max_rows,
                max_cols=args.max_cols,
                excluded_table_patterns=excluded_table_patterns,
            )
        else:
            module["cdr3_table_entries"] = []

    if include_tables:
        modules = [m for m in modules if m["sections"] or m["cdr3_table_entries"]]
    else:
        modules = [m for m in modules if m["sections"]]
    if not modules:
        if include_tables:
            print(f"[ERROR] modules found but no renderable heatmap/table content under: {root}")
        else:
            print(f"[ERROR] modules found but no renderable heatmap/image content under: {root}")
        return 1

    html_text = render_report_html(
        title=args.title,
        modules=modules,
        report_dir=report_dir,
        include_tables=include_tables,
    )
    output_path.write_text(html_text, encoding="utf-8")

    print(f"[OK] modules: {len(modules)}")
    print(f"[OK] report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
