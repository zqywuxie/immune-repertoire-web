"""Apply explicit output preferences to a figure without changing statistical data."""
from matplotlib.text import Text


def save_analysis_figure(figure, buffer, parameters):
    config = parameters.get('chart_config') or {}
    size = config.get('figsize')
    if size:
        figure.set_size_inches(*size)
    font_size = config.get('font_size')
    if font_size:
        for text in figure.findobj(match=Text):
            text.set_fontsize(text.get_fontsize() * float(font_size) / 12)
    figure.savefig(buffer, format='png', dpi=config.get('dpi', 150), bbox_inches='tight', facecolor='white')
