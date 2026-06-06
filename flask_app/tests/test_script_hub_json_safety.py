"""Tests for Script Hub strict JSON payload safety."""

from importlib import import_module
from pathlib import Path
import json
import sys
from types import SimpleNamespace

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parents[1]
for import_dir in (APP_DIR, ROOT_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))


def _import_script_hub_module():
    sys.modules.setdefault("umap", SimpleNamespace(UMAP=object))
    try:
        return import_module("flask_app.routes.api_script_hub")
    except ModuleNotFoundError:
        return import_module("routes.api_script_hub")


def test_sanitize_nan_produces_strict_json_payload():
    api_script_hub = _import_script_hub_module()

    payload = {
        "preview_rows": [[26, float("nan"), pd.NA, pd.NaT, float("inf")]],
        "nested": {"value": float("-inf")},
    }

    sanitized = api_script_hub._sanitize_nan(payload)
    encoded = json.dumps(sanitized, allow_nan=False)

    assert "NaN" not in encoded
    assert "Infinity" not in encoded
    assert sanitized["preview_rows"] == [[26, None, None, None, None]]
    assert sanitized["nested"]["value"] is None
