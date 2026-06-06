"""
Project asset storage service.
"""

from __future__ import annotations

import mimetypes
import shutil
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from werkzeug.utils import secure_filename

from flask_app.exceptions import StorageError, ValidationError
from flask_app.models.database import Project, ProjectAsset, db
from flask_app.services.file_parser import FileParserService
from flask_app.services.group_spec_service import get_group_spec_service
from flask_app.services.sample_registry_service import get_sample_registry_service


class ProjectAssetService:
    """Store project assets and generated results."""

    ASSET_TYPES = {
        'datapoint',
        'profile',
        'pep',
        'sample_summary',
        'group_spec',
        'processed_result',
        'raw_archive',
        'cached_usage',
        'cached_step34',
        'pdf_source',
        'ppt_template',
    }

    SINGLETON_TYPES = {'sample_summary', 'group_spec'}

    def __init__(self, projects_root: Path):
        self.projects_root = Path(projects_root).resolve()
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def get_project_dir(self, project: Project) -> Path:
        return self.projects_root / project.id

    def get_asset_dir(self, project: Project, asset_type: str) -> Path:
        return self.get_project_dir(project) / 'assets' / asset_type

    def list_assets(self, project_id: str, asset_type: str = "") -> List[ProjectAsset]:
        query = ProjectAsset.query.filter(ProjectAsset.project_id == project_id).order_by(ProjectAsset.uploaded_at.desc())
        if asset_type:
            query = query.filter(ProjectAsset.asset_type == asset_type)
        return query.all()

    def upload_assets(
        self,
        project: Project,
        *,
        asset_type: str,
        file_storages: List,
        relative_paths: Optional[List[str]] = None,
        replace_existing: Optional[bool] = None,
    ) -> List[ProjectAsset]:
        if asset_type not in self.ASSET_TYPES:
            raise ValidationError(message="Unsupported asset type", details={'asset_type': asset_type})
        if not file_storages:
            raise ValidationError(message="No files were uploaded", details={'field': 'files'})

        normalized_relative_paths = relative_paths or [''] * len(file_storages)
        if len(normalized_relative_paths) < len(file_storages):
            normalized_relative_paths.extend([''] * (len(file_storages) - len(normalized_relative_paths)))

        if replace_existing is None:
            replace_existing = asset_type in self.SINGLETON_TYPES

        if replace_existing:
            self.delete_assets_by_type(project, asset_type)

        asset_dir = self.get_asset_dir(project, asset_type)
        asset_dir.mkdir(parents=True, exist_ok=True)

        created_assets: List[ProjectAsset] = []
        sample_summary_df = None

        try:
            for index, file_storage in enumerate(file_storages):
                filename = str(file_storage.filename or '').strip()
                if not filename:
                    continue

                raw_bytes = file_storage.read()
                if not raw_bytes:
                    continue

                relative_path = self._sanitize_relative_path(normalized_relative_paths[index] or filename)
                target_path = self._resolve_unique_target(asset_dir, relative_path)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(raw_bytes)

                mime_type = FileParserService.get_mime_type(filename)
                if mime_type == 'application/octet-stream':
                    guessed_mime, _ = mimetypes.guess_type(target_path.name)
                    mime_type = guessed_mime or mime_type

                metadata = {
                    'relative_path': target_path.relative_to(asset_dir).as_posix(),
                }
                if asset_type == 'processed_result':
                    metadata['kind'] = 'analysis_result'

                asset = ProjectAsset(
                    project_id=project.id,
                    asset_type=asset_type,
                    original_name=filename,
                    storage_path=str(target_path),
                    mime_type=mime_type,
                    size=len(raw_bytes),
                    metadata_json=metadata,
                )
                db.session.add(asset)
                created_assets.append(asset)

                if asset_type == 'sample_summary' and sample_summary_df is None:
                    sample_summary_df, _, _ = FileParserService.parse_file(raw_bytes, filename)
        except Exception as exc:
            db.session.rollback()
            raise StorageError(message=f"Failed to store project asset: {exc}") from exc

        db.session.commit()

        if asset_type == 'sample_summary' and sample_summary_df is not None:
            get_sample_registry_service().import_sample_summary_dataframe(project, sample_summary_df)

        return created_assets

    def delete_asset(self, asset: ProjectAsset) -> None:
        target_path = Path(asset.storage_path)
        if asset.asset_type == 'sample_summary':
            from flask_app.models.database import SampleRecord
            SampleRecord.query.filter(SampleRecord.project_id == asset.project_id).delete()
        if asset.asset_type == 'group_spec':
            spec_id = str((asset.metadata_json or {}).get('spec_id') or '').strip()
            if spec_id:
                from flask_app.models.database import ProjectGroupSpec
                ProjectGroupSpec.query.filter(
                    ProjectGroupSpec.project_id == asset.project_id,
                    ProjectGroupSpec.id == spec_id,
                ).delete()
        self._delete_managed_storage_path(asset, target_path)
        db.session.delete(asset)
        db.session.commit()

    def delete_assets_by_type(self, project: Project, asset_type: str) -> None:
        assets = ProjectAsset.query.filter(
            ProjectAsset.project_id == project.id,
            ProjectAsset.asset_type == asset_type,
        ).all()
        for asset in assets:
            target_path = Path(asset.storage_path)
            if target_path.exists() and target_path.is_file():
                target_path.unlink(missing_ok=True)
            db.session.delete(asset)

        if asset_type == 'sample_summary':
            from flask_app.models.database import SampleRecord
            SampleRecord.query.filter(SampleRecord.project_id == project.id).delete()
        if asset_type == 'group_spec':
            from flask_app.models.database import ProjectGroupSpec
            ProjectGroupSpec.query.filter(ProjectGroupSpec.project_id == project.id).delete()

        db.session.commit()

        asset_dir = self.get_asset_dir(project, asset_type)
        if asset_dir.exists():
            shutil.rmtree(asset_dir, ignore_errors=True)

    def register_analysis_result(
        self,
        project: Project,
        *,
        analysis_type: str,
        job_id: str = "",
        output_base: str = "",
        report_path: str = "",
        report_url: str = "",
        metadata_url: str = "",
        zip_url: str = "",
        viewer_url: str = "",
        metadata: Optional[Dict] = None,
    ) -> ProjectAsset:
        chosen_storage = str(report_path or output_base or '').strip()
        if not chosen_storage:
            raise ValidationError(message="Result path is required", details={'field': 'report_path/output_base'})

        result_metadata = metadata or {}
        analysis_signature = str(result_metadata.get('analysis_signature') or '').strip()
        metadata_json = {
            'analysis_type': analysis_type,
            'job_id': job_id,
            'output_base': output_base,
            'report_path': report_path,
            'report_url': report_url,
            'metadata_url': metadata_url,
            'zip_url': zip_url,
            'viewer_url': viewer_url,
            'analysis_signature': analysis_signature,
            'result_id': str(result_metadata.get('result_id') or ''),
            'input_assets': result_metadata.get('input_assets') or [],
            'config_json': result_metadata.get('config_json') or {},
            'metadata': result_metadata,
        }

        existing = None
        if analysis_signature:
            candidates = ProjectAsset.query.filter(
                ProjectAsset.project_id == project.id,
                ProjectAsset.asset_type == 'processed_result',
            ).all()
            for candidate in candidates:
                candidate_meta = candidate.metadata_json or {}
                if str(candidate_meta.get('analysis_signature') or '').strip() == analysis_signature:
                    existing = candidate
                    break

        if existing is None:
            existing = ProjectAsset.query.filter(
                ProjectAsset.project_id == project.id,
                ProjectAsset.asset_type == 'processed_result',
                ProjectAsset.storage_path == chosen_storage,
            ).first()

        if existing:
            existing.original_name = f"{analysis_type}_{job_id or analysis_signature[:12] or uuid.uuid4().hex[:8]}"
            existing.storage_path = chosen_storage
            existing.mime_type = 'text/html' if str(report_path).lower().endswith('.html') else 'application/octet-stream'
            existing.metadata_json = {**(existing.metadata_json or {}), **metadata_json}
            existing.uploaded_at = datetime.utcnow()
            db.session.commit()
            return existing

        asset = ProjectAsset(
            project_id=project.id,
            asset_type='processed_result',
            original_name=f"{analysis_type}_{job_id or analysis_signature[:12] or uuid.uuid4().hex[:8]}",
            storage_path=chosen_storage,
            mime_type='text/html' if str(report_path).lower().endswith('.html') else 'application/octet-stream',
            size=0,
            metadata_json=metadata_json,
        )
        db.session.add(asset)
        db.session.commit()
        return asset

    def register_cached_asset(
        self,
        project: Project,
        *,
        asset_type: str,
        storage_path: str,
        metadata: Optional[Dict] = None,
        original_name: Optional[str] = None,
    ) -> ProjectAsset:
        if asset_type not in self.ASSET_TYPES:
            raise ValidationError(message="Unsupported asset type", details={'asset_type': asset_type})
        if not str(storage_path or "").strip():
            raise ValidationError(message="storage_path is required")

        normalized_path = str(storage_path)
        query = ProjectAsset.query.filter(
            ProjectAsset.project_id == project.id,
            ProjectAsset.storage_path == normalized_path,
            ProjectAsset.asset_type == asset_type,
        )
        existing = query.first()

        if existing:
            if metadata:
                existing.metadata_json = {**(existing.metadata_json or {}), **metadata}
            if original_name:
                existing.original_name = original_name
            existing.uploaded_at = datetime.utcnow()
            db.session.commit()
            return existing

        asset = ProjectAsset(
            project_id=project.id,
            asset_type=asset_type,
            original_name=original_name or f"{asset_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            storage_path=normalized_path,
            size=0,
            metadata_json=metadata or {},
        )
        db.session.add(asset)
        db.session.commit()
        return asset

    def save_group_spec_asset(self, project: Project, *, name: str, spec_json: Dict) -> ProjectAsset:
        spec = get_group_spec_service().save_spec(project, name=name, spec_json=spec_json, replace_existing=True)
        asset_dir = self.get_asset_dir(project, 'group_spec')
        asset_dir.mkdir(parents=True, exist_ok=True)
        target_path = asset_dir / f"{secure_filename(spec.name) or 'group_spec'}.json"
        import json
        target_path.write_text(json.dumps(spec_json, ensure_ascii=False, indent=2), encoding='utf-8')

        existing = ProjectAsset.query.filter(
            ProjectAsset.project_id == project.id,
            ProjectAsset.asset_type == 'group_spec',
            ProjectAsset.original_name == target_path.name,
        ).first()
        if existing is None:
            asset = ProjectAsset(
                project_id=project.id,
                asset_type='group_spec',
                original_name=target_path.name,
                storage_path=str(target_path),
                mime_type='application/json',
                size=target_path.stat().st_size,
                metadata_json={'spec_id': spec.id, 'relative_path': target_path.name},
            )
            db.session.add(asset)
        else:
            existing.storage_path = str(target_path)
            existing.size = target_path.stat().st_size
            existing.metadata_json = {'spec_id': spec.id, 'relative_path': target_path.name}
        db.session.commit()
        return ProjectAsset.query.filter(
            ProjectAsset.project_id == project.id,
            ProjectAsset.asset_type == 'group_spec',
            ProjectAsset.original_name == target_path.name,
        ).first()

    def _resolve_unique_target(self, asset_dir: Path, relative_path: str) -> Path:
        target_path = asset_dir / relative_path
        if not target_path.exists():
            return target_path

        candidate_parent = target_path.parent
        stem = target_path.stem
        suffix = target_path.suffix
        counter = 1
        while True:
            candidate = candidate_parent / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _sanitize_relative_path(self, relative_path: str) -> str:
        raw_value = str(relative_path or '').replace('\\', '/').strip('/')
        if not raw_value:
            raise ValidationError(message="Relative path cannot be empty")
        safe_parts = []
        for part in PurePosixPath(raw_value).parts:
            if part in {'.', ''}:
                continue
            if part == '..':
                raise ValidationError(message="Relative path cannot traverse parent directories")
            safe_parts.append(secure_filename(part) or f"file_{uuid.uuid4().hex[:8]}")
        if not safe_parts:
            raise ValidationError(message="Relative path is invalid")
        return '/'.join(safe_parts)

    def _delete_managed_storage_path(self, asset: ProjectAsset, target_path: Path) -> None:
        """Delete only storage owned by this project's managed asset directory."""
        if not target_path.exists():
            return

        try:
            resolved_target = target_path.resolve()
            project_dir = (self.projects_root / asset.project_id).resolve()
            resolved_target.relative_to(project_dir)
        except (OSError, ValueError):
            return

        if resolved_target == project_dir:
            return

        try:
            if resolved_target.is_dir():
                shutil.rmtree(resolved_target)
            else:
                resolved_target.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(
                message=f"Failed to delete project asset storage: {exc}",
                details={'asset_id': asset.id, 'storage_path': str(target_path)},
            ) from exc


_project_asset_service: Optional[ProjectAssetService] = None


def get_project_asset_service(projects_root: Path) -> ProjectAssetService:
    global _project_asset_service
    resolved = Path(projects_root).resolve()
    if _project_asset_service is None or _project_asset_service.projects_root != resolved:
        _project_asset_service = ProjectAssetService(resolved)
    return _project_asset_service
