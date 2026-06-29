"""Analysis job bridge: create, query, status, retry, cancel, image, download, etc."""

import math
from pathlib import Path

from flask import Blueprint, request, jsonify, current_app, send_file
from PIL import Image

from flask_app.exceptions import ValidationError
from flask_app.models.database import db, Analysis, AnalysisResult

from ._common import _get_owned_file, _get_owned_analysis, logger

bp = Blueprint("api_analysis_bridge", __name__)


@bp.route('/analysis', methods=['POST'])
def create_analysis():
    """
    Create a new analysis task.
    POST /api/analysis
    
    Requirements: 8.1
    
    Request body:
    {
        "type": "similarity_heatmap",
        "file_id": "uuid",
        "field_mapping": {"target_field": "source_column", ...},  // optional
        "parameters": {...},
        "chart_config": {...}
    }
    """
    from services.analysis_service import get_analysis_service
    from services.field_mapping import FieldMappingService
    
    data = request.get_json()

    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    # Validate required fields
    analysis_type = data.get('type')
    file_id = data.get('file_id')
    field_mapping = data.get('field_mapping')
    
    # For similarity_heatmap, support directory-based input
    directory_path = data.get('directory_path')
    selected_samples = data.get('selected_samples', [])
    selected_chains = data.get('selected_chains', [])
    enable_averaging = data.get('enable_averaging', False)
    sample_groups = data.get('sample_groups', [])
    
    if not analysis_type:
        raise ValidationError(
            message="Analysis type is required",
            details={'field': 'type'}
        )
    
    # For similarity_heatmap, directory_path is used instead of file_id
    if analysis_type == 'similarity_heatmap':
        if not directory_path:
            raise ValidationError(
                message="Directory path is required for similarity analysis",
                details={'field': 'directory_path'}
            )
        if len(selected_samples) < 2:
            raise ValidationError(
                message="At least 2 samples are required",
                details={'field': 'selected_samples'}
            )
        if len(selected_chains) < 1:
            raise ValidationError(
                message="At least 1 chain type is required",
                details={'field': 'selected_chains'}
            )
    elif not file_id:
        raise ValidationError(
            message="File ID is required",
            details={'field': 'file_id'}
        )
    
    # If field_mapping is not provided, generate a default mapping based on file columns
    # Skip for directory-based similarity analysis
    if analysis_type == 'similarity_heatmap':
        field_mapping = {}  # Not needed for directory-based analysis
    elif not field_mapping or not isinstance(field_mapping, dict):
        # Get file columns and suggest mapping
        file_record = _get_owned_file(file_id)
        if file_record and file_record.columns:
            # Try to auto-suggest mapping based on column names
            if analysis_type in FieldMappingService.get_supported_analysis_types():
                suggestion = FieldMappingService.suggest_mapping(
                    columns=file_record.columns,
                    analysis_type=analysis_type,
                    saved_templates=[]
                )
                field_mapping = suggestion.mapping
                
                # If mapping confidence is low, try case-insensitive matching
                if suggestion.confidence < 0.5:
                    required_fields = FieldMappingService.get_required_fields(analysis_type)
                    for field in required_fields:
                        if field not in field_mapping:
                            # Try case-insensitive direct match
                            for col in file_record.columns:
                                if col.lower() == field.lower():
                                    field_mapping[field] = col
                                    break
            else:
                # Create identity mapping for all columns
                field_mapping = {col: col for col in file_record.columns}
        else:
            field_mapping = {}
    
    # Validate field mapping has required fields (skip for directory-based similarity analysis)
    if analysis_type != 'similarity_heatmap' and analysis_type in FieldMappingService.get_supported_analysis_types():
        required_fields = FieldMappingService.get_required_fields(analysis_type)
        missing_fields = [field for field in required_fields if field not in field_mapping]
        
        if missing_fields and file_id:
            # Try to find missing fields with case-insensitive matching
            file_record = _get_owned_file(file_id)
            if file_record and file_record.columns:
                for field in missing_fields:
                    for col in file_record.columns:
                        if col.lower() == field.lower() or col.lower().replace(' ', '') == field.lower():
                            field_mapping[field] = col
                            break
    
    # Get optional parameters
    parameters = data.get('parameters', {})
    chart_config = data.get('chart_config', {})
    
    # Get baseline configuration if provided (Requirements: 3.7, 4.7, 5.7, 17.1, 17.2)
    baseline_config = data.get('baseline_config')
    if baseline_config:
        parameters['baseline_config'] = baseline_config
    
    # Get sample groups if provided
    sample_groups_from_request = data.get('sample_groups', [])
    if sample_groups_from_request:
        parameters['sample_groups'] = sample_groups_from_request
    
    # For similarity_heatmap, add directory info to parameters
    if analysis_type == 'similarity_heatmap':
        parameters['directory_path'] = str(PathAccessService.validate_read_path(directory_path))
        parameters['selected_samples'] = selected_samples
        parameters['selected_chains'] = selected_chains
        if enable_averaging:
            parameters['enable_averaging'] = True
            parameters['sample_groups'] = sample_groups
    else:
        # For file-based analysis, add sample_column and selected_samples to parameters
        sample_column = data.get('sample_column')
        if sample_column:
            parameters['sample_column'] = sample_column
        
        file_selected_samples = data.get('selected_samples', [])
        if file_selected_samples:
            parameters['selected_samples'] = file_selected_samples
    
    # Create analysis task
    service = get_analysis_service()
    analysis_id = service.create_analysis(
        analysis_type=analysis_type,
        file_id=file_id if analysis_type != 'similarity_heatmap' else None,
        field_mapping=field_mapping,
        parameters=parameters,
        chart_config=chart_config
    )
    
    return jsonify({
        'id': analysis_id,
        'status': 'pending',
        'message': 'Analysis task created successfully'
    }), 201


