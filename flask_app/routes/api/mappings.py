"""Mapping templates: CRUD, suggest, validate, fields."""

from flask import Blueprint, request, jsonify, current_app

from flask_app.exceptions import ValidationError, FileParseError, StorageError
from flask_app.models.database import db
from flask_app.services.file_parser import FileParserService
from flask_app.services.user_scope import assert_owned, current_user_id, scope_query

from ._common import _get_owned_file, logger

bp = Blueprint("api_mappings", __name__)


@bp.route('/detect-samples', methods=['POST'])
def detect_samples():
    """
    Detect samples in a file based on a sample column.
    POST /api/detect-samples
    Body: { file_id: str, sample_column: str }
    """
    data = request.get_json()
    print(f"DEBUG: Received data: {data}")  # Debug print
    if not data or 'file_id' not in data or 'sample_column' not in data:
        print(f"DEBUG: Validation failed. Data exists: {data is not None}, file_id in data: {'file_id' in data if data else False}, sample_column in data: {'sample_column' in data if data else False}")
        return jsonify({
            'error': 'Missing required fields: file_id, sample_column'
        }), 400
    
    file_id = data['file_id']
    sample_column = data['sample_column']
    
    # Get file record
    file_record = _get_owned_file(file_id)
    
    try:
        # Parse file to detect samples
        with open(file_record.storage_path, 'rb') as f:
            file_content = f.read()
        
        df, columns, row_count = FileParserService.parse_file(file_content, file_record.name)
        
        if sample_column not in columns:
            return jsonify({
                'error': f"Column '{sample_column}' not found in file"
            }), 400
        
        # Get unique samples
        samples = df[sample_column].dropna().unique().tolist()
        samples.sort()
        
        return jsonify({
            'success': True,
            'samples': samples,
            'count': len(samples)
        })
        
    except Exception as e:
        raise FileParseError(
            message=f"Failed to parse file: {str(e)}",
            details={'file_id': file_id, 'sample_column': sample_column}
        )


# =============================================================================
# Field Mapping API - Requirements: 11.2, 11.3, 11.4, 11.5
# =============================================================================

@bp.route('/mappings', methods=['POST'])
def create_mapping_template():
    """
    Create a new field mapping template.
    POST /api/mappings
    
    Requirements: 11.3
    
    Request body:
    {
        "name": "Template name",
        "mapping": {"target_field": "source_column", ...},
        "analysis_type": "similarity_heatmap"
    }
    """
    from models.database import MappingTemplate
    from services.field_mapping import FieldMappingService
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    # Validate required fields
    name = data.get('name')
    mapping = data.get('mapping')
    analysis_type = data.get('analysis_type')
    
    if not name:
        raise ValidationError(
            message="Template name is required",
            details={'field': 'name'}
        )
    
    if not mapping or not isinstance(mapping, dict):
        raise ValidationError(
            message="Mapping dictionary is required",
            details={'field': 'mapping'}
        )
    
    if not analysis_type:
        raise ValidationError(
            message="Analysis type is required",
            details={'field': 'analysis_type'}
        )
    
    # Validate analysis type
    if analysis_type not in FieldMappingService.get_supported_analysis_types():
        raise ValidationError(
            message=f"Unsupported analysis type: {analysis_type}",
            details={
                'field': 'analysis_type',
                'supported_types': FieldMappingService.get_supported_analysis_types()
            }
        )
    
    # Create template record
    try:
        template = MappingTemplate(
            name=name,
            mapping=mapping,
            analysis_type=analysis_type,
            user_id=current_user_id(),
        )
        db.session.add(template)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise StorageError(
            message=f"Failed to save mapping template: {str(e)}",
            details={'name': name}
        )
    
    return jsonify({
        'id': template.id,
        'name': template.name,
        'mapping': template.mapping,
        'analysis_type': template.analysis_type,
        'created_at': template.created_at.isoformat()
    }), 201


@bp.route('/mappings', methods=['GET'])
def list_mapping_templates():
    """
    Get all saved mapping templates.
    GET /api/mappings
    
    Query parameters:
    - analysis_type: Filter by analysis type (optional)
    
    Requirements: 11.3
    """
    from models.database import MappingTemplate
    
    analysis_type = request.args.get('analysis_type')
    
    query = scope_query(MappingTemplate.query, MappingTemplate)
    if analysis_type:
        query = query.filter_by(analysis_type=analysis_type)
    
    templates = query.order_by(MappingTemplate.updated_at.desc()).all()
    
    return jsonify({
        'templates': [
            {
                'id': t.id,
                'name': t.name,
                'mapping': t.mapping,
                'analysis_type': t.analysis_type,
                'created_at': t.created_at.isoformat(),
                'updated_at': t.updated_at.isoformat()
            }
            for t in templates
        ],
        'total': len(templates)
    })


@bp.route('/mappings/<template_id>', methods=['GET'])
def get_mapping_template(template_id):
    """
    Get a mapping template by ID.
    GET /api/mappings/{template_id}
    
    Requirements: 11.3
    """
    from models.database import MappingTemplate
    from exceptions import MappingTemplateNotFoundError
    
    template = MappingTemplate.query.get(template_id)
    
    if not template:
        raise MappingTemplateNotFoundError(
            message=f"Mapping template not found: {template_id}",
            details={'template_id': template_id}
        )
    assert_owned(template, "Mapping template")
    
    return jsonify({
        'id': template.id,
        'name': template.name,
        'mapping': template.mapping,
        'analysis_type': template.analysis_type,
        'created_at': template.created_at.isoformat(),
        'updated_at': template.updated_at.isoformat()
    })


