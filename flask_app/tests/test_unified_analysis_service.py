"""
Tests for Unified Analysis Service
"""
import pytest
import pandas as pd
from services.unified_analysis_service import UnifiedAnalysisService, AnalysisConfig
from services.scheme_manager import SchemeManager


class TestUnifiedAnalysisService:
    """Test UnifiedAnalysisService functionality"""
    
    def test_initialization(self):
        """Test service initialization"""
        service = UnifiedAnalysisService()
        
        assert service is not None
        assert service.scheme_manager is not None
        assert service.field_mapper is not None
    
    def test_get_available_schemes(self):
        """Test getting available schemes"""
        service = UnifiedAnalysisService()
        
        schemes = service.get_available_schemes()
        
        assert isinstance(schemes, list)
        assert len(schemes) > 0
        
        # Check scheme structure
        for scheme in schemes:
            assert 'id' in scheme
            assert 'name' in scheme
            assert 'description' in scheme
            assert 'icon' in scheme
            assert 'category' in scheme
    
    def test_get_scheme_by_id(self):
        """Test getting scheme by ID"""
        service = UnifiedAnalysisService()
        
        # Get a valid scheme
        schemes = service.get_available_schemes()
        if schemes:
            scheme_id = schemes[0]['id']
            
            scheme = service.get_scheme_by_id(scheme_id)
            
            assert scheme is not None
            assert scheme['id'] == scheme_id
            assert 'required_fields' in scheme
            assert 'optional_fields' in scheme
            assert 'default_parameters' in scheme
    
    def test_get_scheme_by_invalid_id(self):
        """Test getting scheme with invalid ID"""
        service = UnifiedAnalysisService()
        
        scheme = service.get_scheme_by_id('invalid_scheme_id')
        
        assert scheme is None
    
    def test_validate_analysis_config_scheme_mode(self):
        """Test validating analysis config in scheme mode"""
        service = UnifiedAnalysisService()
        
        # Get a valid scheme
        schemes = service.get_available_schemes()
        if schemes:
            scheme_id = schemes[0]['id']
            
            # Test with valid config
            result = service.validate_analysis_config(
                mode='scheme',
                scheme_id=scheme_id,
                selected_fields=None,
                file_columns=['Sample', 'IgM_Expression', 'IgD_Expression']
            )
            
            # Should be valid or have warnings about missing fields
            assert isinstance(result.is_valid, bool)
            assert isinstance(result.errors, list)
            assert isinstance(result.warnings, list)
    
    def test_validate_analysis_config_custom_mode(self):
        """Test validating analysis config in custom mode"""
        service = UnifiedAnalysisService()
        
        # Test with valid config
        result = service.validate_analysis_config(
            mode='custom',
            scheme_id=None,
            selected_fields=['Sample', 'Value1', 'Value2'],
            file_columns=['Sample', 'Value1', 'Value2', 'Value3']
        )
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_validate_analysis_config_invalid_mode(self):
        """Test validating analysis config with invalid mode"""
        service = UnifiedAnalysisService()
        
        result = service.validate_analysis_config(
            mode='invalid_mode',
            scheme_id=None,
            selected_fields=None,
            file_columns=[]
        )
        
        assert result.is_valid is False
        assert len(result.errors) > 0
    
    def test_auto_map_fields(self):
        """Test automatic field mapping"""
        service = UnifiedAnalysisService()
        
        # Get a valid scheme
        schemes = service.get_available_schemes()
        if schemes:
            scheme_id = schemes[0]['id']
            
            # Test with matching columns
            file_columns = ['Sample', 'sample_name', 'IgM_Expression', 'IgD_Expression']
            
            field_mapping, missing_fields, confidence_scores = service.auto_map_fields(
                scheme_id, file_columns
            )
            
            assert isinstance(field_mapping, dict)
            assert isinstance(missing_fields, list)
            assert isinstance(confidence_scores, dict)
    
    def test_suggest_scheme(self):
        """Test scheme suggestion based on file columns"""
        service = UnifiedAnalysisService()
        
        # Test with columns that match bcell_isotype scheme
        file_columns = ['Sample', 'IgM_Expression', 'IgD_Expression', 'IgA_Expression']
        
        suggestions = service.suggest_scheme(file_columns, min_confidence=0.3)
        
        assert isinstance(suggestions, list)
        
        # Check suggestion structure
        for suggestion in suggestions:
            assert 'id' in suggestion
            assert 'name' in suggestion
            assert 'confidence' in suggestion
            assert 0.0 <= suggestion['confidence'] <= 1.0


class TestAnalysisConfig:
    """Test AnalysisConfig dataclass"""
    
    def test_analysis_config_creation(self):
        """Test creating AnalysisConfig"""
        config = AnalysisConfig(
            file_id='test_file_id',
            mode='scheme',
            scheme_id='bcell_isotype'
        )
        
        assert config.file_id == 'test_file_id'
        assert config.mode == 'scheme'
        assert config.scheme_id == 'bcell_isotype'
    
    def test_analysis_config_to_dict(self):
        """Test converting AnalysisConfig to dict"""
        config = AnalysisConfig(
            file_id='test_file_id',
            mode='custom',
            selected_fields=['field1', 'field2']
        )
        
        config_dict = config.to_dict()
        
        assert isinstance(config_dict, dict)
        assert config_dict['file_id'] == 'test_file_id'
        assert config_dict['mode'] == 'custom'
        assert config_dict['selected_fields'] == ['field1', 'field2']
