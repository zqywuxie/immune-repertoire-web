"""
UMAPin: usage-based UMAP dimensionality reduction service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


@dataclass
class UmapinReport:
    job_id: str
    output_base: Path
    png_paths: List[str]
    csv_paths: List[str]
    metadata: Dict[str, Any]


class UmapinService:
    """Usage-based UMAP dimensionality reduction."""

    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    def generate_report(
        self,
        *,
        data_path: str,
        param_begin: str,
        param_over: str,
        category_col: str = "Category",
        n_neighbors: int = 6,
        min_dist: float = 0.01,
        n_epochs: int = 100,
        do_fdr: bool = False,
        progress_callback=None,
    ) -> UmapinReport:
        dp = Path(data_path)
        if not dp.exists() or not dp.is_file():
            raise FileNotFoundError(f"Data file not found: {data_path}")

        df = pd.read_csv(dp, low_memory=False)

        # Find or set category column
        if category_col not in df.columns:
            cat_candidates = [c for c in df.columns if c.lower() in ("category", "group", "therapy", "disease")]
            if cat_candidates:
                category_col = cat_candidates[0]
            else:
                raise ValueError(f"Category column not found in {data_path}")

        columns = df.columns.tolist()
        try:
            begin_idx = columns.index(param_begin)
            over_idx = columns.index(param_over) + 1
        except ValueError as exc:
            raise ValueError(f"Column not found: {exc}")

        feature_cols = [c for c in columns[begin_idx:over_idx] if c != category_col]

        if progress_callback:
            progress_callback(10, "UMAPin", f"标准化 {len(feature_cols)} 个特征")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id()
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        # Extract data
        X = df[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0).values
        categories = df[category_col].values

        if progress_callback:
            progress_callback(25, "UMAPin", "运行 UMAP 降维")

        # Standardize
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # UMAP
        try:
            import umap
            reducer = umap.UMAP(n_neighbors=n_neighbors, min_dist=min_dist, n_epochs=n_epochs, random_state=8)
            embedding = reducer.fit_transform(X_scaled)
        except ImportError:
            raise ImportError("umap-learn package is required. Install with: pip install umap-learn")

        if progress_callback:
            progress_callback(70, "UMAPin", "绘制 UMAP 散点图")

        png_paths: List[str] = []
        csv_paths: List[str] = []

        # Scatter plot
        unique_cats = sorted(set(str(c) for c in categories))
        fig, ax = plt.subplots(figsize=(8, 6))
        colors = plt.cm.tab10(np.linspace(0, 1, max(len(unique_cats), 1)))
        for i, cat in enumerate(unique_cats):
            mask = np.array([str(c) == cat for c in categories])
            ax.scatter(embedding[mask, 0], embedding[mask, 1],
                       c=[colors[i]], label=cat, alpha=0.7, s=15)
        ax.set_xlabel("UMAP 1")
        ax.set_ylabel("UMAP 2")
        ax.set_title(f"UMAP (n_neighbors={n_neighbors}, min_dist={min_dist})")
        ax.legend(fontsize=7, loc="best")
        fig.tight_layout()
        png_path = output_base / "umapin_scatter.png"
        fig.savefig(png_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        png_paths.append(str(png_path))

        # Save embedding coordinates
        coord_df = pd.DataFrame({
            "sample": df.iloc[:, 0].values if df.columns[0] != category_col else [f"S{i+1}" for i in range(len(df))],
            "Category": categories,
            "UMAP1": embedding[:, 0],
            "UMAP2": embedding[:, 1],
        })
        coord_path = output_base / "umapin_coordinates.csv"
        coord_df.to_csv(coord_path, index=False, encoding="utf-8-sig")
        csv_paths.append(str(coord_path))

        # Optional FDR correction
        if do_fdr:
            if progress_callback:
                progress_callback(85, "UMAPin", "执行 FDR 校正")
            try:
                self._run_fdr(df, feature_cols, output_base, csv_paths)
            except Exception as exc:
                if progress_callback:
                    progress_callback(88, "UMAPin", f"FDR 跳过: {exc}")

        if progress_callback:
            progress_callback(95, "UMAPin", "完成")

        metadata = {
            "data_path": data_path,
            "feature_count": len(feature_cols),
            "category_col": category_col,
            "n_neighbors": n_neighbors,
            "min_dist": min_dist,
            "n_epochs": n_epochs,
            "unique_groups": unique_cats,
        }

        return UmapinReport(
            job_id=job_id,
            output_base=output_base,
            png_paths=png_paths,
            csv_paths=csv_paths,
            metadata=metadata,
        )

    def _run_fdr(self, df, feature_cols, output_base, csv_paths):
        """Apply Benjamini-Hochberg FDR correction on p-values stored in the dataframe."""
        try:
            from statsmodels.stats.multitest import fdrcorrection
        except ImportError:
            return

        # Look for columns that might contain p-values
        pval_cols = [c for c in df.columns if "p" in c.lower() or "pvalue" in c.lower()]
        if not pval_cols:
            return

        for pcol in pval_cols[:3]:  # limit to first 3 p-value columns
            pvals = pd.to_numeric(df[pcol], errors="coerce").fillna(1.0).values
            if len(pvals) == 0 or all(pvals == 1.0):
                continue
            rejected, pvals_corrected = fdrcorrection(pvals, alpha=0.05)
            result_df = df.copy()
            result_df[f"{pcol}_fdr_flag"] = rejected
            result_df[f"{pcol}_fdr_corrected"] = pvals_corrected
            fdr_path = output_base / f"fdr_{pcol}.csv"
            result_df.to_csv(fdr_path, index=False, encoding="utf-8-sig")
            csv_paths.append(str(fdr_path))

    def _allocate_job_id(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"umapin_{ts}"
