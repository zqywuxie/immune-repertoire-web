"""
Pep CDR3 Sharing Analysis service.
Implements steps 2-7 of the Pep_260213 pipeline:
  Step 2: CDR3 sharing matrix + V/J/VJ usage matrices
  Steps 3-7: Group-dependent analyses (categorization, heatmap, classification, arrangement)
"""

from __future__ import annotations

import json
import os
import re
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import mannwhitneyu

from flask_app.services.figure_style import (
    MUTED_BLUE_RED_CMAP,
    MUTED_DIVERGING_CMAP,
    apply_publication_style,
)

# Encoding fallback for CSV/TSV files (GBK common in Chinese Windows environments)
_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]

apply_publication_style(font_size=9, axes_linewidth=0.85)

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


def _is_table_file(path: Path) -> bool:
    return path.name.lower().endswith((".csv", ".csv.gz", ".tsv", ".tsv.gz"))


def _reference_numeric_sort_key(value: Any) -> List[float]:
    numbers = re.findall(r"[1-9]+\.?[0-9]*", str(value or ""))
    if not numbers:
        return [float("inf")]
    return [float(item) for item in numbers]


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

        total_steps = 2 + len(group_fields) * 5  # step2 + (3-7) per group
        current_step = [0]

        def _progress(msg: str, meta: Optional[Dict] = None):
            current_step[0] += 1
            pct = min(5 + int(current_step[0] / max(total_steps, 1) * 93), 98)
            if progress_callback:
                progress_callback(pct, "Pep Analysis", msg, meta or {})

        # ---- Step 2: CDR3 sharing analysis (per chain, GROUP-INDEPENDENT) ----
        _progress("Step 2: Scanning pep files by chain", {"step": 2})
        chain_files: Dict[str, List[str]] = {chain: [] for chain in chains}
        for file_path in sorted(path for path in pep_dir.rglob("*") if path.is_file() and _is_table_file(path)):
            chain = _infer_chain_from_path(file_path)
            if chain in chains:
                chain_files.setdefault(chain, []).append(str(file_path))

        shared_matrix_paths: List[str] = []
        usage_paths: List[str] = []

        for chain in chains:
            files = chain_files.get(chain, [])
            if not files:
                continue
            _progress(f"Step 2: CDR3 sharing for {chain} ({len(files)} files)", {"step": 2, "chain": chain})
            sh_paths, us_paths = self._run_cdr3_sharing(chain, files, output_base)
            shared_matrix_paths.extend(sh_paths)
            usage_paths.extend(us_paths)

        # ---- Which optional steps to run? ----
        requested_optional = {5, 6, 7, 8} if optional_steps is None else set(optional_steps)
        run_optional = set(requested_optional)
        if 7 in run_optional or 8 in run_optional:
            # Steps 7/8 read Step 6's arrage_pep outputs, so Step 6 is a dependency.
            run_optional.add(6)

        # ---- Steps 3-7: Per group field ----
        heatmap_image_paths: List[str] = []
        heatmap_csv_paths: List[str] = []
        classification_paths: List[str] = []
        proportion_paths: List[str] = []
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

            # ---- Steps 3+4: 并行执行 (mandatory) ----
            _progress(f"Step 3+4 [{gf}]: Adding categories (parallel)", {"step": "3+4", "group_field": gf})

            def _run_step3():
                """Step 3: Add category to shared CDR3"""
                for chain in chains:
                    src = shared_dir / f"{chain}.csv"
                    if src.exists():
                        self._add_cate_shared(src, pep_shared_cate_dir / f"{chain}.csv", profile_df, gf)

            def _run_step4():
                """Step 4: Add category to usage"""
                for usage_type in ["0Vusage", "1Vusage", "0Jusage", "1Jusage", "0VJusage", "1VJusage"]:
                    src_usage_dir = usage_dir / usage_type
                    dst_usage_dir = usage_cate_base / usage_type
                    if src_usage_dir.exists():
                        dst_usage_dir.mkdir(parents=True, exist_ok=True)
                        for chain in chains:
                            src = src_usage_dir / f"{chain}.csv"
                            if src.exists():
                                self._add_cate_usage(src, dst_usage_dir / f"{chain}.csv", profile_df, gf)

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
                    chains, usage_cate_base, field_dir, pvalue_threshold
                )
            if 6 in run_optional:
                optional_tasks[6] = lambda: self._run_step6_for_group(
                    chains, pep_shared_cate_dir, field_dir, min_sample_threshold
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
                dependent_tasks[7] = lambda: self._run_step7_for_group(chains, field_dir)
            if 8 in run_optional:
                dependent_tasks[8] = lambda: self._run_step8_for_group(chains, field_dir)

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
                arr_paths, prp_paths = optional_task_results[6]
                classification_paths.extend(arr_paths)
                proportion_paths.extend(prp_paths)
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

        # ---- Generate ZIP ----
        zip_path = output_base / "pep_analysis_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in shared_matrix_paths + usage_paths + heatmap_image_paths + \
                     heatmap_csv_paths + classification_paths + proportion_paths + \
                     arrange_heatmap_paths + plot_heatmap_paths:
                fp = Path(p)
                if fp.exists():
                    arcname = str(fp.relative_to(output_base))
                    zf.write(fp, arcname)

        combined_source = (
            output_base / group_fields[0] / "usage_cate" / "usage" / "1VJusage"
            if group_fields else output_base / "usage" / "1VJusage"
        )
        df_vj_all_path = self._write_combined_usage(combined_source, output_base / "usage" / "df_VJ_all.csv")
        df_1vj_all_path = self._write_combined_usage(combined_source, output_base / "usage" / "df_1VJusage_all.csv")

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "pep_data_dir": str(pep_dir),
            "profile_path": str(profile_file),
            "group_fields": group_fields,
            "selected_chains": chains,
            "pvalue_threshold": pvalue_threshold,
            "min_sample_threshold": min_sample_threshold,
            "optional_steps_requested": sorted(requested_optional),
            "optional_steps_run": sorted(run_optional),
            "output_counts": {
                "shared_matrix": len(shared_matrix_paths),
                "usage": len(usage_paths),
                "heatmap_images": len(heatmap_image_paths),
                "heatmap_csv": len(heatmap_csv_paths),
                "classification": len(classification_paths),
                "proportion": len(proportion_paths),
                "arrange_heatmap": len(arrange_heatmap_paths),
                "plot_heatmap": len(plot_heatmap_paths),
            },
            "optional_step_errors": all_optional_step_errors,
            "chain_file_counts": {c: len(chain_files.get(c, [])) for c in chains},
            "df_vj_all_path": str(df_vj_all_path) if df_vj_all_path else "",
            "df_1vj_all_path": str(df_1vj_all_path) if df_1vj_all_path else "",
        }
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
            arrange_heatmap_paths=arrange_heatmap_paths,
            plot_heatmap_paths=plot_heatmap_paths,
            zip_path=str(zip_path),
            metadata=metadata,
        )

    # ============================================================
    # Step 2: CDR3 Sharing Analysis
    # ============================================================
    @staticmethod
    def _write_combined_usage(source_dir: Path, output_path: Path) -> Optional[Path]:
        if not source_dir.exists() or not source_dir.is_dir():
            return None
        files = sorted(source_dir.glob("*.csv"))
        if not files:
            return None
        df_all = pd.DataFrame(columns=["sample", "Category"])
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
            df = df[["sample", "Category"] + feature_cols]
            df_all = pd.merge(df_all, df, how="outer", on=["sample", "Category"])
        if df_all.shape[1] <= 2:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df_all.fillna(0).to_csv(output_path, index=False, encoding="utf-8-sig")
        return output_path

    def _run_cdr3_sharing(self, chain: str, file_paths: List[str], output_base: Path) -> Tuple[List[str], List[str]]:
        df_all = pd.DataFrame(columns=["CDR3(pep)"])
        df_gb_all_v = pd.DataFrame(columns=["V"])
        df_n_all_v = pd.DataFrame(columns=["V"])
        df_gb_all_j = pd.DataFrame(columns=["J"])
        df_n_all_j = pd.DataFrame(columns=["J"])
        df_gb_all_vj = pd.DataFrame(columns=["vj"])
        df_n_all_vj = pd.DataFrame(columns=["vj"])

        for file_path in file_paths:
            param_col = os.path.basename(file_path)
            try:
                df = _try_read_csv(file_path, usecols=["CDR3(pep)", "V", "J", "copy"])
            except Exception:
                continue
            if df.empty:
                continue

            type_dict = {"CDR3(pep)": str, "V": str, "J": str, "copy": np.int32}
            df = df.astype(type_dict)

            df_gb = df[["V", "copy"]].groupby("V").sum()
            df_gb["copy"] = df_gb["copy"] / df_gb["copy"].sum()
            df_gb.rename(columns={"copy": param_col}, inplace=True)
            df_gb_all_v = pd.merge(df_gb_all_v, df_gb, how="outer", on="V")

            se_n = df["V"].value_counts(normalize=True)
            df_n = pd.DataFrame(data={"V": se_n.index, param_col: se_n.values})
            df_n_all_v = pd.merge(df_n_all_v, df_n, how="outer", on="V")

            df_gb_j = df[["J", "copy"]].groupby("J").sum()
            df_gb_j["copy"] = df_gb_j["copy"] / df_gb_j["copy"].sum()
            df_gb_j.rename(columns={"copy": param_col}, inplace=True)
            df_gb_all_j = pd.merge(df_gb_all_j, df_gb_j, how="outer", on="J")

            se_n_j = df["J"].value_counts(normalize=True)
            df_n_j = pd.DataFrame(data={"J": se_n_j.index, param_col: se_n_j.values})
            df_n_all_j = pd.merge(df_n_all_j, df_n_j, how="outer", on="J")

            se_vjcombin = df["V"] + ";" + df["J"]
            se_copy = df["copy"]
            df_vj_combine = pd.DataFrame({"vj": se_vjcombin.tolist(), "copy": se_copy.tolist()})
            df_gb_vj = df_vj_combine[["vj", "copy"]].groupby("vj").sum()
            df_gb_vj["copy"] = df_gb_vj["copy"] / df_gb_vj["copy"].sum()
            df_gb_vj.rename(columns={"copy": param_col}, inplace=True)
            df_gb_all_vj = pd.merge(df_gb_all_vj, df_gb_vj, how="outer", on="vj")

            se_n_vj = df_vj_combine["vj"].value_counts(normalize=True)
            df_n_vj = pd.DataFrame(data={"vj": se_n_vj.index, param_col: se_n_vj.values})
            df_n_all_vj = pd.merge(df_n_all_vj, df_n_vj, how="outer", on="vj")

            df.rename(columns={"copy": param_col}, inplace=True)
            concat_df = df[["CDR3(pep)", param_col]].groupby("CDR3(pep)").sum()
            df_all = pd.merge(df_all, concat_df, how="outer", on="CDR3(pep)")

        shared_paths: List[str] = []
        usage_paths: List[str] = []

        # Save shared CDR3 matrix
        shared_dir = output_base / "Pep_shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        shared_csv = shared_dir / f"{chain}.csv"
        df_all.to_csv(shared_csv, index=False)
        shared_paths.append(str(shared_csv))

        # Save usage matrices
        usage_mappings = [
            (df_gb_all_v, "1Vusage"),
            (df_gb_all_j, "1Jusage"),
            (df_n_all_v, "0Vusage"),
            (df_n_all_j, "0Jusage"),
            (df_n_all_vj, "0VJusage"),
            (df_gb_all_vj, "1VJusage"),
        ]
        for df_u, usage_type in usage_mappings:
            usage_dir = output_base / "usage" / usage_type
            usage_dir.mkdir(parents=True, exist_ok=True)
            idx_col = df_u.columns[0]
            df_u.index = df_u[idx_col].tolist()
            df_u_t = df_u.drop(columns=idx_col).T
            csv_path = usage_dir / f"{chain}.csv"
            df_u_t.to_csv(csv_path, index=True)
            usage_paths.append(str(csv_path))

        return shared_paths, usage_paths

    # ============================================================
    # Step 3: Add categories to shared CDR3
    # ============================================================
    @staticmethod
    def _add_cate_shared(src: Path, dst: Path, profile_df: pd.DataFrame, group_field: str) -> None:
        pep_df = _try_read_csv(src)
        cate_dict: Dict[str, list] = {"CDR3(pep)": ["category"]}
        sample_col = profile_df.columns[0]

        for pep_name in pep_df.columns[1:]:
            parts = pep_name.split("__")
            samplename = "__".join(parts[:-1]) if len(parts) > 1 else pep_name
            match = profile_df[profile_df[sample_col] == samplename]
            if not match.empty:
                val = match[group_field].values[0]
                cate_dict[pep_name] = [str(val) if pd.notna(val) else "nan"]

        remove_keys = [k for k, v in cate_dict.items() if v and v[0] == "nan"]
        for k in remove_keys:
            cate_dict.pop(k)

        cate_df = pd.DataFrame(cate_dict)
        pep_df = pd.concat([cate_df, pep_df[list(cate_dict.keys())]])
        dst.parent.mkdir(parents=True, exist_ok=True)
        pep_df.to_csv(dst, index=False)

    # ============================================================
    # Step 4: Add categories to usage matrices
    # ============================================================
    @staticmethod
    def _add_cate_usage(src: Path, dst: Path, profile_df: pd.DataFrame, group_field: str) -> None:
        df = _try_read_csv(src)
        sample_col = profile_df.columns[0]
        index_col = df.columns[0]
        vj_cate: List[str] = []
        use_file: List[str] = []

        for name_vj in df[index_col]:
            parts = str(name_vj).split("__")
            samplename = "__".join(parts[:-1]) if len(parts) > 1 else str(name_vj)
            match = profile_df[profile_df[sample_col] == samplename]
            if not match.empty:
                use_file.append(str(name_vj))
                val = match[group_field].values[0]
                vj_cate.append(str(val) if pd.notna(val) else "nan")

        clean_cate = []
        clean_files = []
        for item, fname in zip(vj_cate, use_file):
            if item != "nan":
                clean_cate.append(item)
                clean_files.append(fname)

        df_s = df[df[index_col].isin(clean_files)]
        df_s.insert(loc=1, column="Category", value=clean_cate)
        unique_cates = sorted(set(clean_cate))
        df_s["Category"] = pd.Categorical(df_s["Category"], categories=unique_cates, ordered=True)
        df_s = df_s.sort_values(by=["Category"])
        df_s.rename(columns={df_s.columns[0]: "sample"}, inplace=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        df_s.to_csv(dst, index=False)

    # ============================================================
    # Step 5: Heatmap with Mann-Whitney U test
    # ============================================================
    @staticmethod
    def _run_heatmap(src: Path, output_dir: Path, pvalue_threshold: float) -> Tuple[List[str], List[str]]:
        output_dir.mkdir(parents=True, exist_ok=True)
        df = _try_read_csv(src)
        df.fillna(0, inplace=True)

        category_col = "Category"
        if category_col not in df.columns:
            return [], []

        data_split_point = df.columns.get_loc(category_col) + 1
        class_dict: Dict[str, list] = {}
        for col_name in df.columns[1:data_split_point]:
            col_types = sorted(df[col_name].dropna().unique().tolist())
            class_dict[col_name] = [t for t in col_types if t != 0]

        p_value_all: Dict[str, list] = {}
        for colname, itemlist in class_dict.items():
            itemlist = sorted(itemlist)
            p_value_all[colname] = []
            for cb in list(combinations(itemlist, 2)):
                for param_col in df.columns[data_split_point:]:
                    try:
                        g_a = df[df[colname] == cb[0]][param_col].dropna()
                        g_b = df[df[colname] == cb[1]][param_col].dropna()
                        if len(g_a) == 0 or len(g_b) == 0:
                            continue
                        pvalue = mannwhitneyu(g_a, g_b, alternative="two-sided").pvalue
                        p_value_all[colname].append((cb[0], cb[1], param_col, pvalue))
                    except Exception:
                        continue

        heatmap_columns = sorted(list(df.columns[data_split_point:]), key=_reference_numeric_sort_key)
        threash_hold_s = pvalue_threshold / 10.0
        threash_hold_p = pvalue_threshold

        image_paths: List[str] = []
        csv_paths: List[str] = []

        for category, p_list in p_value_all.items():
            pre_mapdict: Dict[str, list] = {"category": []}
            for col in heatmap_columns:
                pre_mapdict[col] = []

            for pair in p_list:
                category_vs = f"{pair[0]} vs. {pair[1]}"
                if category_vs not in pre_mapdict["category"]:
                    pre_mapdict["category"].append(category_vs)
                if pair[3] > threash_hold_p:
                    pre_mapdict[pair[2]].append(0)
                    continue
                arr1_avg = np.mean(df[df[category] == pair[0]][pair[2]].values.astype(np.float64))
                arr2_avg = np.mean(df[df[category] == pair[1]][pair[2]].values.astype(np.float64))
                if arr1_avg > arr2_avg:
                    if pair[3] < threash_hold_s:
                        pre_mapdict[pair[2]].append(10)
                    else:
                        pre_mapdict[pair[2]].append(5)
                else:
                    if pair[3] < threash_hold_s:
                        pre_mapdict[pair[2]].append(-10)
                    else:
                        pre_mapdict[pair[2]].append(-5)

            # Pad all columns to same length
            max_len = max(len(v) for v in pre_mapdict.values())
            for col in pre_mapdict:
                if len(pre_mapdict[col]) < max_len:
                    pre_mapdict[col].extend([0] * (max_len - len(pre_mapdict[col])))

            pre_df = pd.DataFrame(pre_mapdict)
            pre_df.index = pre_df["category"]
            pre_df.drop(columns=["category"], inplace=True)

            heat_y = pre_df.shape[0]
            heat_x = pre_df.shape[1]

            if heat_x > 30:
                num_split = heat_x // 30 + 1
                for i in range(num_split):
                    if i == num_split - 1:
                        iso_df = pre_df[pre_df.columns[i * 30:]]
                    else:
                        iso_df = pre_df[pre_df.columns[i * 30:(i + 1) * 30]]
                    pre_x = len(iso_df.columns)
                    plt.subplots(figsize=(max(pre_x, 1), max(heat_y, 1)), dpi=120)
                    sns.heatmap(iso_df, cbar=False, linewidths=0.5, square=True,
                                cmap=MUTED_DIVERGING_CMAP, vmax=10, vmin=-10)
                    plt.ylim(0, heat_y)
                    plt.xlim(0, pre_x)
                    plt.yticks(rotation=0)
                    ax = plt.gca()
                    for spine in ax.spines.values():
                        spine.set_visible(True)
                    jpg_path = output_dir / f"{category}_{i}.jpg"
                    plt.savefig(jpg_path, bbox_inches="tight")
                    plt.clf()
                    plt.close("all")
                    image_paths.append(str(jpg_path))
            else:
                pre_x = len(pre_df.columns)
                plt.subplots(figsize=(max(pre_x, 1), max(heat_y, 1)), dpi=120)
                sns.heatmap(pre_df, cbar=False, linewidths=0.5, square=True,
                            cmap=MUTED_DIVERGING_CMAP, vmax=10, vmin=-10)
                plt.ylim(0, heat_y)
                plt.xlim(0, pre_x)
                plt.yticks(rotation=0)
                ax = plt.gca()
                for spine in ax.spines.values():
                    spine.set_visible(True)
                jpg_path = output_dir / f"{category}.jpg"
                plt.savefig(jpg_path, bbox_inches="tight")
                plt.clf()
                plt.close("all")
                image_paths.append(str(jpg_path))

            csv_dir = output_dir / "csv_file"
            csv_dir.mkdir(parents=True, exist_ok=True)
            csv_path = csv_dir / f"{category}.csv"
            pre_df.to_csv(csv_path)
            csv_paths.append(str(csv_path))

        return image_paths, csv_paths

    # ============================================================
    # Step 6: CDR3 classification statistics
    # ============================================================
    @staticmethod
    def _run_classification(src: Path, arr_dst: Path, prop_dst: Path,
                            min_sample_threshold: int) -> Tuple[Optional[str], Optional[str]]:
        df = _try_read_csv(src, low_memory=False)
        df.fillna(0, inplace=True)
        if df.shape[0] <= 1:
            return None, None

        category_dict: Dict[str, list] = {}
        for cate, idname in zip(df.iloc[0].tolist()[1:], df.iloc[0].index[1:].tolist()):
            category_dict.setdefault(str(cate), []).append(idname)

        df_nocate = df.drop(labels=0, axis=0)
        count_name_list: List[str] = []
        for cate, idnames in category_dict.items():
            ca = np.array(df_nocate[idnames].values, dtype=np.float32).astype(np.int32)
            df[f"{cate}__sum"] = [" "] + ca.sum(axis=1).tolist()
            ca[ca >= 1] = 1
            df[f"{cate}__count"] = [" "] + ca.sum(axis=1).tolist()

        for column in df.columns.tolist():
            if "count" in str(column).lower():
                count_name_list.append(column)

        all_num = np.sum(np.array(df[count_name_list].iloc[1:].values, dtype=np.float32).astype(np.int32), axis=1).tolist()
        all_num.insert(0, " ")
        df["all_num"] = all_num

        df_sort = df.iloc[1:].sort_values(by="all_num", ascending=False)
        df_sort = df_sort[df_sort["all_num"] > min_sample_threshold]

        cb_list: list = []
        for i in range(2, len(count_name_list) + 1):
            cb_list += list(combinations(count_name_list, i))
        cb_list = count_name_list + cb_list

        proportion_dict: Dict[Any, int] = {}
        df_t = pd.DataFrame(columns=df_sort.columns)
        category_list: list = []

        for cb in cb_list:
            other_list = deepcopy(count_name_list)
            if isinstance(cb, str):
                other_list.remove(cb)
                df_m = df_sort[df_sort[cb] != 0]
                for remove_type in other_list:
                    df_m = df_m[df_m[remove_type] == 0]
                pre_num = df_m.shape[0]
                proportion_dict[cb] = pre_num
                category_list += pre_num * [str(cb)]
                df_t = pd.concat([df_t, df_m])
                continue
            df_m = df_sort
            for item in cb:
                other_list.remove(item)
            for item in cb:
                df_m = df_m[df_m[item] != 0]
            for item in other_list:
                df_m = df_m[df_m[item] == 0]
            pre_num = df_m.shape[0]
            proportion_dict[str(cb)] = pre_num
            category_list += pre_num * [str(cb)]
            df_t = pd.concat([df_t, df_m])

        df_t["category"] = category_list
        df_top = pd.DataFrame(df.iloc[0]).T
        df_top["category"] = " "
        df_t = pd.concat([df_top, df_t])

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

    # ============================================================
    # Steps 5-8: Per-group optional helpers (called in parallel)
    # ============================================================

    def _run_step5_for_group(self, chains, usage_cate_base, field_dir, pvalue_threshold):
        """Step 5: Heatmap with Mann-Whitney U test for one group field."""
        images, csvs = [], []
        heatmap_base = field_dir / "heatmap"
        heatmap_base.mkdir(parents=True, exist_ok=True)
        for usage_type in ["0Vusage", "1Vusage", "0Jusage", "1Jusage", "0VJusage", "1VJusage"]:
            src_dir = usage_cate_base / usage_type
            if src_dir.exists():
                for chain in chains:
                    src = src_dir / f"{chain}.csv"
                    if src.exists():
                        h_imgs, h_csvs = self._run_heatmap(
                            src, heatmap_base / usage_type / chain, pvalue_threshold
                        )
                        images.extend(h_imgs)
                        csvs.extend(h_csvs)
        return images, csvs

    def _run_step6_for_group(self, chains, pep_shared_cate_dir, field_dir, min_sample_threshold):
        """Step 6: CDR3 classification statistics for one group field."""
        arr_paths, prp_paths = [], []
        arrage_base = field_dir / "arrage_pep" / "Pep_shared_cate" / "Pep_shared"
        prop_base = field_dir / "prop_pep" / "Pep_shared_cate" / "Pep_shared"
        arrage_base.mkdir(parents=True, exist_ok=True)
        prop_base.mkdir(parents=True, exist_ok=True)
        for chain in chains:
            src = pep_shared_cate_dir / f"{chain}.csv"
            if src.exists():
                arr_path, prp_path = self._run_classification(
                    src, arrage_base / f"{chain}.csv", prop_base / f"{chain}.csv",
                    min_sample_threshold
                )
                if arr_path:
                    arr_paths.append(arr_path)
                if prp_path:
                    prp_paths.append(prp_path)
        return arr_paths, prp_paths

    def _run_step7_for_group(self, chains, field_dir):
        """Step 7: CDR3 arrangement heatmap for one group field."""
        paths = []
        arrange_dir = field_dir / "CDR3_arrage_heatmap"
        arrange_dir.mkdir(parents=True, exist_ok=True)
        arrage_src_base = field_dir / "arrage_pep" / "Pep_shared_cate" / "Pep_shared"
        for chain in chains:
            arr_src = arrage_src_base / f"{chain}.csv"
            if arr_src.exists():
                png_path = self._run_arrange_heatmap(arr_src, arrange_dir / f"{chain}.png")
                if png_path:
                    paths.append(png_path)
        return paths

    def _run_step8_for_group(self, chains, field_dir):
        """Step 8: Plot heatmap (per-chain unique CDR3 heatmap + summary)."""
        paths = []
        arrage_base = field_dir / "arrage_pep" / "Pep_shared_cate" / "Pep_shared"
        output_dir = field_dir / "plot_heatmap"
        output_dir.mkdir(parents=True, exist_ok=True)

        payloads = []
        for chain in chains:
            src = arrage_base / f"{chain}.csv"
            if src.exists():
                try:
                    payload = self._read_plot_heatmap_data(src, chain)
                    payloads.append(payload)
                except Exception:
                    continue

        if not payloads:
            return paths

        vmax = self._get_plot_heatmap_vmax(payloads)

        for payload in payloads:
            out_path = self._plot_chain_heatmap(payload, vmax, output_dir)
            if out_path:
                paths.append(out_path)

        # Summary across all chains
        summary_path = self._plot_summary_heatmap(payloads, vmax, output_dir)
        if summary_path:
            paths.append(summary_path)

        return paths

    # ---- Step 8 helpers (from 8.plot_heatmap.py) ----

    @staticmethod
    def _read_plot_heatmap_data(data_path: Path, chain: str) -> Dict[str, Any]:
        import csv as csv_module
        with data_path.open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv_module.reader(handle))

        if len(rows) < 3:
            raise ValueError(f"Input CSV must contain two header rows: {data_path}")

        header = rows[0]
        group_row = rows[1]
        data_rows = rows[2:]

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

        all_categories = sorted(set(
            r[category_col].strip() for r in data_rows
            if len(r) > category_col
            and r[category_col].strip().endswith("__count")
            and not r[category_col].strip().startswith("(")
        ))
        if not all_categories:
            all_categories = sorted(set(
                r[category_col].strip() for r in data_rows
                if len(r) > category_col and r[category_col].strip()
            ))

        sections = []
        for category in all_categories:
            records = []
            sort_col_name = f"{category.replace('__count', '')}__sum"
            sort_col = header.index(sort_col_name) if sort_col_name in header else None

            for row in data_rows:
                if not row or len(row) <= category_col:
                    continue
                row_category = row[category_col].strip()
                if row_category != category:
                    continue

                values = [float(str(row[i]).strip() or 0) if i < len(row) else 0.0 for i in sample_idx]
                sort_value = float(str(row[sort_col]).strip() or 0) if sort_col is not None else sum(values)
                records.append({
                    "chain": chain,
                    "cdr3": row[cdr3_col].strip(),
                    "category": row_category,
                    "values": values,
                    "sort_value": sort_value,
                })

            records.sort(key=lambda item: (item["sort_value"], sum(item["values"])), reverse=True)
            top_n = 20
            records = records[:top_n]

            # Normalize rows
            matrix = []
            for rec in records:
                vmax_r = max(rec["values"]) if rec["values"] else 0.0
                if vmax_r <= 0:
                    matrix.append([0.0 for _ in rec["values"]])
                else:
                    matrix.append([v / vmax_r for v in rec["values"]])

            sections.append({
                "category": category,
                "title": f"{category.replace('__count', '')} unique",
                "records": records,
                "matrix": matrix,
                "selected_count": len(records),
            })

        return {
            "chain": chain,
            "sections": sections,
            "sample_names": sample_names,
            "sample_groups": sample_groups,
        }

    @staticmethod
    def _get_plot_heatmap_vmax(payloads):
        vmax = 0.0
        for payload in payloads:
            for section in payload["sections"]:
                for row in section["matrix"]:
                    if row:
                        vmax = max(vmax, max(row))
        return vmax if vmax > 0 else 1.0

    @staticmethod
    def _plot_chain_heatmap(payload, color_vmax, output_dir):
        chain = payload["chain"]
        total_plotted = sum(len(s["records"]) for s in payload["sections"])
        if total_plotted == 0:
            return None

        cmap = MUTED_BLUE_RED_CMAP

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
        ax.set_xticklabels(labels, fontsize=8.5, fontweight="bold")

        # Y-axis with CDR3 labels
        label_font_size = 6.6 if n_rows <= 50 else 5.3
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
        cbar.ax.tick_params(labelsize=7.2, length=1.8, width=0.6)
        for tl in cbar.ax.get_yticklabels():
            tl.set_fontweight("bold")
        cbar.outline.set_linewidth(0.6)

        out_path = output_dir / f"{chain}_CT_SRMCY_unique_heatmap.png"
        fig.savefig(out_path, dpi=600, bbox_inches="tight")
        plt.close(fig)
        return str(out_path)

    @staticmethod
    def _plot_summary_heatmap(payloads, color_vmax, output_dir):
        payloads = [p for p in payloads
                    if sum(len(s["records"]) for s in p["sections"]) > 0]
        if not payloads:
            return None

        cmap = MUTED_BLUE_RED_CMAP

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
        ax.set_xticklabels(labels, fontsize=8.5, fontweight="bold")

        label_font_size = 5.8 if n_rows <= 80 else 4.8
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
        cbar.ax.tick_params(labelsize=7.2, length=1.8, width=0.6)
        for tl in cbar.ax.get_yticklabels():
            tl.set_fontweight("bold")
        cbar.outline.set_linewidth(0.6)

        out_path = output_dir / "ALL_CT_SRMCY_unique_heatmap_summary.png"
        fig.savefig(out_path, dpi=600, bbox_inches="tight")
        plt.close(fig)
        return str(out_path)

    @staticmethod
    def _run_arrange_heatmap(src: Path, dst: Path) -> Optional[str]:
        df = _try_read_csv(src)
        if df.shape[0] == 1:
            return None

        data_end = 0
        for i, val in enumerate(df.iloc[0]):
            if str(val).strip() == " ":
                data_end = i
                break
        if data_end == 0:
            return None

        df_s = df[df.columns[1:data_end]].iloc[1:]
        df_s = df_s.apply(pd.to_numeric, errors="coerce").fillna(0)
        df_s[df_s > 1] = 1

        plt.figure(figsize=(20, 8))
        try:
            sns.set_palette("pastel")
            ax = sns.heatmap(df_s, square=False, cmap=MUTED_BLUE_RED_CMAP,
                             cbar_kws={"aspect": 100, "pad": 0.0005}, cbar=False)
            ax.get_yaxis().set_visible(False)
            plt.rcParams.update({"xtick.labelsize": 11, "ytick.labelsize": 11, "font.weight": "bold"})
            dst.parent.mkdir(parents=True, exist_ok=True)
            ax.figure.savefig(dst, bbox_inches="tight", dpi=600)
            plt.clf()
            plt.close("all")
            return str(dst)
        except Exception:
            plt.clf()
            plt.close("all")
            return None

    # ============================================================
    # Helpers
    # ============================================================
    @staticmethod
    def _allocate_job_id(name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{name}_{ts}"
