"""
Pep CDR3 Sharing Analysis service.
Implements steps 2-8 of the Pep_260213 pipeline:
  Step 2: CDR3 sharing matrix + V/J/VJ usage matrices
  Step 3: Add profile group category to shared matrices
  Step 4: Add profile group category to usage matrices
  Step 5: Differential usage heatmaps
  Step 6: CDR3 classification statistics
  Step 7: CDR3 arrangement heatmaps
  Step 8: Unique CDR3 heatmaps and summary heatmap
"""

from __future__ import annotations

import csv
import heapq
import json
import logging
import os
import re
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import mannwhitneyu

logger = logging.getLogger(__name__)

from flask_app.services.figure_style import (
    MUTED_BLUE_RED_CMAP,
    MUTED_DIVERGING_CMAP,
    apply_publication_style,
    save_publication_png,
)

# Encoding fallback for CSV/TSV files (GBK common in Chinese Windows environments)
_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]

apply_publication_style(font_size=9, axes_linewidth=0.85)
_PLOT_LOCK = threading.Lock()
REFERENCE_CATEGORY_ORDER = ["before", "after"]
REFERENCE_STEP8_SECTION_CATEGORIES = [("T1DM__count", "T1DM unique")]
PEP_MAX_ARRANGE_HEATMAP_ROWS = 3000
PEP_STEP_SCRIPTS = {
    1: ("step1_move_file", "1.move_file.ipynb"),
    2: ("step2_pep_shared", "2.Pep_shared.py"),
    3: ("step3_add_cate_shared", "3.add_cate_shared.py"),
    4: ("step4_add_cate_usage", "4.add_cate_usage.py"),
    5: ("step5_heatmap", "5.Heat_map_Thread.py"),
    6: ("step6_pep_statistication", "6.Pep_statistication.py"),
    7: ("step7_cdr3_arrage_heatmap", "7.CDR3_arrage_heatmap_ver1.0.py"),
    8: ("step8_unique_cdr3_heatmap", "8.plot_heatmap.py"),
}
PEP_GROUP_STEP_FRACTIONS = {
    3: (0.00, 0.13),
    4: (0.13, 0.27),
    5: (0.27, 0.62),
    6: (0.62, 0.81),
    7: (0.81, 0.92),
    8: (0.92, 1.00),
}

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


SUPPORTED_CHAINS = {"IGH", "IGK", "IGL", "TRA", "TRB", "TRD", "TRG"}


def _strip_table_suffix(filename: str) -> str:
    name = str(filename or "")
    lowered = name.lower()
    for suffix in (".csv.gz", ".tsv.gz", ".csv", ".tsv", ".txt"):
        if lowered.endswith(suffix):
            return name[:-len(suffix)]
    return Path(name).stem


def _infer_chain_from_path(path: Path) -> str:
    stem = _strip_table_suffix(path.name).upper()
    for chain in sorted(SUPPORTED_CHAINS, key=len, reverse=True):
        if (
            stem.endswith(f"__{chain}")
            or stem.endswith(f"_{chain}")
            or stem.endswith(f"-{chain}")
            or path.parent.name.upper() == chain
        ):
            return chain
    return ""


def _pep_sample_name_from_path(path: Path, chain: str) -> str:
    stem = _strip_table_suffix(path.name)
    for suffix in (f"__{chain}", f"_{chain}", f"-{chain}"):
        if stem.upper().endswith(suffix.upper()):
            return stem[:-len(suffix)]
    return stem


