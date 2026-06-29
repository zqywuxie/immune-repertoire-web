"""Project CRUD API — Phase 5 implementation with raw SQL.

Uses raw SQL via SQLAlchemy text() to avoid ORM model import complexity
during the Flask → FastAPI transition. Each handler maps DB rows to the
Pydantic schemas defined in app/schemas/domain.py.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.auth import require_current_user
from ..core.database import get_db
from ..schemas.domain import (
    ProjectCreate,
    ProjectDetail,
    ProjectListResponse,
    ProjectSummary,
    ProjectUpdate,
)

router = APIRouter(tags=["Projects"], dependencies=[Depends(require_current_user)])

# DB column indices for SELECT * FROM projects
# Adjust these if your schema differs — check flask_app/models/database.py
_COL = {
    "id": 0,
    "name": 1,
    "user_id": 2,
    "institution": 3,
    "cooperation_level": 4,
    "description": 5,
    "status": 6,
    "created_at": 7,
    "updated_at": 8,
}


def _to_summary(row) -> dict:
    """Map a raw DB row to ProjectSummary fields."""
    def col(key, default=None):
        try:
            return row[_COL[key]]
        except (IndexError, KeyError):
            return default

    return {
        "id": col("id", ""),
        "name": col("name", ""),
        "user_id": col("user_id"),
        "institution": col("institution"),
        "cooperation_level": col("cooperation_level"),
        "description": col("description"),
        "status": col("status", "active"),
        "asset_counts": {},
        "sample_count": 0,
        "result_count": 0,
        "group_spec_count": 0,
        "created_at": col("created_at"),
        "updated_at": col("updated_at"),
    }


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    name: Optional[str] = Query(None),
    institution: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List projects with optional name / institution filters."""
    conditions = ["1=1"]
    params: dict = {}

    if name:
        conditions.append("name LIKE :name")
        params["name"] = f"%{name}%"
    if institution:
        conditions.append("institution LIKE :inst")
        params["inst"] = f"%{institution}%"

    sql = f"SELECT * FROM projects WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT 200"
    result = db.execute(text(sql), params)
    rows = result.fetchall()

    return {"projects": [_to_summary(r) for r in rows]}


@router.post("/projects", response_model=ProjectSummary, status_code=201)
async def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project."""
    import uuid

    project_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    sql = text(
        """INSERT INTO projects (id, name, institution, cooperation_level, description, status, created_at, updated_at)
           VALUES (:id, :name, :institution, :cooperation_level, :description, :status, :created_at, :updated_at)"""
    )
    db.execute(
        sql,
        {
            "id": project_id,
            "name": body.name,
            "institution": body.institution,
            "cooperation_level": body.cooperation_level,
            "description": body.description,
            "status": body.status or "active",
            "created_at": now,
            "updated_at": now,
        },
    )
    db.commit()

    return {
        "id": project_id,
        "name": body.name,
        "user_id": None,
        "institution": body.institution,
        "cooperation_level": body.cooperation_level,
        "description": body.description,
        "status": body.status or "active",
        "asset_counts": {},
        "sample_count": 0,
        "result_count": 0,
        "group_spec_count": 0,
        "created_at": now,
        "updated_at": now,
    }


@router.get("/projects/{project_id}", response_model=ProjectSummary)
async def get_project(project_id: str = Path(...), db: Session = Depends(get_db)):
    """Get a single project by ID."""
    result = db.execute(text("SELECT * FROM projects WHERE id = :id"), {"id": project_id})
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _to_summary(row)


@router.patch("/projects/{project_id}", response_model=ProjectSummary)
async def update_project(
    project_id: str = Path(...),
    body: Optional[ProjectUpdate] = None,
    db: Session = Depends(get_db),
):
    """Update a project (partial update)."""
    if body is None:
        raise HTTPException(status_code=400, detail="Request body is required")

    # Verify the project exists
    result = db.execute(text("SELECT * FROM projects WHERE id = :id"), {"id": project_id})
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Build SET clause from non-None fields
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return _to_summary(row)

    updates["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    sql = text(f"UPDATE projects SET {set_clause} WHERE id = :project_id")
    db.execute(sql, {**updates, "project_id": project_id})
    db.commit()

    # Return the updated row
    result = db.execute(text("SELECT * FROM projects WHERE id = :id"), {"id": project_id})
    return _to_summary(result.fetchone())


@router.get("/projects/{project_id}/results")
async def list_project_results(
    project_id: str = Path(...),
    analysis_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List reusable project analysis results."""
    conditions = ["project_id = :project_id", "asset_type = 'processed_result'"]
    params: dict = {"project_id": project_id}

    if analysis_type:
        conditions.append("JSON_EXTRACT(metadata_json, '$.analysis_type') = :analysis_type")
        params["analysis_type"] = analysis_type

    sql = f"SELECT * FROM project_assets WHERE {' AND '.join(conditions)} ORDER BY uploaded_at DESC LIMIT 100"
    rows = db.execute(text(sql), params).fetchall()

    from .assets import _to_asset

    results = []
    for row in rows:
        asset = _to_asset(row, project_id=project_id)
        asset["preview_url"] = f"/api/assets/{row[0]}/preview"
        asset["download_url"] = f"/api/assets/{row[0]}/download"
        results.append(asset)

    return {"success": True, "results": results}
