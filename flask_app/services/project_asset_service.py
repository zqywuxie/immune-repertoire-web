"""
Project asset storage service.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from flask_app.services.input_validation_cache import snapshot
import shutil
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.utils import secure_filename

from flask_app.exceptions import AnalysisInProgressError, StorageError, ValidationError, UploadImpactChangedError, GroupSpecChangedError
from flask_app.models.database import AnalysisJob, Project, ProjectAsset, SampleRecord, db
from flask_app.services.file_parser import FileParserService
from flask_app.services.group_spec_service import get_group_spec_service
from flask_app.services.sample_registry_service import get_sample_registry_service
from flask_app.services.storage_adapter import get_storage_adapter


class ProjectAssetService:
    """Store project assets and generated results."""

    ASSET_TYPES = {
        'datapoint',
        'profile',
        'transcriptome',
        'deconvolution',
        'cibersort',
        'pep',
        'sample_summary',
        'group_spec',
        'processed_result',
        'raw_archive',
        'cached_usage',
        'cached_step34',
        'pdf_source',
        'ppt_template',
        'project_file',
    }

    SINGLETON_TYPES = {'sample_summary', 'group_spec'}

    def __init__(self, projects_root: Path):
        self.projects_root = Path(projects_root).resolve()
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def get_project_dir(self, project: Project) -> Path:
        from flask_app.services.project_storage_paths import project_data_dir
        return project_data_dir(project, self.projects_root)

    def get_asset_dir(self, project: Project, asset_type: str) -> Path:
        return self.get_project_dir(project) / 'assets' / asset_type

    def _create_upload_batch_dir(self, project: Project, asset_type: str) -> tuple[str, Path, Path]:
        from zoneinfo import ZoneInfo
        from flask import current_app, has_app_context

        from flask_app.services.project_storage_paths import project_upload_parent
        assets_root = project_upload_parent(project, self.projects_root)
        timezone_name = current_app.config.get('ANALYSIS_TIMEZONE', 'Asia/Shanghai') if has_app_context() else 'Asia/Shanghai'
        timezone = ZoneInfo(timezone_name)
        assets_root.mkdir(parents=True, exist_ok=True)
        while True:
            batch_id = datetime.now(timezone).strftime('%Y%m%d_%H%M%S') + '__' + uuid.uuid4().hex[:8]
            batch_root = assets_root / batch_id
            try:
                batch_root.mkdir()
            except FileExistsError:
                continue
            asset_dir = batch_root / asset_type
            asset_dir.mkdir()
            return batch_id, asset_dir, assets_root

    def _prune_empty_managed_dirs(self, project: Project, start_path: Path, asset=None) -> None:
        from flask_app.services.project_storage_paths import managed_upload_boundary
        project_root = managed_upload_boundary(project, asset, self.projects_root).parent.parent if asset and (asset.metadata_json or {}).get('managed_layout') == 'user-time-v1' else self.get_project_dir(project).resolve()
        try:
            current = Path(start_path).resolve()
            current.relative_to(project_root)
        except (OSError, ValueError):
            return
        while current != project_root:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def _storage_uri_for_path(self, path: Path) -> str:
        return get_storage_adapter().uri_for_path(path)

    def _metadata_with_storage_uri(self, metadata: Optional[Dict], path: Path | str) -> Dict:
        next_metadata = dict(metadata or {})
        next_metadata.setdefault('storage_uri', self._storage_uri_for_path(Path(path)))
        return next_metadata

    INPUT_TYPES = {'pep', 'profile', 'datapoint', 'transcriptome', 'deconvolution', 'cibersort'}

    @staticmethod
    def dataset_name(asset: ProjectAsset) -> str:
        metadata = asset.metadata_json or {}
        return str(metadata.get('asset_set') or metadata.get('dataset') or metadata.get('data_set')
                   or metadata.get('group_label') or metadata.get('group') or 'Set1').strip() or 'Set1'

    @classmethod
    def asset_query(cls, project_id: str, *, asset_type: str = '', inputs_only: bool = False,
                    asset_set: str = '', search: str = '', validation_status: str = '',
                    include_superseded: bool = False):
        query = ProjectAsset.query.filter(ProjectAsset.project_id == project_id)
        if asset_type:
            aliases = {'profile': ['profile', 'datapoint'], 'deconvolution': ['deconvolution', 'cibersort']}
            query = query.filter(ProjectAsset.asset_type.in_(aliases.get(asset_type, [asset_type]))) if inputs_only else query.filter(ProjectAsset.asset_type == asset_type)
        if inputs_only:
            query = query.filter(ProjectAsset.asset_type.in_(cls.INPUT_TYPES))
        if not include_superseded:
            query = query.filter(ProjectAsset.metadata_json['superseded'].as_boolean().isnot(True))
        if asset_set:
            query = query.filter(cls.dataset_expression() == asset_set)
        if search:
            from sqlalchemy import or_
            query = query.filter(or_(ProjectAsset.original_name.icontains(search, autoescape=True),
                ProjectAsset.metadata_json['description'].as_string().icontains(search, autoescape=True)))
        if validation_status:
            from sqlalchemy import func
            status = func.coalesce(ProjectAsset.metadata_json['validation']['status'].as_string(), 'unknown')
            query = query.filter(status.in_(['invalid', 'failed', 'needs_mapping', 'unknown'])) if validation_status == 'needs_attention' else query.filter(status == validation_status)
        return query

    @staticmethod
    def file_order(sort):
        orders = {'uploaded_desc': ProjectAsset.uploaded_at.desc(), 'uploaded_asc': ProjectAsset.uploaded_at.asc(),
                  'name_asc': ProjectAsset.original_name.asc(), 'name_desc': ProjectAsset.original_name.desc(),
                  'size_asc': ProjectAsset.size.asc(), 'size_desc': ProjectAsset.size.desc()}
        if sort not in orders:
            raise ValidationError(message='请选择有效的文件排序方式。')
        return orders[sort], ProjectAsset.id.desc()

    @staticmethod
    def dataset_expression():
        from sqlalchemy import func
        return func.coalesce(*[func.nullif(func.trim(ProjectAsset.metadata_json[key].as_string()), '')
                               for key in ('asset_set', 'dataset', 'data_set', 'group_label', 'group')], 'Set1')

    def dataset_summaries(self, project_id: str):
        from sqlalchemy import func
        dataset = self.dataset_expression()
        status = func.coalesce(ProjectAsset.metadata_json['validation']['status'].as_string(), 'unknown')
        samples = ProjectAsset.metadata_json['validation']['summary']['inputs'][0]['sample_count'].as_integer()
        rows = self.asset_query(project_id, inputs_only=True).with_entities(
            dataset, ProjectAsset.asset_type, status, func.count(ProjectAsset.id), func.min(samples), func.max(samples)
        ).group_by(dataset, ProjectAsset.asset_type, status).all()
        sets = {}
        aliases = {'datapoint': 'profile', 'cibersort': 'deconvolution'}
        for name, asset_type, state, count, low, high in rows:
            entry = sets.setdefault(name, {'name': name, 'input_count': 0, 'kinds': {}})
            kind = entry['kinds'].setdefault(aliases.get(asset_type, asset_type),
                                          {'count': 0, 'statuses': {}, 'sample_min': None, 'sample_max': None})
            entry['input_count'] += count
            kind['count'] += count
            kind['statuses'][state] = kind['statuses'].get(state, 0) + count
            if low is not None:
                kind['sample_min'] = low if kind['sample_min'] is None else min(low, kind['sample_min'])
                kind['sample_max'] = high if kind['sample_max'] is None else max(high, kind['sample_max'])
        from flask_app.services.project_dataset_service import add_dataset_metadata
        return add_dataset_metadata(project_id, list(sets.values()))

    @staticmethod
    def _input_identity_columns():
        return (ProjectAsset.id, ProjectAsset.project_id, ProjectAsset.asset_type,
                ProjectAsset.original_name, ProjectAsset.storage_path, ProjectAsset.size,
                ProjectAsset.mime_type, ProjectAsset.uploaded_at,
                ProjectAsset.metadata_json['storage_uri'].as_string(),
                ProjectAsset.metadata_json['content_version'].as_string(),
                ProjectAsset.metadata_json['validation']['status'].as_string(),
                ProjectAsset.metadata_json['superseded'].as_boolean())

    @staticmethod
    def _input_identity_payload(row, scope):
        identifier, project, asset_type, name, path, size, mime, uploaded, uri, version, status, history = row
        metadata = {'asset_set': scope, 'validation': {'status': status or 'unknown'}}
        if version:
            metadata['content_version'] = version
        if history:
            metadata['superseded'] = True
        return {'id': identifier, 'project_id': project, 'asset_type': asset_type,
                'original_name': name, 'storage_path': path, 'storage_uri': uri,
                'size': size, 'mime_type': mime, 'uploaded_at': uploaded.isoformat() if uploaded else None,
                'metadata': metadata}

    def input_candidate_page(self, project_id, *, asset_type='', asset_set='', search='',
                             validation_status='', include_superseded=False, page=1, page_size=20):
        query = self.asset_query(project_id, inputs_only=True, asset_type=asset_type,
                                 asset_set=asset_set, search=search, validation_status=validation_status,
                                 include_superseded=include_superseded)
        total = query.count()
        rows = query.with_entities(*self._input_identity_columns(), self.dataset_expression()).order_by(
            ProjectAsset.uploaded_at.desc(), ProjectAsset.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {'assets': [self._input_identity_payload(row[:-1], row[-1]) for row in rows], 'pagination': {
            'page': page, 'page_size': page_size, 'total': total,
            'total_pages': (total + page_size - 1) // page_size if total else 0}}

    def input_candidate_detail(self, project_id, asset_id):
        query = self.asset_query(project_id, inputs_only=True, include_superseded=True).filter(ProjectAsset.id == asset_id)
        row = query.with_entities(*self._input_identity_columns(), self.dataset_expression()).first()
        if row is None:
            raise ValidationError(message='分析输入不存在或不属于当前项目。')
        return self._input_identity_payload(row[:-1], row[-1])

    def replacement_query(self, project_id, asset_type, asset_set, filenames):
        query = self.asset_query(project_id, asset_type=asset_type, asset_set=asset_set)
        if asset_type == 'pep':
            query = query.filter(ProjectAsset.original_name.in_(filenames))
        return query

    def replacement_identities(self, project_id, asset_type, asset_set, filenames):
        rows = self.replacement_query(project_id, asset_type, asset_set, filenames).with_entities(
            ProjectAsset.id, ProjectAsset.original_name,
            ProjectAsset.metadata_json['content_version'].as_string()).all()
        # MySQL may use a case-insensitive collation: retain the original exact PEP rule.
        return sorted([{'id': row.id, 'content_version': str(row[2] or row.id)}
                       for row in rows if asset_type != 'pep' or row.original_name in filenames],
                      key=lambda row: row['id'])

    @staticmethod
    def normalize_expected_versions(value):
        if not isinstance(value, list) or any(not isinstance(row, dict) or set(row) != {'id', 'content_version'}
                or not isinstance(row['id'], str) or not row['id'] or len(row['id']) > 36
                or not isinstance(row['content_version'], str) or not row['content_version']
                or len(row['content_version']) > 128 for row in value):
            raise ValidationError(message='更新范围格式无效，请重新核对。')
        if len({row['id'] for row in value}) != len(value):
            raise ValidationError(message='更新范围包含重复文件，请重新核对。')
        return sorted(value, key=lambda row: row['id'])

    @staticmethod
    def _lock_input_project(project_id):
        # Uploads, input scope edits, removals and directory registrations share this lock.
        db.session.query(Project.id).filter(Project.id == project_id).with_for_update().one()

    def upload_impact(self, project_id, items, *, page=1, page_size=20):
        if not isinstance(items, list) or not items or len(items) > 200:
            raise ValidationError(message='请按每批 1 至 200 项核对更新范围。')
        normalized = []
        for item in items:
            if not isinstance(item, dict) or item.get('asset_type') not in self.INPUT_TYPES:
                raise ValidationError(message='请选择有效的分析输入类型。')
            dataset, name = item.get('asset_set'), item.get('name')
            if not isinstance(dataset, str) or not dataset.strip() or len(dataset.strip()) > 120:
                raise ValidationError(message='请指定要更新的数据集。')
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 255:
                raise ValidationError(message='请指定有效的上传文件名。')
            if not isinstance(item.get('directory', False), bool):
                raise ValidationError(message='请明确文件或目录登记方式。')
            normalized.append({'asset_type':item['asset_type'], 'asset_set':dataset.strip(),
                               'name':name.strip(), 'directory':item.get('directory', False)})
        groups = {}
        for item in normalized:
            if not item['directory']:
                groups.setdefault((item['asset_set'], item['asset_type']), set()).add(item['name'])
        scoped = {}
        for (dataset, kind), filenames in groups.items():
            rows = self.replacement_query(project_id, kind, dataset, filenames).with_entities(
                ProjectAsset.id, ProjectAsset.original_name, ProjectAsset.uploaded_at,
                ProjectAsset.metadata_json['content_version'].as_string()).order_by(
                    ProjectAsset.uploaded_at.desc(), ProjectAsset.id.desc()).all()
            scoped[(dataset, kind)] = [{'id':row.id, 'original_name':row.original_name,
                'uploaded_at':row.uploaded_at.isoformat() if row.uploaded_at else None,
                'content_version':str(row[3] or row.id)} for row in rows
                if kind != 'pep' or row.original_name in filenames]
        impacts = []
        for item in normalized:
            rows = [] if item['directory'] else scoped.get((item['asset_set'], item['asset_type']), [])
            if item['asset_type'] == 'pep':
                rows = [row for row in rows if row['original_name'] == item['name']]
            total = len(rows)
            impacts.append({**item, 'expected_versions':sorted(
                [{'id':row['id'],'content_version':row['content_version']} for row in rows],key=lambda row:row['id']),
                'assets':rows[(page-1)*page_size:page*page_size], 'pagination':{
                    'page':page,'page_size':page_size,'total':total,
                    'total_pages':(total+page_size-1)//page_size if total else 0}})
        return {'impacts':impacts}

    def resolve_input_selection(self, project_id: str, asset_set, asset_ids):
        """Restore exact registered identities, including history, with one bounded projection."""
        if not isinstance(asset_set, str) or not asset_set.strip():
            raise ValidationError(message='请先选择分析数据集。')
        if not isinstance(asset_ids, list) or len(asset_ids) > 500:
            raise ValidationError(message='每次最多恢复 500 份输入，请分批读取。')
        if any(not isinstance(identifier, str) or not identifier or len(identifier) > 36
               or identifier != identifier.strip() for identifier in asset_ids):
            raise ValidationError(message='保存的输入标识无效，请重新选择。')
        scope = asset_set.strip()
        identifiers = list(dict.fromkeys(asset_ids))
        if not identifiers:
            return {'asset_set': scope, 'assets': []}
        # Historical expression aliases were accepted by explicit input restoration.
        query = self.asset_query(project_id, asset_set=scope, include_superseded=True).filter(
            ProjectAsset.id.in_(identifiers), ProjectAsset.asset_type.in_(self.INPUT_TYPES | {'expression'}))
        rows = query.with_entities(*self._input_identity_columns()).all()
        if len(rows) != len(identifiers):
            raise ValidationError(message='部分保存的输入已移除或不属于本数据集，请重新选择或重试。')
        assets = {row.id: self._input_identity_payload(row, scope) for row in rows}
        return {'asset_set': scope, 'assets': [assets[identifier] for identifier in identifiers]}

    def input_selection(self, project_id: str, asset_set: str):
        """Complete clone selection and bounded scalar candidates without validation reports."""
        from sqlalchemy import func
        if not asset_set.strip():
            raise ValidationError(message='请先选择分析数据集。')
        scope = asset_set.strip()
        query = self.asset_query(project_id, inputs_only=True, asset_set=scope)
        aliases = {'datapoint': 'profile', 'cibersort': 'deconvolution'}
        totals = {'pep': 0, 'profile': 0, 'transcriptome': 0, 'deconvolution': 0}
        for kind, count in query.with_entities(ProjectAsset.asset_type, func.count(ProjectAsset.id)).group_by(ProjectAsset.asset_type).all():
            totals[aliases.get(kind, kind)] += count
        # JSON projection avoids transferring/parsing every file's sample arrays and quality report.
        columns = self._input_identity_columns()
        assets = []
        truncated = []
        for kind, types in [('pep', ['pep']), ('profile', ['profile', 'datapoint']),
                            ('transcriptome', ['transcriptome']), ('deconvolution', ['deconvolution', 'cibersort'])]:
            selected = query.filter(ProjectAsset.asset_type.in_(types)).with_entities(*columns).order_by(
                ProjectAsset.uploaded_at.desc(), ProjectAsset.id.desc())
            # All default clone inputs are needed for execution; scalar alternatives are browsed by page.
            if kind != 'pep':
                selected = selected.limit(50)
                if totals[kind] > 50:
                    truncated.append(kind)
            for row in selected.all():
                assets.append(self._input_identity_payload(row, scope))
        return {'asset_set': scope, 'assets': assets, 'totals': totals, 'truncated_kinds': truncated}

    def list_assets(self, project_id: str, asset_type: str = '', *, include_superseded: bool = False) -> List[ProjectAsset]:
        query = self.asset_query(project_id, asset_type=asset_type, include_superseded=include_superseded)
        ordered_query = query.order_by(ProjectAsset.uploaded_at.desc(), ProjectAsset.id.desc())
        try:
            return ordered_query.all()
        except OperationalError as exc:
            if not _is_mysql_sort_memory_error(exc):
                raise
            db.session.rollback()
            assets = query.all()
            return sorted(
                assets,
                key=lambda asset: (asset.uploaded_at or datetime.min, asset.id or ""),
                reverse=True,
            )

    @staticmethod
    def normalize_upload_operation(operation_id: str) -> str:
        if not operation_id:
            return ''
        try:
            return str(uuid.UUID(str(operation_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationError(message='上传操作标识无效，请重新选择文件。') from exc

    @staticmethod
    def upload_operation_asset_id(project_id: str, operation_id: str, index: int = 0) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f'immune:upload:{project_id}:{operation_id}:{index}'))

    def saved_upload_operation(self, project_id: str, operation_id: str, manifest=None) -> List[ProjectAsset]:
        operation_id = self.normalize_upload_operation(operation_id)
        if not operation_id:
            return []
        first = db.session.get(ProjectAsset, self.upload_operation_asset_id(project_id, operation_id))
        if first is None:
            return []
        receipt = (first.metadata_json or {}).get('upload_operation') or {}
        if first.project_id != project_id or receipt.get('id') != operation_id:
            raise ValidationError(message='上传操作与已保存记录不一致。')
        if manifest is not None and receipt.get('manifest') != manifest:
            raise ValidationError(message='本次选择与原上传操作不同，请重新选择文件。')
        assets = [db.session.get(ProjectAsset, self.upload_operation_asset_id(project_id, operation_id, index))
                  for index in range(receipt['count'])]
        if any(asset is None or asset.project_id != project_id for asset in assets):
            raise ValidationError(message='本次上传的部分文件已移除，请查看项目文件列表。')
        return assets

    def upload_assets(
        self, project: Project, *, asset_type: str, file_storages: List,
        relative_paths: Optional[List[str]] = None, replace_existing: Optional[bool] = None,
        metadata: Optional[Dict] = None, operation_id: str = "",
        expected_versions=None, require_expected_versions: bool = False,
    ) -> List[ProjectAsset]:
        if asset_type not in self.ASSET_TYPES:
            raise ValidationError(message='不支持此文件类型。')
        if not file_storages:
            raise ValidationError(message='请选择文件。')
        paths = list(relative_paths or [])
        paths.extend([''] * (len(file_storages) - len(paths)))
        if replace_existing is None:
            replace_existing = asset_type in self.SINGLETON_TYPES
        dataset = str((metadata or {}).get('asset_set') or 'Set1').strip() or 'Set1'
        operation_id = self.normalize_upload_operation(operation_id)
        manifest = {'kind': 'files', 'asset_type': asset_type, 'asset_set': dataset,
                    'replace_existing': bool(replace_existing),
                    'files': [{'name': str(storage.filename or '').strip(),
                               'relative_path': paths[index] or str(storage.filename or '').strip()}
                              for index, storage in enumerate(file_storages)]}
        if operation_id:
            saved = self.saved_upload_operation(project.id, operation_id, manifest)
            if saved:
                return saved
        names = {str(storage.filename or '').strip() for storage in file_storages}
        expected = self.normalize_expected_versions(expected_versions) if expected_versions is not None else None
        if replace_existing and require_expected_versions and expected is None:
            raise ValidationError(message='请先核对更新范围，再保存当前版本。')
        initial = self.replacement_identities(project.id, asset_type, dataset, names) if replace_existing else []
        if replace_existing and expected is not None and expected != initial:
            raise UploadImpactChangedError()
        has_previous = bool(initial)
        previous = []
        batch, directory, root = self._create_upload_batch_dir(project, asset_type)
        created = []
        summary_frame = None
        try:
            for index, storage in enumerate(file_storages):
                filename = str(storage.filename or '').strip()
                if not filename:
                    raise ValidationError(message='文件名称不能为空。')
                target = self._resolve_unique_target(directory, self._sanitize_relative_path(paths[index] or filename))
                target.parent.mkdir(parents=True, exist_ok=True)
                digest, size = hashlib.sha256(), 0
                with target.open('wb') as output:
                    while chunk := storage.stream.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                if not size:
                    raise ValidationError(message=f'文件为空：{filename}')
                mime = FileParserService.get_mime_type(filename)
                if mime == 'application/octet-stream':
                    mime = mimetypes.guess_type(target.name)[0] or mime
                info = {**dict(metadata or {}), 'relative_path': target.relative_to(root).as_posix(),
                        'upload_batch': batch, 'managed_layout': 'user-time-v1', 'storage_user': root.name,
                        'storage_uri': self._storage_uri_for_path(target), 'content_version': digest.hexdigest(),
                        'upload_snapshot': snapshot(target), 'validation': {'status': 'pending'}}
                if operation_id:
                    info['upload_operation'] = {'id': operation_id, 'count': len(file_storages), 'manifest': manifest}
                if asset_type == 'processed_result':
                    info['kind'] = 'analysis_result'
                candidate = ProjectAsset(project_id=project.id, asset_type=asset_type, original_name=filename,
                                         storage_path=str(target), mime_type=mime, size=size, metadata_json=info)
                if operation_id:
                    candidate.id = self.upload_operation_asset_id(project.id, operation_id, index)
                # Inspect before adding the candidate: validation's cache commits must
                # not publish half an upload transaction or retire an existing input.
                if has_previous and asset_type in self.INPUT_TYPES:
                    from flask_app.services.input_validation_cache import validate_uploaded_asset
                    with db.session.no_autoflush:
                        checked = validate_uploaded_asset(candidate)
                    if checked.get('errors'):
                        raise ValidationError(message='新文件校验未通过，原版本已保留。', details={'errors': checked['errors']})
                    states = [item.get('status') for item in checked.get('inputs', [])]
                    info['validation'] = {'status': 'needs_mapping' if 'needs_mapping' in states else 'valid',
                                          'summary': checked}
                    candidate.metadata_json = info
                created.append(candidate)
                if asset_type == 'sample_summary' and summary_frame is None:
                    from flask_app.routes.api_script_hub._common import _robust_read_csv
                    summary_frame = _robust_read_csv(target, dtype=str, keep_default_na=False)
            # Validation may commit cache state; acquire the publication lock only after it.
            self._lock_input_project(project.id)
            if operation_id:
                saved = self.saved_upload_operation(project.id, operation_id)
                if saved:
                    if (saved[0].metadata_json or {}).get('upload_operation', {}).get('manifest') != manifest:
                        raise ValidationError(message='本次选择与原上传操作不同，请重新选择文件。')
                    db.session.rollback()
                    shutil.rmtree(directory.parent)
                    return saved
            if replace_existing:
                previous = self.replacement_query(project.id, asset_type, dataset, names).populate_existing().with_for_update().all()
                if asset_type == 'pep':
                    previous = [asset for asset in previous if asset.original_name in names]
                actual = sorted([{'id':asset.id,'content_version':str((asset.metadata_json or {}).get('content_version') or asset.id)}
                                 for asset in previous],key=lambda row:row['id'])
                if expected is not None and expected != actual:
                    raise UploadImpactChangedError()
            db.session.add_all(created)
            db.session.flush()
            if summary_frame is not None:
                get_sample_registry_service().import_sample_summary_dataframe(
                    project, summary_frame, commit=False, source_asset_id=created[0].id,
                    asset_set=dataset, replace_existing=bool(replace_existing))
            for old in previous:
                old.metadata_json = {**(old.metadata_json or {}), 'superseded': True,
                                     'superseded_by': [asset.id for asset in created]}
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            shutil.rmtree(directory.parent)
            if operation_id and isinstance(exc, IntegrityError):
                saved = self.saved_upload_operation(project.id, operation_id, manifest)
                if saved:
                    return saved
            if isinstance(exc, (ValidationError, UploadImpactChangedError)):
                raise
            raise StorageError(message=f'保存文件失败：{exc}') from exc
        from flask_app.services.input_validation_cache import schedule_uploaded_validation
        schedule_uploaded_validation(created)
        return created

    def delete_asset(self, asset: ProjectAsset) -> Dict:
        if asset.asset_type in self.INPUT_TYPES or asset.asset_type == 'group_spec':
            self._lock_input_project(asset.project_id)
            db.session.refresh(asset, with_for_update=True)
        self.assert_asset_unreferenced(asset)
        target_path = Path(asset.storage_path)
        if asset.asset_type == 'sample_summary':
            get_sample_registry_service().remove_source_records(asset.project_id, asset.id)
        if asset.asset_type == 'group_spec' and not (asset.metadata_json or {}).get('superseded'):
            spec_id = str((asset.metadata_json or {}).get('spec_id') or '').strip()
            if spec_id:
                from flask_app.models.database import ProjectGroupSpec
                ProjectGroupSpec.query.filter(
                    ProjectGroupSpec.project_id == asset.project_id,
                    ProjectGroupSpec.id == spec_id,
                ).delete()
        self._delete_managed_storage_path(asset, target_path)
        project = db.session.get(Project, asset.project_id)
        if project is not None:
            self._prune_empty_managed_dirs(project, target_path.parent, asset)
        retained = target_path.exists()
        db.session.delete(asset)
        db.session.commit()
        return {'storage_retained': retained}

    def assert_asset_unreferenced(self, asset: ProjectAsset) -> None:
        from flask_app.services.project_asset_lineage import iter_referencing_jobs, referencing_schemes
        schemes = referencing_schemes(asset).all()
        if schemes:
            raise AnalysisInProgressError(
                message='文件仍被分组方案引用：' + '、'.join(spec.name for spec in schemes) + '。请先调整或删除这些方案。',
                details={'group_spec_ids': [spec.id for spec in schemes]},
            )
        job = next(iter_referencing_jobs(asset), None)
        if job:
            raise AnalysisInProgressError(message='文件仍被任务引用，请保留该版本。',
                                          details={'job_id': job['id'], 'status': job['status']})

    def update_asset_metadata(self, asset: ProjectAsset, changes: Dict) -> ProjectAsset:
        if asset.asset_type in self.INPUT_TYPES or asset.asset_type == 'group_spec':
            self._lock_input_project(asset.project_id)
            db.session.refresh(asset, with_for_update=True)
        if not isinstance(changes, dict) or set(changes) - {'asset_set', 'group_label', 'description'}:
            raise ValidationError(message='只允许修改数据集归属和文件说明。')
        if set(changes) - {'description'}:
            self.assert_asset_unreferenced(asset)
        if 'description' in changes:
            if not isinstance(changes['description'], str) or len(changes['description']) > 2000:
                raise ValidationError(message='文件说明须为不超过 2000 字的文本。')
        metadata = {**(asset.metadata_json or {}), **changes}
        if 'asset_set' in changes:
            label = str(changes['asset_set'] or '').strip()
            if not label or len(label) > 120:
                raise ValidationError(message='数据集名称须为 1 至 120 个字符。')
            metadata.update(asset_set=label, group_label=label)
        next_dataset = str(metadata.get('asset_set') or metadata.get('dataset') or metadata.get('data_set')
                           or metadata.get('group_label') or metadata.get('group') or 'Set1').strip() or 'Set1'
        if asset.asset_type == 'sample_summary' and next_dataset != self.dataset_name(asset):
            source_record = db.session.query(SampleRecord.id).filter(
                SampleRecord.project_id == asset.project_id,
                SampleRecord.extra_metadata['source_asset_id'].as_string() == asset.id,
            ).first()
            if source_record:
                raise ValidationError(message='该登记表已有来源登记，不能直接更换数据集。请在目标数据集中导入登记表，原有登记信息会保留。')
        asset.metadata_json = metadata
        db.session.commit()
        return asset

    def delete_assets_by_type(self, project: Project, asset_type: str) -> None:
        assets = ProjectAsset.query.filter(
            ProjectAsset.project_id == project.id,
            ProjectAsset.asset_type == asset_type,
        ).all()
        for asset in assets:
            self.assert_asset_unreferenced(asset)
        for asset in assets:
            target_path = Path(asset.storage_path)
            self._delete_managed_storage_path(asset, target_path)
            self._prune_empty_managed_dirs(project, target_path.parent, asset)
            db.session.delete(asset)

        if asset_type == 'sample_summary':
            for asset in assets:
                get_sample_registry_service().remove_source_records(project.id, asset.id)
        if asset_type == 'group_spec':
            from flask_app.models.database import ProjectGroupSpec
            ProjectGroupSpec.query.filter(ProjectGroupSpec.project_id == project.id).delete()

        db.session.commit()

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
            'storage_uri': self._storage_uri_for_path(Path(chosen_storage)),
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

        from flask_app.services.project_result_catalog import saved_result_dataset
        scope = saved_result_dataset({'metadata_json':result_metadata})
        if scope:
            metadata_json['asset_set'] = scope

        chosen_path = Path(chosen_storage).resolve()
        if not chosen_path.exists():
            raise ValidationError(message="分析输出文件不存在，无法登记结果")
        from flask_app.services.path_access_service import PathAccessService
        PathAccessService.validate_read_path(chosen_path)
        result_files = []
        for file in ([chosen_path] if chosen_path.is_file() else chosen_path.rglob("*")):
            if file.is_file() and not file.is_symlink():
                result_files.append({"name": file.name if chosen_path.is_file() else file.relative_to(chosen_path).as_posix(), "size": file.stat().st_size})
        if not result_files:
            raise ValidationError(message="分析输出目录为空，无法登记结果")
        metadata_json["result_files"] = result_files
        result_size = sum(item["size"] for item in result_files)
        candidates = ProjectAsset.query.filter_by(project_id=project.id, asset_type="processed_result").all()
        existing = next((item for item in candidates if job_id and (item.metadata_json or {}).get("job_id") == job_id), None)

        if existing:
            existing.original_name = f"{analysis_type}_{job_id or analysis_signature[:12] or uuid.uuid4().hex[:8]}"
            existing.storage_path = chosen_storage
            existing.size = result_size
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
            size=result_size,
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
        original_name: Optional[str] = None, operation_id: str = "", operation_source_path: str = "",
    ) -> ProjectAsset:
        if asset_type not in self.ASSET_TYPES:
            raise ValidationError(message="Unsupported asset type", details={'asset_type': asset_type})
        if not str(storage_path or "").strip():
            raise ValidationError(message="storage_path is required")

        normalized_path = str(storage_path)
        metadata_json = self._metadata_with_storage_uri(metadata, normalized_path)
        operation_id = self.normalize_upload_operation(operation_id)
        if operation_id:
            manifest = {'kind': 'path', 'asset_type': asset_type, 'storage_path': normalized_path,
                        'requested_path': operation_source_path or normalized_path,
                        'asset_set': str((metadata or {}).get('asset_set') or 'Set1').strip() or 'Set1',
                        'original_name': original_name}
            saved = self.saved_upload_operation(project.id, operation_id, manifest)
            if saved:
                return saved[0]
            if asset_type in self.INPUT_TYPES:
                self._lock_input_project(project.id)
                saved = self.saved_upload_operation(project.id, operation_id)
                if saved:
                    if (saved[0].metadata_json or {}).get('upload_operation', {}).get('manifest') != manifest:
                        raise ValidationError(message='本次选择与原上传操作不同，请重新添加目录。')
                    db.session.rollback()
                    return saved[0]
            metadata_json['upload_operation'] = {'id': operation_id, 'count': 1, 'manifest': manifest}
            asset = ProjectAsset(id=self.upload_operation_asset_id(project.id, operation_id),
                project_id=project.id, asset_type=asset_type, original_name=original_name or Path(normalized_path).name,
                storage_path=normalized_path, size=0, metadata_json=metadata_json)
            db.session.add(asset)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                saved = self.saved_upload_operation(project.id, operation_id, manifest)
                if not saved:
                    raise
                return saved[0]
            return asset
        if asset_type in self.INPUT_TYPES:
            self._lock_input_project(project.id)
        query = ProjectAsset.query.filter(
            ProjectAsset.project_id == project.id,
            ProjectAsset.storage_path == normalized_path,
            ProjectAsset.asset_type == asset_type,
        )
        existing = query.populate_existing().first()

        if existing:
            existing.metadata_json = {**(existing.metadata_json or {}), **metadata_json}
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
            metadata_json=metadata_json,
        )
        db.session.add(asset)
        db.session.commit()
        return asset

    def save_group_spec_asset(self, project: Project, *, name: str, spec_json: Dict, spec_id: str = '',
                              expected_revision=None, require_expected_revision=False) -> ProjectAsset:
        """Publish a new immutable file only after the complete save succeeds."""
        import json
        target_path = None
        try:
            from flask_app.models.database import ProjectGroupSpec
            self._lock_input_project(project.id)
            group_service = get_group_spec_service()
            if spec_id:
                existing = ProjectGroupSpec.query.filter_by(project_id=project.id, id=spec_id) \
                    .populate_existing().with_for_update().first()
                if existing is None:
                    raise GroupSpecChangedError(message='分组方案已删除，当前编辑已保留；可以另存新方案。')
                if require_expected_revision and (not isinstance(expected_revision, str) or not expected_revision or len(expected_revision) > 128):
                    raise ValidationError(message='请重新读取方案版本后编辑保存。')
                version = group_service.revision_query(project.id, [spec_id]).with_for_update().first()
                actual_revision = version[0] if version else group_service.legacy_revision(existing)
                if expected_revision is not None and expected_revision != actual_revision:
                    raise GroupSpecChangedError()
            elif require_expected_revision:
                duplicate = ProjectGroupSpec.query.filter_by(project_id=project.id, name=str(name or 'default').strip() or 'default') \
                    .with_for_update().first()
                if duplicate is not None:
                    raise ValidationError(message='此方案名称已存在，请使用新名称，或读取已有方案后编辑。')
            spec = get_group_spec_service().save_spec(
                project, name=name, spec_json=spec_json, replace_existing=True, commit=False, spec_id=spec_id)
            previous = ProjectAsset.query.filter(
                ProjectAsset.project_id == project.id, ProjectAsset.asset_type == 'group_spec',
                ProjectAsset.metadata_json['spec_id'].as_string() == spec.id,
                ProjectAsset.metadata_json['superseded'].as_boolean().isnot(True),
            ).populate_existing().with_for_update().all()
            asset_dir = self.get_asset_dir(project, 'group_spec')
            asset_dir.mkdir(parents=True, exist_ok=True)
            target_path = asset_dir / f'{spec.id}__{uuid.uuid4().hex}.json'
            content = json.dumps(spec.spec_json, ensure_ascii=False, indent=2)
            target_path.write_text(content, encoding='utf-8')
            asset = ProjectAsset(
                project_id=project.id, asset_type='group_spec', original_name=f'{spec.name}.json',
                storage_path=str(target_path), mime_type='application/json', size=target_path.stat().st_size,
                metadata_json={'spec_id': spec.id, 'relative_path': target_path.name,
                               'storage_uri': self._storage_uri_for_path(target_path),
                               'content_version': hashlib.sha256(content.encode('utf-8')).hexdigest()},
            )
            db.session.add(asset)
            db.session.flush()
            for old in previous:
                old.metadata_json = {**(old.metadata_json or {}), 'superseded': True, 'superseded_by': [asset.id]}
            db.session.commit()
            return asset
        except Exception as error:
            db.session.rollback()
            if target_path is not None:
                target_path.unlink(missing_ok=True)
            if isinstance(error, (ValidationError, GroupSpecChangedError)):
                raise
            raise StorageError(message=f'分组方案未保存，原方案已保留：{error}') from error

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
            safe = re.sub(r'[<>:"|?*\x00-\x1f]', '_', part).strip(' .')
            safe_parts.append(safe or f"file_{uuid.uuid4().hex[:8]}")
        if not safe_parts:
            raise ValidationError(message="Relative path is invalid")
        return '/'.join(safe_parts)

    def _delete_managed_storage_path(self, asset: ProjectAsset, target_path: Path) -> None:
        """Delete only storage owned by this project's managed asset directory."""
        if not target_path.exists():
            return

        try:
            resolved_target = target_path.resolve()
            project = db.session.get(Project, asset.project_id)
            from flask_app.services.project_storage_paths import managed_upload_boundary
            project_dir = managed_upload_boundary(project, asset, self.projects_root) if project else (self.projects_root / "legacy" / asset.project_id).resolve()
            resolved_target.relative_to(project_dir)
        except (OSError, ValueError):
            return

        if resolved_target == project_dir:
            return

        # Imported inputs and reused results may refer to the same file or a child.
        from flask_app.routes.api_jobs import _collect_result_paths
        paths = []
        for storage, metadata in ProjectAsset.query.filter(ProjectAsset.id != asset.id).with_entities(
                ProjectAsset.storage_path, ProjectAsset.metadata_json).all():
            paths.extend([storage, *_collect_result_paths(metadata or {})])
        for payload, result in AnalysisJob.query.filter(AnalysisJob.project_id != asset.project_id).with_entities(
                AnalysisJob.payload, AnalysisJob.result).all():
            paths.extend(_collect_result_paths(payload or {}))
            paths.extend(_collect_result_paths(result or {}))
        for raw_path in paths:
            if raw_path and Path(raw_path).is_absolute():
                other = Path(raw_path).resolve()
                if other == resolved_target or other in resolved_target.parents or resolved_target in other.parents:
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


def _is_mysql_sort_memory_error(exc: OperationalError) -> bool:
    """Detect MySQL 1038 sort-buffer errors and allow a narrower fallback."""
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", ())
    if args and str(args[0]) == "1038":
        return True
    message = str(orig or exc).lower()
    return "out of sort memory" in message or "sort buffer size" in message
