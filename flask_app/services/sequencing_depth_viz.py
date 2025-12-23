"""
Sequencing Depth Visualization Service
Generates comprehensive visualizations for sequencing depth analysis.
Refactored from sequencing_depth_visualization_final.py
Requirements: 14.2, 14.5
"""

import os
from typing import Dict, Any, Optional, Tuple, List
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import rcParams

# 设置中文字体
rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
rcParams["axes.unicode_minus"] = False


class SequencingDepthVisualizationService:
    """
    Service for generating comprehensive sequencing depth visualizations.
    Creates multi-panel charts showing various sequencing metrics.
    """
    
    # Default colors for metrics
    DEFAULT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9b59b6", "#8c564b"
    ]
    
    def __init__(self):
        """Initialize the visualization service."""
        pass
    
    @staticmethod
    def validate_parameters(
        data_file: str,
        output_path: str,
        parameters: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate input parameters for visualization generation.
        
        Args:
            data_file: Path to the Excel data file
            output_path: Directory path for output files
            parameters: Dictionary of analysis parameters
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check data file exists
        if not os.path.exists(data_file):
            return False, f"数据文件不存在: {data_file}"
        
        # Check data file extension
        if not data_file.endswith(('.xlsx', '.xls', '.csv')):
            return False, "数据文件必须是Excel或CSV格式"
        
        # Check output path is valid
        if not output_path:
            return False, "输出路径不能为空"
        
        return True, None
    
    @staticmethod
    def extract_sequencing_data(
        data_file: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Tuple[pd.DataFrame, List[str]]:
        """
        Extract sequencing data from Excel file.
        
        Args:
            data_file: Path to Excel file
            parameters: Optional parameters including sample_filter and sample_order
            
        Returns:
            Tuple of (DataFrame with metrics, list of sample names)
        """
        params = parameters or {}
        
        # Read data
        if data_file.endswith('.csv'):
            df = pd.read_csv(data_file)
        else:
            df = pd.read_excel(data_file)
        
        # Filter samples
        sample_filter = params.get('sample_filter', r'NW_11_\d{4}CT$')
        ct_samples = df[df["Sample"].str.contains(sample_filter, regex=True, na=False)]
        
        # Get sample order
        sample_order = params.get('sample_order')
        if sample_order:
            ct_samples = ct_samples.set_index("Sample").loc[sample_order].reset_index()
        else:
            sample_order = ct_samples["Sample"].tolist()
        
        # Extract sequencing metrics
        sequencing_data = []
        for _, row in ct_samples.iterrows():
            sample = row["Sample"]
            
            # Extract metrics
            total_rna = int(row["Total_Receptor_RNA"])
            reads_umi = float(row["Reads/UMI"])
            migs_good = int(row["MigsGoodTotal"])
            reads_good = int(row["ReadsGoodTotal"])
            
            # Calculate quality metrics
            qc_rate = (migs_good / total_rna * 100) if total_rna > 0 else 0
            utilization_rate = (reads_good / total_rna * 100) if total_rna > 0 else 0
            
            sequencing_data.append({
                "Sample": sample,
                "Total_Receptor_RNA": total_rna,
                "Reads_per_UMI": reads_umi,
                "MigsGood_Total": migs_good,
                "ReadsGood_Total": reads_good,
                "QC_Rate": qc_rate,
                "Utilization_Rate": utilization_rate,
            })
        
        sequencing_df = pd.DataFrame(sequencing_data)
        
        return sequencing_df, sample_order
    
    @staticmethod
    def generate_four_panel_chart(
        data_file: str,
        output_path: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate four-panel chart for main sequencing metrics.
        
        Args:
            data_file: Path to Excel file containing sequencing data
            output_path: Directory path to save output files
            parameters: Optional parameters including:
                - baseline_sample: Sample name to use as baseline
                - sample_filter: Regex pattern to filter samples
                - sample_order: List of sample names in desired order
                
        Returns:
            Dictionary with:
                - success: bool
                - output_file: str (path to generated PNG)
                - error: str (if success is False)
        """
        try:
            # Validate parameters
            params = parameters or {}
            is_valid, error_msg = SequencingDepthVisualizationService.validate_parameters(
                data_file, output_path, params
            )
            if not is_valid:
                return {'success': False, 'error': error_msg}
            
            # Extract data
            df, sample_order = SequencingDepthVisualizationService.extract_sequencing_data(
                data_file, params
            )
            
            if df.empty:
                return {'success': False, 'error': '未找到匹配的样本数据'}
            
            # Determine baseline sample
            baseline_sample = params.get('baseline_sample')
            if baseline_sample and baseline_sample in sample_order:
                baseline_index = sample_order.index(baseline_sample)
            else:
                baseline_index = len(sample_order) // 2
                baseline_sample = sample_order[baseline_index]
            
            # Create figure with 2x2 subplots
            fig, axes = plt.subplots(2, 2, figsize=(20, 16))
            fig.suptitle(
                f"Sequencing Metrics - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
                fontsize=20,
                fontweight="bold",
                y=0.98,
            )
            
            axes = axes.flatten()
            
            # Metrics to visualize
            metrics = [
                ("Total_Receptor_RNA", "Total Receptor RNA"),
                ("Reads_per_UMI", "Reads/UMI"),
                ("MigsGood_Total", "MigsGood Total"),
                ("ReadsGood_Total", "ReadsGood Total"),
            ]
            
            x_pos = np.arange(len(sample_order))
            bar_width = 0.6
            
            # Plot each metric
            for idx, ((metric_key, metric_name), ax) in enumerate(zip(metrics, axes)):
                # Get values
                values = df[metric_key].values
                baseline_value = values[baseline_index]
                
                # Calculate percentage changes
                pct_change = (values - baseline_value) / baseline_value * 100
                
                # Create bars
                bars = ax.bar(
                    x_pos, pct_change, bar_width,
                    color=SequencingDepthVisualizationService.DEFAULT_COLORS[idx],
                    alpha=0.8
                )
                
                # Highlight baseline bar
                bars[baseline_index].set_alpha(1.0)
                bars[baseline_index].set_edgecolor("black")
                bars[baseline_index].set_linewidth(2)
                
                # Add baseline reference line
                ax.axhline(
                    y=0, color="gray", linestyle="-", linewidth=2,
                    alpha=0.8, label="Baseline (0%)"
                )
                
                # Add value labels
                for j, bar in enumerate(bars):
                    height = bar.get_height()
                    if height >= 0:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height + max(pct_change) * 0.02,
                            f"+{height:.1f}%",
                            ha="center", va="bottom",
                            fontsize=9, fontweight="bold",
                            color=SequencingDepthVisualizationService.DEFAULT_COLORS[idx],
                        )
                    else:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height - max(pct_change) * 0.02,
                            f"{height:.1f}%",
                            ha="center", va="top",
                            fontsize=9, fontweight="bold",
                            color=SequencingDepthVisualizationService.DEFAULT_COLORS[idx],
                        )
                
                # Customize subplot
                ax.set_xticks(x_pos)
                ax.set_xticklabels(sample_order, rotation=45, ha="right", fontsize=11)
                ax.set_ylabel("Percentage Change from Baseline (%)", fontsize=14, fontweight="bold")
                ax.set_xlabel("Sample", fontsize=14, fontweight="bold")
                ax.set_title(metric_name, fontsize=16, fontweight="bold", pad=20)
                ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
                ax.grid(axis="y", alpha=0.3, linestyle="--")
                
                # Set y-axis limits
                ymin = min(pct_change) * 1.1 if min(pct_change) < 0 else -5
                ymax = max(pct_change) * 1.1 if max(pct_change) > 0 else 5
                ax.set_ylim(ymin, ymax)
                
                ax.set_facecolor("#f8f9fa")
            
            plt.tight_layout()
            plt.subplots_adjust(top=0.93)
            
            # Create output directory
            os.makedirs(output_path, exist_ok=True)
            
            # Save figure
            output_file = os.path.join(output_path, "sequencing_metrics_four_panel.png")
            fig.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            
            return {
                'success': True,
                'output_file': output_file,
                'baseline_sample': baseline_sample,
                'sample_count': len(sample_order)
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def generate_quality_metrics_chart(
        data_file: str,
        output_path: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate quality metrics comparison chart.
        
        Args:
            data_file: Path to Excel file containing sequencing data
            output_path: Directory path to save output files
            parameters: Optional parameters
                
        Returns:
            Dictionary with:
                - success: bool
                - output_file: str (path to generated PNG)
                - error: str (if success is False)
        """
        try:
            # Validate parameters
            params = parameters or {}
            is_valid, error_msg = SequencingDepthVisualizationService.validate_parameters(
                data_file, output_path, params
            )
            if not is_valid:
                return {'success': False, 'error': error_msg}
            
            # Extract data
            df, sample_order = SequencingDepthVisualizationService.extract_sequencing_data(
                data_file, params
            )
            
            if df.empty:
                return {'success': False, 'error': '未找到匹配的样本数据'}
            
            # Determine baseline sample
            baseline_sample = params.get('baseline_sample')
            if baseline_sample and baseline_sample in sample_order:
                baseline_index = sample_order.index(baseline_sample)
            else:
                baseline_index = len(sample_order) // 2
                baseline_sample = sample_order[baseline_index]
            
            # Create figure with 1x2 subplots
            fig, axes = plt.subplots(1, 2, figsize=(20, 8))
            fig.suptitle(
                f"Quality Metrics - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
                fontsize=20,
                fontweight="bold",
                y=0.98,
            )
            
            quality_metrics = [
                ("QC_Rate", "QC Rate"),
                ("Utilization_Rate", "Utilization Rate")
            ]
            
            x_pos = np.arange(len(sample_order))
            bar_width = 0.6
            
            for idx, ((metric_key, metric_name), ax) in enumerate(zip(quality_metrics, axes)):
                # Get values
                values = df[metric_key].values
                baseline_value = values[baseline_index]
                
                # Calculate percentage changes
                pct_change = (values - baseline_value) / baseline_value * 100
                
                # Create bars
                bars = ax.bar(
                    x_pos, pct_change, bar_width,
                    color=SequencingDepthVisualizationService.DEFAULT_COLORS[idx + 4],
                    alpha=0.8
                )
                
                # Highlight baseline bar
                bars[baseline_index].set_alpha(1.0)
                bars[baseline_index].set_edgecolor("black")
                bars[baseline_index].set_linewidth(2)
                
                # Add baseline reference line
                ax.axhline(
                    y=0, color="gray", linestyle="-", linewidth=2,
                    alpha=0.8, label="Baseline (0%)"
                )
                
                # Add value labels
                for j, bar in enumerate(bars):
                    height = bar.get_height()
                    if height >= 0:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height + max(pct_change) * 0.02,
                            f"+{height:.1f}%",
                            ha="center", va="bottom",
                            fontsize=9, fontweight="bold",
                            color=SequencingDepthVisualizationService.DEFAULT_COLORS[idx + 4],
                        )
                    else:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height - max(pct_change) * 0.02,
                            f"{height:.1f}%",
                            ha="center", va="top",
                            fontsize=9, fontweight="bold",
                            color=SequencingDepthVisualizationService.DEFAULT_COLORS[idx + 4],
                        )
                
                # Customize subplot
                ax.set_xticks(x_pos)
                ax.set_xticklabels(sample_order, rotation=45, ha="right", fontsize=11)
                ax.set_ylabel("Percentage Change from Baseline (%)", fontsize=14, fontweight="bold")
                ax.set_xlabel("Sample", fontsize=14, fontweight="bold")
                ax.set_title(metric_name, fontsize=16, fontweight="bold", pad=20)
                ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
                ax.grid(axis="y", alpha=0.3, linestyle="--")
                
                # Set y-axis limits
                ymin = min(pct_change) * 1.1 if min(pct_change) < 0 else -5
                ymax = max(pct_change) * 1.1 if max(pct_change) > 0 else 5
                ax.set_ylim(ymin, ymax)
                
                ax.set_facecolor("#f8f9fa")
            
            plt.tight_layout()
            plt.subplots_adjust(top=0.93)
            
            # Create output directory
            os.makedirs(output_path, exist_ok=True)
            
            # Save figure
            output_file = os.path.join(output_path, "quality_metrics_comparison.png")
            fig.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            
            return {
                'success': True,
                'output_file': output_file,
                'baseline_sample': baseline_sample,
                'sample_count': len(sample_order)
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def generate_visualization(
        data_file: str,
        output_path: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate all visualization charts.
        
        Args:
            data_file: Path to Excel file containing sequencing data
            output_path: Directory path to save output files
            parameters: Optional parameters for customization
                
        Returns:
            Dictionary with:
                - success: bool
                - four_panel_file: str (path to four-panel PNG)
                - quality_file: str (path to quality metrics PNG)
                - csv_file: str (path to extracted CSV data)
                - error: str (if success is False)
        """
        try:
            # Extract and save data to CSV
            params = parameters or {}
            df, sample_order = SequencingDepthVisualizationService.extract_sequencing_data(
                data_file, params
            )
            
            # Create output directory
            os.makedirs(output_path, exist_ok=True)
            
            # Save CSV
            csv_file = os.path.join(output_path, "sequencing_data.csv")
            df.to_csv(csv_file, index=False)
            
            # Generate four-panel chart
            four_panel_result = SequencingDepthVisualizationService.generate_four_panel_chart(
                data_file, output_path, params
            )
            
            if not four_panel_result['success']:
                return four_panel_result
            
            # Generate quality metrics chart
            quality_result = SequencingDepthVisualizationService.generate_quality_metrics_chart(
                data_file, output_path, params
            )
            
            if not quality_result['success']:
                return quality_result
            
            return {
                'success': True,
                'four_panel_file': four_panel_result['output_file'],
                'quality_file': quality_result['output_file'],
                'csv_file': csv_file,
                'baseline_sample': four_panel_result['baseline_sample'],
                'sample_count': four_panel_result['sample_count']
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
