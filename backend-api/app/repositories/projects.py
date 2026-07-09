"""ProjectRepository — parameterised SQL for projects table."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class ProjectRepository:
    """Data access for ``projects`` table.

    Every method uses ``text()`` with named bind parameters — no
    f-string concatenation, no positional column-index access.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_all(
        self,
        name: Optional[str] = None,
        institution: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict]:
        conditions = ["1=1"]
        params: dict = {}

        if name:
            conditions.append("name LIKE :name")
            params["name"] = f"%{name}%"
        if institution:
            conditions.append("institution LIKE :inst")
            params["inst"] = f"%{institution}%"

        sql = (
            "SELECT * FROM projects"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY created_at DESC LIMIT :limit"
        )
        params["limit"] = limit
        rows = self.db.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]

    def get_by_id(self, project_id: str) -> Optional[dict]:
        row = self.db.execute(
            text("SELECT * FROM projects WHERE id = :id"), {"id": project_id}
        ).mappings().first()
        return dict(row) if row else None

    def create(self, data: dict) -> dict:
        """Insert a new project row. *data* must include all NOT NULL columns."""
        sql = text(
            """INSERT INTO projects
               (id, name, user_id, institution, cooperation_level,
                description, status, created_at, updated_at)
               VALUES
               (:id, :name, :user_id, :institution, :cooperation_level,
                :description, :status, :created_at, :updated_at)"""
        )
        self.db.execute(sql, data)
        self.db.commit()
        return self.get_by_id(data["id"])  # type: ignore[return-value]

    def update(self, project_id: str, updates: dict) -> Optional[dict]:
        """Apply a partial update. *updates* keys must match column names."""
        if not updates:
            return self.get_by_id(project_id)

        updates["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        sql = text(f"UPDATE projects SET {set_clause} WHERE id = :project_id")
        self.db.execute(sql, {**updates, "project_id": project_id})
        self.db.commit()
        return self.get_by_id(project_id)
