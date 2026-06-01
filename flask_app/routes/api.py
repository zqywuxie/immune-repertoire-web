"""
API routes for the Immune Repertoire Analysis Web Application.
Provides RESTful endpoints for file management, analysis, and configuration.
"""
import io
import os
import platform
import uuid
import logging
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, jsonify, current_app, send_file
from flask_app.services.analysis_service import get_analysis_service
from flask_app.services.ppt_service import PPTService
from flask_app.services.file_parser import FileParserService
from flask_app.services.unified_analysis_service import get_unified_analysis_service
from flask_app.models.database import db, File, Analysis, Annotation, CustomParameter
from flask_app.exceptions import (
    ValidationError,
    FileFormatInvalidError, 
    FileParseError, 
    FileNotFoundError as AppFileNotFoundError,
    StorageError,
    AnalysisNotFoundError
)

# Initialize logger
logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


@api_bp.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'})


@api_bp.route('/info')
def app_info():
    """Application info endpoint."""
    return jsonify({
        'name': current_app.config['APP_NAME'],
        'version': current_app.config['APP_VERSION'],
        'status': 'running'
    })


# =============================================================================
# File Management API - Requirements: 1.1, 1.4, 1.5, 1.6
# =============================================================================

@api_bp.route('/files/upload', methods=['POST'])
def upload_file():
    """
    Upload a data file.
    POST /api/files/upload
    
    Requirements: 1.1, 1.4
    - Accepts CSV, Excel (.xlsx), and gzip-compressed CSV (.csv.gz) formats
    - Validates file structure and displays column information
    - Persists files to database
    """
    # Check if file is present in request
    if 'file' not in request.files:
        raise ValidationError(
            message="No file provided in request",
            details={'field': 'file'}
        )
    
    file = request.files['file']
    
    # Check if filename is empty
    if file.filename == '':
        raise ValidationError(
            message="No file selected",
            details={'field': 'file'}
        )
    
    filename = file.filename
    
    # Validate file extension
    if not FileParserService.validate_extension(filename):
        ext = Path(filename).suffix
        raise FileFormatInvalidError(
            message=f"Unsupported file format: {ext}",
            details={
                'provided_extension': ext,
                'supported_extensions': list(FileParserService.SUPPORTED_EXTENSIONS)
            }
        )
    
    # Read file content
    file_content = file.read()
    
    if len(file_content) == 0:
        raise ValidationError(
            message="Uploaded file is empty",
            details={'field': 'file'}
        )
    
    # Parse file to extract columns and row count
    try:
        df, columns, row_count = FileParserService.parse_file(file_content, filename)
    except (FileFormatInvalidError, FileParseError):
        raise
    except Exception as e:
        raise FileParseError(
            message=f"Failed to parse file: {str(e)}",
            details={'filename': filename}
        )
    
    # Generate unique file ID and storage path
    file_id = str(uuid.uuid4())
    ext = FileParserService.get_extension(filename)
    storage_filename = f"{file_id}{ext}"
    storage_path = Path(current_app.config['UPLOAD_FOLDER']) / storage_filename
    
    # Save file to disk
    try:
        with open(storage_path, 'wb') as f:
            f.write(file_content)
    except Exception as e:
        raise StorageError(
            message=f"Failed to save file: {str(e)}",
            details={'filename': filename}
        )
    
    # Get project name from form data (default to 'default')
    project = request.form.get('project', 'default') or 'default'
    
    # Create database record
    try:
        file_record = File(
            id=file_id,
            name=storage_filename,
            original_name=filename,
            size=len(file_content),
            mime_type=FileParserService.get_mime_type(filename),
            columns=columns,
            row_count=row_count,
            storage_path=str(storage_path),
            uploaded_at=datetime.utcnow(),
            project=project
        )
        db.session.add(file_record)
        db.session.commit()
    except Exception as e:
        # Clean up file if database save fails
        if storage_path.exists():
            storage_path.unlink()
        db.session.rollback()
        raise StorageError(
            message=f"Failed to save file record: {str(e)}",
            details={'filename': filename}
        )
    
    # Return success response with file metadata
    return jsonify({
        'id': file_id,
        'name': filename,
        'size': len(file_content),
        'columns': columns,
        'row_count': row_count,
        'uploaded_at': file_record.uploaded_at.isoformat(),
        'project': project
    }), 201


@api_bp.route('/files/upload-multiple', methods=['POST'])
def upload_multiple_files():
    """
    Upload multiple data files.
    POST /api/files/upload-multiple
    
    Accepts multiple files in a single request.
    Returns an array of uploaded file metadata.
    """
    # Check if files are present in request
    if 'files' not in request.files:
        raise ValidationError(
            message="No files provided in request",
            details={'field': 'files'}
        )
    
    files = request.files.getlist('files')
    
    if not files or len(files) == 0:
        raise ValidationError(
            message="No files selected",
            details={'field': 'files'}
        )
    
    uploaded_files = []
    errors = []
    
    # Process each file
    for i, file in enumerate(files):
        if file.filename == '':
            errors.append({
                'index': i,
                'filename': '',
                'error': 'Empty filename'
            })
            continue
        
        filename = file.filename
        
        # Validate file extension
        if not FileParserService.validate_extension(filename):
            ext = Path(filename).suffix
            errors.append({
                'index': i,
                'filename': filename,
                'error': f"Unsupported file format: {ext}"
            })
            continue
        
        # Read file content
        file_content = file.read()
        
        if len(file_content) == 0:
            errors.append({
                'index': i,
                'filename': filename,
                'error': 'File is empty'
            })
            continue
        
        # Parse file to extract columns and row count
        try:
            df, columns, row_count = FileParserService.parse_file(file_content, filename)
        except (FileFormatInvalidError, FileParseError) as e:
            errors.append({
                'index': i,
                'filename': filename,
                'error': str(e)
            })
            continue
        except Exception as e:
            errors.append({
                'index': i,
                'filename': filename,
                'error': f"Failed to parse file: {str(e)}"
            })
            continue
        
        # Generate unique file ID and storage path
        file_id = str(uuid.uuid4())
        ext = FileParserService.get_extension(filename)
        storage_filename = f"{file_id}{ext}"
        storage_path = Path(current_app.config['UPLOAD_FOLDER']) / storage_filename
        
        # Save file to disk
        try:
            with open(storage_path, 'wb') as f:
                f.write(file_content)
        except Exception as e:
            errors.append({
                'index': i,
                'filename': filename,
                'error': f"Failed to save file: {str(e)}"
            })
            continue
        
        # Create database record
        try:
            file_record = File(
                id=file_id,
                name=storage_filename,
                original_name=filename,
                size=len(file_content),
                mime_type=FileParserService.get_mime_type(filename),
                columns=columns,
                row_count=row_count,
                storage_path=str(storage_path),
                uploaded_at=datetime.utcnow()
            )
            db.session.add(file_record)
            db.session.commit()
            
            uploaded_files.append({
                'id': file_id,
                'name': filename,
                'size': len(file_content),
                'columns': columns,
                'row_count': row_count,
                'uploaded_at': file_record.uploaded_at.isoformat()
            })
            
        except Exception as e:
            # Clean up file if database save fails
            if storage_path.exists():
                storage_path.unlink()
            db.session.rollback()
            errors.append({
                'index': i,
                'filename': filename,
                'error': f"Failed to save file record: {str(e)}"
            })
            continue
    
    return jsonify({
        'uploaded_files': uploaded_files,
        'total_uploaded': len(uploaded_files),
        'total_errors': len(errors),
        'errors': errors
    }), 201

