#!/usr/bin/env python
"""Run the storage_uri backfill migration.

Usage:
    # Dry-run preview
    python scripts/run_backfill.py --dry-run --limit 10

    # Actual migration
    python scripts/run_backfill.py

    # Specific project only
    python scripts/run_backfill.py --project-id <id>
"""

import argparse
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root))

from flask_app.app import create_app
from flask_app.models.database import ProjectAsset, db
from flask_app.services.storage_adapter import get_storage_adapter


def main():
    parser = argparse.ArgumentParser(description="Backfill storage_uri in ProjectAsset metadata")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--project-id", type=str, default=None)
    args = parser.parse_args()

    storage = get_storage_adapter()
    app = create_app()

    with app.app_context():
        query = ProjectAsset.query
        if args.project_id:
            query = query.filter(ProjectAsset.project_id == args.project_id)

        total = query.count()
        updated = 0
        skipped = 0
        offset = 0

        while True:
            batch = query.order_by(ProjectAsset.uploaded_at.asc()).offset(offset).limit(500).all()
            if not batch:
                break

            for asset in batch:
                metadata = asset.metadata_json or {}
                if metadata.get("storage_uri"):
                    skipped += 1
                    continue
                if not asset.storage_path:
                    skipped += 1
                    continue

                uri = storage.uri_for_path(Path(asset.storage_path))
                if not args.dry_run:
                    metadata["storage_uri"] = uri
                    asset.metadata_json = metadata

                updated += 1

                if args.limit and updated >= args.limit:
                    break

                if updated % 100 == 0:
                    print(f"  {updated}/{total} updated, {skipped} skipped")

            if not args.dry_run:
                db.session.commit()

            offset += 500
            if args.limit and updated >= args.limit:
                break

        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done: {updated} assets updated, {skipped} skipped (total: {total})")
        if args.dry_run:
            print("Remove --dry-run to apply changes.")


if __name__ == "__main__":
    main()
