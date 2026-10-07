"""Dataset display names and archive flags never rewrite historical scope references."""
from flask_app.exceptions import ValidationError, DatasetRecordChangedError
from flask_app.models.database import Project, ProjectAsset, ProjectDataset, db
from flask_app.services.user_scope import assert_owned


def update_dataset(project, payload):
    if not isinstance(payload, dict) or set(payload) - {'asset_set', 'display_name', 'description', 'source', 'batch', 'archived', 'expected_revision'}:
        raise ValidationError(message='请提供有效的数据集说明字段。')
    limits = {'asset_set':120, 'display_name':120, 'description':4000, 'source':500, 'batch':120}
    labels = {'asset_set':'数据集标识', 'display_name':'显示名称', 'description':'说明', 'source':'数据来源', 'batch':'采集批次'}
    values = {}
    for field, limit in limits.items():
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, str) or len(value.strip()) > limit:
            raise ValidationError(message=f'{labels[field]}应为不超过 {limit} 字的文本。')
        values[field] = value.strip()
    if not values.get('asset_set') or ('display_name' in values and not values['display_name']):
        raise ValidationError(message='请指定数据集，并填写显示名称。')
    expected = payload.get('expected_revision')
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise ValidationError(message='请先读取数据集当前版本，再保存修改。')
    if 'archived' in payload and not isinstance(payload['archived'], bool):
        raise ValidationError(message='请明确是否归档此数据集。')
    scope = values.pop('asset_set')
    with db.session.no_autoflush:
        locked = Project.query.filter_by(id=project.id).populate_existing().with_for_update().first()
        assert_owned(locked, '项目')
        row = ProjectDataset.query.filter_by(project_id=project.id, scope=scope).populate_existing().with_for_update().first()
        if row is None:
            from flask_app.services.project_asset_service import ProjectAssetService
            exists = ProjectAssetService.asset_query(project.id, inputs_only=True, asset_set=scope,
                include_superseded=True).with_entities(ProjectAsset.id).first()
            if not exists:
                raise ValidationError(message='此数据集尚无已登记输入，或已不存在，请刷新后重新选择。')
        revision = row.revision if row else 0
        if expected != revision:
            raise DatasetRecordChangedError(details={'dataset':row.to_dict() if row else {'name':scope,'revision':0}})
        if row is None:
            row = ProjectDataset(project_id=project.id, scope=scope, display_name=scope)
            db.session.add(row)
        for field, value in values.items():
            setattr(row, field, value)
        if 'archived' in payload:
            row.archived = payload['archived']
        row.revision = revision + 1
    db.session.commit()
    return row.to_dict()


def add_dataset_metadata(project_id, summaries):
    rows = ProjectDataset.query.filter_by(project_id=project_id).all()
    by_scope = {item['name']:item for item in summaries}
    for row in rows:
        entry = by_scope.setdefault(row.scope, {'name':row.scope,'input_count':0,'kinds':{}})
        entry.update(row.to_dict())
    return sorted(by_scope.values(), key=lambda entry: (bool(entry.get('archived')), entry.get('display_name') or entry['name']))
