"""Profile analysis routes: topclone, profile, pep-analysis, pgen-analysis."""

import json
import uuid
from urllib.parse import quote
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request

from flask_app.exceptions import ValidationError
from flask_app.services.boxplot_service import BoxPlotService
from flask_app.services.pep_analysis_service import PepAnalysisService
from flask_app.services.pgen_analysis_service import PgenAnalysisService
from flask_app.services.topclone_service import TopCloneService
from flask_app.services.profile_composition_service import ProfileCompositionService, discover_composition_columns
from flask_app.services.profile_csr_service import ProfileCsrService, discover_csr_measures
from flask_app.services.igh_subclass_topclone_service import IgSubclassTopCloneService
from flask_app.services.project_storage_paths import script_output_parent
from ._common import (
    _ALLOWED_MODULES,
    _RESULT_DIR,
    _build_script_cache_context,
    _build_topclone_viewer,
    _collect_project_script_hub_assets,
    _collect_project_cached_usage_assets,
    _complete_script_task,
    _force_rerun_requested,
    _get_task_state,
    _history_entry,
    _normalize_chain,
    _normalize_script_result,
    _pep_paths_from_request,
    _pep_tra_candidates_from_output_base,
    _primary_pep_path_from_request,
    _profile_path_from_request,
    _record_stage,
    _request_registered_assets,
    _resolve_results_root,
    _robust_read_csv,
    _sanitize_nan,
    _selected_group_values_from_request,
    _script_executor,
    _selected_samples_by_group_from_request,
    _group_sample_identity_from_request,
    _validate_selected_samples_against_group_values,
    _selected_samples_from_request,
    _set_task_state,
    _suggest_profile_ranges,
    _suggest_umap_ranges,
    _try_reuse_script_result,
    _write_pep_analysis_viewer,
    logger,
)
from .boxplot import _discover_boxplot_inputs, _run_boxplot_task
from .modules_config import _inspect_data_selection_payload

bp = Blueprint("script_hub_profile", __name__)