@bp.route('/analysis/<analysis_id>', methods=['GET'])
def get_analysis(analysis_id):
    """
    Get analysis details and results.
    GET /api/analysis/{analysis_id}
    
    Requirements: 8.4
    """
    from services.analysis_service import get_analysis_service
    
    _get_owned_analysis(analysis_id)
    service = get_analysis_service()
    results = service.get_analysis_results(analysis_id)
    
    return jsonify(results)


@bp.route('/analysis/<analysis_id>/status', methods=['GET'])
def get_analysis_status(analysis_id):
    """
    Get analysis task status.
    GET /api/analysis/{analysis_id}/status
    
    Requirements: 8.2
    """
    from services.analysis_service import get_analysis_service
    
    _get_owned_analysis(analysis_id)
    service = get_analysis_service()
    status = service.get_analysis_status(analysis_id)
    
    return jsonify(status)


@bp.route('/analysis/<analysis_id>/data/<table_name>', methods=['GET'])
def get_analysis_data_table(analysis_id, table_name):
    """
    Get a specific data table from analysis results.
    GET /api/analysis/{analysis_id}/data/{table_name}
    
    Requirements: 8.4
    """
    from services.analysis_service import get_analysis_service
    
    _get_owned_analysis(analysis_id)
    service = get_analysis_service()
    table_data = service.get_data_table(analysis_id, table_name)
    
    return jsonify(table_data)


@bp.route('/analysis/<analysis_id>/retry', methods=['POST'])
def retry_analysis(analysis_id):
    """
    Retry a failed analysis task.
    POST /api/analysis/{analysis_id}/retry
    
    Requirements: 8.3
    """
    from services.analysis_service import get_analysis_service
    
    _get_owned_analysis(analysis_id)
    service = get_analysis_service()
    success = service.retry_analysis(analysis_id)
    
    return jsonify({
        'success': success,
        'message': 'Analysis retry initiated' if success else 'Failed to retry analysis'
    })


@bp.route('/analysis/<analysis_id>/cancel', methods=['POST'])
def cancel_analysis(analysis_id):
    """
    Cancel a running analysis task.
    POST /api/analysis/{analysis_id}/cancel
    
    Requirements: 8.3
    """
    from services.analysis_service import get_analysis_service
    
    _get_owned_analysis(analysis_id)
    service = get_analysis_service()
    success = service.cancel_analysis(analysis_id)
    
    return jsonify({
        'success': success,
        'message': 'Analysis cancelled' if success else 'Failed to cancel analysis'
    })


@bp.route('/analysis/<analysis_id>/image/<result_name>', methods=['GET'])
def get_analysis_image(analysis_id, result_name):
    """
    Get a specific image from analysis results.
    GET /api/analysis/{analysis_id}/image/{result_name}
    """
    from models.database import Analysis, AnalysisResult
    from exceptions import AnalysisNotFoundError
    from pathlib import Path
    
    try:
        analysis = _get_owned_analysis(analysis_id)
    except AnalysisNotFoundError:
        return jsonify({'error': 'Analysis not found'}), 404
    
    # Find the result by name
    result = AnalysisResult.query.filter_by(
        analysis_id=analysis_id,
        name=result_name
    ).first()
    
    if not result or not result.file_path:
        return jsonify({'error': 'Result not found'}), 404
    
    file_path = Path(result.file_path)
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(
        file_path,
        mimetype=result.mime_type or 'image/png',
        as_attachment=False
    )