@api_bp.route('/files/projects', methods=['GET'])
def list_projects():
    """
    Get all project names.
    GET /api/files/projects
    """
    # Get distinct project names
    projects = db.session.query(File.project).distinct().all()
    project_list = [p[0] for p in projects if p[0]]
    
    # Ensure 'default' is always included
    if 'default' not in project_list:
        project_list.insert(0, 'default')
    else:
        # Move 'default' to the front
        project_list.remove('default')
        project_list.insert(0, 'default')
    
    return jsonify({
        'projects': project_list
    })


@api_bp.route('/files', methods=['GET'])
def list_files():
    """
    Get all uploaded files.
    GET /api/files
    
    Query parameters:
    - project: Filter by project name (optional)
    
    Requirements: 1.5
    """
    project = request.args.get('project')
    
    query = File.query
    if project:
        query = query.filter(File.project == project)
    
    files = query.order_by(File.uploaded_at.desc()).all()
    
    return jsonify({
        'files': [
            {
                'id': f.id,
                'name': f.original_name,
                'size': f.size,
                'columns': f.columns,
                'column_count': len(f.columns),
                'row_count': f.row_count,
                'uploaded_at': f.uploaded_at.isoformat(),
                'project': f.project or 'default'
            }
            for f in files
        ],
        'total': len(files)
    })


@api_bp.route('/files/<file_id>', methods=['GET'])
def get_file(file_id):
    """
    Get file details by ID.
    GET /api/files/{file_id}
    
    Requirements: 1.5, 1.6
    """
    file_record = File.query.get(file_id)
    
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Get sample data from file
    storage_path = Path(file_record.storage_path)
    sample_data = []
    
    if storage_path.exists():
        try:
            with open(storage_path, 'rb') as f:
                file_content = f.read()
            df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
            # Return all data for analysis (not just 10 rows)
            sample_data = FileParserService.get_sample_data(df, n_rows=df.shape[0])
        except Exception:
            # If we can't read sample data, just return empty list
            pass
    
    return jsonify({
        'id': file_record.id,
        'name': file_record.original_name,
        'size': file_record.size,
        'columns': file_record.columns,
        'column_count': len(file_record.columns),
        'row_count': file_record.row_count,
        'sample_data': sample_data,
        'uploaded_at': file_record.uploaded_at.isoformat()
    })


@api_bp.route('/files/<file_id>/column-values', methods=['GET'])
def get_column_values(file_id):
    """
    Get unique values from a specific column in a file.
    GET /api/files/{file_id}/column-values?column=column_name
    
    Returns unique values for sample detection.
    """
    file_record = File.query.get(file_id)
    
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    column_name = request.args.get('column')
    if not column_name:
        raise ValidationError(
            message="Column name is required",
            details={'parameter': 'column'}
        )
    
    if column_name not in file_record.columns:
        raise ValidationError(
            message=f"Column '{column_name}' not found in file",
            details={'column': column_name, 'available_columns': file_record.columns}
        )
    
    storage_path = Path(file_record.storage_path)
    values = []
    
    if storage_path.exists():
        try:
            with open(storage_path, 'rb') as f:
                file_content = f.read()
            df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
            # Get unique values, drop NaN, convert to string, and sort
            unique_values = df[column_name].dropna().unique().tolist()
            values = sorted([str(v) for v in unique_values])
        except Exception as e:
            raise ValidationError(
                message=f"Failed to read column values: {str(e)}",
                details={'error': str(e)}
            )
    
    return jsonify({
        'column': column_name,
        'values': values,
        'count': len(values)
    })


