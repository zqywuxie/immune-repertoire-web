"""
Tests for Excel file support and sample management functionality.
Requirements: 10.1, 10.2, 10.4, 11.1, 11.2, 11.3, 11.4
"""
import io
import pytest
import pandas as pd
import numpy as np

from services.file_parser import FileParserService
from services.sample_manager import SampleManager
from exceptions import FileParseError, FileFormatInvalidError


class TestReadExcelSheets:
    """Tests for read_excel_sheets method. Requirements: 10.1, 10.2"""
    
    @pytest.fixture
    def sample_excel_content(self, tmp_path):
        """Create a sample Excel file with multiple sheets."""
        excel_path = tmp_path / "test_multi_sheet.xlsx"
        
        # Create DataFrames for different sheets
        df1 = pd.DataFrame({
            'Sample': ['S1', 'S2', 'S3'],
            'Value1': [10, 20, 30],
            'Value2': [1.1, 2.2, 3.3]
        })
        
        df2 = pd.DataFrame({
            'Sample': ['A1', 'A2'],
            'Metric': [100, 200]
        })
        
        df3 = pd.DataFrame({
            'ID': ['X', 'Y', 'Z', 'W'],
            'Score': [5, 10, 15, 20]
        })
        
        # Write to Excel with multiple sheets
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df1.to_excel(writer, sheet_name='Sheet1', index=False)
            df2.to_excel(writer, sheet_name='Summary', index=False)
            df3.to_excel(writer, sheet_name='Scores', index=False)
        
        return str(excel_path)
    
    def test_read_all_sheets(self, sample_excel_content):
        """Test reading all sheets from Excel file."""
        sheets = FileParserService.read_excel_sheets(sample_excel_content)
        
        assert len(sheets) == 3
        assert 'Sheet1' in sheets
        assert 'Summary' in sheets
        assert 'Scores' in sheets
        
        # Verify Sheet1 content
        assert list(sheets['Sheet1'].columns) == ['Sample', 'Value1', 'Value2']
        assert len(sheets['Sheet1']) == 3
        
        # Verify Summary content
        assert list(sheets['Summary'].columns) == ['Sample', 'Metric']
        assert len(sheets['Summary']) == 2
    
    def test_read_specific_sheets(self, sample_excel_content):
        """Test reading specific sheets from Excel file."""
        sheets = FileParserService.read_excel_sheets(
            sample_excel_content,
            sheet_names=['Sheet1', 'Scores']
        )
        
        assert len(sheets) == 2
        assert 'Sheet1' in sheets
        assert 'Scores' in sheets
        assert 'Summary' not in sheets
    
    def test_read_nonexistent_sheet_raises_error(self, sample_excel_content):
        """Test that requesting a nonexistent sheet raises error."""
        with pytest.raises(FileParseError) as exc_info:
            FileParserService.read_excel_sheets(
                sample_excel_content,
                sheet_names=['Sheet1', 'NonExistent']
            )
        assert 'not found' in str(exc_info.value.message).lower()
    
    def test_read_excel_from_bytes(self, sample_excel_content):
        """Test reading Excel from bytes content."""
        with open(sample_excel_content, 'rb') as f:
            content = f.read()
        
        sheets = FileParserService.read_excel_sheets(content)
        assert len(sheets) == 3


class TestGetExcelSheetNames:
    """Tests for get_excel_sheet_names method. Requirements: 10.2"""
    
    @pytest.fixture
    def sample_excel_content(self, tmp_path):
        """Create a sample Excel file with multiple sheets."""
        excel_path = tmp_path / "test_sheets.xlsx"
        
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            pd.DataFrame({'A': [1]}).to_excel(writer, sheet_name='Data', index=False)
            pd.DataFrame({'B': [2]}).to_excel(writer, sheet_name='Config', index=False)
            pd.DataFrame({'C': [3]}).to_excel(writer, sheet_name='Results', index=False)
        
        return str(excel_path)
    
    def test_get_sheet_names(self, sample_excel_content):
        """Test getting sheet names from Excel file."""
        sheet_names = FileParserService.get_excel_sheet_names(sample_excel_content)
        
        assert sheet_names == ['Data', 'Config', 'Results']


