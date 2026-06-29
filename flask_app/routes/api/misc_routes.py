"""Miscellaneous routes: directories, color-schemes, sequencing-depth, deprecated analysis."""

from flask import Blueprint, request, jsonify, current_app

from flask_app.exceptions import ValidationError
from flask_app.services.path_access_service import PathAccessService

from ._common import _get_owned_file, logger

bp = Blueprint("api_misc_routes", __name__)


@bp.route('/directories', methods=['GET'])
def list_directories():
    """
    List directories for browsing.
    GET /api/directories?parent_path=/path/to/dir
    
    Requirements: 12.2, 12.3
    
    Query Parameters:
        parent_path: Optional parent directory path. If not provided, returns allowed base paths.
    
    Returns:
    {
        "current_path": "/path/to/dir",
        "directories": [
            {
                "name": "subdir1",
                "path": "/path/to/dir/subdir1",
                "has_children": true
            }
        ],
        "parent_path": "/path/to"
    }
    """
    parent_path = request.args.get('parent_path')
    
    try:
        visible = PathAccessService.filter_visible_children(parent_path or None)
        result = {
            'current_path': visible.get('current_path'),
            'directories': [
                {
                    'name': item['name'],
                    'path': item['path'],
                    'has_children': item.get('has_children', False),
                }
                for item in visible.get('items', [])
                if item.get('type') == 'directory'
            ],
            'parent_path': visible.get('parent_path'),
            'roots': visible.get('roots', []),
        }
        
        return jsonify(result)
        
    except ValidationError as e:
        raise
    except Exception as e:
        raise ValidationError(
            message=f"Failed to list directories: {str(e)}",
            details={
                'parent_path': parent_path,
                'error_type': type(e).__name__
            }
        )


@bp.route('/directories/validate', methods=['GET'])
def validate_directory():
    """
    Validate a directory path.
    GET /api/directories/validate?path=/path/to/dir
    
    Requirements: 12.4, 12.5
    
    Query Parameters:
        path: Directory path to validate
    
    Returns:
    {
        "valid": true,
        "exists": true,
        "is_directory": true,
        "readable": true,
        "message": "Path is valid"
    }
    """
    path = request.args.get('path')
    
    if not path:
        raise ValidationError(
            message="path parameter is required",
            details={'parameter': 'path'}
        )
    
    try:
        resolved = PathAccessService.validate_read_path(path)
        result = {
            'valid': resolved.is_dir(),
            'exists': resolved.exists(),
            'is_directory': resolved.is_dir(),
            'readable': os.access(resolved, os.R_OK),
            'message': 'Path is valid' if resolved.is_dir() else 'Path is not a directory',
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'valid': False,
            'exists': False,
            'is_directory': False,
            'readable': False,
            'message': str(e)
        })


# =============================================================================
# Color Scheme API - Requirements: 13.1, 13.2, 13.3, 13.4
# =============================================================================

