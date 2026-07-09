"""Project CRUD API — Phase 5 implementation with repository layer."""

from datetime import datetime
from pathlib import Path as FsPath
from typing import Optional

from fastapi import BackgroundTasks
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import FileResponse
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
from ..services.project_service import ProjectService
from ..services.asset_service import AssetService
from ..services.project_export_service import ProjectExportService

router = APIRouter(tags=["Projects"], dependencies=[Depends(require_current_user)])


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    name: Optional[str] = Query(None),
    institution: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List projects with optional name / institution filters."""
    svc = ProjectService(db)
    rows = svc.list_projects(name=name, institution=institution)
    return {"projects": rows}


@router.post("/projects", response_model=ProjectSummary, status_code=201)
async def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new project."""
    import uuid

    svc = ProjectService(db)
    now = datetime.utcnow().isoformat()

    return svc.create_project({
        "id": str(uuid.uuid4()),
        "name": body.name,
        "user_id": None,
        "institution": body.institution,
        "cooperation_level": body.cooperation_level,
        "description": body.description,
        "status": body.status or "active",
        "created_at": now,
        "updated_at": now,
    })


@router.get("/projects/{project_id}", response_model=ProjectSummary)
async def get_project(project_id: str = Path(...), db: Session = Depends(get_db)):
    """Get a single project by ID."""
    svc = ProjectService(db)
    return svc.get_project_or_404(project_id)


@router.patch("/projects/{project_id}", response_model=ProjectSummary)
async def update_project(
    project_id: str = Path(...),
    body: Optional[ProjectUpdate] = None,
    db: Session = Depends(get_db),
):
    """Update a project (partial update)."""
    if body is None:
        raise HTTPException(status_code=400, detail="Request body is required")

    svc = ProjectService(db)
    svc.get_project_or_404(project_id)  # validate existence

    updates = body.model_dump(exclude_none=True)
    if not updates:
        return svc.get_project(project_id)

    return svc.update_project(project_id, updates)


@router.get("/projects/{project_id}/results")
async def list_project_results(
    project_id: str = Path(...),
    analysis_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List reusable project analysis results."""
    svc = AssetService(db)
    assets = svc.find_project_results(project_id, analysis_type=analysis_type)
    for a in assets:
        metadata = a.get("metadata") if isinstance(a.get("metadata"), dict) else {}
        viewer_url = str(metadata.get("viewer_url") or metadata.get("report_url") or "").strip()
        zip_url = str(metadata.get("zip_url") or "").strip()
        a["preview_url"] = viewer_url or f"/api/assets/{a['id']}/preview"
        a["download_url"] = zip_url or f"/api/assets/{a['id']}/download"
    return {"success": True, "results": assets}


@router.get("/projects/{project_id}/export")
async def export_project(
    background_tasks: BackgroundTasks,
    project_id: str = Path(...),
    include_assets: bool = Query(True),
    include_results: bool = Query(True),
    include_group_specs: bool = Query(True),
    include_manifest: bool = Query(True),
    db: Session = Depends(get_db),
):
    """Export project assets/results/group specs as a ZIP bundle."""
    project = ProjectService(db).get_project_or_404(project_id)
    export_path = ProjectExportService(db).build_export_zip(
        project,
        include_assets=include_assets,
        include_results=include_results,
        include_group_specs=include_group_specs,
        include_manifest=include_manifest,
    )
    background_tasks.add_task(_remove_file, export_path)
    safe_name = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in project["name"]) or project_id
    return FileResponse(
        export_path,
        media_type="application/zip",
        filename=f"{safe_name}_export.zip",
        background=background_tasks,
    )


@router.get("/projects/{project_id}/group-specs")
async def list_project_group_specs(
    project_id: str = Path(...),
    db: Session = Depends(get_db),
):
    """List group specs for a project (ScriptHub module form support)."""
    rows = db.execute(
        text(
            "SELECT * FROM project_assets WHERE project_id = :pid "
            "AND asset_type = 'group_spec' ORDER BY uploaded_at DESC"
        ),
        {"pid": project_id},
    ).mappings().all()

    return {
        "group_specs": [
            {
                "id": str(r["id"]),
                "name": str(r.get("original_name", "")),
                "project_id": str(r.get("project_id", "")),
                "spec_json": r.get("metadata_json") if isinstance(r.get("metadata_json"), dict) else {},
            }
            for r in rows
        ]
    }


def _remove_file(path: FsPath) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
