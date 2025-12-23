"""
B Cell Isotype Analysis Module
B细胞同种型分析模块 - 分析B细胞同种型分布
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
class BCellIsotypeModule(AnalysisModule):
    """B细胞同种型分析模块"""
    
    def get_name(self) -> str:
        return "bcell_isotype"
    
    def get_description(self) -> str:
        return "B细胞同种型分布分析（IgM、IgD、IgA、IgG、IgE）"
    
    def get_category(self) -> str:
        return "bcell_analysis"
    
    def get_required_columns(self) -> List[str]:
        return ["Sample", "IgM_Expression", "IgD_Expression", "IgA_Expression", "IgG_Expression", "IgE_Expression"]
    
    def get_optional_columns(self) -> List[str]:
        return ["IgM_UCDR3", "IgD_UCDR3", "IgA_UCDR3", "IgG_UCDR3", "IgE_UCDR3", "Group", "Timepoint"]
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "plot_type": "stacked_bar",  # stacked_bar, heatmap, radar
            "normalize": True,
            "show_values": True,
            "isotypes": ["IgM", "IgD", "IgA", "IgG", "IgE"]
        }
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行B细胞同种型分析"""
        try:
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            # 数据预处理
            processed_data = self._preprocess_data(data, analysis_params)
            
            # 计算同种型分布统计
            distribution_stats = self._calculate_distribution_stats(processed_data, analysis_params)
            
            # 计算同种型相关性
            correlations = self._calculate_isotype_correlations(processed_data, analysis_params)
            
            # 生成分析摘要
            summary = self._generate_summary(processed_data, distribution_stats, analysis_params)
            
            return {
                "processed_data": processed_data.to_dict('records'),
                "distribution_stats": distribution_stats,
                "correlations": correlations,
                "summary": summary,
                "params": analysis_params
            }
            
        except Exception as e:
            logger.error(f"Error in B cell isotype analysis: {e}")
            raise
    
    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        figures = {}
        
        try:
            # 转换数据
            data = pd.DataFrame(results["processed_data"])
            analysis_params = results["params"]
            
            # 根据plot_type生成不同的图表
            if analysis_params["plot_type"] == "stacked_bar":
                figures.update(self._create_stacked_bar_plot(data, analysis_params))
            elif analysis_params["plot_type"] == "heatmap":
                figures.update(self._create_heatmap_plot(data, results["correlations"], analysis_params))
            elif analysis_params["plot_type"] == "radar":
                figures.update(self._create_radar_plot(data, analysis_params))
            
            # 总是创建分布图
            figures.update(self._create_distribution_plot(data, analysis_params))
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
            figures["error"] = f"Visualization error: {str(e)}"
        
        return figures
    
    def _preprocess_data(self, data: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """数据预处理"""
        processed_data = data.copy()
        
        # 确保数值列是正确的类型
        isotype_cols = [f"{iso}_Expression" for iso in params["isotypes"]]
        for col in isotype_cols:
            if col in processed_data.columns:
                processed_data[col] = pd.to_numeric(processed_data[col], errors='coerce')
        
        # 计算总表达量
        processed_data["Total_Expression"] = processed_data[isotype_cols].sum(axis=1)
        
        # 计算百分比
        for iso in params["isotypes"]:
            col = f"{iso}_Expression"
            pct_col = f"{iso}_Percentage"
            processed_data[pct_col] = (processed_data[col] / processed_data["Total_Expression"] * 100).round(2)
        
        return processed_data
    
    def _calculate_distribution_stats(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算分布统计"""
        stats = {}
        
        for iso in params["isotypes"]:
            pct_col = f"{iso}_Percentage"
            if pct_col in data.columns:
                iso_data = data[pct_col].dropna()
                if not iso_data.empty:
                    stats[iso] = {
                        "mean": float(iso_data.mean()),
                        "std": float(iso_data.std()),
                        "min": float(iso_data.min()),
                        "max": float(iso_data.max()),
                        "median": float(iso_data.median())
                    }
        
        return stats
    
    def _calculate_isotype_correlations(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算同种型相关性"""
        pct_cols = [f"{iso}_Percentage" for iso in params["isotypes"]]
        correlation_data = data[pct_cols].corr()
        
        return correlation_data.fillna(0).to_dict()
    
    def _generate_summary(self, data: pd.DataFrame, stats: Dict[str, Any], params: Dict[str, Any]) -> str:
        """生成分析摘要"""
        n_samples = len(data)
        summary = f"分析了 {n_samples} 个样本的B细胞同种型分布。\n\n"
        
        summary += "各同种型平均表达百分比：\n"
        for iso in params["isotypes"]:
            if iso in stats:
                summary += f"  - {iso}: {stats[iso]['mean']:.2f}% ± {stats[iso]['std']:.2f}%\n"
        
        # 找出主要同种型
        dominant_isotypes = []
        for _, row in data.iterrows():
            max_pct = 0
            dominant = None
            for iso in params["isotypes"]:
                pct = row.get(f"{iso}_Percentage", 0)
                if pct > max_pct:
                    max_pct = pct
                    dominant = iso
            if dominant:
                dominant_isotypes.append(dominant)
        
        if dominant_isotypes:
            from collections import Counter
            dominant_count = Counter(dominant_isotypes)
            summary += f"\n主要同种型分布：\n"
            for iso, count in dominant_count.most_common():
                summary += f"  - {iso}: {count} 个样本 ({count/n_samples*100:.1f}%)\n"
        
        return summary
    
    def _create_stacked_bar_plot(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """创建堆叠柱状图"""
        figures = {}
        
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # 准备数据
        pct_cols = [f"{iso}_Percentage" for iso in params["isotypes"]]
        plot_data = data[pct_cols].values
        samples = data["Sample"].values
        
        # 创建堆叠柱状图
        bottom = np.zeros(len(data))
        colors = plt.cm.Set3(np.linspace(0, 1, len(params["isotypes"])))
        
        for i, iso in enumerate(params["isotypes"]):
            values = data[f"{iso}_Percentage"].values
            ax.bar(samples, values, bottom=bottom, label=iso, color=colors[i], alpha=0.8)
            bottom += values
        
        ax.set_title("B细胞同种型分布（堆叠柱状图）", fontsize=14, fontweight='bold')
        ax.set_xlabel("样本")
        ax.set_ylabel("表达百分比 (%)")
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        figures["stacked_bar"] = self._figure_to_base64(fig)
        
        return figures
    
    def _create_heatmap_plot(self, data: pd.DataFrame, correlations: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """创建热图"""
        figures = {}
        
        # 相关性热图
        fig, ax = plt.subplots(figsize=(10, 8))
        
        corr_df = pd.DataFrame(correlations)
        sns.heatmap(corr_df, annot=True, cmap='coolwarm', center=0, 
                   square=True, ax=ax, fmt='.2f')
        
        ax.set_title("同种型相关性热图", fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        figures["correlation_heatmap"] = self._figure_to_base64(fig)
        
        return figures
    
    def _create_radar_plot(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """创建雷达图"""
        figures = {}
        
        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))
        
        # 准备数据
        pct_cols = [f"{iso}_Percentage" for iso in params["isotypes"]]
        angles = np.linspace(0, 2 * np.pi, len(params["isotypes"]), endpoint=False).tolist()
        angles += angles[:1]  # 闭合图形
        
        # 为每个样本绘制雷达图
        for idx, (_, row) in enumerate(data.iterrows()):
            if idx >= 10:  # 最多显示10个样本
                break
            values = [row[f"{iso}_Percentage"] for iso in params["isotypes"]]
            values += values[:1]  # 闭合图形
            
            ax.plot(angles, values, 'o-', linewidth=2, label=row["Sample"])
            ax.fill(angles, values, alpha=0.25)
        
        # 设置标签
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(params["isotypes"])
        ax.set_ylim(0, 100)
        ax.set_title("B细胞同种型分布雷达图", fontsize=14, fontweight='bold', pad=20)
        ax.legend(bbox_to_anchor=(1.2, 1.0))
        ax.grid(True)
        
        plt.tight_layout()
        figures["radar"] = self._figure_to_base64(fig)
        
        return figures
    
    def _create_distribution_plot(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """创建分布图"""
        figures = {}
        
        # 箱线图
        fig, ax = plt.subplots(figsize=(12, 8))
        
        pct_cols = [f"{iso}_Percentage" for iso in params["isotypes"]]
        plot_data = [data[col].dropna().values for col in pct_cols]
        
        bp = ax.boxplot(plot_data, labels=params["isotypes"], patch_artist=True)
        colors = plt.cm.Set3(np.linspace(0, 1, len(params["isotypes"])))
        for patch, color in zip(bp['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        
        ax.set_title("同种型分布箱线图", fontsize=14, fontweight='bold')
        ax.set_ylabel("表达百分比 (%)")
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        figures["distribution"] = self._figure_to_base64(fig)
        
        return figures
