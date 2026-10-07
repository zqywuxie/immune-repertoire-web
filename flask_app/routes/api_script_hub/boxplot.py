"""Boxplot analysis routes for the Script Hub API."""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from flask import Blueprint, current_app, jsonify, request

from flask_app.exceptions import ValidationError
from flask_app.services.boxplot_service import BoxPlotService
from flask_app.services.project_storage_paths import script_output_parent
from ._common import (
    _ALLOWED_MODULES,
    _RESULT_DIR,
    _build_script_cache_context,
    _complete_script_task,
    _force_rerun_requested,
    _get_task_state,
    _history_entry,
    _normalize_script_result,
    _profile_path_from_request,
    _record_stage,
    _resolve_results_root,
    _robust_read_csv,
    _sanitize_nan,
    _selected_samples_by_group_from_request,
    _selected_samples_from_request,
    _script_executor,
    _set_task_state,
    _try_reuse_script_result,
    logger,
)

bp = Blueprint("script_hub_boxplot", __name__)

def _discover_boxplot_inputs(base_path: str, datapoint_path: Optional[str]) -> Dict[str, Any]:
    datapoint = None
    file_candidates: List[str] = []

    if datapoint_path:
        dp = Path(datapoint_path)
        if dp.exists() and dp.is_file():
            datapoint = dp
            file_candidates.append(str(dp.resolve()))

    if not file_candidates and base_path:
        base = Path(base_path)
        if not base.exists():
            raise ValidationError(message="Base path does not exist", details={"base_path": base_path})
        search_roots = [base]
        if base.parent != base:
            search_roots.append(base.parent)
        seen: set[str] = set()
        for root in search_roots:
            for pattern in ["*.csv", "*.tsv", "*/*.csv", "*/*.tsv", "**/*.csv", "**/*.tsv"]:
                for candidate in sorted(root.glob(pattern)):
                    resolved = str(candidate.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        file_candidates.append(resolved)
                        if len(file_candidates) >= 50:
                            break
                if len(file_candidates) >= 50:
                    break
            if len(file_candidates) >= 50:
                break

    if datapoint is None and file_candidates:
        datapoint = Path(file_candidates[0])

    if datapoint is None:
        raise ValidationError(
            message="No CSV/TSV files found. Provide a specific datapoint_path or ensure the base_path contains .csv/.tsv files.",
            details={"base_path": base_path, "datapoint_path": datapoint_path}
        )
    try:
        df = _robust_read_csv(datapoint, nrows=0)
    except pd.errors.EmptyDataError as exc:
        raise ValidationError(
            message="Registered Profile file is empty or has no columns.",
            details={"profile_path": str(datapoint.resolve())},
        ) from exc
    columns = df.columns.tolist()
    if not columns:
        raise ValidationError(
            message="Registered Profile file is empty or has no columns.",
            details={"profile_path": str(datapoint.resolve())},
        )
    return {
        "base_path": base_path,
        "datapoint_path": str(datapoint.resolve()),
        "columns": columns,
        "column_count": len(columns),
        "suggested_param_begin": columns[0] if columns else "",
        "suggested_param_over": columns[-1] if columns else "",
        "file_candidates": file_candidates,
    }


def _run_boxplot_task(
    task_id: str,
    *,
    results_root: Path,
    datapoint_path: str,
    classification_begin: str,
    classification_over: str,
    grouptype_fields: Optional[List[str]] = None,
    param_begin: str,
    param_over: str,
    group_order: Optional[str] = None,
    pvalue_threshold: float = 0.05,
    output_name: Optional[str] = None,
    selected_samples: Optional[List[str]] = None,
    selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
    module_name: str = "boxplot",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "检查指标输入", f"正在读取样本指标表：{datapoint_path}", {"module": module_name})
        dp_path = str(datapoint_path)
        if not Path(dp_path).exists():
            raise FileNotFoundError(f"Datapoint file not found: {dp_path}")
        columns = _robust_read_csv(dp_path, nrows=0).columns.tolist()

        if grouptype_fields:
            for gf in grouptype_fields:
                if gf not in columns:
                    raise ValidationError(message=f"grouptype field not found: {gf}", details={"available_columns": columns})
        elif classification_begin:
            if classification_begin not in columns:
                raise ValidationError(message=f"classification_begin column not found: {classification_begin}", details={"available_columns": columns})
            classification_over = classification_over.strip() if classification_over else classification_begin
            if classification_over not in columns:
                raise ValidationError(message=f"classification_over column not found: {classification_over}", details={"available_columns": columns})
        if param_begin not in columns:
            raise ValidationError(message=f"param_begin column not found: {param_begin}", details={"available_columns": columns})
        if param_over not in columns:
            raise ValidationError(message=f"param_over column not found: {param_over}", details={"available_columns": columns})

        _record_stage(task_id, 10, "指标分组分析", f"已读取 {len(columns)} 列，开始核对分组与指标。", {"module": module_name})

        service = BoxPlotService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        report = service.generate_report(
            datapoint_path=dp_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            grouptype_fields=grouptype_fields,
            param_begin=param_begin,
            param_over=param_over,
            group_order=group_order,
            pvalue_threshold=pvalue_threshold,
            output_name=output_name,
            selected_samples=selected_samples,
            selected_samples_by_group=selected_samples_by_group,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                float(progress or 0.0),
                stage,
                detail,
                {"module": module_name, **(meta or {})}
            )
        )

        png_urls: List[str] = []
        for png_path in report.png_paths:
            rel = Path(png_path).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        pvalue_urls: List[str] = []
        for pv_path in report.pvalue_paths:
            rel = Path(pv_path).relative_to(report.output_base)
            pvalue_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        csv_urls: List[str] = []
        for csv_path in report.csv_paths:
            rel = Path(csv_path).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        sig_urls: List[str] = []
        for sig_path in report.significant_paths:
            rel = Path(sig_path).relative_to(report.output_base)
            sig_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        zip_url = ""
        if report.zip_path:
            zp = Path(report.zip_path)
            if zp.exists():
                rel = zp.relative_to(report.output_base)
                zip_url = f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        viewer_url = ""
        if report.viewer_path and report.viewer_path.exists():
            viewer_url = f"/api/script-hub/results/{report.job_id}/viewer.html"

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "viewer_url": viewer_url,
            "png_urls": png_urls,
            "pvalue_urls": pvalue_urls,
            "csv_urls": csv_urls,
            "significant_urls": sig_urls,
            "zip_url": zip_url,
            "metadata_url": f"/api/script-hub/results/{report.job_id}/boxplot_metadata.json",
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title=f"{module_name.title()} Analysis Results",
            subtitle="Profile: " + str(report.metadata.get("datapoint_path") or datapoint_path),
            dl_extras=[("csv_urls", None, "BoxPlot CSV"), ("pvalue_urls", None, "P-value CSV")],
            zip_name="boxplot_results.zip" if module_name == "boxplot" else f"{module_name}_results.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"指标分析已完成，生成 {len(report.png_paths)} 张图。",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("Script hub BoxPlot task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="Failed",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": module_name},
            history=history[-80:]
        )


