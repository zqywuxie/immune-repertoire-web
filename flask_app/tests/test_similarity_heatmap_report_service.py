"""Tests for SimilarityHeatmapReportService HTML layout behavior."""

from pathlib import Path
from tempfile import TemporaryDirectory

from services.similarity_heatmap_report_service import SimilarityHeatmapReportService


def _matrix_payload() -> dict:
    return {
        "samples": ["SampleA", "SampleB"],
        "values": [
            [1.0, 0.42],
            [0.42, 1.0],
        ],
    }


def test_chain_mode_report_uses_chain_level_tabs():
    with TemporaryDirectory() as tmp_dir:
        service = SimilarityHeatmapReportService(results_root=Path(tmp_dir))
        heatmap_result = {
            "mode": "chain",
            "chains": {
                "IGH": {
                    "metrics": {"r2_inner": {"matrix_data": _matrix_payload()}},
                    "images": {"r2_inner": "ZmFrZV9pbWFnZQ=="},
                },
                "IGK": {
                    "metrics": {"r2_inner": {"matrix_data": _matrix_payload()}},
                    "images": {"r2_inner": "ZmFrZV9pbWFnZQ=="},
                },
            },
        }

        result = service.generate_report(heatmap_result=heatmap_result, output_name="chain_tabs")
        report_html = result.report_path.read_text(encoding="utf-8")

        assert report_html.count('class="chain-tab-btn') == 2
        assert 'class="chain-tab-btn active"' in report_html
        assert 'data-target="chain_panel_chain_IGH"' in report_html
        assert 'data-target="chain_panel_chain_IGK"' in report_html
        assert "Chain: IGH" in report_html
        assert "Chain: IGK" in report_html


def test_traditional_mode_report_does_not_render_chain_tabs():
    with TemporaryDirectory() as tmp_dir:
        service = SimilarityHeatmapReportService(results_root=Path(tmp_dir))
        heatmap_result = {
            "mode": "traditional",
            "metrics": {"r2_inner": {"matrix_data": _matrix_payload()}},
            "images": {"r2_inner": "ZmFrZV9pbWFnZQ=="},
        }

        result = service.generate_report(heatmap_result=heatmap_result, output_name="traditional_no_chain_tabs")
        report_html = result.report_path.read_text(encoding="utf-8")

        assert 'class="chain-tab-btn' not in report_html
