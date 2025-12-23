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


@dataclass
class HeatmapConfig:
    """
    Configuration for heatmap visualization.
    Uses clean, simple defaults for clear readability.
    Requirements: 7.1, 7.5, 7.7, 15.3, 16.1, 16.2, 16.3, 16.5
    """
    title: str = ""
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
        
        # Calculate value range (excluding diagonal if masking)
        vmin, vmax = self._calculate_value_range(matrix, cfg)
        
        # Create figure
        fig, ax = plt.subplots(figsize=(cfg.figure_width, cfg.figure_height))
        
        # Create mask for diagonal if requested
        mask = None
        if cfg.mask_diagonal:
            mask = np.eye(len(matrix), dtype=bool)
        
        # Generate heatmap
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
        
        # Set title and labels with clear, simple styling
        if cfg.title:
            ax.set_title(cfg.title, fontsize=cfg.font_size + 2, fontweight='600', pad=15)
        ax.set_xlabel(cfg.x_label, fontsize=cfg.font_size)
        ax.set_ylabel(cfg.y_label, fontsize=cfg.font_size)
        
        # Set tick parameters for readability
        ax.tick_params(axis='x', rotation=cfg.x_rotation, labelsize=cfg.font_size - 1)
        ax.tick_params(axis='y', rotation=cfg.y_rotation, labelsize=cfg.font_size - 1)
        
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
            'title': cfg.title,
            'color_scheme': cmap,
            'figure_size': (cfg.figure_width, cfg.figure_height),
            'dpi': cfg.dpi,
            'vmin': vmin,
            'vmax': vmax,
            'samples': matrix.index.tolist(),
            'metric_name': metric_name
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
    def get_metric_color_scheme(cls, metric_name: str) -> str:
        """
        Get the default color scheme for a specific metric.
        
        Args:
            metric_name: Name of the similarity metric
            
        Returns:
            Color scheme name
        """
        return cls.METRIC_COLOR_SCHEMES.get(metric_name, cls.METRIC_COLOR_SCHEMES['default'])
