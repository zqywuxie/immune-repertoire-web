"""Job API — Phase 5 implementation with repository layer."""

import asyncio
import json
import logging
import sys
import threading
from pathlib import Path as FsPath
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path as ApiPath, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.auth import require_current_user
from ..core.database import get_db
from ..schemas.domain import (
    JobListResponse,
    JobModulesResponse,
    JobResultsResponse,
    SubmitJobRequest,
    SubmitJobResponse,
)
from ..services.job_service import JobService

router = APIRouter(tags=["Jobs"], dependencies=[Depends(require_current_user)])
logger = logging.getLogger(__name__)
_dispatch_lock = threading.Lock()
_dispatched_jobs: set[str] = set()


class BulkDeleteJobsRequest(BaseModel):
    job_ids: list[str] = Field(default_factory=list)
    delete_results: bool = False


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List background jobs."""
    svc = JobService(db)
    jobs = svc.list_jobs(
        project_id=project_id, status=status, module=module, limit=limit
    )
    _resume_queued_jobs(jobs)
    return {"success": True, "jobs": jobs}


@router.post("/jobs", response_model=SubmitJobResponse)
async def submit_job(body: SubmitJobRequest, db: Session = Depends(get_db)):
    """Submit a unified background job."""
    import uuid
    from datetime import datetime, timezone

    svc = JobService(db)
    svc.validate_module(body.module)

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    svc.submit_job({
        "id": job_id,
        "job_type": "api_request",
        "module": body.module,
        "status": "queued",
        "progress": 0,
        "payload": body.payload,
        "result": {},
        "project_id": body.project_id or None,
        "user_id": None,
        "created_at": now,
        "updated_at": now,
    })

    try:
        _start_background_job(body.module, job_id)
    except RuntimeError as exc:
        _mark_job_failed(job_id, f"Worker dispatch failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to start background job") from exc

    return {
        "success": True,
        "job_id": job_id,
        "task_id": job_id,
        "status_url": f"/api/jobs/{job_id}",
        "status": "queued",
    }


def _start_background_job(module: str, job_id: str) -> None:
    """Start a repository job in a daemon worker thread."""
    with _dispatch_lock:
        if job_id in _dispatched_jobs:
            return
        _dispatched_jobs.add(job_id)

    thread = threading.Thread(
        target=_execute_job_background,
        args=(module, job_id),
        daemon=True,
        name=f"analysis-job-{job_id[:8]}",
    )
    thread.start()


def _execute_job_background(module: str, job_id: str) -> None:
    """Execute a queued job using the shared analysis worker registry."""
    try:
        _mark_job_running(job_id)
        _ensure_project_root_on_path()
        from analysis_workers.main import execute

        result = execute(module, job_id)
        if isinstance(result, dict) and result.get("success") is False:
            error = str(result.get("error") or "Worker returned failure")
            logger.error("Background job %s failed: %s", job_id, error)
            _mark_job_failed(job_id, error)
    except Exception as exc:
        logger.exception("Background job %s crashed before completion", job_id)
        _mark_job_failed(job_id, str(exc))
    finally:
        with _dispatch_lock:
            _dispatched_jobs.discard(job_id)


def _resume_queued_jobs(jobs: list[dict]) -> None:
    """Best-effort resume for queued jobs left behind after server restarts."""
    for job in jobs:
        if job.get("status") != "queued":
            continue
        job_id = str(job.get("job_id") or job.get("id") or "")
        module = str(job.get("module") or "")
        if not job_id or not module:
            continue
        try:
            _start_background_job(module, job_id)
        except RuntimeError as exc:
            _mark_job_failed(job_id, f"Worker resume failed: {exc}")


def _mark_job_running(job_id: str) -> None:
    """Move a queued job to running before the worker bridge imports Flask."""
    try:
        from ..core.database import SessionLocal
        from ..repositories.jobs import JobRepository

        db = SessionLocal()
        try:
            JobRepository(db).update_status(
                job_id,
                status="running",
                progress=1,
                stage="Dispatching worker",
            )
        finally:
            db.close()
    except Exception:
        logger.exception("Failed to mark background job %s as running", job_id)


def _mark_job_failed(job_id: str, error: str) -> None:
    """Best-effort fallback so dispatch failures do not leave jobs queued forever."""
    try:
        from ..core.database import SessionLocal
        from ..repositories.jobs import JobRepository

        db = SessionLocal()
        try:
            JobRepository(db).update_status(
                job_id,
                status="failed",
                progress=100,
                stage=f"Failed: {error[:200]}",
            )
        finally:
            db.close()
    except Exception:
        logger.exception("Failed to mark background job %s as failed", job_id)


def _ensure_project_root_on_path() -> None:
    """Make top-level worker packages importable when FastAPI runs from backend-api."""
    project_root = FsPath(__file__).resolve().parents[3]
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


@router.get("/jobs/modules", response_model=JobModulesResponse)
async def list_job_modules():
    """List frontend-visible job modules from the canonical manifest."""
    from ..services.module_registry import get_module_registry

    registry = get_module_registry()
    return {"success": True, "modules": registry.list_for_frontend()}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str = ApiPath(...), db: Session = Depends(get_db)):
    """Get a single job."""
    svc = JobService(db)
    job = svc.get_job_or_404(job_id)
    return {"success": True, "job": job}


@router.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(job_id: str = ApiPath(...), db: Session = Depends(get_db)):
    """Get normalized job result outputs with envelope-aware aggregation.

    Priority order:
    1. Envelope ``outputs`` array from the standard worker result envelope
    2. Legacy ``viewer_url`` / ``zip_url`` keys (backward compat)
    3. Registered ``project_assets`` rows linked to this job
    """
    from ..services.asset_service import AssetService

    svc = JobService(db)
    job = svc.get_job_or_404(job_id)
    raw_job_result = job.get("result") if isinstance(job.get("result"), dict) else {}
    job_result = _unwrap_result_payload(raw_job_result)

    outputs: list[dict] = []
    seen_outputs: set[str] = set()
    seen_ids: set[str] = set()
    module_label = _result_module_label(job_result, job.get("module", "Result"))

    # ── 1. Envelope outputs (B2 standard format) ──────────────────
    envelope_outputs = job_result.get("outputs")
    if isinstance(envelope_outputs, list):
        for entry in envelope_outputs:
            if not isinstance(entry, dict):
                continue
            asset_id = str(entry.get("asset_id") or "")
            if asset_id and asset_id in seen_ids:
                continue
            if asset_id:
                seen_ids.add(asset_id)
            _append_output(
                outputs,
                seen_outputs,
                label=str(entry.get("label", "")),
                url=str(entry.get("url", "")),
                kind=str(entry.get("kind", "data")),
                module=str(entry.get("module") or module_label),
                category=str(entry.get("category") or ""),
                download_url=str(entry.get("download_url") or ""),
                asset_id=asset_id,
            )

    # ── 2. Legacy viewer_url / zip_url (backward compat) ─────────
    for key in ["viewer_url", "zip_url", "metadata_url"]:
        url = str(job_result.get(key, ""))
        _append_output(
            outputs,
            seen_outputs,
            label=key.replace("_url", "").title(),
            url=url,
            kind="html" if key == "viewer_url" else ("zip" if key == "zip_url" else "json"),
            module=module_label,
            category="Viewer" if key == "viewer_url" else ("Archive" if key == "zip_url" else "Metadata"),
            download_url=url if key == "zip_url" else "",
        )

    chart_results = job_result.get("chart_results") or []
    if isinstance(chart_results, list) and chart_results:
        for item in chart_results:
            if not isinstance(item, dict):
                continue
            child_module = str(item.get("label") or item.get("module") or item.get("name") or item.get("key") or module_label)
            _append_output(
                outputs,
                seen_outputs,
                label=f"{child_module} viewer",
                url=str(item.get("viewer_url") or ""),
                kind="html",
                module=child_module,
                category="Viewer",
            )
            _append_output(
                outputs,
                seen_outputs,
                label=f"{child_module} bundle",
                url=str(item.get("zip_url") or ""),
                kind="zip",
                module=child_module,
                category="Archive",
                download_url=str(item.get("zip_url") or ""),
            )
            _append_output(
                outputs,
                seen_outputs,
                label=f"{child_module} metadata",
                url=str(item.get("metadata_url") or ""),
                kind="json",
                module=child_module,
                category="Metadata",
            )

    for key, category in [("png_urls", "Plots"), ("plot_urls", "Plots"), ("plot_heatmap_urls", "Heatmaps")]:
        values = job_result.get(key)
        if not isinstance(values, list):
            continue
        for index, url in enumerate(values, start=1):
            _append_output(
                outputs,
                seen_outputs,
                label=f"{category} {index}",
                url=str(url or ""),
                kind="image",
                module=module_label,
                category=category,
            )

    # ── 3. Registered project_assets linked to this job ──────────
    project_id = job.get("project_id") or ""
    assets = []
    if project_id:
        asset_svc = AssetService(db)
        try:
            all_results = asset_svc.find_project_results(project_id)
        except Exception:
            logger.warning(
                "Failed to query result assets for job %s; returning viewer outputs without registered assets.",
                job_id,
                exc_info=True,
            )
            all_results = []
        for ar in all_results:
            meta = ar.get("metadata", {})
            asset_job_id = str(meta.get("job_id", "")) if isinstance(meta, dict) else ""
            ar_id = str(ar.get("id", ""))

            if asset_job_id == job_id or ar_id == job_id:
                preview_url = f"/api/assets/{ar_id}/preview"
                download_url = f"/api/assets/{ar_id}/download"

                # Also add to outputs if not already present
                if ar_id not in seen_ids:
                    seen_ids.add(ar_id)
                    _append_output(
                        outputs,
                        seen_outputs,
                        label=str(ar.get("original_name", "")),
                        url=preview_url,
                        kind=_kind_from_mime(ar.get("mime_type", "")),
                        module=module_label,
                        category="Registered Asset",
                        download_url=download_url,
                        asset_id=ar_id,
                    )

                assets.append({
                    "id": ar_id,
                    "project_id": project_id,
                    "asset_type": str(ar.get("asset_type", "")),
                    "original_name": str(ar.get("original_name", "")),
                    "storage_path": str(ar.get("storage_path", "")),
                    "size": int(ar.get("size", 0)),
                    "preview_url": preview_url,
                    "download_url": download_url,
                })

    return {
        "success": True,
        "job": job,
        "status": job["status"],
        "result": job_result,
        "outputs": outputs,
        "assets": assets,
    }


def _append_output(
    outputs: list[dict],
    seen: set[str],
    *,
    label: str,
    url: str,
    kind: str,
    module: str,
    category: str = "",
    download_url: str = "",
    asset_id: str = "",
) -> None:
    url = str(url or "").strip()
    download_url = str(download_url or "").strip()
    raw_identity = url or download_url or str(asset_id or "").strip()
    if not raw_identity:
        return
    identity = f"{module or ''}:{raw_identity}"
    if identity in seen:
        return
    seen.add(identity)
    kind = str(kind or _kind_from_url(identity)).strip().lower()
    outputs.append({
        "label": label,
        "url": url or download_url,
        "kind": kind,
        "module": str(module or "Result"),
        "category": str(category or _default_output_category(kind)),
        "download_url": download_url or (url if kind == "zip" else ""),
        "asset_id": str(asset_id or "").strip() or None,
    })


def _unwrap_result_payload(result: dict) -> dict:
    """Return the actual analysis result from a worker envelope if present."""
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    if isinstance(data, dict) and (
        data.get("viewer_url")
        or data.get("zip_url")
        or data.get("chart_results")
        or data.get("outputs")
        or data.get("files")
    ):
        return data
    return result


def _result_module_label(result: dict, fallback: str) -> str:
    return str(
        result.get("label")
        or result.get("module")
        or result.get("payload_module")
        or result.get("analysis_type")
        or fallback
        or "Result"
    )


def _kind_from_url(url: str) -> str:
    lower = str(url or "").split("?", 1)[0].lower()
    if lower.endswith((".html", ".htm")):
        return "html"
    if lower.endswith((".png", ".jpg", ".jpeg", ".svg", ".webp")):
        return "image"
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".csv", ".tsv", ".xlsx", ".xls")):
        return "csv"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith((".ppt", ".pptx")):
        return "ppt"
    return "data"


def _default_output_category(kind: str) -> str:
    kind = str(kind or "").lower()
    if kind == "zip":
        return "Archive"
    if kind == "html":
        return "Viewer"
    if kind in {"png", "image"}:
        return "Plots"
    if kind == "json":
        return "Metadata"
    return kind.upper() if kind else "File"


def _kind_from_mime(mime_type: str) -> str:
    """Infer output kind from a MIME type string."""
    if not mime_type:
        return "data"
    mime = mime_type.lower()
    if "html" in mime:
        return "html"
    if "image" in mime or "png" in mime or "jpeg" in mime:
        return "image"
    if "csv" in mime or "excel" in mime:
        return "csv"
    if "zip" in mime:
        return "zip"
    if "pdf" in mime:
        return "pdf"
    if "json" in mime:
        return "json"
    if "powerpoint" in mime or "presentation" in mime:
        return "ppt"
    return "data"


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str = ApiPath(...), db: Session = Depends(get_db)):
    """Request job cancellation."""
    svc = JobService(db)
    job = svc.cancel_job(job_id)
    return {"success": True, "job": job}


@router.post("/jobs/bulk-delete")
async def bulk_delete_jobs(body: BulkDeleteJobsRequest, db: Session = Depends(get_db)):
    """Delete multiple terminal jobs, optionally including attached results."""
    svc = JobService(db)
    results = svc.bulk_delete_jobs(body.job_ids, delete_results=body.delete_results)
    return {"success": True, "results": results}


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str = ApiPath(...),
    delete_results: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Delete a job (terminal jobs only)."""
    svc = JobService(db)
    summary = svc.delete_job_with_results(job_id, delete_results=delete_results)
    return {"success": True, **summary}


