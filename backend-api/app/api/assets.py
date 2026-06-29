"""Asset API — Phase 5 implementation."""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.auth import require_current_user
from ..core.database import get_db
from ..schemas.domain import Asset, AssetListResponse, AssetUploadResponse, Pagination

router = APIRouter(tags=["Assets"], dependencies=[Depends(require_current_user)])

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
    replace_existing: str = Form("false"),
    relative_paths: str = Form("[]"),
    db: Session = Depends(get_db),
):
    """Upload project assets with storage_uri generation."""
    import json
    import os
    import uuid
    import mimetypes
    from datetime import datetime, timezone
    from pathlib import Path as FilePath

    # Parse relative paths
    try:
        paths = json.loads(relative_paths) if relative_paths else []
    except json.JSONDecodeError:
        paths = []

    if not isinstance(paths, list):
        paths = []

    uploaded: list[dict] = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    replace = replace_existing.lower() in ("true", "1", "yes")

    # Determine storage root from env or default
    storage_root = os.environ.get("STORAGE_ROOT", "")
    base_dir = FilePath(storage_root) if storage_root else FilePath("flask_app/data/projects")
    project_dir = base_dir / project_id / "assets" / asset_type
    project_dir.mkdir(parents=True, exist_ok=True)

    for idx, file in enumerate(files):
        asset_id = str(uuid.uuid4())
        content = await file.read()
        if not content:
            continue

        # Determine file name
        rel_path = paths[idx] if idx < len(paths) else ""
        if rel_path:
            safe_name = rel_path.replace("\\", "/").split("/")[-1] or (file.filename or f"upload_{idx}")
        else:
            safe_name = file.filename or f"upload_{idx}"

        # Resolve target path
        target_path = project_dir / safe_name

        # Replace existing if requested
        if replace and target_path.exists():
            target_path.unlink()

        # Write file
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        file_size = len(content)

        # Generate storage_uri (local:/// format, no Flask dependency)
        storage_uri = f"local:///{target_path.resolve().as_posix()}"

        # Guess mime type
        mime_type, _ = mimetypes.guess_type(safe_name)

        # Insert into DB
        db.execute(
            text(
                """INSERT INTO project_assets
                   (id, project_id, asset_type, original_name, storage_path, mime_type, size,
                    metadata_json, uploaded_at)
                   VALUES
                   (:id, :project_id, :asset_type, :original_name, :storage_path, :mime_type, :size,
                    :metadata_json, :uploaded_at)"""
            ),
            {
                "id": asset_id,
                "project_id": project_id,
                "asset_type": asset_type,
                "original_name": safe_name,
                "storage_path": str(target_path),
                "mime_type": mime_type,
                "size": file_size,
                "metadata_json": json.dumps({"storage_uri": storage_uri}),
                "uploaded_at": now,
            },
        )
        db.commit()

        uploaded.append({
            "id": asset_id,
            "project_id": project_id,
            "asset_type": asset_type,
            "original_name": safe_name,
            "storage_path": str(target_path),
            "storage_uri": storage_uri,
            "mime_type": mime_type,
            "size": file_size,
            "metadata": {"storage_uri": storage_uri},
            "uploaded_at": now.isoformat(),
        })

    return {"assets": uploaded}


@router.get("/assets/{asset_id}/preview")
async def preview_asset(asset_id: str = Path(...), db: Session = Depends(get_db)):
    """Preview an asset (stable global route)."""
    result = db.execute(text("SELECT * FROM project_assets WHERE id = :id"), {"id": asset_id})
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    from ..core.storage import get_storage_resolver

    asset = _to_asset(row)
    storage = get_storage_resolver()
    path = storage.resolve_asset_path(asset)
    if path is None:
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

    from ..core.storage import get_storage_resolver

    asset = _to_asset(row)
    storage = get_storage_resolver()
    path = storage.resolve_asset_path(asset)
    if path is None:
        raise HTTPException(status_code=404, detail="Asset file not available")

    return FileResponse(
        path,
        media_type=asset.get("mime_type") or "application/octet-stream",
        filename=asset["original_name"],
        headers={"Content-Disposition": f'attachment; filename="{asset["original_name"]}"'},
    )
