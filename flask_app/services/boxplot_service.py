"""
BoxPlot analysis service for DB alignment results.
"""

from __future__ import annotations

import html
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy.stats import mannwhitneyu

from flask_app.services.figure_style import MUTED_CATEGORY_COLORS, PALETTE, apply_publication_style


@dataclass
class BoxPlotReport:
    job_id: str
    output_base: Path
    viewer_path: Path
    png_paths: List[str]
    pvalue_paths: List[str]
    csv_paths: List[str]
    significant_paths: List[str]
    zip_path: str
    metadata: Dict[str, Any]


_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]

_NATURE_COLORS = MUTED_CATEGORY_COLORS
_POINT_COLOR = PALETTE["neutral_dark"]
_AXIS_COLOR = PALETTE["neutral_dark"]


def _apply_publication_style() -> None:
    apply_publication_style(font_size=9.5, axes_linewidth=0.9)


_apply_publication_style()


def _try_read_csv(filepath, **kwargs):
    """Read a CSV/TSV/XLSX with encoding fallback — tries UTF-8, then GBK variants, then latin-1."""
    suffix = str(filepath).lower()
    if suffix.endswith((".xlsx", ".xls", ".xlsm")):
        kwargs.pop("sep", None)
        kwargs.pop("low_memory", None)
        kwargs.pop("encoding", None)
        return pd.read_excel(filepath, sheet_name=kwargs.pop("sheet_name", 0), **kwargs)
    sep = kwargs.pop("sep", ",")
    if suffix.endswith(".tsv"):
        sep = "\t"
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(filepath, encoding=enc, sep=sep, **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    # Last resort: latin-1 decodes any byte without error
    return pd.read_csv(filepath, encoding="latin-1", sep=sep, **kwargs)


class BoxPlotService:
    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    def generate_report(
        self,
        *,
        datapoint_path: str,
        classification_begin: Optional[str] = None,
        classification_over: Optional[str] = None,
        grouptype_fields: Optional[List[str]] = None,
        param_begin: str,
        param_over: str,
        group_order: Optional[str] = None,
        pvalue_threshold: float = 0.05,
        output_name: Optional[str] = None,
        progress_callback=None,
    ) -> BoxPlotReport:
        datapoint = Path(datapoint_path)
        if not datapoint.exists():
            raise FileNotFoundError(f"Datapoint file not found: {datapoint_path}")

        df = _try_read_csv(datapoint, low_memory=False)
        df.fillna(0, inplace=True)

        columns = df.columns.tolist()

        param_begin_idx = columns.index(param_begin)
        param_over_idx = columns.index(param_over) + 1
        param_columns = columns[param_begin_idx:param_over_idx]

        if grouptype_fields:
            class_columns = [c for c in grouptype_fields if c in columns]
        elif classification_begin and classification_begin.strip():
            begin_idx = columns.index(classification_begin)
            over_idx = columns.index(classification_over) + 1
            class_columns = columns[begin_idx:over_idx]
        else:
            class_columns = []

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name or "boxplot")
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        # Parse group_order: supports JSON dict per-field or simple comma-separated
        parsed_order = None
        if group_order and group_order.strip():
            s = group_order.strip()
            if s.startswith("{"):
                try:
                    parsed_order = json.loads(s)
                except json.JSONDecodeError:
                    parsed_order = [x.strip() for x in s.split(",") if x.strip()]
            else:
                parsed_order = [x.strip() for x in s.split(",") if x.strip()]

        png_paths: List[str] = []
        pvalue_paths: List[str] = []
        csv_paths: List[str] = []
        significant_paths: List[str] = []
        skipped_insufficient = 0

        if class_columns:
            png_paths, pvalue_paths, csv_paths, significant_paths, plot_infos, skipped_insufficient = self._generate_grouped(
                df, class_columns, param_columns,
                pvalue_threshold, output_base, progress_callback,
                parsed_order,
            )
        else:
            png_paths, csv_paths = self._generate_ungrouped(
                df, param_columns, output_base, progress_callback,
            )
            plot_infos = []
            skipped_insufficient = 0

        # Count significant vs non-significant
        sig_plots = [p for p in plot_infos if p.get("is_significant")]
        ns_plots = [p for p in plot_infos if not p.get("is_significant")]

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "datapoint_path": str(datapoint),
            "classification_begin": classification_begin,
            "classification_over": classification_over,
            "grouptype_fields": grouptype_fields,
            "param_begin": param_begin,
            "param_over": param_over,
            "group_order": group_order,
            "pvalue_threshold": pvalue_threshold,
            "class_columns": class_columns,
            "param_columns": param_columns,
            "png_paths": png_paths,
            "pvalue_paths": pvalue_paths,
            "csv_paths": csv_paths,
            "significant_paths": significant_paths,
            "class_type_counts": {class_col: len(df[class_col].dropna().unique()) for class_col in class_columns} if class_columns else {},
            "skipped_insufficient_data": skipped_insufficient,
            "plot_count": len(png_paths),
            "significant_plot_count": len(sig_plots),
            "non_significant_plot_count": len(ns_plots),
        }
        (output_base / "boxplot_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        # Generate viewer.html
        viewer_path = output_base / "viewer.html"
        viewer_path.write_text(
            self._build_viewer_html(
                metadata=metadata,
                plot_infos=plot_infos,
                png_urls=self._relative_urls(png_paths, output_base),
                output_base=output_base,
            ),
            encoding="utf-8",
        )

        # Generate ZIP bundle
        zip_path = output_base / "boxplot_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for png_path in png_paths:
                p = Path(png_path)
                if p.exists():
                    # Store as boxplots/{class_col}/{param}.png
                    parts = p.relative_to(output_base).parts
                    arcname = "boxplots/" + "/".join(parts)
                    zf.write(p, arcname)
            for pv_path in pvalue_paths:
                p = Path(pv_path)
                if p.exists():
                    arcname = "pvalues/" + p.relative_to(output_base).name
                    zf.write(p, arcname)
            for csv_path in csv_paths:
                p = Path(csv_path)
                if p.exists():
                    # Store as data/{class_col}/csvfiles/{param}.csv
                    parts = p.relative_to(output_base).parts
                    arcname = "data/" + "/".join(parts)
                    zf.write(p, arcname)
            for sig_path in significant_paths:
                p = Path(sig_path)
                if p.exists():
                    arcname = "significance/" + p.relative_to(output_base).name
                    zf.write(p, arcname)

        if progress_callback:
            msg = f"Generated {len(png_paths)} plot(s)"
            if skipped_insufficient > 0:
                msg += f" — {skipped_insufficient} comparison(s) skipped (groups need ≥2 data points)"
            progress_callback(100, "BoxPlot completed", msg)

        return BoxPlotReport(
            job_id=job_id,
            output_base=output_base,
            viewer_path=viewer_path,
            png_paths=png_paths,
            pvalue_paths=pvalue_paths,
            csv_paths=csv_paths,
            significant_paths=significant_paths,
            zip_path=str(zip_path),
            metadata=metadata,
        )

    @staticmethod
    def _relative_urls(paths: List[str], output_base: Path) -> List[str]:
        result = []
        for p in paths:
            try:
                result.append(str(Path(p).relative_to(output_base).as_posix()))
            except ValueError:
                result.append(p)
        return result

    def _build_viewer_html(
        self,
        *,
        metadata: Dict[str, Any],
        plot_infos: List[Dict[str, Any]],
        png_urls: List[str],
        output_base: Path,
    ) -> str:
        job_id = metadata.get("job_id", "")
        class_columns = metadata.get("class_columns", [])
        param_columns = metadata.get("param_columns", [])
        pvalue_threshold = metadata.get("pvalue_threshold", 0.05)
        sig_count = metadata.get("significant_plot_count", 0)
        total_count = metadata.get("plot_count", 0)
        skipped = metadata.get("skipped_insufficient_data", 0)
        grouptype_fields = metadata.get("grouptype_fields", [])
        datapoint_path = metadata.get("datapoint_path", "")

        # Build plot cards HTML — grouped by class_col
        by_class: Dict[str, List[Dict[str, Any]]] = {}
        for p in plot_infos:
            by_class.setdefault(p["class_col"], []).append(p)

        # Build all plots JSON for JS filtering
        plot_infos_json = json.dumps(plot_infos, ensure_ascii=False).replace("</", "<\\/")

        def _render_card(p: Dict[str, Any]) -> str:
            class_col = html.escape(str(p.get("class_col", "")))
            param = html.escape(str(p.get("param", "")))
            png = html.escape(str(p.get("png", "")))
            is_sig = p.get("is_significant", False)
            badge_text = "显著" if is_sig else "非显著"
            badge_class = "is-sig" if is_sig else "is-ns"
            sig_pairs = p.get("significant_pairs") or []

            pairs_html = ""
            if sig_pairs:
                pairs_html = "<div class=\"pvalue-list\">" + "".join(
                    f"<span>{html.escape(sp['group1'])} vs {html.escape(sp['group2'])} p={float(sp['pvalue']):.4g}</span>"
                    for sp in sig_pairs[:10]
                ) + "</div>"
            return f"""<article class="plot-card" data-class="{class_col}" data-sig="{'1' if is_sig else '0'}">
              <div class="plot-head">
                <div>
                  <strong>{param}</strong>
                  <span>{class_col}</span>
                </div>
                <em class="{badge_class}">{badge_text}</em>
              </div>
              <a href="{png}" target="_blank" rel="noopener">
                <img src="{png}" alt="{param}" loading="lazy">
              </a>
              {pairs_html}
            </article>"""

        cards_html = "".join(_render_card(p) for p in plot_infos) or '<div class="empty-txt">没有生成箱线图。</div>'

        # Class field filter chips
        class_chips = "".join(
            f'<span class="filter-chip is-active" data-class="{html.escape(c)}">{html.escape(c)}</span>'
            for c in class_columns
        )
        if class_columns:
            class_chips += '<span class="filter-chip is-active" data-class="__all__">全部</span>'
        else:
            class_chips = '<span class="filter-chip is-active">(无分类字段)</span>'

        summary_cards = [
            ("分类字段", ", ".join(grouptype_fields) if grouptype_fields else "未分组"),
            ("参数列数", str(len(param_columns))),
            ("P-value 阈值", str(pvalue_threshold)),
            ("显著箱线图", f"{sig_count} / {total_count}" if total_count else "-"),
            ("跳过比较", str(skipped)),
        ]
        summary_html = "".join(
            f'<div class="stat-item"><strong>{html.escape(label)}</strong><span>{html.escape(val)}</span></div>'
            for label, val in summary_cards
        )

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Profile 分析 — 箱线图结果</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Microsoft YaHei", sans-serif; background: #f4f7fa; color: #1e293b; line-height: 1.6; }}
    .page {{ max-width: 1440px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }}
    .header {{ background: #fff; border-radius: 18px; padding: 1.5rem 1.8rem; margin-bottom: 1.2rem; border: 1px solid #dee6ed; box-shadow: 0 8px 24px rgba(0,0,0,.04); }}
    .header h1 {{ font-size: 1.35rem; font-weight: 720; margin-bottom: .35rem; }}
    .header .meta {{ color: #5f7d94; font-size: .88rem; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: .65rem; margin-top: 1rem; }}
    .stat-item {{ flex: 1 1 140px; min-width: 130px; background: #f6f9fc; border-radius: 12px; padding: .75rem 1rem; border: 1px solid #dee8f0; }}
    .stat-item strong {{ display: block; font-size: .72rem; color: #5f7d94; text-transform: uppercase; letter-spacing: .04em; margin-bottom: .22rem; }}
    .stat-item span {{ font-size: .95rem; font-weight: 680; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: .55rem; align-items: center; margin-bottom: 1rem; }}
    .sig-toggle {{ display: inline-flex; align-items: center; gap: .45rem; padding: .52rem 1rem; border-radius: 999px; border: 1px solid #c5d4e0; background: #fff; cursor: pointer; font-size: .84rem; font-weight: 600; transition: border-color .15s, background .15s; user-select: none; }}
    .sig-toggle:hover {{ border-color: #6fa3c4; }}
    .sig-toggle.is-active {{ border-color: #0b6b5f; background: #ecfbf6; color: #0b6b5f; }}
    .filter-chip {{ display: inline-flex; align-items: center; padding: .38rem .72rem; border-radius: 999px; border: 1px solid #c5d4e0; background: #fff; cursor: pointer; font-size: .8rem; transition: all .15s; user-select: none; }}
    .filter-chip:hover {{ border-color: #6fa3c4; }}
    .filter-chip.is-active {{ border-color: #11597c; background: #d8ecfa; box-shadow: 0 0 0 1px #11597c; font-weight: 680; }}
    .filter-chip.is-active[data-sig-only="1"] {{ border-color: #0b6b5f; background: #ecfbf6; box-shadow: 0 0 0 1px #0b6b5f; color: #0b6b5f; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: .85rem; }}
    .plot-card {{ background: #fff; border-radius: 14px; border: 1px solid #dee6ed; overflow: hidden; transition: transform .15s, box-shadow .15s; }}
    .plot-card:hover {{ box-shadow: 0 6px 18px rgba(0,0,0,.07); }}
    .plot-card.is-hidden {{ display: none; }}
    .plot-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: .5rem; padding: .7rem .85rem; border-bottom: 1px solid #edf2f6; background: #fbfdfe; }}
    .plot-head strong {{ display: block; font-size: .82rem; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .plot-head span {{ display: block; color: #5f7d94; font-size: .72rem; margin-top: .05rem; }}
    .plot-head em {{ flex: 0 0 auto; font-size: .68rem; font-weight: 700; padding: .2rem .48rem; border-radius: 999px; font-style: normal; }}
    .plot-head em.is-sig {{ background: #dcfce7; color: #166534; }}
    .plot-head em.is-ns {{ background: #f1f5f9; color: #64748b; }}
    .plot-card img {{ width: 100%; height: auto; display: block; cursor: pointer; }}
    .pvalue-list {{ padding: .5rem .85rem .65rem; display: flex; flex-wrap: wrap; gap: .3rem; }}
    .pvalue-list span {{ display: inline-block; font-size: .68rem; background: #fef9e7; border: 1px solid #fde68a; border-radius: 6px; padding: .15rem .42rem; color: #92400e; }}
    .empty-txt {{ grid-column: 1 / -1; text-align: center; padding: 2.5rem 1rem; color: #8397a8; font-size: .92rem; }}
    .back-link {{ display: inline-flex; align-items: center; gap: .35rem; color: #11597c; text-decoration: none; font-size: .85rem; margin-bottom: .8rem; }}
    .back-link:hover {{ text-decoration: underline; }}
    @media (max-width: 640px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<div class="page">
  <a class="back-link" href="javascript:history.back()">← 返回</a>
  <div class="header">
    <h1>Profile 分析 — 箱线图结果</h1>
    <div class="meta">数据文件: {html.escape(datapoint_path)} &nbsp;|&nbsp; 任务: {html.escape(job_id)}</div>
    <div class="stats">{summary_html}</div>
  </div>
  <div class="toolbar">
    <button class="sig-toggle" id="sigToggle" title="切换显示全部 / 仅显著">🔍 仅显示显著</button>
    <span style="color:#8397a8;font-size:.76rem;margin-left:.35rem;">点击筛选分类字段：</span>
    <div id="classChips">{class_chips}</div>
  </div>
  <div class="grid" id="plotGrid">{cards_html}</div>
</div>
<script>
(function() {{
  const cards = document.querySelectorAll('.plot-card');
  const sigToggle = document.getElementById('sigToggle');
  const classChips = document.querySelectorAll('#classChips .filter-chip[data-class]');
  let sigOnly = false;
  let activeClass = '__all__';

  function applyFilters() {{
    cards.forEach(card => {{
      const matchesSig = !sigOnly || card.dataset.sig === '1';
      const matchesClass = activeClass === '__all__' || card.dataset.class === activeClass;
      card.classList.toggle('is-hidden', !matchesSig || !matchesClass);
    }});
  }}

  sigToggle.addEventListener('click', () => {{
    sigOnly = !sigOnly;
    sigToggle.classList.toggle('is-active', sigOnly);
    sigToggle.textContent = sigOnly ? '✅ 仅显示显著' : '🔍 仅显示显著';
    sigToggle.setAttribute('data-sig-only', sigOnly ? '1' : '0');
    applyFilters();
  }});

  classChips.forEach(chip => {{
    chip.addEventListener('click', () => {{
      activeClass = chip.dataset.class;
      classChips.forEach(c => c.classList.remove('is-active'));
      chip.classList.add('is-active');
      applyFilters();
    }});
  }});
}})();
</script>
</body>
</html>"""

    def generate_significance_boxplots(
        self,
        *,
        output_base: Path,
        sources: List[Dict[str, Any]],
        category_columns: List[str],
        category_mode: str = "single",
        metric_columns: Optional[List[str]] = None,
        metric_pattern: Optional[str] = None,
        pvalue_threshold: float = 0.05,
        min_group_n: int = 2,
        output_subdir: str = "boxplot",
    ) -> Dict[str, Any]:
        """Generate grouped significance boxplots for prepared tabular sources."""
        output_base = Path(output_base)
        boxplot_dir = output_base / output_subdir
        boxplot_dir.mkdir(parents=True, exist_ok=True)

        compiled_metric_pattern = re.compile(metric_pattern) if metric_pattern else None
        category_columns = [str(col) for col in category_columns if str(col or "").strip()]

        all_plot_records: List[Dict[str, Any]] = []
        significant_plot_records: List[Dict[str, Any]] = []
        non_significant_plot_records: List[Dict[str, Any]] = []
        significant_rows: List[Dict[str, Any]] = []

        for source in sources:
            source_path = Path(source.get("path") or "")
            if not source_path.exists():
                continue
            try:
                df = _try_read_csv(source_path, low_memory=False)
            except Exception:
                continue
            if df.empty:
                continue

            if metric_columns:
                current_metrics = [col for col in metric_columns if col in df.columns]
            elif compiled_metric_pattern:
                current_metrics = [col for col in df.columns if compiled_metric_pattern.match(str(col))]
            else:
                current_metrics = []
            if not current_metrics:
                continue

            available_categories = [col for col in category_columns if col in df.columns]
            for cat_col in available_categories:
                df[cat_col] = df[cat_col].astype(str)

            if available_categories:
                analyses = self._build_grouped_analysis_plan(
                    df=df,
                    category_columns=available_categories,
                    category_mode=category_mode,
                )
                for analysis in analyses:
                    group_col = analysis["group_col"]
                    subset = analysis["df"]
                    context = analysis.get("context") or ""
                    group_values = self._ordered_nonempty_values(subset[group_col])
                    if len(group_values) < 2:
                        continue

                    for param in current_metrics:
                        all_pairs: List[Dict[str, Any]] = []
                        significant_pairs: List[Dict[str, Any]] = []
                        for group_a, group_b in combinations(group_values, 2):
                            series_a = pd.to_numeric(
                                subset[subset[group_col] == group_a][param],
                                errors="coerce",
                            ).dropna()
                            series_b = pd.to_numeric(
                                subset[subset[group_col] == group_b][param],
                                errors="coerce",
                            ).dropna()
                            if len(series_a) < min_group_n or len(series_b) < min_group_n:
                                continue
                            pvalue = float(mannwhitneyu(series_a, series_b, alternative="two-sided").pvalue)
                            if pd.isna(pvalue):
                                continue
                            row = {
                                "source": source.get("source", ""),
                                "source_label": source.get("label", ""),
                                "context": context,
                                "class_col": group_col,
                                "group1": group_a,
                                "group2": group_b,
                                "param": param,
                                "chain": self._chain_from_metric_param(param),
                                "pvalue": pvalue,
                            }
                            all_pairs.append(row)
                            if pvalue <= pvalue_threshold:
                                significant_rows.append(row)
                                significant_pairs.append(row)

                        if not all_pairs:
                            continue

                        significance = "significant" if significant_pairs else "non_significant"
                        rel_dir = Path(output_subdir) / significance / self._sanitize_name(source.get("label", "source"))
                        if context:
                            rel_dir = rel_dir / self._sanitize_name(context)
                        rel_dir = rel_dir / self._sanitize_name(group_col)
                        target_dir = output_base / rel_dir
                        target_dir.mkdir(parents=True, exist_ok=True)
                        safe_param = self._sanitize_name(param)
                        png_path = target_dir / f"{safe_param}.png"
                        csv_path = target_dir / f"{safe_param}.csv"

                        keep_cols = ["sample", group_col, param] if "sample" in subset.columns else [group_col, param]
                        plot_df = subset[keep_cols].copy()
                        plot_df[param] = pd.to_numeric(plot_df[param], errors="coerce")
                        plot_df = plot_df.dropna(subset=[group_col, param])
                        plot_df = pd.concat(
                            [plot_df[plot_df[group_col] == value] for value in group_values],
                            ignore_index=True,
                        )
                        if plot_df.empty:
                            continue
                        plot_df.to_csv(csv_path, index=False)
                        self._save_publication_boxplot(
                            plot_df=plot_df,
                            group_col=group_col,
                            param=param,
                            group_values=group_values,
                            significant_pairs=significant_pairs,
                            output_path=png_path,
                        )

                        plot_record = {
                            "source": source.get("source", ""),
                            "source_label": source.get("label", ""),
                            "context": context,
                            "class_col": group_col,
                            "param": param,
                            "chain": self._chain_from_metric_param(param),
                            "significance": significance,
                            "is_significant": bool(significant_pairs),
                            "png": rel_dir.joinpath(f"{safe_param}.png").as_posix(),
                            "csv": rel_dir.joinpath(f"{safe_param}.csv").as_posix(),
                            "pvalues": [
                                {
                                    "group1": row["group1"],
                                    "group2": row["group2"],
                                    "pvalue": row["pvalue"],
                                }
                                for row in significant_pairs
                            ],
                            "all_pvalues": [
                                {
                                    "group1": row["group1"],
                                    "group2": row["group2"],
                                    "pvalue": row["pvalue"],
                                }
                                for row in all_pairs
                            ],
                        }
                        all_plot_records.append(plot_record)
                        if significant_pairs:
                            significant_plot_records.append(plot_record)
                        else:
                            non_significant_plot_records.append(plot_record)
            else:
                for param in current_metrics:
                    try:
                        safe_param = self._sanitize_name(param)
                        rel_dir = (
                            Path(output_subdir)
                            / "non_significant"
                            / self._sanitize_name(source.get("label", "source"))
                            / "ratio_distribution"
                        )
                        target_dir = output_base / rel_dir
                        target_dir.mkdir(parents=True, exist_ok=True)
                        png_path = target_dir / f"{safe_param}.png"
                        csv_path = target_dir / f"{safe_param}.csv"

                        keep_cols = ["sample", param] if "sample" in df.columns else [param]
                        plot_df = df[keep_cols].copy()
                        plot_df[param] = pd.to_numeric(plot_df[param], errors="coerce")
                        plot_df = plot_df.dropna(subset=[param])
                        if len(plot_df) < min_group_n:
                            continue
                        plot_df.to_csv(csv_path, index=False)
                        self._save_publication_ungrouped_boxplot(
                            plot_df=plot_df,
                            param=param,
                            output_path=png_path,
                        )
                        plot_record = {
                            "source": source.get("source", ""),
                            "source_label": source.get("label", ""),
                            "context": "ratio_distribution",
                            "class_col": "All Samples",
                            "param": param,
                            "chain": self._chain_from_metric_param(param),
                            "significance": "non_significant",
                            "is_significant": False,
                            "png": rel_dir.joinpath(f"{safe_param}.png").as_posix(),
                            "csv": rel_dir.joinpath(f"{safe_param}.csv").as_posix(),
                            "pvalues": [],
                            "all_pvalues": [],
                        }
                        all_plot_records.append(plot_record)
                        non_significant_plot_records.append(plot_record)
                    except Exception:
                        continue

        summary_path = ""
        if significant_rows:
            sig_df = pd.DataFrame(significant_rows).sort_values(["source", "class_col", "param", "pvalue"])
            sig_path = boxplot_dir / "significant_pvalue_all.csv"
            sig_df.to_csv(sig_path, index=False)
            summary_path = str(sig_path)

        return {
            "all_plots": all_plot_records,
            "significant_plots": significant_plot_records,
            "non_significant_plots": non_significant_plot_records,
            "significant_rows": significant_rows,
            "significant_summary_path": summary_path,
        }

    @staticmethod
    def _build_grouped_analysis_plan(
        *,
        df: pd.DataFrame,
        category_columns: List[str],
        category_mode: str,
    ) -> List[Dict[str, Any]]:
        if str(category_mode or "").lower() == "cross" and len(category_columns) >= 2:
            first, second = category_columns[0], category_columns[1]
            analyses: List[Dict[str, Any]] = []
            for outer_col, group_col in ((first, second), (second, first)):
                for value in BoxPlotService._ordered_nonempty_values(df[outer_col]):
                    subset = df[df[outer_col].astype(str) == str(value)].copy()
                    if len(subset) < 2:
                        continue
                    analyses.append({
                        "df": subset,
                        "group_col": group_col,
                        "context": f"{outer_col}={value}",
                    })
            return analyses

        return [
            {"df": df, "group_col": col, "context": ""}
            for col in category_columns
        ]

    @staticmethod
    def _ordered_nonempty_values(series: pd.Series) -> List[str]:
        values: List[str] = []
        for raw_value in series.dropna().tolist():
            value = str(raw_value).strip()
            if not value or value in {"0", "0.0"}:
                continue
            if value not in values:
                values.append(value)
        return values

    @staticmethod
    def _chain_from_metric_param(param: str) -> str:
        match = re.match(r"^(TRA|TRB)_", str(param or ""), flags=re.IGNORECASE)
        return match.group(1).upper() if match else ""

    @staticmethod
    def _sanitize_name(value: Any) -> str:
        text = str(value or "item").strip()
        text = re.sub(r"[^\w.\-]+", "_", text, flags=re.UNICODE).strip("._")
        return text or "item"

    @staticmethod
    def _normalise_significant_pairs(significant_pairs: List[Any]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for pair in significant_pairs or []:
            if isinstance(pair, dict):
                result.append({
                    "group1": str(pair.get("group1", "")),
                    "group2": str(pair.get("group2", "")),
                    "pvalue": float(pair.get("pvalue", 1.0)),
                })
            elif isinstance(pair, (list, tuple)) and len(pair) >= 3:
                result.append({
                    "group1": str(pair[0]),
                    "group2": str(pair[1]),
                    "pvalue": float(pair[2]),
                })
        return result

    @staticmethod
    def _jitter_positions(center: float, count: int) -> List[float]:
        if count <= 1:
            return [center] * max(count, 0)
        pattern = [((i % 7) - 3) * 0.026 for i in range(count)]
        return [center + offset for offset in pattern]

    @staticmethod
    def _save_publication_boxplot(
        *,
        plot_df: pd.DataFrame,
        group_col: str,
        param: str,
        group_values: List[str],
        significant_pairs: List[Any],
        output_path: Path,
    ) -> None:
        _apply_publication_style()
        plot_df = plot_df[[group_col, param]].copy()
        plot_df[param] = pd.to_numeric(plot_df[param], errors="coerce")
        plot_df = plot_df.dropna(subset=[group_col, param])
        if plot_df.empty:
            return

        data = [
            plot_df[plot_df[group_col].astype(str) == str(value)][param].dropna().tolist()
            for value in group_values
        ]
        data = [values for values in data if values]
        labels = [
            str(value)
            for value in group_values
            if not plot_df[plot_df[group_col].astype(str) == str(value)][param].dropna().empty
        ]
        if not data:
            return

        fig_width = min(max(0.48 * len(labels) + 1.4, 2.6), 6.2)
        fig, ax = plt.subplots(figsize=(fig_width, 3.15))
        box = ax.boxplot(
            data,
            labels=labels,
            patch_artist=True,
            widths=0.52,
            showfliers=False,
            medianprops={"color": "#272727", "linewidth": 1.05},
            whiskerprops={"color": _AXIS_COLOR, "linewidth": 0.7},
            capprops={"color": _AXIS_COLOR, "linewidth": 0.7},
            boxprops={"edgecolor": _AXIS_COLOR, "linewidth": 0.75},
        )
        for index, patch in enumerate(box["boxes"]):
            patch.set_facecolor(_NATURE_COLORS[index % len(_NATURE_COLORS)])
            patch.set_alpha(0.72)

        for index, values in enumerate(data, start=1):
            ax.scatter(
                BoxPlotService._jitter_positions(index, len(values)),
                values,
                s=10,
                color=_POINT_COLOR,
                alpha=0.55,
                linewidths=0,
                zorder=3,
            )

        pvalue_text = "\n".join(
            f"{row['group1']} vs {row['group2']}: p={row['pvalue']:.3g}"
            for row in BoxPlotService._normalise_significant_pairs(significant_pairs)[:4]
        )
        if len(significant_pairs or []) > 4:
            pvalue_text += f"\n+{len(significant_pairs) - 4} more"
        if pvalue_text:
            ax.text(
                0.02,
                0.98,
                pvalue_text,
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=8.5,
                fontweight="bold",
                color="#243746",
                bbox={"boxstyle": "round,pad=.28", "fc": "#ffffff", "ec": "#d7e2e8", "alpha": 0.92},
            )

        ax.set_xlabel("")
        ax.set_ylabel(param, fontsize=9, fontweight="bold")
        ax.tick_params(axis="x", labelrotation=45, labelsize=8.5, length=2.2, width=0.55, color=_AXIS_COLOR)
        ax.tick_params(axis="y", labelsize=8.5, length=2.2, width=0.55, color=_AXIS_COLOR)
        ax.grid(axis="y", color="#E5E7EB", linewidth=0.4, alpha=0.85)
        ax.set_axisbelow(True)
        fig.tight_layout(pad=0.45)
        fig.savefig(output_path, dpi=600, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    @staticmethod
    def _save_publication_ungrouped_boxplot(
        *,
        plot_df: pd.DataFrame,
        param: str,
        output_path: Path,
    ) -> None:
        _apply_publication_style()
        values = pd.to_numeric(plot_df[param], errors="coerce").dropna().tolist()
        if not values:
            return

        fig, ax = plt.subplots(figsize=(2.5, 3.05))
        box = ax.boxplot(
            [values],
            labels=["All samples"],
            patch_artist=True,
            widths=0.42,
            showfliers=False,
            medianprops={"color": "#272727", "linewidth": 1.05},
            whiskerprops={"color": _AXIS_COLOR, "linewidth": 0.7},
            capprops={"color": _AXIS_COLOR, "linewidth": 0.7},
            boxprops={"edgecolor": _AXIS_COLOR, "linewidth": 0.75},
        )
        box["boxes"][0].set_facecolor(_NATURE_COLORS[1])
        box["boxes"][0].set_alpha(0.72)
        ax.scatter(
            BoxPlotService._jitter_positions(1, len(values)),
            values,
            s=10,
            color=_POINT_COLOR,
            alpha=0.55,
            linewidths=0,
            zorder=3,
        )
        info_text = f"n={len(values)}\nmedian={float(pd.Series(values).median()):.4g}"
        ax.text(
            0.98,
            0.98,
            info_text,
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=8.5,
            fontweight="bold",
            color="#243746",
            bbox={"boxstyle": "round,pad=.28", "fc": "#ffffff", "ec": "#d7e2e8", "alpha": 0.92},
        )
        ax.set_ylabel(param, fontsize=9, fontweight="bold")
        ax.tick_params(axis="x", labelsize=8.5, length=2.2, width=0.55, color=_AXIS_COLOR)
        ax.tick_params(axis="y", labelsize=8.5, length=2.2, width=0.55, color=_AXIS_COLOR)
        ax.grid(axis="y", color="#E5E7EB", linewidth=0.4, alpha=0.85)
        ax.set_axisbelow(True)
        fig.tight_layout(pad=0.45)
        fig.savefig(output_path, dpi=600, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    def _generate_grouped(
        self,
        df: pd.DataFrame,
        class_columns: List[str],
        param_columns: List[str],
        pvalue_threshold: float,
        output_base: Path,
        progress_callback,
        group_order: Optional[List[str]] = None,
    ):
        png_paths: List[str] = []
        pvalue_paths: List[str] = []
        csv_paths: List[str] = []
        significant_paths: List[str] = []
        plot_infos: List[Dict[str, Any]] = []
        total_steps = len(class_columns) * len(param_columns)
        step = 0
        skipped_insufficient = 0

        for class_col in class_columns:
            class_dir = output_base / class_col
            class_dir.mkdir(parents=True, exist_ok=True)
            csv_dir = class_dir / "csvfiles"
            csv_dir.mkdir(parents=True, exist_ok=True)

            raw_types = sorted(df[class_col].dropna().unique().tolist())
            if group_order:
                if isinstance(group_order, dict):
                    field_order = group_order.get(class_col, "")
                    if field_order:
                        ordered = [x.strip() for x in field_order.split(",") if x.strip()]
                        class_types = [t for t in ordered if t in raw_types] + [t for t in raw_types if t not in ordered]
                    else:
                        class_types = raw_types
                else:
                    class_types = [t for t in group_order if t in raw_types] + [t for t in raw_types if t not in group_order]
            else:
                class_types = raw_types
            pvalue_records: List[Dict[str, Any]] = []

            for param in param_columns:
                step += 1
                if progress_callback:
                    progress_callback(
                        5 + int(step / max(total_steps, 1) * 90),
                        "BoxPlot analysis",
                        f"Processing {class_col} / {param}",
                        {"class_col": class_col, "param": param},
                    )

                combo_list = list(combinations(class_types, 2))
                significant_pairs: List[tuple] = []
                for combo in combo_list:
                    try:
                        group_a = df[df[class_col] == combo[0]][param].dropna()
                        group_b = df[df[class_col] == combo[1]][param].dropna()
                        if len(group_a) < 2 or len(group_b) < 2:
                            skipped_insufficient += 1
                            continue
                        pvalue = mannwhitneyu(group_a, group_b, alternative="two-sided").pvalue
                        pvalue_records.append({
                            "class": class_col,
                            "group_a": combo[0],
                            "group_b": combo[1],
                            "param": param,
                            "pvalue": pvalue,
                        })
                        if pvalue <= pvalue_threshold:
                            significant_pairs.append((combo[0], combo[1], pvalue))
                    except Exception:
                        continue

                png_rel = str((class_dir / f"{param}.png").relative_to(output_base))
                self._plot_boxplot(df, class_col, param, class_types,
                                   significant_pairs, class_dir)
                png_paths.append(str(class_dir / f"{param}.png"))

                sig_pairs_data = [
                    {"group1": str(a), "group2": str(b), "pvalue": float(p)}
                    for a, b, p in significant_pairs
                ]
                plot_infos.append({
                    "class_col": class_col,
                    "param": param,
                    "png": png_rel,
                    "is_significant": len(significant_pairs) > 0,
                    "significant_pairs": sig_pairs_data,
                    "pvalue_threshold": pvalue_threshold,
                })

                plot_df = df[(["sample"] if "sample" in df.columns else []) + [class_col, param]]
                concat_df = pd.concat([
                    plot_df[plot_df[class_col] == t] for t in class_types
                ])
                csv_path = csv_dir / f"{param}.csv"
                concat_df.to_csv(csv_path, index=False)
                csv_paths.append(str(csv_path))

            df_pvalues = pd.DataFrame(pvalue_records)
            if not df_pvalues.empty:
                pvalue_csv = class_dir / f"{class_col}_pvalues.csv"
                df_pvalues.to_csv(pvalue_csv, index=False)
                pvalue_paths.append(str(pvalue_csv))

                sig_df = df_pvalues[df_pvalues["pvalue"] <= pvalue_threshold]
                if not sig_df.empty:
                    sig_csv = class_dir / f"{class_col}_significant.csv"
                    sig_df.to_csv(sig_csv, index=False)
                    significant_paths.append(str(sig_csv))

        if significant_paths:
            all_significant_parts: List[pd.DataFrame] = []
            for sig_path in significant_paths:
                try:
                    all_significant_parts.append(pd.read_csv(sig_path))
                except Exception:
                    pass
            if all_significant_parts:
                all_sig_csv = output_base / "_all_significant.csv"
                pd.concat(all_significant_parts, ignore_index=True).to_csv(all_sig_csv, index=False)
                significant_paths.append(str(all_sig_csv))

        return png_paths, pvalue_paths, csv_paths, significant_paths, plot_infos, skipped_insufficient

    def _generate_ungrouped(
        self,
        df: pd.DataFrame,
        param_columns: List[str],
        output_base: Path,
        progress_callback,
    ):
        ungrouped_dir = output_base / "ungrouped"
        ungrouped_dir.mkdir(parents=True, exist_ok=True)
        csv_dir = ungrouped_dir / "csvfiles"
        csv_dir.mkdir(parents=True, exist_ok=True)

        png_paths: List[str] = []
        csv_paths: List[str] = []
        total_steps = len(param_columns)
        for i, param in enumerate(param_columns):
            if progress_callback:
                progress_callback(
                    5 + int((i + 1) / max(total_steps, 1) * 90),
                    "BoxPlot analysis (ungrouped)",
                    f"Processing {param}",
                    {"param": param},
                )

            self._plot_ungrouped_boxplot(df, param, ungrouped_dir)
            png_paths.append(str(ungrouped_dir / f"{param}.png"))

            param_data = df[[param]].dropna()
            csv_path = csv_dir / f"{param}.csv"
            param_data.to_csv(csv_path, index=False)
            csv_paths.append(str(csv_path))

        return png_paths, csv_paths

    @staticmethod
    def _plot_boxplot(
        df: pd.DataFrame,
        class_col: str,
        param: str,
        class_types: List[str],
        significant_pairs: List[tuple],
        output_dir: Path,
    ) -> None:
        BoxPlotService._save_publication_boxplot(
            plot_df=df[[class_col, param]].copy(),
            group_col=class_col,
            param=param,
            group_values=[str(item) for item in class_types],
            significant_pairs=significant_pairs,
            output_path=output_dir / f"{param}.png",
        )

    @staticmethod
    def _plot_ungrouped_boxplot(
        df: pd.DataFrame,
        param: str,
        output_dir: Path,
    ) -> None:
        BoxPlotService._save_publication_ungrouped_boxplot(
            plot_df=df[[param]].copy(),
            param=param,
            output_path=output_dir / f"{param}.png",
        )

    @staticmethod
    def _allocate_job_id(name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{name}_{ts}"
