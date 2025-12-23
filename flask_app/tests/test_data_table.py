"""
Tests for the DataTableService.
Requirements: 2.5, 2.6
"""
import pytest
import numpy as np
import pandas as pd

from services.data_table import DataTableService


class TestMatrixToTable:
    """Tests for matrix_to_table conversion."""
    
    @pytest.fixture
    def sample_matrix(self):
        """Create a sample similarity matrix for testing."""
        data = np.array([
            [1.0, 0.8, 0.6],
            [0.8, 1.0, 0.7],
            [0.6, 0.7, 1.0]
        ])
        return pd.DataFrame(data, index=['A', 'B', 'C'], columns=['A', 'B', 'C'])
    
    def test_matrix_to_table_structure(self, sample_matrix):
        """Test that matrix_to_table returns correct structure."""
        result = DataTableService.matrix_to_table(sample_matrix)
        
        assert 'columns' in result
        assert 'data' in result
        assert 'row_count' in result
        assert 'column_count' in result
    
    def test_matrix_to_table_columns(self, sample_matrix):
        """Test that columns are correctly extracted."""
        result = DataTableService.matrix_to_table(sample_matrix)
        
        # Should have Sample column + 3 data columns
        assert len(result['columns']) == 4
        assert result['columns'][0]['name'] == 'Sample'
        assert result['columns'][1]['name'] == 'A'
        assert result['columns'][2]['name'] == 'B'
        assert result['columns'][3]['name'] == 'C'
    
    def test_matrix_to_table_data(self, sample_matrix):
        """Test that data is correctly converted."""
        result = DataTableService.matrix_to_table(sample_matrix)
        
        assert len(result['data']) == 3
        assert result['data'][0]['Sample'] == 'A'
        assert result['data'][0]['A'] == 1.0
        assert result['data'][0]['B'] == 0.8
    
    def test_matrix_to_table_precision(self, sample_matrix):
        """Test that precision is applied correctly."""
        result = DataTableService.matrix_to_table(sample_matrix, precision=2)
        
        # Values should be rounded to 2 decimal places
        assert result['data'][0]['B'] == 0.8
    
    def test_matrix_to_table_empty(self):
        """Test handling of empty matrix."""
        empty_matrix = pd.DataFrame()
        result = DataTableService.matrix_to_table(empty_matrix)
        
        assert result['columns'] == []
        assert result['data'] == []
        assert result['row_count'] == 0
    
    def test_matrix_to_table_without_index(self, sample_matrix):
        """Test conversion without including index."""
        result = DataTableService.matrix_to_table(sample_matrix, include_index=False)
        
        # Should only have 3 data columns
        assert len(result['columns']) == 3
        assert result['columns'][0]['name'] == 'A'


class TestMatrixToClipboardText:
    """Tests for matrix_to_clipboard_text conversion."""
    
    @pytest.fixture
    def sample_matrix(self):
        """Create a sample similarity matrix for testing."""
        data = np.array([
            [1.0, 0.8],
            [0.8, 1.0]
        ])
        return pd.DataFrame(data, index=['A', 'B'], columns=['A', 'B'])
    
    def test_clipboard_text_format(self, sample_matrix):
        """Test that clipboard text is tab-delimited."""
        result = DataTableService.matrix_to_clipboard_text(sample_matrix)
        
        lines = result.strip().split('\n')
        assert len(lines) == 3  # Header + 2 data rows
        
        # Check tab delimiter
        assert '\t' in lines[0]
        assert '\t' in lines[1]
    
    def test_clipboard_text_header(self, sample_matrix):
        """Test that header row is correct."""
        result = DataTableService.matrix_to_clipboard_text(sample_matrix)
        
        lines = result.split('\n')  # Don't strip to preserve empty first element
        header = lines[0].split('\t')
        
        # Header row: empty string for index, then column names
        assert len(header) == 3  # Empty + A + B
        assert header[0] == ''  # Empty for index column
        assert header[1] == 'A'
        assert header[2] == 'B'
    
    def test_clipboard_text_empty(self):
        """Test handling of empty matrix."""
        empty_matrix = pd.DataFrame()
        result = DataTableService.matrix_to_clipboard_text(empty_matrix)
        
        assert result == ""


class TestMatrixToCSV:
    """Tests for matrix_to_csv conversion."""
    
    @pytest.fixture
    def sample_matrix(self):
        """Create a sample similarity matrix for testing."""
        data = np.array([
            [1.0, 0.8],
            [0.8, 1.0]
        ])
        return pd.DataFrame(data, index=['A', 'B'], columns=['A', 'B'])
    
    def test_csv_format(self, sample_matrix):
        """Test that CSV is properly formatted."""
        result = DataTableService.matrix_to_csv(sample_matrix)
        
        assert ',' in result
        lines = result.strip().split('\n')
        assert len(lines) == 3  # Header + 2 data rows
    
    def test_csv_empty(self):
        """Test handling of empty matrix."""
        empty_matrix = pd.DataFrame()
        result = DataTableService.matrix_to_csv(empty_matrix)
        
        assert result == ""


class TestDataFrameToTable:
    """Tests for general DataFrame to table conversion."""
    
    def test_dataframe_to_table(self):
        """Test converting a general DataFrame."""
        df = pd.DataFrame({
            'name': ['Sample1', 'Sample2'],
            'value': [1.5, 2.5],
            'count': [10, 20]
        })
        
        result = DataTableService.dataframe_to_table(df)
        
        assert len(result['columns']) == 3
        assert len(result['data']) == 2
        assert result['truncated'] is False
    
    def test_dataframe_to_table_max_rows(self):
        """Test truncation with max_rows."""
        df = pd.DataFrame({
            'value': range(100)
        })
        
        result = DataTableService.dataframe_to_table(df, max_rows=10)
        
        assert result['row_count'] == 10
        assert result['truncated'] is True
    
    def test_dataframe_to_table_handles_nan(self):
        """Test handling of NaN values."""
        df = pd.DataFrame({
            'value': [1.0, np.nan, 3.0]
        })
        
        result = DataTableService.dataframe_to_table(df)
        
        assert result['data'][1]['value'] is None


class TestTableStatistics:
    """Tests for table statistics calculation."""
    
    @pytest.fixture
    def sample_matrix(self):
        """Create a sample similarity matrix for testing."""
        data = np.array([
            [1.0, 0.8, 0.6],
            [0.8, 1.0, 0.7],
            [0.6, 0.7, 1.0]
        ])
        return pd.DataFrame(data, index=['A', 'B', 'C'], columns=['A', 'B', 'C'])
    
    def test_statistics_keys(self, sample_matrix):
        """Test that statistics contain expected keys."""
        stats = DataTableService.get_table_statistics(sample_matrix)
        
        assert 'min' in stats
        assert 'max' in stats
        assert 'mean' in stats
        assert 'median' in stats
        assert 'std' in stats
        assert 'n_samples' in stats
        assert 'n_comparisons' in stats
    
    def test_statistics_values(self, sample_matrix):
        """Test that statistics are calculated correctly."""
        stats = DataTableService.get_table_statistics(sample_matrix)
        
        # Off-diagonal values: 0.8, 0.6, 0.8, 0.7, 0.6, 0.7
        assert stats['min'] == 0.6
        assert stats['max'] == 0.8
        assert stats['n_samples'] == 3
        assert stats['n_comparisons'] == 6  # 3x3 - 3 diagonal
    
    def test_statistics_empty(self):
        """Test statistics for empty matrix."""
        empty_matrix = pd.DataFrame()
        stats = DataTableService.get_table_statistics(empty_matrix)
        
        assert stats == {}
