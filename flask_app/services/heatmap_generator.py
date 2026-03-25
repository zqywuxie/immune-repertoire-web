"""
Heatmap Generator Service for the Immune Repertoire Analysis Web Application.
Generates heatmap visualizations for similarity matrices.
Requirements: 2.3, 2.4, 6.1, 7.1, 7.5, 7.7
"""
import io
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd


def format_similarity_value(value: Any, precision: int = 4) -> str:
    """
    Format similarity values for table/annotation display.

    - Non-numeric/NaN/Inf -> '-'
    - Values very close to 0 or 1 are normalized to 0.0000 / 1.0000
    - Other numeric values use fixed decimal precision
    """
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"

    if np.isnan(numeric) or np.isinf(numeric):
        return "-"

    epsilon = 10 ** (-(precision + 2))
    if abs(numeric) < epsilon:
        numeric = 0.0
    elif abs(numeric - 1.0) < epsilon:
        numeric = 1.0

    return f"{numeric:.{precision}f}"


def normalize_sample_order(
    available_samples: List[str],
    requested_order: Optional[List[str]] = None
) -> List[str]:
    """
    Normalize sample ordering while preserving stable behavior.

    Rules:
    - keep original order when no custom order is provided
    - include requested samples first (intersection only, de-duplicated)
    - append remaining available samples in original order
    """
    if not available_samples:
        return []

    available_unique = list(dict.fromkeys(available_samples))
    if not requested_order:
        return available_unique

    if not isinstance(requested_order, (list, tuple)):
        return available_unique

    available_set = set(available_unique)
    ordered_samples: List[str] = []
    seen = set()

    for sample in requested_order:
        if sample in available_set and sample not in seen:
            ordered_samples.append(sample)
            seen.add(sample)

    for sample in available_unique:
        if sample not in seen:
            ordered_samples.append(sample)

    return ordered_samples


@dataclass
class HeatmapConfig:
    """
    Configuration for heatmap visualization.
    Uses clean, simple defaults for clear readability.
    Requirements: 7.1, 7.5, 7.7, 15.3, 16.1, 16.2, 16.3, 16.5
    """
    title: str = ""
    plot_type: str = "heatmap"
    color_scheme: str = "viridis"  # Clear, readable default
    figure_width: int = 10
    figure_height: int = 8
    font_size: int = 12
    dpi: int = 300
    annotation: bool = True
    annotation_format: str = ".2f"  # Simplified to 2 decimal places
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    square: bool = True
    linewidths: float = 0.5
    linecolor: str = "#e0e0e0"  # Light gray for subtle grid
    mask_diagonal: bool = False
    cbar_label: str = "相似度"  # Chinese label
    cbar_shrink: float = 0.8
    x_label: str = "样本"  # Chinese label
    y_label: str = "样本"  # Chinese label
    x_rotation: int = 45
    y_rotation: int = 0