def _run_topclone_task(
    task_id: str,
    *,
    results_root: Path,
    pep_data_path: str,
    datapoint_path: str,
    pep_paths: Optional[List[str]] = None,
    selected_samples: Optional[List[str]] = None,
    selected_group_values: Optional[Dict[str, List[str]]] = None,
    selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
    group_sample_identity: str = "sample",
    mode: str = "trace",
    top_n: int = 10,
    group_field: Optional[str] = None,
    batch_field: Optional[str] = None,
    group_order: Optional[str] = None,
    pvalue_threshold: float = 0.05,
    selected_chains: Optional[List[str]] = None,
    output_name: Optional[str] = None,
    module_name: str = "topclone",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "检查优势克隆输入", f"正在检查克隆序列表：{pep_data_path}", {"module": module_name})

        local_pep = pep_data_path
        local_dp = datapoint_path
        service = TopCloneService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        report = service.generate_report(
            pep_data_path=local_pep,
            datapoint_path=local_dp,
            pep_paths=pep_paths,
            selected_samples=selected_samples,
            selected_group_values=selected_group_values,
            selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
            mode=mode,
            top_n=top_n,
            group_field=group_field,
            batch_field=batch_field,
            group_order=group_order,
            pvalue_threshold=pvalue_threshold,
            selected_chains=selected_chains,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                float(progress or 0.0),
                stage,
                detail,
                {"module": module_name, **(meta or {})}
            )
        )

        result: Dict[str, Any] = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "topclone_csv_url": "",
            "png_urls": [],
            "pvalue_urls": [],
            "csv_urls": [],
            "cdr3_urls": [],
            "per_sample_count": len(report.per_sample_files),
            "metadata": report.metadata,
        }

        if report.topclone_csv_path:
            rel = Path(report.topclone_csv_path).relative_to(report.output_base)
            result["topclone_csv_url"] = f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        cdr3_root = report.output_base / "top_cdr3_sequences"
        if cdr3_root.exists():
            for cdr3_csv in sorted(cdr3_root.rglob("*.csv")):
                rel = cdr3_csv.relative_to(report.output_base)
                result["cdr3_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        if report.boxplot_report:
            bp = report.boxplot_report
            for png_path in bp.png_paths:
                rel = Path(png_path).relative_to(report.output_base)
                result["png_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            for pv_path in bp.pvalue_paths:
                rel = Path(pv_path).relative_to(report.output_base)
                result["pvalue_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            for csv_path in bp.csv_paths:
                rel = Path(csv_path).relative_to(report.output_base)
                result["csv_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            if bp.viewer_path and bp.viewer_path.exists():
                rel = bp.viewer_path.relative_to(report.output_base)
                result["viewer_url"] = f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        if report.stats_csv_path and Path(report.stats_csv_path).is_file():
            rel = Path(report.stats_csv_path).relative_to(report.output_base)
            result["pvalue_urls"].insert(0, f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
        for effect_path in report.effect_heatmap_paths or []:
            rel = Path(effect_path).relative_to(report.output_base)
            result["png_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
        for statistics_path in report.effect_statistics_paths or []:
            rel = Path(statistics_path).relative_to(report.output_base)
            result["pvalue_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        for file_path in report.per_sample_files:
            rel = Path(file_path).relative_to(report.output_base)
            result["cdr3_urls"].append(f"/api/script-hub/results/{report.job_id}/{quote(rel.as_posix(), safe='/')}")
        summary_csv = report.output_base / "top_clones" / "summary.csv"
        if summary_csv.is_file():
            result["csv_urls"].append(f"/api/script-hub/results/{report.job_id}/top_clones/summary.csv")

        result["zip_url"] = f"/api/script-hub/results/{report.job_id}/topclone_results.zip"
        _build_topclone_viewer(report.output_base, result, report.metadata)
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="优势克隆分析结果",
            subtitle="分析方式：" + ("分组比较" if report.metadata.get("mode") == "trace" else "单样本提取") + "　|　链型：" + ", ".join(report.metadata.get("chains", [])),
            dl_extras=[("topclone_csv_url", "topclone.csv", "优势克隆数据表"),
                       ("csv_urls", None, "分析数据表"),
                       ("pvalue_urls", None, "检验统计表"),
                       ("cdr3_urls", None, "Top CDR3 序列")],
            zip_name="topclone_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=(
                f"优势克隆分析完成：纳入 {report.metadata.get('sample_count', 0)} 个样本，"
                f"生成 {len(result['png_urls'])} 张图表。"
                if mode == "trace"
                else f"优势克隆提取完成：生成 {len(report.per_sample_files)} 个结果文件。"
            ),
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("Script hub TopClone task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=0.0,
            stage="执行失败",
            detail=str(exc),
            meta={"phase": "failed", "module": module_name},
            history=history[-80:]
        )

@bp.route("/topclone/inspect", methods=["POST"])
def inspect_topclone():
    try:
        data = request.get_json() or {}
        pep_paths = _pep_paths_from_request(data)
        pep_data_path = _primary_pep_path_from_request(data, "pep_data_path", "base_path")
        if not pep_data_path:
            raise ValidationError(message="pep_data_path is required", details={"field": "pep_data_path"})
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""

        discovery = _inspect_data_selection_payload(pep_paths or [pep_data_path], datapoint_path or None)
        chains = discovery.get("chains", [])
        samples = discovery.get("samples", [])
        category_cols = discovery.get("group_fields", [])

        return jsonify({
            "success": True,
            "pep_data_path": pep_data_path,
            "chains": chains,
            "chain_count": len(chains),
            "sample_count": len(samples),
            "samples": samples[:20],
            "category_cols": category_cols,
            "sample_conflicts": discovery.get("sample_conflicts", []),
            "warnings": discovery.get("warnings", []),
        })
    except ValidationError as exc:
        logger.warning("Validation error in inspect_topclone: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting TopClone inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@bp.route("/topclone/run", methods=["POST"])
def run_topclone():
    try:
        data = request.get_json() or {}
        module_name = "topclone"

        pep_paths = _pep_paths_from_request(data)
        pep_data_path = _primary_pep_path_from_request(data, "pep_data_path", "base_path")
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        if str(data.get("analysis_type") or "").strip().lower() == "igh_subclass_topclone":
            return _queue_igh_subclass_topclone(data, pep_paths, pep_data_path, datapoint_path)
        mode = str(data.get("mode") or "trace").strip()
        top_n = int(data.get("top_n") or 10)
        group_field = str(data.get("group_field") or "").strip() or None
        batch_field = str(data.get("batch_field") or "").strip() or None
        group_order = str(data.get("group_order") or "").strip() or None
        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        selected_chains = [
            _normalize_chain(str(chain))
            for chain in (data.get("selected_chains") if isinstance(data.get("selected_chains"), list) else [])
            if str(chain or "").strip()
        ]
        output_name = str(data.get("output_name") or "").strip() or None
        selected_samples = _selected_samples_from_request(data)
        selected_group_values = _selected_group_values_from_request(data)
        selected_samples_by_group = _selected_samples_by_group_from_request(data)
        group_sample_identity = _group_sample_identity_from_request(data)
        _validate_selected_samples_against_group_values(data)
        if mode not in {"trace", "per_sample"} or top_n < 1:
            raise ValidationError(message="请选择有效分析模式，提取克隆数量至少为 1。", details={"mode": mode, "top_n": top_n})

        if not pep_data_path:
            raise ValidationError(message="pep_data_path is required", details={"field": "pep_data_path"})
        if (mode == "trace" or batch_field or selected_samples or selected_group_values or selected_samples_by_group) and not datapoint_path:
            raise ValidationError(message="分组或样本筛选需要样本指标表。", details={"field": "datapoint_path"})
        if datapoint_path:
            discovery = _inspect_data_selection_payload(pep_paths or [pep_data_path], datapoint_path)
            conflicts = discovery.get("sample_conflicts", [])
            if conflicts and not batch_field:
                raise ValidationError(
                    message="发现跨批次同名样本，请选择批次字段后再提交 TopClone 分析。",
                    details={"sample_conflicts": conflicts},
                )
            profile_columns = discovery.get("profile_columns", [])
            if batch_field and profile_columns and batch_field not in profile_columns:
                raise ValidationError(
                    message="所选批次字段不在当前样本指标表中。",
                    details={"batch_field": batch_field, "available_fields": profile_columns},
                )
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=(
                [{"asset_type": "pep", "path": path} for path in (pep_paths or [pep_data_path])]
                + ([{"asset_type": "profile", "path": datapoint_path}] if datapoint_path else [])
            ),
            config_json={
                "mode": mode,
                "top_n": top_n,
                "group_field": group_field,
                "batch_field": batch_field,
                "group_order": group_order,
                "pvalue_threshold": pvalue_threshold,
                "selected_chains": selected_chains,
                "selected_samples": selected_samples,
                "selected_group_values": selected_group_values,
                "selected_samples_by_group": selected_samples_by_group,
                "group_sample_identity": group_sample_identity,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "pep_data_path": pep_data_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="等待执行",
            detail="优势克隆分析任务已加入队列。",
            meta=queued_meta,
            history=[_history_entry(0.0, "等待执行", "优势克隆分析任务已加入队列。", queued_meta)],
            **cache_context,
        )

        _script_executor.submit(
            _run_topclone_task,
            task_id,
            results_root=_resolve_results_root(),
            pep_data_path=pep_data_path,
            datapoint_path=datapoint_path,
            pep_paths=pep_paths or None,
            selected_samples=selected_samples,
            selected_group_values=selected_group_values,
            selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
            mode=mode,
            top_n=top_n,
            group_field=group_field,
            batch_field=batch_field,
            group_order=group_order,
            pvalue_threshold=pvalue_threshold,
            selected_chains=selected_chains or None,
            output_name=output_name,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_topclone: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing TopClone task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


def _queue_igh_subclass_topclone(data: Dict[str, Any], pep_paths: List[str], pep_data_path: str, datapoint_path: str):
    if not datapoint_path:
        raise ValidationError(message="亚类 TopClone 需要样本指标表提供分组信息。")
    inputs = pep_paths or ([pep_data_path] if pep_data_path else [])
    if not inputs:
        raise ValidationError(message="请选择含 IGH 克隆序列的 PEP 数据。")
    group_field = str(data.get("group_field") or "").strip()
    if not group_field:
        raise ValidationError(message="请选择一个分组列。")
    batch_field = str(data.get("batch_field") or "").strip() or None
    discovery = _inspect_data_selection_payload(inputs, datapoint_path)
    conflicts = discovery.get("sample_conflicts", [])
    if conflicts and not batch_field:
        raise ValidationError(message="发现跨批次同名样本，请选择批次字段后再提交亚类 TopClone 分析。",
                              details={"sample_conflicts": conflicts})
    profile_columns = discovery.get("profile_columns", [])
    if batch_field and profile_columns and batch_field not in profile_columns:
        raise ValidationError(message="所选批次字段不在当前样本指标表中。",
                              details={"batch_field": batch_field, "available_fields": profile_columns})
    group_order_value = data.get("group_order")
    if isinstance(group_order_value, list):
        group_order = [str(item).strip() for item in group_order_value if str(item).strip()]
    else:
        group_order = [item.strip() for item in str(group_order_value or "").split(",") if item.strip()]
    selected_samples = _selected_samples_from_request(data)
    project_id = str(data.get("project_id") or "").strip() or None
    cache_context = _build_script_cache_context(
        project_id=project_id,
        module_name="igh-subclass-topclone",
        input_paths=[{"asset_type": "pep", "path": path} for path in inputs]
            + [{"asset_type": "profile", "path": datapoint_path}],
        config_json={
            "analysis_type": "igh_subclass_topclone", "group_field": group_field,
            "group_order": group_order, "selected_samples": selected_samples,
            "batch_field": batch_field,
        },
    )
    if not _force_rerun_requested(data):
        reused = _try_reuse_script_result(cache_context, "igh-subclass-topclone")
        if reused:
            return jsonify(reused)
    task_id = f"script_task_{uuid.uuid4().hex[:12]}"
    queued_meta = {"phase": "queued", "module": "igh-subclass-topclone", "datapoint_path": datapoint_path}
    _set_task_state(
        task_id, status="queued", progress=0.0, stage="Queued",
        detail="IGH 亚类 TopClone 已加入队列。", meta=queued_meta,
        history=[_history_entry(0.0, "Queued", "IGH 亚类 TopClone 已加入队列。", queued_meta)],
        **cache_context,
    )
    _script_executor.submit(
        _run_igh_subclass_topclone_task, task_id,
        results_root=_resolve_results_root(), pep_paths=inputs,
        datapoint_path=datapoint_path, group_field=group_field,
        group_order=group_order, batch_field=batch_field, selected_samples=selected_samples,
        app_context_app=current_app._get_current_object() if project_id else None,
    )
    return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})


def _run_igh_subclass_topclone_task(
    task_id: str, *, results_root: Path, pep_paths: List[str], datapoint_path: str,
    group_field: str, group_order: List[str], batch_field: Optional[str] = None,
    selected_samples: Optional[List[str]] = None,
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 8, "检查 IGH 克隆数据", "根据样本指标表匹配 IGH 文件及分组。", {"module": "igh-subclass-topclone"})
        service = IgSubclassTopCloneService(
            output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app)
        )
        report = service.generate_report(
            pep_paths=pep_paths, datapoint_path=datapoint_path,
            group_column=group_field, group_order=group_order,
            batch_field=batch_field,
            selected_samples=selected_samples, output_name=task_id,
        )
        base_url = f"/api/script-hub/results/{report.job_id}"
        png_urls = [f"{base_url}/{path.relative_to(report.output_base).as_posix()}" for path in report.png_paths]
        csv_urls = [f"{base_url}/{path.relative_to(report.output_base).as_posix()}" for path in report.csv_paths]
        result = {
            "module": "igh-subclass-topclone", "job_id": report.job_id,
            "output_base": str(report.output_base), "png_urls": png_urls,
            "csv_urls": csv_urls,
            "zip_url": f"{base_url}/{report.zip_path.relative_to(report.output_base).as_posix()}",
            "metadata_url": f"{base_url}/analysis_metadata.json", "metadata": report.metadata,
        }
        _normalize_script_result(
            result, report.output_base, report.metadata,
            title="IGH 免疫球蛋白亚类 TopClone",
            subtitle=f"分组：{group_field}；样本数：{report.metadata['sample_count']}",
            dl_extras=[("csv_urls", None, "亚类 TopClone 统计表")],
            zip_name="IGH_亚类TopClone分析结果.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id, module_name="igh-subclass-topclone",
            detail=f"已生成 {len(report.png_paths)} 张组间差异图和 {len(report.csv_paths)} 份数据表。",
            result=result, history=history, app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("IGH subclass TopClone task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=100.0, stage="Failed", detail=str(exc), error=str(exc),
                        meta={"phase": "failed", "module": "igh-subclass-topclone"}, history=history[-80:])


@bp.route("/profile/inspect", methods=["POST"])
def inspect_profile():
    try:
        data = request.get_json() or {}
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path")
        base_path = str(data.get("base_path") or "").strip()

        discovery = _discover_boxplot_inputs(base_path, datapoint_path)
        suggestions = _suggest_profile_ranges(discovery["columns"])
        discovery.update(suggestions)
        discovery["composition_columns"] = {
            "reads": discover_composition_columns(discovery["columns"], "reads"),
            "clone": discover_composition_columns(discovery["columns"], "clone"),
        }
        discovery["csr_measures"] = discover_csr_measures(discovery["columns"])

        # Read sample rows for preview
        dp = Path(discovery["datapoint_path"])
        preview_rows = []
        try:
            df_preview = _robust_read_csv(dp, nrows=5)
            preview_rows = _sanitize_nan(df_preview.values.tolist())
        except Exception:
            pass
        discovery["preview_rows"] = preview_rows

        return jsonify(_sanitize_nan({"success": True, **discovery}))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_profile: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Profile inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@bp.route("/profile/columns", methods=["POST"])
def get_profile_columns():
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
        suggestions = _suggest_profile_ranges(columns)
        return jsonify({
            "success": True,
            "file_path": file_path,
            "columns": columns,
            "column_count": len(columns),
            **suggestions,
        })
    except ValidationError as exc:
        logger.warning("Validation error in get_profile_columns: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error reading Profile columns: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_COLUMNS_ERROR", "message": str(exc)}), 500


@bp.route("/profile/run", methods=["POST"])
def run_profile():
    try:
        data = request.get_json() or {}
        module_name = "profile"
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""

        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required", details={"field": "datapoint_path"})

        if str(data.get("analysis_type") or "").strip().lower() == "composition":
            return _queue_profile_composition(data, datapoint_path)
        if str(data.get("analysis_type") or "").strip().lower() == "csr":
            return _queue_profile_csr(data, datapoint_path)

        grouping_begin = str(data.get("grouping_begin") or "").strip()
        grouping_over = str(data.get("grouping_over") or "").strip()
        grouptype_fields = data.get("grouptype_fields") if isinstance(data.get("grouptype_fields"), list) else None
        group_order = str(data.get("group_order") or "").strip() or None
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()

        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        output_name = str(data.get("output_name") or "").strip() or None
        selected_samples = _selected_samples_from_request(data)
        selected_group_values = _selected_group_values_from_request(data)
        selected_samples_by_group = _selected_samples_by_group_from_request(data)
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "profile", "path": datapoint_path}],
            config_json={
                "grouping_begin": grouping_begin,
                "grouping_over": grouping_over,
                "grouptype_fields": grouptype_fields or [],
                "group_order": group_order,
                "param_begin": param_begin,
                "param_over": param_over,
                "pvalue_threshold": pvalue_threshold,
                "selected_samples": selected_samples,
                "selected_samples_by_group": selected_samples_by_group,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
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
            classification_begin=grouping_begin,
            classification_over=grouping_over,
            grouptype_fields=grouptype_fields,
            group_order=group_order,
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            output_name=output_name,
            selected_samples=selected_samples,
            selected_samples_by_group=selected_samples_by_group,
            module_name="profile",
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_profile: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing Profile task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


def _queue_profile_composition(data: Dict[str, Any], datapoint_path: str):
    group_column = str(data.get("group_column") or data.get("grouping_begin") or "").strip()
    if not group_column:
        raise ValidationError(message="请选择一个分组列。")
    measure = str(data.get("subclass_measure") or "reads").strip().lower()
    if measure not in {"reads", "clone"}:
        raise ValidationError(message="亚类统计口径请选择读段或克隆数。")
    if not Path(datapoint_path).is_file():
        raise ValidationError(message="样本指标表不存在。")
    columns = _robust_read_csv(datapoint_path, nrows=0).columns.tolist()
    if group_column not in columns:
        raise ValidationError(message="所选分组列不在样本指标表中。")
    composition_columns = discover_composition_columns(columns, measure)
    if not composition_columns["chains"] and not composition_columns["subclass_columns"]:
        raise ValidationError(message=f"样本指标表中没有可用的链构成列或 {measure} 亚类构成列。")

    project_id = str(data.get("project_id") or "").strip() or None
    selected_samples = _selected_samples_from_request(data)
    selected_samples_by_group = _selected_samples_by_group_from_request(data)
    group_order_value = data.get("group_order")
    if isinstance(group_order_value, list):
        group_order = [str(item).strip() for item in group_order_value if str(item).strip()]
    else:
        group_order = [item.strip() for item in str(group_order_value or "").split(",") if item.strip()]
    output_name = str(data.get("output_name") or "").strip() or None
    cache_context = _build_script_cache_context(
        project_id=project_id,
        module_name="profile-composition",
        input_paths=[{"asset_type": "profile", "path": datapoint_path}],
        config_json={
            "group_column": group_column,
            "group_order": group_order,
            "subclass_measure": measure,
            "selected_samples": selected_samples,
            "selected_samples_by_group": selected_samples_by_group,
        },
    )
    if not _force_rerun_requested(data):
        reused_response = _try_reuse_script_result(cache_context, "profile-composition")
        if reused_response:
            return jsonify(reused_response)

    task_id = f"script_task_{uuid.uuid4().hex[:12]}"
    queued_meta = {"phase": "queued", "module": "profile-composition", "datapoint_path": datapoint_path}
    _set_task_state(
        task_id,
        status="queued",
        progress=0.0,
        stage="Queued",
        detail="构成图任务已加入队列。",
        meta=queued_meta,
        history=[_history_entry(0.0, "Queued", "构成图任务已加入队列。", queued_meta)],
        **cache_context,
    )
    _script_executor.submit(
        _run_profile_composition_task,
        task_id,
        results_root=_resolve_results_root(),
        datapoint_path=datapoint_path,
        group_column=group_column,
        group_order=group_order,
        measure=measure,
        selected_samples=selected_samples,
        selected_samples_by_group=selected_samples_by_group,
        app_context_app=current_app._get_current_object() if project_id else None,
    )
    return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})


def _run_profile_composition_task(
    task_id: str,
    *,
    results_root: Path,
    datapoint_path: str,
    group_column: str,
    group_order: List[str],
    measure: str,
    selected_samples: Optional[List[str]] = None,
    selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 8, "读取样本指标", "核对分组、构成列和样本筛选范围。", {"module": "profile-composition"})
        service = ProfileCompositionService(
            output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app)
        )
        report = service.generate_report(
            datapoint_path=datapoint_path,
            group_column=group_column,
            group_order=group_order,
            measure=measure,
            selected_samples=selected_samples,
            selected_samples_by_group=selected_samples_by_group,
            output_name=task_id,
        )
        base_url = f"/api/script-hub/results/{report.job_id}"
        png_urls = [f"{base_url}/{path.relative_to(report.output_base).as_posix()}" for path in report.png_paths]
        csv_urls = [f"{base_url}/{path.relative_to(report.output_base).as_posix()}" for path in report.csv_paths]
        result = {
            "module": "profile-composition",
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "csv_urls": csv_urls,
            "zip_url": f"{base_url}/{report.zip_path.relative_to(report.output_base).as_posix()}",
            "metadata_url": f"{base_url}/analysis_metadata.json",
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="组库链与免疫球蛋白亚类构成",
            subtitle=f"分组：{group_column}；样本数：{report.metadata['sample_count']}",
            dl_extras=[("csv_urls", None, "样本构成与质量表")],
            zip_name="组库构成分析结果.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name="profile-composition",
            detail=f"已生成 {len(report.png_paths)} 张构成图和 {len(report.csv_paths)} 份数据表。",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("Profile composition task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="Failed",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "profile-composition"},
            history=history[-80:],
        )


def _queue_profile_csr(data: Dict[str, Any], datapoint_path: str):
    group_column = str(data.get("group_column") or data.get("grouping_begin") or "").strip()
    if not group_column:
        raise ValidationError(message="请选择一个分组列。")
    if not Path(datapoint_path).is_file():
        raise ValidationError(message="样本指标表不存在。")
    columns = _robust_read_csv(datapoint_path, nrows=0).columns.tolist()
    if group_column not in columns:
        raise ValidationError(message="所选分组列不在样本指标表中。")
    available = discover_csr_measures(columns)
    measure = str(data.get("csr_measure") or "auto").strip()
    normalized = measure.upper()
    if normalized == "AUTO":
        usable = bool(available)
    else:
        key = "CSR_ratio" if normalized == "CSR_RATIO" else normalized
        usable = bool(available.get(key))
    if not usable:
        raise ValidationError(message="样本指标表中没有所选 CSR 指标列，请重新检查输入或切换统计口径。")

    project_id = str(data.get("project_id") or "").strip() or None
    selected_samples = _selected_samples_from_request(data)
    group_order_value = data.get("group_order")
    if isinstance(group_order_value, list):
        group_order = [str(item).strip() for item in group_order_value if str(item).strip()]
    else:
        group_order = [item.strip() for item in str(group_order_value or "").split(",") if item.strip()]
    cache_context = _build_script_cache_context(
        project_id=project_id,
        module_name="profile-csr",
        input_paths=[{"asset_type": "profile", "path": datapoint_path}],
        config_json={
            "group_column": group_column,
            "group_order": group_order,
            "csr_measure": normalized,
            "selected_samples": selected_samples,
        },
    )
    if not _force_rerun_requested(data):
        reused_response = _try_reuse_script_result(cache_context, "profile-csr")
        if reused_response:
            return jsonify(reused_response)

    task_id = f"script_task_{uuid.uuid4().hex[:12]}"
    queued_meta = {"phase": "queued", "module": "profile-csr", "datapoint_path": datapoint_path}
    _set_task_state(
        task_id,
        status="queued",
        progress=0.0,
        stage="Queued",
        detail="CSR 类别转换分析已加入队列。",
        meta=queued_meta,
        history=[_history_entry(0.0, "Queued", "CSR 类别转换分析已加入队列。", queued_meta)],
        **cache_context,
    )
    _script_executor.submit(
        _run_profile_csr_task,
        task_id,
        results_root=_resolve_results_root(),
        datapoint_path=datapoint_path,
        group_column=group_column,
        group_order=group_order,
        measure=measure,
        selected_samples=selected_samples,
        app_context_app=current_app._get_current_object() if project_id else None,
    )
    return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})


