"""
SSH/SFTP file provider for Linux remote data sources.
"""

from __future__ import annotations

import importlib
import posixpath
import stat
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List

from flask_app.exceptions import ValidationError
from flask_app.services.remote_data_source_service import SSHRemoteSource

try:
    import paramiko
except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency is optional in tests
    paramiko = None
    _PARAMIKO_IMPORT_ERROR: ModuleNotFoundError | None = exc
else:  # pragma: no cover - import path is exercised at runtime
    _PARAMIKO_IMPORT_ERROR = None


def _load_paramiko():
    global paramiko, _PARAMIKO_IMPORT_ERROR
    if paramiko is not None:
        return paramiko

    try:
        paramiko = importlib.import_module("paramiko")
        _PARAMIKO_IMPORT_ERROR = None
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime environment
        _PARAMIKO_IMPORT_ERROR = exc
        paramiko = None
    return paramiko


def _require_paramiko():
    paramiko_module = _load_paramiko()
    if paramiko_module is None:
        missing_module = getattr(_PARAMIKO_IMPORT_ERROR, "name", "paramiko")
        if missing_module == "paramiko":
            reason = "paramiko is not installed in the current Python environment"
        else:
            reason = f"paramiko could not be imported because dependency '{missing_module}' is missing"
        raise RuntimeError(
            f"{reason}. Current Python executable: {sys.executable}. "
            "Install the dependency in this environment and restart the Flask backend if it was already running."
        )
    return paramiko_module


def _normalize_remote_path(path: str | None) -> str:
    raw = str(path or "/").strip().replace("\\", "/")
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return posixpath.normpath(raw)


def _is_within_root(root_path: str, target_path: str) -> bool:
    root = _normalize_remote_path(root_path)
    target = _normalize_remote_path(target_path)
    if root == "/":
        return target.startswith("/")
    return target == root or target.startswith(f"{root}/")


@dataclass(frozen=True)
class RemoteDirectoryEntry:
    name: str
    path: str
    is_dir: bool
    size: int
    modified_time: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "is_dir": self.is_dir,
            "size": self.size,
            "modified_time": self.modified_time,
        }


