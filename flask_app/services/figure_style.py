"""
Publication-oriented matplotlib style helpers for analysis figures.

The palette intentionally uses muted red/blue accents on a white background:
clear enough for categorical contrast, but not dark or over-saturated.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap


PALETTE: Dict[str, str] = {
    "blue": "#5B7FCA",
    "blue_soft": "#AFC3E8",
    "red": "#C95D5A",
    "red_soft": "#E7B0A9",
    "teal": "#68A7A3",
    "violet": "#A98CC9",
    "green": "#8CBF88",
    "gold": "#D8B365",
    "neutral_light": "#D8DDE6",
    "neutral_mid": "#8A94A6",
    "neutral_dark": "#3F4652",
    "grid": "#E7EBF1",
}

MUTED_CATEGORY_COLORS: List[str] = [
    PALETTE["blue"],
    PALETTE["red"],
    PALETTE["teal"],
    PALETTE["violet"],
    PALETTE["green"],
    PALETTE["gold"],
    PALETTE["blue_soft"],
    PALETTE["red_soft"],
    PALETTE["neutral_mid"],
]

VOLCANO_COLORS = {
    "Up": PALETTE["red"],
    "Down": PALETTE["blue"],
    "Not Sig": "#B9C0CA",
}

MUTED_BLUE_RED_CMAP = LinearSegmentedColormap.from_list(
    "muted_blue_red",
    ["#F4F7FB", "#D9E4F4", PALETTE["blue"], "#F3E7E5", PALETTE["red_soft"], PALETTE["red"]],
)

MUTED_DIVERGING_CMAP = LinearSegmentedColormap.from_list(
    "muted_diverging_red_blue",
    [PALETTE["blue"], "#F7F7F7", PALETTE["red"]],
)


def apply_publication_style(font_size: float = 9.0, axes_linewidth: float = 0.85) -> None:
    """Apply a compact publication style with editable SVG/PDF text."""
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [
        "Arial",
        "DejaVu Sans",
        "Liberation Sans",
        "Microsoft YaHei",
        "SimHei",
        "sans-serif",
    ]
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["font.size"] = font_size
    plt.rcParams["font.weight"] = "bold"
    plt.rcParams["axes.titleweight"] = "bold"
    plt.rcParams["axes.labelweight"] = "bold"
    plt.rcParams["axes.spines.right"] = False
    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["axes.linewidth"] = axes_linewidth
    plt.rcParams["axes.edgecolor"] = PALETTE["neutral_dark"]
    plt.rcParams["axes.labelcolor"] = PALETTE["neutral_dark"]
    plt.rcParams["xtick.color"] = PALETTE["neutral_dark"]
    plt.rcParams["ytick.color"] = PALETTE["neutral_dark"]
    plt.rcParams["legend.frameon"] = False
    plt.rcParams["legend.title_fontsize"] = font_size
    plt.rcParams["axes.unicode_minus"] = False


def category_palette(labels: Iterable[object]) -> Dict[str, str]:
    """Return a stable muted color map for category labels."""
    unique_labels = [str(label) for label in labels]
    return {
        label: MUTED_CATEGORY_COLORS[index % len(MUTED_CATEGORY_COLORS)]
        for index, label in enumerate(unique_labels)
    }


def soften_axes(ax, grid_axis: str = "y") -> None:
    """Use light grid lines and restrained axis styling."""
    ax.grid(axis=grid_axis, color=PALETTE["grid"], linewidth=0.55, alpha=0.9)
    ax.set_axisbelow(True)
    ax.tick_params(width=0.65, length=2.4, colors=PALETTE["neutral_dark"])
    for spine in ax.spines.values():
        spine.set_color(PALETTE["neutral_dark"])
        spine.set_linewidth(0.7)