@bp.route("/boxplot/inspect", methods=["POST"])
def inspect_boxplot():
    try:
        data = request.get_json() or {}
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path")
        base_path = str(data.get("base_path") or "").strip()

        discovery = _discover_boxplot_inputs(base_path, datapoint_path)
        return jsonify(_sanitize_nan({"success": True, **discovery}))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_boxplot: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting BoxPlot inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@bp.route("/boxplot/columns", methods=["POST"])
def get_boxplot_columns():
    try:
        data = request.get_json() or {}
        file_path = str(data.get("file_path") or "").strip()
        if not file_path:
            raise ValidationError(message="file_path is required", details={"field": "file_path"})

        dp = Path(file_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="File not found", details={"file_path": file_path})
        df = _robust_read_csv(dp, nrows=0)

        columns = df.columns.tolist()
        return jsonify({
            "success": True,
            "file_path": file_path,
            "columns": columns,
            "column_count": len(columns),
            "suggested_param_begin": columns[0] if columns else "",
            "suggested_param_over": columns[-1] if columns else "",
        })
    except ValidationError as exc:
        logger.warning("Validation error in get_boxplot_columns: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error reading BoxPlot columns: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_COLUMNS_ERROR", "message": str(exc)}), 500


@bp.route("/boxplot/group-values", methods=["POST"])
def get_boxplot_group_values():
    try:
        data = request.get_json() or {}
        file_path = str(data.get("file_path") or "").strip()
        column = str(data.get("column") or "").strip()
        if not file_path:
            raise ValidationError(message="file_path is required", details={"field": "file_path"})
        if not column:
            raise ValidationError(message="column is required", details={"field": "column"})

        dp = Path(file_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="File not found", details={"file_path": file_path})
        df = _robust_read_csv(dp, dtype=str)

        if column not in df.columns:
            raise ValidationError(message=f"Column not found: {column}", details={"available_columns": df.columns.tolist()})

        sample_col = str(data.get("sample_col") or "").strip() or _detect_sample_column(df.columns.tolist())
        if sample_col and sample_col not in df.columns:
            raise ValidationError(message="所选样本列不存在，请重新选择。", details={"field": "sample_col"})
        raw_values = df[column].dropna().unique().tolist()
        values = sorted({str(v).strip() for v in raw_values if str(v).strip()})
        batch_field = str(data.get("batch_field") or "").strip() or None
        sample_labels, sample_ids = {}, {}
        if batch_field:
            if not sample_col or batch_field not in df.columns or batch_field == sample_col:
                raise ValidationError(message="所选批次字段不存在或与样本编号列相同。", details={"field": "batch_field"})
            from flask_app.services.pep_analysis_service import _batch_sample_identity
            selected = df[[sample_col, batch_field]].astype("string").apply(lambda col: col.str.strip())
            if selected.isna().any().any() or selected.eq("").any().any():
                raise ValidationError(message="样本编号或批次存在空值，请先整理输入。")
            if selected.duplicated().any():
                raise ValidationError(message="同一批次存在重复样本编号，请先整理输入。")
            identities = [_batch_sample_identity(batch, sample) for sample, batch in selected.itertuples(index=False, name=None)]
            sample_labels = dict(zip(identities, [f"{batch} / {sample}" for sample, batch in selected.itertuples(index=False, name=None)]))
            sample_ids = dict(zip(identities, selected[sample_col]))
            df[sample_col] = identities
        samples_by_value = _samples_by_group_value(df, sample_col, column) if sample_col else {}
        return jsonify({
            "success": True,
            "file_path": file_path,
            "column": column,
            "values": values,
            "sample_column": sample_col,
            "samples_by_value": samples_by_value,
            "sample_labels": sample_labels,
            "sample_ids": sample_ids,
            "count": len(values),
        })
    except ValidationError as exc:
        logger.warning("Validation error in get_boxplot_group_values: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error reading BoxPlot group values: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_GROUP_VALUES_ERROR", "message": str(exc)}), 500


