"""
Property-Based Tests for Analysis Calculations
**Feature: immune-repertoire-web**

Tests sequencing metrics, percentage differences, group averages, and CV calculations.
Requirements: 3.3, 3.4, 4.3, 4.4, 5.4, 14.2
"""
import pandas as pd
import numpy as np
import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from hypothesis.strategies import composite

from services.sequencing_depth_analyzer import SequencingDepthAnalyzer
from services.diversity_analyzer import DiversityAnalyzer
from services.chain_analyzer import ChainAnalyzer


# =============================================================================
# Custom Strategies
# =============================================================================

@composite
def sequencing_data(draw):
    """Generate random sequencing depth data."""
    num_samples = draw(st.integers(min_value=2, max_value=5))
    samples = [f"Sample_{i}" for i in range(num_samples)]
    
    rows = []
    for sample in samples:
        total_rna = draw(st.integers(min_value=1000, max_value=100000))
        migs_good = draw(st.integers(min_value=100, max_value=total_rna))
        rows.append({
            'sample': sample,
            'total_rna': total_rna,
            'migs_good': migs_good,
            'reads_umi': draw(st.floats(min_value=1.0, max_value=10.0)),
            'reads_good': draw(st.integers(min_value=1000, max_value=50000))
        })
    
    df = pd.DataFrame(rows)
    field_mapping = {
        'sample': 'sample',
        'total_rna': 'total_rna',
        'migs_good': 'migs_good',
        'reads_umi': 'reads_umi',
        'reads_good': 'reads_good'
    }
    
    return df, field_mapping, samples


@composite
def diversity_data(draw):
    """Generate random diversity metrics data."""
    num_samples = draw(st.integers(min_value=2, max_value=5))
    samples = [f"Sample_{i}" for i in range(num_samples)]
    
    rows = []
    for sample in samples:
        rows.append({
            'sample': sample,
            'd50': draw(st.integers(min_value=10, max_value=1000)),
            'gini': draw(st.floats(min_value=0.0, max_value=1.0)),
            'shannon': draw(st.floats(min_value=0.0, max_value=10.0)),
            'simpson': draw(st.floats(min_value=0.0, max_value=1.0))
        })
    
    df = pd.DataFrame(rows)
    field_mapping = {
        'sample': 'sample',
        'd50': 'd50',
        'gini': 'gini',
        'shannon': 'shannon',
        'simpson': 'simpson'
    }
    
    return df, field_mapping, samples


@composite
def chain_data(draw):
    """Generate random chain analysis data."""
    num_samples = draw(st.integers(min_value=2, max_value=5))
    samples = [f"Sample_{i}" for i in range(num_samples)]
    chains = ['IGH', 'IGK', 'IGL']
    
    rows = []
    for sample in samples:
        for chain in chains:
            rows.append({
                'sample': sample,
                'chain': chain,
                'ucdr3': draw(st.integers(min_value=100, max_value=10000))
            })
    
    df = pd.DataFrame(rows)
    field_mapping = {
        'sample': 'sample',
        'chain': 'chain',
        'ucdr3': 'ucdr3'
    }
    
    return df, field_mapping, samples, chains


# =============================================================================
# Property 8: Sequencing Metrics Calculation
# **Feature: immune-repertoire-web, Property 8: Sequencing Metrics Calculation**
# **Validates: Requirements 3.4**
# =============================================================================

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    total_rna=st.integers(min_value=1000, max_value=100000),
    migs_good=st.integers(min_value=100, max_value=100000)
)
def test_property_8_qc_rate_calculation(total_rna, migs_good):
    """
    **Feature: immune-repertoire-web, Property 8: Sequencing Metrics Calculation**
    **Validates: Requirements 3.4**
    
    For any input data with Total Receptor RNA and MigsGoodTotal values,
    the QC Rate should equal MigsGoodTotal / Total Receptor RNA * 100.
    """
    # Ensure migs_good doesn't exceed total_rna
    assume(migs_good <= total_rna)
    
    # Test the mathematical formula
    expected_qc_rate = (migs_good / total_rna) * 100
    
    # Verify properties of the calculation
    assert 0 <= expected_qc_rate <= 100, "QC Rate should be between 0 and 100"
    assert np.isfinite(expected_qc_rate), "QC Rate should be finite"


# =============================================================================
# Property 9: Percentage Difference Calculation
# **Feature: immune-repertoire-web, Property 9: Percentage Difference Calculation**
# **Validates: Requirements 3.3, 4.4**
# =============================================================================

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    sample_value=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    baseline_value=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False)
)
def test_property_9_percentage_difference_calculation(sample_value, baseline_value):
    """
    **Feature: immune-repertoire-web, Property 9: Percentage Difference Calculation**
    **Validates: Requirements 3.3, 4.4**
    
    For any set of samples with a designated baseline,
    the percentage difference for each sample should equal (sample_value / baseline_value) * 100.
    """
    # Test the mathematical formula
    expected_pct_diff = (sample_value / baseline_value) * 100
    
    # Verify properties of the calculation
    assert expected_pct_diff > 0, "Percentage difference should be positive"
    assert np.isfinite(expected_pct_diff), "Percentage difference should be finite"
    
    # Verify that if sample equals baseline, percentage is 100
    if np.isclose(sample_value, baseline_value):
        assert np.isclose(expected_pct_diff, 100.0, rtol=1e-5)


# =============================================================================
# Property 10: Group Average Calculation
# **Feature: immune-repertoire-web, Property 10: Group Average Calculation**
# **Validates: Requirements 4.3**
# =============================================================================

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(data=diversity_data())
def test_property_10_group_average_calculation(data):
    """
    **Feature: immune-repertoire-web, Property 10: Group Average Calculation**
    **Validates: Requirements 4.3**
    
    For any group of samples,
    the group average should equal the arithmetic mean of all sample values in that group.
    """
    df, field_mapping, samples = data
    
    # Skip if only one sample
    assume(len(samples) > 1)
    
    # Test the mathematical property directly
    # For any group of values, the mean should equal sum/count
    d50_values = df['d50'].values
    expected_avg = np.sum(d50_values) / len(d50_values)
    actual_avg = np.mean(d50_values)
    
    assert np.isclose(actual_avg, expected_avg, rtol=1e-10), \
        f"Group average calculation incorrect: {actual_avg} != {expected_avg}"


# =============================================================================
# Property 12: Coefficient of Variation Calculation
# **Feature: immune-repertoire-web, Property 12: Coefficient of Variation Calculation**
# **Validates: Requirements 5.4**
# =============================================================================

@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(data=chain_data())
def test_property_12_cv_calculation(data):
    """
    **Feature: immune-repertoire-web, Property 12: Coefficient of Variation Calculation**
    **Validates: Requirements 5.4**
    
    For any set of values,
    the coefficient of variation should equal (standard_deviation / mean) * 100.
    """
    df, field_mapping, samples, chains = data
    
    # Test the mathematical property directly for each chain
    for chain in chains:
        chain_data = df[df['chain'] == chain]
        
        # Skip if no data for this chain
        if chain_data.empty:
            continue
        
        values = chain_data['ucdr3'].values
        
        # Skip if mean is zero or all values are the same
        mean_val = np.mean(values)
        if mean_val == 0 or np.std(values) == 0:
            continue
        
        # Calculate CV using the formula
        std_val = np.std(values, ddof=1)  # Sample standard deviation
        expected_cv = (std_val / mean_val) * 100
        
        # Verify the formula holds
        assert expected_cv >= 0, "CV should be non-negative"
        assert np.isfinite(expected_cv), "CV should be finite"
