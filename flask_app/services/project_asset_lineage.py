"""Read saved replacement edges and references without inferring identity from filenames."""
from pathlib import Path

from flask_app.models.database import AnalysisJob, ProjectAsset, ProjectGroupSpec
from flask_app.services.background_job_service import TERMINAL_STATUSES
from flask_app.services.analysis_artifacts import asset_set_name


def pagination(page, page_size, total):
    return {'page': page, 'page_size': page_size, 'total': total,
            'total_pages': (total + page_size - 1) // page_size}


def asset_reference_kind(asset, value, *, resolved_target=None):
    """Keep deletion and reference views on the same exact-ID/path containment rule."""
    target = resolved_target if resolved_target is not None else Path(asset.storage_path).resolve()

    def walk(item):
        if isinstance(item, dict):
            values = item.values()
        elif isinstance(item, (list, tuple)):
            values = item
        elif isinstance(item, str):
            if item == asset.id:
                return 'asset_id'
            if Path(item).is_absolute():
                other = Path(item).resolve()
                if target == other or target in other.parents or other in target.parents:
                    return 'path'
            return ''
        else:
            return ''
        found = ''
        for entry in values:
            match = walk(entry)
            if match == 'asset_id':
                return match
            found = found or match
        return found

    return walk(value)


def iter_referencing_jobs(asset):
    from sqlalchemy import or_
    target = Path(asset.storage_path).resolve()
    query = AnalysisJob.query.filter_by(project_id=asset.project_id).filter(or_(
        AnalysisJob.job_type.is_(None), AnalysisJob.status.is_(None),
        AnalysisJob.job_type != 'input_validation', AnalysisJob.status.notin_(TERMINAL_STATUSES),
    )).with_entities(
        AnalysisJob.id, AnalysisJob.module, AnalysisJob.job_type, AnalysisJob.status,
        AnalysisJob.created_at, AnalysisJob.payload, AnalysisJob.result,
    ).order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
    for job in query.yield_per(100):
        match = asset_reference_kind(asset, [job.payload or {}, job.result or {}], resolved_target=target)
        if match:
            payload = job.payload or {}
            yield {'id': job.id, 'name': str(payload.get('_task_name') or payload.get('task_name') or payload.get('output_name') or ''),
                   'module': job.module, 'status': job.status, 'match': match,
                   'created_at': job.created_at.isoformat() if job.created_at else None,
                   'asset_set': str(payload.get('asset_set') or '')}


def referencing_schemes(asset):
    return ProjectGroupSpec.query.filter(ProjectGroupSpec.project_id == asset.project_id,
        ProjectGroupSpec.spec_json['source_asset_id'].as_string() == asset.id)


def _versions(asset, page, page_size):
    from flask_app.services.project_asset_service import ProjectAssetService
    # Only IDs/edges are read for the graph; potentially large validation reports are never loaded.
    rows = ProjectAsset.query.filter_by(project_id=asset.project_id).with_entities(
        ProjectAsset.id, ProjectAsset.metadata_json['superseded_by']).all()
    adjacency = {identifier: set() for identifier, _ in rows}
    missing = set()
    for identifier, successors in rows:
        for successor in successors if isinstance(successors, list) else []:
            if not isinstance(successor, str):
                continue
            if successor not in adjacency:
                missing.add((identifier, successor))
                continue
            adjacency[identifier].add(successor)
            adjacency[successor].add(identifier)
    connected, remaining = set(), [asset.id]
    while remaining:
        current = remaining.pop()
        if current in connected:
            continue
        connected.add(current)
        remaining.extend(adjacency.get(current, set()) - connected)
    query = ProjectAsset.query.filter(ProjectAsset.project_id == asset.project_id, ProjectAsset.id.in_(connected))
    total = query.count()
    rows = query.with_entities(ProjectAsset.id, ProjectAsset.original_name, ProjectAsset.asset_type,
        ProjectAsset.uploaded_at, ProjectAsset.metadata_json['content_version'].as_string(),
        ProjectAsset.metadata_json['superseded'].as_boolean(),
        ProjectAssetService.dataset_expression(),
        ProjectAsset.metadata_json['superseded_by']).order_by(ProjectAsset.uploaded_at.desc(), ProjectAsset.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    entries = [{'id': row[0], 'name': row[1], 'asset_type': row[2],
                'created_at': row[3].isoformat() if row[3] else None, 'content_version': row[4],
                'superseded': bool(row[5]), 'asset_set': row[6],
                'superseded_by': row[7] if isinstance(row[7], list) else []} for row in rows]
    return entries, pagination(page, page_size, total), sum(1 for before, _ in missing if before in connected)


def asset_lineage(asset, section='versions', page=1, page_size=20):
    if section == 'versions':
        entries, paging, missing = _versions(asset, page, page_size)
        return {'section': section, 'items': entries, 'pagination': paging, 'unavailable_links': missing}
    if section == 'groups':
        query = referencing_schemes(asset)
        total = query.count()
        specs = query.with_entities(ProjectGroupSpec.id, ProjectGroupSpec.name, ProjectGroupSpec.updated_at) \
            .order_by(ProjectGroupSpec.updated_at.desc(), ProjectGroupSpec.id.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
        entries = [{'id': spec.id, 'name': spec.name, 'created_at': spec.updated_at.isoformat() if spec.updated_at else None,
                    'asset_set': asset_set_name(asset)} for spec in specs]
    else:
        entries, total = [], 0
        for job in iter_referencing_jobs(asset):
            if (page - 1) * page_size <= total < page * page_size:
                entries.append(job)
            total += 1
    return {'section': section, 'items': entries, 'pagination': pagination(page, page_size, total)}
