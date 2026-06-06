"""
Volcano plot analysis service for VJ usage differential comparison.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from glob import glob
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from flask_app.services.figure_style import PALETTE, VOLCANO_COLORS, apply_publication_style, soften_axes

# Encoding fallback for CSV/TSV files (GBK common in Chinese Windows environments)
_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]

def _try_read_csv(filepath, **kwargs):
    """Read CSV/TSV with encoding fallback."""
    suffix = str(filepath).lower()
    if suffix.endswith(".xlsx"):
        import pandas as pd
        return pd.read_excel(filepath, sheet_name=kwargs.pop("sheet_name", 0), **kwargs)
    import pandas as pd
    sep = kwargs.pop("sep", ",")
    if suffix.endswith((".tsv", ".tsv.gz")):
        sep = "\t"
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(filepath, encoding=enc, sep=sep, **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(filepath, sep=sep, **kwargs)


apply_publication_style(font_size=10, axes_linewidth=0.9)


@dataclass
class VolcanoReport:
    job_id: str
    output_base: Path
    png_paths: List[str]
    csv_paths: List[str]
    metadata: Dict[str, Any]


class VolcanoService:
    """Differential VJ usage analysis with volcano plots."""

    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    def generate_report(
        self,
        *,
        data_dir: str,
        pvalue_threshold: float = 0.05,
        pseudocount: float = 1e-3,
        progress_callback=None,
    ) -> VolcanoReport:
        data_path = Path(data_dir)
        if not data_path.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id()
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        csv_files = self._prepare_csv_files(data_path, output_base)
        if not csv_files:
            raise ValueError(f"No VJ usage CSV files found in {data_dir}")

        png_paths: List[str] = []
        csv_paths: List[str] = []

        total = len(csv_files)
        for idx, file_path in enumerate(csv_files):
            if progress_callback:
                progress_callback(
                    5 + (idx / total) * 90,
                    "火山图分析",
                    f"处理 {file_path.name} ({idx+1}/{total})",
                )

            title = self._extract_title(file_path.name)
            try:
                result_df, png_path = self._volcano_one_file(
                    file_path, output_base, title,
                    pvalue_threshold=pvalue_threshold,
                    pseudocount=pseudocount,
                )
                png_paths.append(str(png_path))
                csv_path = output_base / f"{title}_volcano_results.csv"
                result_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
                csv_paths.append(str(csv_path))
            except Exception as exc:
                if progress_callback:
                    progress_callback(
                        5 + (idx / total) * 90,
                        "火山图分析",
                        f"跳过 {file_path.name}: {exc}",
                    )

        if progress_callback:
            progress_callback(95, "火山图分析", f"完成 {len(png_paths)} 个火山图")

        metadata = {
            "data_dir": data_dir,
            "file_count": total,
            "output_count": len(png_paths),
            "pvalue_threshold": pvalue_threshold,
        }

        return VolcanoReport(
            job_id=job_id,
            output_base=output_base,
            png_paths=png_paths,
            csv_paths=csv_paths,
            metadata=metadata,
        )

    def _prepare_csv_files(self, data_path: Path, output_base: Path) -> List[Path]:
        """Resolve a df*.csv file or concatenate per-chain usage CSVs like the reference notebooks."""
        if data_path.is_file():
            return [data_path]

        resolved_dir = self._resolve_usage_dir(data_path)
        df_files = sorted(resolved_dir.glob("df*.csv"))
        if df_files:
            return df_files

        chain_files = [
            path for path in sorted(resolved_dir.glob("*.csv"))
            if path.is_file() and not path.name.lower().startswith("df")
        ]
        usable = []
        for path in chain_files:
            cols = _try_read_csv(path, nrows=0).columns.tolist()
            if "Category" in cols and len(cols) > cols.index("Category") + 1:
                usable.append(path)

        if not usable:
            return []

        merged = self._concat_usage_files(usable)
        output_name = f"df_{self._safe_title(resolved_dir.name)}_all.csv"
        output_path = output_base / output_name
        merged.to_csv(output_path, index=False, encoding="utf-8-sig")
        return [output_path]

    @staticmethod
    def _resolve_usage_dir(data_path: Path) -> Path:
        for candidate in (
            data_path / "1VJusage",
            data_path / "usage" / "1VJusage",
            data_path / "0VJusage",
            data_path / "usage" / "0VJusage",
        ):
            if candidate.exists() and candidate.is_dir():
                return candidate
        return data_path

    @staticmethod
    def _concat_usage_files(files: List[Path]) -> pd.DataFrame:
        df_all = pd.DataFrame(columns=["sample", "Category"])
        for file_path in files:
            df = _try_read_csv(file_path, low_memory=False)
            if df.empty or "Category" not in df.columns:
                continue
            first_col = df.columns[0]
            if first_col != "sample":
                df = df.rename(columns={first_col: "sample"})
            feature_cols = [c for c in df.columns if c not in ("sample", "Category")]
            df = df[["sample", "Category"] + feature_cols]
            df_all = pd.merge(df_all, df, how="outer", on=["sample", "Category"])
        return df_all.fillna(0)

    @staticmethod
    def _safe_title(name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or "usage")).strip("_")
        return safe or "usage"

    def _volcano_one_file(
        self,
        file_path: Path,
        output_base: Path,
        title: str,
        pvalue_threshold: float = 0.05,
        pseudocount: float = 1e-3,
    ):
        df = _try_read_csv(file_path, low_memory=False)
        df = df.copy()
        df.fillna(0, inplace=True)

        # Expect first column as sample id, and a "Category" column
        if df.columns[0].lower() != "sample":
            df.rename(columns={df.columns[0]: "sample"}, inplace=True)

        if "Category" not in df.columns:
            # Try to find a category-like column
            cat_cols = [c for c in df.columns if c.lower() in ("category", "group", "therapy", "disease")]
            if cat_cols:
                df.rename(columns={cat_cols[0]: "Category"}, inplace=True)
            else:
                raise ValueError(f"No Category column found in {file_path.name}")

        groups = sorted(df["Category"].dropna().unique())
        if len(groups) < 2:
            raise ValueError(f"Need at least 2 unique Category values, got {groups}")

        group1, group2 = groups[0], groups[1]
        category_idx = df.columns.tolist().index("Category")
        feature_cols = [c for c in df.columns[category_idx + 1:] if c not in ("sample", "Category")]
        if not feature_cols:
            raise ValueError("No feature columns found")

        g1_df = df[df["Category"] == group1][feature_cols]
        g2_df = df[df["Category"] == group2][feature_cols]

        results = []
        for col in feature_cols:
            v1 = pd.to_numeric(g1_df[col], errors="coerce").fillna(0).values
            v2 = pd.to_numeric(g2_df[col], errors="coerce").fillna(0).values

            mean1 = np.mean(v1)
            mean2 = np.mean(v2)
            fc = (mean1 + pseudocount) / (mean2 + pseudocount)
            log2fc = np.log2(fc)

            try:
                _, pval = mannwhitneyu(v1, v2, alternative="two-sided")
            except Exception:
                pval = 1.0

            significant = "Not Sig"
            if pval < pvalue_threshold:
                significant = "Up" if log2fc > 0 else "Down"

            results.append({
                "Gene": col,
                "Mean_" + str(group1): round(mean1, 6),
                "Mean_" + str(group2): round(mean2, 6),
                "FC": round(fc, 6),
                "log2FC": round(log2fc, 6),
                "P-value": pval,
                "significant": significant,
            })

        result_df = pd.DataFrame(results)
        if result_df.empty:
            result_df = pd.DataFrame(columns=["Gene", "FC", "log2FC", "P-value", "significant"])

        # Generate volcano plot
        png_path = output_base / f"{title}_volcano.png"
        self._draw_volcano(result_df, pvalue_threshold, group1, group2, title, png_path)

        export_df = result_df[result_df["P-value"] < pvalue_threshold][
            ["Gene", "log2FC", "P-value", "FC", "significant"]
        ].copy()
        if not export_df.empty:
            df_pos = export_df[export_df["log2FC"] > 0].sort_values("log2FC", ascending=False)
            df_neg = export_df[export_df["log2FC"] < 0].sort_values("log2FC", ascending=True)
            export_df = pd.concat([df_pos, df_neg], axis=0).reset_index(drop=True)

        return export_df, png_path

    def _draw_volcano(self, df, p_cutoff, g1, g2, title, output_path):
        fig, ax = plt.subplots(figsize=(6.4, 5.6))
        if df.empty:
            ax.set_xlabel(f"log2(Fold Change)\n({g1} / {g2})")
            ax.set_ylabel("-log10(P value)")
            ax.set_title(title)
            ax.text(0.5, 0.5, "No valid features", ha="center", va="center", transform=ax.transAxes)
            fig.tight_layout()
            fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            return
        df["neg_log10_p"] = -np.log10(df["P-value"].clip(lower=1e-300))

        for label in ["Not Sig", "Down", "Up"]:
            subdf = df[df["significant"] == label]
            ax.scatter(
                subdf["log2FC"],
                subdf["neg_log10_p"],
                c=VOLCANO_COLORS[label],
                label=label,
                alpha=0.82 if label == "Not Sig" else 0.9,
                s=38 if label == "Not Sig" else 46,
                edgecolors="white",
                linewidths=0.8,
            )

        fc_cutoff = 0
        ax.axhline(-np.log10(p_cutoff), linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)
        ax.axvline(fc_cutoff, linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)
        ax.axvline(-fc_cutoff, linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)

        ax.set_xlabel(f"log2(Fold Change)\n({g1} / {g2})")
        ax.set_ylabel("-log10(P value)")
        ax.set_title(title)
        soften_axes(ax, grid_axis="both")
        ax.legend(loc="best", markerscale=1.0)
        fig.tight_layout()
        fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close(fig)

    @staticmethod
    def _extract_title(filename: str) -> str:
        name = filename.replace(".csv", "")
        for prefix in ("df_", "df"):
            if name.startswith(prefix):
                name = name[len(prefix):]
        for suffix in ("_all", "_volcano_results"):
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name or "volcano"

    def _allocate_job_id(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"volcano_{ts}"
