"""
Treemap report service.

Generates PNG outputs per sample under:
<results_root>/treemap_report/<job_id>/<sample>/
  individual_treemaps/
    PNG/
  7chain_treemaps/
    PNG/
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PIL import Image

from flask_app.exceptions import ValidationError
from flask_app.services.auto_heatmap_service import get_auto_heatmap_service
from flask_app.services.treemap_plotter import build_treemap_layout, render_treemap_layout
from flask_app.services.treemap_renderer import (
    detect_columns,
    detect_dialect,
    open_text_file,
    read_repertoire,
    read_repertoire_rows,
)

logger = logging.getLogger(__name__)


CHAIN_ORDER_TCR = ["TRA", "TRB", "TRD", "TRG"]
CHAIN_ORDER_BCR = ["IGH", "IGK", "IGL"]
CHAIN_ORDER_ALL = CHAIN_ORDER_TCR + CHAIN_ORDER_BCR
OVERVIEW_ORDER_TCR = ["TRA", "TRB", "TRD", "TRG"]
OVERVIEW_ORDER_BCR = ["IGK", "IGH", "IGL"]
TOP_CHAIN_WEIGHTS = {"TRA": 1.75, "TRB": 1.75, "TRD": 0.75, "TRG": 0.75}
BOTTOM_CHAIN_WEIGHTS = {"IGK": 0.9, "IGH": 1.55, "IGL": 0.9}
CHAIN_CELL_MAP = {
    "IGH": "B cell",
    "IGK": "B cell",
    "IGL": "B cell",
    "TRA": "T cell",
    "TRB": "T cell",
    "TRD": "T cell",
    "TRG": "T cell",
}
@dataclass
class TreemapReportResult:
    job_id: str
    output_base: Path
    metadata_path: Path
    metadata: Dict[str, Any]


class TreemapReportService:
    _RESULT_DIR = "treemap_report"
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
        return f"treemap_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

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
        return normalized if normalized in CHAIN_ORDER_ALL else None

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
            if chain and filepath and chain in selected:
                chain_files[chain] = filepath
        return chain_files

    @staticmethod
    def _detect_columns_for_path(path: Path, overrides: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        with open_text_file(path) as handle:
            sample = handle.read(4096)
            handle.seek(0)
            reader = csv.DictReader(handle, dialect=detect_dialect(sample))
            fieldnames = reader.fieldnames or []

        if not fieldnames:
            raise ValidationError(message=f"文件缺少表头: {path.name}")

        try:
            return detect_columns(fieldnames, overrides)
        except ValueError as exc:
            raise ValidationError(message=str(exc)) from exc

    @staticmethod
    def _weights_to_grid_template(chains: List[str], weights: Dict[str, float]) -> str:
        return " ".join(f"minmax(0, {weights.get(chain, 1.0)}fr)" for chain in chains)

    @staticmethod
    def _weighted_boxes(
        chains: List[str],
        weights: Dict[str, float],
        start: int,
        end: int,
    ) -> Dict[str, tuple[int, int]]:
        total = sum(weights.get(chain, 1.0) for chain in chains) or 1.0
        current = start
        boxes: Dict[str, tuple[int, int]] = {}
        for idx, chain in enumerate(chains):
            if idx == len(chains) - 1:
                next_pos = end
            else:
                width = int(round((end - start) * (weights.get(chain, 1.0) / total)))
                next_pos = min(end, current + max(1, width))
            boxes[chain] = (current, next_pos)
            current = next_pos
        return boxes

    def _sample_dirs(self, output_base: Path, sample_safe_name: str) -> Dict[str, Path]:
        sample_root = output_base / sample_safe_name
        paths = {
            "sample_root": sample_root,
            "individual_png": sample_root / "individual_treemaps" / "PNG",
            "individual_json": sample_root / "individual_treemaps" / "JSON",
            "topclone_csv": sample_root / "topclone" / "CSV",
            "topclone_json": sample_root / "topclone" / "JSON",
            "overview_png": sample_root / "7chain_treemaps" / "PNG",
        }
        for path in paths.values():
            if path is not sample_root:
                path.mkdir(parents=True, exist_ok=True)
        return paths

    @staticmethod
    def _write_topclone_csv(
        topclone_rows: List[Dict[str, Any]],
        output_path: Path,
        top_n: int,
    ) -> None:
        fieldnames = ["CDR3(pep)", "joinedSeq", "V", "D", "J", "C", "copy"]
        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for clone in topclone_rows[: max(1, int(top_n))]:
                writer.writerow(
                    {
                        "CDR3(pep)": clone.get("cdr3", ""),
                        "joinedSeq": clone.get("joined_seq", ""),
                        "V": clone.get("v", ""),
                        "D": clone.get("d", ""),
                        "J": clone.get("j", ""),
                        "C": clone.get("c", ""),
                        "copy": clone.get("copy", ""),
                    }
                )

    @staticmethod
    def _clone_id(clone: Dict[str, Any]) -> str:
        return f"{clone.get('v', '')}|{clone.get('j', '')}|{clone.get('cdr3', '')}"

    @staticmethod
    def _write_topclone_json(
        topclone_rows: List[Dict[str, Any]],
        output_path: Path,
        top_n: int,
    ) -> None:
        rows: List[Dict[str, Any]] = []
        for index, clone in enumerate(topclone_rows[: max(1, int(top_n))], start=1):
            rows.append(
                {
                    "clone_id": TreemapReportService._clone_id(clone),
                    "rank": index,
                    "cdr3": clone.get("cdr3", ""),
                    "joined_seq": clone.get("joined_seq", ""),
                    "v": clone.get("v", ""),
                    "d": clone.get("d", ""),
                    "j": clone.get("j", ""),
                    "c": clone.get("c", ""),
                    "copy": clone.get("copy", ""),
                }
            )
        output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _compose_overview_png_from_individuals(
        chain_png_paths: Dict[str, Path],
        output_path: Path,
        canvas_size: int = 3600,
        top_ratio: float = 0.17,
        line_width: int = 10,
    ) -> None:
        canvas = Image.new("RGB", (canvas_size, canvas_size), "white")
        draw_color = (0, 0, 0)
        top_height = int(canvas_size * top_ratio)
        bottom_height = canvas_size - top_height

        def fit_and_paste(img_path: Optional[Path], box: tuple[int, int, int, int]) -> None:
            x0, y0, x1, y1 = box
            if not img_path or not img_path.exists():
                return
            image = Image.open(img_path).convert("RGB")
            target_w = max(1, x1 - x0)
            target_h = max(1, y1 - y0)
            resized = image.resize((target_w, target_h), Image.Resampling.LANCZOS)
            canvas.paste(resized, (x0, y0))

        top_boxes = TreemapReportService._weighted_boxes(OVERVIEW_ORDER_TCR, TOP_CHAIN_WEIGHTS, 0, canvas_size)
        for chain in OVERVIEW_ORDER_TCR:
            x0, x1 = top_boxes[chain]
            fit_and_paste(chain_png_paths.get(chain), (x0, 0, x1, top_height))

        bottom_boxes = TreemapReportService._weighted_boxes(OVERVIEW_ORDER_BCR, BOTTOM_CHAIN_WEIGHTS, 0, canvas_size)
        for chain in OVERVIEW_ORDER_BCR:
            x0, x1 = bottom_boxes[chain]
            fit_and_paste(chain_png_paths.get(chain), (x0, top_height, x1, canvas_size))

        from PIL import ImageDraw
        draw = ImageDraw.Draw(canvas)
        half = max(1, line_width // 2)
        draw.line((0, top_height, canvas_size, top_height), fill=draw_color, width=line_width)
        for chain in OVERVIEW_ORDER_TCR[:-1]:
            x = top_boxes[chain][1]
            draw.line((x, 0, x, top_height), fill=draw_color, width=line_width)
        for chain in OVERVIEW_ORDER_BCR[:-1]:
            x = bottom_boxes[chain][1]
            draw.line((x, top_height, x, canvas_size), fill=draw_color, width=line_width)
        draw.rectangle((0, 0, canvas_size - 1, canvas_size - 1), outline=draw_color, width=line_width)
        canvas.save(output_path)

    @staticmethod
    def _build_interactive_viewer_html(viewer_payload: Dict[str, Any]) -> str:
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Treemap Viewer</title>
  <style>
    *{box-sizing:border-box}
    :root{--bg:#edf3f6;--panel:#fff;--ink:#142033;--muted:#617086;--line:#d8e2ea;--accent:#0f766e;--accent2:#be6b16;--soft:#f6f9fb;--shadow:0 18px 42px rgba(31,45,61,.13)}
    body{margin:0;font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink)}
    .app{display:grid;grid-template-columns:380px minmax(0,1fr);min-height:100vh}
    .sidebar{display:flex;flex-direction:column;gap:14px;padding:18px;border-right:1px solid var(--line);background:linear-gradient(180deg,#fff,#f7fafc)}
    .head h1{margin:0 0 6px;font-size:22px;font-weight:750}.head p{margin:0;color:var(--muted);font-size:13px;line-height:1.5}
    .stack{display:grid;gap:11px}.field{display:grid;gap:7px}label{font-size:12px;font-weight:750;color:#44556b}
    select,input{width:100%;height:38px;padding:0 11px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);font-size:13px;outline:none}
    select:focus,input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(15,118,110,.13)}
    .seg{display:grid;grid-template-columns:1fr 1fr;padding:3px;border:1px solid var(--line);border-radius:9px;background:#fff}
    .seg button{height:34px;border:0;border-radius:7px;background:transparent;color:#506075;font-weight:750;cursor:pointer}.seg button.active{background:var(--accent);color:#fff;box-shadow:0 6px 18px rgba(15,118,110,.22)}
    .actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.actions button,.stage-tabs button{height:36px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);font-weight:700;cursor:pointer}.actions button.primary{background:#182334;color:#fff;border-color:#182334}.actions button:disabled{opacity:.45;cursor:not-allowed}
    .meta,.detail{padding:11px;border:1px solid var(--line);border-radius:8px;background:var(--soft);font-size:12px;line-height:1.55;color:#4e5f75}
    .detail h2{margin:0 0 8px;font-size:13px;color:#172236}.detail-grid{display:grid;grid-template-columns:70px minmax(0,1fr);gap:5px 8px}.detail-grid b{color:#34445a}.detail-grid span{word-break:break-all;color:#172236}
    .table-card{min-height:0;border:1px solid var(--line);border-radius:8px;background:#fff;overflow:hidden}.table-head{display:flex;align-items:center;justify-content:space-between;padding:10px 11px;border-bottom:1px solid var(--line)}.table-head h2{margin:0;font-size:13px}.table-head span{font-size:12px;color:var(--muted)}
    .table-scroll{max-height:35vh;overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:8px 9px;border-bottom:1px solid #edf1f5;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#f8fafc;color:#506075;font-weight:750;z-index:1}td.num{text-align:right;font-variant-numeric:tabular-nums}td.seq{max-width:145px;word-break:break-all;color:#1f3a5f}tr.clone-row{cursor:pointer}tr.clone-row:hover{background:#f4faf9}tr.clone-row.selected{background:#dff3ef}
    .viewer{position:relative;min-width:0;height:100vh;padding:18px;background:radial-gradient(circle at top left,#f9fbfd,#eef4f7 45%,#e7edf2)}
    .stage-shell{height:100%;display:grid;grid-template-rows:auto minmax(0,1fr);gap:12px}.stage-tabs{display:flex;align-items:center;gap:8px}.stage-tabs button.active{background:#172236;color:#fff;border-color:#172236}.hint{margin-left:auto;color:#657286;font-size:12px}
    .stage{min-height:0;border:1px solid var(--line);border-radius:12px;background:#fff;box-shadow:var(--shadow);overflow:hidden}.pane{height:100%;display:none}.pane.active{display:flex}.png-pane{align-items:center;justify-content:center;padding:22px}.png-pane img{max-width:100%;max-height:100%;object-fit:contain;background:#fff}.interactive-pane{position:relative;align-items:center;justify-content:center;background:#fbfcfd}.interactive-pane svg{width:100%;height:100%;display:block}.clone-shape{cursor:pointer;transition:opacity .14s ease,filter .14s ease}.clone-shape:hover{opacity:.82;filter:drop-shadow(0 0 4px rgba(15,118,110,.35))}.tetris-block rect{stroke:rgba(255,255,255,.72);stroke-width:.18;vector-effect:non-scaling-stroke}.clone-shape.selected rect{stroke:#111827;stroke-width:2.2;vector-effect:non-scaling-stroke}.clone-shape.selected{filter:drop-shadow(0 0 7px rgba(190,107,22,.45))}
    .empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:28px;text-align:center;color:#59697f}.empty-card{max-width:460px;padding:22px;border:1px solid var(--line);border-radius:12px;background:#fff;box-shadow:var(--shadow)}.empty-card h2{margin:0 0 10px;font-size:20px;color:#172236}.empty-card p{margin:0;line-height:1.6}
    @media (max-width:1080px){.app{grid-template-columns:1fr}.viewer{height:72vh}.table-scroll{max-height:260px}}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="head"><h1>Treemap Viewer</h1><p>PNG 用于静态预览，交互视图用于点击 clone 并和 TopClone 表格联动。</p></div>
      <div class="stack">
        <div class="field"><label for="sampleSelect">样本</label><select id="sampleSelect"></select></div>
        <div class="field"><label for="chainSelect">链</label><select id="chainSelect"></select></div>
        <div class="field"><label>图像格式</label><div class="seg" id="modeSwitch"><button type="button" data-mode="tetris">俄罗斯方块</button><button type="button" data-mode="qr">二维码</button></div></div>
      </div>
      <div class="actions"><button id="openPngBtn" class="primary" type="button">打开 PNG</button><button id="openTopcloneBtn" type="button">TopClone CSV</button><button id="downloadZipBtn" type="button">下载 ZIP</button><button id="clearSelectBtn" type="button">清除选择</button></div>
      <div class="meta" id="summary"></div>
      <section class="detail"><h2>Clone Detail</h2><div class="detail-grid" id="cloneDetail"><b>状态</b><span>未选择 clone</span></div></section>
      <div class="field"><label for="topcloneSearch">TopClone 搜索</label><input id="topcloneSearch" type="search" placeholder="CDR3 / V / J" /></div>
      <section class="table-card"><div class="table-head"><h2>TopClone</h2><span id="topcloneCount">0</span></div><div class="table-scroll" id="tableScroll"><table><thead><tr><th>#</th><th>CDR3</th><th>V</th><th>J</th><th>copy</th></tr></thead><tbody id="topcloneBody"></tbody></table></div></section>
    </aside>
    <main class="viewer">
      <div class="stage-shell">
        <div class="stage-tabs" id="viewSwitch"><button type="button" data-view="png">PNG 预览</button><button type="button" data-view="interactive">交互视图</button><span class="hint" id="stageHint"></span></div>
        <section class="stage">
          <div class="pane png-pane" id="pngPane"><img id="viewerImage" alt="treemap png" /></div>
          <div class="pane interactive-pane" id="interactivePane"><svg id="interactiveSvg" role="img" aria-label="interactive treemap"></svg><div class="empty" id="interactiveEmpty" hidden><div class="empty-card"><h2 id="interactiveEmptyTitle">缺少交互布局</h2><p id="interactiveEmptyText">旧任务可能没有 layout JSON，请重新生成 treemap。</p></div></div></div>
        </section>
      </div>
    </main>
  </div>
  <script>
    const DATA = __VIEWER_PAYLOAD__;
    const NS = 'http://www.w3.org/2000/svg';
    const sampleSelect = document.getElementById('sampleSelect');
    const chainSelect = document.getElementById('chainSelect');
    const image = document.getElementById('viewerImage');
    const summary = document.getElementById('summary');
    const cloneDetail = document.getElementById('cloneDetail');
    const topcloneBody = document.getElementById('topcloneBody');
    const topcloneCount = document.getElementById('topcloneCount');
    const topcloneSearch = document.getElementById('topcloneSearch');
    const tableScroll = document.getElementById('tableScroll');
    const modeButtons = Array.from(document.querySelectorAll('#modeSwitch button'));
    const viewButtons = Array.from(document.querySelectorAll('#viewSwitch button'));
    const pngPane = document.getElementById('pngPane');
    const interactivePane = document.getElementById('interactivePane');
    const interactiveSvg = document.getElementById('interactiveSvg');
    const interactiveEmpty = document.getElementById('interactiveEmpty');
    const interactiveEmptyTitle = document.getElementById('interactiveEmptyTitle');
    const interactiveEmptyText = document.getElementById('interactiveEmptyText');
    const stageHint = document.getElementById('stageHint');
    const state = {mode: DATA.default_mode === 'qr' ? 'qr' : 'tetris', view: 'png', selectedCloneId: null, topcloneRows: [], layout: null};

    function escapeHtml(value){return String(value ?? '').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
    function formatCopy(value){const number=Number(value);return Number.isFinite(number)?number.toLocaleString('en-US'):escapeHtml(value);}
    function currentSample(){return (DATA.samples || []).find(sample=>sample.sample_name===sampleSelect.value) || null;}
    function currentEntry(){const sample=currentSample();return sample && sample.individual_treemaps ? sample.individual_treemaps[chainSelect.value] || null : null;}
    function currentImageUrl(){const entry=currentEntry();return entry ? (entry[state.mode + '_png'] || entry.png || '') : '';}
    function currentLayout(){const entry=currentEntry();return entry ? (entry[state.mode + '_layout'] || null) : null;}
    function setActive(buttons,key,value){buttons.forEach(btn=>btn.classList.toggle('active',btn.dataset[key]===value));}
    function showInteractiveMessage(title,text){
      interactiveEmptyTitle.textContent=title;
      interactiveEmptyText.textContent=text;
      interactiveEmpty.hidden=false;
    }
    function hideInteractiveMessage(){interactiveEmpty.hidden=true;}

    function updateSummary(){
      const sample=currentSample();
      if(!sample){summary.textContent='没有可用结果。';return;}
      const modeText=state.mode==='qr'?'二维码':'俄罗斯方块';
      summary.textContent=`样本: ${sample.display_name || sample.sample_name} | 链: ${chainSelect.value || '-'} | 格式: ${modeText} | 展示: ${state.view === 'png' ? 'PNG' : '交互'}`;
    }

    function showDetail(item){
      if(!item){cloneDetail.innerHTML='<b>状态</b><span>未选择 clone</span>';return;}
      cloneDetail.innerHTML=`
        <b>Rank</b><span>${escapeHtml(item.rank || '-')}</span>
        <b>V</b><span>${escapeHtml(item.v || '-')}</span>
        <b>J</b><span>${escapeHtml(item.j || '-')}</span>
        <b>CDR3</b><span>${escapeHtml(item.cdr3 || '-')}</span>
        <b>Copy</b><span>${formatCopy(item.copy)}</span>
      `;
    }

    function selectClone(cloneId, options={}){
      state.selectedCloneId=cloneId || null;
      document.querySelectorAll('.clone-shape.selected').forEach(node=>node.classList.remove('selected'));
      document.querySelectorAll('tr.clone-row.selected').forEach(node=>node.classList.remove('selected'));
      if(!cloneId){showDetail(null);return;}
      const shape=Array.from(interactiveSvg.querySelectorAll('.clone-shape')).find(node=>node.dataset.cloneId===cloneId);
      const row=Array.from(topcloneBody.querySelectorAll('tr.clone-row')).find(node=>node.dataset.cloneId===cloneId);
      const item=(state.layout && state.layout.items || []).find(entry=>entry.clone_id===cloneId) || state.topcloneRows.find(entry=>entry.clone_id===cloneId);
      if(shape) shape.classList.add('selected');
      if(row){
        row.classList.add('selected');
        if(options.scrollTable !== false) row.scrollIntoView({block:'nearest'});
      }
      showDetail(item || null);
      if(!shape && cloneId){
        stageHint.textContent='该 clone 未在当前交互图中渲染';
      }
    }

    function loadTopclone(){
      const entry=currentEntry();
      topcloneBody.innerHTML='<tr><td colspan="5">加载中...</td></tr>';
      topcloneCount.textContent='0';
      state.topcloneRows=[];
      if(!entry || !Array.isArray(entry.topclone_rows)){topcloneBody.innerHTML='<tr><td colspan="5">没有内嵌 TopClone 数据。</td></tr>';return;}
      state.topcloneRows=entry.topclone_rows || [];
      renderTopclone();
    }

    function renderTopclone(){
      const keyword=topcloneSearch.value.trim().toLowerCase();
      const filtered=state.topcloneRows.filter(row=>{
        if(!keyword) return true;
        return [row.cdr3,row.v,row.j,row.c].some(value=>String(value || '').toLowerCase().includes(keyword));
      });
      topcloneCount.textContent=`${filtered.length}/${state.topcloneRows.length}`;
      if(!filtered.length){topcloneBody.innerHTML='<tr><td colspan="5">没有匹配记录。</td></tr>';return;}
      topcloneBody.innerHTML=filtered.slice(0, Number(DATA.top_n || 100)).map(row=>`
        <tr class="clone-row" data-clone-id="${escapeHtml(row.clone_id)}">
          <td class="num">${escapeHtml(row.rank)}</td>
          <td class="seq">${escapeHtml(row.cdr3)}</td>
          <td>${escapeHtml(row.v)}</td>
          <td>${escapeHtml(row.j)}</td>
          <td class="num">${formatCopy(row.copy)}</td>
        </tr>
      `).join('');
      if(state.selectedCloneId) selectClone(state.selectedCloneId,{scrollTable:false});
    }

    function loadLayout(){
      const layout=currentLayout();
      state.layout=null;
      interactiveSvg.innerHTML='';
      hideInteractiveMessage();
      stageHint.textContent='';
      if(!layout){
        showInteractiveMessage('缺少交互布局','当前样本/链/格式没有内嵌交互布局。请重新生成 treemap。');
        return;
      }
      state.layout=layout;
      renderInteractive();
    }

    function renderInteractive(){
      const layout=state.layout;
      interactiveSvg.innerHTML='';
      if(!layout || !layout.canvas || !(layout.items || []).length){
        showInteractiveMessage('交互布局为空','layout JSON 已加载，但没有可渲染的 clone 数据。');
        return;
      }
      hideInteractiveMessage();
      const width=Number(layout.canvas.width || 1000);
      const height=Number(layout.canvas.height || 1000);
      interactiveSvg.setAttribute('viewBox',`0 0 ${width} ${height}`);
      interactiveSvg.setAttribute('preserveAspectRatio','xMidYMid meet');
      (layout.items || []).forEach(item=>{
        const group=document.createElementNS(NS,'g');
        group.classList.add('clone-shape');
        group.dataset.cloneId=item.clone_id;
        group.dataset.rank=item.rank || '';
        group.dataset.shape=item.shape || '';
        group.dataset.rotation=item.rotation ?? '';
        if(layout.mode === 'qr'){
          const rectData=item.rect || {};
          const rect=document.createElementNS(NS,'rect');
          const side=Math.min(Number(rectData.dx || 0),Number(rectData.dy || 0));
          rect.setAttribute('x',rectData.x || 0);
          rect.setAttribute('y',rectData.y || 0);
          rect.setAttribute('width',rectData.dx || 0);
          rect.setAttribute('height',rectData.dy || 0);
          rect.setAttribute('rx',Math.min(side * 0.18, 28));
          rect.setAttribute('fill',item.color || '#000');
          group.appendChild(rect);
        }else{
          const blocks=Array.isArray(item.blocks) ? item.blocks : [];
          if(blocks.length){
            blocks.forEach((block,blockIndex)=>{
              const blockGroup=document.createElementNS(NS,'g');
              blockGroup.classList.add('tetris-block');
              blockGroup.dataset.shape=block.shape || '';
              blockGroup.dataset.rotation=block.rotation ?? '';
              blockGroup.dataset.blockIndex=String(blockIndex);
              (block.cells || []).forEach(cell=>{
                const rect=document.createElementNS(NS,'rect');
                rect.setAttribute('x',cell.x || 0);
                rect.setAttribute('y',cell.y || 0);
                rect.setAttribute('width',cell.dx || 0);
                rect.setAttribute('height',cell.dy || 0);
                rect.setAttribute('fill',item.color || '#000');
                blockGroup.appendChild(rect);
              });
              if(blockGroup.childNodes.length) group.appendChild(blockGroup);
            });
          }else{
            group.classList.add('tetris-block');
            (item.cells || []).forEach(cell=>{
              const rect=document.createElementNS(NS,'rect');
              rect.setAttribute('x',cell.x || 0);
              rect.setAttribute('y',cell.y || 0);
              rect.setAttribute('width',cell.dx || 0);
              rect.setAttribute('height',cell.dy || 0);
              rect.setAttribute('fill',item.color || '#000');
              group.appendChild(rect);
            });
          }
        }
        if(!group.childNodes.length && item.rect){
          const cell=item.rect;
            const rect=document.createElementNS(NS,'rect');
            rect.setAttribute('x',cell.x || 0);
            rect.setAttribute('y',cell.y || 0);
            rect.setAttribute('width',cell.dx || 0);
            rect.setAttribute('height',cell.dy || 0);
            rect.setAttribute('fill',item.color || '#000');
            group.appendChild(rect);
        }
        interactiveSvg.appendChild(group);
      });
      if(state.selectedCloneId) selectClone(state.selectedCloneId,{scrollTable:false});
    }

    function updateStage(){
      pngPane.classList.toggle('active',state.view==='png');
      interactivePane.classList.toggle('active',state.view==='interactive');
      setActive(viewButtons,'view',state.view);
      if(state.view==='interactive') loadLayout();
    }

    function updateImage(){
      const url=currentImageUrl();
      image.src=url || '';
      document.getElementById('openPngBtn').disabled=!url;
      document.getElementById('openTopcloneBtn').disabled=!(currentEntry() && currentEntry().topclone_csv);
      document.getElementById('downloadZipBtn').disabled=!DATA.zip_url;
      setActive(modeButtons,'mode',state.mode);
      updateSummary();
      updateStage();
      loadTopclone();
    }

    function onSampleChange(){
      const sample=currentSample();
      chainSelect.innerHTML='';
      if(!sample){updateImage();return;}
      (sample.chains || []).forEach(chain=>{
        const option=document.createElement('option');
        option.value=chain;option.textContent=chain;chainSelect.appendChild(option);
      });
      if(sample.chains && sample.chains.length) chainSelect.value=sample.chains[0];
      state.selectedCloneId=null;
      showDetail(null);
      updateImage();
    }

    sampleSelect.addEventListener('change',onSampleChange);
    chainSelect.addEventListener('change',()=>{state.selectedCloneId=null;showDetail(null);updateImage();});
    topcloneSearch.addEventListener('input',renderTopclone);
    topcloneBody.addEventListener('click',event=>{
      const row=event.target.closest('tr.clone-row');
      if(row){
        if(state.view!=='interactive'){
          state.view='interactive';
          updateSummary();
          updateStage();
        }
        selectClone(row.dataset.cloneId);
      }
    });
    interactiveSvg.addEventListener('click',event=>{
      const shape=event.target.closest('.clone-shape');
      if(shape) selectClone(shape.dataset.cloneId);
    });
    modeButtons.forEach(btn=>btn.addEventListener('click',()=>{state.mode=btn.dataset.mode==='qr'?'qr':'tetris';state.selectedCloneId=null;showDetail(null);updateImage();}));
    viewButtons.forEach(btn=>btn.addEventListener('click',()=>{state.view=btn.dataset.view==='interactive'?'interactive':'png';updateSummary();updateStage();}));
    document.getElementById('openPngBtn').addEventListener('click',()=>{const url=currentImageUrl();if(url) window.open(url,'_blank','noopener');});
    document.getElementById('openTopcloneBtn').addEventListener('click',()=>{const entry=currentEntry();if(entry && entry.topclone_csv) window.open(entry.topclone_csv,'_blank','noopener');});
    document.getElementById('downloadZipBtn').addEventListener('click',()=>{if(DATA.zip_url) window.open(DATA.zip_url,'_blank','noopener');});
    document.getElementById('clearSelectBtn').addEventListener('click',()=>selectClone(null));

    (DATA.samples || []).forEach(sample=>{
      const option=document.createElement('option');
      option.value=sample.sample_name;option.textContent=sample.display_name || sample.sample_name;sampleSelect.appendChild(option);
    });
    setActive(modeButtons,'mode',state.mode);
    setActive(viewButtons,'view',state.view);
    if((DATA.samples || []).length){sampleSelect.value=DATA.samples[0].sample_name;onSampleChange();}else{updateSummary();updateStage();}
  </script>
</body>
</html>"""
        return html.replace("__VIEWER_PAYLOAD__", json.dumps(viewer_payload, ensure_ascii=False))

    @staticmethod
    def _viewer_result_url(job_id: str, relative_path: Any) -> str:
        value = str(relative_path or "").strip().replace("\\", "/")
        if not value:
            return ""
        if value.startswith(("http://", "https://", "/api/")):
            return value
        return f"/api/treemap/results/{job_id}/{value.lstrip('/')}"

    @staticmethod
    def _read_viewer_json(output_base: Path, relative_path: Any, default: Any) -> Any:
        value = str(relative_path or "").strip().replace("\\", "/")
        if not value or value.startswith(("http://", "https://", "/api/")):
            return default
        target = (output_base / value).resolve()
        try:
            if output_base.resolve() not in target.parents and target != output_base.resolve():
                return default
            if not target.exists() or not target.is_file():
                return default
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Failed to inline treemap viewer JSON: %s", target, exc_info=True)
            return default

    @staticmethod
    def _normalize_viewer_samples(samples: List[Dict[str, Any]], job_id: str, output_base: Path) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for sample in samples:
            sample_copy = dict(sample)
            individual: Dict[str, Dict[str, str]] = {}
            for chain, paths in (sample.get("individual_treemaps") or {}).items():
                entry = {
                    key: TreemapReportService._viewer_result_url(job_id, path)
                    for key, path in (paths or {}).items()
                }
                entry["tetris_layout"] = TreemapReportService._read_viewer_json(
                    output_base,
                    (paths or {}).get("tetris_layout_json"),
                    None,
                )
                entry["qr_layout"] = TreemapReportService._read_viewer_json(
                    output_base,
                    (paths or {}).get("qr_layout_json"),
                    None,
                )
                entry["topclone_rows"] = TreemapReportService._read_viewer_json(
                    output_base,
                    (paths or {}).get("topclone_json"),
                    [],
                )
                individual[chain] = entry
            overview = {
                key: TreemapReportService._viewer_result_url(job_id, path)
                for key, path in (sample.get("overview_treemaps") or {}).items()
            }
            sample_copy["individual_treemaps"] = individual
            sample_copy["overview_treemaps"] = overview
            normalized.append(sample_copy)
        return normalized

    @staticmethod
    def _build_static_viewer_html(metadata: Dict[str, Any], zip_url: str, output_base: Optional[Path] = None) -> str:
        job_id = str(metadata.get("job_id") or "")
        base = Path(output_base) if output_base is not None else Path(".")
        viewer_payload = {
            "job_id": job_id,
            "samples": TreemapReportService._normalize_viewer_samples(metadata.get("samples", []), job_id, base.resolve()),
            "zip_url": zip_url,
            "topclone_only": bool(metadata.get("topclone_only")),
            "default_mode": metadata.get("layout_mode") or "tetris",
            "canvas_shape": metadata.get("canvas_shape") or "portrait",
            "top_n": metadata.get("top_n") or 100,
        }
        return TreemapReportService._build_interactive_viewer_html(viewer_payload)
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Treemap Viewer</title>
  <style>
    *{box-sizing:border-box}
    :root{
      --bg:#eef3f7;
      --panel:#ffffff;
      --ink:#152033;
      --muted:#657286;
      --line:#d8e1ea;
      --accent:#0f766e;
      --accent-strong:#0b5f59;
      --soft:#f6f9fb;
      --shadow:0 18px 45px rgba(31,45,61,.12);
    }
    body{margin:0;font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink)}
    .app{display:grid;grid-template-columns:360px minmax(0,1fr);min-height:100vh}
    .sidebar{display:flex;flex-direction:column;gap:16px;padding:20px;border-right:1px solid var(--line);background:linear-gradient(180deg,#fff 0%,#f8fbfd 100%)}
    .head h1{margin:0 0 6px;font-size:22px;font-weight:720;letter-spacing:0}
    .head p{margin:0;color:var(--muted);font-size:13px;line-height:1.5}
    .field{display:grid;gap:7px}
    label{font-size:12px;font-weight:700;color:#415066}
    select,input{width:100%;height:38px;padding:0 11px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);font-size:13px;outline:none}
    select:focus,input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(15,118,110,.13)}
    .stack{display:grid;gap:12px}
    .seg{display:grid;grid-template-columns:1fr 1fr;padding:3px;border:1px solid var(--line);border-radius:9px;background:#fff}
    .seg button{height:34px;border:0;border-radius:7px;background:transparent;color:#506075;font-weight:700;cursor:pointer}
    .seg button.active{background:var(--accent);color:#fff;box-shadow:0 6px 18px rgba(15,118,110,.23)}
    .actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}
    .actions button,.tool button{height:36px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);font-weight:650;cursor:pointer}
    .actions button.primary{background:#182334;color:#fff;border-color:#182334}
    .actions button:disabled,.tool button:disabled{opacity:.45;cursor:not-allowed}
    .meta{padding:12px;border-radius:8px;background:var(--soft);border:1px solid var(--line);font-size:12px;line-height:1.55;color:#4e5f75}
    .table-card{min-height:0;border:1px solid var(--line);border-radius:8px;background:#fff;overflow:hidden}
    .table-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 11px;border-bottom:1px solid var(--line)}
    .table-head h2{margin:0;font-size:13px}
    .table-head span{font-size:12px;color:var(--muted)}
    .table-scroll{max-height:38vh;overflow:auto}
    table{width:100%;border-collapse:collapse;font-size:12px}
    th,td{padding:8px 9px;border-bottom:1px solid #edf1f5;text-align:left;vertical-align:top}
    th{position:sticky;top:0;background:#f8fafc;color:#506075;font-weight:750;z-index:1}
    td.num{text-align:right;font-variant-numeric:tabular-nums}
    td.seq{max-width:142px;word-break:break-all;color:#1f3a5f}
    .viewer{position:relative;min-width:0;height:100vh;background:radial-gradient(circle at top left,#f8fbfd 0,#eef3f7 42%,#e8eef4 100%);overflow:hidden}
    .toolbar{position:absolute;z-index:5;top:18px;left:18px;display:flex;align-items:center;gap:8px;padding:8px;border:1px solid rgba(216,225,234,.9);border-radius:10px;background:rgba(255,255,255,.9);box-shadow:var(--shadow);backdrop-filter:blur(10px)}
    .tool{display:flex;gap:6px}
    .tool button{width:34px;height:32px;padding:0}
    .zoom-label{min-width:52px;text-align:center;font-size:12px;font-weight:750;color:#405066}
    .canvas{height:100%;display:flex;align-items:center;justify-content:center;padding:72px 42px 42px;cursor:grab}
    .canvas.dragging{cursor:grabbing}
    #viewerImage{max-width:min(86vw,1100px);max-height:calc(100vh - 130px);object-fit:contain;transform-origin:center center;will-change:transform;box-shadow:0 24px 70px rgba(31,45,61,.18);background:#fff}
    .empty-state{display:flex;align-items:center;justify-content:center;height:100%;padding:32px;text-align:center;color:#4b5563}
    .empty-card{max-width:460px;padding:24px;border-radius:12px;background:#fff;border:1px solid var(--line);box-shadow:var(--shadow)}
    .empty-card h2{margin:0 0 12px;font-size:22px;color:#111827}
    .empty-card p{margin:0 0 12px;line-height:1.6}
    .empty-card a{color:var(--accent-strong);font-weight:700}
    @media (max-width: 1080px){
      .app{grid-template-columns:1fr}
      .viewer{height:68vh}
      .table-scroll{max-height:260px}
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="head">
        <h1>Treemap Viewer</h1>
        <p>切换二维码/俄罗斯方块布局，查看单链图片与 TopClone 明细。</p>
      </div>
      <div class="stack">
        <div class="field">
          <label for="sampleSelect">样本</label>
          <select id="sampleSelect"></select>
        </div>
        <div class="field">
          <label for="chainSelect">链</label>
          <select id="chainSelect"></select>
        </div>
        <div class="field">
          <label>图像格式</label>
          <div class="seg" id="modeSwitch">
            <button type="button" data-mode="tetris">俄罗斯方块</button>
            <button type="button" data-mode="qr">二维码</button>
          </div>
        </div>
      </div>
      <div class="actions">
        <button id="openPngBtn" class="primary" type="button">打开 PNG</button>
        <button id="openTopcloneBtn" type="button">TopClone CSV</button>
        <button id="downloadZipBtn" type="button">下载 ZIP</button>
        <button id="resetViewBtn" type="button">重置视图</button>
      </div>
      <div class="meta" id="summary"></div>
      <div class="field">
        <label for="topcloneSearch">TopClone 搜索</label>
        <input id="topcloneSearch" type="search" placeholder="CDR3 / V / J" />
      </div>
      <section class="table-card">
        <div class="table-head">
          <h2>TopClone</h2>
          <span id="topcloneCount">0</span>
        </div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr><th>#</th><th>CDR3</th><th>V</th><th>J</th><th>copy</th></tr>
            </thead>
            <tbody id="topcloneBody"></tbody>
          </table>
        </div>
      </section>
    </aside>
    <main class="viewer">
      <div class="toolbar">
        <div class="tool">
          <button id="zoomOutBtn" type="button">-</button>
          <button id="zoomInBtn" type="button">+</button>
        </div>
        <span class="zoom-label" id="zoomLabel">100%</span>
      </div>
      <div class="canvas" id="canvas">
        <img id="viewerImage" alt="treemap" />
      </div>
      <div class="empty-state" id="viewerEmptyState" hidden>
        <div class="empty-card" id="viewerEmptyStateCard"></div>
      </div>
    </main>
  </div>
  <script>
    const DATA = __VIEWER_PAYLOAD__;
    const sampleSelect = document.getElementById('sampleSelect');
    const chainSelect = document.getElementById('chainSelect');
    const image = document.getElementById('viewerImage');
    const canvas = document.getElementById('canvas');
    const summary = document.getElementById('summary');
    const emptyState = document.getElementById('viewerEmptyState');
    const emptyStateCard = document.getElementById('viewerEmptyStateCard');
    const openPngBtn = document.getElementById('openPngBtn');
    const openTopcloneBtn = document.getElementById('openTopcloneBtn');
    const resetViewBtn = document.getElementById('resetViewBtn');
    const zoomInBtn = document.getElementById('zoomInBtn');
    const zoomOutBtn = document.getElementById('zoomOutBtn');
    const zoomLabel = document.getElementById('zoomLabel');
    const topcloneBody = document.getElementById('topcloneBody');
    const topcloneCount = document.getElementById('topcloneCount');
    const topcloneSearch = document.getElementById('topcloneSearch');
    const modeButtons = Array.from(document.querySelectorAll('#modeSwitch button'));
    const TOPCLONE_ONLY = Boolean(DATA.topclone_only);
    const topcloneCache = new Map();
    const state = {
      mode: DATA.default_mode === 'qr' ? 'qr' : 'tetris',
      scale: 1,
      panX: 0,
      panY: 0,
      dragging: false,
      dragStartX: 0,
      dragStartY: 0,
      basePanX: 0,
      basePanY: 0
    };

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({
        '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
      }[ch]));
    }

    function formatCopy(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) return escapeHtml(value);
      return number.toLocaleString('en-US');
    }

    function currentSample() {
      return (DATA.samples || []).find(sample => sample.sample_name === sampleSelect.value) || null;
    }

    function currentChainEntry() {
      const sample = currentSample();
      const chain = chainSelect.value;
      return sample && sample.individual_treemaps ? sample.individual_treemaps[chain] || null : null;
    }

    function currentImageUrl() {
      const entry = currentChainEntry();
      if (!entry) return '';
      return entry[state.mode + '_png'] || entry.png || '';
    }

    function updateModeButtons() {
      modeButtons.forEach(btn => btn.classList.toggle('active', btn.dataset.mode === state.mode));
    }

    function updateTransform() {
      image.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.scale})`;
      zoomLabel.textContent = `${Math.round(state.scale * 100)}%`;
    }

    function resetView() {
      state.scale = 1;
      state.panX = 0;
      state.panY = 0;
      updateTransform();
    }

    function updateActionButtons() {
      const entry = currentChainEntry();
      openPngBtn.disabled = !currentImageUrl();
      openTopcloneBtn.disabled = !(entry && entry.topclone_csv);
      document.getElementById('downloadZipBtn').disabled = !DATA.zip_url;
    }

    function updateSummary() {
      const sample = currentSample();
      if (!sample) {
        summary.textContent = '没有可用结果。';
        return;
      }
      const modeText = TOPCLONE_ONLY ? '仅 TopClone' : (state.mode === 'qr' ? '二维码' : '俄罗斯方块');
      summary.textContent = `样本: ${sample.display_name || sample.sample_name} | 链: ${chainSelect.value || '-'} | 格式: ${modeText} | 画布: ${DATA.canvas_shape || '-'}`;
    }

    async function loadTopclone() {
      const entry = currentChainEntry();
      topcloneBody.innerHTML = '<tr><td colspan="5">加载中...</td></tr>';
      topcloneCount.textContent = '0';
      if (!entry || !entry.topclone_json) {
        topcloneBody.innerHTML = '<tr><td colspan="5">没有 TopClone JSON。</td></tr>';
        return;
      }
      try {
        if (!topcloneCache.has(entry.topclone_json)) {
          const response = await fetch(entry.topclone_json);
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          topcloneCache.set(entry.topclone_json, await response.json());
        }
        renderTopclone(topcloneCache.get(entry.topclone_json) || []);
      } catch (error) {
        topcloneBody.innerHTML = '<tr><td colspan="5">TopClone 加载失败，可打开 CSV 查看。</td></tr>';
      }
    }

    function renderTopclone(rows) {
      const keyword = topcloneSearch.value.trim().toLowerCase();
      const filtered = rows.filter(row => {
        if (!keyword) return true;
        return [row.cdr3, row.v, row.j, row.c].some(value => String(value || '').toLowerCase().includes(keyword));
      });
      topcloneCount.textContent = `${filtered.length}/${rows.length}`;
      if (!filtered.length) {
        topcloneBody.innerHTML = '<tr><td colspan="5">没有匹配记录。</td></tr>';
        return;
      }
      topcloneBody.innerHTML = filtered.slice(0, Number(DATA.top_n || 100)).map(row => `
        <tr>
          <td class="num">${escapeHtml(row.rank)}</td>
          <td class="seq">${escapeHtml(row.cdr3)}</td>
          <td>${escapeHtml(row.v)}</td>
          <td>${escapeHtml(row.j)}</td>
          <td class="num">${formatCopy(row.copy)}</td>
        </tr>
      `).join('');
    }

    function updateImage() {
      const sample = currentSample();
      const chain = chainSelect.value;
      const entry = currentChainEntry();
      const imageUrl = currentImageUrl();
      if (!sample || !entry) {
        image.src = '';
        canvas.style.display = 'flex';
        emptyState.hidden = true;
        updateActionButtons();
        updateSummary();
        loadTopclone();
        return;
      }

      if (TOPCLONE_ONLY || !imageUrl) {
        image.src = '';
        canvas.style.display = 'none';
        emptyState.hidden = false;
        const sampleLabel = sample.display_name || sample.sample_name || '';
        const downloadLink = entry.topclone_csv
          ? `<p><a href="${entry.topclone_csv}" target="_blank" rel="noopener">下载 ${escapeHtml(sampleLabel)} / ${escapeHtml(chain)} TopClone CSV</a></p>`
          : '<p>当前链没有可用的 TopClone CSV。</p>';
        emptyStateCard.innerHTML = `<h2>TopClone-only</h2><p>这次 treemap 任务未生成图，只导出 TopClone 表格。</p>${downloadLink}`;
      } else {
        emptyState.hidden = true;
        canvas.style.display = 'flex';
        image.src = imageUrl;
      }

      resetView();
      updateActionButtons();
      updateSummary();
      loadTopclone();
    }

    function onSampleChange() {
      const sample = currentSample();
      chainSelect.innerHTML = '';
      if (!sample) {
        updateImage();
        return;
      }
      (sample.chains || []).forEach(chain => {
        const option = document.createElement('option');
        option.value = chain;
        option.textContent = chain;
        chainSelect.appendChild(option);
      });
      if (sample.chains && sample.chains.length > 0) {
        chainSelect.value = sample.chains[0];
      }
      updateImage();
    }

    sampleSelect.addEventListener('change', onSampleChange);
    chainSelect.addEventListener('change', updateImage);
    topcloneSearch.addEventListener('input', () => {
      const entry = currentChainEntry();
      if (entry && entry.topclone_json && topcloneCache.has(entry.topclone_json)) {
        renderTopclone(topcloneCache.get(entry.topclone_json) || []);
      }
    });
    modeButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        state.mode = btn.dataset.mode === 'qr' ? 'qr' : 'tetris';
        updateModeButtons();
        updateImage();
      });
    });
    openPngBtn.addEventListener('click', () => {
      const imageUrl = currentImageUrl();
      if (imageUrl) {
        window.open(imageUrl, '_blank', 'noopener');
      }
    });
    openTopcloneBtn.addEventListener('click', () => {
      const entry = currentChainEntry();
      if (entry && entry.topclone_csv) {
        window.open(entry.topclone_csv, '_blank', 'noopener');
      }
    });
    document.getElementById('downloadZipBtn').addEventListener('click', () => {
      if (DATA.zip_url) window.open(DATA.zip_url, '_blank', 'noopener');
    });
    resetViewBtn.addEventListener('click', resetView);
    zoomInBtn.addEventListener('click', () => {
      state.scale = Math.min(5, state.scale * 1.18);
      updateTransform();
    });
    zoomOutBtn.addEventListener('click', () => {
      state.scale = Math.max(0.25, state.scale / 1.18);
      updateTransform();
    });
    canvas.addEventListener('wheel', event => {
      event.preventDefault();
      const next = event.deltaY < 0 ? state.scale * 1.08 : state.scale / 1.08;
      state.scale = Math.min(5, Math.max(0.25, next));
      updateTransform();
    }, { passive: false });
    canvas.addEventListener('pointerdown', event => {
      state.dragging = true;
      state.dragStartX = event.clientX;
      state.dragStartY = event.clientY;
      state.basePanX = state.panX;
      state.basePanY = state.panY;
      canvas.classList.add('dragging');
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', event => {
      if (!state.dragging) return;
      state.panX = state.basePanX + event.clientX - state.dragStartX;
      state.panY = state.basePanY + event.clientY - state.dragStartY;
      updateTransform();
    });
    canvas.addEventListener('pointerup', event => {
      state.dragging = false;
      canvas.classList.remove('dragging');
      canvas.releasePointerCapture(event.pointerId);
    });

    (DATA.samples || []).forEach(sample => {
      const option = document.createElement('option');
      option.value = sample.sample_name;
      option.textContent = sample.display_name || sample.sample_name;
      sampleSelect.appendChild(option);
    });
    updateModeButtons();
    updateTransform();
    if ((DATA.samples || []).length > 0) {
      sampleSelect.value = DATA.samples[0].sample_name;
      onSampleChange();
    } else {
      updateSummary();
      updateActionButtons();
    }
  </script>
</body>
</html>"""
        return html.replace("__VIEWER_PAYLOAD__", json.dumps(viewer_payload, ensure_ascii=False))

    def generate_report(
        self,
        samples: List[Dict[str, Any]],
        selected_chains: List[str],
        field_mapping: Dict[str, Any],
        output_name: Optional[str] = None,
        min_copy_default: int = 30,
        top_n: int = 100,
        topclone_only: bool = False,
        style: str = "classic",
        layout_mode: str = "tetris",
        canvas_shape: str = "square",
        progress_callback: Optional[Callable[[float, str, str, Optional[Dict[str, Any]]], None]] = None,
    ) -> TreemapReportResult:
        def emit(
            progress: float,
            stage: str,
            detail: str,
            meta: Optional[Dict[str, Any]] = None,
        ) -> None:
            if progress_callback:
                progress_callback(max(0.0, min(100.0, progress)), stage, detail, meta or {})

        if not samples:
            raise ValidationError(message="至少需要一个样本。")

        normalized_chains = [chain for chain in (self._normalize_chain(item) for item in selected_chains) if chain]
        if not normalized_chains:
            raise ValidationError(message="至少需要选择一条链。")

        layout_mode = str(layout_mode or "tetris").strip().lower()
        if layout_mode not in {"tetris", "qr"}:
            layout_mode = "tetris"
        topclone_only = bool(topclone_only)

        overrides = {
            "cdr3": field_mapping.get("cdr3_column"),
            "copy": field_mapping.get("copy_column"),
            "v": field_mapping.get("v_column"),
            "d": None,
            "j": field_mapping.get("j_column"),
            "c": None,
            "chain": None,
            "cell_type": None,
            "joined_seq": None,
        }

        job_id = self._allocate_job_id(output_name)
        output_base = self.results_root / self._RESULT_DIR / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        emit(2.0, "初始化任务", "正在整理样本和链选择。", {"phase": "init"})

        sample_work_items: List[Dict[str, Any]] = []
        for sample in samples:
            display_name = str(sample.get("display_name") or sample.get("original_name") or "").strip()
            if not display_name:
                continue
            chain_files = self._extract_sample_chain_files(sample, normalized_chains)
            if not chain_files:
                continue
            sample_work_items.append(
                {
                    "sample": sample,
                    "display_name": display_name,
                    "sample_safe_name": self._sanitize_file_stem(display_name),
                    "chain_files": chain_files,
                }
            )

        if not sample_work_items:
            raise ValidationError(message="没有匹配到可生成的样本，请检查样本选择和链选择。")

        total_units = 2  # metadata/viewer + finalize
        for item in sample_work_items:
            chain_count = len(item["chain_files"])
            total_units += chain_count  # topclone csv/json
            if not topclone_only:
                total_units += chain_count * 2  # tetris + qr individual PNG
                total_units += 1  # overview PNG

        completed_units = 0
        total_samples = len(sample_work_items)
        total_chain_jobs = sum(len(item["chain_files"]) for item in sample_work_items)
        generated_sample_count = 0

        def progress_meta(
            *,
            phase: str = "running",
            sample_name: Optional[str] = None,
            sample_index: Optional[int] = None,
            chain_name: Optional[str] = None,
            chain_index: Optional[int] = None,
            chain_total: Optional[int] = None,
            input_file: Optional[str] = None,
            output_file: Optional[str] = None,
        ) -> Dict[str, Any]:
            return {
                "phase": phase,
                "total_samples": total_samples,
                "total_chain_jobs": total_chain_jobs,
                "generated_samples": generated_sample_count,
                "completed_units": completed_units,
                "total_units": total_units,
                "current_sample": sample_name,
                "current_sample_index": sample_index,
                "current_chain": chain_name,
                "current_chain_index": chain_index,
                "current_chain_total": chain_total,
                "current_input_file": input_file,
                "current_output_file": output_file,
            }

        def advance(
            stage: str,
            detail: str,
            *,
            phase: str = "running",
            sample_name: Optional[str] = None,
            sample_index: Optional[int] = None,
            chain_name: Optional[str] = None,
            chain_index: Optional[int] = None,
            chain_total: Optional[int] = None,
            input_file: Optional[str] = None,
            output_file: Optional[str] = None,
        ) -> None:
            nonlocal completed_units
            completed_units += 1
            progress = 4.0 + (completed_units / max(1, total_units)) * 94.0
            emit(
                progress,
                stage,
                detail,
                progress_meta(
                    phase=phase,
                    sample_name=sample_name,
                    sample_index=sample_index,
                    chain_name=chain_name,
                    chain_index=chain_index,
                    chain_total=chain_total,
                    input_file=input_file,
                    output_file=output_file,
                ),
            )

        result_samples: List[Dict[str, Any]] = []
        warnings: List[str] = []

        for sample_index, item in enumerate(sample_work_items, start=1):
            sample = item["sample"]
            display_name = item["display_name"]
            sample_safe_name = item["sample_safe_name"]
            sample_dirs = self._sample_dirs(output_base, sample_safe_name)
            chain_files = item["chain_files"]
            ordered_sample_chains = [chain for chain in CHAIN_ORDER_ALL if chain in chain_files]
            emit(
                4.0 + ((completed_units / max(1, total_units)) * 94.0),
                f"处理样本 {sample_index}/{len(sample_work_items)}",
                f"正在准备样本 {display_name}",
                progress_meta(
                    phase="sample_prepare",
                    sample_name=display_name,
                    sample_index=sample_index,
                ),
            )

            generated_chains: List[str] = []
            chain_outputs: Dict[str, Dict[str, str]] = {}

            for chain_index, chain in enumerate(ordered_sample_chains, start=1):
                filepath = chain_files[chain]
                input_path = Path(filepath).expanduser().resolve()
                if not input_path.exists():
                    logger.warning("Treemap input file not found: %s", input_path)
                    continue

                emit(
                    4.0 + ((completed_units / max(1, total_units)) * 94.0),
                    "读取链数据",
                    f"{display_name} | {chain} | {input_path.name}",
                    progress_meta(
                        phase="read_chain",
                        sample_name=display_name,
                        sample_index=sample_index,
                        chain_name=chain,
                        chain_index=chain_index,
                        chain_total=len(ordered_sample_chains),
                        input_file=input_path.name,
                    ),
                )

                columns = self._detect_columns_for_path(input_path, overrides)
                if not columns.get("cdr3") or not columns.get("copy") or not columns.get("v") or not columns.get("j"):
                    raise ValidationError(message=f"{input_path.name} 未识别到 CDR3、copy、V 或 J 列。")

                topclone_rows, _ = read_repertoire_rows(input_path, columns)
                if not topclone_rows:
                    logger.warning("Treemap input file has no usable rows: %s", input_path)
                    continue
                topclone_filename = f"{sample_safe_name}__{chain}_topclone.csv"
                topclone_json_filename = f"{sample_safe_name}__{chain}_top100_clone.json"
                topclone_path = sample_dirs["topclone_csv"] / topclone_filename
                topclone_json_path = sample_dirs["topclone_json"] / topclone_json_filename
                self._write_topclone_csv(topclone_rows, topclone_path, top_n=max(1, int(top_n)))
                self._write_topclone_json(topclone_rows, topclone_json_path, top_n=max(1, int(top_n)))
                advance(
                    "导出 TopClone",
                    f"{display_name} | {chain}",
                    phase="topclone",
                    sample_name=display_name,
                    sample_index=sample_index,
                    chain_name=chain,
                    chain_index=chain_index,
                    chain_total=len(ordered_sample_chains),
                    input_file=input_path.name,
                    output_file=topclone_filename,
                )

                generated_chains.append(chain)
                chain_output = {
                    "topclone_csv": str(topclone_path.relative_to(output_base)).replace("\\", "/"),
                    "topclone_json": str(topclone_json_path.relative_to(output_base)).replace("\\", "/"),
                }

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

                    for mode_key in ("tetris", "qr"):
                        png_filename = f"{sample_safe_name}__{chain}_treemap_{mode_key}.png"
                        layout_filename = f"{sample_safe_name}__{chain}_treemap_{mode_key}_layout.json"
                        png_path = sample_dirs["individual_png"] / png_filename
                        layout_path = sample_dirs["individual_json"] / layout_filename

                        layout = build_treemap_layout(
                            csv_path=input_path,
                            mode=mode_key,
                            canvas_shape=canvas_shape,
                            cdr3_col=columns.get("cdr3", "CDR3(pep)"),
                            copy_col=columns.get("copy", "copy"),
                            v_col=columns.get("v", "V"),
                            j_col=columns.get("j", "J"),
                        )
                        layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
                        render_treemap_layout(layout, png_path)

                        chain_output[f"{mode_key}_png"] = str(png_path.relative_to(output_base)).replace("\\", "/")
                        chain_output[f"{mode_key}_layout_json"] = str(layout_path.relative_to(output_base)).replace("\\", "/")
                        advance(
                            "生成单链 PNG",
                            f"{display_name} | {chain} | {'俄罗斯方块' if mode_key == 'tetris' else '二维码'} ({chain_index}/{len(ordered_sample_chains)})",
                            phase=f"individual_png_{mode_key}",
                            sample_name=display_name,
                            sample_index=sample_index,
                            chain_name=chain,
                            chain_index=chain_index,
                            chain_total=len(ordered_sample_chains),
                            input_file=input_path.name,
                            output_file=png_filename,
                        )

                    default_png_key = f"{layout_mode}_png"
                    chain_output["png"] = chain_output.get(default_png_key) or chain_output.get("tetris_png") or chain_output.get("qr_png", "")

                chain_outputs[chain] = chain_output

            if not generated_chains:
                continue

            overview_treemaps: Dict[str, str] = {}
            if not topclone_only:
                overview_png_filename = f"{sample_safe_name}__ALL_treemap.png"
                overview_png_path = sample_dirs["overview_png"] / overview_png_filename

                # Collect already-generated individual chain PNGs
                rendered_png_paths: Dict[str, Path] = {}
                for chain in generated_chains:
                    png_relative = chain_outputs.get(chain, {}).get("png")
                    if not png_relative:
                        continue
                    png_path = output_base / png_relative
                    if png_path.exists() and png_path.is_file():
                        rendered_png_paths[chain] = png_path

                if rendered_png_paths:
                    self._compose_overview_png_from_individuals(rendered_png_paths, overview_png_path)
                    advance(
                        "导出七链 PNG",
                        f"{display_name} | overview",
                        phase="overview_png",
                        sample_name=display_name,
                        sample_index=sample_index,
                        output_file=overview_png_filename,
                    )
                else:
                    warning = f"{display_name} 未生成可用于汇总的 treemap PNG，已保留 CSV 输出。"
                    warnings.append(warning)
                    logger.warning(warning)

                overview_treemaps = {}
                if overview_png_path.exists() and overview_png_path.is_file():
                    overview_treemaps["png"] = str(overview_png_path.relative_to(output_base)).replace("\\", "/")

            generated_sample_count += 1
            result_samples.append(
                {
                    "sample_name": display_name,
                    "display_name": display_name,
                    "sample_safe_name": sample_safe_name,
                    "chains": generated_chains,
                    "individual_treemaps": chain_outputs,
                    "overview_treemaps": overview_treemaps,
                }
            )

        if not result_samples:
            raise ValidationError(message="没有生成任何 treemap 结果，请检查样本、链和字段映射。")

        metadata = {
            "job_id": job_id,
            "created_at": datetime.now().isoformat(),
            "selected_chains": normalized_chains,
            "field_mapping": overrides,
            "min_copy_default": max(0, int(min_copy_default)),
            "top_n": max(1, int(top_n)),
            "topclone_only": topclone_only,
            "style": style,
            "layout_mode": layout_mode,
            "canvas_shape": canvas_shape,
            "samples": result_samples,
            "warnings": warnings,
        }
        metadata_path = output_base / self._METADATA_FILE_NAME
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        viewer_path = output_base / self._VIEWER_FILE_NAME
        viewer_path.write_text(
            self._build_static_viewer_html(
                metadata=metadata,
                zip_url=f"/api/treemap/export-zip/{job_id}",
                output_base=output_base,
            ),
            encoding="utf-8",
        )
        advance(
            "写入结果清单",
            "正在写入 metadata.json 和 viewer.html",
            phase="metadata",
            output_file=f"{self._METADATA_FILE_NAME}, {self._VIEWER_FILE_NAME}",
        )
        completion_detail = (
            f"共生成 {len(result_samples)} 个样本的 topclone 结果。"
            if topclone_only
            else f"共生成 {len(result_samples)} 个样本的 treemap 结果。"
        )
        emit(100.0, "任务完成", completion_detail)

        return TreemapReportResult(
            job_id=job_id,
            output_base=output_base,
            metadata_path=metadata_path,
            metadata=metadata,
        )

    def _resolve_job_root(self, job_id: str) -> Path:
        safe_job_id = self._sanitize_job_id(job_id)
        job_root = (self.results_root / self._RESULT_DIR / safe_job_id).resolve()
        if not job_root.exists() or not job_root.is_dir():
            raise FileNotFoundError(f"Treemap result job not found: {job_id}")
        return job_root

    def read_metadata(self, job_id: str) -> Dict[str, Any]:
        job_root = self._resolve_job_root(job_id)
        metadata_path = job_root / self._METADATA_FILE_NAME
        if not metadata_path.exists():
            raise FileNotFoundError(f"Treemap metadata not found: {job_id}")
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def resolve_result_file(self, job_id: str, relative_path: str) -> Path:
        job_root = self._resolve_job_root(job_id)
        target = (job_root / relative_path).resolve()
        if job_root not in target.parents and target != job_root:
            raise ValidationError(message="非法结果文件路径。")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"Treemap result file not found: {relative_path}")
        return target

    def build_zip_buffer(self, job_id: str) -> tuple[io.BytesIO, str]:
        job_root = self._resolve_job_root(job_id)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for path in sorted(job_root.rglob("*")):
                if path.is_file():
                    zip_file.write(path, arcname=str(path.relative_to(job_root)).replace("\\", "/"))
        zip_buffer.seek(0)
        return zip_buffer, f"{job_id}_treemap_results.zip"


_treemap_report_service: Optional[TreemapReportService] = None


def get_treemap_report_service(results_root: Optional[Path] = None) -> TreemapReportService:
    global _treemap_report_service

    if results_root is None:
        results_root = Path(__file__).resolve().parents[1] / "data" / "results"

    resolved_root = Path(results_root).resolve()
    if _treemap_report_service is None or _treemap_report_service.results_root != resolved_root:
        _treemap_report_service = TreemapReportService(results_root=resolved_root)

    return _treemap_report_service
