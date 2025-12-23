"""
Chain-Specific Analyzer Service for the Immune Repertoire Analysis Web Application.
Implements chain-specific analysis, visualization, and statistical calculations.
Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 12.2

Supported chains:
1. IGH - Immunoglobulin Heavy Chain
2. IGK - Immunoglobulin Kappa Light Chain
3. IGL - Immunoglobulin Lambda Light Chain
4. TRA - T Cell Receptor Alpha Chain
5. TRB - T Cell Receptor Beta Chain
6. TRD - T Cell Receptor Delta Chain
7. TRG - T Cell Receptor Gamma Chain
"""
import io
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union, Set

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


@dataclass
class ChainChartConfig:
    """
    Configuration for chain-specific chart visualization.
    Requirements: 7.5, 7.6, 7.7
    """
    title: str = ""
    figure_width: int = 12
    figure_height: int = 8
    font_size: int = 12
    dpi: int = 300
    bar_width: float = 0.8
    bar_spacing: float = 0.2
    show_values: bool = True
    value_format: str = "{:.2f}"
    colors: Optional[List[str]] = None
    x_label: str = "Sample"
    y_label: str = "Value"
    x_rotation: int = 45
    legend_location: str = "upper right"
    grid: bool = True
    grid_alpha: float = 0.3