@api_bp.route('/files/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    """
    Delete a file by ID.
    DELETE /api/files/{file_id}
    
    Requirements: 1.6
    """
    file_record = File.query.get(file_id)
    
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Delete file from disk
    storage_path = Path(file_record.storage_path)
    if storage_path.exists():
        try:
            storage_path.unlink()
        except Exception as e:
            raise StorageError(
                message=f"Failed to delete file from storage: {str(e)}",
                details={'file_id': file_id}
            )
    
    # Delete database record
    try:
        db.session.delete(file_record)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise StorageError(
            message=f"Failed to delete file record: {str(e)}",
            details={'file_id': file_id}
        )
    
    return jsonify({
        'success': True,
        'message': f"File '{file_record.original_name}' deleted successfully"
    })


@api_bp.route('/files/<file_id>/download', methods=['GET'])
def download_file(file_id):
    """
    Download a file by ID.
    GET /api/files/{file_id}/download
    """
    file_record = File.query.get(file_id)
    
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    storage_path = Path(file_record.storage_path)
    if not storage_path.exists():
        raise AppFileNotFoundError(
            message=f"File not found on disk: {file_id}",
            details={'file_id': file_id}
        )
    
    return send_file(
        storage_path,
        as_attachment=True,
        download_name=file_record.original_name,
        mimetype=file_record.mime_type
    )


@api_bp.route('/files/<file_id>/rename', methods=['PUT'])
def rename_file(file_id):
    """
    Rename a file by ID.
    PUT /api/files/{file_id}/rename
    Body: { "name": "new_filename.csv" }
    """
    file_record = File.query.get(file_id)
    
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    data = request.get_json()
    if not data or 'name' not in data:
        raise ValidationError(
            message="New filename is required",
            details={'field': 'name'}
        )
    
    new_name = data['name'].strip()
    if not new_name:
        raise ValidationError(
            message="Filename cannot be empty",
            details={'field': 'name'}
        )
    
    # Validate extension matches original
    old_ext = FileParserService.get_extension(file_record.original_name)
    new_ext = FileParserService.get_extension(new_name)
    
    if old_ext != new_ext:
        raise ValidationError(
            message=f"File extension cannot be changed. Expected: {old_ext}",
            details={'field': 'name', 'expected_extension': old_ext}
        )
    
    try:
        file_record.original_name = new_name
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise StorageError(
            message=f"Failed to rename file: {str(e)}",
            details={'file_id': file_id}
        )
    
    return jsonify({
        'success': True,
        'id': file_record.id,
        'name': file_record.original_name,
        'message': f"File renamed to '{new_name}'"
    })


@api_bp.route('/files/<file_id>/preview', methods=['GET'])
def preview_file(file_id):
    """
    Get file preview with data content.
    GET /api/files/{file_id}/preview?rows=50&offset=0
    """
    file_record = File.query.get(file_id)
    
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Get pagination parameters
    rows = request.args.get('rows', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    # Limit max rows
    rows = min(rows, 500)
    
    storage_path = Path(file_record.storage_path)
    if not storage_path.exists():
        raise AppFileNotFoundError(
            message=f"File not found on disk: {file_id}",
            details={'file_id': file_id}
        )
    
    # Check if it's a PDF file
    if file_record.original_name.lower().endswith('.pdf'):
        return jsonify({
            'id': file_record.id,
            'name': file_record.original_name,
            'is_pdf': True,
            'message': 'PDF files cannot be previewed as data'
        })
    
    try:
        with open(storage_path, 'rb') as f:
            file_content = f.read()
        
        df, columns, total_rows = FileParserService.parse_file(
            file_content, file_record.original_name
        )
        
        # Apply pagination
        df_slice = df.iloc[offset:offset + rows]
        
        # Convert to records, handling NaN values
        import numpy as np
        df_slice = df_slice.replace({np.nan: None})
        data = df_slice.to_dict('records')
        
        return jsonify({
            'id': file_record.id,
            'name': file_record.original_name,
            'columns': columns,
            'data': data,
            'total_rows': total_rows,
            'offset': offset,
            'rows_returned': len(data),
            'has_more': offset + len(data) < total_rows
        })
        
    except Exception as e:
        raise FileParseError(
            message=f"Failed to preview file: {str(e)}",
            details={'file_id': file_id}
        )


@api_bp.route('/files/search', methods=['GET'])
def search_files():
    """
    Search files by name or filter by various criteria.
    GET /api/files/search?q=keyword&project=xxx&type=data|pdf&sort=name|date|size&order=asc|desc
    """
    query_str = request.args.get('q', '').strip()
    project = request.args.get('project', '')
    file_type = request.args.get('type', '')  # 'data' or 'pdf'
    sort_by = request.args.get('sort', 'date')  # 'name', 'date', 'size'
    order = request.args.get('order', 'desc')  # 'asc' or 'desc'
    
    query = File.query
    
    # Filter by search query
    if query_str:
        query = query.filter(File.original_name.ilike(f'%{query_str}%'))
    
    # Filter by project
    if project:
        query = query.filter(File.project == project)
    
    # Filter by file type
    if file_type == 'pdf':
        query = query.filter(File.original_name.ilike('%.pdf'))
    elif file_type == 'data':
        query = query.filter(~File.original_name.ilike('%.pdf'))
    
    # Apply sorting
    if sort_by == 'name':
        sort_column = File.original_name
    elif sort_by == 'size':
        sort_column = File.size
    else:  # default to date
        sort_column = File.uploaded_at
    
    if order == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())
    
    files = query.all()
    
    return jsonify({
        'files': [
            {
                'id': f.id,
                'name': f.original_name,
                'size': f.size,
                'columns': f.columns,
                'column_count': len(f.columns) if f.columns else 0,
                'row_count': f.row_count,
                'uploaded_at': f.uploaded_at.isoformat(),
                'project': f.project or 'default'
            }
            for f in files
        ],
        'total': len(files),
        'query': query_str,
        'filters': {
            'project': project,
            'type': file_type,
            'sort': sort_by,
            'order': order
        }
    })


@api_bp.route('/detect-samples', methods=['POST'])
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
    file_record = File.query.get(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
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

@api_bp.route('/mappings', methods=['POST'])
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
            analysis_type=analysis_type
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


@api_bp.route('/mappings', methods=['GET'])
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
    
    query = MappingTemplate.query
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


@api_bp.route('/mappings/<template_id>', methods=['GET'])
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
    
    return jsonify({
        'id': template.id,
        'name': template.name,
        'mapping': template.mapping,
        'analysis_type': template.analysis_type,
        'created_at': template.created_at.isoformat(),
        'updated_at': template.updated_at.isoformat()
    })


@api_bp.route('/mappings/<template_id>', methods=['DELETE'])
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


@api_bp.route('/mappings/suggest', methods=['POST'])
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
    templates = MappingTemplate.query.filter_by(analysis_type=analysis_type).all()
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


@api_bp.route('/mappings/validate', methods=['POST'])
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


@api_bp.route('/mappings/fields/<analysis_type>', methods=['GET'])
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

@api_bp.route('/field-mapping/suggest', methods=['GET'])
def suggest_field_mapping_get():
    """
    Suggest field mapping for a file and analysis type.
    GET /api/field-mapping/suggest?file_id=xxx&analysis_type=xxx
    """
    from services.field_mapping import FieldMappingService
    
    file_id = request.args.get('file_id')
    analysis_type = request.args.get('analysis_type')
    
    if not file_id or not analysis_type:
        return jsonify({'error': 'File ID and analysis type are required'}), 400
    
    # Get file info
    file_record = File.query.get(file_id)
    if not file_record:
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

@api_bp.route('/upload-folder', methods=['POST'])
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


@api_bp.route('/browse-directory', methods=['GET'])
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

    # Auto-detect reasonable root on Linux
    if not path:
        if platform.system() == 'Linux':
            candidates = ['/data', '/home', '/mnt', '/opt', '/srv', '/']
        else:
            candidates = [
                str(Path.home() / 'Data'),
                str(Path.home()),
                'C:/Data', 'D:/Data', 'E:/Data',
            ]

        for candidate in candidates:
            p = Path(candidate)
            if p.exists() and p.is_dir():
                path = str(p)
                break
        else:
            path = str(Path.cwd())

    try:
        resolved = Path(path).resolve()

        # Security: block sensitive system paths on Linux
        restricted_prefixes = ['/sys', '/proc', '/dev', '/run', '/boot', '/etc', '/root']
        if platform.system() == 'Linux':
            for prefix in restricted_prefixes:
                if str(resolved).startswith(prefix):
                    return jsonify({
                        'error': 'Access denied: system directory restricted',
                        'current_path': str(resolved),
                        'parent_path': str(resolved.parent) if resolved.parent != resolved else None,
                        'items': [],
                    }), 403

        if not resolved.exists():
            return jsonify({
                'error': 'Directory not found',
                'current_path': str(resolved),
                'parent_path': str(resolved.parent) if resolved.parent != resolved else None,
                'items': [],
            }), 404

        if not resolved.is_dir():
            return jsonify({'error': 'Path is not a directory'}), 400

        items = []
        try:
            for item in sorted(resolved.iterdir()):
                try:
                    is_dir = item.is_dir()
                    # Use suffixes (plural) to support compound extensions like .csv.gz
                    suffix = ''.join(item.suffixes).lower()

                    # Apply file filter
                    if not is_dir and allowed_extensions and suffix not in allowed_extensions:
                        continue

                    # Skip hidden items (start with .)
                    if item.name.startswith('.'):
                        continue

                    # Check if directory has children (for expand icon)
                    has_children = False
                    if is_dir:
                        try:
                            has_children = any(
                                not child.name.startswith('.')
                                for child in item.iterdir()
                            )
                        except (PermissionError, OSError):
                            has_children = False

                    item_info = {
                        'name': item.name,
                        'path': str(item),
                        'type': 'directory' if is_dir else 'file',
                        'suffix': suffix if not is_dir else '',
                        'has_children': has_children,
                    }
                    items.append(item_info)
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError) as e:
            return jsonify({'error': f'Cannot read directory: {str(e)}'}), 403

        parent_path = str(resolved.parent) if resolved.parent != resolved else None
        # Don't allow navigating above filesystem root
        if parent_path and not Path(parent_path).exists():
            parent_path = None

        return jsonify({
            'current_path': str(resolved),
            'parent_path': parent_path,
            'items': items,
            'platform': platform.system(),
        })

    except Exception as e:
        logger.exception("Unexpected error browsing directory: %s", path)
        return jsonify({'error': 'Internal server error while browsing directory'}), 500


@api_bp.route('/generate-ppt', methods=['POST'])
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


@api_bp.route('/scan-directory', methods=['POST'])
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

@api_bp.route('/analysis', methods=['POST'])
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
        file_record = File.query.get(file_id)
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
            file_record = File.query.get(file_id)
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
        parameters['directory_path'] = directory_path
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


@api_bp.route('/analysis/<analysis_id>', methods=['GET'])
def get_analysis(analysis_id):
    """
    Get analysis details and results.
    GET /api/analysis/{analysis_id}
    
    Requirements: 8.4
    """
    from services.analysis_service import get_analysis_service
    
    service = get_analysis_service()
    results = service.get_analysis_results(analysis_id)
    
    return jsonify(results)


@api_bp.route('/analysis/<analysis_id>/status', methods=['GET'])
def get_analysis_status(analysis_id):
    """
    Get analysis task status.
    GET /api/analysis/{analysis_id}/status
    
    Requirements: 8.2
    """
    from services.analysis_service import get_analysis_service
    
    service = get_analysis_service()
    status = service.get_analysis_status(analysis_id)
    
    return jsonify(status)


@api_bp.route('/analysis/<analysis_id>/data/<table_name>', methods=['GET'])
def get_analysis_data_table(analysis_id, table_name):
    """
    Get a specific data table from analysis results.
    GET /api/analysis/{analysis_id}/data/{table_name}
    
    Requirements: 8.4
    """
    from services.analysis_service import get_analysis_service
    
    service = get_analysis_service()
    table_data = service.get_data_table(analysis_id, table_name)
    
    return jsonify(table_data)


@api_bp.route('/analysis/<analysis_id>/retry', methods=['POST'])
def retry_analysis(analysis_id):
    """
    Retry a failed analysis task.
    POST /api/analysis/{analysis_id}/retry
    
    Requirements: 8.3
    """
    from services.analysis_service import get_analysis_service
    
    service = get_analysis_service()
    success = service.retry_analysis(analysis_id)
    
    return jsonify({
        'success': success,
        'message': 'Analysis retry initiated' if success else 'Failed to retry analysis'
    })


@api_bp.route('/analysis/<analysis_id>/cancel', methods=['POST'])
def cancel_analysis(analysis_id):
    """
    Cancel a running analysis task.
    POST /api/analysis/{analysis_id}/cancel
    
    Requirements: 8.3
    """
    from services.analysis_service import get_analysis_service
    
    service = get_analysis_service()
    success = service.cancel_analysis(analysis_id)
    
    return jsonify({
        'success': success,
        'message': 'Analysis cancelled' if success else 'Failed to cancel analysis'
    })


@api_bp.route('/analysis/<analysis_id>/image/<result_name>', methods=['GET'])
def get_analysis_image(analysis_id, result_name):
    """
    Get a specific image from analysis results.
    GET /api/analysis/{analysis_id}/image/{result_name}
    """
    from models.database import Analysis, AnalysisResult
    from exceptions import AnalysisNotFoundError
    from pathlib import Path
    
    analysis = Analysis.query.get(analysis_id)
    if not analysis:
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


@api_bp.route('/analysis/<analysis_id>/download', methods=['GET'])
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


@api_bp.route('/analysis/<analysis_id>/exports', methods=['GET'])
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


@api_bp.route('/analysis/<analysis_id>/merge-images', methods=['POST'])
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
    analysis = Analysis.query.get(analysis_id)
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


@api_bp.route('/analysis/types', methods=['GET'])
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

@api_bp.route('/config', methods=['GET'])
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


@api_bp.route('/config', methods=['POST'])
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


@api_bp.route('/config', methods=['PATCH'])
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


@api_bp.route('/config/reset', methods=['POST'])
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


@api_bp.route('/config/options', methods=['GET'])
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

@api_bp.route('/parameters/templates', methods=['GET'])
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


@api_bp.route('/parameters/templates/<template_id>', methods=['GET'])
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


@api_bp.route('/parameters/templates', methods=['POST'])
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


@api_bp.route('/parameters/templates/<template_id>', methods=['PUT'])
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


@api_bp.route('/parameters/templates/<template_id>', methods=['DELETE'])
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


@api_bp.route('/parameters/defaults/<analysis_type>', methods=['GET'])
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


@api_bp.route('/parameters/validate', methods=['POST'])
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

@api_bp.route('/annotations/<analysis_id>', methods=['GET'])
def get_annotations(analysis_id):
    """
    Get all annotations for an analysis.
    GET /api/annotations/{analysis_id}
    
    Query parameters:
    - result_id: Filter by result ID (optional)
    
    Requirements: 12.5
    """
    from services.annotation_service import get_annotation_service
    
    result_id = request.args.get('result_id')
    
    service = get_annotation_service()
    annotations = service.get_annotations(analysis_id, result_id)
    
    return jsonify({
        'analysis_id': analysis_id,
        'result_id': result_id,
        'annotations': [a.to_dict() for a in annotations],
        'total': len(annotations)
    })


@api_bp.route('/annotations/<analysis_id>', methods=['POST'])
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
    from services.annotation_service import get_annotation_service
    
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


@api_bp.route('/annotations/item/<annotation_id>', methods=['GET'])
def get_annotation(annotation_id):
    """
    Get a single annotation by ID.
    GET /api/annotations/item/{annotation_id}
    
    Requirements: 12.5
    """
    from services.annotation_service import get_annotation_service
    
    service = get_annotation_service()
    annotation = service.get_annotation(annotation_id)
    
    if not annotation:
        raise ValidationError(
            message=f"Annotation not found: {annotation_id}",
            details={'annotation_id': annotation_id}
        )
    
    return jsonify(annotation.to_dict())


@api_bp.route('/annotations/item/<annotation_id>', methods=['PUT'])
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
    from services.annotation_service import get_annotation_service
    
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


@api_bp.route('/annotations/item/<annotation_id>', methods=['DELETE'])
def delete_annotation(annotation_id):
    """
    Delete an annotation.
    DELETE /api/annotations/item/{annotation_id}
    
    Requirements: 12.5
    """
    from services.annotation_service import get_annotation_service
    
    service = get_annotation_service()
    success = service.delete_annotation(annotation_id)
    
    return jsonify({
        'success': success,
        'message': 'Annotation deleted successfully'
    })


@api_bp.route('/annotations/<analysis_id>/clear', methods=['DELETE'])
def clear_annotations(analysis_id):
    """
    Delete all annotations for an analysis.
    DELETE /api/annotations/{analysis_id}/clear
    
    Query parameters:
    - result_id: Only clear annotations for specific result (optional)
    
    Requirements: 12.5
    """
    from services.annotation_service import get_annotation_service
    
    result_id = request.args.get('result_id')
    
    service = get_annotation_service()
    count = service.delete_all_annotations(analysis_id, result_id)
    
    return jsonify({
        'success': True,
        'deleted_count': count,
        'message': f'{count} annotation(s) deleted successfully'
    })


@api_bp.route('/annotations/types', methods=['GET'])
def get_annotation_types():
    """
    Get supported annotation types and their default styles.
    GET /api/annotations/types
    
    Requirements: 12.5
    """
    from services.annotation_service import get_annotation_service
    
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

@api_bp.route('/groups', methods=['POST'])
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
    from models.database import SampleGroup, File
    
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
        file_record = File.query.get(file_id)
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


@api_bp.route('/groups', methods=['GET'])
def list_sample_groups():
    """
    Get all sample groups.
    GET /api/groups
    
    Query parameters:
    - file_id: Filter by associated file (optional)
    
    Requirements: 16.1
    """
    from models.database import SampleGroup
    
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


@api_bp.route('/groups/<group_id>', methods=['GET'])
def get_sample_group(group_id):
    """
    Get a sample group by ID.
    GET /api/groups/{group_id}
    
    Requirements: 16.1
    """
    from models.database import SampleGroup
    
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


@api_bp.route('/groups/<group_id>', methods=['PUT'])
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
    from models.database import SampleGroup
    
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


@api_bp.route('/groups/<group_id>', methods=['DELETE'])
def delete_sample_group(group_id):
    """
    Delete a sample group.
    DELETE /api/groups/{group_id}
    
    Requirements: 16.1
    """
    from models.database import SampleGroup
    
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



@api_bp.route('/groups/averages', methods=['POST'])
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
    from models.database import SampleGroup, File
    from services.grouping_service import get_grouping_service
    from services.file_parser import FileParserService
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
    file_record = File.query.get(file_id)
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


# =============================================================================
# Baseline Selection API - Requirements: 17.1, 17.2, 17.3, 17.4
# =============================================================================

@api_bp.route('/baseline/calculate', methods=['POST'])
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
    from models.database import SampleGroup, File
    from services.grouping_service import get_grouping_service
    from services.file_parser import FileParserService
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
    file_record = File.query.get(file_id)
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


@api_bp.route('/baseline/value', methods=['POST'])
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
    from models.database import SampleGroup, File
    from services.grouping_service import get_grouping_service
    from services.file_parser import FileParserService
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
    file_record = File.query.get(file_id)
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

@api_bp.route('/analysis/fields/<file_id>', methods=['GET'])
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
    from services.analysis.modules.field_analyzer import FieldAnalyzerModule
    from pathlib import Path
    
    # Get file record
    file_record = File.query.get(file_id)
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


@api_bp.route('/analysis/field-data', methods=['POST'])
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
    from services.analysis.modules.field_analyzer import FieldAnalyzerModule, ChartConfig
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
    file_record = File.query.get(file_id)
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


# =============================================================================
# PDF Extraction API - Requirements: 9.1-9.6
# =============================================================================

@api_bp.route('/pdf/extract-tables', methods=['POST'])
def extract_pdf_tables():
    """
    Extract B cell isotype tables from PDF files.
    POST /api/pdf/extract-tables
    
    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
    
    Request body:
    {
        "file_ids": ["file_id1", "file_id2", ...]
    }
    
    Returns:
    {
        "extracted_data": {filename: {expression: [...], unique_cdr3: [...]}},
        "failed_files": [filenames],
        "error_messages": {filename: error_message},
        "table_data": {headers: [...], rows: [...], tab_separated: "..."}
    }
    """
    from services.analysis.modules.pdf_extractor import (
        PDFExtractor,
        PDFExtractorError,
        PDFFileNotFoundError as PDFNotFound,
        PDFParseError
    )
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    file_ids = data.get('file_ids', [])
    
    if not file_ids:
        raise ValidationError(
            message="At least one file_id is required",
            details={'field': 'file_ids'}
        )
    
    # Get file paths from database
    pdf_paths = []
    file_id_to_name = {}
    
    for file_id in file_ids:
        file_record = File.query.get(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # Validate it's a PDF file
        if not PDFExtractor.is_pdf_file(file_record.original_name):
            raise ValidationError(
                message=f"File is not a PDF: {file_record.original_name}",
                details={'file_id': file_id, 'filename': file_record.original_name}
            )
        
        pdf_paths.append(file_record.storage_path)
        file_id_to_name[file_record.storage_path] = file_record.original_name
    
    # Extract tables from PDFs
    extractor = PDFExtractor()
    
    try:
        result = extractor.batch_extract_tables(pdf_paths)
    except PDFExtractorError as e:
        raise ValidationError(
            message=f"PDF extraction failed: {str(e)}",
            details={'error': str(e)}
        )
    
    # Map storage paths back to original filenames
    extracted_data = {}
    for storage_path, data in result.get('extracted_data', {}).items():
        original_name = file_id_to_name.get(
            str(Path(storage_path).parent / storage_path),
            Path(storage_path).name
        )
        # Use the storage path's filename which matches what batch_extract_tables returns
        for key in result.get('extracted_data', {}).keys():
            if Path(key).name == Path(storage_path).name:
                extracted_data[original_name] = result['extracted_data'][key]
                break
    
    # Re-map the extracted data with original filenames
    final_extracted = {}
    error_messages = {}
    failed_files = []
    
    for storage_path in pdf_paths:
        storage_name = Path(storage_path).name
        original_name = file_id_to_name.get(storage_path, storage_name)
        
        if storage_name in result.get('extracted_data', {}):
            final_extracted[original_name] = result['extracted_data'][storage_name]
        elif storage_name in result.get('failed_files', []):
            failed_files.append(original_name)
            if storage_name in result.get('error_messages', {}):
                error_messages[original_name] = result['error_messages'][storage_name]
    
    # Generate table data if we have extracted data
    table_data = {}
    if final_extracted:
        table_data = extractor.get_data_table(final_extracted)
    
    return jsonify({
        'extracted_data': final_extracted,
        'failed_files': failed_files,
        'error_messages': error_messages,
        'table_data': table_data,
        'success_count': len(final_extracted),
        'fail_count': len(failed_files)
    })


@api_bp.route('/pdf/generate-chart', methods=['POST'])
def generate_bcell_isotype_chart():
    """
    Generate B cell isotype distribution chart from extracted PDF data.
    POST /api/pdf/generate-chart
    
    Request body:
    {
        "extracted_data": {
            "sample_name": {
                "expression": [values...],
                "unique_cdr3": [values...]
            },
            ...
        }
    }
    """
    import io
    import base64
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    
    data = request.get_json()
    if not data or 'extracted_data' not in data:
        raise ValidationError(
            message="Missing extracted_data in request body",
            details={}
        )
    
    extracted_data = data['extracted_data']
    if not extracted_data:
        raise ValidationError(
            message="No data available for chart generation",
            details={}
        )
    
    try:
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False
        
        isotypes = ["IgM", "IgD", "IgA1/2", "IgG1/2", "IgG3/4", "IgE"]
        samples = list(extracted_data.keys())
        
        charts = []
        
        # 为每个样本生成图表
        for sample_name in samples:
            sample_data = extracted_data.get(sample_name, {})
            if not sample_data:
                continue
            
            fig = _create_bcell_chart_for_sample(sample_name, sample_data, isotypes)
            if fig:
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
                buf.seek(0)
                charts.append({
                    'title': f'B Cell Isotype Distribution ({sample_name})',
                    'base64': base64.b64encode(buf.read()).decode('utf-8')
                })
                plt.close(fig)
        
        return jsonify({
            'charts': charts,
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        raise ValidationError(
            message=f"Chart generation failed: {str(e)}",
            details={'error': str(e)}
        )


def _create_bcell_chart_for_sample(sample_name, sample_data, isotypes):
    """为单个样本创建B细胞同型分布图表 - 参考extract_bcell_isotype_final.py"""
    import matplotlib.pyplot as plt
    
    # 创建1x2布局的图表
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    fig.suptitle(
        f"B Cell Isotype Distribution ({sample_name})",
        fontsize=18,
        fontweight="bold",
        y=0.95,
    )
    
    expression_values = sample_data.get("expression", [])
    cdr3_values = sample_data.get("unique_cdr3", [])
    
    # 确保数据长度匹配
    while len(expression_values) < len(isotypes):
        expression_values.append(0)
    while len(cdr3_values) < len(isotypes):
        cdr3_values.append(0)
    
    # 按百分比排序 - Expression
    expr_sorted = sorted(
        zip(isotypes, expression_values), key=lambda x: x[1], reverse=True
    )
    expr_isotypes, expr_values = zip(*expr_sorted) if expr_sorted else ([], [])
    
    # 按百分比排序 - Unique CDR3
    cdr3_sorted = sorted(
        zip(isotypes, cdr3_values), key=lambda x: x[1], reverse=True
    )
    cdr3_isotypes, cdr3_vals = zip(*cdr3_sorted) if cdr3_sorted else ([], [])
    
    # Expression水平条形图
    colors1 = ["#2E86AB", "#457B9D", "#5DADE2", "#85C1E9", "#AED6F1", "#D6EAF8"]
    bars1 = ax1.barh(
        range(len(expr_isotypes)),
        expr_values,
        color=colors1[:len(expr_isotypes)],
        alpha=0.8,
    )
    
    ax1.set_xlabel("Percentage (%)", fontsize=14, fontweight="bold")
    ax1.set_title("Expression %", fontsize=16, fontweight="bold", pad=20)
    ax1.set_yticks(range(len(expr_isotypes)))
    ax1.set_yticklabels(expr_isotypes, fontsize=12)
    ax1.grid(axis="x", alpha=0.3, linestyle="--")
    ax1.set_facecolor("#f8f9fa")
    
    # 添加数值标签
    max_expr = max(expr_values) if expr_values else 1
    for bar, value in zip(bars1, expr_values):
        ax1.text(
            value + max_expr * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.2f}%",
            ha="left",
            va="center",
            fontsize=11,
            fontweight="bold",
        )
    ax1.set_xlim(0, max_expr * 1.15)
    
    # Unique CDR3水平条形图
    colors2 = ["#A23B72", "#C06C84", "#F67280", "#F8B195", "#F6B352", "#FFA07A"]
    bars2 = ax2.barh(
        range(len(cdr3_isotypes)),
        cdr3_vals,
        color=colors2[:len(cdr3_isotypes)],
        alpha=0.8,
    )
    
    ax2.set_xlabel("Percentage (%)", fontsize=14, fontweight="bold")
    ax2.set_title("Unique CDR3 %", fontsize=16, fontweight="bold", pad=20)
    ax2.set_yticks(range(len(cdr3_isotypes)))
    ax2.set_yticklabels(cdr3_isotypes, fontsize=12)
    ax2.grid(axis="x", alpha=0.3, linestyle="--")
    ax2.set_facecolor("#f8f9fa")
    
    # 添加数值标签
    max_cdr3 = max(cdr3_vals) if cdr3_vals else 1
    for bar, value in zip(bars2, cdr3_vals):
        ax2.text(
            value + max_cdr3 * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.2f}%",
            ha="left",
            va="center",
            fontsize=11,
            fontweight="bold",
        )
    ax2.set_xlim(0, max_cdr3 * 1.15)
    
    plt.tight_layout()
    plt.subplots_adjust(top=0.88)
    
    return fig


@api_bp.route('/pdf/download-charts', methods=['POST'])
def download_charts_as_zip():
    """
    Download all charts as a ZIP file.
    POST /api/pdf/download-charts
    """
    import io
    import base64
    import zipfile
    from flask import send_file
    
    data = request.get_json()
    if not data or 'charts' not in data:
        raise ValidationError(
            message="Missing charts in request body",
            details={}
        )
    
    charts = data['charts']
    if not charts:
        raise ValidationError(
            message="No charts to download",
            details={}
        )
    
    try:
        # 创建内存中的ZIP文件
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for chart in charts:
                # 生成文件名
                title = chart.get('title', 'chart')
                # 清理文件名中的非法字符
                import re
                filename = re.sub(r'[^\w\u4e00-\u9fa5\-_]', '_', title) + '.png'
                
                # 解码base64数据
                image_data = base64.b64decode(chart['base64'])
                
                # 添加到ZIP
                zip_file.writestr(filename, image_data)
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='bcell_isotype_charts.zip'
        )
        
    except Exception as e:
        logger.error(f"Error creating ZIP file: {e}")
        raise ValidationError(
            message=f"Failed to create ZIP file: {str(e)}",
            details={'error': str(e)}
        )


@api_bp.route('/pdf/download-images', methods=['POST'])
def download_images_as_zip():
    """
    Download all extracted images as a ZIP file.
    POST /api/pdf/download-images
    """
    import io
    import base64
    import zipfile
    from flask import send_file
    
    data = request.get_json()
    if not data or 'images' not in data:
        raise ValidationError(
            message="Missing images in request body",
            details={}
        )
    
    images = data['images']
    if not images:
        raise ValidationError(
            message="No images to download",
            details={}
        )
    
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for pdf_name, img_list in images.items():
                # 清理PDF名称作为文件夹名
                import re
                folder_name = re.sub(r'[^\w\u4e00-\u9fa5\-_]', '_', pdf_name.replace('.pdf', ''))
                
                for img_data in img_list:
                    # 生成文件名
                    filename = f"{folder_name}/image_{img_data['index']}.png"
                    
                    # 解码base64数据
                    image_bytes = base64.b64decode(img_data['image'])
                    
                    # 添加到ZIP
                    zip_file.writestr(filename, image_bytes)
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='extracted_images.zip'
        )
        
    except Exception as e:
        logger.error(f"Error creating images ZIP file: {e}")
        raise ValidationError(
            message=f"Failed to create ZIP file: {str(e)}",
            details={'error': str(e)}
        )


# =============================================================================
# PDF Image Extraction API - Requirements: 12.1-12.6
# =============================================================================

@api_bp.route('/pdf/images/<file_id>', methods=['GET'])
def list_pdf_images(file_id):
    """
    List all images in a PDF file with thumbnails.
    GET /api/pdf/images/{file_id}
    
    Requirements: 12.1, 12.2
    
    Returns:
    {
        "images": [
            {
                "index": 0,
                "width": 800,
                "height": 600,
                "page_number": 1,
                "thumbnail": "base64_encoded_thumbnail"
            },
            ...
        ],
        "total_count": 10
    }
    """
    from services.analysis.modules.pdf_extractor import (
        PDFExtractor,
        PDFExtractorError,
        PDFImageExtractionError
    )
    
    # Get file record
    file_record = File.query.get(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Validate it's a PDF file
    if not PDFExtractor.is_pdf_file(file_record.original_name):
        raise ValidationError(
            message=f"File is not a PDF: {file_record.original_name}",
            details={'file_id': file_id, 'filename': file_record.original_name}
        )
    
    # List images
    extractor = PDFExtractor(file_record.storage_path)
    
    try:
        images = extractor.list_images()
    except PDFExtractorError as e:
        raise ValidationError(
            message=f"Failed to list PDF images: {str(e)}",
            details={'error': str(e)}
        )
    
    return jsonify({
        'images': images,
        'total_count': len(images),
        'filename': file_record.original_name
    })


@api_bp.route('/pdf/extract-images', methods=['POST'])
def extract_pdf_images():
    """
    Extract images from PDF files by index.
    POST /api/pdf/extract-images
    
    Requirements: 12.3, 12.4, 12.5, 12.6
    
    Request body:
    {
        "file_ids": ["file_id1", "file_id2", ...],
        "indices": [16, -1]  // Optional, defaults to [16, -1]
    }
    
    Returns:
    {
        "extracted_images": {
            "filename.pdf": [
                {"index": 16, "image": "base64_encoded_image"},
                {"index": -1, "image": "base64_encoded_image"}
            ]
        },
        "failed_files": ["filename2.pdf"],
        "error_messages": {"filename2.pdf": "error message"}
    }
    """
    from services.analysis.modules.pdf_extractor import (
        PDFExtractor,
        PDFExtractorError,
        PDFImageExtractionError
    )
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={'field': 'body'}
        )
    
    file_ids = data.get('file_ids', [])
    indices = data.get('indices', PDFExtractor.DEFAULT_IMAGE_INDICES)
    
    if not file_ids:
        raise ValidationError(
            message="At least one file_id is required",
            details={'field': 'file_ids'}
        )
    
    if not isinstance(indices, list):
        raise ValidationError(
            message="Indices must be a list of integers",
            details={'field': 'indices'}
        )
    
    # Get file paths from database
    pdf_paths = []
    file_id_to_name = {}
    
    for file_id in file_ids:
        file_record = File.query.get(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # Validate it's a PDF file
        if not PDFExtractor.is_pdf_file(file_record.original_name):
            raise ValidationError(
                message=f"File is not a PDF: {file_record.original_name}",
                details={'file_id': file_id, 'filename': file_record.original_name}
            )
        
        pdf_paths.append(file_record.storage_path)
        file_id_to_name[file_record.storage_path] = file_record.original_name
    
    # Extract images from PDFs
    extractor = PDFExtractor()
    
    try:
        result = extractor.batch_extract_images(pdf_paths, indices)
    except PDFExtractorError as e:
        raise ValidationError(
            message=f"PDF image extraction failed: {str(e)}",
            details={'error': str(e)}
        )
    
    # Map storage paths back to original filenames
    final_extracted = {}
    error_messages = {}
    failed_files = []
    
    for storage_path in pdf_paths:
        storage_name = Path(storage_path).name
        original_name = file_id_to_name.get(storage_path, storage_name)
        
        if storage_name in result.get('extracted_images', {}):
            # Convert tuple format to dict format for JSON response
            images_data = result['extracted_images'][storage_name]
            final_extracted[original_name] = [
                {'index': idx, 'image': img_base64}
                for idx, img_base64 in images_data
            ]
        elif storage_name in result.get('failed_files', []):
            failed_files.append(original_name)
            if storage_name in result.get('error_messages', {}):
                error_messages[original_name] = result['error_messages'][storage_name]
    
    return jsonify({
        'extracted_images': final_extracted,
        'failed_files': failed_files,
        'error_messages': error_messages,
        'indices_used': indices,
        'success_count': len(final_extracted),
        'fail_count': len(failed_files)
    })


# =============================================================================
# PDF Image Extraction API - Requirements: 8.1, 8.2, 8.3, 8.6, 8.7, 8.8, 8.9, 8.10
# =============================================================================

@api_bp.route('/pdf/upload', methods=['POST'])
def upload_pdf():
    """
    Upload a PDF file for image extraction.
    POST /api/pdf/upload
    
    Requirements: 8.1, 8.2
    
    Returns:
    {
        "file_id": "uuid",
        "filename": "report.pdf",
        "page_count": 10,
        "file_size": 1024000
    }
    """
    from services.pdf_extractor import PDFExtractorService
    
    # Check if file is present
    if 'file' not in request.files:
        raise ValidationError(
            message="No file provided in request",
            details={'field': 'file'}
        )
    
    file = request.files['file']
    
    if file.filename == '':
        raise ValidationError(
            message="No file selected",
            details={'field': 'file'}
        )
    
    filename = file.filename
    
    # Validate PDF extension
    if not filename.lower().endswith('.pdf'):
        raise FileFormatInvalidError(
            message=f"File must be a PDF",
            details={'provided_extension': Path(filename).suffix}
        )
    
    # Read file content
    file_content = file.read()
    
    if len(file_content) == 0:
        raise ValidationError(
            message="Uploaded file is empty",
            details={'field': 'file'}
        )
    
    # Check file size
    pdf_max_size = current_app.config.get('PDF_MAX_SIZE', 50 * 1024 * 1024)
    if len(file_content) > pdf_max_size:
        raise ValidationError(
            message=f"PDF file too large. Maximum size: {pdf_max_size / (1024*1024)}MB",
            details={'file_size': len(file_content), 'max_size': pdf_max_size}
        )
    
    # Generate unique file ID and storage path
    file_id = str(uuid.uuid4())
    storage_filename = f"{file_id}.pdf"
    storage_path = Path(current_app.config['UPLOAD_FOLDER']) / storage_filename
    
    # Save file to disk
    try:
        with open(storage_path, 'wb') as f:
            f.write(file_content)
    except Exception as e:
        raise StorageError(
            message=f"Failed to save file: {str(e)}",
            details={'filename': filename}
        )
    
    # Get PDF info
    try:
        pdf_info = PDFExtractorService.get_pdf_info(str(storage_path))
    except Exception as e:
        # Clean up file if info extraction fails
        if storage_path.exists():
            storage_path.unlink()
        raise FileParseError(
            message=f"Failed to read PDF: {str(e)}",
            details={'filename': filename}
        )
    
    # Get project name from form data (default to 'default')
    project = request.form.get('project', 'default') or 'default'
    
    # Create file record in database
    file_record = File(
        id=file_id,
        name=storage_filename,
        original_name=filename,
        size=len(file_content),
        storage_path=str(storage_path),
        mime_type='application/pdf',
        columns=[],  # PDFs don't have columns
        row_count=pdf_info['page_count'],
        project=project
    )
    
    db.session.add(file_record)
    db.session.commit()
    
    return jsonify({
        'file_id': file_id,
        'filename': filename,
        'page_count': pdf_info['page_count'],
        'file_size': len(file_content),
        'metadata': pdf_info.get('metadata', {}),
        'project': project
    }), 201


@api_bp.route('/pdf/extract', methods=['POST'])
def extract_pdf_to_folders():
    """
    Extract images from a PDF file.
    POST /api/pdf/extract
    
    Requirements: 8.6, 8.7, 8.8, 8.9, 8.10
    
    Request body:
    {
        "file_id": "uuid",
        "output_path": "/path/to/output",
        "sample_mapping": {
            "0": "Sample1",
            "1": "Sample2"
        }
    }
    
    Returns:
    {
        "success": true,
        "samples": {
            "Sample1": 5,
            "Sample2": 3
        },
        "total_images": 8,
        "output_path": "/path/to/output",
        "errors": []
    }
    """
    from services.pdf_extractor import PDFExtractorService
    
    data = request.get_json()
    
    if not data:
        raise ValidationError(
            message="Request body is required",
            details={}
        )
    
    file_id = data.get('file_id')
    output_path = data.get('output_path')
    sample_mapping = data.get('sample_mapping', {})
    
    if not file_id:
        raise ValidationError(
            message="file_id is required",
            details={'field': 'file_id'}
        )
    
    if not output_path:
        raise ValidationError(
            message="output_path is required",
            details={'field': 'output_path'}
        )
    
    # Get file record
    file_record = File.query.get(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Validate it's a PDF
    if not file_record.original_name.lower().endswith('.pdf'):
        raise ValidationError(
            message="File is not a PDF",
            details={'file_id': file_id, 'filename': file_record.original_name}
        )
    
    # Convert sample_mapping keys to integers
    sample_mapping_int = {}
    if sample_mapping:
        try:
            sample_mapping_int = {int(k): v for k, v in sample_mapping.items()}
        except (ValueError, TypeError):
            raise ValidationError(
                message="sample_mapping keys must be page numbers (integers)",
                details={'sample_mapping': sample_mapping}
            )
    
    # Extract images
    try:
        result = PDFExtractorService.extract_images(
            pdf_path=file_record.storage_path,
            output_path=output_path,
            sample_mapping=sample_mapping_int if sample_mapping_int else None
        )
        
        return jsonify({
            'success': result.success,
            'samples': result.samples,
            'total_images': result.total_images,
            'output_path': result.output_path,
            'errors': result.errors
        })
        
    except FileParseError as e:
        raise
    except Exception as e:
        raise FileParseError(
            message=f"Failed to extract images: {str(e)}",
            details={
                'file_id': file_id,
                'error_type': type(e).__name__
            }
        )


@api_bp.route('/pdf/samples/<file_id>', methods=['GET'])
def detect_pdf_samples(file_id):
    """
    Detect sample names from a PDF file.
    GET /api/pdf/samples/{file_id}
    
    Requirements: 8.8
    
    Returns:
    {
        "samples": ["Sample1", "Sample2", "Sample3"]
    }
    """
    from services.pdf_extractor import PDFExtractorService
    
    # Get file record
    file_record = File.query.get(file_id)
    if not file_record:
        raise AppFileNotFoundError(
            message=f"File not found: {file_id}",
            details={'file_id': file_id}
        )
    
    # Validate it's a PDF
    if not file_record.original_name.lower().endswith('.pdf'):
        raise ValidationError(
            message="File is not a PDF",
            details={'file_id': file_id, 'filename': file_record.original_name}
        )
    
    # Detect samples
    try:
        samples = PDFExtractorService.detect_samples(file_record.storage_path)
        
        return jsonify({
            'samples': samples
        })
        
    except FileParseError as e:
        raise
    except Exception as e:
        raise FileParseError(
            message=f"Failed to detect samples: {str(e)}",
            details={
                'file_id': file_id,
                'error_type': type(e).__name__
            }
        )


# =============================================================================
# Directory Browser API - Requirements: 12.2, 12.3, 12.4, 12.5
# =============================================================================

@api_bp.route('/directories', methods=['GET'])
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
    from services.directory_service import DirectoryService
    
    parent_path = request.args.get('parent_path')
    
    # Get configuration
    allowed_base_paths = current_app.config.get('ALLOWED_BASE_PATHS', [])
    hidden_directories = current_app.config.get('HIDDEN_DIRECTORIES', [])
    
    try:
        result = DirectoryService.list_directories(
            parent_path=parent_path,
            allowed_base_paths=allowed_base_paths,
            hidden_directories=hidden_directories
        )
        
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


@api_bp.route('/directories/validate', methods=['GET'])
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
    from services.directory_service import DirectoryService
    
    path = request.args.get('path')
    
    if not path:
        raise ValidationError(
            message="path parameter is required",
            details={'parameter': 'path'}
        )
    
    # Get configuration
    allowed_base_paths = current_app.config.get('ALLOWED_BASE_PATHS', [])
    
    try:
        result = DirectoryService.validate_path(
            path=path,
            allowed_base_paths=allowed_base_paths
        )
        
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

@api_bp.route('/color-schemes', methods=['GET'])
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


@api_bp.route('/color-schemes/<scheme_name>', methods=['GET'])
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

@api_bp.route('/sequencing-depth/ppt', methods=['POST'])
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
    from services.sequencing_depth_ppt import SequencingDepthPPTService
    
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


@api_bp.route('/sequencing-depth/visualization', methods=['POST'])
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
    from services.sequencing_depth_viz import SequencingDepthVisualizationService
    
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


@api_bp.route('/sequencing-depth/bar-chart', methods=['POST'])
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
    from services.sequencing_reads_chart import SequencingReadsChartService
    
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


@api_bp.route('/sequencing-depth/results/<result_id>', methods=['GET'])
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

@api_bp.route('/analysis/bcell-isotype', methods=['POST'])
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
        file_record = File.query.get(file_id)
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


@api_bp.route('/analysis/shm', methods=['POST'])
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
        file_record = File.query.get(file_id)
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


@api_bp.route('/analysis/ig-metrics', methods=['POST'])
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
        file_record = File.query.get(file_id)
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


@api_bp.route('/analysis/custom-field', methods=['POST'])
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
        file_record = File.query.get(file_id)
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