def _sample_match_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\.(csv|tsv|txt|gz|xlsx?)$", "", text)
    text = re.sub(r"(__|-|_)?(tra|trb|trg|trd|igh|igk|igl)$", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def _is_table_file(path: Path) -> bool:
    return path.name.lower().endswith((".csv", ".csv.gz", ".tsv", ".tsv.gz"))


def _reference_numeric_sort_key(value: Any) -> List[float]:
    numbers = re.findall(r"[1-9]+\.?[0-9]*", str(value or ""))
    if not numbers:
        return [float("inf")]
    return [float(item) for item in numbers]


def _reference_heatmap_column_order(columns: List[str]) -> List[str]:
    ordered = list(columns)
    for i in range(1, len(ordered)):
        for k in range(0, len(ordered) - i):
            numbers_pre = np.array(re.findall(r"[1-9]+\.?[0-9]*", ordered[k]), dtype=np.float16).tolist()
            numbers_behind = np.array(re.findall(r"[1-9]+\.?[0-9]*", ordered[k + 1]), dtype=np.float16).tolist()
            n1, n2 = len(numbers_pre), len(numbers_behind)
            minlen = int(np.min(np.array([n1, n2]))) if max(n1, n2) else 0
            maxlen_flag = n1 > minlen
            for j in range(minlen):
                if numbers_pre[j] != numbers_behind[j]:
                    if numbers_pre[j] > numbers_behind[j]:
                        ordered[k], ordered[k + 1] = ordered[k + 1], ordered[k]
                    break
                if j == minlen - 1 and maxlen_flag:
                    ordered[k], ordered[k + 1] = ordered[k + 1], ordered[k]
    return ordered


def _reference_category_order(values: List[Any], preferred: Optional[List[str]] = None) -> List[str]:
    categories = sorted([str(v) for v in values if str(v) not in {"", "0", "nan"}])
    index_sorted = list(preferred or REFERENCE_CATEGORY_ORDER)
    index_sorted.reverse()
    if index_sorted:
        for cate in index_sorted:
            if cate in categories:
                categories.remove(cate)
                categories.insert(0, cate)
    categories.reverse()
    return categories


def _reference_step8_cmap():
    return LinearSegmentedColormap.from_list(
        "nature_blue_yellow_red",
        ["#235AA6", "#F3E8A3", "#CF2B24"],
    )


@dataclass
class PepAnalysisReport:
    job_id: str
    output_base: Path
    shared_matrix_paths: List[str]
    usage_paths: List[str]
    heatmap_image_paths: List[str]
    heatmap_csv_paths: List[str]
    classification_paths: List[str]
    proportion_paths: List[str]
    proportion_plot_paths: List[str]
    arrange_heatmap_paths: List[str]
    plot_heatmap_paths: List[str]
    zip_path: str
    metadata: Dict[str, Any]


class PepAnalysisService:
    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    def generate_report(
        self,
        *,
        pep_data_dir: str,
        profile_path: str,
        group_fields: List[str],
        selected_chains: List[str],
        pvalue_threshold: float = 0.05,
        min_sample_threshold: int = 3,
        output_name: Optional[str] = None,
        optional_steps: Optional[set] = None,
        selected_samples: Optional[List[str]] = None,
        project_id: Optional[str] = None,
        progress_callback=None,
    ) -> PepAnalysisReport:
        pep_dir = Path(pep_data_dir)
        if not pep_dir.exists():
            raise FileNotFoundError(f"Pep data directory not found: {pep_data_dir}")

        profile_file = Path(profile_path)
        if not profile_file.exists():
            raise FileNotFoundError(f"Profile file not found: {profile_path}")

        profile_df = _try_read_csv(profile_file, low_memory=False)
        profile_df.fillna(0, inplace=True)
        selected_sample_keys = {
            _sample_match_key(sample)
            for sample in (selected_samples or [])
            if _sample_match_key(sample)
        }
        if selected_sample_keys and not profile_df.empty:
            sample_col = profile_df.columns[0]
            profile_df = profile_df[
                profile_df[sample_col].map(_sample_match_key).isin(selected_sample_keys)
            ].copy()
            if profile_df.empty:
                raise ValueError("No Profile rows matched the selected Pep Analysis samples")

        for gf in group_fields:
            if gf not in profile_df.columns:
                raise ValueError(f"Group field '{gf}' not found in profile columns: {profile_df.columns.tolist()}")

        chains = [c.upper() for c in selected_chains if c.upper() in SUPPORTED_CHAINS]
        if not chains:
            raise ValueError("No supported chains selected")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name or "pep_analysis")
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        group_index = {field: index for index, field in enumerate(group_fields)}
        group_span = 63.0 / max(len(group_fields), 1)
        last_progress = [0.0]

        def _step_int(meta: Dict[str, Any]) -> Optional[int]:
            raw_step = meta.get("step")
            if isinstance(raw_step, int):
                return raw_step
            text = str(raw_step or "").strip()
            return int(text) if text.isdigit() else None

        def _progress_fraction(meta: Dict[str, Any]) -> float:
            try:
                processed = float(meta.get("processed", 0))
                total = float(meta.get("total", 0))
            except (TypeError, ValueError):
                return 0.0
            if total <= 0:
                return 0.0
            return max(0.0, min(1.0, processed / total))

        def _weighted_pct(meta: Dict[str, Any], fallback: float) -> float:
            if meta.get("absolute_pct"):
                return fallback
            step = _step_int(meta)
            fraction = _progress_fraction(meta)
            if step == 1:
                return 1.0 + 4.0 * fraction
            if step == 2:
                return 5.0 + 30.0 * fraction
            if step in PEP_GROUP_STEP_FRACTIONS:
                gf = str(meta.get("group_field") or group_fields[0] if group_fields else "").strip()
                idx = group_index.get(gf, 0)
                start_frac, end_frac = PEP_GROUP_STEP_FRACTIONS[step]
                return 35.0 + idx * group_span + group_span * (
                    start_frac + (end_frac - start_frac) * fraction
                )
            return fallback

        def _enrich_meta(meta: Optional[Dict]) -> Dict[str, Any]:
            clean_meta = dict(meta or {})
            step = _step_int(clean_meta)
            if step in PEP_STEP_SCRIPTS:
                step_key, script = PEP_STEP_SCRIPTS[step]
                clean_meta.setdefault("step_key", step_key)
                clean_meta.setdefault("script", script)
            clean_meta.setdefault("module", "pep-analysis")
            return clean_meta

        def _emit(pct: float, msg: str, meta: Optional[Dict] = None):
            clean_meta = _enrich_meta(meta)
            weighted = _weighted_pct(clean_meta, pct)
            if weighted < 100:
                weighted = min(weighted, 98.0)
            weighted = max(last_progress[0], weighted)
            last_progress[0] = weighted
            if progress_callback:
                progress_callback(weighted, "Pep Analysis", msg, clean_meta)

        def _progress(msg: str, meta: Optional[Dict] = None):
            fallback = min(last_progress[0] + 0.5, 98.0)
            _emit(fallback, msg, meta)

        def _status(pct: float, msg: str, meta: Optional[Dict] = None):
            _emit(pct, msg, meta)

        # ---- Step 2: CDR3 sharing analysis (per chain, GROUP-INDEPENDENT) ----
        _status(
            1,
            "Step 1: Preparing PEP inputs (1.move_file.ipynb equivalent)",
            {"step": 1, "stage": "step1_prepare_inputs", "processed": 0, "total": 1},
        )
        _status(
            5,
            "Step 1: Input validation complete",
            {"step": 1, "stage": "step1_prepare_inputs", "processed": 1, "total": 1},
        )
        _progress(
            "Step 2: Scanning pep files by chain",
            {"step": 2, "stage": "step2_scan_pep_files", "processed": 0, "total": max(len(chains), 1)},
        )
        chain_files: Dict[str, List[str]] = {chain: [] for chain in chains}
        for file_path in sorted(path for path in pep_dir.rglob("*") if path.is_file() and _is_table_file(path)):
            chain = _infer_chain_from_path(file_path)
            if chain in chains:
                if selected_sample_keys:
                    sample_name = _pep_sample_name_from_path(file_path, chain)
                    if _sample_match_key(sample_name) not in selected_sample_keys:
                        continue
                chain_files.setdefault(chain, []).append(str(file_path))
        if selected_sample_keys:
            _status(
                12,
                f"Step 2: selected sample filter kept {sum(len(items) for items in chain_files.values())} pep files",
                {
                    "step": 2,
                    "stage": "step2_filter_selected_samples",
                    "selected_sample_count": len(selected_sample_keys),
                    "chain_file_counts": {chain: len(chain_files.get(chain, [])) for chain in chains},
                },
            )

        shared_matrix_paths: List[str] = []
        usage_paths: List[str] = []

        for chain in chains:
            files = chain_files.get(chain, [])
            if not files:
                continue
            _progress(
                f"Step 2: CDR3 sharing for {chain} ({len(files)} files)",
                {
                    "step": 2,
                    "stage": "step2_read_files",
                    "chain": chain,
                    "processed": chains.index(chain),
                    "total": max(len(chains), 1),
                },
            )

            def _step2_progress(
                processed: int,
                total: int,
                current_file: str,
                chain_name: str = chain,
                phase: str = "reading",
                label: str = "",
            ):
                chain_index = chains.index(chain_name)
                chain_span = 28.0 / max(len(chains), 1)
                base_pct = 8.0 + chain_index * chain_span
                pct = min(base_pct + chain_span * (processed / max(total, 1)), 36.0)
                if phase != "reading":
                    pct = min(base_pct + chain_span * 0.92 + chain_span * 0.08 * (processed / max(total, 1)), 36.0)
                detail = (
                    f"Step 2 [{chain_name}]: processed {processed}/{total} files"
                    if phase == "reading"
                    else f"Step 2 [{chain_name}]: {label or phase}"
                )
                _status(
                    pct,
                    detail,
                    {
                        "step": 2,
                        "chain": chain_name,
                        "stage": f"step2_{phase}",
                        "phase": phase,
                        "processed": processed,
                        "total": total,
                        "current_file": current_file,
                        "label": label,
                        "absolute_pct": True,
                    },
                )

            sh_paths, us_paths = self._run_cdr3_sharing(
                chain,
                files,
                output_base,
                progress_callback=_step2_progress,
            )
            shared_matrix_paths.extend(sh_paths)
            usage_paths.extend(us_paths)

        # ---- Which optional steps to run? ----
        requested_optional = {5, 6, 7, 8} if optional_steps is None else set(optional_steps)
        requested_optional = {step for step in requested_optional if step in {5, 6, 7, 8}}
        run_optional = set(requested_optional)
        if 7 in run_optional or 8 in run_optional:
            # Steps 7/8 read Step 6's arrage_pep outputs, so Step 6 is a dependency.
            run_optional.add(6)

        # ---- Steps 3-7: Per group field ----
        heatmap_image_paths: List[str] = []
        heatmap_csv_paths: List[str] = []
        classification_paths: List[str] = []
        proportion_paths: List[str] = []
        proportion_plot_paths: List[str] = []
        arrange_heatmap_paths: List[str] = []
        plot_heatmap_paths: List[str] = []
        all_optional_step_errors: List[Dict[str, Any]] = []

        from concurrent.futures import ThreadPoolExecutor, as_completed

        for gf in group_fields:
            field_dir = output_base / gf
            field_dir.mkdir(parents=True, exist_ok=True)

            shared_dir = output_base / "Pep_shared"
            usage_dir = output_base / "usage"
            pep_shared_cate_dir = field_dir / "Pep_shared_cate" / "Pep_shared"
            pep_shared_cate_dir.mkdir(parents=True, exist_ok=True)
            usage_cate_base = field_dir / "usage_cate" / "usage"
            usage_cate_base.mkdir(parents=True, exist_ok=True)

            # ---- Steps 3+4: Add category annotations (mandatory) ----
            _progress(f"Step 3+4 [{gf}]: Adding categories", {"step": "3+4", "group_field": gf})

            def _run_step3():
                """Step 3: Add category to shared CDR3"""
                existing = [chain for chain in chains if (shared_dir / f"{chain}.csv").exists()]
                total = max(len(existing), 1)
                for idx, chain in enumerate(existing, start=1):
                    src = shared_dir / f"{chain}.csv"
                    _progress(
                        f"Step 3 [{gf}]: annotating Pep_shared {idx}/{total} ({chain})",
                        {"step": 3, "group_field": gf, "chain": chain, "processed": idx - 1, "total": total},
                    )
                    self._add_cate_shared(src, pep_shared_cate_dir / f"{chain}.csv", profile_df, gf)
                    _progress(
                        f"Step 3 [{gf}]: annotated Pep_shared {idx}/{total} ({chain})",
                        {"step": 3, "group_field": gf, "chain": chain, "processed": idx, "total": total},
                    )

            def _run_step4():
                """Step 4: Add category to usage"""
                tasks: List[Tuple[str, str, Path, Path]] = []
                for usage_type in ["0Vusage", "1Vusage", "0Jusage", "1Jusage", "0VJusage", "1VJusage"]:
                    src_usage_dir = usage_dir / usage_type
                    dst_usage_dir = usage_cate_base / usage_type
                    if src_usage_dir.exists():
                        dst_usage_dir.mkdir(parents=True, exist_ok=True)
                        for chain in chains:
                            src = src_usage_dir / f"{chain}.csv"
                            if src.exists():
                                tasks.append((usage_type, chain, src, dst_usage_dir / f"{chain}.csv"))
                total = max(len(tasks), 1)
                for idx, (usage_type, chain, src, dst) in enumerate(tasks, start=1):
                    _progress(
                        f"Step 4 [{gf}]: annotating usage {idx}/{total} ({usage_type}/{chain})",
                        {
                            "step": 4,
                            "group_field": gf,
                            "usage_type": usage_type,
                            "chain": chain,
                            "processed": idx - 1,
                            "total": total,
                        },
                    )
                    self._add_cate_usage(src, dst, profile_df, gf)
                    _progress(
                        f"Step 4 [{gf}]: annotated usage {idx}/{total} ({usage_type}/{chain})",
                        {
                            "step": 4,
                            "group_field": gf,
                            "usage_type": usage_type,
                            "chain": chain,
                            "processed": idx,
                            "total": total,
                        },
                    )

            # Run steps 3 and 4 in parallel
            with ThreadPoolExecutor(max_workers=2) as step34_executor:
                futures = {
                    step34_executor.submit(_run_step3): "step3",
                    step34_executor.submit(_run_step4): "step4",
                }
                for future in as_completed(futures):
                    step_label = futures[future]
                    try:
                        future.result()
                    except Exception as exc:
                        raise RuntimeError(f"Step {step_label} failed for [{gf}]: {exc}") from exc

            _progress(f"Step 3+4 [{gf}]: Category annotation complete", {"step": "3+4", "group_field": gf})

            # ---- Optional Steps 5-8: 并行执行 (user-selectable) ----
            optional_task_results: Dict[int, Any] = {}
            optional_step_errors: List[Dict[str, Any]] = []
            optional_tasks = {}

            if 5 in run_optional:
                optional_tasks[5] = lambda: self._run_step5_for_group(
                    chains, usage_cate_base, field_dir, pvalue_threshold,
                    progress_callback=lambda message, meta=None: _status(
                        last_progress[0],
                        f"Step 5 [{gf}]: {message}",
                        {"step": 5, "group_field": gf, "stage": "step5_heatmap", **(meta or {})},
                    ),
                )
            if 6 in run_optional:
                optional_tasks[6] = lambda: self._run_step6_for_group(
                    chains, pep_shared_cate_dir, field_dir, min_sample_threshold,
                    progress_callback=lambda message, meta=None: _status(
                        last_progress[0],
                        f"Step 6 [{gf}]: {message}",
                        {"step": 6, "group_field": gf, "stage": "step6_pep_statistication", **(meta or {})},
                    ),
                )

            if optional_tasks:
                _progress(f"Steps {sorted(optional_tasks.keys())} [{gf}]: Running selected optional steps",
                          {"step": "optional", "group_field": gf, "optional_steps": sorted(optional_tasks.keys())})
                with ThreadPoolExecutor(max_workers=min(len(optional_tasks), 2)) as opt_executor:
                    opt_futures = {
                        opt_executor.submit(fn): step_num
                        for step_num, fn in optional_tasks.items()
                    }
                    for future in as_completed(opt_futures):
                        step_num = opt_futures[future]
                        try:
                            result = future.result()
                            optional_task_results[step_num] = result
                        except Exception as exc:
                            _progress(f"Step {step_num} [{gf}]: failed — {exc}",
                                      {"step": step_num, "group_field": gf, "error": str(exc)})
                            optional_step_errors.append({
                                "group_field": gf,
                                "step": step_num,
                                "error": str(exc),
                            })

            dependent_tasks = {}
            if 7 in run_optional:
                dependent_tasks[7] = lambda: self._run_step7_for_group(
                    chains,
                    field_dir,
                    progress_callback=lambda message, meta=None: _status(
                        last_progress[0],
                        f"Step 7 [{gf}]: {message}",
                        {"step": 7, "group_field": gf, "stage": "step7_cdr3_arrage_heatmap", **(meta or {})},
                    ),
                )
            if 8 in run_optional:
                dependent_tasks[8] = lambda: self._run_step8_for_group(
                    chains,
                    field_dir,
                    progress_callback=lambda message, meta=None: _status(
                        last_progress[0],
                        f"Step 8 [{gf}]: {message}",
                        {"step": 8, "group_field": gf, "stage": "step8_unique_cdr3_heatmap", **(meta or {})},
                    ),
                )

            if dependent_tasks:
                _progress(f"Steps {sorted(dependent_tasks.keys())} [{gf}]: Running after Step 6 dependency",
                          {"step": "optional-dependent", "group_field": gf, "optional_steps": sorted(dependent_tasks.keys())})
                with ThreadPoolExecutor(max_workers=min(len(dependent_tasks), 2)) as dep_executor:
                    dep_futures = {
                        dep_executor.submit(fn): step_num
                        for step_num, fn in dependent_tasks.items()
                    }
                    for future in as_completed(dep_futures):
                        step_num = dep_futures[future]
                        try:
                            result = future.result()
                            optional_task_results[step_num] = result
                            _progress(
                                f"Step {step_num} [{gf}]: completed",
                                {"step": step_num, "group_field": gf},
                            )
                        except Exception as exc:
                            _progress(f"Step {step_num} [{gf}]: failed — {exc}",
                                      {"step": step_num, "group_field": gf, "error": str(exc)})
                            optional_step_errors.append({
                                "group_field": gf,
                                "step": step_num,
                                "error": str(exc),
                            })

            # Collect optional step results
            if 5 in optional_task_results:
                h_imgs, h_csvs = optional_task_results[5]
                heatmap_image_paths.extend(h_imgs)
                heatmap_csv_paths.extend(h_csvs)
            if 6 in optional_task_results:
                arr_paths, prp_paths, prp_plot_paths = optional_task_results[6]
                classification_paths.extend(arr_paths)
                proportion_paths.extend(prp_paths)
                proportion_plot_paths.extend(prp_plot_paths)
            if 7 in optional_task_results:
                arrange_heatmap_paths.extend(optional_task_results[7])
            if 8 in optional_task_results:
                plot_heatmap_paths.extend(optional_task_results[8])

            if optional_step_errors:
                all_optional_step_errors.extend(optional_step_errors)
                for err in optional_step_errors:
                    _progress(
                        f"Optional step {err['step']} [{err['group_field']}] failed: {err['error']}",
                        {"step": err["step"], "group_field": err["group_field"], "error": err["error"]},
                    )

        combined_source = (
            output_base / group_fields[0] / "usage_cate" / "usage" / "1VJusage"
            if group_fields else output_base / "usage" / "1VJusage"
        )
        df_vj_all_path = self._write_combined_usage(combined_source, output_base / "usage" / "df_VJ_all.csv")
        df_1vj_all_path = self._write_combined_usage(combined_source, output_base / "usage" / "df_1VJusage_all.csv")
        for combined_path in (df_vj_all_path, df_1vj_all_path):
            if combined_path and str(combined_path) not in usage_paths:
                usage_paths.append(str(combined_path))

        step_output_counts = {
            1: {
                "input_paths": sum(len(items) for items in chain_files.values()),
                "profile_files": 1 if profile_file.exists() else 0,
            },
            2: {
                "shared_csv": len(shared_matrix_paths),
                "usage_csv": len(usage_paths),
            },
            3: {
                "shared_cate_csv": len([
                    path for gf in group_fields
                    for path in (output_base / gf / "Pep_shared_cate" / "Pep_shared").glob("*.csv")
                ]),
            },
            4: {
                "usage_cate_csv": len([
                    path for gf in group_fields
                    for path in (output_base / gf / "usage_cate" / "usage").rglob("*.csv")
                ]),
            },
            5: {
                "heatmap_images": len(heatmap_image_paths),
                "heatmap_csv": len(heatmap_csv_paths),
            },
            6: {
                "classification_csv": len(classification_paths),
                "proportion_csv": len(proportion_paths),
                "proportion_images": len(proportion_plot_paths),
            },
            7: {
                "arrange_heatmap_images": len(arrange_heatmap_paths),
            },
            8: {
                "unique_cdr3_heatmap_images": len(plot_heatmap_paths),
            },
        }

        step_skip_reasons: Dict[int, str] = {}
        for optional_step in (5, 6, 7, 8):
            if optional_step not in run_optional:
                step_skip_reasons[optional_step] = "Step was not selected in optional_steps."
        if 5 in run_optional and not any(step_output_counts[5].values()):
            step_skip_reasons[5] = "No categorized usage CSV files were available for Step 5 heatmaps."
        if 6 in run_optional and not any(step_output_counts[6].values()):
            step_skip_reasons[6] = "No categorized Pep_shared CSV files were available for Step 6 statistics."
        if 7 in run_optional and not any(step_output_counts[7].values()):
            step_skip_reasons[7] = "No Step 6 arrage_pep CSV outputs were available for Step 7 heatmaps."
        if 8 in run_optional and not any(step_output_counts[8].values()):
            step_skip_reasons[8] = "No Step 6 arrage_pep CSV outputs were available for Step 8 heatmaps."
        step_summary = [
            {
                "step": step,
                "step_key": PEP_STEP_SCRIPTS[step][0],
                "script": PEP_STEP_SCRIPTS[step][1],
                "status": "completed" if any(step_output_counts.get(step, {}).values()) or step in {1, 2, 3, 4} else "skipped",
                "mode": "asset" if step == 1 else ("required" if step in {2, 3, 4} else "optional"),
                "skip_reason": step_skip_reasons.get(step, ""),
                "output_counts": step_output_counts.get(step, {}),
                "errors": [err for err in all_optional_step_errors if err.get("step") == step],
            }
            for step in range(1, 9)
        ]

        # ---- Generate ZIP ----
        zip_path = output_base / "pep_analysis_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in shared_matrix_paths + usage_paths + heatmap_image_paths + \
                     heatmap_csv_paths + classification_paths + proportion_paths + \
                     proportion_plot_paths + arrange_heatmap_paths + plot_heatmap_paths:
                fp = Path(p)
                if fp.exists():
                    arcname = str(fp.relative_to(output_base))
                    zf.write(fp, arcname)

        generated_at = datetime.now().isoformat()
        profile_sample_col = profile_df.columns[0] if len(profile_df.columns) else ""
        sample_list = (
            profile_df[profile_sample_col].dropna().astype(str).tolist()
            if profile_sample_col else sorted(selected_sample_keys)
        )
        output_files = {
            "pep_shared": {
                chain: str(output_base / "Pep_shared" / f"{chain}.csv")
                for chain in chains
                if (output_base / "Pep_shared" / f"{chain}.csv").exists()
            },
            "usage_types": {
                usage_type: str(output_base / "usage" / usage_type)
                for usage_type in ["0Vusage", "1Vusage", "0Jusage", "1Jusage", "0VJusage", "1VJusage"]
                if (output_base / "usage" / usage_type).exists()
            },
            "umapin_tables": {
                "df_VJ_all": str(df_vj_all_path) if df_vj_all_path else "",
                "df_1VJusage_all": str(df_1vj_all_path) if df_1vj_all_path else "",
            },
            "group_dirs": {
                gf: {
                    "pep_shared_cate": str(output_base / gf / "Pep_shared_cate" / "Pep_shared"),
                    "usage_cate": str(output_base / gf / "usage_cate" / "usage"),
                    "arrage_pep": str(output_base / gf / "arrage_pep" / "Pep_shared_cate" / "Pep_shared"),
                    "plot_heatmap": str(output_base / gf / "plot_heatmap"),
                }
                for gf in group_fields
            },
        }
        has_vj_usage = any(
            Path(path).exists()
            for key, path in output_files["usage_types"].items()
            if "VJ" in key.upper()
        ) or bool(df_vj_all_path or df_1vj_all_path)
        has_tra = bool(output_files["pep_shared"].get("TRA"))
        image_files = (
            self._build_pep_image_manifest(output_base, heatmap_image_paths, 5, "Differential heatmaps", "heatmap", generated_at)
            + self._build_pep_image_manifest(output_base, proportion_plot_paths, 6, "CDR3 classification proportions", "proportion", generated_at)
            + self._build_pep_image_manifest(output_base, arrange_heatmap_paths, 7, "CDR3 arrangement heatmaps", "arrangement_heatmap", generated_at)
            + self._build_pep_image_manifest(output_base, plot_heatmap_paths, 8, "Unique CDR3 heatmaps", "unique_cdr3_heatmap", generated_at)
        )
        available_steps = sorted({
            int(item.get("step"))
            for item in step_summary
            if str(item.get("status") or "").lower() == "completed"
            and str(item.get("step") or "").isdigit()
        })
        available_data_types = []
        if profile_file.exists():
            available_data_types.append("profile")
        if has_vj_usage:
            available_data_types.append("VJ usage")
        if any(str(chain).upper() == "TRA" for chain in chains) or has_tra:
            available_data_types.append("TRA")
        if arrange_heatmap_paths:
            available_data_types.append("Step7 images")
        cache_manifest = {
            "cache_id": job_id,
            "analysis_type": "pep-analysis",
            "created_at": generated_at,
            "project_id": project_id or "",
            "project_name": "",
            "job_id": job_id,
            "output_base": str(output_base),
            "profile_path": str(profile_file),
            "pep_data_dir": str(pep_dir),
            "sample_list": sample_list,
            "sample_count": len(sample_list),
            "chains": chains,
            "chain_list": chains,
            "group_fields": group_fields,
            "output_files": output_files,
            "result_files": output_files,
            "image_files": image_files,
            "available_steps": available_steps,
            "available_data_types": available_data_types,
            "has_vj_usage": has_vj_usage,
            "has_profile": profile_file.exists(),
            "has_mait_nkt_tra": has_tra,
            "has_ml_profile": profile_file.exists(),
            "has_ml_vj": has_vj_usage,
            "has_tra": has_tra,
            "has_step7_images": bool(arrange_heatmap_paths),
            "downstream": {
                "mait-nkt": has_tra,
                "volcano": has_vj_usage,
                "umapin": has_vj_usage,
                "ml-analysis": profile_file.exists() or has_vj_usage,
            },
            "step_summary": step_summary,
            "skip_reasons": {
                str(item["step"]): item.get("skip_reason", "")
                for item in step_summary
                if item.get("status") == "skipped" and item.get("skip_reason")
            },
        }

        metadata = {
            "job_id": job_id,
            "generated_at": generated_at,
            "pep_data_dir": str(pep_dir),
            "profile_path": str(profile_file),
            "group_fields": group_fields,
            "selected_chains": chains,
            "selected_sample_count": len(selected_sample_keys),
            "pvalue_threshold": pvalue_threshold,
            "min_sample_threshold": min_sample_threshold,
            "optional_steps_requested": sorted(requested_optional),
            "optional_steps_run": sorted(run_optional),
            "step_summary": step_summary,
            "image_files": image_files,
            "output_counts": {
                "shared_matrix": len(shared_matrix_paths),
                "usage": len(usage_paths),
                "heatmap_images": len(heatmap_image_paths),
                "heatmap_csv": len(heatmap_csv_paths),
                "classification": len(classification_paths),
                "proportion": len(proportion_paths),
                "proportion_plot": len(proportion_plot_paths),
                "arrange_heatmap": len(arrange_heatmap_paths),
                "plot_heatmap": len(plot_heatmap_paths),
            },
            "step7": {
                "input_dirs": [
                    str(output_base / gf / "arrage_pep" / "Pep_shared_cate" / "Pep_shared")
                    for gf in group_fields
                ],
                "output_dirs": [
                    str(output_base / gf / "CDR3_arrage_heatmap")
                    for gf in group_fields
                ],
                "image_count": len(arrange_heatmap_paths),
                "image_files": [
                    item for item in image_files if str(item.get("step") or "") == "7"
                ],
            },
            "optional_step_errors": all_optional_step_errors,
            "chain_file_counts": {c: len(chain_files.get(c, [])) for c in chains},
            "df_vj_all_path": str(df_vj_all_path) if df_vj_all_path else "",
            "df_1vj_all_path": str(df_1vj_all_path) if df_1vj_all_path else "",
            "intermediate_paths": {
                "pep_shared_dir": str(output_base / "Pep_shared"),
                "usage_dir": str(output_base / "usage"),
                "group_dirs": {
                    gf: {
                        "pep_shared_cate_dir": str(output_base / gf / "Pep_shared_cate" / "Pep_shared"),
                        "usage_cate_dir": str(output_base / gf / "usage_cate" / "usage"),
                        "arrage_pep_dir": str(output_base / gf / "arrage_pep" / "Pep_shared_cate" / "Pep_shared"),
                        "prop_pep_dir": str(output_base / gf / "prop_pep" / "Pep_shared_cate" / "Pep_shared"),
                    }
                    for gf in group_fields
                },
                "tra_candidates": [
                    str(path)
                    for path in [output_base / "Pep_shared" / "TRA.csv"]
                    + [output_base / gf / "Pep_shared_cate" / "Pep_shared" / "TRA.csv" for gf in group_fields]
                    if path.exists()
                ],
            },
            "cache_manifest": cache_manifest,
            "cache_manifest_path": str(output_base / "cache_manifest.json"),
        }
        (output_base / "cache_manifest.json").write_text(
            json.dumps(cache_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._update_cache_registry(cache_manifest)
        (output_base / "pep_analysis_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        if progress_callback:
            progress_callback(100, "Pep Analysis completed",
                              f"Generated shared matrices for {len(chains)} chains with {len(group_fields)} group field(s)")

        return PepAnalysisReport(
            job_id=job_id,
            output_base=output_base,
            shared_matrix_paths=shared_matrix_paths,
            usage_paths=usage_paths,
            heatmap_image_paths=heatmap_image_paths,
            heatmap_csv_paths=heatmap_csv_paths,
            classification_paths=classification_paths,
            proportion_paths=proportion_paths,
            proportion_plot_paths=proportion_plot_paths,
            arrange_heatmap_paths=arrange_heatmap_paths,
            plot_heatmap_paths=plot_heatmap_paths,
            zip_path=str(zip_path),
            metadata=metadata,
        )

    # ============================================================
    # Step 2: CDR3 Sharing Analysis
    # ============================================================
    @staticmethod
    def _build_pep_image_manifest(
        output_base: Path,
        paths: List[str],
        step: int,
        data_category: str,
        image_type: str,
        created_at: str,
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for raw_path in paths or []:
            path = Path(str(raw_path or ""))
            if not path.exists() or not path.is_file():
                continue
            try:
                rel = path.relative_to(output_base).as_posix()
            except Exception:
                rel = path.name
            parts = rel.split("/")
            group_field = parts[0] if len(parts) > 2 else "Summary"
            chain = path.stem.split("_", 1)[0].upper() if path.stem else ""
            if path.name.upper().startswith("ALL_"):
                chain = "ALL"
            filter_dimensions = ["group_field", "chain", "image_type"]
            if step == 7 or image_type == "arrangement_heatmap":
                group_field = ""
                filter_dimensions = ["chain"]
            image_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"pep_step{step}_{rel}").strip("_")
            entries.append({
                "image_id": image_id,
                "image_path": rel,
                "image_name": path.name,
                "analysis_type": "PEP",
                "step": str(step),
                "data_category": data_category,
                "image_type": image_type,
                "chain": chain,
                "group": group_field,
                "group_field": group_field,
                "comparison": "",
                "filter_dimensions": filter_dimensions,
                "created_at": created_at,
            })
        return entries

    @staticmethod
    def _write_combined_usage(source_dir: Path, output_path: Path) -> Optional[Path]:
        if not source_dir.exists() or not source_dir.is_dir():
            return None
        files = sorted(source_dir.glob("*.csv"))
        if not files:
            return None
        normalized_frames: List[pd.DataFrame] = []
        for file_path in files:
            df = _try_read_csv(file_path, low_memory=False)
            if df.empty:
                continue
            first_col = df.columns[0]
            if first_col != "sample":
                df = df.rename(columns={first_col: "sample"})
            if "Category" not in df.columns:
                df.insert(1, "Category", "")
            feature_cols = [col for col in df.columns if col not in ("sample", "Category")]
            normalized_frames.append(df[["sample", "Category"] + feature_cols])
        if not normalized_frames:
            return None
        try:
            df_all = pd.concat(
                [df.set_index(["sample", "Category"]) for df in normalized_frames],
                axis=1,
                join="outer",
            ).reset_index()
        except Exception:
            df_all = pd.DataFrame(columns=["sample", "Category"])
            for df in normalized_frames:
                df_all = pd.merge(df_all, df, how="outer", on=["sample", "Category"])
        if df_all.shape[1] <= 2:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df_all.fillna(0).to_csv(output_path, index=False, encoding="utf-8-sig")
        return output_path

    @staticmethod
    def _write_sparse_feature_csv(
        output_path: Path,
        *,
        first_column: str,
        row_order: List[str],
        column_maps: Dict[str, Dict[str, Any]],
        transpose: bool,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_names = list(column_maps.keys())
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if not transpose:
                writer.writerow([first_column, *sample_names])
                for feature in row_order:
                    writer.writerow([feature, *[column_maps[sample].get(feature, "") for sample in sample_names]])
                return

            writer.writerow([first_column, *row_order])
            for sample_name, values in column_maps.items():
                writer.writerow([sample_name, *[values.get(feature, "") for feature in row_order]])

    def _run_cdr3_sharing(
        self,
        chain: str,
        file_paths: List[str],
        output_base: Path,
        progress_callback=None,
    ) -> Tuple[List[str], List[str]]:
        shared_series: Dict[str, Dict[str, Any]] = {}
        one_v_series: Dict[str, Dict[str, Any]] = {}
        zero_v_series: Dict[str, Dict[str, Any]] = {}
        one_j_series: Dict[str, Dict[str, Any]] = {}
        zero_j_series: Dict[str, Dict[str, Any]] = {}
        one_vj_series: Dict[str, Dict[str, Any]] = {}
        zero_vj_series: Dict[str, Dict[str, Any]] = {}

        shared_order: List[str] = []
        v_order: List[str] = []
        j_order: List[str] = []
        vj_order: List[str] = []
        shared_seen: set[str] = set()
        v_seen: set[str] = set()
        j_seen: set[str] = set()
        vj_seen: set[str] = set()
        seen_columns: Dict[str, int] = {}

        def _sample_col(file_path: str) -> str:
            base = os.path.basename(file_path)
            count = seen_columns.get(base, 0)
            seen_columns[base] = count + 1
            if count == 0:
                return base
            stem, suffix = os.path.splitext(base)
            return f"{stem}_{count}{suffix}"

        def _extend_order(order: List[str], existing: set[str], values: Any) -> None:
            for value in values:
                key = str(value)
                if key not in existing:
                    order.append(key)
                    existing.add(key)

        total_files = len(file_paths)
        progress_interval = max(1, total_files // 80)

        for idx, file_path in enumerate(file_paths, start=1):
            param_col = _sample_col(file_path)
            try:
                df = _try_read_csv(
                    file_path,
                    usecols=["CDR3(pep)", "V", "J", "copy"],
                    dtype={"CDR3(pep)": str, "V": str, "J": str},
                )
            except Exception:
                if progress_callback and (idx == total_files or idx % progress_interval == 0):
                    progress_callback(idx, total_files, os.path.basename(file_path))
                continue
            if df.empty:
                if progress_callback and (idx == total_files or idx % progress_interval == 0):
                    progress_callback(idx, total_files, os.path.basename(file_path))
                continue

            df["CDR3(pep)"] = df["CDR3(pep)"].fillna("nan").astype(str)
            df["V"] = df["V"].fillna("nan").astype(str)
            df["J"] = df["J"].fillna("nan").astype(str)
            df["copy"] = pd.to_numeric(df["copy"], errors="coerce").fillna(0).astype(np.int64)

            copy_total = float(df["copy"].sum())
            if copy_total <= 0:
                copy_total = 1.0

            shared = df.groupby("CDR3(pep)", sort=False)["copy"].sum()
            _extend_order(shared_order, shared_seen, shared.index.tolist())
            shared_series[param_col] = shared.to_dict()

            gb_v = df.groupby("V", sort=False)["copy"].sum() / copy_total
            _extend_order(v_order, v_seen, gb_v.index.tolist())
            one_v_series[param_col] = gb_v.to_dict()

            n_v = df["V"].value_counts(normalize=True, sort=False)
            _extend_order(v_order, v_seen, n_v.index.tolist())
            zero_v_series[param_col] = n_v.to_dict()

            gb_j = df.groupby("J", sort=False)["copy"].sum() / copy_total
            _extend_order(j_order, j_seen, gb_j.index.tolist())
            one_j_series[param_col] = gb_j.to_dict()

            n_j = df["J"].value_counts(normalize=True, sort=False)
            _extend_order(j_order, j_seen, n_j.index.tolist())
            zero_j_series[param_col] = n_j.to_dict()

            vj = df["V"] + ";" + df["J"]
            gb_vj = df["copy"].groupby(vj, sort=False).sum() / copy_total
            _extend_order(vj_order, vj_seen, gb_vj.index.tolist())
            one_vj_series[param_col] = gb_vj.to_dict()

            n_vj = vj.value_counts(normalize=True, sort=False)
            _extend_order(vj_order, vj_seen, n_vj.index.tolist())
            zero_vj_series[param_col] = n_vj.to_dict()

            if progress_callback and (idx == total_files or idx % progress_interval == 0):
                progress_callback(idx, total_files, os.path.basename(file_path))

        shared_paths: List[str] = []
        usage_paths: List[str] = []

        # Save shared CDR3 matrix
        shared_dir = output_base / "Pep_shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        shared_csv = shared_dir / f"{chain}.csv"
        if progress_callback:
            progress_callback(total_files, total_files, shared_csv.name, phase="assembling", label="assembling Pep_shared matrix")
        if progress_callback:
            progress_callback(total_files, total_files, shared_csv.name, phase="writing_shared", label=f"writing Pep_shared/{chain}.csv")
        self._write_sparse_feature_csv(
            shared_csv,
            first_column="CDR3(pep)",
            row_order=shared_order,
            column_maps=shared_series,
            transpose=False,
        )
        shared_paths.append(str(shared_csv))

        usage_mappings: List[Tuple[Dict[str, Dict[str, Any]], str, List[str]]] = [
            (one_v_series, "1Vusage", v_order),
            (one_j_series, "1Jusage", j_order),
            (zero_v_series, "0Vusage", v_order),
            (zero_j_series, "0Jusage", j_order),
            (zero_vj_series, "0VJusage", vj_order),
            (one_vj_series, "1VJusage", vj_order),
        ]
        for series_map, usage_type, feature_order in usage_mappings:
            usage_dir = output_base / "usage" / usage_type
            usage_dir.mkdir(parents=True, exist_ok=True)
            csv_path = usage_dir / f"{chain}.csv"
            if progress_callback:
                progress_callback(
                    total_files,
                    total_files,
                    csv_path.name,
                    phase="writing_usage",
                    label=f"writing usage/{usage_type}/{chain}.csv",
                )
            self._write_sparse_feature_csv(
                csv_path,
                first_column="",
                row_order=feature_order,
                column_maps=series_map,
                transpose=True,
            )
            usage_paths.append(str(csv_path))

        return shared_paths, usage_paths

    # ============================================================
    # Step 3: Add categories to shared CDR3
    # ============================================================
    @staticmethod
    def _add_cate_shared(src: Path, dst: Path, profile_df: pd.DataFrame, group_field: str) -> None:
        header_df = _try_read_csv(src, nrows=0)
        source_columns = list(header_df.columns)
        if not source_columns:
            return
        sample_col = profile_df.columns[0]
        group_map = {
            str(sample): value
            for sample, value in profile_df.set_index(sample_col)[group_field].to_dict().items()
        }

        cate_values: Dict[str, str] = {}
        for pep_name in source_columns[1:]:
            parts = pep_name.split("__")
            samplename = "__".join(parts[:-1]) if len(parts) > 1 else pep_name
            if samplename in group_map:
                val = group_map[samplename]
                category = str(val) if pd.notna(val) else "nan"
                if category != "nan":
                    cate_values[pep_name] = category

        categories = _reference_category_order(list(dict.fromkeys(cate_values.values())))
        categories_dict: Dict[str, List[str]] = {}
        for col, category in cate_values.items():
            categories_dict.setdefault(category, []).append(col)
        ordered_sample_columns: List[str] = []
        for category in categories:
            for col in categories_dict.get(category, []):
                ordered_sample_columns.insert(0, col)
        ordered_columns = ["CDR3(pep)", *ordered_sample_columns]

        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(ordered_columns)
            writer.writerow(["category", *[cate_values[col] for col in ordered_sample_columns]])
            chunks = _try_read_csv(src, usecols=ordered_columns, chunksize=100_000, low_memory=False)
            for chunk in chunks:
                chunk.loc[:, ordered_columns].to_csv(handle, index=False, header=False)

    # ============================================================
    # Step 4: Add categories to usage matrices
    # ============================================================
    @staticmethod
    def _add_cate_usage(src: Path, dst: Path, profile_df: pd.DataFrame, group_field: str) -> None:
        df = _try_read_csv(src)
        sample_col = profile_df.columns[0]
        index_col = df.columns[0]
        group_map = {
            str(sample): value
            for sample, value in profile_df.set_index(sample_col)[group_field].to_dict().items()
        }

        sample_names = df[index_col].astype(str).map(
            lambda name: "__".join(name.split("__")[:-1]) if "__" in name else name
        )
        categories = sample_names.map(group_map)
        clean_cate = categories.map(lambda value: str(value) if pd.notna(value) else "nan")
        mask = clean_cate.ne("nan")

        df_s = df.loc[mask].copy()
        clean_cate = clean_cate.loc[mask].tolist()
        df_s.insert(loc=1, column="Category", value=clean_cate)
        category_order = [item for item in REFERENCE_CATEGORY_ORDER if item in set(clean_cate)]
        category_order.extend(sorted(str(item) for item in set(clean_cate) if str(item) not in category_order))
        df_s["Category"] = pd.Categorical(df_s["Category"], categories=category_order, ordered=True)
        df_s.sort_values(by=["Category"], ascending=True, inplace=True)
        df_s.rename(columns={df_s.columns[0]: "sample"}, inplace=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        df_s.to_csv(dst, index=False)

    # ============================================================
    # Step 5: Heatmap with Mann-Whitney U test
    # ============================================================
    @staticmethod
    def _run_heatmap(src: Path, output_dir: Path, pvalue_threshold: float) -> Tuple[List[str], List[str]]:
        output_dir.mkdir(parents=True, exist_ok=True)
        df = _try_read_csv(src, low_memory=False)

        if df.shape[1] < 3:
            return [], []

        data_split_point = 2
        category_col = df.columns[1]
        feature_cols = df.columns[data_split_point:].tolist()
        if not feature_cols:
            return [], []

        category_series = df[category_col].astype(str)
        itemlist = sorted([
            item for item in category_series.dropna().unique().tolist()
            if item not in {"", "0", "nan"}
        ])

        numeric_df = df.loc[:, feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0).astype(np.float32)
        heatmap_columns = _reference_heatmap_column_order(feature_cols)
        threash_hold_s = pvalue_threshold / 10.0
        threash_hold_p = pvalue_threshold

        image_paths: List[str] = []
        csv_paths: List[str] = []
        rows: List[np.ndarray] = []
        row_names: List[str] = []
        csv_dir = output_dir / "csv_file"
        csv_dir.mkdir(parents=True, exist_ok=True)
        csv_path = csv_dir / f"{category_col}.csv"

        if len(itemlist) < 2:
            pd.DataFrame(columns=heatmap_columns).to_csv(csv_path)
            return [], [str(csv_path)]

        values_cache = {
            item: numeric_df.loc[category_series == item].to_numpy(dtype=np.float32, copy=False)
            for item in itemlist
        }
        for group_a, group_b in combinations(itemlist, 2):
            arr_a = values_cache.get(group_a)
            arr_b = values_cache.get(group_b)
            if arr_a is None or arr_b is None or arr_a.size == 0 or arr_b.size == 0:
                continue
            try:
                pvalues = mannwhitneyu(arr_a, arr_b, alternative="two-sided", axis=0).pvalue
            except Exception:
                pvalues = np.array([
                    mannwhitneyu(arr_a[:, idx], arr_b[:, idx], alternative="two-sided").pvalue
                    for idx in range(len(feature_cols))
                ])
            mean_a = np.nanmean(arr_a, axis=0)
            mean_b = np.nanmean(arr_b, axis=0)
            row = np.zeros(len(feature_cols), dtype=np.int8)
            valid = pvalues <= threash_hold_p
            stronger = pvalues < threash_hold_s
            direction = np.where(mean_a > mean_b, 1, -1)
            row[valid] = np.where(stronger[valid], 10, 5) * direction[valid]
            rows.append(row)
            row_names.append(f"{group_a} vs. {group_b}")

        if not rows:
            pd.DataFrame(columns=heatmap_columns).to_csv(csv_path)
            return [], [str(csv_path)]

        pre_df = pd.DataFrame(np.vstack(rows), index=row_names, columns=feature_cols)
        pre_df = pre_df.loc[:, heatmap_columns]

        heat_y = pre_df.shape[0]
        heat_x = pre_df.shape[1]

        pre_df.to_csv(csv_path)
        csv_paths.append(str(csv_path))

        if heat_y <= 0 or heat_x <= 0:
            return image_paths, csv_paths

        if heat_x > 30:
            num_split = heat_x // 30 + 1
            for i in range(num_split):
                if i == num_split - 1:
                    iso_df = pre_df[pre_df.columns[i * 30:]]
                else:
                    iso_df = pre_df[pre_df.columns[i * 30:(i + 1) * 30]]
                pre_x = len(iso_df.columns)
                plt.subplots(figsize=(pre_x, heat_y), dpi=120)
                sns.heatmap(iso_df, cbar=False, linewidths=0.5, square=True,
                            cmap="coolwarm", vmax=10, vmin=-10)
                plt.ylim(0, heat_y)
                plt.xlim(0, pre_x)
                plt.yticks(rotation=0)
                ax = plt.gca()
                for spine in ax.spines.values():
                    spine.set_visible(True)
                png_path = output_dir / f"{category_col}_{i}.png"
                save_publication_png(plt.gcf(), png_path)
                plt.clf()
                plt.close("all")
                image_paths.append(str(png_path))
        else:
            pre_x = len(pre_df.columns)
            plt.subplots(figsize=(pre_x, heat_y), dpi=120)
            sns.heatmap(pre_df, cbar=False, linewidths=0.5, square=True,
                        cmap="coolwarm", vmax=10, vmin=-10)
            plt.ylim(0, heat_y)
            plt.xlim(0, pre_x)
            plt.yticks(rotation=0)
            ax = plt.gca()
            for spine in ax.spines.values():
                spine.set_visible(True)
            png_path = output_dir / f"{category_col}.png"
            save_publication_png(plt.gcf(), png_path)
            plt.clf()
            plt.close("all")
            image_paths.append(str(png_path))

        return image_paths, csv_paths

    # ============================================================
    # Step 6: CDR3 classification statistics
    # ============================================================
    @staticmethod
    def _run_classification(src: Path, arr_dst: Path, prop_dst: Path,
                            min_sample_threshold: int) -> Tuple[Optional[str], Optional[str]]:
        df = _try_read_csv(src, low_memory=False)
        if df.shape[0] <= 1:
            return None, None

        category_dict: Dict[str, list] = {}
        for cate, idname in zip(df.iloc[0].tolist()[1:], df.iloc[0].index[1:].tolist()):
            if str(cate).strip() == " ":
                break
            category_dict.setdefault(str(cate), []).append(idname)

        if not category_dict:
            return None, None

        df_nocate = df.iloc[1:].copy()
        count_name_list: List[str] = []
        aggregate_data: Dict[str, np.ndarray] = {}
        for cate, idnames in category_dict.items():
            ca = df_nocate.loc[:, idnames].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(dtype=np.float32)
            sum_values = ca.sum(axis=1).astype(np.int32)
            aggregate_data[f"{cate}__sum"] = sum_values
            ca = (ca >= 1).astype(np.int8)
            count_values = ca.sum(axis=1).astype(np.int16)
            aggregate_data[f"{cate}__count"] = count_values
            count_name_list.append(f"{cate}__count")

        for column, values in aggregate_data.items():
            df_nocate[column] = values
        all_num = np.sum(
            np.column_stack([aggregate_data[column] for column in count_name_list]),
            axis=1,
        ).astype(np.int16)
        df_nocate["all_num"] = all_num

        df_sort = df_nocate[df_nocate["all_num"] > min_sample_threshold].sort_values(by="all_num", ascending=False)

        cb_list: list = []
        for i in range(2, len(count_name_list) + 1):
            cb_list += list(combinations(count_name_list, i))
        cb_list = count_name_list + cb_list

        proportion_dict: Dict[Any, int] = {}
        selected_frames: List[pd.DataFrame] = []
        category_list: List[str] = []
        count_matrix = df_sort.loc[:, count_name_list].to_numpy(dtype=np.int16, copy=False) if not df_sort.empty else np.empty((0, len(count_name_list)))
        positive_matrix = count_matrix != 0
        count_index = {name: idx for idx, name in enumerate(count_name_list)}

        for cb in cb_list:
            if isinstance(cb, str):
                selected = positive_matrix[:, count_index[cb]].copy()
                for other in count_name_list:
                    if other != cb:
                        selected &= ~positive_matrix[:, count_index[other]]
                category_name = cb
            else:
                selected = np.ones(len(df_sort), dtype=bool)
                cb_set = set(cb)
                for item in cb:
                    selected &= positive_matrix[:, count_index[item]]
                for other in count_name_list:
                    if other not in cb_set:
                        selected &= ~positive_matrix[:, count_index[other]]
                category_name = str(cb)
            pre_num = int(selected.sum())
            proportion_dict[category_name] = pre_num
            if pre_num:
                selected_frames.append(df_sort.loc[selected])
                category_list.extend([str(category_name)] * pre_num)

        if selected_frames:
            df_t = pd.concat(selected_frames, axis=0, copy=False)
            df_t = df_t.copy()
            df_t["category"] = category_list
        else:
            df_t = pd.DataFrame(columns=list(df_nocate.columns) + ["category"])

        top_row = {column: df.iloc[0][column] if column in df.columns else " " for column in df_t.columns}
        for column in aggregate_data.keys():
            top_row[column] = " "
        top_row["all_num"] = " "
        top_row["category"] = " "
        df_top = pd.DataFrame([top_row], columns=df_t.columns)
        df_t = pd.concat([df_top, df_t], ignore_index=True)

        arr_dst.parent.mkdir(parents=True, exist_ok=True)
        df_t.to_csv(arr_dst, index=False)

        sum_value = sum(proportion_dict.values())
        for key in proportion_dict:
            proportion_dict[key] = proportion_dict[key] / max(sum_value, 1)

        prop_df = pd.DataFrame({
            "cate": list(proportion_dict.keys()),
            "prop": list(proportion_dict.values()),
        })
        prop_dst.parent.mkdir(parents=True, exist_ok=True)
        prop_df.to_csv(prop_dst, index=False)

        return str(arr_dst), str(prop_dst)

    @staticmethod
    def _plot_proportion_bar(prop_csv: Path, dst: Path) -> Optional[str]:
        if not prop_csv.exists():
            return None
        prop_df = _try_read_csv(prop_csv, low_memory=False)
        if prop_df.empty or "cate" not in prop_df.columns or "prop" not in prop_df.columns:
            return None

        plot_df = prop_df.copy()
        plot_df["cate"] = plot_df["cate"].astype(str)
        plot_df["prop"] = pd.to_numeric(plot_df["prop"], errors="coerce").fillna(0)
        plot_df = plot_df.sort_values("prop", ascending=True)
        if plot_df.empty:
            return None

        dst.parent.mkdir(parents=True, exist_ok=True)
        height = max(3.2, min(12.0, 0.32 * len(plot_df) + 1.8))
        fig, ax = plt.subplots(figsize=(7.2, height), dpi=180)
        colors = sns.color_palette("Blues", n_colors=max(len(plot_df), 3))
        ax.barh(plot_df["cate"], plot_df["prop"], color=colors[-len(plot_df):])
        ax.set_xlabel("Proportion")
        ax.set_ylabel("")
        ax.set_xlim(0, max(1.0, float(plot_df["prop"].max()) * 1.08))
        ax.tick_params(axis="y", labelsize=7)
        ax.grid(axis="x", linestyle="--", alpha=0.25)
        for y, value in enumerate(plot_df["prop"].tolist()):
            ax.text(value + 0.01, y, f"{value:.2%}", va="center", fontsize=7)
        fig.tight_layout()
        save_publication_png(fig, dst)
        plt.close(fig)
        return str(dst)

    # ============================================================
    # Steps 5-8: Per-group optional helpers (called in parallel)
    # ============================================================

    def _run_step5_for_group(self, chains, usage_cate_base, field_dir, pvalue_threshold, progress_callback=None):
        """Step 5: Heatmap with Mann-Whitney U test for one group field."""
        images, csvs = [], []
        heatmap_base = field_dir / "heatmap"
        heatmap_base.mkdir(parents=True, exist_ok=True)
        planned = [
            (usage_type, chain, usage_cate_base / usage_type / f"{chain}.csv")
            for usage_type in ["0Vusage", "1Vusage", "0Jusage", "1Jusage", "0VJusage", "1VJusage"]
            for chain in chains
            if (usage_cate_base / usage_type / f"{chain}.csv").exists()
        ]
        total = max(len(planned), 1)
        if progress_callback:
            progress_callback(
                f"processing {len(planned)} usage files",
                {"stage": "step5_load_usage_cate", "processed": 0, "total": total},
            )
        for index, (usage_type, chain, src) in enumerate(planned, start=1):
            if progress_callback:
                progress_callback(
                    f"running heatmap {index}/{total} ({usage_type}, {chain})",
                    {
                        "stage": "step5_compute_mwu",
                        "usage_type": usage_type,
                        "chain": chain,
                        "processed": index - 1,
                        "total": total,
                    },
                )
            with _PLOT_LOCK:
                h_imgs, h_csvs = self._run_heatmap(
                    src, heatmap_base / usage_type / chain, pvalue_threshold
                )
            images.extend(h_imgs)
            csvs.extend(h_csvs)
            if progress_callback:
                progress_callback(
                    f"heatmap complete {index}/{total} ({usage_type}, {chain})",
                    {
                        "stage": "step5_write_heatmap_png",
                        "usage_type": usage_type,
                        "chain": chain,
                        "processed": index,
                        "total": total,
                    },
                )
        return images, csvs

    def _run_step6_for_group(self, chains, pep_shared_cate_dir, field_dir, min_sample_threshold, progress_callback=None):
        """Step 6: CDR3 classification statistics for one group field."""
        arr_paths, prp_paths, prp_plot_paths = [], [], []
        arrage_base = field_dir / "arrage_pep" / "Pep_shared_cate" / "Pep_shared"
        prop_base = field_dir / "prop_pep" / "Pep_shared_cate" / "Pep_shared"
        arrage_base.mkdir(parents=True, exist_ok=True)
        prop_base.mkdir(parents=True, exist_ok=True)
        planned = [(chain, pep_shared_cate_dir / f"{chain}.csv") for chain in chains if (pep_shared_cate_dir / f"{chain}.csv").exists()]
        total = max(len(planned), 1)
        if progress_callback:
            progress_callback(
                f"processing {len(planned)} shared files",
                {"stage": "step6_load_shared_cate", "processed": 0, "total": total},
            )
        for index, (chain, src) in enumerate(planned, start=1):
            if progress_callback:
                progress_callback(
                    f"running classification {index}/{total} ({chain})",
                    {
                        "stage": "step6_count_combinations",
                        "chain": chain,
                        "processed": index - 1,
                        "total": total,
                    },
                )
            arr_path, prp_path = self._run_classification(
                src, arrage_base / f"{chain}.csv", prop_base / f"{chain}.csv",
                min_sample_threshold
            )
            if arr_path:
                arr_paths.append(arr_path)
            if prp_path:
                prp_paths.append(prp_path)
            if progress_callback:
                progress_callback(
                    f"classification complete {index}/{total} ({chain})",
                    {
                        "stage": "step6_write_prop_pep",
                        "chain": chain,
                        "processed": index,
                        "total": total,
                    },
                )
        return arr_paths, prp_paths, prp_plot_paths

    def _run_step7_for_group(self, chains, field_dir, progress_callback=None):
        """Step 7: CDR3 arrangement heatmap for one group field."""
        paths = []
        arrange_dir = field_dir / "CDR3_arrage_heatmap"
        arrange_dir.mkdir(parents=True, exist_ok=True)
        arrage_src_base = field_dir / "arrage_pep" / "Pep_shared_cate" / "Pep_shared"
        planned = [(chain, arrage_src_base / f"{chain}.csv") for chain in chains if (arrage_src_base / f"{chain}.csv").exists()]
        total = max(len(planned), 1)
        if progress_callback:
            progress_callback(
                f"Step7 started: processing {len(planned)} arrage files",
                {
                    "stage": "step7_start",
                    "processed": 0,
                    "total": total,
                    "input_dir": str(arrage_src_base),
                    "output_dir": str(arrange_dir),
                },
            )
        if not planned:
            if progress_callback:
                progress_callback(
                    "skipped: no Step 6 arrage_pep CSV files found",
                    {
                        "stage": "step7_missing_dependency",
                        "processed": 1,
                        "total": 1,
                        "input_dir": str(arrage_src_base),
                        "output_dir": str(arrange_dir),
                        "skip_reason": "missing_step6_arrage_pep",
                    },
                )
            return paths
        for index, (chain, arr_src) in enumerate(planned, start=1):
            out_path = arrange_dir / f"{chain}.png"
            if progress_callback:
                progress_callback(
                    f"plotting arrange heatmap {index}/{total} ({chain})",
                    {
                        "stage": "step7_plot_arrange_heatmap",
                        "chain": chain,
                        "processed": index - 1,
                        "total": total,
                        "input_path": str(arr_src),
                        "output_path": str(out_path),
                    },
                )
            try:
                with _PLOT_LOCK:
                    png_path = self._run_arrange_heatmap(arr_src, out_path)
            except Exception as exc:
                logger.warning("Step7 arrange heatmap failed for %s: %s", arr_src, exc, exc_info=True)
                png_path = None
                if progress_callback:
                    progress_callback(
                        f"Step7 failed for {chain}: {exc}",
                        {
                            "stage": "step7_failed",
                            "chain": chain,
                            "processed": index,
                            "total": total,
                            "input_path": str(arr_src),
                            "output_path": str(out_path),
                            "error": str(exc),
                        },
                    )
            if png_path:
                paths.append(png_path)
            elif progress_callback:
                progress_callback(
                    f"Step7 skipped {chain}: no drawable matrix",
                    {
                        "stage": "step7_no_image",
                        "chain": chain,
                        "processed": index,
                        "total": total,
                        "input_path": str(arr_src),
                        "output_path": str(out_path),
                        "skip_reason": "empty_or_invalid_step7_matrix",
                    },
                )
            if progress_callback:
                progress_callback(
                    f"arrange heatmap complete {index}/{total} ({chain})",
                    {
                        "stage": "step7_write_arrange_heatmap",
                        "chain": chain,
                        "processed": index,
                        "total": total,
                        "generated_image_count": len(paths),
                    },
                )
        if progress_callback:
            progress_callback(
                f"Step7 completed: generated {len(paths)} image(s)",
                {
                    "stage": "step7_complete",
                    "processed": total,
                    "total": total,
                    "output_dir": str(arrange_dir),
                    "generated_image_count": len(paths),
                },
            )
        return paths

    def _run_step8_for_group(self, chains, field_dir, progress_callback=None):
        """Step 8: Plot heatmap (per-chain unique CDR3 heatmap + summary)."""
        paths = []
        arrage_base = field_dir / "arrage_pep" / "Pep_shared_cate" / "Pep_shared"
        output_dir = field_dir / "plot_heatmap"
        output_dir.mkdir(parents=True, exist_ok=True)

        payloads = []
        readable = [(chain, arrage_base / f"{chain}.csv") for chain in chains if (arrage_base / f"{chain}.csv").exists()]
        total_read = max(len(readable), 1)
        if progress_callback:
            progress_callback(
                f"reading {len(readable)} arrage files",
                {"stage": "step8_read_arrage_data", "processed": 0, "total": total_read},
            )
        if not readable:
            if progress_callback:
                progress_callback(
                    "skipped: no Step 6 arrage_pep CSV files found",
                    {"stage": "step8_missing_dependency", "processed": 1, "total": 1, "skip_reason": "missing_step6_arrage_pep"},
                )
            return paths
        for index, (chain, src) in enumerate(readable, start=1):
            try:
                payload = self._read_plot_heatmap_data(src, chain)
                payloads.append(payload)
            except Exception:
                continue
            if progress_callback:
                progress_callback(
                    f"read unique CDR3 data {index}/{total_read} ({chain})",
                    {"stage": "step8_read_arrage_data", "chain": chain, "processed": index, "total": total_read},
                )

        if not payloads:
            return paths

        vmax = self._get_plot_heatmap_vmax(payloads)

        total_plot = len(payloads) + 1
        for index, payload in enumerate(payloads, start=1):
            with _PLOT_LOCK:
                out_path = self._plot_chain_heatmap(payload, vmax, output_dir)
            if out_path:
                paths.append(out_path)
            chain_name = str(payload.get("chain") or "")
            if progress_callback:
                progress_callback(
                    f"unique CDR3 heatmap complete {index}/{total_plot} ({chain_name})",
                    {
                        "stage": "step8_plot_chain_heatmap",
                        "chain": chain_name,
                        "processed": index,
                        "total": total_plot,
                    },
                )

        # Summary across all chains
        with _PLOT_LOCK:
            summary_path = self._plot_summary_heatmap(payloads, vmax, output_dir)
        if summary_path:
            paths.append(summary_path)
        if progress_callback:
            progress_callback(
                f"unique CDR3 summary heatmap complete {total_plot}/{total_plot}",
                {"stage": "step8_plot_summary_heatmap", "chain": "ALL", "processed": total_plot, "total": total_plot},
            )

        return paths

    # ---- Step 8 helpers (from 8.plot_heatmap.py) ----

    @staticmethod
    def _read_plot_heatmap_data(data_path: Path, chain: str) -> Dict[str, Any]:
        import csv as csv_module
        with data_path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv_module.reader(handle)
            try:
                header = next(reader)
                group_row = next(reader)
            except StopIteration as exc:
                raise ValueError(f"Input CSV must contain two header rows: {data_path}") from exc

            sample_idx = [
                i for i, group in enumerate(group_row)
                if i > 0 and group.strip() not in {"", "category"}
            ]
            if not sample_idx:
                raise ValueError(f"No sample category columns found: {data_path}")

            cdr3_col = header.index("CDR3(pep)")
            category_col = header.index("category")
            sample_names = []
            for i in sample_idx:
                sample_name = Path(header[i]).stem
                sample_name = sample_name.replace(f"__{chain}", "")
                sample_names.append(sample_name)

            sample_groups = [group_row[i].strip() for i in sample_idx]
            sort_cols: Dict[str, Optional[int]] = {}
            selected_counts: Dict[str, int] = {}
            top_records: Dict[str, List[Tuple[Tuple[float, float], int, Dict[str, Any]]]] = {}
            available_categories: List[str] = []
            counter = 0

            def _track_category(category: str) -> None:
                if category not in selected_counts:
                    selected_counts[category] = 0
                    top_records[category] = []
                    sort_col_name = f"{category.replace('__count', '')}__sum"
                    sort_cols[category] = header.index(sort_col_name) if sort_col_name in header else None

            for category, _ in REFERENCE_STEP8_SECTION_CATEGORIES:
                _track_category(category)

            for row in reader:
                if not row or len(row) <= category_col:
                    continue
                row_category = row[category_col].strip()
                if not row_category.endswith("__count") or row_category.startswith("("):
                    continue
                if row_category not in available_categories:
                    available_categories.append(row_category)
                _track_category(row_category)
                values = [float(str(row[i]).strip() or 0) if i < len(row) else 0.0 for i in sample_idx]
                sort_col = sort_cols.get(row_category)
                sort_value = float(str(row[sort_col]).strip() or 0) if sort_col is not None and sort_col < len(row) else sum(values)
                rec = {
                    "chain": chain,
                    "cdr3": row[cdr3_col].strip(),
                    "category": row_category,
                    "values": values,
                    "sort_value": sort_value,
                }
                selected_counts[row_category] += 1
                sort_key = (sort_value, sum(values))
                heap = top_records[row_category]
                counter += 1
                if len(heap) < 20:
                    heapq.heappush(heap, (sort_key, counter, rec))
                else:
                    heapq.heappushpop(heap, (sort_key, counter, rec))

        def _build_sections(section_categories: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
            built_sections = []
            for category, section_title in section_categories:
                heap = top_records.get(category, [])
                records = [
                    item[2] for item in sorted(heap, key=lambda item: item[0], reverse=True)
                ]
                selected_count = selected_counts.get(category, 0)

                matrix = []
                for rec in records:
                    vmax_r = max(rec["values"]) if rec["values"] else 0.0
                    if vmax_r <= 0:
                        matrix.append([0.0 for _ in rec["values"]])
                    else:
                        matrix.append([v / vmax_r for v in rec["values"]])

                built_sections.append({
                    "category": category,
                    "title": section_title,
                    "records": records,
                    "matrix": matrix,
                    "selected_count": selected_count,
                })
            return built_sections

        sections = _build_sections(REFERENCE_STEP8_SECTION_CATEGORIES)
        if not any(section["selected_count"] for section in sections) and available_categories:
            sections = _build_sections([
                (category, f"{category.replace('__count', '')} unique")
                for category in available_categories
            ])

        return {
            "chain": chain,
            "sections": sections,
            "sample_names": sample_names,
            "sample_groups": sample_groups,
        }

    @staticmethod
    def _get_plot_heatmap_vmax(payloads):
        return 1.0

    @staticmethod
    def _plot_chain_heatmap(payload, color_vmax, output_dir):
        chain = payload["chain"]
        total_plotted = sum(len(s["records"]) for s in payload["sections"])
        if total_plotted == 0:
            return None

        cmap = _reference_step8_cmap()

        # Build combined matrix
        records = []
        matrix = []
        for section in payload["sections"]:
            records.extend(section["records"])
            matrix.extend(section["matrix"])

        n_rows = len(records)
        n_cols = len(payload["sample_names"])

        cell_size = 0.115
        label_width = 1.25
        cbar_gap = 0.03
        cbar_width = 0.10
        cbar_height = 0.78
        left_margin = 0.14
        right_margin = 0.12
        bottom_margin = 0.22
        top_margin = 0.34
        heatmap_width = n_cols * cell_size
        heatmap_height = n_rows * cell_size
        fig_width = heatmap_width + label_width + cbar_gap + cbar_width + left_margin + right_margin
        fig_height = heatmap_height + bottom_margin + top_margin

        fig = plt.figure(figsize=(fig_width, fig_height))
        ax = fig.add_axes([
            left_margin / fig_width,
            bottom_margin / fig_height,
            heatmap_width / fig_width,
            heatmap_height / fig_height,
        ])
        cbar_ax = fig.add_axes([
            (left_margin + heatmap_width + label_width + cbar_gap) / fig_width,
            (bottom_margin + heatmap_height - min(cbar_height, heatmap_height)) / fig_height,
            cbar_width / fig_width,
            min(cbar_height, heatmap_height) / fig_height,
        ])
        im = ax.imshow(matrix, aspect="equal", interpolation="nearest",
                       cmap=cmap, vmin=0, vmax=color_vmax)

        # X-axis with group labels
        sample_groups = payload["sample_groups"]
        groups = []
        start = 0
        for i in range(1, len(sample_groups) + 1):
            if i == len(sample_groups) or sample_groups[i] != sample_groups[start]:
                groups.append({"label": sample_groups[start], "start": start, "end": i - 1,
                               "center": (start + i - 1) / 2})
                start = i
        labels = [""] * n_cols
        for g in groups:
            labels[(g["start"] + g["end"]) // 2] = g["label"]
        ax.set_xticks(range(n_cols))
        ax.set_xticklabels(labels, fontsize=7.0, fontweight="bold")

        # Y-axis with CDR3 labels
        label_font_size = 5.4 if n_rows <= 50 else 4.4
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels(
            [f"{chain}_{r['cdr3']}" for r in records],
            fontsize=label_font_size, fontweight="bold"
        )
        ax.yaxis.tick_right()

        # Grid
        ax.set_xticks([i - 0.5 for i in range(1, n_cols)], minor=True)
        ax.set_yticks([i - 0.5 for i in range(1, n_rows)], minor=True)
        ax.grid(which="minor", color="white", linewidth=1.0)
        ax.tick_params(which="minor", bottom=False, left=False)
        ax.set_xlim(-0.5, n_cols - 0.5)
        ax.set_ylim(n_rows - 0.5, -0.5)
        for spine in ax.spines.values():
            spine.set_visible(False)

        cbar = fig.colorbar(im, cax=cbar_ax)
        cbar.set_ticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
        cbar.ax.tick_params(labelsize=5.8, length=1.8, width=0.6)
        for tl in cbar.ax.get_yticklabels():
            tl.set_fontweight("bold")
        cbar.outline.set_linewidth(0.6)

        out_path = output_dir / f"{chain}_CT_SRMCY_unique_heatmap.png"
        save_publication_png(fig, out_path)
        plt.close(fig)
        return str(out_path)

    @staticmethod
    def _plot_summary_heatmap(payloads, color_vmax, output_dir):
        payloads = [p for p in payloads
                    if sum(len(s["records"]) for s in p["sections"]) > 0]
        if not payloads:
            return None

        cmap = _reference_step8_cmap()

        reference_groups = payloads[0]["sample_groups"]
        for payload in payloads[1:]:
            if payload["sample_groups"] != reference_groups:
                raise ValueError("ALL heatmap requires the same sample category order in every chain.")

        # Merge all payloads
        all_records = []
        all_matrix = []
        for payload in payloads:
            for section in payload["sections"]:
                all_records.extend(section["records"])
                all_matrix.extend(section["matrix"])

        n_rows = len(all_records)
        n_cols = len(payloads[0]["sample_names"])

        cell_size = 0.105
        label_width = 1.25
        cbar_gap = 0.03
        cbar_width = 0.10
        cbar_height = 0.78
        left_margin = 0.14
        right_margin = 0.12
        bottom_margin = 0.22
        top_margin = 0.34
        heatmap_width = n_cols * cell_size
        heatmap_height = n_rows * cell_size
        fig_width = heatmap_width + label_width + cbar_gap + cbar_width + left_margin + right_margin
        fig_height = heatmap_height + bottom_margin + top_margin

        fig = plt.figure(figsize=(fig_width, fig_height))
        ax = fig.add_axes([
            left_margin / fig_width,
            bottom_margin / fig_height,
            heatmap_width / fig_width,
            heatmap_height / fig_height,
        ])
        cbar_ax = fig.add_axes([
            (left_margin + heatmap_width + label_width + cbar_gap) / fig_width,
            (bottom_margin + heatmap_height - min(cbar_height, heatmap_height)) / fig_height,
            cbar_width / fig_width,
            min(cbar_height, heatmap_height) / fig_height,
        ])
        im = ax.imshow(all_matrix, aspect="equal", interpolation="nearest",
                       cmap=cmap, vmin=0, vmax=color_vmax)

        sample_groups = payloads[0]["sample_groups"]
        groups = []
        start = 0
        for i in range(1, len(sample_groups) + 1):
            if i == len(sample_groups) or sample_groups[i] != sample_groups[start]:
                groups.append({"label": sample_groups[start], "start": start, "end": i - 1,
                               "center": (start + i - 1) / 2})
                start = i
        labels = [""] * n_cols
        for g in groups:
            labels[(g["start"] + g["end"]) // 2] = g["label"]
        ax.set_xticks(range(n_cols))
        ax.set_xticklabels(labels, fontsize=7.0, fontweight="bold")

        label_font_size = 4.8 if n_rows <= 80 else 4.0
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels(
            [f"{r.get('chain', 'ALL')}_{r.get('cdr3', '')}" for r in all_records],
            fontsize=label_font_size, fontweight="bold"
        )
        ax.yaxis.tick_right()

        ax.set_xticks([i - 0.5 for i in range(1, n_cols)], minor=True)
        ax.set_yticks([i - 0.5 for i in range(1, n_rows)], minor=True)
        ax.grid(which="minor", color="white", linewidth=1.0)
        ax.tick_params(which="minor", bottom=False, left=False)
        ax.set_xlim(-0.5, n_cols - 0.5)
        ax.set_ylim(n_rows - 0.5, -0.5)
        for spine in ax.spines.values():
            spine.set_visible(False)

        cbar = fig.colorbar(im, cax=cbar_ax)
        cbar.set_ticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
        cbar.ax.tick_params(labelsize=5.8, length=1.8, width=0.6)
        for tl in cbar.ax.get_yticklabels():
            tl.set_fontweight("bold")
        cbar.outline.set_linewidth(0.6)

        out_path = output_dir / "ALL_CT_SRMCY_unique_heatmap_summary.png"
        save_publication_png(fig, out_path)
        plt.close(fig)
        return str(out_path)

    @staticmethod
    def _run_arrange_heatmap(src: Path, dst: Path) -> Optional[str]:
        df = _try_read_csv(src)
        if df.shape[0] <= 1 or df.shape[1] <= 1:
            return None

        data_end = PepAnalysisService._find_step7_sample_end_column(df)
        if data_end <= 1:
            return None

        df_s = df[df.columns[1:data_end]].iloc[1:]
        df_s = df_s.apply(pd.to_numeric, errors="coerce").fillna(0)
        df_s = df_s.dropna(axis=0, how="all").dropna(axis=1, how="all")
        if df_s.empty:
            return None
        df_s[df_s > 1] = 1
        if df_s.shape[0] > PEP_MAX_ARRANGE_HEATMAP_ROWS:
            df_s = df_s.iloc[:PEP_MAX_ARRANGE_HEATMAP_ROWS]

        plt.figure(figsize=(20, 8))
        try:
            sns.set_palette("pastel")
            ax = sns.heatmap(df_s, square=False, cmap="BuGn",
                             cbar_kws={"aspect": 100, "pad": 0.0005}, cbar=False)
            ax.get_yaxis().set_visible(False)
            plt.rcParams.update({"xtick.labelsize": 10})
            dst.parent.mkdir(parents=True, exist_ok=True)
            save_publication_png(ax.figure, dst, dpi=180)
            plt.clf()
            plt.close("all")
            return str(dst)
        except Exception:
            plt.clf()
            plt.close("all")
            return None

    @staticmethod
    def _find_step7_sample_end_column(df: pd.DataFrame) -> int:
        """Find where sample columns end in Step7 arrage_pep CSVs.

        The original script uses a blank marker row before summary/category columns.
        Pandas may read that marker as a blank string, a single space, or NaN.
        """
        if df.empty or df.shape[1] <= 1:
            return 0
        first_row = df.iloc[0]
        for index, value in enumerate(first_row):
            if index == 0:
                continue
            if pd.isna(value) or str(value).strip() == "":
                return index
        lower_columns = [str(col).strip().lower() for col in df.columns]
        for marker in ("all_num", "category"):
            if marker in lower_columns:
                return lower_columns.index(marker)
        for index, column in enumerate(lower_columns):
            if index > 0 and (column.endswith("__sum") or column in {"sum", "total"}):
                return index
        return len(df.columns)

    # ============================================================
    # Helpers
    # ============================================================
    def _update_cache_registry(self, manifest: Dict[str, Any]) -> None:
        registry_path = self.output_parent / "cache_registry.json"
        output_base = str(manifest.get("output_base") or "")
        entry = {
            "cache_id": manifest.get("cache_id", ""),
            "analysis_type": manifest.get("analysis_type", "pep-analysis"),
            "created_at": manifest.get("created_at", ""),
            "project_id": manifest.get("project_id", ""),
            "project_name": manifest.get("project_name", ""),
            "job_id": manifest.get("job_id", ""),
            "output_base": output_base,
            "manifest_path": str(Path(output_base) / "cache_manifest.json") if output_base else "",
            "sample_count": manifest.get("sample_count", 0),
            "chains": manifest.get("chains", []),
            "chain_list": manifest.get("chain_list", manifest.get("chains", [])),
            "group_fields": manifest.get("group_fields", []),
            "available_steps": manifest.get("available_steps", []),
            "available_data_types": manifest.get("available_data_types", []),
            "has_vj_usage": bool(manifest.get("has_vj_usage")),
            "has_profile": bool(manifest.get("has_profile")),
            "has_tra": bool(manifest.get("has_tra", manifest.get("has_mait_nkt_tra"))),
            "has_mait_nkt_tra": bool(manifest.get("has_mait_nkt_tra")),
            "has_ml_profile": bool(manifest.get("has_ml_profile")),
            "has_ml_vj": bool(manifest.get("has_ml_vj")),
            "has_step7_images": bool(manifest.get("has_step7_images")),
            "downstream": manifest.get("downstream", {}),
        }
        try:
            existing: List[Dict[str, Any]] = []
            if registry_path.exists():
                loaded = json.loads(registry_path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    existing = [item for item in loaded if isinstance(item, dict)]
                elif isinstance(loaded, dict) and isinstance(loaded.get("entries"), list):
                    existing = [item for item in loaded["entries"] if isinstance(item, dict)]
            cache_id = str(entry.get("cache_id") or "")
            entries = [item for item in existing if str(item.get("cache_id") or "") != cache_id]
            entries.append(entry)
            entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
            registry_path.write_text(json.dumps(entries[:200], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("Failed to update PEP cache registry at %s", registry_path, exc_info=True)

    @staticmethod
    def _allocate_job_id(name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{name}_{ts}"