@bp.route('/color-schemes', methods=['GET'])
def list_color_schemes():
    """
    List available color schemes.
    GET /api/color-schemes
    
    Requirements: 13.1
    
    Returns:
    {
        "schemes": [
            {
                "name": "viridis",
                "display_name": "Viridis",
                "type": "sequential",
                "description": "适合连续数据的颜色方�?,
                "colors": ["#440154", "#31688e", "#35b779", "#fde724"]
            }
        ],
        "default": "viridis"
    }
    """
    # Define available color schemes with their properties
    color_schemes = [
        {
            'name': 'viridis',
            'display_name': 'Viridis',
            'type': 'sequential',
            'description': '适合连续数据的颜色方案',
            'colors': ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde724']
        },
        {
            'name': 'plasma',
            'display_name': 'Plasma',
            'type': 'sequential',
            'description': '高对比度的连续颜色方案',
            'colors': ['#0d0887', '#46039f', '#7201a8', '#9c179e', '#bd3786', '#d8576b', '#ed7953', '#fb9f3a', '#fdca26', '#f0f921']
        },
        {
            'name': 'inferno',
            'display_name': 'Inferno',
            'type': 'sequential',
            'description': '暖色调的连续颜色方案',
            'colors': ['#000004', '#1b0c41', '#4a0c6b', '#781c6d', '#a52c60', '#cf4446', '#ed6925', '#fb9b06', '#f7d13d', '#fcffa4']
        },
        {
            'name': 'magma',
            'display_name': 'Magma',
            'type': 'sequential',
            'description': '深色到亮色的连续方案',
            'colors': ['#000004', '#180f3d', '#440f76', '#721f81', '#9e2f7f', '#cd4071', '#f1605d', '#fd9668', '#feca8d', '#fcfdbf']
        },
        {
            'name': 'cividis',
            'display_name': 'Cividis',
            'type': 'sequential',
            'description': '色盲友好的颜色方案',
            'colors': ['#00204d', '#00336f', '#31446b', '#575463', '#7c6556', '#a47449', '#cb8540', '#f39b3d', '#ffb945', '#ffd35c']
        },
        {
            'name': 'coolwarm',
            'display_name': 'Cool Warm',
            'type': 'diverging',
            'description': '冷暖对比的发散颜色方案',
            'colors': ['#3b4cc0', '#6788ee', '#9abbff', '#c9d7f0', '#edd1c2', '#f7a789', '#e26952', '#b40426']
        },
        {
            'name': 'RdYlBu',
            'display_name': 'Red-Yellow-Blue',
            'type': 'diverging',
            'description': '红黄蓝发散颜色方案',
            'colors': ['#a50026', '#d73027', '#f46d43', '#fdae61', '#fee090', '#e0f3f8', '#abd9e9', '#74add1', '#4575b4', '#313695']
        },
        {
            'name': 'Spectral',
            'display_name': 'Spectral',
            'type': 'diverging',
            'description': '光谱发散颜色方案',
            'colors': ['#9e0142', '#d53e4f', '#f46d43', '#fdae61', '#fee08b', '#e6f598', '#abdda4', '#66c2a5', '#3288bd', '#5e4fa2']
        },
        {
            'name': 'Set3',
            'display_name': 'Set 3',
            'type': 'qualitative',
            'description': '适合分类数据的颜色方案',
            'colors': ['#8dd3c7', '#ffffb3', '#bebada', '#fb8072', '#80b1d3', '#fdb462', '#b3de69', '#fccde5', '#d9d9d9', '#bc80bd']
        },
        {
            'name': 'Paired',
            'display_name': 'Paired',
            'type': 'qualitative',
            'description': '成对的分类颜色方案',
            'colors': ['#a6cee3', '#1f78b4', '#b2df8a', '#33a02c', '#fb9a99', '#e31a1c', '#fdbf6f', '#ff7f00', '#cab2d6', '#6a3d9a']
        }
    ]
    
    default_scheme = current_app.config.get('DEFAULT_COLOR_SCHEME', 'viridis')
    
    return jsonify({
        'schemes': color_schemes,
        'default': default_scheme
    })


@bp.route('/color-schemes/<scheme_name>', methods=['GET'])
def get_color_scheme(scheme_name):
    """
    Get details of a specific color scheme.
    GET /api/color-schemes/{scheme_name}
    
    Requirements: 13.1
    
    Returns:
    {
        "name": "viridis",
        "display_name": "Viridis",
        "type": "sequential",
        "description": "适合连续数据的颜色方�?,
        "colors": ["#440154", "#31688e", "#35b779", "#fde724"]
    }
    """
    # Get all schemes
    response = list_color_schemes()
    data = response.get_json()
    
    # Find the requested scheme
    scheme = next((s for s in data['schemes'] if s['name'] == scheme_name), None)
    
    if not scheme:
        raise ValidationError(
            message=f"Color scheme not found: {scheme_name}",
            details={
                'scheme_name': scheme_name,
                'available_schemes': [s['name'] for s in data['schemes']]
            }
        )
    
    return jsonify(scheme)


# =============================================================================
# Sequencing Depth Analysis API - Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8
# =============================================================================

