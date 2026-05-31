"""
TopClone analysis service — trace mode (CDR3_trace) and per-sample mode.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from flask_app.services.boxplot_service import BoxPlotService

CHAIN_NAMES = {"TRA", "TRB", "TRG", "TRD", "IGH", "IGK", "IGL"}
CHAIN_ALIASES: Dict[str, str] = {
    "ALPHA": "TRA", "BETA": "TRB", "GAMMA": "TRG", "DELTA": "TRD",
    "HEAVY": "IGH", "KAPPA": "IGK", "LAMBDA": "IGL",
}
FILE_PATTERN = re.compile(
    r"^(?P<sample>.+?)(?:__|_|-)?(?P<chain>TRA|TRB|TRG|TRD|IGH|IGK|IGL)?$",
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

        # Case 1: pep_data has chain-named subdirectories
        subdirs = [d for d in pep_data.iterdir() if d.is_dir()]
        chain_dirs = {self._normalize_chain(d.name): d for d in subdirs
                      if self._normalize_chain(d.name) in CHAIN_NAMES}
        if chain_dirs:
            for chain, chain_dir in chain_dirs.items():
                files = sorted(chain_dir.glob("*.csv")) + sorted(chain_dir.glob("*.csv.gz"))
                if files:
                    chain_files[chain] = files
            if chain_files:
                return chain_files

        # Case 2: flat directory — detect chain from filename
        for f in sorted(pep_data.glob("*.csv")):
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
        match = FILE_PATTERN.match(stem)
        if match and match.group("chain"):
            return match.group("chain").upper()
        return None

    @staticmethod
    def _parse_sample_name(file_path: Path, chain: str) -> str:
        stem = Path(file_path.name).stem
        # Remove .csv / .csv.gz
        if stem.lower().endswith(".csv"):
            stem = stem[:-4]
        match = FILE_PATTERN.match(stem)
        if match and match.group("sample"):
            return match.group("sample").rstrip("_-")
        return stem

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
        progress_callback,
    ) -> TopCloneReport:
        # 1. Read Profile_All.csv
        profile_df = pd.read_csv(datapoint, low_memory=False)
        profile_df.fillna("", inplace=True)
        if "sample" not in profile_df.columns:
            raise ValueError("Profile_All.csv must have a 'sample' column")
        sample_list = profile_df["sample"].tolist()

        # Category columns: all non-sample, non-param columns
        category_cols = [c for c in profile_df.columns if c != "sample"]

        # 2. Discover chain files
        chain_files = self._discover_files(pep_data)
        if not chain_files:
            raise ValueError("No chain CSV files found in pep_data path")

        if progress_callback:
            progress_callback(5, "TopClone trace", f"Found {len(chain_files)} chain(s), {len(sample_list)} sample(s)")

        # 3. Build topclone data
        topclone_records: List[Dict[str, Any]] = []

        total = len(chain_files) * len(sample_list)
        step = 0

        for sample in sample_list:
            sample_profile = profile_df[profile_df["sample"] == sample]
            record: Dict[str, Any] = {}
            for col in category_cols:
                record[col] = sample_profile[col].values[0] if not sample_profile.empty else ""
            record["sample"] = sample

            for chain, files in chain_files.items():
                # Find the file for this sample + chain
                sample_file = None
                for f in files:
                    parsed = self._parse_sample_name(f, chain)
                    if parsed == sample:
                        sample_file = f
                        break
                if sample_file is None:
                    for n_val in TOP_N_VALUES:
                        record[f"top{n_val}{chain}"] = 0.0
                    continue

                try:
                    df_pep = pd.read_csv(sample_file, low_memory=False)
                    if "CDR3(pep)" not in df_pep.columns or "copy" not in df_pep.columns:
                        for n_val in TOP_N_VALUES:
                            record[f"top{n_val}{chain}"] = 0.0
                        continue

                    df_pep = df_pep[["CDR3(pep)", "copy"]].copy()
                    df_pep["copy"] = pd.to_numeric(df_pep["copy"], errors="coerce").fillna(0)
                    df_grp = df_pep.groupby("CDR3(pep)")["copy"].sum().reset_index()
                    df_grp = df_grp[~df_grp["CDR3(pep)"].str.contains(r"\*|_", na=False)]
                    df_grp = df_grp.sort_values("copy", ascending=False)

                    total_copies = df_grp["copy"].sum()
                    for n_val in TOP_N_VALUES:
                        if total_copies > 0:
                            proportion = df_grp["copy"].iloc[:n_val].sum() / total_copies
                        else:
                            proportion = 0.0
                        record[f"top{n_val}{chain}"] = proportion
                except Exception:
                    for n_val in TOP_N_VALUES:
                        record[f"top{n_val}{chain}"] = 0.0

                step += 1
                if progress_callback:
                    progress_callback(
                        5 + int(step / max(total, 1) * 50),
                        "TopClone trace",
                        f"Processing {sample} / {chain}",
                    )

            topclone_records.append(record)

        # 4. Build and save topclone_df
        topclone_df = pd.DataFrame(topclone_records)
        topclone_csv = output_base / "topclone.csv"
        topclone_df.to_csv(topclone_csv, index=False)

        if progress_callback:
            progress_callback(60, "TopClone trace", "topclone.csv generated, starting BoxPlot")

        # 5. Run BoxPlot on topclone.csv
        param_columns = []
        for n_val in TOP_N_VALUES:
            for chain in sorted(chain_files.keys()):
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
            progress_callback(100, "TopClone completed", f"topclone.csv + {len(boxplot_report.png_paths)} boxplots")

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "mode": "trace",
            "pep_data_path": str(pep_data),
            "datapoint_path": str(datapoint),
            "chains": sorted(chain_files.keys()),
            "sample_count": len(sample_list),
            "topclone_csv": str(topclone_csv),
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
    # Per-sample mode (tcr_artificial_peps_top_clones.ipynb)
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
                sample = self._parse_sample_name(file_path, chain)
                try:
                    df = pd.read_csv(file_path, low_memory=False)
                    missing = [c for c in input_columns if c not in df.columns]
                    if missing:
                        raise ValueError(f"Missing columns: {missing}")

                    out = pd.DataFrame(index=df.index)
                    out["Chain"] = chain
                    out["CDR3(pep)"] = df["CDR3(pep)"].fillna("").astype(str).str.strip()
                    for field in ["joinedSeq", "V", "D", "J", "C"]:
                        out[field] = df[field].fillna("").astype(str).str.strip() if field in df.columns else ""
                    copy_series = df["copy"].fillna("").astype(str).str.replace(",", "", regex=False).str.strip()
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
                except Exception:
                    pass

                step += 1
                if progress_callback:
                    progress_callback(
                        5 + int(step / max(total, 1) * 90),
                        "TopClone per-sample",
                        f"Extracting {sample} / {chain}",
                    )

        if progress_callback:
            progress_callback(100, "TopClone completed", f"{len(per_sample_files)} per-sample file(s)")

        summary_csv = top_clones_root / "summary.csv"
        summary_df = pd.DataFrame([
            {"chain": f.rsplit("/", 3)[-3] if len(f.rsplit("/", 3)) >= 3 else "",
             "sample": Path(f).stem, "file": f}
            for f in per_sample_files
        ])
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
