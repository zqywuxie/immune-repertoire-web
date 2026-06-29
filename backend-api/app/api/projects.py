from fastapi import APIRouter, Path, Query
from typing import Optional

from ..schemas.domain import (
    ProjectListResponse,
    ProjectDetail,
    ProjectCreate,
    ProjectUpdate,
)

router = APIRouter(tags=["Projects"])


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    name: Optional[str] = Query(None),
    institution: Optional[str] = Query(None),
    cooperation_level: Optional[str] = Query(None),
):
    """List projects for the current user."""
    # TODO: Phase 5 — replace with actual DB queries
    return {"projects": []}


@router.post("/projects", response_model=ProjectDetail, status_code=201)
async def create_project(body: ProjectCreate):
    """Create a project."""
    # TODO: Phase 5
    raise NotImplementedError


@router.get("/projects/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str = Path(...)):
    """Get project detail."""
    # TODO: Phase 5
    raise NotImplementedError


@router.patch("/projects/{project_id}", response_model=ProjectDetail)
async def update_project(project_id: str = Path(...), body: ProjectUpdate = None):
    """Update a project."""
    # TODO: Phase 5
    raise NotImplementedError
