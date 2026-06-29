"""Asset API — Phase 5 implementation."""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..schemas.domain import Asset, AssetListResponse, AssetUploadResponse, Pagination

router = APIRouter(tags=["Assets"])

_COL = {
    "id": 0, "project_id": 1, "asset_type": 2, "original_name": 3,
    "storage_path": 4, "mime_type": 5, "size": 6, "metadata_json": 7, "uploaded_at": 8,
}


def _to_asset(row, *, project_id: Optional[str] = None) -> dict:
    def col(key, default=None):
        try:
            return row[_COL[key]]
        except (IndexError, KeyError):
            return default

    metadata_val = col("metadata_json") or {}

    return {
        "id": col("id", ""),
        "project_id": project_id or col("project_id", ""),
        "asset_type": col("asset_type", ""),
        "original_name": col("original_name", ""),
        "storage_path": col("storage_path", ""),
        "storage_uri": metadata_val.get("storage_uri") if isinstance(metadata_val, dict) else None,
        "mime_type": col("mime_type"),
        "size": col("size", 0),
        "metadata": metadata_val if isinstance(metadata_val, dict) else {},
        "uploaded_at": col("uploaded_at"),
    }


@router.get("/projects/{project_id}/assets", response_model=AssetListResponse)
async def list_project_assets(
    project_id: str = Path(...),
    asset_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List project assets (paginated)."""
    conditions = ["project_id = :project_id"]
    params: dict = {"project_id": project_id}

    if asset_type:
        conditions.append("asset_type = :asset_type")
        params["asset_type"] = asset_type

    count_sql = f"SELECT COUNT(*) FROM project_assets WHERE {' AND '.join(conditions)}"
    total = db.execute(text(count_sql), params).fetchone()[0]

    offset = (page - 1) * page_size
    sql = (
        f"SELECT * FROM project_assets WHERE {' AND '.join(conditions)} "
        "ORDER BY uploaded_at DESC LIMIT :limit OFFSET :offset"
    )
    params.update({"limit": page_size, "offset": offset})
    rows = db.execute(text(sql), params).fetchall()

    return {
        "assets": [_to_asset(r, project_id=project_id) for r in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        },
    }


@router.post("/projects/{project_id}/assets", response_model=AssetUploadResponse, status_code=201)
async def upload_project_assets(
    project_id: str = Path(...),
    asset_type: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Upload project assets — proxied to Flask for now."""
    # File upload handling requires Flask's multipart processing.
    # The FastAPI phase keeps this as a forward proxy until Phase 5 completion.
    raise HTTPException(
        status_code=501,
        detail="Asset upload is still served by Flask. Use /api/projects/{project_id}/assets on Flask.",
    )


@router.get("/assets/{asset_id}/preview")
async def preview_asset(asset_id: str = Path(...), db: Session = Depends(get_db)):
    """Preview an asset (stable global route)."""
    result = db.execute(text("SELECT * FROM project_assets WHERE id = :id"), {"id": asset_id})
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    from flask_app.services.storage_adapter import get_storage_adapter

    asset = _to_asset(row)
    storage = get_storage_adapter()
    try:
        path = storage.get_file(asset.get("storage_uri") or asset["storage_path"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Asset file not available")

    media_type = asset.get("mime_type") or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=asset["original_name"])


@router.get("/assets/{asset_id}/download")
async def download_asset(asset_id: str = Path(...), db: Session = Depends(get_db)):
    """Download an asset (stable global route)."""
    result = db.execute(text("SELECT * FROM project_assets WHERE id = :id"), {"id": asset_id})
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    from flask_app.services.storage_adapter import get_storage_adapter

    asset = _to_asset(row)
    storage = get_storage_adapter()
    try:
        path = storage.get_file(asset.get("storage_uri") or asset["storage_path"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Asset file not available")

    return FileResponse(
        path,
        media_type=asset.get("mime_type") or "application/octet-stream",
        filename=asset["original_name"],
        headers={"Content-Disposition": f'attachment; filename="{asset["original_name"]}"'},
    )
