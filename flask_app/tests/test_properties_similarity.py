"""
Property-Based Tests for Similarity Analysis
**Feature: immune-repertoire-web**

Tests similarity matrix calculations, export formats, and data table extraction.
Requirements: 2.3, 2.4, 2.5, 6.1, 6.2, 14.2
"""
import io
import os
import tempfile
from pathlib import Path
from PIL import Image

import pandas as pd
import numpy as np
import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from hypothesis.strategies import composite

from services.similarity_analyzer import SimilarityAnalyzer
from services.heatmap_generator import HeatmapGenerator, HeatmapConfig
from services.export_service import ExportService
from services.data_table import DataTableService


# =============================================================================
# Custom Strategies for Generating Test Data
# =============================================================================

@composite
def sample_repertoire_data(draw):
    """Generate random immune repertoire data for testing."""
    # Generate 2-5 samples
    num_samples = draw(st.integers(min_value=2, max_value=5))
    samples = [f"Sample_{i}" for i in range(num_samples)]
    
    # Generate CDR3 sequences (shared pool)
    num_cdr3 = draw(st.integers(min_value=5, max_value=20))
    cdr3_pool = [f"CDR3_{i}" for i in range(num_cdr3)]
    
    # Generate data rows
    rows = []
    for sample in samples:
        # Each sample has a subset of CDR3 sequences
        num_cdr3_in_sample = draw(st.integers(min_value=2, max_value=num_cdr3))
        sample_cdr3 = draw(st.lists(
            st.sampled_from(cdr3_pool),
            min_size=num_cdr3_in_sample,
            max_size=num_cdr3_in_sample,
            unique=True
        ))
        
        for cdr3 in sample_cdr3:
            copy_count = draw(st.integers(min_value=1, max_value=1000))
            rows.append({
                'sample': sample,
                'cdr3': cdr3,
                'copy': copy_count
            })
    
    df = pd.DataFrame(rows)
    field_mapping = {'sample': 'sample', 'cdr3': 'cdr3', 'copy': 'copy'}
    
    return df, field_mapping, samples


# =============================================================================
# Property 5: Similarity Matrix Symmetry
# **Feature: immune-repertoire-web, Property 5: Similarity Matrix Symmetry**
# **Validates: Requirements 2.3**
# =============================================================================

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(data=sample_repertoire_data())
def test_property_5_r2_inner_symmetry(data):
    """
    **Feature: immune-repertoire-web, Property 5: Similarity Matrix Symmetry**
    **Validates: Requirements 2.3**
    
    For any symmetric similarity metric (R² inner),
    the resulting similarity matrix should be symmetric: matrix[i][j] == matrix[j][i].
    """
    df, field_mapping, samples = data
    
    analyzer = SimilarityAnalyzer(df, field_mapping)
    matrix = analyzer.calculate_r2_inner()
    
    # Check symmetry
    for i in range(len(samples)):
        for j in range(len(samples)):
            assert np.isclose(matrix.iloc[i, j], matrix.iloc[j, i]), \
                f"Matrix not symmetric at ({i}, {j}): {matrix.iloc[i, j]} != {matrix.iloc[j, i]}"


@settings(max_examples=100)
@given(data=sample_repertoire_data())
def test_property_5_r2_outer_symmetry(data):
    """
    **Feature: immune-repertoire-web, Property 5: Similarity Matrix Symmetry**
    **Validates: Requirements 2.3**
    
    For any symmetric similarity metric (R² outer),
    the resulting similarity matrix should be symmetric.
    """
    df, field_mapping, samples = data
    
    analyzer = SimilarityAnalyzer(df, field_mapping)
    matrix = analyzer.calculate_r2_outer()
    
    # Check symmetry
    for i in range(len(samples)):
        for j in range(len(samples)):
            assert np.isclose(matrix.iloc[i, j], matrix.iloc[j, i]), \
                f"Matrix not symmetric at ({i}, {j})"


@settings(max_examples=100)
@given(data=sample_repertoire_data())
def test_property_5_morisita_horn_symmetry(data):
    """
    **Feature: immune-repertoire-web, Property 5: Similarity Matrix Symmetry**
    **Validates: Requirements 2.3**
    
    For any symmetric similarity metric (Morisita-Horn),
    the resulting similarity matrix should be symmetric.
    """
    df, field_mapping, samples = data
    
    analyzer = SimilarityAnalyzer(df, field_mapping)
    matrix = analyzer.calculate_morisita_horn()
    
    # Check symmetry
    for i in range(len(samples)):
        for j in range(len(samples)):
            assert np.isclose(matrix.iloc[i, j], matrix.iloc[j, i]), \
                f"Matrix not symmetric at ({i}, {j})"


@settings(max_examples=100)
@given(data=sample_repertoire_data())
def test_property_5_sorensen_symmetry(data):
    """
    **Feature: immune-repertoire-web, Property 5: Similarity Matrix Symmetry**
    **Validates: Requirements 2.3**
    
    For any symmetric similarity metric (Sorensen),
    the resulting similarity matrix should be symmetric.
    """
    df, field_mapping, samples = data
    
    analyzer = SimilarityAnalyzer(df, field_mapping)
    matrix = analyzer.calculate_sorensen()
    
    # Check symmetry
    for i in range(len(samples)):
        for j in range(len(samples)):
            assert np.isclose(matrix.iloc[i, j], matrix.iloc[j, i]), \
                f"Matrix not symmetric at ({i}, {j})"


