"""
API routes for the Immune Repertoire Analysis Web Application.
Provides RESTful endpoints for file management, analysis, and configuration.
"""
import io
import os
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, jsonify, current_app, send_file
from services.analysis_service import get_analysis_service
from services.ppt_service import PPTService
from services.file_parser import FileParserService
from models.database import db, File, Analysis, Annotation, CustomParameter
from exceptions import (
    ValidationError,
    FileFormatInvalidError, 
    FileParseError, 
    FileNotFoundError as AppFileNotFoundError,
    StorageError,
    AnalysisNotFoundError
)

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
        'uploaded_at': file_record.uploaded_at.isoformat()
    }), 201
