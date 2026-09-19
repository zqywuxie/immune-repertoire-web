"""Resolve reusable analysis outputs within an owned project and data set."""
from pathlib import Path
from urllib.parse import quote

from flask_app.exceptions import ValidationError
from flask_app.models.database import AnalysisJob, Project, ProjectAsset, db
from flask_app.services.user_scope import assert_owned


def asset_set_name(asset):
    meta = asset.metadata_json or {}
    return str(next((meta[key] for key in ('asset_set', 'dataset', 'data_set', 'group_label', 'group') if meta.get(key)), 'Set1')).strip() or 'Set1'


def _path(value):
    return str(Path(str(value)).resolve()) if value else ''


def capture_input_lineage(project_id, input_paths, asset_set=''):
    from flask_app.services.input_preparation import analysis_input_path
    assets = ProjectAsset.query.filter_by(project_id=project_id).all()
    inputs = {_path(item.get('path')) for item in input_paths if item.get('path')}
    refs = []
    for asset in assets:
        if asset.asset_type not in {'pep', 'profile', 'datapoint', 'transcriptome', 'expression', 'cibersort', 'deconvolution'}:
            continue
        if _path(analysis_input_path(asset)) not in inputs or (asset_set and asset_set_name(asset) != asset_set):
            continue
        path = Path(analysis_input_path(asset))
        if not path.exists():
            continue
        stat = path.stat()
        refs.append({'asset_id': asset.id, 'asset_set': asset_set_name(asset), 'path': _path(path),
                     'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns})
    names = {ref['asset_set'] for ref in refs}
    return {'asset_set': asset_set or (next(iter(names)) if len(names) == 1 else ''), 'source_assets': refs}


def scoped_pep_candidates(project_id, asset_set, cache_type=''):
    # Import lazily: existing routes retain their legacy candidate adapters.
    from flask_app.routes.api_script_hub.tasks_results import _build_pep_cache_candidates, _pep_cache_type_filter
    project = db.session.get(Project, str(project_id))
    assert_owned(project, '项目')
    assets = ProjectAsset.query.filter_by(project_id=str(project_id)).all()
    jobs = {job.id: job for job in AnalysisJob.query.filter_by(project_id=str(project_id)).all()}
    accepted = _pep_cache_type_filter(cache_type)
    result = []
    seen = set()
    for raw in _build_pep_cache_candidates(str(project_id)):
        if accepted and raw.get('cache_type') not in accepted:
            continue
        candidate = dict(raw)
        path = Path(str(candidate.get('path') or '')).resolve()
        job_id = str(candidate.get('job_id') or '')
        job = jobs.get(job_id)
        # Old manifests used report IDs, while SQL assets store the task ID.
        if job is None:
            for asset in assets:
                if asset.asset_type != 'cached_usage':
                    continue
                meta = asset.metadata_json or {}
                base = meta.get('pep_output_base') or meta.get('output_base')
                if base and path.is_relative_to(Path(base).resolve()):
                    job = jobs.get(str(meta.get('source_job_id') or ''))
                    if job is not None:
                        job_id = job.id
                        candidate['profile_path'] = meta.get('profile_path') or candidate.get('profile_path')
                        break
        payload = job.payload or {} if job else {}
        source_assets = payload.get('source_assets') or []
        dataset = str(payload.get('asset_set') or candidate.get('asset_set') or '')
        if not dataset:
            paths = { _path(item.get('path')) for item in payload.get('input_assets', []) if item.get('path') }
            if candidate.get('profile_path'):
                paths.add(_path(candidate['profile_path']))
            names = {asset_set_name(asset) for asset in assets if asset.asset_type in {'profile', 'datapoint'} and _path(asset.storage_path) in paths}
            if len(names) == 1:
                dataset = next(iter(names))
        if dataset and asset_set and dataset != asset_set:
            continue
        reason = ''
        if not job or not dataset:
            reason = '旧结果的来源任务或数据集无法确认，请重新运行前置分析。'
        elif job.status != 'completed':
            reason = '来源分析尚未成功完成。'
        elif not path.exists() or candidate.get('status') == 'missing':
            reason = '结果文件已不存在，请重新运行来源分析。'
        elif candidate.get('cache_type') != 'profile' and (not (job.result or {}).get('output_base') or not path.is_relative_to(Path(job.result['output_base']).resolve())):
            reason = '文件不属于来源任务登记的结果目录。'
        elif source_assets:
            for ref in source_assets:
                asset = next((item for item in assets if item.id == ref.get('asset_id')), None)
                source_path = Path(str(ref.get('path') or ''))
                from flask_app.services.input_preparation import analysis_input_path
                try:
                    current_source = analysis_input_path(asset) if asset else ''
                except ValidationError as error:
                    reason = error.message
                    break
                if not asset or _path(current_source) != _path(source_path) or not source_path.exists():
                    reason = '来源输入已替换或删除，请重新运行前置分析。'
                    break
                stat = source_path.stat()
                if stat.st_size != ref.get('size') or stat.st_mtime_ns != ref.get('mtime_ns'):
                    reason = '来源输入已修改，请重新运行前置分析。'
                    break
        if candidate.get('cache_type') in {'vj_usage', 'umapin_table'}:
            feature_ready = supports_feature_groups(candidate) if not reason else False
            targets = list(candidate.get('available_for') or [])
            if not feature_ready:
                candidate['available_for'] = [target for target in targets if target != 'umapin']
                if cache_type == 'umapin' and not reason:
                    reason = '该产物没有特征降维需要的分组列，请选择带分组的汇总特征表。'
            else:
                candidate['available_for'] = list(dict.fromkeys([*targets, 'umapin']))
        artifact_id = f"{job_id}:{candidate['cache_type']}:{quote(str(path), safe='')}"
        if artifact_id in seen:
            continue
        seen.add(artifact_id)
        result.append({**candidate, 'id': artifact_id, 'artifact_id': artifact_id, 'job_id': job_id,
                       'asset_set': dataset, 'project_id': str(project_id), 'reason': reason,
                       'status': 'unavailable' if reason else 'available',
                       'source_task_name': str(payload.get('task_name') or payload.get('_task_name') or '克隆共享分析')})
    return sorted(result, key=lambda item: (item['status'] != 'available', str(item.get('created_at') or '')), reverse=False)


def supports_feature_groups(candidate):
    """Use header-only checks for the Category column required by feature UMAP."""
    from flask_app.services.umapin_service import UmapinService, _try_read_csv
    path = Path(str(candidate.get('path') or ''))
    paths = [path] if path.is_file() else [
        file for directory in UmapinService._candidate_usage_dirs(path)
        for file in sorted(directory.glob('*.csv')) if file.is_file() and file.resolve().is_relative_to(path.resolve())
    ]
    for file in paths:
        try:
            columns = list(_try_read_csv(file, nrows=0).columns)
        except (OSError, ValueError, UnicodeError):
            continue
        if 'Category' in columns and len(columns) > columns.index('Category') + 1:
            return True
    return False


def downstream_spec(module, data):
    if module == 'volcano' and data.get('input_mode') in {'usage', 'vj_usage'}:
        return 'volcano', 'data_dir'
    if module == 'umapin':
        return 'umapin', 'data_path'
    if module == 'ml-analysis' and data.get('mode') in {'vj', 'profile_vj'}:
        return 'ml-vj', 'usage_path'
    if module == 'mait-nkt' and data.get('tra_source') == 'pep_analysis':
        return 'mait-nkt', 'tra_path'
    return None


def resolve_upstream_input(module, data):
    data.pop("upstream_input", None)
    spec = downstream_spec(module, data)
    if not spec:
        return None
    project_id = str(data.get('project_id') or '').strip()
    dataset = str(data.get('asset_set') or '').strip()
    artifact_id = str(data.get('upstream_artifact_id') or '').strip()
    # Legacy path-based calls remain supported when no project dataset was specified.
    if not project_id or not dataset:
        if artifact_id:
            raise ValidationError(message='选择上游结果时必须指定项目和数据集。')
        return None
    cache_type, field = spec
    candidates = scoped_pep_candidates(project_id, dataset, cache_type)
    selected = [c for c in candidates if c['id'] == artifact_id] if artifact_id else []
    if not artifact_id and data.get(field):
        selected = [c for c in candidates if _path(c['path']) == _path(data[field])]
    if not selected and not artifact_id and not data.get(field):
        selected = [c for c in candidates if c['status'] == 'available']
    if len(selected) != 1:
        raise ValidationError(message='请选择当前数据集的一项可用前置分析结果。', details={'field': 'upstream_artifact_id'})
    candidate = selected[0]
    if candidate['status'] != 'available':
        raise ValidationError(message=candidate['reason'])
    requested_chain = str(data.get('chain') or '').upper()
    if requested_chain and candidate.get('chains') and requested_chain not in candidate['chains']:
        raise ValidationError(message='所选结果不包含当前分析需要的链。')
    group_field = str(data.get('group_field') or '').strip()
    if group_field and candidate.get('group_fields') and group_field not in candidate['group_fields']:
        raise ValidationError(message='所选结果未按当前分组字段生成，请选择匹配的前置结果。')
    data[field] = candidate['path']
    data['source_job_id'] = candidate['job_id']
    data['upstream_artifact_id'] = candidate['id']
    ref = {'artifact_id': candidate['id'], 'source_job_id': candidate['job_id'], 'project_id': project_id,
           'asset_set': dataset, 'module': module, 'cache_type': cache_type, 'path': candidate['path'],
           'input_mode': data.get('input_mode'), 'mode': data.get('mode'), 'tra_source': data.get('tra_source'),
           'chain': data.get('chain'), 'group_field': data.get('group_field')}
    data['upstream_input'] = ref
    return ref


def revalidate_job_upstream(job):
    ref = (job.get('payload') or {}).get('upstream_input')
    if not ref:
        return
    data = {**ref, 'upstream_artifact_id': ref['artifact_id']}
    if ref.get('cache_type') == 'differential_expression':
        from flask_app.services.differential_artifacts import resolve_differential_input
        candidate = resolve_differential_input(data)
        if candidate['path'] != ref['path'] or candidate['files'] != ref.get('files'):
            raise ValidationError(message='差异表达结果已改变，请重新选择来源并提交分析。')
        return
    resolved = resolve_upstream_input(ref['module'], data)
    if not resolved or resolved['path'] != ref['path']:
        raise ValidationError(message='前置分析结果已改变，请重新选择。')
