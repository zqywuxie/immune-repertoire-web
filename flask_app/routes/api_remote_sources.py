"""
API routes for SSH Linux remote data sources.
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request, url_for

from flask_app.exceptions import ValidationError
from flask_app.services.remote_data_source_service import get_remote_data_source_service
from flask_app.services.remote_sync_service import get_remote_sync_service
from flask_app.services.ssh_file_provider import build_ssh_file_provider

logger = logging.getLogger(__name__)

remote_sources_bp = Blueprint("remote_sources", __name__, url_prefix="/api/remote-sources")
_sync_executor = ThreadPoolExecutor(max_workers=2)
_sync_task_lock = threading.Lock()
_sync_tasks: Dict[str, Dict[str, Any]] = {}


def _history_entry(progress: float, stage: str, detail: str, meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "progress": round(progress, 2),
        "stage": stage,
        "detail": detail,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "meta": meta or {},
    }


def _set_task_state(task_id: str, **updates: Any) -> None:
    with _sync_task_lock:
        state = _sync_tasks.setdefault(task_id, {})
        state.update(updates)


def _get_task_state(task_id: str) -> Dict[str, Any] | None:
    with _sync_task_lock:
        state = _sync_tasks.get(task_id)
        return dict(state) if state else None


def _run_sync_task(app, task_id: str, *, source_id: str, remote_path: str, force_refresh: bool) -> None:
    with app.app_context():
        try:
            source_service = get_remote_data_source_service()
            source = source_service.get_source(source_id)
            sync_service = get_remote_sync_service()

            def on_progress(progress: float, stage: str, detail: str, meta: Dict[str, Any] | None = None) -> None:
                history_item = _history_entry(progress, stage, detail, meta)
                with _sync_task_lock:
                    state = _sync_tasks.setdefault(task_id, {})
                    history = state.setdefault("history", [])
                    if not history or history[-1] != history_item:
                        history.append(history_item)
                        if len(history) > 80:
                            del history[:-80]
                    state.update(
                        {
                            "status": "running",
                            "progress": round(progress, 2),
                            "stage": stage,
                            "detail": detail,
                            "meta": meta or {},
                        }
                    )

            result = sync_service.sync_directory(
                source,
                remote_path,
                force_refresh=force_refresh,
                progress_callback=on_progress,
            )
            history = (_get_task_state(task_id) or {}).get("history", [])
            completion_meta = {
                "phase": "completed",
                "source_id": source_id,
                "remote_path": result["remote_path"],
                "local_cache_path": result["local_cache_path"],
                "file_count": result["file_count"],
            }
            completion = _history_entry(100.0, "Remote sync completed", "Remote data is ready for chord scanning", completion_meta)
            if not history or history[-1] != completion:
                history.append(completion)

            _set_task_state(
                task_id,
                status="completed",
                progress=100.0,
                stage="Remote sync completed",
                detail="Remote data is ready for chord scanning",
                meta=completion_meta,
                history=history[-80:],
                result=result,
            )
        except Exception as exc:
            logger.error("Remote sync task failed: %s", exc, exc_info=True)
            history = (_get_task_state(task_id) or {}).get("history", [])
            failure = _history_entry(100.0, "Remote sync failed", str(exc), {"phase": "failed"})
            if not history or history[-1] != failure:
                history.append(failure)
            _set_task_state(
                task_id,
                status="failed",
                progress=100.0,
                stage="Remote sync failed",
                detail=str(exc),
                error=str(exc),
                meta={"phase": "failed"},
                history=history[-80:],
            )


@remote_sources_bp.route("", methods=["GET"])
def list_remote_sources():
    try:
        service = get_remote_data_source_service()
        return jsonify({"success": True, "sources": service.list_sources()})
    except Exception as exc:
        logger.error("Failed to load SSH remote sources: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "REMOTE_SOURCE_ERROR", "message": str(exc)}), 500


@remote_sources_bp.route("/test", methods=["POST"])
def test_remote_source():
    try:
        data = request.get_json() or {}
        source_id = str(data.get("source_id") or "").strip()
        if not source_id:
            raise ValidationError(message="Please select an SSH remote source", details={"field": "source_id"})

        source = get_remote_data_source_service().get_source(source_id)
        provider = build_ssh_file_provider(source)
        test_result = provider.test_connection()
        return jsonify({"success": True, "source": source.to_public_dict(), "test_result": test_result})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("SSH remote source test failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "REMOTE_SOURCE_TEST_FAILED", "message": str(exc)}), 500


@remote_sources_bp.route("/browse", methods=["POST"])
def browse_remote_source():
    try:
        data = request.get_json() or {}
        source_id = str(data.get("source_id") or "").strip()
        if not source_id:
            raise ValidationError(message="Please select an SSH remote source", details={"field": "source_id"})

        source = get_remote_data_source_service().get_source(source_id)
        provider = build_ssh_file_provider(source)
        browse_result = provider.list_dir(data.get("path"))
        return jsonify({"success": True, **browse_result, "source": source.to_public_dict()})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("SSH remote source browse failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "REMOTE_BROWSE_FAILED", "message": str(exc)}), 500


@remote_sources_bp.route("/sync", methods=["POST"])
def sync_remote_source():
    try:
        data = request.get_json() or {}
        source_id = str(data.get("source_id") or "").strip()
        remote_path = str(data.get("remote_path") or "").strip()
        if not source_id:
            raise ValidationError(message="Please select an SSH remote source", details={"field": "source_id"})
        if not remote_path:
            raise ValidationError(message="Please select a remote directory", details={"field": "remote_path"})

        source = get_remote_data_source_service().get_source(source_id)
        provider = build_ssh_file_provider(source)
        resolved_remote_path = provider.resolve_remote_path(remote_path)

        task_id = f"remote_sync_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "source_id": source_id, "remote_path": resolved_remote_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Remote sync queued",
            detail="Waiting to start remote sync",
            meta=queued_meta,
            history=[_history_entry(0.0, "Remote sync queued", "Waiting to start remote sync", queued_meta)],
        )

        app = current_app._get_current_object()
        _sync_executor.submit(
            _run_sync_task,
            app,
            task_id,
            source_id=source_id,
            remote_path=resolved_remote_path,
            force_refresh=bool(data.get("force_refresh", False)),
        )

        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "status_url": url_for("remote_sources.get_remote_sync_task_status", task_id=task_id),
            }
        )
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Failed to queue remote sync: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "REMOTE_SYNC_ERROR", "message": str(exc)}), 500


@remote_sources_bp.route("/sync-task/<task_id>", methods=["GET"])
def get_remote_sync_task_status(task_id: str):
    task = _get_task_state(task_id)
    if not task:
        return jsonify({"success": False, "error": "NOT_FOUND", "message": "Remote sync task does not exist"}), 404
    return jsonify({"success": True, **task})