@bp.route("/boxplot/group-values-bulk", methods=["POST"])
def get_boxplot_group_values_bulk():
    try:
        data = request.get_json() or {}
        file_path = str(data.get("file_path") or "").strip()
        columns = data.get("columns") if isinstance(data.get("columns"), list) else []
        if not file_path:
            raise ValidationError(message="file_path is required", details={"field": "file_path"})
        if not columns:
            raise ValidationError(message="columns is required", details={"field": "columns"})

        dp = Path(file_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="File not found", details={"file_path": file_path})
        df = _robust_read_csv(dp, dtype=str)

        result: Dict[str, Any] = {}
        sample_col = _detect_sample_column(df.columns.tolist())
        for column in columns:
            if column not in df.columns:
                result[column] = {"error": f"Column not found: {column}"}
                continue
            raw_values = df[column].dropna().unique().tolist()
            values = sorted({str(v).strip() for v in raw_values if str(v).strip()})
            samples_by_value = _samples_by_group_value(df, sample_col, column) if sample_col else {}
            result[column] = {"values": values, "count": len(values), "sample_column": sample_col, "samples_by_value": samples_by_value}

        return jsonify({
            "success": True,
            "file_path": file_path,
            "groups": result,
        })
    except ValidationError as exc:
        logger.warning("Validation error in get_boxplot_group_values_bulk: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error reading BoxPlot group values bulk: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_GROUP_VALUES_BULK_ERROR", "message": str(exc)}), 500


