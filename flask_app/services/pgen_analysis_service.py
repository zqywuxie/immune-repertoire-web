"""
Pgen analysis service based on _reference/anal_pipeline/Pgen_260213.

The workflow uses SoNNia when available to evaluate CDR3/V/J triples from
registered PEP assets and summarizes mean Pgen values by sample and chain.
"""

from __future__ import annotations

import json
import os
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde, ks_2samp

from flask_app.services.figure_style import (
    MUTED_BLUE_RED_CMAP,
    MUTED_CATEGORY_COLORS,
    PALETTE,
    apply_publication_style,
    save_publication_png,
    soften_axes,
)


_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]
SUPPORTED_CHAINS = {"IGH", "IGK", "IGL", "TRA", "TRB", "TRD", "TRG"}
SKIPPED_SONNIA_CHAINS = {"TRD", "TRG"}

apply_publication_style(font_size=10, axes_linewidth=0.9)


def _try_read_table(filepath, **kwargs):
    suffix = str(filepath).lower()
    sep = kwargs.pop("sep", ",")
    if suffix.endswith((".tsv", ".tsv.gz")):
        sep = "\t"
    if suffix.endswith((".xlsx", ".xls", ".xlsm")):
        kwargs.pop("low_memory", None)
        return pd.read_excel(filepath, sheet_name=kwargs.pop("sheet_name", 0), **kwargs)
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(filepath, encoding=enc, sep=sep, compression="infer", **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(filepath, sep=sep, compression="infer", **kwargs)


def _strip_table_suffix(filename: str) -> str:
    name = str(filename or "")
    lowered = name.lower()
    for suffix in (".csv.gz", ".tsv.gz", ".txt.gz", ".csv", ".tsv", ".txt", ".xlsx", ".xls", ".xlsm"):
        if lowered.endswith(suffix):
            return name[:-len(suffix)]
    return Path(name).stem


def _normalize_chain(value: str) -> str:
    value = str(value or "").strip().upper()
    return {"TCRA": "TRA", "TCRB": "TRB"}.get(value, value)


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


def _sample_name_from_file(path: Path, chain: str) -> str:
    stem = _strip_table_suffix(path.name)
    upper = stem.upper()
    for marker in (f"__{chain}", f"_{chain}", f"-{chain}"):
        index = upper.rfind(marker)
        if index > 0:
            return stem[:index].rstrip("_- ")
    if _normalize_chain(path.parent.name) == chain:
        return stem
    return Path(stem).stem


def _batch_name_from_file(path: Path, batch_values: Optional[set[str]]) -> Optional[str]:
    if not batch_values:
        return None
    matches = [parent.name.strip() for parent in path.parents
               if parent.name.strip() in batch_values and parent.name.upper() not in SUPPORTED_CHAINS]
    if len(matches) > 1:
        raise ValueError(f"PEP 文件路径匹配到多个批次目录：{path}")
    return matches[0] if matches else None


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.=-]+", "_", str(value or "pgen")).strip("_")
    return safe or "pgen"


@dataclass
class PgenAnalysisReport:
    job_id: str
    output_base: Path
    detail_paths: List[str]
    csv_paths: List[str]
    png_paths: List[str]
    pdf_paths: List[str]
    zip_path: str
    metadata: Dict[str, Any]


