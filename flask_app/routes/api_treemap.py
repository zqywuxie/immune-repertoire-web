"""
API routes for treemap generation, browsing, and export.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, current_app, jsonify, request, send_file, url_for

from flask_app.exceptions import ValidationError
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.background_job_service import get_background_job_service
from flask_app.services.user_scope import current_user_id
from flask_app.services.treemap_report_service import get_treemap_report_service

logger = logging.getLogger(__name__)

treemap_bp = Blueprint("treemap", __name__, url_prefix="/api/treemap")
_treemap_executor = ThreadPoolExecutor(max_workers=2)
_treemap_task_lock = threading.Lock()
_treemap_tasks: Dict[str, Dict[str, Any]] = {}


def _get_service():
    results_root = Path(current_app.config.get("RESULTS_FOLDER", Path(current_app.root_path) / "data" / "results"))
    if not results_root.is_absolute():
        results_root = Path(current_app.root_path) / results_root
    return get_treemap_report_service(results_root=PathAccessService.results_root_for_user(results_root.resolve()))


def _validate_sample_paths(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    validated = []
    for sample in samples:
        item = dict(sample)
        data_files = []
        for file_info in item.get("data_files") or []:
            file_item = dict(file_info)
            if file_item.get("filepath"):
                file_item["filepath"] = str(PathAccessService.validate_read_path(file_item["filepath"]))
            data_files.append(file_item)
        item["data_files"] = data_files
        if item.get("folder_path"):
            item["folder_path"] = str(PathAccessService.validate_read_path(item["folder_path"]))
        validated.append(item)
    return validated


def _set_task_state(task_id: str, **updates: Any) -> None:
    with _treemap_task_lock:
        task = _treemap_tasks.setdefault(task_id, {})
        updates.setdefault("user_id", task.get("user_id") or current_user_id())
        task.update(updates)
        snapshot = dict(task)
    try:
        get_background_job_service().upsert_job(task_id, {
            "job_type": "treemap",
            "module": "treemap",
            "task_id": task_id,
            **snapshot,
        })
    except Exception:
        logger.warning("Failed to sync treemap task %s to global job store", task_id, exc_info=True)


def _get_task_state(task_id: str) -> Dict[str, Any] | None:
    with _treemap_task_lock:
        task = _treemap_tasks.get(task_id)
        return dict(task) if task else None


def _history_entry(progress: float, stage: str, detail: str, meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "progress": round(progress, 2),
        "stage": stage,
        "detail": detail,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "meta": meta or {},
    }


def _merge_progress_meta(
    base_meta: Dict[str, Any] | None,
    *,
    total_samples: int,
    selected_chains: List[str],
    samples: List[Dict[str, Any]],
    detail: str,
) -> Dict[str, Any]:
    meta = dict(base_meta or {})
    meta.setdefault("total_samples", total_samples)
    meta.setdefault("selected_chain_count", len(selected_chains))
    meta.setdefault("selected_chains", list(selected_chains))

    detail_parts = [part.strip() for part in str(detail or "").split("|")]
    prepare_match = re.match(r"^正在准备样本\s+(.+)$", str(detail or "").strip())
    if prepare_match and not meta.get("current_sample"):
        sample_name = prepare_match.group(1).strip()
        if sample_name:
            meta["current_sample"] = sample_name
    if detail_parts:
        sample_name = detail_parts[0]
        sample_names = {
            str(sample.get("display_name") or sample.get("original_name") or "").strip()
            for sample in samples
        }
        if sample_name and sample_name in sample_names:
            if not meta.get("current_sample"):
                meta["current_sample"] = sample_name
            ordered_names = [
                str(sample.get("display_name") or sample.get("original_name") or "").strip()
                for sample in samples
                if str(sample.get("display_name") or sample.get("original_name") or "").strip()
            ]
            if sample_name in ordered_names and not meta.get("current_sample_index"):
                meta["current_sample_index"] = ordered_names.index(sample_name) + 1
    if len(detail_parts) > 1:
        chain_name = detail_parts[1]
        chain_match = re.match(r"^(?P<name>[^()]+?)(?:\s+\((?P<index>\d+)/(?P<total>\d+)\))?$", chain_name)
        if chain_match:
            parsed_chain_name = chain_match.group("name").strip()
            if parsed_chain_name and parsed_chain_name.lower() != "overview" and not meta.get("current_chain"):
                meta["current_chain"] = parsed_chain_name
            if chain_match.group("index") and not meta.get("current_chain_index"):
                meta["current_chain_index"] = int(chain_match.group("index"))
            if chain_match.group("total") and not meta.get("current_chain_total"):
                meta["current_chain_total"] = int(chain_match.group("total"))

    return meta


def _build_sample_payload(job_id: str, sample_info: Dict[str, Any]) -> Dict[str, Any]:
    individual_urls = {
        chain: {
            kind: url_for("treemap.get_treemap_result_file", job_id=job_id, relative_path=relative_path)
            for kind, relative_path in paths.items()
        }
        for chain, paths in sample_info.get("individual_treemaps", {}).items()
    }

    overview_info = sample_info.get("overview_treemaps", {})
    overview_urls = {
        kind: url_for("treemap.get_treemap_result_file", job_id=job_id, relative_path=relative_path)
        for kind, relative_path in overview_info.items()
    } if overview_info else {}

    return {
        "sample_name": sample_info.get("sample_name"),
        "display_name": sample_info.get("display_name"),
        "chains": sample_info.get("chains", []),
        "individual_treemaps": individual_urls,
        "overview_treemaps": overview_urls,
    }


def _run_treemap_task(
    task_id: str,
    *,
    results_root: Path,
    samples: List[Dict[str, Any]],
    selected_chains: List[str],
    field_mapping: Dict[str, Any],
    output_name: str | None,
    min_copy_default: Any,
    top_n: Any,
    topclone_only: Any,
    style: Any,
    layout_mode: Any,
    canvas_shape: Any,
) -> None:
    try:
        service = get_treemap_report_service(results_root=results_root)

        def on_progress(
            progress: float,
            stage: str,
            detail: str,
            meta: Dict[str, Any] | None = None,
        ) -> None:
            merged_meta = _merge_progress_meta(
                meta,
                total_samples=len(samples),
                selected_chains=selected_chains,
                samples=samples,
                detail=detail,
            )
            history_entry = _history_entry(progress, stage, detail, merged_meta)
            with _treemap_task_lock:
                task = _treemap_tasks.setdefault(task_id, {})
                task["status"] = "running"
                task["progress"] = round(progress, 2)
                task["stage"] = stage
                task["detail"] = detail
                task["meta"] = merged_meta
                history = task.setdefault("history", [])
                if not history or history[-1] != history_entry:
                    history.append(history_entry)
                    if len(history) > 60:
                        del history[:-60]

        result = service.generate_report(
            samples=samples,
            selected_chains=selected_chains,
            field_mapping=field_mapping,
            output_name=output_name,
            min_copy_default=min_copy_default,
            top_n=top_n,
            topclone_only=bool(topclone_only),
            style=style,
            layout_mode=layout_mode,
            canvas_shape=canvas_shape,
            progress_callback=on_progress,
        )

        result_samples = result.metadata.get("samples", [])
        topclone_only = bool(result.metadata.get("topclone_only"))
        completion_detail = (
            f"共生成 {len(result_samples)} 个样本的 topclone 结果。"
            if topclone_only
            else f"共生成 {len(result_samples)} 个样本的 treemap 结果。"
        )
        _set_task_state(
            task_id,
            status="completed",
            progress=100.0,
            stage="任务完成",
            detail=completion_detail,
            result={
                "job_id": result.job_id,
                "sample_count": len(result_samples),
                "viewer_url": f"/api/treemap/results/{result.job_id}/viewer.html",
                "zip_url": f"/api/treemap/export-zip/{result.job_id}",
                "topclone_only": topclone_only,
            },
        )
        task_history = (_get_task_state(task_id) or {}).get("history", [])
        completion_entry = _history_entry(
            100.0,
            "任务完成",
            completion_detail,
            {
                "phase": "completed",
                "generated_samples": len(result_samples),
                "total_samples": len(samples),
                "selected_chain_count": len(selected_chains),
                "selected_chains": list(selected_chains),
                "topclone_only": topclone_only,
            },
        )
        if not task_history or (
            task_history[-1].get("stage") != completion_entry["stage"]
            or task_history[-1].get("detail") != completion_entry["detail"]
            or round(float(task_history[-1].get("progress", 0.0)), 2) != completion_entry["progress"]
        ):
            task_history.append(completion_entry)
        _set_task_state(
            task_id,
            stage="任务完成",
            detail=completion_detail,
            meta={
                "phase": "completed",
                "generated_samples": len(result_samples),
                "total_samples": len(samples),
                "selected_chain_count": len(selected_chains),
                "selected_chains": list(selected_chains),
                "topclone_only": topclone_only,
            },
            history=task_history[-60:],
        )
    except Exception as exc:
        logger.error("Treemap background task failed: %s", exc, exc_info=True)
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="任务失败",
            detail=str(exc),
            error=str(exc),
        )
        task_history = (_get_task_state(task_id) or {}).get("history", [])
        failure_entry = _history_entry(100.0, "任务失败", str(exc), {"phase": "failed"})
        if not task_history or (
            task_history[-1].get("stage") != failure_entry["stage"]
            or task_history[-1].get("detail") != failure_entry["detail"]
            or round(float(task_history[-1].get("progress", 0.0)), 2) != failure_entry["progress"]
        ):
            task_history.append(failure_entry)
        _set_task_state(
            task_id,
            stage="任务失败",
            meta={"phase": "failed"},
            history=task_history[-60:],
        )


@treemap_bp.route("/generate", methods=["POST"])
def generate_treemap():
    try:
        data = request.get_json() or {}

        samples = data.get("samples") or []
        if not samples:
            raise ValidationError(message="请先扫描并提供样本列表。", details={"field": "samples"})
        samples = _validate_sample_paths(samples)

        selected_chains = data.get("selected_chains") or []
        if not selected_chains:
            raise ValidationError(message="请至少选择一条链。", details={"field": "selected_chains"})

        field_mapping = data.get("field_mapping") or {}
        if not field_mapping.get("cdr3_column"):
            raise ValidationError(message="请选择 CDR3 列。", details={"field": "cdr3_column"})
        if not field_mapping.get("copy_column"):
            raise ValidationError(message="请选择 copy 列。", details={"field": "copy_column"})
        if not field_mapping.get("v_column"):
            raise ValidationError(message="请选择 V 列。", details={"field": "v_column"})
        if not field_mapping.get("j_column"):
            raise ValidationError(message="请选择 J 列。", details={"field": "j_column"})

        config = data.get("config") or {}
        output_name = str(config.get("output_name") or "").strip() or None
        min_copy_default = config.get("min_copy_default", 30)
        top_n = config.get("top_n", 100)
        topclone_only = bool(config.get("topclone_only"))
        layout_mode = str(config.get("layout_mode") or "tetris").strip().lower()
        if layout_mode not in {"tetris", "qr"}:
            layout_mode = "tetris"

        results_root = Path(current_app.config.get("RESULTS_FOLDER", Path(current_app.root_path) / "data" / "results"))
        if not results_root.is_absolute():
            results_root = Path(current_app.root_path) / results_root
        results_root = PathAccessService.results_root_for_user(results_root.resolve())

        task_id = f"treemap_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="任务已创建",
            detail="任务已进入队列，等待开始。",
            history=[{"progress": 0.0, "stage": "任务已创建", "detail": "任务已进入队列，等待开始。"}],
        )
        _set_task_state(
            task_id,
            stage="任务已创建",
            detail="任务已进入队列，等待开始。",
            meta={
                "phase": "queued",
                "total_samples": len(samples),
                "selected_chain_count": len(selected_chains),
                "selected_chains": list(selected_chains),
            },
            history=[
                _history_entry(
                    0.0,
                    "任务已创建",
                    "任务已进入队列，等待开始。",
                    {
                        "phase": "queued",
                        "total_samples": len(samples),
                        "selected_chain_count": len(selected_chains),
                        "selected_chains": list(selected_chains),
                    },
                )
            ],
        )

        _treemap_executor.submit(
            _run_treemap_task,
            task_id,
            results_root=results_root,
            samples=samples,
            selected_chains=selected_chains,
            field_mapping=field_mapping,
            output_name=output_name,
            min_copy_default=min_copy_default,
            top_n=top_n,
            topclone_only=topclone_only,
            style=style,
            layout_mode=layout_mode,
            canvas_shape=canvas_shape,
        )

        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "status_url": url_for("treemap.get_treemap_task_status", task_id=task_id),
            }
        )

    except ValidationError as exc:
        logger.warning("Validation error in generate_treemap: %s", exc.message)
        return jsonify(
            {
                "success": False,
                "error": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        ), 400

    except Exception as exc:
        logger.error("Error generating treemap bundle: %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "TREEMAP_GENERATION_ERROR",
                "message": f"生成 treemap 结果时发生错误: {str(exc)}",
            }
        ), 500


@treemap_bp.route("/task/<task_id>", methods=["GET"])
def get_treemap_task_status(task_id: str):
    task = _get_task_state(task_id)
    if not task:
        return jsonify(
            {
                "success": False,
                "error": "NOT_FOUND",
                "message": "Treemap 任务不存在。",
            }
        ), 404
    return jsonify({"success": True, **task})


@treemap_bp.route("/job/<job_id>", methods=["GET"])
def get_treemap_job(job_id: str):
    try:
        service = _get_service()
        metadata = service.read_metadata(job_id)
        samples = [_build_sample_payload(job_id, sample_info) for sample_info in metadata.get("samples", [])]
        if not samples:
            raise ValidationError(message="该任务下没有可查看的 treemap 结果。")

        default_sample = samples[0]
        default_chain = default_sample["chains"][0] if default_sample["chains"] else None

        return jsonify(
            {
                "success": True,
                "job_id": job_id,
                "samples": samples,
                "default_sample": default_sample.get("sample_name"),
                "default_chain": default_chain,
                "topclone_only": bool(metadata.get("topclone_only")),
                "zip_url": url_for("treemap.export_treemap_zip", job_id=job_id),
            }
        )

    except ValidationError as exc:
        logger.warning("Validation error in get_treemap_job: %s", exc.message)
        return jsonify(
            {
                "success": False,
                "error": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        ), 400

    except FileNotFoundError:
        return jsonify(
            {
                "success": False,
                "error": "NOT_FOUND",
                "message": "Treemap 任务不存在。",
            }
        ), 404

    except Exception as exc:
        logger.error("Error reading treemap job: %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "TREEMAP_JOB_ERROR",
                "message": f"读取 treemap 任务时发生错误: {str(exc)}",
            }
        ), 500


@treemap_bp.route("/export-zip/<job_id>", methods=["GET"])
def export_treemap_zip(job_id: str):
    try:
        service = _get_service()
        zip_buffer, download_name = service.build_zip_buffer(job_id)
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=download_name,
        )

    except ValidationError as exc:
        logger.warning("Validation error in export_treemap_zip: %s", exc.message)
        return jsonify(
            {
                "success": False,
                "error": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        ), 400

    except FileNotFoundError:
        return jsonify(
            {
                "success": False,
                "error": "NOT_FOUND",
                "message": "Treemap 结果不存在。",
            }
        ), 404

    except Exception as exc:
        logger.error("Error exporting treemap zip: %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "TREEMAP_EXPORT_ERROR",
                "message": f"导出 treemap ZIP 时发生错误: {str(exc)}",
            }
        ), 500


@treemap_bp.route("/results/<job_id>/<path:relative_path>", methods=["GET"])
def get_treemap_result_file(job_id: str, relative_path: str):
    try:
        service = _get_service()
        target_file = service.resolve_result_file(job_id, relative_path)
        return send_file(target_file)

    except ValidationError as exc:
        logger.warning("Validation error in get_treemap_result_file: %s", exc.message)
        return jsonify(
            {
                "success": False,
                "error": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        ), 400

    except FileNotFoundError:
        return jsonify(
            {
                "success": False,
                "error": "NOT_FOUND",
                "message": "Treemap 结果文件不存在。",
            }
        ), 404

    except Exception as exc:
        logger.error("Error serving treemap result file: %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "TREEMAP_FILE_SERVE_ERROR",
                "message": f"读取 treemap 结果文件时发生错误: {str(exc)}",
            }
        ), 500