class ChainAnalyzer:
    """
    Analyzer for chain-specific immune repertoire analysis.
    Supports 7 default chains and custom chain identifiers.
    Requirements: 5.1, 12.2
    """
    
    # Default supported chains
    DEFAULT_CHAINS = ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']
    
    # Chain descriptions
    CHAIN_DESCRIPTIONS = {
        'IGH': 'Immunoglobulin Heavy Chain',
        'IGK': 'Immunoglobulin Kappa Light Chain',
        'IGL': 'Immunoglobulin Lambda Light Chain',
        'TRA': 'T Cell Receptor Alpha Chain',
        'TRB': 'T Cell Receptor Beta Chain',
        'TRD': 'T Cell Receptor Delta Chain',
        'TRG': 'T Cell Receptor Gamma Chain'
    }
    
    # Default colors for chains
    DEFAULT_CHAIN_COLORS = {
        'IGH': '#3498db',   # Blue
        'IGK': '#e74c3c',   # Red
        'IGL': '#2ecc71',   # Green
        'TRA': '#f39c12',   # Orange
        'TRB': '#9b59b6',   # Purple
        'TRD': '#1abc9c',   # Teal
        'TRG': '#e67e22'    # Dark Orange
    }
    
    def __init__(
        self,
        data: pd.DataFrame,
        field_mapping: Dict[str, str],
        chart_config: Optional[ChainChartConfig] = None,
        custom_chains: Optional[List[str]] = None
    ):
        """
        Initialize the chain analyzer.
        
        Args:
            data: DataFrame containing immune repertoire data
            field_mapping: Mapping from required fields to actual column names
                Required fields: 'sample', 'chain', 'cdr3' (or 'clone_id'), 'copy' (or 'reads')
            chart_config: Optional configuration for chart generation
            custom_chains: Optional list of custom chain identifiers to support
                          (in addition to default chains)
        
        Requirements: 5.1, 12.2
        """
        self.data = data
        self.field_mapping = field_mapping
        self.chart_config = chart_config or ChainChartConfig()
        
        # Extract column names from mapping
        self.sample_col = field_mapping.get('sample', 'sample')
        self.chain_col = field_mapping.get('chain', 'chain')
        self.cdr3_col = field_mapping.get('cdr3', field_mapping.get('clone_id', 'CDR3(pep)'))
        self.copy_col = field_mapping.get('copy', field_mapping.get('reads', 'copy'))
        
        # Set up supported chains (default + custom)
        self._supported_chains: Set[str] = set(self.DEFAULT_CHAINS)
        if custom_chains:
            self._supported_chains.update(custom_chains)
        
        # Build data structures
        self._samples: List[str] = []
        self._chains: List[str] = []
        self._chain_data: Dict[str, pd.DataFrame] = {}
        self._chain_metrics: Dict[str, pd.DataFrame] = {}
        
        self._prepare_data()
    
    def _prepare_data(self) -> None:
        """Prepare data structures for chain-specific analysis."""
        if self.data.empty:
            return
        
        # Get unique samples
        if self.sample_col in self.data.columns:
            self._samples = sorted(self.data[self.sample_col].dropna().unique().tolist())
        else:
            self._samples = ['all_data']
            self.data = self.data.copy()
            self.data[self.sample_col] = 'all_data'
        
        # Get unique chains present in data
        if self.chain_col in self.data.columns:
            data_chains = set(self.data[self.chain_col].dropna().unique().tolist())
            # Filter to supported chains
            self._chains = sorted([c for c in data_chains if c in self._supported_chains])
        else:
            self._chains = []
        
        # Build chain-specific data
        for chain in self._chains:
            chain_data = self.data[self.data[self.chain_col] == chain].copy()
            self._chain_data[chain] = chain_data
    
    @property
    def samples(self) -> List[str]:
        """Get list of sample names."""
        return self._samples
    
    @property
    def chains(self) -> List[str]:
        """Get list of chains present in data."""
        return self._chains
    
    @property
    def supported_chains(self) -> List[str]:
        """Get list of all supported chains (default + custom)."""
        return sorted(list(self._supported_chains))
    
    def add_custom_chain(self, chain_id: str, description: Optional[str] = None) -> None:
        """
        Add a custom chain identifier.
        
        Args:
            chain_id: Chain identifier string
            description: Optional description for the chain
            
        Requirements: 12.2
        """
        self._supported_chains.add(chain_id)
        if description:
            self.CHAIN_DESCRIPTIONS[chain_id] = description
        
        # Re-prepare data to include new chain
        self._prepare_data()
    
    def remove_custom_chain(self, chain_id: str) -> bool:
        """
        Remove a custom chain identifier.
        
        Args:
            chain_id: Chain identifier to remove
            
        Returns:
            True if chain was removed, False if it was a default chain
            
        Requirements: 12.2
        """
        if chain_id in self.DEFAULT_CHAINS:
            return False  # Cannot remove default chains
        
        self._supported_chains.discard(chain_id)
        self._prepare_data()
        return True
    
    def get_chain_data(self, chain: str) -> pd.DataFrame:
        """
        Get data for a specific chain.
        
        Args:
            chain: Chain identifier
            
        Returns:
            DataFrame containing data for the specified chain
        """
        return self._chain_data.get(chain, pd.DataFrame())
    
    def get_chain_description(self, chain: str) -> str:
        """
        Get description for a chain.
        
        Args:
            chain: Chain identifier
            
        Returns:
            Description string
        """
        return self.CHAIN_DESCRIPTIONS.get(chain, f"Custom Chain: {chain}")
    
    def calculate_chain_metrics(
        self,
        chains: Optional[List[str]] = None,
        metric: str = 'ucdr3'
    ) -> pd.DataFrame:
        """
        Calculate metrics for each chain across samples.
        
        Args:
            chains: List of chains to analyze. If None, uses all available chains.
            metric: Metric to calculate. Options:
                   - 'ucdr3': Unique CDR3 count
                   - 'total_reads': Total reads/copy count
                   - 'clone_count': Total clone count
                   
        Returns:
            DataFrame with samples as index and chains as columns
            
        Requirements: 5.1
        """
        if chains is None:
            chains = self._chains
        else:
            chains = [c for c in chains if c in self._chains]
        
        if not chains:
            return pd.DataFrame()
        
        metrics_data = {}
        
        for chain in chains:
            chain_data = self._chain_data.get(chain, pd.DataFrame())
            if chain_data.empty:
                metrics_data[chain] = {s: 0 for s in self._samples}
                continue
            
            sample_metrics = {}
            for sample in self._samples:
                sample_data = chain_data[chain_data[self.sample_col] == sample]
                
                if metric == 'ucdr3':
                    # Count unique CDR3 sequences
                    if self.cdr3_col in sample_data.columns:
                        value = sample_data[self.cdr3_col].nunique()
                    else:
                        value = 0
                elif metric == 'total_reads':
                    # Sum of reads/copy
                    if self.copy_col in sample_data.columns:
                        value = sample_data[self.copy_col].sum()
                    else:
                        value = 0
                elif metric == 'clone_count':
                    # Total number of clones
                    value = len(sample_data)
                else:
                    value = 0
                
                sample_metrics[sample] = value
            
            metrics_data[chain] = sample_metrics
        
        return pd.DataFrame(metrics_data)
    
    def calculate_cv(
        self,
        chains: Optional[List[str]] = None,
        metric: str = 'ucdr3'
    ) -> pd.Series:
        """
        Calculate Coefficient of Variation (CV) for each chain.
        
        CV = (standard_deviation / mean) * 100
        
        Args:
            chains: List of chains to analyze
            metric: Metric to calculate CV for
            
        Returns:
            Series with CV values for each chain
            
        Requirements: 5.4
        """
        metrics_df = self.calculate_chain_metrics(chains, metric)
        
        if metrics_df.empty:
            return pd.Series(dtype=float)
        
        cv_values = {}
        for chain in metrics_df.columns:
            values = metrics_df[chain].values
            mean_val = np.mean(values)
            std_val = np.std(values, ddof=0)  # Population std
            
            if mean_val > 0:
                cv = (std_val / mean_val) * 100
            else:
                cv = 0.0
            
            cv_values[chain] = cv
        
        return pd.Series(cv_values, name='cv')
    
    def calculate_range_difference(
        self,
        chains: Optional[List[str]] = None,
        metric: str = 'ucdr3'
    ) -> pd.DataFrame:
        """
        Calculate range difference statistics for each chain.
        
        Args:
            chains: List of chains to analyze
            metric: Metric to calculate range for
            
        Returns:
            DataFrame with min, max, range, and range_percent for each chain
            
        Requirements: 5.4
        """
        metrics_df = self.calculate_chain_metrics(chains, metric)
        
        if metrics_df.empty:
            return pd.DataFrame()
        
        range_data = {}
        for chain in metrics_df.columns:
            values = metrics_df[chain].values
            min_val = np.min(values)
            max_val = np.max(values)
            range_val = max_val - min_val
            mean_val = np.mean(values)
            
            if mean_val > 0:
                range_percent = (range_val / mean_val) * 100
            else:
                range_percent = 0.0
            
            range_data[chain] = {
                'min': min_val,
                'max': max_val,
                'range': range_val,
                'mean': mean_val,
                'range_percent': range_percent
            }
        
        return pd.DataFrame(range_data).T
    
    def calculate_statistics(
        self,
        chains: Optional[List[str]] = None,
        metric: str = 'ucdr3'
    ) -> pd.DataFrame:
        """
        Calculate comprehensive statistics for each chain.
        
        Args:
            chains: List of chains to analyze
            metric: Metric to calculate statistics for
            
        Returns:
            DataFrame with statistics (mean, std, cv, min, max, range) for each chain
            
        Requirements: 5.4
        """
        metrics_df = self.calculate_chain_metrics(chains, metric)
        
        if metrics_df.empty:
            return pd.DataFrame()
        
        stats_data = {}
        for chain in metrics_df.columns:
            values = metrics_df[chain].values
            mean_val = np.mean(values)
            std_val = np.std(values, ddof=0)
            min_val = np.min(values)
            max_val = np.max(values)
            range_val = max_val - min_val
            
            if mean_val > 0:
                cv = (std_val / mean_val) * 100
                range_percent = (range_val / mean_val) * 100
            else:
                cv = 0.0
                range_percent = 0.0
            
            stats_data[chain] = {
                'mean': mean_val,
                'std': std_val,
                'cv': cv,
                'min': min_val,
                'max': max_val,
                'range': range_val,
                'range_percent': range_percent
            }
        
        return pd.DataFrame(stats_data).T



