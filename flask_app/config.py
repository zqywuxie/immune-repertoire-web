"""
Configuration management module for the Immune Repertoire Analysis Web Application.
Supports environment variable configuration and single-command startup.
Requirements: 13.1, 13.2, 13.3
"""
import os
from pathlib import Path


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
    
    # Database settings - SQLite for single-command startup
    BASE_DIR = Path(__file__).parent
    DATABASE_PATH = BASE_DIR / 'data' / 'immune_repertoire.db'
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 
        f'sqlite:///{DATABASE_PATH}'
    )
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
    # Empty list means no restrictions - can browse all directories
    ALLOWED_BASE_PATHS = []
    HIDDEN_DIRECTORIES = ['.git', '__pycache__', 'node_modules', '.hypothesis', '$RECYCLE.BIN', 'System Volume Information']
    
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
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


# Configuration dictionary for easy access
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
