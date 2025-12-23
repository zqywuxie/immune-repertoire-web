"""
Pytest configuration and fixtures for the Immune Repertoire Web Application tests.
"""
import os
import sys
import tempfile
import pytest

# Add the flask_app directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models.database import db


@pytest.fixture
def app():
    """Create application for testing."""
    app = create_app('testing')
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def sample_csv_content():
    """Sample CSV file content for testing."""
    return b"sample,cdr3,reads,copy\nS1,CASSF,100,50\nS1,CASSG,200,100\nS2,CASSF,150,75"


@pytest.fixture
def sample_csv_file(sample_csv_content):
    """Create a temporary CSV file for testing."""
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as f:
        f.write(sample_csv_content)
        return f.name
