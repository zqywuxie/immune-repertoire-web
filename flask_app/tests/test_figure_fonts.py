"""Container rendering and actual application imports preserve available Chinese fonts."""
import importlib
import logging
import warnings

import matplotlib.pyplot as plt
from matplotlib import font_manager, ft2font


def test_application_and_legacy_font_setup_render_chinese(tmp_path, caplog):
    from flask_app.app import create_app
    app = create_app("testing")
    from flask_app.services.analysis.base_module import PlotConfig
    from flask_app.services.figure_style import available_plot_fonts, apply_publication_style
    # These services previously overwrote the process-wide font list during imports.
    for module in ["integrated_analysis", "ppt_service", "sequencing_depth_ppt", "sequencing_depth_viz", "sequencing_reads_chart"]:
        importlib.import_module("flask_app.services." + module)
    PlotConfig.setup_chinese_font()
    apply_publication_style()
    installed = {font.name for font in font_manager.fontManager.ttflist}
    assert set(available_plot_fonts()) <= installed
    font_path = font_manager.findfont(font_manager.FontProperties(family=available_plot_fonts()[0]), fallback_to_default=False)
    glyphs = ft2font.FT2Font(font_path)
    assert all(glyphs.get_char_index(ord(character)) for character in "组库指标样本分组比较")
    caplog.clear()
    with warnings.catch_warnings(record=True) as caught, caplog.at_level(logging.WARNING, logger="matplotlib.font_manager"):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot([1, 2], [-1, 1])
        ax.set_title("组库指标与分组比较")
        ax.set_xlabel("样本编号")
        ax.set_ylabel("指标值")
        try:
            fig.savefig(tmp_path / "chinese.png")
            fig.savefig(tmp_path / "chinese.svg")
        finally:
            plt.close(fig)
    assert not any("Glyph" in str(item.message) and "missing" in str(item.message) for item in caught)
    assert not any("findfont" in record.getMessage() for record in caplog.records)
    assert (tmp_path / "chinese.png").stat().st_size > 1000
    assert "组库指标与分组比较" in (tmp_path / "chinese.svg").read_text()