def _run_profile_csr_task(
    task_id: str,
    *,
    results_root: Path,
    datapoint_path: str,
    group_column: str,
    group_order: List[str],
    measure: str,
    selected_samples: Optional[List[str]] = None,
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 8, "读取样本指标", "核对 CSR 指标、分组和样本范围。", {"module": "profile-csr"})
        service = ProfileCsrService(
            output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app)
        )
        report = service.generate_report(
            datapoint_path=datapoint_path,
            group_column=group_column,
            group_order=group_order,
            measure=measure,
            selected_samples=selected_samples,
            output_name=task_id,
        )
        base_url = f"/api/script-hub/results/{report.job_id}"
        png_urls = [f"{base_url}/{path.relative_to(report.output_base).as_posix()}" for path in report.png_paths]
        csv_urls = [f"{base_url}/{path.relative_to(report.output_base).as_posix()}" for path in report.csv_paths]
        result = {
            "module": "profile-csr", "job_id": report.job_id,
            "output_base": str(report.output_base), "png_urls": png_urls,
            "csv_urls": csv_urls,
            "zip_url": f"{base_url}/{report.zip_path.relative_to(report.output_base).as_posix()}",
            "metadata_url": f"{base_url}/analysis_metadata.json", "metadata": report.metadata,
        }
        _normalize_script_result(
            result, report.output_base, report.metadata,
            title="免疫球蛋白类别转换矩阵",
            subtitle=f"分组：{group_column}；样本数：{report.metadata['sample_count']}",
            dl_extras=[("csv_urls", None, "CSR 统计表")],
            zip_name="免疫球蛋白类别转换分析结果.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id, module_name="profile-csr",
            detail=f"已生成 {len(report.png_paths)} 张矩阵图和 {len(report.csv_paths)} 份统计表。",
            result=result, history=history, app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("Profile CSR task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id, status="failed", progress=100.0, stage="Failed", detail=str(exc), error=str(exc),
            meta={"phase": "failed", "module": "profile-csr"}, history=history[-80:],
        )


# ---- Pep Analysis inspect ----
@bp.route("/pep-analysis/inspect", methods=["POST"])
def inspect_pep_analysis():
    try:
        data = request.get_json() or {}
        pep_paths = _pep_paths_from_request(data)
        base_path = _primary_pep_path_from_request(data, "base_path", "pep_data_dir", "pep_data_path")
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path")

        discovery = _inspect_data_selection_payload(pep_paths, profile_path)

        if not discovery["chains"]:
            raise ValidationError(
                message="No pep files detected. Expected format: {Sample}__{Chain}.csv",
                details={"base_path": base_path, "pep_paths": pep_paths, "warnings": discovery.get("warnings", [])}
            )

        return jsonify({
            "success": True,
            "base_path": base_path or (pep_paths[0] if pep_paths else ""),
            "profile_path": discovery["profile_path"],
            "chains": discovery["chains"],
            "chain_count": discovery["chain_count"],
            "sample_count": discovery["sample_count"],
            "pep_file_count": discovery["pep_file_count"],
            "profile_candidates": discovery["profile_candidates"][:10],
            "profile_columns": discovery["profile_columns"],
            "group_fields": discovery["group_fields"],
            "warnings": discovery["warnings"],
        })
    except ValidationError as exc:
        logger.warning("Validation error in inspect_pep_analysis: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Pep analysis inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


# ---- Pep Analysis run ----
@bp.route("/pep-analysis/run", methods=["POST"])
def run_pep_analysis():
    try:
        data = request.get_json() or {}
        module_name = "pep-analysis"

        pep_paths = _pep_paths_from_request(data)
        pep_data_dir = _primary_pep_path_from_request(data, "pep_data_dir", "base_path", "pep_data_path")
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path") or ""
        selected_chains = data.get("selected_chains") if isinstance(data.get("selected_chains"), list) else []
        group_fields = data.get("group_fields") if isinstance(data.get("group_fields"), list) else []
        batch_field = str(data.get("batch_field") or "").strip() or None
        selected_samples = _selected_samples_from_request(data)
        selected_group_values = _selected_group_values_from_request(data)
        selected_samples_by_group = _selected_samples_by_group_from_request(data)
        group_sample_identity = _group_sample_identity_from_request(data)

        if not pep_data_dir:
            raise ValidationError(message="pep_data_dir is required", details={"field": "pep_data_dir"})
        if not profile_path:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})
        if not selected_chains:
            raise ValidationError(message="selected_chains is required", details={"field": "selected_chains"})
        if not group_fields:
            raise ValidationError(message="group_fields is required", details={"field": "group_fields"})

        pep_inputs = pep_paths or [pep_data_dir]
        discovery = _inspect_data_selection_payload(pep_inputs, profile_path)
        if batch_field:
            profile_columns = discovery.get("profile_columns", [])
            if batch_field not in profile_columns:
                raise ValidationError(
                    message=f"样本指标表中不存在批次字段“{batch_field}”",
                    details={"field": "batch_field", "available_fields": profile_columns},
                )
            sample_column = profile_columns[0] if profile_columns else ""
            if batch_field == sample_column:
                raise ValidationError(message="批次字段不能与样本编号列相同", details={"field": "batch_field"})
            batch_rows = _robust_read_csv(profile_path, usecols=[sample_column, batch_field], dtype=str)
            if batch_rows[batch_field].isna().any() or batch_rows[batch_field].astype(str).str.strip().eq("").any():
                raise ValidationError(message="样本指标表中存在空批次值", details={"field": "batch_field"})
            if batch_rows.duplicated([sample_column, batch_field]).any():
                raise ValidationError(message="样本指标表中存在重复的批次与样本编号组合", details={"field": "batch_field"})
        if discovery.get("sample_conflicts") and not batch_field:
            raise ValidationError(
                message="所选 PEP 文件中存在同名样本与链型；当前共享克隆流程无法区分批次，请先整理样本编号。",
                details={"sample_conflicts": discovery["sample_conflicts"]},
            )

        _validate_selected_samples_against_group_values(data)

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        min_sample_threshold = int(data.get("min_sample_threshold") or 3)
        optional_steps_raw = data.get("optional_steps") if isinstance(data.get("optional_steps"), list) else None
        optional_steps = {int(step) for step in optional_steps_raw if str(step).isdigit()} if optional_steps_raw is not None else None
        optional_steps = {step for step in optional_steps if step in {5, 6, 7, 8, 9, 10, 11, 12}} if optional_steps is not None else None
        group_order_raw = data.get("group_order")
        try:
            group_order_value = json.loads(group_order_raw) if isinstance(group_order_raw, str) else group_order_raw
        except (TypeError, ValueError):
            group_order_value = {}
        group_order = {
            str(field): [value.strip() for value in str(order).split(",") if value.strip()]
            for field, order in (group_order_value.items() if isinstance(group_order_value, dict) else [])
        }
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None
        app_context_app = current_app._get_current_object() if project_id else None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=(
                [{"asset_type": "pep", "path": path} for path in (pep_paths or [pep_data_dir])]
                + [{"asset_type": "profile", "path": profile_path}]
            ),
            config_json={
                "selected_chains": selected_chains,
                "group_fields": group_fields,
                "batch_field": batch_field,
                "group_order": str(data.get("group_order") or "").strip() or None,
                "selected_samples": selected_samples,
                "selected_group_values": selected_group_values,
                "selected_samples_by_group": selected_samples_by_group,
                "group_sample_identity": group_sample_identity,
                "pvalue_threshold": pvalue_threshold,
                "min_sample_threshold": min_sample_threshold,
                "optional_steps": sorted(optional_steps) if optional_steps is not None else None,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "pep_data_dir": pep_data_dir}
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
            _run_pep_analysis_task,
            task_id,
            results_root=_resolve_results_root(),
            pep_data_dir=pep_data_dir,
            pep_paths=pep_paths or None,
            profile_path=profile_path,
            group_fields=group_fields,
            selected_chains=selected_chains,
            batch_field=batch_field,
            pvalue_threshold=pvalue_threshold,
            min_sample_threshold=min_sample_threshold,
            optional_steps=optional_steps,
            output_name=output_name,
            selected_samples=selected_samples,
            selected_group_values=selected_group_values,
            selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
            group_order=group_order,
            project_id=project_id,
            app_context_app=app_context_app
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_pep_analysis: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing Pep analysis task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- Pgen Analysis inspect ----
@bp.route("/pgen-analysis/inspect", methods=["POST"])
def inspect_pgen_analysis():
    try:
        data = request.get_json() or {}
        pep_paths = _pep_paths_from_request(data)
        base_path = _primary_pep_path_from_request(data, "base_path", "pep_data_dir", "pep_data_path")
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path")
        discovery = _inspect_data_selection_payload(pep_paths, profile_path)
        sonnia_status = PgenAnalysisService.dependency_status()
        runnable_chains = [chain for chain in discovery["chains"] if chain not in {"TRD", "TRG"}]

        if not discovery["chains"]:
            raise ValidationError(
                message="No pep files detected. Expected format: {Sample}__{Chain}.csv",
                details={"base_path": base_path, "pep_paths": pep_paths, "warnings": discovery.get("warnings", [])},
            )
        if not discovery["profile_path"]:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})

        return jsonify(_sanitize_nan({
            "success": True,
            "base_path": base_path or (pep_paths[0] if pep_paths else ""),
            "profile_path": discovery["profile_path"],
            "chains": discovery["chains"],
            "runnable_chains": runnable_chains,
            "skipped_chains": [chain for chain in discovery["chains"] if chain in {"TRD", "TRG"}],
            "chain_count": len(discovery["chains"]),
            "sample_count": discovery["sample_count"],
            "pep_file_count": discovery["pep_file_count"],
            "profile_candidates": discovery["profile_candidates"][:10],
            "profile_columns": discovery["profile_columns"],
            "sample_conflicts": discovery.get("sample_conflicts", []),
            "sample_column_candidates": [c for c in discovery["profile_columns"] if str(c).strip().lower() == "sample"]
                or discovery["profile_columns"][:1],
            "distribution_category_candidates": [
                c for c in discovery["profile_columns"]
                if str(c).strip().lower() != "sample"
            ],
            "sonnia": sonnia_status,
            "warnings": discovery["warnings"],
        }))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_pgen_analysis: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Pgen analysis inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@bp.route("/pgen-analysis/run", methods=["POST"])
