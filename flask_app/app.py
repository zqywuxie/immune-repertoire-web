"""
Main Flask application entry point for the Immune Repertoire Analysis Web Application.
Single-command startup: python app.py
Requirements: 13.1, 13.2, 13.3, 13.4
"""
import json
import math
import os
import sys

# Ensure project root is importable so `flask_app.*` imports resolve.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load .env from project root before any config imports read os.environ
from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

import numpy as np
from flask import Flask, jsonify, redirect, request, url_for
from flask_login import LoginManager
from flask_app.config import config
from flask_app.models.database import db


def _sanitize_json_value(value):
    """Recursively replace NaN/Infinity with None so JSON output is spec-compliant."""
    if isinstance(value, dict):
        return {k: _sanitize_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_json_value(v) for v in value]
    if isinstance(value, (np.floating, float)):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.ndarray):
        return _sanitize_json_value(value.tolist())
    return value


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that sanitizes NaN/Inf values before serialization."""

    def default(self, obj):
        if isinstance(obj, (np.floating, float)):
            val = float(obj)
            if math.isnan(val) or math.isinf(val):
                return None
            return val
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return _sanitize_json_value(obj.tolist())
        return super().default(obj)

    def encode(self, obj):
        return super().encode(_sanitize_json_value(obj))

    def iterencode(self, obj, _one_shot=False):
        return super().iterencode(_sanitize_json_value(obj), _one_shot=_one_shot)


OPTIONAL_DEPENDENCY_HINTS = {
    'pptx': 'Missing dependency "python-pptx". Install it with: pip install python-pptx or pip install -r requirements.txt',
}



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
    app.json_encoder = SafeJSONEncoder
    
    # Load configuration
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # Initialize extensions
    db.init_app(app)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith('/api/'):
            return jsonify({'error_code': 'AUTH_REQUIRED', 'message': 'Authentication required'}), 401
        return redirect(url_for('auth.login', next=request.full_path if request.query_string else request.path))
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login."""
        from flask_app.models.database import User
        try:
            return User.query.get(int(user_id))
        except (TypeError, ValueError):
            return None

    @app.before_request
    def require_login_for_application():
        if request.method == 'OPTIONS' and request.path.startswith('/api/'):
            return '', 204
        if not app.config.get('REQUIRE_LOGIN', True):
            return None
        endpoint = request.endpoint or ''
        if endpoint.startswith('static') or endpoint.startswith('auth.'):
            return None
        if endpoint in {'api.health_check', 'api.app_info'}:
            return None
        from flask_login import current_user
        if current_user.is_authenticated:
            return None
        return unauthorized()

    @app.context_processor
    def inject_auth_context():
        from flask_login import current_user
        return {'current_user': current_user}

    @app.after_request
    def add_api_cors_headers(response):
        origin = str(request.headers.get('Origin') or '').rstrip('/')
        allowed_origins = set(app.config.get('FRONTEND_ORIGINS') or [])
        if origin and origin in allowed_origins and request.path.startswith('/api/'):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Vary'] = 'Origin'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = request.headers.get(
                'Access-Control-Request-Headers',
                'Content-Type, Authorization',
            )
            if app.config.get('API_CORS_ALLOW_CREDENTIALS', True):
                response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register blueprints (routes)
    register_blueprints(app)
    
    # Initialize database
    with app.app_context():
        db.create_all()
        from flask_app.services.schema_compatibility import ensure_schema_compatibility
        ensure_schema_compatibility()

    # Initialize persistent background job service
    from flask_app.services.background_job_service import init_background_job_service
    init_background_job_service(app)

    # Initialize analysis service
    from flask_app.services.analysis_service import init_analysis_service
    init_analysis_service(app)
    
    # Initialize config service
    from flask_app.services.config_service import init_config_service
    init_config_service(app)
    
    # Initialize parameter template service
    from flask_app.services.parameter_template_service import init_parameter_template_service
    init_parameter_template_service(app)
    
    # Initialize annotation service
    from flask_app.services.annotation_service import init_annotation_service
    init_annotation_service(app)
    
    # Initialize modular analysis system
    from flask_app.services.analysis.registry import init_analysis_registry
    init_analysis_registry()
    
    return app


def register_error_handlers(app):
    """Register error handlers for the application. Requirements: 1.3, 13.4"""
    from flask_app.exceptions import AppException
    
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
    from flask_app.routes.auth import auth_bp
    from flask_app.routes.pages import pages_bp
    from flask_app.routes.api import api_bp
    from flask_app.routes.api_projects import project_api_bp
    from flask_app.routes.api_analysis import analysis_bp
    from flask_app.routes.api_statistical import statistical_bp
    from flask_app.routes.api_auto_heatmap import auto_heatmap_bp
    from flask_app.routes.api_chord import chord_bp
    from flask_app.routes.api_script_hub import register_script_hub_routes
    from flask_app.routes.api_treemap import treemap_bp
    from flask_app.routes.api_jobs import jobs_bp

    try:
        from flask_app.routes.api_ppt import ppt_bp
        from flask_app.routes.api_ppt_comparison import ppt_comparison_bp
    except ModuleNotFoundError as exc:
        missing_module = getattr(exc, 'name', None)
        hint = OPTIONAL_DEPENDENCY_HINTS.get(missing_module)
        if hint:
            raise RuntimeError(hint) from exc
        raise
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(jobs_bp)
    app.register_blueprint(project_api_bp)
    # Register the new analysis blueprint
    app.register_blueprint(analysis_bp, url_prefix='/api/analysis')
    # Register statistical analysis blueprint
    app.register_blueprint(statistical_bp)
    # Register PPT heatmap replacement blueprint
    app.register_blueprint(ppt_bp)
    # Register PPT comparison blueprint
    app.register_blueprint(ppt_comparison_bp)
    # Register auto heatmap analysis API blueprint
    app.register_blueprint(auto_heatmap_bp)
    # Register chord diagram analysis API blueprint
    app.register_blueprint(chord_bp)
    # Register script hub API blueprint (modular package)
    register_script_hub_routes(app)
    # Register treemap analysis API blueprint
    app.register_blueprint(treemap_bp)


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
