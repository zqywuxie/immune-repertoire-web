"""Project-owned GO-BP GSEA sources for infiltration pathway concordance."""
from pathlib import Path

import numpy as np
import pandas as pd

from flask_app.exceptions import ValidationError
from flask_app.models.database import AnalysisJob, Project, ProjectAsset, db
from flask_app.services.input_preparation import analysis_input_path
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.user_scope import assert_owned
from flask_app.services.volcano_service import VolcanoService


GO_BP_TERMS = (
    'GO:0002250', 'GO:0046649', 'GO:0042110', 'GO:0042113', 'GO:0006959',
    'GO:0045087', 'GO:0002274', 'GO:0006954', 'GO:0019221', 'GO:0006956',
)


def validate_go_bp_table(path):
    frame = pd.read_csv(path, dtype={'ID': str})
    required = {'ID', 'Description', 'setSize', 'NES', 'pvalue', 'p.adjust', 'qvalue'}
    if not required.issubset(frame.columns):
        raise ValidationError(message='来源不是完整 GO-BP GSEA 表，缺少必要统计字段。')
    if frame['ID'].duplicated().any():
        raise ValidationError(message='来源 GO 通路编号重复，请重新生成富集结果。')
    missing = set(GO_BP_TERMS) - set(frame['ID'])
    if missing:
        raise ValidationError(message='来源缺少预定义通路：' + '、'.join(sorted(missing)) + '。请检查基因覆盖与完整富集输出。')
    selected = frame.set_index('ID').loc[list(GO_BP_TERMS)]
    values = selected[['setSize', 'NES', 'pvalue', 'p.adjust']].apply(pd.to_numeric, errors='coerce')
    if not np.isfinite(values.to_numpy()).all() or (values['setSize'] <= 0).any():
        raise ValidationError(message='来源通路统计包含缺失或非法数值。')
    if ((values[['pvalue', 'p.adjust']] < 0) | (values[['pvalue', 'p.adjust']] > 1)).any().any():
        raise ValidationError(message='来源通路的概率值不在零至一之间。')
    return selected.reset_index()


def _check_lineage(job):
    payload = job.payload or {}
    if payload.get('upstream_input'):
        from flask_app.services.analysis_artifacts import revalidate_job_upstream
        revalidate_job_upstream({'payload': payload})
    refs = payload.get('source_assets') or []
    if not refs and not payload.get('upstream_input'):
        raise ValidationError(message='来源输入记录不完整，请重新运行富集分析。')
    for ref in refs:
        asset = db.session.get(ProjectAsset, ref.get('asset_id'))
        if not asset or asset.project_id != job.project_id:
            raise ValidationError(message='来源输入已删除或不属于当前项目。')
        path = Path(analysis_input_path(asset)).resolve()
        stat = path.stat()
        if str(path) != str(Path(ref['path']).resolve()) or stat.st_size != ref['size'] or stat.st_mtime_ns != ref['mtime_ns']:
            raise ValidationError(message='来源输入已改变，请重新运行富集分析。')


def pathway_candidates(project_id, asset_set):
    assert_owned(db.session.get(Project, str(project_id)), '项目')
    if not asset_set:
        raise ValidationError(message='请选择来源数据集。')
    candidates = []
    for job in AnalysisJob.query.filter_by(project_id=str(project_id), module='go-kegg-enrichment').all():
        payload, result = job.payload or {}, job.result or {}
        if payload.get('asset_set') != asset_set:
            continue
        metadata = result.get('metadata') or {}
        comparisons = metadata.get('comparisons') or []
        if not comparisons:
            candidates.append({'id': job.id + ':go-bp', 'job_id': job.id, 'status': 'unavailable',
                               'reason': '来源未记录比较方向，请重新运行富集分析。'})
        names = [VolcanoService._safe_title(f"{pair.get('group1')}_vs_{pair.get('group2')}") for pair in comparisons]
        for index, pair in enumerate(comparisons):
            reason, path, file_ref = '', None, None
            try:
                if job.status != 'completed':
                    raise ValidationError(message='来源富集分析尚未成功完成。')
                if not pair.get('group1') or not pair.get('group2') or pair['group1'] == pair['group2']:
                    raise ValidationError(message='来源比较方向记录无效。')
                if names.count(names[index]) != 1:
                    raise ValidationError(message='来源比较名称对应多个组对，无法确定通路方向。')
                if not result.get('output_base'):
                    raise ValidationError(message='来源结果目录未登记。')
                output = PathAccessService.validate_read_path(result['output_base']).resolve()
                relative = f'enrichment_results/GO/BP/{names[index]}/GSEA/GSEA_GO_BP_full.csv'
                if relative not in (metadata.get('full_go_gsea_tables') or []):
                    raise ValidationError(message='来源没有完整 GO-BP 通路表，请重新运行启用 GSEA 的富集分析。')
                path = (output / relative).resolve()
                if not path.is_relative_to(output) or not path.is_file():
                    raise ValidationError(message='完整 GO-BP 通路文件不存在或不属于来源任务。')
                _check_lineage(job)
                validate_go_bp_table(path)
                stat = path.stat()
                file_ref = {'relative_path': relative, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
            except (OSError, ValueError, ValidationError) as error:
                reason = getattr(error, 'message', str(error))
            candidates.append({'id': f'{job.id}:go-bp:{index}', 'job_id': job.id,
                'project_id': str(project_id), 'asset_set': asset_set, 'comparison': pair,
                'path': str(path) if path else '', 'file': file_ref,
                'status': 'unavailable' if reason else 'available', 'reason': reason,
                'created_at': job.created_at.isoformat() if job.created_at else None})
    return candidates


def resolve_pathway_input(data):
    project_id, asset_set = str(data.get('project_id') or ''), str(data.get('asset_set') or '')
    if not project_id or not asset_set:
        raise ValidationError(message='请选择项目、数据集和完整通路来源。')
    selected = [item for item in pathway_candidates(project_id, asset_set)
                if item['id'] == data.get('upstream_artifact_id')]
    if len(selected) != 1:
        raise ValidationError(message='请选择当前项目和数据集的一项通路结果。')
    candidate = selected[0]
    if candidate['status'] != 'available':
        raise ValidationError(message=candidate['reason'])
    requested = data.get('comparison')
    pair = candidate['comparison']
    if requested != [pair['group1'], pair['group2']]:
        raise ValidationError(message='通路来源与当前比较方向不一致，请按来源选择组别顺序。')
    data['upstream_input'] = {'artifact_id': candidate['id'], 'source_job_id': candidate['job_id'],
        'project_id': project_id, 'asset_set': asset_set, 'cache_type': 'go_bp_gsea',
        'path': candidate['path'], 'file': candidate['file'], 'comparison': requested}
    return candidate
