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

SUPPORTED_CHAINS = {"IGH", "IGK", "IGL", "TRA", "TRB", "TRD", "TRG"}


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
        progress_callback=None,
    ) -> PepAnalysisReport:
        pep_dir = Path(pep_data_dir)
        if not pep_dir.exists():
            raise FileNotFoundError(f"Pep data directory not found: {pep_data_dir}")

        profile_file = Path(profile_path)
        if not profile_file.exists():
            raise FileNotFoundError(f"Profile file not found: {profile_path}")

        profile_df = pd.read_csv(profile_file, low_memory=False)
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
        chain_files: Dict[str, List[str]] = {}
        for root, dirs, filenames in os.walk(str(pep_dir)):
            for filename in filenames:
                if not filename.endswith(".csv"):
                    continue
                for chain in chains:
                    if f"__{chain}.csv" in filename or filename.endswith(f"__{chain}.csv"):
                        chain_files.setdefault(chain, []).append(os.path.join(root, filename))
                        break

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

        # ---- Steps 3-7: Per group field ----
        heatmap_image_paths: List[str] = []
        heatmap_csv_paths: List[str] = []
        classification_paths: List[str] = []
        proportion_paths: List[str] = []
        arrange_heatmap_paths: List[str] = []

        for gf in group_fields:
            field_dir = output_base / gf
            field_dir.mkdir(parents=True, exist_ok=True)

            # Step 3: Add category to shared CDR3
            _progress(f"Step 3 [{gf}]: Adding categories to shared CDR3", {"step": 3, "group_field": gf})
            shared_dir = output_base / "Pep_shared"
            pep_shared_cate_dir = field_dir / "Pep_shared_cate" / "Pep_shared"
            pep_shared_cate_dir.mkdir(parents=True, exist_ok=True)
            for chain in chains:
                src = shared_dir / f"{chain}.csv"
                if src.exists():
                    self._add_cate_shared(src, pep_shared_cate_dir / f"{chain}.csv", profile_df, gf)

            # Step 4: Add category to usage
            _progress(f"Step 4 [{gf}]: Adding categories to usage matrices", {"step": 4, "group_field": gf})
            usage_dir = output_base / "usage"
            usage_cate_base = field_dir / "usage_cate" / "usage"
            usage_cate_base.mkdir(parents=True, exist_ok=True)
            for usage_type in ["0Vusage", "1Vusage", "0Jusage", "1Jusage", "0VJusage", "1VJusage"]:
                src_usage_dir = usage_dir / usage_type
                dst_usage_dir = usage_cate_base / usage_type
                if src_usage_dir.exists():
                    dst_usage_dir.mkdir(parents=True, exist_ok=True)
                    for chain in chains:
                        src = src_usage_dir / f"{chain}.csv"
                        if src.exists():
                            self._add_cate_usage(src, dst_usage_dir / f"{chain}.csv", profile_df, gf)

            # Step 5: Heatmap with Mann-Whitney U test
            _progress(f"Step 5 [{gf}]: V/J/VJ usage heatmaps", {"step": 5, "group_field": gf})
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
                            heatmap_image_paths.extend(h_imgs)
                            heatmap_csv_paths.extend(h_csvs)

            # Step 6: CDR3 classification statistics
            _progress(f"Step 6 [{gf}]: CDR3 classification statistics", {"step": 6, "group_field": gf})
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
                        classification_paths.append(arr_path)
                    if prp_path:
                        proportion_paths.append(prp_path)

            # Step 7: CDR3 arrangement heatmap
            _progress(f"Step 7 [{gf}]: CDR3 arrangement heatmaps", {"step": 7, "group_field": gf})
            arrange_dir = field_dir / "CDR3_arrage_heatmap"
            arrange_dir.mkdir(parents=True, exist_ok=True)
            for chain in chains:
                arr_src = arrage_base / f"{chain}.csv"
                if arr_src.exists():
                    png_path = self._run_arrange_heatmap(arr_src, arrange_dir / f"{chain}.png")
                    if png_path:
                        arrange_heatmap_paths.append(png_path)

        # ---- Generate ZIP ----
        zip_path = output_base / "pep_analysis_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in shared_matrix_paths + usage_paths + heatmap_image_paths + \
                     heatmap_csv_paths + classification_paths + proportion_paths + arrange_heatmap_paths:
                fp = Path(p)
                if fp.exists():
                    arcname = str(fp.relative_to(output_base))
                    zf.write(fp, arcname)

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "pep_data_dir": str(pep_dir),
            "profile_path": str(profile_file),
            "group_fields": group_fields,
            "selected_chains": chains,
            "pvalue_threshold": pvalue_threshold,
            "min_sample_threshold": min_sample_threshold,
            "chain_file_counts": {c: len(chain_files.get(c, [])) for c in chains},
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
            zip_path=str(zip_path),
            metadata=metadata,
        )

    # ============================================================
    # Step 2: CDR3 Sharing Analysis
    # ============================================================
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
                df = pd.read_csv(file_path, usecols=["CDR3(pep)", "V", "J", "copy"])
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
        pep_df = pd.read_csv(src)
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
        df = pd.read_csv(src)
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
        df = pd.read_csv(src)
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
                        if len(g_a) < 2 or len(g_b) < 2:
                            continue
                        pvalue = mannwhitneyu(g_a, g_b, alternative="two-sided").pvalue
                        p_value_all[colname].append((cb[0], cb[1], param_col, pvalue))
                    except Exception:
                        continue

        heatmap_columns = list(df.columns[data_split_point:])
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
                    plt.subplots(figsize=(pre_x, heat_y), dpi=120)
                    sns.heatmap(iso_df, cbar=False, linewidths=0.5, square=True,
                                cmap="coolwarm", vmax=10, vmin=-10)
                    plt.ylim(0, heat_y)
                    plt.xlim(0, pre_x)
                    plt.yticks(rotation=0)
                    jpg_path = output_dir / f"{category}_{i}.jpg"
                    plt.savefig(jpg_path, bbox_inches="tight")
                    plt.clf()
                    plt.close("all")
                    image_paths.append(str(jpg_path))
            else:
                pre_x = len(pre_df.columns)
                plt.subplots(figsize=(pre_x, heat_y), dpi=120)
                sns.heatmap(pre_df, cbar=False, linewidths=0.5, square=True,
                            cmap="coolwarm", vmax=10, vmin=-10)
                plt.ylim(0, heat_y)
                plt.xlim(0, pre_x)
                plt.yticks(rotation=0)
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
        df = pd.read_csv(src, low_memory=False)
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
    # Step 7: CDR3 arrangement heatmap
    # ============================================================
    @staticmethod
    def _run_arrange_heatmap(src: Path, dst: Path) -> Optional[str]:
        df = pd.read_csv(src)
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
            ax = sns.heatmap(df_s, square=False, cmap="BuGn",
                             cbar_kws={"aspect": 100, "pad": 0.0005}, cbar=False)
            ax.get_yaxis().set_visible(False)
            plt.rcParams.update({"xtick.labelsize": 10})
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
