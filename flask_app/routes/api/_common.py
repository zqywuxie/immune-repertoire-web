"""Shared utilities for the modular API package.

This module holds the parent Blueprint, shared imports, and helper
functions used by two or more sub-modules (files, mappings, analysis_bridge,
etc.).  Each sub-module imports what it needs from here.
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
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.user_scope import assign_owner, assert_owned, current_user_id, scope_query
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


def _get_owned_file(file_id: str) -> File:
    file_record = File.query.get(file_id)
    if not file_record:
        raise AppFileNotFoundError(message=f"File not found: {file_id}", details={'file_id': file_id})
    assert_owned(file_record, "File")
    return file_record


def _get_owned_analysis(analysis_id: str) -> Analysis:
    analysis = Analysis.query.get(analysis_id)
    if not analysis:
        raise AnalysisNotFoundError(message=f"Analysis not found: {analysis_id}", details={'analysis_id': analysis_id})
    assert_owned(analysis, "Analysis")
    return analysis


