"""
Basic tests for the refactored analyzer classes.
Tests the BaseAnalyzer interface and basic functionality of each analyzer.
"""

import pytest
import pandas as pd
import numpy as np
from services.analyzers import (
    BaseAnalyzer,
    ValidationResult,
    BCellIsotypeAnalyzer,
    SHMAnalyzer,
    IGMetricsAnalyzer,
    CustomFieldAnalyzer
)


class TestBaseAnalyzer:
    """Tests for BaseAnalyzer abstract class"""
    
    def test_cannot_instantiate_base_analyzer(self):
        """BaseAnalyzer is abstract and cannot be instantiated"""
        with pytest.raises(TypeError):
            BaseAnalyzer()
    
    def test_validation_result_creation(self):
        """ValidationResult can be created with errors and warnings"""
        result = ValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"]
        )
        
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1


class TestBCellIsotypeAnalyzer:
    """Tests for BCellIsotypeAnalyzer"""
    
    def test_analyzer_initialization(self):
        """BCellIsotypeAnalyzer can be initialized"""
        analyzer = BCellIsotypeAnalyzer()
        assert analyzer is not None
        assert isinstance(analyzer, BaseAnalyzer)
    
    def test_get_required_fields(self):
        """BCellIsotypeAnalyzer returns required fields"""
        analyzer = BCellIsotypeAnalyzer()
        required = analyzer.get_required_fields()
        
        assert isinstance(required, list)
        assert "Sample" in required
    
    def test_get_default_parameters(self):
        """BCellIsotypeAnalyzer returns default parameters"""
        analyzer = BCellIsotypeAnalyzer()
        params = analyzer.get_default_parameters()
        
        assert isinstance(params, dict)
        assert "sample_column" in params
        assert "baseline_sample" in params
    
    def test_validate_empty_data(self):
        """BCellIsotypeAnalyzer rejects empty data"""
        analyzer = BCellIsotypeAnalyzer()
        empty_df = pd.DataFrame()
        
        result = analyzer.validate_data(empty_df)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
    
    def test_validate_valid_data(self):
        """BCellIsotypeAnalyzer accepts valid data"""
        analyzer = BCellIsotypeAnalyzer()
        
        # Create sample data with isotype columns
        data = pd.DataFrame({
            'Sample': ['S1', 'S2'],
            'IgM_Expression': [10.5, 12.3],
            'IgM_Unique_CDR3': [8.2, 9.1],
            'IgG_Expression': [15.0, 14.5]
        })
        
        result = analyzer.validate_data(data)
        
        assert result.is_valid is True
    
    def test_analyze_basic(self):
        """BCellIsotypeAnalyzer can perform basic analysis"""
        analyzer = BCellIsotypeAnalyzer()
        
        # Create sample data
        data = pd.DataFrame({
            'Sample': ['S1', 'S2', 'S3'],
            'IgM_Expression': [10.5, 12.3, 11.0],
            'IgM_Unique_CDR3': [8.2, 9.1, 8.5],
            'IgG1/2_Expression': [15.0, 14.5, 16.0]
        })
        
        params = {
            'sample_column': 'Sample'
        }
        
        result = analyzer.analyze(data, params)
        
        assert isinstance(result, dict)
        assert 'samples' in result
        assert 'isotype_data' in result
        assert len(result['samples']) == 3


class TestSHMAnalyzer:
    """Tests for SHMAnalyzer"""
    
    def test_analyzer_initialization(self):
        """SHMAnalyzer can be initialized"""
        analyzer = SHMAnalyzer()
        assert analyzer is not None
        assert isinstance(analyzer, BaseAnalyzer)
    
    def test_get_required_fields(self):
        """SHMAnalyzer returns required fields"""
        analyzer = SHMAnalyzer()
        required = analyzer.get_required_fields()
        
        assert isinstance(required, list)
        assert "Sample" in required
        assert "IGHA_SHM0" in required
        assert "IGHA_SHM1" in required
    
    def test_validate_empty_data(self):
        """SHMAnalyzer rejects empty data"""
        analyzer = SHMAnalyzer()
        empty_df = pd.DataFrame()
        
        result = analyzer.validate_data(empty_df)
        
        assert result.is_valid is False


class TestIGMetricsAnalyzer:
    """Tests for IGMetricsAnalyzer"""
    
    def test_analyzer_initialization(self):
        """IGMetricsAnalyzer can be initialized"""
        analyzer = IGMetricsAnalyzer()
        assert analyzer is not None
        assert isinstance(analyzer, BaseAnalyzer)
    
    def test_get_required_fields(self):
        """IGMetricsAnalyzer returns required fields"""
        analyzer = IGMetricsAnalyzer()
        required = analyzer.get_required_fields()
        
        assert isinstance(required, list)
        assert "Sample" in required
    
    def test_get_default_parameters(self):
        """IGMetricsAnalyzer returns default parameters"""
        analyzer = IGMetricsAnalyzer()
        params = analyzer.get_default_parameters()
        
        assert isinstance(params, dict)
        assert "chains" in params
        assert "metrics" in params
        assert params["chains"] == ["IGH", "IGK", "IGL"]
    
    def test_validate_valid_data(self):
        """IGMetricsAnalyzer accepts valid data"""
        analyzer = IGMetricsAnalyzer()
        
        # Create sample data with IG metrics
        data = pd.DataFrame({
            'Sample': ['S1', 'S2'],
            'IGH_Reads': [1000, 1200],
            'IGH_UCDR3': [500, 600],
            'IGK_Reads': [800, 900]
        })
        
        result = analyzer.validate_data(data)
        
        assert result.is_valid is True


