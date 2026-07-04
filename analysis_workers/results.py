"""Standalone worker result registration helper.

Provides a Flask-free way for workers to write job progress, status,
and register output assets in the database.  Uses the same SQLAlchemy
engine configuration as ``backend-api`` so repository patterns are shared.

Standard worker result envelope::

    {
        "outputs": [
            {"label": "Treemap HTML", "url": "/path/to/output.html",
             "kind": "html", "asset_id": None},
        ],
        "metrics": {"duration_seconds": 12.5, "files_generated": 2},
        "summary": "Generated treemap with 150 clones",
    }

Usage inside a worker task::

    from analysis_workers.results import build_envelope, worker_results

    worker_results.set_running(job_id, stage="generating-treemap")
    worker_results.set_progress(job_id, 50.0, stage="processing")

    # ... do work, produce files ...

    envelope = build_envelope(
        outputs=[
            {"label": "Treemap", "url": str(output_path), "kind": "html"},
        ],
        metrics={"duration_seconds": 12.5},
        summary="Generated treemap with 150 clones",
    )
    worker_results.finalize_job(job_id, project_id, envelope)
"""

from __future__ import annotations

import json
import hashlib
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# ── database setup ────────────────────────────────────────────────────
# Reuse API_DATABASE_URL if available; fall back to the common default.
_DATABASE_URL = os.environ.get(
    "API_DATABASE_URL",
    "mysql+pymysql://root:@127.0.0.1:3306/immune_repertoire",
)

_engine = create_engine(
    _DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted"}

# ── standard worker result envelope ───────────────────────────────────


@dataclass
class WorkerOutput:
    """A single output produced by a worker task."""

    label: str
    url: str  # local path initially; replaced with preview URL after registration
    kind: str = "data"  # html, png, csv, zip, ppt, pdf, json, data
    asset_id: Optional[str] = None  # filled after register_output_asset()
    mime_type: Optional[str] = None


@dataclass
class WorkerResultEnvelope:
    """Standardised result envelope returned by every worker.

    This is the canonical shape that the job results API and frontend
    result viewer consume.  Workers populate ``outputs`` and
    ``metrics``; ``summary`` is a human-readable one-liner.
    """

    outputs: List[WorkerOutput] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    raw_result: Dict[str, Any] = field(default_factory=dict)  # legacy compat

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outputs": [
                {
                    "label": o.label,
                    "url": o.url,
                    "kind": o.kind,
                    "asset_id": o.asset_id,
                    "mime_type": o.mime_type,
                }
                for o in self.outputs
            ],
            "metrics": self.metrics,
            "summary": self.summary,
            "raw_result": self.raw_result,
        }


