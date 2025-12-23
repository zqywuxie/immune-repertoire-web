"""
Tests for the Analysis Service.
Requirements: 8.1, 8.2, 8.3, 8.4
"""
import pytest
import time
from unittest.mock import patch, MagicMock
import pandas as pd

from services.analysis_service import (
    AnalysisService,
    AnalysisStatus,
    AnalysisType,
    AnalysisProgress,
    AnalysisResults,
    AnalysisResultItem
)


class TestAnalysisStatus:
    """Tests for AnalysisStatus enum."""
    
    def test_status_values(self):
        """Test that all expected status values exist."""
        assert AnalysisStatus.PENDING.value == 'pending'
        assert AnalysisStatus.RUNNING.value == 'running'
        assert AnalysisStatus.COMPLETED.value == 'completed'
        assert AnalysisStatus.FAILED.value == 'failed'
        assert AnalysisStatus.CANCELLED.value == 'cancelled'


class TestAnalysisType:
    """Tests for AnalysisType enum."""
    
    def test_type_values(self):
        """Test that all expected analysis types exist."""
        assert AnalysisType.SIMILARITY_HEATMAP.value == 'similarity_heatmap'
        assert AnalysisType.SEQUENCING_DEPTH.value == 'sequencing_depth'
        assert AnalysisType.DIVERSITY_METRICS.value == 'diversity_metrics'
        assert AnalysisType.CHAIN_SPECIFIC.value == 'chain_specific'


class TestAnalysisProgress:
    """Tests for AnalysisProgress dataclass."""
    
    def test_default_values(self):
        """Test default progress values."""
        progress = AnalysisProgress()
        assert progress.progress == 0.0
        assert progress.current_step == ""
        assert progress.total_steps == 0
        assert progress.completed_steps == 0
    
    def test_custom_values(self):
        """Test custom progress values."""
        progress = AnalysisProgress(
            progress=50.0,
            current_step="Processing",
            total_steps=10,
            completed_steps=5
        )
        assert progress.progress == 50.0
        assert progress.current_step == "Processing"
        assert progress.total_steps == 10
        assert progress.completed_steps == 5


class TestAnalysisResultItem:
    """Tests for AnalysisResultItem dataclass."""
    
    def test_required_fields(self):
        """Test creating result item with required fields."""
        item = AnalysisResultItem(
            result_type='visualization',
            name='test_heatmap',
            file_path='/path/to/file.png',
            mime_type='image/png'
        )
        assert item.result_type == 'visualization'
        assert item.name == 'test_heatmap'
        assert item.file_path == '/path/to/file.png'
        assert item.mime_type == 'image/png'
        assert item.table_data is None
        assert item.metadata is None
    
    def test_optional_fields(self):
        """Test creating result item with optional fields."""
        table_data = {'columns': ['A', 'B'], 'data': []}
        metadata = {'title': 'Test'}
        
        item = AnalysisResultItem(
            result_type='data_table',
            name='test_table',
            file_path='/path/to/file.csv',
            mime_type='text/csv',
            table_data=table_data,
            metadata=metadata
        )
        assert item.table_data == table_data
        assert item.metadata == metadata


class TestAnalysisResults:
    """Tests for AnalysisResults dataclass."""
    
    def test_default_values(self):
        """Test default results values."""
        results = AnalysisResults()
        assert results.items == []
        assert results.summary is None
    
    def test_with_items(self):
        """Test results with items."""
        item = AnalysisResultItem(
            result_type='visualization',
            name='test',
            file_path='/path',
            mime_type='image/png'
        )
        results = AnalysisResults(items=[item])
        assert len(results.items) == 1
        assert results.items[0].name == 'test'


class TestAnalysisServiceInit:
    """Tests for AnalysisService initialization."""
    
    def test_init_without_app(self):
        """Test initialization without Flask app."""
        service = AnalysisService()
        assert service.app is None
        assert service.results_folder is None
    
    def test_init_with_results_folder(self):
        """Test initialization with results folder."""
        service = AnalysisService(results_folder='/tmp/results')
        assert service.results_folder == '/tmp/results'


