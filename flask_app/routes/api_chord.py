"""
API routes for chord diagram generation, browsing, and export.
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from flask import Blueprint, current_app, jsonify, request, send_file, url_for

from flask_app.exceptions import ValidationError
from flask_app.services.chord_report_service import get_chord_report_service

logger = logging.getLogger(__name__)

chord_bp = Blueprint("chord", __name__, url_prefix="/api/chord")
_chord_executor = ThreadPoolExecutor(max_workers=2)
_chord_task_lock = threading.Lock()
_chord_tasks: Dict[str, Dict[str, Any]] = {}


def _get_service():
    results_root = Path(current_app.config.get("RESULTS_FOLDER", Path(current_app.root_path) / "data" / "results"))
    if not results_root.is_absolute():
        results_root = Path(current_app.root_path) / results_root
    return get_chord_report_service(results_root=results_root)


def _set_task_state(task_id: str, **updates: Any) -> None:
    with _chord_task_lock:
        task = _chord_tasks.setdefault(task_id, {})
        task.update(updates)


def _get_task_state(task_id: str) -> Dict[str, Any] | None:
    with _chord_task_lock:
        task = _chord_tasks.get(task_id)
        return dict(task) if task else None


def _history_entry(progress: float, stage: str, detail: str, meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "progress": round(progress, 2),
        "stage": stage,
        "detail": detail,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "meta": meta or {},
    }


def _run_chord_task(
    task_id: str,
    *,
    results_root: Path,
    samples: List[Dict[str, Any]],
    selected_chains: List[str],
    field_mapping: Dict[str, Any],
    output_name: str | None,
    count_mode: str,
) -> None:
    try:
        service = get_chord_report_service(results_root=results_root)

        def on_progress(progress: float, stage: str, detail: str, meta: Dict[str, Any] | None = None) -> None:
            history_entry = _history_entry(progress, stage, detail, meta)
            with _chord_task_lock:
                task = _chord_tasks.setdefault(task_id, {})
                task["status"] = "running"
                task["progress"] = round(progress, 2)
                task["stage"] = stage
                task["detail"] = detail
                task["meta"] = meta or {}
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
            count_mode=count_mode,
            progress_callback=on_progress,
        )

        task_history = (_get_task_state(task_id) or {}).get("history", [])
        completion_meta = {
            "phase": "completed",
            "total_samples": result.metadata.get("sample_count", 0),
            "selected_chain_count": len(selected_chains),
            "selected_chains": list(selected_chains),
            "total_units": result.metadata.get("total_outputs", 0),
            "completed_units": result.metadata.get("total_outputs", 0),
        }
        completion_entry = _history_entry(
            100.0,
            "任务完成",
            f"共生成 {result.metadata.get('total_outputs', 0)} 个 chord 图结果。",
            completion_meta,
        )
        if not task_history or task_history[-1] != completion_entry:
            task_history.append(completion_entry)

        _set_task_state(
            task_id,
            status="completed",
            progress=100.0,
            stage="任务完成",
            detail=f"共生成 {result.metadata.get('total_outputs', 0)} 个 chord 图结果。",
            meta=completion_meta,
            history=task_history[-60:],
            result={
                "job_id": result.job_id,
                "sample_count": result.metadata.get("sample_count", 0),
                "output_count": result.metadata.get("total_outputs", 0),
                "viewer_url": f"/api/chord/results/{result.job_id}/viewer.html",
                "zip_url": f"/api/chord/export-zip/{result.job_id}",
            },
        )
    except Exception as exc:
        logger.error("Chord background task failed: %s", exc, exc_info=True)
        task_history = (_get_task_state(task_id) or {}).get("history", [])
        failure_entry = _history_entry(100.0, "任务失败", str(exc), {"phase": "failed"})
        if not task_history or task_history[-1] != failure_entry:
            task_history.append(failure_entry)
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="任务失败",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed"},
            history=task_history[-60:],
        )


@chord_bp.route("/generate", methods=["POST"])
def generate_chord():
    try:
        data = request.get_json() or {}

        samples = data.get("samples") or []
        if not samples:
            raise ValidationError(message="请先扫描并提供样本列表。", details={"field": "samples"})

        selected_chains = data.get("selected_chains") or []
        if not selected_chains:
            raise ValidationError(message="请至少选择一条链。", details={"field": "selected_chains"})

        field_mapping = data.get("field_mapping") or {}
        if not field_mapping.get("v_column"):
            raise ValidationError(message="请选择 V 列。", details={"field": "v_column"})
        if not field_mapping.get("j_column"):
            raise ValidationError(message="请选择 J 列。", details={"field": "j_column"})

        config = data.get("config") or {}
        output_name = str(config.get("output_name") or "").strip() or None
        count_mode = "rows"

        results_root = Path(current_app.config.get("RESULTS_FOLDER", Path(current_app.root_path) / "data" / "results"))
        if not results_root.is_absolute():
            results_root = Path(current_app.root_path) / results_root

        task_id = f"chord_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {
            "phase": "queued",
            "total_samples": len(samples),
            "selected_chain_count": len(selected_chains),
            "selected_chains": list(selected_chains),
        }
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="任务已创建",
            detail="任务已进入队列，等待开始。",
            meta=queued_meta,
            history=[_history_entry(0.0, "任务已创建", "任务已进入队列，等待开始。", queued_meta)],
        )

        _chord_executor.submit(
            _run_chord_task,
            task_id,
            results_root=results_root,
            samples=samples,
            selected_chains=selected_chains,
            field_mapping=field_mapping,
            output_name=output_name,
            count_mode=count_mode,
        )

        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "status_url": url_for("chord.get_chord_task_status", task_id=task_id),
            }
        )

    except ValidationError as exc:
        logger.warning("Validation error in generate_chord: %s", exc.message)
        return jsonify(
            {
                "success": False,
                "error": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        ), 400

    except Exception as exc:
        logger.error("Error generating chord bundle: %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "CHORD_GENERATION_ERROR",
                "message": f"生成 chord 结果时发生错误: {str(exc)}",
            }
        ), 500


@chord_bp.route("/task/<task_id>", methods=["GET"])
def get_chord_task_status(task_id: str):
    task = _get_task_state(task_id)
    if not task:
        return jsonify(
            {
                "success": False,
                "error": "NOT_FOUND",
                "message": "Chord 任务不存在。",
            }
        ), 404
    return jsonify({"success": True, **task})


@chord_bp.route("/job/<job_id>", methods=["GET"])
def get_chord_job(job_id: str):
    try:
        metadata = _get_service().read_metadata(job_id)
        return jsonify(
            {
                "success": True,
                "job_id": job_id,
                "metadata": metadata,
                "viewer_url": url_for("chord.get_chord_result_file", job_id=job_id, relative_path="viewer.html"),
                "zip_url": url_for("chord.export_chord_zip", job_id=job_id),
            }
        )

    except FileNotFoundError:
        return jsonify(
            {
                "success": False,
                "error": "NOT_FOUND",
                "message": "Chord 任务不存在。",
            }
        ), 404

    except Exception as exc:
        logger.error("Error reading chord job: %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "CHORD_JOB_READ_ERROR",
                "message": f"读取 chord 任务时发生错误: {str(exc)}",
            }
        ), 500


@chord_bp.route("/export-zip/<job_id>", methods=["GET"])
def export_chord_zip(job_id: str):
    try:
        buffer, filename = _get_service().build_zip_archive(job_id)
        return send_file(buffer, mimetype="application/zip", as_attachment=True, download_name=filename)

    except FileNotFoundError:
        return jsonify(
            {
                "success": False,
                "error": "NOT_FOUND",
                "message": "Chord 结果不存在。",
            }
        ), 404

    except Exception as exc:
        logger.error("Error exporting chord zip: %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "CHORD_EXPORT_ERROR",
                "message": f"导出 chord ZIP 时发生错误: {str(exc)}",
            }
        ), 500


@chord_bp.route("/results/<job_id>/<path:relative_path>", methods=["GET"])
def get_chord_result_file(job_id: str, relative_path: str):
    try:
        path = _get_service().resolve_result_path(job_id, relative_path)
        return send_file(path)

    except ValidationError as exc:
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
                "message": "Chord 结果文件不存在。",
            }
        ), 404

    except Exception as exc:
        logger.error("Error serving chord result file: %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "CHORD_RESULT_READ_ERROR",
                "message": f"读取 chord 结果文件时发生错误: {str(exc)}",
            }
        ), 500
