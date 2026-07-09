"""Module registry — loads analysis modules from the canonical YAML manifest.

Serves as the single source of truth for ``/api/jobs/modules``,
replacing the previously hardcoded list in the route handler.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# Resolve the manifest relative to the project root.
_MANIFEST_PATH = Path(__file__).resolve().parents[3] / "docs" / "api" / "module-manifest.yaml"


class ModuleRegistry:
    """Read-only registry of enabled analysis modules."""

    def __init__(self, manifest_path: Optional[Path] = None) -> None:
        self._path = manifest_path or _MANIFEST_PATH
        self._modules: List[Dict[str, Any]] = []
        self._by_key: Dict[str, Dict[str, Any]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, yaml.YAMLError):
            self._loaded = True
            return

        modules = raw.get("modules") if isinstance(raw, dict) else []
        if not isinstance(modules, list):
            self._loaded = True
            return

        for m in modules:
            if not isinstance(m, dict):
                continue
            if m.get("enabled") is False:
                continue
            self._modules.append(m)
            self._by_key[m.get("key", "")] = m

        self._loaded = True

    @property
    def modules(self) -> List[Dict[str, Any]]:
        self._ensure_loaded()
        return list(self._modules)

    def list_for_frontend(self) -> List[Dict[str, Any]]:
        """Return a minimal list suitable for ``/api/jobs/modules``."""
        self._ensure_loaded()
        return [
            {
                "key": m["key"],
                "label": m.get("label", m["key"]),
                "category": m.get("category", ""),
                "description": m.get("description", ""),
                "output_kinds": m.get("output_kinds", []),
                "ui_entry": m.get("ui_entry", ""),
            }
            for m in self._modules
        ]

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        self._ensure_loaded()
        return self._by_key.get(key)

    def validate_module(self, key: str) -> bool:
        """Return True if *key* is a known, enabled module."""
        return self.get(key) is not None

    def input_schema(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the JSON Schema for a module's payload parameter."""
        m = self.get(key)
        return m.get("input_schema") if m else None


@lru_cache(maxsize=1)
def get_module_registry() -> ModuleRegistry:
    return ModuleRegistry()
