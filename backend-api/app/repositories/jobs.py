"""JobRepository — parameterised SQL for analysis_jobs table."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class JobRepository:
    """Data access for ``analysis_jobs`` table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _json_dict(value) -> dict:
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
    def _json_list(value) -> list:
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []

    @staticmethod
    def _to_dict(row) -> dict:
        """Map an analysis_jobs row to a stable dict."""
        try:
            row_id = str(row["id"]) if row.get("id") is not None else ""
            return {
                "id": row_id,
                "job_id": row_id,
                "task_id": row_id,
                "job_type": str(row["job_type"]) if row.get("job_type") else "",
                "module": str(row["module"]) if row.get("module") else "",
                "status": str(row["status"]) if row.get("status") else "queued",
                "progress": float(row["progress"]) if row.get("progress") is not None else 0.0,
                "stage": str(row["stage"]) if row.get("stage") else None,
                "detail": str(row["detail"]) if row.get("detail") else None,
                "payload": JobRepository._json_dict(row.get("payload")),
                "result": JobRepository._json_dict(row.get("result")),
                "history": JobRepository._json_list(row.get("history")),
                "meta": JobRepository._json_dict(row.get("meta")),
                "error": str(row["error"]) if row.get("error") else None,
                "cancel_requested": bool(row.get("cancel_requested")),
                "project_id": str(row["project_id"]) if row.get("project_id") else None,
                "user_id": row.get("user_id"),
                "parent_job_id": str(row["parent_job_id"]) if row.get("parent_job_id") else None,
                "child_label": str(row["child_label"]) if row.get("child_label") else None,
                "hidden_from_default_list": bool(row.get("hidden_from_default_list")),
                "created_at": str(row["created_at"]) if row.get("created_at") else None,
                "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
                "started_at": str(row["started_at"]) if row.get("started_at") else None,
                "completed_at": str(row["completed_at"]) if row.get("completed_at") else None,
            }
        except Exception:
            return {
                "id": "", "job_type": "", "module": "", "status": "queued",
                "progress": 0.0, "payload": {}, "result": {},
            }

    # ── queries ────────────────────────────────────────────────────────

    def list_all(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        conditions = ["1=1"]
        params: dict = {}

        if project_id:
            conditions.append("project_id = :project_id")
            params["project_id"] = project_id
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if module:
            conditions.append("module = :module")
            params["module"] = module

        sql = (
            "SELECT * FROM analysis_jobs"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY created_at DESC LIMIT :limit"
        )
        params["limit"] = limit
        rows = self.db.execute(text(sql), params).mappings().all()
        return [self._to_dict(r) for r in rows]

    def get_by_id(self, job_id: str) -> Optional[dict]:
        row = self.db.execute(
            text("SELECT * FROM analysis_jobs WHERE id = :jid"),
            {"jid": job_id},
        ).mappings().first()
        return self._to_dict(row) if row else None

    def create(self, data: dict) -> dict:
        sql = text(
            """INSERT INTO analysis_jobs
               (id, job_type, module, status, progress, payload, result,
                project_id, user_id, created_at, updated_at)
               VALUES
               (:id, :job_type, :module, :status, :progress, :payload, :result,
                :project_id, :user_id, :created_at, :updated_at)"""
        )
        params = dict(data)
        params["payload"] = json.dumps(params.get("payload") or {}, ensure_ascii=False, default=str)
        params["result"] = json.dumps(params.get("result") or {}, ensure_ascii=False, default=str)
        self.db.execute(sql, params)
        self.db.commit()
        return self._to_dict(data)

    def update_status(
        self,
        job_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        stage: Optional[str] = None,
    ) -> Optional[dict]:
        """Partial update of job status fields."""
        sets = []
        params: dict = {"jid": job_id}
        if status is not None:
            sets.append("status = :status")
            params["status"] = status
        if progress is not None:
            sets.append("progress = :progress")
            params["progress"] = progress
        if stage is not None:
            sets.append("stage = :stage")
            params["stage"] = stage
        if not sets:
            return self.get_by_id(job_id)
        sets.append("updated_at = :updated_at")
        params["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        sql = text(
            "UPDATE analysis_jobs SET "
            + ", ".join(sets)
            + " WHERE id = :jid"
        )
        self.db.execute(sql, params)
        self.db.commit()
        return self.get_by_id(job_id)

    def set_cancel_requested(self, job_id: str) -> None:
        self.db.execute(
            text(
                "UPDATE analysis_jobs SET cancel_requested = 1, "
                "updated_at = :updated_at WHERE id = :jid"
            ),
            {
                "jid": job_id,
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
            },
        )
        self.db.commit()

    def delete(self, job_id: str) -> bool:
        result = self.db.execute(
            text("DELETE FROM analysis_jobs WHERE id = :jid"),
            {"jid": job_id},
        )
        self.db.commit()
        return result.rowcount > 0
