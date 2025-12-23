"""
Database initialization script for the Immune Repertoire Analysis Web Application.
Run this script to create all database tables.

Usage: python init_db.py
"""
import os
import sys

# Add the flask_app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models.database import db


def init_database():
    """Initialize the database with all tables."""
    app = create_app()
    
    with app.app_context():
        # Create all tables
        db.create_all()
        print("Database tables created successfully!")
        
        # Print table names
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"Created tables: {', '.join(tables)}")


if __name__ == '__main__':
    init_database()
