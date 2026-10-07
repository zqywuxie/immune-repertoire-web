"""Scoped, paginated project catalog with projected and batched counts."""
from collections import Counter
from sqlalchemy import case, func, or_

from flask_app.exceptions import ValidationError
from flask_app.models.database import Project, ProjectAsset, ProjectGroupSpec, SampleRecord
from flask_app.services.project_asset_service import ProjectAssetService
from flask_app.services.user_scope import scope_query
from flask_app.services.project_input_summary import normalize_sample_identifier


SORTS = {
    'created_desc': (Project.created_at.desc(), Project.id.desc()),
    'updated_desc': (Project.updated_at.desc(), Project.id.desc()),
    'name_asc': (Project.name.asc(), Project.id.asc()),
    'name_desc': (Project.name.desc(), Project.id.desc()),
}


def _contains(column, value):
    # Search terms are literal, including '%' and '_' in project names.
    pattern = str(value).strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return column.ilike('%' + pattern + '%', escape='\\')


def _base_payload(project):
    return {key: getattr(project, key) for key in
            ('id', 'name', 'user_id', 'institution', 'cooperation_level', 'description', 'status')} | {
        'created_at': project.created_at.isoformat() if project.created_at else None,
        'updated_at': project.updated_at.isoformat() if project.updated_at else None,
    }


def _counts(project_ids, result_counts):
    """Read count columns and sample identifiers, never full asset metadata."""
    counts = {identifier: {'asset_counts': {}, 'historical_asset_count': 0,
                          'registered_sample_count': 0, 'group_spec_count': 0,
                          'input_samples': set(), 'datasets': set()}
              for identifier in project_ids}
    if not project_ids:
        return counts
    superseded = ProjectAsset.metadata_json['superseded'].as_boolean().is_(True)
    rows = ProjectAsset.query.filter(ProjectAsset.project_id.in_(project_ids)).with_entities(
        ProjectAsset.project_id, ProjectAsset.asset_type, func.count(ProjectAsset.id),
        func.sum(case((superseded, 1), else_=0)),
    ).group_by(ProjectAsset.project_id, ProjectAsset.asset_type).all()
    for identifier, kind, total, historical in rows:
        entry = counts[identifier]
        entry['historical_asset_count'] += int(historical or 0)
        if total - (historical or 0):
            entry['asset_counts'][kind] = int(total - (historical or 0))
    for model, key in ((SampleRecord, 'registered_sample_count'), (ProjectGroupSpec, 'group_spec_count')):
        for identifier, amount in model.query.filter(model.project_id.in_(project_ids)).with_entities(
            model.project_id, func.count(model.id)
        ).group_by(model.project_id).all():
            counts[identifier][key] = amount
    inputs = ProjectAsset.query.filter(
        ProjectAsset.project_id.in_(project_ids),
        ProjectAsset.asset_type.in_(ProjectAssetService.INPUT_TYPES),
        ProjectAsset.metadata_json['superseded'].as_boolean().isnot(True),
    ).with_entities(ProjectAsset.project_id, ProjectAssetService.dataset_expression(),
                    ProjectAsset.metadata_json['validation']['summary']['inputs']).all()
    for identifier, dataset, reports in inputs:
        entry = counts[identifier]
        entry['datasets'].add(dataset)
        for report in reports or []:
            entry['input_samples'].update((dataset, normalize_sample_identifier(sample)) for sample in report.get('samples', [])
                                          if normalize_sample_identifier(sample))
    for identifier, amount in result_counts(project_ids).items():
        assets = counts[identifier]['asset_counts']
        if amount:
            assets['processed_result'] = amount
        else:
            assets.pop('processed_result', None)
    return counts


def project_catalog(*, page=1, page_size=24, search='', status='', sort='created_desc',
                    name='', institution='', cooperation_level='', view='summary', result_counts):
    if sort not in SORTS:
        raise ValidationError(message='请选择有效的项目排序方式。')
    if view not in {'summary', 'selector'}:
        raise ValidationError(message='请选择有效的项目列表类型。')
    query = scope_query(Project.query, Project)
    if search.strip():
        query = query.filter(or_(_contains(Project.name, search), _contains(Project.institution, search)))
    for column, value in ((Project.name, name), (Project.institution, institution),
                          (Project.cooperation_level, cooperation_level)):
        if str(value).strip():
            query = query.filter(_contains(column, value))
    if status.strip():
        query = query.filter(Project.status == status.strip())
    total = query.count()
    projects = query.order_by(*SORTS[sort]).offset((page - 1) * page_size).limit(page_size).all()
    payloads = [_base_payload(project) for project in projects]
    if view == 'summary':
        counts = _counts([project.id for project in projects], result_counts)
        for item in payloads:
            entry = counts[item['id']]
            assets = entry['asset_counts']
            item.update({key: entry[key] for key in ('asset_counts', 'historical_asset_count',
                                                     'registered_sample_count', 'group_spec_count')})
            item.update(sample_count=entry['registered_sample_count'],
                        input_sample_count=len(entry['input_samples']), dataset_count=len(entry['datasets']),
                        result_count=assets.get('processed_result', 0),
                        has_datapoint=bool(assets.get('datapoint')), has_profile=bool(assets.get('profile')),
                        has_pep=bool(assets.get('pep')), has_sample_summary=bool(assets.get('sample_summary')),
                        has_group_spec=bool(assets.get('group_spec')))
            item['asset_status'] = {
                'has_profile': bool(assets.get('profile') or assets.get('datapoint')),
                'has_pep': bool(assets.get('pep')), 'has_transcriptome': bool(assets.get('transcriptome')),
                'has_deconvolution': bool(assets.get('deconvolution') or assets.get('cibersort')),
                'has_results': bool(assets.get('processed_result')), 'asset_set_count': len(entry['datasets']),
            }
    return {'projects': payloads, 'pagination': {
        'page': page, 'page_size': page_size, 'total': total,
        'total_pages': (total + page_size - 1) // page_size,
    }}


def project_statistics(result_counts):
    rows = scope_query(Project.query, Project).with_entities(Project.id, Project.status).all()
    entries = _counts([row.id for row in rows], result_counts)
    return {
        'project_count': len(rows), 'status_counts': dict(Counter(row.status for row in rows)),
        'pep_project_count': sum(bool(entry['asset_counts'].get('pep')) for entry in entries.values()),
        'file_count': sum(sum(entry['asset_counts'].values()) for entry in entries.values()),
        'result_count': sum(entry['asset_counts'].get('processed_result', 0) for entry in entries.values()),
        'input_sample_count': sum(len(entry['input_samples']) for entry in entries.values()),
        'registered_sample_count': sum(entry['registered_sample_count'] for entry in entries.values()),
        'dataset_count': sum(len(entry['datasets']) for entry in entries.values()),
        'group_spec_count': sum(entry['group_spec_count'] for entry in entries.values()),
    }
