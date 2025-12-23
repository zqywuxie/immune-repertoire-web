"""
Tests for the SequencingDepthAnalyzer and BarChartGenerator services.
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 7.6
"""
import pytest
import numpy as np
import pandas as pd

from services.sequencing_depth_analyzer import (
    SequencingDepthAnalyzer,
    BarChartConfig,
    BarChartGenerator
)


class TestSequencingDepthAnalyzerBasic:
    """Basic tests for SequencingDepthAnalyzer initialization."""
    
    def test_analyzer_initialization(self):
        """Test that analyzer initializes correctly with valid data."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'Total Receptor RNA': [100000, 150000],
            'Reads/UMI': [15.5, 16.2],
            'MigsGoodTotal': [95000, 140000],
            'ReadsGoodTotal': [4500000, 5000000]
        })
        field_mapping = {
            'sample': 'sample',
            'total_receptor_rna': 'Total Receptor RNA',
            'reads_umi': 'Reads/UMI',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal'
        }
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        
        assert len(analyzer.samples) == 2
        assert 'A' in analyzer.samples
        assert 'B' in analyzer.samples
    
    def test_analyzer_with_empty_data(self):
        """Test that analyzer handles empty data gracefully."""
        data = pd.DataFrame()
        field_mapping = {'sample': 'sample'}
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        
        assert len(analyzer.samples) == 0
    
    def test_get_metrics(self):
        """Test that get_metrics returns correct DataFrame."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'Total Receptor RNA': [100000, 150000],
            'Reads/UMI': [15.5, 16.2],
            'MigsGoodTotal': [95000, 140000],
            'ReadsGoodTotal': [4500000, 5000000]
        })
        field_mapping = {
            'sample': 'sample',
            'total_receptor_rna': 'Total Receptor RNA',
            'reads_umi': 'Reads/UMI',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal'
        }
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        metrics = analyzer.get_metrics()
        
        assert 'total_receptor_rna' in metrics.columns
        assert 'reads_umi' in metrics.columns
        assert metrics.loc['A', 'total_receptor_rna'] == 100000


class TestQualityMetricsCalculation:
    """Tests for quality metrics calculation (QC Rate and Final Utilization Rate)."""
    
    def test_calculate_qc_rate(self):
        """Test QC Rate calculation: MigsGoodTotal / Total Receptor RNA * 100."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'Total Receptor RNA': [100000, 200000],
            'MigsGoodTotal': [95000, 180000],
            'ReadsGoodTotal': [4500000, 5000000]
        })
        field_mapping = {
            'sample': 'sample',
            'total_receptor_rna': 'Total Receptor RNA',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal'
        }
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        qc_rate = analyzer.calculate_qc_rate()
        
        # QC Rate = MigsGoodTotal / Total Receptor RNA * 100
        # A: 95000 / 100000 * 100 = 95.0
        # B: 180000 / 200000 * 100 = 90.0
        assert abs(qc_rate['A'] - 95.0) < 0.01
        assert abs(qc_rate['B'] - 90.0) < 0.01
    
    def test_calculate_final_utilization_rate(self):
        """Test Final Utilization Rate calculation."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'Total Receptor RNA': [100000, 200000],
            'MigsGoodTotal': [95000, 180000],
            'ReadsGoodTotal': [4500000, 10000000]
        })
        field_mapping = {
            'sample': 'sample',
            'total_receptor_rna': 'Total Receptor RNA',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal'
        }
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        utilization = analyzer.calculate_final_utilization_rate()
        
        # Final Utilization Rate = ReadsGoodTotal / Total Receptor RNA * 100
        # A: 4500000 / 100000 * 100 = 4500.0
        # B: 10000000 / 200000 * 100 = 5000.0
        assert abs(utilization['A'] - 4500.0) < 0.01
        assert abs(utilization['B'] - 5000.0) < 0.01
    
    def test_calculate_quality_metrics(self):
        """Test that calculate_quality_metrics returns both metrics."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'Total Receptor RNA': [100000, 200000],
            'MigsGoodTotal': [95000, 180000],
            'ReadsGoodTotal': [4500000, 10000000]
        })
        field_mapping = {
            'sample': 'sample',
            'total_receptor_rna': 'Total Receptor RNA',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal'
        }
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        quality = analyzer.calculate_quality_metrics()
        
        assert 'qc_rate' in quality.columns
        assert 'final_utilization_rate' in quality.columns
    
    def test_qc_rate_with_zero_total_rna(self):
        """Test QC Rate handles zero Total Receptor RNA gracefully."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'Total Receptor RNA': [0, 200000],
            'MigsGoodTotal': [95000, 180000],
            'ReadsGoodTotal': [4500000, 10000000]
        })
        field_mapping = {
            'sample': 'sample',
            'total_receptor_rna': 'Total Receptor RNA',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal'
        }
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        qc_rate = analyzer.calculate_qc_rate()
        
        # Should return 0 for division by zero case
        assert qc_rate['A'] == 0.0
        assert abs(qc_rate['B'] - 90.0) < 0.01


