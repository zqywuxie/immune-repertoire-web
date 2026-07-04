"""
Volcano plot analysis service for VJ usage differential comparison.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from glob import glob
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, ttest_ind

from flask_app.services.figure_style import PALETTE, VOLCANO_COLORS, apply_publication_style, save_publication_png, soften_axes

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

    def generate_expression_report(
        self,
        *,
        expression_path: str,
        group_prefix: str = "tpm_",
        comparisons: Optional[Sequence[Sequence[str]]] = None,
        pvalue_threshold: float = 0.05,
        logfc_cutoff: float = 1.0,
        output_name: Optional[str] = None,
        output_base: Optional[Path] = None,
        job_id: Optional[str] = None,
        progress_callback=None,
    ) -> VolcanoReport:
        """Generate volcano plots from an RNA-seq style expression matrix.

        The expected input mirrors the reference R script: genes in the first
        column/index and samples in columns named like ``tpm_<group>_<n>``.
        """
        input_path = Path(expression_path)
        if not input_path.exists() or not input_path.is_file():
            raise FileNotFoundError(f"Expression matrix not found: {expression_path}")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id_value = job_id or self._allocate_job_id(output_name or "volcano_expression")
        output_base_value = (output_base or (self.output_parent / job_id_value)).resolve()
        output_base_value.mkdir(parents=True, exist_ok=True)

        expr_df = self._read_expression_matrix(input_path)
        sample_groups = self._infer_sample_groups(expr_df.columns.tolist(), group_prefix=group_prefix)
        if len(set(sample_groups.values())) < 2:
            raise ValueError("Need at least two sample groups in expression matrix columns")

        requested_comparisons = self._normalize_comparisons(comparisons, sample_groups)
        expr_df = expr_df.loc[(expr_df.fillna(0).sum(axis=1) > 0)]
        expr_log = np.log2(expr_df.apply(pd.to_numeric, errors="coerce").fillna(0) + 1.0)

        png_paths: List[str] = []
        csv_paths: List[str] = []
        total = max(1, len(requested_comparisons))

        for idx, (group1, group2) in enumerate(requested_comparisons):
            comp_name = self._safe_title(f"{group1}_vs_{group2}")
            if progress_callback:
                progress_callback(
                    5 + (idx / total) * 90,
                    "表达矩阵火山图",
                    f"差异分析 {group1} vs {group2}",
                )

            deg = self._expression_de_one_comparison(
                expr_log,
                sample_groups,
                group1,
                group2,
                pvalue_threshold=pvalue_threshold,
                logfc_cutoff=logfc_cutoff,
            )
            comp_dir = output_base_value / "DEG" / comp_name
            volcano_dir = comp_dir / "volcano"
            comp_dir.mkdir(parents=True, exist_ok=True)
            volcano_dir.mkdir(parents=True, exist_ok=True)

            full_csv = comp_dir / f"DEG_{comp_name}.csv"
            deg.to_csv(full_csv, index=False, encoding="utf-8-sig")
            csv_paths.append(str(full_csv))

            sig_csv = comp_dir / f"DEG_significant_{comp_name}.csv"
            sig_df = deg[deg["significant"].isin(["Up", "Down"])].copy()
            sig_df.to_csv(sig_csv, index=False, encoding="utf-8-sig")
            csv_paths.append(str(sig_csv))

            png_path = volcano_dir / f"volcano_{comp_name}.png"
            self._draw_expression_volcano(
                deg,
                pvalue_threshold=pvalue_threshold,
                logfc_cutoff=logfc_cutoff,
                title=f"Volcano: {comp_name}",
                output_png=png_path,
            )
            png_paths.append(str(png_path))

        if progress_callback:
            progress_callback(96, "表达矩阵火山图", f"完成 {len(png_paths)} 个比较")

        metadata = {
            "input_mode": "expression",
            "expression_path": str(input_path.resolve()),
            "group_prefix": group_prefix,
            "groups": sorted(set(sample_groups.values())),
            "sample_count": len(sample_groups),
            "gene_count": int(expr_df.shape[0]),
            "comparisons": [{"group1": a, "group2": b} for a, b in requested_comparisons],
            "pvalue_threshold": pvalue_threshold,
            "logfc_cutoff": logfc_cutoff,
            "pdf_paths": [],
        }

        return VolcanoReport(
            job_id=job_id_value,
            output_base=output_base_value,
            png_paths=png_paths,
            csv_paths=csv_paths,
            metadata=metadata,
        )

    @staticmethod
    def inspect_expression_matrix(expression_path: str, group_prefix: str = "tpm_") -> Dict[str, Any]:
        path = Path(expression_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Expression matrix not found: {expression_path}")
        df = VolcanoService._read_expression_matrix(path)
        sample_groups = VolcanoService._infer_sample_groups(df.columns.tolist(), group_prefix=group_prefix)
        groups = sorted(set(sample_groups.values()))
        group_counts = {group: list(sample_groups.values()).count(group) for group in groups}
        suggested = [{"group1": a, "group2": b} for a, b in combinations(groups, 2)]
        return {
            "expression_path": str(path.resolve()),
            "gene_count": int(df.shape[0]),
            "sample_count": int(df.shape[1]),
            "groups": groups,
            "group_counts": group_counts,
            "suggested_comparisons": suggested,
            "columns": df.columns.tolist(),
        }

    def _prepare_csv_files(self, data_path: Path, output_base: Path) -> List[Path]:
        """Resolve a df*.csv file or concatenate per-chain usage CSVs like the reference notebooks."""
        if data_path.is_file():
            return [data_path]

        for resolved_dir in self._candidate_usage_dirs(data_path):
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

            if usable:
                merged = self._concat_usage_files(usable)
                output_name = f"df_{self._safe_title(resolved_dir.name)}_all.csv"
                output_path = output_base / output_name
                merged.to_csv(output_path, index=False, encoding="utf-8-sig")
                return [output_path]
        return []

    @staticmethod
    def _resolve_usage_dir(data_path: Path) -> Path:
        for candidate in VolcanoService._candidate_usage_dirs(data_path):
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
        ]
        if data_path.name in {"1VJusage", "0VJusage"}:
            candidates.extend([
                data_path.parent / "0VJusage",
                data_path.parent / "1VJusage",
                data_path.parent,
            ])
        if data_path.parent.name == "usage":
            candidates.extend([
                data_path.parent / "0VJusage",
                data_path.parent / "1VJusage",
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

    @staticmethod
    def _read_expression_matrix(path: Path) -> pd.DataFrame:
        if str(path).lower().endswith((".xlsx", ".xls", ".xlsm")):
            df = pd.read_excel(path, sheet_name=0)
        else:
            sep = "\t" if str(path).lower().endswith((".tsv", ".tsv.gz")) else ","
            df = _try_read_csv(path, sep=sep, low_memory=False)
        if df.empty or df.shape[1] < 3:
            raise ValueError("Expression matrix must contain a gene column and at least two sample columns")
        first_col = df.columns[0]
        df = df.copy()
        df[first_col] = df[first_col].astype(str)
        df = df[df[first_col].str.strip() != ""]
        df = df.set_index(first_col)
        df.index.name = "gene_symbol"
        numeric_df = df.apply(pd.to_numeric, errors="coerce").fillna(0)
        numeric_df = numeric_df.loc[~numeric_df.index.duplicated(keep="first")]
        return numeric_df

    @staticmethod
    def _infer_sample_groups(columns: List[str], *, group_prefix: str = "tpm_") -> Dict[str, str]:
        groups: Dict[str, str] = {}
        for column in columns:
            group = str(column or "").strip()
            if group_prefix and group.startswith(group_prefix):
                group = group[len(group_prefix):]
            group = re.sub(r"_\d+$", "", group)
            group = group.strip()
            if not group:
                raise ValueError(f"Could not infer group from sample column: {column}")
            groups[column] = group
        return groups

    @staticmethod
    def _normalize_comparisons(
        comparisons_value: Optional[Sequence[Sequence[str]]],
        sample_groups: Dict[str, str],
    ) -> List[Tuple[str, str]]:
        available = sorted(set(sample_groups.values()))
        if not comparisons_value:
            return [(a, b) for a, b in combinations(available, 2)]

        normalized: List[Tuple[str, str]] = []
        for item in comparisons_value:
            if len(item) < 2:
                continue
            group1 = str(item[0] or "").strip()
            group2 = str(item[1] or "").strip()
            if not group1 or not group2 or group1 == group2:
                continue
            if group1 not in available or group2 not in available:
                raise ValueError(f"Unknown comparison group: {group1} vs {group2}")
            normalized.append((group1, group2))
        if not normalized:
            raise ValueError("No valid comparisons were provided")
        return normalized

    @staticmethod
    def _bh_adjust(pvalues: Sequence[float]) -> np.ndarray:
        values = np.asarray([1.0 if pd.isna(p) else float(p) for p in pvalues], dtype=float)
        n = len(values)
        if n == 0:
            return values
        order = np.argsort(values)
        ranked = values[order]
        adjusted = np.empty(n, dtype=float)
        prev = 1.0
        for i in range(n - 1, -1, -1):
            rank = i + 1
            value = min(prev, ranked[i] * n / rank)
            adjusted[order[i]] = min(value, 1.0)
            prev = value
        return adjusted

    def _expression_de_one_comparison(
        self,
        expr_log: pd.DataFrame,
        sample_groups: Dict[str, str],
        group1: str,
        group2: str,
        *,
        pvalue_threshold: float,
        logfc_cutoff: float,
    ) -> pd.DataFrame:
        g1_cols = [col for col, group in sample_groups.items() if group == group1 and col in expr_log.columns]
        g2_cols = [col for col, group in sample_groups.items() if group == group2 and col in expr_log.columns]
        if len(g1_cols) < 2 or len(g2_cols) < 2:
            raise ValueError(f"{group1} vs {group2} requires at least two samples per group")

        g1 = expr_log[g1_cols]
        g2 = expr_log[g2_cols]
        mean1 = g1.mean(axis=1)
        mean2 = g2.mean(axis=1)
        logfc = mean1 - mean2
        stat, pvalues = ttest_ind(g1.values, g2.values, axis=1, equal_var=False, nan_policy="omit")
        pvalues = np.nan_to_num(pvalues, nan=1.0, posinf=1.0, neginf=1.0)
        stat = np.nan_to_num(stat, nan=0.0, posinf=0.0, neginf=0.0)
        adj = self._bh_adjust(pvalues)

        result = pd.DataFrame({
            "gene_symbol": expr_log.index.astype(str),
            "logFC": logfc.values,
            "AveExpr": expr_log.mean(axis=1).values,
            "t": stat,
            "P.Value": pvalues,
            "adj.P.Val": adj,
        })
        result["significant"] = "Not significant"
        result.loc[(result["P.Value"] < pvalue_threshold) & (result["logFC"] > logfc_cutoff), "significant"] = "Up"
        result.loc[(result["P.Value"] < pvalue_threshold) & (result["logFC"] < -logfc_cutoff), "significant"] = "Down"
        result = result.sort_values("P.Value", ascending=True).reset_index(drop=True)
        return result

    def _draw_expression_volcano(
        self,
        deg: pd.DataFrame,
        *,
        pvalue_threshold: float,
        logfc_cutoff: float,
        title: str,
        output_png: Path,
    ) -> None:
        plot_df = deg.copy()
        plot_df["logP"] = -np.log10(plot_df["P.Value"].clip(lower=1e-300)).clip(upper=50)
        color_map = {
            "Up": VOLCANO_COLORS["Up"],
            "Down": VOLCANO_COLORS["Down"],
            "Not significant": VOLCANO_COLORS["Not Sig"],
        }
        fig, ax = plt.subplots(figsize=(7.2, 6.2))
        for label in ["Not significant", "Down", "Up"]:
            sub = plot_df[plot_df["significant"] == label]
            ax.scatter(
                sub["logFC"],
                sub["logP"],
                c=color_map[label],
                label=label,
                alpha=0.72 if label == "Not significant" else 0.9,
                s=16 if label == "Not significant" else 24,
                edgecolors="none",
            )
        ax.axvline(-logfc_cutoff, linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)
        ax.axvline(logfc_cutoff, linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)
        ax.axhline(-np.log10(max(pvalue_threshold, 1e-300)), linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)
        ax.set_xlabel("log2(Fold Change)")
        ax.set_ylabel("-log10(P value)")
        ax.set_title(title)
        top_up = plot_df[plot_df["significant"] == "Up"].nlargest(10, "logFC")
        top_down = plot_df[plot_df["significant"] == "Down"].nsmallest(10, "logFC")
        for _, row in pd.concat([top_up, top_down]).iterrows():
            ax.text(row["logFC"], row["logP"], str(row["gene_symbol"])[:24], fontsize=7, color=PALETTE["neutral_dark"])
        soften_axes(ax, grid_axis="both")
        ax.legend(loc="best", markerscale=1.2)
        fig.tight_layout()
        save_publication_png(fig, output_png)
        plt.close(fig)

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
            save_publication_png(fig, output_path)
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
        save_publication_png(fig, output_path)
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

    def _allocate_job_id(self, prefix: str = "volcano") -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{self._safe_title(prefix)}_{ts}"
