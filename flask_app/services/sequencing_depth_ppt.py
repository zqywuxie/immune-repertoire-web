"""
Sequencing Depth PPT Module Service
Generates PPT-ready visualizations for sequencing depth analysis.
Refactored from sequencing_depth_ppt_module_final.py
Requirements: 14.1, 14.4
"""

import os
from typing import Dict, Any, Optional, Tuple
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import rcParams

# 设置中文字体
rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
rcParams["axes.unicode_minus"] = False


class SequencingDepthPPTService:
    """
    Service for generating PPT-ready sequencing depth visualizations.
    Creates table and bar chart modules suitable for PowerPoint insertion.
    """
    
    def __init__(self):
        """Initialize the PPT service."""
        pass
    
    @staticmethod
    def validate_parameters(
        data_file: str,
        output_path: str,
        parameters: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate input parameters for PPT generation.
        
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
        if not data_file.endswith(('.xlsx', '.xls')):
            return False, "数据文件必须是Excel格式 (.xlsx 或 .xls)"
        
        # Check output path is valid
        if not output_path:
            return False, "输出路径不能为空"
        
        # Validate baseline sample if provided
        baseline_sample = parameters.get('baseline_sample')
        if baseline_sample and not isinstance(baseline_sample, str):
            return False, "基准样本名称必须是字符串"
        
        return True, None
    
    @staticmethod
    def generate_ppt_table(
        data_file: str,
        output_path: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate PPT-ready table module showing sequencing depth differences.
        
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
            is_valid, error_msg = SequencingDepthPPTService.validate_parameters(
                data_file, output_path, params
            )
            if not is_valid:
                return {'success': False, 'error': error_msg}
            
            # Read data from Excel
            df = pd.read_excel(data_file)
            
            # Filter for CT samples (or use custom filter)
            sample_filter = params.get('sample_filter', r'NW_11_\d{4}CT$')
            ct_samples = df[df["Sample"].str.contains(sample_filter, regex=True, na=False)]
            
            if ct_samples.empty:
                return {'success': False, 'error': f'未找到匹配的样本 (过滤器: {sample_filter})'}
            
            # Get sample order
            sample_order = params.get('sample_order')
            if sample_order:
                # Use provided order
                ct_samples = ct_samples.set_index("Sample").loc[sample_order].reset_index()
            else:
                # Use default order from data
                sample_order = ct_samples["Sample"].tolist()
            
            # Extract data for visualization
            data = {
                "Total Receptor RNA": ct_samples["Total_Receptor_RNA"].tolist(),
                "MigsGoodTotal": ct_samples["MigsGoodTotal"].tolist(),
                "ReadsGoodTotal": ct_samples["ReadsGoodTotal"].tolist(),
            }
            
            samples = sample_order
            df_data = pd.DataFrame(data, index=samples)
            
            # Determine baseline sample
            baseline_sample = params.get('baseline_sample')
            if baseline_sample and baseline_sample in samples:
                baseline_index = samples.index(baseline_sample)
            else:
                # Use middle sample as default
                baseline_index = len(samples) // 2
                baseline_sample = samples[baseline_index]
            
            baseline_values = df_data.iloc[baseline_index]
            
            # Calculate relative percentages
            percentage_diff = df_data.div(baseline_values) * 100
            
            # Create table figure
            fig, ax = plt.subplots(1, 1, figsize=(12, 3.5))
            fig.patch.set_facecolor("none")  # Transparent background
            ax.set_facecolor("none")  # Transparent background
            
            # Set margins to 0
            plt.margins(0, 0)
            ax.set_position([0, 0, 1, 1])
            
            # Prepare table data
            table_data = []
            for i, sample in enumerate(samples):
                row = [sample]
                for metric in data.keys():
                    diff = percentage_diff.loc[sample, metric] - 100
                    if i == baseline_index:
                        row.append("Baseline")
                    elif diff > 0:
                        row.append(f"+{diff:.1f}%")
                    else:
                        row.append(f"{diff:.1f}%")
                table_data.append(row)
            
            # Create table
            table = ax.table(
                cellText=table_data,
                colLabels=["Sample", "Total RNA", "MigsGood", "ReadsGood"],
                cellLoc="center",
                loc="center",
                colWidths=[0.12, 0.22, 0.22, 0.22],
            )
            
            # Set table style
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1, 1.5)
            
            # Set header color
            for i in range(len(data.keys()) + 1):
                table[(0, i)].set_facecolor("#34495e")
                table[(0, i)].set_text_props(weight="bold", color="white")
            
            # Highlight baseline sample row
            for j in range(len(data.keys()) + 1):
                table[(baseline_index + 1, j)].set_facecolor("#ffebee")
                table[(baseline_index + 1, j)].set_text_props(color="red", weight="bold")
            
            # Hide axes
            ax.axis("off")
            
            plt.tight_layout(pad=0)
            
            # Create output directory
            os.makedirs(output_path, exist_ok=True)
            
            # Save figure
            output_file = os.path.join(output_path, "sequencing_depth_table.png")
            fig.savefig(
                output_file,
                dpi=300,
                bbox_inches="tight",
                facecolor="none",
                edgecolor="none",
                transparent=True,
            )
            plt.close(fig)
            
            return {
                'success': True,
                'output_file': output_file,
                'baseline_sample': baseline_sample,
                'sample_count': len(samples)
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def generate_ppt_bar_chart(
        data_file: str,
        output_path: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate PPT-ready bar chart showing sequencing depth differences.
        
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
            is_valid, error_msg = SequencingDepthPPTService.validate_parameters(
                data_file, output_path, params
            )
            if not is_valid:
                return {'success': False, 'error': error_msg}
            
            # Read data from Excel
            df = pd.read_excel(data_file)
            
            # Filter for CT samples (or use custom filter)
            sample_filter = params.get('sample_filter', r'NW_11_\d{4}CT$')
            ct_samples = df[df["Sample"].str.contains(sample_filter, regex=True, na=False)]
            
            if ct_samples.empty:
                return {'success': False, 'error': f'未找到匹配的样本 (过滤器: {sample_filter})'}
            
            # Get sample order
            sample_order = params.get('sample_order')
            if sample_order:
                ct_samples = ct_samples.set_index("Sample").loc[sample_order].reset_index()
            else:
                sample_order = ct_samples["Sample"].tolist()
            
            # Extract data
            data = {
                "Total Receptor RNA": ct_samples["Total_Receptor_RNA"].tolist(),
                "MigsGoodTotal": ct_samples["MigsGoodTotal"].tolist(),
                "ReadsGoodTotal": ct_samples["ReadsGoodTotal"].tolist(),
            }
            
            df_data = pd.DataFrame(data, index=sample_order)
            
            # Determine baseline sample
            baseline_sample = params.get('baseline_sample')
            if baseline_sample and baseline_sample in sample_order:
                baseline_index = sample_order.index(baseline_sample)
            else:
                baseline_index = len(sample_order) // 2
                baseline_sample = sample_order[baseline_index]
            
            baseline_values = df_data.iloc[baseline_index]
            
            # Calculate percentage difference
            percentage_diff = df_data.div(baseline_values) * 100 - 100
            
            # Create figure
            fig, ax = plt.subplots(1, 1, figsize=(14, 6))
            fig.patch.set_facecolor("none")
            ax.set_facecolor("none")
            
            # Set colors
            colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]
            x = np.arange(len(sample_order))
            width = 0.25
            
            # Plot bars
            for i, (metric, color) in enumerate(zip(data.keys(), colors)):
                bars = ax.bar(
                    x + i * width,
                    percentage_diff[metric],
                    width,
                    label=metric,
                    color=color,
                    alpha=0.8,
                )
                
                # Highlight baseline sample
                bars[baseline_index].set_edgecolor("black")
                bars[baseline_index].set_linewidth(2)
                bars[baseline_index].set_alpha(1.0)
                
                # Add value labels
                for j, bar in enumerate(bars):
                    height = bar.get_height()
                    if j == baseline_index:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height + 1,
                            "基准",
                            ha="center",
                            va="bottom",
                            fontsize=8,
                            fontweight="bold",
                            color="red",
                        )
                    elif height > 0:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height + 1,
                            f"+{height:.0f}%",
                            ha="center",
                            va="bottom",
                            fontsize=8,
                            fontweight="bold",
                        )
                    else:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height - 2,
                            f"{height:.0f}%",
                            ha="center",
                            va="top",
                            fontsize=8,
                            fontweight="bold",
                        )
            
            # Add baseline line
            ax.axhline(y=0, color="red", linestyle="--", alpha=0.7, label="Baseline (0%)")
            
            # Configure chart
            ax.set_title(
                f"Sequencing Depth Differences (Baseline: {baseline_sample})",
                fontsize=14,
                fontweight="bold",
            )
            ax.set_ylabel("Percentage Difference (%)", fontsize=12)
            ax.set_xlabel("Sample", fontsize=12)
            ax.set_xticks(x + width)
            ax.set_xticklabels(sample_order, rotation=45, ha="right")
            ax.legend(loc="upper left", fontsize=10)
            ax.grid(axis="y", alpha=0.3)
            
            plt.tight_layout()
            
            # Create output directory
            os.makedirs(output_path, exist_ok=True)
            
            # Save figure
            output_file = os.path.join(output_path, "sequencing_depth_bar_chart.png")
            fig.savefig(
                output_file,
                dpi=300,
                bbox_inches="tight",
                facecolor="none",
                edgecolor="none",
                transparent=True,
            )
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
    def generate_ppt(
        data_file: str,
        output_path: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate both table and bar chart PPT modules.
        
        Args:
            data_file: Path to Excel file containing sequencing data
            output_path: Directory path to save output files
            parameters: Optional parameters for customization
                
        Returns:
            Dictionary with:
                - success: bool
                - table_file: str (path to table PNG)
                - bar_chart_file: str (path to bar chart PNG)
                - error: str (if success is False)
        """
        # Generate table
        table_result = SequencingDepthPPTService.generate_ppt_table(
            data_file, output_path, parameters
        )
        
        if not table_result['success']:
            return table_result
        
        # Generate bar chart
        bar_result = SequencingDepthPPTService.generate_ppt_bar_chart(
            data_file, output_path, parameters
        )
        
        if not bar_result['success']:
            return bar_result
        
        return {
            'success': True,
            'table_file': table_result['output_file'],
            'bar_chart_file': bar_result['output_file'],
            'baseline_sample': table_result['baseline_sample'],
            'sample_count': table_result['sample_count']
        }