@bp.route('/sequencing-depth/ppt', methods=['POST'])
def generate_sequencing_depth_ppt():
    """
    Generate PPT-ready sequencing depth visualizations.
    POST /api/sequencing-depth/ppt
    
    Requirements: 14.1, 14.4, 14.7
    
    Request Body:
    {
        "data_file": "/path/to/data.xlsx",
        "output_path": "/path/to/output",
        "parameters": {
            "baseline_sample": "NW_11_1030CT",
            "sample_filter": "NW_11_\\d{4}CT$",
            "sample_order": ["Sample1", "Sample2", ...]
        }
    }
    
    Returns:
    {
        "success": true,
        "result_id": "uuid",
        "table_file": "/path/to/table.png",
        "bar_chart_file": "/path/to/bar_chart.png",
        "baseline_sample": "NW_11_1030CT",
        "sample_count": 11
    }
    """
    from flask_app.services.sequencing_depth_ppt import SequencingDepthPPTService
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'expected': 'JSON object with data_file and output_path'}
        )
    
    data_file = data.get('data_file')
    output_path = data.get('output_path')
    parameters = data.get('parameters', {})
    
    if not data_file:
        raise ValidationError(
            message="data_file is required",
            details={'field': 'data_file'}
        )
    
    if not output_path:
        raise ValidationError(
            message="output_path is required",
            details={'field': 'output_path'}
        )
    
    try:
        # Generate result ID
        result_id = str(uuid.uuid4())
        
        # Create result directory
        result_dir = os.path.join(output_path, result_id)
        os.makedirs(result_dir, exist_ok=True)
        
        # Generate PPT modules
        result = SequencingDepthPPTService.generate_ppt(
            data_file=data_file,
            output_path=result_dir,
            parameters=parameters
        )
        
        if not result['success']:
            raise ValidationError(
                message=result.get('error', 'PPT generation failed'),
                details={'result': result}
            )
        
        # Add result ID to response
        result['result_id'] = result_id
        
        return jsonify(result)
        
    except Exception as e:
        raise ValidationError(
            message=f"Failed to generate PPT modules: {str(e)}",
            details={
                'data_file': data_file,
                'output_path': output_path,
                'error_type': type(e).__name__
            }
        )


@bp.route('/sequencing-depth/visualization', methods=['POST'])
def generate_sequencing_depth_visualization():
    """
    Generate comprehensive sequencing depth visualizations.
    POST /api/sequencing-depth/visualization
    
    Requirements: 14.2, 14.5, 14.7
    
    Request Body:
    {
        "data_file": "/path/to/data.xlsx",
        "output_path": "/path/to/output",
        "parameters": {
            "baseline_sample": "NW_11_1030CT",
            "sample_filter": "NW_11_\\d{4}CT$",
            "sample_order": ["Sample1", "Sample2", ...]
        }
    }
    
    Returns:
    {
        "success": true,
        "result_id": "uuid",
        "four_panel_file": "/path/to/four_panel.png",
        "quality_file": "/path/to/quality.png",
        "csv_file": "/path/to/data.csv",
        "baseline_sample": "NW_11_1030CT",
        "sample_count": 11
    }
    """
    from flask_app.services.sequencing_depth_viz import SequencingDepthVisualizationService
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'expected': 'JSON object with data_file and output_path'}
        )
    
    data_file = data.get('data_file')
    output_path = data.get('output_path')
    parameters = data.get('parameters', {})
    
    if not data_file:
        raise ValidationError(
            message="data_file is required",
            details={'field': 'data_file'}
        )
    
    if not output_path:
        raise ValidationError(
            message="output_path is required",
            details={'field': 'output_path'}
        )
    
    try:
        # Generate result ID
        result_id = str(uuid.uuid4())
        
        # Create result directory
        result_dir = os.path.join(output_path, result_id)
        os.makedirs(result_dir, exist_ok=True)
        
        # Generate visualizations
        result = SequencingDepthVisualizationService.generate_visualization(
            data_file=data_file,
            output_path=result_dir,
            parameters=parameters
        )
        
        if not result['success']:
            raise ValidationError(
                message=result.get('error', 'Visualization generation failed'),
                details={'result': result}
            )
        
        # Add result ID to response
        result['result_id'] = result_id
        
        return jsonify(result)
        
    except Exception as e:
        raise ValidationError(
            message=f"Failed to generate visualizations: {str(e)}",
            details={
                'data_file': data_file,
                'output_path': output_path,
                'error_type': type(e).__name__
            }
        )


