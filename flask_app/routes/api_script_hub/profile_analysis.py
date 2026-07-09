"""Profile analysis routes: topclone, profile, pep-analysis, pgen-analysis."""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request

from flask_app.exceptions import ValidationError
from flask_app.services.boxplot_service import BoxPlotService
from flask_app.services.pep_analysis_service import PepAnalysisService
from flask_app.services.pgen_analysis_service import PgenAnalysisService
from flask_app.services.topclone_service import TopCloneService
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
    _script_executor,
    _selected_samples_by_group_from_request,
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
    mode: str = "trace",
    top_n: int = 10,
    group_field: Optional[str] = None,
    group_order: Optional[str] = None,
    pvalue_threshold: float = 0.05,
    selected_chains: Optional[List[str]] = None,
    output_name: Optional[str] = None,
    module_name: str = "topclone",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "TopClone inspect", f"Scanning {pep_data_path}", {"module": module_name})

        local_pep = pep_data_path
        local_dp = datapoint_path
        service = TopCloneService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            pep_data_path=local_pep,
            datapoint_path=local_dp,
            mode=mode,
            top_n=top_n,
            group_field=group_field,
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

        result["zip_url"] = f"/api/script-hub/results/{report.job_id}/topclone_results.zip"
        _build_topclone_viewer(report.output_base, result, report.metadata)
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="TopClone Analysis Results",
            subtitle="Mode: " + str(report.metadata.get("mode", "")) + " | Chains: " + ", ".join(report.metadata.get("chains", [])),
            dl_extras=[("topclone_csv_url", "topclone.csv", "TopClone CSV"),
                       ("csv_urls", None, "BoxPlot CSV"),
                       ("pvalue_urls", None, "P-value CSV"),
                       ("cdr3_urls", None, "CDR3 Sequences")],
            zip_name="topclone_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"TopClone generated {len(result['png_urls'])} boxplots",
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
            stage="Failed",
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

        discovery = _inspect_data_selection_payload([pep_data_path], datapoint_path or None)
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
        mode = str(data.get("mode") or "trace").strip()
        top_n = int(data.get("top_n") or 10)
        group_field = str(data.get("group_field") or "").strip() or None
        group_order = str(data.get("group_order") or "").strip() or None
        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        selected_chains = [
            _normalize_chain(str(chain))
            for chain in (data.get("selected_chains") if isinstance(data.get("selected_chains"), list) else [])
            if str(chain or "").strip()
        ]
        output_name = str(data.get("output_name") or "").strip() or None

        if not pep_data_path:
            raise ValidationError(message="pep_data_path is required", details={"field": "pep_data_path"})
        if mode == "trace" and not datapoint_path:
            raise ValidationError(message="datapoint_path is required for trace mode", details={"field": "datapoint_path"})
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
                "group_order": group_order,
                "pvalue_threshold": pvalue_threshold,
                "selected_chains": selected_chains,
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
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
            **cache_context,
        )

        _script_executor.submit(
            _run_topclone_task,
            task_id,
            results_root=_resolve_results_root(),
            pep_data_path=pep_data_path,
            datapoint_path=datapoint_path,
            mode=mode,
            top_n=top_n,
            group_field=group_field,
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


@bp.route("/profile/inspect", methods=["POST"])
def inspect_profile():
    try:
        data = request.get_json() or {}
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path")
        base_path = str(data.get("base_path") or "").strip()

        discovery = _discover_boxplot_inputs(base_path, datapoint_path)
        suggestions = _suggest_profile_ranges(discovery["columns"])
        discovery.update(suggestions)

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
        selected_samples = _selected_samples_from_request(data)
        selected_samples_by_group = _selected_samples_by_group_from_request(data)

        if not pep_data_dir:
            raise ValidationError(message="pep_data_dir is required", details={"field": "pep_data_dir"})
        if not profile_path:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})
        if not selected_chains:
            raise ValidationError(message="selected_chains is required", details={"field": "selected_chains"})
        if not group_fields:
            raise ValidationError(message="group_fields is required", details={"field": "group_fields"})

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        min_sample_threshold = int(data.get("min_sample_threshold") or 3)
        optional_steps_raw = data.get("optional_steps") if isinstance(data.get("optional_steps"), list) else None
        optional_steps = {int(step) for step in optional_steps_raw if str(step).isdigit()} if optional_steps_raw is not None else None
        optional_steps = {step for step in optional_steps if step in {5, 6, 7, 8}} if optional_steps is not None else None
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
                "group_order": str(data.get("group_order") or "").strip() or None,
                "selected_samples": selected_samples,
                "selected_samples_by_group": selected_samples_by_group,
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
            profile_path=profile_path,
            group_fields=group_fields,
            selected_chains=selected_chains,
            pvalue_threshold=pvalue_threshold,
            min_sample_threshold=min_sample_threshold,
            optional_steps=optional_steps,
            output_name=output_name,
            selected_samples=selected_samples,
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
                "distribution_category_col": distribution_category_col or "",
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
            profile_path=profile_path,
            selected_chains=selected_chains,
            species=species,
            sample_col=sample_col,
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
    profile_path: str,
    selected_chains: List[str],
    species: str = "human",
    sample_col: str = "sample",
    distribution_category_col: Optional[str] = None,
    output_name: Optional[str] = None,
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        module_name = "pgen-analysis"
        _record_stage(task_id, 5, "Pgen analysis", f"Preparing {pep_data_dir}", {"module": module_name})
        service = PgenAnalysisService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            pep_data_dir=pep_data_dir,
            profile_path=profile_path,
            selected_chains=selected_chains,
            species=species,
            sample_col=sample_col,
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
    profile_path: str,
    group_fields: List[str],
    selected_chains: List[str],
    pvalue_threshold: float = 0.05,
    min_sample_threshold: int = 3,
    optional_steps: Optional[set] = None,
    output_name: Optional[str] = None,
    selected_samples: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    app_context_app: Optional[Any] = None
) -> None:
    try:
        _record_stage(task_id, 5, "Pep Analysis", f"Scanning pep data from {pep_data_dir}", {"module": "pep-analysis"})

        local_pep_dir = pep_data_dir
        local_profile = profile_path
        _record_stage(task_id, 8, "Pep Analysis", f"Profile: {profile_path}, Groups: {group_fields}, Chains: {selected_chains}", {"module": "pep-analysis"})

        service = PepAnalysisService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            pep_data_dir=local_pep_dir,
            profile_path=local_profile,
            group_fields=group_fields,
            selected_chains=selected_chains,
            pvalue_threshold=pvalue_threshold,
            min_sample_threshold=min_sample_threshold,
            optional_steps=optional_steps,
            output_name=output_name,
            selected_samples=selected_samples,
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
            "zip_url": _url(report.zip_path),
            "metadata_url": f"/api/script-hub/results/{report.job_id}/pep_analysis_metadata.json",
            "metadata": report.metadata,
        }
        result["png_urls"] = [
            url for url in result["heatmap_image_urls"] + result["proportion_plot_urls"] + result["arrange_heatmap_urls"] + result["plot_heatmap_urls"]
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
                    job_id=report.job_id,
                    output_base=str(report.output_base),
                    selected_chains=selected_chains,
                    group_fields=group_fields,
                    pep_data_dir=pep_data_dir,
                    profile_path=profile_path,
                    projects_root=results_root.parent / "projects",
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


