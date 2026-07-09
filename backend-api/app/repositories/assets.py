"""AssetRepository — parameterised SQL for project_assets table."""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class AssetRepository:
    """Data access for ``project_assets`` table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _metadata_dict(value) -> dict:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _to_dict(row, *, project_id: Optional[str] = None) -> dict:
        """Map a ``project_assets`` row (dict or mapping) to a stable dict."""
        metadata_val = AssetRepository._metadata_dict(row.get("metadata_json"))
        return {
            "id": str(row.get("id", "")),
            "project_id": project_id or str(row.get("project_id", "")),
            "asset_type": str(row.get("asset_type", "")),
            "original_name": str(row.get("original_name", "")),
            "storage_path": str(row.get("storage_path", "")),
            "storage_uri": metadata_val.get("storage_uri"),
            "mime_type": row.get("mime_type"),
            "size": int(row.get("size", 0)),
            "metadata": metadata_val,
            "uploaded_at": row.get("uploaded_at"),
        }

    # ── queries ────────────────────────────────────────────────────────

    def list_by_project(
        self,
        project_id: str,
        asset_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        """Return (rows, total_count)."""
        conditions = ["project_id = :project_id"]
        params: dict = {"project_id": project_id}

        if asset_type:
            conditions.append("asset_type = :asset_type")
            params["asset_type"] = asset_type

        where_clause = " AND ".join(conditions)

        total = self.db.execute(
            text(f"SELECT COUNT(*) FROM project_assets WHERE {where_clause}"),
            params,
        ).scalar() or 0

        offset = (page - 1) * page_size
        sql = (
            f"SELECT * FROM project_assets WHERE {where_clause}"
            " ORDER BY uploaded_at DESC LIMIT :limit OFFSET :offset"
        )
        params.update({"limit": page_size, "offset": offset})
        rows = self.db.execute(text(sql), params).mappings().all()

        return [self._to_dict(r, project_id=project_id) for r in rows], total

    def list_all_by_project(self, project_id: str, limit: int = 5000) -> list[dict]:
        rows = self.db.execute(
            text(
                "SELECT * FROM project_assets WHERE project_id = :project_id "
                "ORDER BY uploaded_at DESC LIMIT :limit"
            ),
            {"project_id": project_id, "limit": limit},
        ).mappings().all()
        return [self._to_dict(r, project_id=project_id) for r in rows]

    def count_by_project_type(self, project_id: str) -> dict[str, int]:
        rows = self.db.execute(
            text(
                "SELECT asset_type, COUNT(*) AS count FROM project_assets "
                "WHERE project_id = :project_id GROUP BY asset_type"
            ),
            {"project_id": project_id},
        ).mappings().all()
        return {str(r["asset_type"]): int(r["count"] or 0) for r in rows}

    def asset_set_count(self, project_id: str) -> int:
        rows = self.db.execute(
            text(
                "SELECT metadata_json FROM project_assets "
                "WHERE project_id = :project_id"
            ),
            {"project_id": project_id},
        ).mappings().all()
        names: set[str] = set()
        for row in rows:
            metadata = self._metadata_dict(row.get("metadata_json"))
            name = str(metadata.get("asset_set") or metadata.get("group_label") or "").strip()
            if name:
                names.add(name)
        return len(names)

    def get_by_id(self, asset_id: str) -> Optional[dict]:
        row = self.db.execute(
            text("SELECT * FROM project_assets WHERE id = :id"), {"id": asset_id}
        ).mappings().first()
        return self._to_dict(row) if row else None

    def create(self, data: dict) -> dict:
        sql = text(
            """INSERT INTO project_assets
               (id, project_id, asset_type, original_name, storage_path,
                mime_type, size, metadata_json, uploaded_at)
               VALUES
               (:id, :project_id, :asset_type, :original_name, :storage_path,
                :mime_type, :size, :metadata_json, :uploaded_at)"""
        )
        self.db.execute(sql, data)
        self.db.commit()
        return self._to_dict(data)

    def update_metadata(self, asset_id: str, metadata: dict) -> Optional[dict]:
        self.db.execute(
            text(
                "UPDATE project_assets SET metadata_json = :metadata_json "
                "WHERE id = :id"
            ),
            {"id": asset_id, "metadata_json": json.dumps(metadata, ensure_ascii=False)},
        )
        self.db.commit()
        return self.get_by_id(asset_id)

    def delete(self, asset_id: str) -> bool:
        result = self.db.execute(
            text("DELETE FROM project_assets WHERE id = :id"), {"id": asset_id}
        )
        self.db.commit()
        return result.rowcount > 0

    def find_by_project_and_type(
        self,
        project_id: str,
        asset_type: str = "processed_result",
        analysis_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Find processed-result assets (used by job results aggregation)."""
        conditions = ["project_id = :project_id", "asset_type = :asset_type"]
        params: dict = {"project_id": project_id, "asset_type": asset_type}

        if analysis_type:
            conditions.append(
                "JSON_EXTRACT(metadata_json, '$.analysis_type') = :analysis_type"
            )
            params["analysis_type"] = analysis_type

        sql = (
            f"SELECT * FROM project_assets"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY uploaded_at DESC LIMIT :limit"
        )
        params["limit"] = limit
        rows = self.db.execute(text(sql), params).mappings().all()
        return [self._to_dict(r, project_id=project_id) for r in rows]
