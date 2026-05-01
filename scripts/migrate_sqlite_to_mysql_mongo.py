"""
Migrate data from SQLite to MySQL + MongoDB.

Usage:
    python scripts/migrate_sqlite_to_mysql_mongo.py [--sqlite-path PATH] [--dry-run]

Requires MySQL and MongoDB to be running (e.g., via docker-compose up -d).
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def connect_sqlite(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_sqlite_tables(conn: sqlite3.Connection) -> list:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row[0] for row in cursor.fetchall()]


def migrate_to_mysql(conn: sqlite3.Connection, dry_run: bool = False):
    """Migrate relational tables from SQLite to MySQL via SQLAlchemy."""
    from flask_app import create_app
    from flask_app.models.database import db, Project, ProjectAsset, SampleRecord, ProjectGroupSpec

    app = create_app()
    with app.app_context():
        db.create_all()

        tables = get_sqlite_tables(conn)
        print(f"SQLite tables found: {tables}")

        # ── Projects ──
        if 'projects' in tables:
            rows = conn.execute("SELECT * FROM projects").fetchall()
            print(f"Migrating {len(rows)} projects...")
            for row in rows:
                row_dict = dict(row)
                existing = Project.query.get(row_dict.get('id'))
                if not existing:
                    p = Project(
                        id=row_dict.get('id'),
                        name=row_dict.get('name', ''),
                        institution=row_dict.get('institution', ''),
                        cooperation_level=row_dict.get('cooperation_level', ''),
                        description=row_dict.get('description', ''),
                        status=row_dict.get('status', 'active'),
                    )
                    db.session.add(p)
            if not dry_run:
                db.session.commit()
            print(f"  Projects: {len(rows)} rows migrated")

        # ── Project Assets ──
        if 'project_assets' in tables:
            rows = conn.execute("SELECT * FROM project_assets").fetchall()
            print(f"Migrating {len(rows)} project_assets...")
            for row in rows:
                row_dict = dict(row)
                existing = ProjectAsset.query.get(row_dict.get('id'))
                if not existing:
                    a = ProjectAsset(
                        id=row_dict.get('id'),
                        project_id=row_dict.get('project_id', ''),
                        asset_type=row_dict.get('asset_type', ''),
                        original_name=row_dict.get('original_name', ''),
                        storage_path=row_dict.get('storage_path', ''),
                        mime_type=row_dict.get('mime_type', ''),
                        size=row_dict.get('size', 0),
                        metadata_json=json.loads(row_dict.get('metadata_json', '{}')) if isinstance(row_dict.get('metadata_json'), str) else (row_dict.get('metadata_json') or {}),
                    )
                    db.session.add(a)
            if not dry_run:
                db.session.commit()
            print(f"  ProjectAssets: {len(rows)} rows migrated")

        # ── Sample Records ──
        if 'sample_records' in tables:
            rows = conn.execute("SELECT * FROM sample_records").fetchall()
            print(f"Migrating {len(rows)} sample_records...")
            for row in rows:
                row_dict = dict(row)
                existing = SampleRecord.query.get(row_dict.get('id'))
                if not existing:
                    s = SampleRecord(
                        id=row_dict.get('id'),
                        project_id=row_dict.get('project_id', ''),
                        sample_id=row_dict.get('sample_id', ''),
                        sample_name=row_dict.get('sample_name', ''),
                        species=row_dict.get('species', ''),
                        chain=row_dict.get('chain', ''),
                        illness=row_dict.get('illness', ''),
                        is_healthy=row_dict.get('is_healthy'),
                        institution=row_dict.get('institution', ''),
                    )
                    db.session.add(s)
            if not dry_run:
                db.session.commit()
            print(f"  SampleRecords: {len(rows)} rows migrated")

        # ── Group Specs ──
        if 'project_group_specs' in tables:
            rows = conn.execute("SELECT * FROM project_group_specs").fetchall()
            print(f"Migrating {len(rows)} group_specs...")
            for row in rows:
                row_dict = dict(row)
                existing = ProjectGroupSpec.query.get(row_dict.get('id'))
                if not existing:
                    g = ProjectGroupSpec(
                        id=row_dict.get('id'),
                        project_id=row_dict.get('project_id', ''),
                        name=row_dict.get('name', 'default'),
                        spec_json=json.loads(row_dict.get('spec_json', '{}')) if isinstance(row_dict.get('spec_json'), str) else (row_dict.get('spec_json') or {}),
                    )
                    db.session.add(g)
            if not dry_run:
                db.session.commit()
            print(f"  GroupSpecs: {len(rows)} rows migrated")


def migrate_to_mongo(conn: sqlite3.Connection, dry_run: bool = False):
    """Migrate file and asset data from SQLite to MongoDB."""
    from flask_app.services.mongo_service import (
        save_rawdata_asset, save_result, save_cached_usage, ping
    )

    if not ping():
        print("WARNING: MongoDB is not reachable. Skipping MongoDB migration.")
        return

    tables = get_sqlite_tables(conn)

    # ── Files → rawdata ──
    if 'files' in tables:
        rows = conn.execute("SELECT * FROM files").fetchall()
        print(f"Migrating {len(rows)} files to MongoDB rawdata...")
        for row in rows:
            row_dict = dict(row)
            try:
                save_rawdata_asset(
                    project_id=row_dict.get('project', 'default'),
                    asset_type='uploaded_file',
                    original_name=row_dict.get('original_name', ''),
                    storage_path=row_dict.get('storage_path', ''),
                    size=row_dict.get('size', 0),
                    mime_type=row_dict.get('mime_type', ''),
                    columns=json.loads(row_dict.get('columns', '[]')) if isinstance(row_dict.get('columns'), str) else (row_dict.get('columns') or []),
                )
            except Exception as exc:
                print(f"  Skipping file {row_dict.get('id')}: {exc}")
        print(f"  Files: {len(rows)} rows migrated to rawdata")

    # ── Project Assets (raw types) → rawdata ──
    raw_asset_types = {'pep', 'datapoint', 'raw_archive', 'sample_summary'}
    if 'project_assets' in tables:
        rows = conn.execute(
            "SELECT * FROM project_assets WHERE asset_type IN ('pep', 'datapoint', 'raw_archive', 'sample_summary')"
        ).fetchall()
        print(f"Migrating {len(rows)} raw project_assets to MongoDB...")
        for row in rows:
            row_dict = dict(row)
            try:
                meta = row_dict.get('metadata_json')
                if isinstance(meta, str):
                    meta = json.loads(meta) if meta else {}
                save_rawdata_asset(
                    project_id=row_dict.get('project_id', ''),
                    asset_type=row_dict.get('asset_type', ''),
                    original_name=row_dict.get('original_name', ''),
                    storage_path=row_dict.get('storage_path', ''),
                    size=row_dict.get('size', 0),
                    mime_type=row_dict.get('mime_type', ''),
                    metadata_json=meta or {},
                )
            except Exception as exc:
                print(f"  Skipping asset {row_dict.get('id')}: {exc}")
        print(f"  Assets: {len(rows)} rows migrated to rawdata")


def main():
    parser = argparse.ArgumentParser(description='Migrate SQLite to MySQL + MongoDB')
    parser.add_argument('--sqlite-path', default=None,
                        help='Path to SQLite database (default: flask_app/data/immune_repertoire.db)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview migrations without writing')
    args = parser.parse_args()

    sqlite_path = args.sqlite_path
    if not sqlite_path:
        sqlite_path = Path(__file__).resolve().parent.parent / 'flask_app' / 'data' / 'immune_repertoire.db'

    if not os.path.exists(sqlite_path):
        print(f"ERROR: SQLite database not found at {sqlite_path}")
        sys.exit(1)

    print(f"Source SQLite: {sqlite_path}")
    print(f"Dry run: {args.dry_run}")
    print()

    conn = connect_sqlite(str(sqlite_path))
    try:
        migrate_to_mysql(conn, dry_run=args.dry_run)
        print()
        migrate_to_mongo(conn, dry_run=args.dry_run)
        print()
        print("Migration complete.")
        if args.dry_run:
            print("(Dry run — no data was written)")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
