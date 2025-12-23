"""
Tests for the Chain Analyzer Service.
Tests chain-specific analysis, visualization, and statistical calculations.
Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 12.2
"""
import pytest
import numpy as np
import pandas as pd

from services.chain_analyzer import (
    ChainAnalyzer,
    ChainChartConfig,
    ChainChartGenerator
)


@pytest.fixture
def sample_chain_data():
    """Create sample chain data for testing."""
    data = {
        'sample': ['S1', 'S1', 'S1', 'S2', 'S2', 'S2', 'S3', 'S3', 'S3'],
        'chain': ['IGH', 'IGK', 'TRB', 'IGH', 'IGK', 'TRB', 'IGH', 'IGK', 'TRB'],
        'cdr3': ['CASSF', 'CQQSY', 'CASSS', 'CASSF', 'CQQSY', 'CASST', 'CASSG', 'CQQST', 'CASSU'],
        'copy': [100, 50, 200, 150, 75, 180, 120, 60, 220]
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_field_mapping():
    """Create sample field mapping for testing."""
    return {
        'sample': 'sample',
        'chain': 'chain',
        'cdr3': 'cdr3',
        'copy': 'copy'
    }


@pytest.fixture
def chain_analyzer(sample_chain_data, sample_field_mapping):
    """Create a ChainAnalyzer instance for testing."""
    return ChainAnalyzer(sample_chain_data, sample_field_mapping)


@pytest.fixture
def chain_chart_generator():
    """Create a ChainChartGenerator instance for testing."""
    return ChainChartGenerator()


class TestChainAnalyzer:
    """Tests for ChainAnalyzer class."""
    
    def test_initialization(self, chain_analyzer):
        """Test ChainAnalyzer initialization."""
        assert chain_analyzer is not None
        assert len(chain_analyzer.samples) == 3
        assert set(chain_analyzer.samples) == {'S1', 'S2', 'S3'}
    
    def test_default_chains(self, chain_analyzer):
        """Test default chain support."""
        # Requirements: 5.1
        default_chains = ChainAnalyzer.DEFAULT_CHAINS
        assert 'IGH' in default_chains
        assert 'IGK' in default_chains
        assert 'IGL' in default_chains
        assert 'TRA' in default_chains
        assert 'TRB' in default_chains
        assert 'TRD' in default_chains
        assert 'TRG' in default_chains
        assert len(default_chains) == 7
    
    def test_chains_in_data(self, chain_analyzer):
        """Test detection of chains present in data."""
        # Requirements: 5.1
        chains = chain_analyzer.chains
        assert 'IGH' in chains
        assert 'IGK' in chains
        assert 'TRB' in chains
        assert len(chains) == 3
    
    def test_supported_chains(self, chain_analyzer):
        """Test supported chains list."""
        # Requirements: 5.1
        supported = chain_analyzer.supported_chains
        assert len(supported) == 7  # All default chains
        for chain in ChainAnalyzer.DEFAULT_CHAINS:
            assert chain in supported
    
    def test_add_custom_chain(self, chain_analyzer):
        """Test adding custom chain identifier."""
        # Requirements: 12.2
        chain_analyzer.add_custom_chain('CUSTOM1', 'Custom Chain 1')
        assert 'CUSTOM1' in chain_analyzer.supported_chains
        assert chain_analyzer.get_chain_description('CUSTOM1') == 'Custom Chain 1'
    
    def test_remove_custom_chain(self, chain_analyzer):
        """Test removing custom chain identifier."""
        # Requirements: 12.2
        chain_analyzer.add_custom_chain('CUSTOM2')
        assert 'CUSTOM2' in chain_analyzer.supported_chains
        
        result = chain_analyzer.remove_custom_chain('CUSTOM2')
        assert result is True
        assert 'CUSTOM2' not in chain_analyzer.supported_chains
    
    def test_cannot_remove_default_chain(self, chain_analyzer):
        """Test that default chains cannot be removed."""
        # Requirements: 12.2
        result = chain_analyzer.remove_custom_chain('IGH')
        assert result is False
        assert 'IGH' in chain_analyzer.supported_chains
    
    def test_get_chain_data(self, chain_analyzer):
        """Test getting data for a specific chain."""
        igh_data = chain_analyzer.get_chain_data('IGH')
        assert len(igh_data) == 3  # 3 samples with IGH
        assert all(igh_data['chain'] == 'IGH')
    
    def test_get_chain_description(self, chain_analyzer):
        """Test getting chain descriptions."""
        assert 'Heavy' in chain_analyzer.get_chain_description('IGH')
        assert 'Kappa' in chain_analyzer.get_chain_description('IGK')
        assert 'Custom' in chain_analyzer.get_chain_description('UNKNOWN')
    
    def test_calculate_chain_metrics_ucdr3(self, chain_analyzer):
        """Test calculating unique CDR3 count metrics."""
        # Requirements: 5.1
        metrics = chain_analyzer.calculate_chain_metrics(metric='ucdr3')
        
        assert not metrics.empty
        assert 'IGH' in metrics.columns
        assert 'IGK' in metrics.columns
        assert 'TRB' in metrics.columns
        
        # Each sample has 1 unique CDR3 per chain in test data
        for sample in ['S1', 'S2', 'S3']:
            assert metrics.loc[sample, 'IGH'] == 1
    
    def test_calculate_chain_metrics_total_reads(self, chain_analyzer):
        """Test calculating total reads metrics."""
        # Requirements: 5.1
        metrics = chain_analyzer.calculate_chain_metrics(metric='total_reads')
        
        assert not metrics.empty
        # S1 IGH has copy=100
        assert metrics.loc['S1', 'IGH'] == 100
        # S2 IGH has copy=150
        assert metrics.loc['S2', 'IGH'] == 150
    
    def test_calculate_chain_metrics_specific_chains(self, chain_analyzer):
        """Test calculating metrics for specific chains only."""
        # Requirements: 5.1
        metrics = chain_analyzer.calculate_chain_metrics(chains=['IGH', 'TRB'], metric='ucdr3')
        
        assert 'IGH' in metrics.columns
        assert 'TRB' in metrics.columns
        assert 'IGK' not in metrics.columns
    
    def test_calculate_cv(self, chain_analyzer):
        """Test CV calculation."""
        # Requirements: 5.4
        cv = chain_analyzer.calculate_cv(metric='total_reads')
        
        assert not cv.empty
        assert 'IGH' in cv.index
        assert 'IGK' in cv.index
        assert 'TRB' in cv.index
        
        # CV should be non-negative
        assert all(cv >= 0)
    
    def test_cv_formula(self, chain_analyzer):
        """Test that CV is calculated correctly: CV = (std / mean) * 100."""
        # Requirements: 5.4
        metrics = chain_analyzer.calculate_chain_metrics(metric='total_reads')
        cv = chain_analyzer.calculate_cv(metric='total_reads')
        
        for chain in cv.index:
            values = metrics[chain].values
            expected_cv = (np.std(values, ddof=0) / np.mean(values)) * 100
            assert abs(cv[chain] - expected_cv) < 0.0001
    
    def test_calculate_range_difference(self, chain_analyzer):
        """Test range difference calculation."""
        # Requirements: 5.4
        range_df = chain_analyzer.calculate_range_difference(metric='total_reads')
        
        assert not range_df.empty
        assert 'min' in range_df.columns
        assert 'max' in range_df.columns
        assert 'range' in range_df.columns
        assert 'range_percent' in range_df.columns
        
        # Range should equal max - min
        for chain in range_df.index:
            assert range_df.loc[chain, 'range'] == range_df.loc[chain, 'max'] - range_df.loc[chain, 'min']
    
    def test_calculate_statistics(self, chain_analyzer):
        """Test comprehensive statistics calculation."""
        # Requirements: 5.4
        stats = chain_analyzer.calculate_statistics(metric='total_reads')
        
        assert not stats.empty
        assert 'mean' in stats.columns
        assert 'std' in stats.columns
        assert 'cv' in stats.columns
        assert 'min' in stats.columns
        assert 'max' in stats.columns
        assert 'range' in stats.columns
        assert 'range_percent' in stats.columns


class TestChainChartGenerator:
    """Tests for ChainChartGenerator class."""
    
    def test_initialization(self, chain_chart_generator):
        """Test ChainChartGenerator initialization."""
        assert chain_chart_generator is not None
        assert chain_chart_generator.default_config is not None
    
    def test_generate_single_chain_chart(self, chain_analyzer, chain_chart_generator):
        """Test generating a single chain chart."""
        # Requirements: 5.2
        metrics = chain_analyzer.calculate_chain_metrics(metric='ucdr3')
        
        image_bytes, metadata = chain_chart_generator.generate_single_chain_chart(
            metrics, 'IGH'
        )
        
        assert image_bytes is not None
        assert len(image_bytes) > 0
        assert metadata['chain'] == 'IGH'
        assert 'samples' in metadata
    
    def test_generate_combined_comparison_chart(self, chain_analyzer, chain_chart_generator):
        """Test generating a combined comparison chart."""
        # Requirements: 5.3
        metrics = chain_analyzer.calculate_chain_metrics(metric='ucdr3')
        
        image_bytes, metadata = chain_chart_generator.generate_combined_comparison_chart(
            metrics, ['IGH', 'IGK', 'TRB']
        )
        
        assert image_bytes is not None
        assert len(image_bytes) > 0
        assert metadata['chains'] == ['IGH', 'IGK', 'TRB']
        assert 'samples' in metadata
    
    def test_generate_all_chain_charts(self, chain_analyzer, chain_chart_generator):
        """Test generating all chain charts (individual + combined)."""
        # Requirements: 5.2, 5.3
        metrics = chain_analyzer.calculate_chain_metrics(metric='ucdr3')
        
        individual_charts, combined_chart = chain_chart_generator.generate_all_chain_charts(
            metrics, ['IGH', 'IGK', 'TRB']
        )
        
        # Should have 3 individual charts (one per chain)
        assert len(individual_charts) == 3
        
        # Combined chart should exist
        assert combined_chart is not None
        assert len(combined_chart[0]) > 0  # image bytes
    
    def test_visualization_count_property(self, chain_analyzer, chain_chart_generator):
        """Test that N chains produce N+1 visualizations (N individual + 1 combined)."""
        # Requirements: 5.2, 5.3
        # Property 11: Chain-Specific Visualization Count
        metrics = chain_analyzer.calculate_chain_metrics(metric='ucdr3')
        chains = ['IGH', 'IGK']  # 2 chains
        
        individual_charts, combined_chart = chain_chart_generator.generate_all_chain_charts(
            metrics, chains
        )
        
        # N individual charts + 1 combined = N+1 total
        total_visualizations = len(individual_charts) + 1
        assert total_visualizations == len(chains) + 1
    
    def test_generate_statistics_chart(self, chain_analyzer, chain_chart_generator):
        """Test generating a statistics chart."""
        # Requirements: 5.4
        stats = chain_analyzer.calculate_statistics(metric='total_reads')
        
        image_bytes, metadata = chain_chart_generator.generate_statistics_chart(
            stats, 'cv'
        )
        
        assert image_bytes is not None
        assert len(image_bytes) > 0
        assert metadata['stat_type'] == 'cv'
    
    def test_extract_data_table(self, chain_analyzer, chain_chart_generator):
        """Test extracting data as table format."""
        # Requirements: 5.5, 5.6
        metrics = chain_analyzer.calculate_chain_metrics(metric='ucdr3')
        
        table_data = chain_chart_generator.extract_data_table(metrics)
        
        assert 'columns' in table_data
        assert 'data' in table_data
        assert 'row_count' in table_data
        assert 'Sample' in table_data['columns']
        assert table_data['row_count'] == 3  # 3 samples
    
    def test_extract_statistics_table(self, chain_analyzer, chain_chart_generator):
        """Test extracting statistics as table format."""
        # Requirements: 5.5, 5.6
        stats = chain_analyzer.calculate_statistics(metric='total_reads')
        
        table_data = chain_chart_generator.extract_statistics_table(stats)
        
        assert 'columns' in table_data
        assert 'data' in table_data
        assert 'row_count' in table_data
        assert 'Chain' in table_data['columns']
        assert 'CV (%)' in table_data['columns']
    
    def test_custom_config(self, chain_analyzer, chain_chart_generator):
        """Test using custom chart configuration."""
        metrics = chain_analyzer.calculate_chain_metrics(metric='ucdr3')
        
        custom_config = ChainChartConfig(
            title='Custom Title',
            figure_width=14,
            figure_height=10,
            dpi=150
        )
        
        image_bytes, metadata = chain_chart_generator.generate_single_chain_chart(
            metrics, 'IGH', custom_config
        )
        
        assert metadata['title'] == 'Custom Title'
        assert metadata['figure_size'] == (14, 10)
        assert metadata['dpi'] == 150
    
    def test_get_available_palettes(self, chain_chart_generator):
        """Test getting available color palettes."""
        palettes = ChainChartGenerator.get_available_palettes()
        
        assert 'default' in palettes
        assert 'pastel' in palettes
        assert 'bright' in palettes
        assert 'colorblind' in palettes
    
    def test_get_palette_colors(self, chain_chart_generator):
        """Test getting colors for a palette."""
        colors = ChainChartGenerator.get_palette_colors('default')
        
        assert len(colors) == 7  # 7 default colors
        assert all(c.startswith('#') for c in colors)


class TestChainAnalyzerEdgeCases:
    """Tests for edge cases in ChainAnalyzer."""
    
    def test_empty_data(self, sample_field_mapping):
        """Test handling of empty data."""
        empty_df = pd.DataFrame()
        analyzer = ChainAnalyzer(empty_df, sample_field_mapping)
        
        assert analyzer.samples == []
        assert analyzer.chains == []
    
    def test_missing_chain_column(self, sample_field_mapping):
        """Test handling of missing chain column."""
        data = pd.DataFrame({
            'sample': ['S1', 'S2'],
            'cdr3': ['CASSF', 'CASSG'],
            'copy': [100, 200]
        })
        analyzer = ChainAnalyzer(data, sample_field_mapping)
        
        assert analyzer.chains == []
    
    def test_chain_not_in_data(self, chain_analyzer, chain_chart_generator):
        """Test handling of chain not present in data."""
        metrics = chain_analyzer.calculate_chain_metrics(chains=['IGL'], metric='ucdr3')
        
        # IGL is not in test data, should return empty or zeros
        assert metrics.empty or (metrics['IGL'] == 0).all()
    
    def test_invalid_chain_in_chart(self, chain_analyzer, chain_chart_generator):
        """Test error handling for invalid chain in chart generation."""
        metrics = chain_analyzer.calculate_chain_metrics(metric='ucdr3')
        
        with pytest.raises(ValueError):
            chain_chart_generator.generate_single_chain_chart(metrics, 'INVALID_CHAIN')
    
    def test_no_valid_chains_in_comparison(self, chain_analyzer, chain_chart_generator):
        """Test error handling when no valid chains for comparison."""
        metrics = chain_analyzer.calculate_chain_metrics(metric='ucdr3')
        
        with pytest.raises(ValueError):
            chain_chart_generator.generate_combined_comparison_chart(
                metrics, ['INVALID1', 'INVALID2']
            )
