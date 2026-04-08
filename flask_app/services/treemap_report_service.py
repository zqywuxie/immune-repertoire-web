"""
Treemap report service.

Generates HTML and PNG outputs per sample under:
<results_root>/treemap_report/<job_id>/<sample>/
  individual_treemaps/
    HTML/
    PNG/
  7chain_treemaps/
    HTML/
    PNG/
"""

from __future__ import annotations

import csv
import html
import io
import json
import logging
import math
import os
import re
import subprocess
import tempfile
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PIL import Image

from flask_app.exceptions import ValidationError
from flask_app.services.auto_heatmap_service import get_auto_heatmap_service
from flask_app.services.treemap_renderer import (
    detect_columns,
    detect_dialect,
    escape_html_text,
    HTML_TEMPLATE,
    load_d3_script_tag,
    make_title,
    open_text_file,
    read_repertoire,
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
OVERVIEW_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>__TITLE__</title>
  <style>
    :root{
      --bg:#080808;
      --line:#000000;
      --label-bg:rgba(0,0,0,.72);
      --label-text:#ffffff;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      background:var(--bg);
      color:#fff;
      font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    }
    .page{
      min-height:100vh;
      padding:12px;
      background:#000;
    }
    .rows{
      display:grid;
      gap:10px;
      align-content:start;
      background:#000;
    }
    .row{
      display:grid;
      gap:10px;
    }
    .row.top{grid-template-columns:__TOP_GRID__;}
    .row.bottom{grid-template-columns:__BOTTOM_GRID__;}
    .panel{
      position:relative;
      aspect-ratio:1 / 1;
      background:#fff;
      overflow:hidden;
      border:1px solid #000;
    }
    .panel iframe{
      width:100%;
      height:100%;
      border:0;
      display:block;
      background:#fff;
    }
    .panel .label{
      position:absolute;
      top:8px;
      left:8px;
      z-index:2;
      padding:4px 8px;
      border-radius:999px;
      background:var(--label-bg);
      color:var(--label-text);
      font-size:12px;
      font-weight:700;
      letter-spacing:.02em;
    }
    @media (max-width:1100px){
      .row.top,.row.bottom{grid-template-columns:repeat(2, minmax(0, 1fr));}
    }
    @media (max-width:700px){
      .row.top,.row.bottom{grid-template-columns:1fr;}
    }
  </style>
</head>
<body>
  <div class="page">
    <div class="rows">
      <div class="row top">
        __TOP_PANELS__
      </div>
      <div class="row bottom">
        __BOTTOM_PANELS__
      </div>
    </div>
  </div>
</body>
</html>
"""


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
        self._browser_path: Optional[Path] = None
        self._d3_script_tag: Optional[str] = None

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

    @staticmethod
    def _build_overview_html(
        sample_name: str,
        chain_html_paths: Dict[str, Path],
        overview_html_dir: Path,
    ) -> str:
        safe_sample_name = html.escape(sample_name)
        top_items: List[str] = []
        bottom_items: List[str] = []
        for chain in OVERVIEW_ORDER_TCR:
            html_path = chain_html_paths.get(chain)
            if not html_path:
                continue
            relative_ref = Path(os.path.relpath(html_path, start=overview_html_dir)).as_posix()
            top_items.append(
                f'''<section class="panel {chain.lower()}">
  <div class="label">{chain}</div>
  <iframe src="{relative_ref}?mode=panel" loading="lazy" title="{safe_sample_name} {chain}"></iframe>
</section>'''
            )
        for chain in OVERVIEW_ORDER_BCR:
            html_path = chain_html_paths.get(chain)
            if not html_path:
                continue
            relative_ref = Path(os.path.relpath(html_path, start=overview_html_dir)).as_posix()
            bottom_items.append(
                f'''<section class="panel {chain.lower()}">
  <div class="label">{chain}</div>
  <iframe src="{relative_ref}?mode=panel" loading="lazy" title="{safe_sample_name} {chain}"></iframe>
</section>'''
            )

        return (
            OVERVIEW_TEMPLATE
            .replace("__TITLE__", f"{safe_sample_name} All Chains Treemap")
            .replace("__TOP_GRID__", TreemapReportService._weights_to_grid_template(OVERVIEW_ORDER_TCR, TOP_CHAIN_WEIGHTS))
            .replace("__BOTTOM_GRID__", TreemapReportService._weights_to_grid_template(OVERVIEW_ORDER_BCR, BOTTOM_CHAIN_WEIGHTS))
            .replace("__TOP_PANELS__", "\n".join(top_items))
            .replace("__BOTTOM_PANELS__", "\n".join(bottom_items))
        )

    @staticmethod
    def _build_overview_export_html(chain_html_paths: Dict[str, Path], export_html_dir: Path) -> str:
        blocks: List[str] = []
        for chain in OVERVIEW_ORDER_TCR:
            html_path = chain_html_paths.get(chain)
            if not html_path:
                continue
            ref = Path(os.path.relpath(html_path, start=export_html_dir)).as_posix()
            blocks.append(f'<section class="panel tcr"><iframe src="{ref}?mode=panel-fill" title="{chain}"></iframe></section>')
        top_row = "\n".join(blocks)

        blocks = []
        for chain in OVERVIEW_ORDER_BCR:
            html_path = chain_html_paths.get(chain)
            if not html_path:
                continue
            ref = Path(os.path.relpath(html_path, start=export_html_dir)).as_posix()
            blocks.append(f'<section class="panel bcr"><iframe src="{ref}?mode=panel-fill" title="{chain}"></iframe></section>')
        bottom_row = "\n".join(blocks)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Treemap PNG Export</title>
  <style>
    *{{box-sizing:border-box}}
    html,body{{margin:0;width:1440px;height:1440px;overflow:hidden;background:#ffffff}}
    .page{{width:100%;height:100%;background:#ffffff;display:grid;grid-template-rows:320px minmax(0,1fr)}}
    .row{{display:grid;gap:0;height:100%;align-items:stretch}}
    .row.top{{grid-template-columns:{TreemapReportService._weights_to_grid_template(OVERVIEW_ORDER_TCR, TOP_CHAIN_WEIGHTS)}}}
    .row.bottom{{grid-template-columns:{TreemapReportService._weights_to_grid_template(OVERVIEW_ORDER_BCR, BOTTOM_CHAIN_WEIGHTS)}}}
    .panel{{height:100%;min-height:0;border:2px solid #000;background:#fff;overflow:hidden}}
    .panel iframe{{width:100%;height:100%;border:0;display:block;background:#fff}}
  </style>
</head>
<body>
  <div class="page">
    <div class="row top">{top_row}</div>
    <div class="row bottom">{bottom_row}</div>
  </div>
</body>
</html>"""

    def _sample_dirs(self, output_base: Path, sample_safe_name: str) -> Dict[str, Path]:
        sample_root = output_base / sample_safe_name
        paths = {
            "sample_root": sample_root,
            "individual_html": sample_root / "individual_treemaps" / "HTML",
            "individual_png": sample_root / "individual_treemaps" / "PNG",
            "overview_html": sample_root / "7chain_treemaps" / "HTML",
            "overview_png": sample_root / "7chain_treemaps" / "PNG",
        }
        for path in paths.values():
            if path is not sample_root:
                path.mkdir(parents=True, exist_ok=True)
        return paths

    def _get_browser_path(self) -> Path:
        if self._browser_path and self._browser_path.exists():
            return self._browser_path

        candidates = [
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("ProgramFiles", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                self._browser_path = candidate
                return candidate
        raise ValidationError(message="未找到可用的 Edge/Chrome 浏览器，无法生成 treemap PNG。")

    def _get_d3_script_tag(self) -> str:
        if self._d3_script_tag is None:
            self._d3_script_tag = load_d3_script_tag()
        return self._d3_script_tag

    def _build_html_cached(
        self,
        clones: list[dict[str, Any]],
        summary: dict[str, Any],
        title: str,
        source_name: str,
        columns: dict[str, str | None],
        default_min_copy: int,
        top_n: int,
        style: str = "classic",
        layout_mode: str = "tetris",
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
            "style": style,
            "layoutMode": layout_mode,
        }
        html_text = HTML_TEMPLATE.replace("__PAGE_TITLE__", escape_html_text(title))
        html_text = html_text.replace("__D3_SCRIPT__", self._get_d3_script_tag())
        html_text = html_text.replace("__DATA_JSON__", json.dumps(clones, ensure_ascii=False))
        html_text = html_text.replace("__SETTINGS_JSON__", json.dumps(settings, ensure_ascii=False))
        return html_text

    def _render_html_to_png(
        self,
        html_path: Path,
        png_path: Path,
        width: int,
        height: int,
        panel_mode: bool = False,
        scale_factor: int = 3,
    ) -> None:
        browser_path = self._get_browser_path()
        url = html_path.resolve().as_uri()
        if panel_mode:
            url = f"{url}?mode=panel"

        command = [
            str(browser_path),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=1500",
            f"--force-device-scale-factor={scale_factor}",
            f"--window-size={width},{height}",
            f"--screenshot={png_path}",
            url,
        ]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def _trim_white_border(png_path: Path, bg_threshold: int = 248, output_size: Optional[tuple[int, int]] = None) -> None:
        image = Image.open(png_path).convert("RGBA")
        width, height = image.size
        pixels = image.load()

        left, top = width, height
        right, bottom = -1, -1
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if a == 0:
                    continue
                if r < bg_threshold or g < bg_threshold or b < bg_threshold:
                    if x < left:
                        left = x
                    if y < top:
                        top = y
                    if x > right:
                        right = x
                    if y > bottom:
                        bottom = y

        if right >= left and bottom >= top:
            image = image.crop((left, top, right + 1, bottom + 1))

        if output_size:
            image = image.resize(output_size, Image.Resampling.LANCZOS)

        image.save(png_path)

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
    def _build_static_viewer_html(metadata: Dict[str, Any], zip_url: str) -> str:
        viewer_payload = {
            "samples": metadata.get("samples", []),
            "zip_url": zip_url,
        }
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Treemap Viewer</title>
  <style>
    *{{box-sizing:border-box}}
    body{{margin:0;font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f4f6f8;color:#1f2937}}
    .app{{display:grid;grid-template-columns:320px minmax(0,1fr);min-height:100vh}}
    .sidebar{{padding:20px;border-right:1px solid #dbe2ea;background:#ffffff}}
    .sidebar h1{{margin:0 0 8px;font-size:22px}}
    .sidebar p{{margin:0 0 18px;color:#6b7280;font-size:14px;line-height:1.5}}
    .sidebar label{{display:block;margin-bottom:6px;font-size:13px;font-weight:600}}
    .sidebar select,.sidebar button{{width:100%;padding:10px 12px;border-radius:10px;border:1px solid #cfd8e3;font-size:14px;background:#fff}}
    .sidebar .stack{{display:grid;gap:14px}}
    .sidebar .actions{{display:grid;gap:10px;margin-top:14px}}
    .sidebar button{{cursor:pointer;background:#111827;color:#fff;border-color:#111827}}
    .sidebar button.secondary{{background:#fff;color:#111827}}
    .content{{padding:0;background:#ffffff}}
    iframe{{width:100%;height:100vh;border:0;display:block;background:#fff}}
    .meta{{margin-top:14px;padding:12px;border-radius:12px;background:#f8fafc;border:1px solid #e5e7eb;font-size:13px;color:#4b5563}}
    @media (max-width: 1080px){{.app{{grid-template-columns:1fr}} iframe{{height:78vh}}}}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <h1>Treemap Viewer</h1>
      <p>选择样本和链，直接全屏查看单链 treemap。</p>
      <div class="stack">
        <div>
          <label for="sampleSelect">样本</label>
          <select id="sampleSelect"></select>
        </div>
        <div>
          <label for="chainSelect">链</label>
          <select id="chainSelect"></select>
        </div>
      </div>
      <div class="actions">
        <button id="openHtmlBtn" type="button">新窗口打开当前 HTML</button>
        <button id="openPngBtn" class="secondary" type="button">新窗口打开当前 PNG</button>
        <button id="downloadZipBtn" class="secondary" type="button">下载 ZIP</button>
      </div>
      <div class="meta" id="summary"></div>
    </aside>
    <main class="content">
      <iframe id="viewerFrame" title="treemap viewer"></iframe>
    </main>
  </div>
  <script>
    const DATA = {json.dumps(viewer_payload, ensure_ascii=False)};
    const sampleSelect = document.getElementById('sampleSelect');
    const chainSelect = document.getElementById('chainSelect');
    const frame = document.getElementById('viewerFrame');
    const summary = document.getElementById('summary');

    function currentSample() {{
      return (DATA.samples || []).find(sample => sample.sample_name === sampleSelect.value) || null;
    }}

    function updateSummary() {{
      const sample = currentSample();
      if (!sample) {{
        summary.textContent = '没有可用结果。';
        return;
      }}
      summary.textContent = `当前样本: ${{sample.display_name || sample.sample_name}} | 可选链: ${{(sample.chains || []).join(', ')}}`;
    }}

    function updateFrame() {{
      const sample = currentSample();
      const chain = chainSelect.value;
      if (!sample || !sample.individual_treemaps || !sample.individual_treemaps[chain]) {{
        frame.src = 'about:blank';
        updateSummary();
        return;
      }}
      frame.src = sample.individual_treemaps[chain].html;
      updateSummary();
    }}

    function onSampleChange() {{
      const sample = currentSample();
      chainSelect.innerHTML = '';
      if (!sample) {{
        updateFrame();
        return;
      }}
      (sample.chains || []).forEach(chain => {{
        const option = document.createElement('option');
        option.value = chain;
        option.textContent = chain;
        chainSelect.appendChild(option);
      }});
      if (sample.chains && sample.chains.length > 0) {{
        chainSelect.value = sample.chains[0];
      }}
      updateFrame();
    }}

    sampleSelect.addEventListener('change', onSampleChange);
    chainSelect.addEventListener('change', updateFrame);
    document.getElementById('openHtmlBtn').addEventListener('click', () => {{
      const sample = currentSample();
      const chain = chainSelect.value;
      const url = sample && sample.individual_treemaps && sample.individual_treemaps[chain] ? sample.individual_treemaps[chain].html : '';
      if (url) window.open(url, '_blank', 'noopener');
    }});
    document.getElementById('openPngBtn').addEventListener('click', () => {{
      const sample = currentSample();
      const chain = chainSelect.value;
      const url = sample && sample.individual_treemaps && sample.individual_treemaps[chain] ? sample.individual_treemaps[chain].png : '';
      if (url) window.open(url, '_blank', 'noopener');
    }});
    document.getElementById('downloadZipBtn').addEventListener('click', () => {{
      if (DATA.zip_url) window.open(DATA.zip_url, '_blank', 'noopener');
    }});

    (DATA.samples || []).forEach(sample => {{
      const option = document.createElement('option');
      option.value = sample.sample_name;
      option.textContent = sample.display_name || sample.sample_name;
      sampleSelect.appendChild(option);
    }});
    if ((DATA.samples || []).length > 0) {{
      sampleSelect.value = DATA.samples[0].sample_name;
      onSampleChange();
    }} else {{
      updateSummary();
    }}
  </script>
</body>
</html>"""

    def generate_report(
        self,
        samples: List[Dict[str, Any]],
        selected_chains: List[str],
        field_mapping: Dict[str, Any],
        output_name: Optional[str] = None,
        min_copy_default: int = 30,
        top_n: int = 100,
        style: str = "classic",
        layout_mode: str = "tetris",
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

        style = str(style or "classic").strip().lower()
        if style not in {"classic", "minimal"}:
            style = "classic"
        layout_mode = str(layout_mode or "tetris").strip().lower()
        if layout_mode not in {"tetris", "qr"}:
            layout_mode = "tetris"

        overrides = {
            "cdr3": field_mapping.get("cdr3_column"),
            "copy": field_mapping.get("copy_column"),
            "v": field_mapping.get("v_column"),
            "j": field_mapping.get("j_column"),
            "c": None,
            "chain": None,
            "cell_type": None,
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
            total_units += chain_count  # html
            total_units += chain_count  # png
            total_units += 2  # overview html + png

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

        for sample_index, item in enumerate(sample_work_items, start=1):
            sample = item["sample"]
            display_name = item["display_name"]
            sample_safe_name = item["sample_safe_name"]
            sample_dirs = self._sample_dirs(output_base, sample_safe_name)
            chain_files = item["chain_files"]
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
            overview_source_paths: Dict[str, Path] = {}

            for chain_index, chain in enumerate(CHAIN_ORDER_ALL, start=1):
                filepath = chain_files.get(chain)
                if not filepath:
                    continue

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
                        chain_total=len(chain_files),
                        input_file=input_path.name,
                    ),
                )

                columns = self._detect_columns_for_path(input_path, overrides)
                if not columns.get("cdr3") or not columns.get("copy") or not columns.get("v") or not columns.get("j"):
                    raise ValidationError(message=f"{input_path.name} 未识别到 CDR3、copy、V 或 J 列。")

                clones, summary = read_repertoire(input_path, columns)
                if not clones:
                    logger.warning("Treemap input file has no usable rows: %s", input_path)
                    continue

                derived_cell_type = CHAIN_CELL_MAP.get(chain, "Unknown")
                for clone in clones:
                    clone["chain"] = chain
                    clone["cell_type"] = derived_cell_type

                html_filename = f"{sample_safe_name}__{chain}_treemap.html"
                png_filename = f"{sample_safe_name}__{chain}_treemap.png"
                html_path = sample_dirs["individual_html"] / html_filename
                png_path = sample_dirs["individual_png"] / png_filename

                html_content = self._build_html_cached(
                    clones=clones,
                    summary=summary,
                    title=make_title(input_path, f"{display_name} {chain} clonotype tetris map"),
                    source_name=input_path.name,
                    columns=columns,
                    default_min_copy=max(0, int(min_copy_default)),
                    top_n=max(1, int(top_n)),
                    style=style,
                    layout_mode=layout_mode,
                )
                html_path.write_text(html_content, encoding="utf-8")
                advance(
                    "生成单链 HTML",
                    f"{display_name} | {chain} ({chain_index}/{len(chain_files)})",
                    phase="individual_html",
                    sample_name=display_name,
                    sample_index=sample_index,
                    chain_name=chain,
                    chain_index=chain_index,
                    chain_total=len(chain_files),
                    input_file=input_path.name,
                    output_file=html_filename,
                )

                generated_chains.append(chain)
                overview_source_paths[chain] = html_path
                chain_outputs[chain] = {
                    "html": str(html_path.relative_to(output_base)).replace("\\", "/"),
                    "png": str(png_path.relative_to(output_base)).replace("\\", "/"),
                }

            if not generated_chains:
                continue

            overview_html_filename = f"{sample_safe_name}__ALL_treemap.html"
            overview_png_filename = f"{sample_safe_name}__ALL_treemap.png"
            overview_html_path = sample_dirs["overview_html"] / overview_html_filename
            overview_png_path = sample_dirs["overview_png"] / overview_png_filename

            overview_html_path.write_text(
                self._build_overview_html(display_name, overview_source_paths, sample_dirs["overview_html"]),
                encoding="utf-8",
            )
            advance(
                "生成七链 HTML",
                f"{display_name} | overview",
                phase="overview_html",
                sample_name=display_name,
                sample_index=sample_index,
                output_file=overview_html_filename,
            )

            png_tasks: List[tuple[Path, Path, int, int, bool]] = []
            for chain in generated_chains:
                html_path = sample_dirs["individual_html"] / f"{sample_safe_name}__{chain}_treemap.html"
                png_path = sample_dirs["individual_png"] / f"{sample_safe_name}__{chain}_treemap.png"
                png_tasks.append((html_path, png_path, 1200, 1200, True))

            with ThreadPoolExecutor(max_workers=min(6, max(1, len(png_tasks)))) as executor:
                future_map = {
                    executor.submit(self._render_html_to_png, html_path, png_path, width, height, panel_mode): (html_path, png_path)
                    for html_path, png_path, width, height, panel_mode in png_tasks
                }
                for future in as_completed(future_map):
                    future.result()
                    html_path, png_path = future_map[future]
                    chain_name = html_path.stem.split("__")[-1].replace("_treemap", "")
                    advance(
                        "导出单链 PNG",
                        f"{display_name} | {chain_name}",
                        phase="individual_png",
                        sample_name=display_name,
                        sample_index=sample_index,
                        chain_name=chain_name,
                        chain_total=len(generated_chains),
                        input_file=html_path.name,
                        output_file=png_path.name,
                    )

            for _, png_path, _, _, _ in png_tasks:
                self._trim_white_border(png_path, output_size=(1800, 1800))

            overview_png_sources = {
                chain: sample_dirs["individual_png"] / f"{sample_safe_name}__{chain}_treemap.png"
                for chain in generated_chains
            }
            self._compose_overview_png_from_individuals(overview_png_sources, overview_png_path)
            advance(
                "导出七链 PNG",
                f"{display_name} | overview",
                phase="overview_png",
                sample_name=display_name,
                sample_index=sample_index,
                output_file=overview_png_filename,
            )

            result_samples.append(
                {
                    "sample_name": display_name,
                    "display_name": display_name,
                    "sample_safe_name": sample_safe_name,
                    "chains": generated_chains,
                    "individual_treemaps": chain_outputs,
                    "overview_treemaps": {
                        "html": str(overview_html_path.relative_to(output_base)).replace("\\", "/"),
                        "png": str(overview_png_path.relative_to(output_base)).replace("\\", "/"),
                    },
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
            "style": style,
            "layout_mode": layout_mode,
            "samples": result_samples,
        }
        metadata_path = output_base / self._METADATA_FILE_NAME
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        viewer_path = output_base / self._VIEWER_FILE_NAME
        viewer_path.write_text(
            self._build_static_viewer_html(
                metadata=metadata,
                zip_url=f"/api/treemap/export-zip/{job_id}",
            ),
            encoding="utf-8",
        )
        advance(
            "写入结果清单",
            "正在写入 metadata.json 和 viewer.html",
            phase="metadata",
            output_file=f"{self._METADATA_FILE_NAME}, {self._VIEWER_FILE_NAME}",
        )
        emit(100.0, "任务完成", f"共生成 {len(result_samples)} 个样本的 treemap 结果。")

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
