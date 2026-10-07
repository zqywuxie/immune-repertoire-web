"""
TopClone analysis service — trace mode (CDR3_trace) and per-sample mode.

Trace mode mirrors the CDR3_trace.ipynb reference notebook:
  - reads pep_data/{chain}/{sample}__{chain}.csv(.gz)
  - groups + filters CDR3 sequences, computes top-N clone proportions
  - merges profile annotations (therapy, disease, etc.)
  - outputs topclone.csv + per-chain top CDR3 sequence files + boxplots
"""

from __future__ import annotations

import json
import logging
import re
from itertools import combinations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from scipy.stats import mannwhitneyu

from flask_app.services.boxplot_service import BoxPlotService
from flask_app.services.pep_analysis_service import _batch_sample_identity
from flask_app.services.figure_style import apply_publication_style

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
    if suffix.endswith(".tsv"):
        sep = "\t"
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(filepath, encoding=enc, sep=sep, **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(filepath, sep=sep, **kwargs)


logger = logging.getLogger(__name__)

CHAIN_NAMES = {"TRA", "TRB", "TRG", "TRD", "IGH", "IGK", "IGL"}
CHAIN_ALIASES: Dict[str, str] = {
    "ALPHA": "TRA", "BETA": "TRB", "GAMMA": "TRG", "DELTA": "TRD",
    "HEAVY": "IGH", "KAPPA": "IGK", "LAMBDA": "IGL",
}
FILE_PATTERN = re.compile(
    r"^(?P<sample>.+?)__(?P<chain>TRA|TRB|TRG|TRD|IGH|IGK|IGL)$",
    re.IGNORECASE,
)
TOP_N_VALUES = [10, 20, 50, 100]


@dataclass
class TopCloneReport:
    job_id: str
    output_base: Path
    topclone_csv_path: Optional[str]
    boxplot_report: Any  # BoxPlotReport or None
    per_sample_files: List[str]
    metadata: Dict[str, Any]
    stats_csv_path: Optional[str] = None
    effect_heatmap_paths: Optional[List[str]] = None
    effect_statistics_paths: Optional[List[str]] = None


class TopCloneService:
    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def generate_report(
        self,
        *,
        pep_data_path: str,
        datapoint_path: str,
        pep_paths: Optional[List[str]] = None,
        selected_samples: Optional[List[str]] = None,
        selected_group_values: Optional[Dict[str, List[str]]] = None,
        selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
        group_sample_identity: str = "sample",
        mode: str = "trace",
        top_n: int = 10,
        group_field: Optional[str] = None,
        batch_field: Optional[str] = None,
        group_order: Optional[str] = None,
        pvalue_threshold: float = 0.05,
        output_name: Optional[str] = None,
        profile_sheet: Optional[str] = None,
        selected_chains: Optional[List[str]] = None,
        progress_callback=None,
    ) -> TopCloneReport:
        pep_data = Path(pep_data_path)
        inputs = list(dict.fromkeys(pep_paths or [pep_data_path]))
        for path in inputs:
            if not Path(path).exists():
                raise FileNotFoundError(f"克隆数据路径不存在：{path}")
        if mode not in {"trace", "per_sample"}:
            raise ValueError("请选择有效的优势克隆分析模式。")
        if top_n < 1:
            raise ValueError("提取克隆数量必须至少为 1。")
        if not isinstance(group_sample_identity, str) or group_sample_identity not in {"sample", "batch_sample"} or (group_sample_identity == "batch_sample" and not batch_field):
            raise ValueError("批次样本选择需要有效的批次字段与编号方式。")

        datapoint = Path(datapoint_path)
        if datapoint_path and not datapoint.is_file():
            raise FileNotFoundError(f"Datapoint file not found: {datapoint_path}")

        profile_df = None
        batch_values = set()
        if datapoint_path:
            profile_df = self._read_profile(datapoint, profile_sheet, batch_field,
                list(dict.fromkeys([group_field] + list(selected_group_values or {}) + list(selected_samples_by_group or {}))))
            profile_df, batch_values = self._select_profile(
                profile_df, batch_field, selected_samples, selected_group_values,
                selected_samples_by_group, group_sample_identity,
            )
        elif mode == "trace" or batch_field or selected_samples or selected_group_values or selected_samples_by_group:
            raise ValueError("分组或样本筛选需要样本指标表。")
        chain_files = self._discover_inputs(inputs)
        self.output_parent.mkdir(parents=True, exist_ok=True)
        from flask_app.services.project_storage_paths import allocate_result_dir
        job_id, output_base = allocate_result_dir(self.output_parent, "topclone")

        if mode == "trace":
            report = self._run_trace_mode(
                pep_data=pep_data,
                datapoint=datapoint,
                profile_df=profile_df,
                batch_values=batch_values,
                chain_files=chain_files,
                group_sample_identity=group_sample_identity,
                output_base=output_base,
                job_id=job_id,
                group_field=group_field,
                batch_field=batch_field,
                group_order=group_order,
                pvalue_threshold=pvalue_threshold,
                output_name=output_name,
                profile_sheet=profile_sheet,
                selected_chains=selected_chains,
                progress_callback=progress_callback,
            )
        else:
            report = self._run_per_sample_mode(
                pep_data=pep_data,
                output_base=output_base,
                job_id=job_id,
                top_n=top_n,
                profile_df=profile_df,
                batch_values=batch_values,
                batch_field=batch_field,
                chain_files=chain_files,
                group_sample_identity=group_sample_identity,
                selected_chains=selected_chains,
                progress_callback=progress_callback,
            )

        report.metadata["pep_paths"] = inputs
        return report

    # ------------------------------------------------------------------
    # Chain / sample discovery
    # ------------------------------------------------------------------
    def _discover_files(self, pep_data: Path) -> Dict[str, List[Path]]:
        """Return {chain: [file_path, ...]} for all supported chain CSV files."""
        chain_files: Dict[str, List[Path]] = {}
        if pep_data.is_file():
            chain = self._detect_chain_from_filename(pep_data.name)
            return {chain: [pep_data]} if chain else {}

        # Support both the original chain/sample layout and batch/chain/sample.
        chain_dirs = [
            directory for directory in pep_data.rglob("*")
            if directory.is_dir() and self._normalize_chain(directory.name) in CHAIN_NAMES
        ]
        if self._normalize_chain(pep_data.name) in CHAIN_NAMES:
            chain_dirs.append(pep_data)
        if chain_dirs:
            for chain_dir in chain_dirs:
                chain = self._normalize_chain(chain_dir.name)
                files = (
                    sorted(chain_dir.glob("*.csv"))
                    + sorted(chain_dir.glob("*.csv.gz"))
                )
                if files:
                    chain_files.setdefault(chain, []).extend(files)
            if chain_files:
                return chain_files

        # Fallback: flat directory — detect chain from filename
        for f in sorted(list(pep_data.glob("*.csv")) + list(pep_data.glob("*.csv.gz"))):
            chain = self._detect_chain_from_filename(f.name)
            if chain:
                chain_files.setdefault(chain, []).append(f)

        return chain_files

    def _discover_inputs(self, inputs: List[str]) -> Dict[str, List[Path]]:
        chain_files: Dict[str, List[Path]] = {}
        seen = set()
        for source in inputs:
            for chain, files in self._discover_files(Path(source)).items():
                for file in files:
                    resolved = file.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        chain_files.setdefault(chain, []).append(file)
        return chain_files

    @staticmethod
    def _select_profile(profile_df, batch_field, selected_samples, selected_group_values,
                        selected_samples_by_group, group_sample_identity):
        if "sample" not in profile_df.columns:
            raise ValueError("样本指标表缺少 sample 列。")
        profile_df["sample"] = profile_df["sample"].astype(str).str.strip()
        if profile_df["sample"].eq("").any():
            raise ValueError("样本指标表包含空样本编号。")
        batch_values = set()
        if batch_field:
            if batch_field not in profile_df.columns or batch_field == "sample":
                raise ValueError("所选批次字段不存在或不能是样本编号字段。")
            profile_df[batch_field] = profile_df[batch_field].astype(str).str.strip()
            if profile_df[batch_field].eq("").any():
                raise ValueError("样本指标表包含空批次编号。")
            if profile_df.duplicated(["sample", batch_field]).any():
                raise ValueError("样本指标表中的样本编号与批次组合必须唯一。")
            batch_values = set(profile_df[batch_field])
        elif profile_df["sample"].duplicated().any():
            raise ValueError("样本指标表存在跨批次同名样本，请选择批次字段后再分析。")
        identities = (
            pd.Series([_batch_sample_identity(batch, sample) for sample, batch in
                       profile_df[["sample", batch_field]].itertuples(index=False, name=None)], index=profile_df.index)
            if group_sample_identity == "batch_sample" else profile_df["sample"]
        )
        for field, values in (selected_group_values or {}).items():
            if field not in profile_df.columns:
                raise ValueError(f"所选分组字段不存在：{field}")
            profile_df[field] = profile_df[field].astype(str).str.strip()
            allowed = {str(value).strip() for value in values if str(value).strip()}
            if allowed:
                profile_df = profile_df[profile_df[field].isin(allowed)].copy()
        for field, groups in (selected_samples_by_group or {}).items():
            if field not in profile_df.columns:
                raise ValueError(f"所选样本分组字段不存在：{field}")
            profile_df[field] = profile_df[field].astype(str).str.strip()
            keep = pd.Series(False, index=profile_df.index)
            for group, samples in groups.items():
                keep |= profile_df[field].eq(str(group).strip()) & identities.loc[profile_df.index].isin(
                    {str(sample).strip() for sample in samples})
            profile_df = profile_df[keep].copy()
        if selected_samples:
            profile_df = profile_df[profile_df["sample"].isin({str(sample).strip() for sample in selected_samples})].copy()
        if profile_df.empty:
            raise ValueError("筛选后没有可分析的样本，请检查分组和样本选择。")
        return profile_df, batch_values

    @staticmethod
    def _normalize_chain(raw: str) -> str:
        upper = re.sub(r"[^A-Za-z]", "", raw).upper()
        return CHAIN_ALIASES.get(upper, upper)

    @staticmethod
    def _detect_chain_from_filename(filename: str) -> Optional[str]:
        stem = Path(filename).stem
        # Strip .csv if present (for .csv.gz, stem only removes .gz)
        if stem.lower().endswith(".csv"):
            stem = stem[:-4]
        match = FILE_PATTERN.match(stem)
        if match and match.group("chain"):
            return match.group("chain").upper()
        return None

    @classmethod
    def _filter_chain_files(
        cls,
        chain_files: Dict[str, List[Path]],
        selected_chains: Optional[List[str]],
    ) -> Dict[str, List[Path]]:
        selected = {
            cls._normalize_chain(str(chain))
            for chain in (selected_chains or [])
            if str(chain or "").strip()
        }
        if not selected:
            return chain_files
        return {
            chain: files
            for chain, files in chain_files.items()
            if cls._normalize_chain(chain) in selected
        }

    @staticmethod
    def _parse_sample_name(file_path: Path, chain: str) -> Optional[str]:
        """Extract sample name from a PEP file path like {sample}__{chain}.csv(.gz)."""
        stem = Path(file_path.name).stem
        if stem.lower().endswith(".csv"):
            stem = stem[:-4]
        match = FILE_PATTERN.match(stem)
        if match and match.group("sample"):
            return match.group("sample").rstrip("_-")
        return None

    @staticmethod
    def _batch_for_file(file_path: Path, pep_root: Path, batch_values: set[str]) -> Optional[str]:
        """Return the unique selected batch label present in a file's ancestors."""
        matches = {
            ancestor.name.strip()
            for ancestor in file_path.parents
            if ancestor.name.strip() in batch_values
        }
        if len(matches) > 1:
            raise ValueError(
                f"PEP 文件路径包含多个可匹配批次目录：{file_path}"
            )
        return next(iter(matches)) if matches else None

    @staticmethod
    def _read_profile(
        path: Path, sheet: Optional[str] = None, batch_field: Optional[str] = None,
        text_fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """Read profile CSV or XLSX file."""
        text_columns = {"sample": str, **{field: str for field in (text_fields or []) if field}}
        if batch_field:
            text_columns[batch_field] = str
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            df = pd.read_excel(path, sheet_name=sheet or 0, dtype=text_columns)
        elif suffix == ".tsv":
            df = _try_read_csv(path, sep="\t", low_memory=False, dtype=text_columns)
        else:
            df = _try_read_csv(path, low_memory=False, dtype=text_columns)
        df.fillna("", inplace=True)
        return df

    @staticmethod
    def _compute_top_clones(df_pep: pd.DataFrame) -> Dict[str, Any]:
        """
        Compute top-N clone proportions and top CDR3 sequences from a PEP dataframe.

        Returns dict with keys:
          - f'top{N}_proportion' for each N in TOP_N_VALUES
          - f'top{N}_cdr3s' for each N — sorted list of CDR3(pep) strings
        """
        df = df_pep[["CDR3(pep)", "copy"]].copy()
        df["copy"] = pd.to_numeric(df["copy"], errors="coerce").fillna(0)
        df_grp = df.groupby("CDR3(pep)")["copy"].sum().reset_index()
        df_grp = df_grp[~df_grp["CDR3(pep)"].str.contains(r"\*|_", na=False)]
        df_grp = df_grp.sort_values("copy", ascending=False)

        total_copies = df_grp["copy"].sum()
        result: Dict[str, Any] = {}
        for n_val in TOP_N_VALUES:
            top_slice = df_grp.head(n_val)
            if total_copies > 0:
                result[f"top{n_val}_proportion"] = float(
                    top_slice["copy"].sum() / total_copies
                )
            else:
                result[f"top{n_val}_proportion"] = float("nan")
            result[f"top{n_val}_cdr3s"] = top_slice["CDR3(pep)"].tolist()
        return result

    # ------------------------------------------------------------------
    # Trace mode (CDR3_trace.ipynb)
    # ------------------------------------------------------------------
    def _run_trace_mode(
        self,
        *,
        pep_data: Path,
        datapoint: Path,
        output_base: Path,
        job_id: str,
        profile_df: pd.DataFrame,
        batch_values: set[str],
        chain_files: Dict[str, List[Path]],
        group_sample_identity: str,
        group_field: Optional[str],
        batch_field: Optional[str],
        group_order: Optional[str],
        pvalue_threshold: float,
        output_name: Optional[str] = None,
        profile_sheet: Optional[str] = None,
        selected_chains: Optional[List[str]] = None,
        progress_callback=None,
    ) -> TopCloneReport:
        if group_field and group_field not in profile_df.columns:
            raise ValueError(f"所选分组字段不存在：{group_field}")
        # Profile rows were validated and selected before discovery.
        duplicate_samples = profile_df["sample"].duplicated(keep=False)
        sample_list = profile_df["sample"].tolist()
        category_cols = [c for c in profile_df.columns if c != "sample"]

        # 2. Discover chain files & build O(1) lookup by sample, batch and chain.
        chain_files = self._filter_chain_files(chain_files, selected_chains)
        if not chain_files:
            raise ValueError("No selected chain CSV files found in pep_data path")

        sample_chain_map: Dict[tuple, Path] = {}
        for chain, files in chain_files.items():
            for f in files:
                sample = self._parse_sample_name(f, chain)
                if sample:
                    batch = self._batch_for_file(f, pep_data, batch_values) if batch_field else None
                    if duplicate_samples.any() and batch_field and batch is None:
                        raise ValueError(
                            "无法根据 PEP 目录批次名匹配重复样本，请确保目录名与所选批次字段值一致："
                            f"{sample} / {batch_field}"
                        )
                    key = (sample, batch or "", chain)
                    if key in sample_chain_map:
                        raise ValueError(
                            f"克隆数据中样本、批次与链型组合重复：{sample} / {batch or '未指定批次'} / {chain}"
                        )
                    sample_chain_map[key] = f

        if duplicate_samples.any():
            mapped_sample_batches = {
                (sample, batch) for sample, batch, _chain in sample_chain_map
            }
            unmapped = [
                f"{sample} / {batch}"
                for sample, batch in profile_df.loc[duplicate_samples, ["sample", batch_field]].itertuples(index=False, name=None)
                if (sample, batch) not in mapped_sample_batches
            ]
            if unmapped:
                raise ValueError(
                    "无法根据 PEP 目录批次名匹配重复样本，请确保目录名与所选批次字段值一致："
                    + "、".join(unmapped[:10])
                )

        chains = sorted(chain_files.keys())

        if progress_callback:
            progress_callback(
                5, "优势克隆分析",
                f"发现 {len(chains)} 种链型，指标表含 {len(sample_list)} 个样本。",
                {"chains": chains, "samples": len(sample_list)},
            )

        # 3. Build topclone data + per-chain CDR3 sequences
        topclone_records: List[Dict[str, Any]] = []
        # Store top CDR3 sequences keyed by (chain, n_val) -> {sample: [cdr3, ...]}
        cdr3_sequences: Dict[str, Dict[str, List[str]]] = {}

        total_steps = len(chains) * len(sample_list)
        step = 0

        for chain in chains:
            for n_val in TOP_N_VALUES:
                cdr3_sequences.setdefault(f"{chain}_top{n_val}", {})

        sample_rows = (
            profile_df[["sample", batch_field]].itertuples(index=False, name=None)
            if batch_field else ((sample, None) for sample in sample_list)
        )
        for sample, batch in sample_rows:
            sample_key = (sample, batch) if batch_field else sample
            record: Dict[str, Any] = {"sample": sample}
            if batch_field:
                record[batch_field] = batch
            sample_has_all_chain_data = True

            for chain in chains:
                sample_file = sample_chain_map.get((sample, batch or "", chain))
                if sample_file is None and not batch_field:
                    sample_file = sample_chain_map.get((sample, "", chain))
                if sample_file is None:
                    sample_has_all_chain_data = False
                    break

                step += 1
                try:
                    df_pep = _try_read_csv(sample_file, low_memory=False)
                    if "CDR3(pep)" not in df_pep.columns or "copy" not in df_pep.columns:
                        raise ValueError("缺少 CDR3(pep) 或 copy 列。")
                    if df_pep.empty:
                        sample_has_all_chain_data = False
                        break

                    top_result = self._compute_top_clones(df_pep)

                    for n_val in TOP_N_VALUES:
                        record[f"top{n_val}{chain}"] = top_result[f"top{n_val}_proportion"]
                        cdr3_sequences[f"{chain}_top{n_val}"][sample_key] = top_result[f"top{n_val}_cdr3s"]

                except Exception as exc:
                    raise ValueError(f"处理样本 {sample} / {chain} 失败：{exc}") from exc

                if progress_callback and step % max(1, total_steps // 20) == 0:
                    progress_callback(
                        5 + int(step / max(total_steps, 1) * 50),
                        "优势克隆分析",
                        f"正在处理样本 {sample} / {chain}（{step}/{total_steps}）。",
                    )

            if sample_has_all_chain_data:
                topclone_records.append(record)

        if not topclone_records:
            raise ValueError("No Profile samples have usable data for every selected chain")

        # 4. Build topclone_df and merge with profile annotations
        topclone_df = pd.DataFrame(topclone_records)
        # Merge profile category columns using pd.merge (like reference notebook)
        merge_keys = ["sample"] + ([batch_field] if batch_field else [])
        profile_merge_cols = list(dict.fromkeys(merge_keys + category_cols))
        profile_merge_df = profile_df[profile_merge_cols].copy()
        topclone_df = profile_merge_df.merge(topclone_df, on=merge_keys, how="inner")

        topclone_csv = output_base / "topclone.csv"
        topclone_df.to_csv(topclone_csv, index=False)
        stats_csv = output_base / "pairwise_statistics.csv"
        statistics = self._compute_pairwise_statistics(topclone_df, group_field or "", group_order)
        statistics.to_csv(stats_csv, index=False)
        effect_heatmap_paths, effect_statistics_paths = self._generate_effect_heatmaps(
            topclone_df=topclone_df,
            group_column=group_field or "",
            group_order=group_order,
            output_base=output_base / "topclone_effect_heatmap",
        )

        # 5. Save top CDR3 sequence files per chain
        cdr3_dir = output_base / "top_cdr3_sequences"
        cdr3_dir.mkdir(parents=True, exist_ok=True)
        for chain in chains:
            chain_dir = cdr3_dir / chain
            chain_dir.mkdir(parents=True, exist_ok=True)
            for n_val in TOP_N_VALUES:
                key = f"{chain}_top{n_val}"
                seq_dict = cdr3_sequences.get(key, {})
                records = []
                for sample_key, seqs in seq_dict.items():
                    sample, batch = sample_key if batch_field else (sample_key, None)
                    row = {
                        "sample": sample,
                        "top_cdr3s": ";".join(seqs),
                        "count": len(seqs),
                    }
                    if batch_field:
                        row[batch_field] = batch
                    records.append(row)
                if records:
                    seq_df = pd.DataFrame(records)
                    seq_csv = chain_dir / f"top{n_val}_cdr3s.csv"
                    seq_df.to_csv(seq_csv, index=False)

        if progress_callback:
            progress_callback(60, "优势克隆分析", "优势克隆数据表已生成，开始绘制分组比较图。")

        # 6. Run BoxPlot on topclone.csv
        param_columns = []
        for n_val in TOP_N_VALUES:
            for chain in chains:
                param_columns.append(f"top{n_val}{chain}")

        if param_columns:
            param_begin = param_columns[0]
            param_over = param_columns[-1]
        else:
            param_begin = topclone_df.columns[0]
            param_over = topclone_df.columns[-1]

        boxplot_service = BoxPlotService(output_parent=output_base)
        boxplot_report = boxplot_service.generate_report(
            datapoint_path=str(topclone_csv),
            classification_begin=group_field or "",
            classification_over=group_field or "",
            param_begin=param_begin,
            param_over=param_over,
            group_order=group_order,
            pvalue_threshold=pvalue_threshold,
            output_name=output_name if output_name else None,
            progress_callback=lambda p, s, d, m=None: (
                progress_callback(60 + int(p * 0.35), s, d, m) if progress_callback else None
            ),
        )

        if progress_callback:
            progress_callback(
                100, "优势克隆分析完成",
                f"已纳入 {len(topclone_df)} 个匹配样本，生成 {len(boxplot_report.png_paths)} 张比较图和 CDR3 序列表。",
            )

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "mode": "trace",
            "pep_data_path": str(pep_data),
            "datapoint_path": str(datapoint),
            "profile_sheet": profile_sheet or "",
            "group_field": group_field or "",
            "batch_field": batch_field or "",
            "batch_count": int(profile_df[batch_field].nunique()) if batch_field else 1,
            "group_sample_identity": group_sample_identity,
            "chains": chains,
            "selected_chains": chains,
            "sample_count": len(topclone_df),
            "profile_sample_count": len(sample_list),
            "excluded_unmatched_sample_count": len(sample_list) - len(topclone_df),
            "category_cols": category_cols,
            "topclone_csv": str(topclone_csv),
            "top_clone_values": TOP_N_VALUES,
            "effect_heatmap_count": len(effect_heatmap_paths),
            "effect_statistics_count": len(effect_statistics_paths),
        }

        return TopCloneReport(
            job_id=job_id,
            output_base=output_base,
            topclone_csv_path=str(topclone_csv),
            boxplot_report=boxplot_report,
            per_sample_files=[],
            metadata=metadata,
            stats_csv_path=str(stats_csv),
            effect_heatmap_paths=effect_heatmap_paths,
            effect_statistics_paths=effect_statistics_paths,
        )

    @staticmethod
    def _generate_effect_heatmaps(
        *,
        topclone_df: pd.DataFrame,
        group_column: str,
        group_order: Optional[str],
        output_base: Path,
    ) -> tuple[List[str], List[str]]:
        if not group_column or group_column not in topclone_df.columns:
            return [], []

        chain_order = ("IGH", "IGK", "IGL", "TRA", "TRB", "TRG", "TRD")
        top_n_order = (10, 20, 50, 100)
        schema = {}
        for column in topclone_df.columns:
            match = re.fullmatch(r"top(\d+)(IGH|IGK|IGL|TRA|TRB|TRD|TRG)", str(column), re.IGNORECASE)
            if match:
                schema[(int(match.group(1)), match.group(2).upper())] = str(column)
        if not schema:
            return [], []

        sample_values = topclone_df.get("sample", pd.Series(index=topclone_df.index, dtype="string")).astype("string").str.strip()
        group_values = topclone_df[group_column].astype("string").str.strip()
        rows = []
        chains = [chain for chain in chain_order if any(schema_chain == chain for _, schema_chain in schema)]
        top_ns = [value for value in top_n_order if any(schema_n == value for schema_n, _ in schema)]
        for top_n in top_ns:
            for chain in chains:
                column = schema.get((top_n, chain))
                if column is None:
                    continue
                rows.append(pd.DataFrame({
                    "sample": sample_values,
                    "group": group_values,
                    "chain": chain,
                    "top_n": top_n,
                    "proportion": pd.to_numeric(topclone_df[column], errors="coerce"),
                }))
        if not rows:
            return [], []
        long_df = pd.concat(rows, ignore_index=True).dropna(subset=["sample", "group", "proportion"])
        long_df = long_df[long_df["group"].astype(str).str.len().gt(0)]
        if long_df.empty:
            return [], []

        observed_groups = long_df["group"].drop_duplicates().astype(str).tolist()
        requested_groups = [value.strip() for value in str(group_order or "").split(",") if value.strip()]
        groups = [value for value in requested_groups if value in observed_groups]
        groups.extend(value for value in observed_groups if value not in groups)
        if len(groups) < 2:
            return [], []

        comparisons = list(combinations(groups, 2))
        heatmap_paths: List[str] = []
        statistics_paths: List[str] = []
        all_stats: List[pd.DataFrame] = []
        for group1, group2 in comparisons:
            pair_rows = long_df[long_df["group"].isin([group1, group2])]
            stats_rows = []
            for (chain, top_n), subset in pair_rows.groupby(["chain", "top_n"], observed=True):
                first = subset.loc[subset["group"] == group1, "proportion"].dropna()
                second = subset.loc[subset["group"] == group2, "proportion"].dropna()
                if len(first) and len(second):
                    p_value = float(mannwhitneyu(first, second, alternative="two-sided").pvalue)
                    median_first = float(first.median())
                    median_second = float(second.median())
                    ratio = (median_first + 1e-6) / (median_second + 1e-6)
                else:
                    p_value = np.nan
                    median_first = float(first.median()) if len(first) else np.nan
                    median_second = float(second.median()) if len(second) else np.nan
                    ratio = np.nan
                stats_rows.append({
                    "chain": chain,
                    "top_n": int(top_n),
                    f"n_{group1}": int(len(first)),
                    f"n_{group2}": int(len(second)),
                    f"median_{group1}": median_first,
                    f"median_{group2}": median_second,
                    f"median_ratio_{group1}_over_{group2}": ratio,
                    "p_value": p_value,
                    "p_label": TopCloneService._pvalue_label(p_value),
                })
            if not stats_rows:
                continue
            stats_df = pd.DataFrame(stats_rows).sort_values(["chain", "top_n"])
            pair_dir = output_base if len(comparisons) == 1 else output_base / (
                TopCloneService._safe_effect_name(group1) + "_vs_" + TopCloneService._safe_effect_name(group2)
            )
            pair_dir.mkdir(parents=True, exist_ok=True)
            stats_path = pair_dir / "topclone_effect_heatmap_stats_raw_p.csv"
            stats_df.to_csv(stats_path, index=False, encoding="utf-8-sig")
            effect_path = pair_dir / "topclone_effect_heatmap_raw_p.png"
            TopCloneService._draw_effect_heatmap(stats_df, chains, top_ns, group1, group2, effect_path)
            statistics_paths.append(str(stats_path))
            if effect_path.is_file():
                heatmap_paths.append(str(effect_path))
            all_stats.append(stats_df.assign(group1=group1, group2=group2))

        if len(all_stats) > 1:
            all_stats_path = output_base / "topclone_effect_heatmap_stats_raw_p_all_pairs.csv"
            output_base.mkdir(parents=True, exist_ok=True)
            pd.concat(all_stats, ignore_index=True).to_csv(all_stats_path, index=False, encoding="utf-8-sig")
            statistics_paths.append(str(all_stats_path))
        return heatmap_paths, statistics_paths

    @staticmethod
    def _pvalue_label(value: float) -> str:
        if not np.isfinite(value):
            return "NA"
        if value <= 0.001:
            return "***"
        if value <= 0.01:
            return "**"
        if value <= 0.05:
            return "*"
        return "ns"

    @staticmethod
    def _safe_effect_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._") or "group"

    @staticmethod
    def _draw_effect_heatmap(
        stats: pd.DataFrame,
        chains: List[str],
        top_ns: List[int],
        group1: str,
        group2: str,
        output_path: Path,
    ) -> None:
        ratio_column = f"median_ratio_{group1}_over_{group2}"
        ratio = stats.pivot(index="chain", columns="top_n", values=ratio_column).reindex(index=chains, columns=top_ns)
        labels = stats.pivot(index="chain", columns="top_n", values="p_label").reindex(index=chains, columns=top_ns)
        ratio = ratio.dropna(axis=0, how="all").dropna(axis=1, how="all")
        labels = labels.reindex(index=ratio.index, columns=ratio.columns)
        if ratio.empty:
            return
        apply_publication_style(font_size=10)
        max_distance = float(np.nanmax(np.abs(ratio.to_numpy(dtype=float) - 1.0)))
        ratio_range = max(max_distance, 0.5)
        vmin, vmax = max(0.0, 1.0 - ratio_range), 1.0 + ratio_range
        fig, ax = plt.subplots(figsize=(6.8, 4.2))
        cmap = LinearSegmentedColormap.from_list("topclone_effect", ["#3D78A8", "#F6F6F1", "#B94E36"])
        sns.heatmap(
            ratio, ax=ax, cmap=cmap, center=1, vmin=vmin, vmax=vmax,
            linewidths=0.8, linecolor="white", annot=labels, fmt="",
            annot_kws={"fontsize": 11, "fontweight": "bold"},
            cbar_kws={"label": f"中位数比值（{group1} / {group2}）"},
        )
        ax.set_title(f"优势克隆比例：{group1} / {group2}", fontsize=13, fontweight="bold", pad=10)
        ax.set_xlabel("Top N")
        ax.set_ylabel("链型")
        ax.set_xticklabels([f"Top {int(value)}" for value in ratio.columns], rotation=0)
        ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
        fig.subplots_adjust(bottom=0.23)
        fig.text(0.5, 0.025, "双侧 Mann–Whitney U 检验，原始 p 值；* p≤0.05，** p≤0.01，*** p≤0.001，ns：不显著。", ha="center", va="bottom", fontsize=8)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=600, bbox_inches="tight", pad_inches=0.04, facecolor="white")
        plt.close(fig)

    @staticmethod
    def _compute_pairwise_statistics(
        topclone_df: pd.DataFrame,
        group_column: str,
        group_order: Optional[str],
    ) -> pd.DataFrame:
        columns = ["chain", "top_n", "group1", "group2", "n1", "n2", "p_value", "q_value"]
        if not group_column or group_column not in topclone_df.columns:
            return pd.DataFrame(columns=columns)

        group_series = topclone_df[group_column].astype("string")
        observed = group_series.dropna().loc[lambda values: values.str.len().gt(0)].unique().tolist()
        requested = [value.strip() for value in str(group_order or "").split(",") if value.strip()]
        groups = [value for value in requested if value in observed]
        groups.extend(value for value in observed if value not in groups)

        metric_columns = [
            (column, int(match.group(1)), match.group(2).upper())
            for column in topclone_df.columns
            if (match := re.fullmatch(r"top(\d+)(IGH|IGK|IGL|TRA|TRB|TRD|TRG)", str(column), re.IGNORECASE))
        ]
        records: List[Dict[str, Any]] = []
        for column, top_n, chain in metric_columns:
            numeric = pd.to_numeric(topclone_df[column], errors="raise")
            if ((numeric.dropna() < 0) | (numeric.dropna() > 1)).any():
                raise ValueError(f"{column} 的克隆比例必须在 0 到 1 之间。")
            arrays = {
                group: numeric[group_series.eq(group).fillna(False)].dropna().to_numpy(dtype=float)
                for group in groups
            }
            if not any(len(values) for values in arrays.values()):
                continue
            for group1, group2 in combinations(groups, 2):
                first, second = arrays[group1], arrays[group2]
                p_value = (
                    float(mannwhitneyu(first, second, alternative="two-sided").pvalue)
                    if len(first) and len(second) else np.nan
                )
                records.append({
                    "chain": chain, "top_n": top_n, "group1": group1, "group2": group2,
                    "n1": len(first), "n2": len(second), "p_value": p_value, "q_value": np.nan,
                })

        result = pd.DataFrame(records, columns=columns)
        if result.empty:
            return result
        finite = np.flatnonzero(np.isfinite(result["p_value"].to_numpy(dtype=float)))
        if finite.size:
            order = finite[np.argsort(result.loc[finite, "p_value"].to_numpy(dtype=float), kind="stable")]
            ranked = result.loc[order, "p_value"].to_numpy(dtype=float)
            adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1, dtype=float)
            adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
            result.loc[order, "q_value"] = np.clip(adjusted, 0.0, 1.0)
        return result.sort_values(["chain", "top_n"], kind="stable").reset_index(drop=True)

    # ------------------------------------------------------------------
    # Per-sample mode: extract raw top-N rows from each PEP file
    # ------------------------------------------------------------------
    def _run_per_sample_mode(
        self,
        *,
        pep_data: Path,
        output_base: Path,
        job_id: str,
        top_n: int,
        profile_df: Optional[pd.DataFrame],
        batch_values: set[str],
        batch_field: Optional[str],
        chain_files: Dict[str, List[Path]],
        group_sample_identity: str,
        selected_chains: Optional[List[str]],
        progress_callback,
    ) -> TopCloneReport:
        chain_files = self._filter_chain_files(chain_files, selected_chains)
        if not chain_files:
            raise ValueError("No selected chain CSV files found in pep_data path")

        selected_keys = None
        if profile_df is not None:
            selected_keys = (set(profile_df[["sample", batch_field]].itertuples(index=False, name=None))
                             if batch_field else {(sample, "") for sample in profile_df["sample"]})
        file_batches = {}
        seen = set()
        filtered = {}
        for chain, files in chain_files.items():
            for file in files:
                sample = self._parse_sample_name(file, chain) or file.stem
                batch = self._batch_for_file(file, pep_data, batch_values) if batch_field else None
                if selected_keys is not None and (sample, batch or "") not in selected_keys:
                    continue
                key = (sample, batch or "", chain)
                if key in seen:
                    raise ValueError(f"克隆数据中样本、批次与链型组合重复：{sample} / {batch or '未指定批次'} / {chain}")
                seen.add(key)
                file_batches[file] = batch
                filtered.setdefault(chain, []).append(file)
        chain_files = filtered
        if not chain_files:
            raise ValueError("筛选后没有匹配的克隆数据，请检查批次目录名、样本编号和链型。")

        output_columns = ["index", "Chain", "CDR3(pep)", "joinedSeq", "V", "D", "J", "C", "copy"]
        input_columns = ["CDR3(pep)", "joinedSeq", "V", "D", "J", "C", "copy"]

        top_clones_root = output_base / "top_clones"
        top_clones_root.mkdir(parents=True, exist_ok=True)

        per_sample_files: List[str] = []
        summary_rows = []
        total = sum(len(files) for files in chain_files.values())
        step = 0

        for chain, files in chain_files.items():
            chain_out = top_clones_root / chain
            chain_out.mkdir(parents=True, exist_ok=True)

            for file_path in files:
                sample = self._parse_sample_name(file_path, chain) or Path(file_path.name).stem
                try:
                    df = _try_read_csv(file_path, low_memory=False)
                    missing = [c for c in input_columns if c not in df.columns]
                    if missing:
                        logger.debug("Skipping %s: missing columns %s", file_path, missing)
                        continue

                    out = pd.DataFrame(index=df.index)
                    out["Chain"] = chain
                    out["CDR3(pep)"] = df["CDR3(pep)"].fillna("").astype(str).str.strip()
                    for field in ["joinedSeq", "V", "D", "J", "C"]:
                        out[field] = (
                            df[field].fillna("").astype(str).str.strip()
                            if field in df.columns else ""
                        )
                    copy_series = (
                        df["copy"].fillna("").astype(str)
                        .str.replace(",", "", regex=False).str.strip()
                    )
                    out["copy"] = pd.to_numeric(copy_series, errors="coerce")
                    out = out.dropna(subset=["copy"])
                    out = out[out["CDR3(pep)"] != ""]
                    out = out.sort_values(by=["copy", "CDR3(pep)"], ascending=[False, True])
                    out = out.head(top_n).reset_index(drop=True)
                    out.insert(0, "index", range(1, len(out) + 1))
                    out = out[[c for c in output_columns if c in out.columns]]

                    batch = file_batches[file_path]
                    # An encoded batch prefix separates same-ID samples without using batch values as paths.
                    filename = f"{_batch_sample_identity(batch, sample)}_top{top_n}.csv" if batch_field else f"{sample}_top{top_n}.csv"
                    filename = filename.replace("/", "%2F").replace("\\", "%5C").replace(":", "%3A")
                    out_file = chain_out / filename
                    out.to_csv(out_file, index=False)
                    per_sample_files.append(str(out_file))
                    summary_rows.append({"chain": chain, "sample": sample, "file": str(out_file),
                                         **({batch_field: batch} if batch_field else {})})
                except Exception as exc:
                    logger.warning("Failed per-sample extraction for %s: %s", file_path, exc)

                step += 1
                if progress_callback and step % max(1, total // 10) == 0:
                    progress_callback(
                        5 + int(step / max(total, 1) * 90),
                        "优势克隆提取",
                        f"正在提取样本 {sample} / {chain}（{step}/{total}）。",
                    )

        if progress_callback:
            progress_callback(
                100, "优势克隆提取",
                f"已生成 {len(per_sample_files)} 个单样本结果文件。",
            )

        # Build summary
        summary_csv = top_clones_root / "summary.csv"
        if not summary_rows:
            raise ValueError("所选克隆数据未生成有效结果，请检查必需列和数据内容。")
        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_csv(summary_csv, index=False)

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "mode": "per_sample",
            "batch_field": batch_field or "",
            "group_sample_identity": group_sample_identity,
            "pep_data_path": str(pep_data),
            "top_n": top_n,
            "chains": sorted(chain_files.keys()),
            "selected_chains": sorted(chain_files.keys()),
            "file_count": len(per_sample_files),
            "top_clone_values": [top_n],
            "sample_count": len(summary_df[["sample"] + ([batch_field] if batch_field else [])].drop_duplicates()),
            **({"profile_sample_count": len(profile_df),
                "excluded_unmatched_sample_count": len(profile_df) - len(summary_df[["sample"] + ([batch_field] if batch_field else [])].drop_duplicates())}
               if profile_df is not None else {}),
        }

        return TopCloneReport(
            job_id=job_id,
            output_base=output_base,
            topclone_csv_path=None,
            boxplot_report=None,
            per_sample_files=per_sample_files,
            metadata=metadata,
        )

    @staticmethod
    def _allocate_job_id(name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{name}_{ts}"