def run_pgen_analysis():
    try:
        data = request.get_json() or {}
        module_name = "pgen-analysis"

        pep_paths = _pep_paths_from_request(data)
        pep_data_dir = _primary_pep_path_from_request(data, "pep_data_dir", "base_path", "pep_data_path")
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path") or ""
        selected_chains = data.get("selected_chains") if isinstance(data.get("selected_chains"), list) else []
        species = str(data.get("species") or "human").strip().lower() or "human"
        sample_col = str(data.get("sample_col") or "sample").strip() or "sample"
        distribution_category_col = str(data.get("distribution_category_col") or "").strip() or None
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None

        if not pep_data_dir:
            raise ValidationError(message="pep_data_dir is required", details={"field": "pep_data_dir"})
        if not profile_path:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})
        if not selected_chains:
            raise ValidationError(message="selected_chains is required", details={"field": "selected_chains"})

        batch_field = str(data.get("batch_field") or "").strip() or None
        selected_samples = _selected_samples_from_request(data)
        selected_group_values = _selected_group_values_from_request(data)
        selected_samples_by_group = _selected_samples_by_group_from_request(data)
        group_sample_identity = _group_sample_identity_from_request(data)
        _validate_selected_samples_against_group_values(data)
        pgen_inputs = pep_paths or [pep_data_dir]
        discovery = _inspect_data_selection_payload(pgen_inputs, profile_path)
        if discovery.get("sample_conflicts") and not batch_field:
            raise ValidationError(
                message="发现跨批次同名样本，请选择批次字段后再提交生成概率分析。",
                details={"sample_conflicts": discovery["sample_conflicts"]},
            )
        profile_columns = discovery.get("profile_columns", [])
        if batch_field and profile_columns and batch_field not in profile_columns:
            raise ValidationError(
                message="所选批次字段不在当前样本指标表中。",
                details={"batch_field": batch_field, "available_fields": profile_columns},
            )

        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=(
                [{"asset_type": "pep", "path": path} for path in (pep_paths or [pep_data_dir])]
                + [{"asset_type": "profile", "path": profile_path}]
            ),
            config_json={
                "selected_chains": selected_chains,
                "species": species,
                "sample_col": sample_col,
                "batch_field": batch_field,
                "distribution_category_col": distribution_category_col or "",
                "selected_samples": selected_samples,
                "selected_group_values": selected_group_values,
                "selected_samples_by_group": selected_samples_by_group,
                "group_sample_identity": group_sample_identity,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "pep_data_dir": pep_data_dir}
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
            _run_pgen_analysis_task,
            task_id,
            results_root=_resolve_results_root(),
            pep_data_dir=pep_data_dir,
            pep_paths=pep_paths or None,
            profile_path=profile_path,
            selected_chains=selected_chains,
            species=species,
            sample_col=sample_col,
            batch_field=batch_field,
            selected_samples=selected_samples,
            selected_group_values=selected_group_values,
            selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
            distribution_category_col=distribution_category_col,
            output_name=output_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_pgen_analysis: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing Pgen analysis task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