class TestCustomFieldAnalyzer:
    """Tests for CustomFieldAnalyzer"""
    
    def test_analyzer_initialization(self):
        """CustomFieldAnalyzer can be initialized"""
        analyzer = CustomFieldAnalyzer()
        assert analyzer is not None
        assert isinstance(analyzer, BaseAnalyzer)
    
    def test_get_required_fields(self):
        """CustomFieldAnalyzer returns required fields"""
        analyzer = CustomFieldAnalyzer()
        required = analyzer.get_required_fields()
        
        assert isinstance(required, list)
        assert "Sample" in required
    
    def test_get_default_parameters(self):
        """CustomFieldAnalyzer returns default parameters"""
        analyzer = CustomFieldAnalyzer()
        params = analyzer.get_default_parameters()
        
        assert isinstance(params, dict)
        assert "fields" in params
        assert "chart_type" in params
        assert params["chart_type"] == "bar"
    
    def test_validate_valid_data(self):
        """CustomFieldAnalyzer accepts valid numeric data"""
        analyzer = CustomFieldAnalyzer()
        
        # Create sample data with numeric fields
        data = pd.DataFrame({
            'Sample': ['S1', 'S2', 'S3'],
            'Field1': [10.5, 12.3, 11.0],
            'Field2': [8.2, 9.1, 8.5],
            'Field3': [15.0, 14.5, 16.0]
        })
        
        result = analyzer.validate_data(data)
        
        assert result.is_valid is True
    
    def test_analyze_requires_fields(self):
        """CustomFieldAnalyzer requires fields parameter"""
        analyzer = CustomFieldAnalyzer()
        
        data = pd.DataFrame({
            'Sample': ['S1', 'S2'],
            'Field1': [10.5, 12.3]
        })
        
        # Should raise error when fields not specified
        with pytest.raises(RuntimeError, match="Custom field analysis failed"):
            analyzer.analyze(data, {})
    
    def test_analyze_with_fields(self):
        """CustomFieldAnalyzer can analyze specified fields"""
        analyzer = CustomFieldAnalyzer()
        
        data = pd.DataFrame({
            'Sample': ['S1', 'S2', 'S3'],
            'Field1': [10.5, 12.3, 11.0],
            'Field2': [8.2, 9.1, 8.5]
        })
        
        params = {
            'fields': ['Field1', 'Field2']
        }
        
        result = analyzer.analyze(data, params)
        
        assert isinstance(result, dict)
        assert 'samples' in result
        assert 'fields' in result
        assert 'field_data' in result
        assert result['fields'] == ['Field1', 'Field2']
        assert len(result['samples']) == 3
    
    def test_get_available_fields(self):
        """CustomFieldAnalyzer can identify available fields"""
        analyzer = CustomFieldAnalyzer()
        
        data = pd.DataFrame({
            'Sample': ['S1', 'S2'],
            'NumericField': [10.5, 12.3],
            'StringField': ['A', 'B']
        })
        
        available = analyzer.get_available_fields(data)
        
        assert isinstance(available, dict)
        assert 'numeric' in available
        assert 'non_numeric' in available
        assert 'all' in available
        assert 'NumericField' in available['numeric']


class TestAnalyzerIntegration:
    """Integration tests for analyzer functionality"""
    
    def test_merge_parameters(self):
        """All analyzers can merge parameters correctly"""
        analyzer = CustomFieldAnalyzer()
        
        user_params = {
            'fields': ['Field1'],
            'chart_type': 'line'
        }
        
        merged = analyzer.merge_parameters(user_params)
        
        # Should have user parameters
        assert merged['fields'] == ['Field1']
        assert merged['chart_type'] == 'line'
        
        # Should have default parameters
        assert 'sample_column' in merged
        assert 'baseline_sample' in merged
    
    def test_analyzer_info(self):
        """All analyzers provide analyzer info"""
        analyzers = [
            BCellIsotypeAnalyzer(),
            SHMAnalyzer(),
            IGMetricsAnalyzer(),
            CustomFieldAnalyzer()
        ]
        
        for analyzer in analyzers:
            info = analyzer.get_analyzer_info()
            
            assert isinstance(info, dict)
            assert 'name' in info
            assert 'required_fields' in info
            assert 'optional_fields' in info
            assert 'default_parameters' in info