class HeatmapGenerator:
    """
    Generator for heatmap visualizations.
    Supports customizable color schemes, titles, dimensions, and fonts.
    Requirements: 2.3, 2.4, 6.1, 7.1, 7.5, 7.7
    """
    
    # Predefined color schemes for different metrics
    METRIC_COLOR_SCHEMES = {
        'r2_inner': 'Greens',
        'r2_outer': 'Purples',
        'cdr3_sharing': 'Reds',
        'expression_sharing': 'Blues',
        'morisita_horn': 'Oranges',
        'sorensen': 'YlGnBu',
        'default': 'viridis'
    }
    
    # Available color palettes
    AVAILABLE_PALETTES = [
        'viridis', 'plasma', 'inferno', 'magma', 'cividis',
        'Greens', 'Blues', 'Reds', 'Purples', 'Oranges',
        'YlGnBu', 'YlOrRd', 'RdYlBu', 'RdYlBu_r', 'coolwarm',
        'RdBu', 'RdBu_r', 'BrBG', 'PiYG', 'PRGn'
    ]

    AVAILABLE_PLOT_TYPES = ['heatmap', 'treemap']
    
    def __init__(self, config: Optional[HeatmapConfig] = None):
        """
        Initialize the heatmap generator.
        
        Args:
            config: Optional default configuration for heatmaps
        """
        self.default_config = config or HeatmapConfig()
        
        # Set up matplotlib for clean, readable output
        # Requirements: 16.1, 16.2, 16.3, 16.5
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        # Simplified styling - clean and professional
        plt.rcParams['figure.facecolor'] = 'white'
        plt.rcParams['axes.facecolor'] = 'white'
        plt.rcParams['axes.edgecolor'] = '#495057'
        plt.rcParams['axes.linewidth'] = 1.0
        plt.rcParams['axes.labelcolor'] = '#212529'
        plt.rcParams['axes.titlesize'] = 12
        plt.rcParams['axes.labelsize'] = 10
        plt.rcParams['xtick.color'] = '#495057'
        plt.rcParams['ytick.color'] = '#495057'
        plt.rcParams['xtick.labelsize'] = 9
        plt.rcParams['ytick.labelsize'] = 9
        plt.rcParams['grid.color'] = '#dee2e6'
        plt.rcParams['grid.linestyle'] = '-'
        plt.rcParams['grid.linewidth'] = 0.5
        plt.rcParams['grid.alpha'] = 0.2
    
    def generate_heatmap(
        self,
        matrix: pd.DataFrame,
        config: Optional[HeatmapConfig] = None,
        metric_name: Optional[str] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a heatmap visualization from a similarity matrix.
        
        Args:
            matrix: Similarity matrix as DataFrame
            config: Optional configuration (uses default if not provided)
            metric_name: Optional metric name for automatic color scheme selection
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 2.3, 2.4, 6.1, 7.1, 7.5, 7.7
        """
        cfg = config or self.default_config
        
        # Select color scheme based on metric name if not specified
        if metric_name and cfg.color_scheme == self.default_config.color_scheme:
            cmap = self.METRIC_COLOR_SCHEMES.get(metric_name, cfg.color_scheme)
        else:
            cmap = cfg.color_scheme

        plot_type = (cfg.plot_type or 'heatmap').lower()
        if plot_type not in self.AVAILABLE_PLOT_TYPES:
            raise ValueError(f"Unsupported plot type: {plot_type}")

        if plot_type == 'treemap':
            return self._generate_treemap(matrix, cfg, cmap, metric_name)

        return self._generate_standard_heatmap(matrix, cfg, cmap, metric_name)

    def _generate_standard_heatmap(
        self,
        matrix: pd.DataFrame,
        cfg: HeatmapConfig,
        cmap: str,
        metric_name: Optional[str] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Generate the default matrix heatmap visualization."""
        vmin, vmax = self._calculate_value_range(matrix, cfg)

        fig, ax = plt.subplots(figsize=(cfg.figure_width, cfg.figure_height))

        mask = None
        if cfg.mask_diagonal:
            mask = np.eye(len(matrix), dtype=bool)

        sns.heatmap(
            matrix,
            annot=cfg.annotation,
            fmt=cfg.annotation_format,
            cmap=cmap,
            mask=mask,
            vmin=vmin,
            vmax=vmax,
            square=cfg.square,
            linewidths=cfg.linewidths,
            linecolor=cfg.linecolor,
            cbar_kws={'label': cfg.cbar_label, 'shrink': cfg.cbar_shrink},
            ax=ax,
            annot_kws={'fontsize': cfg.font_size - 2}
        )

        if cfg.title:
            ax.set_title(cfg.title, fontsize=cfg.font_size + 2, fontweight='600', pad=15)
        ax.set_xlabel(cfg.x_label, fontsize=cfg.font_size)
        ax.set_ylabel(cfg.y_label, fontsize=cfg.font_size)
        ax.tick_params(axis='x', rotation=cfg.x_rotation, labelsize=cfg.font_size - 1)
        ax.tick_params(axis='y', rotation=cfg.y_rotation, labelsize=cfg.font_size - 1)

        plt.tight_layout()

        image_bytes = self._save_figure(fig, cfg)
        metadata = {
            'title': cfg.title,
            'plot_type': 'heatmap',
            'color_scheme': cmap,
            'figure_size': (cfg.figure_width, cfg.figure_height),
            'dpi': cfg.dpi,
            'vmin': vmin,
            'vmax': vmax,
            'samples': matrix.index.tolist(),
            'metric_name': metric_name
        }
        return image_bytes, metadata

    def _generate_treemap(
        self,
        matrix: pd.DataFrame,
        cfg: HeatmapConfig,
        cmap: str,
        metric_name: Optional[str] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Generate a treemap using per-sample aggregate similarity as area and color."""
        sample_scores = self._calculate_treemap_scores(matrix)
        normalized_sizes = self._normalize_treemap_sizes(sample_scores.values)
        rectangles = self._compute_treemap_rectangles(normalized_sizes)

        fig, ax = plt.subplots(figsize=(cfg.figure_width, cfg.figure_height))
        vmin, vmax = self._calculate_treemap_color_range(sample_scores.values)
        norm = plt.Normalize(vmin=vmin, vmax=vmax)
        colormap = plt.get_cmap(cmap)

        for (x, y, dx, dy), (sample_name, score) in zip(rectangles, sample_scores.items()):
            patch = plt.Rectangle(
                (x, y),
                dx,
                dy,
                facecolor=colormap(norm(score)),
                edgecolor=cfg.linecolor,
                linewidth=max(cfg.linewidths, 0.8)
            )
            ax.add_patch(patch)

            if cfg.annotation:
                label = f"{sample_name}\n{format_similarity_value(score, precision=4)}"
            else:
                label = str(sample_name)

            text_size = max(cfg.font_size - 2, 8)
            ax.text(
                x + dx / 2,
                y + dy / 2,
                label,
                ha='center',
                va='center',
                fontsize=text_size,
                color=self._get_text_color_for_background(colormap(norm(score))),
                wrap=True,
                clip_on=True
            )

        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.invert_yaxis()
        ax.axis('off')

        if cfg.title:
            ax.set_title(cfg.title, fontsize=cfg.font_size + 2, fontweight='600', pad=15)

        scalar_mappable = plt.cm.ScalarMappable(norm=norm, cmap=colormap)
        scalar_mappable.set_array([])
        fig.colorbar(
            scalar_mappable,
            ax=ax,
            shrink=cfg.cbar_shrink,
            label=cfg.cbar_label
        )

        plt.tight_layout()

        image_bytes = self._save_figure(fig, cfg)
        metadata = {
            'title': cfg.title,
            'plot_type': 'treemap',
            'color_scheme': cmap,
            'figure_size': (cfg.figure_width, cfg.figure_height),
            'dpi': cfg.dpi,
            'vmin': vmin,
            'vmax': vmax,
            'samples': matrix.index.tolist(),
            'metric_name': metric_name,
            'treemap_scores': sample_scores.to_dict()
        }
        return image_bytes, metadata
    
    def _calculate_value_range(
        self, 
        matrix: pd.DataFrame, 
        config: HeatmapConfig
    ) -> Tuple[float, float]:
        """
        Calculate the value range for the heatmap color scale.
        
        Args:
            matrix: Similarity matrix
            config: Heatmap configuration
            
        Returns:
            Tuple of (vmin, vmax)
        """
        if config.vmin is not None and config.vmax is not None:
            return config.vmin, config.vmax
        
        values = matrix.values.copy()
        
        if config.mask_diagonal:
            np.fill_diagonal(values, np.nan)
        
        vmin = np.nanmin(values) if config.vmin is None else config.vmin
        vmax = np.nanmax(values) if config.vmax is None else config.vmax
        
        # Handle edge cases
        if np.isnan(vmin) or np.isnan(vmax) or vmin == vmax:
            vmin = 0.0
            vmax = 1.0
        
        return vmin, vmax

    def _calculate_treemap_scores(self, matrix: pd.DataFrame) -> pd.Series:
        """Aggregate each sample's similarity to all other samples for treemap sizing."""
        values = matrix.astype(float).copy()
        if len(values) > 1:
            np.fill_diagonal(values.values, np.nan)
            scores = values.mean(axis=1, skipna=True).fillna(0.0)
        else:
            scores = values.iloc[:, 0].fillna(0.0)
        return scores.clip(lower=0.0)

    def _normalize_treemap_sizes(self, values: np.ndarray) -> List[float]:
        """Ensure treemap blocks always have positive area."""
        numeric_values = [max(float(value), 0.0) for value in values]
        total = sum(numeric_values)
        if total <= 0:
            return [1.0 for _ in numeric_values]
        return numeric_values

    def _compute_treemap_rectangles(
        self,
        sizes: List[float],
        x: float = 0.0,
        y: float = 0.0,
        width: float = 1.0,
        height: float = 1.0
    ) -> List[Tuple[float, float, float, float]]:
        """Create a simple balanced treemap layout without external dependencies."""
        if not sizes:
            return []

        if len(sizes) == 1:
            return [(x, y, width, height)]

        total = sum(sizes)
        split_index = 1
        running_total = sizes[0]
        half_total = total / 2
        while split_index < len(sizes) - 1 and running_total < half_total:
            split_index += 1
            running_total += sizes[split_index - 1]

        first_group = sizes[:split_index]
        second_group = sizes[split_index:]
        first_total = sum(first_group)
        first_ratio = first_total / total if total > 0 else 0.5

        if width >= height:
            first_width = width * first_ratio
            return (
                self._compute_treemap_rectangles(first_group, x, y, first_width, height) +
                self._compute_treemap_rectangles(second_group, x + first_width, y, width - first_width, height)
            )

        first_height = height * first_ratio
        return (
            self._compute_treemap_rectangles(first_group, x, y, width, first_height) +
            self._compute_treemap_rectangles(second_group, x, y + first_height, width, height - first_height)
        )

    def _calculate_treemap_color_range(self, values: np.ndarray) -> Tuple[float, float]:
        """Calculate color normalization range for treemap rectangles."""
        numeric = np.asarray(values, dtype=float)
        vmin = float(np.nanmin(numeric)) if numeric.size else 0.0
        vmax = float(np.nanmax(numeric)) if numeric.size else 1.0
        if np.isnan(vmin) or np.isnan(vmax) or vmin == vmax:
            return 0.0, 1.0
        return vmin, vmax

    def _save_figure(self, fig: Any, cfg: HeatmapConfig) -> bytes:
        """Save a matplotlib figure to PNG bytes and close it."""
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=cfg.dpi, bbox_inches='tight')
        buffer.seek(0)
        image_bytes = buffer.getvalue()
        buffer.close()
        plt.close(fig)
        return image_bytes

    def _get_text_color_for_background(self, rgba_color: Tuple[float, float, float, float]) -> str:
        """Choose a readable label color for treemap blocks."""
        red, green, blue = rgba_color[:3]
        luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
        return '#212529' if luminance > 0.6 else '#ffffff'
    
    def generate_combined_heatmaps(
        self,
        matrices: Dict[str, pd.DataFrame],
        config: Optional[HeatmapConfig] = None,
        main_title: str = ""
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a combined figure with multiple heatmaps.
        
        Args:
            matrices: Dictionary mapping metric names to similarity matrices
            config: Optional configuration
            main_title: Main title for the combined figure
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 2.3, 2.4, 6.1
        """
        cfg = config or self.default_config
        
        n_metrics = len(matrices)
        if n_metrics == 0:
            raise ValueError("No matrices provided")
        
        # Calculate grid layout
        n_cols = min(3, n_metrics)
        n_rows = (n_metrics + n_cols - 1) // n_cols
        
        # Create figure with simplified layout
        fig_width = cfg.figure_width * n_cols * 0.7
        fig_height = cfg.figure_height * n_rows * 0.7
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(fig_width, fig_height))
        
        if main_title:
            fig.suptitle(main_title, fontsize=cfg.font_size + 4, fontweight='600', y=0.995)
        
        # Flatten axes for easy iteration
        if n_metrics == 1:
            axes = [axes]
        else:
            axes = axes.flatten() if hasattr(axes, 'flatten') else [axes]
        
        # Generate each heatmap
        metric_names = list(matrices.keys())
        for idx, (name, matrix) in enumerate(matrices.items()):
            ax = axes[idx]
            
            if matrix is not None and not matrix.empty:
                cmap = self.METRIC_COLOR_SCHEMES.get(name, cfg.color_scheme)
                vmin, vmax = self._calculate_value_range(matrix, cfg)
                
                mask = None
                if cfg.mask_diagonal:
                    mask = np.eye(len(matrix), dtype=bool)
                
                sns.heatmap(
                    matrix,
                    annot=cfg.annotation,
                    fmt=cfg.annotation_format,
                    cmap=cmap,
                    mask=mask,
                    vmin=vmin,
                    vmax=vmax,
                    square=cfg.square,
                    linewidths=cfg.linewidths,
                    linecolor=cfg.linecolor,
                    cbar_kws={'label': '相似度', 'shrink': cfg.cbar_shrink},
                    ax=ax,
                    annot_kws={'fontsize': cfg.font_size - 4}
                )
                
                title = name.replace('_', ' ').title()
                ax.set_title(title, fontsize=cfg.font_size, fontweight='600', pad=10)
                ax.set_xlabel(cfg.x_label, fontsize=cfg.font_size - 2)
                ax.set_ylabel(cfg.y_label, fontsize=cfg.font_size - 2)
                ax.tick_params(axis='x', rotation=cfg.x_rotation, labelsize=cfg.font_size - 3)
                ax.tick_params(axis='y', rotation=cfg.y_rotation, labelsize=cfg.font_size - 3)
            else:
                ax.text(0.5, 0.5, '无数据', ha='center', va='center',
                       transform=ax.transAxes, fontsize=cfg.font_size)
                ax.set_title(name.replace('_', ' ').title(), fontsize=cfg.font_size, fontweight='600')
        
        # Hide unused axes
        for idx in range(len(matrices), len(axes)):
            axes[idx].set_visible(False)
        
        plt.tight_layout()
        
        # Save to bytes buffer
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=cfg.dpi, bbox_inches='tight')
        buffer.seek(0)
        image_bytes = buffer.getvalue()
        buffer.close()
        plt.close(fig)
        
        # Generate metadata
        metadata = {
            'main_title': main_title,
            'metrics': metric_names,
            'figure_size': (fig_width, fig_height),
            'dpi': cfg.dpi,
            'n_rows': n_rows,
            'n_cols': n_cols
        }
        
        return image_bytes, metadata
    
    @classmethod
    def get_available_palettes(cls) -> List[str]:
        """
        Get list of available color palettes.
        
        Returns:
            List of palette names
        """
        return cls.AVAILABLE_PALETTES.copy()

    @classmethod
    def get_available_plot_types(cls) -> List[str]:
        """Get list of supported plot types."""
        return cls.AVAILABLE_PLOT_TYPES.copy()
    
    @classmethod
    def get_metric_color_scheme(cls, metric_name: str) -> str:
        """
        Get the default color scheme for a specific metric.
        
        Args:
            metric_name: Name of the similarity metric
            
        Returns:
            Color scheme name
        """
        return cls.METRIC_COLOR_SCHEMES.get(metric_name, cls.METRIC_COLOR_SCHEMES['default'])
