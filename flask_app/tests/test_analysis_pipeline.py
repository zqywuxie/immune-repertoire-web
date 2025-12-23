"""
Tests for Analysis Pipeline
"""
import pytest
import pandas as pd
from unittest.mock import Mock, MagicMock, patch
from services.analysis_pipeline import AnalysisPipeline
from services.analyzers.base_analyzer import BaseAnalyzer, ValidationResult


class MockAnalyzer(BaseAnalyzer):
    """Mock analyzer for testing"""
    
    def analyze(self, data: pd.DataFrame, parameters: dict) -> dict:
        """Mock analyze method"""
        return {
            'samples': list(data['Sample'].unique()) if 'Sample' in data.columns else [],
            'data': {'test': 'data'},
            'statistics': {'count': len(data)},
            'charts': [],
            'tables': []
        }
    
    def get_required_fields(self) -> list:
        """Mock required fields"""
        return ['Sample']
    
    def get_default_parameters(self) -> dict:
        """Mock default parameters"""
        return {'param1': 'value1'}


class TestAnalysisPipeline:
    """Test AnalysisPipeline functionality"""
    
    def test_initialization(self):
        """Test pipeline initialization"""
        pipeline = AnalysisPipeline(save_history=False)
        
        assert pipeline is not None
        assert pipeline.save_history is False
    
    def test_preprocess_data(self):
        """Test data preprocessing"""
        pipeline = AnalysisPipeline(save_history=False)
        
        # Create test data
        data = pd.DataFrame({
            'sample_id': ['S1', 'S2', 'S3'],
            'value1': [10, 20, 30],
            'value2': [100, 200, 300]
        })
        
        # Define field mapping
        field_mapping = {
            'Sample': 'sample_id',
            'Value1': 'value1'
        }
        
        # Preprocess
        processed = pipeline._preprocess_data(data, field_mapping)
        
        # Check results
        assert 'Sample' in processed.columns
        assert 'Value1' in processed.columns
        assert 'value2' not in processed.columns  # Not in mapping
        assert len(processed) == 3
    
    def test_preprocess_data_removes_empty_rows(self):
        """Test that preprocessing removes empty rows"""
        pipeline = AnalysisPipeline(save_history=False)
        
        # Create test data with empty row
        data = pd.DataFrame({
            'sample_id': ['S1', None, 'S3'],
            'value1': [10, None, 30]
        })
        
        field_mapping = {
            'Sample': 'sample_id',
            'Value1': 'value1'
        }
        
        processed = pipeline._preprocess_data(data, field_mapping)
        
        # Empty row should be removed
        assert len(processed) == 2
    
    def test_generate_result(self):
        """Test result generation"""
        pipeline = AnalysisPipeline(save_history=False)
        
        analysis_output = {
            'samples': ['S1', 'S2'],
            'data': {'test': 'data'},
            'statistics': {'count': 2},
            'charts': [{'type': 'bar'}],
            'tables': [{'data': []}]
        }
        
        result = pipeline._generate_result(
            analysis_id='test_id',
            analysis_output=analysis_output,
            parameters={'param1': 'value1'},
            file_id='file_123',
            analysis_type='test_analysis',
            mode='scheme',
            scheme_id='test_scheme',
            scheme_name='Test Scheme',
            selected_fields=None,
            field_mapping={'Sample': 'sample_id'}
        )
        
        # Check result structure
        assert result['id'] == 'test_id'
        assert result['file_id'] == 'file_123'
        assert result['mode'] == 'scheme'
        assert result['scheme_id'] == 'test_scheme'
        assert result['scheme_name'] == 'Test Scheme'
        assert result['status'] == 'completed'
        assert result['samples'] == ['S1', 'S2']
        assert result['statistics'] == {'count': 2}
    
    @patch('services.analysis_pipeline.db')
    def test_execute_success(self, mock_db):
        """Test successful pipeline execution"""
        pipeline = AnalysisPipeline(save_history=False)
        
        # Create test data
        data = pd.DataFrame({
            'Sample': ['S1', 'S2', 'S3'],
            'Value': [10, 20, 30]
        })
        
        # Create mock analyzer
        analyzer = MockAnalyzer()
        
        # Execute pipeline
        result = pipeline.execute(
            analyzer=analyzer,
            data=data,
            field_mapping={'Sample': 'Sample'},
            parameters={'param1': 'value1'},
            file_id='file_123',
            analysis_type='test_analysis',
            mode='scheme',
            scheme_id='test_scheme',
            scheme_name='Test Scheme'
        )
        
        # Check result
        assert result['status'] == 'completed'
        assert 'analysis_id' in result
        assert 'results' in result
        assert result['results']['status'] == 'completed'
    
    @patch('services.analysis_pipeline.db')
    def test_execute_validation_failure(self, mock_db):
        """Test pipeline execution with validation failure"""
        pipeline = AnalysisPipeline(save_history=False)
        
        # Create test data without required field
        data = pd.DataFrame({
            'Value': [10, 20, 30]
        })
        
        # Create mock analyzer
        analyzer = MockAnalyzer()
        
        # Execute pipeline
        result = pipeline.execute(
            analyzer=analyzer,
            data=data,
            field_mapping={'Sample': 'NonExistentColumn'},
            parameters={},
            file_id='file_123',
            analysis_type='test_analysis',
            mode='scheme'
        )
        
        # Should fail validation
        assert result['status'] == 'failed'
        assert 'error_message' in result
    
    def test_validate_before_execution(self):
        """Test validation before execution"""
        pipeline = AnalysisPipeline(save_history=False)
        
        # Create valid data
        data = pd.DataFrame({
            'Sample': ['S1', 'S2', 'S3'],
            'Value': [10, 20, 30]
        })
        
        analyzer = MockAnalyzer()
        field_mapping = {'Sample': 'Sample'}
        
        is_valid, error_msg = pipeline.validate_before_execution(
            analyzer=analyzer,
            data=data,
            field_mapping=field_mapping
        )
        
        assert is_valid is True
        assert error_msg is None
    
    def test_validate_before_execution_invalid(self):
        """Test validation with invalid data"""
        pipeline = AnalysisPipeline(save_history=False)
        
        # Create invalid data (missing required field)
        data = pd.DataFrame({
            'Value': [10, 20, 30]
        })
        
        analyzer = MockAnalyzer()
        field_mapping = {'Sample': 'NonExistent'}
        
        is_valid, error_msg = pipeline.validate_before_execution(
            analyzer=analyzer,
            data=data,
            field_mapping=field_mapping
        )
        
        assert is_valid is False
        assert error_msg is not None
