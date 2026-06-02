"""
API routes for unified chart generation of heatmap, treemap, and chord outputs.
"""

from __future__ import annotations

import base64
import html
import json
import logging
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request, send_file

from flask_app.exceptions import ValidationError
from flask_app.services.auto_heatmap_service import (
    DataFileInfo,
    FieldMapping,
    SampleFolderInfo,
    get_auto_heatmap_service,
)
from flask_app.services.chord_report_service import get_chord_report_service
from flask_app.services.db_alignment_service import DBAlignmentService
from flask_app.services.heatmap_generator import HeatmapConfig, HeatmapGenerator
from flask_app.services.similarity_heatmap_report_service import get_similarity_heatmap_report_service
from flask_app.services.treemap_report_service import get_treemap_report_service

logger = logging.getLogger(__name__)

combined_analysis_bp = Blueprint("combined_analysis", __name__, url_prefix="/api/combined-analysis")
_combined_executor = ThreadPoolExecutor(max_workers=2)
_combined_task_lock = threading.Lock()
_combined_tasks: Dict[str, Dict[str, Any]] = {}

_RESULT_DIR = "combined_analysis_report"
_METADATA_FILE_NAME = "metadata.json"
_VIEWER_FILE_NAME = "viewer.html"
_ALLOWED_MODULES = ["heatmap", "treemap", "chord"]


def _history_entry(progress: float, stage: str, detail: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "progress": round(progress, 2),
        "stage": stage,
        "detail": detail,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "meta": meta or {},
    }


def _set_task_state(task_id: str, **updates: Any) -> None:
    with _combined_task_lock:
        task = _combined_tasks.setdefault(task_id, {})
        task.update(updates)


def _get_task_state(task_id: str) -> Dict[str, Any] | None:
    with _combined_task_lock:
        task = _combined_tasks.get(task_id)
        return dict(task) if task else None


def _sanitize_job_id(raw_name: Optional[str]) -> str:
    if raw_name:
        candidate = re.sub(r"[^A-Za-z0-9_-]+", "_", str(raw_name).strip()).strip("_")
        if candidate:
            return candidate
    return f"combined_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _allocate_job_id(results_root: Path, requested_name: Optional[str]) -> str:
    base_id = _sanitize_job_id(requested_name)
    run_root = results_root / _RESULT_DIR
    run_root.mkdir(parents=True, exist_ok=True)

    candidate = base_id
    suffix = 1
    while (run_root / candidate).exists():
        candidate = f"{base_id}_{suffix}"
        suffix += 1
    return candidate


def _resolve_results_root() -> Path:
    results_root = Path(current_app.config.get("RESULTS_FOLDER", Path(current_app.root_path) / "data" / "results"))
    if not results_root.is_absolute():
        results_root = Path(current_app.root_path) / results_root
    return results_root.resolve()


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _parse_samples(samples_data: Any) -> List[Dict[str, Any]]:
    if not isinstance(samples_data, list) or len(samples_data) < 2:
        raise ValidationError(message="请至少选择 2 个样本", details={"field": "samples"})

    samples: List[Dict[str, Any]] = []
    for sample in samples_data:
        if not isinstance(sample, dict):
            continue
        samples.append(
            {
                "original_name": sample.get("original_name", ""),
                "display_name": sample.get("display_name", sample.get("original_name", "")),
                "folder_path": sample.get("folder_path", ""),
                "data_files": list(sample.get("data_files", []) or []),
            }
        )

    if len(samples) < 2:
        raise ValidationError(message="请至少选择 2 个有效样本", details={"field": "samples"})
    return samples


def _parse_heatmap_samples(samples_data: List[Dict[str, Any]]) -> List[SampleFolderInfo]:
    parsed_samples: List[SampleFolderInfo] = []
    for sample in samples_data:
        data_files = [
            DataFileInfo(
                filename=file_info.get("filename", ""),
                filepath=file_info.get("filepath", ""),
                size=file_info.get("size", 0),
                rows=file_info.get("rows", 0),
                columns=file_info.get("columns", []),
            )
            for file_info in sample.get("data_files", [])
        ]
        parsed_samples.append(
            SampleFolderInfo(
                original_name=sample.get("original_name", ""),
                display_name=sample.get("display_name", sample.get("original_name", "")),
                folder_path=sample.get("folder_path", ""),
                data_files=data_files,
            )
        )
    return parsed_samples


