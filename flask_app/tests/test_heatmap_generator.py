"""
Tests for the HeatmapGenerator service.
Requirements: 2.3, 2.4, 6.1, 7.1, 7.5, 7.7
"""
import pytest
import numpy as np
import pandas as pd

from services.heatmap_generator import HeatmapGenerator, HeatmapConfig


class TestHeatmapConfig:
    """Tests for HeatmapConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = HeatmapConfig()
        
        assert config.title == ""
        assert config.color_scheme == "viridis"
        assert config.figure_width == 10
        assert config.figure_height == 8
        assert config.font_size == 12
        assert config.dpi == 300
        assert config.annotation is True
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = HeatmapConfig(
            title="Test Heatmap",
            color_scheme="plasma",
            figure_width=12,
            figure_height=10,
            dpi=150
        )
        
        assert config.title == "Test Heatmap"
        assert config.color_scheme == "plasma"
        assert config.figure_width == 12
        assert config.figure_height == 10
        assert config.dpi == 150


class TestHeatmapGenerator:
    """Tests for HeatmapGenerator class."""
    
    @pytest.fixture
    def sample_matrix(self):
        """Create a sample similarity matrix for testing."""
        data = np.array([
            [1.0, 0.8, 0.6],
            [0.8, 1.0, 0.7],
            [0.6, 0.7, 1.0]
        ])
        return pd.DataFrame(data, index=['A', 'B', 'C'], columns=['A', 'B', 'C'])
    
    def test_generator_initialization(self):
        """Test generator initializes correctly."""
        generator = HeatmapGenerator()
        
        assert generator.default_config is not None
        assert isinstance(generator.default_config, HeatmapConfig)
    
    def test_generator_with_custom_config(self):
        """Test generator with custom default config."""
        config = HeatmapConfig(title="Default Title", dpi=150)
        generator = HeatmapGenerator(config)
        
        assert generator.default_config.title == "Default Title"
        assert generator.default_config.dpi == 150
    
    def test_generate_heatmap_returns_bytes(self, sample_matrix):
        """Test that generate_heatmap returns PNG bytes."""
        generator = HeatmapGenerator()
        image_bytes, metadata = generator.generate_heatmap(sample_matrix)
        
        assert isinstance(image_bytes, bytes)
        assert len(image_bytes) > 0
        # Check PNG magic bytes
        assert image_bytes[:8] == b'\x89PNG\r\n\x1a\n'
    
    def test_generate_heatmap_returns_metadata(self, sample_matrix):
        """Test that generate_heatmap returns correct metadata."""
        config = HeatmapConfig(title="Test Matrix", dpi=150)
        generator = HeatmapGenerator()
        image_bytes, metadata = generator.generate_heatmap(sample_matrix, config)
        
        assert 'title' in metadata
        assert metadata['title'] == "Test Matrix"
        assert 'dpi' in metadata
        assert metadata['dpi'] == 150
        assert 'samples' in metadata
        assert metadata['samples'] == ['A', 'B', 'C']
    
    def test_generate_heatmap_with_metric_name(self, sample_matrix):
        """Test heatmap generation with metric name for color scheme."""
        generator = HeatmapGenerator()
        image_bytes, metadata = generator.generate_heatmap(
            sample_matrix, 
            metric_name='r2_inner'
        )
        
        assert metadata['metric_name'] == 'r2_inner'
        assert metadata['color_scheme'] == 'Greens'  # Default for r2_inner
    
    def test_get_available_palettes(self):
        """Test getting available color palettes."""
        palettes = HeatmapGenerator.get_available_palettes()
        
        assert isinstance(palettes, list)
        assert 'viridis' in palettes
        assert 'plasma' in palettes
        assert 'Greens' in palettes
    
    def test_get_metric_color_scheme(self):
        """Test getting default color scheme for metrics."""
        assert HeatmapGenerator.get_metric_color_scheme('r2_inner') == 'Greens'
        assert HeatmapGenerator.get_metric_color_scheme('r2_outer') == 'Purples'
        assert HeatmapGenerator.get_metric_color_scheme('cdr3_sharing') == 'Reds'
        assert HeatmapGenerator.get_metric_color_scheme('unknown') == 'viridis'


class TestCombinedHeatmaps:
    """Tests for combined heatmap generation."""
    
    @pytest.fixture
    def sample_matrices(self):
        """Create sample matrices for testing."""
        data = np.array([
            [1.0, 0.8],
            [0.8, 1.0]
        ])
        matrix = pd.DataFrame(data, index=['A', 'B'], columns=['A', 'B'])
        return {
            'r2_inner': matrix.copy(),
            'sorensen': matrix.copy()
        }
    
    def test_generate_combined_heatmaps(self, sample_matrices):
        """Test generating combined heatmaps."""
        generator = HeatmapGenerator()
        image_bytes, metadata = generator.generate_combined_heatmaps(
            sample_matrices,
            main_title="Combined Test"
        )
        
        assert isinstance(image_bytes, bytes)
        assert len(image_bytes) > 0
        assert metadata['main_title'] == "Combined Test"
        assert 'r2_inner' in metadata['metrics']
        assert 'sorensen' in metadata['metrics']
    
    def test_generate_combined_heatmaps_empty_raises(self):
        """Test that empty matrices dict raises ValueError."""
        generator = HeatmapGenerator()
        
        with pytest.raises(ValueError):
            generator.generate_combined_heatmaps({})