@bp.route('/sequencing-depth/bar-chart', methods=['POST'])
def generate_sequencing_reads_bar_chart():
    """
    Generate sequencing reads bar charts by chain type.
    POST /api/sequencing-depth/bar-chart
    
    Requirements: 14.3, 14.6, 14.7
    
    Request Body:
    {
        "data_file": "/path/to/data.xlsx",
        "output_path": "/path/to/output",
        "parameters": {
            "baseline_sample": "NW_11_1030CT",
            "sample_filter": "NW_11_\\d{4}CT$",
            "sample_order": ["Sample1", "Sample2", ...]
        }
    }
    
    Returns:
    {
        "success": true,
        "result_id": "uuid",
        "tcr_file": "/path/to/tcr_chart.png",
        "ig_file": "/path/to/ig_chart.png",
        "csv_file": "/path/to/data.csv",
        "baseline_sample": "NW_11_1030CT",
        "sample_count": 11
    }
    """
    from flask_app.services.sequencing_reads_chart import SequencingReadsChartService
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'expected': 'JSON object with data_file and output_path'}
        )
    
    data_file = data.get('data_file')
    output_path = data.get('output_path')
    parameters = data.get('parameters', {})
    
    if not data_file:
        raise ValidationError(
            message="data_file is required",
            details={'field': 'data_file'}
        )
    
    if not output_path:
        raise ValidationError(
            message="output_path is required",
            details={'field': 'output_path'}
        )
    
    try:
        # Generate result ID
        result_id = str(uuid.uuid4())
        
        # Create result directory
        result_dir = os.path.join(output_path, result_id)
        os.makedirs(result_dir, exist_ok=True)
        
        # Generate bar charts
        result = SequencingReadsChartService.generate_bar_chart(
            data_file=data_file,
            output_path=result_dir,
            parameters=parameters
        )
        
        if not result['success']:
            raise ValidationError(
                message=result.get('error', 'Bar chart generation failed'),
                details={'result': result}
            )
        
        # Add result ID to response
        result['result_id'] = result_id
        
        return jsonify(result)
        
    except Exception as e:
        raise ValidationError(
            message=f"Failed to generate bar charts: {str(e)}",
            details={
                'data_file': data_file,
                'output_path': output_path,
                'error_type': type(e).__name__
            }
        )


@bp.route('/sequencing-depth/results/<result_id>', methods=['GET'])
def get_sequencing_depth_result(result_id):
    """
    Get sequencing depth analysis result files.
    GET /api/sequencing-depth/results/{result_id}
    
    Requirements: 14.8
    
    Query Parameters:
        file_type: Type of file to retrieve (table, bar_chart, four_panel, quality, tcr, ig, csv)
    
    Returns:
        File download or JSON with file paths
    """
    file_type = request.args.get('file_type')
    
    # Get results directory from configuration
    results_base = current_app.config.get('RESULTS_DIR', 'data/results')
    result_dir = os.path.join(results_base, result_id)
    
    if not os.path.exists(result_dir):
        raise ValidationError(
            message=f"Result not found: {result_id}",
            details={'result_id': result_id}
        )
    
    # If no file_type specified, return list of available files
    if not file_type:
        files = []
        for filename in os.listdir(result_dir):
            file_path = os.path.join(result_dir, filename)
            if os.path.isfile(file_path):
                files.append({
                    'name': filename,
                    'size': os.path.getsize(file_path),
                    'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
                })
        
        return jsonify({
            'result_id': result_id,
            'files': files
        })
    
    # Map file types to filenames
    file_mapping = {
        'table': 'sequencing_depth_table.png',
        'bar_chart': 'sequencing_depth_bar_chart.png',
        'four_panel': 'sequencing_metrics_four_panel.png',
        'quality': 'quality_metrics_comparison.png',
        'tcr': 'tcr_reads_percentage_change.png',
        'ig': 'ig_reads_percentage_change.png',
        'csv': 'sequencing_data.csv',
        'reads_csv': 'sequencing_reads_data.csv'
    }
    
    filename = file_mapping.get(file_type)
    if not filename:
        raise ValidationError(
            message=f"Invalid file_type: {file_type}",
            details={
                'file_type': file_type,
                'valid_types': list(file_mapping.keys())
            }
        )
    
    file_path = os.path.join(result_dir, filename)
    
    if not os.path.exists(file_path):
        raise ValidationError(
            message=f"File not found: {filename}",
            details={
                'result_id': result_id,
                'file_type': file_type,
                'filename': filename
            }
        )
    
    # Determine mimetype
    if filename.endswith('.png'):
        mimetype = 'image/png'
    elif filename.endswith('.csv'):
        mimetype = 'text/csv'
    else:
        mimetype = 'application/octet-stream'
    
    return send_file(
        file_path,
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename
    )




# =============================================================================
# Backward Compatibility API - DEPRECATED
# Requirements: 7.1, 7.2, 7.3
# These endpoints maintain backward compatibility with old analysis modules
# =============================================================================