def _parse_field_mapping(field_mapping_data: Any) -> Dict[str, str]:
    field_mapping_data = field_mapping_data if isinstance(field_mapping_data, dict) else {}
    field_mapping = {
        "cdr3_column": str(field_mapping_data.get("cdr3_column", "")).strip(),
        "copy_column": str(field_mapping_data.get("copy_column", "")).strip(),
        "v_column": str(field_mapping_data.get("v_column", "")).strip(),
        "j_column": str(field_mapping_data.get("j_column", "")).strip(),
    }

    missing = [key for key, value in field_mapping.items() if not value]
    if missing:
        raise ValidationError(message="请完成字段映射", details={"missing_fields": missing})
    return field_mapping


def _parse_selected_modules(modules_data: Any) -> List[str]:
    if not isinstance(modules_data, list):
        return list(_ALLOWED_MODULES)

    selected_modules: List[str] = []
    for item in modules_data:
        value = str(item or "").strip().lower()
        if value in _ALLOWED_MODULES and value not in selected_modules:
            selected_modules.append(value)

    if not selected_modules:
        raise ValidationError(message="请至少选择 1 个生成内容", details={"field": "selected_modules"})
    return selected_modules


def _build_heatmap_chain_result(
    samples: List[Dict[str, Any]],
    selected_chains: List[str],
    field_mapping: Dict[str, str],
    color_scheme: str,
    annotation: bool,
) -> Dict[str, Any]:
    auto_heatmap_service = get_auto_heatmap_service()
    generator = HeatmapGenerator()
    metric_titles = {
        "expression_sharing": "Expression",
        "morisita_horn": "Morisita-Horn",
        "cdr3_sharing": "uCDR3",
        "r2_inner": "R^2 Inner",
        "r2_outer": "R^2 Outer",
        "sorensen": "Sorensen",
    }

    sample_infos = _parse_heatmap_samples(samples)
    chain_data = auto_heatmap_service.load_sample_data_by_chains(
        sample_infos,
        selected_chains,
        FieldMapping(
            cdr3_column=field_mapping["cdr3_column"],
            copy_column=field_mapping["copy_column"],
        ),
    )
    if not chain_data:
        raise ValidationError(message="没有足够的链数据用于生成 heatmap")

    result: Dict[str, Any] = {
        "success": True,
        "plot_type": "heatmap",
        "mode": "chain",
        "chains": {},
        "metrics": {},
        "images": {},
    }

    for chain, sample_data in chain_data.items():
        if len(sample_data) < 2:
            continue

        all_metrics = auto_heatmap_service.calculate_all_metrics(sample_data)
        chain_result = {"metrics": {}, "images": {}, "sample_count": len(sample_data)}

        for metric_name, matrix in all_metrics.items():
            metric_config = HeatmapConfig(
                title=f"{chain} - {metric_titles.get(metric_name, metric_name)}",
                plot_type="heatmap",
                color_scheme=color_scheme,
                annotation=annotation,
                figure_width=10,
                figure_height=8,
                dpi=150,
            )
            heatmap_bytes, _ = generator.generate_heatmap(matrix, metric_config, metric_name=metric_name)
            table_data = {"columns": ["Sample"] + matrix.columns.tolist(), "rows": []}
            for idx, row_name in enumerate(matrix.index):
                row = [row_name] + [
                    round(value, 4) if value is not None else None
                    for value in matrix.iloc[idx].tolist()
                ]
                table_data["rows"].append(row)

            chain_result["images"][metric_name] = base64.b64encode(heatmap_bytes).decode("utf-8")
            chain_result["metrics"][metric_name] = {
                "matrix_data": {
                    "samples": matrix.index.tolist(),
                    "columns": matrix.columns.tolist(),
                    "values": matrix.values.tolist(),
                },
                "table_data": table_data,
            }

        if chain_result["metrics"]:
            result["chains"][chain] = chain_result

    if not result["chains"]:
        raise ValidationError(message="所有链的有效样本数都不足 2，无法生成 heatmap")
    return result


