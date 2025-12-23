"""
Tests for the Field Analyzer Module
Requirements: 5.1, 5.3, 5.5, 5.6
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
import sys
import os

# Add the flask_app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestFieldAnalyzerModule:
    """Tests for FieldAnalyzerModule class"""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing"""
        return pd.DataFrame({
            'Sample': ['S1', 'S2', 'S3', 'S4'],
            'Value1': [10.0, 20.0, 30.0, 40.0],
            'Value2': [100.0, 200.0, 300.0, 400.0],
            'Category': ['A', 'B', 'A', 'B'],
            'Mixed': ['1', '2', 'three', '4']
        })
    
    @pytest.fixture
    def analyzer(self):
        """Create FieldAnalyzerModule instance"""
        # Import here to avoid import issues during collection
        from services.analysis.modules.field_analyzer import FieldAnalyzerModule
        return FieldAnalyzerModule()
    
    def test_identify_numeric_fields(self, analyzer, sample_data):
        """
        Test that identify_numeric_fields correctly identifies numeric columns.
        Requirements: 5.1
        """
        numeric_fields = analyzer.identify_numeric_fields(sample_data)
        
        # Value1 and Value2 should be identified as numeric
        assert 'Value1' in numeric_fields
        assert 'Value2' in numeric_fields
        # Category should not be numeric
        assert 'Category' not in numeric_fields
    
    def test_identify_numeric_fields_empty_dataframe(self, analyzer):
        """Test identify_numeric_fields with empty DataFrame"""
        empty_df = pd.DataFrame()
        numeric_fields = analyzer.identify_numeric_fields(empty_df)
        assert numeric_fields == []
    
    def test_extract_field_data(self, analyzer, sample_data):
        """
        Test that extract_field_data correctly extracts field values.
        Requirements: 5.3
        """
        fields = ['Value1', 'Value2']
        result = analyzer.extract_field_data(sample_data, fields, 'Sample')
        
        # Check structure
        assert 'S1' in result
        assert 'S2' in result
        assert 'S3' in result
        assert 'S4' in result
        
        # Check values
        assert result['S1']['Value1'] == 10.0
        assert result['S2']['Value1'] == 20.0
        assert result['S1']['Value2'] == 100.0
        assert result['S4']['Value2'] == 400.0
    
    def test_extract_field_data_missing_field(self, analyzer, sample_data):
        """Test extract_field_data with a field that doesn't exist"""
        fields = ['Value1', 'NonExistent']
        result = analyzer.extract_field_data(sample_data, fields, 'Sample')
        
        # Should still extract Value1
        assert result['S1']['Value1'] == 10.0
        # NonExistent should not be in the result
        assert 'NonExistent' not in result['S1']
    
    def test_calculate_percentage_diff(self, analyzer, sample_data):
        """
        Test that calculate_percentage_diff correctly calculates percentage differences.
        Requirements: 5.6
        
        Formula: ((sample_value - baseline_value) / baseline_value) * 100
        """
        result = analyzer.calculate_percentage_diff(
            sample_data, 'Value1', 'S1', 'Sample'
        )
        
        # S1 is baseline, so diff should be 0
        assert result['S1'] == 0.0
        
        # S2: ((20 - 10) / 10) * 100 = 100%
        assert result['S2'] == 100.0
        
        # S3: ((30 - 10) / 10) * 100 = 200%
        assert result['S3'] == 200.0
        
        # S4: ((40 - 10) / 10) * 100 = 300%
        assert result['S4'] == 300.0
    
    def test_calculate_percentage_diff_baseline_not_found(self, analyzer, sample_data):
        """Test calculate_percentage_diff when baseline sample doesn't exist"""
        result = analyzer.calculate_percentage_diff(
            sample_data, 'Value1', 'NonExistent', 'Sample'
        )
        
        # Should return empty dict when baseline not found
        assert result == {}
    
    def test_calculate_percentage_diff_zero_baseline(self, analyzer):
        """Test calculate_percentage_diff when baseline value is zero"""
        data = pd.DataFrame({
            'Sample': ['S1', 'S2'],
            'Value': [0.0, 10.0]
        })
        
        result = analyzer.calculate_percentage_diff(data, 'Value', 'S1', 'Sample')
        
        # Should return empty dict when baseline is zero (division by zero)
        assert result == {}
    
    def test_get_data_table(self, analyzer, sample_data):
        """
        Test that get_data_table generates correct table structure.
        Requirements: 5.5
        """
        fields = ['Value1', 'Value2']
        result = analyzer.get_data_table(sample_data, fields, 'Sample')
        
        # Check structure
        assert 'headers' in result
        assert 'rows' in result
        assert 'tab_separated' in result
        
        # Check headers
        assert result['headers'] == ['Sample', 'Value1', 'Value2']
        
        # Check rows
        assert len(result['rows']) == 4
        assert result['rows'][0][0] == 'S1'
        assert result['rows'][0][1] == 10.0
    
    def test_get_data_table_with_baseline(self, analyzer, sample_data):
        """Test get_data_table with baseline sample for percentage diff"""
        fields = ['Value1']
        result = analyzer.get_data_table(sample_data, fields, 'Sample', baseline_sample='S1')
        
        # Headers should include diff column
        assert 'Value1_Diff%' in result['headers']
        
        # Check that diff values are included
        # First row (S1) should have 0% diff
        s1_row = result['rows'][0]
        diff_index = result['headers'].index('Value1_Diff%')
        assert s1_row[diff_index] == 0.0
    
    def test_tab_separated_format(self, analyzer, sample_data):
        """
        Test that tab_separated output is correctly formatted.
        Requirements: 7.2, 7.4
        """
        fields = ['Value1']
        result = analyzer.get_data_table(sample_data, fields, 'Sample')
        
        tab_separated = result['tab_separated']
        lines = tab_separated.split('\n')
        
        # First line should be headers
        assert lines[0] == 'Sample\tValue1'
        
        # Data lines should be tab-separated
        assert lines[1] == 'S1\t10.0'
        assert lines[2] == 'S2\t20.0'
    
    def test_analyze(self, analyzer, sample_data):
        """Test the analyze method"""
        params = {
            'sample_column': 'Sample',
            'fields': ['Value1', 'Value2'],
            'baseline_sample': 'S1'
        }
        
        result = analyzer.analyze(sample_data, params)
        
        # Check result structure
        assert 'samples' in result
        assert 'fields' in result
        assert 'field_data' in result
        assert 'percentage_diffs' in result
        assert 'table_data' in result
        
        # Check samples
        assert result['samples'] == ['S1', 'S2', 'S3', 'S4']
        
        # Check fields
        assert result['fields'] == ['Value1', 'Value2']
    
    def test_validate_data(self, analyzer, sample_data):
        """Test data validation"""
        is_valid, message = analyzer.validate_data(sample_data)
        assert is_valid is True
        assert message == "数据验证通过"
    
    def test_validate_data_empty(self, analyzer):
        """Test validation with empty DataFrame"""
        empty_df = pd.DataFrame()
        is_valid, message = analyzer.validate_data(empty_df)
        assert is_valid is False
        assert "数据为空" in message
    
    def test_validate_data_no_numeric(self, analyzer):
        """Test validation with no numeric columns"""
        non_numeric_df = pd.DataFrame({
            'A': ['a', 'b', 'c'],
            'B': ['x', 'y', 'z']
        })
        is_valid, message = analyzer.validate_data(non_numeric_df)
        assert is_valid is False
        assert "数值" in message
    
    def test_analyze_with_selected_samples(self, analyzer, sample_data):
        """
        Test that analyze correctly filters data by selected samples.
        Requirements: 21.3, 21.5
        """
        params = {
            'sample_column': 'Sample',
            'fields': ['Value1', 'Value2'],
            'selected_samples': ['S1', 'S3']  # Only select S1 and S3
        }
        
        result = analyzer.analyze(sample_data, params)
        
        # Check that only selected samples are in results
        assert result['samples'] == ['S1', 'S3']
        assert len(result['samples']) == 2
        
        # Check field data only contains selected samples
        assert 'S1' in result['field_data']
        assert 'S3' in result['field_data']
        assert 'S2' not in result['field_data']
        assert 'S4' not in result['field_data']
        
        # Verify values for selected samples
        assert result['field_data']['S1']['Value1'] == 10.0
        assert result['field_data']['S3']['Value1'] == 30.0


