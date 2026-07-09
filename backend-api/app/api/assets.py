"""Asset API — Phase 5 implementation with repository layer."""

from pathlib import Path as FsPath
from typing import Optional

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..core.auth import require_current_user
from ..core.database import get_db
from ..schemas.domain import AssetListResponse, AssetUploadResponse, Pagination
from ..services.asset_service import AssetService

router = APIRouter(tags=["Assets"], dependencies=[Depends(require_current_user)])


class AssetMetadataUpdate(BaseModel):
    metadata_json: dict = Field(default_factory=dict)


class AssetPathRegister(BaseModel):
    asset_type: str
    storage_path: str
    original_name: Optional[str] = None
    metadata_json: dict = Field(default_factory=dict)


@router.get("/projects/{project_id}/assets", response_model=AssetListResponse)
async def list_project_assets(
    project_id: str = Path(...),
    asset_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List project assets (paginated)."""
    svc = AssetService(db)
    assets, total = svc.list_assets(
        project_id, asset_type=asset_type, page=page, page_size=page_size
    )
    return {
        "assets": assets,
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
    asset_set: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload project assets with storage_uri generation."""
    import json
    import os
    import uuid
    import mimetypes
    from datetime import datetime, timezone
    from pathlib import Path as FilePath

    try:
        paths = json.loads(relative_paths) if relative_paths else []
    except json.JSONDecodeError:
        paths = []

    if not isinstance(paths, list):
        paths = []

    uploaded: list[dict] = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    replace = replace_existing.lower() in ("true", "1", "yes")

    storage_root = os.environ.get("STORAGE_ROOT", "")
    base_dir = FilePath(storage_root) if storage_root else FilePath("flask_app/data/projects")
    project_dir = base_dir / project_id / "assets" / asset_type
    project_dir.mkdir(parents=True, exist_ok=True)

    svc = AssetService(db)

    for idx, file in enumerate(files):
        asset_id = str(uuid.uuid4())
        content = await file.read()
        if not content:
            continue

        rel_path = paths[idx] if idx < len(paths) else ""
        if rel_path:
            safe_name = rel_path.replace("\\", "/").split("/")[-1] or (file.filename or f"upload_{idx}")
        else:
            safe_name = file.filename or f"upload_{idx}"

        target_path = project_dir / safe_name
        if replace and target_path.exists():
            target_path.unlink()

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        file_size = len(content)

        storage_uri = f"local:///{target_path.resolve().as_posix()}"
        mime_type, _ = mimetypes.guess_type(safe_name)

        metadata = {"storage_uri": storage_uri}
        if asset_set:
            metadata.update({"asset_set": asset_set, "group_label": asset_set})

        asset_data = {
            "id": asset_id,
            "project_id": project_id,
            "asset_type": asset_type,
            "original_name": safe_name,
            "storage_path": str(target_path),
            "mime_type": mime_type,
            "size": file_size,
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
            "uploaded_at": now,
        }

        created = svc.create_asset(asset_data)
        uploaded.append(created)

    return {"assets": uploaded}


@router.post("/projects/{project_id}/assets/register", response_model=AssetUploadResponse, status_code=201)
async def register_project_asset_path(
    body: AssetPathRegister,
    project_id: str = Path(...),
    db: Session = Depends(get_db),
):
    """Register an existing server-side asset path without uploading bytes."""
    import json
    import mimetypes
    import os
    import uuid
    from datetime import datetime, timezone

    path = os.path.abspath(body.storage_path)
    original_name = body.original_name or os.path.basename(path) or body.asset_type
    storage_uri = body.metadata_json.get("storage_uri") or f"local:///{path.replace(os.sep, '/')}"
    metadata = dict(body.metadata_json or {})
    metadata["storage_uri"] = storage_uri

    mime_type, _ = mimetypes.guess_type(original_name)
    size = os.path.getsize(path) if os.path.exists(path) and os.path.isfile(path) else 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    svc = AssetService(db)
    asset = svc.create_asset({
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "asset_type": body.asset_type,
        "original_name": original_name,
        "storage_path": path,
        "mime_type": mime_type,
        "size": size,
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
        "uploaded_at": now,
    })
    return {"assets": [asset]}


@router.patch("/projects/{project_id}/assets/{asset_id}")
async def update_project_asset(
    body: AssetMetadataUpdate,
    project_id: str = Path(...),
    asset_id: str = Path(...),
    db: Session = Depends(get_db),
):
    """Update asset metadata, including asset_set assignment."""
    svc = AssetService(db)
    asset = svc.get_asset_or_404(asset_id)
    if str(asset.get("project_id")) != str(project_id):
        raise HTTPException(status_code=404, detail="Asset not found in project")
    metadata = dict(asset.get("metadata") or {})
    metadata.update(body.metadata_json or {})
    updated = svc.update_asset_metadata(asset_id, metadata)
    return {"success": True, "asset": updated}


@router.patch("/assets/{asset_id}")
async def update_asset_metadata(
    body: AssetMetadataUpdate,
    asset_id: str = Path(...),
    db: Session = Depends(get_db),
):
    """Update asset metadata through the stable global asset route."""
    svc = AssetService(db)
    asset = svc.get_asset_or_404(asset_id)
    metadata = dict(asset.get("metadata") or {})
    metadata.update(body.metadata_json or {})
    updated = svc.update_asset_metadata(asset_id, metadata)
    return {"success": True, "asset": updated}


@router.get("/assets/{asset_id}/preview")
async def preview_asset(asset_id: str = Path(...), db: Session = Depends(get_db)):
    """Preview an asset (stable global route)."""
    svc = AssetService(db)
    asset = svc.get_asset_or_404(asset_id)
    redirect_url = _result_redirect_url(asset, preview=True)
    if redirect_url:
        return RedirectResponse(redirect_url)
    path = svc.resolve_asset_file(asset)
    if path is None:
        raise HTTPException(status_code=404, detail="Asset file not available")
    path = _preview_target(path)
    media_type = asset.get("mime_type") or "application/octet-stream"
    return FileResponse(path, media_type=_media_type_for_path(path, media_type), filename=path.name, content_disposition_type="inline")


@router.get("/assets/{asset_id}/download")
async def download_asset(asset_id: str = Path(...), db: Session = Depends(get_db)):
    """Download an asset (stable global route)."""
    svc = AssetService(db)
    asset = svc.get_asset_or_404(asset_id)
    redirect_url = _result_redirect_url(asset, preview=False)
    if redirect_url:
        return RedirectResponse(redirect_url)
    path = svc.resolve_asset_file(asset)
    if path is None:
        raise HTTPException(status_code=404, detail="Asset file not available")
    path = _download_target(path)
    return FileResponse(
        path,
        media_type=_media_type_for_path(path, asset.get("mime_type") or "application/octet-stream"),
        filename=path.name or asset["original_name"],
        headers={"Content-Disposition": f'attachment; filename="{path.name or asset["original_name"]}"'},
    )


def _result_redirect_url(asset: dict, *, preview: bool) -> str:
    """Prefer canonical result URLs for processed_result assets.

    Serving a generated ``viewer.html`` through ``/api/assets/{id}/preview`` can
    break relative image/script links. The result metadata already stores the
    canonical viewer and ZIP routes, so use them when available.
    """
    if str(asset.get("asset_type") or "") != "processed_result":
        return ""
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    keys = ("viewer_url", "report_url") if preview else ("zip_url",)
    for key in keys:
        url = str(metadata.get(key) or "").strip()
        if url:
            return url
    return ""


def _preview_target(path: FsPath) -> FsPath:
    if path.is_file():
        return path
    for name in ("viewer.html", "index.html", "report.html", "metadata.html"):
        candidate = path / name
        if candidate.is_file():
            return candidate
    for pattern in ("*.html", "*.htm", "*.png", "*.jpg", "*.jpeg", "*.pdf", "*.csv", "*.json"):
        candidate = next(path.glob(pattern), None)
        if candidate and candidate.is_file():
            return candidate
    raise HTTPException(status_code=404, detail="No previewable result file found")


def _download_target(path: FsPath) -> FsPath:
    if path.is_file():
        return path
    preferred = [
        "results.zip",
        "script_hub_results.zip",
        "pep_analysis_results.zip",
        "boxplot_results.zip",
        "topclone_results.zip",
        "ml_analysis_results.zip",
        "mait_nkt_results.zip",
    ]
    for name in preferred:
        candidate = path / name
        if candidate.is_file():
            return candidate
    candidate = next(path.glob("*.zip"), None)
    if candidate and candidate.is_file():
        return candidate
    raise HTTPException(status_code=404, detail="No downloadable result archive found")


def _media_type_for_path(path: FsPath, fallback: str) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return "text/html; charset=utf-8"
    if suffix == ".json":
        return "application/json"
    if suffix == ".csv":
        return "text/csv; charset=utf-8"
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".zip":
        return "application/zip"
    return fallback or "application/octet-stream"
