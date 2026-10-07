"""
Project group specification service.
"""

from __future__ import annotations

from typing import Any, Dict, List

from flask_app.exceptions import StorageError, ValidationError
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
        commit: bool = True,
        spec_id: str = '',
    ) -> ProjectGroupSpec:
        spec_name = str(name or 'default').strip() or 'default'
        if not isinstance(spec_json, dict) or not spec_json:
            raise ValidationError(message="Group specification cannot be empty", details={'field': 'spec_json'})

        if spec_id:
            existing = ProjectGroupSpec.query.filter_by(id=spec_id, project_id=project.id).first()
            if existing is None:
                raise ValidationError(message='分组方案不属于当前项目或已删除。')
            duplicate = ProjectGroupSpec.query.filter(ProjectGroupSpec.project_id == project.id,
                ProjectGroupSpec.name == spec_name, ProjectGroupSpec.id != spec_id).first()
            if duplicate is not None:
                raise ValidationError(message='此方案名称已存在，请使用其他名称。')
            from flask_app.services.project_group_source import validate_group_definition
            definition = validate_group_definition(project.id, {**(existing.spec_json or {}), **spec_json})
            existing.name = spec_name
            existing.spec_json = definition
            db.session.commit() if commit else db.session.flush()
            return existing

        from flask_app.services.project_group_source import validate_group_definition
        spec_json = validate_group_definition(project.id, spec_json)
        if replace_existing:
            existing = ProjectGroupSpec.query.filter(
                ProjectGroupSpec.project_id == project.id,
                ProjectGroupSpec.name == spec_name,
            ).first()
            if existing is not None:
                existing.spec_json = spec_json
                db.session.commit() if commit else db.session.flush()
                return existing

        spec = ProjectGroupSpec(
            project_id=project.id,
            name=spec_name,
            spec_json=spec_json,
        )
        db.session.add(spec)
        db.session.commit() if commit else db.session.flush()
        return spec

    @staticmethod
    def _source_path(asset):
        from flask_app.routes.api_projects import _resolve_asset_path
        try:
            return _resolve_asset_path(asset).resolve()
        except (ValidationError, StorageError, OSError):
            return None

    @staticmethod
    def revision_query(project_id, identifiers):
        from flask_app.models.database import ProjectAsset
        return ProjectAsset.query.filter(
            ProjectAsset.project_id == project_id, ProjectAsset.asset_type == 'group_spec',
            ProjectAsset.metadata_json['spec_id'].as_string().in_(identifiers),
            ProjectAsset.metadata_json['superseded'].as_boolean().isnot(True),
        ).with_entities(ProjectAsset.id, ProjectAsset.metadata_json['spec_id'].as_string()) \
            .order_by(ProjectAsset.uploaded_at.desc(), ProjectAsset.id.desc())

    @staticmethod
    def legacy_revision(spec):
        return 'legacy:' + (spec.updated_at.isoformat() if spec.updated_at else spec.id)

    @staticmethod
    def source_identities(query):
        from types import SimpleNamespace
        from flask_app.models.database import ProjectAsset
        from flask_app.services.project_asset_service import ProjectAssetService
        keys = ('storage_uri', 'output_base', 'report_path', 'viewer_path', 'file_path', 'source_asset_id')
        rows = query.with_entities(ProjectAsset.id, ProjectAsset.original_name, ProjectAsset.storage_path,
            ProjectAssetService.dataset_expression(),
            *[ProjectAsset.metadata_json[key].as_string() for key in keys]).all()
        return [SimpleNamespace(id=row[0], original_name=row[1], storage_path=row[2],
                metadata_json={'asset_set': row[3], **dict(zip(keys, row[4:]))}) for row in rows]

    def catalog(self, project_id, *, asset_set='', search='', page=1, page_size=20):
        from types import SimpleNamespace
        from sqlalchemy import case, func, or_
        from flask_app.models.database import ProjectAsset
        from flask_app.services.project_asset_service import ProjectAssetService
        definition = ProjectGroupSpec.spec_json
        scope = func.coalesce(func.nullif(func.trim(definition['asset_set'].as_string()), ''),
            case((ProjectAsset.id.isnot(None), ProjectAssetService.dataset_expression()), else_=''))
        query = ProjectGroupSpec.query.outerjoin(ProjectAsset,
            (ProjectAsset.id == definition['source_asset_id'].as_string()) &
            (ProjectAsset.project_id == ProjectGroupSpec.project_id)
        ).filter(ProjectGroupSpec.project_id == project_id)
        if asset_set:
            query = query.filter(or_(scope == asset_set, scope == ''))
        if search:
            escaped = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            query = query.filter(ProjectGroupSpec.name.ilike('%' + escaped + '%', escape='\\'))
        total = query.with_entities(ProjectGroupSpec.id).count()
        count = (func.json_array_length if db.engine.dialect.name == 'sqlite' else func.json_length)(definition['groups'])
        keys = ('group_field', 'source_asset_id', 'source_content_version', 'source_sheet', 'asset_set')
        rows = query.with_entities(ProjectGroupSpec.id, ProjectGroupSpec.name,
            ProjectGroupSpec.created_at, ProjectGroupSpec.updated_at, count,
            *[definition[key].as_string() for key in keys], *[definition['groups'][index] for index in range(6)]
        ).order_by(ProjectGroupSpec.updated_at.desc(), ProjectGroupSpec.id.desc()).offset((page-1)*page_size).limit(page_size).all()
        projected = []
        for row in rows:
            spec_json = dict(zip(keys, row[5:10]))
            spec_json['groups'] = [value for value in row[10:] if value is not None]
            item = {'id':row[0], 'name':row[1], 'project_id':project_id, 'group_count':int(row[4] or 0),
                    'created_at':row[2].isoformat() if row[2] else None,
                    'updated_at':row[3].isoformat() if row[3] else None, 'spec_json':spec_json}
            projected.append(SimpleNamespace(id=row[0], updated_at=row[3], spec_json=spec_json, to_dict=lambda item=item:item))
        items = self.describe_specs(project_id, specs=projected)
        for item in items:
            definition = item.pop('spec_json')
            item['group_preview'] = [str(value.get('name') or value.get('label') or '') if isinstance(value,dict) else str(value)
                                     for value in definition['groups']]
            item['group_field'] = definition.get('group_field') or ''
            item['asset_set'] = item['source']['asset_set'] or str(definition.get('asset_set') or '')
            item['source_content_version'] = definition.get('source_content_version')
            item['project_wide'] = not item['asset_set']
        return {'items':items, 'pagination':{'page':page,'page_size':page_size,'total':total,
                                            'total_pages':(total+page_size-1)//page_size if total else 0}}

    def describe_specs(self, project_id: str, *, profile_path: str = '', asset_set: str = '', specs=None):
        from pathlib import Path
        from flask_app.models.database import ProjectAsset
        from flask_app.routes.api_projects import _resolve_asset_path
        from flask_app.services.project_asset_service import ProjectAssetService
        specs = self.list_specs(project_id) if specs is None else specs
        revisions = {}
        for version_id, identifier in self.revision_query(project_id, [spec.id for spec in specs]).all() if specs else []:
            revisions.setdefault(identifier, version_id)
        identifiers = {str((spec.spec_json or {}).get('source_asset_id') or '') for spec in specs} - {''}
        sources = {asset.id: asset for asset in self.source_identities(ProjectAsset.query.filter(
            ProjectAsset.project_id == project_id, ProjectAsset.id.in_(identifiers)))} if identifiers else {}
        prepared = self.source_identities(ProjectAsset.query.filter(ProjectAsset.project_id == project_id,
            ProjectAsset.metadata_json['source_asset_id'].as_string().in_(identifiers))) if identifiers and profile_path else []
        selected = Path(profile_path).resolve() if profile_path else None
        payload = []
        for spec in specs:
            definition = spec.spec_json or {}
            identifier = str(definition.get('source_asset_id') or '')
            source = sources.get(identifier)
            dataset = ProjectAssetService.dataset_name(source) if source else str(definition.get('asset_set') or '')
            reason = ''
            if identifier and source is None:
                reason = '来源指标表已移除，请重新绑定来源。'
            elif source is not None and not profile_path and self._source_path(source) is None:
                reason = '来源文件无法读取，请检查存储位置。'
            elif asset_set and dataset and dataset != asset_set:
                reason = '方案属于其他数据集。'
            elif selected and source is not None:
                candidates = [source, *[asset for asset in prepared if (asset.metadata_json or {}).get('source_asset_id') == identifier]]
                if not any(self._source_path(asset) == selected for asset in candidates):
                    reason = '方案来源版本与当前指标表不同。'
            item = spec.to_dict()
            item['revision'] = revisions.get(spec.id) or self.legacy_revision(spec)
            item['source'] = {'asset_id': identifier or None, 'name': source.original_name if source else '',
                              'asset_set': dataset, 'content_version': definition.get('source_content_version'),
                              'available': not reason, 'reason': reason}
            payload.append(item)
        return payload

    def apply_to_payload(self, module: str, payload: Dict[str, Any], project_id: str = '') -> Dict[str, Any]:
        from copy import deepcopy
        from flask_app.models.database import ProjectAsset
        from flask_app.services.user_scope import assert_owned
        result = deepcopy(payload)
        identifier = str(result.get('group_spec_id') or '').strip()
        if not identifier:
            return result
        if module not in {'profile', 'boxplot'}:
            raise ValidationError(message='此分析不支持项目分组方案，请使用模块中的分组设置。')
        project_id = str(project_id or result.get('project_id') or '').strip()
        spec = ProjectGroupSpec.query.filter_by(id=identifier, project_id=project_id).first()
        if spec is None:
            raise ValidationError(message='所选分组方案不属于当前项目或已删除。')
        assert_owned(spec.project, '项目')
        definition = deepcopy(spec.spec_json or {})
        source_id = str(definition.get('source_asset_id') or '')
        selected_path = str(result.get('datapoint_path') or result.get('profile_path') or '')
        if source_id and selected_path:
            from pathlib import Path
            from flask_app.routes.api_projects import _resolve_asset_path
            source = ProjectAsset.query.filter_by(id=source_id, project_id=project_id).first()
            if source is None:
                raise ValidationError(message='方案来源指标表已移除，请重新选择方案。')
            candidates = [source, *ProjectAsset.query.filter(ProjectAsset.project_id == project_id,
                ProjectAsset.metadata_json['source_asset_id'].as_string() == source_id).all()]
            if not any(Path(selected_path).resolve() == self._source_path(candidate) for candidate in candidates):
                raise ValidationError(message='分组方案来源版本与当前分析输入不同，请选择匹配的方案或指标表。')
        groups = definition.get('groups') or []
        order = [str(item.get('name') or item.get('label') or '') if isinstance(item, dict) else str(item) for item in groups]
        order = [item.strip() for item in order if item.strip()]
        if not order or len(order) != len(set(order)) or any(',' in item for item in order):
            raise ValidationError(message='分组方案的顺序不能为空或重复，分组名称不能包含英文逗号。')
        field = str(definition.get('group_field') or '').strip()
        if field:
            result.update(group_column=field, grouptype_fields=[field], classification_begin=field, classification_over=field)
        result['project_id'] = project_id
        result['group_order'] = ','.join(order)
        version = ProjectAsset.query.filter(ProjectAsset.project_id == project_id, ProjectAsset.asset_type == 'group_spec',
            ProjectAsset.metadata_json['spec_id'].as_string() == identifier,
            ProjectAsset.metadata_json['superseded'].as_boolean().isnot(True)).order_by(ProjectAsset.uploaded_at.desc()).first()
        result['group_spec_snapshot'] = {'id': spec.id, 'name': spec.name, 'project_id': project_id,
            'spec_json': definition, 'group_order': result['group_order'],
            'asset_id': version.id if version else None, 'content_version': (version.metadata_json or {}).get('content_version') if version else None}
        return result

    def delete_spec(self, spec_id: str) -> None:
        spec = ProjectGroupSpec.query.get(spec_id)
        if spec is None:
            raise ValidationError(message="Group specification not found", details={'group_spec_id': spec_id})
        db.session.delete(spec)
        db.session.commit()


_group_spec_service = GroupSpecService()


def get_group_spec_service() -> GroupSpecService:
    return _group_spec_service