def _generate_heatmap_report(
    results_root: Path,
    samples: List[Dict[str, Any]],
    selected_chains: List[str],
    field_mapping: Dict[str, str],
    output_name: Optional[str],
    color_scheme: str,
    annotation: bool,
) -> Dict[str, Any]:
    heatmap_result = _build_heatmap_chain_result(
        samples=samples,
        selected_chains=selected_chains,
        field_mapping=field_mapping,
        color_scheme=color_scheme,
        annotation=annotation,
    )
    report_service = get_similarity_heatmap_report_service(results_root=results_root)
    report = report_service.generate_report(
        heatmap_result=heatmap_result,
        output_name=output_name,
        embed_images=False,
        context={
            "source": "combined_analysis",
            "selected_chains": list(selected_chains),
            "selected_samples": [sample.get("display_name") or sample.get("original_name") for sample in samples],
        },
    )
    archive_path = report_service.create_archive(report.job_id, archive_name="shared_analysis.zip")
    archive_relative_path = archive_path.relative_to(report.output_base).as_posix()

    return {
        "status": "completed",
        "label": "Heatmap",
        "job_id": report.job_id,
        "viewer_url": f"/api/auto-heatmap/similarity-report/results/{report.job_id}/similarity_heatmap_report.html",
        "zip_url": f"/api/auto-heatmap/similarity-report/results/{report.job_id}/{archive_relative_path}",
        "metadata_url": f"/api/auto-heatmap/similarity-report/results/{report.job_id}/metadata.json",
        "chain_count": len(heatmap_result.get("chains", {})),
    }


def _generate_treemap_report(
    results_root: Path,
    samples: List[Dict[str, Any]],
    selected_chains: List[str],
    field_mapping: Dict[str, str],
    output_name: Optional[str],
    min_copy_default: Any,
    top_n: Any,
    topclone_only: Any,
    layout_mode: str,
    canvas_shape: str = "square",
) -> Dict[str, Any]:
    report = get_treemap_report_service(results_root=results_root).generate_report(
        samples=samples,
        selected_chains=selected_chains,
        field_mapping=field_mapping,
        output_name=output_name,
        min_copy_default=min_copy_default,
        top_n=top_n,
        topclone_only=bool(topclone_only),
        style="classic",
        layout_mode=layout_mode,
        canvas_shape=canvas_shape,
    )
    return {
        "status": "completed",
        "label": "Treemap",
        "job_id": report.job_id,
        "viewer_url": f"/api/treemap/results/{report.job_id}/viewer.html",
        "zip_url": f"/api/treemap/export-zip/{report.job_id}",
        "metadata_url": f"/api/treemap/results/{report.job_id}/metadata.json",
        "topclone_only": bool(report.metadata.get("topclone_only")),
        "warnings": report.metadata.get("warnings") or [],
    }


def _generate_chord_report(
    results_root: Path,
    samples: List[Dict[str, Any]],
    selected_chains: List[str],
    field_mapping: Dict[str, str],
    output_name: Optional[str],
) -> Dict[str, Any]:
    report = get_chord_report_service(results_root=results_root).generate_report(
        samples=samples,
        selected_chains=selected_chains,
        field_mapping=field_mapping,
        output_name=output_name,
        count_mode="rows",
    )
    return {
        "status": "completed",
        "label": "Chord",
        "job_id": report.job_id,
        "viewer_url": f"/api/chord/results/{report.job_id}/viewer.html",
        "zip_url": f"/api/chord/export-zip/{report.job_id}",
        "metadata_url": f"/api/chord/results/{report.job_id}/metadata.json",
    }


