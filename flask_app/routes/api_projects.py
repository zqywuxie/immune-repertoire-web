"""
Project, sample, and project-analysis integration APIs for the active Flask gateway.

The React application and retained server pages use this blueprint. The parallel
FastAPI implementation remains separate; preserve both existing task contracts.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from flask_app.services.project_result_catalog import (
    _mongo_result_to_asset, _result_identity, _asset_result_identity, project_result_page,
)
from flask_app.services.result_file_response import send_result_file
from flask import Blueprint, current_app, jsonify, redirect, request, send_file

from flask_app.exceptions import StorageError, ValidationError
from flask_app.models.database import ProjectAsset
from flask_app.services.group_spec_service import get_group_spec_service
from flask_app.services.integration_catalog_service import get_integration_catalog
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.project_analysis_bridge import get_project_analysis_bridge
from flask_app.services.project_asset_service import get_project_asset_service
from flask_app.services.project_service import get_project_service
from flask_app.services.sample_registry_service import get_sample_registry_service
from flask_app.services.storage_adapter import get_storage_adapter


project_api_bp = Blueprint('project_api', __name__, url_prefix='/api')


def _projects_root() -> Path:
    return Path(current_app.root_path) / 'data' / 'projects'


def _project_service():
    return get_project_service(_projects_root())


def _asset_service():
    return get_project_asset_service(_projects_root())


def _parse_csv_values(raw_value: str | None) -> List[str]:
    return [item.strip() for item in str(raw_value or '').split(',') if item.strip()]


def _pagination_args(default_page_size: int = 50, max_page_size: int = 200) -> tuple[int, int]:
    try:
        page = int(request.args.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.args.get('page_size', default_page_size))
    except (TypeError, ValueError):
        page_size = default_page_size
    page = max(1, page)
    page_size = min(max(1, page_size), max_page_size)
    return page, page_size


def _paginate_items(items: List[Dict[str, Any]], *, page: int, page_size: int) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], {
        'page': page,
        'page_size': page_size,
        'total': total,
        'total_pages': (total + page_size - 1) // page_size if total else 0,
    }


def _resolve_asset_path(asset: ProjectAsset) -> Path:
    metadata = asset.metadata_json or {}
    fallback_candidates = [
        metadata.get('storage_uri'),
        asset.storage_path,
        metadata.get('output_base'),
        metadata.get('report_path'),
        metadata.get('viewer_path'),
        metadata.get('file_path'),
    ]
    storage = get_storage_adapter()
    for candidate in fallback_candidates:
        fallback_path = storage.resolve(candidate)
        if fallback_path and fallback_path.exists():
            return fallback_path

    raise StorageError(message="Asset file is not available", details={'asset_id': asset.id})


def _preview_target(path: Path) -> Path:
    if path.is_file():
        return path
    for name in ('viewer.html', 'index.html', 'report.html', 'metadata.html'):
        candidate = path / name
        if candidate.exists() and candidate.is_file():
            return candidate
    for pattern in ('*.html', '*.htm', '*.png', '*.jpg', '*.jpeg', '*.pdf', '*.csv', '*.json'):
        candidate = next(path.glob(pattern), None)
        if candidate and candidate.exists() and candidate.is_file():
            return candidate
    raise StorageError(message="No previewable result file found", details={'storage_path': str(path)})


def _download_target(path: Path) -> Path:
    if path.is_file():
        return path
    for name in (
        'results.zip',
        'script_hub_results.zip',
        'pep_analysis_results.zip',
        'boxplot_results.zip',
        'topclone_results.zip',
        'ml_analysis_results.zip',
        'mait_nkt_results.zip',
    ):
        candidate = path / name
        if candidate.exists() and candidate.is_file():
            return candidate
    candidate = next(path.glob('*.zip'), None)
    if candidate and candidate.exists() and candidate.is_file():
        return candidate
    raise StorageError(message="No downloadable result archive found", details={'storage_path': str(path)})


def _result_redirect_url(asset: ProjectAsset, *, as_attachment: bool) -> str:
    if asset.asset_type != 'processed_result':
        return ''
    metadata = asset.metadata_json or {}
    keys = ('zip_url',) if as_attachment else ('viewer_url', 'report_url')
    for key in keys:
        url = str(metadata.get(key) or '').strip()
        if url:
            return url
    return ''


def _mimetype_for_path(path: Path, fallback: str | None) -> str | None:
    suffix = path.suffix.lower()
    if suffix in {'.html', '.htm'}:
        return 'text/html; charset=utf-8'
    if suffix == '.json':
        return 'application/json'
    if suffix == '.csv':
        return 'text/csv; charset=utf-8'
    if suffix == '.png':
        return 'image/png'
    if suffix in {'.jpg', '.jpeg'}:
        return 'image/jpeg'
    if suffix == '.pdf':
        return 'application/pdf'
    if suffix == '.zip':
        return 'application/zip'
    return fallback


def _get_project_asset(project_id: str, asset_id: str) -> ProjectAsset:
    asset = ProjectAsset.query.filter(
        ProjectAsset.id == asset_id,
        ProjectAsset.project_id == project_id,
    ).first()
    if asset is None:
        raise ValidationError(message="Project asset not found", details={'asset_id': asset_id})
    return asset


def _get_asset(asset_id: str) -> ProjectAsset:
    asset = ProjectAsset.query.filter(ProjectAsset.id == asset_id).first()
    if asset is None:
        raise ValidationError(message="Project asset not found", details={'asset_id': asset_id})
    return asset


def _send_asset_file(asset: ProjectAsset, *, as_attachment: bool):
    redirect_url = _result_redirect_url(asset, as_attachment=as_attachment)
    if redirect_url:
        return redirect(redirect_url)

    resolved_path = _resolve_asset_path(asset)
    target_path = _download_target(resolved_path) if as_attachment else _preview_target(resolved_path)
    return send_result_file(
        target_path,
        as_attachment=as_attachment,
        download_name=asset.original_name or target_path.name,
        mimetype=_mimetype_for_path(target_path, None if as_attachment else asset.mime_type),
    )


def _mongo_cached_usage_to_asset(doc: Dict[str, Any]) -> Dict[str, Any]:
    metadata = doc.get('metadata_json') if isinstance(doc.get('metadata_json'), dict) else {}
    merged_metadata = {
        **metadata,
        'source': 'mongodb',
        'mongo_id': str(doc.get('_id') or ''),
        'source_job_id': doc.get('source_job_id', ''),
        'source_result_signature': doc.get('source_result_signature') or metadata.get('source_result_signature', ''),
        'source_result_id': doc.get('source_result_id') or metadata.get('source_result_id', ''),
        'usage_scope': doc.get('usage_scope') or metadata.get('usage_scope', ''),
        'group_field': doc.get('group_field') or metadata.get('group_field', ''),
        'chains': doc.get('chains') or metadata.get('chains', []),
        'group_fields': doc.get('group_fields') or metadata.get('group_fields', []),
        'usage_types': doc.get('usage_types') or metadata.get('usage_types', {}),
    }
    cached_at = doc.get('cached_at')
    return {
        'id': str(doc.get('_id') or ''),
        'project_id': doc.get('project_id', ''),
        'asset_type': 'cached_usage',
        'original_name': doc.get('original_name') or f"cached_usage_{doc.get('source_job_id', '')}",
        'storage_path': doc.get('storage_path') or metadata.get('storage_path', ''),
        'mime_type': None,
        'size': 0,
        'metadata': merged_metadata,
        'metadata_json': merged_metadata,
        'uploaded_at': cached_at.isoformat() if hasattr(cached_at, 'isoformat') else None,
    }


def _merge_mongo_results(project_id: str, payload_assets: List[Dict[str, Any]], analysis_type: str = '') -> List[Dict[str, Any]]:
    seen, merged = set(), []
    for item in payload_assets:
        if item.get('asset_type') == 'processed_result':
            key = _asset_result_identity(item)
            if key in seen:
                continue
            seen.add(key)
        merged.append(item)
    try:
        from flask_app.services.mongo_service import get_project_results
        documents = get_project_results(project_id, analysis_type or None)
        for document in documents:
            item = _mongo_result_to_asset(document)
            key = _asset_result_identity(item)
            if key not in seen:
                seen.add(key)
                merged.append(item)
    except Exception:
        current_app.logger.warning("Failed to load Mongo results for project %s", project_id, exc_info=True)
    return merged


RESULT_IDENTITY_PROJECTION = {
    'project_id': 1, 'analysis_signature': 1, 'job_id': 1, 'output_base': 1,
    'metadata_json.analysis_signature': 1, 'metadata_json.job_id': 1, 'metadata_json.output_base': 1,
}


def _project_result_count(project_id: str) -> int:
    rows = _asset_service().asset_query(project_id, asset_type='processed_result').with_entities(
        ProjectAsset.metadata_json['analysis_signature'].as_string(),
        ProjectAsset.metadata_json['job_id'].as_string(), ProjectAsset.storage_path, ProjectAsset.id,
    ).all()
    seen = {_result_identity(*row) for row in rows}
    try:
        from flask_app.services.mongo_service import get_project_results
        for doc in get_project_results(project_id, projection=RESULT_IDENTITY_PROJECTION):
            seen.add(_asset_result_identity(_mongo_result_to_asset(doc)))
    except Exception:
        current_app.logger.warning('无法读取项目结果汇总：%s', project_id, exc_info=True)
    return len(seen)


def _project_result_counts(project_ids):
    if not project_ids:
        return {}
    seen = {identifier: set() for identifier in project_ids}
    rows = ProjectAsset.query.filter(
        ProjectAsset.project_id.in_(project_ids), ProjectAsset.asset_type == 'processed_result',
        ProjectAsset.metadata_json['superseded'].as_boolean().isnot(True),
    ).with_entities(ProjectAsset.project_id, ProjectAsset.metadata_json['analysis_signature'].as_string(),
        ProjectAsset.metadata_json['job_id'].as_string(), ProjectAsset.storage_path, ProjectAsset.id).all()
    for project_id, signature, job, path, identifier in rows:
        seen[project_id].add(_result_identity(signature, job, path, identifier))
    try:
        from flask_app.services.mongo_service import get_projects_results
        for doc in get_projects_results(project_ids, projection=RESULT_IDENTITY_PROJECTION):
            if doc.get('project_id') in seen:
                seen[doc['project_id']].add(_asset_result_identity(_mongo_result_to_asset(doc)))
    except Exception:
        current_app.logger.warning('无法读取项目列表结果汇总', exc_info=True)
    return {identifier: len(keys) for identifier, keys in seen.items()}


def _with_result_count(payload, count):
    payload['result_count'] = count
    if count:
        payload['asset_counts']['processed_result'] = count
    else:
        payload['asset_counts'].pop('processed_result', None)
    payload['asset_status']['has_results'] = bool(count)
    return payload


@project_api_bp.route('/projects', methods=['GET'])
def list_projects():
    from flask_app.services.project_catalog_service import project_catalog
    page, page_size = _pagination_args(default_page_size=24)
    return jsonify(project_catalog(
        page=page, page_size=page_size, search=request.args.get('q', ''),
        status=request.args.get('status', ''), sort=request.args.get('sort', 'created_desc'),
        name=request.args.get('name', ''), institution=request.args.get('institution', ''),
        cooperation_level=request.args.get('cooperation_level', ''),
        view=request.args.get('view', 'summary'), result_counts=_project_result_counts,
    ))


@project_api_bp.route('/projects/statistics', methods=['GET'])
def get_project_statistics():
    from flask_app.services.project_catalog_service import project_statistics
    return jsonify(project_statistics(_project_result_counts))


@project_api_bp.route('/projects', methods=['POST'])
def create_project():
    payload = request.get_json() or {}
    project = _project_service().create_project(
        name=payload.get('name', ''),
        institution=payload.get('institution', ''),
        cooperation_level=payload.get('cooperation_level', ''),
        description=payload.get('description', ''),
        status=payload.get('status', 'active'),
    )
    return jsonify(project.to_dict()), 201


@project_api_bp.route('/projects/<project_id>', methods=['GET'])
def get_project(project_id: str):
    project = _project_service().get_project(project_id)
    if request.args.get('summary_only', '').lower() in {'1', 'true'}:
        payload = _with_result_count(project.to_dict(summary_only=True), _project_result_count(project.id))
        if request.args.get('include_group_specs', 'true').lower() != 'false':
            payload['group_specs'] = get_group_spec_service().describe_specs(project.id)
        return jsonify(payload)
    assets = _asset_service().list_assets(project.id)
    group_specs = get_group_spec_service().list_specs(project.id)
    sample_records = get_sample_registry_service().list_samples(project_id=project.id)
    payload = project.to_dict()
    payload_assets = _merge_mongo_results(project.id, [asset.to_dict() for asset in assets])
    payload['assets'] = payload_assets
    payload['asset_counts'] = {
        **(payload.get('asset_counts') or {}),
        'processed_result': len([asset for asset in payload_assets if asset.get('asset_type') == 'processed_result']),
    }
    _with_result_count(payload, payload['asset_counts'].get('processed_result', 0))
    payload['group_specs'] = get_group_spec_service().describe_specs(project.id)
    payload['samples_preview'] = [sample.to_dict() for sample in sample_records[:20]]
    return jsonify(payload)


@project_api_bp.route('/projects/<project_id>', methods=['PATCH'])
def update_project(project_id: str):
    project = _project_service().get_project(project_id)
    payload = request.get_json() or {}
    updated = _project_service().update_project(project, payload)
    return jsonify(_with_result_count(updated.to_dict(), _project_result_count(project_id)))


@project_api_bp.route('/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    project = _project_service().get_project(project_id)
    _project_service().delete_project(project)
    return jsonify({'success': True})


@project_api_bp.route('/projects/<project_id>/datasets', methods=['GET'])
def list_project_datasets(project_id: str):
    _project_service().get_project(project_id)
    from flask_app.services.input_validation_cache import synchronize_validation_jobs
    synchronize_validation_jobs(project_id)
    return jsonify({'datasets': _asset_service().dataset_summaries(project_id)})


@project_api_bp.route('/projects/<project_id>/datasets', methods=['PUT'])
def update_project_dataset(project_id: str):
    project = _project_service().get_project(project_id)
    from flask_app.services.project_dataset_service import update_dataset
    return jsonify({'dataset':update_dataset(project, request.get_json(silent=True))})


@project_api_bp.route('/projects/<project_id>/input-selection', methods=['GET'])
def get_project_input_selection(project_id: str):
    _project_service().get_project(project_id)
    asset_set = request.args.get('asset_set', '').strip()
    if not asset_set:
        raise ValidationError(message='请先选择分析数据集。')
    from flask_app.services.input_validation_cache import synchronize_validation_jobs
    synchronize_validation_jobs(project_id)
    return jsonify(_asset_service().input_selection(project_id, asset_set))


@project_api_bp.route('/projects/<project_id>/input-selection/resolve', methods=['POST'])
def resolve_project_input_selection(project_id: str):
    _project_service().get_project(project_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError(message='请提供数据集和保存的输入标识。')
    from flask_app.services.input_validation_cache import synchronize_validation_jobs
    synchronize_validation_jobs(project_id)
    return jsonify(_asset_service().resolve_input_selection(project_id, payload.get('asset_set'), payload.get('asset_ids')))


@project_api_bp.route('/projects/<project_id>/assets', methods=['GET'])
def list_project_assets(project_id: str):
    project = _project_service().get_project(project_id)
    asset_type = request.args.get('asset_type', '').strip()
    page, page_size = _pagination_args()
    service = _asset_service()
    inputs_only = request.args.get('inputs_only', '').lower() in {'1', 'true'}
    view = request.args.get('view', 'full')
    if view not in {'full', 'selector'}:
        raise ValidationError(message='请选择有效的文件列表类型。')
    if view == 'selector' and not inputs_only:
        raise ValidationError(message='轻量候选列表只用于分析输入，请限定输入范围。')
    if inputs_only or asset_type in service.INPUT_TYPES:
        from flask_app.services.input_validation_cache import synchronize_validation_jobs
        synchronize_validation_jobs(project_id)
    if view == 'selector':
        return jsonify(service.input_candidate_page(project.id, asset_type=asset_type,
            asset_set=request.args.get('asset_set', '').strip(), search=request.args.get('q', '').strip(),
            validation_status=request.args.get('validation_status', '').strip(),
            include_superseded=request.args.get('include_superseded') == 'true', page=page, page_size=page_size))
    if inputs_only or (asset_type and asset_type != 'processed_result'):
        query = service.asset_query(project.id, asset_type=asset_type, inputs_only=inputs_only,
                                    asset_set=request.args.get('asset_set', '').strip(),
                                    search=request.args.get('q', '').strip(),
                                    validation_status=request.args.get('validation_status', '').strip(),
                                    include_superseded=request.args.get('include_superseded') == 'true')
        total = query.count()
        order = service.file_order(request.args.get('sort', 'uploaded_desc'))
        assets = query.order_by(*order).offset((page - 1) * page_size).limit(page_size).all()
        return jsonify({'assets': [asset.to_dict() for asset in assets], 'pagination': {
            'page': page, 'page_size': page_size, 'total': total,
            'total_pages': (total + page_size - 1) // page_size if total else 0}})
    if asset_type == 'processed_result':
        paged_assets, pagination = project_result_page(service.asset_query(project.id, asset_type=asset_type),
            project.id, page=page, page_size=page_size)
        return jsonify({'assets': paged_assets, 'pagination': pagination})
    assets = service.list_assets(project.id, asset_type=asset_type)
    payload_assets = [asset.to_dict() for asset in assets]
    if not asset_type or asset_type == 'processed_result':
        payload_assets = _merge_mongo_results(project.id, payload_assets)
        if asset_type == 'processed_result':
            payload_assets = [asset for asset in payload_assets if asset.get('asset_type') == 'processed_result']
    paged_assets, pagination = _paginate_items(payload_assets, page=page, page_size=page_size)
    return jsonify({'assets': paged_assets, 'pagination': pagination})


@project_api_bp.route('/projects/<project_id>/results', methods=['GET'])
def list_project_results(project_id: str):
    project = _project_service().get_project(project_id)
    analysis_type = request.args.get('analysis_type', '').strip()
    asset_set = request.args.get('asset_set', '').strip()
    job_id = request.args.get('job_id', '').strip()
    unscoped = request.args.get('unscoped', '').lower() in {'true', '1'}
    if unscoped and asset_set:
        raise ValidationError(message='请选择具体数据集或未记录数据集范围。')
    page, page_size = _pagination_args()
    query = _asset_service().asset_query(project.id, asset_type='processed_result')
    results, pagination, facets = project_result_page(query, project.id, analysis_type=analysis_type,
        asset_set=asset_set, job_id=job_id, unscoped=unscoped, page=page, page_size=page_size, include_facets=True)
    return jsonify({'success': True, 'results': results, 'pagination': pagination, 'facets': facets})


@project_api_bp.route('/projects/<project_id>/assets', methods=['POST'])
def upload_project_assets(project_id: str):
    project = _project_service().get_project(project_id)
    asset_type = str(request.form.get('asset_type') or '').strip()
    if not asset_type:
        raise ValidationError(message="asset_type is required", details={'field': 'asset_type'})

    files = request.files.getlist('files')
    relative_paths_raw = request.form.get('relative_paths', '[]')
    replace_existing = str(request.form.get('replace_existing') or '').strip().lower() in {'1', 'true', 'yes', 'on'}
    asset_set = str(request.form.get('asset_set') or '').strip()
    asset_metadata = {'asset_set': asset_set, 'group_label': asset_set} if asset_set else None

    try:
        relative_paths = json.loads(relative_paths_raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(message="relative_paths must be valid JSON") from exc

    if not isinstance(relative_paths, list):
        raise ValidationError(message="relative_paths must be a list")

    try:
        expected_versions = json.loads(request.form['expected_versions']) if 'expected_versions' in request.form else None
    except (ValueError, TypeError) as exc:
        raise ValidationError(message='更新范围格式无效，请重新核对。') from exc

    assets = _asset_service().upload_assets(
        project,
        asset_type=asset_type,
        file_storages=files,
        relative_paths=[str(item or '') for item in relative_paths],
        replace_existing=replace_existing,
        metadata=asset_metadata,
        operation_id=str(request.form.get('operation_id') or ''),
        expected_versions=expected_versions,
        require_expected_versions=replace_existing and asset_type in _asset_service().INPUT_TYPES,
    )
    return jsonify({'assets': [asset.to_dict() for asset in assets]}), 201


@project_api_bp.route('/projects/<project_id>/upload-impact', methods=['POST'])
def preview_upload_impact(project_id: str):
    _project_service().get_project(project_id)
    payload = request.get_json()
    if not isinstance(payload, dict):
        raise ValidationError(message='请提供有效的更新清单。')
    page, size = _pagination_args(default_page_size=20, max_page_size=100)
    return jsonify(_asset_service().upload_impact(project_id, payload.get('items'), page=page, page_size=size))


@project_api_bp.route('/projects/<project_id>/upload-operations/<operation_id>', methods=['GET'])
def get_upload_operation(project_id: str, operation_id: str):
    _project_service().get_project(project_id)
    assets = _asset_service().saved_upload_operation(project_id, operation_id)
    return jsonify({'saved': bool(assets), 'assets': [asset.to_dict() for asset in assets]})


@project_api_bp.route('/projects/<project_id>/cached-assets', methods=['GET'])
def list_cached_assets(project_id: str):
    project = _project_service().get_project(project_id)
    asset_type = request.args.get('asset_type', 'cached_usage').strip()
    assets = _asset_service().list_assets(project.id, asset_type=asset_type)
    payload_assets = [asset.to_dict() for asset in assets]
    if asset_type == 'cached_usage':
        try:
            from flask_app.services.mongo_service import get_cached_usage
            mongo_assets = [_mongo_cached_usage_to_asset(doc) for doc in get_cached_usage(project.id)]
            seen = {(item.get('asset_type'), item.get('storage_path'), (item.get('metadata') or {}).get('source_job_id')) for item in payload_assets}
            for item in mongo_assets:
                key = (item.get('asset_type'), item.get('storage_path'), (item.get('metadata') or {}).get('source_job_id'))
                if key not in seen:
                    seen.add(key)
                    payload_assets.append(item)
        except Exception:
            current_app.logger.warning("Failed to load Mongo cached usage for project %s", project.id, exc_info=True)
    return jsonify({'success': True, 'assets': payload_assets})


@project_api_bp.route('/projects/<project_id>/assets/register', methods=['POST'])
def register_project_asset_path(project_id: str):
    project = _project_service().get_project(project_id)
    payload = request.get_json() or {}
    asset_type = str(payload.get('asset_type') or '').strip()
    storage_path = str(payload.get('storage_path') or '').strip()
    original_name = str(payload.get('original_name') or '').strip() or None
    metadata_json = payload.get('metadata_json') or None

    if not asset_type:
        raise ValidationError(message="asset_type is required", details={'field': 'asset_type'})
    if not storage_path:
        raise ValidationError(message="storage_path is required", details={'field': 'storage_path'})
    storage_path = str(PathAccessService.validate_read_path(storage_path))

    asset = _asset_service().register_cached_asset(
        project,
        asset_type=asset_type,
        storage_path=storage_path,
        original_name=original_name,
        metadata=metadata_json,
        operation_id=str(payload.get('operation_id') or ''),
        operation_source_path=str(payload.get('storage_path') or '').strip(),
    )
    return jsonify(asset.to_dict()), 201


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>/download', methods=['GET'])
def download_project_asset(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    return _send_asset_file(asset, as_attachment=True)


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>/preview', methods=['GET'])
def preview_project_asset(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    return _send_asset_file(asset, as_attachment=False)

@project_api_bp.route('/assets/<asset_id>/download', methods=['GET'])
def download_asset(asset_id: str):
    asset = _get_asset(asset_id)
    _project_service().get_project(asset.project_id)
    return _send_asset_file(asset, as_attachment=True)


@project_api_bp.route('/assets/<asset_id>/preview', methods=['GET'])
def preview_asset(asset_id: str):
    asset = _get_asset(asset_id)
    _project_service().get_project(asset.project_id)
    return _send_asset_file(asset, as_attachment=False)


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>', methods=['GET'])
def get_project_asset_details(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    view = request.args.get('view', 'full')
    if view not in {'full', 'selector'}:
        raise ValidationError(message='请选择有效的文件读取类型。')
    if view == 'selector':
        return jsonify({'asset': _asset_service().input_candidate_detail(project_id, asset_id)})
    asset = _get_project_asset(project_id, asset_id)
    return jsonify({'asset': asset.to_dict()})


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>/lineage', methods=['GET'])
def get_project_asset_lineage(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    section = request.args.get('section', 'versions')
    if section not in {'versions', 'jobs', 'groups'}:
        raise ValidationError(message='请选择版本记录、引用任务或分组方案。')
    from flask_app.services.project_asset_lineage import asset_lineage
    page, size = _pagination_args(default_page_size=20, max_page_size=100)
    return jsonify(asset_lineage(asset, section, page, size))


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>', methods=['DELETE'])
def delete_project_asset(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    result = _asset_service().delete_asset(asset)
    return jsonify({'success': True, **(result or {})})


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>', methods=['PATCH'])
def update_project_asset(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    changes = (request.get_json() or {}).get('metadata_json')
    updated = _asset_service().update_asset_metadata(asset, changes)
    return jsonify({'success': True, 'asset': updated.to_dict()})


@project_api_bp.route('/assets/<asset_id>', methods=['PATCH', 'DELETE'])
def mutate_global_asset(asset_id: str):
    asset = _get_asset(asset_id)
    _project_service().get_project(asset.project_id)
    if request.method == 'DELETE':
        result = _asset_service().delete_asset(asset)
        return jsonify({'success': True, **(result or {})})
    updated = _asset_service().update_asset_metadata(asset, (request.get_json() or {}).get('metadata_json'))
    return jsonify({'success': True, 'asset': updated.to_dict()})


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>/validate', methods=['POST'])
def retry_asset_validation(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    from flask_app.services.input_validation_cache import schedule_uploaded_validation, KINDS
    from flask_app.models.database import AnalysisJob, db
    from flask_app.exceptions import AnalysisInProgressError
    if asset.asset_type not in KINDS:
        raise ValidationError(message='此文件不需要分析输入校验。')
    previous = db.session.get(AnalysisJob, (asset.metadata_json or {}).get('validation_job_id')) if (asset.metadata_json or {}).get('validation_job_id') else None
    if previous and previous.status in {'queued', 'running'}:
        raise AnalysisInProgressError(message='该文件正在校验，请等待完成。')
    asset.metadata_json = {**(asset.metadata_json or {}), 'validation': {'status': 'pending'}}
    db.session.commit()
    schedule_uploaded_validation([asset])
    return jsonify({'success': True, 'asset': asset.to_dict()})


@project_api_bp.route('/projects/<project_id>/input-samples', methods=['GET'])
def list_input_samples(project_id: str):
    _project_service().get_project(project_id)
    from flask_app.services.project_input_summary import input_sample_summary, projected_input_assets
    service = _asset_service()
    assets = projected_input_assets(service.asset_query(project_id, inputs_only=True, asset_set=request.args.get('asset_set', '').strip()))
    payload = input_sample_summary(assets, request.args.get('q', '').strip(), request.args.get('state', '').strip())
    registration_state = request.args.get('registration_state', '').strip()
    if registration_state not in {'', 'unregistered', 'registered', 'multiple'}:
        raise ValidationError(message='请选择有效的登记状态。')
    from flask_app.services.project_input_summary import add_registration_status
    if registration_state:
        # Read each scoped registration once instead of rescanning it for every 500 inputs.
        add_registration_status(project_id, payload['samples'], complete_scope=True)
        payload['samples'] = [row for row in payload['samples']
                              if row['registration']['status'] == registration_state]
    page, size = _pagination_args()
    payload['samples'], payload['pagination'] = _paginate_items(payload['samples'], page=page, page_size=size)
    if not registration_state:
        add_registration_status(project_id, payload['samples'])
    return jsonify(payload)


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>/table-preview', methods=['GET'])
def preview_project_input_table(project_id: str, asset_id: str):
    from flask_app.routes.api_script_hub._common import _robust_read_csv, _sanitize_nan
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    if asset.asset_type not in _asset_service().INPUT_TYPES:
        raise ValidationError(message='请选择分析输入文件。')
    root = _resolve_asset_path(asset).resolve()
    relative = request.args.get('file', '').strip()
    directory = root.is_dir()
    files = []
    include_files = request.args.get('include_files', 'true').lower() != 'false'
    if directory and include_files:
        from flask_app.services.directory_table_catalog import directory_table_names
        files = sorted(directory_table_names(root))
    page, size = _pagination_args()
    selected, pagination = _paginate_items(files, page=page, page_size=size)
    selected = [{'name': name, 'size': (root / name).stat().st_size} for name in selected]
    payload = {'directory': directory, 'files': selected, 'pagination': pagination, 'columns': [], 'rows': []}
    if directory and not relative:
        return jsonify(payload)
    target = root / relative if directory else root
    if relative and not directory:
        raise ValidationError(message='单文件资产不能选择目录子文件。')
    if directory and (Path(relative).is_absolute() or not target.resolve().is_relative_to(root)
                      or any(parent.is_symlink() for parent in [target, *target.parents] if parent != root and parent.is_relative_to(root))):
        raise ValidationError(message='只能预览已登记目录内的表格。')
    if not target.is_file() or not target.name.lower().endswith(('.csv', '.tsv', '.txt', '.csv.gz', '.tsv.gz', '.xlsx')):
        raise ValidationError(message='所选表格不存在或不支持预览。')
    try:
        separator = '\t' if target.name.lower().endswith(('.tsv', '.tsv.gz')) else ','
        frame = _robust_read_csv(target, nrows=5, dtype=str, keep_default_na=False, sep=separator)
    except Exception as error:
        raise ValidationError(message='表格无法读取，请检查文件格式。') from error
    payload.update(columns=frame.columns.tolist(), rows=frame.values.tolist(), row_count=len(frame), column_count=len(frame.columns))
    return jsonify(_sanitize_nan(payload))


@project_api_bp.route('/projects/<project_id>/assets/download', methods=['POST'])
def download_project_asset_selection(project_id: str):
    _project_service().get_project(project_id)
    from flask_app.services.project_input_summary import download_asset_selection
    identifiers = (request.get_json() or {}).get('asset_ids')
    if not isinstance(identifiers, list) or not identifiers or len(identifiers) > 200:
        raise ValidationError(message='请选择 1 至 200 个文件。')
    assets = [_get_project_asset(project_id, str(identifier)) for identifier in dict.fromkeys(identifiers)]
    return download_asset_selection(assets, _resolve_asset_path)


@project_api_bp.route('/projects/<project_id>/group-specs/<spec_id>', methods=['GET'])
def get_project_group_spec(project_id: str, spec_id: str):
    _project_service().get_project(project_id)
    from flask_app.models.database import ProjectGroupSpec
    spec = ProjectGroupSpec.query.filter_by(project_id=project_id, id=spec_id).first()
    if spec is None:
        raise ValidationError(message='分组方案不存在或不属于当前项目。')
    return jsonify({'group_spec': get_group_spec_service().describe_specs(project_id, specs=[spec])[0]})


@project_api_bp.route('/projects/<project_id>/group-specs/<spec_id>', methods=['DELETE'])
def delete_project_group_spec(project_id: str, spec_id: str):
    _project_service().get_project(project_id)
    from flask_app.models.database import ProjectGroupSpec
    _asset_service()._lock_input_project(project_id)
    spec = ProjectGroupSpec.query.filter_by(id=spec_id, project_id=project_id).populate_existing().with_for_update().first()
    if spec is None:
        raise ValidationError(message='分组方案不存在。')
    asset = ProjectAsset.query.filter(ProjectAsset.project_id == project_id, ProjectAsset.asset_type == 'group_spec',
                                      ProjectAsset.metadata_json['spec_id'].as_string() == spec_id,
                                      ProjectAsset.metadata_json['superseded'].as_boolean().isnot(True)).populate_existing().with_for_update().first()
    if asset:
        _asset_service().delete_asset(asset)
    else:
        get_group_spec_service().delete_spec(spec_id)
    return jsonify({'success': True})


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>/group-values', methods=['GET'])
def project_group_values(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    from flask_app.services.project_group_source import inspect_group_source
    result = inspect_group_source(asset, request.args.get('field', '').strip(), request.args.get('sheet_name') or None,
                                  include_samples=request.args.get('include_samples', 'true').lower() != 'false')
    return jsonify({'success': True, **result})


@project_api_bp.route('/projects/<project_id>/group-specs', methods=['GET'])
def list_project_group_specs(project_id: str):
    _project_service().get_project(project_id)
    view = request.args.get('view', 'full')
    if view == 'summary':
        page, size = _pagination_args(default_page_size=20, max_page_size=100)
        return jsonify(get_group_spec_service().catalog(project_id, page=page, page_size=size,
            asset_set=request.args.get('asset_set', '').strip(), search=request.args.get('q', '').strip()))
    if view != 'full':
        raise ValidationError(message='不支持的分组方案列表视图。')
    specs = get_group_spec_service().describe_specs(project_id,
        profile_path=request.args.get('profile_path', '').strip(), asset_set=request.args.get('asset_set', '').strip())
    return jsonify({'group_specs': specs})


@project_api_bp.route('/projects/<project_id>/group-specs', methods=['POST'])
def save_project_group_spec(project_id: str):
    project = _project_service().get_project(project_id)
    payload = request.get_json() or {}
    spec_json = payload.get('spec_json')
    if not isinstance(spec_json, dict):
        raise ValidationError(message='请提供有效的分组方案。', details={'field': 'spec_json'})
    if 'groups' in spec_json and (not isinstance(spec_json['groups'], list) or not spec_json['groups']):
        raise ValidationError(message='请至少填写一个分组。')

    asset = _asset_service().save_group_spec_asset(
        project,
        name=payload.get('name', 'default'),
        spec_json=spec_json,
        spec_id=str(payload.get('id') or '').strip(),
        expected_revision=payload.get('expected_revision'), require_expected_revision=True,
    )
    if request.args.get('view') == 'detail':
        from flask_app.models.database import ProjectGroupSpec, db
        spec = db.session.get(ProjectGroupSpec, asset.metadata_json['spec_id'])
        return jsonify({'group_spec': get_group_spec_service().describe_specs(project_id, specs=[spec])[0]}), 201
    return jsonify({
        'asset': asset.to_dict() if asset else None,
        'group_specs': get_group_spec_service().describe_specs(project_id),
    }), 201


@project_api_bp.route('/projects/<project_id>/analysis/<analysis_type>/prepare', methods=['POST'])
def prepare_project_analysis(project_id: str, analysis_type: str):
    project = _project_service().get_project(project_id)
    payload = get_project_analysis_bridge().prepare(project, analysis_type)
    return jsonify(payload)


@project_api_bp.route('/projects/<project_id>/analysis/<analysis_type>/register-result', methods=['POST'])
def register_project_analysis_result(project_id: str, analysis_type: str):
    project = _project_service().get_project(project_id)
    payload = request.get_json() or {}
    asset = _asset_service().register_analysis_result(
        project,
        analysis_type=analysis_type,
        job_id=str(payload.get('job_id') or ''),
        output_base=str(payload.get('output_base') or ''),
        report_path=str(payload.get('report_path') or ''),
        report_url=str(payload.get('report_url') or ''),
        metadata_url=str(payload.get('metadata_url') or ''),
        zip_url=str(payload.get('zip_url') or ''),
        viewer_url=str(payload.get('viewer_url') or ''),
        metadata=payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {},
    )
    return jsonify(asset.to_dict()), 201


def _sample_batch_service():
    from flask_app.services.sample_batch_service import SampleBatchService
    return SampleBatchService(_asset_service())


@project_api_bp.route('/projects/<project_id>/samples/batch/template', methods=['POST'])
def sample_batch_template(project_id: str):
    project = _project_service().get_project(project_id)
    payload = request.get_json() or {}
    if not isinstance(payload, dict):
        raise ValidationError(message='请指定登记模板范围。')
    buffer = _sample_batch_service().template(project, payload.get('asset_set'), payload.get('record_ids'))
    return send_file(buffer, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='样本批量登记模板.xlsx')


@project_api_bp.route('/projects/<project_id>/samples/batch/preview', methods=['POST'])
def sample_batch_preview(project_id: str):
    project = _project_service().get_project(project_id)
    service = _sample_batch_service()
    if request.files:
        uploaded = request.files.get('file')
        if uploaded is None:
            raise ValidationError(message='请选择登记表文件。')
        rows = service.read_file(uploaded)
        dataset = request.form.get('asset_set', '')
        allow = request.form.get('allow_unmatched', 'false')
        if allow not in ('true', 'false'):
            raise ValidationError(message='请明确是否允许补充未关联输入的登记。')
        allow_unmatched = allow == 'true'
        try:
            record_ids = json.loads(request.form['record_ids']) if 'record_ids' in request.form else None
        except (ValueError, TypeError) as error:
            raise ValidationError(message='所选登记范围格式无效，请重新选择。') from error
    else:
        payload = request.get_json() or {}
        if not isinstance(payload, dict):
            raise ValidationError(message='请提供有效的批量登记变更。')
        rows, dataset, allow_unmatched = payload.get('rows'), payload.get('asset_set'), payload.get('allow_unmatched', False)
        record_ids = payload.get('record_ids')
    return jsonify(service.preview(project, dataset, rows, allow_unmatched, record_ids=record_ids))


@project_api_bp.route('/projects/<project_id>/samples/batch/apply', methods=['POST'])
def sample_batch_apply(project_id: str):
    project = _project_service().get_project(project_id)
    payload = request.get_json() or {}
    if not isinstance(payload, dict):
        raise ValidationError(message='请提供有效的预览与保存行。')
    return jsonify(_sample_batch_service().apply(project, payload.get('preview_token'), payload.get('rows')))


@project_api_bp.route('/projects/<project_id>/samples/registration', methods=['GET', 'POST'])
def input_sample_registration(project_id: str):
    project = _project_service().get_project(project_id)
    payload = (request.get_json() or {}) if request.method == 'POST' else request.args
    sample_id = str(payload.get('sample_id') or '').strip()
    dataset = str(payload.get('asset_set') or '').strip()
    if not sample_id or len(sample_id) > 255 or not dataset or len(dataset) > 120:
        raise ValidationError(message='请指定数据集及原始样本编号。')
    from flask_app.services.project_input_summary import iter_input_sample_ids
    from flask_app.models.database import Project, SampleRecord, db
    if request.method == 'POST':
        db.session.query(Project).filter_by(id=project.id).with_for_update().one()
    identifiers = iter_input_sample_ids(_asset_service().asset_query(project.id, inputs_only=True, asset_set=dataset))
    if not any(identifier == sample_id for identifier in identifiers):
        raise ValidationError(message='当前数据集中没有识别到此样本，请先完成输入校验和映射。')
    from sqlalchemy import or_
    records = SampleRecord.query.filter(
        SampleRecord.project_id == project.id,
        SampleRecord.extra_metadata['asset_set'].as_string() == dataset,
        or_(SampleRecord.extra_metadata['input_sample_id'].as_string() == sample_id,
            SampleRecord.sample_id == sample_id),
    ).yield_per(100)
    matching = []
    for candidate in records:
        # A missing mapping falls back to the original ID; explicit null/other mappings do not.
        if (candidate.extra_metadata or {}).get('input_sample_id', candidate.sample_id) == sample_id:
            matching.append(candidate)
            if len(matching) == 2:
                break
    if len(matching) > 1:
        raise ValidationError(message='此编号对应多条登记，请在样本管理中确认，不会自动合并。')
    record = matching[0] if matching else None
    if request.method == 'GET':
        return jsonify({'sample': record.to_dict() if record else None, 'project_name': project.name})
    fields = payload.get('fields')
    if not isinstance(fields, dict) or set(fields) - {
        'sample_name', 'sequence_id', 'spices', 'institution', 'chain_flag', 'is_healthy',
        'illness', 'is_pe', 'contain_method', 'iso_tag', 'expected_values',
    }:
        raise ValidationError(message='请填写有效的补充登记信息。')
    try:
        if record is None:
            record = SampleRecord(project_id=project.id, sample_id=sample_id, sample_name=sample_id,
                                  extra_metadata={'asset_set': dataset, 'input_sample_id': sample_id, 'registration_kind': 'manual'})
            db.session.add(record)
        record = get_sample_registry_service().update_sample(record, fields, input_sample_id=sample_id)
        return jsonify({'sample': record.to_dict()}), 200
    except Exception:
        db.session.rollback()
        raise


@project_api_bp.route('/samples', methods=['GET'])
def list_samples():
    samples = get_sample_registry_service().list_samples(
        project_id=request.args.get('project_id', ''),
        asset_set=request.args.get('asset_set', ''),
        sample_id=request.args.get('sample_id', ''),
        input_sample_id=request.args.get('input_sample_id', ''),
        sample_name=request.args.get('sample_name', ''),
        search=request.args.get('q', ''),
        project_name=request.args.get('project_name', ''),
        institution=request.args.get('institution', ''),
        sequence_id=request.args.get('sequence_id', ''),
        contain_method=request.args.get('contain_method', ''),
        iso_tag=request.args.get('iso_tag', ''),
        spices=_parse_csv_values(request.args.get('spices')),
        chain_flag=_parse_csv_values(request.args.get('chain_flag')),
        is_healthy=request.args.get('is_healthy', ''),
        illness=_parse_csv_values(request.args.get('illness')),
        is_pe=request.args.get('is_pe', ''),
        page=_pagination_args()[0] if 'page' in request.args else None,
        page_size=_pagination_args()[1],
    )
    if isinstance(samples, tuple):
        rows, pagination = samples
        return jsonify({'samples': [sample.to_dict() for sample in rows], 'pagination': pagination})
    return jsonify({'samples': [sample.to_dict() for sample in samples]})


@project_api_bp.route('/samples/<sample_id>', methods=['PUT'])
def update_sample(sample_id: str):
    payload = request.get_json() or {}
    service = get_sample_registry_service()
    sample = service.get_sample(sample_id)
    updated = service.update_sample(sample, payload)
    return jsonify(updated.to_dict())


@project_api_bp.route('/samples/field-options', methods=['GET'])
def get_sample_field_options():
    from flask_app.services.sample_field_catalog import field_options_response
    return jsonify(field_options_response(request.args, get_sample_registry_service()))


@project_api_bp.route('/samples/export', methods=['GET', 'POST'])
def export_samples():
    from flask_app.services.sample_export_service import build_sample_export
    selected_ids = None
    if request.method == 'POST':
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get('filters'), dict):
            raise ValidationError(message='请提供有效的所选登记和筛选范围。')
        selected_ids = payload.get('record_ids')
        if not isinstance(selected_ids, list) or not 1 <= len(selected_ids) <= 5000 or any(
            not isinstance(identifier, str) or not identifier or len(identifier) > 36
            or identifier != identifier.strip() for identifier in selected_ids):
            raise ValidationError(message='请先选择 1 至 5000 条登记；空选择不会导出全部数据。')
        selected_ids = list(dict.fromkeys(selected_ids))
        arguments = {**payload['filters'], 'format':payload.get('format','xlsx'), 'columns':payload.get('columns','business')}
        if any(not isinstance(value, str) for value in arguments.values()):
            raise ValidationError(message='导出筛选条件格式无效。')
    else:
        arguments = request.args
    format = arguments.get('format', 'csv')
    columns = arguments.get('columns', 'legacy')
    if format not in {'csv', 'xlsx'} or columns not in {'legacy', 'business', 'technical'}:
        raise ValidationError(message='导出格式或字段范围不支持')
    query = get_sample_registry_service().sample_query(
        project_id=arguments.get('project_id', ''),
        asset_set=arguments.get('asset_set', ''),
        sample_id=arguments.get('sample_id', ''),
        input_sample_id=arguments.get('input_sample_id', ''),
        sample_name=arguments.get('sample_name', ''),
        search=arguments.get('q', ''),
        project_name=arguments.get('project_name', ''),
        institution=arguments.get('institution', ''),
        sequence_id=arguments.get('sequence_id', ''),
        contain_method=arguments.get('contain_method', ''),
        iso_tag=arguments.get('iso_tag', ''),
        spices=_parse_csv_values(arguments.get('spices')),
        chain_flag=_parse_csv_values(arguments.get('chain_flag')),
        is_healthy=arguments.get('is_healthy', ''),
        illness=_parse_csv_values(arguments.get('illness')),
        is_pe=arguments.get('is_pe', ''),
    )
    if selected_ids is not None:
        from flask_app.models.database import SampleRecord
        query = query.filter(SampleRecord.id.in_(selected_ids))
        if query.count() != len(selected_ids):
            raise ValidationError(message='部分所选登记已移除或不符合当前范围，请刷新列表后重新选择。')
    output, count = build_sample_export(query, format=format, columns=columns)
    filename = f"样本登记_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
    mime = 'text/csv; charset=utf-8' if format == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    try:
        response = send_file(output, mimetype=mime, as_attachment=True, download_name=filename)
    except BaseException:
        output.close()
        raise
    response.headers['X-Export-Count'] = str(count)
    response.headers['Cache-Control'] = 'no-store'
    response.call_on_close(output.close)
    return response


@project_api_bp.route('/pageresearch', methods=['POST'])
def django_compatible_sample_search():
    payload = request.get_json(silent=True) or request.form.to_dict(flat=True) or {}
    samples = get_sample_registry_service().list_samples(
        project_id=str(payload.get('project_id') or ''),
        sample_id=str(payload.get('sample_id') or ''),
        sample_name=str(payload.get('sample_name') or payload.get('sample') or ''),
        project_name=str(payload.get('project_name') or ''),
        institution=str(payload.get('institution') or ''),
        sequence_id=str(payload.get('sequence_id') or ''),
        contain_method=str(payload.get('contain_method') or ''),
        iso_tag=str(payload.get('iso_tag') or ''),
        spices=_parse_csv_values(payload.get('spices')),
        chain_flag=_parse_csv_values(payload.get('chain_flag')),
        is_healthy=str(payload.get('is_healthy') or ''),
        illness=_parse_csv_values(payload.get('illness')),
        is_pe=str(payload.get('is_pe') or ''),
    )
    return jsonify({
        'success': True,
        'count': len(samples),
        'results': [sample.to_dict() for sample in samples],
    })


@project_api_bp.route('/get_field_list_by_parm', methods=['GET'])
def django_compatible_field_list():
    field_name = request.args.get('parm', '') or request.args.get('field', '')
    payload = get_sample_registry_service().get_distinct_field_values(
        project_id=request.args.get('project_id', ''),
        asset_set=request.args.get('asset_set', ''),
        field_name=field_name,
    )
    values = next(iter(payload.values()), []) if payload else []
    return jsonify({'success': True, 'field': field_name, 'values': values})


@project_api_bp.route('/edit_sample_data', methods=['POST'])
def django_compatible_edit_sample():
    payload = request.get_json(silent=True) or request.form.to_dict(flat=True) or {}
    sample_id = str(payload.get('id') or payload.get('sample_record_id') or payload.get('sample_id') or '').strip()
    if not sample_id:
        raise ValidationError(message="sample_id is required", details={'field': 'sample_id'})
    service = get_sample_registry_service()
    sample = service.get_sample(sample_id)
    updated = service.update_sample(sample, payload)
    return jsonify({'success': True, 'sample': updated.to_dict()})


@project_api_bp.route('/downloadsamplefile', methods=['GET'])
def django_compatible_download_samples():
    return export_samples()


@project_api_bp.route('/integration/catalog', methods=['GET'])
def integration_catalog():
    return jsonify({'success': True, 'catalog': get_integration_catalog()})


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>/prepare-input', methods=['POST'])
def prepare_project_input(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    from flask_app.services.input_preparation import prepare_table
    mapping = prepare_table(asset, request.get_json() or {}, Path(current_app.root_path) / 'data' / 'projects')
    return jsonify({'success': True, 'asset_id': asset.id, 'input_preparation': mapping})


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>/input-schema', methods=['POST'])
def inspect_original_input_schema(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    if asset.asset_type not in {'profile','datapoint','transcriptome','expression','deconvolution','cibersort'}:
        raise ValidationError(message='请选择原始样本表、转录组或浸润表。')
    from flask_app.services.input_table_schema import inspect_table_schema
    input_preparation = (asset.metadata_json or {}).get('input_preparation') or {}
    requested_sheet = (request.get_json() or {}).get('sheet_name')
    if requested_sheet is None:
        requested_sheet = input_preparation.get('sheet_name')
    schema = inspect_table_schema(_resolve_asset_path(asset), requested_sheet)
    return jsonify({'success': True, 'asset_id':asset.id, 'input_preparation':input_preparation, **schema})


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>/prepare-input', methods=['DELETE'])
def reset_project_input(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = _get_project_asset(project_id, asset_id)
    from flask_app.services.input_preparation import reset_input_preparation
    changed = reset_input_preparation(asset)
    return jsonify({'success': True, 'changed': changed, 'asset_id':asset.id})
