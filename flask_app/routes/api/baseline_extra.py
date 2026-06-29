"""Baseline calculations and field data analysis."""

import pandas as pd
from pathlib import Path

from flask import Blueprint, request, jsonify, current_app

from flask_app.exceptions import ValidationError
from flask_app.models.database import db, File, SampleGroup
from flask_app.services.file_parser import FileParserService

from ._common import _get_owned_file, logger

bp = Blueprint("api_baseline_extra", __name__)


@bp.route('/baseline/calculate', methods=['POST'])
def calculate_baseline_differences():
    """
    Calculate percentage differences relative to a baseline sample or group.
    POST /api/baseline/calculate
    
    Requirements: 17.1, 17.2, 17.4
    
    Request body:
    {
        "baseline_type": "sample" or "group",
        "baseline_id": "sample_id or group_id",
        "target_ids": ["id1", "id2", ...],
        "target_type": "sample" or "group",
        "metric_fields": ["field1", "field2", ...],
        "file_id": "uuid",
        "sample_column": "sample"  // optional, defaults to "sample"
    }
    
    Returns:
    {
        "baseline_type": "sample" or "group",
        "baseline_id": "...",
        "baseline_name": "...",
        "baseline_values": {"field1": value1, ...},
        "percentage_differences": {
            "target_id1": {"field1": percentage1, ...},
            ...
        },
        "target_info": {
            "target_id1": {"name": "...", "type": "...", "values": {...}},
            ...
        }
    }
    """
    from flask_app.models.database import SampleGroup, File
    from flask_app.services.grouping_service import get_grouping_service
    from flask_app.services.file_parser import FileParserService
    from pathlib import Path
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    baseline_type = data.get('baseline_type')
    baseline_id = data.get('baseline_id')
    target_ids = data.get('target_ids')
    target_type = data.get('target_type')
    metric_fields = data.get('metric_fields')
    file_id = data.get('file_id')
    sample_column = data.get('sample_column', 'sample')
    
    # Validate required fields
    if not baseline_type or baseline_type not in ['sample', 'group']:
        raise ValidationError(
            message="baseline_type must be 'sample' or 'group'",
            details={'field': 'baseline_type'}
        )
    
    if not baseline_id:
        raise ValidationError(
            message="baseline_id is required",
            details={'field': 'baseline_id'}
        )
    
    if not target_ids or not isinstance(target_ids, list):
        raise ValidationError(
            message="target_ids list is required",
            details={'field': 'target_ids'}
        )
    
    if not target_type or target_type not in ['sample', 'group']:
        raise ValidationError(
            message="target_type must be 'sample' or 'group'",
            details={'field': 'target_type'}
        )
    
    if not metric_fields or not isinstance(metric_fields, list):
        raise ValidationError(
            message="metric_fields list is required",
            details={'field': 'metric_fields'}
        )
    
    if not file_id:
        raise ValidationError(
            message="file_id is required",
            details={'field': 'file_id'}
        )
    
    # Get file record
    file_record = _get_owned_file(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Load file data
    storage_path = Path(file_record.storage_path)
    if not storage_path.exists():
        raise AppFileNotFoundError(
            message=f"File data not found on disk",
            details={'file_id': file_id}
        )
    
    try:
        with open(storage_path, 'rb') as f:
            file_content = f.read()
        df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
    except Exception as e:
        raise ValidationError(
            message=f"Failed to read file data: {str(e)}",
            details={'error': str(e)}
        )
    
    # Get baseline group sample IDs if baseline is a group
    baseline_group_sample_ids = None
    if baseline_type == 'group':
        baseline_group = SampleGroup.query.get(baseline_id)
        if not baseline_group:
            raise ValidationError(
                message=f"Baseline group not found: {baseline_id}",
                details={'baseline_id': baseline_id}
            )
        baseline_group_sample_ids = baseline_group.sample_ids
    
    # Get target groups if target_type is 'group'
    target_groups = None
    if target_type == 'group':
        target_groups = []
        for target_id in target_ids:
            group = SampleGroup.query.get(target_id)
            if not group:
                raise ValidationError(
                    message=f"Target group not found: {target_id}",
                    details={'target_id': target_id}
                )
            target_groups.append({
                'id': group.id,
                'name': group.name,
                'sample_ids': group.sample_ids
            })
    
    # Calculate percentage differences
    service = get_grouping_service()
    result = service.calculate_percentage_differences(
        data=df,
        baseline_type=baseline_type,
        baseline_id=baseline_id,
        target_ids=target_ids,
        target_type=target_type,
        metric_fields=metric_fields,
        sample_column=sample_column,
        baseline_group_sample_ids=baseline_group_sample_ids,
        target_groups=target_groups
    )
    
    return jsonify(result.to_dict())


@bp.route('/baseline/value', methods=['POST'])
def get_baseline_value():
    """
    Get baseline value for a sample or group.
    POST /api/baseline/value
    
    Requirements: 17.1, 17.2
    
    Request body:
    {
        "baseline_type": "sample" or "group",
        "baseline_id": "sample_id or group_id",
        "metric_fields": ["field1", "field2", ...],
        "file_id": "uuid",
        "sample_column": "sample"  // optional, defaults to "sample"
    }
    
    Returns:
    {
        "baseline_type": "sample" or "group",
        "baseline_id": "...",
        "baseline_name": "...",
        "baseline_values": {"field1": value1, ...}
    }
    """
    from flask_app.models.database import SampleGroup, File
    from flask_app.services.grouping_service import get_grouping_service
    from flask_app.services.file_parser import FileParserService
    from pathlib import Path
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    baseline_type = data.get('baseline_type')
    baseline_id = data.get('baseline_id')
    metric_fields = data.get('metric_fields')
    file_id = data.get('file_id')
    sample_column = data.get('sample_column', 'sample')
    
    # Validate required fields
    if not baseline_type or baseline_type not in ['sample', 'group']:
        raise ValidationError(
            message="baseline_type must be 'sample' or 'group'",
            details={'field': 'baseline_type'}
        )
    
    if not baseline_id:
        raise ValidationError(
            message="baseline_id is required",
            details={'field': 'baseline_id'}
        )
    
    if not metric_fields or not isinstance(metric_fields, list):
        raise ValidationError(
            message="metric_fields list is required",
            details={'field': 'metric_fields'}
        )
    
    if not file_id:
        raise ValidationError(
            message="file_id is required",
            details={'field': 'file_id'}
        )
    
    # Get file record
    file_record = _get_owned_file(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Load file data
    storage_path = Path(file_record.storage_path)
    if not storage_path.exists():
        raise AppFileNotFoundError(
            message=f"File data not found on disk",
            details={'file_id': file_id}
        )
    
    try:
        with open(storage_path, 'rb') as f:
            file_content = f.read()
        df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
    except Exception as e:
        raise ValidationError(
            message=f"Failed to read file data: {str(e)}",
            details={'error': str(e)}
        )
    
    # Get baseline group sample IDs if baseline is a group
    group_sample_ids = None
    if baseline_type == 'group':
        baseline_group = SampleGroup.query.get(baseline_id)
        if not baseline_group:
            raise ValidationError(
                message=f"Baseline group not found: {baseline_id}",
                details={'baseline_id': baseline_id}
            )
        group_sample_ids = baseline_group.sample_ids
    
    # Get baseline value
    service = get_grouping_service()
    result = service.get_baseline_value(
        data=df,
        baseline_type=baseline_type,
        baseline_id=baseline_id,
        metric_fields=metric_fields,
        sample_column=sample_column,
        group_sample_ids=group_sample_ids
    )
    
    return jsonify(result.to_dict())


# =============================================================================
# Field Analysis API - Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
# =============================================================================

@bp.route('/analysis/fields/<file_id>', methods=['GET'])
def get_file_fields(file_id):
    """
    Get all numeric fields from a file for field analysis.
    GET /api/analysis/fields/{file_id}
    
    Requirements: 5.1, 5.2
    
    Returns:
    {
        "numeric_fields": ["field1", "field2", ...],
        "sample_column": "Sample",
        "row_count": 100,
        "all_columns": ["col1", "col2", ...]
    }
    """
    from flask_app.services.analysis.modules.field_analyzer import FieldAnalyzerModule
    from pathlib import Path
    
    # Get file record
    file_record = _get_owned_file(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Load file data
    storage_path = Path(file_record.storage_path)
    if not storage_path.exists():
        raise AppFileNotFoundError(
            message=f"File data not found on disk",
            details={'file_id': file_id}
        )
    
    try:
        with open(storage_path, 'rb') as f:
            file_content = f.read()
        df, columns, row_count = FileParserService.parse_file(file_content, file_record.original_name)
    except Exception as e:
        raise FileParseError(
            message=f"Failed to read file data: {str(e)}",
            details={'error': str(e)}
        )
    
    # Use FieldAnalyzerModule to identify numeric fields
    analyzer = FieldAnalyzerModule()
    numeric_fields = analyzer.identify_numeric_fields(df)
    
    # Try to detect sample column
    sample_column = None
    sample_column_candidates = ['Sample', 'sample', 'SAMPLE', 'SampleName', 'sample_name', 'ID', 'id']
    for candidate in sample_column_candidates:
        if candidate in columns:
            sample_column = candidate
            break
    
    # If no sample column found, use the first non-numeric column
    if not sample_column:
        for col in columns:
            if col not in numeric_fields:
                sample_column = col
                break
    
    return jsonify({
        'numeric_fields': numeric_fields,
        'sample_column': sample_column,
        'row_count': row_count,
        'all_columns': columns
    })


@bp.route('/analysis/field-data', methods=['POST'])
def analyze_field_data():
    """
    Analyze selected fields from a file.
    POST /api/analysis/field-data
    
    Requirements: 5.2, 5.3, 5.4, 5.5, 5.6, 21.3, 21.5
    
    Request body:
    {
        "file_id": "uuid",
        "fields": ["field1", "field2", ...],
        "sample_column": "Sample",
        "selected_samples": ["sample1", "sample2", ...] (optional),
        "baseline_sample": "sample_name" (optional),
        "chart_config": {
            "title": "Chart Title",
            "figsize": [12, 8],
            "dpi": 300,
            "color_scheme": "viridis",
            "bar_width": 0.8,
            "font_size": 12,
            "show_values": true
        } (optional),
        "plot_type": "bar" | "line" | "grouped_bar" (optional, default: "bar")
    }
    
    Returns:
    {
        "analysis_id": "uuid",
        "samples": ["sample1", "sample2", ...],
        "fields": ["field1", "field2", ...],
        "field_data": {sample: {field: value}},
        "percentage_diffs": {sample: {field: diff}} (if baseline_sample provided),
        "table_data": {
            "headers": [...],
            "rows": [...],
            "tab_separated": "..."
        },
        "charts": {
            "chart_name": "base64_image_data"
        }
    }
    """
    from flask_app.services.analysis.modules.field_analyzer import FieldAnalyzerModule, ChartConfig
    from pathlib import Path
    import pandas as pd
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    file_id = data.get('file_id')
    fields = data.get('fields', [])
    sample_column = data.get('sample_column', 'Sample')
    selected_samples = data.get('selected_samples', [])  # Requirements: 21.3, 21.5
    baseline_sample = data.get('baseline_sample')
    chart_config = data.get('chart_config', {})
    plot_type = data.get('plot_type', 'bar')
    
    if not file_id:
        raise ValidationError(
            message="file_id is required",
            details={'field': 'file_id'}
        )
    
    # Get file record
    file_record = _get_owned_file(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Load file data
    storage_path = Path(file_record.storage_path)
    if not storage_path.exists():
        raise AppFileNotFoundError(
            message=f"File data not found on disk",
            details={'file_id': file_id}
        )
    
    try:
        with open(storage_path, 'rb') as f:
            file_content = f.read()
        df, columns, row_count = FileParserService.parse_file(file_content, file_record.original_name)
    except Exception as e:
        raise FileParseError(
            message=f"Failed to read file data: {str(e)}",
            details={'error': str(e)}
        )
    
    # Validate sample column
    if sample_column not in columns:
        raise ValidationError(
            message=f"Sample column '{sample_column}' not found in file",
            details={'sample_column': sample_column, 'available_columns': columns}
        )
    
    # Create analyzer and run analysis
    analyzer = FieldAnalyzerModule(config={'chart_config': chart_config})
    
    # If no fields specified, use all numeric fields
    if not fields:
        fields = analyzer.identify_numeric_fields(df)
        # Exclude sample column from fields
        fields = [f for f in fields if f != sample_column]
    
    # Validate fields exist
    missing_fields = [f for f in fields if f not in columns]
    if missing_fields:
        raise ValidationError(
            message=f"Fields not found in file: {missing_fields}",
            details={'missing_fields': missing_fields, 'available_columns': columns}
        )
    
    # Validate baseline sample if provided
    if baseline_sample:
        samples_in_file = df[sample_column].unique().tolist()
        if baseline_sample not in samples_in_file:
            raise ValidationError(
                message=f"Baseline sample '{baseline_sample}' not found in file",
                details={'baseline_sample': baseline_sample, 'available_samples': samples_in_file}
            )
    
    # Run analysis
    params = {
        'sample_column': sample_column,
        'fields': fields,
        'selected_samples': selected_samples,  # Requirements: 21.3, 21.5
        'baseline_sample': baseline_sample,
        'plot_type': plot_type,
        'chart_config': chart_config
    }
    
    try:
        results = analyzer.analyze(df, params)
        charts = analyzer.visualize(results, params)
    except Exception as e:
        raise ValidationError(
            message=f"Analysis failed: {str(e)}",
            details={'error': str(e)}
        )
    
    # Generate analysis ID
    analysis_id = str(uuid.uuid4())
    
    return jsonify({
        'analysis_id': analysis_id,
        'samples': results.get('samples', []),
        'fields': results.get('fields', []),
        'field_data': results.get('field_data', {}),
        'percentage_diffs': results.get('percentage_diffs'),
        'baseline_sample': baseline_sample,
        'table_data': results.get('table_data', {}),
        'charts': charts
    })