class TestPercentageDifferenceCalculation:
    """Tests for percentage difference calculation."""
    
    def test_percentage_difference_with_baseline_sample(self):
        """Test percentage difference with specified baseline sample."""
        data = pd.DataFrame({
            'sample': ['A', 'B', 'C'],
            'Total Receptor RNA': [100000, 150000, 200000],
            'MigsGoodTotal': [95000, 140000, 190000],
            'ReadsGoodTotal': [4500000, 6000000, 8000000]
        })
        field_mapping = {
            'sample': 'sample',
            'total_receptor_rna': 'Total Receptor RNA',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal'
        }
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        pct_diff = analyzer.calculate_percentage_difference(baseline_sample='A')
        
        # A is baseline (100%), B = 150%, C = 200% for total_receptor_rna
        assert abs(pct_diff.loc['A', 'total_receptor_rna'] - 100.0) < 0.01
        assert abs(pct_diff.loc['B', 'total_receptor_rna'] - 150.0) < 0.01
        assert abs(pct_diff.loc['C', 'total_receptor_rna'] - 200.0) < 0.01
    
    def test_percentage_difference_with_minimum(self):
        """Test percentage difference using minimum values as baseline."""
        data = pd.DataFrame({
            'sample': ['A', 'B', 'C'],
            'Total Receptor RNA': [200000, 100000, 150000],
            'MigsGoodTotal': [190000, 95000, 140000],
            'ReadsGoodTotal': [8000000, 4500000, 6000000]
        })
        field_mapping = {
            'sample': 'sample',
            'total_receptor_rna': 'Total Receptor RNA',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal'
        }
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        pct_diff = analyzer.calculate_percentage_difference(use_minimum=True)
        
        # B has minimum total_receptor_rna (100000), so B = 100%
        # A = 200%, C = 150%
        assert abs(pct_diff.loc['B', 'total_receptor_rna'] - 100.0) < 0.01
        assert abs(pct_diff.loc['A', 'total_receptor_rna'] - 200.0) < 0.01
        assert abs(pct_diff.loc['C', 'total_receptor_rna'] - 150.0) < 0.01
    
    def test_percentage_difference_default_first_sample(self):
        """Test percentage difference uses first sample as default baseline."""
        data = pd.DataFrame({
            'sample': ['A', 'B'],
            'Total Receptor RNA': [100000, 150000],
            'MigsGoodTotal': [95000, 140000],
            'ReadsGoodTotal': [4500000, 6000000]
        })
        field_mapping = {
            'sample': 'sample',
            'total_receptor_rna': 'Total Receptor RNA',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal'
        }
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        pct_diff = analyzer.calculate_percentage_difference()
        
        # First sample (A) is baseline
        assert abs(pct_diff.loc['A', 'total_receptor_rna'] - 100.0) < 0.01
    
    def test_get_baseline_sample(self):
        """Test get_baseline_sample returns correct sample."""
        data = pd.DataFrame({
            'sample': ['A', 'B', 'C'],
            'Total Receptor RNA': [200000, 100000, 150000],
            'MigsGoodTotal': [190000, 95000, 140000],
            'ReadsGoodTotal': [8000000, 4500000, 6000000]
        })
        field_mapping = {
            'sample': 'sample',
            'total_receptor_rna': 'Total Receptor RNA',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal'
        }
        
        analyzer = SequencingDepthAnalyzer(data, field_mapping)
        
        # With use_minimum=True, should return B (minimum total_receptor_rna)
        baseline = analyzer.get_baseline_sample(use_minimum=True)
        assert baseline == 'B'
        
        # With use_minimum=False, should return first sample
        baseline = analyzer.get_baseline_sample(use_minimum=False)
        assert baseline == 'A'



