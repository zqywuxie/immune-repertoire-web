"""
Tests for B Cell Isotype Analyzer Module
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

import pytest
import pandas as pd
import numpy as np
from io import BytesIO


class TestBcellIsotypeAnalyzer:
    """Test suite for BcellIsotypeAnalyzer class"""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance"""
        from services.analysis.modules.bcell_isotype_analyzer import BcellIsotypeAnalyzer
        return BcellIsotypeAnalyzer()
    
    @pytest.fixture
    def sample_data(self):
        """Create sample B cell isotype data"""
        return pd.DataFrame({
            'Sample': ['Sample1', 'Sample2', 'Sample3'],
            'IgM_Expression': [25.5, 30.2, 22.1],
            'IgM_Unique_CDR3': [20.3, 25.1, 18.5],
            'IgD_Expression': [15.2, 12.8, 18.3],
            'IgD_Unique_CDR3': [12.1, 10.5, 15.2],
            'IgA1/2_Expression': [18.5, 20.1, 16.8],
            'IgA1/2_Unique_CDR3': [15.2, 17.3, 14.1],
            'IgG1/2_Expression': [22.3, 18.5, 25.1],
            'IgG1/2_Unique_CDR3': [18.5, 15.2, 21.3],
            'IgG3/4_Expression': [12.5, 14.2, 10.8],
            'IgG3/4_Unique_CDR3': [10.2, 12.1, 8.9],
            'IgE_Expression': [6.0, 4.2, 6.9],
            'IgE_Unique_CDR3': [5.1, 3.5, 5.8]
        })
    
    @pytest.fixture
    def sample_data_with_percentages(self):
        """Create sample data with percentage format"""
        return pd.DataFrame({
            'Sample': ['Sample1', 'Sample2'],
            'IgM_Expression': ['25.5%', '30.2%'],
            'IgM_Unique_CDR3': ['20.3%', '25.1%'],
            'IgD_Expression': ['15.2%', '12.8%'],
            'IgD_Unique_CDR3': ['12.1%', '10.5%']
        })
    
    def test_get_name(self, analyzer):
        """Test module name"""
        assert analyzer.get_name() == "bcell_isotype_analyzer"
    
    def test_get_description(self, analyzer):
        """Test module description"""
        desc = analyzer.get_description()
        assert "B细胞" in desc or "B cell" in desc.lower()
    
    def test_get_category(self, analyzer):
        """Test module category"""
        assert analyzer.get_category() == "bcell_analysis"
    
    def test_isotypes_constant(self, analyzer):
        """Test ISOTYPES constant contains all 6 isotypes"""
        expected = ["IgM", "IgD", "IgA1/2", "IgG1/2", "IgG3/4", "IgE"]
        assert analyzer.ISOTYPES == expected
    
    def test_validate_data_empty(self, analyzer):
        """Test validation with empty DataFrame"""
        df = pd.DataFrame()
        is_valid, message = analyzer.validate_data(df)
        assert not is_valid
        assert "空" in message or "empty" in message.lower()
    
    def test_validate_data_no_isotype_columns(self, analyzer):
        """Test validation with no isotype columns"""
        df = pd.DataFrame({
            'Sample': ['A', 'B'],
            'Value1': [1, 2],
            'Value2': [3, 4]
        })
        is_valid, message = analyzer.validate_data(df)
        assert not is_valid
    
    def test_validate_data_valid(self, analyzer, sample_data):
        """Test validation with valid data"""
        is_valid, message = analyzer.validate_data(sample_data)
        assert is_valid

    def test_extract_isotype_data(self, analyzer, sample_data):
        """Test extracting isotype data from DataFrame
        Requirements: 1.2
        """
        result = analyzer.extract_isotype_data(sample_data, 'Sample')
        
        # Check all samples are present
        assert 'Sample1' in result
        assert 'Sample2' in result
        assert 'Sample3' in result
        
        # Check all isotypes are present for each sample
        for sample in result:
            for isotype in analyzer.ISOTYPES:
                assert isotype in result[sample]
                assert 'expression' in result[sample][isotype]
                assert 'unique_cdr3' in result[sample][isotype]
        
        # Check specific values
        assert result['Sample1']['IgM']['expression'] == 25.5
        assert result['Sample1']['IgM']['unique_cdr3'] == 20.3
    
    def test_extract_isotype_data_with_percentages(self, analyzer, sample_data_with_percentages):
        """Test extracting data with percentage format strings"""
        result = analyzer.extract_isotype_data(sample_data_with_percentages, 'Sample')
        
        # Values should be extracted without % sign
        assert result['Sample1']['IgM']['expression'] == 25.5
        assert result['Sample2']['IgM']['expression'] == 30.2
    
    def test_calculate_percentage_diff(self, analyzer, sample_data):
        """Test percentage difference calculation
        Requirements: 1.5
        """
        result = analyzer.calculate_percentage_diff(sample_data, 'Sample1', 'Sample')
        
        # Baseline sample should have 0% diff
        assert result['Sample1']['IgM']['expression_diff'] == 0.0
        assert result['Sample1']['IgM']['cdr3_diff'] == 0.0
        
        # Check calculation for Sample2
        # IgM Expression: ((30.2 - 25.5) / 25.5) * 100 = 18.43%
        expected_expr_diff = round(((30.2 - 25.5) / 25.5) * 100, 2)
        assert result['Sample2']['IgM']['expression_diff'] == expected_expr_diff
    
    def test_calculate_percentage_diff_invalid_baseline(self, analyzer, sample_data):
        """Test percentage diff with invalid baseline sample"""
        result = analyzer.calculate_percentage_diff(sample_data, 'NonExistent', 'Sample')
        assert result == {}
    
    def test_analyze(self, analyzer, sample_data):
        """Test full analysis workflow"""
        params = {
            'sample_column': 'Sample',
            'baseline_sample': 'Sample1'
        }
        
        result = analyzer.analyze(sample_data, params)
        
        assert 'samples' in result
        assert 'isotypes' in result
        assert 'isotype_data' in result
        assert 'percentage_diffs' in result
        assert 'table_data' in result
        
        assert len(result['samples']) == 3
        assert result['isotypes'] == analyzer.ISOTYPES
    
    def test_analyze_without_baseline(self, analyzer, sample_data):
        """Test analysis without baseline sample"""
        params = {
            'sample_column': 'Sample',
            'baseline_sample': None
        }
        
        result = analyzer.analyze(sample_data, params)
        
        assert result['percentage_diffs'] is None
        assert result['baseline_sample'] is None
    
    def test_generate_table_data(self, analyzer, sample_data):
        """Test table data generation
        Requirements: 1.4
        """
        isotype_data = analyzer.extract_isotype_data(sample_data, 'Sample')
        samples = list(isotype_data.keys())
        
        table_data = analyzer._generate_table_data(isotype_data, samples, None)
        
        assert 'headers' in table_data
        assert 'rows' in table_data
        assert 'tab_separated' in table_data
        
        # Check headers include all isotypes
        headers = table_data['headers']
        assert 'Sample' in headers
        assert 'IgM_Expression' in headers
        assert 'IgM_Unique_CDR3' in headers
        
        # Check rows count
        assert len(table_data['rows']) == 3
    
    def test_generate_table_data_with_diffs(self, analyzer, sample_data):
        """Test table data generation with percentage diffs"""
        isotype_data = analyzer.extract_isotype_data(sample_data, 'Sample')
        percentage_diffs = analyzer.calculate_percentage_diff(sample_data, 'Sample1', 'Sample')
        samples = list(isotype_data.keys())
        
        table_data = analyzer._generate_table_data(isotype_data, samples, percentage_diffs)
        
        # Check diff columns are included
        headers = table_data['headers']
        assert 'IgM_Expr_Diff%' in headers
        assert 'IgM_CDR3_Diff%' in headers

    def test_to_tab_separated(self, analyzer):
        """Test tab-separated format generation
        Requirements: 7.2, 7.4
        """
        headers = ['Sample', 'Value1', 'Value2']
        rows = [['A', 1, 2], ['B', 3, 4]]
        
        result = analyzer._to_tab_separated(headers, rows)
        
        lines = result.split('\n')
        assert len(lines) == 3
        assert lines[0] == 'Sample\tValue1\tValue2'
        assert lines[1] == 'A\t1\t2'
        assert lines[2] == 'B\t3\t4'
    
    def test_visualize(self, analyzer, sample_data):
        """Test visualization generation
        Requirements: 1.3
        """
        params = {
            'sample_column': 'Sample',
            'baseline_sample': 'Sample1',
            'chart_config': {
                'title': 'Test Chart',
                'figsize': (16, 8),
                'dpi': 100,
                'show_values': True
            }
        }
        
        results = analyzer.analyze(sample_data, params)
        figures = analyzer.visualize(results, params)
        
        # Should have charts for each sample
        assert 'isotype_Sample1' in figures
        assert 'isotype_Sample2' in figures
        assert 'isotype_Sample3' in figures
        
        # Should have percentage diff chart
        assert 'percentage_diff' in figures
        
        # Charts should be base64 encoded
        for key, value in figures.items():
            if key != 'error':
                assert isinstance(value, str)
                assert len(value) > 0
    
    def test_visualize_without_baseline(self, analyzer, sample_data):
        """Test visualization without baseline"""
        params = {
            'sample_column': 'Sample',
            'baseline_sample': None,
            'chart_config': {}
        }
        
        results = analyzer.analyze(sample_data, params)
        figures = analyzer.visualize(results, params)
        
        # Should have sample charts but no diff chart
        assert 'isotype_Sample1' in figures
        assert 'percentage_diff' not in figures
    
    def test_get_data_table(self, analyzer, sample_data):
        """Test get_data_table method
        Requirements: 1.4
        """
        table_data = analyzer.get_data_table(sample_data, 'Sample', 'Sample1')
        
        assert 'headers' in table_data
        assert 'rows' in table_data
        assert 'tab_separated' in table_data
    
    def test_generate_horizontal_bar_chart(self, analyzer, sample_data):
        """Test horizontal bar chart generation
        Requirements: 1.3
        """
        png_bytes, table_data = analyzer.generate_horizontal_bar_chart(
            sample_data, 'Sample1', 'Sample'
        )
        
        # Should return PNG bytes
        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        
        # Should return table data
        assert 'headers' in table_data
        assert 'rows' in table_data
    
    def test_generate_horizontal_bar_chart_invalid_sample(self, analyzer, sample_data):
        """Test horizontal bar chart with invalid sample"""
        with pytest.raises(ValueError):
            analyzer.generate_horizontal_bar_chart(
                sample_data, 'NonExistent', 'Sample'
            )


