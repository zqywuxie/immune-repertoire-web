"""Enrichment and visualization routes: umap, volcano, go-kegg, umapin, ml-analysis, mait-nkt."""

import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request

from flask_app.exceptions import ValidationError
from flask_app.services.umap_service import UmapService
from flask_app.services.volcano_service import VolcanoService
from flask_app.services.go_kegg_enrichment_service import GoKeggEnrichmentService
from flask_app.services.umapin_service import UmapinService
from flask_app.services.ml_analysis_service import MLAnalysisService
from flask_app.services.mait_nkt_service import MaitNktService
from flask_app.services.figure_style import save_publication_png
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.path_config import RESULTS_DIR
from ._common import (
    _ALLOWED_MODULES,
    _RESULT_DIR,
    _as_bool,
    _build_and_save_viewer,
    _build_script_cache_context,
    _collect_project_cached_usage_assets,
    _collect_project_script_hub_assets,
    _complete_script_task,
    _force_rerun_requested,
    _get_task_state,
    _history_entry,
    _infer_wide_chain_from_filename,
    _iter_candidate_pep_files,
    _normalize_chain,
    _normalize_script_result,
    _profile_path_from_request,
    _looks_like_category_row,
    _read_header_columns,
    _read_table_columns,
    _record_stage,
    _resolve_usage_data_dir,
    _request_registered_assets,
    _resolve_pep_analysis_tra_source,
    _resolve_project_cached_usage_path,
    _resolve_results_root,
    _robust_read_csv,
    _sanitize_nan,
    _script_executor,
    _set_task_state,
    _suggest_profile_ranges,
    _suggest_umap_ranges,
    _transcriptome_path_from_request,
    _try_reuse_script_result,
    get_script_hub_job_service,
    logger,
)
from .profile_analysis import _suggest_profile_ranges, _suggest_umap_ranges
bp = Blueprint("script_hub_enrichment", __name__)

def _run_umap_task(
    task_id: str,
    *,
    results_root: Path,
    datapoint_path: str,
    classification_begin: str,
    classification_over: str,
    param_begin: str,
    param_over: str,
    pvalue_threshold: float = 0.05,
    n_neighbors: int = 6,
    min_dist: float = 0.01,
    output_name: Optional[str] = None,
    module_name: str = "umap",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "UMAP inspect", f"Reading {datapoint_path}", {"module": module_name})
        dp_path = str(datapoint_path)
        if Path(dp_path).exists():
            columns = _robust_read_csv(dp_path, nrows=0).columns.tolist()
        else:
            raise FileNotFoundError(f"Datapoint file not found: {dp_path}")
        if (not classification_begin or not classification_over) and columns:
            range_suggestions = _suggest_umap_ranges(columns)
            classification_begin = classification_begin or range_suggestions["suggested_classification_begin"]
            classification_over = classification_over or range_suggestions["suggested_classification_over"]
        if classification_begin not in columns:
            raise ValidationError(message=f"classification_begin not found: {classification_begin}")
        if classification_over not in columns:
            raise ValidationError(message=f"classification_over not found: {classification_over}")
        if param_begin not in columns:
            raise ValidationError(message=f"param_begin not found: {param_begin}")
        if param_over not in columns:
            raise ValidationError(message=f"param_over not found: {param_over}")

        _record_stage(task_id, 10, "UMAP analysis", f"Starting with {len(columns)} columns", {"module": module_name})

        service = UmapService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            datapoint_path=dp_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            )
        )

        png_urls = []
        for p in report.png_paths:
            rel = Path(p).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        csv_urls = []
        for c in report.csv_paths:
            rel = Path(c).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        pdf_urls = []
        for p in report.pdf_paths:
            rel = Path(p).relative_to(report.output_base)
            pdf_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        zip_url = ""
        if report.zip_path:
            zp = Path(report.zip_path)
            if zp.exists():
                rel = zp.relative_to(report.output_base)
                zip_url = f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "pdf_urls": pdf_urls,
            "csv_urls": csv_urls,
            "zip_url": zip_url,
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="UMAP Analysis Results",
            subtitle="Profile: " + str(report.metadata.get("datapoint_path") or datapoint_path),
            dl_extras=[("csv_urls", None, "UMAP CSV"), ("pdf_urls", None, "UMAP PDF")],
            zip_name="umap_results.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=report.metadata.get("message") or f"UMAP generated {len(report.png_paths)} plots",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("UMAP task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="Failed",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@bp.route("/umap/inspect", methods=["POST"])
