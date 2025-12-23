"""
Diversity Analyzer Service for the Immune Repertoire Analysis Web Application.
Implements diversity metrics calculation, sample grouping, and visualization.
Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 12.1

Metrics implemented:
1. D50 - Number of clones comprising 50% of total expression
2. Gini Index - Measure of clonal distribution inequality
3. Shannon Entropy - Information-theoretic diversity measure
4. Simpson Index - Probability-based diversity measure
"""
import io
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


@dataclass
class DiversityChartConfig:
    """
    Configuration for diversity chart visualization.
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


class DiversityAnalyzer:
    """
    Analyzer for immune repertoire diversity metrics.
    Calculates D50, Gini index, Shannon entropy, and Simpson index.
    Requirements: 4.1
    """
    
    # Available diversity metrics
    METRICS = ['d50', 'gini', 'shannon', 'simpson']
    
    # Default colors for metrics
    DEFAULT_COLORS = {
        'd50': '#3498db',       # Blue
        'gini': '#e74c3c',      # Red
        'shannon': '#2ecc71',   # Green
        'simpson': '#f39c12'    # Orange
    }
    
    def __init__(
        self,
        data: pd.DataFrame,
        field_mapping: Dict[str, str],
        chart_config: Optional[DiversityChartConfig] = None
    ):
        """
        Initialize the diversity analyzer.
        
        Args:
            data: DataFrame containing immune repertoire data
            field_mapping: Mapping from required fields to actual column names
                Required fields: 'sample', 'cdr3' (or 'clone_id'), 'copy' (or 'reads')
            chart_config: Optional configuration for chart generation
        """
        self.data = data
        self.field_mapping = field_mapping
        self.chart_config = chart_config or DiversityChartConfig()
        
        # Extract column names from mapping
        self.sample_col = field_mapping.get('sample', 'sample')
        self.cdr3_col = field_mapping.get('cdr3', field_mapping.get('clone_id', 'CDR3(pep)'))
        self.copy_col = field_mapping.get('copy', field_mapping.get('reads', 'copy'))
        self.chain_col = field_mapping.get('chain', 'chain')
        
        # Build sample data structures
        self._samples: List[str] = []
        self._sample_abundances: Dict[str, np.ndarray] = {}
        self._metrics_cache: Dict[str, pd.Series] = {}
        
        self._prepare_data()
    
    def _prepare_data(self) -> None:
        """Prepare data structures for diversity calculations."""
        if self.data.empty:
            return
        
        # Get unique samples
        if self.sample_col in self.data.columns:
            self._samples = sorted(self.data[self.sample_col].dropna().unique().tolist())
        else:
            self._samples = ['all_data']
            self.data = self.data.copy()
            self.data[self.sample_col] = 'all_data'
        
        # Build abundance arrays for each sample
        for sample in self._samples:
            sample_data = self.data[self.data[self.sample_col] == sample]
            
            if self.copy_col in sample_data.columns:
                # Get abundance values (copy numbers/reads)
                abundances = sample_data[self.copy_col].dropna().values.astype(float)
                # Filter out zero and negative values
                abundances = abundances[abundances > 0]
                self._sample_abundances[sample] = abundances
    
    @property
    def samples(self) -> List[str]:
        """Get list of sample names."""
        return self._samples
    
    def calculate_d50(self, sample: Optional[str] = None) -> Union[float, pd.Series]:
        """
        Calculate D50 for one or all samples.
        
        D50 is the minimum number of clones that comprise 50% of total expression.
        A lower D50 indicates a more oligoclonal (less diverse) repertoire.
        
        Args:
            sample: Optional sample name. If None, calculates for all samples.
            
        Returns:
            D50 value for single sample, or Series with D50 for all samples.
            
        Requirements: 4.1
        """
        if sample is not None:
            return self._calculate_d50_single(sample)
        
        # Calculate for all samples
        d50_values = {}
        for s in self._samples:
            d50_values[s] = self._calculate_d50_single(s)
        
        return pd.Series(d50_values, name='d50')
    
    def _calculate_d50_single(self, sample: str) -> float:
        """Calculate D50 for a single sample."""
        if sample not in self._sample_abundances:
            return 0.0
        
        abundances = self._sample_abundances[sample]
        if len(abundances) == 0:
            return 0.0
        
        # Sort abundances in descending order
        sorted_abundances = np.sort(abundances)[::-1]
        total = np.sum(sorted_abundances)
        
        if total == 0:
            return 0.0
        
        # Find minimum number of clones comprising 50% of total
        cumsum = np.cumsum(sorted_abundances)
        threshold = total * 0.5
        
        # D50 is the count of clones needed to reach 50%
        d50 = np.searchsorted(cumsum, threshold, side='left') + 1
        
        return float(d50)
    
    def calculate_gini(self, sample: Optional[str] = None) -> Union[float, pd.Series]:
        """
        Calculate Gini index for one or all samples.
        
        Gini index measures inequality in clone abundance distribution.
        Range: [0, 1], where 0 = perfect equality, 1 = maximum inequality.
        
        Formula:
        G = (2 * Σ(i * x_i)) / (n * Σx_i) - (n + 1) / n
        
        Where x_i are sorted abundances and i is the rank.
        
        Args:
            sample: Optional sample name. If None, calculates for all samples.
            
        Returns:
            Gini index for single sample, or Series with Gini for all samples.
            
        Requirements: 4.1
        """
        if sample is not None:
            return self._calculate_gini_single(sample)
        
        gini_values = {}
        for s in self._samples:
            gini_values[s] = self._calculate_gini_single(s)
        
        return pd.Series(gini_values, name='gini')
    
    def _calculate_gini_single(self, sample: str) -> float:
        """Calculate Gini index for a single sample."""
        if sample not in self._sample_abundances:
            return 0.0
        
        abundances = self._sample_abundances[sample]
        n = len(abundances)
        
        if n == 0:
            return 0.0
        
        # Sort abundances in ascending order
        sorted_abundances = np.sort(abundances)
        total = np.sum(sorted_abundances)
        
        if total == 0:
            return 0.0
        
        # Calculate Gini coefficient
        # G = (2 * Σ(i * x_i)) / (n * Σx_i) - (n + 1) / n
        cumsum = np.cumsum(sorted_abundances)
        gini = (2 * np.sum((np.arange(1, n + 1) * sorted_abundances))) / (n * total) - (n + 1) / n
        
        return float(gini)
    
    def calculate_shannon(self, sample: Optional[str] = None) -> Union[float, pd.Series]:
        """
        Calculate Shannon entropy for one or all samples.
        
        Shannon entropy measures diversity using information theory.
        Higher values indicate greater diversity.
        
        Formula:
        H = -Σ(p_i * log2(p_i))
        
        Where p_i is the proportion of clone i.
        
        Args:
            sample: Optional sample name. If None, calculates for all samples.
            
        Returns:
            Shannon entropy for single sample, or Series for all samples.
            
        Requirements: 4.1
        """
        if sample is not None:
            return self._calculate_shannon_single(sample)
        
        shannon_values = {}
        for s in self._samples:
            shannon_values[s] = self._calculate_shannon_single(s)
        
        return pd.Series(shannon_values, name='shannon')
    
    def _calculate_shannon_single(self, sample: str) -> float:
        """Calculate Shannon entropy for a single sample."""
        if sample not in self._sample_abundances:
            return 0.0
        
        abundances = self._sample_abundances[sample]
        if len(abundances) == 0:
            return 0.0
        
        total = np.sum(abundances)
        if total == 0:
            return 0.0
        
        # Calculate proportions
        proportions = abundances / total
        
        # Filter out zero proportions to avoid log(0)
        proportions = proportions[proportions > 0]
        
        # Calculate Shannon entropy: H = -Σ(p_i * log2(p_i))
        entropy = -np.sum(proportions * np.log2(proportions))
        
        return float(entropy)
    
    def calculate_simpson(self, sample: Optional[str] = None) -> Union[float, pd.Series]:
        """
        Calculate Simpson index for one or all samples.
        
        Simpson index measures the probability that two randomly selected
        clones belong to different clonotypes.
        
        Formula (Simpson's Diversity Index, 1 - D):
        1 - D = 1 - Σ(p_i²)
        
        Range: [0, 1], where higher values indicate greater diversity.
        
        Args:
            sample: Optional sample name. If None, calculates for all samples.
            
        Returns:
            Simpson index for single sample, or Series for all samples.
            
        Requirements: 4.1
        """
        if sample is not None:
            return self._calculate_simpson_single(sample)
        
        simpson_values = {}
        for s in self._samples:
            simpson_values[s] = self._calculate_simpson_single(s)
        
        return pd.Series(simpson_values, name='simpson')
    
    def _calculate_simpson_single(self, sample: str) -> float:
        """Calculate Simpson index for a single sample."""
        if sample not in self._sample_abundances:
            return 0.0
        
        abundances = self._sample_abundances[sample]
        if len(abundances) == 0:
            return 0.0
        
        total = np.sum(abundances)
        if total == 0:
            return 0.0
        
        # Calculate proportions
        proportions = abundances / total
        
        # Calculate Simpson's Diversity Index: 1 - Σ(p_i²)
        simpson = 1 - np.sum(proportions ** 2)
        
        return float(simpson)
    
    def calculate_all_metrics(self) -> pd.DataFrame:
        """
        Calculate all diversity metrics for all samples.
        
        Returns:
            DataFrame with samples as index and metrics as columns.
            Columns: d50, gini, shannon, simpson
            
        Requirements: 4.1
        """
        return pd.DataFrame({
            'd50': self.calculate_d50(),
            'gini': self.calculate_gini(),
            'shannon': self.calculate_shannon(),
            'simpson': self.calculate_simpson()
        })
    
    def calculate_metric(self, metric_name: str) -> pd.Series:
        """
        Calculate a specific diversity metric.
        
        Args:
            metric_name: Name of the metric ('d50', 'gini', 'shannon', 'simpson')
            
        Returns:
            Series with metric values for all samples
            
        Raises:
            ValueError: If metric name is not recognized
        """
        metric_methods = {
            'd50': self.calculate_d50,
            'gini': self.calculate_gini,
            'shannon': self.calculate_shannon,
            'simpson': self.calculate_simpson
        }
        
        if metric_name not in metric_methods:
            raise ValueError(
                f"Unknown metric: {metric_name}. "
                f"Available metrics: {list(metric_methods.keys())}"
            )
        
        return metric_methods[metric_name]()



class SampleGrouper:
    """
    Handles sample grouping and group-level calculations.
    Requirements: 4.3, 12.1
    """
    
    def __init__(self, metrics_df: pd.DataFrame):
        """
        Initialize the sample grouper.
        
        Args:
            metrics_df: DataFrame with samples as index and metrics as columns
        """
        self.metrics_df = metrics_df
        self._groups: Dict[str, List[str]] = {}
    
    def set_groups(self, groups: Dict[str, List[str]]) -> None:
        """
        Set custom sample groupings.
        
        Args:
            groups: Dictionary mapping group names to lists of sample names
            
        Requirements: 12.1
        """
        # Validate that all samples exist
        all_samples = set(self.metrics_df.index)
        for group_name, samples in groups.items():
            invalid_samples = set(samples) - all_samples
            if invalid_samples:
                raise ValueError(
                    f"Invalid samples in group '{group_name}': {invalid_samples}"
                )
        
        self._groups = groups
    
    def get_groups(self) -> Dict[str, List[str]]:
        """Get current group definitions."""
        return self._groups.copy()
    
    def calculate_group_averages(
        self,
        metrics: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Calculate average metric values for each group.
        
        Args:
            metrics: Optional list of metrics to include. If None, uses all.
            
        Returns:
            DataFrame with groups as index and metrics as columns
            
        Requirements: 4.3
        """
        if not self._groups:
            raise ValueError("No groups defined. Call set_groups() first.")
        
        df = self.metrics_df
        if metrics:
            available_metrics = [m for m in metrics if m in df.columns]
            df = df[available_metrics]
        
        group_averages = {}
        for group_name, samples in self._groups.items():
            # Filter to samples that exist in the data
            valid_samples = [s for s in samples if s in df.index]
            if valid_samples:
                group_averages[group_name] = df.loc[valid_samples].mean()
            else:
                group_averages[group_name] = pd.Series(
                    {col: np.nan for col in df.columns}
                )
        
        return pd.DataFrame(group_averages).T
    
    def calculate_group_statistics(
        self,
        metrics: Optional[List[str]] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Calculate comprehensive statistics for each group.
        
        Args:
            metrics: Optional list of metrics to include
            
        Returns:
            Dictionary with 'mean', 'std', 'min', 'max', 'count' DataFrames
            
        Requirements: 4.3
        """
        if not self._groups:
            raise ValueError("No groups defined. Call set_groups() first.")
        
        df = self.metrics_df
        if metrics:
            available_metrics = [m for m in metrics if m in df.columns]
            df = df[available_metrics]
        
        stats = {
            'mean': {},
            'std': {},
            'min': {},
            'max': {},
            'count': {}
        }
        
        for group_name, samples in self._groups.items():
            valid_samples = [s for s in samples if s in df.index]
            if valid_samples:
                group_data = df.loc[valid_samples]
                stats['mean'][group_name] = group_data.mean()
                stats['std'][group_name] = group_data.std()
                stats['min'][group_name] = group_data.min()
                stats['max'][group_name] = group_data.max()
                stats['count'][group_name] = len(valid_samples)
            else:
                for stat_name in stats:
                    if stat_name == 'count':
                        stats[stat_name][group_name] = 0
                    else:
                        stats[stat_name][group_name] = pd.Series(
                            {col: np.nan for col in df.columns}
                        )
        
        return {
            stat_name: pd.DataFrame(stat_data).T 
            for stat_name, stat_data in stats.items()
        }
    
    def calculate_percentage_difference(
        self,
        baseline_group: Optional[str] = None,
        metrics: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Calculate percentage difference of group averages relative to baseline.
        
        Args:
            baseline_group: Group name to use as baseline (100%).
                           If None, uses first group.
            metrics: Optional list of metrics to include
            
        Returns:
            DataFrame with percentage values (baseline = 100%)
            
        Requirements: 4.4
        """
        group_averages = self.calculate_group_averages(metrics)
        
        if group_averages.empty:
            return pd.DataFrame()
        
        # Determine baseline
        if baseline_group is not None and baseline_group in group_averages.index:
            baseline_values = group_averages.loc[baseline_group]
        else:
            baseline_values = group_averages.iloc[0]
        
        # Calculate percentage difference
        percentage_df = pd.DataFrame(
            index=group_averages.index,
            columns=group_averages.columns,
            dtype=float
        )
        
        for col in group_averages.columns:
            if baseline_values[col] > 0:
                percentage_df[col] = (group_averages[col] / baseline_values[col]) * 100
            else:
                percentage_df[col] = 0.0
        
        return percentage_df


class DiversityChartGenerator:
    """
    Generator for diversity metric visualizations.
    Requirements: 4.2, 4.4, 4.5, 4.6
    """
    
    # Default colors for metrics
    DEFAULT_METRIC_COLORS = {
        'd50': '#3498db',       # Blue
        'gini': '#e74c3c',      # Red
        'shannon': '#2ecc71',   # Green
        'simpson': '#f39c12'    # Orange
    }
    
    # Available color palettes
    COLOR_PALETTES = {
        'default': ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c'],
        'pastel': ['#a8d8ea', '#f8b4b4', '#b4f8b4', '#f8e4b4', '#d4b4f8', '#b4f8e4'],
        'bright': ['#0066ff', '#ff0066', '#00ff66', '#ffcc00', '#9900ff', '#00ffcc'],
        'dark': ['#1a5276', '#922b21', '#1e8449', '#b7950b', '#6c3483', '#117a65'],
        'colorblind': ['#0072B2', '#D55E00', '#009E73', '#F0E442', '#CC79A7', '#56B4E9']
    }
    
    def __init__(self, config: Optional[DiversityChartConfig] = None):
        """
        Initialize the diversity chart generator.
        
        Args:
            config: Optional default configuration for charts
        """
        self.default_config = config or DiversityChartConfig()
        
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
    
    def generate_comparison_chart(
        self,
        data: pd.DataFrame,
        metrics: List[str],
        config: Optional[DiversityChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a bar chart comparing diversity metrics across samples.
        
        Args:
            data: DataFrame with samples as index and metrics as columns
            metrics: List of metric column names to include
            config: Optional configuration
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 4.2
        """
        cfg = config or self.default_config
        
        # Filter to requested metrics
        available_metrics = [m for m in metrics if m in data.columns]
        if not available_metrics:
            raise ValueError("No valid metrics found in data")
        
        plot_data = data[available_metrics]
        samples = plot_data.index.tolist()
        n_samples = len(samples)
        n_metrics = len(available_metrics)
        
        # Calculate bar positions
        x = np.arange(n_samples)
        total_width = cfg.bar_width
        individual_width = total_width / n_metrics
        
        # Get colors
        colors = self._get_colors(available_metrics, cfg)
        
        # Create figure
        fig, ax = plt.subplots(figsize=(cfg.figure_width, cfg.figure_height))
        
        # Plot bars for each metric
        for i, (metric, color) in enumerate(zip(available_metrics, colors)):
            offset = (i - n_metrics / 2 + 0.5) * individual_width
            bars = ax.bar(
                x + offset,
                plot_data[metric],
                individual_width * (1 - cfg.bar_spacing),
                label=self._format_metric_name(metric),
                color=color,
                alpha=0.8
            )
            
            # Add value labels if requested
            if cfg.show_values:
                self._add_value_labels(ax, bars, cfg)
        
        # Configure axes
        ax.set_xlabel(cfg.x_label, fontsize=cfg.font_size, fontweight='bold')
        ax.set_ylabel(cfg.y_label, fontsize=cfg.font_size, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=cfg.x_rotation, ha='right', fontsize=cfg.font_size - 1)
        ax.tick_params(axis='y', labelsize=cfg.font_size - 1)
        
        if cfg.title:
            ax.set_title(cfg.title, fontsize=cfg.font_size + 4, fontweight='bold', pad=15)
        
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
            'title': cfg.title,
            'metrics': available_metrics,
            'samples': samples,
            'figure_size': (cfg.figure_width, cfg.figure_height),
            'dpi': cfg.dpi
        }
        
        return image_bytes, metadata
    
    def generate_single_metric_chart(
        self,
        data: pd.DataFrame,
        metric: str,
        config: Optional[DiversityChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a bar chart for a single diversity metric.
        
        Args:
            data: DataFrame with samples as index
            metric: Column name of the metric to plot
            config: Optional configuration
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 4.2
        """
        cfg = config or self.default_config
        
        if metric not in data.columns:
            raise ValueError(f"Metric '{metric}' not found in data")
        
        samples = data.index.tolist()
        values = data[metric].values
        
        # Get color
        color = self.DEFAULT_METRIC_COLORS.get(metric, '#3498db')
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
        ax.set_ylabel(cfg.y_label or self._format_metric_name(metric),
                     fontsize=cfg.font_size, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=cfg.x_rotation, ha='right', fontsize=cfg.font_size - 1)
        ax.tick_params(axis='y', labelsize=cfg.font_size - 1)
        
        title = cfg.title or self._format_metric_name(metric)
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
            'metric': metric,
            'samples': samples,
            'figure_size': (cfg.figure_width, cfg.figure_height),
            'dpi': cfg.dpi
        }
        
        return image_bytes, metadata
    
    def generate_group_comparison_chart(
        self,
        group_data: pd.DataFrame,
        metrics: List[str],
        config: Optional[DiversityChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a bar chart comparing group averages.
        
        Args:
            group_data: DataFrame with groups as index and metrics as columns
            metrics: List of metric column names to include
            config: Optional configuration
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 4.4
        """
        cfg = config or self.default_config
        
        # Use comparison chart with groups as samples
        return self.generate_comparison_chart(group_data, metrics, cfg)
    
    def generate_percentage_difference_chart(
        self,
        data: pd.DataFrame,
        metrics: List[str],
        baseline_label: str = "Baseline (100%)",
        config: Optional[DiversityChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a bar chart showing percentage differences relative to baseline.
        
        Args:
            data: DataFrame with percentage values (baseline = 100%)
            metrics: List of metric column names to include
            baseline_label: Label for the baseline reference line
            config: Optional configuration
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 4.4
        """
        cfg = config or self.default_config
        
        # Filter to requested metrics
        available_metrics = [m for m in metrics if m in data.columns]
        if not available_metrics:
            raise ValueError("No valid metrics found in data")
        
        plot_data = data[available_metrics]
        groups = plot_data.index.tolist()
        n_groups = len(groups)
        n_metrics = len(available_metrics)
        
        # Calculate bar positions
        x = np.arange(n_groups)
        total_width = cfg.bar_width
        individual_width = total_width / n_metrics
        
        # Get colors
        colors = self._get_colors(available_metrics, cfg)
        
        # Create figure
        fig, ax = plt.subplots(figsize=(cfg.figure_width, cfg.figure_height))
        
        # Plot bars for each metric
        for i, (metric, color) in enumerate(zip(available_metrics, colors)):
            offset = (i - n_metrics / 2 + 0.5) * individual_width
            bars = ax.bar(
                x + offset,
                plot_data[metric],
                individual_width * (1 - cfg.bar_spacing),
                label=self._format_metric_name(metric),
                color=color,
                alpha=0.8
            )
            
            # Add percentage difference labels
            if cfg.show_values:
                for bar in bars:
                    height = bar.get_height()
                    diff = height - 100
                    if abs(diff) > 0.1:
                        label = f"+{diff:.1f}%" if diff > 0 else f"{diff:.1f}%"
                    else:
                        label = "Baseline"
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        height,
                        label,
                        ha='center',
                        va='bottom',
                        fontsize=cfg.font_size - 3,
                        fontweight='bold'
                    )
        
        # Add baseline reference line
        ax.axhline(y=100, color='red', linestyle='--', alpha=0.7, linewidth=1.5,
                  label=baseline_label)
        
        # Configure axes
        ax.set_xlabel('Group', fontsize=cfg.font_size, fontweight='bold')
        ax.set_ylabel('Relative Percentage (%)', fontsize=cfg.font_size, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(groups, rotation=cfg.x_rotation, ha='right', fontsize=cfg.font_size - 1)
        ax.tick_params(axis='y', labelsize=cfg.font_size - 1)
        
        title = cfg.title or 'Group Percentage Difference Relative to Baseline'
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
            'metrics': available_metrics,
            'groups': groups,
            'baseline_label': baseline_label,
            'figure_size': (cfg.figure_width, cfg.figure_height),
            'dpi': cfg.dpi
        }
        
        return image_bytes, metadata
    
    def extract_data_table(
        self,
        data: pd.DataFrame,
        metrics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Extract data as a table format suitable for display and copying.
        
        Args:
            data: DataFrame with metrics
            metrics: Optional list of metrics to include
            
        Returns:
            Dictionary with table data for frontend display
            
        Requirements: 4.5, 4.6
        """
        if metrics:
            available_metrics = [m for m in metrics if m in data.columns]
            table_data = data[available_metrics].copy()
        else:
            table_data = data.copy()
        
        # Format column names for display
        formatted_columns = [self._format_metric_name(col) for col in table_data.columns]
        
        # Convert to list of dictionaries for JSON serialization
        records = []
        for sample in table_data.index:
            record = {'Sample': str(sample)}
            for col, formatted_col in zip(table_data.columns, formatted_columns):
                value = table_data.loc[sample, col]
                if pd.isna(value):
                    record[formatted_col] = None
                elif isinstance(value, float):
                    record[formatted_col] = round(value, 4)
                else:
                    record[formatted_col] = value
            records.append(record)
        
        return {
            'columns': ['Sample'] + formatted_columns,
            'data': records,
            'row_count': len(records)
        }
    
    def _get_colors(self, metrics: List[str], config: DiversityChartConfig) -> List[str]:
        """Get colors for the given metrics."""
        if config.colors and len(config.colors) >= len(metrics):
            return config.colors[:len(metrics)]
        
        # Use default metric colors
        colors = []
        for metric in metrics:
            if metric in self.DEFAULT_METRIC_COLORS:
                colors.append(self.DEFAULT_METRIC_COLORS[metric])
            else:
                idx = len(colors) % len(self.COLOR_PALETTES['default'])
                colors.append(self.COLOR_PALETTES['default'][idx])
        
        return colors
    
    def _add_value_labels(
        self,
        ax: plt.Axes,
        bars: Any,
        config: DiversityChartConfig
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
    
    def _format_metric_name(self, metric: str) -> str:
        """Format metric name for display."""
        name_mapping = {
            'd50': 'D50',
            'gini': 'Gini Index',
            'shannon': 'Shannon Entropy',
            'simpson': 'Simpson Index'
        }
        return name_mapping.get(metric, metric.replace('_', ' ').title())
    
    @classmethod
    def get_available_palettes(cls) -> List[str]:
        """Get list of available color palettes."""
        return list(cls.COLOR_PALETTES.keys())
    
    @classmethod
    def get_palette_colors(cls, palette_name: str) -> List[str]:
        """Get colors for a specific palette."""
        return cls.COLOR_PALETTES.get(palette_name, cls.COLOR_PALETTES['default']).copy()
