from fastapi import APIRouter, Path, Query

from ..schemas.domain import (
    JobListResponse,
    JobModulesResponse,
    SubmitJobRequest,
    SubmitJobResponse,
    JobResultsResponse,
)

router = APIRouter(tags=["Jobs"])


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    project_id: str | None = Query(None),
    status: str | None = Query(None),
    module: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """List background jobs."""
    # TODO: Phase 5
    return {"jobs": []}


@router.post("/jobs", response_model=SubmitJobResponse)
async def submit_job(body: SubmitJobRequest):
    """Submit a unified background job."""
    # TODO: Phase 5
    raise NotImplementedError


@router.get("/jobs/modules", response_model=JobModulesResponse)
async def list_job_modules():
    """List frontend-visible job modules."""
    return {"modules": [{"key": "charts.combined", "label": "综合图表"}]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str = Path(...)):
    """Get a background job."""
    # TODO: Phase 5
    raise NotImplementedError


@router.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
async def get_job_results(job_id: str = Path(...)):
    """Get normalized job result outputs."""
    # TODO: Phase 5
    raise NotImplementedError


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str = Path(...)):
    """Request job cancellation."""
    # TODO: Phase 5
    raise NotImplementedError
