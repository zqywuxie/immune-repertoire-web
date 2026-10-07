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

from flask_app.services.figure_style import category_palette, apply_publication_style, save_publication_png, soften_axes

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

    @staticmethod
    def prepare_input(*, data_path, param_begin="", param_over="", category_col="Category",
                      sample_column="", selected_categories=None, selected_samples=None, output_base=None, validate_sample_count=True):
        path = Path(data_path)
        if not path.exists():
            raise FileNotFoundError("未找到所选 V/J 使用数据，请重新选择。")
        source, df = UmapinService._load_or_concat_usage(path, output_base)
        columns = df.columns.tolist()
        category_col, sample_column = UmapinService._identity_columns(columns, category_col, sample_column)
        samples = df[sample_column].astype(str).str.strip() if sample_column else pd.Series([f"S{i+1}" for i in range(len(df))], index=df.index)
        categories = df[category_col].astype(str).str.strip()
        if samples.eq("").any() or samples.duplicated().any():
            raise ValueError("特征表存在空白或重复样本编号，请先明确样本对应关系。")
        if categories.eq("").any():
            raise ValueError("特征表存在空分组值，请检查上游结果。")
        df[category_col] = categories
        keep = pd.Series(True, index=df.index)
        if selected_categories is not None:
            chosen = {str(v).strip() for v in selected_categories}
            if chosen - set(categories):
                raise ValueError("所选分组不存在于当前特征表。")
            keep &= categories.isin(chosen)
        if selected_samples is not None:
            chosen = {str(v).strip() for v in selected_samples}
            if chosen - set(samples):
                raise ValueError("所选样本不存在于当前特征表，请重新检查输入。")
            keep &= samples.isin(chosen)
        df, samples = df.loc[keep].copy(), samples.loc[keep].copy()
        if validate_sample_count and len(df) < 3:
            raise ValueError("UMAP 降维至少需要 3 个样本，请检查所选输入。")
        feature_candidates = [c for c in columns if c not in {sample_column, category_col} and pd.to_numeric(df[c], errors="coerce").notna().any()]
        if bool(param_begin) != bool(param_over):
            raise ValueError("特征范围的起始列和结束列必须同时设置。")
        if not param_begin and feature_candidates:
            param_begin, param_over = feature_candidates[0], feature_candidates[-1]
        if param_begin not in columns or param_over not in columns:
            raise ValueError("未找到所选特征列，请重新选择特征范围。")
        begin, end = columns.index(param_begin), columns.index(param_over)
        if begin > end:
            raise ValueError("特征起始列不能位于结束列之后。")
        features = [c for c in columns[begin:end+1] if c not in {sample_column, category_col}]
        if not features or not df[features].apply(pd.to_numeric, errors="coerce").notna().any().any():
            raise ValueError("所选范围内没有可用于降维的数值特征列。")
        if not np.isfinite(df[features].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy()).all():
            raise ValueError("UMAP 输入包含无穷值，请检查特征列。")
        return {"source": source, "data": df, "samples": samples, "sample_column": sample_column,
                "category_col": category_col, "features": features, "feature_candidates": feature_candidates}

    @staticmethod
    def _identity_columns(columns, category_col="Category", sample_column=""):
        """Use the same grouping aliases and identity columns for header checks and execution."""
        if category_col not in columns:
            candidates = [c for c in columns if c.lower() in ("category", "group", "therapy", "disease")]
            if category_col != "Category" or not candidates:
                raise ValueError("所选数据中没有指定分组列，请重新选择。")
            category_col = candidates[0]
        if sample_column and sample_column not in columns:
            raise ValueError("所选样本编号列不存在，请重新选择。")
        if not sample_column:
            sample_column = next((c for c in columns if c.lower() in {"sample", "sample_id", "sampleid", "id"}), "")
            if not sample_column and columns[0] != category_col:
                sample_column = columns[0]
        if sample_column == category_col:
            raise ValueError("样本编号与分组不能使用同一列。")
        return category_col, sample_column

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
        sample_column: str = "",
        selected_categories=None, selected_samples=None,
        output_name: str = "umapin",
        progress_callback=None,
    ) -> UmapinReport:
        if n_neighbors < 2 or not 0 <= min_dist <= 1 or n_epochs < 1:
            raise ValueError("UMAP 参数超出有效范围。")
        prepared = self.prepare_input(data_path=data_path, param_begin=param_begin, param_over=param_over,
            category_col=category_col, sample_column=sample_column,
            selected_categories=selected_categories, selected_samples=selected_samples)
        source_path, df = prepared["source"], prepared["data"]
        feature_cols, category_col = prepared["features"], prepared["category_col"]
        sample_column = prepared["sample_column"]
        from flask_app.services.project_storage_paths import allocate_result_dir
        job_id, output_base = allocate_result_dir(self.output_parent, "umapin")
        # Keep the actual selected matrix alongside a directory-based analysis.
        if source_path.is_dir():
            source_path = output_base / "df_VJ_all.csv"
            df.to_csv(source_path, index=False, encoding="utf-8-sig")


        if progress_callback:
            progress_callback(10, "UMAPin", f"标准化 {len(feature_cols)} 个特征")

        # Extract data
        X = df[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0).values
        categories = df[category_col].values
        if len(df) < 3:
            raise ValueError("UMAP 降维至少需要 3 个样本，请检查所选输入。")
        if not np.isfinite(X).all():
            raise ValueError("UMAP 输入包含无穷值，请检查特征列。")

        if progress_callback:
            progress_callback(25, "UMAPin", "运行 UMAP 降维")

        # Standardize
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # UMAP
        try:
            if progress_callback:
                progress_callback(25, "UMAP 降维", "正在加载运行环境，首次初始化可能较慢")
            from flask_app.services.umap_service import _load_umap_dependencies
            _, umap = _load_umap_dependencies()
            local_neighbors = min(max(2, n_neighbors), max(2, len(df) - 1))
            reducer = umap.UMAP(n_neighbors=local_neighbors, min_dist=min_dist, n_epochs=n_epochs, random_state=8, init="random" if len(df) == 3 else "spectral", n_jobs=1)
            if progress_callback:
                progress_callback(40, "UMAP 降维", f"正在计算 {len(df)} 个样本；首次运行需编译计算内核")
            embedding = reducer.fit_transform(X_scaled)
        except ImportError:
            raise ImportError("容器缺少 UMAP 依赖，请重建分析运行镜像并重新部署。")

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
        save_publication_png(fig, png_path)
        plt.close(fig)
        png_paths.append(str(png_path))

        # Save embedding coordinates
        coord_df = pd.DataFrame({
            "sample": prepared["samples"].to_numpy(),
            "Category": categories,
            "UMAP1": embedding[:, 0],
            "UMAP2": embedding[:, 1],
        })
        coord_path = output_base / "umapin_coordinates.csv"
        coord_df.to_csv(coord_path, index=False, encoding="utf-8-sig")
        csv_paths.append(str(coord_path))
        if source_path.parent == output_base:
            csv_paths.append(str(source_path))

        # Optional FDR correction
        warnings = []
        fdr_status = "disabled"
        if do_fdr:
            if progress_callback:
                progress_callback(85, "UMAPin", "执行 FDR 校正")
            try:
                before = len(csv_paths)
                self._run_fdr(df, feature_cols, output_base, csv_paths)
                fdr_status = "completed" if len(csv_paths) > before else "no_pvalues"
                if fdr_status == "no_pvalues": warnings.append("没有可校正的 p 值列，未生成 FDR 校正结果。")
            except Exception as exc:
                fdr_status = "failed"
                warnings.append(f"FDR 校正未完成：{exc}")
                if progress_callback:
                    progress_callback(88, "UMAP 降维", warnings[-1])

        if progress_callback:
            progress_callback(95, "UMAPin", "完成")

        metadata = {
            "output_name": output_name,
            "sample_column": sample_column,
            "sample_count": len(df),
            "selected_categories": selected_categories,
            "selected_samples": selected_samples,
            "feature_columns": feature_cols,
            "do_fdr": do_fdr,
            "fdr_status": fdr_status,
            "warnings": warnings,
            "data_path": data_path,
            "resolved_data_path": str(source_path),
            "feature_count": len(feature_cols),
            "category_col": category_col,
            "n_neighbors": n_neighbors,
            "effective_n_neighbors": local_neighbors,
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

    @staticmethod
    def _load_or_concat_usage(data_path: Path, output_base: Optional[Path] = None) -> tuple[Path, pd.DataFrame]:
        files, concatenate = UmapinService._usage_source_files(data_path)
        if not files:
            raise FileNotFoundError(f"所选目录中没有可用的 V/J 使用 CSV 文件：{data_path}")
        if not concatenate:
            return files[0], _try_read_csv(files[0], dtype=str, keep_default_na=False)
        merged = UmapinService._concat_usage_files(files)
        if output_base is not None:
            output_path = output_base / "df_VJ_all.csv"
            merged.to_csv(output_path, index=False, encoding="utf-8-sig")
            return output_path, merged
        return data_path, merged

    @staticmethod
    def _usage_source_files(data_path: Path) -> tuple[List[Path], bool]:
        """Select the exact named summary or chain files consumed by the loader."""
        if data_path.is_file():
            return [data_path], False
        for resolved_dir in UmapinService._candidate_usage_dirs(data_path):
            for candidate_name in ("df_VJ_all.csv", "df_1VJusage_all.csv", "df_VJ.csv", "df_all.csv"):
                candidate = resolved_dir / candidate_name
                if candidate.exists() and candidate.is_file():
                    return [candidate], False
            chain_files = [
                path for path in sorted(resolved_dir.glob("*.csv"))
                if path.is_file() and not path.name.lower().startswith("df")
            ]
            usable = []
            for path in chain_files:
                cols = _try_read_csv(path, nrows=0).columns.tolist()
                if "Category" in cols and len(cols) > cols.index("Category") + 1:
                    usable.append(path)
            if usable:
                return usable, True
        return [], False

    @staticmethod
    def _resolve_usage_dir(data_path: Path) -> Path:
        for candidate in UmapinService._candidate_usage_dirs(data_path):
            return candidate
        return data_path

    @staticmethod
    def _candidate_usage_dirs(data_path: Path) -> List[Path]:
        candidates = [
            data_path,
            data_path / "1VJusage",
            data_path / "usage" / "1VJusage",
            data_path / "0VJusage",
            data_path / "usage" / "0VJusage",
            data_path / "1Vusage",
        ]
        if data_path.name in {"1VJusage", "0VJusage", "1Vusage"}:
            candidates.extend([
                data_path.parent / "0VJusage",
                data_path.parent / "1VJusage",
                data_path.parent / "1Vusage",
                data_path.parent,
            ])
        if data_path.parent.name == "usage":
            candidates.extend([
                data_path.parent / "0VJusage",
                data_path.parent / "1VJusage",
                data_path.parent / "1Vusage",
                data_path.parent,
            ])
        seen: set[str] = set()
        valid: List[Path] = []
        for candidate in candidates:
            key = str(candidate.resolve()) if candidate.exists() else str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists() and candidate.is_dir():
                valid.append(candidate)
        return valid

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
            df = _try_read_csv(file_path, dtype=str, keep_default_na=False)
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
    def pvalue_columns(columns):
        return [c for c in columns if c.lower() in {"p", "pvalue", "p_value", "p.value"}
                or c.lower().endswith(("_pvalue", "_p_value", ".pvalue", ".p.value"))]

    def _run_fdr(self, df, feature_cols, output_base, csv_paths):
        """Apply Benjamini-Hochberg FDR correction on p-values stored in the dataframe."""
        try:
            from statsmodels.stats.multitest import fdrcorrection
        except ImportError:
            return

        # Look for columns that might contain p-values
        pval_cols = self.pvalue_columns(df.columns)
        if not pval_cols:
            return

        for pcol in pval_cols[:3]:  # limit to first 3 p-value columns
            raw = pd.to_numeric(df[pcol], errors="coerce")
            if not raw.notna().any():
                continue
            pvals = raw.fillna(1.0).values
            if len(pvals) == 0:
                continue
            if not np.isfinite(pvals).all() or (pvals < 0).any() or (pvals > 1).any():
                raise ValueError(f"p 值列 {pcol} 含有不在 0 到 1 内的数值。")
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
