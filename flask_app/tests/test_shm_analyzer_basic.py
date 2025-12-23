"""
Basic tests for SHM Analyzer
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest
from services.analysis.modules.shm_analyzer import SHMAnalyzer


class TestSHMAnalyzerBasic:
    """Basic tests for SHMAnalyzer"""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance"""
        return SHMAnalyzer()
    
    @pytest.fixture
    def sample_data(self):
        """Create sample test data"""
        return pd.DataFrame({
            'Sample': ['Sample1', 'Sample2', 'Sample3'],
            'IGHA_SHM0': [0.1, 0.15, 0.12],
            'IGHA_SHM1': [0.2, 0.25, 0.22],
            'IGHG12_SHM0': [0.3, 0.35, 0.32],
            'IGHG12_SHM1': [0.4, 0.45, 0.42],
            'IGHG34_SHM0': [0.5, 0.55, 0.52],
            'IGHG34_SHM1': [0.6, 0.65, 0.62],
            'IGHM_IGHD_SHM0': [0.7, 0.75, 0.72],
            'IGHM_IGHD_SHM1': [0.8, 0.85, 0.82],
            'IGH_SHM0': [0.9, 0.95, 0.92],
            'IGH_SHM1': [1.0, 1.05, 1.02]
        })
    
    def test_get_name(self, analyzer):
        """Test module name"""
        assert analyzer.get_name() == "shm_analyzer"
    
    def test_get_description(self, analyzer):
        """Test module description"""
        assert "SHM" in analyzer.get_description()
    
    def test_validate_shm_fields_valid(self, analyzer, sample_data):
        """Test SHM field validation with valid data"""
        is_valid, present, missing = analyzer.validate_shm_fields(sample_data)
        assert is_valid is True
        assert len(present) == 10
        assert len(missing) == 0
    
    def test_validate_shm_fields_missing(self, analyzer):
        """Test SHM field validation with missing fields"""
        data = pd.DataFrame({
            'Sample': ['Sample1'],
            'IGHA_SHM0': [0.1],
            'IGHA_SHM1': [0.2]
        })
        is_valid, present, missing = analyzer.validate_shm_fields(data)
        assert is_valid is False
        assert len(missing) > 0
    
    def test_validate_data_valid(self, analyzer, sample_data):
        """Test data validation with valid data"""
        is_valid, message = analyzer.validate_data(sample_data)
        assert is_valid is True
    
    def test_validate_data_empty(self, analyzer):
        """Test data validation with empty data"""
        data = pd.DataFrame()
        is_valid, message = analyzer.validate_data(data)
        assert is_valid is False
    
    def test_extract_shm_data(self, analyzer, sample_data):
        """Test SHM data extraction"""
        shm_data = analyzer.extract_shm_data(sample_data)
        assert len(shm_data) == 3
        assert 'Sample1' in shm_data
        assert 'IgA' in shm_data['Sample1']
        assert shm_data['Sample1']['IgA']['shm0'] == 0.1
        assert shm_data['Sample1']['IgA']['shm1'] == 0.2
    
    def test_calculate_percentage_changes(self, analyzer, sample_data):
        """Test percentage change calculation"""
        pct_changes = analyzer.calculate_percentage_changes(sample_data, 'Sample1')
        assert len(pct_changes) == 3
        # Sample1 should have 0% change (it's the baseline)
        assert pct_changes['Sample1']['IgA']['shm0_pct_change'] == 0.0
        # Sample2 should have positive change
        assert pct_changes['Sample2']['IgA']['shm0_pct_change'] > 0
    
    def test_analyze(self, analyzer, sample_data):
        """Test full analysis"""
        results = analyzer.analyze(sample_data, {'baseline_sample': 'Sample1'})
        assert 'samples' in results
        assert 'isotype_labels' in results
        assert 'shm_data' in results
        assert 'percentage_changes' in results
        assert 'table_data' in results
        assert len(results['samples']) == 3
        assert len(results['isotype_labels']) == 5
    
    def test_get_data_table(self, analyzer, sample_data):
        """Test data table generation"""
        table_data = analyzer.get_data_table(sample_data)
        assert 'headers' in table_data
        assert 'rows' in table_data
        assert 'tab_separated' in table_data
        assert len(table_data['rows']) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
