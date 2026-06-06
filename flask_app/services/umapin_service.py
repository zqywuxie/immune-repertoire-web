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

from flask_app.services.figure_style import category_palette, apply_publication_style, soften_axes

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
        if not dp.exists():
            raise FileNotFoundError(f"Data path not found: {data_path}")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id()
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        source_path, df = self._load_or_concat_usage(dp, output_base)

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
        if not feature_cols:
            raise ValueError("No feature columns found for UMAPin")

        if progress_callback:
            progress_callback(10, "UMAPin", f"标准化 {len(feature_cols)} 个特征")

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
            local_neighbors = min(max(2, n_neighbors), max(2, len(df) - 1))
            reducer = umap.UMAP(n_neighbors=local_neighbors, min_dist=min_dist, n_epochs=n_epochs, random_state=8)
            embedding = reducer.fit_transform(X_scaled)
        except ImportError:
            raise ImportError("umap-learn package is required. Install with: pip install umap-learn")

        if progress_callback:
            progress_callback(70, "UMAPin", "绘制 UMAP 散点图")

        png_paths: List[str] = []
        csv_paths: List[str] = []

        # Scatter plot, matching the reference UMAPin notebook style.
        unique_cats = sorted(set(str(c) for c in categories))
        palette = category_palette(unique_cats)
        fig, ax = plt.subplots(figsize=(5.4, 4.8))
        for cat in unique_cats:
            mask = np.array([str(item) == cat for item in categories])
            ax.scatter(
                embedding[mask, 0],
                embedding[mask, 1],
                c=palette[cat],
                label=cat,
                s=36,
                alpha=0.88,
                edgecolors="white",
                linewidths=0.55,
            )
        ax.legend(title=category_col, loc="best", markerscale=1.1)
        ax.set_xlabel("UMAP1")
        ax.set_ylabel("UMAP2")
        ax.set_aspect("equal", "datalim")
        soften_axes(ax, grid_axis="both")
        png_path = output_base / self._reference_plot_name(source_path)
        fig.savefig(png_path, bbox_inches="tight", dpi=300, facecolor="white")
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
            "resolved_data_path": str(source_path),
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

    def _load_or_concat_usage(self, data_path: Path, output_base: Path) -> tuple[Path, pd.DataFrame]:
        if data_path.is_file():
            return data_path, _try_read_csv(data_path, low_memory=False)

        resolved_dir = self._resolve_usage_dir(data_path)
        for candidate_name in ("df_VJ_all.csv", "df_1VJusage_all.csv", "df_VJ.csv", "df_all.csv"):
            candidate = resolved_dir / candidate_name
            if candidate.exists() and candidate.is_file():
                return candidate, _try_read_csv(candidate, low_memory=False)

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
            raise FileNotFoundError(f"No usage CSV files found under {data_path}")

        merged = self._concat_usage_files(usable)
        output_path = output_base / "df_VJ_all.csv"
        merged.to_csv(output_path, index=False, encoding="utf-8-sig")
        return output_path, merged

    @staticmethod
    def _resolve_usage_dir(data_path: Path) -> Path:
        for candidate in (
            data_path / "1VJusage",
            data_path / "usage" / "1VJusage",
            data_path / "0VJusage",
            data_path / "usage" / "0VJusage",
            data_path / "1Vusage",
        ):
            if candidate.exists() and candidate.is_dir():
                return candidate
        return data_path

    @staticmethod
    def _reference_plot_name(source_path: Path) -> str:
        lower = source_path.stem.lower()
        if "vj" in lower:
            prefix = "VJ"
        elif "j" in lower and "usage" in lower:
            prefix = "J"
        elif "v" in lower and "usage" in lower:
            prefix = "V"
        else:
            prefix = "UMAPin"
        return f"{prefix}_p005.png"

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
