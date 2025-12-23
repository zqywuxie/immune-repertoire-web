"""
SHM Fields Analysis Module
体细胞超突变(SHM)字段分析模块 - 分析IGHA、IGHG12、IGHG34、IGHM_IGHD的SHM0和SHM1值
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, Any, List, Tuple
import logging
import io
import base64

from ..base_module import AnalysisModule, AnalysisResult
from ..registry import register_module

logger = logging.getLogger(__name__)


@register_module
class SHMFieldsAnalysisModule(AnalysisModule):
    """体细胞超突变字段分析模块"""
    
    def get_name(self) -> str:
        return "shm_fields_analysis"
    
    def get_description(self) -> str:
        return "体细胞超突变分析（IGHA、IGHG12、IGHG34、IGHM_IGHD的SHM0和SHM1值）"
    
    def get_category(self) -> str:
        return "mutation_analysis"
    
    def get_required_columns(self) -> List[str]:
        return ["Sample"]
    
    def get_optional_columns(self) -> List[str]:
        return [
            "Group", "Timepoint", "Condition",
            "IGHA_SHM0", "IGHA_SHM1",
            "IGHG12_SHM0", "IGHG12_SHM1", 
            "IGHG34_SHM0", "IGHG34_SHM1",
            "IGHM_IGHD_SHM0", "IGHM_IGHD_SHM1"
        ]
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "isotypes": ["IGHA", "IGHG12", "IGHG34", "IGHM_IGHD"],
            "plot_type": "comparison",  # comparison, distribution, heatmap
            "show_values": True,
            "sort_samples": True,
            "baseline_sample": None,  # 基线样本，用于计算百分比变化
            "color_scheme": "Set1"
        }
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行SHM字段分析"""
        try:
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            # 验证所需列
            missing_cols = self._validate_columns(data, analysis_params)
            if missing_cols:
                raise ValueError(f"缺少必需的列: {', '.join(missing_cols)}")
            
            # 处理数据
            processed_data = self._process_data(data, analysis_params)
            
            # 生成图表
            charts = self._generate_charts(processed_data, analysis_params)
            
            # 生成统计摘要
            summary = self._generate_summary(processed_data, analysis_params)
            
            return {
                "success": True,
                "data": processed_data.to_dict('records'),
                "charts": charts,
                "summary": summary,
                "parameters": analysis_params
            }
            
        except Exception as e:
            logger.error(f"SHM字段分析失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _validate_columns(self, data: pd.DataFrame, params: Dict[str, Any]) -> List[str]:
        """验证所需列是否存在"""
        missing = []
        isotypes = params["isotypes"]
        
        # 检查样本列
        if "Sample" not in data.columns:
            missing.append("Sample")
        
        # 检查每个亚型的SHM0和SHM1列
        for isotype in isotypes:
            shm0_col = f"{isotype}_SHM0"
            shm1_col = f"{isotype}_SHM1"
            if shm0_col not in data.columns:
                missing.append(shm0_col)
            if shm1_col not in data.columns:
                missing.append(shm1_col)
        
        return missing
    
    def _process_data(self, data: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """处理数据"""
        isotypes = params["isotypes"]
        df = data.copy()
        
        # 计算每个亚型的SHM差值和变化率
        for isotype in isotypes:
            shm0_col = f"{isotype}_SHM0"
            shm1_col = f"{isotype}_SHM1"
            diff_col = f"{isotype}_SHM_diff"
            pct_change_col = f"{isotype}_SHM_pct_change"
            
            # 计算差值
            df[diff_col] = df[shm1_col] - df[shm0_col]
            
            # 计算百分比变化（避免除零）
            df[pct_change_col] = np.where(
                df[shm0_col] != 0,
                (df[shm1_col] - df[shm0_col]) / df[shm0_col] * 100,
                np.nan
            )
        
        # 如果指定了基线样本，计算相对于基线的变化
        if params["baseline_sample"] and params["baseline_sample"] in df["Sample"].values:
            baseline_data = df[df["Sample"] == params["baseline_sample"]].iloc[0]
            for isotype in isotypes:
                shm0_col = f"{isotype}_SHM0"
                baseline_col = f"{isotype}_baseline_SHM0"
                baseline_pct_col = f"{isotype}_baseline_pct_change"
                
                df[baseline_col] = df[shm0_col] - baseline_data[shm0_col]
                df[baseline_pct_col] = np.where(
                    baseline_data[shm0_col] != 0,
                    (df[shm0_col] - baseline_data[shm0_col]) / baseline_data[shm0_col] * 100,
                    np.nan
                )
        
        # 排序样本
        if params["sort_samples"] and "Group" in df.columns:
            df = df.sort_values(["Group", "Sample"])
        elif params["sort_samples"]:
            df = df.sort_values("Sample")
        
        return df
    
    def _generate_charts(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """生成图表"""
        charts = {}
        isotypes = params["isotypes"]
        
        # 设置中文字体
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False
        
        if params["plot_type"] in ["comparison", "both"]:
            # 生成对比图
            charts["comparison_chart"] = self._create_comparison_chart(data, isotypes, params)
        
        if params["plot_type"] in ["distribution", "both"]:
            # 生成分布图
            charts["distribution_chart"] = self._create_distribution_chart(data, isotypes, params)
        
        if params["plot_type"] in ["heatmap", "both"]:
            # 生成热图
            charts["heatmap"] = self._create_heatmap(data, isotypes, params)
        
        return charts
    
    def _create_comparison_chart(self, data: pd.DataFrame, isotypes: List[str], 
                                params: Dict[str, Any]) -> str:
        """创建SHM对比图"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle("体细胞超突变(SHM)对比分析", fontsize=16)
        
        # 设置颜色
        colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        
        # 为每个亚型创建子图
        for idx, isotype in enumerate(isotypes):
            row, col = idx // 2, idx % 2
            ax = axes[row, col]
            
            shm0_col = f"{isotype}_SHM0"
            shm1_col = f"{isotype}_SHM1"
            
            # 绘制SHM0和SHM1的条形图
            samples = data["Sample"].tolist()
            x = np.arange(len(samples))
            width = 0.35
            
            ax.bar(x - width/2, data[shm0_col], width, label='SHM0', color=colors[0], alpha=0.8)
            ax.bar(x + width/2, data[shm1_col], width, label='SHM1', color=colors[1], alpha=0.8)
            
            # 设置标题和标签
            ax.set_title(f"{isotype} SHM对比")
            ax.set_xlabel("样本")
            ax.set_ylabel("SHM值")
            ax.legend()
            ax.set_xticks(x)
            ax.set_xticklabels(samples, rotation=45, ha='right')
            
            # 显示数值
            if params["show_values"]:
                for i, (shm0, shm1) in enumerate(zip(data[shm0_col], data[shm1_col])):
                    ax.text(i - width/2, shm0 + max(data[shm0_col]) * 0.01, 
                           f"{shm0:.2f}", ha='center', va='bottom', fontsize=8)
                    ax.text(i + width/2, shm1 + max(data[shm1_col]) * 0.01, 
                           f"{shm1:.2f}", ha='center', va='bottom', fontsize=8)
        
        plt.tight_layout()
        
        # 转换为base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return f"data:image/png;base64,{image_base64}"
    
    def _create_distribution_chart(self, data: pd.DataFrame, isotypes: List[str], 
                                  params: Dict[str, Any]) -> str:
        """创建SHM分布图"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle("体细胞超突变(SHM)分布分析", fontsize=16)
        
        # 为每个亚型创建箱线图
        for idx, isotype in enumerate(isotypes):
            row, col = idx // 2, idx % 2
            ax = axes[row, col]
            
            shm0_col = f"{isotype}_SHM0"
            shm1_col = f"{isotype}_SHM1"
            
            # 准备数据
            shm0_data = data[shm0_col].tolist()
            shm1_data = data[shm1_col].tolist()
            
            # 创建箱线图
            box_data = [shm0_data, shm1_data]
            bp = ax.boxplot(box_data, labels=['SHM0', 'SHM1'], patch_artist=True)
            
            # 设置颜色
            colors = ['lightblue', 'lightcoral']
            for patch, color in zip(bp['boxes'], colors):
                patch.set_facecolor(color)
            
            # 设置标题和标签
            ax.set_title(f"{isotype} SHM分布")
            ax.set_ylabel("SHM值")
            ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 转换为base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return f"data:image/png;base64,{image_base64}"
    
    def _create_heatmap(self, data: pd.DataFrame, isotypes: List[str], 
                       params: Dict[str, Any]) -> str:
        """创建SHM热图"""
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # 准备数据矩阵
        matrix_data = []
        labels = []
        
        for isotype in isotypes:
            # 使用SHM0数据
            shm0_col = f"{isotype}_SHM0"
            matrix_data.append(data[shm0_col].tolist())
            labels.append(f"{isotype}_SHM0")
            
            # 使用SHM1数据
            shm1_col = f"{isotype}_SHM1"
            matrix_data.append(data[shm1_col].tolist())
            labels.append(f"{isotype}_SHM1")
        
        # 创建热图
        sns.heatmap(matrix_data,
                   xticklabels=data["Sample"].tolist(),
                   yticklabels=labels,
                   annot=params["show_values"],
                   fmt=".2f",
                   cmap="RdYlBu_r",
                   center=0,
                   ax=ax)
        
        ax.set_title("体细胞超突变(SHM)热图")
        ax.set_xlabel("样本")
        ax.set_ylabel("亚型_SHM状态")
        
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        # 转换为base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return f"data:image/png;base64,{image_base64}"
    
    def _generate_summary(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成统计摘要"""
        isotypes = params["isotypes"]
        summary = {
            "total_samples": len(data),
            "isotypes": isotypes,
            "shm_stats": {}
        }
        
        # 计算每个亚型的SHM统计信息
        for isotype in isotypes:
            shm0_col = f"{isotype}_SHM0"
            shm1_col = f"{isotype}_SHM1"
            diff_col = f"{isotype}_SHM_diff"
            
            shm_summary = {
                "shm0_mean": float(data[shm0_col].mean()),
                "shm0_std": float(data[shm0_col].std()),
                "shm1_mean": float(data[shm1_col].mean()),
                "shm1_std": float(data[shm1_col].std()),
                "diff_mean": float(data[diff_col].mean()),
                "diff_std": float(data[diff_col].std()),
                "increased_samples": int((data[shm1_col] > data[shm0_col]).sum()),
                "decreased_samples": int((data[shm1_col] < data[shm0_col]).sum())
            }
            
            summary["shm_stats"][isotype] = shm_summary
        
        # 计算相关性矩阵
        shm_cols = []
        for isotype in isotypes:
            shm_cols.extend([f"{isotype}_SHM0", f"{isotype}_SHM1"])
        
        correlation_data = data[shm_cols].corr()
        summary["correlation_matrix"] = correlation_data.to_dict()
        
        return summary

    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        # 图表已在analyze方法中生成
        if results.get("success") and "charts" in results:
            return results["charts"]
        return {}
