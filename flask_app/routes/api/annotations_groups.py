"""Annotations and sample groups: CRUD, types, averages."""

from pathlib import Path

from flask import Blueprint, request, jsonify, current_app

from flask_app.exceptions import ValidationError
from flask_app.models.database import db, File, SampleGroup
from flask_app.services.file_parser import FileParserService

from ._common import _get_owned_file, _get_owned_analysis, logger

bp = Blueprint("api_annotations_groups", __name__)


@bp.route('/annotations/<analysis_id>', methods=['GET'])
def get_annotations(analysis_id):
    """
    Get all annotations for an analysis.
    GET /api/annotations/{analysis_id}
    
    Query parameters:
    - result_id: Filter by result ID (optional)
    
    Requirements: 12.5
    """
    from flask_app.services.annotation_service import get_annotation_service
    
    result_id = request.args.get('result_id')
    
    service = get_annotation_service()
    annotations = service.get_annotations(analysis_id, result_id)
    
    return jsonify({
        'analysis_id': analysis_id,
        'result_id': result_id,
        'annotations': [a.to_dict() for a in annotations],
        'total': len(annotations)
    })


@bp.route('/annotations/<analysis_id>', methods=['POST'])
def create_annotation(analysis_id):
    """
    Create a new annotation.
    POST /api/annotations/{analysis_id}
    
    Request body:
    {
        "annotation_type": "text",
        "position_x": 100,
        "position_y": 200,
        "content": "Sample annotation",
        "result_id": "uuid",  // optional
        "style": {...}  // optional
    }
    
    Requirements: 12.5
    """
    from flask_app.services.annotation_service import get_annotation_service
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    annotation_type = data.get('annotation_type')
    position_x = data.get('position_x')
    position_y = data.get('position_y')
    
    if not annotation_type:
        raise ValidationError(
            message="Annotation type is required",
            details={'field': 'annotation_type'}
        )
    
    if position_x is None or position_y is None:
        raise ValidationError(
            message="Position (position_x, position_y) is required",
            details={'fields': ['position_x', 'position_y']}
        )
    
    service = get_annotation_service()
    annotation = service.create_annotation(
        analysis_id=analysis_id,
        annotation_type=annotation_type,
        position_x=position_x,
        position_y=position_y,
        content=data.get('content'),
        result_id=data.get('result_id'),
        style=data.get('style')
    )
    
    return jsonify({
        'success': True,
        'annotation': annotation.to_dict(),
        'message': 'Annotation created successfully'
    }), 201


@bp.route('/annotations/item/<annotation_id>', methods=['GET'])
def get_annotation(annotation_id):
    """
    Get a single annotation by ID.
    GET /api/annotations/item/{annotation_id}
    
    Requirements: 12.5
    """
    from flask_app.services.annotation_service import get_annotation_service
    
    service = get_annotation_service()
    annotation = service.get_annotation(annotation_id)
    
    if not annotation:
        raise ValidationError(
            message=f"Annotation not found: {annotation_id}",
            details={'annotation_id': annotation_id}
        )
    
    return jsonify(annotation.to_dict())


@bp.route('/annotations/item/<annotation_id>', methods=['PUT'])
def update_annotation(annotation_id):
    """
    Update an annotation.
    PUT /api/annotations/item/{annotation_id}
    
    Request body:
    {
        "content": "Updated text",  // optional
        "position_x": 150,  // optional
        "position_y": 250,  // optional
        "style": {...}  // optional
    }
    
    Requirements: 12.5
    """
    from flask_app.services.annotation_service import get_annotation_service
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    service = get_annotation_service()
    annotation = service.update_annotation(
        annotation_id=annotation_id,
        content=data.get('content'),
        position_x=data.get('position_x'),
        position_y=data.get('position_y'),
        style=data.get('style')
    )
    
    return jsonify({
        'success': True,
        'annotation': annotation.to_dict(),
        'message': 'Annotation updated successfully'
    })


@bp.route('/annotations/item/<annotation_id>', methods=['DELETE'])
def delete_annotation(annotation_id):
    """
    Delete an annotation.
    DELETE /api/annotations/item/{annotation_id}
    
    Requirements: 12.5
    """
    from flask_app.services.annotation_service import get_annotation_service
    
    service = get_annotation_service()
    success = service.delete_annotation(annotation_id)
    
    return jsonify({
        'success': success,
        'message': 'Annotation deleted successfully'
    })