def inspect_umap():
    try:
        data = request.get_json() or {}
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required", details={"field": "datapoint_path"})

        dp = Path(datapoint_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="Datapoint file not found", details={"datapoint_path": datapoint_path})
        df = _robust_read_csv(dp, nrows=0)
        columns = df.columns.tolist()
        suggestions = _suggest_umap_ranges(columns)
        return jsonify({
            "success": True,
            "datapoint_path": str(dp.resolve()),
            "columns": columns,
            "column_count": len(columns),
            **suggestions,
        })
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@bp.route("/umap/run", methods=["POST"])
def run_umap():
    try:
        data = request.get_json() or {}
        module_name = "umap"
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        classification_begin = str(data.get("classification_begin") or "").strip()
        classification_over = str(data.get("classification_over") or "").strip()
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()

        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required")

        dp = Path(datapoint_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="Datapoint file not found", details={"datapoint_path": datapoint_path})
        columns = _robust_read_csv(dp, nrows=0).columns.tolist()
        suggestions = _suggest_umap_ranges(columns)
        classification_begin = classification_begin or suggestions["suggested_classification_begin"]
        classification_over = classification_over or suggestions["suggested_classification_over"]
        param_begin = param_begin or suggestions["suggested_param_begin"]
        param_over = param_over or suggestions["suggested_param_over"]
        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")
        if not classification_begin or not classification_over:
            raise ValidationError(message="classification_begin and classification_over are required")

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        n_neighbors = int(data.get("n_neighbors") or 6)
        min_dist = float(data.get("min_dist") or 0.01)
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "profile", "path": datapoint_path}],
            config_json={
                "classification_begin": classification_begin,
                "classification_over": classification_over,
                "param_begin": param_begin,
                "param_over": param_over,
                "pvalue_threshold": pvalue_threshold,
                "n_neighbors": n_neighbors,
                "min_dist": min_dist,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="Queued",
                        detail="Task created", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "Queued", "Task created", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_umap_task, task_id,
            results_root=_resolve_results_root(),
            datapoint_path=datapoint_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            output_name=output_name,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- Volcano Analysis ----

def _usage_union_columns(data_dir: Path) -> List[str]:
    columns: List[str] = ["sample", "Category"]
    seen = set(columns)
    for csv_path in sorted(data_dir.glob("*.csv")):
        header = _read_header_columns(csv_path)
        if "Category" not in header:
            continue
        category_idx = header.index("Category")
        for col in header[category_idx + 1:]:
            if col not in seen:
                seen.add(col)
                columns.append(col)
    return columns


def _parse_group_comparisons(raw_value: Any) -> List[List[str]]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        pairs = []
        for line in re.split(r"[\n;]+", text):
            line = line.strip()
            if not line:
                continue
            if "_vs_" in line:
                left, right = line.split("_vs_", 1)
            elif "," in line:
                left, right = line.split(",", 1)
            else:
                continue
            pairs.append([left.strip(), right.strip()])
        return [pair for pair in pairs if pair[0] and pair[1] and pair[0] != pair[1]]
    if isinstance(raw_value, list):
        pairs = []
        for item in raw_value:
            if isinstance(item, dict):
                left = str(item.get("group1") or "").strip()
                right = str(item.get("group2") or "").strip()
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                left = str(item[0] or "").strip()
                right = str(item[1] or "").strip()
            else:
                continue
            if left and right and left != right:
                pairs.append([left, right])
        return pairs
    return []


@bp.route("/volcano/inspect", methods=["POST"])
def inspect_volcano():
    try:
        data = request.get_json() or {}
        input_mode = str(data.get("input_mode") or "usage").strip().lower()
        if input_mode == "expression":
            expression_path = _transcriptome_path_from_request(
                data,
                "expression_path",
                "transcriptome_path",
                "profile_path",
                "datapoint_path",
            ) or ""
            if not expression_path:
                raise ValidationError(message="expression_path is required", details={"field": "expression_path"})
            group_prefix = str(data.get("group_prefix") or "tpm_").strip()
            inspect = VolcanoService.inspect_expression_matrix(expression_path, group_prefix=group_prefix)
            return jsonify({"success": True, "input_mode": "expression", **inspect})

        data_dir = str(data.get("data_dir") or "").strip() or _resolve_project_cached_usage_path(data, preferred="volcano")
        base_path = str(data.get("base_path") or "").strip()

        if not data_dir and not base_path:
            raise ValidationError(message="data_dir or base_path is required", details={"field": "data_dir"})

        search_dir = data_dir or base_path
        dp = Path(search_dir)
        if not dp.exists():
            raise ValidationError(message=f"Directory not found: {search_dir}", details={"data_dir": search_dir})

        if dp.is_file():
            dp = dp.parent
        dp = _resolve_usage_data_dir(dp)

        file_list = sorted([str(f.resolve()) for f in list(dp.glob("df*.csv")) + list(dp.glob("df*.csv.gz")) if f.is_file()])
        if not file_list:
            file_list = sorted([str(f.resolve()) for f in list(dp.glob("*.csv")) + list(dp.glob("*.csv.gz")) if f.is_file()])

        return jsonify({
            "success": True,
            "data_dir": str(dp.resolve()),
            "file_count": len(file_list),
            "files": [Path(f).name for f in file_list[:20]],
        })
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Volcano inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_volcano_task(
    task_id: str,
    *,
    results_root: Path,
    data_dir: str,
    input_mode: str = "usage",
    expression_path: str = "",
    group_prefix: str = "tpm_",
    comparisons: Optional[List[List[str]]] = None,
    pvalue_threshold: float = 0.05,
    logfc_cutoff: float = 1.0,
    module_name: str = "volcano",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "火山图分析", f"扫描 {expression_path or data_dir}", {"module": module_name})

        local_data_dir = data_dir

        service = VolcanoService(output_parent=results_root / _RESULT_DIR)
        if input_mode == "expression":
            report = service.generate_expression_report(
                expression_path=expression_path,
                group_prefix=group_prefix,
                comparisons=comparisons or None,
                pvalue_threshold=pvalue_threshold,
                logfc_cutoff=logfc_cutoff,
                progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                    task_id, float(progress or 0.0), stage, detail,
                    {"module": module_name, **(meta or {})}
                )
            )
        else:
            report = service.generate_report(
                data_dir=local_data_dir,
                pvalue_threshold=pvalue_threshold,
                progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                    task_id, float(progress or 0.0), stage, detail,
                    {"module": module_name, **(meta or {})}
                )
            )

        png_urls = []
        for p in report.png_paths:
            rel = Path(p).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        csv_urls = []
        for c in report.csv_paths:
            rel = Path(c).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "csv_urls": csv_urls,
            "metadata": report.metadata,
        }
        # Generate viewer.html for Volcano
        _build_and_save_viewer(report.output_base, result, report.metadata,
            title="Volcano Plot Results",
            subtitle="Data: " + str(report.metadata.get("expression_path") or report.metadata.get("data_dir", "")),
            dl_extras=[("csv_urls", None, "Volcano CSV")])
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="Volcano Plot Results",
            subtitle="Data: " + str(report.metadata.get("expression_path") or report.metadata.get("data_dir", "")),
            dl_extras=[("csv_urls", None, "Volcano CSV")],
            zip_name="volcano_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"火山图分析完成，生成 {len(png_urls)} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("Volcano task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@bp.route("/volcano/run", methods=["POST"])
def run_volcano():
    try:
        data = request.get_json() or {}
        module_name = "volcano"
        input_mode = str(data.get("input_mode") or "usage").strip().lower()
        data_dir = ""
        expression_path = ""
        group_prefix = str(data.get("group_prefix") or "tpm_").strip()
        comparisons = _parse_group_comparisons(data.get("comparisons"))
        if input_mode == "expression":
            expression_path = _transcriptome_path_from_request(
                data,
                "expression_path",
                "transcriptome_path",
                "profile_path",
                "datapoint_path",
            ) or ""
            if not expression_path:
                raise ValidationError(message="expression_path is required", details={"field": "expression_path"})
        else:
            data_dir = str(data.get("data_dir") or "").strip() or _resolve_project_cached_usage_path(data, preferred="volcano")
            if not data_dir:
                raise ValidationError(message="data_dir is required", details={"field": "data_dir"})
        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        logfc_cutoff = float(data.get("logfc_cutoff") or 1.0)
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "transcriptome" if input_mode == "expression" else "cached_usage", "path": expression_path or data_dir}],
            config_json={
                "input_mode": input_mode,
                "group_prefix": group_prefix if input_mode == "expression" else "",
                "comparisons": comparisons if input_mode == "expression" else [],
                "pvalue_threshold": pvalue_threshold,
                "logfc_cutoff": logfc_cutoff if input_mode == "expression" else None,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_volcano_task, task_id,
            results_root=_resolve_results_root(),
            data_dir=data_dir,
            input_mode=input_mode,
            expression_path=expression_path,
            group_prefix=group_prefix,
            comparisons=comparisons,
            pvalue_threshold=pvalue_threshold,
            logfc_cutoff=logfc_cutoff,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- GO / KEGG Enrichment ----

@bp.route("/go-kegg-enrichment/inspect", methods=["POST"])
def inspect_go_kegg_enrichment():
    try:
        data = request.get_json() or {}
        expression_path = _transcriptome_path_from_request(
            data,
            "expression_path",
            "transcriptome_path",
            "profile_path",
            "datapoint_path",
        ) or ""
        if not expression_path:
            raise ValidationError(message="expression_path is required", details={"field": "expression_path"})
        group_prefix = str(data.get("group_prefix") or "tpm_").strip()
        inspect = GoKeggEnrichmentService.inspect_expression_matrix(expression_path, group_prefix=group_prefix)
        return jsonify({"success": True, **inspect})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting GO/KEGG inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_go_kegg_enrichment_task(
    task_id: str,
    *,
    results_root: Path,
    expression_path: str,
    group_prefix: str = "tpm_",
    comparisons: Optional[List[List[str]]] = None,
    pvalue_threshold: float = 0.05,
    logfc_cutoff: float = 1.0,
    enrich_pvalue_cutoff: float = 0.05,
    p_adjust_method: str = "none",
    show_category: int = 20,
    simplify_go: bool = True,
    do_gsea: bool = True,
    output_name: Optional[str] = None,
    module_name: str = "go-kegg-enrichment",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 4, "GO/KEGG", f"读取表达矩阵 {expression_path}", {"module": module_name})
        service = GoKeggEnrichmentService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            expression_path=expression_path,
            group_prefix=group_prefix,
            comparisons=comparisons or None,
            pvalue_threshold=pvalue_threshold,
            logfc_cutoff=logfc_cutoff,
            enrich_pvalue_cutoff=enrich_pvalue_cutoff,
            p_adjust_method=p_adjust_method,
            show_category=show_category,
            simplify_go=simplify_go,
            do_gsea=do_gsea,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            ),
        )

        def _url(path_value: str) -> str:
            path = Path(path_value)
            rel = path.relative_to(report.output_base)
            return f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": [_url(p) for p in report.png_paths],
            "csv_urls": [_url(p) for p in report.csv_paths],
            "log_url": _url(report.log_path),
            "zip_url": _url(report.zip_path),
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="GO / KEGG Enrichment Results",
            subtitle="Expression: " + str(report.metadata.get("expression_path", "")),
            dl_extras=[("csv_urls", None, "CSV"), ("log_url", "go_kegg_enrichment.log", "Log")],
            zip_name="go_kegg_enrichment_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"GO/KEGG 富集分析完成，生成 {len(report.csv_paths)} 个表格和 {len(report.png_paths)} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("GO/KEGG task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@bp.route("/go-kegg-enrichment/run", methods=["POST"])
def run_go_kegg_enrichment():
    try:
        data = request.get_json() or {}
        module_name = "go-kegg-enrichment"
        expression_path = _transcriptome_path_from_request(
            data,
            "expression_path",
            "transcriptome_path",
            "profile_path",
            "datapoint_path",
        ) or ""
        if not expression_path:
            raise ValidationError(message="expression_path is required", details={"field": "expression_path"})
        group_prefix = str(data.get("group_prefix") or "tpm_").strip()
        comparisons = _parse_group_comparisons(data.get("comparisons"))
        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        logfc_cutoff = float(data.get("logfc_cutoff") or 1.0)
        enrich_pvalue_cutoff = float(data.get("enrich_pvalue_cutoff") or 0.05)
        p_adjust_method = str(data.get("p_adjust_method") or "none").strip() or "none"
        show_category = int(data.get("show_category") or 20)
        simplify_go = _as_bool(data.get("simplify_go"), True)
        do_gsea = _as_bool(data.get("do_gsea"), True)
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "transcriptome", "path": expression_path}],
            config_json={
                "group_prefix": group_prefix,
                "comparisons": comparisons,
                "pvalue_threshold": pvalue_threshold,
                "logfc_cutoff": logfc_cutoff,
                "enrich_pvalue_cutoff": enrich_pvalue_cutoff,
                "p_adjust_method": p_adjust_method,
                "show_category": show_category,
                "simplify_go": simplify_go,
                "do_gsea": do_gsea,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)
        _script_executor.submit(
            _run_go_kegg_enrichment_task, task_id,
            results_root=_resolve_results_root(),
            expression_path=expression_path,
            group_prefix=group_prefix,
            comparisons=comparisons,
            pvalue_threshold=pvalue_threshold,
            logfc_cutoff=logfc_cutoff,
            enrich_pvalue_cutoff=enrich_pvalue_cutoff,
            p_adjust_method=p_adjust_method,
            show_category=show_category,
            simplify_go=simplify_go,
            do_gsea=do_gsea,
            output_name=output_name,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- UMAPin Analysis ----

@bp.route("/umapin/inspect", methods=["POST"])
def inspect_umapin():
    try:
        data = request.get_json() or {}
        data_path = str(data.get("data_path") or "").strip() or _resolve_project_cached_usage_path(data, preferred="umapin")
        if not data_path:
            base_path = str(data.get("base_path") or "").strip()
            if base_path:
                data_path = base_path
            else:
                raise ValidationError(message="data_path or base_path is required", details={"field": "data_path"})

        dp = Path(data_path)
        if not dp.exists():
            raise ValidationError(message=f"File not found: {data_path}", details={"data_path": data_path})

        resolved_dir = None
        union_columns: List[str] = []
        if dp.is_dir():
            dp = _resolve_usage_data_dir(dp)
            resolved_dir = dp
            found = None
            for cn in ("df_VJ_all.csv", "df_1VJusage_all.csv", "df_VJ.csv", "df_all.csv"):
                cdt = dp / cn
                if cdt.exists() and cdt.is_file():
                    found = cdt
                    break
            if found:
                dp = found
            else:
                union_columns = _usage_union_columns(dp)

        if union_columns:
            columns = union_columns
            data_path_value = str((resolved_dir or dp).resolve())
        elif not dp.is_file():
            raise ValidationError(message=f"Not a file: {dp}", details={"data_path": str(dp)})
        else:
            columns = _robust_read_csv(dp, nrows=0).columns.tolist()
            data_path_value = str(dp.resolve())

        cat_candidates = [c for c in columns if c.lower() in ("category", "group", "therapy", "disease")]
        category_col = cat_candidates[0] if cat_candidates else ""

        return jsonify({
            "success": True,
            "data_path": data_path_value,
            "columns": columns,
            "column_count": len(columns),
            "category_col": category_col,
            "suggested_param_begin": columns[2] if len(columns) > 2 else (columns[0] if columns else ""),
            "suggested_param_over": columns[-1] if columns else "",
        })
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting UMAPin inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_umapin_task(
    task_id: str,
    *,
    results_root: Path,
    data_path: str,
    param_begin: str,
    param_over: str,
    category_col: str = "Category",
    n_neighbors: int = 6,
    min_dist: float = 0.01,
    do_fdr: bool = False,
    module_name: str = "umapin",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "UMAPin", f"读取 {data_path}", {"module": module_name})

        dp = data_path

        service = UmapinService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            data_path=dp,
            param_begin=param_begin,
            param_over=param_over,
            category_col=category_col,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            do_fdr=do_fdr,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            )
        )

        png_urls = []
        for p in report.png_paths:
            rel = Path(p).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
        csv_urls = []
        for c in report.csv_paths:
            rel = Path(c).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "csv_urls": csv_urls,
            "metadata": report.metadata,
        }
        # Generate viewer.html for UMAPin
        _build_and_save_viewer(report.output_base, result, report.metadata,
            title="UMAPin Dimensionality Reduction Results",
            subtitle="Features: " + str(report.metadata.get("feature_count", "")) + " | Groups: " + ", ".join(report.metadata.get("unique_groups", [])),
            dl_extras=[("csv_urls", None, "UMAPin CSV")])
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="UMAPin Dimensionality Reduction Results",
            subtitle="Features: " + str(report.metadata.get("feature_count", "")) + " | Groups: " + ", ".join(report.metadata.get("unique_groups", [])),
            dl_extras=[("csv_urls", None, "UMAPin CSV")],
            zip_name="umapin_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"UMAPin 完成，{len(png_urls)} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("UMAPin task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@bp.route("/umapin/run", methods=["POST"])
def run_umapin():
    try:
        data = request.get_json() or {}
        module_name = "umapin"
        data_path = str(data.get("data_path") or "").strip() or _resolve_project_cached_usage_path(data, preferred="umapin")
        if not data_path:
            raise ValidationError(message="data_path is required", details={"field": "data_path"})

        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()
        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")

        category_col = str(data.get("category_col") or "Category").strip()
        n_neighbors = int(data.get("n_neighbors") or 6)
        min_dist = float(data.get("min_dist") or 0.01)
        do_fdr = bool(data.get("do_fdr") or False)
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "cached_usage", "path": data_path}],
            config_json={
                "param_begin": param_begin,
                "param_over": param_over,
                "category_col": category_col,
                "n_neighbors": n_neighbors,
                "min_dist": min_dist,
                "do_fdr": do_fdr,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_umapin_task, task_id,
            results_root=_resolve_results_root(),
            data_path=data_path,
            param_begin=param_begin,
            param_over=param_over,
            category_col=category_col,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            do_fdr=do_fdr,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- Machine Learning Analysis ----

def _suggest_ml_label(columns: List[str]) -> str:
    preferred = ["group_type", "timepoint", "Category", "category", "group", "disease", "therapy"]
    lower_map = {str(col).lower(): col for col in columns}
    for key in preferred:
        if key.lower() in lower_map:
            return lower_map[key.lower()]
    non_sample = [col for col in columns if str(col).strip().lower() not in {"sample", "sample_id", "id"}]
    return non_sample[0] if non_sample else (columns[0] if columns else "")


def _suggest_ml_sample(columns: List[str]) -> str:
    lower_map = {str(col).lower(): col for col in columns}
    for key in ("sample", "sample_id", "sampleid", "id"):
        if key in lower_map:
            return lower_map[key]
    return columns[0] if columns else "Sample"


def _list_payload(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _ml_profile_feature_candidates(
    profile_file: Path,
    columns: List[str],
    *,
    sample_col: str,
    label_col: str,
    filter_col: str = "",
) -> List[str]:
    excluded = {sample_col, label_col}
    if filter_col:
        excluded.add(filter_col)
    try:
        preview_df = _robust_read_csv(profile_file, nrows=200, low_memory=False)
    except TypeError:
        preview_df = _robust_read_csv(profile_file, nrows=200)
    except Exception:
        preview_df = pd.DataFrame(columns=columns)
    candidates: List[str] = []
    for col in columns:
        if col in excluded:
            continue
        if col in preview_df.columns:
            numeric = pd.to_numeric(preview_df[col], errors="coerce")
            if not numeric.notna().any():
                continue
        candidates.append(col)
    return candidates


def _ml_usage_feature_range(
    *,
    profile_path: str,
    usage_path: str,
    sample_col: str,
    param_begin: str,
    param_over: str,
) -> List[str]:
    profile_file = Path(profile_path)
    profile_df = _robust_read_csv(profile_file, low_memory=False)
    sample_source_col = sample_col if sample_col in profile_df.columns else _suggest_ml_sample(profile_df.columns.tolist())
    profile_samples = set(profile_df[sample_source_col].dropna().astype(str))
    candidates = MLAnalysisService.collect_usage_feature_candidates(
        profile_samples=profile_samples,
        usage_path=usage_path,
        sample_col=sample_source_col,
    )
    values = [str(item.get("value") or "").strip() for item in candidates if str(item.get("value") or "").strip()]
    if not values:
        return []
    if not param_begin or not param_over:
        return values
    if param_begin not in values or param_over not in values:
        raise ValidationError(
            message="VJ usage param_begin or param_over not found in usage features",
            details={"param_begin": param_begin, "param_over": param_over},
        )
    start = values.index(param_begin)
    end = values.index(param_over)
    if start > end:
        start, end = end, start
    return values[start:end + 1]


@bp.route("/ml-analysis/inspect", methods=["POST"])
def inspect_ml_analysis():
    try:
        data = request.get_json() or {}
        project_id = str(data.get("project_id") or "").strip()
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path")
        if not profile_path:
            raise ValidationError(message="Profile file is required", details={"field": "profile_path"})

        profile_file = Path(profile_path)
        if not profile_file.exists():
            raise ValidationError(message=f"Profile file not found: {profile_path}", details={"profile_path": profile_path})

        columns = _read_table_columns(profile_file)
        if not columns:
            raise ValidationError(message="No columns detected from Profile file", details={"profile_path": profile_path})

        usage_path = str(data.get("usage_path") or "").strip() or _resolve_project_cached_usage_path(data, preferred="umapin")
        cached_usage_assets = _collect_project_cached_usage_assets(project_id) if project_id else []
        suggestions = _suggest_profile_ranges(columns)
        label_col = str(data.get("label_col") or "").strip() or _suggest_ml_label(columns)
        sample_col = str(data.get("sample_col") or "").strip() or _suggest_ml_sample(columns)
        filter_col = str(data.get("filter_col") or "").strip()

        filter_candidates = [
            col for col in columns
            if col not in {sample_col}
            and len(col) < 80
        ]
        profile_feature_candidates = _ml_profile_feature_candidates(
            profile_file,
            columns,
            sample_col=sample_col,
            label_col=label_col,
            filter_col=filter_col,
        )
        usage_feature_candidates: List[Dict[str, str]] = []
        if usage_path:
            try:
                profile_df = _robust_read_csv(profile_file, low_memory=False)
                sample_source_col = sample_col if sample_col in profile_df.columns else _suggest_ml_sample(profile_df.columns.tolist())
                profile_samples = set(profile_df[sample_source_col].dropna().astype(str))
                usage_feature_candidates = MLAnalysisService.collect_usage_feature_candidates(
                    profile_samples=profile_samples,
                    usage_path=usage_path,
                    sample_col=sample_source_col,
                )
            except Exception:
                logger.warning("Failed to inspect ML usage feature candidates", exc_info=True)

        return jsonify({
            "success": True,
            "profile_path": str(profile_file.resolve()),
            "usage_path": usage_path,
            "columns": columns,
            "column_count": len(columns),
            "sample_col": sample_col,
            "label_col": label_col,
            "filter_candidates": filter_candidates,
            "profile_feature_candidates": profile_feature_candidates,
            "usage_feature_candidates": usage_feature_candidates,
            "suggested_param_begin": suggestions.get("param_begin") or (columns[0] if columns else ""),
            "suggested_param_over": suggestions.get("param_over") or (columns[-1] if columns else ""),
            "cached_usage_assets": cached_usage_assets[:20],
        })
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting ML inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_ml_analysis_task(
    task_id: str,
    *,
    results_root: Path,
    profile_path: str,
    mode: str,
    label_col: str,
    sample_col: str,
    param_begin: str,
    param_over: str,
    usage_path: str,
    filter_col: str,
    filter_value: str,
    feature_cols: List[str],
    usage_feature_cols: List[str],
    custom_threshold: float,
    cv_splits: int,
    roc_cv_splits: int,
    module_name: str = "ml-analysis",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "机器学习分析", f"读取 Profile: {profile_path}", {"module": module_name})

        service = MLAnalysisService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            profile_path=profile_path,
            mode=mode,
            label_col=label_col,
            sample_col=sample_col,
            param_begin=param_begin,
            param_over=param_over,
            usage_path=usage_path,
            filter_col=filter_col,
            filter_value=filter_value,
            feature_cols=feature_cols,
            usage_feature_cols=usage_feature_cols,
            custom_threshold=custom_threshold,
            cv_splits=cv_splits,
            roc_cv_splits=roc_cv_splits,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            ),
        )

        def _urls(paths: List[str]) -> List[str]:
            urls: List[str] = []
            for path in paths:
                rel = Path(path).relative_to(report.output_base)
                urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            return urls

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": _urls(report.png_paths),
            "csv_urls": _urls(report.csv_paths),
            "text_urls": _urls(report.text_paths),
            "metadata": report.metadata,
        }
        subtitle = (
            "Mode: " + str(report.metadata.get("mode", ""))
            + " | Label: " + str(report.metadata.get("label_col", ""))
            + " | Features: " + str(report.metadata.get("selected_feature_number", ""))
        )
        _build_and_save_viewer(
            report.output_base,
            result,
            report.metadata,
            title="Machine Learning Analysis Results",
            subtitle=subtitle,
            dl_extras=[("csv_urls", None, "ML CSV"), ("text_urls", None, "ML Text")],
        )
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="Machine Learning Analysis Results",
            subtitle=subtitle,
            dl_extras=[("csv_urls", None, "ML CSV"), ("text_urls", None, "ML Text")],
            zip_name="ml_analysis_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"机器学习分析完成，生成 {len(result['png_urls'])} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("ML analysis task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@bp.route("/ml-analysis/run", methods=["POST"])
def run_ml_analysis():
    try:
        data = request.get_json() or {}
        module_name = "ml-analysis"
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path") or ""
        if not profile_path:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})

        mode = str(data.get("mode") or "profile").strip().lower()
        usage_path = str(data.get("usage_path") or "").strip()
        if mode == "vj-usage":
            usage_path = usage_path or _resolve_project_cached_usage_path(data, preferred="umapin")
            if not usage_path:
                raise ValidationError(message="usage_path is required for VJ usage ML", details={"field": "usage_path"})

        label_col = str(data.get("label_col") or "").strip()
        if not label_col:
            raise ValidationError(message="label_col is required", details={"field": "label_col"})

        sample_col = str(data.get("sample_col") or "Sample").strip() or "Sample"
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()
        filter_col = str(data.get("filter_col") or "").strip()
        filter_value = str(data.get("filter_value") or "").strip()
        feature_cols = _list_payload(data.get("feature_cols"))
        usage_feature_cols = _list_payload(data.get("usage_feature_cols"))
        if mode == "profile":
            feature_cols = []
            if not param_begin or not param_over:
                raise ValidationError(message="param_begin and param_over are required for Profile ML", details={"fields": ["param_begin", "param_over"]})
            usage_feature_cols = []
        if mode == "vj-usage":
            if not param_begin or not param_over:
                raise ValidationError(message="param_begin and param_over are required for VJ usage ML", details={"fields": ["param_begin", "param_over"]})
            usage_feature_cols = _ml_usage_feature_range(
                profile_path=profile_path,
                usage_path=usage_path,
                sample_col=sample_col,
                param_begin=param_begin,
                param_over=param_over,
            )
            if not usage_feature_cols:
                raise ValidationError(message="No VJ usage features found in selected parameter range", details={"field": "param_begin,param_over"})
        custom_threshold = float(data.get("custom_threshold") or 0.003)
        cv_splits = int(data.get("cv_splits") or 3)
        roc_cv_splits = int(data.get("roc_cv_splits") or 7)
        project_id = str(data.get("project_id") or "").strip() or None

        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[
                {"asset_type": "profile", "path": profile_path},
                *([{"asset_type": "cached_usage", "path": usage_path}] if usage_path else []),
            ],
            config_json={
                "mode": mode,
                "label_col": label_col,
                "sample_col": sample_col,
                "param_begin": param_begin,
                "param_over": param_over,
                "filter_col": filter_col,
                "filter_value": filter_value,
                **({"feature_cols": feature_cols} if mode != "profile" else {}),
                "usage_feature_cols": usage_feature_cols,
                "custom_threshold": custom_threshold,
                "cv_splits": cv_splits,
                "roc_cv_splits": roc_cv_splits,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_ml_analysis_task, task_id,
            results_root=_resolve_results_root(),
            profile_path=profile_path,
            mode=mode,
            label_col=label_col,
            sample_col=sample_col,
            param_begin=param_begin,
            param_over=param_over,
            usage_path=usage_path,
            filter_col=filter_col,
            filter_value=filter_value,
            feature_cols=feature_cols,
            usage_feature_cols=usage_feature_cols,
            custom_threshold=custom_threshold,
            cv_splits=cv_splits,
            roc_cv_splits=roc_cv_splits,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error running ML analysis: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500

@bp.route("/mait-nkt/inspect", methods=["POST"])
def inspect_mait_nkt():
    try:
        data = request.get_json() or {}
        tra_source = str(data.get("tra_source") or "upload").strip()
        tra_path = str(data.get("tra_path") or "").strip()
        source_job_id = str(data.get("source_job_id") or "").strip()
        profile_path = _profile_path_from_request(data, "profile_path")

        # Resolve TRA data source
        tra_df = None
        resolved_tra_path = ""
        resolved_source_job_id = source_job_id
        resolved_source_kind = tra_source
        resolved_output_base = ""
        if tra_source == "pep_analysis" and tra_path and Path(tra_path).exists() and Path(tra_path).is_file():
            resolved_tra_path = str(PathAccessService.validate_read_path(tra_path))
            resolved_source_kind = "pep_analysis_resolved_path"
            tra_df = _robust_read_csv(Path(resolved_tra_path))
        elif tra_source == "pep_analysis":
            resolved = _resolve_pep_analysis_tra_source(data)
            resolved_tra_path = resolved["path"]
            resolved_source_job_id = str(resolved.get("source_job_id") or source_job_id)
            resolved_source_kind = str(resolved.get("source_kind") or "pep_analysis")
            resolved_output_base = str(resolved.get("output_base") or "")
            tra_df = resolved["dataframe"]
        elif tra_path:
            dp = Path(tra_path)
            if not dp.exists() or not dp.is_file():
                raise ValidationError(message="TRA file not found", details={"file_path": tra_path})
            resolved_tra_path = tra_path
            tra_df = _robust_read_csv(dp)
        else:
            raise ValidationError(
                message="请提供 TRA CSV 文件路径或选择 PEP 共享分析结果",
                details={"tra_source": tra_source},
            )

        # Detect sample columns
        sample_cols = []
        has_category_row = False
        if tra_df is not None and len(tra_df.columns) > 1:
            sample_cols = [str(c) for c in tra_df.columns[1:]]
            if len(tra_df) >= 1:
                second_row = tra_df.iloc[0, 1:]
                if _looks_like_category_row(second_row):
                    has_category_row = True

        # Load profile for group values
        profile_groups: Dict[str, Any] = {}
        if profile_path:
            pp = Path(profile_path)
            if pp.exists():
                pf = _robust_read_csv(pp)
                for col in pf.columns:
                    vals = sorted(set(str(v) for v in pf[col].dropna()))
                    profile_groups[col] = vals

        return jsonify(_sanitize_nan({
            "success": True,
            "tra_source": tra_source,
            "resolved_tra_path": resolved_tra_path,
            "source_job_id": resolved_source_job_id,
            "source_kind": resolved_source_kind,
            "pep_output_base": resolved_output_base,
            "sample_columns": sample_cols,
            "sample_count": len(sample_cols),
            "has_category_row": has_category_row,
            "profile_groups": profile_groups,
        }))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_mait_nkt: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting MAIT/NKT inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@bp.route("/mait-nkt/run", methods=["POST"])
def run_mait_nkt():
    try:
        data = request.get_json() or {}
        module_name = "mait-nkt"

        tra_source = str(data.get("tra_source") or "upload").strip()
        tra_path = str(data.get("tra_path") or "").strip()
        source_job_id = str(data.get("source_job_id") or "").strip()
        profile_path = _profile_path_from_request(data, "profile_path") or ""
        group_field = str(data.get("group_field") or "").strip()
        group_order = str(data.get("group_order") or "").strip() or None

        if not profile_path:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})
        if not group_field:
            raise ValidationError(message="group_field is required", details={"field": "group_field"})

        project_id = str(data.get("project_id") or "").strip() or None
        resolved_tra_path = tra_path
        resolved_source_job_id = source_job_id
        if tra_source == "pep_analysis" and tra_path and Path(tra_path).exists() and Path(tra_path).is_file():
            resolved_tra_path = str(PathAccessService.validate_read_path(tra_path))
        elif tra_source == "pep_analysis":
            resolved = _resolve_pep_analysis_tra_source(data)
            resolved_tra_path = resolved["path"]
            resolved_source_job_id = str(resolved.get("source_job_id") or source_job_id)

        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[
                {"asset_type": "tra", "path": resolved_tra_path} if tra_source == "upload" else {"asset_type": "pep_analysis_tra", "path": resolved_tra_path, "source_job_id": resolved_source_job_id},
                {"asset_type": "profile", "path": profile_path},
            ],
            config_json={"group_field": group_field, "group_order": group_order, "tra_source": tra_source},
        )
        if not _force_rerun_requested(data):
            cached = _try_reuse_script_result(cache_context, module_name)
            if cached:
                return jsonify(_sanitize_nan(cached))

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(
            task_id,
            status="queued",
            module=module_name,
            progress=0.0,
            stage="Queued",
            detail="MAIT/NKT analysis task queued",
            created_at=datetime.now().strftime("%H:%M:%S"),
            history=[_history_entry(0, "Queued", "MAIT/NKT analysis task queued")],
            **cache_context,
        )

        analysis_signature = cache_context.get("analysis_signature", "")

        _script_executor.submit(
            _run_mait_nkt_task,
            task_id,
            results_root=Path(current_app.config.get("RESULTS_FOLDER", str(RESULTS_DIR))),
            tra_source=tra_source,
            tra_path=resolved_tra_path,
            source_job_id=resolved_source_job_id,
            profile_path=profile_path,
            group_field=group_field,
            group_order=group_order,
            project_id=project_id,
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify(_sanitize_nan({
            "success": True,
            "task_id": task_id,
            "status": "queued",
            "module": module_name,
            "status_url": f"/api/script-hub/task/{task_id}",
            "analysis_signature": analysis_signature,
        }))
    except ValidationError as exc:
        logger.warning("Validation error in run_mait_nkt: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error running MAIT/NKT analysis: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


def _run_mait_nkt_task(
    task_id: str,
    *,
    results_root: Path,
    tra_source: str,
    tra_path: str,
    source_job_id: str,
    profile_path: str,
    group_field: str,
    group_order: Optional[str],
    project_id: Optional[str] = None,
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 2, "Loading", "Reading TRA data")
        tra_df = None
        resolved_tra_path = tra_path
        if tra_source == "pep_analysis":
            dp = Path(tra_path) if tra_path else None
            if dp and dp.exists() and dp.is_file():
                tra_df = _robust_read_csv(dp)
                resolved_tra_path = str(dp)
            else:
                resolved = _resolve_pep_analysis_tra_source({
                    "project_id": project_id or "",
                    "source_job_id": source_job_id,
                })
                tra_df = resolved["dataframe"]
                resolved_tra_path = resolved["path"]
        else:
            dp = Path(tra_path)
            if not dp.exists():
                raise ValidationError(message="TRA file not found", details={"file_path": tra_path})
            tra_df = _robust_read_csv(dp)

        _record_stage(task_id, 8, "Loading", "Reading profile data")
        pp = Path(profile_path)
        if not pp.exists():
            raise ValidationError(message="Profile file not found", details={"file_path": profile_path})
        profile_df = _robust_read_csv(pp)

        group_order_list = None
        if group_order:
            group_order_list = [x.strip() for x in group_order.split(",") if x.strip()]

        service = MaitNktService(output_parent=results_root / _RESULT_DIR)

        def _progress(percent, stage, detail):
            _record_stage(task_id, percent, stage, detail)

        report = service.generate_report(
            tra_df=tra_df,
            profile_df=profile_df,
            group_field=group_field,
            group_order=group_order_list,
            progress_callback=_progress,
            job_id=task_id,
            datapoint_path=resolved_tra_path or tra_path,
        )

        # Build result URLs
        png_urls = []
        for png in report.png_paths:
            rel = Path(png).relative_to(report.output_base).as_posix()
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel}")

        result = {
            "module": "mait-nkt",
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "viewer_url": f"/api/script-hub/results/{report.job_id}/viewer.html",
            "png_urls": png_urls,
            "zip_url": f"/api/script-hub/results/{report.job_id}/mait_nkt_results.zip",
            "metadata": report.metadata,
        }

        normalized = _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="MAIT/NKT 分析",
            subtitle=f"分组字段: {group_field}",
            dl_extras=[],
            zip_name="mait_nkt_results.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name="mait-nkt",
            detail=f"MAIT/NKT 分析完成，生成 {len(png_urls)} 张图",
            result=normalized,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("MAIT/NKT task %s failed: %s", task_id, exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="失败",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "mait-nkt"},
            history=history[-80:],
        )


# ── helper: looks like category row ────────────────────────────────────