class TestFilterSamplesByPattern:
    """Tests for filter_samples_by_pattern method. Requirements: 10.4"""
    
    @pytest.fixture
    def sample_df(self):
        """Create a sample DataFrame for testing."""
        return pd.DataFrame({
            'Sample': ['Control_1', 'Control_2', 'Treatment_A', 'Treatment_B', 'Other'],
            'Value': [10, 20, 30, 40, 50]
        })
    
    def test_filter_by_prefix_pattern(self, sample_df):
        """Test filtering samples by prefix pattern."""
        filtered = FileParserService.filter_samples_by_pattern(
            sample_df, r'^Control_.*'
        )
        
        assert len(filtered) == 2
        assert list(filtered['Sample']) == ['Control_1', 'Control_2']
    
    def test_filter_by_suffix_pattern(self, sample_df):
        """Test filtering samples by suffix pattern."""
        filtered = FileParserService.filter_samples_by_pattern(
            sample_df, r'.*_[AB]$'
        )
        
        assert len(filtered) == 2
        assert 'Treatment_A' in filtered['Sample'].values
        assert 'Treatment_B' in filtered['Sample'].values
    
    def test_filter_by_contains_pattern(self, sample_df):
        """Test filtering samples by contains pattern."""
        filtered = FileParserService.filter_samples_by_pattern(
            sample_df, r'Treatment'
        )
        
        assert len(filtered) == 2
    
    def test_filter_no_matches(self, sample_df):
        """Test filtering with no matches returns empty DataFrame."""
        filtered = FileParserService.filter_samples_by_pattern(
            sample_df, r'^NonExistent.*'
        )
        
        assert len(filtered) == 0
    
    def test_filter_invalid_pattern_raises_error(self, sample_df):
        """Test that invalid regex pattern raises error."""
        with pytest.raises(FileParseError) as exc_info:
            FileParserService.filter_samples_by_pattern(
                sample_df, r'[invalid('
            )
        assert 'invalid regex' in str(exc_info.value.message).lower()
    
    def test_filter_missing_column_raises_error(self, sample_df):
        """Test that missing sample column raises error."""
        with pytest.raises(FileParseError) as exc_info:
            FileParserService.filter_samples_by_pattern(
                sample_df, r'.*', sample_column='NonExistent'
            )
        assert 'not found' in str(exc_info.value.message).lower()


class TestIdentifySampleColumn:
    """Tests for identify_sample_column method."""
    
    def test_identify_sample_column_exact_match(self):
        """Test identifying sample column with exact match."""
        df = pd.DataFrame({'Sample': ['S1'], 'Value': [1]})
        assert FileParserService.identify_sample_column(df) == 'Sample'
    
    def test_identify_sample_column_case_insensitive(self):
        """Test identifying sample column case-insensitively."""
        df = pd.DataFrame({'SAMPLE': ['S1'], 'Value': [1]})
        assert FileParserService.identify_sample_column(df) == 'SAMPLE'
    
    def test_identify_sample_column_alternative_names(self):
        """Test identifying sample column with alternative names."""
        df = pd.DataFrame({'ID': ['S1'], 'Value': [1]})
        assert FileParserService.identify_sample_column(df) == 'ID'
    
    def test_identify_sample_column_fallback_to_first_non_numeric(self):
        """Test fallback to first non-numeric column."""
        df = pd.DataFrame({'Name': ['S1'], 'Count': [1]})
        assert FileParserService.identify_sample_column(df) == 'Name'