@bp.route('/analysis/<analysis_id>/download', methods=['GET'])
def download_analysis_result(analysis_id):
    """
    Download analysis result file.
    GET /api/analysis/{analysis_id}/download
    
    Query parameters:
    - result_name: Name of the result to download (optional for zip format)
    - format: Output format (png, csv, zip, all)
      - png: Download single heatmap as PNG image
      - csv: Download single heatmap data as CSV
      - all: Download single heatmap as ZIP with PNG and CSV
      - zip: Download all results as ZIP archive
    - include_metadata: Whether to include metadata (default: true)
    - custom_name: Custom name for ZIP file (optional)
    
    Requirements: 3.3, 3.4, 3.5, 6.1, 6.2, 6.3, 6.4
    """
    from services.export_service import get_export_service
    from exceptions import AnalysisNotFoundError
    
    result_name = request.args.get('result_name')
    export_format = request.args.get('format', 'png').lower()
    include_metadata = request.args.get('include_metadata', 'true').lower() == 'true'
    custom_name = request.args.get('custom_name')
    
    # Validate format
    if export_format not in ['png', 'csv', 'zip', 'all']:
        raise ValidationError(
            message=f"Unsupported export format: {export_format}",
            details={
                'format': export_format,
                'supported_formats': ['png', 'csv', 'zip', 'all']
            }
        )
    
    export_service = get_export_service()
    
    # Handle ZIP batch export (all results)
    if export_format == 'zip':
        file_bytes, filename, mime_type = export_service.export_all_results(
            analysis_id=analysis_id,
            include_metadata=include_metadata,
            custom_name=custom_name
        )
    else:
        # For PNG, CSV, and 'all', result_name is required
        if not result_name:
            raise ValidationError(
                message="Result name is required for PNG, CSV, and 'all' exports",
                details={'field': 'result_name'}
            )
        
        file_bytes, filename, mime_type = export_service.export_single_result(
            analysis_id=analysis_id,
            result_name=result_name,
            format=export_format,
            include_metadata=include_metadata
        )
    
    # Return file as download
    return send_file(
        io.BytesIO(file_bytes),
        mimetype=mime_type,
        as_attachment=True,
        download_name=filename
    )


@bp.route('/analysis/<analysis_id>/exports', methods=['GET'])
def get_available_exports(analysis_id):
    """
    Get list of available exports for an analysis.
    GET /api/analysis/{analysis_id}/exports
    
    Requirements: 6.1, 6.2, 6.3
    """
    from services.export_service import get_export_service
    
    export_service = get_export_service()
    exports = export_service.get_available_exports(analysis_id)
    
    return jsonify({
        'analysis_id': analysis_id,
        'exports': exports
    })


