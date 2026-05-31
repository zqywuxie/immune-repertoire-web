from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any


HEADER_ALIASES = {
    "cdr3": [
        "cdr3(pep)",
        "cdr3_pep",
        "cdr3pep",
        "cdr3aa",
        "cdr3_aa",
        "cdr3",
        "aa_cdr3",
    ],
    "copy": [
        "copy",
        "copies",
        "count",
        "clonecount",
        "clone_count",
        "readcount",
        "read_count",
        "reads",
        "umis",
        "umi",
    ],
    "v": ["v", "vgene", "v_gene", "bestvgene", "v_call"],
    "d": ["d", "dgene", "d_gene", "bestdgene", "d_call"],
    "j": ["j", "jgene", "j_gene", "bestjgene", "j_call"],
    "c": ["c", "cgene", "c_gene", "constant", "constant_gene", "isotype"],
    "chain": ["chain", "chain_type", "receptor_chain", "locus"],
    "cell_type": ["cell_type", "celltype", "lymphocyte_type", "receptor_type"],
    "joined_seq": ["joinedseq", "joined_seq", "joinedsequence", "joined_sequence"],
}

CHAIN_CELL_MAP = {
    "IGH": "B cell",
    "IGK": "B cell",
    "IGL": "B cell",
    "TRA": "T cell",
    "TRB": "T cell",
    "TRD": "T cell",
    "TRG": "T cell",
}

D3_CDN_URL = "https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"


def normalize_header(value: str) -> str:
    value = value.strip().lower()
    return re.sub(r"[\s\-_./]+", "", value)