@bp.route('/mappings/<template_id>', methods=['DELETE'])
def delete_mapping_template(template_id):
    """
    Delete a mapping template by ID.
    DELETE /api/mappings/{template_id}
    
    Requirements: 11.3
    """
    from models.database import MappingTemplate
    from exceptions import MappingTemplateNotFoundError
    
    template = MappingTemplate.query.get(template_id)
    
    if not template:
        raise MappingTemplateNotFoundError(
            message=f"Mapping template not found: {template_id}",
            details={'template_id': template_id}
        )
    assert_owned(template, "Mapping template")
    
    try:
        db.session.delete(template)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise StorageError(
            message=f"Failed to delete mapping template: {str(e)}",
            details={'template_id': template_id}
        )
    
    return jsonify({
        'success': True,
        'message': f"Mapping template '{template.name}' deleted successfully"
    })


@bp.route('/mappings/suggest', methods=['POST'])
def suggest_mapping():
    """
    Suggest field mappings based on column names.
    POST /api/mappings/suggest
    
    Requirements: 11.4
    
    Request body:
    {
        "columns": ["col1", "col2", ...],
        "analysis_type": "similarity_heatmap"
    }
    """
    from models.database import MappingTemplate
    from services.field_mapping import FieldMappingService
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    columns = data.get('columns')
    analysis_type = data.get('analysis_type')
    
    if not columns or not isinstance(columns, list):
        raise ValidationError(
            message="Columns list is required",
            details={'field': 'columns'}
        )
    
    if not analysis_type:
        raise ValidationError(
            message="Analysis type is required",
            details={'field': 'analysis_type'}
        )
    
    # Validate analysis type
    if analysis_type not in FieldMappingService.get_supported_analysis_types():
        raise ValidationError(
            message=f"Unsupported analysis type: {analysis_type}",
            details={
                'field': 'analysis_type',
                'supported_types': FieldMappingService.get_supported_analysis_types()
            }
        )
    
    # Get saved templates for matching
    templates = scope_query(MappingTemplate.query, MappingTemplate).filter_by(analysis_type=analysis_type).all()
    saved_templates = [
        {
            'id': t.id,
            'name': t.name,
            'mapping': t.mapping,
            'analysis_type': t.analysis_type
        }
        for t in templates
    ]
    
    # Get suggestions
    suggestion = FieldMappingService.suggest_mapping(
        columns=columns,
        analysis_type=analysis_type,
        saved_templates=saved_templates
    )
    
    # Get required fields info
    required_fields = FieldMappingService.get_field_info(analysis_type)
    
    return jsonify({
        'suggested_mapping': suggestion.mapping,
        'confidence': suggestion.confidence,
        'matched_template_id': suggestion.matched_template_id,
        'field_scores': suggestion.field_scores,
        'required_fields': required_fields
    })


@bp.route('/mappings/validate', methods=['POST'])
def validate_mapping():
    """
    Validate a field mapping for an analysis type.
    POST /api/mappings/validate
    
    Requirements: 11.5
    
    Request body:
    {
        "mapping": {"target_field": "source_column", ...},
        "analysis_type": "similarity_heatmap",
        "columns": ["col1", "col2", ...]
    }
    """
    from services.field_mapping import FieldMappingService
    from exceptions import MappingIncompleteError
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    mapping = data.get('mapping')
    analysis_type = data.get('analysis_type')
    columns = data.get('columns')
    
    if not mapping or not isinstance(mapping, dict):
        raise ValidationError(
            message="Mapping dictionary is required",
            details={'field': 'mapping'}
        )
    
    if not analysis_type:
        raise ValidationError(
            message="Analysis type is required",
            details={'field': 'analysis_type'}
        )
    
    if not columns or not isinstance(columns, list):
        raise ValidationError(
            message="Columns list is required",
            details={'field': 'columns'}
        )
    
    # Validate analysis type
    if analysis_type not in FieldMappingService.get_supported_analysis_types():
        raise ValidationError(
            message=f"Unsupported analysis type: {analysis_type}",
            details={
                'field': 'analysis_type',
                'supported_types': FieldMappingService.get_supported_analysis_types()
            }
        )
    
    # Validate mapping
    result = FieldMappingService.validate_mapping(
        analysis_type=analysis_type,
        mapping=mapping,
        available_columns=columns
    )
    
    return jsonify({
        'is_valid': result.is_valid,
        'missing_fields': result.missing_fields,
        'mapped_fields': result.mapped_fields,
        'message': result.message
    })


@bp.route('/mappings/fields/<analysis_type>', methods=['GET'])
def get_required_fields(analysis_type):
    """
    Get required fields for an analysis type.
    GET /api/mappings/fields/{analysis_type}
    
    Requirements: 11.2
    """
    from services.field_mapping import FieldMappingService
    
    # Validate analysis type
    if analysis_type not in FieldMappingService.get_supported_analysis_types():
        raise ValidationError(
            message=f"Unsupported analysis type: {analysis_type}",
            details={
                'analysis_type': analysis_type,
                'supported_types': FieldMappingService.get_supported_analysis_types()
            }
        )
    
    fields = FieldMappingService.get_field_info(analysis_type)
    
    return jsonify({
        'analysis_type': analysis_type,
        'required_fields': fields
    })


# =============================================================================
# Field Mapping API - GET endpoint for frontend
# =============================================================================