def _generate_db_alignment_report(
    results_root: Path,
    samples: List[Dict[str, Any]],
    selected_chains: List[str],
    field_mapping: Dict[str, str],
    output_name: Optional[str],
    base_path: Optional[str],
    profile_path: Optional[str],
    categories: List[str],
    contained_pathology: bool,
    pathology_values: List[str],
    progress_callback,
) -> Dict[str, Any]:
    report = DBAlignmentService(output_parent=results_root / _RESULT_DIR).generate_report(
        samples=samples,
        selected_chains=selected_chains,
        field_mapping=field_mapping,
        output_name=output_name,
        base_path=base_path,
        profile_path=profile_path,
        categories=categories,
        contained_pathology=contained_pathology,
        pathology_values=pathology_values,
        progress_callback=progress_callback,
    )
    return {
        "status": "completed",
        "label": "DB Alignment",
        "job_id": report.job_id,
        "viewer_url": f"/api/combined-analysis/results/{report.job_id}/viewer.html",
        "zip_url": f"/api/combined-analysis/results/{report.job_id}/db_alignment_bundle.zip",
        "metadata_url": f"/api/combined-analysis/results/{report.job_id}/metadata.json",
        "output_base": str(report.output_base),
        "report_path": str(report.viewer_path),
        "sample_count": int(report.metadata.get("sample_count") or 0),
    }