def _run_pgen_analysis_task(
    task_id: str,
    *,
    results_root: Path,
    pep_data_dir: str,
    pep_paths: Optional[List[str]] = None,
    profile_path: str,
    selected_chains: List[str],
    species: str = "human",
    sample_col: str = "sample",
    batch_field: Optional[str] = None,
    selected_samples: Optional[List[str]] = None,
    selected_group_values: Optional[Dict[str, List[str]]] = None,
    selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
    group_sample_identity: str = "sample",
    distribution_category_col: Optional[str] = None,
    output_name: Optional[str] = None,
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        module_name = "pgen-analysis"
        _record_stage(task_id, 5, "Pgen analysis", f"Preparing {pep_data_dir}", {"module": module_name})
        service = PgenAnalysisService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        report = service.generate_report(
            pep_data_dir=pep_data_dir,
            pep_paths=pep_paths,
            profile_path=profile_path,
            selected_chains=selected_chains,
            species=species,
            sample_col=sample_col,
            batch_field=batch_field,
            selected_samples=selected_samples,
            selected_group_values=selected_group_values,
            selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
            distribution_category_col=distribution_category_col,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                float(progress or 0.0),
                stage,
                detail,
                {"module": module_name, **(meta or {})},
            ),
        )

        def _url(path_str: str) -> str:
            path = Path(path_str)
            return f"/api/script-hub/results/{report.job_id}/{path.relative_to(report.output_base).as_posix()}"

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "detail_urls": [_url(p) for p in report.detail_paths],
            "csv_urls": [_url(p) for p in report.csv_paths],
            "png_urls": [_url(p) for p in report.png_paths],
            "zip_url": _url(report.zip_path),
            "metadata_url": f"/api/script-hub/results/{report.job_id}/pgen_analysis_metadata.json",
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="Pgen Analysis Results",
            subtitle="Chains: " + ", ".join(report.metadata.get("selected_chains") or selected_chains),
            dl_extras=[
                ("csv_urls", None, "Pgen Summary CSV"),
                ("detail_urls", None, "Per-sample Pgen Detail CSV"),
            ],
            zip_name="pgen_analysis_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"Pgen analysis completed: {len(report.detail_paths)} detail tables, {len(report.png_paths)} figures",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("Script hub Pgen analysis task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="Failed",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "pgen-analysis"},
            history=history[-80:],
        )


