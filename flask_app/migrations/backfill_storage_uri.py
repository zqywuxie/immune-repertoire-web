"""Batch migration: backfill storage_uri in ProjectAsset metadata_json.

Run from the project root:
    python flask_app/migrations/backfill_storage_uri.py [--dry-run] [--limit N] [--project-id X]

This script reads every ProjectAsset that is missing ``storage_uri`` in
``metadata_json`` and derives one from the existing ``storage_path`` via the
``LocalStorageAdapter``.

Phase 4 of the frontend/backend separation refactor.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure flask_app is on the Python path
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from flask_app import create_app
from flask_app.models.database import ProjectAsset, db
from flask_app.services.storage_adapter import get_storage_adapter


def backfill_storage_uris(
    *,
    dry_run: bool = False,
    limit: int | None = None,
    project_id: str | None = None,
) -> dict:
    """Backfill storage_uri for assets that don't have one yet.

    Returns a summary dict with counts.
    """
    storage = get_storage_adapter()

    query = ProjectAsset.query
    if project_id:
        query = query.filter(ProjectAsset.project_id == project_id)

    total = query.count()
    processed = 0
    updated = 0
    skipped = 0
    errors = 0

    offset = 0
    batch_size = 500

    while True:
        batch = query.order_by(ProjectAsset.uploaded_at.asc()).offset(offset).limit(batch_size).all()
        if not batch:
            break

        for asset in batch:
            processed += 1
            if limit and processed > limit:
                break

            metadata = asset.metadata_json or {}

            # Already has storage_uri — skip
            if metadata.get("storage_uri"):
                skipped += 1
                continue

            # Need storage_path to derive URI
            if not asset.storage_path:
                skipped += 1
                continue

            try:
                derived_uri = storage.uri_for_path(Path(asset.storage_path))
            except Exception:
                errors += 1
                print(f"[WARN ] Failed to derive URI for asset {asset.id} (path={asset.storage_path!r})")
                continue

            if not dry_run:
                metadata["storage_uri"] = derived_uri
                asset.metadata_json = metadata

            updated += 1
            if processed % 100 == 0 or (limit and processed >= (limit or 0)):
                print(f"[INFO ] Scanned {processed}/{total}… updated={updated} skipped={skipped} errors={errors}")

        if not dry_run:
            db.session.commit()

        offset += batch_size
        if limit and processed >= limit:
            break

    if not dry_run and updated:
        db.session.commit()

    return {
        "total": total,
        "processed": processed,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill storage_uri in ProjectAsset metadata")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--limit", type=int, default=None, help="Max assets to process")
    parser.add_argument("--project-id", type=str, default=None, help="Limit to a specific project")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        summary = backfill_storage_uris(
            dry_run=args.dry_run,
            limit=args.limit,
            project_id=args.project_id,
        )
        print(f"\n[DONE ] {summary}")
        if summary["dry_run"]:
            print("[NOTE ] Dry run — no changes were written. Remove --dry-run to apply.")


if __name__ == "__main__":
    main()
