from fastapi import APIRouter, Path, Query, UploadFile, File, Form

from ..schemas.domain import AssetListResponse, AssetUploadResponse

router = APIRouter(tags=["Assets"])


@router.get("/projects/{project_id}/assets", response_model=AssetListResponse)
async def list_project_assets(
    project_id: str = Path(...),
    asset_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List project assets (paginated)."""
    # TODO: Phase 5
    return {"assets": [], "pagination": None}


@router.post("/projects/{project_id}/assets", response_model=AssetUploadResponse, status_code=201)
async def upload_project_assets(
    project_id: str = Path(...),
    asset_type: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Upload project assets."""
    # TODO: Phase 5
    return {"assets": []}


@router.get("/assets/{asset_id}/preview")
async def preview_asset(asset_id: str = Path(...)):
    """Preview an asset (stable global route)."""
    # TODO: Phase 5
    raise NotImplementedError


@router.get("/assets/{asset_id}/download")
async def download_asset(asset_id: str = Path(...)):
    """Download an asset (stable global route)."""
    # TODO: Phase 5
    raise NotImplementedError
