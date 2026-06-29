"""Configuration and parameter templates: CRUD, reset, options, validate, defaults."""

from flask import Blueprint, request, jsonify, current_app

from flask_app.exceptions import ValidationError
from flask_app.services.config_service import get_config_service

from ._common import logger

bp = Blueprint("api_config_params", __name__)


@bp.route('/config', methods=['GET'])
def get_config():
    """
    Get user configuration.
    GET /api/config
    
    Query parameters:
    - config_id: Configuration ID (default: 'default')
    
    Requirements: 7.4
    """
    from flask_app.services.config_service import get_config_service
    
    config_id = request.args.get('config_id', 'default')
    
    service = get_config_service()
    config = service.get_config(config_id)
    
    return jsonify({
        'config_id': config_id,
        'config': config.to_dict()
    })


@bp.route('/config', methods=['POST'])
def save_config():
    """
    Save user configuration.
    POST /api/config
    
    Request body:
    {
        "config_id": "default",  // optional
        "config": {
            "default_color_scheme": "viridis",
            "default_figure_size": [10, 8],
            ...
        }
    }
    
    Requirements: 7.3
    """
    from flask_app.services.config_service import get_config_service, UserConfiguration
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    config_data = data.get('config')
    config_id = data.get('config_id', 'default')
    
    if not config_data or not isinstance(config_data, dict):
        raise ValidationError(
            message="Configuration data is required",
            details={'field': 'config'}
        )
    
    service = get_config_service()
    
    # Validate configuration
    errors = service.validate_config(config_data)
    if errors:
        raise ValidationError(
            message="Invalid configuration values",
            details={'validation_errors': errors}
        )
    
    # Create and save configuration
    config = UserConfiguration.from_dict(config_data)
    saved_config = service.save_config(config, config_id)
    
    return jsonify({
        'success': True,
        'config_id': config_id,
        'config': saved_config.to_dict(),
        'message': 'Configuration saved successfully'
    })


@bp.route('/config', methods=['PATCH'])
def update_config():
    """
    Update specific configuration fields.
    PATCH /api/config
    
    Request body:
    {
        "config_id": "default",  // optional
        "updates": {
            "default_color_scheme": "plasma",
            ...
        }
    }
    
    Requirements: 7.3
    """
    from flask_app.services.config_service import get_config_service
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    updates = data.get('updates')
    config_id = data.get('config_id', 'default')
    
    if not updates or not isinstance(updates, dict):
        raise ValidationError(
            message="Updates dictionary is required",
            details={'field': 'updates'}
        )
    
    service = get_config_service()
    
    # Validate updates
    errors = service.validate_config(updates)
    if errors:
        raise ValidationError(
            message="Invalid configuration values",
            details={'validation_errors': errors}
        )
    
    # Update configuration
    updated_config = service.update_config(updates, config_id)
    
    return jsonify({
        'success': True,
        'config_id': config_id,
        'config': updated_config.to_dict(),
        'message': 'Configuration updated successfully'
    })


@bp.route('/config/reset', methods=['POST'])
def reset_config():
    """
    Reset configuration to defaults.
    POST /api/config/reset
    
    Request body:
    {
        "config_id": "default"  // optional
    }
    
    Requirements: 7.3
    """
    from flask_app.services.config_service import get_config_service
    
    data = request.get_json() or {}
    config_id = data.get('config_id', 'default')
    
    service = get_config_service()
    default_config = service.reset_config(config_id)
    
    return jsonify({
        'success': True,
        'config_id': config_id,
        'config': default_config.to_dict(),
        'message': 'Configuration reset to defaults'
    })


@bp.route('/config/options', methods=['GET'])
def get_config_options():
    """
    Get available configuration options.
    GET /api/config/options
    
    Requirements: 7.1, 7.2
    """
    from flask_app.services.config_service import get_config_service
    
    service = get_config_service()
    
    return jsonify({
        'color_schemes': service.get_available_color_schemes(),
        'themes': service.get_available_themes(),
        'locales': service.get_available_locales()
    })


# =============================================================================
# Parameter Template API - Requirements: 12.3, 12.4
# =============================================================================

@bp.route('/parameters/templates', methods=['GET'])
def list_parameter_templates():
    """
    Get all parameter templates.
    GET /api/parameters/templates
    
    Query parameters:
    - analysis_type: Filter by analysis type (optional)
    
    Requirements: 12.4
    """
    from services.parameter_template_service import get_parameter_template_service
    
    analysis_type = request.args.get('analysis_type')
    
    service = get_parameter_template_service()
    templates = service.get_templates(analysis_type)
    
    return jsonify({
        'templates': [t.to_dict() for t in templates],
        'total': len(templates)
    })


