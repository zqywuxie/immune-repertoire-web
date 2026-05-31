"""
Project group specification service.
"""

from __future__ import annotations

from typing import Any, Dict, List

from flask_app.exceptions import ValidationError
from flask_app.models.database import Project, ProjectGroupSpec, db


class GroupSpecService:
    """Save and retrieve project group specifications."""

    def list_specs(self, project_id: str) -> List[ProjectGroupSpec]:
        return ProjectGroupSpec.query.filter(
            ProjectGroupSpec.project_id == project_id
        ).order_by(ProjectGroupSpec.updated_at.desc()).all()

    def save_spec(
        self,
        project: Project,
        *,
        name: str,
        spec_json: Dict[str, Any],
        replace_existing: bool = True,
    ) -> ProjectGroupSpec:
        spec_name = str(name or 'default').strip() or 'default'
        if not isinstance(spec_json, dict) or not spec_json:
            raise ValidationError(message="Group specification cannot be empty", details={'field': 'spec_json'})

        if replace_existing:
            existing = ProjectGroupSpec.query.filter(
                ProjectGroupSpec.project_id == project.id,
                ProjectGroupSpec.name == spec_name,
            ).first()
            if existing is not None:
                existing.spec_json = spec_json
                db.session.commit()
                return existing

        spec = ProjectGroupSpec(
            project_id=project.id,
            name=spec_name,
            spec_json=spec_json,
        )
        db.session.add(spec)
        db.session.commit()
        return spec

    def delete_spec(self, spec_id: str) -> None:
        spec = ProjectGroupSpec.query.get(spec_id)
        if spec is None:
            raise ValidationError(message="Group specification not found", details={'group_spec_id': spec_id})
        db.session.delete(spec)
        db.session.commit()


_group_spec_service = GroupSpecService()


def get_group_spec_service() -> GroupSpecService:
    return _group_spec_service
