"""
Tests for the DiversityAnalyzer, SampleGrouper, and DiversityChartGenerator services.
Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 12.1
"""
import pytest
import numpy as np
import pandas as pd

from services.diversity_analyzer import (
    DiversityAnalyzer,
    DiversityChartConfig,
    DiversityChartGenerator,
    SampleGrouper
)


class TestDiversityAnalyzerBasic:
    """Basic tests for DiversityAnalyzer initialization."""
    
    def test_analyzer_initialization(self):
        """Test that analyzer initializes correctly with valid data."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'B', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR1', 'CDR2', 'CDR4'],
            'copy': [100, 50, 25, 80, 60, 40]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        
        assert len(analyzer.samples) == 2
        assert 'A' in analyzer.samples
        assert 'B' in analyzer.samples
    
    def test_analyzer_with_empty_data(self):
        """Test that analyzer handles empty data gracefully."""
        data = pd.DataFrame()
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        
        assert len(analyzer.samples) == 0
    
    def test_analyzer_with_custom_config(self):
        """Test that analyzer accepts custom chart configuration."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR1'],
            'copy': [100, 200]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        config = DiversityChartConfig(title="Test", bar_width=0.6)
        
        analyzer = DiversityAnalyzer(data, field_mapping, config)
        
        assert analyzer.chart_config.title == "Test"
        assert analyzer.chart_config.bar_width == 0.6