def _cache_pep_usage_assets(
    project_id: str,
    job_id: str,
    output_base: str,
    selected_chains: List[str],
    group_fields: List[str],
    pep_data_dir: str,
    profile_path: str,
    projects_root: Path,
    analysis_signature: str = "",
    result_id: str = "",
) -> None:
    """Register Pep analysis usage directory as a cached_usage project asset."""
    try:
        from flask_app.models.database import Project
        from flask_app.services.project_asset_service import get_project_asset_service
        from pathlib import Path as _Path

        projects_root = _Path(projects_root)
        if not projects_root.exists():
            logger.warning("Projects root does not exist, skipping usage caching")
            return

        asset_service = get_project_asset_service(projects_root)
        project = Project.query.filter(Project.id == project_id).first()
        if project is None:
            logger.warning("Project %s not found, skipping usage caching", project_id)
            return

        output_dir = _Path(output_base)
        usage_dir = output_dir / "usage"
        mongo_save_cached_usage = None
        try:
            from flask_app.services.mongo_service import save_cached_usage
            mongo_save_cached_usage = save_cached_usage
        except Exception:
            logger.warning("Mongo cached usage service unavailable; SQL ProjectAsset cache will be used", exc_info=True)

        usage_types = {}
        for sub in ["1Vusage", "1Jusage", "1VJusage", "0Vusage", "0Jusage", "0VJusage"]:
            sub_path = usage_dir / sub
            if sub_path.exists() and sub_path.is_dir():
                usage_types[sub] = str(sub_path)

        if not usage_types:
            logger.info("No usage subdirectories found in %s", usage_dir)
            return

        def _usage_metadata(*, scope: str, storage_path: _Path, group_field: str = "") -> Dict[str, Any]:
            usage_type_dirs = {}
            for sub in ["1Vusage", "1Jusage", "1VJusage", "0Vusage", "0Jusage", "0VJusage"]:
                sub_path = storage_path / sub
                if sub_path.exists() and sub_path.is_dir():
                    usage_type_dirs[sub] = str(sub_path)
            return {
                "source_job_id": job_id,
                "source_result_signature": analysis_signature,
                "source_result_id": result_id,
                "source_module": "pep-analysis",
                "usage_scope": scope,
                "group_field": group_field,
                "chains": selected_chains,
                "group_fields": group_fields,
                "usage_types": usage_type_dirs,
                "pep_data_dir": pep_data_dir,
                "profile_path": profile_path,
                "pep_output_base": str(output_dir),
                "pep_shared_dir": str(output_dir / "Pep_shared"),
                "pep_shared_TRA_path": str(output_dir / "Pep_shared" / "TRA.csv") if (output_dir / "Pep_shared" / "TRA.csv").exists() else "",
                "pep_shared_cate_dir": str(output_dir / group_field / "Pep_shared_cate" / "Pep_shared") if group_field else "",
                "pep_shared_cate_TRA_path": str(output_dir / group_field / "Pep_shared_cate" / "Pep_shared" / "TRA.csv") if group_field and (output_dir / group_field / "Pep_shared_cate" / "Pep_shared" / "TRA.csv").exists() else "",
                "volcano_data_dir": str(storage_path / "1VJusage") if (storage_path / "1VJusage").exists() else str(storage_path),
                "usage_1vj_path": str(storage_path / "1VJusage") if (storage_path / "1VJusage").exists() else "",
                "umapin_data_path": str(output_dir / "usage" / "df_1VJusage_all.csv") if scope == "usage" and (output_dir / "usage" / "df_1VJusage_all.csv").exists() else "",
                "df_vj_all_path": str(output_dir / "usage" / "df_VJ_all.csv") if scope == "usage" and (output_dir / "usage" / "df_VJ_all.csv").exists() else "",
                "df_1vj_all_path": str(output_dir / "usage" / "df_1VJusage_all.csv") if scope == "usage" and (output_dir / "usage" / "df_1VJusage_all.csv").exists() else "",
            }

        metadata = _usage_metadata(scope="usage", storage_path=usage_dir)
        metadata.update({
            "source_job_id": job_id,
            "source_result_signature": analysis_signature,
            "source_result_id": result_id,
            "source_module": "pep-analysis",
            "usage_scope": "usage",
            "chains": selected_chains,
            "group_fields": group_fields,
            "usage_types": usage_types,
            "pep_data_dir": pep_data_dir,
            "profile_path": profile_path,
            "pep_output_base": str(output_dir),
            "pep_shared_dir": str(output_dir / "Pep_shared"),
            "pep_shared_TRA_path": str(output_dir / "Pep_shared" / "TRA.csv") if (output_dir / "Pep_shared" / "TRA.csv").exists() else "",
            "df_vj_all_path": str(output_dir / "usage" / "df_VJ_all.csv") if (output_dir / "usage" / "df_VJ_all.csv").exists() else "",
            "df_1vj_all_path": str(output_dir / "usage" / "df_1VJusage_all.csv") if (output_dir / "usage" / "df_1VJusage_all.csv").exists() else "",
            "umapin_data_path": str(output_dir / "usage" / "df_1VJusage_all.csv") if (output_dir / "usage" / "df_1VJusage_all.csv").exists() else "",
        })

        asset = asset_service.register_cached_asset(
            project=project,
            asset_type="cached_usage",
            storage_path=str(usage_dir),
            metadata=metadata,
            original_name=f"pep_usage_{job_id}"
        )
        if mongo_save_cached_usage is not None:
            mongo_save_cached_usage(
                project_id=project_id,
                source_job_id=job_id,
                chains=selected_chains,
                group_fields=group_fields,
                usage_types=metadata.get("usage_types") or {},
                pep_data_dir=pep_data_dir,
                    profile_path=profile_path,
                    storage_path=str(usage_dir),
                    original_name=f"pep_usage_{job_id}",
                    metadata_json={**metadata, "storage_path": str(usage_dir)},
                )
        logger.info("Cached pep usage asset %s for project %s", asset.id, project_id)

        for group_field in group_fields:
            usage_cate_dir = output_dir / group_field / "usage_cate" / "usage"
            if not usage_cate_dir.exists() or not usage_cate_dir.is_dir():
                continue
            cate_metadata = _usage_metadata(
                scope="usage_cate",
                storage_path=usage_cate_dir,
                group_field=group_field,
            )
            cate_asset = asset_service.register_cached_asset(
                project=project,
                asset_type="cached_usage",
                storage_path=str(usage_cate_dir),
                metadata=cate_metadata,
                original_name=f"pep_usage_cate_{group_field}_{job_id}"
            )
            if mongo_save_cached_usage is not None:
                mongo_save_cached_usage(
                    project_id=project_id,
                    source_job_id=job_id,
                    chains=selected_chains,
                    group_fields=group_fields,
                    usage_types=cate_metadata.get("usage_types") or {},
                    pep_data_dir=pep_data_dir,
                    profile_path=profile_path,
                    storage_path=str(usage_cate_dir),
                    original_name=f"pep_usage_cate_{group_field}_{job_id}",
                    metadata_json={**cate_metadata, "storage_path": str(usage_cate_dir)},
                )
            logger.info("Cached pep usage_cate asset %s for project %s field %s", cate_asset.id, project_id, group_field)
    except Exception as exc:
        logger.warning("Failed to cache pep usage assets for project %s: %s", project_id, exc)


