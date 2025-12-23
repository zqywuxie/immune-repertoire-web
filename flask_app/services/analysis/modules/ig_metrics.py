"""
IG Metrics Analysis Module
免疫球蛋白指标分析模块 - 计算和可视化多样性指标
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
class IGMetricsModule(AnalysisModule):
    """免疫球蛋白指标分析模块"""
    
    def get_name(self) -> str:
        return "ig_metrics"
    
    def get_description(self) -> str:
        return "免疫球蛋白多样性指标分析（D50、Gini指数、Shannon指数等）"
    
    def get_category(self) -> str:
        return "diversity_analysis"
    
    def get_required_columns(self) -> List[str]:
        return ["Sample", "Chain", "Reads", "UCDR3", "D50", "Gini_index", "Shannon"]
    
    def get_optional_columns(self) -> List[str]:
        return ["Group", "Timepoint", "Condition"]
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "chains": ["IGH", "IGK", "IGL"],
            "metrics": ["D50", "Gini_index", "Shannon"],
            "plot_type": "comparison",  # comparison, distribution, correlation
            "sort_samples": True,
            "show_values": True
        }
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行IG指标分析"""
        try:
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            # 数据预处理
            processed_data = self._preprocess_data(data, analysis_params)
            
            # 计算统计信息
            statistics = self._calculate_statistics(processed_data, analysis_params)
            
            # 执行相关性分析
            correlations = self._calculate_correlations(processed_data, analysis_params)
            
            # 生成分析摘要
            summary = self._generate_summary(processed_data, statistics, analysis_params)
            
            return {
                "processed_data": processed_data.to_dict('records'),
                "statistics": statistics,
                "correlations": correlations,
                "summary": summary,
                "params": analysis_params
            }
            
        except Exception as e:
            logger.error(f"Error in IG metrics analysis: {e}")
            raise
    
    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        figures = {}
        
        try:
            # 转换数据
            data = pd.DataFrame(results["processed_data"])
            analysis_params = results["params"]
            
            # 根据plot_type生成不同的图表
            if analysis_params["plot_type"] == "comparison":
                figures.update(self._create_comparison_plots(data, analysis_params))
            elif analysis_params["plot_type"] == "distribution":
                figures.update(self._create_distribution_plots(data, analysis_params))
            elif analysis_params["plot_type"] == "correlation":
                figures.update(self._create_correlation_plots(data, results["correlations"], analysis_params))
            
            # 总是创建概览图
            figures.update(self._create_overview_plot(data, analysis_params))
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
            figures["error"] = f"Visualization error: {str(e)}"
        
        return figures
    
    def _preprocess_data(self, data: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """数据预处理"""
        # 筛选指定的链
        filtered_data = data[data["Chain"].isin(params["chains"])].copy()
        
        # 确保数值列是正确的类型
        numeric_cols = ["Reads", "UCDR3", "D50", "Gini_index", "Shannon"]
        for col in numeric_cols:
            if col in filtered_data.columns:
                filtered_data[col] = pd.to_numeric(filtered_data[col], errors='coerce')
        
        # 排序样本
        if params.get("sort_samples", True):
            filtered_data = filtered_data.sort_values(["Sample", "Chain"])
        
        return filtered_data
    
    def _calculate_statistics(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算统计信息"""
        stats = {}
        
        for chain in params["chains"]:
            chain_data = data[data["Chain"] == chain]
            if not chain_data.empty:
                chain_stats = {}
                for metric in params["metrics"]:
                    if metric in chain_data.columns:
                        metric_data = chain_data[metric].dropna()
                        if not metric_data.empty:
                            chain_stats[metric] = {
                                "mean": float(metric_data.mean()),
                                "std": float(metric_data.std()),
                                "min": float(metric_data.min()),
                                "max": float(metric_data.max()),
                                "median": float(metric_data.median()),
                                "count": int(metric_data.count())
                            }
                stats[chain] = chain_stats
        
        return stats
    
    def _calculate_correlations(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算指标间的相关性"""
        correlations = {}
        
        # 准备数据透视表
        pivot_data = data.pivot(index="Sample", columns="Chain", values=params["metrics"])
        
        # 计算每个指标的相关性矩阵
        for metric in params["metrics"]:
            if metric in pivot_data.columns.get_level_values(0):
                metric_data = pivot_data[metric]
                # 只保留有数据的列
                metric_data = metric_data.dropna(axis=1, how='all')
                if not metric_data.empty:
                    corr_matrix = metric_data.corr()
                    correlations[metric] = corr_matrix.fillna(0).to_dict()
        
        return correlations
    
    def _generate_summary(self, data: pd.DataFrame, statistics: Dict[str, Any], params: Dict[str, Any]) -> str:
        """生成分析摘要"""
        n_samples = data["Sample"].nunique()
        n_chains = len(params["chains"])
        
        summary = f"分析了 {n_samples} 个样本的 {n_chains} 条免疫链（{', '.join(params['chains'])}）。\n\n"
        
        for chain in params["chains"]:
            if chain in statistics:
                chain_stats = statistics[chain]
                summary += f"{chain}链统计信息：\n"
                for metric, stats in chain_stats.items():
                    summary += f"  - {metric}: 平均值={stats['mean']:.3f}±{stats['std']:.3f}\n"
                summary += "\n"
        
        return summary
    
    def _create_comparison_plots(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """创建对比图"""
        figures = {}
        
        # 多指标对比图
        fig, axes = plt.subplots(len(params["metrics"]), 1, figsize=(12, 5*len(params["metrics"])))
        if len(params["metrics"]) == 1:
            axes = [axes]
        
        for i, metric in enumerate(params["metrics"]):
            ax = axes[i]
            
            # 为每个链创建数据
            for chain in params["chains"]:
                chain_data = data[data["Chain"] == chain]
                if not chain_data.empty:
                    x_pos = np.arange(len(chain_data))
                    ax.bar(x_pos, chain_data[metric], width=0.8/len(params["chains"]), 
                          label=f"{chain}", alpha=0.8)
            
            ax.set_title(f"{metric} 指标对比", fontsize=14, fontweight='bold')
            ax.set_xlabel("样本")
            ax.set_ylabel(metric)
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # 设置x轴标签
            samples = data["Sample"].unique()
            ax.set_xticks(np.arange(len(samples)))
            ax.set_xticklabels(samples, rotation=45, ha='right')
        
        plt.tight_layout()
        figures["comparison"] = self._figure_to_base64(fig)
        
        return figures
    
    def _create_distribution_plots(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """创建分布图"""
        figures = {}
        
        # 箱线图
        fig, axes = plt.subplots(1, len(params["metrics"]), figsize=(5*len(params["metrics"]), 6))
        if len(params["metrics"]) == 1:
            axes = [axes]
        
        for i, metric in enumerate(params["metrics"]):
            ax = axes[i]
            
            # 准备数据
            plot_data = []
            labels = []
            for chain in params["chains"]:
                chain_data = data[data["Chain"] == chain][metric].dropna()
                if not chain_data.empty:
                    plot_data.append(chain_data.values)
                    labels.append(chain)
            
            if plot_data:
                bp = ax.boxplot(plot_data, labels=labels, patch_artist=True)
                for patch in bp['boxes']:
                    patch.set_facecolor('lightblue')
                    patch.set_alpha(0.7)
            
            ax.set_title(f"{metric} 分布", fontsize=14, fontweight='bold')
            ax.set_ylabel(metric)
            ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        figures["distribution"] = self._figure_to_base64(fig)
        
        return figures
    
    def _create_correlation_plots(self, data: pd.DataFrame, correlations: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """创建相关性图"""
        figures = {}
        
        # 相关性热图
        for metric, corr_matrix in correlations.items():
            fig, ax = plt.subplots(figsize=(8, 6))
            
            # 转换为DataFrame
            corr_df = pd.DataFrame(corr_matrix)
            
            # 创建热图
            sns.heatmap(corr_df, annot=True, cmap='coolwarm', center=0, 
                       square=True, ax=ax, fmt='.2f')
            
            ax.set_title(f"{metric} 相关性热图", fontsize=14, fontweight='bold')
            
            plt.tight_layout()
            figures[f"correlation_{metric}"] = self._figure_to_base64(fig)
        
        return figures
    
    def _create_overview_plot(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """创建概览图"""
        figures = {}
        
        # 创建多子图概览
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        axes = axes.flatten()
        
        # 1. Reads分布
        ax = axes[0]
        for chain in params["chains"]:
            chain_data = data[data["Chain"] == chain]
            if not chain_data.empty:
                ax.plot(chain_data["Sample"], chain_data["Reads"], marker='o', label=chain)
        ax.set_title("Reads计数", fontweight='bold')
        ax.set_ylabel("Reads")
        ax.legend()
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3)
        
        # 2. UCDR3分布
        ax = axes[1]
        for chain in params["chains"]:
            chain_data = data[data["Chain"] == chain]
            if not chain_data.empty:
                ax.plot(chain_data["Sample"], chain_data["UCDR3"], marker='s', label=chain)
        ax.set_title("Unique CDR3计数", fontweight='bold')
        ax.set_ylabel("UCDR3")
        ax.legend()
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3)
        
        # 3. D50指数
        ax = axes[2]
        for chain in params["chains"]:
            chain_data = data[data["Chain"] == chain]
            if not chain_data.empty:
                ax.plot(chain_data["Sample"], chain_data["D50"], marker='^', label=chain)
        ax.set_title("D50指数", fontweight='bold')
        ax.set_ylabel("D50")
        ax.legend()
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3)
        
        # 4. Gini指数
        ax = axes[3]
        for chain in params["chains"]:
            chain_data = data[data["Chain"] == chain]
            if not chain_data.empty:
                ax.plot(chain_data["Sample"], chain_data["Gini_index"], marker='d', label=chain)
        ax.set_title("Gini指数", fontweight='bold')
        ax.set_ylabel("Gini Index")
        ax.legend()
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3)
        
        plt.suptitle("免疫球蛋白指标概览", fontsize=16, fontweight='bold')
        plt.tight_layout()
        
        figures["overview"] = self._figure_to_base64(fig)
        
        return figures