class ChainChartGenerator:
    """
    Generator for chain-specific visualizations.
    Supports single chain charts, combined comparison charts, and data table extraction.
    Requirements: 5.2, 5.3, 5.5, 5.6
    """
    
    # Default colors for chains
    DEFAULT_CHAIN_COLORS = {
        'IGH': '#3498db',   # Blue
        'IGK': '#e74c3c',   # Red
        'IGL': '#2ecc71',   # Green
        'TRA': '#f39c12',   # Orange
        'TRB': '#9b59b6',   # Purple
        'TRD': '#1abc9c',   # Teal
        'TRG': '#e67e22'    # Dark Orange
    }
    
    # Available color palettes
    COLOR_PALETTES = {
        'default': ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22'],
        'pastel': ['#a8d8ea', '#f8b4b4', '#b4f8b4', '#f8e4b4', '#d4b4f8', '#b4f8e4', '#f8d4b4'],
        'bright': ['#0066ff', '#ff0066', '#00ff66', '#ffcc00', '#9900ff', '#00ffcc', '#ff9900'],
        'dark': ['#1a5276', '#922b21', '#1e8449', '#b7950b', '#6c3483', '#117a65', '#935116'],
        'colorblind': ['#0072B2', '#D55E00', '#009E73', '#F0E442', '#CC79A7', '#56B4E9', '#E69F00']
    }
    
    def __init__(self, config: Optional[ChainChartConfig] = None):
        """
        Initialize the chain chart generator.
        
        Args:
            config: Optional default configuration for charts
        """
        self.default_config = config or ChainChartConfig()
        
        # Set up matplotlib for scientific publication style
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        # Professional styling for scientific publications
        plt.rcParams['figure.facecolor'] = 'white'
        plt.rcParams['axes.facecolor'] = 'white'
        plt.rcParams['axes.edgecolor'] = '#2c3e50'
        plt.rcParams['axes.linewidth'] = 1.0
        plt.rcParams['axes.labelcolor'] = '#2c3e50'
        plt.rcParams['axes.titlesize'] = 12
        plt.rcParams['axes.labelsize'] = 10
        plt.rcParams['xtick.color'] = '#2c3e50'
        plt.rcParams['ytick.color'] = '#2c3e50'
        plt.rcParams['xtick.labelsize'] = 9
        plt.rcParams['ytick.labelsize'] = 9
        plt.rcParams['grid.color'] = '#dee2e6'
        plt.rcParams['grid.linestyle'] = '-'
        plt.rcParams['grid.linewidth'] = 0.5
        plt.rcParams['grid.alpha'] = 0.3
    
    def generate_single_chain_chart(
        self,
        data: pd.DataFrame,
        chain: str,
        config: Optional[ChainChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a bar chart for a single chain across samples.
        
        Args:
            data: DataFrame with samples as index and chains as columns
            chain: Chain identifier to plot
            config: Optional configuration
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 5.2
        """
        cfg = config or self.default_config
        
        if chain not in data.columns:
            raise ValueError(f"Chain '{chain}' not found in data")
        
        samples = data.index.tolist()
        values = data[chain].values
        
        # Get color for chain
        color = self.DEFAULT_CHAIN_COLORS.get(chain, '#3498db')
        if cfg.colors and len(cfg.colors) > 0:
            color = cfg.colors[0]
        
        # Create figure
        fig, ax = plt.subplots(figsize=(cfg.figure_width, cfg.figure_height))
        
        # Plot bars
        x = np.arange(len(samples))
        bars = ax.bar(x, values, cfg.bar_width, color=color, alpha=0.8)
        
        # Add value labels if requested
        if cfg.show_values:
            self._add_value_labels(ax, bars, cfg)
        
        # Configure axes
        ax.set_xlabel(cfg.x_label, fontsize=cfg.font_size, fontweight='bold')
        ax.set_ylabel(cfg.y_label, fontsize=cfg.font_size, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=cfg.x_rotation, ha='right', fontsize=cfg.font_size - 1)
        ax.tick_params(axis='y', labelsize=cfg.font_size - 1)
        
        title = cfg.title or f'{chain} Analysis'
        ax.set_title(title, fontsize=cfg.font_size + 4, fontweight='bold', pad=15)
        
        # Add grid
        if cfg.grid:
            ax.grid(axis='y', alpha=cfg.grid_alpha, linestyle='--')
            ax.set_axisbelow(True)
        
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
            'title': title,
            'chain': chain,
            'samples': samples,
            'figure_size': (cfg.figure_width, cfg.figure_height),
            'dpi': cfg.dpi
        }
        
        return image_bytes, metadata
    
    def generate_combined_comparison_chart(
        self,
        data: pd.DataFrame,
        chains: List[str],
        config: Optional[ChainChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a combined bar chart comparing multiple chains across samples.
        
        Args:
            data: DataFrame with samples as index and chains as columns
            chains: List of chain identifiers to include
            config: Optional configuration
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 5.3
        """
        cfg = config or self.default_config
        
        # Filter to requested chains
        available_chains = [c for c in chains if c in data.columns]
        if not available_chains:
            raise ValueError("No valid chains found in data")
        
        plot_data = data[available_chains]
        samples = plot_data.index.tolist()
        n_samples = len(samples)
        n_chains = len(available_chains)
        
        # Calculate bar positions
        x = np.arange(n_samples)
        total_width = cfg.bar_width
        individual_width = total_width / n_chains
        
        # Get colors
        colors = self._get_colors(available_chains, cfg)
        
        # Create figure
        fig, ax = plt.subplots(figsize=(cfg.figure_width, cfg.figure_height))
        
        # Plot bars for each chain
        for i, (chain, color) in enumerate(zip(available_chains, colors)):
            offset = (i - n_chains / 2 + 0.5) * individual_width
            bars = ax.bar(
                x + offset,
                plot_data[chain],
                individual_width * (1 - cfg.bar_spacing),
                label=chain,
                color=color,
                alpha=0.8
            )
            
            # Add value labels if requested
            if cfg.show_values and n_chains <= 3:  # Only show values if not too crowded
                self._add_value_labels(ax, bars, cfg)
        
        # Configure axes
        ax.set_xlabel(cfg.x_label, fontsize=cfg.font_size, fontweight='bold')
        ax.set_ylabel(cfg.y_label, fontsize=cfg.font_size, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=cfg.x_rotation, ha='right', fontsize=cfg.font_size - 1)
        ax.tick_params(axis='y', labelsize=cfg.font_size - 1)
        
        title = cfg.title or 'Chain Comparison'
        ax.set_title(title, fontsize=cfg.font_size + 4, fontweight='bold', pad=15)
        
        # Add legend
        ax.legend(loc=cfg.legend_location, fontsize=cfg.font_size - 2)
        
        # Add grid
        if cfg.grid:
            ax.grid(axis='y', alpha=cfg.grid_alpha, linestyle='--')
            ax.set_axisbelow(True)
        
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
            'title': title,
            'chains': available_chains,
            'samples': samples,
            'figure_size': (cfg.figure_width, cfg.figure_height),
            'dpi': cfg.dpi
        }
        
        return image_bytes, metadata
    
    def generate_all_chain_charts(
        self,
        data: pd.DataFrame,
        chains: Optional[List[str]] = None,
        config: Optional[ChainChartConfig] = None
    ) -> Tuple[List[Tuple[bytes, Dict[str, Any]]], Tuple[bytes, Dict[str, Any]]]:
        """
        Generate individual charts for each chain plus a combined comparison chart.
        
        Args:
            data: DataFrame with samples as index and chains as columns
            chains: List of chains to include. If None, uses all available.
            config: Optional configuration
            
        Returns:
            Tuple of (list of individual chart tuples, combined chart tuple)
            Each chart tuple is (PNG bytes, metadata dict)
            
        Requirements: 5.2, 5.3
        """
        if chains is None:
            chains = [c for c in data.columns if c in ChainAnalyzer.DEFAULT_CHAINS or c in data.columns]
        
        available_chains = [c for c in chains if c in data.columns]
        
        # Generate individual charts
        individual_charts = []
        for chain in available_chains:
            chart_config = config or self.default_config
            single_config = ChainChartConfig(
                title=f'{chain} Analysis',
                figure_width=chart_config.figure_width,
                figure_height=chart_config.figure_height,
                font_size=chart_config.font_size,
                dpi=chart_config.dpi,
                bar_width=chart_config.bar_width,
                bar_spacing=chart_config.bar_spacing,
                show_values=chart_config.show_values,
                value_format=chart_config.value_format,
                colors=[self.DEFAULT_CHAIN_COLORS.get(chain, '#3498db')],
                x_label=chart_config.x_label,
                y_label=chart_config.y_label,
                x_rotation=chart_config.x_rotation,
                legend_location=chart_config.legend_location,
                grid=chart_config.grid,
                grid_alpha=chart_config.grid_alpha
            )
            chart = self.generate_single_chain_chart(data, chain, single_config)
            individual_charts.append(chart)
        
        # Generate combined chart
        combined_config = config or self.default_config
        combined_config = ChainChartConfig(
            title=combined_config.title or 'Combined Chain Comparison',
            figure_width=combined_config.figure_width,
            figure_height=combined_config.figure_height,
            font_size=combined_config.font_size,
            dpi=combined_config.dpi,
            bar_width=combined_config.bar_width,
            bar_spacing=combined_config.bar_spacing,
            show_values=combined_config.show_values,
            value_format=combined_config.value_format,
            colors=combined_config.colors,
            x_label=combined_config.x_label,
            y_label=combined_config.y_label,
            x_rotation=combined_config.x_rotation,
            legend_location=combined_config.legend_location,
            grid=combined_config.grid,
            grid_alpha=combined_config.grid_alpha
        )
        combined_chart = self.generate_combined_comparison_chart(data, available_chains, combined_config)
        
        return individual_charts, combined_chart
    
    def generate_statistics_chart(
        self,
        stats_df: pd.DataFrame,
        stat_type: str = 'cv',
        config: Optional[ChainChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a bar chart for chain statistics (CV, range, etc.).
        
        Args:
            stats_df: DataFrame with chains as index and statistics as columns
            stat_type: Statistic to plot ('cv', 'range', 'range_percent', 'mean', 'std')
            config: Optional configuration
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 5.4
        """
        cfg = config or self.default_config
        
        if stat_type not in stats_df.columns:
            raise ValueError(f"Statistic '{stat_type}' not found in data")
        
        chains = stats_df.index.tolist()
        values = stats_df[stat_type].values
        
        # Get colors for chains
        colors = [self.DEFAULT_CHAIN_COLORS.get(c, '#3498db') for c in chains]
        
        # Create figure
        fig, ax = plt.subplots(figsize=(cfg.figure_width, cfg.figure_height))
        
        # Plot bars
        x = np.arange(len(chains))
        bars = ax.bar(x, values, cfg.bar_width, color=colors, alpha=0.8)
        
        # Add value labels
        if cfg.show_values:
            self._add_value_labels(ax, bars, cfg)
        
        # Configure axes
        ax.set_xlabel('Chain', fontsize=cfg.font_size, fontweight='bold')
        y_label = self._format_stat_name(stat_type)
        ax.set_ylabel(y_label, fontsize=cfg.font_size, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(chains, fontsize=cfg.font_size - 1)
        ax.tick_params(axis='y', labelsize=cfg.font_size - 1)
        
        title = cfg.title or f'Chain {y_label}'
        ax.set_title(title, fontsize=cfg.font_size + 4, fontweight='bold', pad=15)
        
        # Add grid
        if cfg.grid:
            ax.grid(axis='y', alpha=cfg.grid_alpha, linestyle='--')
            ax.set_axisbelow(True)
        
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
            'title': title,
            'stat_type': stat_type,
            'chains': chains,
            'figure_size': (cfg.figure_width, cfg.figure_height),
            'dpi': cfg.dpi
        }
        
        return image_bytes, metadata
    
    def extract_data_table(
        self,
        data: pd.DataFrame,
        chains: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Extract chain data as a table format suitable for display and copying.
        
        Args:
            data: DataFrame with samples as index and chains as columns
            chains: Optional list of chains to include
            
        Returns:
            Dictionary with table data for frontend display
            
        Requirements: 5.5, 5.6
        """
        if chains:
            available_chains = [c for c in chains if c in data.columns]
            table_data = data[available_chains].copy()
        else:
            table_data = data.copy()
        
        # Convert to list of dictionaries for JSON serialization
        records = []
        for sample in table_data.index:
            record = {'Sample': str(sample)}
            for chain in table_data.columns:
                value = table_data.loc[sample, chain]
                if pd.isna(value):
                    record[chain] = None
                elif isinstance(value, float):
                    record[chain] = round(value, 4)
                else:
                    record[chain] = int(value) if isinstance(value, (int, np.integer)) else value
            records.append(record)
        
        return {
            'columns': ['Sample'] + list(table_data.columns),
            'data': records,
            'row_count': len(records)
        }
    
    def extract_statistics_table(
        self,
        stats_df: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Extract statistics data as a table format suitable for display and copying.
        
        Args:
            stats_df: DataFrame with chains as index and statistics as columns
            
        Returns:
            Dictionary with table data for frontend display
            
        Requirements: 5.5, 5.6
        """
        # Format column names for display
        formatted_columns = [self._format_stat_name(col) for col in stats_df.columns]
        
        # Convert to list of dictionaries for JSON serialization
        records = []
        for chain in stats_df.index:
            record = {'Chain': str(chain)}
            for col, formatted_col in zip(stats_df.columns, formatted_columns):
                value = stats_df.loc[chain, col]
                if pd.isna(value):
                    record[formatted_col] = None
                elif isinstance(value, float):
                    record[formatted_col] = round(value, 4)
                else:
                    record[formatted_col] = value
            records.append(record)
        
        return {
            'columns': ['Chain'] + formatted_columns,
            'data': records,
            'row_count': len(records)
        }
    
    def _get_colors(self, chains: List[str], config: ChainChartConfig) -> List[str]:
        """Get colors for the given chains."""
        if config.colors and len(config.colors) >= len(chains):
            return config.colors[:len(chains)]
        
        # Use default chain colors
        colors = []
        for chain in chains:
            if chain in self.DEFAULT_CHAIN_COLORS:
                colors.append(self.DEFAULT_CHAIN_COLORS[chain])
            else:
                idx = len(colors) % len(self.COLOR_PALETTES['default'])
                colors.append(self.COLOR_PALETTES['default'][idx])
        
        return colors
    
    def _add_value_labels(
        self,
        ax: plt.Axes,
        bars: Any,
        config: ChainChartConfig
    ) -> None:
        """Add value labels on top of bars."""
        for bar in bars:
            height = bar.get_height()
            label = config.value_format.format(height)
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height,
                label,
                ha='center',
                va='bottom',
                fontsize=config.font_size - 3
            )
    
    def _format_stat_name(self, stat: str) -> str:
        """Format statistic name for display."""
        name_mapping = {
            'cv': 'CV (%)',
            'mean': 'Mean',
            'std': 'Std Dev',
            'min': 'Minimum',
            'max': 'Maximum',
            'range': 'Range',
            'range_percent': 'Range (%)'
        }
        return name_mapping.get(stat, stat.replace('_', ' ').title())
    
    @classmethod
    def get_available_palettes(cls) -> List[str]:
        """Get list of available color palettes."""
        return list(cls.COLOR_PALETTES.keys())
    
    @classmethod
    def get_palette_colors(cls, palette_name: str) -> List[str]:
        """Get colors for a specific palette."""
        return cls.COLOR_PALETTES.get(palette_name, cls.COLOR_PALETTES['default']).copy()
