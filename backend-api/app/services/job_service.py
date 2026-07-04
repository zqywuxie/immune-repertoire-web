"""JobService — thin orchestration over JobRepository."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..repositories.assets import AssetRepository
from ..repositories.jobs import JobRepository

# Fallback module allowlist (used when manifest YAML is unavailable).
_FALLBACK_MODULES = {
    "charts.combined", "treemap.generate", "chord.generate",
    "analysis.execute", "analysis.batch", "analysis.execute-unified",
    "statistical.analyze", "statistical.boxplot", "statistical.analyze-multiple",
    "statistical.summary-boxplot", "statistical.analyze-batch", "statistical.analyze-direct",
    "auto-heatmap.generate-heatmap", "auto-heatmap.generate-pipeline-report",
    "auto-heatmap.generate-heatmap-report", "auto-heatmap.export-shared-cdr3",
    "ppt.scan-images", "ppt.load-image", "ppt.render-slides",
    "ppt-comparison.scan-heatmaps", "ppt-comparison.generate",
}

_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted"}


def _is_valid_module(module: str) -> bool:
    """Check module validity — manifest first, fallback set second."""
    try:
        from .module_registry import get_module_registry
        registry = get_module_registry()
        if registry.modules:  # only trust the manifest if it loaded modules
            return registry.validate_module(module)
    except Exception:
        pass
    return module in _FALLBACK_MODULES


class JobService:
    """Business logic for job submission, status, and lifecycle."""

    def __init__(self, db: Session) -> None:
        self.repo = JobRepository(db)

    # ── validation ────────────────────────────────────────────────────

    def validate_module(self, module: str) -> None:
        if not _is_valid_module(module):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported job module: {module}",
            )

    @staticmethod
    def is_terminal(status: str) -> bool:
        return status in _TERMINAL_STATUSES

    # ── CRUD ───────────────────────────────────────────────────────────

    def list_jobs(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        return self.repo.list_all(
            project_id=project_id, status=status, module=module, limit=limit
        )

    def get_job(self, job_id: str) -> Optional[dict]:
        return self.repo.get_by_id(job_id)

    def get_job_or_404(self, job_id: str) -> dict:
        job = self.repo.get_by_id(job_id)
        if job is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    def submit_job(self, data: dict) -> dict:
        self.validate_module(data["module"])
        return self.repo.create(data)

    def cancel_job(self, job_id: str) -> dict:
        job = self.get_job_or_404(job_id)
        self.repo.set_cancel_requested(job_id)
        return job

    def delete_job(self, job_id: str) -> dict:
        job = self.get_job_or_404(job_id)
        if not self.is_terminal(job["status"]):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail="Running or queued jobs must be cancelled before deletion.",
            )
        summary = self.delete_job_with_results(job_id, delete_results=False)
        return summary["deleted_job"]

    def delete_job_with_results(self, job_id: str, delete_results: bool = False) -> dict:
        job = self.get_job_or_404(job_id)
        if not self.is_terminal(job["status"]):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail="Running or queued jobs must be cancelled before deletion.",
            )

        summary = {
            "deleted_job": None,
            "deleted_children": 0,
            "deleted_assets": [],
            "deleted_paths": [],
            "skipped_paths": [],
            "errors": [],
        }
        child_jobs = self._child_jobs(job_id) if not job.get("parent_job_id") else []
        for child in child_jobs:
            if delete_results:
                cleanup = self._cleanup_job_results(child)
                self._extend_cleanup(summary, cleanup)
            if self.repo.delete(child["id"]):
                summary["deleted_children"] += 1

        if delete_results:
            cleanup = self._cleanup_job_results(job)
            self._extend_cleanup(summary, cleanup)

        self.repo.delete(job_id)
        summary["deleted_job"] = job
        return summary

    def bulk_delete_jobs(self, job_ids: list[str], delete_results: bool = False) -> list[dict]:
        results = []
        for job_id in job_ids:
            clean_id = str(job_id or "").strip()
            if not clean_id:
                continue
            try:
                summary = self.delete_job_with_results(clean_id, delete_results=delete_results)
                results.append({"job_id": clean_id, "success": True, **summary})
            except Exception as exc:
                results.append({"job_id": clean_id, "success": False, "error": str(exc)})
        return results

    @staticmethod
    def _extend_cleanup(summary: dict, cleanup: dict) -> None:
        for key in ("deleted_assets", "deleted_paths", "skipped_paths", "errors"):
            summary[key].extend(cleanup.get(key, []))

    def _child_jobs(self, parent_job_id: str) -> list[dict]:
        jobs = self.repo.list_all(limit=500)
        return [
            job for job in jobs
            if str((job.get("payload") or {}).get("parent_job_id") or "") == parent_job_id
        ]

    def _cleanup_job_results(self, job: dict) -> dict:
        job_id = str(job.get("job_id") or job.get("id") or "")
        assets = self._job_result_assets(job)
        paths = set(self._collect_result_paths(job.get("result") or {}))
        for asset in assets:
            if asset.get("storage_path"):
                paths.add(str(asset["storage_path"]))
            metadata = asset.get("metadata") or {}
            for key in ("output_base", "report_path", "metadata_path", "zip_path"):
                if metadata.get(key):
                    paths.add(str(metadata[key]))

        deleted_paths: list[str] = []
        skipped_paths: list[str] = []
        errors: list[str] = []
        roots = self._allowed_delete_roots()
        for raw_path in sorted(paths, key=len, reverse=True):
            path = Path(raw_path)
            if not path.exists() or not self._path_under_roots(path, roots):
                skipped_paths.append(raw_path)
                continue
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
                deleted_paths.append(str(path))
            except OSError as exc:
                errors.append(f"{path}: {exc}")

        deleted_assets = []
        if job_id:
            try:
                self.repo.db.execute(text("DELETE FROM job_assets WHERE job_id = :job_id"), {"job_id": job_id})
                self.repo.db.commit()
            except Exception:
                self.repo.db.rollback()
        for asset in assets:
            asset_id = str(asset.get("id") or "")
            if asset_id:
                self.repo.db.execute(text("DELETE FROM project_assets WHERE id = :id"), {"id": asset_id})
                deleted_assets.append(asset_id)
        self.repo.db.commit()

        return {
            "deleted_assets": deleted_assets,
            "deleted_paths": deleted_paths,
            "skipped_paths": skipped_paths,
            "errors": errors,
        }

    def _job_result_assets(self, job: dict) -> list[dict]:
        project_id = str(job.get("project_id") or "")
        job_id = str(job.get("job_id") or job.get("id") or "")
        if not project_id or not job_id:
            return []
        rows = self.repo.db.execute(
            text(
                "SELECT * FROM project_assets WHERE project_id = :project_id "
                "AND asset_type = 'processed_result'"
            ),
            {"project_id": project_id},
        ).mappings().all()
        assets = []
        for row in rows:
            asset = AssetRepository._to_dict(row, project_id=project_id)
            meta = asset.get("metadata") or {}
            if str(meta.get("job_id") or "") == job_id or str(meta.get("task_id") or "") == job_id:
                assets.append(asset)
        return assets

    @staticmethod
    def _collect_result_paths(value) -> list[str]:
        paths: list[str] = []
        path_keys = {"output_base", "report_path", "metadata_path", "zip_path", "viewer_path", "file_path", "path"}

        def walk(item, key_hint: str = "") -> None:
            if isinstance(item, dict):
                for key, child in item.items():
                    walk(child, str(key))
                return
            if isinstance(item, list):
                for child in item:
                    walk(child, key_hint)
                return
            if key_hint not in path_keys:
                return
            raw = str(item or "").strip()
            if raw and not raw.startswith(("http://", "https://", "/api/")):
                paths.append(raw)

        walk(value)
        return paths

    @staticmethod
    def _allowed_delete_roots() -> list[Path]:
        root = Path(__file__).resolve().parents[3]
        return [
            (root / "flask_app" / "data" / "results").resolve(),
            (root / "data" / "results").resolve(),
            (root / "flask_app" / "data" / "projects").resolve(),
        ]

    @staticmethod
    def _path_under_roots(path: Path, roots: list[Path]) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        for root in roots:
            try:
                resolved.relative_to(root)
                return resolved != root
            except ValueError:
                continue
        return False
