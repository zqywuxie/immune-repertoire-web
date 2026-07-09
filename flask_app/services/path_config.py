"""Centralized path configuration — replaces hardcoded Windows paths.

All paths can be overridden via environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_path(key: str, default: str) -> Path:
    return Path(os.environ.get(key, default))


# Core data directories — default to <project_root>/flask_app/data/…
_DATA_BASE = Path(__file__).resolve().parents[2]  # project root
DATA_ROOT = _env_path("DATA_ROOT", str(_DATA_BASE / "flask_app" / "data"))
PROJECTS_DIR = _env_path("PROJECTS_DIR", str(DATA_ROOT / "projects"))
RESULTS_DIR = _env_path("RESULTS_DIR", str(DATA_ROOT / "results"))
UPLOADS_DIR = _env_path("UPLOADS_DIR", str(DATA_ROOT / "uploads"))
REFERENCE_DIR = _env_path("REFERENCE_DIR", str(DATA_ROOT / "reference"))
USERS_DIR = _env_path("USERS_DIR", str(DATA_ROOT / "users"))
CUSTOM_SCHEMES_DIR = _env_path("CUSTOM_SCHEMES_DIR", str(DATA_ROOT / "custom_schemes"))

# Storage
STORAGE_ROOT = _env_path("STORAGE_ROOT", str(PROJECTS_DIR))


def get_data_subdir(name: str) -> Path:
    """Get a subdirectory under DATA_ROOT, creating it if needed."""
    path = DATA_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path
