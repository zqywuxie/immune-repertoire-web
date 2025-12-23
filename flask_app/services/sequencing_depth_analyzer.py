"""
Sequencing Depth Analyzer Service for the Immune Repertoire Analysis Web Application.
Implements sequencing depth metrics calculation and visualization.
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 7.6

Metrics implemented:
1. Total Receptor RNA - Raw sequencing depth
2. Reads/UMI - Library complexity ratio
3. MigsGoodTotal - Quality filtered reads
4. ReadsGoodTotal - Final usable reads
5. QC Rate - Quality control rate (MigsGoodTotal / Total Receptor RNA * 100)
6. Final Utilization Rate - Final utilization (ReadsGoodTotal / Total Receptor RNA * 100)
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
class BarChartConfig:
    """
    Configuration for bar chart visualization.
    Requirements: 7.6
    """
    title: str = ""
    figure_width: int = 12
    figure_height: int = 8
    font_size: int = 12
    dpi: int = 300
    bar_width: float = 0.8
    bar_spacing: float = 0.2
    show_values: bool = True
    value_format: str = "{:.1f}"
    colors: Optional[List[str]] = None
    x_label: str = "Sample"
    y_label: str = "Value"
    x_rotation: int = 45
    legend_location: str = "upper right"
    grid: bool = True
    grid_alpha: float = 0.3


class SequencingDepthAnalyzer:
    """
    Analyzer for sequencing depth metrics.
    Calculates various sequencing quality metrics and generates visualizations.
    Requirements: 3.1, 3.2, 3.3, 3.4
    """
    
    # Default metric columns
    DEFAULT_METRICS = [
        'total_receptor_rna',
        'reads_umi',
        'migs_good_total',
        'reads_good_total'
    ]
    
    # Default colors for metrics
    DEFAULT_COLORS = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c']
    
    def __init__(
        self,
        data: pd.DataFrame,
        field_mapping: Dict[str, str],
        chart_config: Optional[BarChartConfig] = None
    ):
        """
        Initialize the sequencing depth analyzer.
        
        Args:
            data: DataFrame containing sequencing depth data
            field_mapping: Mapping from required fields to actual column names
                Required fields: 'sample', 'total_receptor_rna', 'reads_umi', 
                                'migs_good_total', 'reads_good_total'
            chart_config: Optional configuration for chart generation
        """
        self.data = data
        self.field_mapping = field_mapping
        self.chart_config = chart_config or BarChartConfig()
        
        # Extract column names from mapping
        self.sample_col = field_mapping.get('sample', 'sample')
        self.total_rna_col = field_mapping.get('total_receptor_rna', 'Total Receptor RNA')
        self.reads_umi_col = field_mapping.get('reads_umi', 'Reads/UMI')
        self.migs_good_col = field_mapping.get('migs_good_total', 'MigsGoodTotal')
        self.reads_good_col = field_mapping.get('reads_good_total', 'ReadsGoodTotal')
        
        # Prepare data
        self._samples: List[str] = []
        self._metrics_df: Optional[pd.DataFrame] = None
        self._prepare_data()
    
    def _prepare_data(self) -> None:
        """Prepare data structures for analysis."""
        if self.data.empty:
            return
        
        # Get unique samples
        if self.sample_col in self.data.columns:
            self._samples = self.data[self.sample_col].dropna().unique().tolist()
        else:
            self._samples = list(range(len(self.data)))
            self.data = self.data.copy()
            self.data[self.sample_col] = self._samples
        
        # Build metrics DataFrame
        metrics_data = {self.sample_col: self._samples}
        
        for col_name, mapped_col in [
            ('total_receptor_rna', self.total_rna_col),
            ('reads_umi', self.reads_umi_col),
            ('migs_good_total', self.migs_good_col),
            ('reads_good_total', self.reads_good_col)
        ]:
            if mapped_col in self.data.columns:
                if self.sample_col in self.data.columns:
                    # Group by sample and aggregate
                    grouped = self.data.groupby(self.sample_col)[mapped_col].first()
                    metrics_data[col_name] = [grouped.get(s, 0) for s in self._samples]
                else:
                    metrics_data[col_name] = self.data[mapped_col].tolist()
        
        self._metrics_df = pd.DataFrame(metrics_data)
        self._metrics_df.set_index(self.sample_col, inplace=True)
    
    @property
    def samples(self) -> List[str]:
        """Get list of sample names."""
        return self._samples
    
    @property
    def metrics_df(self) -> pd.DataFrame:
        """Get the metrics DataFrame."""
        return self._metrics_df if self._metrics_df is not None else pd.DataFrame()

    
    def get_metrics(self) -> pd.DataFrame:
        """
        Get the basic sequencing depth metrics.
        
        Returns:
            DataFrame with columns: total_receptor_rna, reads_umi, 
                                   migs_good_total, reads_good_total
            Index: sample names
            
        Requirements: 3.1
        """
        return self.metrics_df.copy()
    
    def calculate_qc_rate(self) -> pd.Series:
        """
        Calculate QC Rate for each sample.
        
        Formula: QC Rate = MigsGoodTotal / Total Receptor RNA * 100
        
        Returns:
            Series with QC Rate (%) for each sample
            
        Requirements: 3.4
        """
        if self._metrics_df is None or self._metrics_df.empty:
            return pd.Series(dtype=float)
        
        total_rna = self._metrics_df.get('total_receptor_rna', pd.Series(dtype=float))
        migs_good = self._metrics_df.get('migs_good_total', pd.Series(dtype=float))
        
        # Avoid division by zero
        qc_rate = pd.Series(index=self._metrics_df.index, dtype=float)
        mask = total_rna > 0
        qc_rate[mask] = (migs_good[mask] / total_rna[mask]) * 100
        qc_rate[~mask] = 0.0
        
        return qc_rate
    
    def calculate_final_utilization_rate(self) -> pd.Series:
        """
        Calculate Final Utilization Rate for each sample.
        
        Formula: Final Utilization Rate = ReadsGoodTotal / Total Receptor RNA * 100
        
        Returns:
            Series with Final Utilization Rate (%) for each sample
            
        Requirements: 3.4
        """
        if self._metrics_df is None or self._metrics_df.empty:
            return pd.Series(dtype=float)
        
        total_rna = self._metrics_df.get('total_receptor_rna', pd.Series(dtype=float))
        reads_good = self._metrics_df.get('reads_good_total', pd.Series(dtype=float))
        
        # Avoid division by zero
        utilization_rate = pd.Series(index=self._metrics_df.index, dtype=float)
        mask = total_rna > 0
        utilization_rate[mask] = (reads_good[mask] / total_rna[mask]) * 100
        utilization_rate[~mask] = 0.0
        
        return utilization_rate
    
    def calculate_quality_metrics(self) -> pd.DataFrame:
        """
        Calculate all quality metrics (QC Rate and Final Utilization Rate).
        
        Returns:
            DataFrame with columns: qc_rate, final_utilization_rate
            Index: sample names
            
        Requirements: 3.4
        """
        return pd.DataFrame({
            'qc_rate': self.calculate_qc_rate(),
            'final_utilization_rate': self.calculate_final_utilization_rate()
        })
    
    def calculate_percentage_difference(
        self,
        baseline_sample: Optional[str] = None,
        use_minimum: bool = False,
        metrics: Optional[List[str]] = None,
        baseline_type: Optional[str] = None,
        baseline_values: Optional[Dict[str, float]] = None
    ) -> pd.DataFrame:
        """
        Calculate percentage difference relative to a baseline sample or group.
        
        Args:
            baseline_sample: Sample name to use as baseline (100%).
                            If None and use_minimum=False, uses first sample.
            use_minimum: If True, use the sample with minimum values as baseline.
            metrics: List of metric columns to calculate. If None, uses all available.
            baseline_type: Type of baseline ('sample' or 'group'). If 'group', 
                          baseline_values must be provided.
            baseline_values: Pre-calculated baseline values for group baseline.
                            Dict mapping metric names to baseline values.
        
        Returns:
            DataFrame with percentage values relative to baseline (baseline = 100%)
            
        Requirements: 3.3, 3.7
        """
        if self._metrics_df is None or self._metrics_df.empty:
            return pd.DataFrame()
        
        df = self._metrics_df.copy()
        
        # Select metrics to calculate
        if metrics is None:
            metrics = [col for col in df.columns if col in self.DEFAULT_METRICS]
        else:
            metrics = [m for m in metrics if m in df.columns]
        
        if not metrics:
            return pd.DataFrame()
        
        df = df[metrics]
        
        # Determine baseline values
        if baseline_type == 'group' and baseline_values is not None:
            # Use pre-calculated group baseline values
            baseline_series = pd.Series({m: baseline_values.get(m, 0.0) for m in metrics})
        elif use_minimum:
            # Use minimum value for each metric
            baseline_series = df.min()
        elif baseline_sample is not None and baseline_sample in df.index:
            baseline_series = df.loc[baseline_sample]
        else:
            # Use first sample as baseline
            baseline_series = df.iloc[0]
        
        # Calculate percentage difference
        # Avoid division by zero
        percentage_df = pd.DataFrame(index=df.index, columns=df.columns, dtype=float)
        for col in df.columns:
            if baseline_series[col] > 0:
                percentage_df[col] = (df[col] / baseline_series[col]) * 100
            else:
                percentage_df[col] = 0.0
        
        return percentage_df
    
    def calculate_percentage_difference_with_baseline(
        self,
        baseline_type: str,
        baseline_id: str,
        metrics: Optional[List[str]] = None,
        group_sample_ids: Optional[List[str]] = None
    ) -> Tuple[pd.DataFrame, Dict[str, float]]:
        """
        Calculate percentage difference with flexible baseline selection.
        
        Supports both individual sample and group baselines.
        
        Args:
            baseline_type: 'sample' or 'group'
            baseline_id: Sample name or group identifier
            metrics: List of metric columns to calculate. If None, uses all available.
            group_sample_ids: List of sample IDs if baseline_type is 'group'
        
        Returns:
            Tuple of (percentage_df, baseline_values_dict)
            
        Requirements: 3.7, 17.1, 17.2
        """
        if self._metrics_df is None or self._metrics_df.empty:
            return pd.DataFrame(), {}
        
        df = self._metrics_df.copy()
        
        # Select metrics to calculate
        if metrics is None:
            metrics = [col for col in df.columns if col in self.DEFAULT_METRICS]
        else:
            metrics = [m for m in metrics if m in df.columns]
        
        if not metrics:
            return pd.DataFrame(), {}
        
        df = df[metrics]
        
        # Calculate baseline values based on type
        baseline_values = {}
        
        if baseline_type == 'sample':
            if baseline_id in df.index:
                for col in metrics:
                    baseline_values[col] = float(df.loc[baseline_id, col])
            else:
                # Fallback to first sample
                for col in metrics:
                    baseline_values[col] = float(df.iloc[0][col])
        
        elif baseline_type == 'group':
            if group_sample_ids:
                # Calculate group average for each metric
                valid_samples = [s for s in group_sample_ids if s in df.index]
                if valid_samples:
                    for col in metrics:
                        baseline_values[col] = float(df.loc[valid_samples, col].mean())
                else:
                    for col in metrics:
                        baseline_values[col] = float(df.iloc[0][col])
            else:
                for col in metrics:
                    baseline_values[col] = float(df.iloc[0][col])
        
        else:
            # Default to first sample
            for col in metrics:
                baseline_values[col] = float(df.iloc[0][col])
        
        # Calculate percentage differences
        percentage_df = self.calculate_percentage_difference(
            metrics=metrics,
            baseline_type=baseline_type,
            baseline_values=baseline_values
        )
        
        return percentage_df, baseline_values
    
    def get_baseline_sample(self, use_minimum: bool = True) -> str:
        """
        Get the baseline sample name.
        
        Args:
            use_minimum: If True, returns sample with minimum total_receptor_rna.
                        Otherwise returns first sample.
        
        Returns:
            Sample name to use as baseline
        """
        if not self._samples:
            return ""
        
        if use_minimum and self._metrics_df is not None and 'total_receptor_rna' in self._metrics_df.columns:
            return self._metrics_df['total_receptor_rna'].idxmin()
        
        return self._samples[0]
    
    def get_available_baselines(self) -> Dict[str, Any]:
        """
        Get available baseline options (samples and groups).
        
        Returns:
            Dictionary with 'samples' list and placeholder for 'groups'
            
        Requirements: 17.3
        """
        return {
            'samples': self._samples.copy(),
            'groups': []  # Groups are managed externally via GroupingService
        }



class BarChartGenerator:
    """
    Generator for bar chart visualizations.
    Supports customizable bar width, spacing, colors, and other configurations.
    Requirements: 3.2, 3.5, 3.6, 7.6
    """
    
    # Default colors for different metrics
    DEFAULT_METRIC_COLORS = {
        'total_receptor_rna': '#3498db',  # Blue
        'reads_umi': '#e74c3c',           # Red
        'migs_good_total': '#2ecc71',     # Green
        'reads_good_total': '#f39c12',    # Orange
        'qc_rate': '#9b59b6',             # Purple
        'final_utilization_rate': '#1abc9c'  # Teal
    }
    
    # Available color palettes
    AVAILABLE_PALETTES = [
        'default', 'pastel', 'bright', 'dark', 'colorblind'
    ]
    
    # Predefined color palettes
    COLOR_PALETTES = {
        'default': ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c'],
        'pastel': ['#a8d8ea', '#f8b4b4', '#b4f8b4', '#f8e4b4', '#d4b4f8', '#b4f8e4'],
        'bright': ['#0066ff', '#ff0066', '#00ff66', '#ffcc00', '#9900ff', '#00ffcc'],
        'dark': ['#1a5276', '#922b21', '#1e8449', '#b7950b', '#6c3483', '#117a65'],
        'colorblind': ['#0072B2', '#D55E00', '#009E73', '#F0E442', '#CC79A7', '#56B4E9']
    }
    
    def __init__(self, config: Optional[BarChartConfig] = None):
        """
        Initialize the bar chart generator.
        
        Args:
            config: Optional default configuration for bar charts
        """
        self.default_config = config or BarChartConfig()
        
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
        config: Optional[BarChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a bar chart comparing multiple metrics across samples.
        
        Args:
            data: DataFrame with samples as index and metrics as columns
            metrics: List of metric column names to include
            config: Optional configuration (uses default if not provided)
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 3.2, 7.6
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
        config: Optional[BarChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a bar chart for a single metric across samples.
        
        Args:
            data: DataFrame with samples as index
            metric: Column name of the metric to plot
            config: Optional configuration
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 3.2, 7.6
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

    
    def generate_percentage_difference_chart(
        self,
        data: pd.DataFrame,
        metrics: List[str],
        baseline_label: str = "Baseline (100%)",
        config: Optional[BarChartConfig] = None
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
            
        Requirements: 3.3, 7.6
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
            
            # Add percentage difference labels
            if cfg.show_values:
                for bar in bars:
                    height = bar.get_height()
                    diff = height - 100
                    if abs(diff) > 0.1:  # Only show if difference is significant
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
        ax.set_xlabel(cfg.x_label, fontsize=cfg.font_size, fontweight='bold')
        ax.set_ylabel('Relative Percentage (%)', fontsize=cfg.font_size, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=cfg.x_rotation, ha='right', fontsize=cfg.font_size - 1)
        ax.tick_params(axis='y', labelsize=cfg.font_size - 1)
        
        title = cfg.title or 'Percentage Difference Relative to Baseline'
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
            'samples': samples,
            'baseline_label': baseline_label,
            'figure_size': (cfg.figure_width, cfg.figure_height),
            'dpi': cfg.dpi
        }
        
        return image_bytes, metadata
    
    def generate_quality_metrics_chart(
        self,
        data: pd.DataFrame,
        config: Optional[BarChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Generate a bar chart for quality metrics (QC Rate and Final Utilization Rate).
        
        Args:
            data: DataFrame with qc_rate and final_utilization_rate columns
            config: Optional configuration
            
        Returns:
            Tuple of (PNG image bytes, metadata dict)
            
        Requirements: 3.4, 7.6
        """
        cfg = config or self.default_config
        
        metrics = ['qc_rate', 'final_utilization_rate']
        available_metrics = [m for m in metrics if m in data.columns]
        
        if not available_metrics:
            raise ValueError("No quality metrics found in data")
        
        # Override y_label for percentage
        quality_config = BarChartConfig(
            title=cfg.title or 'Data Quality Metrics Comparison',
            figure_width=cfg.figure_width,
            figure_height=cfg.figure_height,
            font_size=cfg.font_size,
            dpi=cfg.dpi,
            bar_width=cfg.bar_width,
            bar_spacing=cfg.bar_spacing,
            show_values=cfg.show_values,
            value_format="{:.1f}%",
            colors=cfg.colors or ['#9b59b6', '#1abc9c'],
            x_label=cfg.x_label,
            y_label='Percentage (%)',
            x_rotation=cfg.x_rotation,
            legend_location=cfg.legend_location,
            grid=cfg.grid,
            grid_alpha=cfg.grid_alpha
        )
        
        return self.generate_comparison_chart(data, available_metrics, quality_config)
    
    def _get_colors(self, metrics: List[str], config: BarChartConfig) -> List[str]:
        """Get colors for the given metrics."""
        if config.colors and len(config.colors) >= len(metrics):
            return config.colors[:len(metrics)]
        
        # Use default metric colors
        colors = []
        for metric in metrics:
            if metric in self.DEFAULT_METRIC_COLORS:
                colors.append(self.DEFAULT_METRIC_COLORS[metric])
            else:
                # Fallback to palette
                idx = len(colors) % len(self.COLOR_PALETTES['default'])
                colors.append(self.COLOR_PALETTES['default'][idx])
        
        return colors
    
    def _add_value_labels(
        self, 
        ax: plt.Axes, 
        bars: Any, 
        config: BarChartConfig
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
            'total_receptor_rna': 'Total Receptor RNA',
            'reads_umi': 'Reads/UMI',
            'migs_good_total': 'MigsGoodTotal',
            'reads_good_total': 'ReadsGoodTotal',
            'qc_rate': 'QC Rate',
            'final_utilization_rate': 'Final Utilization Rate'
        }
        return name_mapping.get(metric, metric.replace('_', ' ').title())
    
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
            
        Requirements: 3.5, 3.6
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
    
    @classmethod
    def get_available_palettes(cls) -> List[str]:
        """Get list of available color palettes."""
        return cls.AVAILABLE_PALETTES.copy()
    
    @classmethod
    def get_palette_colors(cls, palette_name: str) -> List[str]:
        """Get colors for a specific palette."""
        return cls.COLOR_PALETTES.get(palette_name, cls.COLOR_PALETTES['default']).copy()