@bp.route('/analysis/<analysis_id>/merge-images', methods=['POST'])
def merge_analysis_images(analysis_id):
    """
    Merge multiple visualization images into a single image.
    POST /api/analysis/{analysis_id}/merge-images
    
    Request body:
    {
        "result_names": ["result1", "result2", ...],  // Names of results to merge
        "layout": "horizontal" | "vertical" | "grid",  // Layout mode (default: horizontal)
        "columns": 2,  // Number of columns for grid layout (default: 2)
        "spacing": 20,  // Spacing between images in pixels (default: 20)
        "background_color": "#ffffff"  // Background color (default: white)
    }
    
    Returns merged image as PNG download.
    """
    from PIL import Image
    from models.database import Analysis, AnalysisResult
    from exceptions import AnalysisNotFoundError
    import math
    
    # Get analysis
    analysis = _get_owned_analysis(analysis_id)
    if not analysis:
        raise AnalysisNotFoundError(
            message=f"Analysis not found: {analysis_id}",
            details={'analysis_id': analysis_id}
        )
    
    data = request.get_json()
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    result_names = data.get('result_names', [])
    if not result_names or len(result_names) < 1:
        raise ValidationError(
            message="At least 1 result name is required",
            details={'field': 'result_names'}
        )
    
    layout = data.get('layout', 'horizontal')
    columns = data.get('columns', 2)
    spacing = data.get('spacing', 20)
    background_color = data.get('background_color', '#ffffff')
    
    # Get visualization results
    results = AnalysisResult.query.filter(
        AnalysisResult.analysis_id == analysis_id,
        AnalysisResult.result_type == 'visualization',
        AnalysisResult.name.in_(result_names)
    ).all()
    
    if not results:
        raise ValidationError(
            message="No visualization results found for the specified names",
            details={'result_names': result_names}
        )
    
    # Sort results by the order in result_names
    result_map = {r.name: r for r in results}
    ordered_results = [result_map[name] for name in result_names if name in result_map]
    
    # Load images
    images = []
    for result in ordered_results:
        if result.file_path and Path(result.file_path).exists():
            try:
                img = Image.open(result.file_path)
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                images.append(img)
            except Exception as e:
                current_app.logger.warning(f"Failed to load image {result.file_path}: {e}")
    
    if not images:
        raise ValidationError(
            message="No valid images found to merge",
            details={'result_names': result_names}
        )
    
    # If only one image, return it directly
    if len(images) == 1:
        img_bytes = io.BytesIO()
        images[0].save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return send_file(
            img_bytes,
            mimetype='image/png',
            as_attachment=True,
            download_name=f'merged_{analysis_id}.png'
        )
    
    # Calculate merged image dimensions
    if layout == 'horizontal':
        total_width = sum(img.width for img in images) + spacing * (len(images) - 1)
        max_height = max(img.height for img in images)
        merged = Image.new('RGBA', (total_width, max_height), background_color)
        
        x_offset = 0
        for img in images:
            # Center vertically
            y_offset = (max_height - img.height) // 2
            merged.paste(img, (x_offset, y_offset))
            x_offset += img.width + spacing
            
    elif layout == 'vertical':
        max_width = max(img.width for img in images)
        total_height = sum(img.height for img in images) + spacing * (len(images) - 1)
        merged = Image.new('RGBA', (max_width, total_height), background_color)
        
        y_offset = 0
        for img in images:
            # Center horizontally
            x_offset = (max_width - img.width) // 2
            merged.paste(img, (x_offset, y_offset))
            y_offset += img.height + spacing
            
    else:  # grid layout
        rows = math.ceil(len(images) / columns)
        
        # Calculate cell dimensions (max width and height in each row/column)
        cell_width = max(img.width for img in images)
        cell_height = max(img.height for img in images)
        
        total_width = cell_width * columns + spacing * (columns - 1)
        total_height = cell_height * rows + spacing * (rows - 1)
        merged = Image.new('RGBA', (total_width, total_height), background_color)
        
        for i, img in enumerate(images):
            row = i // columns
            col = i % columns
            
            x_offset = col * (cell_width + spacing) + (cell_width - img.width) // 2
            y_offset = row * (cell_height + spacing) + (cell_height - img.height) // 2
            merged.paste(img, (x_offset, y_offset))
    
    # Convert to RGB for PNG output (remove alpha channel)
    if merged.mode == 'RGBA':
        background = Image.new('RGB', merged.size, background_color)
        background.paste(merged, mask=merged.split()[3])
        merged = background
    
    # Save to bytes
    img_bytes = io.BytesIO()
    merged.save(img_bytes, format='PNG', dpi=(300, 300))
    img_bytes.seek(0)
    
    return send_file(
        img_bytes,
        mimetype='image/png',
        as_attachment=True,
        download_name=f'merged_{analysis_id}.png'
    )


@bp.route('/analysis/types', methods=['GET'])
def get_analysis_types():
    """
    Get available analysis types.
    GET /api/analysis/types
    """
    from services.analysis_service import AnalysisType
    
    types = [
        {
            'id': AnalysisType.SIMILARITY_HEATMAP.value,
            'name': 'Similarity Heatmap',
            'description': 'Generate similarity heatmaps using various metrics'
        },
        {
            'id': AnalysisType.SEQUENCING_DEPTH.value,
            'name': 'Sequencing Depth',
            'description': 'Analyze sequencing depth and quality metrics'
        },
        {
            'id': AnalysisType.DIVERSITY_METRICS.value,
            'name': 'Diversity Metrics',
            'description': 'Calculate diversity metrics (D50, Gini, Shannon, Simpson)'
        },
        {
            'id': AnalysisType.CHAIN_SPECIFIC.value,
            'name': 'Chain-Specific Analysis',
            'description': 'Analyze immune receptor chains (IGH, IGK, IGL, TRA, TRB, TRD, TRG)'
        }
    ]
    
    return jsonify({'types': types})


# =============================================================================
# Configuration API - Requirements: 7.3, 7.4, 12.3, 12.4, 12.5
# =============================================================================