def _build_viewer_html(metadata: Dict[str, Any]) -> str:
    modules = metadata.get("modules", {})
    module_order = metadata.get("selected_modules") or list(modules.keys()) or list(_ALLOWED_MODULES)
    cards: List[str] = []

    for module_key in module_order:
        module_info = modules.get(module_key) or {}
        label = html.escape(str(module_info.get("label") or module_key.title()))
        status = str(module_info.get("status") or "failed").strip().lower()
        message = html.escape(str(module_info.get("message") or ""))
        viewer_url = module_info.get("viewer_url")
        zip_url = module_info.get("zip_url")

        buttons: List[str] = []
        if viewer_url:
            buttons.append(
                f'<a class="btn btn-primary" href="{html.escape(str(viewer_url))}" target="_blank" rel="noopener">打开查看器</a>'
            )
        if zip_url:
            buttons.append(
                f'<a class="btn btn-secondary" href="{html.escape(str(zip_url))}" target="_blank" rel="noopener">下载 ZIP</a>'
            )
        if not buttons:
            buttons.append('<span class="empty-note">该模块未生成可用文件</span>')

        status_class = "ok" if status == "completed" else "failed"
        status_text = "已生成" if status == "completed" else "失败"
        message_html = f'<div class="message">{message}</div>' if message else ""

        cards.append(
            f"""
            <section class="card">
              <div class="card-head">
                <h2>{label}</h2>
                <span class="status {status_class}">{status_text}</span>
              </div>
              {message_html}
              <div class="actions">{''.join(buttons)}</div>
            </section>
            """
        )

    summary = html.escape(str(metadata.get("summary") or ""))
    generated_at = html.escape(str(metadata.get("generated_at") or ""))
    sample_count = int(metadata.get("sample_count") or 0)
    chain_text = html.escape(", ".join(metadata.get("selected_chains") or []) or "-")
    selected_module_text = html.escape(", ".join(module_order) or "-")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Combined Analysis Report</title>
  <style>
    :root {{
      --bg: #f4f7fb;
      --card: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --line: #dbe3ef;
      --primary: #0d6efd;
      --ok-bg: #e8f7ee;
      --ok-text: #146c43;
      --fail-bg: #fdecec;
      --fail-text: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: linear-gradient(180deg, #eef3f9 0%, #f8fbff 100%); color: var(--text); font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }}
    .page {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 48px; }}
    .hero {{ background: var(--card); border: 1px solid var(--line); border-radius: 20px; padding: 24px; box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06); margin-bottom: 20px; }}
    .hero h1 {{ margin: 0 0 8px; font-size: 28px; }}
    .hero p {{ margin: 0; color: var(--muted); line-height: 1.6; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 18px; }}
    .summary-item {{ border: 1px solid var(--line); border-radius: 16px; background: #f8fbff; padding: 14px 16px; }}
    .summary-item .label {{ font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
    .summary-item .value {{ font-size: 16px; font-weight: 700; word-break: break-word; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 18px; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05); }}
    .card-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }}
    .card h2 {{ margin: 0; font-size: 20px; }}
    .status {{ border-radius: 999px; padding: 6px 10px; font-size: 12px; font-weight: 700; }}
    .status.ok {{ background: var(--ok-bg); color: var(--ok-text); }}
    .status.failed {{ background: var(--fail-bg); color: var(--fail-text); }}
    .message {{ color: var(--muted); margin-bottom: 14px; min-height: 24px; line-height: 1.6; word-break: break-word; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .btn {{ display: inline-flex; align-items: center; justify-content: center; min-height: 40px; padding: 0 16px; border-radius: 12px; text-decoration: none; font-weight: 700; border: 1px solid transparent; }}
    .btn-primary {{ background: var(--primary); color: #fff; }}
    .btn-secondary {{ background: #fff; color: var(--text); border-color: var(--line); }}
    .empty-note {{ color: var(--muted); font-size: 14px; }}
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>一键分析结果</h1>
      <p>{summary}</p>
      <div class="summary">
        <div class="summary-item"><div class="label">样本数</div><div class="value">{sample_count}</div></div>
        <div class="summary-item"><div class="label">链类型</div><div class="value">{chain_text}</div></div>
        <div class="summary-item"><div class="label">生成模块</div><div class="value">{selected_module_text}</div></div>
        <div class="summary-item"><div class="label">生成时间</div><div class="value">{generated_at}</div></div>
      </div>
    </div>
    <div class="grid">{''.join(cards)}</div>
  </div>
</body>
</html>"""


def _write_combined_bundle(
    results_root: Path,
    requested_name: Optional[str],
    samples: List[Dict[str, Any]],
    selected_chains: List[str],
    selected_modules: List[str],
    modules: Dict[str, Dict[str, Any]],
    summary: str,
) -> Dict[str, Any]:
    job_id = _allocate_job_id(results_root, requested_name)
    output_base = results_root / _RESULT_DIR / job_id
    output_base.mkdir(parents=True, exist_ok=True)

    metadata = {
        "job_id": job_id,
        "generated_at": datetime.now().isoformat(),
        "sample_count": len(samples),
        "selected_chains": list(selected_chains),
        "selected_modules": list(selected_modules),
        "summary": summary,
        "modules": modules,
    }

    metadata_path = output_base / _METADATA_FILE_NAME
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    viewer_path = output_base / _VIEWER_FILE_NAME
    viewer_path.write_text(_build_viewer_html(metadata), encoding="utf-8")

    return {
        "job_id": job_id,
        "output_base": str(output_base),
        "report_path": str(viewer_path),
        "viewer_url": f"/api/combined-analysis/results/{job_id}/{_VIEWER_FILE_NAME}",
        "metadata_url": f"/api/combined-analysis/results/{job_id}/{_METADATA_FILE_NAME}",
    }


def _scaled_progress_callback(task_id: str, module_key: str, module_label: str, start: float, end: float):
    def callback(progress: float, stage: str, detail: str, meta: Optional[Dict[str, Any]] = None) -> None:
        scaled_progress = start + (max(0.0, min(100.0, float(progress or 0.0))) / 100.0) * (end - start)
        merged_meta = dict(meta or {})
        merged_meta["module"] = module_key
        merged_meta["module_label"] = module_label
        merged_meta.setdefault("phase", merged_meta.get("phase") or "running")
        history_item = _history_entry(scaled_progress, f"{module_label} | {stage}", detail, merged_meta)

        with _combined_task_lock:
            task = _combined_tasks.setdefault(task_id, {})
            task["status"] = "running"
            task["progress"] = round(scaled_progress, 2)
            task["stage"] = f"{module_label} | {stage}"
            task["detail"] = detail
            task["meta"] = merged_meta
            history = task.setdefault("history", [])
            if not history or history[-1] != history_item:
                history.append(history_item)
                if len(history) > 80:
                    del history[:-80]

    return callback


def _record_stage(task_id: str, progress: float, stage: str, detail: str, meta: Optional[Dict[str, Any]] = None) -> None:
    history_item = _history_entry(progress, stage, detail, meta)
    with _combined_task_lock:
        task = _combined_tasks.setdefault(task_id, {})
        task["status"] = "running"
        task["progress"] = round(progress, 2)
        task["stage"] = stage
        task["detail"] = detail
        task["meta"] = meta or {}
        history = task.setdefault("history", [])
        if not history or history[-1] != history_item:
            history.append(history_item)
            if len(history) > 80:
                del history[:-80]


def _run_combined_task(
    task_id: str,
    *,
    results_root: Path,
    samples: List[Dict[str, Any]],
    selected_chains: List[str],
    selected_modules: List[str],
    field_mapping: Dict[str, str],
    output_name: Optional[str],
    heatmap_color_scheme: str,
    heatmap_annotation: bool,
    treemap_min_copy_default: Any,
    treemap_top_n: Any,
    treemap_topclone_only: Any,
    treemap_layout_mode: str,
    treemap_canvas_shape: str,
    base_path: Optional[str],
    db_alignment_profile_path: Optional[str],
    db_alignment_categories: List[str],
    db_alignment_contained_pathology: bool,
    db_alignment_pathology_values: List[str],
) -> None:
    try:
        modules: Dict[str, Dict[str, Any]] = {}
        completed_modules = 0
        total_modules = len(selected_modules)

        _record_stage(
            task_id,
            5.0,
            "准备任务",
            f"开始生成: {' / '.join(selected_modules)}",
            {
                "phase": "init",
                "module": "combined",
                "sample_count": len(samples),
                "selected_chains": list(selected_chains),
                "selected_modules": list(selected_modules),
            },
        )

        progress_base = 10.0
        progress_total = 85.0
        progress_step = progress_total / max(total_modules, 1)

        for index, module_name in enumerate(selected_modules):
            start_progress = progress_base + progress_step * index
            end_progress = progress_base + progress_step * (index + 1)

            try:
                if module_name == "heatmap":
                    _record_stage(
                        task_id,
                        start_progress,
                        "Heatmap | 读取数据",
                        "正在计算链式相似度矩阵",
                        {"phase": "read_input", "module": "heatmap", "module_label": "Heatmap"},
                    )
                    modules["heatmap"] = _generate_heatmap_report(
                        results_root=results_root,
                        samples=samples,
                        selected_chains=selected_chains,
                        field_mapping=field_mapping,
                        output_name=f"{output_name}_heatmap" if output_name else None,
                        color_scheme=heatmap_color_scheme,
                        annotation=heatmap_annotation,
                    )
                    completed_modules += 1
                    _record_stage(
                        task_id,
                        end_progress,
                        "Heatmap | 完成",
                        "Heatmap 报告已生成",
                        {"phase": "completed", "module": "heatmap", "module_label": "Heatmap"},
                    )
                elif module_name == "treemap":
                    report = get_treemap_report_service(results_root=results_root).generate_report(
                        samples=samples,
                        selected_chains=selected_chains,
                        field_mapping=field_mapping,
                        output_name=f"{output_name}_treemap" if output_name else None,
                        min_copy_default=treemap_min_copy_default,
                        top_n=treemap_top_n,
                        topclone_only=bool(treemap_topclone_only),
                        style="classic",
                        layout_mode=treemap_layout_mode,
                        canvas_shape=treemap_canvas_shape,
                        progress_callback=_scaled_progress_callback(task_id, "treemap", "Treemap", start_progress, end_progress),
                    )
                    modules["treemap"] = {
                        "status": "completed",
                        "label": "Treemap",
                        "job_id": report.job_id,
                        "viewer_url": f"/api/treemap/results/{report.job_id}/viewer.html",
                        "zip_url": f"/api/treemap/export-zip/{report.job_id}",
                        "metadata_url": f"/api/treemap/results/{report.job_id}/metadata.json",
                        "topclone_only": bool(report.metadata.get("topclone_only")),
                        "warnings": report.metadata.get("warnings") or [],
                    }
                    completed_modules += 1
                elif module_name == "chord":
                    report = get_chord_report_service(results_root=results_root).generate_report(
                        samples=samples,
                        selected_chains=selected_chains,
                        field_mapping=field_mapping,
                        output_name=f"{output_name}_chord" if output_name else None,
                        count_mode="rows",
                        progress_callback=_scaled_progress_callback(task_id, "chord", "Chord", start_progress, end_progress),
                    )
                    modules["chord"] = {
                        "status": "completed",
                        "label": "Chord",
                        "job_id": report.job_id,
                        "viewer_url": f"/api/chord/results/{report.job_id}/viewer.html",
                        "zip_url": f"/api/chord/export-zip/{report.job_id}",
                        "metadata_url": f"/api/chord/results/{report.job_id}/metadata.json",
                    }
                    completed_modules += 1
                elif module_name == "db-alignment":
                    modules["db-alignment"] = _generate_db_alignment_report(
                        results_root=results_root,
                        samples=samples,
                        selected_chains=selected_chains,
                        field_mapping=field_mapping,
                        output_name=f"{output_name}_db_alignment" if output_name else None,
                        base_path=base_path,
                        profile_path=db_alignment_profile_path,
                        categories=db_alignment_categories,
                        contained_pathology=db_alignment_contained_pathology,
                        pathology_values=db_alignment_pathology_values,
                        progress_callback=_scaled_progress_callback(task_id, "db-alignment", "DB Alignment", start_progress, end_progress),
                    )
                    completed_modules += 1
            except Exception as exc:
                logger.error("Combined analysis %s generation failed: %s", module_name, exc, exc_info=True)
                modules[module_name] = {
                    "status": "failed",
                    "label": module_name.title(),
                    "message": str(exc),
                }
                _record_stage(
                    task_id,
                    end_progress,
                    f"{module_name.title()} | 失败",
                    str(exc),
                    {"phase": "failed", "module": module_name, "module_label": module_name.title()},
                )

        if completed_modules <= 0:
            raise ValidationError(message="所选模块都未生成成功，请检查输入数据和字段映射")

        failed_modules = [
            name for name in selected_modules if (modules.get(name) or {}).get("status") != "completed"
        ]
        summary = (
            f"已生成 {completed_modules}/{total_modules} 个模块结果"
            if not failed_modules
            else f"已生成 {completed_modules}/{total_modules} 个模块结果，失败模块: {', '.join(failed_modules)}"
        )
        bundle = _write_combined_bundle(
            results_root=results_root,
            requested_name=output_name,
            samples=samples,
            selected_chains=selected_chains,
            selected_modules=selected_modules,
            modules=modules,
            summary=summary,
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        completion_meta = {
            "phase": "completed",
            "module": "combined",
            "completed_modules": completed_modules,
            "total_modules": total_modules,
            "failed_modules": failed_modules,
            "selected_modules": list(selected_modules),
        }
        completion_entry = _history_entry(100.0, "任务完成", summary, completion_meta)
        if not history or history[-1] != completion_entry:
            history.append(completion_entry)

        _set_task_state(
            task_id,
            status="completed",
            progress=100.0,
            stage="任务完成",
            detail=summary,
            meta=completion_meta,
            history=history[-80:],
            result={
                **bundle,
                "summary": summary,
                "modules": modules,
                "completed_modules": completed_modules,
                "failed_modules": failed_modules,
                "selected_modules": list(selected_modules),
            },
        )
    except Exception as exc:
        logger.error("Combined analysis task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        failure_entry = _history_entry(100.0, "任务失败", str(exc), {"phase": "failed", "module": "combined"})
        if not history or history[-1] != failure_entry:
            history.append(failure_entry)
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="任务失败",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "combined"},
            history=history[-80:],
        )


@combined_analysis_bp.route("/generate", methods=["POST"])
def generate_combined_analysis():
    try:
        data = request.get_json() or {}
        samples = _parse_samples(data.get("samples"))

        selected_chains = [
            str(item).strip().upper()
            for item in (data.get("selected_chains") or [])
            if str(item).strip()
        ]
        if not selected_chains:
            raise ValidationError(message="请至少选择 1 条链", details={"field": "selected_chains"})

        selected_modules = _parse_selected_modules(data.get("selected_modules"))
        field_mapping = _parse_field_mapping(data.get("field_mapping"))
        config = data.get("config") or {}

        output_name = str(config.get("output_name") or "").strip() or None
        heatmap_color_scheme = str(config.get("heatmap_color_scheme") or "viridis").strip() or "viridis"
        heatmap_annotation = _as_bool(config.get("heatmap_annotation"), True)
        treemap_min_copy_default = config.get("treemap_min_copy_default", 30)
        treemap_top_n = config.get("treemap_top_n", 100)
        treemap_topclone_only = _as_bool(config.get("treemap_topclone_only"), False)
        treemap_layout_mode = str(config.get("treemap_layout_mode") or "tetris").strip().lower()
        treemap_canvas_shape = str(config.get("treemap_canvas_shape") or "square").strip().lower()
        base_path = str(config.get("base_path") or "").strip() or None
        db_alignment_profile_path = str(config.get("db_alignment_profile_path") or "").strip() or None
        db_alignment_categories = [
            str(item).strip()
            for item in (config.get("db_alignment_categories") or [])
            if str(item).strip()
        ]
        db_alignment_contained_pathology = _as_bool(config.get("db_alignment_contained_pathology"), False)
        db_alignment_pathology_values = [
            str(item).strip()
            for item in (config.get("db_alignment_pathology_values") or [])
            if str(item).strip()
        ]
        if treemap_layout_mode not in {"tetris", "qr"}:
            treemap_layout_mode = "tetris"
        if treemap_canvas_shape not in {"square", "portrait"}:
            treemap_canvas_shape = "square"

        results_root = _resolve_results_root()
        task_id = f"combined_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {
            "phase": "queued",
            "module": "combined",
            "sample_count": len(samples),
            "selected_chains": list(selected_chains),
            "selected_modules": list(selected_modules),
        }
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="任务已创建",
            detail="任务已进入队列，等待开始",
            meta=queued_meta,
            history=[_history_entry(0.0, "任务已创建", "任务已进入队列，等待开始", queued_meta)],
        )

        _combined_executor.submit(
            _run_combined_task,
            task_id,
            results_root=results_root,
            samples=samples,
            selected_chains=selected_chains,
            selected_modules=selected_modules,
            field_mapping=field_mapping,
            output_name=output_name,
            heatmap_color_scheme=heatmap_color_scheme,
            heatmap_annotation=heatmap_annotation,
            treemap_min_copy_default=treemap_min_copy_default,
            treemap_top_n=treemap_top_n,
            treemap_topclone_only=treemap_topclone_only,
            treemap_layout_mode=treemap_layout_mode,
            treemap_canvas_shape=treemap_canvas_shape,
            base_path=base_path,
            db_alignment_profile_path=db_alignment_profile_path,
            db_alignment_categories=db_alignment_categories,
            db_alignment_contained_pathology=db_alignment_contained_pathology,
            db_alignment_pathology_values=db_alignment_pathology_values,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/combined-analysis/task/{task_id}"})

    except ValidationError as exc:
        logger.warning("Validation error in generate_combined_analysis: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400

    except Exception as exc:
        logger.error("Error queuing combined analysis task: %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "COMBINED_ANALYSIS_ERROR",
                "message": f"生成一键分析任务时发生错误: {str(exc)}",
            }
        ), 500


@combined_analysis_bp.route("/task/<task_id>", methods=["GET"])
def get_combined_analysis_task(task_id: str):
    task = _get_task_state(task_id)
    if not task:
        return jsonify({"success": False, "error": "NOT_FOUND", "message": "任务不存在"}), 404
    return jsonify({"success": True, **task})


@combined_analysis_bp.route("/results/<job_id>/<path:relative_path>", methods=["GET"])
def get_combined_analysis_result(job_id: str, relative_path: str):
    try:
        if not job_id:
            raise ValidationError(message="job_id is required")
        if not relative_path:
            raise ValidationError(message="relative_path is required")

        base_dir = (_resolve_results_root() / _RESULT_DIR / job_id).resolve()
        if not base_dir.exists() or not base_dir.is_dir():
            raise FileNotFoundError(job_id)

        target_path = (base_dir / relative_path).resolve()
        try:
            target_path.relative_to(base_dir)
        except ValueError as exc:
            raise ValidationError(message="Invalid result path") from exc

        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(target_path)

        return send_file(target_path)

    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400

    except FileNotFoundError:
        return jsonify({"success": False, "error": "NOT_FOUND", "message": "结果文件不存在"}), 404

    except Exception as exc:
        logger.error("Error serving combined analysis result file: %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "COMBINED_RESULT_READ_ERROR",
                "message": f"读取结果文件时发生错误: {str(exc)}",
            }
        ), 500
