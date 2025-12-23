"""
Tests for backward compatibility of old analysis API endpoints.

Requirements: 7.1, 7.2, 7.3
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
import pandas as pd


@pytest.fixture
def app():
    """Create test Flask app."""
    from app import create_app
    app = create_app('testing')
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def mock_file_record():
    """Create mock file record."""
    mock_file = Mock()
    mock_file.id = 'test-file-id'
    mock_file.original_name = 'test.csv'
    mock_file.storage_path = 'data/uploads/test-file-id.csv'
    mock_file.columns = ['Sample_Name', 'Isotype', 'VGene', 'Sequence', 'Mutation_Rate']
    return mock_file


@pytest.fixture
def mock_analysis_result():
    """Create mock analysis result."""
    return {
        'id': 'test-analysis-id',
        'status': 'completed',
        'mode': 'scheme',
        'scheme_id': 'bcell_isotype',
        'scheme_name': 'B细胞同型分析',
        'charts': [
            {
                'name': 'isotype_distribution',
                'type': 'pie',
                'data': {'labels': ['IgG', 'IgM'], 'values': [60, 40]}
            }
        ],
        'tables': [],
        'statistics': {'total_sequences': 100}
    }


class TestBackwardCompatibilityAPI:
    """Test backward compatibility API endpoints."""
    
    def test_bcell_isotype_deprecated_endpoint_exists(self, client):
        """Test that the deprecated B细胞同型分析 endpoint exists."""
        # POST without data should return 400 or 415, but endpoint should exist
        response = client.post('/api/analysis/bcell-isotype')
        assert response.status_code in [400, 415, 500]  # Not 404
    
    def test_shm_deprecated_endpoint_exists(self, client):
        """Test that the deprecated SHM分析 endpoint exists."""
        response = client.post('/api/analysis/shm')
        assert response.status_code in [400, 415, 500]  # Not 404
    
    def test_ig_metrics_deprecated_endpoint_exists(self, client):
        """Test that the deprecated IG指标分析 endpoint exists."""
        response = client.post('/api/analysis/ig-metrics')
        assert response.status_code in [400, 415, 500]  # Not 404
    
    def test_custom_field_deprecated_endpoint_exists(self, client):
        """Test that the deprecated 自定义字段分析 endpoint exists."""
        response = client.post('/api/analysis/custom-field')
        assert response.status_code in [400, 415, 500]  # Not 404
    
    @patch('routes.api.File')
    @patch('routes.api.FileParserService')
    @patch('routes.api.get_unified_analysis_service')
    @patch('routes.api.Path')
    def test_bcell_isotype_calls_unified_service(
        self, mock_path, mock_service_getter, mock_parser, mock_file_model, 
        client, mock_file_record, mock_analysis_result
    ):
        """Test that deprecated bcell-isotype endpoint calls unified service."""
        # Setup mocks
        mock_file_model.query.get.return_value = mock_file_record
        mock_path_instance = Mock()
        mock_path_instance.exists.return_value = True
        mock_path.return_value = mock_path_instance
        
        # Mock file reading
        mock_df = pd.DataFrame({
            'Sample_Name': ['S1', 'S2'],
            'Isotype': ['IgG', 'IgM'],
            'VGene': ['IGHV1-1', 'IGHV2-1']
        })
        mock_parser.parse_file.return_value = (mock_df, list(mock_df.columns), len(mock_df))
        
        # Mock unified service
        mock_service = Mock()
        mock_service.execute_analysis.return_value = mock_analysis_result
        mock_service_getter.return_value = mock_service
        
        # Mock file open
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b'test data'
            
            # Make request
            response = client.post(
                '/api/analysis/bcell-isotype',
                data=json.dumps({
                    'file_id': 'test-file-id',
                    'field_mapping': {'Sample_Name': 'Sample_Name'},
                    'parameters': {}
                }),
                content_type='application/json'
            )
        
        # Verify response
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['analysis_id'] == 'test-analysis-id'
        
        # Verify unified service was called with correct scheme
        mock_service.execute_analysis.assert_called_once()
        call_kwargs = mock_service.execute_analysis.call_args[1]
        assert call_kwargs['mode'] == 'scheme'
        assert call_kwargs['scheme_id'] == 'bcell_isotype'
    
    @patch('routes.api.File')
    @patch('routes.api.FileParserService')
    @patch('routes.api.get_unified_analysis_service')
    @patch('routes.api.Path')
    def test_deprecated_endpoint_returns_deprecation_headers(
        self, mock_path, mock_service_getter, mock_parser, mock_file_model,
        client, mock_file_record, mock_analysis_result
    ):
        """Test that deprecated endpoints return deprecation warning headers."""
        # Setup mocks
        mock_file_model.query.get.return_value = mock_file_record
        mock_path_instance = Mock()
        mock_path_instance.exists.return_value = True
        mock_path.return_value = mock_path_instance
        
        mock_df = pd.DataFrame({'Sample_Name': ['S1'], 'Isotype': ['IgG']})
        mock_parser.parse_file.return_value = (mock_df, list(mock_df.columns), len(mock_df))
        
        mock_service = Mock()
        mock_service.execute_analysis.return_value = mock_analysis_result
        mock_service_getter.return_value = mock_service
        
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = b'test data'
            
            response = client.post(
                '/api/analysis/bcell-isotype',
                data=json.dumps({'file_id': 'test-file-id'}),
                content_type='application/json'
            )
        
        # Check deprecation headers
        assert 'X-API-Deprecated' in response.headers
        assert response.headers['X-API-Deprecated'] == 'true'
        assert 'X-API-Deprecation-Message' in response.headers
        assert 'deprecated' in response.headers['X-API-Deprecation-Message'].lower()
        assert 'X-API-Sunset-Date' in response.headers


class TestURLRedirects:
    """Test URL redirects for old analysis pages."""
    
    def test_field_analysis_redirects_to_unified(self, client):
        """Test that /analysis/field redirects to unified analysis page."""
        response = client.get('/analysis/field', follow_redirects=False)
        assert response.status_code == 302
        assert '/analysis' in response.location
    
    def test_bcell_isotype_redirects_to_unified(self, client):
        """Test that /analysis/bcell-isotype redirects to unified analysis page."""
        response = client.get('/analysis/bcell-isotype', follow_redirects=False)
        assert response.status_code == 302
        assert '/analysis' in response.location
        assert 'scheme=bcell_isotype' in response.location
    
    def test_shm_redirects_to_unified(self, client):
        """Test that /analysis/shm redirects to unified analysis page."""
        response = client.get('/analysis/shm', follow_redirects=False)
        assert response.status_code == 302
        assert '/analysis' in response.location
        assert 'scheme=shm_analysis' in response.location
    
    def test_ig_metrics_redirects_to_unified(self, client):
        """Test that /analysis/ig-metrics redirects to unified analysis page."""
        response = client.get('/analysis/ig-metrics', follow_redirects=False)
        assert response.status_code == 302
        assert '/analysis' in response.location
        assert 'scheme=ig_metrics' in response.location
    
    def test_redirect_preserves_query_parameters(self, client):
        """Test that redirects preserve query parameters."""
        response = client.get(
            '/analysis/bcell-isotype?file_id=test-123&param=value',
            follow_redirects=False
        )
        assert response.status_code == 302
        assert 'file_id=test-123' in response.location
        assert 'param=value' in response.location
        assert 'scheme=bcell_isotype' in response.location


class TestHistoryMigration:
    """Test history record migration."""
    
    def test_analysis_model_has_new_fields(self):
        """Test that Analysis model has new unified analysis fields."""
        from models.database import Analysis
        
        # Check that the model has the new fields
        assert hasattr(Analysis, 'mode')
        assert hasattr(Analysis, 'scheme_id')
        assert hasattr(Analysis, 'scheme_name')
        assert hasattr(Analysis, 'selected_fields')
    
    def test_migrated_records_have_valid_mode(self, app):
        """Test that migrated records have valid mode values."""
        from models.database import Analysis
        
        with app.app_context():
            # Get all analyses
            analyses = Analysis.query.all()
            
            for analysis in analyses:
                # If mode is set, it should be valid
                if analysis.mode is not None:
                    assert analysis.mode in ['scheme', 'custom']
    
    def test_scheme_mode_has_scheme_id(self, app):
        """Test that scheme mode analyses have scheme_id."""
        from models.database import Analysis
        
        with app.app_context():
            # Get scheme mode analyses
            scheme_analyses = Analysis.query.filter_by(mode='scheme').all()
            
            for analysis in scheme_analyses:
                # Scheme mode should have scheme_id
                assert analysis.scheme_id is not None
                assert analysis.scheme_name is not None
    
    def test_custom_mode_has_selected_fields(self, app):
        """Test that custom mode analyses have selected_fields."""
        from models.database import Analysis
        
        with app.app_context():
            # Get custom mode analyses
            custom_analyses = Analysis.query.filter_by(mode='custom').all()
            
            for analysis in custom_analyses:
                # Custom mode should have selected_fields (can be empty list)
                assert analysis.selected_fields is not None
                assert isinstance(analysis.selected_fields, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