def open_text_file(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def detect_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:

        class DefaultDialect(csv.excel):
            delimiter = ","

        return DefaultDialect()


def detect_columns(
    fieldnames: list[str], overrides: dict[str, str | None]
) -> dict[str, str | None]:
    normalized = {normalize_header(name): name for name in fieldnames}
    detected: dict[str, str | None] = {}
    for logical_name, aliases in HEADER_ALIASES.items():
        override = overrides.get(logical_name)
        if override:
            if override not in fieldnames:
                raise ValueError(f"指定列不存在: {logical_name}={override}")
            detected[logical_name] = override
            continue
        detected[logical_name] = None
        for alias in aliases:
            match = normalized.get(normalize_header(alias))
            if match:
                detected[logical_name] = match
                break
    return detected


def parse_copy(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def clean_text(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def infer_chain(*values: str) -> str:
    joined = " ".join(value for value in values if value).upper()
    for prefix in ("IGH", "IGK", "IGL", "TRA", "TRB", "TRD", "TRG"):
        if prefix in joined:
            return prefix
    return "Unknown"


def infer_cell_type(raw_value: str | None, chain: str) -> str:
    if raw_value:
        lowered = str(raw_value).strip().lower()
        if lowered in {"b", "bcell", "b-cell", "b cell"}:
            return "B cell"
        if lowered in {"t", "tcell", "t-cell", "t cell"}:
            return "T cell"
    return CHAIN_CELL_MAP.get(chain, "Unknown")


def vj_pair_name(v: str, j: str) -> str:
    if v and j:
        return f"{v} | {j}"
    if v:
        return f"{v} | J?"
    if j:
        return f"V? | {j}"
    return "V? | J?"


def make_title(path: Path, title: str | None) -> str:
    return title or f"{path.stem} clonotype tetris map"


def _normalize_copy_value(copy_value: float) -> int | float:
    return int(copy_value) if math.isclose(copy_value, round(copy_value)) else round(copy_value, 4)


def read_repertoire_rows(
    path: Path, columns: dict[str, str | None]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stats = {
        "input_rows": 0,
        "used_rows": 0,
        "skipped_missing_copy": 0,
        "skipped_missing_cdr3": 0,
    }

    with open_text_file(path) as handle:
        sample = handle.read(4096)
        handle.seek(0)
        reader = csv.DictReader(handle, dialect=detect_dialect(sample))
        if not reader.fieldnames:
            raise ValueError("未检测到表头。")

        for row in reader:
            stats["input_rows"] += 1
            cdr3 = clean_text(
                row.get(columns["cdr3"] or "", "") if columns["cdr3"] else ""
            )
            if not cdr3:
                stats["skipped_missing_cdr3"] += 1
                continue

            copy_value = parse_copy(
                row.get(columns["copy"] or "", "") if columns["copy"] else ""
            )
            if copy_value is None or copy_value <= 0:
                stats["skipped_missing_copy"] += 1
                continue

            v = (
                clean_text(row.get(columns["v"] or "", "") if columns["v"] else "")
                or "V?"
            )
            d = clean_text(row.get(columns["d"] or "", "") if columns.get("d") else "")
            j = (
                clean_text(row.get(columns["j"] or "", "") if columns["j"] else "")
                or "J?"
            )
            c = clean_text(row.get(columns["c"] or "", "") if columns["c"] else "")
            joined_seq = clean_text(
                row.get(columns["joined_seq"] or "", "") if columns.get("joined_seq") else ""
            )
            raw_chain = clean_text(
                row.get(columns["chain"] or "", "") if columns["chain"] else ""
            )
            raw_cell_type = clean_text(
                row.get(columns["cell_type"] or "", "") if columns["cell_type"] else ""
            )

            chain = infer_chain(raw_chain, c, v, j)
            cell_type = infer_cell_type(raw_cell_type, chain)
            rows.append(
                {
                    "cdr3": cdr3,
                    "copy": copy_value,
                    "v": v,
                    "d": d,
                    "j": j,
                    "c": c,
                    "joined_seq": joined_seq,
                    "chain": chain,
                    "cell_type": cell_type,
                    "row_count": 1,
                    "source_order": stats["input_rows"],
                }
            )
            stats["used_rows"] += 1

    aggregated: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("v") or "V?"),
            str(row.get("j") or "J?"),
            str(row.get("cdr3") or ""),
        )
        if key not in aggregated:
            aggregated[key] = {
                **row,
                "copy": 0.0,
                "row_count": 0,
                "source_order": row.get("source_order", 0),
            }
        target = aggregated[key]
        target["copy"] += float(row.get("copy", 0) or 0)
        target["row_count"] += int(row.get("row_count", 0) or 0)
        target["source_order"] = min(
            int(target.get("source_order", 0) or 0),
            int(row.get("source_order", 0) or 0),
        )
        for optional_key in ("d", "c", "joined_seq", "chain", "cell_type"):
            if row.get(optional_key) and not target.get(optional_key):
                target[optional_key] = row[optional_key]

    rows = list(aggregated.values())
    rows.sort(
        key=lambda item: (
            -item["copy"],
            item["v"],
            item["j"],
            item["cdr3"],
            item.get("source_order", 0),
        )
    )
    total_copy = sum(float(item["copy"]) for item in rows)
    for item in rows:
        copy_value = float(item["copy"])
        item["copy"] = _normalize_copy_value(copy_value)
        item["frequency"] = (copy_value / total_copy) if total_copy else 0.0
        item["vj_pair"] = vj_pair_name(item["v"], item["j"])
        item["clone_id"] = f"{item['v']}|{item['j']}|{item['cdr3']}"

    summary = {"total_clones": len(rows), "total_copy": total_copy, **stats}
    return rows, summary


def read_repertoire(
    path: Path, columns: dict[str, str | None]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return read_repertoire_rows(path, columns)


def escape_html_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def load_d3_script_tag() -> str:
    try:
        with urllib.request.urlopen(D3_CDN_URL, timeout=20) as response:
            script_text = response.read().decode("utf-8")
        return f"<script>{script_text}</script>"
    except Exception:
        return f'<script src="{D3_CDN_URL}"></script>'


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>__PAGE_TITLE__</title>
  __D3_SCRIPT__
  <style>
    :root{
      --bg:#f2efe9;
      --bg-deep:#e4e0d8;
      --panel:rgba(251,249,245,.94);
      --line:rgba(42,49,56,.1);
      --ink:#1c242b;
      --muted:#5c6770;
      --accent:#2d6c8d;
      --shadow:0 18px 54px rgba(28,36,43,.12);
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
      color:var(--ink);
      background:
        radial-gradient(circle at top left,rgba(125,145,162,.16),transparent 34%),
        radial-gradient(circle at 82% 16%,rgba(75,122,150,.12),transparent 28%),
        linear-gradient(135deg,var(--bg),var(--bg-deep));
    }
    body.panel-mode{background:#ffffff}
    .page{padding:22px}
    .hero,.layout{display:grid;gap:16px}
    .hero{grid-template-columns:1.45fr 1fr;margin-bottom:16px}
    .layout{grid-template-columns:minmax(0,1.45fr) 420px;align-items:start}
    .card{
      background:var(--panel);
      border:1px solid var(--line);
      border-radius:20px;
      box-shadow:var(--shadow);
      backdrop-filter:blur(10px);
    }
    .intro{padding:24px 26px}
    .intro h1{margin:0 0 10px;font-size:30px;line-height:1.04;letter-spacing:-.035em}
    .intro p{margin:0;color:var(--muted);font-size:14px;line-height:1.6}
    .meta,.legend{display:flex;flex-wrap:wrap;gap:8px}
    .meta{margin-top:15px}
    .pill,.legend-item{
      display:inline-flex;
      align-items:center;
      gap:8px;
      padding:7px 12px;
      border-radius:999px;
      background:rgba(255,255,255,.8);
      border:1px solid rgba(18,15,12,.08);
      font-size:12px;
      color:#41515e;
    }
    .controls,.chart-panel,.table-panel{padding:18px}
    .controls{display:grid;gap:14px}
    .controls h2,.panel-head h2{margin:0;font-size:16px}
    .control-row{display:grid;gap:8px}
    .control-row label{font-size:13px;font-weight:600}
    .control-inline{display:grid;grid-template-columns:1fr 120px;gap:10px;align-items:center}
    input[type=range]{width:100%;accent-color:var(--accent)}
    input[type=number]{
      width:100%;
      padding:10px 12px;
      border-radius:12px;
      border:1px solid rgba(20,17,14,.14);
      background:rgba(255,255,255,.88);
      font:inherit;
    }
    .summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
    .stat{
      background:rgba(255,255,255,.82);
      border:1px solid rgba(20,17,14,.08);
      border-radius:15px;
      padding:12px;
    }
    .stat .label{display:block;font-size:12px;color:var(--muted);margin-bottom:6px}
    .stat .value{display:block;font-size:20px;font-weight:700;letter-spacing:-.02em}
    .panel-head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin-bottom:12px}
    .panel-head p{margin:0;color:var(--muted);font-size:12px}
    .chart-panel .panel-head{display:none}
    #treemap{
      width:100%;
      aspect-ratio:1 / 1;
      height:auto;
      display:block;
      background:#ffffff;
      border:1px solid rgba(52,67,80,.08);
      border-radius:18px;
    }
    .table-wrap{
      max-height:760px;
      overflow:auto;
      border:1px solid rgba(20,17,14,.08);
      border-radius:16px;
      background:rgba(255,255,255,.84);
    }
    table{width:100%;border-collapse:collapse;font-size:12px}
    thead th{
      position:sticky;
      top:0;
      z-index:1;
      text-align:left;
      padding:10px 8px;
      background:#f4eddf;
      border-bottom:1px solid rgba(20,17,14,.08);
      white-space:nowrap;
    }
    tbody td{padding:9px 8px;border-bottom:1px solid rgba(20,17,14,.06);vertical-align:top}
    tbody tr:hover{background:rgba(45,108,141,.06)}
    .cdr3{font-family:Consolas,"SFMono-Regular",monospace;word-break:break-all}
    .shape-badge{
      display:inline-flex;
      min-width:28px;
      justify-content:center;
      padding:3px 7px;
      border-radius:999px;
      font-size:11px;
      font-weight:700;
      background:rgba(17,15,13,.08);
    }
    .legend-shape{width:34px;height:22px;display:block}
    .tooltip{
      position:fixed;
      z-index:20;
      pointer-events:none;
      min-width:220px;
      max-width:360px;
      padding:12px 14px;
      border-radius:14px;
      color:#fffdf8;
      background:rgba(18,17,14,.94);
      box-shadow:0 22px 60px rgba(0,0,0,.28);
      border:1px solid rgba(255,255,255,.1);
      opacity:0;
      transform:translateY(6px);
      transition:opacity .12s ease,transform .12s ease;
    }
    .tooltip.visible{opacity:1;transform:translateY(0)}
    .tooltip h3{
      margin:0 0 8px;
      font-size:14px;
      font-family:Consolas,"SFMono-Regular",monospace;
      word-break:break-all;
    }
    .tip-grid{display:grid;grid-template-columns:auto 1fr;gap:5px 12px;font-size:12px;line-height:1.45}
    .tip-grid dt{color:rgba(255,255,255,.72)}
    .tip-grid dd{margin:0}
    .empty{font-size:18px;font-weight:700;fill:#6d655c}
    body.panel-mode .page{padding:0}
    body.panel-mode .hero,
    body.panel-mode .table-panel,
    body.panel-mode .tooltip{display:none}
    body.panel-mode .layout{display:block}
    body.panel-mode .chart-panel{
      padding:0;
      background:transparent;
      border:none;
      border-radius:0;
      box-shadow:none;
      backdrop-filter:none;
    }
    body.panel-mode #treemap{
      border:none;
      border-radius:0;
      width:100vw;
      height:100vh;
      aspect-ratio:auto;
    }
    @media (max-width:1320px){.hero,.layout{grid-template-columns:1fr}.table-wrap{max-height:none}}
    @media (max-width:760px){
      .page{padding:14px}
      .intro h1{font-size:24px}
      .summary{grid-template-columns:1fr}
      .control-inline{grid-template-columns:1fr}
      #treemap{aspect-ratio:1 / 1}
    }
    .minimal-style {
      background: #f8f9fa;
    }
    .minimal-style .card {
      background: #ffffff;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .minimal-style .intro h1 {
      color: #2c3e50;
      font-weight: 600;
    }
    .minimal-style .controls h2 {
      color: #34495e;
      font-size: 18px;
      margin-bottom: 16px;
    }
    .minimal-style .legend-shape {
      background: #ecf0f1;
      border: 1px solid #bdc3c7;
    }
    .minimal-style #treemap {
      background: #ffffff;
      border: 1px solid #e0e0e0;
    }
    .minimal-style .tooltip {
      background: rgba(255, 255, 255, 0.95);
      color: #2c3e50;
      border: 1px solid #ddd;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="card intro">
        <h1 id="pageTitle"></h1>
        <p id="pageSubtitle"></p>
        <div class="meta" id="meta"></div>
      </div>
      <div class="card controls">
        <h2>筛选与拼图设置</h2>
        <div class="control-row">
          <label for="thresholdSlider">最小 clone 丰度</label>
          <div class="control-inline">
            <input id="thresholdSlider" type="range" min="0" step="1" />
            <input id="thresholdInput" type="number" min="0" step="1" />
          </div>
        </div>
        <div class="summary">
          <div class="stat"><span class="label">当前显示 clone</span><span class="value" id="filteredCloneCount">0</span></div>
          <div class="stat"><span class="label">当前总 copy</span><span class="value" id="filteredCopyTotal">0</span></div>
          <div class="stat"><span class="label">全部 clone</span><span class="value" id="allCloneCount">0</span></div>
          <div class="stat"><span class="label">全部总 copy</span><span class="value" id="allCopyTotal">0</span></div>
        </div>
        <div class="control-row">
          <label>Treemap 形式</label>
          <select id="layoutSelect">
            <option value="tetris">俄罗斯方块</option>
            <option value="qr">二维码形式</option>
          </select>
        </div>
        <div class="control-row">
          <label>CANVAS_SHAPE</label>
          <select id="canvasShapeSelect">
            <option value="square">square</option>
            <option value="portrait">portrait</option>
          </select>
        </div>
        <div class="control-row">
          <label id="legendLabel">图例</label>
          <div class="legend" id="legend"></div>
        </div>
      </div>
    </section>
    <section class="layout">
      <div class="card chart-panel">
        <div class="panel-head">
          <div><h2>Clone Matrix</h2><p id="chartDescription">按 V/J gene 分层后连续拼接成矩阵，每个 clone 用一个 tetromino 表示</p></div>
          <p id="chartHint"></p>
        </div>
        <svg id="treemap" viewBox="0 0 960 960" preserveAspectRatio="xMidYMid meet"></svg>
      </div>
      <div class="card table-panel">
        <div class="panel-head">
          <div><h2>Top 100 Clones</h2><p>右侧列出当前阈值下丰度最高的 clone，并显示其当前布局形式</p></div>
          <p id="tableHint"></p>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>#</th><th>CDR3</th><th>copy</th><th>freq</th><th>C</th><th>shape</th><th>V</th><th>J</th></tr></thead>
            <tbody id="topTableBody"></tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
  <div class="tooltip" id="tooltip"></div>
  <script>
    const searchParams = new URLSearchParams(window.location.search);
    const mode = searchParams.get("mode");
    const panelMode = mode === "panel" || mode === "panel-fill";
    const panelFillMode = mode === "panel-fill";
    if (panelMode) document.body.classList.add("panel-mode");
    const CLONES = __DATA_JSON__;
    const SETTINGS = __SETTINGS_JSON__;
    const VISUAL_LIMIT = 1800;
    const CANVAS_PRESETS = {
      square: {w: 960, h: 960, label: "Square"},
      portrait: {w: 700, h: 1500, label: "Portrait"}
    };
    const TREEMAP_REFERENCE_PALETTE = ["#89b8c8","#9fd183","#d8d856","#73b6df","#4e7fc9","#a36fd6","#6d4aa8","#ef8a78","#eca9c4","#cb4fa0","#b99673","#7b5438","#a6b84d","#67b8b5","#d5dde2","#c8cdd5","#f0dc88","#f0aa4b","#9fded0","#76caef","#b291e5","#96ab72","#dfa9d0","#eac0a3","#3f97cb","#58c45a","#de679b","#d7ea79"];
    const MOSAIC_REFERENCE_PALETTE = ["#981840","#104008","#a020b0","#e8c040","#f8e838","#8098d0","#e89080","#e860d0","#901098","#70a0e8","#a8f888","#286028","#58d000","#d0b040","#2818f0","#c0f018","#684820","#685820","#b088e0","#988060","#e06040","#50d018","#2058a0","#b84858","#10c8a8","#a02080","#c878c8","#b858b8","#d8e008","#b80068","#f86018","#5848c8","#582060","#90d018","#280018","#10f0f8","#40d830","#006b4a","#3ec4d1","#ef0db8","#80d9ab","#0da12f","#225bb7"];
    const VIVID_PALETTE = TREEMAP_REFERENCE_PALETTE;
    const QR_REFERENCE_PALETTE = MOSAIC_REFERENCE_PALETTE;
    const QR_HOTSPOT_COLORS = ["#4f84b5","#69b052","#6d5094","#d986bc","#875a3e","#b2b04c","#6ea2e0","#9767cc","#ddd25f","#58aaa4","#cad6dc","#e2adc8"];
    const QR_MICRO_PALETTE = ["#8ec7d0","#b8d98b","#e0db76","#95c7e4","#6f93cf","#b592db","#efb5a5","#f0bfd2","#86c2b1","#dad7b3","#f1dea1","#e3b36d","#9fd6df","#c7b5e2","#d88db4","#d2e38b"];
    const QR_NEUTRAL_PALETTE = ["#d7dbe1","#cfdada","#e2e4e8","#d3d3d6","#b4baa9","#c8c09d","#e0cec2","#dde2bc"];
    const SHAPES = {
      I:[[0,0],[1,0],[2,0],[3,0]],
      O:[[0,0],[1,0],[0,1],[1,1]],
      T:[[0,0],[1,0],[2,0],[1,1]],
      S:[[1,0],[2,0],[0,1],[1,1]],
      Z:[[0,0],[1,0],[1,1],[2,1]],
      J:[[0,0],[0,1],[1,1],[2,1]],
      L:[[2,0],[0,1],[1,1],[2,1]]
    };
    const SHAPE_ORDER = ["I","O","T","S","Z","J","L"];
    const SHAPE_ROTATIONS = Object.fromEntries(SHAPE_ORDER.map((name) => [name, buildRotations(SHAPES[name])]));
    const BCR_CHAINS = new Set(["IGH", "IGK", "IGL"]);
    const requestedThreshold = Number(searchParams.get("threshold"));
    const requestedLayoutMode = searchParams.get("layout");
    const requestedCanvasShape = searchParams.get("canvas_shape") || searchParams.get("canvasShape");
    const initialLayoutMode = requestedLayoutMode === "qr" || requestedLayoutMode === "tetris"
      ? requestedLayoutMode
      : (SETTINGS.layoutMode || "tetris");
    const initialCanvasShape = CANVAS_PRESETS[requestedCanvasShape]
      ? requestedCanvasShape
      : (CANVAS_PRESETS[SETTINGS.canvasShape] ? SETTINGS.canvasShape : "square");
    const IS_BCR_DATASET = CLONES.some((record) => BCR_CHAINS.has(String(record.chain || "").toUpperCase()));
    const BCR_C_SHAPE_RULE = buildBcrCShapeRule(CLONES);
    const state = {
      threshold: Number.isFinite(requestedThreshold) ? requestedThreshold : SETTINGS.defaultMinCopy,
      layoutMode: initialLayoutMode,
      canvasShape: initialCanvasShape
    };
    let MATRIX_W = CANVAS_PRESETS[state.canvasShape].w;
    let MATRIX_H = CANVAS_PRESETS[state.canvasShape].h;
    const svg = d3.select("#treemap");
    if (panelFillMode) {
      svg.attr("preserveAspectRatio", "none");
    }
    const tooltip = document.getElementById("tooltip");
    const thresholdSlider = document.getElementById("thresholdSlider");
    const thresholdInput = document.getElementById("thresholdInput");
    const topTableBody = document.getElementById("topTableBody");
    updateCanvasGeometry();
    document.getElementById("pageTitle").textContent = SETTINGS.title;
    document.getElementById("pageSubtitle").textContent = `Input: ${SETTINGS.sourceName} | Columns: CDR3=${SETTINGS.columns.cdr3 || "NA"}, copy=${SETTINGS.columns.copy || "NA"}, V=${SETTINGS.columns.v || "NA"}, J=${SETTINGS.columns.j || "NA"}, C=${SETTINGS.columns.c || "NA"}`;
    document.getElementById("allCloneCount").textContent = fmtInt(SETTINGS.summary.total_clones);
    document.getElementById("allCopyTotal").textContent = fmtInt(SETTINGS.summary.total_copy);
    thresholdSlider.max = String(Math.max(0, SETTINGS.maxCopy));
    thresholdInput.max = String(Math.max(0, SETTINGS.maxCopy));
    thresholdSlider.value = String(state.threshold);
    thresholdInput.value = String(state.threshold);
    thresholdSlider.addEventListener("input", () => setThreshold(Number(thresholdSlider.value || 0)));
    thresholdInput.addEventListener("change", () => setThreshold(Number(thresholdInput.value || 0)));
    const layoutSelect = document.getElementById("layoutSelect");
    if (layoutSelect) {
      layoutSelect.value = state.layoutMode;
      layoutSelect.addEventListener("change", () => {
        state.layoutMode = layoutSelect.value;
        syncUrlState();
        renderLegend();
        updateChartDescription();
        safeRender();
      });
    }
    const canvasShapeSelect = document.getElementById("canvasShapeSelect");
    if (canvasShapeSelect) {
      canvasShapeSelect.value = state.canvasShape;
      canvasShapeSelect.addEventListener("change", () => {
        state.canvasShape = CANVAS_PRESETS[canvasShapeSelect.value] ? canvasShapeSelect.value : "square";
        updateCanvasGeometry();
        syncUrlState();
        renderMeta();
        safeRender();
      });
    }
    renderMeta();
    renderLegend();
    updateChartDescription();
    setThreshold(state.threshold);

    function setThreshold(v) {
      state.threshold = Math.max(0, Math.min(SETTINGS.maxCopy, Math.round(Number.isFinite(v) ? v : 0)));
      thresholdSlider.value = String(state.threshold);
      thresholdInput.value = String(state.threshold);
      syncUrlState();
      safeRender();
    }

    function syncUrlState() {
      try {
        const nextParams = new URLSearchParams(window.location.search);
        nextParams.set("threshold", String(state.threshold));
        nextParams.set("layout", state.layoutMode);
        nextParams.set("canvas_shape", state.canvasShape);
        const nextQuery = nextParams.toString();
        const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}${window.location.hash || ""}`;
        window.history.replaceState(null, "", nextUrl);
      } catch (error) {
        console.warn("Failed to sync treemap URL state:", error);
      }
    }

    function updateCanvasGeometry() {
      const preset = CANVAS_PRESETS[state.canvasShape] || CANVAS_PRESETS.square;
      MATRIX_W = preset.w;
      MATRIX_H = preset.h;
      svg.attr("viewBox", `0 0 ${MATRIX_W} ${MATRIX_H}`);
      if (!panelFillMode) {
        svg.style("aspect-ratio", `${MATRIX_W} / ${MATRIX_H}`);
      }
    }

    function renderMeta() {
      const meta = document.getElementById("meta");
      const vGeneCount = new Set(CLONES.map((d) => d.v || "V?")).size;
      const jGeneCount = new Set(CLONES.map((d) => d.j || "J?")).size;
      const vjPairCount = new Set(CLONES.map((d) => `${d.v || "V?"}|${d.j || "J?"}`)).size;
      const items = [
        `默认阈值 ${fmtInt(SETTINGS.defaultMinCopy)}`,
        `输入行 ${fmtInt(SETTINGS.summary.input_rows)}`,
        `有效行 ${fmtInt(SETTINGS.summary.used_rows)}`,
        `聚合 clone ${fmtInt(SETTINGS.summary.total_clones)}`,
        `画布 ${CANVAS_PRESETS[state.canvasShape]?.label || state.canvasShape}`,
        `V gene ${fmtInt(vGeneCount)}`,
        `J gene ${fmtInt(jGeneCount)}`,
        `VJ pair ${fmtInt(vjPairCount)}`
      ];
      if (IS_BCR_DATASET && BCR_C_SHAPE_RULE.entries.length) {
        items.push(`BCR按 C 区定形`);
        items.push(`C 区 ${fmtInt(BCR_C_SHAPE_RULE.entries.length)}`);
      }
      meta.innerHTML = items.map((text) => `<span class="pill">${esc(text)}</span>`).join("");
    }

    function renderLegend() {
      const legend = document.getElementById("legend");
      const legendLabel = document.getElementById("legendLabel");
      if (state.layoutMode === "qr") {
        if (legendLabel) legendLabel.textContent = "二维码图例";
        legend.innerHTML = [
          `<div class="legend-item">${miniQrSvg(1, 1, "qr-dot")}<span>像素点</span></div>`,
          `<div class="legend-item">${miniQrSvg(2, 3, "qr-mid")}<span>矩形块</span></div>`,
          `<div class="legend-item">${miniQrSvg(4, 5, "qr-core")}<span>热点块</span></div>`
        ].join("");
        return;
      }
      if (IS_BCR_DATASET && BCR_C_SHAPE_RULE.entries.length) {
        if (legendLabel) legendLabel.textContent = "BCR 俄罗斯方块图例";
        const legendItems = BCR_C_SHAPE_RULE.entries.map((entry) =>
          `<div class="legend-item">${miniShapeSvg(entry.shape)}<span>${esc(entry.label)} → ${entry.shape}${entry.reused ? " · 复用" : ""}</span></div>`
        );
        if (BCR_C_SHAPE_RULE.hasOverflow) {
          legendItems.push(`<div class="legend-item"><span>超过 ${SHAPE_ORDER.length} 种 C 区时会循环复用方块，但同一 C 始终保持同一种形状</span></div>`);
        }
        legend.innerHTML = legendItems.join("");
        return;
      }
      if (legendLabel) legendLabel.textContent = "俄罗斯方块图例";
      legend.innerHTML = SHAPE_ORDER.map((shape) =>
        `<div class="legend-item">${miniShapeSvg(shape)}<span>${shape}</span></div>`
      ).join("");
    }

    function updateChartDescription() {
      const chartDescription = document.getElementById("chartDescription");
      if (!chartDescription) return;
      chartDescription.textContent = state.layoutMode === "qr"
        ? "按 V/J gene 分层后压缩成二维码风格像素矩阵，每个 clone 占据一块离散网格区域"
        : (IS_BCR_DATASET
          ? "BCR 模式下按 V/J gene 分层连续拼接成矩阵，并按 C 区分配固定 tetromino；同一 C 区始终使用同一种方块"
          : "按 V/J gene 分层后连续拼接成矩阵，每个 clone 用一个 tetromino 表示");
    }

    function render() {
      const filtered = CLONES
        .filter((d) => d.copy >= state.threshold)
        .sort((a, b) => b.copy - a.copy || geneSort(a.v, b.v) || a.cdr3.localeCompare(b.cdr3))
        .map((d, index) => ({...d, displayRank: index + 1}));
      const filteredTotal = d3.sum(filtered, (d) => d.copy);
      const visualRecords = filtered.length > VISUAL_LIMIT ? filtered.slice(0, VISUAL_LIMIT) : filtered;
      const layout = computeLayout(visualRecords);
      document.getElementById("filteredCloneCount").textContent = fmtInt(filtered.length);
      document.getElementById("filteredCopyTotal").textContent = fmtInt(filteredTotal);
      document.getElementById("chartHint").textContent = "";
      document.getElementById("tableHint").textContent = filtered.length
        ? `阈值 >= ${fmtInt(state.threshold)}`
        : "Top 100 为空";
      renderTable(filtered, filteredTotal);
      renderPuzzle(layout, filtered.length > VISUAL_LIMIT ? filtered.length - VISUAL_LIMIT : 0);
    }

    function computeLayout(records) {
      return state.layoutMode === "qr"
        ? computeQrLayout(records)
        : computeGroupLayout(records);
    }

    function safeRender() {
      try {
        render();
      } catch (error) {
        console.error("Clone puzzle render failed:", error);
        showRenderError(error);
      }
    }

    function showRenderError(error) {
      const message = error && error.message ? error.message : String(error);
      document.getElementById("chartHint").textContent = `渲染失败: ${message}`;
      document.getElementById("tableHint").textContent = "页面脚本发生错误";
      topTableBody.innerHTML = `<tr><td colspan="7" style="padding:16px;color:#b42318">渲染失败：${esc(message)}</td></tr>`;
      svg.selectAll("*").remove();
      svg.append("text")
        .attr("class", "empty")
        .attr("x", MATRIX_W / 2)
        .attr("y", MATRIX_H * 0.42)
        .attr("text-anchor", "middle")
        .text("页面渲染失败");
      svg.append("text")
        .attr("x", MATRIX_W / 2)
        .attr("y", MATRIX_H * 0.42 + 30)
        .attr("text-anchor", "middle")
        .attr("font-size", 12)
        .attr("fill", "#8b3a2d")
        .text(fitText(message, 90));
    }

    function renderTable(records, totalCopy) {
      const top = records.slice(0, SETTINGS.topN);
      topTableBody.innerHTML = top.length ? top.map((d, i) => `
        <tr>
          <td>${d.displayRank || i + 1}</td>
          <td class="cdr3">${esc(d.cdr3)}</td>
          <td>${fmtInt(d.copy)}</td>
          <td>${fmtPct(totalCopy ? d.copy / totalCopy : d.frequency)}</td>
          <td>${esc(displayCLabel(d))}</td>
          <td><span class="shape-badge">${esc(displayShapeLabel(d))}</span></td>
          <td>${esc(d.v || "V?")}</td>
          <td>${esc(d.j || "J?")}</td>
        </tr>
      `).join("") : `<tr><td colspan="8" style="padding:16px;color:#6a6258">当前阈值下无 clone。</td></tr>`;
    }

    function renderPuzzle(layout, hiddenCount) {
      svg.selectAll("*").remove();
      if (!layout.placed.length) {
        svg.append("text").attr("class", "empty").attr("x", MATRIX_W / 2).attr("y", MATRIX_H / 2).attr("text-anchor", "middle").text("当前阈值下没有可显示的 clone");
        return;
      }

      const root = svg.append("g");
      layout.placed.forEach((piece) => drawPiece(root, piece, piece.cellSize || layout.cellSize));

      if (false) {
        svg.append("text")
          .attr("x", 1184)
          .attr("y", 748)
          .attr("text-anchor", "end")
          .attr("font-size", 11)
          .attr("fill", "#5c6770")
          .text(`为保证流畅度，拼图仅展示前 ${fmtInt(VISUAL_LIMIT)} 个 clone，另有 ${fmtInt(hiddenCount)} 个未绘制`);
      }
    }

    function renderVBand(root, band) {
      const accent = groupColor(band.name);
      const g = root.append("g").attr("class", "v-band");

      g.append("rect")
        .attr("x", band.x0)
        .attr("y", band.y0)
        .attr("width", Math.max(0, band.x1 - band.x0))
        .attr("height", Math.max(0, band.y1 - band.y0))
        .attr("fill", hexToRgba(accent, 0.035))
        .attr("stroke", hexToRgba(accent, 0.22))
        .attr("stroke-width", 1);

      if (band.showLabel) {
        const title = `${band.name}  ${fmtInt(band.totalCopy)} copy`;
        g.append("text")
          .attr("x", band.x0 + 8)
          .attr("y", band.y0 + 16)
          .attr("font-size", 11)
          .attr("font-weight", 700)
          .attr("fill", "#24303a")
          .text(fitText(title, Math.floor((band.x1 - band.x0 - 14) / 8)));
      }
    }

    function renderGroup(root, group, index) {
      const accent = pairBaseColor(group);
      const g = root.append("g").attr("class", "vj-group");

      g.append("rect")
        .attr("x", group.x0)
        .attr("y", group.y0)
        .attr("width", Math.max(0, group.x1 - group.x0))
        .attr("height", Math.max(0, group.y1 - group.y0))
        .attr("fill", hexToRgba(accent, 0.12))
        .attr("stroke", hexToRgba(accent, 0.38))
        .attr("stroke-width", 0.9);

      const title = `${group.name} · ${fmtInt(group.totalCopy)} copy · ${fmtInt(group.items.length)} clones`;
      if (group.showLabel) {
        g.append("text")
          .attr("x", group.x0 + 6)
          .attr("y", group.y0 + 16)
          .attr("font-size", 9)
          .attr("font-weight", 700)
          .attr("fill", "#26323b")
          .text(fitText(title, Math.floor((group.x1 - group.x0 - 10) / 7.2)));
      }

      if (group.omitted > 0) {
        g.append("text")
          .attr("x", group.x1 - 6)
          .attr("y", group.y0 + 16)
          .attr("text-anchor", "end")
          .attr("font-size", 10)
          .attr("fill", "#6a6258")
          .text(`未排入 ${fmtInt(group.omitted)}`);
      }

      const pieces = g.append("g").attr("transform", `translate(${group.innerX},${group.innerY})`);
      group.placed.forEach((piece) => drawPiece(pieces, piece, group.cellSize));
    }

    function drawPiece(parent, piece, cellSize) {
      const fill = piece.displayColor || pieceColor(piece);
      const originX = piece.absolute ? piece.x : piece.x * cellSize;
      const originY = piece.absolute ? piece.y : piece.y * cellSize;
      const pieceGroup = parent.append("g")
        .attr("transform", `translate(${originX},${originY})`);
      const body = pieceGroup.append("g");
      const hoverTransform = piece.filler ? "" : pieceHoverTransform(piece, cellSize);

      if (!piece.filler) {
        pieceGroup
          .style("cursor", "pointer")
          .on("mouseenter", (event) => {
            pieceGroup.raise();
            body.interrupt()
              .transition()
              .duration(160)
              .ease(d3.easeCubicOut)
              .attr("transform", hoverTransform)
              .style("filter", "drop-shadow(0 12px 18px rgba(0,0,0,.28)) drop-shadow(0 2px 3px rgba(255,255,255,.14))");
            showTip(event, piece);
          })
          .on("mousemove", (event) => moveTip(event))
          .on("mouseleave", () => {
            body.interrupt()
              .transition()
              .duration(150)
              .ease(d3.easeCubicOut)
              .attr("transform", "")
              .style("filter", null);
            hideTip();
          });
      }

      if (piece.rects && piece.rects.length) {
        piece.rects.forEach((rect) => {
          const rectWidth = rect.w * cellSize + 0.3;
          const rectHeight = rect.h * cellSize + 0.3;
          const inset = state.layoutMode === "qr" && !piece.filler
            ? Math.min(qrBlockGap(rectWidth, rectHeight) / 2, rectWidth * 0.22, rectHeight * 0.22)
            : 0;
          const rounded = state.layoutMode === "qr" && !piece.filler
            ? Math.min(36, Math.max(0.08, Math.min(rectWidth - inset * 2, rectHeight - inset * 2) * 0.28))
            : 0;
          body.append("rect")
            .attr("x", rect.x * cellSize + inset)
            .attr("y", rect.y * cellSize + inset)
            .attr("width", Math.max(0.01, rectWidth - inset * 2))
            .attr("height", Math.max(0.01, rectHeight - inset * 2))
            .attr("fill", fill)
            .attr("rx", rounded)
            .attr("ry", rounded)
            .attr("shape-rendering", rounded ? null : "crispEdges");
        });
        return;
      }

      piece.cells.forEach(([cx, cy]) => {
        body.append("rect")
          .attr("x", cx * piece.scale * cellSize - 0.15)
          .attr("y", cy * piece.scale * cellSize - 0.15)
          .attr("width", piece.scale * cellSize + 0.3)
          .attr("height", piece.scale * cellSize + 0.3)
          .attr("fill", fill)
          .attr("shape-rendering", "crispEdges");
      });
    }

    function computeGroupLayout(records) {
      if (!records.length) return {cellSize: 0, placed: []};

      const pieces = makeReferenceHierarchyTetrisPieces(records);
      pieces.forEach((piece, index) => { piece._pid = index + 1; });
      return {
        cellSize: 1,
        placed: pieces,
        omitted: Math.max(0, records.length - pieces.length),
        cols: MATRIX_W,
        rows: MATRIX_H
      };
    }

    function qrBlockGap(width, height) {
      const side = Math.min(width, height);
      if (side < 2) return 0.02;
      if (side < 3.5) return 0.04;
      if (side < 6) return 0.07;
      if (side < 10) return 0.12;
      if (side < 18) return 0.20;
      if (side < 36) return 0.32;
      return 0.62;
    }

    function computeQrLayout(records) {
      if (!records.length) return {cellSize: 0, placed: []};

      const placed = makeReferenceHierarchyRects(records)
        .map((rect, index) => ({
          ...rect,
          _pid: index + 1,
          shape: "QR",
          qr: true,
          x: rect.x,
          y: rect.y,
          scale: 1,
          displayColor: referenceCloneColor(rect, index),
          rects: [{x: 0, y: 0, w: rect.dx, h: rect.dy}]
        }));

      return {
        cellSize: 1,
        placed,
        omitted: Math.max(0, records.length - placed.length),
        cols: MATRIX_W,
        rows: MATRIX_H
      };
    }

    function makeReferenceHierarchyTetrisPieces(records) {
      const vGroups = groupByWithTotals(records, (record) => record.v || "V?");
      const vRects = squarifyItems(vGroups, 0, 0, MATRIX_W, MATRIX_H, "totalCopy");
      const pieces = [];

      vRects.forEach((vRect) => {
        const jGroups = groupByWithTotals(vRect.items, (record) => record.j || "J?");
        const jRects = squarifyItems(jGroups, vRect.x, vRect.y, vRect.dx, vRect.dy, "totalCopy");
        jRects.forEach((jRect) => {
          const clones = jRect.items.slice().sort(referenceCloneSort);
          pieces.push(...packTetrominoesInRect(clones, jRect));
        });
      });

      return transformAbsolutePieces(pieces, true, true);
    }

    function packTetrominoesInRect(items, rect) {
      if (!items.length || rect.dx <= 2 || rect.dy <= 2) return [];
      const startCell = Math.max(2, Math.min(16, chooseCellSize(rect.dx, rect.dy, items.length)));
      let best = {cellSize: 2, placed: [], omitted: Infinity, cols: 0, rows: 0};

      for (let cellSize = startCell; cellSize >= 2; cellSize -= 1) {
        const cols = Math.max(1, Math.floor(rect.dx / cellSize));
        const rows = Math.max(1, Math.floor(rect.dy / cellSize));
        if (cols < 2 || rows < 2) continue;
        const occupancy = Array.from({length: rows}, () => new Uint8Array(cols));
        const scales = computeScales(items, cols, rows, 0.92);
        const placed = [];
        let omitted = 0;

        items.forEach((item, index) => {
          const placement = placePiece(occupancy, cols, rows, item, scales[index]);
          if (placement) {
            placed.push({
              ...item,
              ...placement,
              absolute: true,
              cellSize,
              x: rect.x + placement.x * cellSize,
              y: rect.y + placement.y * cellSize,
            });
          } else {
            omitted += 1;
          }
        });

        if (omitted < best.omitted || (omitted === best.omitted && cellSize > best.cellSize)) {
          best = {cellSize, placed, omitted, cols, rows};
        }
        if (omitted === 0) break;
      }

      return best.placed;
    }

    function transformAbsolutePieces(pieces, flipX, flipY) {
      return pieces.map((piece) => {
        const bounds = piecePixelBounds(piece);
        const next = {...piece};
        if (flipX) next.x = MATRIX_W - piece.x - bounds.w;
        if (flipY) next.y = MATRIX_H - piece.y - bounds.h;
        return next;
      });
    }

    function piecePixelBounds(piece) {
      if (piece.rects && piece.rects.length) {
        return {
          w: d3.max(piece.rects, (rect) => (rect.x + rect.w) * (piece.cellSize || 1)) || 1,
          h: d3.max(piece.rects, (rect) => (rect.y + rect.h) * (piece.cellSize || 1)) || 1
        };
      }
      const dims = shapeDimensions(piece.cells || SHAPES.O);
      const cellSize = piece.cellSize || 1;
      const scale = piece.scale || 1;
      return {w: dims.w * scale * cellSize, h: dims.h * scale * cellSize};
    }

    function makeReferenceHierarchyRects(records) {
      const vGroups = groupByWithTotals(records, (record) => record.v || "V?");
      const vRects = squarifyItems(vGroups, 0, 0, MATRIX_W, MATRIX_H, "totalCopy");
      const leafRects = [];

      vRects.forEach((vRect) => {
        const jGroups = groupByWithTotals(vRect.items, (record) => record.j || "J?");
        const jRects = squarifyItems(jGroups, vRect.x, vRect.y, vRect.dx, vRect.dy, "totalCopy");
        jRects.forEach((jRect) => {
          const clones = jRect.items.slice().sort(referenceCloneSort);
          const cloneRects = squarifyItems(clones, jRect.x, jRect.y, jRect.dx, jRect.dy, "copy");
          leafRects.push(...cloneRects);
        });
      });

      return transformReferenceRects(leafRects, true, true, false);
    }

    function groupByWithTotals(records, keyFn) {
      const groups = new Map();
      records.forEach((record) => {
        const key = keyFn(record);
        if (!groups.has(key)) {
          groups.set(key, {
            name: key,
            totalCopy: 0,
            sourceOrder: Number(record.source_order || record.sourceOrder || 0),
            items: []
          });
        }
        const group = groups.get(key);
        group.totalCopy += Number(record.copy || 0);
        group.sourceOrder = Math.min(group.sourceOrder, Number(record.source_order || record.sourceOrder || 0));
        group.items.push(record);
      });
      return Array.from(groups.values()).sort((a, b) =>
        b.totalCopy - a.totalCopy
        || a.sourceOrder - b.sourceOrder
        || geneSort(a.name, b.name)
      );
    }

    function referenceCloneSort(a, b) {
      return Number(b.copy || 0) - Number(a.copy || 0)
        || Number(a.source_order || a.sourceOrder || 0) - Number(b.source_order || b.sourceOrder || 0)
        || geneSort(a.v, b.v)
        || geneSort(a.j, b.j)
        || String(a.cdr3 || "").localeCompare(String(b.cdr3 || ""));
    }

    function squarifyItems(items, x, y, dx, dy, valueKey) {
      const values = items.map((item) => Number(item[valueKey] || 0));
      const areas = normalizeReferenceAreas(values, dx, dy);
      const pending = items.map((item, index) => ({...item, _area: areas[index] || 0})).filter((item) => item._area > 0);
      const rects = [];
      let row = [];

      while (pending.length) {
        const item = pending[0];
        const side = Math.min(dx, dy);
        const nextRow = row.concat(item);
        if (!row.length || worstReferenceRatio(nextRow.map((entry) => entry._area), side) <= worstReferenceRatio(row.map((entry) => entry._area), side)) {
          row.push(pending.shift());
          continue;
        }
        const layout = layoutReferenceRow(row, x, y, dx, dy);
        rects.push(...layout.rects);
        x = layout.x;
        y = layout.y;
        dx = layout.dx;
        dy = layout.dy;
        row = [];
      }

      if (row.length) {
        const layout = layoutReferenceRow(row, x, y, dx, dy);
        rects.push(...layout.rects);
      }

      return rects;
    }

    function normalizeReferenceAreas(values, dx, dy) {
      const total = d3.sum(values);
      if (!total || dx <= 0 || dy <= 0) return [];
      const scale = (dx * dy) / total;
      return values.map((value) => Number(value || 0) * scale);
    }

    function worstReferenceRatio(row, side) {
      if (!row.length || side <= 0) return Infinity;
      const rowSum = d3.sum(row);
      const rowMin = d3.min(row);
      const rowMax = d3.max(row);
      if (!rowSum || !rowMin || rowMin <= 0) return Infinity;
      const sideSq = side * side;
      return Math.max(sideSq * rowMax / (rowSum * rowSum), (rowSum * rowSum) / (sideSq * rowMin));
    }

    function layoutReferenceRow(rowItems, x, y, dx, dy) {
      const rowSum = d3.sum(rowItems, (item) => item._area);
      const rects = [];
      if (!rowSum || dx <= 0 || dy <= 0) return {rects, x, y, dx, dy};
      const useVertical = dx >= dy;

      if (useVertical) {
        const width = rowSum / dy;
        let cursorY = y;
        rowItems.forEach((item, index) => {
          const height = index === rowItems.length - 1 ? (y + dy) - cursorY : item._area / width;
          rects.push({...item, x, y: cursorY, dx: width, dy: height});
          cursorY += height;
        });
        return {rects, x: x + width, y, dx: dx - width, dy};
      }

      const height = rowSum / dx;
      let cursorX = x;
      rowItems.forEach((item, index) => {
        const width = index === rowItems.length - 1 ? (x + dx) - cursorX : item._area / height;
        rects.push({...item, x: cursorX, y, dx: width, dy: height});
        cursorX += width;
      });
      return {rects, x, y: y + height, dx, dy: dy - height};
    }

    function transformReferenceRects(rects, flipX, flipY, swapXY) {
      const transformW = swapXY ? MATRIX_H : MATRIX_W;
      const transformH = swapXY ? MATRIX_W : MATRIX_H;
      const scaleX = MATRIX_W / transformW;
      const scaleY = MATRIX_H / transformH;
      return rects.map((rect) => {
        let x = rect.x;
        let y = rect.y;
        let dx = rect.dx;
        let dy = rect.dy;
        if (swapXY) [x, y, dx, dy] = [y, x, dy, dx];
        if (flipX) x = transformW - x - dx;
        if (flipY) y = transformH - y - dy;
        return {...rect, x: x * scaleX, y: y * scaleY, dx: dx * scaleX, dy: dy * scaleY};
      });
    }

    function referenceCloneColor(record, index) {
      return paletteColor(record.clone_id || `${record.v}|${record.j}|${record.cdr3}|${index + 123}`, QR_REFERENCE_PALETTE);
    }

    function packMatrix(items, width, height) {
      const startCell = Math.max(3, Math.min(16, chooseCellSize(width, height, items.length) + 2));
      let best = {cellSize: 2, placed: [], omitted: Infinity, cols: 0, rows: 0};

      for (let cellSize = startCell; cellSize >= 2; cellSize -= 1) {
        const cols = Math.max(24, Math.floor(width / cellSize));
        const rows = Math.max(16, Math.floor(height / cellSize));
        const occupancy = Array.from({length: rows}, () => new Uint8Array(cols));
        const scales = computeScales(items, cols, rows, 0.985);
        const placed = [];
        let omitted = 0;

        items.forEach((item, index) => {
          const placement = placePiece(occupancy, cols, rows, item, scales[index]);
          if (placement) {
            placed.push({...item, ...placement});
          } else {
            omitted += 1;
          }
        });

        if (omitted < best.omitted || (omitted === best.omitted && cellSize > best.cellSize)) {
          best = {cellSize, placed, omitted, cols, rows};
        }
        if (omitted === 0) break;
      }

      const pieceGrid = Array.from({length: best.rows}, () => new Uint32Array(best.cols));
      best.placed.forEach((piece, index) => {
        piece._pid = index + 1;
        stampPieceId(pieceGrid, piece, piece._pid);
      });

      const fillers = fillRemainingGaps(pieceGrid, best.cols, best.rows, best.placed.length + 1);
      const allPieces = best.placed.concat(fillers);
      assignDisplayColors(allPieces, pieceGrid, best.cols, best.rows);

      return {
        cellSize: best.cellSize,
        placed: allPieces,
        omitted: best.omitted,
        cols: best.cols,
        rows: best.rows
      };
    }

    function chooseCellSize(width, height, itemCount) {
      const approx = Math.floor(Math.sqrt((width * height) / Math.max(itemCount * 16, 24)));
      return Math.max(4, Math.min(16, approx || 8));
    }

    function computeScales(items, cols, rows, fillRatio = 0.96) {
      const targetCells = Math.max(items.length * 4 + 8, Math.floor(cols * rows * fillRatio));
      const maxScale = Math.max(1, Math.floor(Math.min(cols, rows) / 4));
      const totalCopy = d3.sum(items, (d) => d.copy) || 1;
      let adjust = targetCells / totalCopy;
      let scales = items.map((item) => clampScale(Math.round(Math.sqrt((item.copy * adjust) / 4)), maxScale));

      for (let i = 0; i < 12; i += 1) {
        const occupied = d3.sum(scales, (scale) => 4 * scale * scale);
        if (occupied <= targetCells * 1.02) break;
        adjust *= targetCells / occupied;
        scales = items.map((item) => clampScale(Math.round(Math.sqrt((item.copy * adjust) / 4)), maxScale));
      }
      return scales;
    }

    function chooseQrGridSide(itemCount) {
      const targetCells = Math.max(9216, Math.min(32400, Math.ceil(itemCount * 7.2)));
      return clamp(Math.ceil(Math.sqrt(targetCells)), 96, 180);
    }

    function computeQrWeight(record, index) {
      const base = Math.max(1, Number(record.copy) || 1);
      const pairSeed = Math.abs(hashCode(`${record.v || "V?"}|${record.j || "J?"}|${index}`)) % 9;
      return Math.pow(base, 0.68) * (1 + pairSeed * 0.025);
    }

    function allocateDiscreteByWeights(total, weights, minSize = 1) {
      if (!weights.length) return [];
      if (weights.length === 1) return [total];
      if (total < weights.length * minSize) return null;

      const baseSizes = weights.map(() => minSize);
      let remaining = total - weights.length * minSize;
      const totalWeight = d3.sum(weights) || 1;
      const scaled = weights.map((weight) => (weight / totalWeight) * remaining);
      const sizes = baseSizes.map((size, index) => size + Math.floor(scaled[index]));
      remaining = total - d3.sum(sizes);

      if (remaining > 0) {
        const order = scaled
          .map((value, index) => ({index, frac: value - Math.floor(value)}))
          .sort((a, b) => b.frac - a.frac || a.index - b.index);
        for (let i = 0; i < remaining; i += 1) {
          sizes[order[i % order.length].index] += 1;
        }
      }

      return sizes;
    }

    function expandQrFragments(items, cellAllocations) {
      const fragments = [];
      items.forEach((item, index) => {
        const totalArea = Math.max(1, cellAllocations[index] || 1);
        const areaFragments = splitQrAreaFragments(totalArea, index, index < 14);
        areaFragments.forEach((fragment, fragmentIndex) => {
          fragments.push({
            ...item,
            cloneRank: index,
            fragmentArea: fragment.area,
            fragmentKind: fragment.kind,
            qrWeight: fragment.area,
            fragmentIndex,
            fragmentSeed: Math.abs(hashCode(`${item.cdr3}|${item.v}|${item.j}|${fragmentIndex}|${fragment.kind}`)),
            displayColor: qrFragmentColor(item, index, fragmentIndex, fragment.kind),
          });
        });
      });

      return fragments.sort((a, b) => {
        const priorityA = qrFragmentPriority(a.fragmentKind);
        const priorityB = qrFragmentPriority(b.fragmentKind);
        return priorityA - priorityB
          || b.fragmentArea - a.fragmentArea
          || b.copy - a.copy
          || a.cdr3.localeCompare(b.cdr3);
      });
    }

    function splitQrAreaFragments(totalArea, seed, allowHotspot) {
      const fragments = [];
      let remaining = totalArea;
      const maxFragments = clamp(Math.round(Math.sqrt(totalArea) * 1.9), 1, 40);

      if (allowHotspot && totalArea >= 24) {
        const hotspotArea = clamp(
          Math.round(totalArea * 0.16),
          16,
          Math.max(16, Math.round(totalArea * 0.28))
        );
        fragments.push({area: hotspotArea, kind: "hotspot"});
        remaining -= hotspotArea;
      }

      if (remaining <= 0) {
        return fragments;
      }

      const tailCount = Math.max(1, maxFragments - fragments.length);
      const weights = Array.from({length: tailCount}, (_, idx) => {
        const jitter = 1 + (((seed + idx * 3) % 7) - 3) * 0.035;
        return (1 / Math.pow(idx + 1.35, 1.06)) * jitter;
      });
      const areas = allocateDiscreteByWeights(remaining, weights, 1) || [remaining];
      areas.forEach((area, idx) => {
        const kind = area >= 10 ? "mid" : area >= 4 ? "small" : "tile";
        fragments.push({area, kind});
      });

      return fragments;
    }

    function qrFragmentPriority(kind) {
      if (kind === "hotspot") return 0;
      if (kind === "mid") return 1;
      if (kind === "small") return 2;
      return 3;
    }

    function qrFragmentColor(record, cloneRank, fragmentIndex, kind) {
      const seed = Math.abs(hashCode(`${record.cdr3}|${record.v}|${record.j}|${fragmentIndex}|${kind}`));
      let sourcePalette = QR_MICRO_PALETTE;
      let baseHex = paletteColor(`${record.cdr3}|${record.v}|${record.j}`, QR_REFERENCE_PALETTE);

      if (kind === "hotspot") {
        sourcePalette = QR_HOTSPOT_COLORS;
        baseHex = sourcePalette[cloneRank % sourcePalette.length];
      } else if (kind === "mid") {
        sourcePalette = QR_REFERENCE_PALETTE;
        baseHex = sourcePalette[(cloneRank * 3 + fragmentIndex) % sourcePalette.length];
      } else if (kind === "small") {
        sourcePalette = (seed % 6 === 0) ? QR_NEUTRAL_PALETTE : QR_MICRO_PALETTE;
        baseHex = sourcePalette[(cloneRank + fragmentIndex + seed) % sourcePalette.length];
      } else {
        sourcePalette = (seed % 4 <= 1) ? QR_NEUTRAL_PALETTE : QR_MICRO_PALETTE;
        baseHex = sourcePalette[(cloneRank * 5 + fragmentIndex + seed) % sourcePalette.length];
      }

      const base = d3.hcl(baseHex);
      const shift = ((seed % 15) - 7) * (kind === "hotspot" ? 1.0 : 1.35);
      base.h = ((base.h || 0) + shift + 360) % 360;
      base.c = clamp(
        base.c + (kind === "hotspot" ? 14 : kind === "mid" ? 8 : kind === "small" ? 3 : 1),
        kind === "tile" ? 8 : 14,
        kind === "hotspot" ? 72 : 58
      );
      base.l = clamp(
        kind === "hotspot" ? 51 : kind === "mid" ? 59 : kind === "small" ? 67 : 73,
        44,
        82
      );
      return base.formatHex();
    }

    function qrHotspotTemplates() {
      return [
        {x: 0.66, y: 0.54, w: 0.11, h: 0.30, round: 0.42},
        {x: 0.91, y: 0.50, w: 0.12, h: 0.23, round: 0.42},
        {x: 0.87, y: 0.26, w: 0.14, h: 0.12, round: 0.4},
        {x: 0.70, y: 0.17, w: 0.09, h: 0.16, round: 0.42},
        {x: 0.39, y: 0.89, w: 0.12, h: 0.14, round: 0.42},
        {x: 0.15, y: 0.88, w: 0.07, h: 0.15, round: 0.42},
        {x: 0.54, y: 0.43, w: 0.07, h: 0.17, round: 0.4},
        {x: 0.30, y: 0.13, w: 0.07, h: 0.07, round: 0.38},
        {x: 0.08, y: 0.56, w: 0.05, h: 0.13, round: 0.4},
        {x: 0.93, y: 0.86, w: 0.07, h: 0.11, round: 0.42},
        {x: 0.52, y: 0.69, w: 0.06, h: 0.19, round: 0.4},
        {x: 0.23, y: 0.76, w: 0.05, h: 0.10, round: 0.38},
      ];
    }

    function placeQrHotspots(items, occupancy, cols, rows, placed) {
      const templates = qrHotspotTemplates();
      const hotspotCount = Math.min(templates.length, Math.max(6, Math.min(items.length, Math.ceil(Math.sqrt(items.length) * 1.05))));
      const pending = [];

      items.forEach((item, index) => {
        if (index >= hotspotCount) {
          pending.push(item);
          return;
        }

        const template = templates[index];
        const placement = findQrHotspotPlacement(item, template, index, occupancy, cols, rows);
        if (!placement) {
          pending.push(item);
          return;
        }

        stampRect(occupancy, placement.x, placement.y, placement.w, placement.h);
        placed.push({
          ...item,
          shape: "QR",
          qr: true,
          hotspot: true,
          x: placement.x,
          y: placement.y,
          scale: 1,
          rects: [{x: 0, y: 0, w: placement.w, h: placement.h}]
        });
      });

      return pending;
    }

    function findQrHotspotPlacement(item, template, rank, occupancy, cols, rows) {
      const seed = Math.abs(hashCode(`${item.cdr3}|${item.v}|${item.j}|hotspot|${rank}`));
      const intensity = clamp(1.08 - rank * 0.038, 0.72, 1.08);
      const templateW = clamp(Math.round(cols * template.w * intensity), 4, Math.max(4, cols - 2));
      const templateH = clamp(Math.round(rows * template.h * intensity), 4, Math.max(4, rows - 2));
      const targetArea = Math.max(8, item.fragmentArea || Math.round(templateW * templateH * 0.5));
      const templateRatio = templateW / Math.max(1, templateH);
      const areaWidth = Math.max(4, Math.round(Math.sqrt(targetArea * templateRatio)));
      const areaHeight = Math.max(4, Math.round(targetArea / Math.max(1, areaWidth)));
      const baseW = clamp(Math.min(templateW, areaWidth), 4, Math.max(4, cols - 2));
      const baseH = clamp(Math.min(templateH, areaHeight), 4, Math.max(4, rows - 2));
      const variants = hotspotDimensionVariants(baseW, baseH, seed);
      const anchorX = clamp(Math.round(cols * template.x), 0, cols - 1);
      const anchorY = clamp(Math.round(rows * template.y), 0, rows - 1);

      for (const variant of variants) {
        for (let radius = 0; radius <= 18; radius += 1) {
          const offsets = hotspotOffsets(radius, seed);
          for (const [dx, dy] of offsets) {
            const x = clamp(anchorX - Math.floor(variant.w / 2) + dx, 0, cols - variant.w);
            const y = clamp(anchorY - Math.floor(variant.h / 2) + dy, 0, rows - variant.h);
            if (fitsRect(occupancy, x, y, variant.w, variant.h)) {
              return {x, y, w: variant.w, h: variant.h};
            }
          }
        }
      }

      return null;
    }

    function hotspotDimensionVariants(baseW, baseH, seed) {
      const variants = [];
      const seen = new Set();
      const deltas = [0, -1, 1, -2, 2, -3, 3];
      deltas.forEach((dw, index) => {
        const dh = deltas[(index + (seed % deltas.length)) % deltas.length];
        const w = Math.max(4, baseW + dw);
        const h = Math.max(4, baseH + dh);
        const key = `${w}x${h}`;
        if (!seen.has(key)) {
          seen.add(key);
          variants.push({w, h});
        }
      });
      return variants.sort((a, b) => (b.w * b.h) - (a.w * a.h));
    }

    function hotspotOffsets(radius, seed) {
      if (radius === 0) return [[0, 0]];
      const offsets = [];
      for (let dx = -radius; dx <= radius; dx += 1) {
        offsets.push([dx, -radius], [dx, radius]);
      }
      for (let dy = -radius + 1; dy <= radius - 1; dy += 1) {
        offsets.push([-radius, dy], [radius, dy]);
      }
      const rotate = seed % Math.max(1, offsets.length);
      return offsets.map((_, index) => offsets[(index + rotate) % offsets.length]);
    }

    function extractQrFreeZones(occupancy, cols, rows) {
      const scratch = occupancy.map((row) => Uint8Array.from(row));
      const zones = [];
      for (let y = 0; y < rows; y += 1) {
        for (let x = 0; x < cols; x += 1) {
          if (scratch[y][x]) continue;
          const zone = growQrFreeZone(scratch, x, y, cols, rows);
          if (!zone) continue;
          stampRect(scratch, zone.x, zone.y, zone.w, zone.h);
          if (zone.w * zone.h >= 4) zones.push(zone);
        }
      }
      return zones.sort((a, b) => (b.w * b.h) - (a.w * a.h));
    }

    function growQrFreeZone(grid, startX, startY, cols, rows) {
      let width = 0;
      while (startX + width < cols && !grid[startY][startX + width]) width += 1;
      if (width <= 0) return null;

      let best = {x: startX, y: startY, w: width, h: 1, area: width};
      let minWidth = width;
      for (let h = 1; startY + h < rows; h += 1) {
        let rowWidth = 0;
        while (rowWidth < minWidth && startX + rowWidth < cols && !grid[startY + h][startX + rowWidth]) {
          rowWidth += 1;
        }
        minWidth = rowWidth;
        if (minWidth <= 0) break;
        const area = minWidth * (h + 1);
        if (area >= best.area) {
          best = {x: startX, y: startY, w: minWidth, h: h + 1, area};
        }
      }
      return best;
    }

    function assignQrItemsToZones(items, zones) {
      const groups = zones.map(() => []);
      if (!items.length || !zones.length) return groups;

      const loads = zones.map(() => 0);
      const areas = zones.map((zone) => Math.max(1, zone.w * zone.h));

      items.forEach((item) => {
        let bestIndex = 0;
        let bestScore = Infinity;
        for (let i = 0; i < zones.length; i += 1) {
          const projected = (loads[i] + (item.qrWeight || 1)) / areas[i];
          if (projected < bestScore) {
            bestScore = projected;
            bestIndex = i;
          }
        }
        groups[bestIndex].push(item);
        loads[bestIndex] += item.qrWeight || 1;
      });

      return groups;
    }

    function layoutQrPartition(items, x, y, w, h, depth, placed) {
      if (!items.length || w <= 0 || h <= 0) return;
      if (items.length === 1) {
        placed.push({
          ...items[0],
          shape: "QR",
          qr: true,
          x,
          y,
          scale: 1,
          rects: [{x: 0, y: 0, w, h}]
        });
        return;
      }

      if (w === 1 || h === 1 || items.length <= 3 || (w * h <= items.length * 2.4 && Math.min(w, h) <= 3)) {
        layoutQrStrip(items, x, y, w, h, depth, placed);
        return;
      }

      const orientation = chooseQrOrientation(items, w, h, depth);
      const maxGroups = Math.min(Math.max(2, Math.min(w, h)), items.length);
      let desiredGroups = 2;
      if (items.length >= 64 && Math.min(w, h) >= 10) desiredGroups = 6;
      else if (items.length >= 36 && Math.min(w, h) >= 8) desiredGroups = 5;
      else if (items.length >= 18 && Math.min(w, h) >= 6) desiredGroups = 4;
      else if (items.length >= 8 && Math.min(w, h) >= 4) desiredGroups = 3;
      desiredGroups = Math.min(desiredGroups, maxGroups);
      const groups = splitQrGroups(items, desiredGroups);
      const span = orientation === "vertical" ? w : h;

      if (!groups.length || span < groups.length) {
        layoutQrStrip(items, x, y, w, h, depth, placed);
        return;
      }

      const spans = allocateQrSpans(
        span,
        groups.map((group) => d3.sum(group, (item) => item.qrWeight || 1))
      );
      if (!spans) {
        layoutQrStrip(items, x, y, w, h, depth, placed);
        return;
      }

      let offset = 0;
      groups.forEach((group, index) => {
        const seg = spans[index];
        if (orientation === "vertical") {
          layoutQrPartition(group, x + offset, y, seg, h, depth + 1, placed);
        } else {
          layoutQrPartition(group, x, y + offset, w, seg, depth + 1, placed);
        }
        offset += seg;
      });
    }

    function layoutQrStrip(items, x, y, w, h, depth, placed) {
      const stripeBias = depth >= 4 && Math.min(w, h) <= 5;
      const orientation = stripeBias
        ? (w >= h ? "vertical" : "horizontal")
        : ((w >= h && w > 1) || h === 1 ? "vertical" : "horizontal");
      const span = orientation === "vertical" ? w : h;
      const sizes = allocateQrSpans(span, items.map((item) => item.qrWeight || 1), 1);
      if (!sizes) return;

      let offset = 0;
      items.forEach((item, index) => {
        const seg = sizes[index];
        const rect = orientation === "vertical"
          ? {x: x + offset, y, w: seg, h}
          : {x, y: y + offset, w, h: seg};
        placed.push({
          ...item,
          shape: "QR",
          qr: true,
          x: rect.x,
          y: rect.y,
          scale: 1,
          rects: [{x: 0, y: 0, w: rect.w, h: rect.h}]
        });
        offset += seg;
      });
    }

    function chooseQrOrientation(items, w, h, depth) {
      if (depth >= 4 && Math.min(w, h) <= 6) {
        return w >= h ? "vertical" : "horizontal";
      }
      if (w / h >= 1.22) return "vertical";
      if (h / w >= 1.22) return "horizontal";
      const seedBase = items.length
        ? Math.abs(hashCode(`${items[0].cdr3}|${items[items.length - 1].cdr3}|${depth}|qr-split`))
        : depth;
      return ((seedBase + depth) % 2 === 0) ? "vertical" : "horizontal";
    }

    function splitQrGroups(items, groupCount) {
      if (groupCount <= 1 || items.length <= 1) return [items];
      const weights = items.map((item) => item.qrWeight || 1);
      const totalWeight = d3.sum(weights) || 1;
      const target = totalWeight / groupCount;
      const groups = [];
      let current = [];
      let currentWeight = 0;
      let created = 0;

      items.forEach((item, index) => {
        current.push(item);
        currentWeight += item.qrWeight || 1;
        const remainingItems = items.length - index - 1;
        const remainingGroups = groupCount - created - 1;
        const shouldSplit = remainingGroups > 0
          && remainingItems >= remainingGroups
          && currentWeight >= target * 0.92;
        if (shouldSplit) {
          groups.push(current);
          current = [];
          currentWeight = 0;
          created += 1;
        }
      });
      if (current.length) groups.push(current);
      return groups.filter((group) => group.length);
    }

    function allocateQrSpans(total, weights, minSize = 1) {
      if (!weights.length) return [];
      if (weights.length === 1) return [total];
      if (total < weights.length * minSize) return null;

      const minSizes = weights.map(() => minSize);
      let remaining = total - (weights.length * minSize);
      const totalWeight = d3.sum(weights) || 1;
      const extras = weights.map((weight) => (weight / totalWeight) * remaining);
      const sizes = minSizes.map((size, index) => size + Math.floor(extras[index]));
      remaining = total - d3.sum(sizes);

      if (remaining > 0) {
        const order = extras
          .map((value, index) => ({index, frac: value - Math.floor(value)}))
          .sort((a, b) => b.frac - a.frac || a.index - b.index);
        for (let i = 0; i < remaining; i += 1) {
          sizes[order[i % order.length].index] += 1;
        }
      }

      return sizes;
    }

    function clampScale(value, maxScale) {
      return Math.max(1, Math.min(maxScale, Number.isFinite(value) ? value : 1));
    }

    function placePiece(occupancy, cols, rows, item, desiredScale) {
      const shape = shapeKeyForRecord(item);
      const rotations = orderedRotations(shape, item);

      for (let scale = desiredScale; scale >= 1; scale -= 1) {
        for (const cells of rotations) {
          const dims = shapeDimensions(cells);
          const width = dims.w * scale;
          const height = dims.h * scale;
          if (width > cols || height > rows) continue;

          for (let y = 0; y <= rows - height; y += 1) {
            for (let x = 0; x <= cols - width; x += 1) {
              if (!fitsShape(occupancy, x, y, cells, scale)) continue;
              stampShape(occupancy, x, y, cells, scale);
              return {shape, cells, scale, x, y};
            }
          }
        }
      }
      return null;
    }

    function orderedRotations(shape, item) {
      const options = SHAPE_ROTATIONS[shape] || [SHAPES.O];
      const start = Math.abs(hashCode(`${item.cdr3}|${item.v}|${item.j}`)) % options.length;
      return options.map((_, index) => options[(index + start) % options.length]);
    }

    function fitsShape(occupancy, x, y, cells, scale) {
      for (const [cx, cy] of cells) {
        for (let yy = 0; yy < scale; yy += 1) {
          for (let xx = 0; xx < scale; xx += 1) {
            if (occupancy[y + cy * scale + yy][x + cx * scale + xx]) return false;
          }
        }
      }
      return true;
    }

    function fitsRect(occupancy, x, y, w, h) {
      for (let yy = 0; yy < h; yy += 1) {
        for (let xx = 0; xx < w; xx += 1) {
          if (occupancy[y + yy][x + xx]) return false;
        }
      }
      return true;
    }

    function stampShape(occupancy, x, y, cells, scale) {
      for (const [cx, cy] of cells) {
        for (let yy = 0; yy < scale; yy += 1) {
          for (let xx = 0; xx < scale; xx += 1) {
            occupancy[y + cy * scale + yy][x + cx * scale + xx] = 1;
          }
        }
      }
    }

    function stampRect(occupancy, x, y, w, h) {
      for (let yy = 0; yy < h; yy += 1) {
        for (let xx = 0; xx < w; xx += 1) {
          occupancy[y + yy][x + xx] = 1;
        }
      }
    }

    function forEachPieceUnit(piece, callback) {
      if (piece.rects && piece.rects.length) {
        piece.rects.forEach((rect) => {
          for (let yy = 0; yy < rect.h; yy += 1) {
            for (let xx = 0; xx < rect.w; xx += 1) {
              callback(piece.x + rect.x + xx, piece.y + rect.y + yy);
            }
          }
        });
        return;
      }

      piece.cells.forEach(([cx, cy]) => {
        for (let yy = 0; yy < piece.scale; yy += 1) {
          for (let xx = 0; xx < piece.scale; xx += 1) {
            callback(piece.x + cx * piece.scale + xx, piece.y + cy * piece.scale + yy);
          }
        }
      });
    }

    function stampPieceId(grid, piece, id) {
      forEachPieceUnit(piece, (gx, gy) => {
        grid[gy][gx] = id;
      });
    }

    function fillRemainingGaps(grid, cols, rows, nextId) {
      const fillers = [];
      for (let y = 0; y < rows; y += 1) {
        let x = 0;
        while (x < cols) {
          if (grid[y][x]) {
            x += 1;
            continue;
          }

          let runEnd = x + 1;
          while (runEnd < cols && !grid[y][runEnd]) runEnd += 1;

          let cursor = x;
          while (cursor < runEnd) {
            const remaining = runEnd - cursor;
            const maxSeg = Math.min(remaining, 8);
            const seg = Math.max(1, Math.min(maxSeg, 2 + (Math.abs(hashCode(`${cursor}|${y}|gap`)) % maxSeg)));
            const filler = {
              _pid: nextId,
              filler: true,
              x: cursor,
              y,
              scale: 1,
              cdr3: `gap-${nextId}`,
              rects: [{x: 0, y: 0, w: seg, h: 1}]
            };
            fillers.push(filler);
            stampPieceId(grid, filler, nextId);
            nextId += 1;
            cursor += seg;
          }

          x = runEnd;
        }
      }
      return fillers;
    }

    function pieceArea(piece) {
      let area = 0;
      forEachPieceUnit(piece, () => { area += 1; });
      return area;
    }

    function adjacentPieceWeights(piece, grid, cols, rows) {
      const weights = new Map();
      const addNeighbor = (id) => {
        if (!id || id === piece._pid) return;
        weights.set(id, (weights.get(id) || 0) + 1);
      };
      forEachPieceUnit(piece, (gx, gy) => {
        if (gx > 0) {
          const left = grid[gy][gx - 1];
          addNeighbor(left);
        }
        if (gx + 1 < cols) {
          const right = grid[gy][gx + 1];
          addNeighbor(right);
        }
        if (gy > 0) {
          const top = grid[gy - 1][gx];
          addNeighbor(top);
        }
        if (gy + 1 < rows) {
          const bottom = grid[gy + 1][gx];
          addNeighbor(bottom);
        }
      });
      return weights;
    }

    function colorDistance(hexA, hexB) {
      const a = d3.lab(hexA);
      const b = d3.lab(hexB);
      return Math.hypot((a.l || 0) - (b.l || 0), (a.a || 0) - (b.a || 0), (a.b || 0) - (b.b || 0));
    }

    function hueDistance(hexA, hexB) {
      const a = d3.hcl(hexA);
      const b = d3.hcl(hexB);
      const hueA = Number.isFinite(a.h) ? a.h : 0;
      const hueB = Number.isFinite(b.h) ? b.h : 0;
      const diff = Math.abs(hueA - hueB) % 360;
      return Math.min(diff, 360 - diff);
    }

    function closestPaletteIndex(color, palette) {
      let bestIndex = 0;
      let bestScore = Infinity;
      for (let i = 0; i < palette.length; i += 1) {
        const distance = colorDistance(color, palette[i]);
        if (distance < bestScore) {
          bestScore = distance;
          bestIndex = i;
        }
      }
      return bestIndex;
    }

    function assignDisplayColors(pieces, grid, cols, rows) {
      const palette = currentPalette();
      const piecesById = new Map(pieces.map((piece) => [piece._pid, piece]));
      const adjacency = new Map(
        pieces.map((piece) => [piece._pid, adjacentPieceWeights(piece, grid, cols, rows)])
      );
      const order = pieces.slice().sort((a, b) => {
        const aTouch = Array.from(adjacency.get(a._pid)?.values() || []).reduce((sum, value) => sum + value, 0);
        const bTouch = Array.from(adjacency.get(b._pid)?.values() || []).reduce((sum, value) => sum + value, 0);
        return bTouch - aTouch || pieceArea(b) - pieceArea(a) || a._pid - b._pid;
      });

      order.forEach((piece) => {
        if (piece.qr && piece.displayColor && !piece.filler) {
          piece.colorIndex = closestPaletteIndex(piece.displayColor, palette);
          return;
        }
        const neighborWeights = adjacency.get(piece._pid) || new Map();

        const seed = Math.abs(hashCode(`${piece.x}|${piece.y}|${piece.cdr3 || piece._pid}`));
        const semanticAnchor = piece.filler ? "#d7ddd2" : pieceColor(piece);
        let bestIndex = 0;
        let bestScore = -Infinity;

        for (let i = 0; i < palette.length; i += 1) {
          const candidate = (seed + i * 7) % palette.length;
          const candidateColor = palette[candidate];
          let score = 0;
          let minNeighborDistance = Infinity;
          let minNeighborHue = Infinity;

          neighborWeights.forEach((touchCount, id) => {
            const neighbor = piecesById.get(id);
            if (!neighbor || !neighbor.displayColor) return;
            const distance = colorDistance(candidateColor, neighbor.displayColor);
            const hueGap = hueDistance(candidateColor, neighbor.displayColor);
            const weight = 1 + Math.min(8, touchCount) * 0.42;

            minNeighborDistance = Math.min(minNeighborDistance, distance);
            minNeighborHue = Math.min(minNeighborHue, hueGap);
            score += distance * weight;
            score += hueGap * 0.18 * weight;

            if (distance < 26) {
              score -= Math.pow(26 - distance, 2) * 0.34 * weight;
            }
            if (hueGap < 24) {
              score -= (24 - hueGap) * 0.95 * weight;
            }
            if (String(neighbor.displayColor).toLowerCase() === candidateColor.toLowerCase()) {
              score -= 36 + touchCount * 10;
            }
          });

          if (Number.isFinite(minNeighborDistance)) {
            score += minNeighborDistance * 2.7;
            score += minNeighborHue * 0.35;
          } else {
            score += 24;
          }

          const anchorDistance = colorDistance(candidateColor, semanticAnchor);
          score += piece.filler
            ? -anchorDistance * 0.05
            : Math.max(0, 54 - anchorDistance) * 0.2;

          if (piece.filler) {
            const muted = d3.hcl(candidateColor);
            score += clamp(76 - muted.c, 0, 42) * 0.65;
            score += clamp(muted.l - 58, 0, 18) * 0.3;
          }

          score += ((seed + candidate * 13) % 17) * 0.01;
          if (score > bestScore) {
            bestScore = score;
            bestIndex = candidate;
          }
        }

        piece.colorIndex = bestIndex;
        piece.displayColor = palette[bestIndex];
      });
    }

    function shapeKeyForRecord(record) {
      if (state.layoutMode === "tetris" && BCR_CHAINS.has(String(record.chain || "").toUpperCase())) {
        const cKey = normalizeCRegion(record.c);
        if (cKey && BCR_C_SHAPE_RULE.shapeByC[cKey]) {
          return BCR_C_SHAPE_RULE.shapeByC[cKey];
        }
      }
      return SHAPE_ORDER[Math.abs(hashCode(`${record.cdr3}|${record.v}|${record.j}|${record.chain}`)) % SHAPE_ORDER.length];
    }

    function buildRotations(cells) {
      const seen = new Set();
      let current = cells;
      const rotations = [];
      for (let i = 0; i < 4; i += 1) {
        const normalized = normalizeCells(current);
        const key = normalized.map(([x, y]) => `${x},${y}`).join("|");
        if (!seen.has(key)) {
          seen.add(key);
          rotations.push(normalized);
        }
        current = current.map(([x, y]) => [y, -x]);
      }
      return rotations;
    }

    function normalizeCells(cells) {
      const minX = d3.min(cells, (d) => d[0]) || 0;
      const minY = d3.min(cells, (d) => d[1]) || 0;
      return cells
        .map(([x, y]) => [x - minX, y - minY])
        .sort((a, b) => (a[1] - b[1]) || (a[0] - b[0]));
    }

    function shapeDimensions(cells) {
      return {
        w: (d3.max(cells, (d) => d[0]) || 0) + 1,
        h: (d3.max(cells, (d) => d[1]) || 0) + 1
      };
    }

    function pieceBounds(piece, cellSize) {
      if (piece.rects && piece.rects.length) {
        return {
          w: d3.max(piece.rects, (d) => (d.x + d.w) * cellSize) || cellSize,
          h: d3.max(piece.rects, (d) => (d.y + d.h) * cellSize) || cellSize
        };
      }
      const dims = shapeDimensions(piece.cells);
      return {
        w: dims.w * piece.scale * cellSize,
        h: dims.h * piece.scale * cellSize
      };
    }

    function pieceHoverTransform(piece, cellSize) {
      const bounds = pieceBounds(piece, cellSize);
      const major = Math.max(bounds.w, bounds.h, 32);
      const scale = clamp(1.05 + 18 / (major + 48), 1.06, 1.16);
      const rise = clamp(cellSize * 1.6, 4, 10);
      const shiftX = bounds.w * (1 - scale) / 2;
      const shiftY = bounds.h * (1 - scale) / 2 - rise;
      return `translate(${shiftX},${shiftY}) scale(${scale})`;
    }

    function pieceColor(record) {
      const base = d3.hcl(pairBaseColor(record));
      const hueShift = ((Math.abs(hashCode(`${record.shape}|${record.cdr3}`)) % 17) - 8) * 1.7;
      base.h = ((base.h || 0) + hueShift + 360) % 360;
      base.c = clamp(base.c + 12, 30, 78);
      base.l = clamp(62 + Math.min(12, Math.log2((record.copy || 1) + 1) * 1.6), 56, 80);
      return base.formatHex();
    }

    function groupColor(name) {
      return paletteColor(name, currentPalette());
    }

    function jColor(name) {
      return paletteColor(`j:${name}`, currentPalette());
    }

    function pairBaseColor(record) {
      const mixed = d3.interpolateLab(groupColor(record.v || record.name || "V?"), jColor(record.j || "J?"))(0.5);
      const c = d3.hcl(mixed);
      c.c = clamp(c.c + 10, 26, 68);
      c.l = clamp(c.l + 6, 56, 80);
      return c.formatHex();
    }

    function paletteColor(key, palette) {
      return palette[Math.abs(hashCode(String(key || ""))) % palette.length];
    }
    function normalizeCRegion(value) {
      const text = String(value || "").trim().toUpperCase().replace(/\\s+/g, "");
      return text ? text.replace(/\\*.*$/, "") : "";
    }
    function displayCLabel(record) {
      const raw = String(record.c || "").trim();
      if (raw) return raw;
      const normalized = normalizeCRegion(record.c);
      return normalized || "NA";
    }
    function buildBcrCShapeRule(records) {
      const totals = new Map();
      const labels = new Map();
      records.forEach((record) => {
        const chain = String(record.chain || "").toUpperCase();
        if (!BCR_CHAINS.has(chain)) return;
        const cKey = normalizeCRegion(record.c) || "C?";
        const cLabel = String(record.c || "").trim() || cKey;
        totals.set(cKey, (totals.get(cKey) || 0) + Number(record.copy || 0));
        if (!labels.has(cKey)) labels.set(cKey, cLabel);
      });
      const entries = Array.from(totals.entries())
        .sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0], undefined, {numeric: true, sensitivity: "base"}))
        .map(([cKey], index) => ({
          cKey,
          label: labels.get(cKey) || cKey,
          shape: SHAPE_ORDER[index % SHAPE_ORDER.length],
          reused: index >= SHAPE_ORDER.length
        }));
      const shapeByC = Object.fromEntries(entries.map((entry) => [entry.cKey, entry.shape]));
      return {
        entries,
        shapeByC,
        hasOverflow: entries.length > SHAPE_ORDER.length
      };
    }
    function displayShapeLabel(record) {
      return state.layoutMode === "qr" ? "QR" : shapeKeyForRecord(record);
    }
    function showTip(event, d) {
      tooltip.innerHTML = `<h3>${esc(d.cdr3)}</h3><dl class="tip-grid">
        <dt>序号</dt><dd>${fmtInt(d.displayRank || 0)}</dd>
        <dt>copy</dt><dd>${fmtInt(d.copy)}</dd>
        <dt>C</dt><dd>${esc(displayCLabel(d))}</dd>
        <dt>shape</dt><dd>${esc(displayShapeLabel(d))}</dd>
        <dt>V</dt><dd>${esc(d.v)}</dd>
        <dt>J</dt><dd>${esc(d.j)}</dd>
      </dl>`;
      tooltip.classList.add("visible");
      moveTip(event);
    }
    function moveTip(event) {
      const w = tooltip.offsetWidth || 260, h = tooltip.offsetHeight || 180, o = 18;
      tooltip.style.left = `${Math.max(12, Math.min(window.innerWidth - w - 12, event.clientX + o))}px`;
      tooltip.style.top = `${Math.max(12, Math.min(window.innerHeight - h - 12, event.clientY + o))}px`;
    }
    function hideTip() { tooltip.classList.remove("visible"); }
    function miniShapeSvg(shape) {
      const cells = SHAPES[shape];
      const dims = shapeDimensions(cells);
      const size = 8;
      const fill = paletteColor(shape, currentPalette());
      const blocks = cells.map(([x, y]) =>
        `<rect x="${x * size + 4}" y="${y * size + 3}" width="${size}" height="${size}" rx="2" ry="2" fill="${fill}" stroke="rgba(0,0,0,.25)" stroke-width="1"></rect>`
      ).join("");
      return `<svg class="legend-shape" viewBox="0 0 ${(dims.w + 1) * size} ${(dims.h + 1) * size}" aria-hidden="true">${blocks}</svg>`;
    }
    function geneSort(a, b) { return String(a || "").localeCompare(String(b || ""), undefined, {numeric:true,sensitivity:"base"}); }
    function fitText(text, limit) { return !limit || text.length <= limit ? text : `${text.slice(0, Math.max(3, limit - 3))}...`; }
    function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
    function fmtInt(v) { return new Intl.NumberFormat("zh-CN", {maximumFractionDigits:0}).format(v); }
    function fmtPct(v) { return `${(v * 100).toFixed(v >= .1 ? 1 : 2)}%`; }
    function esc(v) { return String(v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;"); }
    function hashCode(text) { let h = 0; for (let i = 0; i < text.length; i += 1) h = ((h << 5) - h + text.charCodeAt(i)) | 0; return h; }
    function hashHue(text) { return Math.abs(hashCode(text)) % 360; }
    function hexToRgba(hex, alpha) { const c = d3.color(hex); return `rgba(${c.r}, ${c.g}, ${c.b}, ${alpha})`; }
    function textColor(hex) { const c = d3.color(hex); const y = (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255; return y > .66 ? "#151410" : "#fffef9"; }
    function currentPalette() { return TREEMAP_REFERENCE_PALETTE; }

    function groupColor(name) {
      return paletteColor(name, currentPalette());
    }
    
    function jColor(name) {
      return paletteColor(`j:${name}`, currentPalette());
    }
    
    function pairBaseColor(record) {
      const mixed = d3.interpolateLab(groupColor(record.v || record.name || "V?"), jColor(record.j || "J?"))(0.5);
      const c = d3.hcl(mixed);
      c.c = clamp(c.c + 18, 42, 84);
      c.l = clamp(c.l + 8, 56, 80);
      return c.formatHex();
    }
    
    function pieceColor(record) {
      const base = d3.hcl(pairBaseColor(record));
      const hueShift = ((Math.abs(hashCode(`${record.shape}|${record.cdr3}`)) % 17) - 8) * 2.2;
      base.h = ((base.h || 0) + hueShift + 360) % 360;
      base.c = clamp(base.c + 22, 48, 88);
      base.l = clamp(60 + Math.min(14, Math.log2((record.copy || 1) + 1) * 2.2), 54, 82);
      return base.formatHex();
    }
    
    function miniShapeSvg(shape) {
      const cells = SHAPES[shape];
      const dims = shapeDimensions(cells);
      const size = 8;
      const fill = paletteColor(shape, currentPalette());
      const blocks = cells.map(([x, y]) =>
        `<rect x="${x * size + 4}" y="${y * size + 3}" width="${size}" height="${size}" rx="2" ry="2" fill="${fill}" stroke="rgba(0,0,0,.25)" stroke-width="1"></rect>`
      ).join("");
      return `<svg class="legend-shape" viewBox="0 0 ${(dims.w + 1) * size} ${(dims.h + 1) * size}" aria-hidden="true">${blocks}</svg>`;
    }

    function miniQrSvg(w, h, key) {
      const size = 7;
      const width = w * size + 8;
      const height = h * size + 8;
      const fill = paletteColor(key, currentPalette());
      const radius = Math.min(6, Math.max(2, Math.min(w * size, h * size) * 0.18));
      return `<svg class="legend-shape" viewBox="0 0 ${width} ${height}" aria-hidden="true"><rect x="4" y="4" width="${w * size}" height="${h * size}" rx="${radius}" ry="${radius}" fill="${fill}" stroke="rgba(0,0,0,.18)" stroke-width="1"></rect></svg>`;
    }
  </script>
</body>
</html>
"""


def build_html(
    clones: list[dict[str, Any]],
    summary: dict[str, Any],
    title: str,
    source_name: str,
    columns: dict[str, str | None],
    default_min_copy: int,
    top_n: int,
    style: str = "classic",
    layout_mode: str = "tetris",
    canvas_shape: str = "square",
) -> str:
    max_copy = int(max((float(item["copy"]) for item in clones), default=0))
    settings = {
        "title": title,
        "sourceName": source_name,
        "columns": columns,
        "summary": {
            **summary,
            "total_copy": int(summary["total_copy"])
            if math.isclose(summary["total_copy"], round(summary["total_copy"]))
            else round(summary["total_copy"], 4),
        },
        "defaultMinCopy": min(default_min_copy, max_copy),
        "topN": top_n,
        "maxCopy": max_copy,
        "style": style,
        "layoutMode": layout_mode,
        "canvasShape": canvas_shape,
    }
    html = HTML_TEMPLATE.replace("__PAGE_TITLE__", escape_html_text(title))
    html = html.replace("__D3_SCRIPT__", load_d3_script_tag())
    html = html.replace("__DATA_JSON__", json.dumps(clones, ensure_ascii=False))
    html = html.replace("__SETTINGS_JSON__", json.dumps(settings, ensure_ascii=False))
    return html


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据 repertoire pep 数据生成可交互 clonotype treemap HTML。"
    )
    parser.add_argument("input", help="输入文件路径，支持 csv/csv.gz/tsv/tsv.gz")
    parser.add_argument(
        "-o", "--output", help="输出 HTML 路径，默认与输入同目录同名后缀 _treemap.html"
    )
    parser.add_argument("--title", help="页面标题")
    parser.add_argument(
        "--min-copy-default", type=int, default=30, help="默认表达量阈值"
    )
    parser.add_argument(
        "--top-n", type=int, default=100, help="旁侧表格显示的 top N 条目"
    )
    parser.add_argument("--cdr3-column", help="显式指定 CDR3 列名")
    parser.add_argument("--copy-column", help="显式指定 copy 列名")
    parser.add_argument("--v-column", help="显式指定 V 列名")
    parser.add_argument("--j-column", help="显式指定 J 列名")
    parser.add_argument("--c-column", help="显式指定 C 列名")
    parser.add_argument("--chain-column", help="显式指定 chain 列名")
    parser.add_argument("--cell-column", help="显式指定细胞类型列名")
    parser.add_argument(
        "--canvas-shape",
        choices=["square", "portrait"],
        default="square",
        help="输出画布形状",
    )
    return parser.parse_args()


def derive_output_path(input_path: Path, output: str | None) -> Path:
    if output:
        return Path(output).expanduser().resolve()
    if input_path.suffix.lower() == ".gz":
        inner = input_path.with_suffix("")
        return inner.with_name(f"{inner.stem}_treemap.html")
    return input_path.with_name(f"{input_path.stem}_treemap.html")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"输入文件不存在: {input_path}", file=sys.stderr)
        return 1

    with open_text_file(input_path) as handle:
        sample = handle.read(4096)
        handle.seek(0)
        reader = csv.DictReader(handle, dialect=detect_dialect(sample))
        fieldnames = reader.fieldnames or []
    if not fieldnames:
        print("未检测到表头，无法继续。", file=sys.stderr)
        return 1

    column_overrides = {
        "cdr3": args.cdr3_column,
        "copy": args.copy_column,
        "v": args.v_column,
        "j": args.j_column,
        "c": args.c_column,
        "chain": args.chain_column,
        "cell_type": args.cell_column,
    }
    try:
        columns = detect_columns(fieldnames, column_overrides)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not columns["cdr3"] or not columns["copy"]:
        print(
            "至少需要识别到 CDR3 列和 copy 列。可通过 --cdr3-column / --copy-column 手工指定。",
            file=sys.stderr,
        )
        return 1

    clones, summary = read_repertoire(input_path, columns)
    if not clones:
        print("没有读到有效 clone 数据，请检查输入文件。", file=sys.stderr)
        return 1

    output_path = derive_output_path(input_path, args.output)
    html = build_html(
        clones=clones,
        summary=summary,
        title=make_title(input_path, args.title),
        source_name=input_path.name,
        columns=columns,
        default_min_copy=max(0, args.min_copy_default),
        top_n=max(1, args.top_n),
        canvas_shape=args.canvas_shape,
    )
    output_path.write_text(html, encoding="utf-8")

    print(f"HTML generated: {output_path}")
    print(f"Clones: {summary['total_clones']}, total copy: {summary['total_copy']}")
    print(f"Detected columns: {json.dumps(columns, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
