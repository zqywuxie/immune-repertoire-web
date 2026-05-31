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
    "cdr3": ["cdr3(pep)", "cdr3_pep", "cdr3pep", "cdr3aa", "cdr3_aa", "cdr3", "aa_cdr3"],
    "copy": ["copy", "copies", "count", "clonecount", "clone_count", "readcount", "read_count", "reads", "umis", "umi"],
    "v": ["v", "vgene", "v_gene", "bestvgene", "v_call"],
    "j": ["j", "jgene", "j_gene", "bestjgene", "j_call"],
    "c": ["c", "cgene", "c_gene", "constant", "constant_gene", "isotype"],
    "chain": ["chain", "chain_type", "receptor_chain", "locus"],
    "cell_type": ["cell_type", "celltype", "lymphocyte_type", "receptor_type"],
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


def detect_columns(fieldnames: list[str], overrides: dict[str, str | None]) -> dict[str, str | None]:
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


def read_repertoire(path: Path, columns: dict[str, str | None]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    aggregated: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
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
            cdr3 = clean_text(row.get(columns["cdr3"] or "", "") if columns["cdr3"] else "")
            if not cdr3:
                stats["skipped_missing_cdr3"] += 1
                continue

            copy_value = parse_copy(row.get(columns["copy"] or "", "") if columns["copy"] else "")
            if copy_value is None or copy_value <= 0:
                stats["skipped_missing_copy"] += 1
                continue

            v = clean_text(row.get(columns["v"] or "", "") if columns["v"] else "") or "V?"
            j = clean_text(row.get(columns["j"] or "", "") if columns["j"] else "") or "J?"
            c = clean_text(row.get(columns["c"] or "", "") if columns["c"] else "")
            raw_chain = clean_text(row.get(columns["chain"] or "", "") if columns["chain"] else "")
            raw_cell_type = clean_text(row.get(columns["cell_type"] or "", "") if columns["cell_type"] else "")

            chain = infer_chain(raw_chain, c, v, j)
            cell_type = infer_cell_type(raw_cell_type, chain)
            key = (cell_type, chain, v, j, cdr3)

            if key not in aggregated:
                aggregated[key] = {
                    "cdr3": cdr3,
                    "copy": 0.0,
                    "v": v,
                    "j": j,
                    "c": c,
                    "chain": chain,
                    "cell_type": cell_type,
                    "row_count": 0,
                }

            aggregated[key]["copy"] += copy_value
            aggregated[key]["row_count"] += 1
            if c and not aggregated[key]["c"]:
                aggregated[key]["c"] = c
            stats["used_rows"] += 1

    clones = list(aggregated.values())
    clones.sort(key=lambda item: (-item["copy"], item["chain"], item["v"], item["j"], item["cdr3"]))
    total_copy = sum(float(item["copy"]) for item in clones)
    for item in clones:
        copy_value = float(item["copy"])
        item["copy"] = int(copy_value) if math.isclose(copy_value, round(copy_value)) else round(copy_value, 4)
        item["frequency"] = (copy_value / total_copy) if total_copy else 0.0
        item["vj_pair"] = vj_pair_name(item["v"], item["j"])

    summary = {"total_clones": len(clones), "total_copy": total_copy, **stats}
    return clones, summary


def escape_html_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


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
          <label>俄罗斯方块形状</label>
          <div class="legend" id="legend"></div>
        </div>
      </div>
    </section>
    <section class="layout">
      <div class="card chart-panel">
        <div class="panel-head">
          <div><h2>Clone Matrix</h2><p>按 V/J gene 分层后连续拼接成矩阵，每个 clone 用一个 tetromino 表示</p></div>
          <p id="chartHint"></p>
        </div>
        <svg id="treemap" viewBox="0 0 960 960" preserveAspectRatio="xMidYMid meet"></svg>
      </div>
      <div class="card table-panel">
        <div class="panel-head">
          <div><h2>Top 100 Clones</h2><p>右侧列出当前阈值下丰度最高的 clone，并标记其方块类型</p></div>
          <p id="tableHint"></p>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>#</th><th>CDR3</th><th>copy</th><th>freq</th><th>V</th><th>J</th></tr></thead>
            <tbody id="topTableBody"></tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
  <div class="tooltip" id="tooltip"></div>
  <script>
    const mode = new URLSearchParams(window.location.search).get("mode");
    const panelMode = mode === "panel" || mode === "panel-fill";
    const panelFillMode = mode === "panel-fill";
    if (panelMode) document.body.classList.add("panel-mode");
    const CLONES = __DATA_JSON__;
    const SETTINGS = __SETTINGS_JSON__;
    const VISUAL_LIMIT = 1800;
    const MATRIX_W = 960;
    const MATRIX_H = 960;
    const VIVID_PALETTE = ["#ef84c2","#61e72a","#fff36b","#4be4df","#4890ef","#ff6458","#d4008f","#8d18ff","#41b39e","#ffd87f","#d7ff6d","#ff941c","#2d67d7","#ffb4b4","#cfd3d8"];
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
    const state = {threshold: SETTINGS.defaultMinCopy};
    const svg = d3.select("#treemap");
    if (panelFillMode) {
      svg.attr("preserveAspectRatio", "none");
    }
    const tooltip = document.getElementById("tooltip");
    const thresholdSlider = document.getElementById("thresholdSlider");
    const thresholdInput = document.getElementById("thresholdInput");
    const topTableBody = document.getElementById("topTableBody");
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
    renderMeta();
    renderLegend();
    setThreshold(state.threshold);

    function setThreshold(v) {
      state.threshold = Math.max(0, Math.min(SETTINGS.maxCopy, Math.round(Number.isFinite(v) ? v : 0)));
      thresholdSlider.value = String(state.threshold);
      thresholdInput.value = String(state.threshold);
      safeRender();
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
        `V gene ${fmtInt(vGeneCount)}`,
        `J gene ${fmtInt(jGeneCount)}`,
        `VJ pair ${fmtInt(vjPairCount)}`
      ];
      meta.innerHTML = items.map((text) => `<span class="pill">${esc(text)}</span>`).join("");
    }

    function renderLegend() {
      document.getElementById("legend").innerHTML = SHAPE_ORDER.map((shape) =>
        `<div class="legend-item">${miniShapeSvg(shape)}<span>${shape}</span></div>`
      ).join("");
    }

    function render() {
      const filtered = CLONES
        .filter((d) => d.copy >= state.threshold)
        .sort((a, b) => b.copy - a.copy || geneSort(a.v, b.v) || a.cdr3.localeCompare(b.cdr3));
      const filteredTotal = d3.sum(filtered, (d) => d.copy);
      const visualRecords = filtered.length > VISUAL_LIMIT ? filtered.slice(0, VISUAL_LIMIT) : filtered;
      const layout = computeGroupLayout(visualRecords);
      document.getElementById("filteredCloneCount").textContent = fmtInt(filtered.length);
      document.getElementById("filteredCopyTotal").textContent = fmtInt(filteredTotal);
      document.getElementById("chartHint").textContent = "";
      document.getElementById("tableHint").textContent = filtered.length
        ? `阈值 >= ${fmtInt(state.threshold)}`
        : "Top 100 为空";
      renderTable(filtered, filteredTotal);
      renderPuzzle(layout, filtered.length > VISUAL_LIMIT ? filtered.length - VISUAL_LIMIT : 0);
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
        .attr("x", 600)
        .attr("y", 360)
        .attr("text-anchor", "middle")
        .text("页面渲染失败");
      svg.append("text")
        .attr("x", 600)
        .attr("y", 390)
        .attr("text-anchor", "middle")
        .attr("font-size", 12)
        .attr("fill", "#8b3a2d")
        .text(fitText(message, 90));
    }

    function renderTable(records, totalCopy) {
      const top = records.slice(0, SETTINGS.topN);
      topTableBody.innerHTML = top.length ? top.map((d, i) => `
        <tr>
          <td>${i + 1}</td>
          <td class="cdr3">${esc(d.cdr3)}</td>
          <td>${fmtInt(d.copy)}</td>
          <td>${fmtPct(totalCopy ? d.copy / totalCopy : d.frequency)}</td>
          <td>${esc(d.v || "V?")}</td>
          <td>${esc(d.j || "J?")}</td>
        </tr>
      `).join("") : `<tr><td colspan="6" style="padding:16px;color:#6a6258">当前阈值下无 clone。</td></tr>`;
    }

    function renderPuzzle(layout, hiddenCount) {
      svg.selectAll("*").remove();
      if (!layout.placed.length) {
        svg.append("text").attr("class", "empty").attr("x", 600).attr("y", 380).attr("text-anchor", "middle").text("当前阈值下没有可显示的 clone");
        return;
      }

      const root = svg.append("g");
      layout.placed.forEach((piece) => drawPiece(root, piece, layout.cellSize));

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
      const pieceGroup = parent.append("g")
        .attr("transform", `translate(${piece.x * cellSize},${piece.y * cellSize})`);
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
          body.append("rect")
            .attr("x", rect.x * cellSize - 0.15)
            .attr("y", rect.y * cellSize - 0.15)
            .attr("width", rect.w * cellSize + 0.3)
            .attr("height", rect.h * cellSize + 0.3)
            .attr("fill", fill)
            .attr("shape-rendering", "crispEdges");
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

      const pairTotals = new Map();
      records.forEach((record) => {
        const key = `${record.v || "V?"}|${record.j || "J?"}`;
        pairTotals.set(key, (pairTotals.get(key) || 0) + record.copy);
      });

      const ordered = records.slice().sort((a, b) => {
        const pairA = `${a.v || "V?"}|${a.j || "J?"}`;
        const pairB = `${b.v || "V?"}|${b.j || "J?"}`;
        return (pairTotals.get(pairB) || 0) - (pairTotals.get(pairA) || 0)
          || geneSort(a.v, b.v)
          || geneSort(a.j, b.j)
          || b.copy - a.copy
          || a.cdr3.localeCompare(b.cdr3);
      });

      return packMatrix(ordered, MATRIX_W, MATRIX_H);
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

    function stampShape(occupancy, x, y, cells, scale) {
      for (const [cx, cy] of cells) {
        for (let yy = 0; yy < scale; yy += 1) {
          for (let xx = 0; xx < scale; xx += 1) {
            occupancy[y + cy * scale + yy][x + cx * scale + xx] = 1;
          }
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

    function adjacentPieceIds(piece, grid, cols, rows) {
      const ids = new Set();
      forEachPieceUnit(piece, (gx, gy) => {
        if (gx > 0) {
          const left = grid[gy][gx - 1];
          if (left && left !== piece._pid) ids.add(left);
        }
        if (gx + 1 < cols) {
          const right = grid[gy][gx + 1];
          if (right && right !== piece._pid) ids.add(right);
        }
        if (gy > 0) {
          const top = grid[gy - 1][gx];
          if (top && top !== piece._pid) ids.add(top);
        }
        if (gy + 1 < rows) {
          const bottom = grid[gy + 1][gx];
          if (bottom && bottom !== piece._pid) ids.add(bottom);
        }
      });
      return ids;
    }

    function assignDisplayColors(pieces, grid, cols, rows) {
      const piecesById = new Map(pieces.map((piece) => [piece._pid, piece]));
      const order = pieces.slice().sort((a, b) => pieceArea(b) - pieceArea(a) || a._pid - b._pid);

      order.forEach((piece) => {
        const neighborIds = adjacentPieceIds(piece, grid, cols, rows);
        const used = new Set();
        neighborIds.forEach((id) => {
          const neighbor = piecesById.get(id);
          if (neighbor && Number.isInteger(neighbor.colorIndex)) used.add(neighbor.colorIndex);
        });

        const seed = Math.abs(hashCode(`${piece.x}|${piece.y}|${piece.cdr3 || piece._pid}`));
        let bestIndex = 0;
        let bestScore = -Infinity;

        for (let i = 0; i < VIVID_PALETTE.length; i += 1) {
          const candidate = (seed + i * 7) % VIVID_PALETTE.length;
          let score = used.has(candidate) ? -100 : 0;
          neighborIds.forEach((id) => {
            const neighbor = piecesById.get(id);
            if (!neighbor || !Number.isInteger(neighbor.colorIndex)) return;
            const dist = Math.abs(candidate - neighbor.colorIndex);
            score += Math.min(dist, VIVID_PALETTE.length - dist);
          });
          if (piece.filler) score += candidate % 2 === 0 ? 1 : 0;
          if (score > bestScore) {
            bestScore = score;
            bestIndex = candidate;
          }
        }

        piece.colorIndex = bestIndex;
        piece.displayColor = VIVID_PALETTE[bestIndex];
      });
    }

    function shapeKeyForRecord(record) {
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
      const hueShift = ((Math.abs(hashCode(`${record.shape}|${record.cdr3}`)) % 17) - 8) * 2.2;
      base.h = ((base.h || 0) + hueShift + 360) % 360;
      base.c = clamp(base.c + 22, 48, 88);
      base.l = clamp(60 + Math.min(14, Math.log2((record.copy || 1) + 1) * 2.2), 54, 82);
      return base.formatHex();
    }

    function groupColor(name) {
      return paletteColor(name, VIVID_PALETTE);
    }

    function jColor(name) {
      return paletteColor(`j:${name}`, VIVID_PALETTE);
    }

    function pairBaseColor(record) {
      const mixed = d3.interpolateLab(groupColor(record.v || record.name || "V?"), jColor(record.j || "J?"))(0.5);
      const c = d3.hcl(mixed);
      c.c = clamp(c.c + 18, 42, 84);
      c.l = clamp(c.l + 8, 56, 80);
      return c.formatHex();
    }

    function paletteColor(key, palette) {
      return palette[Math.abs(hashCode(String(key || ""))) % palette.length];
    }
    function showTip(event, d) {
      tooltip.innerHTML = `<h3>${esc(d.cdr3)}</h3><dl class="tip-grid">
        <dt>copy</dt><dd>${fmtInt(d.copy)}</dd>
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
      const fill = paletteColor(shape, VIVID_PALETTE);
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
) -> str:
    max_copy = int(max((float(item["copy"]) for item in clones), default=0))
    settings = {
        "title": title,
        "sourceName": source_name,
        "columns": columns,
        "summary": {
            **summary,
            "total_copy": int(summary["total_copy"]) if math.isclose(summary["total_copy"], round(summary["total_copy"])) else round(summary["total_copy"], 4),
        },
        "defaultMinCopy": min(default_min_copy, max_copy),
        "topN": top_n,
        "maxCopy": max_copy,
    }
    html = HTML_TEMPLATE.replace("__PAGE_TITLE__", escape_html_text(title))
    html = html.replace("__D3_SCRIPT__", load_d3_script_tag())
    html = html.replace("__DATA_JSON__", json.dumps(clones, ensure_ascii=False))
    html = html.replace("__SETTINGS_JSON__", json.dumps(settings, ensure_ascii=False))
    return html


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 repertoire pep 数据生成可交互 clonotype treemap HTML。")
    parser.add_argument("input", help="输入文件路径，支持 csv/csv.gz/tsv/tsv.gz")
    parser.add_argument("-o", "--output", help="输出 HTML 路径，默认与输入同目录同名后缀 _treemap.html")
    parser.add_argument("--title", help="页面标题")
    parser.add_argument("--min-copy-default", type=int, default=30, help="默认表达量阈值")
    parser.add_argument("--top-n", type=int, default=100, help="旁侧表格显示的 top N 条目")
    parser.add_argument("--cdr3-column", help="显式指定 CDR3 列名")
    parser.add_argument("--copy-column", help="显式指定 copy 列名")
    parser.add_argument("--v-column", help="显式指定 V 列名")
    parser.add_argument("--j-column", help="显式指定 J 列名")
    parser.add_argument("--c-column", help="显式指定 C 列名")
    parser.add_argument("--chain-column", help="显式指定 chain 列名")
    parser.add_argument("--cell-column", help="显式指定细胞类型列名")
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
        print("至少需要识别到 CDR3 列和 copy 列。可通过 --cdr3-column / --copy-column 手工指定。", file=sys.stderr)
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
    )
    output_path.write_text(html, encoding="utf-8")

    print(f"HTML generated: {output_path}")
    print(f"Clones: {summary['total_clones']}, total copy: {summary['total_copy']}")
    print(f"Detected columns: {json.dumps(columns, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
