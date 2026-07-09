"""API Blueprint package — modularised from the monolithic api.py.

Each domain module registers its own Blueprint under the parent
``api_bp`` (prefix ``/api``).  Import ``register_api_routes(app)``
from here and call it during application creation.
"""

from flask import Blueprint


def _build_api_bp():
    """Create a fresh parent Blueprint with all sub-blueprints registered as children.

    Returns a new Blueprint each call, safe for repeated app creation (e.g. tests).
    """
    from . import (
        files,
        mappings,
        directories_files,
        analysis_bridge,
        config_params,
        annotations_groups,
        baseline_extra,
        pdf_routes,
        misc_routes,
    )

    bp = Blueprint("api", __name__, url_prefix="/api")

    for mod in [
        files,
        mappings,
        directories_files,
        analysis_bridge,
        config_params,
        annotations_groups,
        baseline_extra,
        pdf_routes,
        misc_routes,
    ]:
        bp.register_blueprint(mod.bp)

    return bp


def register_api_routes(app):
    """Register all API sub-blueprints with the Flask application."""
    app.register_blueprint(_build_api_bp())


def __getattr__(name):
    """Lazy attribute access for backward-compatible ``api_bp``.

    Legacy code accesses ``api_bp`` as a module attribute.
    Returns a freshly-built Blueprint so repeated app creation works.
    """
    if name == "api_bp":
        return _build_api_bp()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
