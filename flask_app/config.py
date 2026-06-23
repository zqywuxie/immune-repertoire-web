"""
Configuration management module for the Immune Repertoire Analysis Web Application.
Supports environment variable configuration and single-command startup.
Requirements: 13.1, 13.2, 13.3
"""
import json
import os
from pathlib import Path


def _resolve_database_uri(base_dir: Path) -> str:
    """Return MySQL URI if available, otherwise fall back to SQLite."""
    env_url = os.environ.get('DATABASE_URL', '').strip()
    if env_url:
        return env_url
    try:
        from flask_app.database_config import SQLALCHEMY_DATABASE_URI as uri
        return uri
    except Exception:
        return f'sqlite:///{base_dir / "data" / "immune_repertoire.db"}'


class Config:
    """Base configuration class."""
    
    # Application settings
    APP_NAME = "Immune Repertoire Analysis"
    APP_VERSION = "1.0.0"
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Server settings
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))
    DEBUG = False
    
    # Database settings
    BASE_DIR = Path(__file__).parent
    DATABASE_PATH = BASE_DIR / 'data' / 'immune_repertoire.db'
    SQLALCHEMY_DATABASE_URI = _resolve_database_uri(BASE_DIR)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File storage settings
    UPLOAD_FOLDER = BASE_DIR / 'data' / 'uploads'
    RESULTS_FOLDER = BASE_DIR / 'data' / 'results'
    PDF_EXTRACTION_FOLDER = BASE_DIR / 'data' / 'pdf_extractions'
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max upload size
    
    # Allowed file extensions
    ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.csv.gz', '.pdf'}
    
    # PDF Configuration
    PDF_MAX_SIZE = 50 * 1024 * 1024  # 50MB
    ALLOWED_IMAGE_FORMATS = ['png', 'jpg', 'jpeg']
    
    # Directory Browser Configuration
    # Empty list is only unrestricted when REQUIRE_LOGIN is disabled.
    ALLOWED_BASE_PATHS = [
        item.strip()
        for item in os.environ.get('ALLOWED_BASE_PATHS', '').split(os.pathsep)
        if item.strip()
    ]
    HIDDEN_DIRECTORIES = ['.git', '__pycache__', 'node_modules', '.hypothesis', '$RECYCLE.BIN', 'System Volume Information']
    REQUIRE_LOGIN = os.environ.get('REQUIRE_LOGIN', 'true').lower() not in {'0', 'false', 'no', 'off'}
    AUTH_REGISTER_ENABLED = os.environ.get('AUTH_REGISTER_ENABLED', 'true').lower() not in {'0', 'false', 'no', 'off'}
    AUTH_FIRST_USER_ADMIN = os.environ.get('AUTH_FIRST_USER_ADMIN', 'true').lower() not in {'0', 'false', 'no', 'off'}
    USER_DATA_ROOT = Path(os.environ.get('USER_DATA_ROOT', str(BASE_DIR / 'data' / 'users')))
    DEFAULT_USER_ALLOWED_PATHS = [
        item.strip()
        for item in os.environ.get('DEFAULT_USER_ALLOWED_PATHS', '').split(os.pathsep)
        if item.strip()
    ]

    # Visualization defaults
    DEFAULT_COLOR_SCHEME = 'viridis'
    DEFAULT_FIGURE_SIZE = (10, 8)
    DEFAULT_FONT_SIZE = 12
    DEFAULT_DPI = 300
    
    @classmethod
    def init_app(cls, app):
        """Initialize application with this configuration."""
        # Ensure data directories exist
        cls.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        cls.RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)
        cls.PDF_EXTRACTION_FOLDER.mkdir(parents=True, exist_ok=True)
        cls.USER_DATA_ROOT.mkdir(parents=True, exist_ok=True)
        cls.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        # Additional production setup can go here


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    REQUIRE_LOGIN = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


# Configuration dictionary for easy access
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