def _run_pep_analysis_task(
    task_id: str,
    *,
    results_root: Path,
    pep_data_dir: str,
    pep_paths: Optional[List[str]] = None,
    profile_path: str,
    group_fields: List[str],
    selected_chains: List[str],
    batch_field: Optional[str] = None,
    pvalue_threshold: float = 0.05,
    min_sample_threshold: int = 3,
    optional_steps: Optional[set] = None,
    output_name: Optional[str] = None,
    selected_samples: Optional[List[str]] = None,
    selected_group_values: Optional[Dict[str, List[str]]] = None,
    selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
    group_sample_identity: str = "sample",
    group_order: Optional[Dict[str, List[str]]] = None,
    project_id: Optional[str] = None,
    app_context_app: Optional[Any] = None
) -> None:
    try:
        _record_stage(task_id, 5, "Pep Analysis", f"Scanning pep data from {pep_data_dir}", {"module": "pep-analysis"})

        local_pep_dir = pep_data_dir
        local_profile = profile_path
        _record_stage(task_id, 8, "Pep Analysis", f"Profile: {profile_path}, Groups: {group_fields}, Chains: {selected_chains}", {"module": "pep-analysis"})

        service = PepAnalysisService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        report = service.generate_report(
            pep_data_dir=local_pep_dir,
            pep_paths=pep_paths,
            profile_path=local_profile,
            group_fields=group_fields,
            selected_chains=selected_chains,
            batch_field=batch_field,
            pvalue_threshold=pvalue_threshold,
            min_sample_threshold=min_sample_threshold,
            optional_steps=optional_steps,
            output_name=output_name,
            selected_samples=selected_samples,
            selected_group_values=selected_group_values,
            selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
            group_order=group_order,
            project_id=project_id,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                float(progress or 0.0),
                stage,
                detail,
                {"module": "pep-analysis", **(meta or {})}
            )
        )

        def _rel(path_str: str) -> str:
            return str(Path(path_str).relative_to(report.output_base).as_posix())

        def _url(path_str: str) -> str:
            return f"/api/script-hub/results/{report.job_id}/{_rel(path_str)}"

        result = {
            "module": "pep-analysis",
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "shared_matrix_urls": [_url(p) for p in report.shared_matrix_paths],
            "usage_urls": [_url(p) for p in report.usage_paths],
            "heatmap_image_urls": [_url(p) for p in report.heatmap_image_paths],
            "heatmap_csv_urls": [_url(p) for p in report.heatmap_csv_paths],
            "classification_urls": [_url(p) for p in report.classification_paths],
            "proportion_urls": [_url(p) for p in report.proportion_paths],
            "proportion_plot_urls": [_url(p) for p in getattr(report, "proportion_plot_paths", [])],
            "arrange_heatmap_urls": [_url(p) for p in report.arrange_heatmap_paths],
            "plot_heatmap_urls": [_url(p) for p in report.plot_heatmap_paths],
            "clone_tracking_image_urls": [_url(p) for p in getattr(report, "clone_tracking_image_paths", [])],
            "clone_tracking_table_urls": [_url(p) for p in getattr(report, "clone_tracking_table_paths", [])],
            "category_heatmap_urls": [_url(p) for p in getattr(report, "category_heatmap_paths", [])],
            "category_alignment_urls": [_url(p) for p in getattr(report, "category_alignment_paths", [])],
            "zip_url": _url(report.zip_path),
            "metadata_url": f"/api/script-hub/results/{report.job_id}/pep_analysis_metadata.json",
            "metadata": report.metadata,
        }
        result["png_urls"] = [
            url for url in result["heatmap_image_urls"] + result["proportion_plot_urls"] + result["arrange_heatmap_urls"] + result["plot_heatmap_urls"] + result["clone_tracking_image_urls"] + result["category_heatmap_urls"]
            if str(url).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg"))
        ]
        _write_pep_analysis_viewer(report.output_base, result, report.metadata)
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="PEP Sharing Analysis Results",
            subtitle="Chains: " + ", ".join(report.metadata.get("selected_chains") or selected_chains),
            dl_extras=[
                ("shared_matrix_urls", None, "Shared Matrix CSV"),
                ("usage_urls", None, "Usage CSV"),
                ("heatmap_csv_urls", None, "Heatmap CSV"),
                ("classification_urls", None, "Classification CSV"),
                ("proportion_urls", None, "Proportion CSV"),
                ("proportion_plot_urls", None, "Proportion Plots"),
                ("clone_tracking_image_urls", None, "\u8de8\u7ec4\u5171\u4eab CDR3 \u8f68\u8ff9\u56fe"),
                ("clone_tracking_table_urls", None, "\u8de8\u7ec4\u5171\u4eab CDR3 \u7ed3\u679c\u8868"),
                ("category_heatmap_urls", None, "CDR3 \u5206\u7c7b\u70ed\u56fe"),
                ("category_alignment_urls", None, "\u5206\u7c7b\u5171\u4eab\u514b\u9686\u53c2\u8003\u5e93\u6bd4\u5bf9\u7ed3\u679c"),
            ],
            zip_name="pep_analysis_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name="pep-analysis",
            detail=f"Pep analysis completed: {len(report.shared_matrix_paths)} shared matrices, "
                   f"{len(report.heatmap_image_paths)} heatmaps, {len(report.arrange_heatmap_paths)} arrange heatmaps",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )

        # Cache usage data as project asset if project_id provided
        if project_id:
            def _cache_project_usage_assets() -> None:
                _cache_pep_usage_assets(
                    project_id=project_id,
                    job_id=task_id,
                    output_base=str(report.output_base),
                    selected_chains=selected_chains,
                    group_fields=group_fields,
                    pep_data_dir=pep_data_dir,
                    profile_path=profile_path,
                    projects_root=Path(current_app.root_path) / "data" / "projects",
                    analysis_signature=str(result.get("analysis_signature") or ""),
                    result_id=str(result.get("result_id") or ""),
                )

            if app_context_app is not None:
                with app_context_app.app_context():
                    _cache_project_usage_assets()
            else:
                _cache_project_usage_assets()
    except Exception as exc:
        logger.error("Script hub Pep analysis task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="Failed",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "pep-analysis"},
            history=history[-80:]
        )