class TestAnalysisServiceWithApp:
    """Tests for AnalysisService with Flask app context."""
    
    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        from app import create_app
        app = create_app('testing')
        return app
    
    @pytest.fixture
    def service(self, app):
        """Create AnalysisService with app."""
        service = AnalysisService()
        service.init_app(app)
        return service
    
    def test_init_app(self, app, service):
        """Test init_app sets up service correctly."""
        assert service.app == app
        assert service.results_folder is not None
    
    def test_create_analysis_invalid_type(self, app, service):
        """Test creating analysis with invalid type raises error."""
        from exceptions import ValidationError
        
        with app.app_context():
            with pytest.raises(ValidationError) as exc_info:
                service.create_analysis(
                    analysis_type='invalid_type',
                    file_id='test-file-id',
                    field_mapping={'sample': 'Sample'}
                )
            assert 'Unsupported analysis type' in str(exc_info.value.message)
    
    def test_create_analysis_file_not_found(self, app, service):
        """Test creating analysis with non-existent file raises error."""
        from exceptions import FileNotFoundError as AppFileNotFoundError
        
        with app.app_context():
            # Use sequencing_depth instead of similarity_heatmap
            # (similarity_heatmap now requires directory_path)
            with pytest.raises(AppFileNotFoundError):
                service.create_analysis(
                    analysis_type='sequencing_depth',
                    file_id='non-existent-file-id',
                    field_mapping={'sample': 'Sample'}
                )
    
    def test_get_analysis_status_not_found(self, app, service):
        """Test getting status of non-existent analysis raises error."""
        from exceptions import AnalysisNotFoundError
        
        with app.app_context():
            with pytest.raises(AnalysisNotFoundError):
                service.get_analysis_status('non-existent-analysis-id')
    
    def test_get_analysis_results_not_found(self, app, service):
        """Test getting results of non-existent analysis raises error."""
        from exceptions import AnalysisNotFoundError
        
        with app.app_context():
            with pytest.raises(AnalysisNotFoundError):
                service.get_analysis_results('non-existent-analysis-id')
    
    def test_get_data_table_not_found(self, app, service):
        """Test getting data table of non-existent analysis raises error."""
        from exceptions import AnalysisNotFoundError
        
        with app.app_context():
            with pytest.raises(AnalysisNotFoundError):
                service.get_data_table('non-existent-analysis-id', 'test_table')
    
    def test_retry_analysis_not_found(self, app, service):
        """Test retrying non-existent analysis raises error."""
        from exceptions import AnalysisNotFoundError
        
        with app.app_context():
            with pytest.raises(AnalysisNotFoundError):
                service.retry_analysis('non-existent-analysis-id')
    
    def test_cancel_analysis_not_found(self, app, service):
        """Test cancelling non-existent analysis raises error."""
        from exceptions import AnalysisNotFoundError
        
        with app.app_context():
            with pytest.raises(AnalysisNotFoundError):
                service.cancel_analysis('non-existent-analysis-id')


class TestProgressMonotonicity:
    """
    Tests for progress monotonicity property.
    **Feature: immune-repertoire-web, Property 14: Progress Monotonicity**
    **Validates: Requirements 8.2**
    """
    
    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        from app import create_app
        app = create_app('testing')
        return app
    
    @pytest.fixture
    def service(self, app):
        """Create AnalysisService with app."""
        service = AnalysisService()
        service.init_app(app)
        return service
    
    def test_progress_never_decreases(self, app, service):
        """
        Test that progress value never decreases.
        **Feature: immune-repertoire-web, Property 14: Progress Monotonicity**
        **Validates: Requirements 8.2**
        """
        analysis_id = 'test-analysis-id'
        
        with app.app_context():
            # Set initial progress
            service.update_progress(analysis_id, 50.0, 'Step 1')
            
            # Try to decrease progress
            service.update_progress(analysis_id, 30.0, 'Step 2')
            
            # Check that progress didn't decrease
            with service._progress_lock:
                cached = service._progress_cache.get(analysis_id)
            
            assert cached is not None
            assert cached.progress >= 50.0  # Progress should not decrease
    
    def test_progress_can_increase(self, app, service):
        """Test that progress can increase normally."""
        analysis_id = 'test-analysis-id-2'
        
        with app.app_context():
            # Set initial progress
            service.update_progress(analysis_id, 25.0, 'Step 1')
            
            # Increase progress
            service.update_progress(analysis_id, 75.0, 'Step 2')
            
            # Check that progress increased
            with service._progress_lock:
                cached = service._progress_cache.get(analysis_id)
            
            assert cached is not None
            assert cached.progress == 75.0


class TestDataFrameToTable:
    """Tests for _dataframe_to_table helper method."""
    
    @pytest.fixture
    def service(self):
        """Create AnalysisService."""
        return AnalysisService()
    
    def test_basic_conversion(self, service):
        """Test basic DataFrame to table conversion."""
        df = pd.DataFrame({
            'A': [1, 2, 3],
            'B': [4.5, 5.5, 6.5]
        }, index=['row1', 'row2', 'row3'])
        
        result = service._dataframe_to_table(df, 'Sample')
        
        assert 'columns' in result
        assert 'data' in result
        assert 'row_count' in result
        assert result['columns'] == ['Sample', 'A', 'B']
        assert result['row_count'] == 3
    
    def test_handles_nan_values(self, service):
        """Test that NaN values are converted to None."""
        import numpy as np
        
        df = pd.DataFrame({
            'A': [1, np.nan, 3],
            'B': [4.5, 5.5, np.nan]
        }, index=['row1', 'row2', 'row3'])
        
        result = service._dataframe_to_table(df, 'Index')
        
        # Check that NaN values are None
        assert result['data'][1]['A'] is None
        assert result['data'][2]['B'] is None
    
    def test_rounds_float_values(self, service):
        """Test that float values are rounded to 4 decimal places."""
        df = pd.DataFrame({
            'A': [1.123456789, 2.987654321]
        }, index=['row1', 'row2'])
        
        result = service._dataframe_to_table(df, 'Index')
        
        assert result['data'][0]['A'] == 1.1235
        assert result['data'][1]['A'] == 2.9877
