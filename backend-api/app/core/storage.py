"""Standalone storage resolver for FastAPI — no Flask dependency."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


class StorageResolver:
    """Resolve storage URIs and legacy paths to filesystem paths.

    Unlike Flask's LocalStorageAdapter, this resolver does NOT depend on
    Flask app context or the Flask-specific storage adapter singleton.
    It uses the same URI format (``local:///...``) for compatibility.
    """

    @staticmethod
    def resolve(storage_ref: str | None) -> Path | None:
        """Resolve a storage URI or legacy path to a filesystem Path."""
        raw = str(storage_ref or "").strip()
        if not raw:
            return None

        # Legacy Windows absolute path
        if len(raw) >= 3 and raw[1] == ":" and raw[2] in {"\\", "/"}:
            return Path(raw)

        parsed = urlparse(raw)
        if parsed.scheme:
            if parsed.scheme != "local":
                return None
            if parsed.netloc and parsed.path:
                path_str = unquote(f"/{parsed.netloc}{parsed.path}")
            else:
                path_str = unquote(parsed.path or parsed.netloc)
            if len(path_str) >= 4 and path_str[0] == "/" and path_str[2] == ":":
                path_str = path_str[1:]
            return Path(path_str)

        return Path(raw)

    @staticmethod
    def get_file(storage_uri: str) -> Path:
        """Resolve and verify a file exists. Raises FileNotFoundError."""
        path = StorageResolver.resolve(storage_uri)
        if path is None:
            raise FileNotFoundError(f"Cannot resolve storage URI: {storage_uri!r}")
        if not path.is_file():
            raise FileNotFoundError(f"Resolved path is not a readable file: {path}")
        return path

    @staticmethod
    def resolve_asset_path(asset: dict) -> Path | None:
        """Try storage_uri first, fall back to storage_path.

        Project result assets may point at an output directory rather than a
        single file. Return any existing filesystem path and let the API layer
        choose the preview/download target.
        """
        candidates = [
            asset.get("storage_uri"),
            asset.get("storage_path"),
        ]
        for candidate in candidates:
            path = StorageResolver.resolve(candidate)
            if path and path.exists():
                return path
        return None


_storage = StorageResolver()


def get_storage_resolver() -> StorageResolver:
    return _storage
