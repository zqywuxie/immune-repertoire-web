"""
Volcano plot analysis service for VJ usage differential comparison.
"""

from __future__ import annotations

import os
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

# Chinese font support
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


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

        csv_files = sorted(data_path.glob("df*.csv"))
        if not csv_files:
            csv_files = sorted(data_path.glob("*.csv"))
        if not csv_files:
            raise ValueError(f"No CSV files found in {data_dir}")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id()
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

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

    def _volcano_one_file(
        self,
        file_path: Path,
        output_base: Path,
        title: str,
        pvalue_threshold: float = 0.05,
        pseudocount: float = 1e-3,
    ):
        df = pd.read_csv(file_path, low_memory=False)

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
        feature_cols = [c for c in df.columns if c not in ("sample", "Category")]
        if not feature_cols:
            raise ValueError("No feature columns found")

        g1_df = df[df["Category"] == group1][feature_cols]
        g2_df = df[df["Category"] == group2][feature_cols]

        results = []
        for col in feature_cols:
            v1 = g1_df[col].dropna().values.astype(float)
            v2 = g2_df[col].dropna().values.astype(float)
            if len(v1) < 2 or len(v2) < 2:
                continue

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
        result_df.sort_values("P-value", inplace=True)

        # Generate volcano plot
        png_path = output_base / f"{title}_volcano.png"
        self._draw_volcano(result_df, pvalue_threshold, group1, group2, title, png_path)

        # Filter significant
        sig_df = result_df[result_df["significant"] != "Not Sig"]
        return sig_df, png_path

    def _draw_volcano(self, df, p_cutoff, g1, g2, title, output_path):
        fig, ax = plt.subplots(figsize=(7, 6))
        df["neg_log10_p"] = -np.log10(df["P-value"].clip(lower=1e-300))

        not_sig = df[df["significant"] == "Not Sig"]
        up = df[df["significant"] == "Up"]
        down = df[df["significant"] == "Down"]

        ax.scatter(not_sig["log2FC"], not_sig["neg_log10_p"], c="gray", alpha=0.4, s=10, label="不显著")
        ax.scatter(up["log2FC"], up["neg_log10_p"], c="red", alpha=0.6, s=18, label=f"{g1} 上调")
        ax.scatter(down["log2FC"], down["neg_log10_p"], c="blue", alpha=0.6, s=18, label=f"{g2} 上调")

        ax.axhline(-np.log10(p_cutoff), color="gray", linestyle="--", linewidth=0.8)
        ax.axvline(0, color="gray", linestyle="--", linewidth=0.8)

        ax.set_xlabel("log2 Fold Change")
        ax.set_ylabel("-log10 P-value")
        ax.set_title(f"Volcano: {title}\n{g1} vs {g2}")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
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
