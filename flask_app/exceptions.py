"""
Custom exception classes for the Immune Repertoire Analysis Web Application.
Provides structured error handling with error codes and messages.
Requirements: 1.3, 13.4
"""
from datetime import datetime
from typing import Optional, Dict, Any


class AppException(Exception):
    """Base exception class for application errors."""
    
    error_code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message: str = "An unexpected error occurred"
    
    def __init__(
        self, 
        message: Optional[str] = None, 
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message or self.__class__.message
        self.details = details or {}
        self.timestamp = datetime.utcnow()
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response."""
        response = {
            'error_code': self.error_code,
            'message': self.message,
            'timestamp': self.timestamp.isoformat()
        }
        if self.details:
            response['details'] = self.details
        return response


# File-related exceptions
class FileFormatInvalidError(AppException):
    """Raised when file format is not supported. Requirements: 1.1"""
    error_code = "FILE_FORMAT_INVALID"
    http_status = 400
    message = "Unsupported file format"


class FileParseError(AppException):
    """Raised when file content cannot be parsed. Requirements: 1.3"""
    error_code = "FILE_PARSE_ERROR"
    http_status = 400
    message = "File content could not be parsed"


class FileNotFoundError(AppException):
    """Raised when requested file does not exist."""
    error_code = "FILE_NOT_FOUND"
    http_status = 404
    message = "Requested file not found"


class FileTooLargeError(AppException):
    """Raised when file exceeds maximum size limit."""
    error_code = "FILE_TOO_LARGE"
    http_status = 413
    message = "File exceeds maximum size limit"


# Mapping-related exceptions
class MappingIncompleteError(AppException):
    """Raised when required fields are not mapped. Requirements: 11.5"""
    error_code = "MAPPING_INCOMPLETE"
    http_status = 400
    message = "Required fields are not mapped"


class MappingTemplateNotFoundError(AppException):
    """Raised when mapping template does not exist."""
    error_code = "MAPPING_TEMPLATE_NOT_FOUND"
    http_status = 404
    message = "Mapping template not found"


# Analysis-related exceptions
class AnalysisNotFoundError(AppException):
    """Raised when requested analysis does not exist."""
    error_code = "ANALYSIS_NOT_FOUND"
    http_status = 404
    message = "Requested analysis not found"


class AnalysisFailedError(AppException):
    """Raised when analysis execution fails. Requirements: 8.3"""
    error_code = "ANALYSIS_FAILED"
    http_status = 500
    message = "Analysis execution failed"


class AnalysisInProgressError(AppException):
    """Raised when trying to modify an analysis that is in progress."""
    error_code = "ANALYSIS_IN_PROGRESS"
    http_status = 409
    message = "Analysis is currently in progress"


class AnalysisCancelledError(AppException):
    """Raised when analysis was cancelled."""
    error_code = "ANALYSIS_CANCELLED"
    http_status = 400
    message = "Analysis was cancelled"


class AnalysisRetryLimitError(AppException):
    """Raised when maximum retry attempts exceeded. Requirements: 8.3"""
    error_code = "ANALYSIS_RETRY_LIMIT"
    http_status = 400
    message = "Maximum retry attempts exceeded"


class AnalysisTypeNotSupportedError(AppException):
    """Raised when analysis type is not supported."""
    error_code = "ANALYSIS_TYPE_NOT_SUPPORTED"
    http_status = 400
    message = "Analysis type is not supported"


# Storage-related exceptions
class StorageError(AppException):
    """Raised when file storage operation fails."""
    error_code = "STORAGE_ERROR"
    http_status = 500
    message = "File storage operation failed"


# Validation exceptions
class ValidationError(AppException):
    """Raised when input validation fails."""
    error_code = "VALIDATION_ERROR"
    http_status = 400
    message = "Input validation failed"


# PPT-related exceptions
class PPTError(AppException):
    """Base exception class for PPT processing errors."""
    error_code = "PPT_ERROR"
    http_status = 500
    message = "PPT processing error"


class PPTFileInvalidError(PPTError):
    """Raised when PPT file is invalid or unsupported."""
    error_code = "PPT_FILE_INVALID"
    http_status = 400
    message = "Invalid PPT file"


class PPTParseError(PPTError):
    """Raised when PPT parsing fails."""
    error_code = "PPT_PARSE_ERROR"
    http_status = 400
    message = "Failed to parse PPT file"


class PPTSlideNotFoundError(PPTError):
    """Raised when requested PPT slide is not found."""
    error_code = "PPT_SLIDE_NOT_FOUND"
    http_status = 404
    message = "PPT slide not found"


class PPTImageReplacementError(PPTError):
    """Raised when PPT image replacement fails."""
    error_code = "PPT_IMAGE_REPLACEMENT_ERROR"
    http_status = 500
    message = "Failed to replace images in PPT"


class PPTSessionNotFoundError(PPTError):
    """Raised when PPT replacement session cannot be found."""
    error_code = "PPT_SESSION_NOT_FOUND"
    http_status = 404
    message = "PPT session not found"


class PPTNoHeatmapsError(PPTError):
    """Raised when no heatmaps/images are found for replacement."""
    error_code = "PPT_NO_HEATMAPS"
    http_status = 400
    message = "No heatmaps found for replacement"
