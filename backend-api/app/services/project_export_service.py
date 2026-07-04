"""Project export service for database-management downloads."""

from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .asset_service import AssetService


class ProjectExportService:
    """Build project-level ZIP exports without exposing server paths."""

    def __init__(self, db: Session) -> None:
        self.assets = AssetService(db)

    def build_export_zip(
        self,
        project: dict,
        *,
        include_assets: bool = True,
        include_results: bool = True,
        include_group_specs: bool = True,
        include_manifest: bool = True,
    ) -> Path:
        project_id = str(project["id"])
        all_assets = self.assets.list_all_project_assets(project_id)
        selected_assets = [
            asset for asset in all_assets
            if self._include_asset(asset, include_assets, include_results, include_group_specs)
        ]

        fd, tmp_name = tempfile.mkstemp(prefix=f"project_{project_id[:8]}_", suffix=".zip")
        os.close(fd)
        zip_path = Path(tmp_name)

        manifest = {
            "project": self._safe_project(project),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "include_assets": include_assets,
            "include_results": include_results,
            "include_group_specs": include_group_specs,
            "asset_count": len(selected_assets),
            "assets": [self._safe_asset(asset) for asset in selected_assets],
        }

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if include_manifest:
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
                )
            if include_group_specs:
                group_specs = [
                    self._safe_asset(asset) for asset in all_assets
                    if str(asset.get("asset_type")) == "group_spec"
                ]
                archive.writestr(
                    "group_specs/group_specs.json",
                    json.dumps(group_specs, ensure_ascii=False, indent=2, default=str),
                )

            seen_names: set[str] = set()
            for asset in selected_assets:
                source = self.assets.resolve_asset_file(asset)
                if source is None:
                    continue
                prefix = self._asset_prefix(asset)
                if source.is_file():
                    arcname = self._unique_archive_name(
                        f"{prefix}/{self._safe_name(str(asset.get('original_name') or source.name))}",
                        seen_names,
                    )
                    archive.write(source, arcname)
                elif source.is_dir():
                    for child in source.rglob("*"):
                        if child.is_file():
                            rel = child.relative_to(source).as_posix()
                            arcname = self._unique_archive_name(
                                f"{prefix}/{self._safe_name(str(asset.get('original_name') or source.name))}/{rel}",
                                seen_names,
                            )
                            archive.write(child, arcname)

        return zip_path

    @staticmethod
    def _include_asset(
        asset: dict,
        include_assets: bool,
        include_results: bool,
        include_group_specs: bool,
    ) -> bool:
        asset_type = str(asset.get("asset_type") or "")
        if asset_type == "processed_result":
            return include_results
        if asset_type == "group_spec":
            return include_group_specs
        return include_assets

    @staticmethod
    def _asset_prefix(asset: dict) -> str:
        asset_type = str(asset.get("asset_type") or "asset")
        if asset_type == "processed_result":
            return "results"
        if asset_type == "group_spec":
            return "group_specs/files"
        return f"assets/{ProjectExportService._safe_name(asset_type)}"

    @staticmethod
    def _safe_project(project: dict) -> dict:
        return {
            "id": project.get("id"),
            "name": project.get("name"),
            "institution": project.get("institution"),
            "cooperation_level": project.get("cooperation_level"),
            "description": project.get("description"),
            "status": project.get("status"),
            "asset_counts": project.get("asset_counts") or {},
            "asset_status": project.get("asset_status") or {},
        }

    @staticmethod
    def _safe_asset(asset: dict) -> dict:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        public_metadata = {
            key: value
            for key, value in metadata.items()
            if key not in {"storage_uri", "storage_path", "path", "server_path"}
        }
        return {
            "id": asset.get("id"),
            "asset_type": asset.get("asset_type"),
            "original_name": asset.get("original_name"),
            "mime_type": asset.get("mime_type"),
            "size": asset.get("size"),
            "asset_set": metadata.get("asset_set") or metadata.get("group_label"),
            "metadata": public_metadata,
            "uploaded_at": asset.get("uploaded_at"),
        }

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._()\-\u4e00-\u9fff]+", "_", value.strip())
        return cleaned.strip("._") or "item"

    @staticmethod
    def _unique_archive_name(name: str, seen: set[str]) -> str:
        candidate = name
        counter = 2
        while candidate in seen:
            path = Path(name)
            candidate = f"{path.with_suffix('').as_posix()}_{counter}{path.suffix}"
            counter += 1
        seen.add(candidate)
        return candidate