class SSHFileProvider:
    def __init__(self, source: SSHRemoteSource) -> None:
        self.source = source

    def resolve_remote_path(self, path: str | None = None) -> str:
        root = _normalize_remote_path(self.source.root_path)
        if not path:
            return root

        raw = str(path).strip().replace("\\", "/")
        candidate = _normalize_remote_path(raw if raw.startswith("/") else posixpath.join(root, raw))
        if not _is_within_root(root, candidate):
            raise ValidationError(
                message="Remote path is outside the configured root directory",
                details={"field": "path", "root_path": root, "path": candidate},
            )
        return candidate

    @contextmanager
    def open_sftp(self) -> Iterator[Any]:
        paramiko_module = _require_paramiko()
        ssh_client = paramiko_module.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko_module.AutoAddPolicy())

        connect_kwargs: Dict[str, Any] = {
            "hostname": self.source.host,
            "port": self.source.port,
            "username": self.source.username,
            "timeout": 15,
        }
        if self.source.auth_type == "password":
            connect_kwargs["password"] = self.source.password
        else:
            connect_kwargs["key_filename"] = self.source.key_path

        ssh_client.connect(**connect_kwargs)
        sftp_client = ssh_client.open_sftp()
        try:
            yield sftp_client
        finally:
            try:
                sftp_client.close()
            finally:
                ssh_client.close()

    def test_connection(self) -> Dict[str, Any]:
        with self.open_sftp() as sftp_client:
            resolved_root = self.resolve_remote_path(self.source.root_path)
            root_stat = sftp_client.stat(resolved_root)
            return {
                "root_path": resolved_root,
                "is_dir": stat.S_ISDIR(root_stat.st_mode),
            }

    def list_dir(self, path: str | None = None) -> Dict[str, Any]:
        remote_path = self.resolve_remote_path(path)
        with self.open_sftp() as sftp_client:
            current_stat = sftp_client.stat(remote_path)
            if not stat.S_ISDIR(current_stat.st_mode):
                raise ValidationError(message="Selected remote path is not a directory", details={"field": "path"})

            entries: List[RemoteDirectoryEntry] = []
            for item in sftp_client.listdir_attr(remote_path):
                name = item.filename
                child_path = _normalize_remote_path(posixpath.join(remote_path, name))
                entries.append(
                    RemoteDirectoryEntry(
                        name=name,
                        path=child_path,
                        is_dir=stat.S_ISDIR(item.st_mode),
                        size=int(getattr(item, "st_size", 0) or 0),
                        modified_time=int(getattr(item, "st_mtime", 0) or 0),
                    )
                )

        entries.sort(key=lambda entry: (not entry.is_dir, entry.name.lower()))
        parent_path = posixpath.dirname(remote_path.rstrip("/")) or "/"
        if not _is_within_root(self.source.root_path, parent_path):
            parent_path = None

        return {
            "root_path": self.resolve_remote_path(self.source.root_path),
            "current_path": remote_path,
            "parent_path": parent_path,
            "entries": [entry.to_dict() for entry in entries],
        }

    def download_tree(
        self,
        remote_path: str,
        local_dir: Path,
        *,
        include_extensions: Iterable[str],
        hidden_directories: Iterable[str],
        progress_callback: Callable[[float, str, str, Dict[str, Any] | None], None] | None = None,
    ) -> Dict[str, Any]:
        normalized_remote_path = self.resolve_remote_path(remote_path)
        allowed_exts = {str(ext).lower() for ext in include_extensions}
        hidden_names = {str(name).lower() for name in hidden_directories}

        with self.open_sftp() as sftp_client:
            remote_root_stat = sftp_client.stat(normalized_remote_path)
            if not stat.S_ISDIR(remote_root_stat.st_mode):
                raise ValidationError(message="Selected remote path is not a directory", details={"field": "remote_path"})

            files_to_download = self._collect_downloadable_files(
                sftp_client,
                normalized_remote_path,
                allowed_exts=allowed_exts,
                hidden_names=hidden_names,
            )

            if not files_to_download:
                raise ValidationError(
                    message="No supported repertoire files were found in the remote directory",
                    details={"field": "remote_path", "remote_path": normalized_remote_path},
                )

            total_bytes = sum(item["size"] for item in files_to_download)
            downloaded_bytes = 0
            local_dir.mkdir(parents=True, exist_ok=True)

            for index, item in enumerate(files_to_download, start=1):
                relative_path = item["relative_path"]
                local_path = local_dir / Path(relative_path)
                local_path.parent.mkdir(parents=True, exist_ok=True)
                sftp_client.get(item["remote_path"], str(local_path))
                downloaded_bytes += item["size"]

                if progress_callback:
                    percent = 25.0 + (index / len(files_to_download)) * 75.0
                    progress_callback(
                        percent,
                        "Downloading remote files",
                        f"Downloaded {relative_path}",
                        {
                            "phase": "download_remote",
                            "current_file": relative_path,
                            "downloaded_files": index,
                            "total_files": len(files_to_download),
                            "downloaded_bytes": downloaded_bytes,
                            "total_bytes": total_bytes,
                        },
                    )

        return {
            "remote_path": normalized_remote_path,
            "file_count": len(files_to_download),
            "total_bytes": total_bytes,
            "downloaded_files": [item["relative_path"] for item in files_to_download],
        }

    def _collect_downloadable_files(
        self,
        sftp_client: Any,
        remote_root: str,
        *,
        allowed_exts: set[str],
        hidden_names: set[str],
    ) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []

        def walk(current_path: str) -> None:
            for item in sftp_client.listdir_attr(current_path):
                name = item.filename
                child_path = _normalize_remote_path(posixpath.join(current_path, name))
                if stat.S_ISDIR(item.st_mode):
                    if name.lower() in hidden_names:
                        continue
                    walk(child_path)
                    continue

                if not self._matches_allowed_extension(name, allowed_exts):
                    continue

                collected.append(
                    {
                        "remote_path": child_path,
                        "relative_path": posixpath.relpath(child_path, remote_root),
                        "size": int(getattr(item, "st_size", 0) or 0),
                    }
                )

        walk(remote_root)
        collected.sort(key=lambda item: item["relative_path"].lower())
        return collected

    @staticmethod
    def _matches_allowed_extension(filename: str, allowed_exts: set[str]) -> bool:
        lower_name = filename.lower()
        return any(lower_name.endswith(ext) for ext in allowed_exts)


def build_ssh_file_provider(source: SSHRemoteSource) -> SSHFileProvider:
    return SSHFileProvider(source)
