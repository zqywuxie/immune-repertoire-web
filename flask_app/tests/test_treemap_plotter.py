"""Tests for treemap_plotter module."""
import tempfile
from pathlib import Path

import pytest

from flask_app.services.treemap_plotter import (
    generate_treemap,
    _load_plot_df,
    _normalize_sizes,
    _squarify_items,
    CANVAS_W,
    CANVAS_H,
)


def test_normalize_sizes():
    """Area normalization preserves total area and proportions."""
    result = _normalize_sizes([10.0, 20.0, 30.0], 100, 100)
    total = sum(result)
    assert abs(total - 10000) < 1.0  # dx * dy = 10000
    # Proportions preserved
    ratios = [r / total for r in result]
    assert abs(ratios[0] - 10/60) < 0.01
    assert abs(ratios[1] - 20/60) < 0.01
    assert abs(ratios[2] - 30/60) < 0.01


def test_normalize_sizes_empty():
    """Empty or zero-total values returns empty list."""
    assert _normalize_sizes([], 100, 100) == []
    assert _normalize_sizes([0.0, 0.0], 100, 100) == []


def test_squarify_items_basic():
    """Squarify produces rects within canvas bounds."""
    items = [
        {"name": "A", "value": 10},
        {"name": "B", "value": 20},
    ]
    rects = _squarify_items(items, 0, 0, 100, 100, "value")
    assert len(rects) == 2
    for r in rects:
        assert 0 <= r["x"] <= 100
        assert 0 <= r["y"] <= 100
        assert r["dx"] > 0
        assert r["dy"] > 0
    # Total area should approximate 10000
    total_area = sum(r["dx"] * r["dy"] for r in rects)
    assert abs(total_area - 10000) < 1.0


def test_generate_treemap_tetris(tmp_path):
    """Generate a Tetris treemap from a small CSV and verify output."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text("V,J,CDR3(pep),copy\nTRBV1,TRBJ1,CASSA,100\nTRBV1,TRBJ1,CASSB,50\nTRBV2,TRBJ2,CASSC,25\n")

    output_path = tmp_path / "output_tetris.png"
    result = generate_treemap(csv_path, output_path, mode="tetris")
    assert result.exists()
    assert result.stat().st_size > 1000  # should be a real image


def test_generate_treemap_qr(tmp_path):
    """Generate a QR treemap from a small CSV and verify output."""
    csv_path = tmp_path / "test_qr.csv"
    csv_path.write_text("V,J,CDR3(pep),copy\nTRBV1,TRBJ1,CASSA,100\nTRBV1,TRBJ1,CASSB,50\n")

    output_path = tmp_path / "output_qr.png"
    result = generate_treemap(csv_path, output_path, mode="qr")
    assert result.exists()
    assert result.stat().st_size > 1000


def test_generate_treemap_invalid_mode(tmp_path):
    """Invalid mode raises ValueError."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text("V,J,CDR3(pep),copy\nTRBV1,TRBJ1,CASSA,100\n")
    output_path = tmp_path / "output.png"
    with pytest.raises(ValueError, match="Unsupported mode"):
        generate_treemap(csv_path, output_path, mode="invalid")


def test_load_plot_df_min_count(tmp_path):
    """Rows with copy below min_count are filtered."""
    csv_path = tmp_path / "test_min.csv"
    csv_path.write_text("V,J,CDR3(pep),copy\nTRBV1,TRBJ1,CASSA,100\nTRBV1,TRBJ1,CASSB,0\n")

    df = _load_plot_df(csv_path, "CDR3(pep)", "copy", "V", "J", min_count=1)
    assert len(df) == 1
    assert df.iloc[0]["copy"] == 100


def test_load_plot_df_empty_raises(tmp_path):
    """Empty data after filtering raises ValueError."""
    csv_path = tmp_path / "test_empty.csv"
    csv_path.write_text("V,J,CDR3(pep),copy\n")
    with pytest.raises(ValueError):
        _load_plot_df(csv_path, "CDR3(pep)", "copy", "V", "J")
