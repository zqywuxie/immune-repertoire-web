"""
DB alignment report generation service.
Integrates the VDJdb / McPAS-TCR exact-match workflow from the legacy Django
project and anal_pipeline into the Flask analysis workspace.
"""

from __future__ import annotations

import html
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from flask_app.exceptions import ValidationError


_VIEWER_FILE_NAME = "viewer.html"
_METADATA_FILE_NAME = "metadata.json"
_ZIP_FILE_NAME = "db_alignment_bundle.zip"


@dataclass
class DBAlignmentReport:
    job_id: str
    output_base: Path
    viewer_path: Path
    metadata_path: Path
    zip_path: Path
    summary_path: Path
    metadata: Dict[str, Any]


class DBAlignmentService:
    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()
        self.app_root = Path(__file__).resolve().parents[1]
        self.vdjdb_path = self.app_root / "data" / "reference_db" / "vdjdb.csv"
        self.mcpas_path = self.app_root / "data" / "reference_db" / "McPAS-TCR.csv"

    def generate_report(
        self,
        *,
        samples: List[Dict[str, Any]],
        selected_chains: List[str],
        field_mapping: Dict[str, str],
        output_name: Optional[str] = None,
        base_path: Optional[str] = None,
        profile_path: Optional[str] = None,
        categories: Optional[List[str]] = None,
        contained_pathology: bool = False,
        pathology_values: Optional[List[str]] = None,
        progress_callback=None,
        ssh_file_provider=None,
    ) -> DBAlignmentReport:
        if not self.vdjdb_path.exists() or not self.mcpas_path.exists():
            raise ValidationError(
                message="DB alignment reference databases are missing",
                details={
                    "vdjdb_path": str(self.vdjdb_path),
                    "mcpas_path": str(self.mcpas_path),
                },
            )

        allowed_chains = [chain for chain in selected_chains if str(chain or "").strip().upper() in {"TRA", "TRB"}]
        if not allowed_chains:
            raise ValidationError(message="DB alignment only supports TRA/TRB chains")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name)
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)
        alignment_dir = output_base / "alignment"
        alignment_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(3, "加载数据库", "正在读取 VDJdb 和 McPAS-TCR")

        vdj_db = pd.read_csv(self.vdjdb_path, low_memory=False)
        mcpas_db = pd.read_csv(self.mcpas_path, low_memory=False)
        vdj_db["Reference"] = vdj_db["Reference"].astype(str)
        mcpas_db["PubMed.ID"] = mcpas_db["PubMed.ID"].astype(str)

        normalized_categories = [item for item in (categories or []) if item]
        pathology_filters = [item for item in (pathology_values or []) if item]

        processed_rows: List[Dict[str, Any]] = []
        ratio_rows: List[Dict[str, Any]] = []
        skipped_files: List[Dict[str, str]] = []
        total_units = max(len(samples) * len(allowed_chains), 1)
        processed_index = 0

        for sample in samples:
            sample_name = str(sample.get("original_name") or sample.get("display_name") or "").strip()
            display_name = str(sample.get("display_name") or sample_name).strip()
            if not sample_name:
                continue

            ratio_row: Dict[str, Any] = {"sample": sample_name}
            files_by_chain = self._group_sample_files(sample.get("data_files") or [])

            for chain in allowed_chains:
                file_info = files_by_chain.get(chain)
                if not file_info:
                    skipped_files.append({"sample": sample_name, "chain": chain, "reason": "missing_input_file"})
                    continue

                processed_index += 1
                if progress_callback:
                    progress = min(92, 5 + int(processed_index / total_units * 82))
                    progress_callback(
                        progress,
                        "样本比对",
                        f"正在处理 {display_name} / {chain}",
                        {"sample": display_name, "chain": chain, "file": file_info.get("filepath", "")},
                    )

                input_df = self._load_input_frame(
                    file_info.get("filepath", ""), field_mapping,
                    ssh_file_provider=ssh_file_provider,
                )
                if input_df.empty:
                    skipped_files.append({"sample": sample_name, "chain": chain, "reason": "empty_input"})
                    continue

                vdj_matches = self._match_vdjdb(input_df, vdj_db, contained_pathology, pathology_filters)
                mcpas_matches = self._match_mcpas(input_df, mcpas_db, chain, contained_pathology, pathology_filters)

                safe_sample_name = self._sanitize_name(sample_name)
                vdj_filename = f"{safe_sample_name}__{chain}__VDJdb.csv"
                mcpas_filename = f"{safe_sample_name}__{chain}__McPASTCR.csv"
                vdj_path = alignment_dir / vdj_filename
                mcpas_path = alignment_dir / mcpas_filename
                vdj_matches.to_csv(vdj_path, index=False)
                mcpas_matches.to_csv(mcpas_path, index=False)

                total_copy = float(input_df["copy"].sum()) if not input_df.empty else 0.0
                matched_vdj = input_df[input_df["CDR3(pep)"].isin(vdj_matches["CDR3(pep)"])] if not vdj_matches.empty else input_df.iloc[0:0]
                matched_mcpas = input_df[input_df["CDR3(pep)"].isin(mcpas_matches["CDR3(pep)"])] if not mcpas_matches.empty else input_df.iloc[0:0]
                ratio_vdj = float(matched_vdj["copy"].sum() / total_copy) if total_copy > 0 else 0.0
                ratio_mcpas = float(matched_mcpas["copy"].sum() / total_copy) if total_copy > 0 else 0.0

                ratio_row[f"{chain}_ratio_VDJdb"] = ratio_vdj
                ratio_row[f"{chain}_ratio_McPASTCR"] = ratio_mcpas

                processed_rows.append(
                    {
                        "sample": sample_name,
                        "display_name": display_name,
                        "chain": chain,
                        "input_file": str(file_info.get("filepath", "")),
                        "input_rows": int(len(input_df)),
                        "matched_vdjdb": int(len(vdj_matches)),
                        "matched_mcpas": int(len(mcpas_matches)),
                        "ratio_vdjdb": ratio_vdj,
                        "ratio_mcpas": ratio_mcpas,
                        "vdjdb_file": vdj_filename,
                        "mcpas_file": mcpas_filename,
                    }
                )

            ratio_rows.append(ratio_row)

        if not processed_rows:
            raise ValidationError(message="No TRA/TRB sample files could be processed for DB alignment")

        ratio_df = pd.DataFrame(ratio_rows).fillna(0.0)
        summary_path = output_base / "specify_ratio.csv"
        ratio_df.to_csv(summary_path, index=False)

        notes: List[str] = []
        used_categories: List[str] = []
        merged_summary_path: Optional[Path] = None

        profile_df: pd.DataFrame | None = None
        detected_profile_path: str | Path | None = None

        if ssh_file_provider is not None:
            if profile_path:
                try:
                    profile_bytes = ssh_file_provider.read_file_bytes(profile_path)
                    profile_df = pd.read_csv(io.BytesIO(profile_bytes), low_memory=False)
                    detected_profile_path = profile_path
                except Exception as exc:
                    notes.append(f"Failed to read remote profile file {profile_path}: {exc}")
        else:
            detected_profile_path = self._resolve_profile_path(profile_path=profile_path, base_path=base_path)
            if detected_profile_path is not None:
                try:
                    profile_df = pd.read_csv(detected_profile_path, low_memory=False)
                except Exception as exc:
                    notes.append(f"Failed to read profile file {detected_profile_path}: {exc}")

        if detected_profile_path is not None and profile_df is not None:
            if "sample" not in profile_df.columns:
                notes.append(f"Profile file has no 'sample' column: {detected_profile_path}")
            else:
                used_categories = [item for item in normalized_categories if item in profile_df.columns]
                merge_columns = ["sample"] + used_categories
                merged_df = profile_df[merge_columns].merge(ratio_df, how="inner", on="sample")
                merged_summary_path = output_base / "specify_ratio_with_profile.csv"
                merged_df.to_csv(merged_summary_path, index=False)
                missing_categories = sorted(set(normalized_categories) - set(used_categories))
                if missing_categories:
                    notes.append(f"Missing profile categories: {', '.join(missing_categories)}")
        else:
            notes.append("Profile file was not provided or auto-detected; only raw ratio output is available.")

        processed_df = pd.DataFrame(processed_rows)
        processed_table_path = output_base / "alignment_summary.csv"
        processed_df.to_csv(processed_table_path, index=False)

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "selected_chains": allowed_chains,
            "sample_count": len({row["sample"] for row in processed_rows}),
            "processed_count": len(processed_rows),
            "profile_path": str(detected_profile_path) if detected_profile_path else "",
            "categories": normalized_categories,
            "used_categories": used_categories,
            "contained_pathology": bool(contained_pathology),
            "pathology_values": pathology_filters,
            "notes": notes,
            "reference_files": {
                "vdjdb": str(self.vdjdb_path),
                "mcpas_tcr": str(self.mcpas_path),
            },
            "outputs": {
                "alignment_dir": str(alignment_dir),
                "ratio_summary": str(summary_path),
                "merged_ratio_summary": str(merged_summary_path) if merged_summary_path else "",
                "alignment_summary": str(processed_table_path),
            },
            "processed_rows": processed_rows,
            "skipped_files": skipped_files,
        }

        metadata_path = output_base / _METADATA_FILE_NAME
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        ratio_preview_df = pd.read_csv(merged_summary_path) if merged_summary_path and merged_summary_path.exists() else ratio_df
        viewer_path = output_base / _VIEWER_FILE_NAME
        viewer_path.write_text(
            self._build_viewer_html(
                metadata=metadata,
                processed_preview=processed_df.head(20),
                ratio_preview=ratio_preview_df.head(20),
            ),
            encoding="utf-8",
        )

        zip_path = output_base / _ZIP_FILE_NAME
        self._create_zip(output_base, zip_path)

        if progress_callback:
            progress_callback(100, "结果完成", f"DB alignment 已生成 {len(processed_rows)} 个样本链结果")

        return DBAlignmentReport(
            job_id=job_id,
            output_base=output_base,
            viewer_path=viewer_path,
            metadata_path=metadata_path,
            zip_path=zip_path,
            summary_path=summary_path,
            metadata=metadata,
        )

    def _build_viewer_html(
        self,
        *,
        metadata: Dict[str, Any],
        processed_preview: pd.DataFrame,
        ratio_preview: pd.DataFrame,
    ) -> str:
        summary_cards = [
            ("样本数", str(metadata.get("sample_count", 0))),
            ("链类型", ", ".join(metadata.get("selected_chains") or []) or "-"),
            ("Profile", metadata.get("profile_path") or "未提供"),
            ("病原过滤", "开启" if metadata.get("contained_pathology") else "关闭"),
        ]
        notes_html = "".join(f"<li>{html.escape(str(note))}</li>" for note in (metadata.get("notes") or []))
        processed_html = processed_preview.to_html(index=False, classes="data-table", border=0, justify="left")
        ratio_html = ratio_preview.to_html(index=False, classes="data-table", border=0, justify="left")

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DB Alignment</title>
  <style>
    :root {{
      --bg: #f5f7fa;
      --card: #ffffff;
      --ink: #132238;
      --muted: #62748a;
      --line: #d9e2ec;
      --accent: #0f766e;
      --accent-soft: #ecfdf5;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: linear-gradient(180deg, #edf7f4 0%, #f8fbfd 52%, #ffffff 100%); color: var(--ink); font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }}
    .page {{ max-width: 1200px; margin: 0 auto; padding: 28px 20px 40px; }}
    .hero, .panel {{ background: var(--card); border: 1px solid var(--line); border-radius: 20px; box-shadow: 0 16px 38px rgba(19, 34, 56, 0.06); }}
    .hero {{ padding: 24px; margin-bottom: 18px; }}
    .hero h1 {{ margin: 0 0 8px; font-size: 30px; }}
    .hero p {{ margin: 0; color: var(--muted); line-height: 1.65; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-top: 18px; }}
    .summary-card {{ background: var(--accent-soft); border: 1px solid #c8ece4; border-radius: 16px; padding: 14px 16px; }}
    .summary-card .label {{ font-size: 12px; color: #0f5f5a; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .04em; }}
    .summary-card .value {{ font-size: 16px; font-weight: 700; word-break: break-word; }}
    .grid {{ display: grid; gap: 18px; }}
    .panel {{ padding: 18px; }}
    .panel h2 {{ margin: 0 0 12px; font-size: 20px; }}
    .notes {{ margin: 0; padding-left: 18px; color: var(--muted); line-height: 1.6; }}
    .empty {{ color: var(--muted); }}
    .table-wrap {{ overflow: auto; border: 1px solid var(--line); border-radius: 16px; background: #fff; }}
    table.data-table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    table.data-table th, table.data-table td {{ padding: 10px 12px; border-bottom: 1px solid #e8eef5; text-align: left; vertical-align: top; }}
    table.data-table th {{ position: sticky; top: 0; background: #f8fbfc; }}
    .subhead {{ font-size: 13px; color: var(--muted); margin: -4px 0 12px; }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>DB Alignment</h1>
      <p>基于 `djangoProject` 的 VDJdb / McPAS-TCR 精确匹配流程，已在统一分析工作台中完成整合。</p>
      <div class="cards">
        {''.join(f'<div class="summary-card"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>' for label, value in summary_cards)}
      </div>
    </section>
    <div class="grid">
      <section class="panel">
        <h2>运行说明</h2>
        <div class="subhead">生成时间: {html.escape(str(metadata.get("generated_at") or "-"))}</div>
        {f'<ul class="notes">{notes_html}</ul>' if notes_html else '<div class="empty">本次运行没有额外说明。</div>'}
      </section>
      <section class="panel">
        <h2>比对汇总</h2>
        <div class="subhead">预览前 20 条样本链记录</div>
        <div class="table-wrap">{processed_html}</div>
      </section>
      <section class="panel">
        <h2>比例汇总</h2>
        <div class="subhead">优先展示合并 Profile 后结果，否则展示原始比例表</div>
        <div class="table-wrap">{ratio_html}</div>
      </section>
    </div>
  </div>
</body>
</html>"""

    def _create_zip(self, output_base: Path, zip_path: Path) -> None:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in output_base.rglob("*"):
                if not file_path.is_file() or file_path == zip_path:
                    continue
                archive.write(file_path, arcname=file_path.relative_to(output_base))

    def _resolve_profile_path(self, *, profile_path: Optional[str], base_path: Optional[str]) -> Optional[Path]:
        explicit = Path(str(profile_path or "").strip()) if str(profile_path or "").strip() else None
        if explicit and explicit.exists() and explicit.is_file():
            return explicit.resolve()

        if not base_path:
            return None

        base = Path(base_path)
        candidates: List[Path] = []
        if base.exists():
            search_roots = [base]
            if base.parent != base:
                search_roots.append(base.parent)
            for root in search_roots:
                candidates.extend([root / "Profile_All.csv", root / "Profile.csv"])
                candidates.extend(sorted(root.glob("Profile*.csv"))[:5])

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        return None

    def _group_sample_files(self, data_files: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for file_info in data_files:
            filename = str(file_info.get("filename") or "")
            chain = self._infer_chain_from_filename(filename)
            if chain and chain not in grouped:
                grouped[chain] = file_info
        return grouped

    @staticmethod
    def _infer_chain_from_filename(filename: str) -> str:
        match = re.search(r"(?:__|_)([A-Za-z0-9-]+)\.csv(?:\.gz)?$", filename or "", flags=re.IGNORECASE)
        if not match:
            return ""

        raw_chain = match.group(1).upper()
        alias_map = {
            "TCRA": "TRA",
            "TCRB": "TRB",
        }
        return alias_map.get(raw_chain, raw_chain)

    @staticmethod
    def _sanitize_name(value: str) -> str:
        candidate = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "").strip("_")
        return candidate or "sample"

    def _allocate_job_id(self, requested_name: Optional[str]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(requested_name or "").strip()).strip("_")
        prefix = base_name or f"db_alignment_{timestamp}"
        candidate = f"{prefix}_{datetime.now().strftime('%f')}"
        while (self.output_parent / candidate).exists():
            candidate = f"{prefix}_{datetime.now().strftime('%f')}"
        return candidate

    @staticmethod
    def _load_input_frame(filepath: str, field_mapping: Dict[str, str], ssh_file_provider=None) -> pd.DataFrame:
        if ssh_file_provider is not None:
            return DBAlignmentService._load_input_frame_remote(ssh_file_provider, filepath, field_mapping)

        target = Path(str(filepath or ""))
        if not target.exists():
            raise ValidationError(message=f"Input file does not exist: {filepath}")

        df = pd.read_csv(target, low_memory=False, compression="infer")
        cdr3_col = field_mapping["cdr3_column"]
        copy_col = field_mapping["copy_column"]
        missing = [column for column in [cdr3_col, copy_col] if column not in df.columns]
        if missing:
            raise ValidationError(
                message="DB alignment input file is missing mapped columns",
                details={"filepath": str(target), "missing_columns": missing},
            )

        output = pd.DataFrame({
            "CDR3(pep)": df[cdr3_col].fillna("").astype(str).str.strip(),
            "copy": pd.to_numeric(df[copy_col], errors="coerce").fillna(0),
        })
        return output[output["CDR3(pep)"] != ""]

    @staticmethod
    def _load_input_frame_remote(ssh_file_provider, remote_path: str, field_mapping: Dict[str, str]) -> pd.DataFrame:
        file_bytes = ssh_file_provider.read_file_bytes(remote_path)
        df = pd.read_csv(io.BytesIO(file_bytes), low_memory=False)
        cdr3_col = field_mapping["cdr3_column"]
        copy_col = field_mapping["copy_column"]
        missing = [column for column in [cdr3_col, copy_col] if column not in df.columns]
        if missing:
            raise ValidationError(
                message="Remote DB alignment input file is missing mapped columns",
                details={"remote_path": remote_path, "missing_columns": missing},
            )

        output = pd.DataFrame({
            "CDR3(pep)": df[cdr3_col].fillna("").astype(str).str.strip(),
            "copy": pd.to_numeric(df[copy_col], errors="coerce").fillna(0),
        })
        return output[output["CDR3(pep)"] != ""]

    @staticmethod
    def _match_vdjdb(
        input_df: pd.DataFrame,
        vdj_db: pd.DataFrame,
        contained_pathology: bool,
        pathology_filters: List[str],
    ) -> pd.DataFrame:
        result = vdj_db[vdj_db["CDR3"].isin(input_df["CDR3(pep)"].tolist())][
            ["CDR3", "Species", "Epitope", "Epitope species", "Reference"]
        ].copy()
        if result.empty:
            return pd.DataFrame(columns=["CDR3(pep)", "Species", "Epitope.peptide", "Pathology", "PubMed.ID"])

        result.insert(0, "CDR3(pep)", result.pop("CDR3"))
        result.insert(2, "Epitope.peptide", result.pop("Epitope"))
        result.insert(3, "Pathology", result.pop("Epitope species"))
        result.insert(4, "PubMed.ID", result.pop("Reference"))
        result = result[result["Species"] == "HomoSapiens"]
        if contained_pathology and pathology_filters:
            result = result[result["Pathology"].isin(pathology_filters)]
        return result.reset_index(drop=True)

    @staticmethod
    def _match_mcpas(
        input_df: pd.DataFrame,
        mcpas_db: pd.DataFrame,
        chain: str,
        contained_pathology: bool,
        pathology_filters: List[str],
    ) -> pd.DataFrame:
        source_column = "CDR3.alpha.aa" if chain == "TRA" else "CDR3.beta.aa"
        result = mcpas_db[mcpas_db[source_column].isin(input_df["CDR3(pep)"].tolist())][
            [source_column, "Species", "Epitope.peptide", "Pathology", "PubMed.ID"]
        ].copy()
        if result.empty:
            return pd.DataFrame(columns=["CDR3(pep)", "Species", "Epitope.peptide", "Pathology", "PubMed.ID"])

        result.insert(0, "CDR3(pep)", result.pop(source_column))
        result = result[result["Species"] == "Human"]
        if contained_pathology and pathology_filters:
            result = result[result["Pathology"].isin(pathology_filters)]
        return result.reset_index(drop=True)
