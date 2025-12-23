"""
Chain Analysis Module
链特异性分析模块 - 分析不同免疫链的表达和特征
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
class ChainAnalysisModule(AnalysisModule):
    """链特异性分析模块"""
    
    def get_name(self) -> str:
        return "chain_analysis"
    
    def get_description(self) -> str:
        return "链特异性分析（BCR链：IGH、IGK、IGL；TCR链：TRA、TRB、TRG、TRD）"
    
    def get_category(self) -> str:
        return "chain_specificity"
    
    def get_required_columns(self) -> List[str]:
        return ["Sample", "Chain_Type", "Expression"]
    
    def get_optional_columns(self) -> List[str]:
        return ["Reads", "UCDR3", "D50", "Gini_index", "Shannon", "Group", "Timepoint"]
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "plot_type": "overview",  # overview, radar, correlation
            "chains": ["IGH", "IGK", "IGL", "TRA", "TRB", "TRG", "TRD"],
            "chain_categories": {
                "BCR": ["IGH", "IGK", "IGL"],
                "TCR": ["TRA", "TRB", "TRG", "TRD"]
            },
            "normalize": True
        }
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行链特异性分析"""
        try:
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            # 数据预处理
            processed_data = self._preprocess_data(data, analysis_params)
            
            # 计算链分布统计
            chain_stats = self._calculate_chain_stats(processed_data, analysis_params)
            
            # 计算链间相关性
            correlations = self._calculate_chain_correlations(processed_data, analysis_params)
            
            # 生成分析摘要
            summary = self._generate_summary(processed_data, chain_stats, analysis_params)
            
            return {
                "processed_data": processed_data.to_dict('records'),
                "chain_stats": chain_stats,
                "correlations": correlations,
                "summary": summary,
                "params": analysis_params
            }
            
        except Exception as e:
            logger.error(f"Error in chain analysis: {e}")
            raise
    
    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        figures = {}
        
        try:
            # 转换数据
            data = pd.DataFrame(results["processed_data"])
            analysis_params = results["params"]
            
            # 根据plot_type生成不同的图表
            if analysis_params["plot_type"] == "overview":
                figures.update(self._create_overview_plots(data, results["chain_stats"], analysis_params))
            elif analysis_params["plot_type"] == "radar":
                figures.update(self._create_radar_plots(data, analysis_params))
            elif analysis_params["plot_type"] == "correlation":
                figures.update(self._create_correlation_plots(data, results["correlations"], analysis_params))
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
            figures["error"] = f"Visualization error: {str(e)}"
        
        return figures
    
    def _preprocess_data(self, data: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """数据预处理"""
        processed_data = data.copy()
        
        # 确保数值列是正确的类型
        numeric_cols = ["Expression", "Reads", "UCDR3", "D50", "Gini_index", "Shannon"]
        for col in numeric_cols:
            if col in processed_data.columns:
                processed_data[col] = pd.to_numeric(processed_data[col], errors='coerce')
        
        # 筛选指定的链
        processed_data = processed_data[processed_data["Chain_Type"].isin(params["chains"])]
        
        return processed_data
    
    def _calculate_chain_stats(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算链统计"""
        stats = {}
        
        for chain in params["chains"]:
            chain_data = data[data["Chain_Type"] == chain]
            if not chain_data.empty:
                expression_data = chain_data["Expression"].dropna()
                if not expression_data.empty:
                    stats[chain] = {
                        "mean_expression": float(expression_data.mean()),
                        "std_expression": float(expression_data.std()),
                        "median_expression": float(expression_data.median()),
                        "sample_count": int(len(chain_data))
                    }
                    
                    # 如果有其他指标，也计算统计
                    for metric in ["Reads", "UCDR3", "D50", "Gini_index", "Shannon"]:
                        if metric in chain_data.columns:
                            metric_data = chain_data[metric].dropna()
                            if not metric_data.empty:
                                stats[chain][f"mean_{metric.lower()}"] = float(metric_data.mean())
                                stats[chain][f"std_{metric.lower()}"] = float(metric_data.std())
        
        return stats
    
    def _calculate_chain_correlations(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算链间相关性"""
        # 创建透视表
        pivot_data = data.pivot_table(values="Expression", index="Sample", columns="Chain_Type", aggfunc="mean")
        
        # 只保留有数据的链
        available_chains = [chain for chain in params["chains"] if chain in pivot_data.columns]
        pivot_data = pivot_data[available_chains]
        
        # 计算相关性矩阵
        correlation_matrix = pivot_data.corr()
        
        return correlation_matrix.fillna(0).to_dict()
    
    def _generate_summary(self, data: pd.DataFrame, stats: Dict[str, Any], params: Dict[str, Any]) -> str:
        """生成分析摘要"""
        n_samples = data["Sample"].nunique()
        
        summary = f"链特异性分析报告\n"
        summary += f"================\n\n"
        summary += f"分析样本数: {n_samples}\n"
        summary += f"分析链数: {len([c for c in params['chains'] if c in stats])}\n\n"
        
        # BCR链统计
        summary += "BCR链统计：\n"
        for chain in params["chain_categories"]["BCR"]:
            if chain in stats:
                s = stats[chain]
                summary += f"  - {chain}: 平均表达量={s['mean_expression']:.2f}±{s['std_expression']:.2f}\n"
        
        # TCR链统计
        summary += "\nTCR链统计：\n"
        for chain in params["chain_categories"]["TCR"]:
            if chain in stats:
                s = stats[chain]
                summary += f"  - {chain}: 平均表达量={s['mean_expression']:.2f}±{s['std_expression']:.2f}\n"
        
        return summary
    
    def _create_overview_plots(self, data: pd.DataFrame, stats: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """创建概览图"""
        figures = {}
        
        # 链分布柱状图
        fig, ax = plt.subplots(figsize=(12, 8))
        
        chains = []
        mean_expressions = []
        std_expressions = []
        
        for chain in params["chains"]:
            if chain in stats:
                chains.append(chain)
                mean_expressions.append(stats[chain]["mean_expression"])
                std_expressions.append(stats[chain]["std_expression"])
        
        x_pos = np.arange(len(chains))
        colors = ['skyblue' if chain in params["chain_categories"]["BCR"] else 'lightcoral' 
                 for chain in chains]
        
        bars = ax.bar(x_pos, mean_expressions, yerr=std_expressions, capsize=5, 
                     color=colors, alpha=0.7)
        
        ax.set_xlabel("链类型")
        ax.set_ylabel("平均表达量")
        ax.set_title("各链表达量分布", fontsize=14, fontweight='bold')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(chains)
        ax.grid(True, alpha=0.3)
        
        # 添加图例
        from matplotlib.patches import Patch
        legend_elements = [Patch(facecolor='skyblue', alpha=0.7, label='BCR'),
                          Patch(facecolor='lightcoral', alpha=0.7, label='TCR')]
        ax.legend(handles=legend_elements)
        
        plt.tight_layout()
        figures["chain_distribution"] = self._figure_to_base64(fig)
        
        return figures
    
    def _create_radar_plots(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """创建雷达图"""
        figures = {}
        
        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))
        
        # 准备数据
        available_chains = [c for c in params["chains"] if c in data["Chain_Type"].values]
        angles = np.linspace(0, 2 * np.pi, len(available_chains), endpoint=False).tolist()
        angles += angles[:1]  # 闭合图形
        
        # 为每个样本绘制雷达图
        for idx, (sample, group) in enumerate(data.groupby("Sample")):
            if idx >= 10:  # 最多显示10个样本
                break
            
            values = []
            for chain in available_chains:
                chain_data = group[group["Chain_Type"] == chain]
                if not chain_data.empty:
                    values.append(chain_data["Expression"].mean())
                else:
                    values.append(0)
            
            values += values[:1]  # 闭合图形
            
            ax.plot(angles, values, 'o-', linewidth=2, label=sample)
            ax.fill(angles, values, alpha=0.25)
        
        # 设置标签
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(available_chains)
        ax.set_title("链表达量雷达图", fontsize=14, fontweight='bold', pad=20)
        ax.legend(bbox_to_anchor=(1.2, 1.0))
        ax.grid(True)
        
        plt.tight_layout()
        figures["radar"] = self._figure_to_base64(fig)
        
        return figures
    
    def _create_correlation_plots(self, data: pd.DataFrame, correlations: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """创建相关性图"""
        figures = {}
        
        if correlations:
            fig, ax = plt.subplots(figsize=(10, 8))
            
            corr_df = pd.DataFrame(correlations)
            
            # 创建热图
            sns.heatmap(corr_df, annot=True, fmt=".2f", cmap='coolwarm', 
                       center=0, square=True, ax=ax)
            
            ax.set_title("链间相关性热图", fontsize=14, fontweight='bold')
            
            plt.tight_layout()
            figures["correlation_heatmap"] = self._figure_to_base64(fig)
        
        return figures
