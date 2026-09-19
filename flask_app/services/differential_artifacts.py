"""Owned, completed expression results available to functional enrichment."""
from pathlib import Path
from flask_app.exceptions import ValidationError
from flask_app.models.database import AnalysisJob, Project, ProjectAsset, db
from flask_app.services.user_scope import assert_owned
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.input_preparation import analysis_input_path


def differential_candidates(project_id, asset_set):
    assert_owned(db.session.get(Project, str(project_id)), '项目')
    if not asset_set:
        raise ValidationError(message='请选择来源数据集。')
    candidates = []
    for job in AnalysisJob.query.filter_by(project_id=str(project_id), module='volcano').all():
        payload, result = job.payload or {}, job.result or {}
        metadata = result.get('metadata') or {}
        if payload.get('asset_set') != asset_set or metadata.get('input_mode') != 'expression':
            continue
        reason, files = '', []
        root = None
        if job.status != 'completed':
            reason = '来源差异表达分析尚未成功完成。'
        elif not result.get('output_base'):
            reason = '来源结果目录未登记，请重新运行差异表达分析。'
        else:
            try:
                output = PathAccessService.validate_read_path(result['output_base'])
                root = output / 'DEG'
                if not root.is_dir() or not root.resolve().is_relative_to(output.resolve()):
                    raise ValueError('完整差异表达结果目录不存在。')
                for path in sorted(root.rglob('DEG_*.csv')):
                    if 'significant' in path.name.lower() or not path.is_file():
                        continue
                    if not path.resolve().is_relative_to(root.resolve()):
                        raise ValueError('差异表达文件超出来源目录。')
                    stat = path.stat()
                    files.append({'relative_path':path.relative_to(root).as_posix(), 'size':stat.st_size, 'mtime_ns':stat.st_mtime_ns})
                if not files:
                    raise ValueError('来源结果缺少完整差异表达表。')
                for ref in payload.get('source_assets') or []:
                    asset = db.session.get(ProjectAsset, ref.get('asset_id'))
                    if not asset or asset.project_id != job.project_id:
                        raise ValueError('来源输入已删除，请重新运行差异表达分析。')
                    current = Path(analysis_input_path(asset)).resolve()
                    stat = current.stat()
                    if str(current) != str(Path(ref['path']).resolve()) or stat.st_size != ref['size'] or stat.st_mtime_ns != ref['mtime_ns']:
                        raise ValueError('来源输入已改变，请重新运行差异表达分析。')
            except (OSError, ValueError, ValidationError) as error:
                reason = getattr(error, 'message', str(error))
        candidates.append({'id':job.id+':deg', 'job_id':job.id, 'project_id':str(project_id),
            'asset_set':asset_set, 'path':str(root) if root else '', 'metadata':metadata,
            'files':files, 'status':'unavailable' if reason else 'available', 'reason':reason,
            'created_at':job.created_at.isoformat() if job.created_at else None})
    return candidates


def resolve_differential_input(data):
    project_id, asset_set = str(data.get('project_id') or ''), str(data.get('asset_set') or '')
    if not project_id or not asset_set:
        raise ValidationError(message='复用差异表达结果时必须选择项目和数据集。')
    selected = [item for item in differential_candidates(project_id, asset_set)
                if item['id'] == data.get('upstream_artifact_id')]
    if len(selected) != 1:
        raise ValidationError(message='请选择当前项目和数据集的差异表达结果。')
    candidate = selected[0]
    if candidate['status'] != 'available':
        raise ValidationError(message=candidate['reason'])
    ref = {'artifact_id':candidate['id'], 'source_job_id':candidate['job_id'], 'project_id':project_id,
           'asset_set':asset_set, 'module':'go-kegg-enrichment', 'cache_type':'differential_expression',
           'path':candidate['path'], 'files':candidate['files']}
    data['upstream_input'] = ref
    return candidate
