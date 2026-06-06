"""
DB alignment report generation service.
Integrates the VDJdb / McPAS-TCR exact-match workflow from the legacy Django
project and anal_pipeline into the Flask analysis workspace.
"""

from __future__ import annotations

import html
import io
import json
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from flask_app.exceptions import ValidationError
from flask_app.services.boxplot_service import BoxPlotService

logger = logging.getLogger(__name__)


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
        profile_sheet: Optional[str] = None,
        categories: Optional[List[str]] = None,
        category_mode: str = "single",
        contained_pathology: bool = False,
        pathology_values: Optional[List[str]] = None,
        progress_callback=None,
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
        specify_ratio_dir = output_base / "specify_ratio"
        specify_ratio_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(3, "加载数据库", "正在读取 VDJdb 和 McPAS-TCR")

        vdj_db = pd.read_csv(self.vdjdb_path, low_memory=False)
        mcpas_db = pd.read_csv(self.mcpas_path, low_memory=False)
        vdj_db["Reference"] = vdj_db["Reference"].astype(str)
        mcpas_db["PubMed.ID"] = mcpas_db["PubMed.ID"].astype(str)

        normalized_categories = [item for item in (categories or []) if item]
        normalized_category_mode = str(category_mode or "single").strip().lower()
        if normalized_category_mode not in {"single", "cross"}:
            normalized_category_mode = "single"
        pathology_filters = [item for item in (pathology_values or []) if item]

        processed_rows: List[Dict[str, Any]] = []
        ratio_rows: List[Dict[str, Any]] = []
        pathology_ratio_rows: Dict[str, Dict[str, Dict[str, Any]]] = {}
        pathology_summary_paths: Dict[str, str] = {}
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
                )
                if input_df.empty:
                    skipped_files.append({"sample": sample_name, "chain": chain, "reason": "empty_input"})
                    continue

                vdj_matches = self._match_vdjdb(input_df, vdj_db)
                mcpas_matches = self._match_mcpas(input_df, mcpas_db, chain)

                safe_sample_name = self._sanitize_name(sample_name)
                vdj_filename = f"{safe_sample_name}__{chain}__VDJdb.csv"
                mcpas_filename = f"{safe_sample_name}__{chain}__McPASTCR.csv"
                vdj_path = alignment_dir / vdj_filename
                mcpas_path = alignment_dir / mcpas_filename
                vdj_matches.to_csv(vdj_path, index=False)
                mcpas_matches.to_csv(mcpas_path, index=False)

                pathologies = self._collect_pathologies(vdj_matches, mcpas_matches, pathology_filters if contained_pathology else [])
                self._save_pathology_alignment_results(
                    alignment_dir=alignment_dir,
                    vdj_matches=vdj_matches,
                    mcpas_matches=mcpas_matches,
                    sample_name=safe_sample_name,
                    chain=chain,
                    pathologies=pathologies,
                )

                total_copy = float(input_df["copy"].sum()) if not input_df.empty else 0.0
                matched_vdj = input_df[input_df["CDR3(pep)"].isin(vdj_matches["CDR3(pep)"])] if not vdj_matches.empty else input_df.iloc[0:0]
                matched_mcpas = input_df[input_df["CDR3(pep)"].isin(mcpas_matches["CDR3(pep)"])] if not mcpas_matches.empty else input_df.iloc[0:0]
                ratio_vdj = float(matched_vdj["copy"].sum() / total_copy) if total_copy > 0 else 0.0
                ratio_mcpas = float(matched_mcpas["copy"].sum() / total_copy) if total_copy > 0 else 0.0

                ratio_row[f"{chain}_ratio_VDJdb"] = ratio_vdj
                ratio_row[f"{chain}_ratio_McPASTCR"] = ratio_mcpas

                for pathology in pathologies:
                    pathology_vdj = self._filter_by_pathology(vdj_matches, pathology)
                    pathology_mcpas = self._filter_by_pathology(mcpas_matches, pathology)
                    pathology_rows = pathology_ratio_rows.setdefault(str(pathology), {})
                    pathology_row = pathology_rows.setdefault(sample_name, {"sample": sample_name})
                    pathology_row[f"{chain}_ratio_VDJdb"] = self._compute_ratio(input_df, pathology_vdj["CDR3(pep)"])
                    pathology_row[f"{chain}_ratio_McPASTCR"] = self._compute_ratio(input_df, pathology_mcpas["CDR3(pep)"])

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
        (specify_ratio_dir / "specify_ratio.csv").write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")

        notes: List[str] = []
        used_categories: List[str] = []
        merged_summary_path: Optional[Path] = None

        profile_df: pd.DataFrame | None = None
        detected_profile_path: str | Path | None = None

        detected_profile_path = self._resolve_profile_path(profile_path=profile_path, base_path=base_path)
        if detected_profile_path is not None:
            try:
                profile_df = self._read_profile_frame(detected_profile_path, profile_sheet)
            except Exception as exc:
                sheet_note = f" sheet {profile_sheet}" if profile_sheet else ""
                notes.append(f"Failed to read profile file {detected_profile_path}{sheet_note}: {exc}")

        if detected_profile_path is not None and profile_df is not None:
            sample_column = self._find_profile_sample_column(profile_df)
            if not sample_column:
                notes.append(f"Profile file has no sample column: {detected_profile_path}")
            else:
                profile_merge_df, used_categories = self._build_profile_merge_frame(
                    profile_df,
                    sample_column=sample_column,
                    categories=normalized_categories,
                    category_mode=normalized_category_mode,
                )
                merged_df = profile_merge_df.merge(ratio_df, how="inner", on="sample")
                merged_summary_path = output_base / "specify_ratio_with_profile.csv"
                merged_df.to_csv(merged_summary_path, index=False)
                merged_df.to_csv(specify_ratio_dir / "specify_ratio_with_profile.csv", index=False)
                missing_categories = sorted(set(normalized_categories) - set(used_categories))
                if missing_categories:
                    notes.append(f"Missing profile categories: {', '.join(missing_categories)}")
        else:
            notes.append("Profile file was not provided or auto-detected; only raw ratio output is available.")

        for pathology, sample_rows in sorted(pathology_ratio_rows.items()):
            pathology_df = pd.DataFrame(sample_rows.values()).fillna(0.0)
            if detected_profile_path is not None and profile_df is not None:
                sample_column = self._find_profile_sample_column(profile_df)
                if sample_column:
                    profile_merge_df, _ = self._build_profile_merge_frame(
                        profile_df,
                        sample_column=sample_column,
                        categories=normalized_categories,
                        category_mode=normalized_category_mode,
                    )
                    pathology_df = profile_merge_df.merge(pathology_df, how="inner", on="sample")
            pathology_filename = f"specify_ratio__{self._sanitize_name(pathology)}.csv"
            pathology_path = specify_ratio_dir / pathology_filename
            pathology_df.to_csv(pathology_path, index=False)
            pathology_summary_paths[str(pathology)] = str(pathology_path)

        if progress_callback:
            progress_callback(94, "显著性箱线图", "正在运行 Pathology ratio 显著性箱线图")

        boxplot_report = self._run_significant_boxplots(
            output_base=output_base,
            specify_ratio_dir=specify_ratio_dir,
            merged_summary_path=merged_summary_path,
            pathology_summary_paths=pathology_summary_paths,
            used_categories=used_categories,
            category_mode=normalized_category_mode,
        )

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
            "profile_sheet": str(profile_sheet or ""),
            "categories": normalized_categories,
            "category_mode": normalized_category_mode,
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
                "ratio_summary_dir": str(specify_ratio_dir),
                "merged_ratio_summary": str(merged_summary_path) if merged_summary_path else "",
                "alignment_summary": str(processed_table_path),
                "pathology_summaries": pathology_summary_paths,
                "boxplot_dir": str(output_base / "boxplot"),
                "significant_boxplot_summary": boxplot_report.get("significant_summary_path", ""),
            },
            "boxplot_count": len(boxplot_report.get("all_plots") or []),
            "boxplots": boxplot_report.get("all_plots") or [],
            "significant_boxplot_count": len(boxplot_report.get("significant_plots") or []),
            "significant_boxplots": boxplot_report.get("significant_plots") or [],
            "non_significant_boxplot_count": len(boxplot_report.get("non_significant_plots") or []),
            "non_significant_boxplots": boxplot_report.get("non_significant_plots") or [],
            "significant_pvalues": boxplot_report.get("significant_rows") or [],
            "pathology_count": len(pathology_summary_paths),
            "pathologies": sorted(pathology_summary_paths.keys()),
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

    def _run_significant_boxplots(
        self,
        *,
        output_base: Path,
        specify_ratio_dir: Path,
        merged_summary_path: Optional[Path],
        pathology_summary_paths: Dict[str, str],
        used_categories: List[str],
        category_mode: str,
        pvalue_threshold: float = 0.05,
        min_group_n: int = 2,
    ) -> Dict[str, Any]:
        category_columns = [str(col) for col in used_categories if str(col or "").strip()]

        sources: List[Dict[str, Any]] = []
        if merged_summary_path and merged_summary_path.exists():
            sources.append({
                "label": "Overall",
                "source": "overall",
                "path": merged_summary_path,
            })
        # Only include the raw specify_ratio.csv as fallback when no
        # profile-merged CSV is available. Otherwise the merged CSV already
        # provides grouped boxplots and the raw CSV would generate redundant
        # ungrouped "ratio_distribution" plots alongside them.
        if not merged_summary_path or not merged_summary_path.exists():
            raw_ratio_path = specify_ratio_dir / "specify_ratio.csv"
            if raw_ratio_path.exists():
                sources.append({
                    "label": "Overall",
                    "source": "overall",
                    "path": raw_ratio_path,
                })
        for pathology, raw_path in sorted((pathology_summary_paths or {}).items()):
            path = Path(raw_path)
            if path.exists():
                sources.append({
                    "label": str(pathology),
                    "source": f"Pathology/{pathology}",
                    "path": path,
                })

        boxplot_report = BoxPlotService(output_parent=output_base).generate_significance_boxplots(
            output_base=output_base,
            sources=sources,
            category_columns=category_columns,
            category_mode=category_mode,
            metric_pattern=r"^(TRA|TRB)_ratio_(VDJdb|McPASTCR)$",
            pvalue_threshold=pvalue_threshold,
            min_group_n=min_group_n,
            output_subdir="boxplot",
        )
        logger.info(
            "Boxplot generation complete: %d total, %d significant, %d non-significant",
            len(boxplot_report.get("all_plots") or []),
            len(boxplot_report.get("significant_plots") or []),
            len(boxplot_report.get("non_significant_plots") or []),
        )
        return boxplot_report

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
            ("全部箱线图", str(metadata.get("boxplot_count", 0))),
            ("显著箱线图", str(metadata.get("significant_boxplot_count", 0))),
        ]
        notes_html = "".join(f"<li>{html.escape(str(note))}</li>" for note in (metadata.get("notes") or []))
        processed_columns = list(processed_preview.columns)
        processed_rows_html = "".join(
            "<tr data-chain=\"{}\">{}</tr>".format(
                html.escape(str(row.get("chain") or "")),
                "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in processed_columns),
            )
            for _, row in processed_preview.iterrows()
        )
        processed_html = (
            '<table class="data-table"><thead><tr>'
            + "".join(f"<th>{html.escape(str(column))}</th>" for column in processed_columns)
            + "</tr></thead><tbody>"
            + (processed_rows_html or '<tr><td class="empty" colspan="99">No processed rows.</td></tr>')
            + "</tbody></table>"
        )
        ratio_html = ratio_preview.to_html(index=False, classes="data-table", border=0, justify="left")
        significant_rows = metadata.get("significant_pvalues") or []
        significant_rows_html = "".join(
            f"""<tr data-chain="{html.escape(str(row.get('chain') or ''))}" data-pathology="{html.escape(str(row.get('source_label') or row.get('source') or ''))}">
              <td>{html.escape(str(row.get('source_label') or row.get('source') or ''))}</td>
              <td>{html.escape(str(row.get('context') or '-'))}</td>
              <td>{html.escape(str(row.get('class_col') or ''))}</td>
              <td>{html.escape(str(row.get('group1') or ''))} vs {html.escape(str(row.get('group2') or ''))}</td>
              <td>{html.escape(str(row.get('param') or ''))}</td>
              <td>{float(row.get('pvalue') or 0):.4g}</td>
            </tr>"""
            for row in significant_rows[:200]
        )
        significant_table_html = f"""
          <table class="data-table">
            <thead><tr><th>Source</th><th>Context</th><th>Field</th><th>Comparison</th><th>Param</th><th>p value</th></tr></thead>
            <tbody>{significant_rows_html or '<tr><td class="empty" colspan="6">No significant p values.</td></tr>'}</tbody>
          </table>
        """
        all_boxplots = metadata.get("boxplots") or []
        significant_boxplots = metadata.get("significant_boxplots") or []

        def render_boxplot_cards(plots: List[Dict[str, Any]], empty_text: str) -> str:
            cards = []
            for plot in plots:
                badge = "显著" if plot.get("is_significant") else "非显著"
                badge_class = "sig" if plot.get("is_significant") else "ns"
                cards.append(
                    f"""<article class="plot-card" data-chain="{html.escape(str(plot.get('chain') or ''))}" data-significance="{html.escape(str(plot.get('significance') or ''))}" data-pathology="{html.escape(str(plot.get('source_label') or plot.get('source') or ''))}">
                      <div class="plot-head">
                        <div>
                          <strong>{html.escape(str(plot.get('param') or ''))}</strong>
                          <span>{html.escape(str(plot.get('source_label') or plot.get('source') or ''))} · {html.escape(str(plot.get('class_col') or ''))}{' · ' + html.escape(str(plot.get('context'))) if plot.get('context') else ''}</span>
                        </div>
                        <div class="plot-tags"><b>{html.escape(str(plot.get('chain') or '-'))}</b><em class="{badge_class}">{badge}</em></div>
                      </div>
                      <a href="{html.escape(str(plot.get('png') or ''))}" target="_blank" rel="noopener">
                        <img src="{html.escape(str(plot.get('png') or ''))}" alt="{html.escape(str(plot.get('param') or 'boxplot'))}" loading="lazy">
                      </a>
                    </article>"""
                )
            return "".join(cards) or f'<div class="empty">{html.escape(empty_text)}</div>'

        all_boxplot_cards_html = render_boxplot_cards(all_boxplots, "没有箱线图结果。")
        significant_boxplot_cards_html = render_boxplot_cards(significant_boxplots, "没有检测到显著箱线图结果。")
        boxplots_json = json.dumps(all_boxplots, ensure_ascii=False).replace("</", "<\\/")

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
    body {{ margin: 0; background: #f6f8fa; color: var(--ink); font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }}
    .page {{ max-width: 1240px; margin: 0 auto; padding: 22px 18px 34px; }}
    .topbar {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 14px; }}
    h1 {{ margin: 0 0 5px; font-size: 24px; letter-spacing: 0; }}
    .sub {{ margin: 0; color: var(--muted); font-size: 13px; line-height: 1.55; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; min-width: 420px; }}
    .summary-card {{ background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }}
    .summary-card .label {{ font-size: 11px; color: var(--muted); margin-bottom: 3px; }}
    .summary-card .value {{ font-size: 15px; font-weight: 760; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .toolbar {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 12px 0; padding: 8px; border: 1px solid var(--line); border-radius: 10px; background: #fff; }}
    .tabs, .chain-filter, .pathology-filter {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    button {{ font: inherit; }}
    .tab-btn, .chain-btn, .path-btn {{ border: 1px solid var(--line); background: #fff; color: #304354; border-radius: 8px; padding: 7px 10px; cursor: pointer; }}
    .tab-btn.is-active, .chain-btn.is-active, .path-btn.is-active {{ border-color: var(--accent); background: var(--accent-soft); color: #0f5f5a; font-weight: 700; }}
    .panel {{ display: none; padding: 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--card); }}
    .panel.is-active {{ display: block; }}
    .panel h2 {{ margin: 0 0 10px; font-size: 17px; }}
    .notes {{ margin: 0; padding-left: 18px; color: var(--muted); line-height: 1.6; }}
    .empty {{ color: var(--muted); }}
    .table-wrap {{ overflow: auto; border: 1px solid var(--line); border-radius: 8px; background: #fff; max-height: 560px; }}
    table.data-table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
    table.data-table th, table.data-table td {{ padding: 8px 10px; border-bottom: 1px solid #e8eef5; text-align: left; vertical-align: top; white-space: nowrap; }}
    table.data-table th {{ position: sticky; top: 0; background: #f8fbfc; }}
    .subhead {{ font-size: 12px; color: var(--muted); margin: -4px 0 10px; }}
    .plot-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
    .plot-card {{ border: 1px solid var(--line); border-radius: 8px; background: #fff; overflow: hidden; }}
    .plot-head {{ display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; padding: 9px 10px; border-bottom: 1px solid #edf2f5; }}
    .plot-head strong {{ display: block; font-size: 13px; }}
    .plot-head span {{ display: block; margin-top: 2px; color: var(--muted); font-size: 11.5px; line-height: 1.35; }}
    .plot-head b {{ color: #0f5f5a; font-size: 12px; }}
    .plot-tags {{ display: flex; flex-direction: column; align-items: flex-end; gap: 5px; flex: 0 0 auto; }}
    .plot-tags em {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 2px 7px; font-style: normal; font-size: 11px; font-weight: 700; }}
    .plot-tags em.sig {{ background: #ecfdf5; color: #0f766e; border: 1px solid #bce7d7; }}
    .plot-tags em.ns {{ background: #f2f5f7; color: #6b7c8c; border: 1px solid #dbe4ea; }}
    .plot-card img {{ display: block; width: 100%; height: 230px; object-fit: contain; background: #fff; }}
    [data-hidden="1"] {{ display: none !important; }}
    @media (max-width: 860px) {{
      .topbar {{ display: block; }}
      .cards {{ min-width: 0; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 12px; }}
      .toolbar {{ align-items: flex-start; flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header class="topbar">
      <div>
        <h1>DB Alignment</h1>
        <p class="sub">VDJdb / McPAS-TCR 精确匹配，Pathology 分类导出，并区分全部、显著与非显著箱线图。</p>
        <p class="sub">Profile: {html.escape(str(metadata.get("profile_path") or "未提供"))}{(" / " + html.escape(str(metadata.get("profile_sheet")))) if metadata.get("profile_sheet") else ""}</p>
      </div>
      <div class="cards">
        {''.join(f'<div class="summary-card"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>' for label, value in summary_cards)}
      </div>
    </header>

    <div class="toolbar">
      <div class="tabs">
        <button class="tab-btn is-active" data-tab="overview">概览</button>
        <button class="tab-btn" data-tab="boxplots">全部箱线图</button>
        <button class="tab-btn" data-tab="significant-boxplots">显著箱线图</button>
        <button class="tab-btn" data-tab="ratio">比例表</button>
        <button class="tab-btn" data-tab="alignment">比对汇总</button>
      </div>
      <div class="chain-filter" aria-label="chain filter">
        <button class="chain-btn is-active" data-chain-filter="all">All</button>
        <button class="chain-btn" data-chain-filter="TRA">TRA</button>
        <button class="chain-btn" data-chain-filter="TRB">TRB</button>
      </div>
      <div class="pathology-filter" aria-label="pathology filter">
        <select class="path-btn" id="pathology-select" style="border:1px solid var(--line);color:#304354;border-radius:8px;padding:7px 10px;font:inherit;font-size:12px;max-width:220px;background:#fff;cursor:pointer;">
          <option value="all">All pathologies</option>
          {''.join(f'<option value="{html.escape(p)}">{html.escape(p[:55])}</option>' for p in metadata.get("pathologies") or [])}
        </select>
      </div>
    </div>

    <section class="panel is-active" data-panel="overview">
      <h2>运行说明</h2>
      <div class="subhead">生成时间: {html.escape(str(metadata.get("generated_at") or "-"))}</div>
      {f'<ul class="notes">{notes_html}</ul>' if notes_html else '<div class="empty">本次运行没有额外说明。</div>'}
      <div class="table-wrap" style="margin-top:12px;">{significant_table_html}</div>
    </section>

    <section class="panel" data-panel="boxplots">
      <h2>全部箱线图</h2>
      <div class="subhead">包含显著与非显著结果；压缩包中分别位于 boxplot/significant 和 boxplot/non_significant。</div>
      <div class="plot-grid">
        {all_boxplot_cards_html}
      </div>
    </section>

    <section class="panel" data-panel="significant-boxplots">
      <h2>显著箱线图</h2>
      <div class="subhead">仅展示 Mann-Whitney U 检验 p <= 0.05 的结果；链过滤会同步更新当前列表。</div>
      <div class="plot-grid">
        {significant_boxplot_cards_html}
      </div>
    </section>

    <section class="panel" data-panel="ratio">
      <h2>比例汇总</h2>
      <div class="subhead">优先展示合并 Profile 后结果，否则展示原始比例表。</div>
      <div class="table-wrap">{ratio_html}</div>
    </section>

    <section class="panel" data-panel="alignment">
      <h2>比对汇总</h2>
      <div class="subhead">预览前 20 条样本链记录；可用链过滤查看 TRA / TRB。</div>
      <div class="table-wrap">{processed_html}</div>
    </section>
  </div>
  <script id="boxplot-data" type="application/json">{boxplots_json}</script>
  <script>
    (function() {{
      let activeChain = 'all';
      let activePathology = 'all';
      const setTab = (tab) => {{
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.toggle('is-active', btn.dataset.tab === tab));
        document.querySelectorAll('[data-panel]').forEach(panel => panel.classList.toggle('is-active', panel.dataset.panel === tab));
      }};
      const applyFilters = () => {{
        document.querySelectorAll('[data-chain][data-pathology]').forEach(el => {{
          const rowChain = (el.dataset.chain || '').toUpperCase();
          const rowPath = (el.dataset.pathology || '').toUpperCase();
          const chainMatch = activeChain === 'all' || rowChain === activeChain;
          const pathMatch = activePathology === 'all' || rowPath === activePathology.toUpperCase();
          el.dataset.hidden = (chainMatch && pathMatch) ? '0' : '1';
        }});
        // Also filter elements that only have data-chain (e.g. alignment summary rows)
        document.querySelectorAll('[data-chain]:not([data-pathology])').forEach(el => {{
          const rowChain = (el.dataset.chain || '').toUpperCase();
          const visible = activeChain === 'all' || rowChain === activeChain;
          el.dataset.hidden = visible ? '0' : '1';
        }});
      }};
      const setChain = (chain) => {{
        activeChain = chain || 'all';
        document.querySelectorAll('.chain-btn').forEach(btn => btn.classList.toggle('is-active', btn.dataset.chainFilter === activeChain));
        applyFilters();
      }};
      const setPathology = (pathology) => {{
        activePathology = pathology || 'all';
        applyFilters();
      }};
      document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => setTab(btn.dataset.tab)));
      document.querySelectorAll('.chain-btn').forEach(btn => btn.addEventListener('click', () => setChain(btn.dataset.chainFilter)));
      const pathSelect = document.getElementById('pathology-select');
      if (pathSelect) pathSelect.addEventListener('change', () => setPathology(pathSelect.value));
      applyFilters();
    }})();
  </script>
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
                candidates.extend([
                    root / "Profile_All.csv",
                    root / "Profile.csv",
                    root / "Profile_All.xlsx",
                    root / "Profile.xlsx",
                ])
                for pattern in ("Profile*.csv", "Profile*.xlsx"):
                    candidates.extend(sorted(root.glob(pattern))[:5])

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        return None

    @staticmethod
    def _read_profile_frame(path: Path, profile_sheet: Optional[str] = None) -> pd.DataFrame:
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            return pd.read_excel(path, sheet_name=profile_sheet or 0)
        sep = "\t" if suffix == ".tsv" else ","
        return pd.read_csv(path, sep=sep, low_memory=False)

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
        candidate = re.sub(r'[\\/:*?"<>|]+', "_", str(value or "")).strip()
        return candidate or "Unknown"

    def _allocate_job_id(self, requested_name: Optional[str]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(requested_name or "").strip()).strip("_")
        prefix = base_name or f"db_alignment_{timestamp}"
        candidate = f"{prefix}_{datetime.now().strftime('%f')}"
        while (self.output_parent / candidate).exists():
            candidate = f"{prefix}_{datetime.now().strftime('%f')}"
        return candidate

    @staticmethod
    def _load_input_frame(filepath: str, field_mapping: Dict[str, str]) -> pd.DataFrame:
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
        output["CDR3_match"] = output["CDR3(pep)"].map(DBAlignmentService._normalize_cdr3_for_match)
        return output[output["CDR3(pep)"] != ""]

    @staticmethod
    def _normalize_cdr3_for_match(value: Any) -> str:
        cdr3 = str(value or "").strip()
        if not cdr3:
            return ""
        return cdr3 if cdr3.startswith("C") else f"C{cdr3}"

    @staticmethod
    def _pep_copy(input_df: pd.DataFrame) -> pd.DataFrame:
        return input_df.groupby("CDR3(pep)", as_index=False)["copy"].sum()

    @staticmethod
    def _cdr3_lookup(input_df: pd.DataFrame) -> pd.DataFrame:
        return input_df[["CDR3(pep)", "CDR3_match"]].drop_duplicates()

    @staticmethod
    def _compute_ratio(input_df: pd.DataFrame, matched_cdr3_values: Any) -> float:
        total_copy = float(input_df["copy"].sum()) if not input_df.empty else 0.0
        if total_copy <= 0:
            return 0.0
        return float(input_df[input_df["CDR3(pep)"].isin(list(matched_cdr3_values))]["copy"].sum() / total_copy)

    @staticmethod
    def _find_profile_sample_column(profile_df: pd.DataFrame) -> str:
        for candidate in ["sample", "Sample", "SAMPLE"]:
            if candidate in profile_df.columns:
                return candidate
        for column in profile_df.columns:
            if str(column).strip().lower() == "sample":
                return str(column)
        return ""

    @staticmethod
    def _build_profile_merge_frame(
        profile_df: pd.DataFrame,
        *,
        sample_column: str,
        categories: List[str],
        category_mode: str,
    ) -> tuple[pd.DataFrame, List[str]]:
        used_categories = [item for item in categories if item in profile_df.columns]
        merge_columns = [sample_column] + used_categories
        profile_merge_df = profile_df[merge_columns].rename(columns={sample_column: "sample"}).copy()

        if category_mode == "cross" and used_categories:
            profile_merge_df["cross_category"] = profile_merge_df[used_categories].apply(
                lambda row: " | ".join(str(value) for value in row.fillna("Unknown").tolist()),
                axis=1,
            )

        return profile_merge_df, used_categories

    @staticmethod
    def _match_vdjdb(input_df: pd.DataFrame, vdj_db: pd.DataFrame) -> pd.DataFrame:
        lookup_df = DBAlignmentService._cdr3_lookup(input_df)
        result = vdj_db[vdj_db["CDR3"].isin(input_df["CDR3_match"].dropna().tolist())][
            ["CDR3", "Species", "Epitope", "Epitope species", "Reference"]
        ].copy()
        if result.empty:
            return pd.DataFrame(columns=["CDR3(pep)", "Species", "Epitope.peptide", "Pathology", "Reference", "copy"])

        result = result.rename(columns={
            "CDR3": "CDR3_match",
            "Epitope": "Epitope.peptide",
            "Epitope species": "Pathology",
        })
        result = result.merge(lookup_df, on="CDR3_match", how="left").drop(columns=["CDR3_match"])
        result = result[result["Species"] == "HomoSapiens"]
        result = result[["CDR3(pep)", "Species", "Epitope.peptide", "Pathology", "Reference"]]
        result = result.merge(DBAlignmentService._pep_copy(input_df), on="CDR3(pep)", how="left")
        return result.reset_index(drop=True)

    @staticmethod
    def _match_mcpas(input_df: pd.DataFrame, mcpas_db: pd.DataFrame, chain: str) -> pd.DataFrame:
        source_column = "CDR3.alpha.aa" if chain == "TRA" else "CDR3.beta.aa"
        lookup_df = DBAlignmentService._cdr3_lookup(input_df)
        result = mcpas_db[mcpas_db[source_column].isin(input_df["CDR3_match"].dropna().tolist())][
            [source_column, "Species", "Epitope.peptide", "Pathology", "PubMed.ID"]
        ].copy()
        if result.empty:
            return pd.DataFrame(columns=["CDR3(pep)", "Species", "Epitope.peptide", "Pathology", "PubMed.ID", "copy"])

        result = result.rename(columns={source_column: "CDR3_match"})
        result = result.merge(lookup_df, on="CDR3_match", how="left").drop(columns=["CDR3_match"])
        result = result[result["Species"] == "Human"]
        result = result[["CDR3(pep)", "Species", "Epitope.peptide", "Pathology", "PubMed.ID"]]
        result = result.merge(DBAlignmentService._pep_copy(input_df), on="CDR3(pep)", how="left")
        return result.reset_index(drop=True)

    @staticmethod
    def _collect_pathologies(vdj_matches: pd.DataFrame, mcpas_matches: pd.DataFrame, pathology_filters: List[str]) -> List[str]:
        if pathology_filters:
            return list(pathology_filters)

        values: set[str] = set()
        for frame in [vdj_matches, mcpas_matches]:
            if "Pathology" not in frame.columns or frame.empty:
                continue
            values.update(frame["Pathology"].fillna("Unknown").astype(str).tolist())
        return sorted(values)

    @staticmethod
    def _filter_by_pathology(frame: pd.DataFrame, pathology: str) -> pd.DataFrame:
        if "Pathology" not in frame.columns or frame.empty:
            return frame.iloc[0:0].copy()
        return frame[frame["Pathology"].fillna("Unknown").astype(str) == str(pathology)]

    @staticmethod
    def _save_pathology_alignment_results(
        *,
        alignment_dir: Path,
        vdj_matches: pd.DataFrame,
        mcpas_matches: pd.DataFrame,
        sample_name: str,
        chain: str,
        pathologies: List[str],
    ) -> None:
        for pathology in pathologies:
            pathology_dir = alignment_dir / DBAlignmentService._sanitize_name(str(pathology))
            pathology_dir.mkdir(parents=True, exist_ok=True)
            DBAlignmentService._filter_by_pathology(vdj_matches, pathology).to_csv(
                pathology_dir / f"{sample_name}__{chain}__VDJdb.csv",
                index=False,
            )
            DBAlignmentService._filter_by_pathology(mcpas_matches, pathology).to_csv(
                pathology_dir / f"{sample_name}__{chain}__McPASTCR.csv",
                index=False,
            )