def build_envelope(
    outputs: Optional[List[Dict[str, Any]]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    summary: str = "",
    raw_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience builder for the standard worker result envelope."""
    return {
        "outputs": [
            WorkerOutput(
                label=o.get("label", ""),
                url=o.get("url", ""),
                kind=o.get("kind", "data"),
                asset_id=o.get("asset_id"),
                mime_type=o.get("mime_type"),
            )
            for o in (outputs or [])
        ],
        "metrics": metrics or {},
        "summary": summary,
        "raw_result": raw_result or {},
    }


def kind_from_path(path: str) -> str:
    """Infer the output ``kind`` from a file extension."""
    ext = Path(path).suffix.lower()
    return {
        ".html": "html",
        ".htm": "html",
        ".png": "png",
        ".jpg": "image",
        ".jpeg": "image",
        ".svg": "image",
        ".csv": "csv",
        ".tsv": "csv",
        ".zip": "zip",
        ".pptx": "ppt",
        ".ppt": "ppt",
        ".pdf": "pdf",
        ".json": "json",
        ".xlsx": "data",
    }.get(ext, "data")


# ── worker lifecycle helper ───────────────────────────────────────────


class WorkerResults:
    """Standalone helper for workers to manage job lifecycle and asset registration.

    All methods create their own DB session — no shared session state.
    This keeps each operation atomic and avoids cross-worker session conflicts.
    """

    # ── job lifecycle ─────────────────────────────────────────────────

    def set_status(
        self,
        job_id: str,
        status: str,
        *,
        progress: float = 0.0,
        stage: Optional[str] = None,
        detail: str = "",
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Low-level job status update. Prefer the named helpers below."""
        db = _SessionLocal()
        try:
            job = db.execute(
                text("SELECT * FROM analysis_jobs WHERE id = :jid OR id = :jid2"),
                {"jid": job_id, "jid2": job_id},
            ).mappings().first()

            if job is None:
                return None

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            updates: dict = {}
            set_parts = ["status = :status", "progress = :progress", "updated_at = :updated_at"]
            updates["status"] = status
            updates["progress"] = progress
            updates["updated_at"] = now

            if stage is not None:
                set_parts.append("stage = :stage")
                updates["stage"] = stage
            if detail:
                set_parts.append("detail = :detail")
                updates["detail"] = detail
            if result is not None:
                set_parts.append("result = :result")
                updates["result"] = json.dumps(result, default=str)
            if error is not None:
                set_parts.append("error = :error")
                updates["error"] = error
            if status == "running" and not job.get("started_at"):
                set_parts.append("started_at = :started_at")
                updates["started_at"] = now
            if status in TERMINAL_STATUSES and not job.get("completed_at"):
                set_parts.append("completed_at = :completed_at")
                updates["completed_at"] = now

            updates["jid"] = job_id
            sql = text(f"UPDATE analysis_jobs SET {', '.join(set_parts)} WHERE id = :jid")
            db.execute(sql, updates)
            db.commit()
            return {"id": job_id, "status": status, "progress": progress}
        finally:
            db.close()

    def set_running(self, job_id: str, stage: str = "executing") -> Optional[Dict[str, Any]]:
        """Mark a job as running."""
        return self.set_status(job_id, "running", progress=0.0, stage=stage)

    def set_progress(
        self, job_id: str, progress: float, stage: str = "", detail: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Update job progress and optionally stage/detail."""
        return self.set_status(job_id, "running", progress=progress, stage=stage, detail=detail)

    def set_completed(
        self, job_id: str, result: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Mark a job as completed with a result dict."""
        return self.set_status(
            job_id,
            "completed",
            progress=100.0,
            stage="Completed",
            result=result or {},
        )

    def set_failed(self, job_id: str, error: str) -> Optional[Dict[str, Any]]:
        """Mark a job as failed with an error message."""
        return self.set_status(
            job_id,
            "failed",
            progress=100.0,
            stage="Failed",
            error=error,
        )

    def finalize_job(
        self,
        job_id: str,
        project_id: str,
        envelope: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Complete a job using the standard result envelope.

        Registers every output in the envelope as a ``project_assets`` row,
        fills in ``asset_id`` on each output, then calls ``set_completed``
        with the fully populated envelope.

        Returns the completed job dict, or None if the job is not found.
        """
        outputs = envelope.get("outputs", [])

        for output in outputs:
            if not isinstance(output, WorkerOutput):
                continue
            file_path = output.url
            if not file_path:
                continue

            registered = self.register_output_asset(
                project_id=project_id,
                job_id=job_id,
                file_path=file_path,
                asset_type="processed_result",
                original_name=Path(file_path).name,
                mime_type=output.mime_type,
                metadata={
                    "job_id": job_id,
                    "label": output.label,
                    "kind": output.kind,
                },
            )
            if registered:
                output.asset_id = registered["id"]
                # Replace local path with preview URL
                output.url = f"/api/assets/{registered['id']}/preview"

        envelope_dict = _envelope_to_dict(envelope)
        return self.set_completed(job_id, result=envelope_dict)

    # ── asset registration ────────────────────────────────────────────

    def register_output_asset(
        self,
        project_id: str,
        *,
        job_id: str = "",
        file_path: str = "",
        asset_type: str = "processed_result",
        original_name: Optional[str] = None,
        mime_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Register an output file as a project asset row.

        Returns the created asset dict, or None if ``file_path`` is empty.
        """
        if not file_path or not project_id:
            return None

        db = _SessionLocal()
        try:
            asset_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            path = Path(file_path)
            if not original_name:
                original_name = path.name

            if not mime_type:
                mime_type = self._guess_mime(file_path)

            storage_uri = f"local:///{path.resolve().as_posix()}"
            file_size = path.stat().st_size if path.is_file() else 0

            # Compute checksum for data integrity (SHA-256)
            checksum = ""
            checksum_algo = "sha256"
            if path.is_file():
                try:
                    sha = hashlib.sha256()
                    with open(path, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            sha.update(chunk)
                    checksum = sha.hexdigest()
                except (OSError, PermissionError):
                    pass

            meta = dict(metadata or {})
            meta.setdefault("job_id", job_id)
            meta["storage_uri"] = storage_uri
            meta["checksum"] = checksum
            meta["checksum_algorithm"] = checksum_algo

            db.execute(
                text(
                    """INSERT INTO project_assets
                       (id, project_id, asset_type, original_name, storage_path,
                        mime_type, size, metadata_json, uploaded_at)
                       VALUES
                       (:id, :project_id, :asset_type, :original_name, :storage_path,
                        :mime_type, :size, :metadata_json, :uploaded_at)"""
                ),
                {
                    "id": asset_id,
                    "project_id": project_id,
                    "asset_type": asset_type,
                    "original_name": original_name,
                    "storage_path": str(path),
                    "mime_type": mime_type,
                    "size": file_size,
                    "metadata_json": json.dumps(meta, default=str),
                    "uploaded_at": now,
                },
            )
            db.commit()

            # Register job_assets lineage (D1) — best-effort, table may not exist
            if job_id:
                try:
                    lineage_id = str(uuid.uuid4())
                    db.execute(
                        text(
                            """INSERT INTO job_assets (id, job_id, asset_id, role)
                               VALUES (:id, :job_id, :asset_id, :role)"""
                        ),
                        {"id": lineage_id, "job_id": job_id, "asset_id": asset_id, "role": "output"},
                    )
                    db.commit()
                except Exception:
                    # Table likely doesn't exist yet — non-critical
                    db.rollback()

            return {
                "id": asset_id,
                "project_id": project_id,
                "asset_type": asset_type,
                "original_name": original_name,
                "storage_path": str(path),
                "storage_uri": storage_uri,
                "mime_type": mime_type,
                "size": file_size,
                "checksum": checksum,
                "checksum_algorithm": checksum_algo,
                "metadata": meta,
            }
        finally:
            db.close()

    # ── query helpers ─────────────────────────────────────────────────

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Read a job record by id."""
        db = _SessionLocal()
        try:
            row = db.execute(
                text("SELECT * FROM analysis_jobs WHERE id = :jid"),
                {"jid": job_id},
            ).mappings().first()
            return dict(row) if row else None
        finally:
            db.close()

    # ── internal ──────────────────────────────────────────────────────

    @staticmethod
    def _guess_mime(file_path: str) -> str:
        import mimetypes

        mime, _ = mimetypes.guess_type(file_path)
        return mime or "application/octet-stream"


def _envelope_to_dict(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an envelope (with WorkerOutput objects) to a plain dict."""
    outputs_raw = []
    for o in envelope.get("outputs", []):
        if isinstance(o, WorkerOutput):
            outputs_raw.append({
                "label": o.label,
                "url": o.url,
                "kind": o.kind,
                "asset_id": o.asset_id,
                "mime_type": o.mime_type,
            })
        elif isinstance(o, dict):
            outputs_raw.append(o)
    return {
        "outputs": outputs_raw,
        "metrics": envelope.get("metrics", {}),
        "summary": envelope.get("summary", ""),
        "raw_result": envelope.get("raw_result", {}),
    }


# Module-level convenience instance (no state, safe to share)
worker_results = WorkerResults()
