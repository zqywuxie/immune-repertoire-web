"""
Project domain service.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from flask import current_app

from flask_app.exceptions import AnalysisInProgressError, StorageError, ValidationError
from flask_app.models.database import AnalysisJob, Project, ProjectAsset, db
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
            raise ValidationError(message="项目不存在或已移除。", details={'project_id': project_id})
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
            raise ValidationError(message="请填写项目名称。", details={'field': 'name'})

        existing_query = Project.query.filter(Project.name == project_name)
        existing_query = existing_query.filter(Project.user_id == current_user_id())
        existing = existing_query.first()
        if existing is not None:
            raise ValidationError(message="项目名称已存在，请使用其他名称。", details={'field': 'name', 'value': project_name})

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
            raise ValidationError(message="请填写项目名称。", details={'field': 'name'})
        if name != project.name:
            existing_query = Project.query.filter(Project.name == name, Project.id != project.id)
            existing_query = existing_query.filter(Project.user_id == current_user_id())
            existing = existing_query.first()
            if existing is not None:
                raise ValidationError(message="项目名称已存在，请使用其他名称。", details={'field': 'name', 'value': name})
            project.name = name

        project.institution = str(payload.get('institution') or '').strip() or None
        project.cooperation_level = str(payload.get('cooperation_level') or '').strip() or None
        project.description = str(payload.get('description') or '').strip() or None
        project.status = str(payload.get('status') or project.status or 'active').strip() or 'active'
        db.session.commit()
        return project

    def delete_project(self, project: Project) -> None:
        from flask_app.services.background_job_service import TERMINAL_STATUSES
        from flask_app.services.project_storage_paths import project_results_dir

        jobs = AnalysisJob.query.filter_by(project_id=project.id).all()
        active_jobs = [job for job in jobs if job.status not in TERMINAL_STATUSES]
        if active_jobs:
            raise AnalysisInProgressError(
                message="项目仍有未结束的分析任务，请等待任务结束后再删除。",
                details={"active_job_ids": [job.id for job in active_jobs]},
            )

        data_root = Path(current_app.config.get("PROJECT_DATA_ROOT") or self.projects_root).resolve()
        results_root = Path(current_app.config["RESULTS_FOLDER"]).resolve()
        project_dir = self.get_project_dir(project)
        results_dir = project_results_dir(project, results_root)
        from flask_app.services.project_storage_paths import managed_upload_boundary, managed_result_directory
        assets = ProjectAsset.query.filter_by(project_id=project.id).all()
        uploaded_files, run_directories = [], set()
        for asset in assets:
            if (asset.metadata_json or {}).get("managed_layout") == "user-time-v1":
                boundary = managed_upload_boundary(project, asset, self.projects_root)
                target = Path(asset.storage_path)
                if not target.is_symlink() and target.resolve().is_relative_to(boundary):
                    uploaded_files.append((target, boundary.parent.parent))
            metadata = asset.metadata_json or {}
            if asset.asset_type == "processed_result" and metadata.get("output_base"):
                directory = managed_result_directory(project, metadata["output_base"], results_root)
                if directory is not None:
                    run_directories.add(directory)
        for job in jobs:
            for path in (job.payload or {}).get("allocated_output_dirs") or []:
                directory = managed_result_directory(project, path, results_root)
                if directory is not None:
                    run_directories.add(directory)
        # Another project's imported inputs or reused results remain referenced.
        protected = []
        from flask_app.routes.api_jobs import _collect_result_paths
        for asset in ProjectAsset.query.filter(ProjectAsset.project_id != project.id).all():
            protected.extend([asset.storage_path, *_collect_result_paths(asset.metadata_json or {})])
        for job in AnalysisJob.query.filter(AnalysisJob.project_id != project.id).all():
            protected.extend(_collect_result_paths(job.result or {}))
            protected.extend(_collect_result_paths(job.payload or {}))
        protected = [Path(path).resolve() for path in protected if path]
        def referenced(path):
            path = Path(path).resolve()
            return any(path == other or path in other.parents or other in path.parents for other in protected)

        from flask_app.services.mongo_service import delete_project_records
        try:
            for job in jobs:
                db.session.delete(job)
            db.session.delete(project)
            db.session.flush()
            delete_project_records(project.id)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        if not referenced(project_dir):
            self._remove_managed_directory(project_dir, data_root)
        if not referenced(results_dir):
            self._remove_managed_directory(results_dir, results_root)
        for path, user_root in uploaded_files:
            if referenced(path):
                continue
            if path.is_file():
                path.unlink(missing_ok=True)
            self._prune_empty_parents(path.parent, user_root)
        for directory in sorted(run_directories, key=lambda path: len(path.parts), reverse=True):
            if not referenced(directory):
                self._remove_managed_directory(directory, results_root)
                self._prune_empty_parents(directory.parent, results_root / directory.relative_to(results_root).parts[0])

    @staticmethod
    def _prune_empty_parents(path, boundary):
        path, boundary = Path(path).resolve(), Path(boundary).resolve()
        while path != boundary and boundary in path.parents:
            try:
                path.rmdir()
            except OSError:
                break
            path = path.parent

    @staticmethod
    def _remove_managed_directory(path: Path, root: Path) -> None:
        root = Path(root).resolve()
        target = Path(path)
        if target.is_symlink():
            raise StorageError(message="项目目录不能是符号链接", details={"path": str(target)})
        resolved = target.resolve()
        if resolved == root or root not in resolved.parents:
            raise StorageError(message="拒绝删除存储根目录之外的数据", details={"path": str(target)})
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise StorageError(message="项目目录不在配置的数据根目录内") from exc

        current = root
        for segment in relative.parts:
            current = current / segment
            if current.is_symlink():
                raise StorageError(message="项目目录包含符号链接，已停止清理", details={"path": str(current)})
        if resolved.exists():
            shutil.rmtree(resolved)

    def get_project_dir(self, project: Project) -> Path:
        from flask_app.services.project_storage_paths import project_data_dir
        return project_data_dir(project, self.projects_root)

    def get_asset_type_dir(self, project: Project, asset_type: str) -> Path:
        return self.get_project_dir(project) / 'assets' / asset_type


_project_service: Optional[ProjectService] = None


def get_project_service(projects_root: Path) -> ProjectService:
    global _project_service
    resolved = Path(projects_root).resolve()
    if _project_service is None or _project_service.projects_root != resolved:
        _project_service = ProjectService(resolved)
    return _project_service
