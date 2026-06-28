"""
Pgen analysis service based on _reference/anal_pipeline/Pgen_260213.

The workflow uses SoNNia when available to evaluate CDR3/V/J triples from
registered PEP assets and summarizes mean Pgen values by sample and chain.
"""

from __future__ import annotations

import json
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
from scipy.stats import gaussian_kde

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
            return {"available": True, "message": "SoNNia is available"}
        except Exception as exc:
            return {
                "available": False,
                "message": "SoNNia is not installed or cannot be imported. Install sonnia to run Pgen analysis.",
                "error": str(exc),
            }

    def generate_report(
        self,
        *,
        pep_data_dir: str,
        profile_path: str,
        selected_chains: List[str],
        species: str = "human",
        sample_col: str = "sample",
        distribution_category_col: Optional[str] = None,
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

        profile_df = _try_read_table(profile_file, low_memory=False)
        sample_col = self._resolve_sample_column(profile_df, sample_col)
        profile_df[sample_col] = profile_df[sample_col].astype(str)
        distribution_category_col = self._resolve_distribution_category_column(
            profile_df,
            sample_col,
            distribution_category_col,
        )

        chains = [_normalize_chain(chain) for chain in selected_chains if _normalize_chain(chain) in SUPPORTED_CHAINS]
        chains = [chain for chain in dict.fromkeys(chains) if chain not in SKIPPED_SONNIA_CHAINS]
        if not chains:
            raise ValueError("No supported SoNNia chain selected. TRD/TRG are skipped by the reference workflow.")

        files_by_chain = self._collect_pep_files(pep_dir, chains)
        if not any(files_by_chain.values()):
            raise ValueError("No matching PEP files found for selected chains")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name or "pgen_analysis")
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)
        detail_base = output_base / "Pgen"
        detail_base.mkdir(parents=True, exist_ok=True)

        detail_paths: List[str] = []
        png_paths: List[str] = []
        pdf_paths: List[str] = []
        processed: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        pgen_mean: Dict[str, Dict[str, float]] = {}
        total_files = sum(len(items) for items in files_by_chain.values())
        done = 0

        for chain in chains:
            colname = f"Pgen_{chain}"
            pgen_mean.setdefault(colname, {})
            model_name = f"{species}{chain}"
            model_ref = self._sonnia_model_reference(model_name)
            processor = Processing(pgen_model=model_ref)
            self._repair_sonnia_windows_gene_sets(processor, model_ref)
            for pep_file in files_by_chain.get(chain, []):
                done += 1
                sample = _sample_name_from_file(pep_file, chain)
                if progress_callback:
                    pct = 8 + int(done / max(total_files, 1) * 76)
                    progress_callback(pct, "Pgen analysis", f"Evaluating {sample} / {chain}")

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
                model = SoNNia(data_seqs=data_seqs, pgen_model=model_ref)
                q_data, pgen_data, ppost_data = model.evaluate_seqs(model.data_seqs)

                detail_df = pd.DataFrame(model.data_seqs, columns=["CDR3(pep)", "V", "J"])
                detail_df.insert(3, "Pgen", pgen_data)
                detail_df.insert(4, "Q", q_data)
                detail_df.insert(5, "Ppost", ppost_data)
                detail_df["V"] = detail_df["V"].map(lambda value: self._prefix_gene(chain, value))
                detail_df["J"] = detail_df["J"].map(lambda value: self._prefix_gene(chain, value))

                sample_dir = detail_base / _safe_name(sample)
                sample_dir.mkdir(parents=True, exist_ok=True)
                detail_path = sample_dir / f"{chain}.csv"
                detail_df.to_csv(detail_path, index=False, encoding="utf-8-sig")
                detail_paths.append(str(detail_path))

                mean_value = float(pd.to_numeric(detail_df["Pgen"], errors="coerce").mean())
                pgen_mean[colname][sample] = mean_value
                processed.append({
                    "sample": sample,
                    "chain": chain,
                    "sequence_count": int(detail_df.shape[0]),
                    "mean_pgen": mean_value,
                    "detail_path": str(detail_path),
                })

        if not processed:
            detail = "; ".join(
                f"{Path(item['file']).name} ({item['chain']}): {item['reason']}"
                for item in skipped[:8]
            )
            raise ValueError(f"No valid sequences were evaluated by SoNNia. {detail}".strip())

        if progress_callback:
            progress_callback(88, "Pgen analysis", "Writing summary outputs")

        pgen_df = pd.DataFrame(pgen_mean)
        pgen_df.index.name = sample_col
        pgen_df = pgen_df.reset_index()
        merged = profile_df.merge(pgen_df, on=sample_col, how="inner")
        mean_path = output_base / "Pgen_mean.csv"
        merged.to_csv(mean_path, index=False, encoding="utf-8-sig")

        detail_index_path = output_base / "Pgen_detail_index.csv"
        pd.DataFrame(processed).to_csv(detail_index_path, index=False, encoding="utf-8-sig")

        self._plot_mean_by_chain(pd.DataFrame(processed), output_base, png_paths, pdf_paths)
        self._plot_sample_heatmap(merged, sample_col, output_base, png_paths, pdf_paths)

        distribution_csv_paths = self._plot_public_pgen_distributions(
            processed_records=processed,
            profile_df=profile_df,
            sample_col=sample_col,
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
            "distribution_category_col": distribution_category_col,
            "selected_chains": chains,
            "skipped_chains": [chain for chain in selected_chains if _normalize_chain(chain) in SKIPPED_SONNIA_CHAINS],
            "sample_count": int(pd.DataFrame(processed)["sample"].nunique()),
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
    def _collect_pep_files(pep_dir: Path, chains: List[str]) -> Dict[str, List[Path]]:
        result: Dict[str, List[Path]] = {chain: [] for chain in chains}
        for path in sorted(pep_dir.rglob("*")):
            if not path.is_file() or not path.name.lower().endswith((".csv", ".csv.gz", ".tsv", ".tsv.gz")):
                continue
            chain = _infer_chain_from_path(path)
            if chain in result:
                result[chain].append(path)
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
    def _plot_sample_heatmap(merged: pd.DataFrame, sample_col: str, output_base: Path, png_paths: List[str], pdf_paths: List[str]) -> None:
        value_cols = [col for col in merged.columns if str(col).startswith("Pgen_")]
        if not value_cols:
            return
        matrix = merged[[sample_col] + value_cols].set_index(sample_col)
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
    ) -> List[str]:
        if not category_col or category_col not in profile_df.columns:
            return []

        output_dir = output_base / "pgen_distribution"
        output_dir.mkdir(parents=True, exist_ok=True)
        sample_category: Dict[str, str] = {}
        for _, row in profile_df[[sample_col, category_col]].dropna(how="any").iterrows():
            sample = str(row[sample_col]).strip()
            category = str(row[category_col]).strip()
            if sample and category and category.lower() != "nan":
                sample_category[sample] = category

        if not sample_category:
            return []

        stats_records: List[Dict[str, Any]] = []
        records_by_chain: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
        for item in processed_records:
            sample = str(item.get("sample") or "").strip()
            chain = _normalize_chain(str(item.get("chain") or ""))
            detail_path = Path(str(item.get("detail_path") or ""))
            if not sample or not chain or not detail_path.exists():
                continue
            try:
                detail_df = _try_read_table(detail_path, usecols=["CDR3(pep)", "Pgen"])
            except Exception:
                continue
            for _, row in detail_df.iterrows():
                cdr3 = str(row.get("CDR3(pep)", "")).strip()
                pgen = pd.to_numeric(row.get("Pgen"), errors="coerce")
                if not cdr3 or cdr3.lower() == "nan" or not np.isfinite(pgen):
                    continue
                records_by_chain[chain].append((sample, cdr3, float(pgen)))

        for chain in sorted(records_by_chain):
            category_values, category_stats, meta = PgenAnalysisService._classify_public_pgen_by_category(
                records_by_chain[chain],
                sample_category,
            )
            for category, stats in category_stats.items():
                stats_records.append({
                    "chain": chain,
                    "category_column": category_col,
                    "category": category,
                    "total_cdr3": stats["total_cdr3"],
                    "public_cdr3": stats["public_cdr3"],
                    "public_nonzero": stats["public_nonzero"],
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
            )
            if out_path:
                png_paths.append(str(out_path))

        if not stats_records:
            return []
        stats_path = output_dir / "pgen_public_distribution_stats.csv"
        pd.DataFrame(stats_records).to_csv(stats_path, index=False, encoding="utf-8-sig")
        return [str(stats_path)]

    @staticmethod
    def _classify_public_pgen_by_category(
        rows: List[Tuple[str, str, float]],
        sample_category: Dict[str, str],
    ) -> Tuple[Dict[str, np.ndarray], Dict[str, Dict[str, int]], Dict[str, int]]:
        cat_cdr3_samples: Dict[str, Dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        cat_pgen_values: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        total_rows = 0
        matched_rows = 0
        zero_pgen = 0

        for sample, cdr3, pgen in rows:
            category = sample_category.get(sample)
            if category is None:
                continue
            matched_rows += 1
            total_rows += 1
            cat_cdr3_samples[category][cdr3].add(sample)
            if pgen > 0.0:
                cat_pgen_values[category].append((cdr3, pgen))
            else:
                zero_pgen += 1

        category_values: Dict[str, np.ndarray] = {}
        category_stats: Dict[str, Dict[str, int]] = {}
        for category in sorted(cat_cdr3_samples):
            cdr3_samples = cat_cdr3_samples[category]
            public_cdr3s = {
                cdr3 for cdr3, samples in cdr3_samples.items()
                if len(samples) >= 2
            }
            vals = [
                -np.log10(pgen)
                for cdr3, pgen in cat_pgen_values[category]
                if cdr3 in public_cdr3s
            ]
            arr = np.array(vals, dtype=np.float64) if vals else np.array([], dtype=np.float64)
            category_values[category] = arr
            category_stats[category] = {
                "total_cdr3": len(cdr3_samples),
                "public_cdr3": len(public_cdr3s),
                "public_nonzero": int(arr.size),
            }

        return category_values, category_stats, {
            "total_rows": total_rows,
            "matched_rows": matched_rows,
            "zero_pgen": zero_pgen,
        }

    @staticmethod
    def _plot_distribution_chain(
        chain: str,
        category_values: Dict[str, np.ndarray],
        category_stats: Dict[str, Dict[str, int]],
        category_col: str,
        output_dir: Path,
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
        ax.set_title(f"{chain} public CDR3s", loc="center", fontweight="bold", pad=4)
        ax.legend(loc="upper right", handlelength=1.2, borderaxespad=0.2, labelspacing=0.35)
        ax.tick_params(axis="both", direction="out")
        ax.margins(y=0.08)
        ax.set_xlim(x[0], x[-1])
        safe_col = _safe_name(category_col)
        out_path = output_dir / f"{chain}_{safe_col}_pgen_public.png"
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