def _detect_sample_column(columns: List[str]) -> str:
    lower_map = {str(col).strip().lower(): str(col) for col in columns}
    for preferred in ("sample", "sample_id", "sample_name", "id"):
        if preferred in lower_map:
            return lower_map[preferred]
    return ""


def _samples_by_group_value(df, sample_col: str, group_col: str) -> Dict[str, List[str]]:
    if not sample_col or sample_col not in df.columns or group_col not in df.columns:
        return {}
    work_df = df[list(dict.fromkeys([sample_col, group_col]))].dropna(subset=[sample_col, group_col]).copy()
    work_df[sample_col] = work_df[sample_col].astype(str).str.strip()
    work_df[group_col] = work_df[group_col].astype(str).str.strip()
    result: Dict[str, List[str]] = {}
    for group_value, group_df in work_df.groupby(group_col):
        result[str(group_value)] = sorted({
            str(item).strip() for item in group_df[sample_col].tolist() if str(item).strip()
        })
    return result


@bp.route("/boxplot/run", methods=["POST"])
def run_boxplot():
    try:
        data = request.get_json() or {}
        module_name = str(data.get("module") or "boxplot").strip().lower()
        if module_name not in _ALLOWED_MODULES:
            raise ValidationError(message="Unsupported script hub module", details={"module": module_name})

        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""

        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required", details={"field": "datapoint_path"})

        classification_begin = str(data.get("classification_begin") or "").strip()
        classification_over = str(data.get("classification_over") or "").strip()
        grouptype_fields = data.get("grouptype_fields") if isinstance(data.get("grouptype_fields"), list) else None
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()
        group_order = str(data.get("group_order") or "").strip() or None

        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        output_name = str(data.get("output_name") or "").strip() or None
        selected_samples = _selected_samples_from_request(data)
        selected_samples_by_group = _selected_samples_by_group_from_request(data)
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name="boxplot",
            input_paths=[{"asset_type": "profile", "path": datapoint_path}],
            config_json={
                "classification_begin": classification_begin,
                "classification_over": classification_over,
                "grouptype_fields": grouptype_fields or [],
                "param_begin": param_begin,
                "param_over": param_over,
                "group_order": group_order,
                "pvalue_threshold": pvalue_threshold,
                "selected_samples": selected_samples,
                "selected_samples_by_group": selected_samples_by_group,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, "boxplot")
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "datapoint_path": datapoint_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
            **cache_context,
        )

        _script_executor.submit(
            _run_boxplot_task,
            task_id,
            results_root=_resolve_results_root(),
            datapoint_path=datapoint_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            grouptype_fields=grouptype_fields,
            param_begin=param_begin,
            param_over=param_over,
            group_order=group_order,
            pvalue_threshold=pvalue_threshold,
            output_name=output_name,
            selected_samples=selected_samples,
            selected_samples_by_group=selected_samples_by_group,
            module_name="boxplot",
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_boxplot: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing BoxPlot task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500
