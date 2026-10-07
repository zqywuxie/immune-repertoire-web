"""Inspect a project's explicit Profile version without changing sample identities."""
from flask_app.exceptions import ValidationError


def inspect_group_source(asset, field, sheet=None, *, include_samples=True):
    from flask_app.routes.api_projects import _resolve_asset_path
    from flask_app.routes.api_script_hub._common import _robust_read_csv
    from flask_app.routes.api_script_hub.boxplot import _detect_sample_column, _samples_by_group_value
    from flask_app.services.input_table_schema import inspect_table_schema
    from flask_app.services.project_asset_service import ProjectAssetService
    if asset.asset_type not in {'profile', 'datapoint'}:
        raise ValidationError(message='请选择指标表的具体版本。')
    path = _resolve_asset_path(asset)
    schema = inspect_table_schema(path, sheet)
    if schema['requires_sheet_selection']:
        raise ValidationError(message='指标表包含多个工作表，请明确选择。')
    if not field or field not in schema['columns']:
        raise ValidationError(message='分组字段不在所选指标表中。')
    if schema['columns'].count(field) > 1:
        raise ValidationError(message='分组字段名称重复，请先整理输入表。')
    sample_column = _detect_sample_column(schema['columns'])
    options = {'dtype': str, 'keep_default_na': False, 'usecols': list(dict.fromkeys([field] + ([sample_column] if sample_column else [])))}
    if schema['selected_sheet'] is not None:
        options['sheet_name'] = schema['selected_sheet']
    if path.suffix.lower() == '.tsv':
        options['sep'] = '\t'
    frame = _robust_read_csv(path, **options)
    column = frame[field].astype(str).str.strip()
    values = sorted({value for value in column if value})
    samples_by_value = _samples_by_group_value(frame, sample_column, field) if include_samples else {}
    sample_counts = {}
    if sample_column:
        samples = frame[sample_column].astype(str).str.strip()
        valid = samples.ne('') & column.ne('')
        sample_counts = samples[valid].groupby(column[valid]).nunique().to_dict()
    return {'values': values, 'row_counts': {value: int(count) for value, count in column.value_counts().items() if value},
            'sample_column': sample_column, 'samples_by_value': samples_by_value,
            'sample_counts': {str(value): int(count) for value, count in sample_counts.items()},
            'asset_id': asset.id, 'asset_set': ProjectAssetService.dataset_name(asset),
            'content_version': (asset.metadata_json or {}).get('content_version') or asset.id,
            'selected_sheet': schema['selected_sheet']}


def validate_group_definition(project_id, definition):
    from flask_app.models.database import ProjectAsset
    identifier = str(definition.get('source_asset_id') or '').strip()
    if not identifier:
        return definition
    asset = ProjectAsset.query.filter_by(id=identifier, project_id=project_id).first()
    if asset is None:
        raise ValidationError(message='来源指标表不属于当前项目或已删除。')
    source = inspect_group_source(asset, str(definition.get('group_field') or ''), definition.get('source_sheet'), include_samples=False)
    names = [str(value.get('name') or value.get('label') or '') if isinstance(value, dict) else str(value)
             for value in definition.get('groups') or []]
    if not names or len(names) != len(set(names)) or any(value not in source['values'] or ',' in value for value in names):
        raise ValidationError(message='所选分组为空、重复或不在来源指标表中，请重新确认。')
    requested_version = definition.get('source_content_version')
    if requested_version and requested_version != source['content_version']:
        raise ValidationError(message='来源版本已发生变化，请重新读取分组后保存。')
    return {**definition, 'source_content_version': source['content_version'],
            'source_sheet': source['selected_sheet'], 'asset_set': source['asset_set']}
