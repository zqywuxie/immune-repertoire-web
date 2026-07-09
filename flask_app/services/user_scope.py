"""Helpers for applying current-user ownership rules."""

from __future__ import annotations

from typing import Any

from flask import current_app
from flask_login import current_user

from flask_app.exceptions import ValidationError


def is_authenticated() -> bool:
    return bool(getattr(current_user, "is_authenticated", False))


def is_admin() -> bool:
    return bool(is_authenticated() and getattr(current_user, "is_admin", False))


def current_user_id() -> int | None:
    if not is_authenticated():
        return None
    try:
        return int(current_user.get_id())
    except (TypeError, ValueError):
        return None


def scope_query(query, model):
    """Limit a SQLAlchemy query to the current user unless current user is admin."""
    if not is_authenticated() and not current_app.config.get("REQUIRE_LOGIN", True):
        return query
    if is_admin() or not hasattr(model, "user_id"):
        return query
    user_id = current_user_id()
    if user_id is None:
        return query.filter(False)
    return query.filter(model.user_id == user_id)


def assign_owner(obj: Any) -> None:
    """Assign current user_id to a new model instance when the model supports it."""
    if hasattr(obj, "user_id") and current_user_id() is not None:
        obj.user_id = current_user_id()


def assert_owned(obj: Any, resource_name: str = "Resource") -> None:
    """Raise ValidationError if current user cannot access obj."""
    if obj is None:
        raise ValidationError(message=f"{resource_name} not found")
    if not is_authenticated() and (
        current_app.config.get("TESTING", False)
        or not current_app.config.get("REQUIRE_LOGIN", True)
    ):
        return
    if is_admin() or not hasattr(obj, "user_id"):
        return
    owner_id = getattr(obj, "user_id", None)
    if owner_id is None:
        raise ValidationError(message=f"{resource_name} is not assigned to your account")
    if int(owner_id) != current_user_id():
        raise ValidationError(message=f"{resource_name} not found")
