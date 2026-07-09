"""AssetService — thin orchestration over AssetRepository + StorageResolver."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..core.storage import get_storage_resolver
from ..repositories.assets import AssetRepository


class AssetService:
    """Business logic for asset CRUD, preview, and download."""

    def __init__(self, db: Session) -> None:
        self.repo = AssetRepository(db)

    def list_assets(
        self,
        project_id: str,
        asset_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        return self.repo.list_by_project(
            project_id, asset_type=asset_type, page=page, page_size=page_size
        )

    def get_asset(self, asset_id: str) -> Optional[dict]:
        return self.repo.get_by_id(asset_id)

    def get_asset_or_404(self, asset_id: str) -> dict:
        asset = self.repo.get_by_id(asset_id)
        if asset is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Asset not found")
        return asset

    def create_asset(self, data: dict) -> dict:
        return self.repo.create(data)

    def update_asset_metadata(self, asset_id: str, metadata: dict) -> dict:
        updated = self.repo.update_metadata(asset_id, metadata)
        if updated is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Asset not found")
        return updated

    def delete_asset(self, asset_id: str) -> bool:
        return self.repo.delete(asset_id)

    def resolve_asset_file(self, asset: dict):
        """Return a filesystem Path for the asset, or None."""
        storage = get_storage_resolver()
        return storage.resolve_asset_path(asset)

    def find_project_results(
        self,
        project_id: str,
        analysis_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        return self.repo.find_by_project_and_type(
            project_id,
            asset_type="processed_result",
            analysis_type=analysis_type,
            limit=limit,
        )

    def list_all_project_assets(self, project_id: str, limit: int = 5000) -> list[dict]:
        return self.repo.list_all_by_project(project_id, limit=limit)

    def project_asset_counts(self, project_id: str) -> dict[str, int]:
        return self.repo.count_by_project_type(project_id)

    def project_asset_status(self, project_id: str) -> dict:
        counts = self.project_asset_counts(project_id)
        has_profile = bool(counts.get("profile") or counts.get("datapoint"))
        has_datapoint = bool(counts.get("datapoint") or counts.get("profile"))
        has_pep = bool(counts.get("pep"))
        has_sample_summary = bool(counts.get("sample_summary") or counts.get("sample"))
        has_group_spec = bool(counts.get("group_spec"))
        has_results = bool(counts.get("processed_result"))
        return {
            "has_profile": has_profile,
            "has_datapoint": has_datapoint,
            "has_pep": has_pep,
            "has_sample_summary": has_sample_summary,
            "has_group_spec": has_group_spec,
            "has_results": has_results,
            "asset_set_count": self.repo.asset_set_count(project_id),
        }
