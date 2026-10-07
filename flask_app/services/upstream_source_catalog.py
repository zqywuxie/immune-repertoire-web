"""Lightweight management views over the existing, strictly validated sources.

Availability is still established by the scientific source services. Paging this
view bounds the response, not their validation scan; it never changes resolution.
"""
from collections import Counter
from flask_app.exceptions import ValidationError
from flask_app.models.database import AnalysisJob


def source_view_options(args):
    view = str(args.get('view') or '').strip()
    if not view:
        return None
    if view not in {'summary', 'catalog'}:
        raise ValidationError(message='前置结果视图不支持。')
    project_id = str(args.get('project_id') or '').strip()
    asset_set = str(args.get('asset_set') or '').strip()
    if not project_id or not asset_set:
        raise ValidationError(message='请指定前置结果所属项目和数据集。')
    search = str(args.get('q') or '').strip()
    status = str(args.get('status') or '').strip()
    if len(search) > 200 or status not in {'', 'available', 'unavailable'}:
        raise ValidationError(message='前置结果查询条件不支持。')
    try:
        page = int(args.get('page', 1))
        page_size = int(args.get('page_size', 20))
    except (ValueError, TypeError):
        raise ValidationError(message='请提供有效的前置结果页码。')
    if page < 1 or not 1 <= page_size <= 100:
        raise ValidationError(message='前置结果页码须为正数，每页最多 100 项。')
    return dict(view=view, project_id=project_id, asset_set=asset_set,
                search=search, status=status, page=page, page_size=page_size)



def _description(candidate):
    labels={'vj_usage':'V/J 基因使用结果','umapin_table':'降维特征结果',
            'tra_shared':'受体 α 链共享结果','usage':'基因使用结果'}
    parts=[labels.get(candidate.get('cache_type'), '')]
    chains=candidate.get('chains')
    if isinstance(chains,list):
        parts.append('链：'+'、'.join(str(value) for value in chains[:7]))
    fields=candidate.get('group_fields')
    field=candidate.get('group_field')
    if field:
        parts.append('分组字段：'+str(field))
    elif isinstance(fields,list) and fields:
        parts.append('分组字段：'+'、'.join(str(value) for value in fields[:3]))
    metadata=candidate.get('metadata') or {}
    pairs=[candidate['comparison']] if candidate.get('comparison') else metadata.get('comparisons') or []
    directions=[]
    for pair in pairs[:3] if isinstance(pairs,list) else []:
        if isinstance(pair,dict):
            first,second=pair.get('group1'),pair.get('group2')
        elif isinstance(pair,(list,tuple)) and len(pair)==2:
            first,second=pair
        else:
            continue
        directions.append(str(first or '未记录组别')+' → '+str(second or '未记录组别'))
    if directions:
        parts.append('比较：'+'；'.join(directions)+(f'（共 {len(pairs)} 个比较）' if len(pairs)>3 else ''))
    return ' · '.join(part for part in parts if part)


def source_management_view(candidates, *, view, project_id, asset_set,
                           search='', status='', page=1, page_size=20):
    rows = []
    for candidate in candidates:
        # Unknown legacy sources remain unavailable with their original reason;
        # never silently advertise them as belonging to the selected dataset.
        if candidate.get('project_id') not in (None, '', project_id):
            continue
        if candidate.get('asset_set') not in (None, '', asset_set):
            continue
        rows.append({key: candidate.get(key) for key in (
            'id', 'job_id', 'asset_set', 'created_at', 'source_task_name', 'cache_type', 'comparison'
        ) if candidate.get(key) is not None})
        rows[-1].update(project_id=project_id,
            status='available' if candidate.get('status') == 'available' else 'unavailable',
            reason={
                'Path does not exist':'来源路径不存在，请检查来源文件或重新运行。',
                'Path is required':'来源路径未记录，请重新运行来源分析。',
                'Path is not a directory':'来源路径不是目录，请检查来源结果。',
                'Access denied: system directory restricted':'来源位于限制访问的系统目录，请检查数据路径。',
                'Access denied: insufficient filesystem read permission':'没有读取来源文件的权限，请检查目录权限。',
                'Access denied: insufficient filesystem write permission':'没有写入来源目录的权限，请检查目录权限。',
                'No readable filesystem root is available for this process':'当前服务没有可读取的数据目录，请检查部署配置。',
            }.get(str(candidate.get('reason') or ''), str(candidate.get('reason') or '')))
        if view == 'catalog':
            rows[-1]['description'] = _description(candidate)
            pair = rows[-1].get('comparison')
            if isinstance(pair, dict):
                rows[-1]['comparison'] = {key: str(pair.get(key) or '') for key in ('group1','group2')}
    counts = Counter(row['status'] for row in rows)
    reasons = Counter(row['reason'] or '来源暂不可用。' for row in rows if row['status'] == 'unavailable')
    summary = {'total': len(rows), 'available': counts['available'], 'unavailable': counts['unavailable'],
               'reasons': [{'reason': reason, 'count': count} for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))]}
    if view == 'summary':
        return {'success': True, 'summary': summary}

    job_ids = list({row.get('job_id') for row in rows if row.get('job_id')})
    names = {}
    if job_ids:
        # Read only names/date for presentation, never whole job payload/result.
        jobs = AnalysisJob.query.filter(AnalysisJob.project_id == project_id, AnalysisJob.id.in_(job_ids)).with_entities(
            AnalysisJob.id, AnalysisJob.payload['_task_name'].as_string(),
            AnalysisJob.payload['task_name'].as_string(), AnalysisJob.created_at)
        names = {job[0]: (job[1] or job[2] or '', job[3]) for job in jobs.all()}
    for row in rows:
        name, created = names.get(row.get('job_id'), ('', None))
        row['source_task_name'] = str(row.get('source_task_name') or name or '未命名来源任务')
        if not row.get('created_at') and created:
            row['created_at'] = created.isoformat()
    # A stable ID tie-breaker; latest results first within each availability state.
    rows.sort(key=lambda row: (str(row.get('created_at') or ''), str(row['id'])), reverse=True)
    rows.sort(key=lambda row: row['status'] != 'available')
    if status:
        rows = [row for row in rows if row['status'] == status]
    if search:
        needle = search.casefold()
        rows = [row for row in rows if needle in ' '.join([
            str(row.get('source_task_name') or ''), str(row.get('id') or ''), str(row.get('job_id') or ''),
            str(row.get('cache_type') or ''), str(row.get('created_at') or ''), str(row.get('description') or ''),
            str((row.get('comparison') or {}).get('group1') or ''),
            str((row.get('comparison') or {}).get('group2') or ''),
        ]).casefold()]
    total = len(rows)
    return {'success': True, 'summary': summary, 'candidates': rows[(page-1)*page_size:page*page_size],
            'pagination': {'page': page, 'page_size': page_size, 'total': total,
                           'total_pages': (total + page_size - 1) // page_size}}
