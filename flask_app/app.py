"""
Main Flask application entry point for the Immune Repertoire Analysis Web Application.
Single-command startup: python app.py
Requirements: 13.1, 13.2, 13.3, 13.4
"""
import json
import os
import sys

# Add current directory to Python path to enable absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from flask import Flask, jsonify
from config import config
from models.database import db


class NumpyJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles numpy types and NaN values."""
    
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            if np.isnan(obj):
                return None
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def create_app(config_name=None):
    """
    Application factory function.
    Creates and configures the Flask application.
    
    Args:
        config_name: Configuration name ('development', 'production', 'testing')
    
    Returns:
        Configured Flask application instance
    """
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
    
    app = Flask(__name__)
    
    # Set custom JSON encoder to handle numpy types and NaN values
    app.json_encoder = NumpyJSONEncoder
    
    # Load configuration
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # Initialize extensions
    db.init_app(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register blueprints (routes)
    register_blueprints(app)
    
    # Initialize database
    with app.app_context():
        db.create_all()
    
    # Initialize analysis service
    from services.analysis_service import init_analysis_service
    init_analysis_service(app)
    
    # Initialize history service
    from services.history_service import init_history_service
    init_history_service(app)
    
    # Initialize config service
    from services.config_service import init_config_service
    init_config_service(app)
    
    # Initialize parameter template service
    from services.parameter_template_service import init_parameter_template_service
    init_parameter_template_service(app)
    
    # Initialize annotation service
    from services.annotation_service import init_annotation_service
    init_annotation_service(app)
    
    # Initialize modular analysis system
    from services.analysis.registry import init_analysis_registry
    init_analysis_registry()
    
    return app


def register_error_handlers(app):
    """Register error handlers for the application. Requirements: 1.3, 13.4"""
    from exceptions import AppException
    
    @app.errorhandler(AppException)
    def handle_app_exception(error):
        """Handle custom application exceptions."""
        return jsonify(error.to_dict()), error.http_status
    
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            'error_code': 'BAD_REQUEST',
            'message': str(error.description) if hasattr(error, 'description') else 'Bad request'
        }), 400
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error_code': 'NOT_FOUND',
            'message': 'Resource not found'
        }), 404
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({
            'error_code': 'FILE_TOO_LARGE',
            'message': 'File exceeds maximum size limit (100MB)'
        }), 413
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({
            'error_code': 'INTERNAL_ERROR',
            'message': 'An unexpected error occurred'
        }), 500


def register_blueprints(app):
    """Register Flask blueprints for routes."""
    from routes.pages import pages_bp
    from routes.api import api_bp
    from routes.api_analysis import analysis_bp
    
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    # Register the new analysis blueprint
    app.register_blueprint(analysis_bp, url_prefix='/api/analysis')


# Application instance for single-command startup
app = create_app()


if __name__ == '__main__':
    # Single-command startup (Requirements: 13.1, 13.2, 13.3)
    try:
        host = app.config.get('HOST', '0.0.0.0')
        port = app.config.get('PORT', 5000)
        debug = app.config.get('DEBUG', False)
        
        print(f"Starting {app.config['APP_NAME']} v{app.config['APP_VERSION']}")
        print(f"Server running at http://{host}:{port}")
        print(f"Debug mode: {debug}")
        
        app.run(host=host, port=port, debug=debug)
    except Exception as e:
        # Requirements: 13.4 - Display clear error messages on startup errors
        print(f"Error starting application: {e}", file=sys.stderr)
        sys.exit(1)
