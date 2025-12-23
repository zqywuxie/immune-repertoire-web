"""
Sequencing Reads Analysis Module
Analyzes sequencing reads across different chains (TRA, TRB, TRD, TRG, IGH, IGK, IGL)
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from typing import Dict, Any, List, Tuple
import logging
import io
import base64
from ..base_module import AnalysisModule
from ..registry import register_module

logger = logging.getLogger(__name__)


@register_module
class SequencingReadsModule(AnalysisModule):
    """Sequencing reads analysis module for visualizing read counts by chain"""
    
    def get_name(self) -> str:
        return "sequencing_reads"
    
    def get_description(self) -> str:
        return "Sequencing reads analysis across different chains"
    
    def get_category(self) -> str:
        return "sequencing"
    
    def get_required_columns(self) -> List[str]:
        return ['Sample']
    
    def get_optional_columns(self) -> List[str]:
        return ['TRA', 'TRB', 'TRD', 'TRG', 'IGH', 'IGK', 'IGL']
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze sequencing reads data"""
        try:
            # Validate input data
            if data.empty:
                raise ValueError("Input data is empty")
            
            # Get sample column
            sample_col = 'Sample'
            if sample_col not in data.columns:
                # Find a column that might contain sample names
                sample_col = data.columns[0]
                logger.warning(f"Sample column not found, using first column: {sample_col}")
            
            # Get chain columns
            chain_columns = ['TRA', 'TRB', 'TRD', 'TRG', 'IGH', 'IGK', 'IGL']
            available_chains = [col for col in chain_columns if col in data.columns]
            
            if not available_chains:
                raise ValueError("No chain columns found in data")
            
            # Prepare results
            results = {
                'processed_data': data.to_dict('records'),
                'params': params,
                'summary': {
                    'total_samples': len(data),
                    'available_chains': available_chains,
                    'total_reads': data[available_chains].sum().sum()
                }
            }
            
            # Calculate statistics
            results['statistics'] = self._calculate_statistics(data, sample_col, available_chains)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in analyze: {e}")
            raise
    
    def _calculate_statistics(self, data: pd.DataFrame, sample_col: str, chains: List[str]) -> Dict[str, Any]:
        """Calculate basic statistics for the data"""
        stats = {}
        
        # Total reads per sample
        stats['reads_per_sample'] = data.groupby(sample_col)[chains].sum().to_dict()
        
        # Total reads per chain
        stats['reads_per_chain'] = data[chains].sum().to_dict()
        
        # Average reads per chain
        stats['avg_reads_per_chain'] = data[chains].mean().to_dict()
        
        return stats
    
    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """Generate visualizations"""
        figures = {}
        
        try:
            # Convert data to DataFrame
            data = pd.DataFrame(results["processed_data"])
            
            # Get sample and chain columns
            sample_col = 'Sample'
            chain_columns = ['TRA', 'TRB', 'TRD', 'TRG', 'IGH', 'IGK', 'IGL']
            available_chains = [col for col in chain_columns if col in data.columns]
            
            # Create bar chart
            figures['reads_bar_chart'] = self._create_reads_bar_chart(data, sample_col, available_chains)
            
            # Create percentage chart
            figures['reads_percentage_chart'] = self._create_percentage_chart(data, sample_col, available_chains)
            
            # Create summary table
            figures['summary_table'] = self._create_summary_table(data, sample_col, available_chains)
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
            figures["error"] = f"Visualization error: {str(e)}"
        
        return figures
    
    def _create_reads_bar_chart(self, data: pd.DataFrame, sample_col: str, chains: List[str]) -> str:
        """Create bar chart of reads by chain"""
        plt.figure(figsize=(12, 8))
        
        # Set Chinese font
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False
        
        # Prepare data
        x = np.arange(len(data))
        width = 0.1
        
        # Create bars for each chain
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']
        
        for i, chain in enumerate(chains):
            if chain in data.columns:
                plt.bar(x + i * width, data[chain], width, label=chain, color=colors[i % len(colors)])
        
        # Customize plot
        plt.xlabel('样本', fontsize=12)
        plt.ylabel('Reads数', fontsize=12)
        plt.title('各链Reads分布', fontsize=14, fontweight='bold')
        plt.xticks(x + width * len(chains) / 2, data[sample_col], rotation=45, ha='right')
        plt.legend(title='链类型')
        plt.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        
        # Save to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return image_base64
    
    def _create_percentage_chart(self, data: pd.DataFrame, sample_col: str, chains: List[str]) -> str:
        """Create stacked percentage chart"""
        plt.figure(figsize=(12, 8))
        
        # Set Chinese font
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False
        
        # Calculate percentages
        chain_data = data[chains].values
        totals = chain_data.sum(axis=1, keepdims=True)
        percentages = (chain_data / totals * 100)
        
        # Create stacked bar chart
        bottom = np.zeros(len(data))
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2']
        
        for i, chain in enumerate(chains):
            if chain in data.columns:
                plt.bar(data[sample_col], percentages[:, i], bottom=bottom, 
                       label=chain, color=colors[i % len(colors)])
                bottom += percentages[:, i]
        
        # Customize plot
        plt.xlabel('样本', fontsize=12)
        plt.ylabel('百分比 (%)', fontsize=12)
        plt.title('各链Reads百分比分布', fontsize=14, fontweight='bold')
        plt.xticks(rotation=45, ha='right')
        plt.legend(title='链类型', bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        
        # Save to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return image_base64
    
    def _create_summary_table(self, data: pd.DataFrame, sample_col: str, chains: List[str]) -> str:
        """Create summary table visualization"""
        plt.figure(figsize=(10, 6))
        
        # Set Chinese font
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False
        
        # Prepare table data
        table_data = []
        headers = ['样本'] + chains + ['总计']
        
        for _, row in data.iterrows():
            row_data = [row[sample_col]]
            total = 0
            for chain in chains:
                if chain in data.columns:
                    value = row[chain]
                    row_data.append(f"{int(value):,}" if pd.notna(value) else "0")
                    total += value if pd.notna(value) else 0
            row_data.append(f"{int(total):,}")
            table_data.append(row_data)
        
        # Create table
        table = plt.table(cellText=table_data, colLabels=headers,
                        cellLoc='center', loc='center',
                        colColours=['#f3f3f3'] * len(headers))
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5)
        
        # Style the table
        for i in range(len(headers)):
            table[(0, i)].set_facecolor('#4CAF50')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        # Remove axes
        plt.axis('off')
        plt.title('Reads统计汇总表', fontsize=14, fontweight='bold', pad=20)
        
        # Save to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return image_base64
