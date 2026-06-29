"""Directory browsing, upload-folder, file-sheets, PPT generation, scanning."""

import re
from pathlib import Path

from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

from flask_app.exceptions import ValidationError
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.ppt_service import PPTService

from ._common import _get_owned_file, logger

bp = Blueprint("api_directories_files", __name__)


@bp.route('/field-mapping/suggest', methods=['GET'])
def suggest_field_mapping_get():
    """
    Suggest field mapping for a file and analysis type.
    GET /api/field-mapping/suggest?file_id=xxx&analysis_type=xxx
    """
    from flask_app.services.field_mapping import FieldMappingService
    
    file_id = request.args.get('file_id')
    analysis_type = request.args.get('analysis_type')
    
    if not file_id or not analysis_type:
        return jsonify({'error': 'File ID and analysis type are required'}), 400
    
    # Get file info
    try:
        file_record = _get_owned_file(file_id)
    except AppFileNotFoundError:
        return jsonify({'error': 'File not found'}), 404
    
    # Get required fields for analysis type
    supported_types = FieldMappingService.get_supported_analysis_types()
    if analysis_type not in supported_types:
        # Return empty mapping for unsupported types
        return jsonify({
            'required_fields': {},
            'columns': file_record.columns or [],
            'suggested_mapping': {},
            'confidence': 0
        })
    
    required_fields = FieldMappingService.get_required_fields(analysis_type)
    field_info = FieldMappingService.get_field_info(analysis_type)
    
    # Generate suggestion
    suggestion = FieldMappingService.suggest_mapping(
        columns=file_record.columns or [],
        analysis_type=analysis_type,
        saved_templates=[]
    )
    
    return jsonify({
        'required_fields': field_info,
        'columns': file_record.columns or [],
        'suggested_mapping': suggestion.mapping,
        'confidence': suggestion.confidence
    })


# =============================================================================
# Directory Scan API - For similarity analysis with directory input
# =============================================================================

@bp.route('/upload-folder', methods=['POST'])
def upload_folder():
    """
    Upload multiple files from a folder for similarity analysis.
    POST /api/upload-folder
    
    Accepts multipart form data with 'files' field containing multiple files.
    Returns the upload path where files are stored.
    """
    import re
    from pathlib import Path
    from werkzeug.utils import secure_filename
    
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files provided'}), 400
    
    # Create upload directory
    upload_base = Path(current_app.config.get('UPLOAD_FOLDER', 'data/uploads'))
    upload_id = str(uuid.uuid4())[:8]
    upload_dir = upload_base / f'similarity_{upload_id}'
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Pattern for valid files
    pattern = re.compile(r'^(.+)__([A-Z]{3,4})\.(csv\.gz|csv)$')
    
    saved_files = []
    samples = set()
    chains = set()
    
    for file in files:
        if file.filename:
            # Check if file matches pattern
            match = pattern.match(file.filename)
            if match:
                sample, chain, ext = match.groups()
                samples.add(sample)
                chains.add(chain)
                
                # Save file
                filename = secure_filename(file.filename)
                file_path = upload_dir / filename
                file.save(str(file_path))
                saved_files.append(filename)
    
    if not saved_files:
        return jsonify({'error': 'No valid files found matching pattern {sample}__{chain}.csv.gz'}), 400
    
    return jsonify({
        'upload_path': str(upload_dir),
        'samples': sorted(list(samples)),
        'chains': sorted(list(chains)),
        'files': saved_files,
        'total_files': len(saved_files)
    })


@bp.route('/file-sheets', methods=['POST'])
def file_sheets():
    """Return sheet names from an Excel (.xlsx) file."""
    data = request.get_json() or {}
    path = str(data.get('path', '')).strip()
    if not path:
        return jsonify({'success': False, 'message': 'path is required'}), 400

    try:
        target = Path(path)
        if not target.exists() or not target.is_file():
            return jsonify({'success': False, 'message': 'File not found'}), 404

        import openpyxl
        wb = openpyxl.load_workbook(target, read_only=True)
        sheets = wb.sheetnames
        wb.close()
        return jsonify({'success': True, 'sheets': sheets, 'count': len(sheets)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/browse-directory', methods=['GET'])
def browse_directory():
    """
    Browse directories on the server filesystem.
    GET /api/browse-directory?path=/some/path&filter=csv,tsv

    Query params:
        path: Absolute path to browse (default: auto-detect Linux root)
        filter: Optional comma-separated file extensions to show (e.g. "csv,tsv,csv.gz")
    """
    path = request.args.get('path', '')
    file_filter = request.args.get('filter', '')

    # Parse file filter
    allowed_extensions = set()
    if file_filter:
        allowed_extensions = {
            ext.strip().lower() if ext.strip().startswith('.') else f'.{ext.strip().lower()}'
            for ext in file_filter.split(',') if ext.strip()
        }

    try:
        return jsonify(PathAccessService.filter_visible_children(path or None, extensions=allowed_extensions))
    except ValidationError as exc:
        return jsonify({
            'error': exc.message,
            'details': exc.details,
            'items': [],
        }), 403

    except Exception as e:
        logger.exception("Unexpected error browsing directory: %s", path)
        return jsonify({'error': 'Internal server error while browsing directory'}), 500


@bp.route('/generate-ppt', methods=['POST'])
def generate_ppt():
    """
    Generate PPT-compatible charts.
    POST /api/generate-ppt
    
    Request body:
    {
        "analysis_type": "sequencing_depth",
        "data": {...}
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError("Request body is required")
        
        analysis_type = data.get('analysis_type')
        analysis_data = data.get('data', {})
        
        if analysis_type == 'sequencing_depth':
            result = PPTService.generate_sequencing_depth_ppt(analysis_data)
        else:
            raise ValidationError(f"Unsupported analysis type: {analysis_type}")
        
        return jsonify(result)
        
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"PPT generation error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/scan-directory', methods=['POST'])
def scan_directory():
    """
    Scan a directory for sample files matching pattern {sample}__{chain}.csv.gz
    Returns available samples and chains.
    
    Request body:
    {
        "path": "/path/to/data/directory"
    }
    """
    import re
    from pathlib import Path
    
    data = request.get_json()
    if not data or not data.get('path'):
        return jsonify({'error': 'Directory path is required'}), 400
    
    dir_path = Path(data['path'])
    
    if not dir_path.exists():
        return jsonify({'error': f'Directory not found: {dir_path}'}), 404
    
    if not dir_path.is_dir():
        return jsonify({'error': f'Path is not a directory: {dir_path}'}), 400
    
    # Pattern: {sample}__{chain}.csv.gz or {sample}__{chain}.csv
    pattern = re.compile(r'^(.+)__([A-Z]{3,4})\.(csv\.gz|csv)$')
    
    samples = set()
    chains = set()
    files = []
    
    for file_path in dir_path.iterdir():
        if file_path.is_file():
            match = pattern.match(file_path.name)
            if match:
                sample, chain, ext = match.groups()
                samples.add(sample)
                chains.add(chain)
                files.append({
                    'name': file_path.name,
                    'sample': sample,
                    'chain': chain,
                    'path': str(file_path)
                })
    
    # Sort for consistent output
    samples_list = sorted(list(samples))
    chains_list = sorted(list(chains))
    
    return jsonify({
        'path': str(dir_path),
        'samples': samples_list,
        'chains': chains_list,
        'files': files,
        'total_files': len(files)
    })


# =============================================================================
# Analysis API - Requirements: 8.1, 8.2, 8.3, 8.4
# =============================================================================

