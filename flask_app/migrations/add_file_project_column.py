"""
Database migration script to add project column to the files table.

This migration adds the following field:
- project: Project/folder name for file organization (default: 'default')
"""

import sqlite3
import sys
from pathlib import Path


def migrate_database(db_path: str):
    """
    Add project column to the files table.
    
    Args:
        db_path: Path to the SQLite database file
    """
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(files)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add project column if it doesn't exist
        if 'project' not in columns:
            print("Adding 'project' column to files table...")
            cursor.execute("""
                ALTER TABLE files 
                ADD COLUMN project VARCHAR(255) DEFAULT 'default'
            """)
            print("✓ Added 'project' column")
            
            # Update existing records to have default project
            cursor.execute("""
                UPDATE files SET project = 'default' WHERE project IS NULL
            """)
            print("✓ Updated existing records with default project")
        else:
            print("✓ 'project' column already exists")
        
        # Commit changes
        conn.commit()
        print("\n✓ Migration completed successfully!")
        
        # Show updated schema
        cursor.execute("PRAGMA table_info(files)")
        columns = cursor.fetchall()
        print("\nUpdated files table schema:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
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
    print("File Project Column Migration")
    print("=" * 60)
    
    # Run migration
    migrate_database(db_path)
    
    print("\n" + "=" * 60)
    print("Migration complete!")
    print("=" * 60)
