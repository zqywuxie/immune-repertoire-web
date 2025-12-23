"""
B细胞成熟状态分析模块
分析B细胞的成熟状态分布（Class-Switched, Naive-Mutated, Naive-Unmutated, IGHM/IGHD-Mutated）
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
class BcellMaturationAnalyzer(AnalysisModule):
    """B细胞成熟状态分析模块"""
    
    # 定义指标映射
    READS_METRICS = [
        ("class_switched_percent_by_reads", "Class-Switched (% Reads)"),
        ("naive_mutated_percent_by_reads", "Naive-Mutated (% Reads)"),
        ("naive_unmutated_percent_by_reads", "Naive-Unmutated (% Reads)"),
        ("IGHM_IGHD_mutated_by_reads", "IGHM/IGHD-Mutated (% Reads)")
    ]
    
    CLONE_METRICS = [
        ("class_switched_percent_by_clone", "Class-Switched (% Clones)"),
        ("naive_mutated_percent_by_clone", "Naive-Mutated (% Clones)"),
        ("naive_unmutated_percent_by_clone", "Naive-Unmutated (% Clones)"),
        ("IGHM_IGHD_mutated_by_clone", "IGHM/IGHD-Mutated (% Clones)")
    ]
    
    def get_name(self) -> str:
        return "bcell_maturation"
    
    def get_description(self) -> str:
        return "B细胞成熟状态分析（Class-Switched, Naive-Mutated, Naive-Unmutated, IGHM/IGHD-Mutated）"
    
    def get_category(self) -> str:
        return "isotype_analysis"
    
    def get_required_columns(self) -> List[str]:
        return ["Sample"]
    
    def get_optional_columns(self) -> List[str]:
        return [col for col, _ in self.READS_METRICS + self.CLONE_METRICS]
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "plot_type": "bar",
            "show_values": True,
            "sort_samples": True,
            "color_scheme": "Set2",
            "baseline_sample": None
        }
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行B细胞成熟状态分析"""
        try:
            analysis_params = {**self.get_default_params(), **params}
            
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
            logger.error(f"B细胞成熟状态分析失败: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _process_data(self, data: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """处理数据，生成输出格式"""
        df = data.copy()
        
        # 构建输出数据
        output_rows = []
        for _, row in df.iterrows():
            sample = row.get('Sample', '')
            output_row = {'Sample': sample}
            
            # 添加Reads指标
            for col, display_name in self.READS_METRICS:
                if col in df.columns:
                    output_row[display_name] = row.get(col, 0)
            
            # 添加Clone指标
            for col, display_name in self.CLONE_METRICS:
                if col in df.columns:
                    output_row[display_name] = row.get(col, 0)
            
            output_rows.append(output_row)
        
        result_df = pd.DataFrame(output_rows)
        
        # 排序样本
        if params.get("sort_samples", True):
            result_df = result_df.sort_values("Sample")
        
        return result_df
    
    def _generate_charts(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """生成图表"""
        charts = {}
        
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False
        plt.style.use("default")
        sns.set_palette(params.get("color_scheme", "Set2"))
        
        # 生成Reads指标条形图
        charts["reads_chart"] = self._create_stacked_bar(data, "Reads", params)
        
        # 生成Clone指标条形图
        charts["clone_chart"] = self._create_stacked_bar(data, "Clones", params)
        
        return charts
    
    def _create_stacked_bar(self, data: pd.DataFrame, metric_type: str, params: Dict[str, Any]) -> str:
        """创建堆叠条形图"""
        fig, ax = plt.subplots(figsize=(14, 8))
        
        samples = data["Sample"].tolist()
        
        # 选择对应的列
        if metric_type == "Reads":
            cols = [name for _, name in self.READS_METRICS]
        else:
            cols = [name for _, name in self.CLONE_METRICS]
        
        # 过滤存在的列
        available_cols = [c for c in cols if c in data.columns]
        
        if not available_cols:
            plt.close()
            return ""
        
        # 创建堆叠条形图
        x = np.arange(len(samples))
        width = 0.6
        bottom = np.zeros(len(samples))
        colors = sns.color_palette(params.get("color_scheme", "Set2"), len(available_cols))
        
        for i, col in enumerate(available_cols):
            values = data[col].fillna(0).values
            ax.bar(x, values, width, bottom=bottom, label=col.replace(f" (% {metric_type})", ""), color=colors[i])
            bottom += values
        
        ax.set_xlabel("样本", fontsize=12)
        ax.set_ylabel(f"百分比 (% {metric_type})", fontsize=12)
        ax.set_title(f"B细胞成熟状态分布 ({metric_type})", fontsize=14)
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=45, ha='right')
        ax.legend(loc='upper right', bbox_to_anchor=(1.15, 1))
        ax.set_ylim(0, 105)
        
        plt.tight_layout()
        
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return f"data:image/png;base64,{image_base64}"
    
    def _generate_summary(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """生成统计摘要"""
        summary = {"total_samples": len(data), "metrics": {}}
        
        all_metrics = self.READS_METRICS + self.CLONE_METRICS
        for col, display_name in all_metrics:
            if display_name in data.columns:
                values = data[display_name].dropna()
                if len(values) > 0:
                    summary["metrics"][display_name] = {
                        "mean": float(values.mean()),
                        "std": float(values.std()),
                        "min": float(values.min()),
                        "max": float(values.max())
                    }
        
        return summary

    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        if results.get("success") and "charts" in results:
            return results["charts"]
        return {}