class TestD50Calculation:
    """Tests for D50 diversity metric calculation."""
    
    def test_d50_single_clone(self):
        """Test D50 with single clone (should be 1)."""
        data = pd.DataFrame({
            'sample': ['A'],
            'CDR3(pep)': ['CDR1'],
            'copy': [100]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        d50 = analyzer.calculate_d50('A')
        
        assert d50 == 1.0
    
    def test_d50_equal_distribution(self):
        """Test D50 with equal clone distribution."""
        # 4 clones with equal abundance - need 2 to reach 50%
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'A'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR4'],
            'copy': [25, 25, 25, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        d50 = analyzer.calculate_d50('A')
        
        assert d50 == 2.0
    
    def test_d50_skewed_distribution(self):
        """Test D50 with skewed clone distribution."""
        # One dominant clone with 60% of total
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'A'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR4'],
            'copy': [60, 20, 15, 5]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        d50 = analyzer.calculate_d50('A')
        
        # First clone (60) already exceeds 50% of total (100)
        assert d50 == 1.0
    
    def test_d50_all_samples(self):
        """Test D50 calculation for all samples."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR2', 'CDR3', 'CDR4'],
            'copy': [60, 40, 25, 25, 25, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        d50_series = analyzer.calculate_d50()
        
        assert isinstance(d50_series, pd.Series)
        assert 'A' in d50_series.index
        assert 'B' in d50_series.index


class TestGiniCalculation:
    """Tests for Gini index calculation."""
    
    def test_gini_perfect_equality(self):
        """Test Gini index with perfect equality (should be 0)."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'A'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR4'],
            'copy': [25, 25, 25, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        gini = analyzer.calculate_gini('A')
        
        # Perfect equality should give Gini close to 0
        assert abs(gini) < 0.01
    
    def test_gini_high_inequality(self):
        """Test Gini index with high inequality."""
        # One clone dominates
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'A'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR4'],
            'copy': [97, 1, 1, 1]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        gini = analyzer.calculate_gini('A')
        
        # High inequality should give Gini close to 1
        assert gini > 0.7
    
    def test_gini_range(self):
        """Test that Gini index is in valid range [0, 1]."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'B', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR1', 'CDR2', 'CDR3'],
            'copy': [50, 30, 20, 90, 5, 5]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        gini_series = analyzer.calculate_gini()
        
        for gini in gini_series.values:
            assert 0 <= gini <= 1


class TestShannonCalculation:
    """Tests for Shannon entropy calculation."""
    
    def test_shannon_single_clone(self):
        """Test Shannon entropy with single clone (should be 0)."""
        data = pd.DataFrame({
            'sample': ['A'],
            'CDR3(pep)': ['CDR1'],
            'copy': [100]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        shannon = analyzer.calculate_shannon('A')
        
        # Single clone has zero entropy
        assert shannon == 0.0
    
    def test_shannon_equal_distribution(self):
        """Test Shannon entropy with equal distribution."""
        # 4 clones with equal abundance: H = log2(4) = 2
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'A'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR4'],
            'copy': [25, 25, 25, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        shannon = analyzer.calculate_shannon('A')
        
        # Equal distribution of 4 clones: H = log2(4) = 2
        assert abs(shannon - 2.0) < 0.01
    
    def test_shannon_non_negative(self):
        """Test that Shannon entropy is non-negative."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR1', 'CDR2'],
            'copy': [50, 30, 20, 80, 20]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        shannon_series = analyzer.calculate_shannon()
        
        for shannon in shannon_series.values:
            assert shannon >= 0


class TestSimpsonCalculation:
    """Tests for Simpson index calculation."""
    
    def test_simpson_single_clone(self):
        """Test Simpson index with single clone (should be 0)."""
        data = pd.DataFrame({
            'sample': ['A'],
            'CDR3(pep)': ['CDR1'],
            'copy': [100]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        simpson = analyzer.calculate_simpson('A')
        
        # Single clone: 1 - 1^2 = 0
        assert simpson == 0.0
    
    def test_simpson_equal_distribution(self):
        """Test Simpson index with equal distribution."""
        # 4 clones with equal abundance: 1 - 4*(0.25)^2 = 1 - 0.25 = 0.75
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'A'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR4'],
            'copy': [25, 25, 25, 25]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        simpson = analyzer.calculate_simpson('A')
        
        # Equal distribution of 4 clones: 1 - 4*(0.25)^2 = 0.75
        assert abs(simpson - 0.75) < 0.01
    
    def test_simpson_range(self):
        """Test that Simpson index is in valid range [0, 1]."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'A', 'B', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR3', 'CDR1', 'CDR2', 'CDR3'],
            'copy': [50, 30, 20, 90, 5, 5]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        simpson_series = analyzer.calculate_simpson()
        
        for simpson in simpson_series.values:
            assert 0 <= simpson <= 1


class TestCalculateAllMetrics:
    """Tests for calculating all metrics at once."""
    
    def test_calculate_all_metrics_returns_all(self):
        """Test that calculate_all_metrics returns all four metrics."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [60, 40, 70, 30]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        metrics = analyzer.calculate_all_metrics()
        
        assert 'd50' in metrics.columns
        assert 'gini' in metrics.columns
        assert 'shannon' in metrics.columns
        assert 'simpson' in metrics.columns
        assert len(metrics) == 2  # Two samples
    
    def test_calculate_metric_by_name(self):
        """Test calculating a specific metric by name."""
        data = pd.DataFrame({
            'sample': ['A', 'A', 'B', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR2', 'CDR1', 'CDR3'],
            'copy': [60, 40, 70, 30]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        gini = analyzer.calculate_metric('gini')
        
        assert isinstance(gini, pd.Series)
        assert 'A' in gini.index
        assert 'B' in gini.index
    
    def test_calculate_metric_invalid_name(self):
        """Test that invalid metric name raises ValueError."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'CDR3(pep)': ['CDR1', 'CDR1'],
            'copy': [100, 200]
        })
        field_mapping = {'sample': 'sample', 'cdr3': 'CDR3(pep)', 'copy': 'copy'}
        
        analyzer = DiversityAnalyzer(data, field_mapping)
        
        with pytest.raises(ValueError):
            analyzer.calculate_metric('invalid_metric')


class TestSampleGrouper:
    """Tests for SampleGrouper class."""
    
    def test_set_groups(self):
        """Test setting sample groups."""
        metrics_df = pd.DataFrame({
            'd50': [5, 10, 8, 12],
            'gini': [0.3, 0.5, 0.4, 0.6]
        }, index=['A', 'B', 'C', 'D'])
        
        grouper = SampleGrouper(metrics_df)
        grouper.set_groups({
            'Group1': ['A', 'B'],
            'Group2': ['C', 'D']
        })
        
        groups = grouper.get_groups()
        assert 'Group1' in groups
        assert 'Group2' in groups
        assert groups['Group1'] == ['A', 'B']
    
    def test_set_groups_invalid_sample(self):
        """Test that invalid sample raises ValueError."""
        metrics_df = pd.DataFrame({
            'd50': [5, 10],
            'gini': [0.3, 0.5]
        }, index=['A', 'B'])
        
        grouper = SampleGrouper(metrics_df)
        
        with pytest.raises(ValueError):
            grouper.set_groups({'Group1': ['A', 'X']})  # X doesn't exist
    
    def test_calculate_group_averages(self):
        """Test calculating group averages."""
        metrics_df = pd.DataFrame({
            'd50': [4.0, 6.0, 8.0, 12.0],
            'gini': [0.2, 0.4, 0.5, 0.7]
        }, index=['A', 'B', 'C', 'D'])
        
        grouper = SampleGrouper(metrics_df)
        grouper.set_groups({
            'Group1': ['A', 'B'],
            'Group2': ['C', 'D']
        })
        
        averages = grouper.calculate_group_averages()
        
        # Group1 average d50: (4 + 6) / 2 = 5
        assert abs(averages.loc['Group1', 'd50'] - 5.0) < 0.01
        # Group2 average d50: (8 + 12) / 2 = 10
        assert abs(averages.loc['Group2', 'd50'] - 10.0) < 0.01
    
    def test_calculate_group_averages_no_groups(self):
        """Test that calculating averages without groups raises error."""
        metrics_df = pd.DataFrame({
            'd50': [5, 10],
            'gini': [0.3, 0.5]
        }, index=['A', 'B'])
        
        grouper = SampleGrouper(metrics_df)
        
        with pytest.raises(ValueError):
            grouper.calculate_group_averages()
    
    def test_calculate_percentage_difference(self):
        """Test calculating percentage difference between groups."""
        metrics_df = pd.DataFrame({
            'd50': [5.0, 5.0, 10.0, 10.0],
            'gini': [0.2, 0.2, 0.4, 0.4]
        }, index=['A', 'B', 'C', 'D'])
        
        grouper = SampleGrouper(metrics_df)
        grouper.set_groups({
            'Group1': ['A', 'B'],
            'Group2': ['C', 'D']
        })
        
        pct_diff = grouper.calculate_percentage_difference(baseline_group='Group1')
        
        # Group1 is baseline (100%)
        assert abs(pct_diff.loc['Group1', 'd50'] - 100.0) < 0.01
        # Group2 d50 is 200% of Group1
        assert abs(pct_diff.loc['Group2', 'd50'] - 200.0) < 0.01


class TestDiversityChartGenerator:
    """Tests for DiversityChartGenerator."""
    
    def test_generator_initialization(self):
        """Test that generator initializes correctly."""
        generator = DiversityChartGenerator()
        assert generator.default_config is not None
    
    def test_generator_with_custom_config(self):
        """Test generator with custom configuration."""
        config = DiversityChartConfig(
            title="Test Chart",
            bar_width=0.6
        )
        generator = DiversityChartGenerator(config)
        
        assert generator.default_config.title == "Test Chart"
        assert generator.default_config.bar_width == 0.6
    
    def test_generate_comparison_chart(self):
        """Test generating a comparison chart."""
        data = pd.DataFrame({
            'd50': [5, 10, 8],
            'gini': [0.3, 0.5, 0.4]
        }, index=['A', 'B', 'C'])
        
        generator = DiversityChartGenerator()
        image_bytes, metadata = generator.generate_comparison_chart(
            data,
            metrics=['d50', 'gini']
        )
        
        assert len(image_bytes) > 0
        assert metadata['metrics'] == ['d50', 'gini']
        assert metadata['samples'] == ['A', 'B', 'C']
    
    def test_generate_single_metric_chart(self):
        """Test generating a single metric chart."""
        data = pd.DataFrame({
            'd50': [5, 10, 8]
        }, index=['A', 'B', 'C'])
        
        generator = DiversityChartGenerator()
        image_bytes, metadata = generator.generate_single_metric_chart(
            data,
            metric='d50'
        )
        
        assert len(image_bytes) > 0
        assert metadata['metric'] == 'd50'
        assert metadata['samples'] == ['A', 'B', 'C']
    
    def test_generate_percentage_difference_chart(self):
        """Test generating a percentage difference chart."""
        data = pd.DataFrame({
            'd50': [100.0, 150.0, 200.0],
            'gini': [100.0, 120.0, 140.0]
        }, index=['Group1', 'Group2', 'Group3'])
        
        generator = DiversityChartGenerator()
        image_bytes, metadata = generator.generate_percentage_difference_chart(
            data,
            metrics=['d50', 'gini']
        )
        
        assert len(image_bytes) > 0
        assert 'baseline_label' in metadata
    
    def test_extract_data_table(self):
        """Test extracting data as table format."""
        data = pd.DataFrame({
            'd50': [5, 10],
            'gini': [0.3, 0.5]
        }, index=['A', 'B'])
        
        generator = DiversityChartGenerator()
        table = generator.extract_data_table(data)
        
        assert 'columns' in table
        assert 'data' in table
        assert 'row_count' in table
        assert table['row_count'] == 2
        assert 'Sample' in table['columns']
    
    def test_invalid_metric_raises_error(self):
        """Test that invalid metric raises ValueError."""
        data = pd.DataFrame({
            'd50': [5, 10]
        }, index=['A', 'B'])
        
        generator = DiversityChartGenerator()
        
        with pytest.raises(ValueError):
            generator.generate_single_metric_chart(data, metric='invalid_metric')
    
    def test_get_available_palettes(self):
        """Test getting available color palettes."""
        palettes = DiversityChartGenerator.get_available_palettes()
        
        assert 'default' in palettes
        assert 'pastel' in palettes
        assert 'colorblind' in palettes


class TestDiversityChartConfig:
    """Tests for DiversityChartConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = DiversityChartConfig()
        
        assert config.title == ""
        assert config.figure_width == 12
        assert config.figure_height == 8
        assert config.bar_width == 0.8
        assert config.dpi == 300
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = DiversityChartConfig(
            title="Custom Title",
            figure_width=15,
            bar_width=0.6,
            colors=['#ff0000', '#00ff00']
        )
        
        assert config.title == "Custom Title"
        assert config.figure_width == 15
        assert config.bar_width == 0.6
        assert config.colors == ['#ff0000', '#00ff00']