class TestBcellChartConfig:
    """Test suite for BcellChartConfig class"""
    
    def test_default_config(self):
        """Test default configuration values"""
        from services.analysis.modules.bcell_isotype_analyzer import BcellChartConfig
        
        config = BcellChartConfig()
        
        assert config.title == ""
        assert config.figsize == (16, 8)
        assert config.dpi == 300
        assert config.font_size == 12
        assert config.show_values == True
        assert len(config.expression_colors) == 6
        assert len(config.cdr3_colors) == 6
    
    def test_from_dict(self):
        """Test creating config from dictionary"""
        from services.analysis.modules.bcell_isotype_analyzer import BcellChartConfig
        
        config_dict = {
            'title': 'Custom Title',
            'figsize': (20, 10),
            'dpi': 150,
            'font_size': 14,
            'show_values': False
        }
        
        config = BcellChartConfig.from_dict(config_dict)
        
        assert config.title == 'Custom Title'
        assert config.figsize == (20, 10)
        assert config.dpi == 150
        assert config.font_size == 14
        assert config.show_values == False


class TestBcellIsotypeAPI:
    """Test suite for B Cell Isotype API endpoints"""
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing"""
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        from app import create_app
        app = create_app('testing')
        
        with app.app_context():
            from models.database import db
            db.create_all()
            yield app
            db.drop_all()
    
    @pytest.fixture
    def sample_file(self, client):
        """Upload a sample file for testing"""
        import io
        
        # Create CSV content
        csv_content = """Sample,IgM_Expression,IgM_Unique_CDR3,IgD_Expression,IgD_Unique_CDR3