class TestFieldAnalyzerAPI:
    """Tests for Field Analyzer API endpoints"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        from app import create_app
        app = create_app()
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    @pytest.fixture
    def sample_file(self, client, tmp_path):
        """Create and upload a sample file"""
        import io
        
        # Create CSV content
        csv_content = "Sample,Value1,Value2,Category\nS1,10,100,A\nS2,20,200,B\nS3,30,300,A\n"
        
        # Upload file
        data = {
            'file': (io.BytesIO(csv_content.encode()), 'test_data.csv')
        }
        response = client.post('/api/files/upload', data=data, content_type='multipart/form-data')
        
        if response.status_code == 201:
            return response.get_json()['id']
        return None
    
    def test_get_file_fields(self, client, sample_file):
        """Test GET /api/analysis/fields/{file_id}"""
        if not sample_file:
            pytest.skip("File upload failed")
        
        response = client.get(f'/api/analysis/fields/{sample_file}')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'numeric_fields' in data
        assert 'sample_column' in data
        assert 'row_count' in data
        assert 'all_columns' in data
        
        # Value1 and Value2 should be numeric
        assert 'Value1' in data['numeric_fields']
        assert 'Value2' in data['numeric_fields']
    
    def test_get_file_fields_not_found(self, client):
        """Test GET /api/analysis/fields/{file_id} with non-existent file"""
        response = client.get('/api/analysis/fields/non-existent-id')
        assert response.status_code == 404
    
    def test_analyze_field_data(self, client, sample_file):
        """Test POST /api/analysis/field-data"""
        if not sample_file:
            pytest.skip("File upload failed")
        
        request_data = {
            'file_id': sample_file,
            'fields': ['Value1', 'Value2'],
            'sample_column': 'Sample',
            'baseline_sample': 'S1',
            'plot_type': 'bar'
        }
        
        response = client.post(
            '/api/analysis/field-data',
            json=request_data,
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'analysis_id' in data
        assert 'samples' in data
        assert 'fields' in data
        assert 'field_data' in data
        assert 'table_data' in data
        assert 'charts' in data
    
    def test_analyze_field_data_missing_file_id(self, client):
        """Test POST /api/analysis/field-data without file_id"""
        request_data = {
            'fields': ['Value1']
        }
        
        response = client.post(
            '/api/analysis/field-data',
            json=request_data,
            content_type='application/json'
        )
        
        assert response.status_code == 400