@bp.route('/parameters/templates/<template_id>', methods=['GET'])
def get_parameter_template(template_id):
    """
    Get a parameter template by ID.
    GET /api/parameters/templates/{template_id}
    
    Requirements: 12.4
    """
    from services.parameter_template_service import get_parameter_template_service
    
    service = get_parameter_template_service()
    template = service.get_template(template_id)
    
    if not template:
        raise ValidationError(
            message=f"Template not found: {template_id}",
            details={'template_id': template_id}
        )
    
    return jsonify(template.to_dict())


@bp.route('/parameters/templates', methods=['POST'])
def create_parameter_template():
    """
    Create a new parameter template.
    POST /api/parameters/templates
    
    Request body:
    {
        "name": "Template name",
        "analysis_type": "similarity_heatmap",
        "parameters": {...}
    }
    
    Requirements: 12.4
    """
    from services.parameter_template_service import get_parameter_template_service
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    name = data.get('name')
    analysis_type = data.get('analysis_type')
    parameters = data.get('parameters', {})
    
    if not name:
        raise ValidationError(
            message="Template name is required",
            details={'field': 'name'}
        )
    
    if not analysis_type:
        raise ValidationError(
            message="Analysis type is required",
            details={'field': 'analysis_type'}
        )
    
    service = get_parameter_template_service()
    
    # Validate parameters
    errors = service.validate_parameters(analysis_type, parameters)
    if errors:
        raise ValidationError(
            message="Invalid parameters",
            details={'validation_errors': errors}
        )
    
    template = service.save_template(
        name=name,
        analysis_type=analysis_type,
        parameters=parameters
    )
    
    return jsonify({
        'success': True,
        'template': template.to_dict(),
        'message': 'Parameter template created successfully'
    }), 201


@bp.route('/parameters/templates/<template_id>', methods=['PUT'])
def update_parameter_template(template_id):
    """
    Update a parameter template.
    PUT /api/parameters/templates/{template_id}
    
    Request body:
    {
        "name": "Updated name",
        "analysis_type": "similarity_heatmap",
        "parameters": {...}
    }
    
    Requirements: 12.4
    """
    from services.parameter_template_service import get_parameter_template_service
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    name = data.get('name')
    analysis_type = data.get('analysis_type')
    parameters = data.get('parameters', {})
    
    if not name:
        raise ValidationError(
            message="Template name is required",
            details={'field': 'name'}
        )
    
    if not analysis_type:
        raise ValidationError(
            message="Analysis type is required",
            details={'field': 'analysis_type'}
        )
    
    service = get_parameter_template_service()
    
    # Validate parameters
    errors = service.validate_parameters(analysis_type, parameters)
    if errors:
        raise ValidationError(
            message="Invalid parameters",
            details={'validation_errors': errors}
        )
    
    template = service.save_template(
        name=name,
        analysis_type=analysis_type,
        parameters=parameters,
        template_id=template_id
    )
    
    return jsonify({
        'success': True,
        'template': template.to_dict(),
        'message': 'Parameter template updated successfully'
    })


@bp.route('/parameters/templates/<template_id>', methods=['DELETE'])
def delete_parameter_template(template_id):
    """
    Delete a parameter template.
    DELETE /api/parameters/templates/{template_id}
    
    Requirements: 12.4
    """
    from services.parameter_template_service import get_parameter_template_service
    
    service = get_parameter_template_service()
    success = service.delete_template(template_id)
    
    return jsonify({
        'success': success,
        'message': 'Parameter template deleted successfully'
    })


@bp.route('/parameters/defaults/<analysis_type>', methods=['GET'])
def get_default_parameters(analysis_type):
    """
    Get default parameters for an analysis type.
    GET /api/parameters/defaults/{analysis_type}
    
    Requirements: 12.3
    """
    from services.parameter_template_service import get_parameter_template_service
    
    service = get_parameter_template_service()
    
    if analysis_type not in service.get_supported_analysis_types():
        raise ValidationError(
            message=f"Unsupported analysis type: {analysis_type}",
            details={
                'analysis_type': analysis_type,
                'supported_types': service.get_supported_analysis_types()
            }
        )
    
    defaults = service.get_default_parameters(analysis_type)
    
    return jsonify({
        'analysis_type': analysis_type,
        'parameters': defaults
    })


@bp.route('/parameters/validate', methods=['POST'])
def validate_parameters():
    """
    Validate parameters for an analysis type.
    POST /api/parameters/validate
    
    Request body:
    {
        "analysis_type": "similarity_heatmap",
        "parameters": {...}
    }
    
    Requirements: 12.3
    """
    from services.parameter_template_service import get_parameter_template_service
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    analysis_type = data.get('analysis_type')
    parameters = data.get('parameters', {})
    
    if not analysis_type:
        raise ValidationError(
            message="Analysis type is required",
            details={'field': 'analysis_type'}
        )
    
    service = get_parameter_template_service()
    errors = service.validate_parameters(analysis_type, parameters)
    
    return jsonify({
        'is_valid': len(errors) == 0,
        'errors': errors
    })


# =============================================================================
# Annotation API - Requirements: 12.5
# =============================================================================

