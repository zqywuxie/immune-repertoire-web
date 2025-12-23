"""
Sequencing Reads Bar Chart Service
Generates bar charts for sequencing reads by chain type.
Refactored from sequencing_reads_bar_chart_final.py
Requirements: 14.3, 14.6
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


class SequencingReadsChartService:
    """
    Service for generating sequencing reads bar charts by chain type.
    Creates separate visualizations for TCR and IG chains.
    """
    
    # Chain types
    TCR_CHAINS = ["TRA", "TRB", "TRD", "TRG"]
    IG_CHAINS = ["IGH", "IGK", "IGL"]
    ALL_CHAINS = TCR_CHAINS + IG_CHAINS
    
    # Default colors for chains
    CHAIN_COLORS = {
        "TRA": "#1f77b4",
        "TRB": "#ff7f0e",
        "TRD": "#2ca02c",
        "TRG": "#d62728",
        "IGH": "#9467bd",
        "IGK": "#8c564b",
        "IGL": "#e377c2",
    }
    
    def __init__(self):
        """Initialize the reads chart service."""
        pass
    
    @staticmethod
    def validate_parameters(
        data_file: str,
        output_path: str,
        parameters: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate input parameters for chart generation.
        
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
    def extract_reads_data(
        data_file: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
        """
        Extract sequencing reads data from Excel file.
        
        Args:
            data_file: Path to Excel file
            parameters: Optional parameters including sample_filter and sample_order
            
        Returns:
            Tuple of (reads DataFrame, percentage DataFrame, list of sample names)
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
        
        # Extract reads and percentage data
        data = {}
        percentage_data = {}
        
        for sample in sample_order:
            sample_data = []
            sample_pct_data = []
            sample_row = ct_samples[ct_samples["Sample"] == sample].iloc[0]
            
            for chain in SequencingReadsChartService.ALL_CHAINS:
                reads_col = f"{chain}_reads"
                pct_col = f"{chain}_percent_reads_all"
                
                if reads_col in sample_row and pct_col in sample_row:
                    sample_data.append(int(sample_row[reads_col]))
                    sample_pct_data.append(float(sample_row[pct_col]))
                else:
                    sample_data.append(0)
                    sample_pct_data.append(0.0)
            
            data[sample] = sample_data
            percentage_data[sample] = sample_pct_data
        
        # Create DataFrames
        df_data = pd.DataFrame(data, index=SequencingReadsChartService.ALL_CHAINS)
        df_pct = pd.DataFrame(percentage_data, index=SequencingReadsChartService.ALL_CHAINS)
        
        return df_data, df_pct, sample_order
    
    @staticmethod
    def generate_tcr_chart(
        data_file: str,
        output_path: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate TCR chains bar chart.
        
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
            is_valid, error_msg = SequencingReadsChartService.validate_parameters(
                data_file, output_path, params
            )
            if not is_valid:
                return {'success': False, 'error': error_msg}
            
            # Extract data
            df_data, df_pct, sample_order = SequencingReadsChartService.extract_reads_data(
                data_file, params
            )
            
            if df_data.empty:
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
                f"TCR Sequencing Reads - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
                fontsize=20,
                fontweight="bold",
                y=0.98,
            )
            
            axes = axes.flatten()
            
            x_pos = np.arange(len(sample_order))
            bar_width = 0.6
            
            # Plot each TCR chain
            for idx, (chain, ax) in enumerate(zip(SequencingReadsChartService.TCR_CHAINS, axes)):
                # Get values
                values = df_data.loc[chain].values
                baseline_value = values[baseline_index]
                
                # Calculate percentage changes
                if baseline_value > 0:
                    pct_change = (values - baseline_value) / baseline_value * 100
                else:
                    pct_change = np.zeros_like(values)
                
                # Create bars
                bars = ax.bar(
                    x_pos, pct_change, bar_width,
                    color=SequencingReadsChartService.CHAIN_COLORS[chain],
                    alpha=0.8
                )
                
                # Highlight baseline bar
                bars[baseline_index].set_edgecolor("black")
                bars[baseline_index].set_linewidth(2)
                bars[baseline_index].set_alpha(1.0)
                
                # Add baseline reference line
                ax.axhline(
                    y=0, color="gray", linestyle="-", linewidth=2,
                    alpha=0.8, label="Baseline (0%)"
                )
                
                # Add value labels
                for j, bar in enumerate(bars):
                    height = bar.get_height()
                    if j == baseline_index:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height + max(pct_change) * 0.02 if max(pct_change) > 0 else 1,
                            "Baseline",
                            ha="center", va="bottom",
                            fontsize=9, fontweight="bold", color="red",
                        )
                    elif height > 0:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height + max(pct_change) * 0.02,
                            f"+{height:.1f}%",
                            ha="center", va="bottom",
                            fontsize=8, fontweight="bold",
                        )
                    else:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height - max(pct_change) * 0.02 if max(pct_change) > 0 else -1,
                            f"{height:.1f}%",
                            ha="center", va="top",
                            fontsize=8, fontweight="bold",
                        )
                
                # Customize subplot
                ax.set_xticks(x_pos)
                ax.set_xticklabels(sample_order, rotation=45, ha="right", fontsize=11)
                ax.set_ylabel("Percentage Change from Baseline (%)", fontsize=14, fontweight="bold")
                ax.set_xlabel("Sample", fontsize=14, fontweight="bold")
                ax.set_title(f"{chain} Reads", fontsize=16, fontweight="bold", pad=20)
                ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
                ax.grid(axis="y", alpha=0.3, linestyle="--")
                
                # Set y-axis limits
                ymin = min(pct_change) * 1.1 if min(pct_change) < 0 else -5
                ymax = max(pct_change) * 1.1 if max(pct_change) > 0 else 5
                ax.set_ylim(ymin, ymax)
                
                ax.set_facecolor("#f8f9fa")
            
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            
            # Create output directory
            os.makedirs(output_path, exist_ok=True)
            
            # Save figure
            output_file = os.path.join(output_path, "tcr_reads_percentage_change.png")
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
    def generate_ig_chart(
        data_file: str,
        output_path: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate IG chains bar chart.
        
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
            is_valid, error_msg = SequencingReadsChartService.validate_parameters(
                data_file, output_path, params
            )
            if not is_valid:
                return {'success': False, 'error': error_msg}
            
            # Extract data
            df_data, df_pct, sample_order = SequencingReadsChartService.extract_reads_data(
                data_file, params
            )
            
            if df_data.empty:
                return {'success': False, 'error': '未找到匹配的样本数据'}
            
            # Determine baseline sample
            baseline_sample = params.get('baseline_sample')
            if baseline_sample and baseline_sample in sample_order:
                baseline_index = sample_order.index(baseline_sample)
            else:
                baseline_index = len(sample_order) // 2
                baseline_sample = sample_order[baseline_index]
            
            # Create figure with 1x3 subplots
            fig, axes = plt.subplots(1, 3, figsize=(24, 8))
            fig.suptitle(
                f"IG Sequencing Reads - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
                fontsize=20,
                fontweight="bold",
                y=0.98,
            )
            
            x_pos = np.arange(len(sample_order))
            bar_width = 0.6
            
            # Plot each IG chain
            for idx, (chain, ax) in enumerate(zip(SequencingReadsChartService.IG_CHAINS, axes)):
                # Get values
                values = df_data.loc[chain].values
                baseline_value = values[baseline_index]
                
                # Calculate percentage changes
                if baseline_value > 0:
                    pct_change = (values - baseline_value) / baseline_value * 100
                else:
                    pct_change = np.zeros_like(values)
                
                # Create bars
                bars = ax.bar(
                    x_pos, pct_change, bar_width,
                    color=SequencingReadsChartService.CHAIN_COLORS[chain],
                    alpha=0.8
                )
                
                # Highlight baseline bar
                bars[baseline_index].set_edgecolor("black")
                bars[baseline_index].set_linewidth(2)
                bars[baseline_index].set_alpha(1.0)
                
                # Add baseline reference line
                ax.axhline(
                    y=0, color="gray", linestyle="-", linewidth=2,
                    alpha=0.8, label="Baseline (0%)"
                )
                
                # Add value labels
                for j, bar in enumerate(bars):
                    height = bar.get_height()
                    if j == baseline_index:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height + max(pct_change) * 0.02 if max(pct_change) > 0 else 1,
                            "Baseline",
                            ha="center", va="bottom",
                            fontsize=9, fontweight="bold", color="red",
                        )
                    elif height > 0:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height + max(pct_change) * 0.02,
                            f"+{height:.1f}%",
                            ha="center", va="bottom",
                            fontsize=8, fontweight="bold",
                        )
                    else:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height - max(pct_change) * 0.02 if max(pct_change) > 0 else -1,
                            f"{height:.1f}%",
                            ha="center", va="top",
                            fontsize=8, fontweight="bold",
                        )
                
                # Customize subplot
                ax.set_xticks(x_pos)
                ax.set_xticklabels(sample_order, rotation=45, ha="right", fontsize=11)
                ax.set_ylabel("Percentage Change from Baseline (%)", fontsize=14, fontweight="bold")
                ax.set_xlabel("Sample", fontsize=14, fontweight="bold")
                ax.set_title(f"{chain} Reads", fontsize=16, fontweight="bold", pad=20)
                ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
                ax.grid(axis="y", alpha=0.3, linestyle="--")
                
                # Set y-axis limits
                ymin = min(pct_change) * 1.1 if min(pct_change) < 0 else -5
                ymax = max(pct_change) * 1.1 if max(pct_change) > 0 else 5
                ax.set_ylim(ymin, ymax)
                
                ax.set_facecolor("#f8f9fa")
            
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            
            # Create output directory
            os.makedirs(output_path, exist_ok=True)
            
            # Save figure
            output_file = os.path.join(output_path, "ig_reads_percentage_change.png")
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
    def generate_bar_chart(
        data_file: str,
        output_path: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate both TCR and IG bar charts.
        
        Args:
            data_file: Path to Excel file containing sequencing data
            output_path: Directory path to save output files
            parameters: Optional parameters for customization
                
        Returns:
            Dictionary with:
                - success: bool
                - tcr_file: str (path to TCR chart PNG)
                - ig_file: str (path to IG chart PNG)
                - csv_file: str (path to extracted CSV data)
                - error: str (if success is False)
        """
        try:
            # Extract and save data to CSV
            params = parameters or {}
            df_data, df_pct, sample_order = SequencingReadsChartService.extract_reads_data(
                data_file, params
            )
            
            # Create output directory
            os.makedirs(output_path, exist_ok=True)
            
            # Save CSV with reads and percentages combined
            csv_file = os.path.join(output_path, "sequencing_reads_data.csv")
            combined_data = []
            for sample in sample_order:
                row = {"Sample": sample}
                for chain in SequencingReadsChartService.ALL_CHAINS:
                    reads = df_data.loc[chain, sample]
                    pct = df_pct.loc[chain, sample]
                    row[chain] = f"{reads} ({pct:.2f}%)"
                combined_data.append(row)
            
            combined_df = pd.DataFrame(combined_data)
            combined_df.to_csv(csv_file, index=False)
            
            # Generate TCR chart
            tcr_result = SequencingReadsChartService.generate_tcr_chart(
                data_file, output_path, params
            )
            
            if not tcr_result['success']:
                return tcr_result
            
            # Generate IG chart
            ig_result = SequencingReadsChartService.generate_ig_chart(
                data_file, output_path, params
            )
            
            if not ig_result['success']:
                return ig_result
            
            return {
                'success': True,
                'tcr_file': tcr_result['output_file'],
                'ig_file': ig_result['output_file'],
                'csv_file': csv_file,
                'baseline_sample': tcr_result['baseline_sample'],
                'sample_count': tcr_result['sample_count']
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