Sample1,25.5,20.3,15.2,12.1
Sample2,30.2,25.1,12.8,10.5
Sample3,22.1,18.5,18.3,15.2"""
        
        data = {
            'file': (io.BytesIO(csv_content.encode()), 'test_bcell.csv')
        }
        
        response = client.post('/api/files/upload', data=data, content_type='multipart/form-data')
        
        if response.status_code == 201:
            return response.get_json()['id']
        return None
    
    def test_bcell_isotype_analysis(self, client, sample_file):
        """Test POST /api/analysis/bcell-isotype"""
        if not sample_file:
            pytest.skip("File upload failed")
        
        response = client.post('/api/analysis/bcell-isotype',
            json={
                'file_id': sample_file,
                'sample_column': 'Sample',
                'baseline_sample': 'Sample1'
            }
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'analysis_id' in data
        assert 'samples' in data
        assert 'isotypes' in data
        assert 'isotype_data' in data
        assert 'table_data' in data
        assert 'charts' in data
    
    def test_bcell_isotype_analysis_no_baseline(self, client, sample_file):
        """Test analysis without baseline sample"""
        if not sample_file:
            pytest.skip("File upload failed")
        
        response = client.post('/api/analysis/bcell-isotype',
            json={
                'file_id': sample_file,
                'sample_column': 'Sample'
            }
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data['percentage_diffs'] is None
    
    def test_bcell_isotype_analysis_file_not_found(self, client):
        """Test analysis with non-existent file"""
        response = client.post('/api/analysis/bcell-isotype',
            json={
                'file_id': 'non-existent-id',
                'sample_column': 'Sample'
            }
        )
        
        assert response.status_code == 404
    
    def test_bcell_isotype_analysis_missing_file_id(self, client):
        """Test analysis without file_id"""
        response = client.post('/api/analysis/bcell-isotype',
            json={
                'sample_column': 'Sample'
            }
        )
        
        assert response.status_code == 400