class TestSampleManagerOrdering:
    """Tests for SampleManager ordering functionality. Requirements: 11.1, 11.2"""
    
    def test_order_samples_custom_order(self):
        """Test ordering samples with custom order."""
        samples = ['S3', 'S1', 'S2', 'S4']
        custom_order = ['S1', 'S2', 'S3', 'S4']
        
        result = SampleManager.order_samples(samples, custom_order=custom_order)
        
        assert result == ['S1', 'S2', 'S3', 'S4']
    
    def test_order_samples_partial_custom_order(self):
        """Test ordering with partial custom order."""
        samples = ['S3', 'S1', 'S2', 'S4', 'S5']
        custom_order = ['S1', 'S2']
        
        result = SampleManager.order_samples(samples, custom_order=custom_order)
        
        # S1 and S2 should come first in order, then remaining in original order
        assert result[:2] == ['S1', 'S2']
        assert set(result[2:]) == {'S3', 'S4', 'S5'}
    
    def test_order_samples_with_sort_key(self):
        """Test ordering samples with sort key function."""
        samples = ['Sample_3', 'Sample_1', 'Sample_2']
        
        result = SampleManager.order_samples(
            samples,
            sort_key=lambda x: int(x.split('_')[1])
        )
        
        assert result == ['Sample_1', 'Sample_2', 'Sample_3']
    
    def test_order_samples_reverse(self):
        """Test ordering samples in reverse."""
        samples = ['S1', 'S2', 'S3']
        
        result = SampleManager.order_samples(
            samples,
            sort_key=lambda x: x,
            reverse=True
        )
        
        assert result == ['S3', 'S2', 'S1']
    
    def test_apply_sample_order_to_dataframe(self):
        """Test applying sample order to DataFrame."""
        df = pd.DataFrame({
            'Sample': ['S3', 'S1', 'S2'],
            'Value': [30, 10, 20]
        })
        sample_order = ['S1', 'S2', 'S3']
        
        result = SampleManager.apply_sample_order_to_dataframe(
            df, sample_order, 'Sample'
        )
        
        assert list(result['Sample']) == ['S1', 'S2', 'S3']
        assert list(result['Value']) == [10, 20, 30]


class TestSampleManagerGrouping:
    """Tests for SampleManager grouping functionality. Requirements: 11.3, 11.4"""
    
    def test_group_samples_by_pattern(self):
        """Test grouping samples by regex pattern."""
        samples = ['Control_1', 'Control_2', 'Treatment_1', 'Treatment_2', 'Other']
        patterns = {
            'Control': r'^Control_.*',
            'Treatment': r'^Treatment_.*'
        }
        
        groups = SampleManager.group_samples_by_pattern(samples, patterns)
        
        assert groups['Control'] == ['Control_1', 'Control_2']
        assert groups['Treatment'] == ['Treatment_1', 'Treatment_2']
    
    def test_group_samples_manually(self):
        """Test manual sample grouping."""
        assignments = {
            'Group1': ['S1', 'S2'],
            'Group2': ['S3', 'S4', 'S5']
        }
        
        groups = SampleManager.group_samples_manually(assignments)
        
        assert groups['Group1'] == ['S1', 'S2']
        assert groups['Group2'] == ['S3', 'S4', 'S5']
    
    def test_calculate_group_statistics(self):
        """Test calculating group statistics."""
        data = pd.DataFrame({
            'Sample': ['S1', 'S2', 'S3', 'S4'],
            'Value1': [10, 20, 30, 40],
            'Value2': [1.0, 2.0, 3.0, 4.0]
        })
        groups = {
            'Group1': ['S1', 'S2'],
            'Group2': ['S3', 'S4']
        }
        
        stats = SampleManager.calculate_group_statistics(
            data, groups, ['Value1', 'Value2']
        )
        
        # Group1 mean for Value1: (10 + 20) / 2 = 15
        assert stats['Group1']['Value1']['mean'] == 15.0
        assert stats['Group1']['Value1']['count'] == 2
        
        # Group2 mean for Value1: (30 + 40) / 2 = 35
        assert stats['Group2']['Value1']['mean'] == 35.0
        
        # Check std is calculated
        assert 'std' in stats['Group1']['Value1']
    
    def test_calculate_group_mean(self):
        """Test calculating group mean."""
        data = pd.DataFrame({
            'Sample': ['S1', 'S2', 'S3', 'S4'],
            'Value': [10, 20, 30, 40]
        })
        groups = {
            'Group1': ['S1', 'S2'],
            'Group2': ['S3', 'S4']
        }
        
        means = SampleManager.calculate_group_mean(data, groups, 'Value')
        
        assert means['Group1'] == 15.0
        assert means['Group2'] == 35.0
    
    def test_create_group_summary_dataframe(self):
        """Test creating summary DataFrame from group statistics."""
        group_stats = {
            'Group1': {
                'Value1': {'mean': 15.0, 'std': 5.0},
                'Value2': {'mean': 1.5, 'std': 0.5}
            },
            'Group2': {
                'Value1': {'mean': 35.0, 'std': 5.0},
                'Value2': {'mean': 3.5, 'std': 0.5}
            }
        }
        
        summary_df = SampleManager.create_group_summary_dataframe(group_stats, 'mean')
        
        assert len(summary_df) == 2
        assert 'Group' in summary_df.columns
        assert 'Value1' in summary_df.columns
        assert 'Value2' in summary_df.columns
