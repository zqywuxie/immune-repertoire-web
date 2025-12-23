"""
Tests for the Flask application core functionality.
Requirements: 13.1, 13.2, 13.3, 13.4
"""
import pytest


class TestAppCreation:
    """Tests for application creation and startup."""
    
    def test_app_creates_successfully(self, app):
        """Test that the application creates successfully."""
        assert app is not None
        assert app.config['TESTING'] is True
    
    def test_app_has_required_config(self, app):
        """Test that required configuration is present."""
        assert 'APP_NAME' in app.config
        assert 'APP_VERSION' in app.config
        assert 'SQLALCHEMY_DATABASE_URI' in app.config
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get('/api/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
    
    def test_info_endpoint(self, client):
        """Test application info endpoint."""
        response = client.get('/api/info')
        assert response.status_code == 200
        data = response.get_json()
        assert 'name' in data
        assert 'version' in data
        assert data['status'] == 'running'


class TestErrorHandlers:
    """Tests for error handling. Requirements: 1.3, 13.4"""
    
    def test_404_error(self, client):
        """Test 404 error handler."""
        response = client.get('/api/nonexistent')
        assert response.status_code == 404
        data = response.get_json()
        assert 'error_code' in data
        assert data['error_code'] == 'NOT_FOUND'
