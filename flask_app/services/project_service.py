"""
Project domain service.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from flask_app.exceptions import ValidationError
from flask_app.models.database import Project, db
from flask_app.services.user_scope import assert_owned, current_user_id, is_admin, scope_query


class ProjectService:
    """CRUD helpers for business projects."""

    def __init__(self, projects_root: Path):
        self.projects_root = Path(projects_root).resolve()
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def list_projects(
        self,
        *,
        name: str = "",
        institution: str = "",
        cooperation_level: str = "",
    ) -> List[Project]:
        query = scope_query(Project.query, Project).order_by(Project.created_at.desc())
        if name:
            query = query.filter(Project.name.ilike(f"%{name.strip()}%"))
        if institution:
            query = query.filter(Project.institution.ilike(f"%{institution.strip()}%"))
        if cooperation_level:
            query = query.filter(Project.cooperation_level.ilike(f"%{cooperation_level.strip()}%"))
        return query.all()

    def get_project(self, project_id: str) -> Project:
        project = Project.query.get(project_id)
        if project is None:
            raise ValidationError(message="Project not found", details={'project_id': project_id})
        assert_owned(project, "Project")
        return project

    def create_project(
        self,
        *,
        name: str,
        institution: str = "",
        cooperation_level: str = "",
        description: str = "",
        status: str = "active",
    ) -> Project:
        project_name = str(name or "").strip()
        if not project_name:
            raise ValidationError(message="Project name is required", details={'field': 'name'})

        existing_query = Project.query.filter(Project.name == project_name)
        if not is_admin():
            existing_query = existing_query.filter(Project.user_id == current_user_id())
        existing = existing_query.first()
        if existing is not None:
            raise ValidationError(message="Project name already exists", details={'field': 'name', 'value': project_name})

        project = Project(
            name=project_name,
            user_id=current_user_id(),
            institution=str(institution or "").strip() or None,
            cooperation_level=str(cooperation_level or "").strip() or None,
            description=str(description or "").strip() or None,
            status=str(status or "active").strip() or "active",
        )
        db.session.add(project)
        db.session.commit()
        self.get_project_dir(project).mkdir(parents=True, exist_ok=True)
        return project

    def update_project(self, project: Project, payload: dict) -> Project:
        name = str(payload.get('name') or project.name).strip()
        if not name:
            raise ValidationError(message="Project name is required", details={'field': 'name'})
        if name != project.name:
            existing_query = Project.query.filter(Project.name == name, Project.id != project.id)
            if not is_admin():
                existing_query = existing_query.filter(Project.user_id == current_user_id())
            existing = existing_query.first()
            if existing is not None:
                raise ValidationError(message="Project name already exists", details={'field': 'name', 'value': name})
            project.name = name

        project.institution = str(payload.get('institution') or '').strip() or None
        project.cooperation_level = str(payload.get('cooperation_level') or '').strip() or None
        project.description = str(payload.get('description') or '').strip() or None
        project.status = str(payload.get('status') or project.status or 'active').strip() or 'active'
        db.session.commit()
        return project

    def delete_project(self, project: Project) -> None:
        project_dir = self.get_project_dir(project)
        db.session.delete(project)
        db.session.commit()
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)

    def get_project_dir(self, project: Project) -> Path:
        owner = str(project.user_id) if project.user_id else "legacy"
        return self.projects_root / owner / project.id

    def get_asset_type_dir(self, project: Project, asset_type: str) -> Path:
        return self.get_project_dir(project) / 'assets' / asset_type


_project_service: Optional[ProjectService] = None


def get_project_service(projects_root: Path) -> ProjectService:
    global _project_service
    resolved = Path(projects_root).resolve()
    if _project_service is None or _project_service.projects_root != resolved:
        _project_service = ProjectService(resolved)
    return _project_service