class TestBarChartGenerator:
    """Tests for BarChartGenerator."""
    
    def test_generator_initialization(self):
        """Test that generator initializes correctly."""
        generator = BarChartGenerator()
        assert generator.default_config is not None
    
    def test_generator_with_custom_config(self):
        """Test generator with custom configuration."""
        config = BarChartConfig(
            title="Test Chart",
            bar_width=0.6,
            bar_spacing=0.3
        )
        generator = BarChartGenerator(config)
        
        assert generator.default_config.title == "Test Chart"
        assert generator.default_config.bar_width == 0.6
    
    def test_generate_comparison_chart(self):
        """Test generating a comparison chart."""
        data = pd.DataFrame({
            'total_receptor_rna': [100000, 150000],
            'migs_good_total': [95000, 140000]
        }, index=['A', 'B'])
        
        generator = BarChartGenerator()
        image_bytes, metadata = generator.generate_comparison_chart(
            data,
            metrics=['total_receptor_rna', 'migs_good_total']
        )
        
        assert len(image_bytes) > 0
        assert metadata['metrics'] == ['total_receptor_rna', 'migs_good_total']
        assert metadata['samples'] == ['A', 'B']
    
    def test_generate_single_metric_chart(self):
        """Test generating a single metric chart."""
        data = pd.DataFrame({
            'total_receptor_rna': [100000, 150000, 200000]
        }, index=['A', 'B', 'C'])
        
        generator = BarChartGenerator()
        image_bytes, metadata = generator.generate_single_metric_chart(
            data,
            metric='total_receptor_rna'
        )
        
        assert len(image_bytes) > 0
        assert metadata['metric'] == 'total_receptor_rna'
        assert metadata['samples'] == ['A', 'B', 'C']
    
    def test_generate_percentage_difference_chart(self):
        """Test generating a percentage difference chart."""
        data = pd.DataFrame({
            'total_receptor_rna': [100.0, 150.0, 200.0],
            'migs_good_total': [100.0, 147.4, 200.0]
        }, index=['A', 'B', 'C'])
        
        generator = BarChartGenerator()
        image_bytes, metadata = generator.generate_percentage_difference_chart(
            data,
            metrics=['total_receptor_rna', 'migs_good_total']
        )
        
        assert len(image_bytes) > 0
        assert 'baseline_label' in metadata
    
    def test_generate_quality_metrics_chart(self):
        """Test generating a quality metrics chart."""
        data = pd.DataFrame({
            'qc_rate': [95.0, 90.0],
            'final_utilization_rate': [4500.0, 5000.0]
        }, index=['A', 'B'])
        
        generator = BarChartGenerator()
        image_bytes, metadata = generator.generate_quality_metrics_chart(data)
        
        assert len(image_bytes) > 0
        assert 'qc_rate' in metadata['metrics'] or 'final_utilization_rate' in metadata['metrics']
    
    def test_extract_data_table(self):
        """Test extracting data as table format."""
        data = pd.DataFrame({
            'total_receptor_rna': [100000, 150000],
            'migs_good_total': [95000, 140000]
        }, index=['A', 'B'])
        
        generator = BarChartGenerator()
        table = generator.extract_data_table(data)
        
        assert 'columns' in table
        assert 'data' in table
        assert 'row_count' in table
        assert table['row_count'] == 2
        assert 'Sample' in table['columns']
    
    def test_get_available_palettes(self):
        """Test getting available color palettes."""
        palettes = BarChartGenerator.get_available_palettes()
        
        assert 'default' in palettes
        assert 'pastel' in palettes
        assert 'colorblind' in palettes
    
    def test_get_palette_colors(self):
        """Test getting colors for a specific palette."""
        colors = BarChartGenerator.get_palette_colors('default')
        
        assert len(colors) > 0
        assert all(c.startswith('#') for c in colors)
    
    def test_invalid_metric_raises_error(self):
        """Test that invalid metric raises ValueError."""
        data = pd.DataFrame({
            'total_receptor_rna': [100000, 150000]
        }, index=['A', 'B'])
        
        generator = BarChartGenerator()
        
        with pytest.raises(ValueError):
            generator.generate_single_metric_chart(data, metric='invalid_metric')
    
    def test_no_valid_metrics_raises_error(self):
        """Test that no valid metrics raises ValueError."""
        data = pd.DataFrame({
            'other_column': [100000, 150000]
        }, index=['A', 'B'])
        
        generator = BarChartGenerator()
        
        with pytest.raises(ValueError):
            generator.generate_comparison_chart(data, metrics=['invalid1', 'invalid2'])


class TestBarChartConfig:
    """Tests for BarChartConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = BarChartConfig()
        
        assert config.title == ""
        assert config.figure_width == 12
        assert config.figure_height == 8
        assert config.bar_width == 0.8
        assert config.bar_spacing == 0.2
        assert config.dpi == 300
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = BarChartConfig(
            title="Custom Title",
            figure_width=15,
            figure_height=10,
            bar_width=0.6,
            colors=['#ff0000', '#00ff00']
        )
        
        assert config.title == "Custom Title"
        assert config.figure_width == 15
        assert config.bar_width == 0.6
        assert config.colors == ['#ff0000', '#00ff00']
