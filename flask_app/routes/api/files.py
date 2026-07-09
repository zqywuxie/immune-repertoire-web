"""File management routes: upload, list, preview, search, download, etc."""

import numpy as np
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, jsonify, current_app, send_file

from flask_app.exceptions import (
    ValidationError,
    FileFormatInvalidError,
    FileParseError,
    FileNotFoundError as AppFileNotFoundError,
    StorageError,
)
from flask_app.models.database import db, File
from flask_app.services.file_parser import FileParserService
from flask_app.services.user_scope import assign_owner, current_user_id, scope_query

from ._common import _get_owned_file

bp = Blueprint("api_files", __name__)

@bp.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'})


@bp.route('/info')
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

@bp.route('/files/upload', methods=['POST'])
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
    upload_root = Path(current_app.config['UPLOAD_FOLDER'])
    if current_user_id() is not None:
        upload_root = upload_root / str(current_user_id())
    upload_root.mkdir(parents=True, exist_ok=True)
    storage_path = upload_root / storage_filename
    
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
            project=project,
            user_id=current_user_id(),
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


@bp.route('/files/upload-multiple', methods=['POST'])
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
        upload_root = Path(current_app.config['UPLOAD_FOLDER'])
        if current_user_id() is not None:
            upload_root = upload_root / str(current_user_id())
        upload_root.mkdir(parents=True, exist_ok=True)
        storage_path = upload_root / storage_filename
        
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
                uploaded_at=datetime.utcnow(),
                user_id=current_user_id(),
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

@bp.route('/files/projects', methods=['GET'])
def list_projects():
    """
    Get all project names.
    GET /api/files/projects
    """
    # Get distinct project names
    query = db.session.query(File.project).distinct()
    if current_user_id() is not None:
        query = query.filter(File.user_id == current_user_id())
    projects = query.all()
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


@bp.route('/files', methods=['GET'])
def list_files():
    """
    Get all uploaded files.
    GET /api/files
    
    Query parameters:
    - project: Filter by project name (optional)
    
    Requirements: 1.5
    """
    project = request.args.get('project')
    
    query = scope_query(File.query, File)
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


@bp.route('/files/<file_id>', methods=['GET'])
def get_file(file_id):
    """
    Get file details by ID.
    GET /api/files/{file_id}
    
    Requirements: 1.5, 1.6
    """
    file_record = _get_owned_file(file_id)
    
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


@bp.route('/files/<file_id>/column-values', methods=['GET'])
def get_column_values(file_id):
    """
    Get unique values from a specific column in a file.
    GET /api/files/{file_id}/column-values?column=column_name
    
    Returns unique values for sample detection.
    """
    file_record = _get_owned_file(file_id)
    
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


@bp.route('/files/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    """
    Delete a file by ID.
    DELETE /api/files/{file_id}
    
    Requirements: 1.6
    """
    file_record = _get_owned_file(file_id)
    
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


@bp.route('/files/<file_id>/download', methods=['GET'])
def download_file(file_id):
    """
    Download a file by ID.
    GET /api/files/{file_id}/download
    """
    file_record = _get_owned_file(file_id)
    
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


@bp.route('/files/<file_id>/rename', methods=['PUT'])
def rename_file(file_id):
    """
    Rename a file by ID.
    PUT /api/files/{file_id}/rename
    Body: { "name": "new_filename.csv" }
    """
    file_record = _get_owned_file(file_id)
    
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


@bp.route('/files/<file_id>/preview', methods=['GET'])
def preview_file(file_id):
    """
    Get file preview with data content.
    GET /api/files/{file_id}/preview?rows=50&offset=0
    """
    file_record = _get_owned_file(file_id)
    
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


@bp.route('/files/search', methods=['GET'])
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
    
    query = scope_query(File.query, File)
    
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


