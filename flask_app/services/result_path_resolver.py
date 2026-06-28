"""Helpers for resolving generated result directories across scoped roots."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from flask import current_app
from flask_login import current_user

from flask_app.services.path_access_service import PathAccessService


def configured_results_root() -> Path:
    """Return the unscoped RESULTS_FOLDER path from app configuration."""
    results_root = Path(current_app.config.get("RESULTS_FOLDER", Path(current_app.root_path) / "data" / "results"))
    if not results_root.is_absolute():
        results_root = Path(current_app.root_path) / results_root
    return results_root.resolve()


def scoped_results_root() -> Path:
    """Return the current user's scoped results root."""
    return PathAccessService.results_root_for_user(configured_results_root())


def candidate_job_roots(
    results_root: str | Path,
    result_dir: str,
    job_id: str,
    *,
    nested_dir: Optional[str] = None,
) -> Iterable[Path]:
    """Yield compatible job roots for legacy and user-scoped result URLs."""
    root = Path(results_root).resolve()
    roots: list[Path] = [root]

    if root.name == "shared" or root.name.isdigit():
        roots.append(root.parent)

    try:
        configured_root = configured_results_root()
        roots.append(configured_root)
        roots.append(scoped_results_root())
    except RuntimeError:
        configured_root = root.parent if (root.name == "shared" or root.name.isdigit()) else root

    allow_sibling_scan = (
        current_app.config.get("TESTING")
        or not current_app.config.get("REQUIRE_LOGIN", True)
        or getattr(current_user, "is_admin", False)
    )
    search_roots = [configured_root] if allow_sibling_scan else []

    seen: set[Path] = set()
    for base in roots:
        candidate = (base / result_dir / job_id).resolve()
        if nested_dir:
            candidate = candidate / nested_dir
        if candidate not in seen:
            seen.add(candidate)
            yield candidate

    for search_root in search_roots:
        try:
            matches = sorted(search_root.glob(f"*/{result_dir}/{job_id}"))
        except OSError:
            continue
        for match in matches:
            candidate = match.resolve()
            if nested_dir:
                candidate = candidate / nested_dir
            if candidate not in seen:
                seen.add(candidate)
                yield candidate
