"""Optional management views; legacy full field-option calls retain their contract."""
from sqlalchemy import func
from flask_app.exceptions import ValidationError
from flask_app.models.database import Project, SampleRecord
from flask_app.services.user_scope import scope_query


def field_options_response(args, service):
    view = args.get('view', '')
    if view not in {'', 'filters', 'catalog'}:
        raise ValidationError(message='筛选候选读取方式不支持。')
    scope = {'project_id': args.get('project_id', ''), 'asset_set': args.get('asset_set', '')}
    field = args.get('field', '')
    if view != 'catalog':
        return {'fields': service.get_distinct_field_values(
            **scope, field_name=field, include_identifiers=view != 'filters')}
    if field not in {'sample_id', 'sequence_id'}:
        raise ValidationError(message='请选择样本编号或序列编号。')
    search = str(args.get('q', '')).strip()
    if len(search) > 200:
        raise ValidationError(message='候选搜索内容请控制在 200 字以内。')
    def integer(name, default, maximum=None):
        raw = str(args.get(name, default))
        if not raw.isascii() or not raw.isdecimal():
            raise ValidationError(message='候选页码或每页数量格式不正确。')
        value = int(raw)
        if value < 1 or maximum and value > maximum:
            raise ValidationError(message='候选页码或每页数量超出范围。')
        return value
    page, size = integer('page', 1), integer('page_size', 20, 100)
    column = getattr(SampleRecord, field)
    value = func.trim(column)
    query = scope_query(SampleRecord.query.join(Project), Project)
    if scope['project_id']:
        query = query.filter(SampleRecord.project_id == scope['project_id'])
    if scope['asset_set']:
        query = query.filter(SampleRecord.extra_metadata['asset_set'].as_string() == scope['asset_set'])
    query = query.with_entities(value).filter(column.isnot(None), value != '').distinct()
    if search:
        query = query.filter(value.icontains(search, autoescape=True))
    total = query.count()
    values = [str(row[0]) for row in query.order_by(value).offset((page - 1) * size).limit(size).all()]
    return {'field': field, 'values': values, 'pagination': {
        'page': page, 'page_size': size, 'total': total,
        'total_pages': (total + size - 1) // size if total else 0}}
