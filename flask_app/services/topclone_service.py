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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from flask_app.services.boxplot_service import BoxPlotService

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
        mode: str = "trace",
        top_n: int = 10,
        group_field: Optional[str] = None,
        group_order: Optional[str] = None,
        pvalue_threshold: float = 0.05,
        output_name: Optional[str] = None,
        profile_sheet: Optional[str] = None,
        progress_callback=None,
    ) -> TopCloneReport:
        pep_data = Path(pep_data_path)
        if not pep_data.exists():
            raise FileNotFoundError(f"pep_data path not found: {pep_data_path}")

        datapoint = Path(datapoint_path)
        if not datapoint.exists():
            raise FileNotFoundError(f"Datapoint file not found: {datapoint_path}")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name or "topclone")
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        if mode == "trace":
            return self._run_trace_mode(
                pep_data=pep_data,
                datapoint=datapoint,
                output_base=output_base,
                job_id=job_id,
                group_field=group_field,
                group_order=group_order,
                pvalue_threshold=pvalue_threshold,
                output_name=output_name,
                profile_sheet=profile_sheet,
                progress_callback=progress_callback,
            )
        else:
            return self._run_per_sample_mode(
                pep_data=pep_data,
                output_base=output_base,
                job_id=job_id,
                top_n=top_n,
                progress_callback=progress_callback,
            )

    # ------------------------------------------------------------------
    # Chain / sample discovery
    # ------------------------------------------------------------------
    def _discover_files(self, pep_data: Path) -> Dict[str, List[Path]]:
        """Return {chain: [file_path, ...]} for all supported chain CSV files."""
        chain_files: Dict[str, List[Path]] = {}

        # Strategy: pep_data has chain-named subdirectories (reference layout)
        # Each file should match {sample}__{chain}.csv(.gz)
        subdirs = [d for d in pep_data.iterdir() if d.is_dir()]
        chain_dirs = {self._normalize_chain(d.name): d for d in subdirs
                      if self._normalize_chain(d.name) in CHAIN_NAMES}
        if chain_dirs:
            for chain, chain_dir in chain_dirs.items():
                files = (
                    sorted(chain_dir.glob("*.csv"))
                    + sorted(chain_dir.glob("*.csv.gz"))
                )
                if files:
                    chain_files[chain] = files
            if chain_files:
                return chain_files

        # Fallback: flat directory — detect chain from filename
        for f in sorted(list(pep_data.glob("*.csv")) + list(pep_data.glob("*.csv.gz"))):
            chain = self._detect_chain_from_filename(f.name)
            if chain:
                chain_files.setdefault(chain, []).append(f)

        return chain_files

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
    def _read_profile(path: Path, sheet: Optional[str] = None) -> pd.DataFrame:
        """Read profile CSV or XLSX file."""
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            df = pd.read_excel(path, sheet_name=sheet or 0)
        elif suffix == ".tsv":
            df = _try_read_csv(path, sep="\t", low_memory=False)
        else:
            df = _try_read_csv(path, low_memory=False)
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
                result[f"top{n_val}_proportion"] = 0.0
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
        group_field: Optional[str],
        group_order: Optional[str],
        pvalue_threshold: float,
        output_name: Optional[str] = None,
        profile_sheet: Optional[str] = None,
        progress_callback=None,
    ) -> TopCloneReport:
        # 1. Read Profile file (CSV or XLSX)
        profile_df = self._read_profile(datapoint, profile_sheet)
        if "sample" not in profile_df.columns:
            raise ValueError("Profile file must have a 'sample' column")
        sample_list = profile_df["sample"].tolist()
        category_cols = [c for c in profile_df.columns if c != "sample"]

        # 2. Discover chain files & build O(1) lookup {(sample, chain): path}
        chain_files = self._discover_files(pep_data)
        if not chain_files:
            raise ValueError("No chain CSV files found in pep_data path")

        sample_chain_map: Dict[tuple, Path] = {}
        for chain, files in chain_files.items():
            for f in files:
                sample = self._parse_sample_name(f, chain)
                if sample:
                    sample_chain_map[(sample, chain)] = f

        chains = sorted(chain_files.keys())

        if progress_callback:
            progress_callback(
                5, "TopClone trace",
                f"Found {len(chains)} chain(s), {len(sample_list)} sample(s)",
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

        for sample in sample_list:
            record: Dict[str, Any] = {"sample": sample}

            for chain in chains:
                sample_file = sample_chain_map.get((sample, chain))
                if sample_file is None:
                    for n_val in TOP_N_VALUES:
                        record[f"top{n_val}{chain}"] = 0.0
                    continue

                step += 1
                try:
                    df_pep = _try_read_csv(sample_file, low_memory=False)
                    if "CDR3(pep)" not in df_pep.columns or "copy" not in df_pep.columns:
                        for n_val in TOP_N_VALUES:
                            record[f"top{n_val}{chain}"] = 0.0
                        continue

                    top_result = self._compute_top_clones(df_pep)

                    for n_val in TOP_N_VALUES:
                        record[f"top{n_val}{chain}"] = top_result[f"top{n_val}_proportion"]
                        cdr3_sequences[f"{chain}_top{n_val}"][sample] = top_result[f"top{n_val}_cdr3s"]

                except Exception as exc:
                    logger.warning("Failed to process %s / %s: %s", sample, chain, exc)
                    for n_val in TOP_N_VALUES:
                        record[f"top{n_val}{chain}"] = 0.0

                if progress_callback and step % max(1, total_steps // 20) == 0:
                    progress_callback(
                        5 + int(step / max(total_steps, 1) * 50),
                        "TopClone trace",
                        f"Processing {sample} / {chain} ({step}/{total_steps})",
                    )

            topclone_records.append(record)

        # 4. Build topclone_df and merge with profile annotations
        topclone_df = pd.DataFrame(topclone_records)
        # Merge profile category columns using pd.merge (like reference notebook)
        profile_merge_df = profile_df[["sample"] + category_cols].copy()
        topclone_df = profile_merge_df.merge(topclone_df, on="sample", how="inner")

        topclone_csv = output_base / "topclone.csv"
        topclone_df.to_csv(topclone_csv, index=False)

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
                for sample, seqs in seq_dict.items():
                    records.append({
                        "sample": sample,
                        "top_cdr3s": ";".join(seqs),
                        "count": len(seqs),
                    })
                if records:
                    seq_df = pd.DataFrame(records)
                    seq_csv = chain_dir / f"top{n_val}_cdr3s.csv"
                    seq_df.to_csv(seq_csv, index=False)

        if progress_callback:
            progress_callback(60, "TopClone trace", "topclone.csv generated, starting BoxPlot")

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
                100, "TopClone completed",
                f"topclone.csv + {len(boxplot_report.png_paths)} boxplots + CDR3 sequences",
            )

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "mode": "trace",
            "pep_data_path": str(pep_data),
            "datapoint_path": str(datapoint),
            "profile_sheet": profile_sheet or "",
            "chains": chains,
            "sample_count": len(sample_list),
            "category_cols": category_cols,
            "topclone_csv": str(topclone_csv),
            "top_clone_values": TOP_N_VALUES,
        }

        return TopCloneReport(
            job_id=job_id,
            output_base=output_base,
            topclone_csv_path=str(topclone_csv),
            boxplot_report=boxplot_report,
            per_sample_files=[],
            metadata=metadata,
        )

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
        progress_callback,
    ) -> TopCloneReport:
        chain_files = self._discover_files(pep_data)
        if not chain_files:
            raise ValueError("No chain CSV files found in pep_data path")

        output_columns = ["index", "Chain", "CDR3(pep)", "joinedSeq", "V", "D", "J", "C", "copy"]
        input_columns = ["CDR3(pep)", "joinedSeq", "V", "D", "J", "C", "copy"]

        top_clones_root = output_base / "top_clones"
        top_clones_root.mkdir(parents=True, exist_ok=True)

        per_sample_files: List[str] = []
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

                    out_file = chain_out / f"{sample}_top{top_n}.csv"
                    out.to_csv(out_file, index=False)
                    per_sample_files.append(str(out_file))
                except Exception as exc:
                    logger.warning("Failed per-sample extraction for %s: %s", file_path, exc)

                step += 1
                if progress_callback and step % max(1, total // 10) == 0:
                    progress_callback(
                        5 + int(step / max(total, 1) * 90),
                        "TopClone per-sample",
                        f"Extracting {sample} / {chain} ({step}/{total})",
                    )

        if progress_callback:
            progress_callback(
                100, "TopClone completed",
                f"{len(per_sample_files)} per-sample file(s)",
            )

        # Build summary
        summary_csv = top_clones_root / "summary.csv"
        summary_rows = []
        for f in per_sample_files:
            p = Path(f)
            summary_rows.append({
                "chain": p.parent.name,
                "sample": p.stem,
                "file": f,
            })
        if summary_rows:
            summary_df = pd.DataFrame(summary_rows)
            summary_df.to_csv(summary_csv, index=False)

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "mode": "per_sample",
            "pep_data_path": str(pep_data),
            "top_n": top_n,
            "chains": sorted(chain_files.keys()),
            "file_count": len(per_sample_files),
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