@router.get("/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str = ApiPath(...),
    interval: float = Query(1.0, ge=0.2, le=30.0),
    max_events: int = Query(300, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Stream job lifecycle events via Server-Sent Events.

    Emits "update" events on each poll cycle and a terminal "completed"
    event when the job reaches a final status. The stream closes
    automatically when the job is terminal.
    """
    terminal_statuses = {"completed", "failed", "cancelled", "interrupted"}

    async def event_generator():
        last_payload = ""
        sent_events = 0

        while sent_events < max_events:
            svc = JobService(db)
            job_data = svc.get_job(job_id)
            if job_data is None:
                yield _sse_message("error", json.dumps({
                    "success": False,
                    "error": "JOB_NOT_FOUND",
                    "message": "Job not found",
                }))
                break

            status = job_data.get("status", "")
            event_name = "completed" if status in terminal_statuses else "update"
            payload = json.dumps(
                {"success": True, "job": job_data, "status": status},
                default=str,
                ensure_ascii=False,
            )

            if payload != last_payload:
                yield _sse_message(event_name, payload)
                last_payload = payload
                sent_events += 1
            else:
                yield _sse_comment("heartbeat")

            if status in terminal_statuses:
                break

            await asyncio.sleep(interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _sse_message(event: str, data: str) -> str:
    """Format an SSE message with optional event type."""
    parts = []
    if event:
        parts.append(f"event: {event}")
    for line in data.splitlines() or [""]:
        parts.append(f"data: {line}")
    return "\n".join(parts) + "\n\n"


def _sse_comment(value: str) -> str:
    """Format an SSE comment (invisible to client, keeps connection alive)."""
    return f": {value}\n\n"