@bp.route('/annotations/<analysis_id>/clear', methods=['DELETE'])
def clear_annotations(analysis_id):
    """
    Delete all annotations for an analysis.
    DELETE /api/annotations/{analysis_id}/clear
    
    Query parameters:
    - result_id: Only clear annotations for specific result (optional)
    
    Requirements: 12.5
    """
    from flask_app.services.annotation_service import get_annotation_service
    
    result_id = request.args.get('result_id')
    
    service = get_annotation_service()
    count = service.delete_all_annotations(analysis_id, result_id)
    
    return jsonify({
        'success': True,
        'deleted_count': count,
        'message': f'{count} annotation(s) deleted successfully'
    })


@bp.route('/annotations/types', methods=['GET'])
def get_annotation_types():
    """
    Get supported annotation types and their default styles.
    GET /api/annotations/types
    
    Requirements: 12.5
    """
    from flask_app.services.annotation_service import get_annotation_service
    
    service = get_annotation_service()
    types = service.get_supported_types()
    
    return jsonify({
        'types': [
            {
                'type': t,
                'default_style': service.get_default_style(t)
            }
            for t in types
        ]
    })


# =============================================================================
# Sample Group API - Requirements: 16.1, 16.2
# =============================================================================

@bp.route('/groups', methods=['POST'])
def create_sample_group():
    """
    Create a new sample group.
    POST /api/groups
    
    Requirements: 16.1
    
    Request body:
    {
        "name": "Group name",
        "sample_ids": ["sample1", "sample2", ...],
        "description": "Optional description",
        "file_id": "uuid"  // optional, for associating with a file
    }
    """
    from flask_app.models.database import SampleGroup, File
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    name = data.get('name')
    sample_ids = data.get('sample_ids')
    description = data.get('description')
    file_id = data.get('file_id')
    
    if not name:
        raise ValidationError(
            message="Group name is required",
            details={'field': 'name'}
        )
    
    if not sample_ids or not isinstance(sample_ids, list):
        raise ValidationError(
            message="Sample IDs list is required",
            details={'field': 'sample_ids'}
        )
    
    if len(sample_ids) == 0:
        raise ValidationError(
            message="At least one sample ID is required",
            details={'field': 'sample_ids'}
        )
    
    # Validate file_id if provided
    if file_id:
        file_record = _get_owned_file(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
    
    # Create group record
    try:
        group = SampleGroup(
            name=name,
            sample_ids=sample_ids,
            description=description,
            file_id=file_id
        )
        db.session.add(group)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise StorageError(
            message=f"Failed to create sample group: {str(e)}",
            details={'name': name}
        )
    
    return jsonify({
        'id': group.id,
        'name': group.name,
        'sample_ids': group.sample_ids,
        'sample_count': len(group.sample_ids),
        'description': group.description,
        'file_id': group.file_id,
        'created_at': group.created_at.isoformat()
    }), 201


@bp.route('/groups', methods=['GET'])
def list_sample_groups():
    """
    Get all sample groups.
    GET /api/groups
    
    Query parameters:
    - file_id: Filter by associated file (optional)
    
    Requirements: 16.1
    """
    from flask_app.models.database import SampleGroup
    
    file_id = request.args.get('file_id')
    
    query = SampleGroup.query
    if file_id:
        query = query.filter_by(file_id=file_id)
    
    groups = query.order_by(SampleGroup.created_at.desc()).all()
    
    return jsonify({
        'groups': [
            {
                'id': g.id,
                'name': g.name,
                'sample_ids': g.sample_ids,
                'sample_count': len(g.sample_ids),
                'description': g.description,
                'file_id': g.file_id,
                'created_at': g.created_at.isoformat()
            }
            for g in groups
        ],
        'total': len(groups)
    })


@bp.route('/groups/<group_id>', methods=['GET'])
def get_sample_group(group_id):
    """
    Get a sample group by ID.
    GET /api/groups/{group_id}
    
    Requirements: 16.1
    """
    from flask_app.models.database import SampleGroup
    
    group = SampleGroup.query.get(group_id)
    
    if not group:
        raise ValidationError(
            message=f"Sample group not found: {group_id}",
            details={'group_id': group_id}
        )
    
    return jsonify({
        'id': group.id,
        'name': group.name,
        'sample_ids': group.sample_ids,
        'sample_count': len(group.sample_ids),
        'description': group.description,
        'file_id': group.file_id,
        'created_at': group.created_at.isoformat()
    })


@bp.route('/groups/<group_id>', methods=['PUT'])
def update_sample_group(group_id):
    """
    Update a sample group.
    PUT /api/groups/{group_id}
    
    Request body:
    {
        "name": "Updated name",
        "sample_ids": ["sample1", "sample2", ...],
        "description": "Updated description"
    }
    
    Requirements: 16.1
    """
    from flask_app.models.database import SampleGroup
    
    group = SampleGroup.query.get(group_id)
    
    if not group:
        raise ValidationError(
            message=f"Sample group not found: {group_id}",
            details={'group_id': group_id}
        )
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    # Update fields if provided
    if 'name' in data:
        if not data['name']:
            raise ValidationError(
                message="Group name cannot be empty",
                details={'field': 'name'}
            )
        group.name = data['name']
    
    if 'sample_ids' in data:
        if not isinstance(data['sample_ids'], list) or len(data['sample_ids']) == 0:
            raise ValidationError(
                message="At least one sample ID is required",
                details={'field': 'sample_ids'}
            )
        group.sample_ids = data['sample_ids']
    
    if 'description' in data:
        group.description = data['description']
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise StorageError(
            message=f"Failed to update sample group: {str(e)}",
            details={'group_id': group_id}
        )
    
    return jsonify({
        'id': group.id,
        'name': group.name,
        'sample_ids': group.sample_ids,
        'sample_count': len(group.sample_ids),
        'description': group.description,
        'file_id': group.file_id,
        'created_at': group.created_at.isoformat()
    })


@bp.route('/groups/<group_id>', methods=['DELETE'])
def delete_sample_group(group_id):
    """
    Delete a sample group.
    DELETE /api/groups/{group_id}
    
    Requirements: 16.1
    """
    from flask_app.models.database import SampleGroup
    
    group = SampleGroup.query.get(group_id)
    
    if not group:
        raise ValidationError(
            message=f"Sample group not found: {group_id}",
            details={'group_id': group_id}
        )
    
    try:
        db.session.delete(group)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise StorageError(
            message=f"Failed to delete sample group: {str(e)}",
            details={'group_id': group_id}
        )
    
    return jsonify({
        'success': True,
        'message': f"Sample group '{group.name}' deleted successfully"
    })



@bp.route('/groups/averages', methods=['POST'])
def calculate_group_averages():
    """
    Calculate averages for multiple sample groups.
    POST /api/groups/averages
    
    Requirements: 16.2, 16.3
    
    Request body:
    {
        "group_ids": ["group1_id", "group2_id", ...],
        "metric_fields": ["field1", "field2", ...],
        "file_id": "uuid",
        "sample_column": "sample"  // optional, defaults to "sample"
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
    
    group_ids = data.get('group_ids')
    metric_fields = data.get('metric_fields')
    file_id = data.get('file_id')
    sample_column = data.get('sample_column', 'sample')
    
    if not group_ids or not isinstance(group_ids, list):
        raise ValidationError(
            message="Group IDs list is required",
            details={'field': 'group_ids'}
        )
    
    if not metric_fields or not isinstance(metric_fields, list):
        raise ValidationError(
            message="Metric fields list is required",
            details={'field': 'metric_fields'}
        )
    
    if not file_id:
        raise ValidationError(
            message="File ID is required",
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
    
    # Get group records
    groups = []
    for group_id in group_ids:
        group = SampleGroup.query.get(group_id)
        if not group:
            raise ValidationError(
                message=f"Sample group not found: {group_id}",
                details={'group_id': group_id}
            )
        groups.append({
            'id': group.id,
            'name': group.name,
            'sample_ids': group.sample_ids
        })
    
    # Calculate averages
    service = get_grouping_service()
    result = service.calculate_multiple_group_averages(
        data=df,
        groups=groups,
        metric_fields=metric_fields,
        sample_column=sample_column
    )
    
    return jsonify(result.to_dict())
