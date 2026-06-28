"""
Project, sample, and project-analysis integration APIs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from flask import Blueprint, current_app, jsonify, request, send_file

from flask_app.exceptions import StorageError, ValidationError
from flask_app.models.database import ProjectAsset
from flask_app.services.group_spec_service import get_group_spec_service
from flask_app.services.integration_catalog_service import get_integration_catalog
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.project_analysis_bridge import get_project_analysis_bridge
from flask_app.services.project_asset_service import get_project_asset_service
from flask_app.services.project_service import get_project_service
from flask_app.services.sample_registry_service import get_sample_registry_service


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


def _mongo_result_to_asset(doc: Dict[str, Any]) -> Dict[str, Any]:
    metadata = doc.get('metadata_json') if isinstance(doc.get('metadata_json'), dict) else {}
    signature = str(doc.get('analysis_signature') or '').strip()
    analysis_type = str(doc.get('analysis_type') or '').strip()
    job_id = str(doc.get('job_id') or '').strip()
    merged_metadata = {
        **metadata,
        'source': 'mongodb',
        'mongo_id': str(doc.get('_id') or ''),
        'result_id': str(doc.get('_id') or ''),
        'analysis_type': analysis_type,
        'job_id': job_id,
        'analysis_signature': signature,
        'output_base': doc.get('output_base') or metadata.get('output_base', ''),
        'viewer_url': doc.get('viewer_url') or metadata.get('viewer_url', ''),
        'report_url': doc.get('viewer_url') or metadata.get('report_url', ''),
        'zip_url': doc.get('zip_url') or metadata.get('zip_url', ''),
        'input_assets': doc.get('input_assets') or [],
        'config_json': doc.get('config_json') or {},
    }
    created_at = doc.get('created_at') or doc.get('updated_at')
    return {
        'id': str(doc.get('_id') or ''),
        'project_id': doc.get('project_id', ''),
        'asset_type': 'processed_result',
        'original_name': f"{analysis_type}_{job_id or signature[:12] or 'result'}",
        'storage_path': doc.get('output_base') or metadata.get('output_base', ''),
        'mime_type': 'application/octet-stream',
        'size': 0,
        'metadata': merged_metadata,
        'metadata_json': merged_metadata,
        'uploaded_at': created_at.isoformat() if hasattr(created_at, 'isoformat') else None,
    }


def _merge_mongo_results(project_id: str, payload_assets: List[Dict[str, Any]], analysis_type: str = '') -> List[Dict[str, Any]]:
    try:
        from flask_app.services.mongo_service import get_project_results
        mongo_assets = [_mongo_result_to_asset(doc) for doc in get_project_results(project_id, analysis_type or None)]
    except Exception:
        current_app.logger.warning("Failed to load Mongo results for project %s", project_id, exc_info=True)
        return payload_assets

    seen = set()
    for item in payload_assets:
        metadata = item.get('metadata') or item.get('metadata_json') or {}
        key = (
            item.get('asset_type'),
            str(metadata.get('analysis_signature') or ''),
            str(metadata.get('job_id') or ''),
            item.get('storage_path') or '',
        )
        seen.add(key)

    for item in mongo_assets:
        metadata = item.get('metadata') or item.get('metadata_json') or {}
        key = (
            item.get('asset_type'),
            str(metadata.get('analysis_signature') or ''),
            str(metadata.get('job_id') or ''),
            item.get('storage_path') or '',
        )
        if key not in seen:
            seen.add(key)
            payload_assets.append(item)
    return payload_assets


@project_api_bp.route('/projects', methods=['GET'])
def list_projects():
    projects = _project_service().list_projects(
        name=request.args.get('name', ''),
        institution=request.args.get('institution', ''),
        cooperation_level=request.args.get('cooperation_level', ''),
    )
    return jsonify({
        'projects': [project.to_dict() for project in projects]
    })


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
    payload['result_count'] = payload['asset_counts'].get('processed_result', 0)
    payload['group_specs'] = [spec.to_dict() for spec in group_specs]
    payload['samples_preview'] = [sample.to_dict() for sample in sample_records[:20]]
    return jsonify(payload)


@project_api_bp.route('/projects/<project_id>', methods=['PATCH'])
def update_project(project_id: str):
    project = _project_service().get_project(project_id)
    payload = request.get_json() or {}
    updated = _project_service().update_project(project, payload)
    return jsonify(updated.to_dict())


@project_api_bp.route('/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    project = _project_service().get_project(project_id)
    _project_service().delete_project(project)
    return jsonify({'success': True})


@project_api_bp.route('/projects/<project_id>/assets', methods=['GET'])
def list_project_assets(project_id: str):
    project = _project_service().get_project(project_id)
    asset_type = request.args.get('asset_type', '').strip()
    page, page_size = _pagination_args()
    assets = _asset_service().list_assets(project.id, asset_type=asset_type)
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
    page, page_size = _pagination_args()
    assets = _merge_mongo_results(project.id, [], analysis_type=analysis_type)
    paged_assets, pagination = _paginate_items(assets, page=page, page_size=page_size)
    return jsonify({'success': True, 'results': paged_assets, 'pagination': pagination})


@project_api_bp.route('/projects/<project_id>/assets', methods=['POST'])
def upload_project_assets(project_id: str):
    project = _project_service().get_project(project_id)
    asset_type = str(request.form.get('asset_type') or '').strip()
    if not asset_type:
        raise ValidationError(message="asset_type is required", details={'field': 'asset_type'})

    files = request.files.getlist('files')
    relative_paths_raw = request.form.get('relative_paths', '[]')
    replace_existing = str(request.form.get('replace_existing') or '').strip().lower() in {'1', 'true', 'yes', 'on'}

    try:
        relative_paths = json.loads(relative_paths_raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(message="relative_paths must be valid JSON") from exc

    if not isinstance(relative_paths, list):
        raise ValidationError(message="relative_paths must be a list")

    assets = _asset_service().upload_assets(
        project,
        asset_type=asset_type,
        file_storages=files,
        relative_paths=[str(item or '') for item in relative_paths],
        replace_existing=replace_existing,
    )
    return jsonify({'assets': [asset.to_dict() for asset in assets]}), 201


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
    )
    return jsonify(asset.to_dict()), 201


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>/download', methods=['GET'])
def download_project_asset(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = ProjectAsset.query.filter(
        ProjectAsset.id == asset_id,
        ProjectAsset.project_id == project_id,
    ).first()
    if asset is None:
        raise ValidationError(message="Project asset not found", details={'asset_id': asset_id})

    target_path = Path(asset.storage_path)
    if not target_path.exists() or not target_path.is_file():
        metadata = asset.metadata_json or {}
        fallback_path = Path(str(metadata.get('report_path') or ''))
        if fallback_path.exists() and fallback_path.is_file():
            target_path = fallback_path
        else:
            raise StorageError(message="Asset file is not available for direct download", details={'asset_id': asset.id})

    return send_file(
        target_path,
        as_attachment=True,
        download_name=asset.original_name or target_path.name,
    )


@project_api_bp.route('/projects/<project_id>/assets/<asset_id>', methods=['DELETE'])
def delete_project_asset(project_id: str, asset_id: str):
    _project_service().get_project(project_id)
    asset = ProjectAsset.query.filter(
        ProjectAsset.id == asset_id,
        ProjectAsset.project_id == project_id,
    ).first()
    if asset is None:
        raise ValidationError(message="Project asset not found", details={'asset_id': asset_id})
    _asset_service().delete_asset(asset)
    return jsonify({'success': True})


@project_api_bp.route('/projects/<project_id>/group-specs', methods=['GET'])
def list_project_group_specs(project_id: str):
    _project_service().get_project(project_id)
    specs = get_group_spec_service().list_specs(project_id)
    return jsonify({'group_specs': [spec.to_dict() for spec in specs]})


@project_api_bp.route('/projects/<project_id>/group-specs', methods=['POST'])
def save_project_group_spec(project_id: str):
    project = _project_service().get_project(project_id)
    payload = request.get_json() or {}
    spec_json = payload.get('spec_json')
    if not isinstance(spec_json, dict):
        raise ValidationError(message="spec_json must be an object", details={'field': 'spec_json'})

    asset = _asset_service().save_group_spec_asset(
        project,
        name=payload.get('name', 'default'),
        spec_json=spec_json,
    )
    specs = get_group_spec_service().list_specs(project_id)
    return jsonify({
        'asset': asset.to_dict() if asset else None,
        'group_specs': [spec.to_dict() for spec in specs],
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


@project_api_bp.route('/samples', methods=['GET'])
def list_samples():
    samples = get_sample_registry_service().list_samples(
        project_id=request.args.get('project_id', ''),
        sample_id=request.args.get('sample_id', ''),
        sample_name=request.args.get('sample_name', ''),
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
    )
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
    service = get_sample_registry_service()
    payload = service.get_distinct_field_values(
        project_id=request.args.get('project_id', ''),
        field_name=request.args.get('field', ''),
    )
    return jsonify({'fields': payload})


@project_api_bp.route('/samples/export', methods=['GET'])
def export_samples():
    samples = get_sample_registry_service().list_samples(
        project_id=request.args.get('project_id', ''),
        sample_id=request.args.get('sample_id', ''),
        sample_name=request.args.get('sample_name', ''),
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
    )
    buffer = get_sample_registry_service().export_samples_csv(samples)
    filename = f"samples_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(buffer, mimetype='text/csv', as_attachment=True, download_name=filename)


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
