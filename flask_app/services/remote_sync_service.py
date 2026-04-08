"""
Remote SSH directory sync service.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict

from flask import current_app

from flask_app.services.remote_data_source_service import SSHRemoteSource
from flask_app.services.ssh_file_provider import build_ssh_file_provider


def _ensure_within(parent: Path, candidate: Path) -> None:
    resolved_parent = parent.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_parent not in [resolved_candidate, *resolved_candidate.parents]:
        raise RuntimeError(f"Path '{resolved_candidate}' is outside remote cache root '{resolved_parent}'")


class RemoteSyncService:
    def __init__(self, cache_root: Path) -> None:
        self.cache_root = cache_root

    def sync_directory(
        self,
        source: SSHRemoteSource,
        remote_path: str,
        *,
        force_refresh: bool = False,
        progress_callback: Callable[[float, str, str, Dict[str, Any] | None], None] | None = None,
    ) -> Dict[str, Any]:
        source_cache_root = self.cache_root / source.source_id
        source_cache_root.mkdir(parents=True, exist_ok=True)
        _ensure_within(self.cache_root, source_cache_root)

        cache_key = hashlib.sha1(f"{source.source_id}:{remote_path}".encode("utf-8")).hexdigest()[:16]
        cache_dir = source_cache_root / cache_key
        data_dir = cache_dir / "data"
        manifest_path = cache_dir / "_remote_sync_manifest.json"

        if cache_dir.exists() and manifest_path.exists() and not force_refresh:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            return {
                "source_id": source.source_id,
                "remote_path": manifest.get("remote_path", remote_path),
                "local_cache_path": str(data_dir),
                "file_count": manifest.get("file_count", 0),
                "total_bytes": manifest.get("total_bytes", 0),
                "reused_cache": True,
            }

        temp_dir = source_cache_root / f"{cache_key}.tmp-{uuid.uuid4().hex[:8]}"
        temp_data_dir = temp_dir / "data"
        _ensure_within(self.cache_root, temp_dir)

        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_data_dir.mkdir(parents=True, exist_ok=True)

        provider = build_ssh_file_provider(source)
        allowed_extensions = current_app.config.get("REMOTE_SYNC_ALLOWED_EXTENSIONS") or []
        hidden_directories = current_app.config.get("REMOTE_SYNC_HIDDEN_DIRECTORIES") or []

        if progress_callback:
            progress_callback(
                10.0,
                "Inspecting remote files",
                f"Scanning {remote_path}",
                {"phase": "scan_remote", "source_id": source.source_id, "remote_path": remote_path},
            )

        sync_info = provider.download_tree(
            remote_path,
            temp_data_dir,
            include_extensions=allowed_extensions,
            hidden_directories=hidden_directories,
            progress_callback=progress_callback,
        )

        manifest = {
            "source_id": source.source_id,
            "source_name": source.name,
            "remote_path": sync_info["remote_path"],
            "local_cache_path": str(temp_data_dir),
            "file_count": sync_info["file_count"],
            "total_bytes": sync_info["total_bytes"],
            "downloaded_files": sync_info["downloaded_files"],
            "synced_at": datetime.utcnow().isoformat() + "Z",
        }
        manifest_path_tmp = temp_dir / "_remote_sync_manifest.json"
        manifest_path_tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        if cache_dir.exists():
            _ensure_within(self.cache_root, cache_dir)
            shutil.rmtree(cache_dir)
        temp_dir.rename(cache_dir)

        final_data_dir = cache_dir / "data"
        return {
            "source_id": source.source_id,
            "remote_path": sync_info["remote_path"],
            "local_cache_path": str(final_data_dir),
            "file_count": sync_info["file_count"],
            "total_bytes": sync_info["total_bytes"],
            "reused_cache": False,
        }


def get_remote_sync_service() -> RemoteSyncService:
    cache_root = Path(current_app.config.get("REMOTE_CACHE_FOLDER", Path(current_app.root_path) / "data" / "remote_cache"))
    if not cache_root.is_absolute():
        cache_root = Path(current_app.root_path) / cache_root
    cache_root.mkdir(parents=True, exist_ok=True)
    return RemoteSyncService(cache_root=cache_root)
