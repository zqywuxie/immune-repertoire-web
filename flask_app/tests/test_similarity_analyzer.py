"""
Tests for the SimilarityAnalyzer service.
Requirements: 2.1, 2.3
"""
import pytest
import numpy as np
import pandas as pd

from services.similarity_analyzer import SimilarityAnalyzer, HeatmapConfig


class TestSimilarityAnalyzerBasic:
    """Basic tests for SimilarityAnalyzer initialization and data preparation."""
    
    def test_analyzer_initialization(self):
        """Test that analyzer initializes correctly with valid data."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        
        assert len(analyzer.samples) == 2
        assert 'A' in analyzer.samples
        assert 'B' in analyzer.samples
    
    def test_analyzer_with_empty_data(self):
        """Test that analyzer handles empty data gracefully."""
        data = pd.DataFrame()
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        
        assert len(analyzer.samples) == 0
    
    def test_analyzer_with_custom_config(self):
        """Test that analyzer accepts custom heatmap configuration."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR1'],
            'copy': [10, 20]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        config = HeatmapConfig(title="Test", color_scheme="plasma")
        
        analyzer = SimilarityAnalyzer(data, field_mapping, config)
        
        assert analyzer.chart_config.title == "Test"
        assert analyzer.chart_config.color_scheme == "plasma"


class TestR2InnerCalculation:
    """Tests for R² inner similarity calculation."""
    
    def test_r2_inner_identical_samples(self):
        """Test R² inner returns 1.0 for identical samples on diagonal."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR2'],
            'copy': [10, 20, 10, 20]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_r2_inner()
        
        # Diagonal should be 1.0
        assert matrix.loc['A', 'A'] == 1.0
        assert matrix.loc['B', 'B'] == 1.0
    
    def test_r2_inner_symmetry(self):
        """Test R² inner matrix is symmetric."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B', 'C', 'C'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3', 'CDR2', 'CDR3'],
            'copy': [10, 20, 15, 25, 30, 10]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_r2_inner()
        
        # Check symmetry
        assert matrix.loc['A', 'B'] == matrix.loc['B', 'A']
        assert matrix.loc['A', 'C'] == matrix.loc['C', 'A']
        assert matrix.loc['B', 'C'] == matrix.loc['C', 'B']
    
    def test_r2_inner_no_shared_cdr3(self):
        """Test R² inner returns 0 when samples share no CDR3."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR4'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_r2_inner()
        
        # No shared CDR3, should be 0
        assert matrix.loc['A', 'B'] == 0.0


class TestR2OuterCalculation:
    """Tests for R² outer similarity calculation."""
    
    def test_r2_outer_diagonal(self):
        """Test R² outer returns 1.0 on diagonal."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_r2_outer()
        
        assert matrix.loc['A', 'A'] == 1.0
        assert matrix.loc['B', 'B'] == 1.0
    
    def test_r2_outer_symmetry(self):
        """Test R² outer matrix is symmetric."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_r2_outer()
        
        assert matrix.loc['A', 'B'] == matrix.loc['B', 'A']


class TestCDR3SharingCalculation:
    """Tests for CDR3 sharing similarity calculation."""
    
    def test_cdr3_sharing_identical_sets(self):
        """Test CDR3 sharing returns 1.0 for identical CDR3 sets."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR2'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_cdr3_sharing()
        
        # Identical CDR3 sets should give 1.0
        assert matrix.loc['A', 'B'] == 1.0
    
    def test_cdr3_sharing_no_overlap(self):
        """Test CDR3 sharing returns 0 for no overlap."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR4'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_cdr3_sharing()
        
        assert matrix.loc['A', 'B'] == 0.0
    
    def test_cdr3_sharing_symmetry(self):
        """Test CDR3 sharing matrix is symmetric."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR1', 'CDR4'],
            'copy': [10, 20, 30, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_cdr3_sharing()
        
        assert matrix.loc['A', 'B'] == matrix.loc['B', 'A']


class TestExpressionSharingCalculation:
    """Tests for expression sharing similarity calculation."""
    
    def test_expression_sharing_diagonal(self):
        """Test expression sharing returns 1.0 on diagonal."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_expression_sharing()
        
        assert matrix.loc['A', 'A'] == 1.0
        assert matrix.loc['B', 'B'] == 1.0
    
    def test_expression_sharing_symmetry(self):
        """Test expression sharing matrix is symmetric."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_expression_sharing()
        
        assert matrix.loc['A', 'B'] == matrix.loc['B', 'A']


class TestMorisitaHornCalculation:
    """Tests for Morisita-Horn similarity calculation."""
    
    def test_morisita_horn_diagonal(self):
        """Test Morisita-Horn returns 1.0 on diagonal."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_morisita_horn()
        
        assert matrix.loc['A', 'A'] == 1.0
        assert matrix.loc['B', 'B'] == 1.0
    
    def test_morisita_horn_symmetry(self):
        """Test Morisita-Horn matrix is symmetric."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_morisita_horn()
        
        assert matrix.loc['A', 'B'] == matrix.loc['B', 'A']


class TestSorensenCalculation:
    """Tests for Sorensen similarity calculation."""
    
    def test_sorensen_identical_sets(self):
        """Test Sorensen returns 1.0 for identical CDR3 sets."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR2'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_sorensen()
        
        assert matrix.loc['A', 'B'] == 1.0
    
    def test_sorensen_no_overlap(self):
        """Test Sorensen returns 0 for no overlap."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR4'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_sorensen()
        
        assert matrix.loc['A', 'B'] == 0.0
    
    def test_sorensen_symmetry(self):
        """Test Sorensen matrix is symmetric."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR1', 'CDR4'],
            'copy': [10, 20, 30, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_sorensen()
        
        assert matrix.loc['A', 'B'] == matrix.loc['B', 'A']
    
    def test_sorensen_partial_overlap(self):
        """Test Sorensen calculation with partial overlap."""
        # A has {CDR1, CDR2}, B has {CDR1, CDR3}
        # Intersection = 1, Sum of sizes = 4
        # Sorensen = 2 * 1 / 4 = 0.5
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_sorensen()
        
        assert matrix.loc['A', 'B'] == 0.5


class TestCalculateAllMetrics:
    """Tests for calculating all metrics at once."""
    
    def test_calculate_all_metrics_returns_all(self):
        """Test that calculate_all_metrics returns all six metrics."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        metrics = analyzer.calculate_all_metrics()
        
        assert 'r2_inner' in metrics
        assert 'r2_outer' in metrics
        assert 'cdr3_sharing' in metrics
        assert 'expression_sharing' in metrics
        assert 'morisita_horn' in metrics
        assert 'sorensen' in metrics
    
    def test_calculate_metric_by_name(self):
        """Test calculating a specific metric by name."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [10, 20, 15, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        matrix = analyzer.calculate_metric('sorensen')
        
        assert not matrix.empty
        assert matrix.loc['A', 'A'] == 1.0
    
    def test_calculate_metric_invalid_name(self):
        """Test that invalid metric name raises ValueError."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR1'],
            'copy': [10, 20]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = SimilarityAnalyzer(data, field_mapping)
        
        with pytest.raises(ValueError):
            analyzer.calculate_metric('invalid_metric')