class PgenAnalysisService:
    """Run the SoNNia Pgen workflow over registered PEP and Profile assets."""

    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    @staticmethod
    def dependency_status() -> Dict[str, Any]:
        try:
            import sonnia  # noqa: F401
            from sonnia.processing import Processing  # noqa: F401
            from sonnia.sonnia import SoNNia  # noqa: F401
            return {"available": True, "message": "生成概率运行环境已就绪。"}
        except Exception as exc:
            return {
                "available": False,
                "message": "生成概率运行环境未就绪，请联系管理员检查分析镜像中的 SoNNia 及模型依赖。",
                "error": str(exc),
            }

    def generate_report(
        self,
        *,
        pep_data_dir: str,
        pep_paths: Optional[List[str]] = None,
        profile_path: str,
        selected_chains: List[str],
        species: str = "human",
        sample_col: str = "sample",
        batch_field: Optional[str] = None,
        distribution_category_col: Optional[str] = None,
        selected_samples: Optional[List[str]] = None,
        selected_group_values: Optional[Dict[str, List[str]]] = None,
        selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
        group_sample_identity: str = "sample",
        output_name: Optional[str] = None,
        progress_callback=None,
    ) -> PgenAnalysisReport:
        dep = self.dependency_status()
        if not dep["available"]:
            raise RuntimeError(dep["message"])

        from sonnia.processing import Processing
        from sonnia.sonnia import SoNNia

        pep_dir = Path(pep_data_dir)
        if not pep_dir.exists():
            raise FileNotFoundError(f"PEP data directory not found: {pep_data_dir}")
        profile_file = Path(profile_path)
        if not profile_file.exists() or not profile_file.is_file():
            raise FileNotFoundError(f"Profile file not found: {profile_path}")

        profile_df = _try_read_table(profile_file, low_memory=False, dtype=str)
        sample_col = self._resolve_sample_column(profile_df, sample_col)
        batch_field = str(batch_field or "").strip() or None
        if batch_field and batch_field not in profile_df.columns:
            raise ValueError(f"Batch column not found: {batch_field}")
        if batch_field == sample_col:
            raise ValueError("Batch column must differ from the sample column")
        profile_df[sample_col] = profile_df[sample_col].astype("string").str.strip()
        if profile_df[sample_col].isna().any() or profile_df[sample_col].eq("").any():
            raise ValueError("Profile contains empty sample IDs")
        profile_keys = [sample_col] + ([batch_field] if batch_field else [])
        if batch_field:
            profile_df[batch_field] = profile_df[batch_field].astype("string").str.strip()
            if profile_df[batch_field].isna().any() or profile_df[batch_field].eq("").any():
                raise ValueError("Profile contains empty batch values")
        profile_batch_values = set(profile_df[batch_field].astype(str)) if batch_field else None
        if not batch_field and profile_df[sample_col].duplicated().any():
            raise ValueError("Profile contains duplicate sample IDs; select a batch field")
        if profile_df.duplicated(profile_keys).any():
            raise ValueError("Profile contains duplicate batch and sample IDs")
        distribution_category_col = self._resolve_distribution_category_column(
            profile_df,
            sample_col,
            distribution_category_col,
        )
        if not isinstance(group_sample_identity, str) or group_sample_identity not in {"sample", "batch_sample"} or (group_sample_identity == "batch_sample" and not batch_field):
            raise ValueError("批次样本选择需要有效的批次字段与编号方式")
        if group_sample_identity == "batch_sample":
            from flask_app.services.pep_analysis_service import _batch_sample_identity
            selection_ids = pd.Series([_batch_sample_identity(batch, sample)
                for sample, batch in profile_df[[sample_col, batch_field]].itertuples(index=False, name=None)], index=profile_df.index)
        else:
            selection_ids = profile_df[sample_col]
        selected_samples = {str(value).strip() for value in (selected_samples or []) if str(value).strip()}
        selected_group_values = selected_group_values or {}
        selected_samples_by_group = selected_samples_by_group or {}
        if selected_samples:
            profile_df = profile_df[profile_df[sample_col].isin(selected_samples)].copy()
        group_values = selected_group_values.get(distribution_category_col, [])
        if group_values:
            profile_df = profile_df[profile_df[distribution_category_col].astype(str).isin(set(map(str, group_values)))].copy()
        group_samples = selected_samples_by_group.get(distribution_category_col, {})
        if group_samples:
            keep = pd.Series(False, index=profile_df.index)
            for group_value, samples in group_samples.items():
                sample_set = set(map(str, samples))
                keep |= (
                    profile_df[distribution_category_col].astype(str).eq(str(group_value))
                    & selection_ids.loc[profile_df.index].isin(sample_set)
                )
            profile_df = profile_df[keep].copy()
        if profile_df.empty:
            raise ValueError("No samples remain after applying the selected group and sample filters")

        chains = [_normalize_chain(chain) for chain in selected_chains if _normalize_chain(chain) in SUPPORTED_CHAINS]
        chains = [chain for chain in dict.fromkeys(chains) if chain not in SKIPPED_SONNIA_CHAINS]
        if not chains:
            raise ValueError("No supported SoNNia chain selected. TRD/TRG are skipped by the reference workflow.")

        sources = [Path(value).expanduser() for value in (pep_paths or [pep_data_dir]) if str(value).strip()]
        files_by_chain = self._collect_pep_files(sources, chains)
        if not any(files_by_chain.values()):
            raise ValueError("No matching PEP files found for selected chains")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        from flask_app.services.project_storage_paths import allocate_result_dir
        job_id, output_base = allocate_result_dir(self.output_parent, "pgen-analysis")
        detail_base = output_base / "Pgen"
        detail_base.mkdir(parents=True, exist_ok=True)

        detail_paths: List[str] = []
        png_paths: List[str] = []
        pdf_paths: List[str] = []
        processed: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        pgen_values: Dict[Tuple[str, ...], Dict[str, float]] = {}
        selected_identities = set(map(tuple, profile_df[profile_keys].astype(str).itertuples(index=False, name=None)))
        batch_values = profile_batch_values
        seen_files: set[Tuple[str, ...]] = set()
        total_files = sum(len(items) for items in files_by_chain.values())
        done = 0

        for chain in chains:
            colname = f"Pgen_{chain}"
            model_name = f"{species}{chain}"
            model_ref = self._sonnia_model_reference(model_name)
            processor = Processing(pgen_model=model_ref)
            self._repair_sonnia_windows_gene_sets(processor, model_ref)
            for pep_file in files_by_chain.get(chain, []):
                done += 1
                sample = _sample_name_from_file(pep_file, chain)
                batch = _batch_name_from_file(pep_file, batch_values)
                identity = (sample, batch) if batch_field else (sample,)
                if batch_field and batch is None and any(key[0] == sample for key in selected_identities):
                    raise ValueError(f"PEP file {pep_file.name} did not match a batch directory")
                if identity not in selected_identities:
                    continue
                file_identity = identity + (chain,)
                if file_identity in seen_files:
                    raise ValueError(f"Duplicate PEP file for sample/batch/chain: {file_identity}")
                seen_files.add(file_identity)
                if progress_callback:
                    pct = 8 + int(done / max(total_files, 1) * 76)
                    progress_callback(pct, "生成概率计算", f"正在计算 {batch + ' / ' if batch_field else ''}{sample} / {chain}")

                prepared = self._prepare_pep_dataframe(pep_file)
                if prepared.empty:
                    skipped.append({
                        "file": str(pep_file),
                        "sample": sample,
                        "chain": chain,
                        "reason": "no CDR3/V/J rows after parsing",
                    })
                    continue
                filtered = processor.filter_dataframe(prepared)
                if filtered.empty:
                    skipped.append({
                        "file": str(pep_file),
                        "sample": sample,
                        "chain": chain,
                        "reason": "all rows removed by SoNNia quality filters",
                        "input_rows": int(prepared.shape[0]),
                    })
                    continue
                data_seqs = filtered.values.astype(str)
                model = SoNNia(data_seqs=data_seqs, pgen_model=model_ref, seed=42)
                # SoNNia 0.3.1 accepts processes but does not assign it.
                # Limit parallel OLGA workers within each queued analysis.
                model.processes = 1
                q_data, pgen_data, ppost_data = model.evaluate_seqs(model.data_seqs)

                detail_df = pd.DataFrame(model.data_seqs, columns=["CDR3(pep)", "V", "J"])
                detail_df.insert(3, "Pgen", pgen_data)
                detail_df.insert(4, "Q", q_data)
                detail_df.insert(5, "Ppost", ppost_data)
                detail_df["V"] = detail_df["V"].map(lambda value: self._prefix_gene(chain, value))
                detail_df["J"] = detail_df["J"].map(lambda value: self._prefix_gene(chain, value))

                sample_dir = detail_base / (_safe_name(batch) if batch_field else "") / _safe_name(sample)
                sample_dir.mkdir(parents=True, exist_ok=True)
                detail_path = sample_dir / f"{chain}.csv"
                detail_df.to_csv(detail_path, index=False, encoding="utf-8-sig")
                detail_paths.append(str(detail_path))

                mean_value = float(pd.to_numeric(detail_df["Pgen"], errors="coerce").mean())
                pgen_values.setdefault(identity, {})[colname] = mean_value
                record = {
                    "sample": sample,
                    "chain": chain,
                    "sequence_count": int(detail_df.shape[0]),
                    "mean_pgen": mean_value,
                    "detail_path": str(detail_path),
                }
                if batch_field:
                    record["batch"] = batch
                processed.append(record)

        if not processed:
            detail = "; ".join(
                f"{Path(item['file']).name} ({item['chain']}): {item['reason']}"
                for item in skipped[:8]
            )
            raise ValueError(f"No valid sequences were evaluated by SoNNia. {detail}".strip())

        if progress_callback:
            progress_callback(88, "生成概率汇总", "正在整理样本均值与序列明细")

        pgen_rows = [
            {sample_col: identity[0], **({batch_field: identity[1]} if batch_field else {}), **values}
            for identity, values in pgen_values.items()
        ]
        pgen_df = pd.DataFrame(pgen_rows, columns=profile_keys + [f"Pgen_{chain}" for chain in chains])
        merged = profile_df.merge(pgen_df, on=profile_keys, how="inner", validate="one_to_one")
        mean_path = output_base / "Pgen_mean.csv"
        merged.to_csv(mean_path, index=False, encoding="utf-8-sig")

        detail_index_path = output_base / "Pgen_detail_index.csv"
        pd.DataFrame(processed).to_csv(detail_index_path, index=False, encoding="utf-8-sig")

        self._plot_mean_by_chain(pd.DataFrame(processed), output_base, png_paths, pdf_paths)
        self._plot_sample_heatmap(merged, sample_col, output_base, png_paths, pdf_paths, batch_field=batch_field)

        distribution_csv_paths = self._plot_public_pgen_distributions(
            processed_records=processed,
            profile_df=profile_df,
            sample_col=sample_col,
            batch_field=batch_field,
            category_col=distribution_category_col,
            output_base=output_base,
            png_paths=png_paths,
        )

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "module": "pgen-analysis",
            "species": species,
            "pep_data_dir": str(pep_dir.resolve()),
            "profile_path": str(profile_file.resolve()),
            "sample_col": sample_col,
            "batch_field": batch_field,
            "group_sample_identity": group_sample_identity,
            "distribution_category_col": distribution_category_col,
            "selected_chains": chains,
            "skipped_chains": [chain for chain in selected_chains if _normalize_chain(chain) in SKIPPED_SONNIA_CHAINS],
            "sample_count": int(len(pgen_values)),
            "batch_count": int(profile_df[batch_field].nunique()) if batch_field else None,
            "processed_file_count": len(processed),
            "skipped_file_count": len(skipped),
            "skipped_files": skipped,
            "detail_file_count": len(detail_paths),
            "summary_csv": str(mean_path),
            "output_counts": {
                "detail_csv": len(detail_paths),
                "summary_csv": 2,
                "distribution_csv": len(distribution_csv_paths),
                "plots": len(png_paths),
                "distribution_plots": len([
                    path for path in png_paths
                    if "/pgen_distribution/" in str(path).replace("\\", "/")
                ]),
            },
        }
        metadata_path = output_base / "pgen_analysis_metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        csv_paths = [str(mean_path), str(detail_index_path), *distribution_csv_paths, str(metadata_path)]
        zip_path = output_base / "pgen_analysis_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in [Path(p) for p in csv_paths + detail_paths + png_paths]:
                if file_path.exists():
                    zf.write(file_path, file_path.relative_to(output_base).as_posix())

        if progress_callback:
            progress_callback(100, "Pgen analysis", "Completed")

        return PgenAnalysisReport(
            job_id=job_id,
            output_base=output_base,
            detail_paths=detail_paths,
            csv_paths=csv_paths,
            png_paths=png_paths,
            pdf_paths=pdf_paths,
            zip_path=str(zip_path),
            metadata=metadata,
        )

    @staticmethod
    def _resolve_distribution_category_column(
        df: pd.DataFrame,
        sample_col: str,
        preferred: Optional[str],
    ) -> str:
        if preferred and preferred in df.columns and preferred != sample_col:
            return preferred
        lower_map = {str(col).strip().lower(): col for col in df.columns}
        if preferred and preferred.strip().lower() in lower_map:
            candidate = lower_map[preferred.strip().lower()]
            if candidate != sample_col:
                return candidate
        for candidate in ("Symptoms", "Category", "category", "group", "Group", "therapy", "disease"):
            if candidate in df.columns and candidate != sample_col:
                return candidate
            lowered = candidate.lower()
            if lowered in lower_map and lower_map[lowered] != sample_col:
                return lower_map[lowered]
        for column in df.columns:
            if column != sample_col:
                return str(column)
        return ""

    @staticmethod
    def _resolve_sample_column(df: pd.DataFrame, preferred: str) -> str:
        if preferred in df.columns:
            return preferred
        lower_map = {str(col).strip().lower(): col for col in df.columns}
        for candidate in ("sample", "Sample", "SAMPLE"):
            if candidate.lower() in lower_map:
                return lower_map[candidate.lower()]
        raise ValueError(f"Sample column not found: {preferred}")

    @staticmethod
    def _collect_pep_files(pep_paths: List[Path], chains: List[str]) -> Dict[str, List[Path]]:
        result: Dict[str, List[Path]] = {chain: [] for chain in chains}
        seen: set[str] = set()
        for source in pep_paths:
            if not source.exists():
                continue
            candidates = [source] if source.is_file() else sorted(source.rglob("*"))
            for path in candidates:
                if not path.is_file() or not path.name.lower().endswith((".csv", ".csv.gz", ".tsv", ".tsv.gz")):
                    continue
                chain = _infer_chain_from_path(path)
                resolved = str(path.resolve())
                if chain in result and resolved not in seen:
                    result[chain].append(path)
                    seen.add(resolved)
        return result

    @staticmethod
    def _prepare_pep_dataframe(pep_file: Path) -> pd.DataFrame:
        df = _try_read_table(pep_file, low_memory=False)
        columns = {str(col).strip().lower(): col for col in df.columns}

        def _pick(*names: str) -> str:
            for name in names:
                if name.lower() in columns:
                    return columns[name.lower()]
            for lowered, original in columns.items():
                if any(name.lower() in lowered for name in names):
                    return original
            return ""

        cdr3_col = _pick("CDR3(pep)", "cdr3_pep", "cdr3aa", "cdr3_aa", "cdr3", "amino_acid")
        v_col = _pick("V", "v_gene", "vgene", "bestvgene", "v_call")
        j_col = _pick("J", "j_gene", "jgene", "bestjgene", "j_call")
        missing = [label for label, col in (("CDR3(pep)", cdr3_col), ("V", v_col), ("J", j_col)) if not col]
        if missing:
            raise ValueError(f"{pep_file.name} missing required columns: {', '.join(missing)}")

        out = df[[cdr3_col, v_col, j_col]].dropna().copy()
        out = out.drop_duplicates([cdr3_col, v_col, j_col])
        out.columns = ["amino_acid", "v_gene", "j_gene"]
        for col in ("amino_acid", "v_gene", "j_gene"):
            out[col] = out[col].astype(str).str.strip()
        out["amino_acid"] = out["amino_acid"].str.upper().str.replace(" ", "", regex=False)
        return out

    @staticmethod
    def _repair_sonnia_windows_gene_sets(processor: Any, model_name: str) -> None:
        """
        SoNNia 0.3.x parses anchor filenames with '/' separators internally.
        On Windows that can turn V/J anchors into D anchors, emptying all filters.
        """
        if os.name != "nt":
            return model_name
        try:
            from sonnia.processing import define_pgen_model, gene_to_num_str
        except Exception:
            return

        try:
            *_, pgen_dir = define_pgen_model(model_name, compute_norm=False, return_pgen_dir=True)
        except Exception:
            return

        pgen_path = Path(pgen_dir)
        for filename, attr, gene_type in (
            ("V_gene_CDR3_anchors.csv", "good_vs", "V"),
            ("J_gene_CDR3_anchors.csv", "good_js", "J"),
        ):
            anchor_path = pgen_path / filename
            if not anchor_path.exists():
                continue
            try:
                anchors = pd.read_csv(anchor_path)
                functional = anchors.loc[
                    anchors["function"].astype(str).str.upper().eq("F"),
                    "gene",
                ]
                genes = {gene_to_num_str(str(gene), gene_type) for gene in functional.dropna()}
            except Exception:
                continue
            if genes:
                setattr(processor, attr, genes)

    @staticmethod
    def _sonnia_model_reference(model_name: str) -> str:
        """
        Return a SoNNia model path that keeps SoNNia 0.3.x Windows path parsing valid.
        """
        if os.name != "nt":
            return model_name
        try:
            from sonnia.processing import define_pgen_model
            *_, pgen_dir = define_pgen_model(model_name, compute_norm=False, return_pgen_dir=True)
        except Exception:
            return model_name
        return str(Path(pgen_dir)).replace("\\", "/").rstrip("/") + "/"

    @staticmethod
    def _prefix_gene(chain: str, value: Any) -> str:
        text = str(value or "").upper()
        if text.startswith(chain):
            return text
        return f"{chain}{text}"

    @staticmethod
    def _plot_mean_by_chain(processed_df: pd.DataFrame, output_base: Path, png_paths: List[str], pdf_paths: List[str]) -> None:
        grouped = processed_df.groupby("chain", as_index=False)["mean_pgen"].mean().sort_values("chain")
        fig, ax = plt.subplots(figsize=(6.8, 4.6))
        ax.bar(grouped["chain"], grouped["mean_pgen"], color=PALETTE["blue"], edgecolor="white", linewidth=0.8)
        ax.set_xlabel("Chain")
        ax.set_ylabel("Mean Pgen")
        ax.set_title("Mean Pgen by Chain")
        soften_axes(ax)
        fig.tight_layout()
        png_path = output_base / "pgen_mean_by_chain.png"
        save_publication_png(fig, png_path)
        plt.close(fig)
        png_paths.append(str(png_path))

    @staticmethod
    def _plot_sample_heatmap(
        merged: pd.DataFrame, sample_col: str, output_base: Path,
        png_paths: List[str], pdf_paths: List[str], *, batch_field: Optional[str] = None,
    ) -> None:
        value_cols = [col for col in merged.columns if str(col).startswith("Pgen_")]
        if not value_cols:
            return
        identity_columns = [sample_col] + ([batch_field] if batch_field else [])
        matrix = merged[identity_columns + value_cols].copy()
        if batch_field:
            matrix[sample_col] = matrix[batch_field].astype(str) + " / " + matrix[sample_col].astype(str)
        matrix = matrix[[sample_col] + value_cols].set_index(sample_col)
        matrix = matrix.apply(pd.to_numeric, errors="coerce")
        if matrix.dropna(how="all").empty:
            return
        fig_h = max(4.6, min(14.0, 1.2 + matrix.shape[0] * 0.36))
        fig_w = max(5.8, min(12.0, 3.2 + matrix.shape[1] * 0.7))
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        im = ax.imshow(matrix.fillna(0).values, aspect="auto", cmap=MUTED_BLUE_RED_CMAP)
        ax.set_xticks(np.arange(len(value_cols)), value_cols, rotation=45, ha="right")
        ax.set_yticks(np.arange(matrix.shape[0]), matrix.index.astype(str))
        ax.set_title("Sample-level Mean Pgen")
        ax.set_xlabel("Pgen feature")
        ax.set_ylabel("Sample")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        fig.tight_layout()
        png_path = output_base / "pgen_sample_heatmap.png"
        save_publication_png(fig, png_path)
        plt.close(fig)
        png_paths.append(str(png_path))

    @staticmethod
    def _plot_public_pgen_distributions(
        *,
        processed_records: List[Dict[str, Any]],
        profile_df: pd.DataFrame,
        sample_col: str,
        category_col: str,
        output_base: Path,
        png_paths: List[str],
        batch_field: Optional[str] = None,
    ) -> List[str]:
        if not category_col or category_col not in profile_df.columns:
            return []

        output_dir = output_base / "pgen_distribution"
        output_dir.mkdir(parents=True, exist_ok=True)
        key_columns = [sample_col] + ([batch_field] if batch_field else [])
        sample_category: Dict[Any, str] = {}
        for _, row in profile_df[key_columns + [category_col]].dropna(how="any").iterrows():
            sample = str(row[sample_col]).strip()
            category = str(row[category_col]).strip()
            if sample and category and category.lower() != "nan":
                key = (sample, str(row[batch_field]).strip()) if batch_field else sample
                sample_category[key] = category

        if not sample_category:
            return []

        stats_by_classification: Dict[str, List[Dict[str, Any]]] = {"public": [], "all": []}
        records_by_chain: Dict[str, List[Tuple[Any, str, float]]] = defaultdict(list)
        samples_by_chain: Dict[str, set[Any]] = defaultdict(set)
        for item in processed_records:
            sample = str(item.get("sample") or "").strip()
            identity = (sample, str(item.get("batch") or "").strip()) if batch_field else sample
            chain = _normalize_chain(str(item.get("chain") or ""))
            detail_path = Path(str(item.get("detail_path") or ""))
            if not sample or not chain or not detail_path.exists():
                continue
            samples_by_chain[chain].add(identity)
            try:
                detail_df = _try_read_table(detail_path, usecols=["CDR3(pep)", "Pgen"])
            except Exception:
                continue
            for _, row in detail_df.iterrows():
                cdr3 = str(row.get("CDR3(pep)", "")).strip()
                pgen = pd.to_numeric(row.get("Pgen"), errors="coerce")
                if not cdr3 or cdr3.lower() == "nan" or not np.isfinite(pgen):
                    continue
                records_by_chain[chain].append((identity, cdr3, float(pgen)))

        comparison_records: List[Dict[str, Any]] = []
        for chain in sorted(samples_by_chain):
            chain_rows = records_by_chain[chain]
            chain_samples = samples_by_chain[chain]
            for classification in ("public", "all"):
                category_values, category_stats, meta = PgenAnalysisService._classify_public_pgen_by_category(
                    chain_rows,
                    sample_category,
                    available_samples=chain_samples,
                    public_only=classification == "public",
                )
                for category, stats in category_stats.items():
                    stats_by_classification[classification].append({
                        "chain": chain,
                        "category_column": category_col,
                        "classification": classification,
                        "category": category,
                        "samples": stats["samples"],
                        "threshold": stats["threshold"],
                        "total_cdr3": stats["total_cdr3"],
                        "public_cdr3": stats["public_cdr3"],
                        "selected_cdr3": stats["selected_cdr3"],
                        "public_nonzero": stats["public_nonzero"],
                        "median_neglog10_pgen": stats["median_neglog10_pgen"],
                        "q1_neglog10_pgen": stats["q1_neglog10_pgen"],
                        "q3_neglog10_pgen": stats["q3_neglog10_pgen"],
                        "total_rows": meta["total_rows"],
                        "matched_rows": meta["matched_rows"],
                        "zero_pgen": meta["zero_pgen"],
                    })
                out_path = PgenAnalysisService._plot_distribution_chain(
                    chain,
                    category_values,
                    category_stats,
                    category_col,
                    output_dir,
                    classification=classification,
                )
                if out_path:
                    png_paths.append(str(out_path))
                comparison_records.extend(PgenAnalysisService._compare_distribution_categories(
                    chain, category_values, classification
                ))

        if not any(stats_by_classification.values()):
            return []
        stats_paths = []
        for classification, records in stats_by_classification.items():
            if not records:
                continue
            stats_path = output_dir / f"pgen_{classification}_distribution_stats.csv"
            pd.DataFrame(records).to_csv(stats_path, index=False, encoding="utf-8-sig")
            stats_paths.append(str(stats_path))
        comparison_path = output_dir / "pgen_distribution_ks_comparisons.csv"
        pd.DataFrame(comparison_records, columns=[
            "chain", "classification", "category_1", "category_2", "n_1", "n_2",
            "ks_statistic", "p_value", "p_value_bh", "median_difference",
            "cliffs_delta", "pgen_cliffs_delta", "note",
        ]).to_csv(comparison_path, index=False, encoding="utf-8-sig")
        return [*stats_paths, str(comparison_path)]

    @staticmethod
    def _classify_public_pgen_by_category(
        rows: List[Tuple[Any, str, float]],
        sample_category: Dict[Any, str],
        *,
        available_samples: Optional[set[Any]] = None,
        public_only: bool = True,
    ) -> Tuple[Dict[str, np.ndarray], Dict[str, Dict[str, int]], Dict[str, int]]:
        cat_cdr3_samples: Dict[str, Dict[str, set[Any]]] = defaultdict(lambda: defaultdict(set))
        cat_pgen_values: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        category_samples: Dict[str, set[Any]] = defaultdict(set)
        total_rows = 0
        zero_pgen = 0

        for sample in available_samples or {sample for sample, _, _ in rows}:
            category = sample_category.get(sample)
            if category is not None:
                category_samples[category].add(sample)

        for sample, cdr3, pgen in rows:
            category = sample_category.get(sample)
            if category is None:
                continue
            total_rows += 1
            cat_cdr3_samples[category][cdr3].add(sample)
            if pgen > 0.0:
                cat_pgen_values[category][cdr3].append(pgen)
            else:
                zero_pgen += 1

        category_values: Dict[str, np.ndarray] = {}
        category_stats: Dict[str, Dict[str, int]] = {}
        for category in sorted(category_samples):
            cdr3_samples = cat_cdr3_samples[category]
            threshold = max(2, int(np.ceil(len(category_samples[category]) * 0.0)))
            public_cdr3s = {
                cdr3 for cdr3, samples in cdr3_samples.items()
                if len(samples) >= threshold
            }
            selected_cdr3s = public_cdr3s if public_only else set(cdr3_samples)
            vals = [
                -np.log10(float(np.median(cat_pgen_values[category][cdr3])))
                for cdr3 in sorted(selected_cdr3s)
                if cat_pgen_values[category][cdr3]
            ]
            arr = np.array(vals, dtype=np.float64) if vals else np.array([], dtype=np.float64)
            category_values[category] = arr
            category_stats[category] = {
                "samples": len(category_samples[category]),
                "threshold": threshold if public_only else 1,
                "total_cdr3": len(cdr3_samples),
                "public_cdr3": len(public_cdr3s),
                "selected_cdr3": len(selected_cdr3s),
                "public_nonzero": int(arr.size),
                "median_neglog10_pgen": float(np.median(arr)) if arr.size else np.nan,
                "q1_neglog10_pgen": float(np.percentile(arr, 25)) if arr.size else np.nan,
                "q3_neglog10_pgen": float(np.percentile(arr, 75)) if arr.size else np.nan,
            }

        return category_values, category_stats, {
            "total_rows": total_rows,
            "matched_rows": total_rows,
            "zero_pgen": zero_pgen,
        }

    @staticmethod
    def _compare_distribution_categories(
        chain: str,
        category_values: Dict[str, np.ndarray],
        classification: str,
    ) -> List[Dict[str, Any]]:
        categories = sorted(category_values)
        comparisons: List[Dict[str, Any]] = []
        for index, category_a in enumerate(categories):
            values_a = category_values[category_a]
            values_a = values_a[np.isfinite(values_a)]
            for category_b in categories[index + 1:]:
                values_b = category_values[category_b]
                values_b = values_b[np.isfinite(values_b)]
                if len(values_a) < 2 or len(values_b) < 2:
                    comparisons.append({
                        "chain": chain, "classification": classification,
                        "category_1": category_a, "category_2": category_b,
                        "n_1": len(values_a), "n_2": len(values_b),
                        "ks_statistic": np.nan, "p_value": np.nan, "p_value_bh": np.nan,
                        "median_difference": np.nan, "cliffs_delta": np.nan,
                        "pgen_cliffs_delta": np.nan,
                        "note": "比较跳过：至少一组的有效 CDR3 少于 2 个。",
                    })
                    continue
                test = ks_2samp(values_a, values_b, alternative="two-sided", method="auto")
                sorted_b = np.sort(values_b)
                greater = np.searchsorted(sorted_b, values_a, side="left").sum()
                less = (len(sorted_b) - np.searchsorted(sorted_b, values_a, side="right")).sum()
                delta = float((greater - less) / (len(values_a) * len(values_b)))
                comparisons.append({
                    "chain": chain, "classification": classification,
                    "category_1": category_a, "category_2": category_b,
                    "n_1": len(values_a), "n_2": len(values_b),
                    "ks_statistic": float(test.statistic), "p_value": float(test.pvalue),
                    "p_value_bh": np.nan,
                    "median_difference": float(np.median(values_a) - np.median(values_b)),
                    "cliffs_delta": delta, "pgen_cliffs_delta": -delta, "note": "",
                })
        valid = [index for index, row in enumerate(comparisons) if np.isfinite(row["p_value"])]
        if valid:
            ordered = sorted(valid, key=lambda index: comparisons[index]["p_value"])
            m = len(ordered)
            adjusted = [comparisons[index]["p_value"] * m / rank for rank, index in enumerate(ordered, 1)]
            adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
            for index, value in zip(ordered, adjusted):
                comparisons[index]["p_value_bh"] = float(min(1.0, value))
        return comparisons

    @staticmethod
    def _plot_distribution_chain(
        chain: str,
        category_values: Dict[str, np.ndarray],
        category_stats: Dict[str, Dict[str, int]],
        category_col: str,
        output_dir: Path,
        *,
        classification: str = "public",
    ) -> Optional[Path]:
        drawable: List[Tuple[int, str, np.ndarray, int]] = []
        for index, category in enumerate(sorted(category_values)):
            vals = category_values[category]
            vals = vals[np.isfinite(vals)]
            if len(vals) < 4 or np.unique(vals).size < 2:
                continue
            drawable.append((index, category, vals, category_stats[category]["public_nonzero"]))
        if not drawable:
            return None

        fig, ax = plt.subplots(figsize=(89 / 25.4, 63 / 25.4), constrained_layout=True)
        pooled = np.concatenate([vals for _, _, vals, _ in drawable])
        x_min, x_max = np.percentile(pooled, [0.5, 99.5])
        if not np.isfinite(x_min) or not np.isfinite(x_max) or x_min >= x_max:
            x_min, x_max = float(pooled.min()), float(pooled.max())
        pad = max((x_max - x_min) * 0.06, 0.2)
        x = np.linspace(x_min - pad, x_max + pad, 500)
        fill_curves = len(drawable) <= 3

        for index, category, vals, public_count in drawable:
            color = MUTED_CATEGORY_COLORS[index % len(MUTED_CATEGORY_COLORS)]
            try:
                kde = gaussian_kde(vals)
                y = kde(x)
            except Exception:
                continue
            ax.plot(x, y, color=color, linewidth=1.35, label=f"{category} (n={public_count:,})")
            if fill_curves:
                ax.fill_between(x, y, alpha=0.08, color=color, linewidth=0)
            median = float(np.median(vals))
            ax.plot(
                [median, median],
                [0, max(y) * 0.08],
                color=color,
                linewidth=0.9,
                solid_capstyle="butt",
            )

        if not ax.lines:
            plt.close(fig)
            return None
        ax.set_xlabel(f"-log10({chain} Pgen)", fontweight="bold")
        ax.set_ylabel("Density", fontweight="bold")
        ax.set_title(f"{chain} {classification.title()} CDR3s", loc="center", fontweight="bold", pad=4)
        ax.legend(loc="upper right", handlelength=1.2, borderaxespad=0.2, labelspacing=0.35)
        ax.tick_params(axis="both", direction="out")
        ax.margins(y=0.08)
        ax.set_xlim(x[0], x[-1])
        safe_col = _safe_name(category_col)
        out_path = output_dir / f"{chain}_{safe_col}_pgen_{classification}.png"
        save_publication_png(fig, out_path)
        plt.close(fig)
        return out_path

    def _allocate_job_id(self, output_name: str) -> str:
        base = _safe_name(output_name or "pgen_analysis")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = f"{base}_{stamp}"
        index = 1
        while (self.output_parent / candidate).exists():
            index += 1
            candidate = f"{base}_{stamp}_{index}"
        return candidate