# =============================================================================
# Property 6: Similarity Matrix Diagonal
# **Feature: immune-repertoire-web, Property 6: Similarity Matrix Diagonal**
# **Validates: Requirements 2.3**
# =============================================================================

@settings(max_examples=100)
@given(data=sample_repertoire_data())
def test_property_6_diagonal_values(data):
    """
    **Feature: immune-repertoire-web, Property 6: Similarity Matrix Diagonal**
    **Validates: Requirements 2.3**
    
    For any similarity matrix,
    the diagonal values should all equal 1.0 (a sample is perfectly similar to itself).
    """
    df, field_mapping, samples = data
    
    analyzer = SimilarityAnalyzer(df, field_mapping)
    
    # Test all metrics
    metrics = [
        analyzer.calculate_r2_inner(),
        analyzer.calculate_r2_outer(),
        analyzer.calculate_cdr3_sharing(),
        analyzer.calculate_expression_sharing(),
        analyzer.calculate_morisita_horn(),
        analyzer.calculate_sorensen()
    ]
    
    for matrix in metrics:
        for i in range(len(samples)):
            diagonal_value = matrix.iloc[i, i]
            assert np.isclose(diagonal_value, 1.0), \
                f"Diagonal value at ({i}, {i}) is {diagonal_value}, expected 1.0"


# =============================================================================
# Property 7: Export Format Validity
# **Feature: immune-repertoire-web, Property 7: Export Format Validity**
# **Validates: Requirements 2.4, 6.1, 6.2**
# =============================================================================

@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(data=sample_repertoire_data())
def test_property_7_png_export_validity(data):
    """
    **Feature: immune-repertoire-web, Property 7: Export Format Validity**
    **Validates: Requirements 2.4, 6.1, 6.2**
    
    For any PNG export request,
    the returned file should be a valid PNG image.
    """
    df, field_mapping, samples = data
    
    analyzer = SimilarityAnalyzer(df, field_mapping)
    matrix = analyzer.calculate_r2_inner()
    
    # Generate heatmap
    config = HeatmapConfig(title="Test Heatmap")
    generator = HeatmapGenerator(config=config)
    png_bytes, metadata = generator.generate_heatmap(
        matrix=matrix,
        config=config
    )
    
    # Verify it's a valid PNG
    try:
        img = Image.open(io.BytesIO(png_bytes))
        assert img.format == 'PNG'
        assert img.size[0] > 0 and img.size[1] > 0
    except Exception as e:
        pytest.fail(f"Invalid PNG image: {e}")


@settings(max_examples=50)
@given(data=sample_repertoire_data())
def test_property_7_csv_export_validity(data):
    """
    **Feature: immune-repertoire-web, Property 7: Export Format Validity**
    **Validates: Requirements 2.4, 6.1, 6.2**
    
    For any CSV export request,
    the returned file should be a valid CSV with headers matching the matrix dimensions.
    """
    df, field_mapping, samples = data
    
    analyzer = SimilarityAnalyzer(df, field_mapping)
    matrix = analyzer.calculate_r2_inner()
    
    # Export to CSV
    csv_buffer = io.StringIO()
    matrix.to_csv(csv_buffer)
    csv_content = csv_buffer.getvalue()
    
    # Verify it's valid CSV
    try:
        df_loaded = pd.read_csv(io.StringIO(csv_content), index_col=0)
        assert df_loaded.shape == matrix.shape
        assert list(df_loaded.columns) == list(matrix.columns)
        assert list(df_loaded.index) == list(matrix.index)
    except Exception as e:
        pytest.fail(f"Invalid CSV format: {e}")


# =============================================================================
# Property 23: Data Table Extraction Consistency
# **Feature: immune-repertoire-web, Property 23: Data Table Extraction Consistency**
# **Validates: Requirements 2.5, 3.5, 4.5, 5.5**
# =============================================================================

@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(data=sample_repertoire_data())
def test_property_23_data_table_extraction_consistency(data):
    """
    **Feature: immune-repertoire-web, Property 23: Data Table Extraction Consistency**
    **Validates: Requirements 2.5, 3.5, 4.5, 5.5**
    
    For any analysis result with a data table,
    the table data should match the underlying calculation results exactly.
    """
    df, field_mapping, samples = data
    
    analyzer = SimilarityAnalyzer(df, field_mapping)
    matrix = analyzer.calculate_r2_inner()
    
    # Extract data table
    table_service = DataTableService()
    table_data = table_service.matrix_to_table(matrix)
    
    # Verify table data matches matrix
    assert 'columns' in table_data
    assert 'data' in table_data
    assert 'row_count' in table_data
    
    # Check dimensions
    assert table_data['row_count'] == len(samples)
    assert len(table_data['columns']) == len(samples) + 1  # +1 for index column
    
    # Check data consistency
    for i, row in enumerate(table_data['data']):
        sample_name = samples[i]
        # Columns is a list of dicts with 'name' key
        first_col_name = table_data['columns'][0]['name']
        assert row[first_col_name] == sample_name  # First column is index
        
        # Check values match matrix (accounting for rounding to 4 decimal places)
        for j in range(len(samples)):
            col_name = table_data['columns'][j + 1]['name']
            table_value = row[col_name]
            matrix_value = round(matrix.iloc[i, j], 4)  # Table rounds to 4 decimals
            assert np.isclose(table_value, matrix_value, rtol=1e-4), \
                f"Table value at ({i}, {j}) doesn't match matrix: {table_value} != {matrix_value}"
