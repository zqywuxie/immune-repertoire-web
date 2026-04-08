"""
Configuration-backed SSH remote data source registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from flask import current_app

from flask_app.exceptions import ValidationError


def _normalize_remote_path(path: str | None) -> str:
    raw = str(path or "/").strip().replace("\\", "/")
    if not raw.startswith("/"):
        raw = f"/{raw}"

    parts: list[str] = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


@dataclass(frozen=True)
class SSHRemoteSource:
    source_id: str
    name: str
    host: str
    port: int
    username: str
    auth_type: str
    password: str | None
    key_path: str | None
    root_path: str
    enabled: bool
    description: str | None = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SSHRemoteSource":
        source_id = str(payload.get("id") or "").strip()
        name = str(payload.get("name") or source_id).strip()
        host = str(payload.get("host") or "").strip()
        username = str(payload.get("username") or "").strip()
        auth_type = str(payload.get("auth_type") or "password").strip().lower()
        if auth_type not in {"password", "private_key"}:
            raise ValidationError(message=f"Unsupported SSH auth type: {auth_type}")

        if not source_id or not host or not username:
            raise ValidationError(message="SSH remote source is missing required fields: id/host/username")

        port = int(payload.get("port") or 22)
        password = payload.get("password")
        key_path = payload.get("key_path")
        if auth_type == "password" and not password:
            raise ValidationError(message=f"SSH remote source '{source_id}' is missing password")
        if auth_type == "private_key" and not key_path:
            raise ValidationError(message=f"SSH remote source '{source_id}' is missing key_path")

        return cls(
            source_id=source_id,
            name=name,
            host=host,
            port=port,
            username=username,
            auth_type=auth_type,
            password=str(password) if password is not None else None,
            key_path=str(key_path) if key_path is not None else None,
            root_path=_normalize_remote_path(payload.get("root_path") or "/"),
            enabled=bool(payload.get("enabled", True)),
            description=str(payload.get("description")).strip() if payload.get("description") else None,
        )

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "auth_type": self.auth_type,
            "root_path": self.root_path,
            "enabled": self.enabled,
            "description": self.description,
        }


class RemoteDataSourceService:
    def __init__(self, source_configs: Iterable[Dict[str, Any]] | None = None) -> None:
        self._sources: Dict[str, SSHRemoteSource] = {}
        for item in source_configs or []:
            source = SSHRemoteSource.from_dict(item)
            self._sources[source.source_id] = source

    def list_sources(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        sources = list(self._sources.values())
        if enabled_only:
            sources = [source for source in sources if source.enabled]
        return [source.to_public_dict() for source in sorted(sources, key=lambda item: item.name.lower())]

    def get_source(self, source_id: str, require_enabled: bool = True) -> SSHRemoteSource:
        source = self._sources.get(str(source_id or "").strip())
        if source is None:
            raise ValidationError(message=f"Unknown SSH remote source: {source_id}", details={"field": "source_id"})
        if require_enabled and not source.enabled:
            raise ValidationError(message=f"SSH remote source is disabled: {source_id}", details={"field": "source_id"})
        return source


def get_remote_data_source_service() -> RemoteDataSourceService:
    source_configs = None

    try:
        from flask_app.services.config_service import get_config_service
        config = get_config_service().get_config()
        source_configs = getattr(config, "ssh_remote_sources", None)
    except Exception:
        source_configs = None

    if not source_configs:
        source_configs = current_app.config.get("SSH_REMOTE_SOURCES") or []

    return RemoteDataSourceService(source_configs)
