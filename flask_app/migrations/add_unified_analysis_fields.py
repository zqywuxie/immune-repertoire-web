"""
Database migration script to add unified analysis fields to the Analysis table.

This migration adds the following fields:
- mode: Analysis mode ('scheme' or 'custom')
- scheme_id: Analysis scheme ID
- scheme_name: Analysis scheme name
- selected_fields: List of selected fields for custom mode

Requirements: 7.6, 10.1
"""

import sqlite3
import sys
from pathlib import Path


def migrate_database(db_path: str):
    """
    Add unified analysis fields to the Analysis table.
    
    Args:
        db_path: Path to the SQLite database file
    """
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(analyses)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add mode column if it doesn't exist
        if 'mode' not in columns:
            print("Adding 'mode' column...")
            cursor.execute("""
                ALTER TABLE analyses 
                ADD COLUMN mode VARCHAR(20)
            """)
            print("✓ Added 'mode' column")
        else:
            print("✓ 'mode' column already exists")
        
        # Add scheme_id column if it doesn't exist
        if 'scheme_id' not in columns:
            print("Adding 'scheme_id' column...")
            cursor.execute("""
                ALTER TABLE analyses 
                ADD COLUMN scheme_id VARCHAR(100)
            """)
            print("✓ Added 'scheme_id' column")
        else:
            print("✓ 'scheme_id' column already exists")
        
        # Add scheme_name column if it doesn't exist
        if 'scheme_name' not in columns:
            print("Adding 'scheme_name' column...")
            cursor.execute("""
                ALTER TABLE analyses 
                ADD COLUMN scheme_name VARCHAR(255)
            """)
            print("✓ Added 'scheme_name' column")
        else:
            print("✓ 'scheme_name' column already exists")
        
        # Add selected_fields column if it doesn't exist
        if 'selected_fields' not in columns:
            print("Adding 'selected_fields' column...")
            cursor.execute("""
                ALTER TABLE analyses 
                ADD COLUMN selected_fields JSON
            """)
            print("✓ Added 'selected_fields' column")
        else:
            print("✓ 'selected_fields' column already exists")
        
        # Commit changes
        conn.commit()
        print("\n✓ Migration completed successfully!")
        
        # Show updated schema
        cursor.execute("PRAGMA table_info(analyses)")
        columns = cursor.fetchall()
        print("\nUpdated Analysis table schema:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        conn.rollback()
        raise
    
    finally:
        conn.close()


def migrate_old_records(db_path: str):
    """
    Migrate old analysis records to populate new fields based on parameters.
    
    This function extracts mode, scheme_id, scheme_name, and selected_fields
    from the parameters JSON field for existing records.
    
    Args:
        db_path: Path to the SQLite database file
    """
    print(f"\nMigrating old records in: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get all analyses with NULL mode (old records)
        cursor.execute("""
            SELECT id, parameters 
            FROM analyses 
            WHERE mode IS NULL
        """)
        
        old_records = cursor.fetchall()
        
        if not old_records:
            print("No old records to migrate")
            return
        
        print(f"Found {len(old_records)} old records to migrate")
        
        import json
        migrated_count = 0
        
        for analysis_id, parameters_json in old_records:
            try:
                parameters = json.loads(parameters_json) if parameters_json else {}
                
                # Extract fields from parameters
                mode = parameters.get('mode')
                scheme_id = parameters.get('scheme_id')
                scheme_name = parameters.get('scheme_name')
                selected_fields_json = json.dumps(parameters.get('selected_fields', []))
                
                # Update the record
                cursor.execute("""
                    UPDATE analyses 
                    SET mode = ?,
                        scheme_id = ?,
                        scheme_name = ?,
                        selected_fields = ?
                    WHERE id = ?
                """, (mode, scheme_id, scheme_name, selected_fields_json, analysis_id))
                
                migrated_count += 1
                
            except Exception as e:
                print(f"  Warning: Failed to migrate record {analysis_id}: {e}")
                continue
        
        conn.commit()
        print(f"✓ Migrated {migrated_count} records")
        
    except Exception as e:
        print(f"✗ Record migration failed: {e}")
        conn.rollback()
        raise
    
    finally:
        conn.close()


if __name__ == '__main__':
    # Default database path
    default_db_path = 'data/immune_repertoire.db'
    
    # Get database path from command line or use default
    db_path = sys.argv[1] if len(sys.argv) > 1 else default_db_path
    
    # Check if database exists
    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("Unified Analysis Fields Migration")
    print("=" * 60)
    
    # Run migration
    migrate_database(db_path)
    
    # Migrate old records
    migrate_old_records(db_path)
    
    print("\n" + "=" * 60)
    print("Migration complete!")
    print("=" * 60)
