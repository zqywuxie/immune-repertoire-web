"""
SHM Analysis Module
体细胞超突变分析模块
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
class SHMAnalysisModule(AnalysisModule):
    """体细胞超突变分析模块"""
    
    def get_name(self) -> str:
        return "shm_analysis"
    
    def get_description(self) -> str:
        return "体细胞超突变分析（FR和CDR区域突变分布、突变频谱）"
    
    def get_category(self) -> str:
        return "mutation_analysis"
    
    def get_required_columns(self) -> List[str]:
        return ["Sample", "Region", "SHM_Rate", "Mutation_Count"]
    
    def get_optional_columns(self) -> List[str]:
        return ["Chain", "Gene", "Position", "Mutation_Type", "Group", "Timepoint"]
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "plot_type": "distribution",  # distribution, spectrum, heatmap
            "regions": ["FR1", "CDR1", "FR2", "CDR2", "FR3", "CDR3"],
            "mutation_types": ["A>G", "A>C", "A>T", "G>A", "G>C", "G>T"],
            "normalize": True
        }
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行SHM分析"""
        try:
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            # 数据预处理
            processed_data = self._preprocess_data(data, analysis_params)
            
            # 计算区域统计
            region_stats = self._calculate_region_stats(processed_data, analysis_params)
            
            # 计算突变频谱
            mutation_spectrum = self._calculate_mutation_spectrum(processed_data, analysis_params)
            
            # 生成分析摘要
            summary = self._generate_summary(processed_data, region_stats, analysis_params)
            
            return {
                "processed_data": processed_data.to_dict('records'),
                "region_stats": region_stats,
                "mutation_spectrum": mutation_spectrum,
                "summary": summary,
                "params": analysis_params
            }
            
        except Exception as e:
            logger.error(f"Error in SHM analysis: {e}")
            raise
    
    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        figures = {}
        
        try:
            # 转换数据
            data = pd.DataFrame(results["processed_data"])
            analysis_params = results["params"]
            
            # 根据plot_type生成不同的图表
            if analysis_params["plot_type"] == "distribution":
                figures.update(self._create_distribution_plots(data, results["region_stats"], analysis_params))
            elif analysis_params["plot_type"] == "spectrum":
                figures.update(self._create_spectrum_plots(data, results["mutation_spectrum"], analysis_params))
            elif analysis_params["plot_type"] == "heatmap":
                figures.update(self._create_heatmap_plots(data, analysis_params))
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
            figures["error"] = f"Visualization error: {str(e)}"
        
        return figures
    
    def _preprocess_data(self, data: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """数据预处理"""
        processed_data = data.copy()
        
        # 确保数值列是正确的类型
        numeric_cols = ["SHM_Rate", "Mutation_Count"]
        for col in numeric_cols:
            if col in processed_data.columns:
                processed_data[col] = pd.to_numeric(processed_data[col], errors='coerce')
        
        return processed_data
    
    def _calculate_region_stats(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算区域统计"""
        stats = {}
        
        for region in params["regions"]:
            region_data = data[data["Region"] == region]
            if not region_data.empty:
                shm_rates = region_data["SHM_Rate"].dropna()
                if not shm_rates.empty:
                    stats[region] = {
                        "mean_shm_rate": float(shm_rates.mean()),
                        "std_shm_rate": float(shm_rates.std()),
                        "median_shm_rate": float(shm_rates.median()),
                        "total_mutations": int(region_data["Mutation_Count"].sum()),
                        "sample_count": int(len(region_data))
                    }
        
        return stats
    
    def _calculate_mutation_spectrum(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """计算突变频谱"""
        spectrum = {}
        
        if "Mutation_Type" in data.columns:
            mutation_counts = data["Mutation_Type"].value_counts()
            total_mutations = mutation_counts.sum()
            
            for mut_type in params["mutation_types"]:
                count = mutation_counts.get(mut_type, 0)
                spectrum[mut_type] = {
                    "count": int(count),
                    "percentage": float(count / total_mutations * 100) if total_mutations > 0 else 0
                }
        
        return spectrum
    
    def _generate_summary(self, data: pd.DataFrame, stats: Dict[str, Any], params: Dict[str, Any]) -> str:
        """生成分析摘要"""
        n_samples = data["Sample"].nunique()
        total_mutations = data["Mutation_Count"].sum()
        
        summary = f"体细胞超突变分析报告\n"
        summary += f"==================\n\n"
        summary += f"分析样本数: {n_samples}\n"
        summary += f"总突变数: {total_mutations:,}\n\n"
        
        summary += "各区域SHM率统计：\n"
        for region in params["regions"]:
            if region in stats:
                s = stats[region]
                summary += f"  - {region}: {s['mean_shm_rate']:.3f}% ± {s['std_shm_rate']:.3f}%\n"
        
        return summary
    
    def _create_distribution_plots(self, data: pd.DataFrame, stats: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """创建分布图"""
        figures = {}
        
        # 区域SHM率对比图
        fig, ax = plt.subplots(figsize=(12, 8))
        
        regions = []
        mean_rates = []
        std_rates = []
        
        for region in params["regions"]:
            if region in stats:
                regions.append(region)
                mean_rates.append(stats[region]["mean_shm_rate"])
                std_rates.append(stats[region]["std_shm_rate"])
        
        x_pos = np.arange(len(regions))
        bars = ax.bar(x_pos, mean_rates, yerr=std_rates, capsize=5, alpha=0.7, color='skyblue')
        
        ax.set_xlabel("区域")
        ax.set_ylabel("SHM Rate (%)")
        ax.set_title("各区域SHM率分布", fontsize=14, fontweight='bold')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(regions)
        ax.grid(True, alpha=0.3)
        
        # 添加数值标签
        for bar, rate in zip(bars, mean_rates):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{rate:.3f}%', ha='center', va='bottom')
        
        plt.tight_layout()
        figures["region_distribution"] = self._figure_to_base64(fig)
        
        return figures
    
    def _create_spectrum_plots(self, data: pd.DataFrame, spectrum: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """创建突变频谱图"""
        figures = {}
        
        if spectrum:
            fig, ax = plt.subplots(figsize=(12, 8))
            
            mut_types = list(spectrum.keys())
            percentages = [spectrum[mt]["percentage"] for mt in mut_types]
            
            bars = ax.bar(mut_types, percentages, color='lightcoral', alpha=0.7)
            
            ax.set_xlabel("突变类型")
            ax.set_ylabel("百分比 (%)")
            ax.set_title("突变频谱分布", fontsize=14, fontweight='bold')
            ax.tick_params(axis='x', rotation=45)
            ax.grid(True, alpha=0.3)
            
            # 添加数值标签
            for bar, pct in zip(bars, percentages):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{pct:.2f}%', ha='center', va='bottom')
            
            plt.tight_layout()
            figures["mutation_spectrum"] = self._figure_to_base64(fig)
        
        return figures
    
    def _create_heatmap_plots(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """创建热图"""
        figures = {}
        
        # 样本-区域SHM率热图
        pivot_data = data.pivot_table(values="SHM_Rate", index="Sample", columns="Region", aggfunc="mean")
        
        if not pivot_data.empty:
            fig, ax = plt.subplots(figsize=(12, 8))
            
            sns.heatmap(pivot_data, annot=True, fmt=".3f", cmap="YlOrRd", 
                       ax=ax, cbar_kws={'label': 'SHM Rate (%)'})
            
            ax.set_title("样本-区域SHM率热图", fontsize=14, fontweight='bold')
            ax.set_xlabel("区域")
            ax.set_ylabel("样本")
            
            plt.tight_layout()
            figures["shm_heatmap"] = self._figure_to_base64(fig)
        
        return figures
