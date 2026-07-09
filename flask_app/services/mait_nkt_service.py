"""
MAIT / iNKT TCR Alignment & Abundance Analysis Service.
========================================================
Aligns TRA CDR3 sequences against reference MAIT/iNKT CDR3s,
computes per-sample abundance profiles and publication-quality boxplots.

TRA data (wide-format: CDR3 × sample) can come from:
  - User-uploaded TRA CSV
  - PEP shared analysis results (Pep_shared/TRA.csv)

Built-in reference: flask_app/data/reference/Alpha_Restrict.csv
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

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from flask_app.services.figure_style import PALETTE, MUTED_CATEGORY_COLORS, apply_publication_style, save_publication_png

# ── module-level constants ────────────────────────────────────────────
_BUILTIN_REFERENCE = Path(__file__).resolve().parent.parent / "data" / "reference" / "Alpha_Restrict.csv"

# CDR3 terminus stripping: remove N-terminal "C" and C-terminal "F"/"W"/"L"
_STRIP_CDR3_TERMINI = True

_NATURE_COLORS = MUTED_CATEGORY_COLORS
_POINT_COLOR = PALETTE["neutral_dark"]
_AXIS_COLOR = PALETTE["neutral_dark"]

_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]


def _try_read_csv(path, **kwargs):
    """Read CSV/TSV/XLSX with encoding fallback."""
    suffix = str(path).lower()
    if suffix.endswith((".xlsx", ".xls", ".xlsm")):
        kwargs.pop("sep", None)
        kwargs.pop("encoding", None)
        kwargs.pop("low_memory", None)
        return pd.read_excel(path, sheet_name=kwargs.pop("sheet_name", 0), **kwargs)
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(path, encoding="latin-1", **kwargs)


@dataclass
class MaitNktReport:
    job_id: str
    output_base: Path
    viewer_path: Path
    png_paths: List[str]
    csv_paths: List[str]
    zip_path: str
    metadata: Dict[str, Any]


class MaitNktService:
    """MAIT / iNKT TCR alignment, abundance profiling, and boxplot generation."""

    def __init__(self, *, output_parent: Path) -> None:
        self._output_parent = output_parent.resolve()
        self._reference_path = _BUILTIN_REFERENCE

    # ── public API ────────────────────────────────────────────────────

    def generate_report(
        self,
        *,
        tra_df: pd.DataFrame,
        profile_df: pd.DataFrame,
        group_field: str,
        group_order: Optional[List[str]] = None,
        progress_callback=None,
        job_id: str = "",
        datapoint_path: str = "",
    ) -> MaitNktReport:
        """Run MAIT/NKT analysis end-to-end.

        Parameters
        ----------
        tra_df : pd.DataFrame
            Wide-format TRA data: rows = CDR3 sequences, columns = sample names.
            Values are abundance counts.  May include a second row with category labels
            (like PEP shared output); if detected, that row is used to build sample→group
            mapping unless *profile_df* provides a richer grouping.
        profile_df : pd.DataFrame
            Sample metadata with at least ``sample`` and *group_field* columns.
        group_field : str
            Column name in *profile_df* to group samples by.
        group_order : list of str, optional
            Desired order of groups on the x-axis.
        progress_callback : callable, optional
            ``callback(percent, stage, detail)`` invoked during processing.
        job_id : str
            Task identifier for output directory naming.
        datapoint_path : str
            Original file path shown in the viewer header.
        """
        if not job_id:
            job_id = f"mait_nkt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"
        output_base = self._output_parent / _sanitize_name(job_id)
        output_base.mkdir(parents=True, exist_ok=True)

        self._maybe_report(progress_callback, 5, "Loading reference", "Reading Alpha_Restrict.csv")
        ref_dict = self._load_reference()

        # Detect if tra_df has an embedded category row (second row is non-numeric)
        cat_map: Dict[str, str] = {}
        tra_data = tra_df.copy()
        if len(tra_data) >= 1:
            second_row_vals = tra_data.iloc[0, 1:] if len(tra_data.columns) > 1 else pd.Series(dtype=object)
            if _looks_like_category_row(second_row_vals):
                sample_names = [str(c) for c in tra_data.columns[1:]]
                sample_cats = [str(v) for v in second_row_vals.values]
                cat_map = dict(zip(sample_names, sample_cats))
                # Remove the category row from data
                tra_data = tra_data.iloc[1:].copy()

        # Build CDR3-indexed numeric matrix
        tra_data.rename(columns={tra_data.columns[0]: "CDR3"}, inplace=True)
        tra_data["CDR3"] = tra_data["CDR3"].astype(str).str.strip()
        tra_data.set_index("CDR3", inplace=True)
        tra_data = tra_data.apply(pd.to_numeric, errors="coerce").fillna(0)

        # Merge grouping from profile_df if provided
        sample_col = _find_profile_sample_column(profile_df) if not profile_df.empty else ""
        if not profile_df.empty and group_field and group_field in profile_df.columns and sample_col:
            profile_lookup = {}
            for _, row in profile_df.iterrows():
                sample = _normalize_sample_name(row.get(sample_col, ""))
                group_val = str(row.get(group_field, "")).strip()
                if sample:
                    profile_lookup[sample] = group_val
            # Prefer profile_df grouping over embedded category row
            if profile_lookup:
                cat_map = {}
                for col in tra_data.columns:
                    sample_name = str(col).strip()
                    base_name = _normalize_sample_name(sample_name)
                    if base_name in profile_lookup:
                        cat_map[sample_name] = profile_lookup[base_name]
                    elif sample_name in profile_lookup:
                        cat_map[sample_name] = profile_lookup[sample_name]

        if not cat_map:
            raise ValueError(
                "无法确定样本分组信息：TRA CSV 中未检测到 category 行，且 Profile 文件中未找到匹配的 sample 列。"
            )

        self._maybe_report(progress_callback, 15, "Computing profile", "Aligning CDR3s against reference")
        profile = self._compute_profile(tra_data, cat_map, ref_dict, group_order)

        # Save profile CSV
        profile_csv = output_base / "MAIT_iNKT_profile.csv"
        profile.to_csv(profile_csv, index=False)
        csv_paths = [str(profile_csv)]

        self._maybe_report(progress_callback, 40, "Generating boxplots", "MAIT fraction boxplot")
        png_paths: List[str] = []
        for cdr3_type in ref_dict:
            y_col = f"{cdr3_type}_fraction"
            if y_col not in profile.columns:
                continue
            out_png = output_base / f"{cdr3_type}_fraction_boxplot.png"
            self._make_boxplot(
                profile=profile,
                x="category",
                y=y_col,
                ylabel=f"{cdr3_type} fraction (of total TRA clonotypes)",
                out_path=out_png,
                group_order=group_order,
            )
            png_paths.append(str(out_png))

        self._maybe_report(progress_callback, 85, "Building viewer", "Generating HTML report")
        viewer_path = output_base / "viewer.html"
        metadata: Dict[str, Any] = {
            "job_id": job_id,
            "module": "mait-nkt",
            "group_field": group_field,
            "group_order": group_order,
            "plot_count": len(png_paths),
            "profile_csv": str(profile_csv),
            "datapoint_path": datapoint_path,
            "cdr3_types": list(ref_dict.keys()),
        }
        self._build_viewer(metadata, png_paths, output_base, viewer_path)

        # Build zip
        zip_path = output_base / "mait_nkt_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(profile_csv, profile_csv.name)
            for png in png_paths:
                pp = Path(png)
                zf.write(png, pp.name)
            zf.write(viewer_path, viewer_path.name)

        self._maybe_report(progress_callback, 100, "Complete", f"Generated {len(png_paths)} plot(s)")

        return MaitNktReport(
            job_id=job_id,
            output_base=output_base,
            viewer_path=viewer_path,
            png_paths=png_paths,
            csv_paths=csv_paths,
            zip_path=str(zip_path),
            metadata=metadata,
        )

    # ── reference loading ─────────────────────────────────────────────

    def _load_reference(self) -> Dict[str, List[str]]:
        """Read Alpha_Restrict.csv → {Type: [CDR3 list]}."""
        if not self._reference_path.exists():
            raise FileNotFoundError(f"Reference file not found: {self._reference_path}")
        df_ref = _try_read_csv(self._reference_path)
        if "CDR3" not in df_ref.columns or "Type" not in df_ref.columns:
            raise ValueError("Reference CSV must contain 'CDR3' and 'Type' columns")
        ref_dict: Dict[str, List[str]] = {}
        for cdr3_type in df_ref["Type"].dropna().unique():
            cdr3_list = df_ref[df_ref["Type"] == cdr3_type]["CDR3"].dropna().unique().tolist()
            if _STRIP_CDR3_TERMINI:
                cdr3_list = [_strip_cdr3_ends(s) for s in cdr3_list]
                cdr3_list = sorted(set(cdr3_list))
            ref_dict[str(cdr3_type).strip()] = cdr3_list
        return ref_dict

    # ── profile computation ───────────────────────────────────────────

    def _compute_profile(
        self,
        df_tall: pd.DataFrame,
        cat_map: Dict[str, str],
        ref_dict: Dict[str, List[str]],
        group_order: Optional[List[str]],
    ) -> pd.DataFrame:
        """Compute per-sample MAIT/iNKT sum, log10 sum, fraction."""
        total = df_tall.sum(axis=0)
        samples = df_tall.columns.tolist()
        profile = pd.DataFrame({"sample": samples})
        profile["category"] = profile["sample"].map(cat_map)

        for cdr3_type, cdr3_list in ref_dict.items():
            matched = [c for c in cdr3_list if c in df_tall.index]
            if matched:
                col_sum = df_tall.loc[matched].sum(axis=0)
            else:
                col_sum = pd.Series(0, index=samples)
            profile[f"{cdr3_type}_sum"] = col_sum.values
            profile[f"{cdr3_type}_log10"] = np.log10(col_sum.replace(0, np.nan)).values
            profile[f"{cdr3_type}_fraction"] = (col_sum / total.replace(0, np.nan)).fillna(0).values

        # Sort by group_order if provided
        if group_order:
            order_map = {name: i for i, name in enumerate(group_order)}
        else:
            seen: List[str] = []
            for v in profile["category"]:
                if v not in seen:
                    seen.append(str(v))
            order_map = {name: i for i, name in enumerate(seen)}
        profile["_sort"] = profile["category"].map(order_map)
        profile.sort_values("_sort", inplace=True)
        profile.drop(columns="_sort", inplace=True)
        profile.reset_index(drop=True, inplace=True)
        return profile

    # ── boxplot drawing ───────────────────────────────────────────────

    @staticmethod
    def _make_boxplot(
        *,
        profile: pd.DataFrame,
        x: str,
        y: str,
        ylabel: str,
        out_path: Path,
        group_order: Optional[List[str]] = None,
    ) -> None:
        """Generate a publication-style boxplot with Mann-Whitney U p-value brackets."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        apply_publication_style(font_size=9.5, axes_linewidth=0.9)

        plot_df = profile[[x, y]].dropna().copy()
        if plot_df.empty:
            return

        groups = group_order or sorted(set(plot_df[x].astype(str)))
        # Filter to groups present in data
        groups = [g for g in groups if g in plot_df[x].astype(str).values]
        if not groups:
            return

        # Pairwise Mann-Whitney U
        significant_pairs: List[tuple] = []
        for g1_name, g2_name in combinations(groups, 2):
            try:
                _, pval = mannwhitneyu(
                    plot_df[plot_df[x].astype(str) == g1_name][y].values,
                    plot_df[plot_df[x].astype(str) == g2_name][y].values,
                    alternative="two-sided",
                )
            except Exception:
                pval = np.nan
            if not np.isnan(pval):
                significant_pairs.append((g1_name, g2_name, float(pval)))

        # Build data list in group order
        data = [
            plot_df[plot_df[x].astype(str) == g][y].dropna().tolist()
            for g in groups
        ]
        data = [d for d in data if d]
        labels = [g for g, d in zip(groups, data) if d]

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
        for idx, patch in enumerate(box["boxes"]):
            patch.set_facecolor(_NATURE_COLORS[idx % len(_NATURE_COLORS)])
            patch.set_alpha(0.72)

        for idx, vals in enumerate(data, start=1):
            ax.scatter(
                _jitter_positions(idx, len(vals)),
                vals,
                s=10,
                color=_POINT_COLOR,
                alpha=0.55,
                linewidths=0,
                zorder=3,
            )

        # ── Significance brackets ──────────────────────────────────
        if significant_pairs and len(labels) >= 2:
            label_to_x = {lbl: i + 1 for i, lbl in enumerate(labels)}
            raw_brackets: List[tuple] = []
            for g1, g2, pv in significant_pairs:
                x1 = label_to_x.get(g1)
                x2 = label_to_x.get(g2)
                if x1 is not None and x2 is not None and x1 != x2:
                    raw_brackets.append((min(x1, x2), max(x1, x2), float(pv)))

            if raw_brackets:
                all_y_vals = []
                for d in data:
                    all_y_vals.extend(d)
                data_max = max(all_y_vals) if all_y_vals else 1
                data_min = min(all_y_vals) if all_y_vals else 0
                data_range = data_max - data_min if data_max != data_min else abs(data_max) * 0.5 or 1.0

                tier_spacing = data_range * 0.12
                y_start = data_max + data_range * 0.08

                raw_brackets.sort(key=lambda b: (b[1] - b[0], b[0]))
                tiers: List[List[tuple]] = []
                for b in raw_brackets:
                    x1, x2, pv = b
                    placed = False
                    for tier in tiers:
                        if all(not (x1 < t[1] and x2 > t[0]) for t in tier):
                            tier.append((x1, x2, pv))
                            placed = True
                            break
                    if not placed:
                        tiers.append([(x1, x2, pv)])

                for ti, tier in enumerate(tiers):
                    y_line = y_start + ti * tier_spacing
                    for (x1, x2, pv) in tier:
                        ax.plot(
                            [x1, x1, x2, x2],
                            [y_line - tier_spacing * 0.28, y_line, y_line, y_line - tier_spacing * 0.28],
                            color=_AXIS_COLOR,
                            linewidth=0.6,
                            clip_on=False,
                        )
                        p_label = f"p={pv:.3g}" if pv >= 0.0001 else "p<0.0001"
                        ax.annotate(
                            p_label,
                            xy=((x1 + x2) / 2, y_line),
                            xytext=(0, 2.5),
                            textcoords="offset points",
                            ha="center",
                            va="bottom",
                            fontsize=7.5,
                            fontweight="bold",
                            color="#3F4652",
                            annotation_clip=False,
                        )

                max_bracket_y = y_start + len(tiers) * tier_spacing
                ax.set_ylim(top=max(ax.get_ylim()[1], max_bracket_y + data_range * 0.06))

            # n-value legend
            n_legend = "  ".join(
                f"{label} (n={len(data[i])})" for i, label in enumerate(labels) if i < len(data)
            )
            if len(n_legend) < 120:
                ax.annotate(
                    n_legend,
                    xy=(0.02, 0.98),
                    xycoords="axes fraction",
                    ha="left",
                    va="top",
                    fontsize=7,
                    fontstyle="italic",
                    color="#5F7D94",
                )

        ax.set_xlabel("")
        ax.set_ylabel(ylabel, fontsize=9, fontweight="bold")
        ax.tick_params(axis="x", labelrotation=45, labelsize=8.5, length=2.2, width=0.55, color=_AXIS_COLOR)
        ax.tick_params(axis="y", labelsize=8.5, length=2.2, width=0.55, color=_AXIS_COLOR)
        ax.grid(axis="y", color="#E5E7EB", linewidth=0.4, alpha=0.85)
        ax.set_axisbelow(True)
        fig.tight_layout(pad=0.45)
        save_publication_png(fig, out_path)
        plt.close(fig)

    # ── viewer HTML ───────────────────────────────────────────────────

    @staticmethod
    def _build_viewer(
        metadata: Dict[str, Any],
        png_paths: List[str],
        output_base: Path,
        viewer_path: Path,
    ) -> None:
        """Write a self-contained HTML viewer for the generated boxplots."""
        job_id = html.escape(str(metadata.get("job_id", "")))
        group_field = html.escape(str(metadata.get("group_field", "")))
        plot_count = metadata.get("plot_count", 0)
        datapoint_path = html.escape(str(metadata.get("datapoint_path", "")))
        cdr3_types = metadata.get("cdr3_types", [])

        # Build relative PNG URLs
        png_cards = ""
        for p in png_paths:
            pp = Path(p)
            try:
                rel = pp.relative_to(output_base).as_posix()
            except ValueError:
                rel = pp.name
            name = pp.stem
            png_cards += f"""<div class="plot-card">
              <h3>{html.escape(name)}</h3>
              <a href="{html.escape(rel)}" target="_blank" rel="noopener">
                <img src="{html.escape(rel)}" alt="{html.escape(name)}" loading="lazy">
              </a>
            </div>"""

        cdr3_type_tags = " ".join(
            f'<span class="type-tag">{html.escape(t)}</span>' for t in cdr3_types
        )

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MAIT/NKT 分析结果</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Microsoft YaHei", sans-serif; background: #f4f7fa; color: #1e293b; line-height: 1.6; }}
    .page {{ max-width: 1100px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }}
    .header {{ background: #fff; border-radius: 18px; padding: 1.5rem 1.8rem; margin-bottom: 1.2rem; border: 1px solid #dee6ed; box-shadow: 0 8px 24px rgba(0,0,0,.04); }}
    .header h1 {{ font-size: 1.35rem; font-weight: 720; margin-bottom: .35rem; }}
    .header .meta {{ color: #5f7d94; font-size: .88rem; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: .65rem; margin-top: 1rem; }}
    .stat-item {{ background: #f6f9fc; border-radius: 12px; padding: .65rem 1rem; border: 1px solid #dee8f0; }}
    .stat-item strong {{ display: block; font-size: .72rem; color: #5f7d94; text-transform: uppercase; letter-spacing: .04em; }}
    .stat-item span {{ font-size: .92rem; font-weight: 680; }}
    .type-tag {{ display: inline-block; padding: .2rem .55rem; border-radius: 999px; background: #d8ecfa; color: #11597c; font-size: .75rem; font-weight: 680; }}
    .grid {{ display: grid; grid-template-columns: 1fr; gap: .85rem; }}
    .plot-card {{ background: #fff; border-radius: 14px; border: 1px solid #dee6ed; overflow: hidden; }}
    .plot-card h3 {{ padding: .65rem .85rem; font-size: .82rem; border-bottom: 1px solid #edf2f6; background: #fbfdfe; }}
    .plot-card img {{ width: 100%; height: auto; display: block; cursor: pointer; }}
    .back-link {{ display: inline-flex; align-items: center; gap: .35rem; color: #11597c; text-decoration: none; font-size: .85rem; margin-bottom: .8rem; }}
    .back-link:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
<div class="page">
  <a class="back-link" href="javascript:history.back()">← 返回</a>
  <div class="header">
    <h1>MAIT/NKT 分析结果</h1>
    <div class="meta">TRA 数据: {datapoint_path} &nbsp;|&nbsp; 任务: {job_id}</div>
    <div class="stats">
      <div class="stat-item"><strong>分组字段</strong><span>{group_field}</span></div>
      <div class="stat-item"><strong>箱线图数</strong><span>{plot_count}</span></div>
      <div class="stat-item"><strong>检测类型</strong><span>{cdr3_type_tags}</span></div>
    </div>
  </div>
  <div class="grid">{png_cards}</div>
</div>
</body>
</html>"""
        viewer_path.write_text(html_content, encoding="utf-8")

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _maybe_report(cb, percent, stage, detail):
        if cb:
            try:
                cb(float(percent), stage, detail)
            except Exception:
                pass


# ── module-level helpers ──────────────────────────────────────────────

def _sanitize_name(value) -> str:
    text = str(value or "item").strip()
    text = re.sub(r"[^\w.\-]+", "_", text, flags=re.UNICODE).strip("._")
    return text or "item"


def _find_profile_sample_column(profile_df: pd.DataFrame) -> str:
    """Return the sample identifier column using common Profile naming variants."""
    if profile_df.empty:
        return ""
    aliases = {
        "sample",
        "sampleid",
        "sample_id",
        "samplename",
        "sample_name",
        "样本",
        "样本名",
        "样本名称",
    }
    for col in profile_df.columns:
        normalized = re.sub(r"[\s\-_]+", "", str(col).strip().lower())
        if normalized in aliases:
            return str(col)
    for col in profile_df.columns:
        if "sample" in str(col).strip().lower():
            return str(col)
    return ""


def _normalize_sample_name(value) -> str:
    """Normalize sample labels from Profile rows and PEP shared TRA columns."""
    sample = str(value or "").strip()
    sample = re.sub(r"\.(csv|tsv|txt)(\.gz)?$", "", sample, flags=re.IGNORECASE)
    sample = re.sub(r"__(TRA|TRB|TRG|TRD|IGH|IGK|IGL)$", "", sample, flags=re.IGNORECASE)
    return sample.strip()


def _strip_cdr3_ends(seq: str) -> str:
    s = seq.strip()
    if s and s[0] == "C":
        s = s[1:]
    if s and s[-1] in ("F", "W", "L"):
        s = s[:-1]
    return s


def _looks_like_category_row(series: pd.Series) -> bool:
    """Return True if the row appears to be category labels (mostly non-numeric)."""
    if series.empty:
        return False
    numeric_count = 0
    total = 0
    for v in series.dropna():
        total += 1
        try:
            float(v)
            numeric_count += 1
        except (ValueError, TypeError):
            pass
    return total > 0 and numeric_count / total < 0.3


def _jitter_positions(center: float, count: int) -> List[float]:
    if count <= 1:
        return [center] * max(count, 0)
    pattern = [((i % 7) - 3) * 0.026 for i in range(count)]
    return [center + offset for offset in pattern]
