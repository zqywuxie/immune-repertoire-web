"""ProjectService — thin orchestration over ProjectRepository."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..repositories.projects import ProjectRepository
from .asset_service import AssetService


class ProjectService:
    """Business logic for project CRUD.

    Currently delegates directly to the repository. Permission checks,
    caching, and cross-service orchestration will be added here in
    subsequent phases.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ProjectRepository(db)

    def list_projects(
        self,
        name: Optional[str] = None,
        institution: Optional[str] = None,
    ) -> list[dict]:
        return [self._enrich_project(row) for row in self.repo.list_all(name=name, institution=institution)]

    def get_project(self, project_id: str) -> Optional[dict]:
        project = self.repo.get_by_id(project_id)
        return self._enrich_project(project) if project else None

    def get_project_or_404(self, project_id: str) -> dict:
        project = self.get_project(project_id)
        if project is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    def create_project(self, data: dict) -> dict:
        created = self.repo.create(data)
        return self._enrich_project(created)

    def update_project(self, project_id: str, updates: dict) -> dict:
        updated = self.repo.update(project_id, updates)
        return self._enrich_project(updated) if updated else updated

    def _enrich_project(self, project: Optional[dict]) -> Optional[dict]:
        if not project:
            return project
        asset_svc = AssetService(self.db)
        counts = asset_svc.project_asset_counts(str(project["id"]))
        status = asset_svc.project_asset_status(str(project["id"]))
        enriched = dict(project)
        enriched["asset_counts"] = counts
        enriched["result_count"] = counts.get("processed_result", 0)
        enriched["group_spec_count"] = counts.get("group_spec", 0)
        enriched["asset_status"] = status
        return enriched