@bp.route('/analysis/bcell-isotype', methods=['POST'])
def analyze_bcell_isotype_deprecated():
    """
    B细胞同型分析 (DEPRECATED)
    POST /api/analysis/bcell-isotype
    
    DEPRECATED: Use /api/analysis/execute-unified with scheme_id='bcell_isotype' instead
    Requirements: 7.1
    
    This endpoint is maintained for backward compatibility and will be removed in a future version.
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="Request body is required",
                details={'field': 'body'}
            )
        
        # Extract old format parameters
        file_id = data.get('file_id')
        field_mapping = data.get('field_mapping', {})
        parameters = data.get('parameters', {})
        
        if not file_id:
            raise ValidationError(
                message="File ID is required",
                details={'field': 'file_id'}
            )
        
        # Get file
        file_record = _get_owned_file(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # Read file data
        storage_path = Path(file_record.storage_path)
        if not storage_path.exists():
            raise StorageError(
                message=f"File not found in storage: {file_id}",
                details={'file_id': file_id}
            )
        
        with open(storage_path, 'rb') as f:
            file_content = f.read()
        df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
        
        # Call unified analysis service with bcell_isotype scheme
        service = get_unified_analysis_service()
        
        result = service.execute_analysis(
            file_id=file_id,
            data=df,
            mode='scheme',
            scheme_id='bcell_isotype',
            selected_fields=None,
            field_mapping=field_mapping,
            parameters=parameters
        )
        
        # Return response with deprecation header
        response = jsonify({
            'success': True,
            'analysis_id': result.get('id'),
            'status': result.get('status'),
            'results': {
                'charts': result.get('charts', []),
                'tables': result.get('tables', []),
                'statistics': result.get('statistics', {})
            }
        })
        
        # Add deprecation warning header
        response.headers['X-API-Deprecated'] = 'true'
        response.headers['X-API-Deprecation-Message'] = 'This endpoint is deprecated. Use /api/analysis/execute-unified instead.'
        response.headers['X-API-Sunset-Date'] = '2026-06-01'
        
        return response
    
    except Exception as e:
        logger.error(f"Error in deprecated bcell-isotype analysis: {e}", exc_info=True)
        return jsonify({
            'error': 'Analysis failed',
            'message': str(e)
        }), 500


@bp.route('/analysis/shm', methods=['POST'])
def analyze_shm_deprecated():
    """
    SHM分析 (DEPRECATED)
    POST /api/analysis/shm
    
    DEPRECATED: Use /api/analysis/execute-unified with scheme_id='shm_analysis' instead
    Requirements: 7.2
    
    This endpoint is maintained for backward compatibility and will be removed in a future version.
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="Request body is required",
                details={'field': 'body'}
            )
        
        # Extract old format parameters
        file_id = data.get('file_id')
        field_mapping = data.get('field_mapping', {})
        parameters = data.get('parameters', {})
        
        if not file_id:
            raise ValidationError(
                message="File ID is required",
                details={'field': 'file_id'}
            )
        
        # Get file
        file_record = _get_owned_file(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # Read file data
        storage_path = Path(file_record.storage_path)
        if not storage_path.exists():
            raise StorageError(
                message=f"File not found in storage: {file_id}",
                details={'file_id': file_id}
            )
        
        with open(storage_path, 'rb') as f:
            file_content = f.read()
        df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
        
        # Call unified analysis service with shm_analysis scheme
        service = get_unified_analysis_service()
        
        result = service.execute_analysis(
            file_id=file_id,
            data=df,
            mode='scheme',
            scheme_id='shm_analysis',
            selected_fields=None,
            field_mapping=field_mapping,
            parameters=parameters
        )
        
        # Return response with deprecation header
        response = jsonify({
            'success': True,
            'analysis_id': result.get('id'),
            'status': result.get('status'),
            'results': {
                'charts': result.get('charts', []),
                'tables': result.get('tables', []),
                'statistics': result.get('statistics', {})
            }
        })
        
        # Add deprecation warning header
        response.headers['X-API-Deprecated'] = 'true'
        response.headers['X-API-Deprecation-Message'] = 'This endpoint is deprecated. Use /api/analysis/execute-unified instead.'
        response.headers['X-API-Sunset-Date'] = '2026-06-01'
        
        return response
    
    except Exception as e:
        logger.error(f"Error in deprecated SHM analysis: {e}", exc_info=True)
        return jsonify({
            'error': 'Analysis failed',
            'message': str(e)
        }), 500


@bp.route('/analysis/ig-metrics', methods=['POST'])
def analyze_ig_metrics_deprecated():
    """
    IG指标分析 (DEPRECATED)
    POST /api/analysis/ig-metrics
    
    DEPRECATED: Use /api/analysis/execute-unified with scheme_id='ig_metrics' instead
    Requirements: 7.3
    
    This endpoint is maintained for backward compatibility and will be removed in a future version.
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="Request body is required",
                details={'field': 'body'}
            )
        
        # Extract old format parameters
        file_id = data.get('file_id')
        field_mapping = data.get('field_mapping', {})
        parameters = data.get('parameters', {})
        
        if not file_id:
            raise ValidationError(
                message="File ID is required",
                details={'field': 'file_id'}
            )
        
        # Get file
        file_record = _get_owned_file(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # Read file data
        storage_path = Path(file_record.storage_path)
        if not storage_path.exists():
            raise StorageError(
                message=f"File not found in storage: {file_id}",
                details={'file_id': file_id}
            )
        
        with open(storage_path, 'rb') as f:
            file_content = f.read()
        df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
        
        # Call unified analysis service with ig_metrics scheme
        service = get_unified_analysis_service()
        
        result = service.execute_analysis(
            file_id=file_id,
            data=df,
            mode='scheme',
            scheme_id='ig_metrics',
            selected_fields=None,
            field_mapping=field_mapping,
            parameters=parameters
        )
        
        # Return response with deprecation header
        response = jsonify({
            'success': True,
            'analysis_id': result.get('id'),
            'status': result.get('status'),
            'results': {
                'charts': result.get('charts', []),
                'tables': result.get('tables', []),
                'statistics': result.get('statistics', {})
            }
        })
        
        # Add deprecation warning header
        response.headers['X-API-Deprecated'] = 'true'
        response.headers['X-API-Deprecation-Message'] = 'This endpoint is deprecated. Use /api/analysis/execute-unified instead.'
        response.headers['X-API-Sunset-Date'] = '2026-06-01'
        
        return response
    
    except Exception as e:
        logger.error(f"Error in deprecated IG metrics analysis: {e}", exc_info=True)
        return jsonify({
            'error': 'Analysis failed',
            'message': str(e)
        }), 500


@bp.route('/analysis/custom-field', methods=['POST'])
def analyze_custom_field_deprecated():
    """
    自定义字段分析 (DEPRECATED)
    POST /api/analysis/custom-field
    
    DEPRECATED: Use /api/analysis/execute-unified with mode='custom' instead
    Requirements: 7.4
    
    This endpoint is maintained for backward compatibility and will be removed in a future version.
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="Request body is required",
                details={'field': 'body'}
            )
        
        # Extract old format parameters
        file_id = data.get('file_id')
        selected_fields = data.get('selected_fields', [])
        field_mapping = data.get('field_mapping', {})
        parameters = data.get('parameters', {})
        
        if not file_id:
            raise ValidationError(
                message="File ID is required",
                details={'field': 'file_id'}
            )
        
        if not selected_fields:
            raise ValidationError(
                message="Selected fields are required",
                details={'field': 'selected_fields'}
            )
        
        # Get file
        file_record = _get_owned_file(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # Read file data
        storage_path = Path(file_record.storage_path)
        if not storage_path.exists():
            raise StorageError(
                message=f"File not found in storage: {file_id}",
                details={'file_id': file_id}
            )
        
        with open(storage_path, 'rb') as f:
            file_content = f.read()
        df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
        
        # Call unified analysis service with custom mode
        service = get_unified_analysis_service()
        
        result = service.execute_analysis(
            file_id=file_id,
            data=df,
            mode='custom',
            scheme_id=None,
            selected_fields=selected_fields,
            field_mapping=field_mapping,
            parameters=parameters
        )
        
        # Return response with deprecation header
        response = jsonify({
            'success': True,
            'analysis_id': result.get('id'),
            'status': result.get('status'),
            'results': {
                'charts': result.get('charts', []),
                'tables': result.get('tables', []),
                'statistics': result.get('statistics', {})
            }
        })
        
        # Add deprecation warning header
        response.headers['X-API-Deprecated'] = 'true'
        response.headers['X-API-Deprecation-Message'] = 'This endpoint is deprecated. Use /api/analysis/execute-unified instead.'
        response.headers['X-API-Sunset-Date'] = '2026-06-01'
        
        return response
    
    except Exception as e:
        logger.error(f"Error in deprecated custom field analysis: {e}", exc_info=True)
        return jsonify({
            'error': 'Analysis failed',
            'message': str(e)
        }), 500
