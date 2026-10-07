"""Project results: merge lightweight identities, hydrate only the requested page."""
from typing import Any, Dict
from collections import Counter
from sqlalchemy import func

from flask import current_app
from flask_app.exceptions import StorageError
from flask_app.models.database import ProjectAsset

SCOPE_KEYS = ('asset_set', 'dataset', 'data_set', 'group_label', 'group')

def saved_result_dataset(doc):
    metadata = doc.get('metadata_json') or {}
    for source in (doc, metadata):
        for key in SCOPE_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip(): return value.strip()
    for source in (doc.get('config_json'), metadata.get('config_json')):
        if isinstance(source, dict):
            value = source.get('asset_set')
            if isinstance(value, str) and value.strip(): return value.strip()
    return ''

def result_scope_expression():
    return func.coalesce(*[func.nullif(func.trim(ProjectAsset.metadata_json[key].as_string()), '') for key in SCOPE_KEYS],
        func.nullif(func.trim(ProjectAsset.metadata_json['config_json']['asset_set'].as_string()), ''), '')

def _mongo_result_to_asset(doc: Dict[str, Any]) -> Dict[str, Any]:
    metadata = doc.get('metadata_json') if isinstance(doc.get('metadata_json'), dict) else {}
    signature = str(doc.get('analysis_signature') or metadata.get('analysis_signature') or '').strip()
    analysis_type = str(doc.get('analysis_type') or metadata.get('analysis_type') or '').strip()
    job_id = str(doc.get('job_id') or metadata.get('job_id') or '').strip()
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
        'input_assets': doc.get('input_assets', metadata.get('input_assets')) or [],
        'config_json': doc.get('config_json', metadata.get('config_json')) or {},
    }
    if saved_result_dataset(doc):
        merged_metadata['asset_set'] = saved_result_dataset(doc)
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
        'preview_url': merged_metadata.get('viewer_url') or merged_metadata.get('report_url') or '',
        'download_url': merged_metadata.get('zip_url') or '',
        'uploaded_at': created_at.isoformat() if hasattr(created_at, 'isoformat') else None,
    }


def _result_identity(signature, job_id, path, identifier=''):
    # A job can have multiple products. Missing paths do not prove two records are identical.
    return (str(signature or ''), str(job_id or ''), str(path or f'id:{identifier}'))


def _asset_result_identity(item):
    metadata = item.get('metadata') or item.get('metadata_json') or {}
    return _result_identity(metadata.get('analysis_signature'), metadata.get('job_id'),
                            item.get('storage_path'), item.get('id'))


IDENTITY_PROJECTION = {
    'project_id': 1, 'analysis_signature': 1, 'job_id': 1, 'output_base': 1,
    'metadata_json.analysis_signature': 1, 'metadata_json.job_id': 1, 'metadata_json.output_base': 1,
    'created_at': 1, 'updated_at': 1, 'analysis_type': 1, 'metadata_json.analysis_type': 1,
    'config_json.asset_set': 1, 'metadata_json.config_json.asset_set': 1,
    **{key: 1 for key in SCOPE_KEYS}, **{'metadata_json.' + key: 1 for key in SCOPE_KEYS},
}

def project_result_page(query, project_id, *, analysis_type='', asset_set='', job_id='', unscoped=False,
                        page=1, page_size=50, include_facets=False):
    # Keep exact cross-store identity and SQL precedence before applying filters.
    candidates = {}
    rows = query.with_entities(ProjectAsset.id, ProjectAsset.uploaded_at, ProjectAsset.storage_path,
        ProjectAsset.metadata_json['analysis_signature'].as_string(),
        ProjectAsset.metadata_json['job_id'].as_string(), ProjectAsset.metadata_json['analysis_type'].as_string(),
        result_scope_expression()).order_by(ProjectAsset.uploaded_at.desc(), ProjectAsset.id.desc()).yield_per(500)
    for identifier, uploaded, path, signature, task, kind, dataset in rows:
        key = _result_identity(signature, task, path, identifier)
        candidates.setdefault(key, ('sql', identifier, uploaded.isoformat() if uploaded else '', identifier,
                                    str(kind or '').strip(), dataset or '', str(task or '').strip()))
    try:
        from flask_app.services.mongo_service import get_project_results
        for doc in get_project_results(project_id, projection=IDENTITY_PROJECTION):
            item = _mongo_result_to_asset(doc)
            key = _asset_result_identity(item)
            candidate = ('mongo', item['id'], item['uploaded_at'] or '', doc.get('_id'),
                         item['metadata']['analysis_type'], saved_result_dataset(doc), item['metadata']['job_id'])
            previous = candidates.get(key)
            if previous is None or (previous[0] == 'mongo' and (candidate[2], candidate[1]) > (previous[2], previous[1])):
                candidates[key] = candidate
        all_results = list(candidates.values())
        datasets = Counter(item[5] for item in all_results if item[5])
        types = Counter(item[4] for item in all_results if item[4])
        facets = {'datasets': [{'name':name,'count':count} for name,count in sorted(datasets.items())],
                  'analysis_types': [{'name':name,'count':count} for name,count in sorted(types.items())],
                  'unscoped_count':sum(not item[5] for item in all_results)}
        matched = [item for item in all_results if (not analysis_type or item[4] == analysis_type)
                   and (not asset_set or item[5] == asset_set) and (not unscoped or not item[5])
                   and (not job_id or item[6] == job_id)]
        total = len(matched)
        ordered = sorted(matched, key=lambda item: (item[2], item[1]), reverse=True)
        selected = ordered[(page-1)*page_size:page*page_size]
        sql_ids = [item[1] for item in selected if item[0] == 'sql']
        mongo_ids = [item[3] for item in selected if item[0] == 'mongo']
        hydrated = {}
        if sql_ids:
            for asset in query.filter(ProjectAsset.id.in_(sql_ids)).all():
                hydrated[('sql', asset.id)] = asset.to_dict()
        if mongo_ids:
            for doc in get_project_results(project_id, identifiers=mongo_ids):
                item = _mongo_result_to_asset(doc)
                hydrated[('mongo', item['id'])] = item
        results = [hydrated[(item[0],item[1])] for item in selected if (item[0],item[1]) in hydrated]
        pagination = {'page':page,'page_size':page_size,'total':total,
                      'total_pages':(total+page_size-1)//page_size if total else 0}
        return (results, pagination, facets) if include_facets else (results, pagination)
    except Exception as error:
        current_app.logger.warning('无法完整读取项目结果：%s', project_id, exc_info=True)
        raise StorageError(message='分析结果暂时无法完整读取，请重试。') from error
