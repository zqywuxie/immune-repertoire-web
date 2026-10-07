"""
Volcano plot analysis service for VJ usage differential comparison.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
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
from scipy.stats import mannwhitneyu

from flask_app.services.figure_style import PALETTE, VOLCANO_COLORS, apply_publication_style, save_publication_png, soften_axes

# Encoding fallback for CSV/TSV files (GBK common in Chinese Windows environments)
_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]

def _try_read_csv(filepath, **kwargs):
    """Read CSV/TSV with encoding fallback."""
    suffix = str(filepath).lower()
    if suffix.endswith(".xlsx"):
        import pandas as pd
        kwargs.pop("low_memory", None)
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
        comparisons: Optional[Sequence[Sequence[str]]] = None,
        minimum_nonzero_samples: int = 3,
        selected_categories: Optional[Sequence[str]] = None,
        selected_samples: Optional[Sequence[str]] = None,
        output_name: Optional[str] = None,
        progress_callback=None,
    ) -> VolcanoReport:
        prepared = self.prepare_usage_inputs(data_dir, selected_categories=selected_categories,
            selected_samples=selected_samples, comparisons=comparisons, validate_comparisons=True)
        if minimum_nonzero_samples < 0:
            raise ValueError("minimum_nonzero_samples must be zero or greater")
        self.output_parent.mkdir(parents=True, exist_ok=True)
        from flask_app.services.project_storage_paths import allocate_result_dir
        job_id, output_base = allocate_result_dir(self.output_parent, "volcano")
        png_paths: List[str] = []
        csv_paths: List[str] = []
        work_items = [(path, table, left, right) for path, table in prepared["tables"]
            for left, right in self._normalize_usage_comparisons(comparisons, table["Category"].drop_duplicates().tolist())]
        csv_files = [path for path, _ in prepared["tables"]]
        used_titles = set()
        comparison_counts = []
        warnings = []

        input_file_count = len(csv_files)
        total = len(work_items)
        for idx, (file_path, table, group1, group2) in enumerate(work_items):
            if progress_callback:
                progress_callback(
                    5 + (idx / total) * 90,
                    "火山图分析",
                    f"处理 {file_path.name}：{group1} vs {group2} ({idx+1}/{total})",
                )

            title = self._safe_title(f"{self._extract_title(file_path.name)}_{group1}_vs_{group2}")
            if title in used_titles:
                title = f"{title}_{idx + 1}"
            used_titles.add(title)
            result_df, png_path = self._volcano_one_file(
                file_path, output_base, title,
                pvalue_threshold=pvalue_threshold,
                pseudocount=pseudocount,
                group_pair=(group1, group2),
                minimum_nonzero_samples=minimum_nonzero_samples,
                table=table,
            )
            group1_n = int(table["Category"].eq(group1).sum())
            group2_n = int(table["Category"].eq(group2).sum())
            comparison_counts.append({"input_file": file_path.name, "group1": group1, "group2": group2,
                "group1_n": group1_n, "group2_n": group2_n, "significant_feature_count": len(result_df)})
            if max(group1_n, group2_n) < minimum_nonzero_samples:
                warnings.append(f"{group1} / {group2} 两组样本数均少于 {minimum_nonzero_samples}，本比较不会标记显著特征。")
            png_paths.append(str(png_path))
            csv_path = output_base / f"{title}_volcano_results.csv"
            result_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            csv_paths.append(str(csv_path))

        if progress_callback:
            progress_callback(95, "火山图分析", f"完成 {len(png_paths)} 个火山图")

        used_samples = {sample for _, table, left, right in work_items
                        for sample in table.loc[table["Category"].isin([left, right]), "sample"]}
        unused_samples = [sample for sample in prepared["samples"] if sample not in used_samples]
        if unused_samples:
            warnings.append(f"所选范围中有 {len(unused_samples)} 个样本不属于本次比较分组，未参与差异计算。")
        metadata = {
            "data_dir": data_dir,
            "input_mode": "usage",
            "show_significance_filter": False,
            "analysis_notes": [
                "比较方向为前组 / 后组；正 log2FC 表示前组使用量较高。按原始 P 值判定显著性，同时报告 BH 校正值。",
                *[f"{row['group1']} / {row['group2']}：前组 {row['group1_n']} 个样本，后组 {row['group2_n']} 个样本，{row['significant_feature_count']} 个显著特征。" for row in comparison_counts],
                *warnings,
            ],
            "output_name": output_name or "V/J 使用差异分析",
            "sample_count": len(used_samples),
            "selected_sample_count": len(prepared["samples"]),
            "analyzed_samples": [sample for sample in prepared["samples"] if sample in used_samples],
            "unused_selected_samples": unused_samples,
            "comparison_sample_counts": comparison_counts,
            "warnings": warnings,
            "samples_by_value": prepared["samples_by_value"],
            "selected_samples": prepared["samples"],
            "significance_column": "P-value",
            "multiple_testing": "BH q_value reported; significance uses raw P-value",
            "file_count": input_file_count,
            "output_count": len(png_paths),
            "pvalue_threshold": pvalue_threshold,
            "comparisons": [
                {"group1": group1, "group2": group2, "input_file": file_path.name}
                for file_path, _, group1, group2 in work_items
            ],
            "minimum_nonzero_samples": minimum_nonzero_samples,
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
        selected_expression_groups=None,
        selected_expression_samples=None,
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
        if output_base is None and job_id is None:
            from flask_app.services.project_storage_paths import allocate_result_dir
            job_id_value, output_base_value = allocate_result_dir(self.output_parent, "volcano")
        else:
            job_id_value = job_id or self._allocate_job_id("volcano_expression")
            output_base_value = (output_base or (self.output_parent / job_id_value)).resolve()
        output_base_value.mkdir(parents=True, exist_ok=True)

        prepared = self.prepare_expression_input(expression_path, group_prefix=group_prefix,
            selected_expression_groups=selected_expression_groups, selected_expression_samples=selected_expression_samples,
            comparisons=comparisons, validate=True)
        expr_df = prepared["data"]
        sample_groups = prepared["sample_groups"]
        requested_comparisons = prepared["comparisons"]
        expr_df = expr_df.loc[(expr_df.sum(axis=1) > 0)]

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
                expr_df,
                sample_groups,
                group1,
                group2,
                pvalue_threshold=pvalue_threshold,
                logfc_cutoff=logfc_cutoff,
                quality_output=output_base_value / "DEG" / comp_name / "QC" / "sample_quality_weights.csv",
            )
            comp_dir = output_base_value / "DEG" / comp_name
            volcano_dir = comp_dir / "volcano"
            comp_dir.mkdir(parents=True, exist_ok=True)
            volcano_dir.mkdir(parents=True, exist_ok=True)

            full_csv = comp_dir / f"DEG_{comp_name}.csv"
            deg.to_csv(full_csv, index=False, encoding="utf-8-sig")
            csv_paths.append(str(full_csv))
            quality_path = comp_dir / "QC" / "sample_quality_weights.csv"
            if quality_path.is_file():
                csv_paths.append(str(quality_path))

            sig_csv = comp_dir / f"DEG_significant_{comp_name}.csv"
            sig_df = deg[deg["significant"].isin(["Up", "Down"])].copy()
            sig_df.to_csv(sig_csv, index=False, encoding="utf-8-sig")
            csv_paths.append(str(sig_csv))

            png_path = volcano_dir / f"volcano_{comp_name}.png"
            self._draw_expression_volcano(
                deg,
                pvalue_threshold=pvalue_threshold,
                logfc_cutoff=logfc_cutoff,
                title=f"表达差异（原始 P 值）：{group1} / {group2}",
                significance_column="significant_raw",
                output_png=png_path,
            )
            png_paths.append(str(png_path))

        if progress_callback:
            progress_callback(96, "表达矩阵火山图", f"完成 {len(png_paths)} 个比较")

        metadata = {
            "input_mode": "expression",
            "show_significance_filter": False,
            "analysis_notes": [
                "表达值按 log2(TPM+1) 转换并进行分位数归一化；使用 limma 质量加权线性模型。结果表的显著基因与后续富集按 BH-FDR 筛选。",
                f"全部所选 {len(sample_groups)} 个表达样本参与归一化；每个比较仅拟合对应两组。",
                *[f"{a} / {b}：前组 {list(sample_groups.values()).count(a)} 个样本，后组 {list(sample_groups.values()).count(b)} 个样本。" for a, b in requested_comparisons],
                "火山图的颜色、纵轴和阈值线沿用原始 P 值；FDR 判定请查看结果表中的 adj.P.Val 与 significant_fdr。",
                f"FDR 阈值为 {pvalue_threshold}，对数倍数变化阈值为 {logfc_cutoff}；比较方向为前组 / 后组。",
            ],
            "output_name": output_name or "表达差异分析",
            "expression_path": str(input_path.resolve()),
            "group_prefix": group_prefix,
            "groups": sorted(set(sample_groups.values())),
            "sample_count": len(sample_groups),
            "selected_expression_samples": list(sample_groups),
            "samples_by_value": prepared["samples_by_value"],
            "comparison_sample_counts": [{"group1": a, "group2": b, "group1_n": list(sample_groups.values()).count(a),
                "group2_n": list(sample_groups.values()).count(b)} for a, b in requested_comparisons],
            "gene_count": int(expr_df.shape[0]),
            "comparisons": [{"group1": a, "group2": b} for a, b in requested_comparisons],
            "pvalue_threshold": pvalue_threshold,
            "logfc_cutoff": logfc_cutoff,
            "differential_method": "limma::lmFit + eBayes(robust=TRUE)",
            "expression_transform": "log2(TPM + 1) + quantile normalization",
            "sample_quality_weights": "limma::arrayWeights",
            "significance_column": "significant_fdr",
            "plot_significance_column": "significant_raw",
            "plot_pvalue_column": "P.Value",
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
    def prepare_expression_input(expression_path: str, *, group_prefix="tpm_", selected_expression_groups=None,
                                 selected_expression_samples=None, comparisons=None, validate=False) -> Dict[str, Any]:
        path = Path(expression_path)
        if not path.is_file():
            raise ValueError("找不到转录组表达矩阵，请核对当前数据集。")
        data = VolcanoService._read_expression_matrix(path)
        sample_groups = VolcanoService._infer_sample_groups(data.columns.tolist(), group_prefix=group_prefix)
        groups = sorted(set(sample_groups.values()))
        for label, choices, available in (("表达分组", selected_expression_groups, groups),
                                          ("表达样本列", selected_expression_samples, list(sample_groups))):
            if choices is not None:
                if not isinstance(choices, (list, tuple)) or not choices:
                    raise ValueError(f"请至少选择一个{label}。")
                if not all(isinstance(choice, str) for choice in choices):
                    raise ValueError(f"{label}必须使用实际文本编号。")
                unknown = set(choices) - set(available)
                if unknown:
                    raise ValueError(f"当前矩阵中不存在所选{label}：{', '.join(sorted(unknown))}")
        selected = [name for name, group in sample_groups.items()
            if (selected_expression_groups is None or group in selected_expression_groups)
            and (selected_expression_samples is None or name in selected_expression_samples)]
        if not selected:
            raise ValueError("所选表达分组与样本没有交集。")
        data = data[selected]
        sample_groups = {name: sample_groups[name] for name in selected}
        groups = sorted(set(sample_groups.values()))
        if validate:
            if len(groups) < 2:
                raise ValueError("表达数据需要至少两个可比较的分组。")
            if not np.isfinite(data.to_numpy()).all() or (data < 0).any().any():
                raise ValueError("TPM 表达值必须为非负有限数值。")
            if not (data.sum(axis=1) > 0).any():
                raise ValueError("所选表达样本没有非零基因。")
        if validate and comparisons is not None and len(comparisons) == 0:
            raise ValueError("请至少选择一个表达组间比较。")
        pairs = VolcanoService._normalize_comparisons(comparisons, sample_groups) if validate else list(combinations(groups, 2))
        counts = {group: list(sample_groups.values()).count(group) for group in groups}
        if validate:
            for left, right in pairs:
                if min(counts[left], counts[right]) < 2:
                    raise ValueError(f"{left} / {right} 每组至少需要两个表达样本。")
        return {"data": data, "sample_groups": sample_groups, "groups": groups, "comparisons": pairs,
                "group_counts": counts, "samples_by_value": {group: [name for name, label in sample_groups.items() if label == group] for group in groups}}

    @staticmethod
    def inspect_expression_matrix(expression_path: str, group_prefix: str = "tpm_") -> Dict[str, Any]:
        path = Path(expression_path)
        if not path.is_file():
            raise ValueError("找不到转录组表达矩阵，请核对当前数据集。")
        # Inspection needs column identities and distinct gene count, not values.
        # Keep execution/preflight on prepare_expression_input for numeric validation.
        excel = str(path).lower().endswith((".xlsx", ".xls", ".xlsm"))
        if excel:
            columns = pd.read_excel(path, sheet_name=0, nrows=0).columns.tolist()
        else:
            sep = "\t" if str(path).lower().endswith((".tsv", ".tsv.gz")) else ","
            columns = _try_read_csv(path, sep=sep, nrows=0).columns.tolist()
        if len(columns) < 3:
            raise ValueError("表达矩阵需要一列基因编号和至少两列样本。")
        genes = set()
        if excel:
            identifiers = pd.read_excel(path, sheet_name=0, usecols=[0]).iloc[:, 0].astype(str)
            genes.update(identifiers[identifiers.str.strip() != ""])
        else:
            # Decode errors may occur after the first chunk, so retry the whole
            # identifier scan rather than choosing an encoding from headers only.
            for encoding in _CSV_ENCODINGS:
                try:
                    genes = set()
                    with pd.read_csv(path, sep=sep, encoding=encoding, low_memory=False, usecols=[0], chunksize=50000) as chunks:
                        for chunk in chunks:
                            identifiers = chunk.iloc[:, 0].astype(str)
                            genes.update(identifiers[identifiers.str.strip() != ""])
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
        if not genes:
            raise ValueError("表达矩阵没有有效基因行。")
        sample_groups = VolcanoService._infer_sample_groups(columns[1:], group_prefix=group_prefix)
        groups = sorted(set(sample_groups.values()))
        samples_by_value = {group: [sample for sample, label in sample_groups.items() if label == group] for group in groups}
        return {"expression_path": str(path.resolve()), "gene_count": len(genes),
            "sample_count": len(sample_groups), "groups": groups,
            "group_counts": {group: len(samples) for group, samples in samples_by_value.items()},
            "samples_by_value": samples_by_value, "columns": columns[1:],
            "suggested_comparisons": [{"group1": a, "group2": b} for a, b in combinations(groups, 2)]}

    @staticmethod
    def prepare_usage_inputs(data_dir: str, *, selected_categories=None, selected_samples=None,
                             comparisons=None, validate_comparisons=False) -> Dict[str, Any]:
        """Inspect and filter the same source tables used by the worker without writing files."""
        source = Path(data_dir)
        if not source.exists():
            raise ValueError(f"找不到基因使用输入：{data_dir}")
        files, concatenate = VolcanoService._usage_source_files(source)
        if concatenate:
            directory = files[0].parent
            tables = [(directory / f"df_{VolcanoService._safe_title(directory.name)}_all.csv",
                       VolcanoService._concat_usage_files(files))]
        else:
            tables = [(path, VolcanoService._read_usage_table(path)) for path in files]
        if not tables:
            raise ValueError("当前结果中没有可用于 V/J 差异分析的基因使用表。")
        identities = {}
        for path, table in tables:
            if table.empty or table["sample"].eq("").any() or table["Category"].eq("").any():
                raise ValueError(f"{path.name} 包含空样本或空分组。")
            if table["sample"].duplicated().any():
                raise ValueError(f"{path.name} 存在重复样本编号，请选择保留批次编号的汇总表。")
            for sample, category in zip(table["sample"], table["Category"]):
                if sample in identities and identities[sample] != category:
                    raise ValueError(f"样本 {sample} 在不同输入表中的分组不一致。")
                identities[sample] = category
        available_categories = list(dict.fromkeys(identities.values()))
        for label, selection, available in (("分组", selected_categories, available_categories),
                                             ("样本", selected_samples, list(identities))):
            if selection is not None:
                if not isinstance(selection, (list, tuple)) or not selection:
                    raise ValueError(f"请至少选择一个{label}。")
                unknown = set(selection) - set(available)
                if unknown:
                    raise ValueError(f"当前输入中不存在所选{label}：{', '.join(sorted(unknown))}")
        filtered = []
        for path, table in tables:
            chosen = table
            if selected_categories is not None:
                chosen = chosen[chosen["Category"].isin(selected_categories)]
            if selected_samples is not None:
                chosen = chosen[chosen["sample"].isin(selected_samples)]
            if chosen.empty:
                continue
            if validate_comparisons:
                pairs = VolcanoService._normalize_usage_comparisons(comparisons, chosen["Category"].drop_duplicates().tolist())
                if not pairs:
                    raise ValueError("所选样本需要包含至少两个可比较的分组。")
            filtered.append((path, chosen.copy()))
        if not filtered:
            raise ValueError("所选分组与样本没有交集，请调整分析范围。")
        chosen_ids = {sample for _, table in filtered for sample in table["sample"]}
        groups = {}
        for sample, category in identities.items():
            if sample in chosen_ids:
                groups.setdefault(category, []).append(sample)
        return {"tables": filtered, "samples": list(sample for sample in identities if sample in chosen_ids),
                "samples_by_value": groups, "groups": list(groups),
                "group_counts": {group: len(samples) for group, samples in groups.items()}}

    @staticmethod
    def _usage_source_files(source: Path) -> Tuple[List[Path], bool]:
        """Choose exactly the files consumed by V/J inspection and execution."""
        if source.is_file():
            return [source], False
        for directory in VolcanoService._candidate_usage_dirs(source):
            files = sorted(set(directory.glob("df*.csv")) | set(directory.glob("df*.csv.gz")))
            if files:
                return files, False
            chain_files = []
            for path in sorted(directory.glob("*.csv")):
                columns = _try_read_csv(path, nrows=0).columns.tolist()
                if "Category" in columns and len(columns) > columns.index("Category") + 1:
                    chain_files.append(path)
            if chain_files:
                return chain_files, True
        return [], False

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
            df = _try_read_csv(file_path, low_memory=False, dtype=str, keep_default_na=False)
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
        safe = re.sub(r"[^\w.-]+", "_", str(name or "usage")).strip("_")
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
        expression: pd.DataFrame,
        sample_groups: Dict[str, str],
        group1: str,
        group2: str,
        *,
        pvalue_threshold: float,
        logfc_cutoff: float,
        quality_output: Path,
    ) -> pd.DataFrame:
        g1_cols = [col for col, group in sample_groups.items() if group == group1 and col in expression.columns]
        g2_cols = [col for col, group in sample_groups.items() if group == group2 and col in expression.columns]
        if len(g1_cols) < 2 or len(g2_cols) < 2:
            raise ValueError(f"{group1} vs {group2} requires at least two samples per group")
        rscript = shutil.which("Rscript")
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_transcriptome_limma.R"
        if not rscript:
            raise RuntimeError("转录组差异分析需要容器内的 Rscript 和 limma 包。")
        with tempfile.TemporaryDirectory(prefix="immune-limma-") as temp_dir:
            temp_root = Path(temp_dir)
            matrix_path = temp_root / "expression.csv"
            group_path = temp_root / "groups.csv"
            output_path = temp_root / "limma.csv"
            quality_path = temp_root / "sample_quality_weights.csv"
            input_frame = expression.copy()
            input_frame.insert(0, "gene_symbol", input_frame.index.astype(str))
            input_frame.to_csv(matrix_path, index=False)
            pd.DataFrame({"sample": list(sample_groups), "group": list(sample_groups.values())}).to_csv(group_path, index=False)
            completed = subprocess.run(
                [rscript, str(script_path), str(matrix_path), str(group_path), group1, group2, str(output_path), str(quality_path)],
                text=True, capture_output=True, check=False,
            )
            if completed.returncode != 0:
                detail_lines = [line.strip() for line in completed.stderr.splitlines() if line.strip()]
                diagnostic = next(
                    (line for line in detail_lines if line.startswith(("Error", "错误"))),
                    next((line for line in detail_lines if line != "Execution halted"), ""),
                )
                raise RuntimeError(
                    "limma 差异分析失败：" + (diagnostic or "请检查 R 运行环境。")
                )
            if not output_path.is_file():
                raise RuntimeError("limma 未生成差异分析结果。")
            result = pd.read_csv(output_path)
            if not quality_path.is_file():
                raise RuntimeError("limma 未生成样本质量权重结果。")
            quality_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(quality_path, quality_output)

        if result.empty:
            raise ValueError(f"{group1} vs {group2} 未生成有效差异表达结果")
        result["significant_raw"] = "Not significant"
        result.loc[(result["P.Value"] < pvalue_threshold) & (result["logFC"] > logfc_cutoff), "significant_raw"] = "Up"
        result.loc[(result["P.Value"] < pvalue_threshold) & (result["logFC"] < -logfc_cutoff), "significant_raw"] = "Down"
        result["significant_fdr"] = "Not significant"
        result.loc[(result["adj.P.Val"] < pvalue_threshold) & (result["logFC"] > logfc_cutoff), "significant_fdr"] = "Up"
        result.loc[(result["adj.P.Val"] < pvalue_threshold) & (result["logFC"] < -logfc_cutoff), "significant_fdr"] = "Down"
        result["significant"] = result["significant_fdr"]
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
        significance_column: str = "significant_raw",
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
            sub = plot_df[plot_df[significance_column] == label]
            ax.scatter(
                sub["logFC"],
                sub["logP"],
                c=color_map[label],
                label={"Up": "升高", "Down": "降低", "Not significant": "未达到显著阈值"}[label],
                alpha=0.72 if label == "Not significant" else 0.9,
                s=16 if label == "Not significant" else 24,
                edgecolors="none",
            )
        ax.axvline(-logfc_cutoff, linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)
        ax.axvline(logfc_cutoff, linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)
        ax.axhline(-np.log10(max(pvalue_threshold, 1e-300)), linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)
        ax.set_xlabel("log2(倍数变化)")
        ax.set_ylabel("-log10(P 值)")
        ax.set_title(title)
        top_up = plot_df[plot_df[significance_column] == "Up"].nlargest(10, "logFC")
        top_down = plot_df[plot_df[significance_column] == "Down"].nsmallest(10, "logFC")
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
        group_pair: Optional[Tuple[str, str]] = None,
        minimum_nonzero_samples: int = 3,
        table: Optional[pd.DataFrame] = None,
    ):
        df = table.copy() if table is not None else self._read_usage_table(file_path)
        groups = df["Category"].drop_duplicates().astype(str).tolist()
        if group_pair is None:
            if len(groups) < 2:
                raise ValueError(f"Need at least 2 unique Category values, got {groups}")
            group1, group2 = groups[0], groups[1]
        else:
            group1, group2 = group_pair
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

            nonzero_n_group1 = int(np.count_nonzero(v1 > 0))
            nonzero_n_group2 = int(np.count_nonzero(v2 > 0))
            max_nonzero_n = max(nonzero_n_group1, nonzero_n_group2)
            passes_support_filter = max_nonzero_n >= minimum_nonzero_samples

            try:
                _, pval = mannwhitneyu(v1, v2, alternative="two-sided")
            except Exception:
                pval = np.nan

            significant = "Not Sig"
            if pval < pvalue_threshold and passes_support_filter:
                significant = "Up" if log2fc > 0 else "Down"

            results.append({
                "Gene": col,
                "Mean_" + str(group1): round(mean1, 6),
                "Mean_" + str(group2): round(mean2, 6),
                "FC": round(fc, 6),
                "log2FC": round(log2fc, 6),
                "P-value": pval,
                "nonzero_n_group1": nonzero_n_group1,
                "nonzero_n_group2": nonzero_n_group2,
                "max_nonzero_n": max_nonzero_n,
                "passes_support_filter": passes_support_filter,
                "significant": significant,
            })

        result_df = pd.DataFrame(results)
        if result_df.empty:
            result_df = pd.DataFrame(columns=[
                "Gene", "FC", "log2FC", "P-value", "q_value", "nonzero_n_group1",
                "nonzero_n_group2", "max_nonzero_n", "passes_support_filter", "significant",
            ])
        else:
            result_df["q_value"] = self._bh_adjust(result_df["P-value"].to_numpy())

        # Generate volcano plot
        png_path = output_base / f"{title}_volcano.png"
        self._draw_volcano(result_df, pvalue_threshold, group1, group2, title, png_path)

        export_df = result_df[
            (result_df["P-value"] < pvalue_threshold) & result_df["passes_support_filter"]
        ][[
            "Gene", "log2FC", "P-value", "q_value", "FC", "significant",
            "nonzero_n_group1", "nonzero_n_group2", "max_nonzero_n", "passes_support_filter",
        ]].copy()
        if not export_df.empty:
            df_pos = export_df[export_df["log2FC"] > 0].sort_values("log2FC", ascending=False)
            df_neg = export_df[export_df["log2FC"] < 0].sort_values("log2FC", ascending=True)
            export_df = pd.concat([df_pos, df_neg], axis=0).reset_index(drop=True)

        return export_df, png_path

    @staticmethod
    def _read_usage_table(file_path: Path, *, nrows=None) -> pd.DataFrame:
        df = _try_read_csv(file_path, low_memory=False, dtype=str, keep_default_na=False, nrows=nrows).copy()
        if len(df.columns) == 0:
            raise ValueError(f"基因使用表 {file_path.name} 没有可读取的列。")
        if df.columns[0] != "sample":
            df.rename(columns={df.columns[0]: "sample"}, inplace=True)
        if "Category" not in df.columns:
            cat_cols = [c for c in df.columns if str(c).lower() in ("category", "group", "therapy", "disease")]
            if cat_cols:
                df.rename(columns={cat_cols[0]: "Category"}, inplace=True)
            else:
                raise ValueError(f"基因使用表 {file_path.name} 缺少分组列。")
        df["sample"] = df["sample"].astype(str).str.strip()
        df["Category"] = df["Category"].astype(str).str.strip()
        return df

    @staticmethod
    def _normalize_usage_comparisons(
        comparisons: Optional[Sequence[Sequence[str]]], groups: Sequence[str]
    ) -> List[Tuple[str, str]]:
        available = [str(group) for group in groups]
        if comparisons is None:
            return list(combinations(available, 2))
        if not comparisons:
            raise ValueError("Select at least one V/J usage group comparison")
        normalized: List[Tuple[str, str]] = []
        seen = set()
        for item in comparisons:
            if len(item) < 2:
                continue
            group1, group2 = str(item[0]).strip(), str(item[1]).strip()
            if group1 == group2 or group1 not in available or group2 not in available:
                raise ValueError(f"Unknown usage comparison group: {group1} vs {group2}")
            if (group1, group2) not in seen:
                seen.add((group1, group2))
                normalized.append((group1, group2))
        if not normalized:
            raise ValueError("No valid usage comparisons were provided")
        return normalized

    def _draw_volcano(self, df, p_cutoff, g1, g2, title, output_path):
        fig, ax = plt.subplots(figsize=(6.4, 5.6))
        if df.empty:
            ax.set_xlabel(f"log2(倍数变化)\n({g1} / {g2})")
            ax.set_ylabel("-log10(P 值)")
            ax.set_title(title)
            ax.text(0.5, 0.5, "无可检验特征", ha="center", va="center", transform=ax.transAxes)
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
                label={"Up": "升高", "Down": "降低", "Not Sig": "未达到显著阈值"}[label],
                alpha=0.82 if label == "Not Sig" else 0.9,
                s=38 if label == "Not Sig" else 46,
                edgecolors="white",
                linewidths=0.8,
            )

        fc_cutoff = 0
        ax.axhline(-np.log10(p_cutoff), linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)
        ax.axvline(fc_cutoff, linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)
        ax.axvline(-fc_cutoff, linestyle="--", color=PALETTE["neutral_mid"], linewidth=0.9)

        ax.set_xlabel(f"log2(倍数变化)\n({g1} / {g2})")
        ax.set_ylabel("-log10(P 值)")
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
