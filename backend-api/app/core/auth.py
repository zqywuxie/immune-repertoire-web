"""Migration-phase authentication for the standalone FastAPI API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, status

from .config import settings


@dataclass(frozen=True)
class ApiPrincipal:
    """Authenticated API caller used during the bridge migration."""

    authenticated: bool
    subject: str
    auth_mode: str


def _bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return ""
    return token.strip()


def require_current_user(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> ApiPrincipal:
    expected = settings.auth_token.strip()
    if not expected:
        return ApiPrincipal(
            authenticated=False,
            subject="migration-anonymous",
            auth_mode="disabled",
        )

    supplied = (x_api_key or "").strip() or _bearer_token(authorization)
    if supplied != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return ApiPrincipal(
        authenticated=True,
        subject="api-token",
        auth_mode="api_token",
    )
