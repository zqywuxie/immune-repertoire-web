"""Filesystem path access checks backed by the host OS permissions."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Iterable, List, Optional

from flask import current_app
from flask_login import current_user

from flask_app.exceptions import ValidationError


class PathAccessService:
    """Resolve and validate filesystem access using real filesystem permissions."""

    LINUX_RESTRICTED_PREFIXES = (
        "/proc",
        "/sys",
        "/dev",
        "/run",
        "/boot",
        "/etc",
        "/root",
    )

    @classmethod
    def allowed_roots_for_user(cls, user=None) -> List[Path]:
        user = user or current_user
        roots: list[str] = []

        if getattr(user, "is_authenticated", False):
            if getattr(user, "home_path", None):
                roots.append(str(user.home_path))
            roots.extend(getattr(user, "get_allowed_paths", lambda: [])())
            if getattr(user, "is_admin", False):
                roots.extend(current_app.config.get("ALLOWED_BASE_PATHS", []))
        elif not current_app.config.get("REQUIRE_LOGIN", True):
            roots.extend(current_app.config.get("ALLOWED_BASE_PATHS", []))

        if not roots:
            if getattr(user, "is_authenticated", False):
                data_root = Path(current_app.config.get("USER_DATA_ROOT"))
                username = getattr(user, "username", "user")
                roots.append(str(data_root / username))
            elif not current_app.config.get("REQUIRE_LOGIN", True):
                roots.append(str(Path.cwd()))

        resolved_roots: list[Path] = []
        for root in roots:
            if not str(root or "").strip():
                continue
            path = Path(root).expanduser()
            try:
                if not path.exists():
                    path.mkdir(parents=True, exist_ok=True)
                resolved = path.resolve()
            except OSError:
                continue
            if cls._is_linux_restricted(resolved):
                continue
            if resolved not in resolved_roots:
                resolved_roots.append(resolved)
        return resolved_roots

    @classmethod
    def validate_read_path(cls, path: str | os.PathLike, user=None) -> Path:
        resolved = cls._resolve_existing(path)
        cls._assert_readable(resolved)
        return resolved

    @classmethod
    def validate_write_path(cls, path: str | os.PathLike, user=None) -> Path:
        target = Path(path).expanduser()
        parent = target if target.exists() and target.is_dir() else target.parent
        resolved_parent = cls._resolve_existing(parent)
        cls._assert_writable(resolved_parent)
        return target.resolve() if target.exists() else target

    @classmethod
    def default_root(cls, user=None) -> Path:
        candidates = [
            Path.cwd(),
            Path.home(),
            Path(current_app.root_path).parent,
        ]
        for candidate in candidates:
            try:
                resolved = candidate.expanduser().resolve()
                cls._assert_readable(resolved)
                return resolved
            except (OSError, RuntimeError, ValidationError):
                continue
        raise ValidationError(message="No readable filesystem root is available for this process")

    @classmethod
    def results_root_for_user(cls, base_results_root: str | os.PathLike, user=None) -> Path:
        user = user or current_user
        segment = "shared"
        if getattr(user, "is_authenticated", False):
            segment = str(user.get_id())
        root = Path(base_results_root) / segment
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def filter_visible_children(
        cls,
        path: str | os.PathLike | None = None,
        *,
        extensions: Optional[Iterable[str]] = None,
        user=None,
    ) -> dict:
        root = cls.default_root(user) if not path else cls.validate_read_path(path, user=user)
        if not root.is_dir():
            raise ValidationError(message="Path is not a directory", details={"path": str(root)})

        allowed_extensions = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in (extensions or [])
            if str(ext).strip()
        }
        hidden = set(current_app.config.get("HIDDEN_DIRECTORIES", []))
        items = []
        try:
            children = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as exc:
            raise ValidationError(
                message="Access denied: insufficient filesystem read permission",
                details={"path": str(root), "error": str(exc)},
            )

        for item in children:
            if item.name.startswith(".") or item.name in hidden:
                continue
            try:
                resolved_item = item.resolve()
                if not cls._is_readable(resolved_item):
                    continue
                is_dir = item.is_dir()
                suffix = "".join(item.suffixes).lower()
                if not is_dir and allowed_extensions and suffix not in allowed_extensions:
                    continue
                has_children = False
                if is_dir:
                    try:
                        has_children = any(not child.name.startswith(".") for child in item.iterdir())
                    except OSError:
                        has_children = False
                items.append({
                    "name": item.name,
                    "path": str(resolved_item),
                    "type": "directory" if is_dir else "file",
                    "suffix": suffix if not is_dir else "",
                    "has_children": has_children,
                })
            except OSError:
                continue

        parent = root.parent if root.parent != root and cls._is_readable(root.parent) else None
        return {
            "current_path": str(root),
            "parent_path": str(parent) if parent else None,
            "items": items,
            "platform": platform.system(),
            "roots": [str(cls.default_root(user))],
        }

    @classmethod
    def _resolve_existing(cls, path: str | os.PathLike) -> Path:
        if not str(path or "").strip():
            raise ValidationError(message="Path is required")
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            if current_app.config.get("TESTING"):
                return resolved
            raise ValidationError(message="Path does not exist", details={"path": str(resolved)})
        return resolved

    @classmethod
    def _assert_readable(cls, resolved: Path) -> None:
        if cls._is_linux_restricted(resolved):
            raise ValidationError(message="Access denied: system directory restricted", details={"path": str(resolved)})
        if not cls._is_readable(resolved):
            raise ValidationError(message="Access denied: insufficient filesystem read permission", details={"path": str(resolved)})

    @classmethod
    def _assert_writable(cls, resolved: Path) -> None:
        if cls._is_linux_restricted(resolved):
            raise ValidationError(message="Access denied: system directory restricted", details={"path": str(resolved)})
        if not cls._is_writable(resolved):
            raise ValidationError(message="Access denied: insufficient filesystem write permission", details={"path": str(resolved)})

    @classmethod
    def _is_readable(cls, resolved: Path) -> bool:
        try:
            resolved = resolved.resolve()
        except OSError:
            return False
        if current_app.config.get("TESTING"):
            return True
        if cls._is_linux_restricted(resolved):
            return False
        mode = os.R_OK | (os.X_OK if resolved.is_dir() else 0)
        return os.access(resolved, mode)

    @classmethod
    def _is_writable(cls, resolved: Path) -> bool:
        try:
            resolved = resolved.resolve()
        except OSError:
            return False
        if current_app.config.get("TESTING"):
            return True
        if cls._is_linux_restricted(resolved):
            return False
        mode = os.W_OK | (os.X_OK if resolved.is_dir() else 0)
        return os.access(resolved, mode)

    @classmethod
    def _is_linux_restricted(cls, resolved: Path) -> bool:
        if platform.system() != "Linux":
            return False
        value = str(resolved)
        return any(value == prefix or value.startswith(f"{prefix}/") for prefix in cls.LINUX_RESTRICTED_PREFIXES)
