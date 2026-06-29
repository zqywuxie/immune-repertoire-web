"""Job API — Phase 5 implementation."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..schemas.domain import (
    JobListResponse,
    JobModulesResponse,
    JobResultsResponse,
    JobSummary,
    SubmitJobRequest,
    SubmitJobResponse,
)

router = APIRouter(tags=["Jobs"])


def _to_job(row) -> dict:
    """Map an analysis_jobs row to JobSummary fields."""
    try:
        return {
            "id": str(row[0]) if row[0] else "",
            "job_id": str(row[1]) if len(row) > 1 and row[1] else None,
            "job_type": str(row[2]) if len(row) > 2 and row[2] else "",
            "module": str(row[3]) if len(row) > 3 and row[3] else "",
            "status": str(row[4]) if len(row) > 4 and row[4] else "queued",
            "progress": float(row[5]) if len(row) > 5 and row[5] is not None else 0.0,
            "stage": str(row[6]) if len(row) > 6 and row[6] else None,
            "detail": str(row[7]) if len(row) > 7 and row[7] else None,
            "payload": row[8] if len(row) > 8 and isinstance(row[8], dict) else {},
            "result": row[9] if len(row) > 9 and isinstance(row[9], dict) else {},
            "error": str(row[10]) if len(row) > 10 and row[10] else None,
            "project_id": str(row[12]) if len(row) > 12 and row[12] else None,
            "user_id": row[13] if len(row) > 13 and row[13] is not None else None,
            "created_at": str(row[14]) if len(row) > 14 and row[14] else None,
            "updated_at": str(row[15]) if len(row) > 15 and row[15] else None,
            "started_at": str(row[16]) if len(row) > 16 and row[16] else None,
            "completed_at": str(row[17]) if len(row) > 17 and row[17] else None,
        }
    except (IndexError, TypeError):
        return {
            "id": "", "job_type": "", "module": "", "status": "queued",
            "progress": 0.0, "payload": {}, "result": {},
        }


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List background jobs."""
    conditions = ["1=1"]
    params: dict = {}

    if project_id:
        conditions.append("project_id = :project_id")
        params["project_id"] = project_id
    if status:
        conditions.append("status = :status")
        params["status"] = status
    if module:
        conditions.append("module = :module")
        params["module"] = module

    sql = f"SELECT * FROM analysis_jobs WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = limit
    rows = db.execute(text(sql), params).fetchall()

    return {"jobs": [_to_job(r) for r in rows]}


@router.post("/jobs", response_model=SubmitJobResponse)
async def submit_job(body: SubmitJobRequest):
    """Submit a unified background job — proxied to Flask for now."""
    raise HTTPException(
        status_code=501,
        detail="Job submission is still served by Flask. Use POST /api/jobs on Flask.",
    )


@router.get("/jobs/modules", response_model=JobModulesResponse)
async def list_job_modules():
    """List frontend-visible job modules."""
    return {"modules": [{"key": "charts.combined", "label": "综合图表"}]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str = Path(...), db: Session = Depends(get_db)):
    """Get a single job."""
    result = db.execute(
        text("SELECT * FROM analysis_jobs WHERE job_id = :jid OR id = :jid"), {"jid": job_id}
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job": _to_job(row)}


@router.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(job_id: str = Path(...), db: Session = Depends(get_db)):
    """Get normalized job result outputs."""
    result = db.execute(
        text("SELECT * FROM analysis_jobs WHERE job_id = :jid OR id = :jid"), {"jid": job_id}
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _to_job(row)
    job_result = job.get("result") if isinstance(job.get("result"), dict) else {}

    # Collect outputs from result
    outputs = []
    seen_urls = set()
    for key in ["viewer_url", "zip_url"]:
        url = job_result.get(key, "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            outputs.append({
                "label": key.replace("_url", "").title(),
                "url": url,
                "kind": "html" if "viewer" in key else "zip",
            })

    # Find registered assets
    project_id = job.get("project_id") or ""
    assets = []
    if project_id:
        asset_rows = db.execute(
            text(
                "SELECT * FROM project_assets WHERE project_id = :pid "
                "AND asset_type = 'processed_result' ORDER BY uploaded_at DESC LIMIT 100"
            ),
            {"pid": project_id},
        ).fetchall()
        for ar in asset_rows:
            try:
                metadata_val = ar[7] if len(ar) > 7 else {}
                asset_job_id = metadata_val.get("job_id", "") if isinstance(metadata_val, dict) else ""
                if asset_job_id == job_id or str(ar[0]) == job_id:
                    assets.append({
                        "id": str(ar[0]),
                        "project_id": project_id,
                        "asset_type": str(ar[2]) if len(ar) > 2 else "",
                        "original_name": str(ar[3]) if len(ar) > 3 else "",
                        "storage_path": str(ar[4]) if len(ar) > 4 else "",
                        "size": int(ar[6]) if len(ar) > 6 else 0,
                        "preview_url": f"/api/assets/{ar[0]}/preview",
                        "download_url": f"/api/assets/{ar[0]}/download",
                    })
            except (IndexError, TypeError):
                continue

    return {
        "success": True,
        "job": job,
        "status": job["status"],
        "result": job_result,
        "outputs": outputs,
        "assets": assets,
    }


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str = Path(...), db: Session = Depends(get_db)):
    """Request job cancellation."""
    result = db.execute(
        text("SELECT * FROM analysis_jobs WHERE job_id = :jid OR id = :jid"), {"jid": job_id}
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")

    db.execute(
        text(
            "UPDATE analysis_jobs SET cancel_requested = 1, "
            "updated_at = NOW() WHERE job_id = :jid OR id = :jid"
        ),
        {"jid": job_id},
    )
    db.commit()

    return {"success": True, "job": _to_job(row)}
