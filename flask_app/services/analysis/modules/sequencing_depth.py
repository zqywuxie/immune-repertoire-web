"""
Sequencing Depth Analysis Module
测序深度分析模块 - 评估测序质量和数据利用效率
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, Any, List, Tuple
import logging

from ..base_module import AnalysisModule, AnalysisResult
from ..registry import register_module

logger = logging.getLogger(__name__)


@register_module
class SequencingDepthModule(AnalysisModule):
    """测序深度分析模块"""
    
    def get_name(self) -> str:
        return "sequencing_depth"
    
    def get_description(self) -> str:
        return "测序深度分析（Total RNA、Reads/UMI、QC Rate、Utilization Rate等）"
    
    def get_category(self) -> str:
        return "quality_control"
    
    def get_required_columns(self) -> List[str]:
        return ["Sample", "Total_Receptor_RNA", "Reads_per_UMI", "MigsGood_Total", "ReadsGood_Total"]
    
    def get_optional_columns(self) -> List[str]:
        return ["Group", "Timepoint", "Condition"]
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "plot_type": "overview",  # overview, quality, utilization
            "show_trends": True,
            "quality_threshold": 80,
            "utilization_threshold": 50
        }
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行测序深度分析"""
        try:
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            # 数据预处理
            processed_data = self._preprocess_data(data, analysis_params)
            
            # 计算质量指标
            quality_metrics = self._calculate_quality_metrics(processed_data, analysis_params)
            
            # 生成质量报告
            quality_report = self._generate_quality_report(processed_data, quality_metrics, analysis_params)
            
            return {
                "processed_data": processed_data.to_dict('records'),
                "quality_metrics": quality_metrics,
                "quality_report": quality_report,
                "params": analysis_params
            }
            
        except Exception as e:
            logger.error(f"Error in sequencing depth analysis: {e}")
            raise
    
    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        figures = {}
        
        try:
            # 转换数据
            data = pd.DataFrame(results["processed_data"])
            analysis_params = results["params"]
            
            # 创建测序深度柱状图
            figures.update(self._create_depth_overview(data, analysis_params))
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
            figures["error"] = f"Visualization error: {str(e)}"
        
        return figures
    
    def _preprocess_data(self, data: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """数据预处理"""
        processed_data = data.copy()
        
        # 确保数值列是正确的类型
        numeric_cols = ["Total_Receptor_RNA", "Reads_per_UMI", "MigsGood_Total", "ReadsGood_Total"]
        for col in numeric_cols:
            if col in processed_data.columns:
                processed_data[col] = pd.to_numeric(processed_data[col], errors='coerce')
        
        # 计算质量指标
        processed_data["QC_Rate"] = (processed_data["MigsGood_Total"] / processed_data["Total_Receptor_RNA"] * 100).round(2)
        processed_data["Utilization_Rate"] = (processed_data["ReadsGood_Total"] / processed_data["Total_Receptor_RNA"] * 100).round(2)
        
        return processed_data
    
    def _calculate_quality_metrics(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算质量指标"""
        metrics = {}
        
        # 基本统计
        metrics["total_samples"] = len(data)
        metrics["mean_total_rna"] = float(data["Total_Receptor_RNA"].mean())
        metrics["mean_reads_per_umi"] = float(data["Reads_per_UMI"].mean())
        metrics["mean_qc_rate"] = float(data["QC_Rate"].mean())
        metrics["mean_utilization_rate"] = float(data["Utilization_Rate"].mean())
        
        # 质量分级
        q_threshold = params.get("quality_threshold", 80)
        u_threshold = params.get("utilization_threshold", 50)
        
        metrics["high_quality_samples"] = int((data["QC_Rate"] >= q_threshold).sum())
        metrics["high_utilization_samples"] = int((data["Utilization_Rate"] >= u_threshold).sum())
        metrics["quality_pass_rate"] = float(metrics["high_quality_samples"] / len(data) * 100)
        metrics["utilization_pass_rate"] = float(metrics["high_utilization_samples"] / len(data) * 100)
        
        return metrics
    
    def _generate_quality_report(self, data: pd.DataFrame, metrics: Dict[str, Any], params: Dict[str, Any]) -> str:
        """生成质量报告"""
        report = f"测序质量分析报告\n"
        report += f"================\n\n"
        report += f"样本总数: {metrics['total_samples']}\n"
        report += f"平均Total RNA: {metrics['mean_total_rna']:,.0f}\n"
        report += f"平均Reads/UMI: {metrics['mean_reads_per_umi']:.2f}\n"
        report += f"平均QC Rate: {metrics['mean_qc_rate']:.2f}%\n"
        report += f"平均Utilization Rate: {metrics['mean_utilization_rate']:.2f}%\n\n"
        
        report += f"质量控制（阈值≥{params.get('quality_threshold', 80)}%）:\n"
        report += f"  - 高质量样本数: {metrics['high_quality_samples']}/{metrics['total_samples']}\n"
        report += f"  - 合格率: {metrics['quality_pass_rate']:.2f}%\n\n"
        
        report += f"数据利用（阈值≥{params.get('utilization_threshold', 50)}%）:\n"
        report += f"  - 高利用率样本数: {metrics['high_utilization_samples']}/{metrics['total_samples']}\n"
        report += f"  - 利用率: {metrics['utilization_pass_rate']:.2f}%\n"
        
        return report
    
    def _create_depth_overview(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """创建测序深度概览图"""
        figures = {}
        
        # Set Chinese font
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False
        
        # Create individual bar charts for each metric
        metrics = [
            ("Total_Receptor_RNA", "Total Receptor RNA", "Reads", "skyblue"),
            ("Reads_per_UMI", "Reads per UMI", "Reads/UMI", "lightgreen"),
            ("QC_Rate", "QC Rate (%)", "QC Rate (%)", "green"),
            ("Utilization_Rate", "Utilization Rate (%)", "Utilization Rate (%)", "blue")
        ]
        
        for i, (col, title, ylabel, color) in enumerate(metrics):
            fig, ax = plt.subplots(figsize=(12, 6))
            
            # Create bar chart
            bars = ax.bar(range(len(data)), data[col], color=color, alpha=0.7)
            
            # Add threshold lines for QC and Utilization rates
            if col == "QC_Rate":
                threshold = params.get("quality_threshold", 80)
                ax.axhline(y=threshold, color='red', linestyle='--', linewidth=2, label=f'Quality Threshold ({threshold}%)')
                # Color bars based on threshold
                for j, bar in enumerate(bars):
                    if data[col].iloc[j] < threshold:
                        bar.set_color('red')
                ax.legend()
            elif col == "Utilization_Rate":
                threshold = params.get("utilization_threshold", 50)
                ax.axhline(y=threshold, color='orange', linestyle='--', linewidth=2, label=f'Utilization Threshold ({threshold}%)')
                # Color bars based on threshold
                for j, bar in enumerate(bars):
                    if data[col].iloc[j] < threshold:
                        bar.set_color('orange')
                ax.legend()
            
            # Customize plot
            ax.set_title(title, fontweight='bold', fontsize=14)
            ax.set_ylabel(ylabel, fontsize=12)
            ax.set_xlabel("Sample", fontsize=12)
            ax.set_xticks(range(len(data)))
            ax.set_xticklabels(data["Sample"], rotation=45, ha='right')
            ax.grid(True, alpha=0.3, axis='y')
            
            # Add value labels on bars
            for j, bar in enumerate(bars):
                height = bar.get_height()
                if col in ["QC_Rate", "Utilization_Rate"]:
                    label = f'{height:.1f}%'
                else:
                    label = f'{height:,.0f}'
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       label, ha='center', va='bottom', fontsize=9)
            
            plt.tight_layout()
            figures[col] = self._figure_to_base64(fig)
            plt.close(fig)
        
        # Create summary table
        fig, ax = plt.subplots(figsize=(14, 8))
        ax.axis('tight')
        ax.axis('off')
        
        # Prepare table data
        table_data = []
        headers = ["Sample", "Total RNA", "Reads/UMI", "MigsGood", "ReadsGood", "QC Rate", "Util Rate"]
        
        for _, row in data.iterrows():
            table_data.append([
                row["Sample"],
                f"{row['Total_Receptor_RNA']:,.0f}",
                f"{row['Reads_per_UMI']:.2f}",
                f"{row['MigsGood_Total']:,.0f}",
                f"{row['ReadsGood_Total']:,.0f}",
                f"{row['QC_Rate']:.1f}%",
                f"{row['Utilization_Rate']:.1f}%"
            ])
        
        # Create table
        table = ax.table(cellText=table_data, colLabels=headers,
                        cellLoc='center', loc='center',
                        colColours=['#f0f0f0']*len(headers))
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5)
        
        # Style the table
        for i in range(len(headers)):
            table[(0, i)].set_facecolor('#e0e0e0')
            table[(0, i)].set_text_props(weight='bold')
        
        plt.title("测序深度数据汇总", fontsize=16, fontweight='bold', pad=20)
        figures["summary_table"] = self._figure_to_base64(fig)
        plt.close(fig)
        
        return figures
    
    def _create_quality_plots(self, data: pd.DataFrame, metrics: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """创建质量指标图"""
        figures = {}
        
        # 质量指标散点图
        fig, ax = plt.subplots(figsize=(10, 8))
        
        scatter = ax.scatter(data["QC_Rate"], data["Utilization_Rate"], 
                           c=data["Total_Receptor_RNA"], cmap='viridis', 
                           s=100, alpha=0.7)
        
        # 添加阈值线
        ax.axvline(x=params.get("quality_threshold", 80), color='red', linestyle='--', alpha=0.5)
        ax.axhline(y=params.get("utilization_threshold", 50), color='orange', linestyle='--', alpha=0.5)
        
        # 添加样本标签
        for i, sample in enumerate(data["Sample"]):
            ax.annotate(sample, (data["QC_Rate"].iloc[i], data["Utilization_Rate"].iloc[i]), 
                       xytext=(5, 5), textcoords='offset points', fontsize=8)
        
        ax.set_xlabel("QC Rate (%)")
        ax.set_ylabel("Utilization Rate (%)")
        ax.set_title("样本质量分布", fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        # 添加颜色条
        cbar = plt.colorbar(scatter)
        cbar.set_label("Total RNA")
        
        plt.tight_layout()
        
        figures["quality_scatter"] = self._figure_to_base64(fig)
        
        return figures
