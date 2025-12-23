"""
Sequencing Reads Chart Analysis Module
测序reads图表分析模块 - 生成各链的reads数和百分比条形图
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
class SequencingReadsChartModule(AnalysisModule):
    """测序reads图表分析模块"""
    
    def get_name(self) -> str:
        return "sequencing_reads_chart"
    
    def get_description(self) -> str:
        return "测序reads条形图分析（TRA/TRB/TRD/TRG/IGH/IGK/IGL reads数和百分比）"
    
    def get_category(self) -> str:
        return "quality_control"
    
    def get_required_columns(self) -> List[str]:
        return ["Sample"]
    
    def get_optional_columns(self) -> List[str]:
        return [
            "Group", "Timepoint", "Condition",
            "TRA_reads", "TRB_reads", "TRD_reads", "TRG_reads",
            "IGH_reads", "IGK_reads", "IGL_reads",
            "TRA_percent_reads_all", "TRB_percent_reads_all", 
            "TRD_percent_reads_all", "TRG_percent_reads_all",
            "IGH_percent_reads_all", "IGK_percent_reads_all", 
            "IGL_percent_reads_all"
        ]
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "chains": ["TRA", "TRB", "TRD", "TRG", "IGH", "IGK", "IGL"],
            "plot_type": "reads",  # reads, percentage, both
            "show_values": True,
            "sort_samples": True,
            "color_scheme": "Set2"
        }
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行测序reads图表分析"""
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
            logger.error(f"测序reads图表分析失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _validate_columns(self, data: pd.DataFrame, params: Dict[str, Any]) -> List[str]:
        """验证所需列是否存在"""
        missing = []
        chains = params["chains"]
        
        # 检查样本列
        if "Sample" not in data.columns:
            missing.append("Sample")
        
        # 检查reads列
        for chain in chains:
            reads_col = f"{chain}_reads"
            if reads_col not in data.columns:
                missing.append(reads_col)
        
        # 如果需要百分比数据
        if params["plot_type"] in ["percentage", "both"]:
            for chain in chains:
                pct_col = f"{chain}_percent_reads_all"
                if pct_col not in data.columns:
                    missing.append(pct_col)
        
        return missing
    
    def _process_data(self, data: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """处理数据"""
        chains = params["chains"]
        df = data.copy()
        
        # 计算总reads数
        reads_cols = [f"{chain}_reads" for chain in chains]
        df["total_reads"] = df[reads_cols].sum(axis=1)
        
        # 如果需要，计算百分比
        if params["plot_type"] in ["percentage", "both"]:
            pct_cols = [f"{chain}_percent_reads_all" for chain in chains]
            # 如果没有提供百分比列，则计算
            if any(col not in df.columns for col in pct_cols):
                for chain in chains:
                    reads_col = f"{chain}_reads"
                    pct_col = f"{chain}_percent_reads_all"
                    if pct_col not in df.columns:
                        df[pct_col] = (df[reads_col] / df["total_reads"] * 100).round(2)
        
        # 排序样本
        if params["sort_samples"] and "Group" in df.columns:
            df = df.sort_values(["Group", "Sample"])
        elif params["sort_samples"]:
            df = df.sort_values("Sample")
        
        return df
    
    def _generate_charts(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """生成图表"""
        charts = {}
        chains = params["chains"]
        
        # 设置中文字体
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
        plt.rcParams["axes.unicode_minus"] = False
        
        # 设置颜色
        colors = sns.color_palette(params["color_scheme"], len(chains))
        
        if params["plot_type"] in ["reads", "both"]:
            # 生成reads数条形图
            charts["reads_chart"] = self._create_reads_bar_chart(data, chains, colors, params)
        
        if params["plot_type"] in ["percentage", "both"]:
            # 生成百分比条形图
            charts["percentage_chart"] = self._create_percentage_bar_chart(data, chains, colors, params)
        
        return charts
    
    def _create_reads_bar_chart(self, data: pd.DataFrame, chains: List[str], 
                              colors: List, params: Dict[str, Any]) -> str:
        """创建reads数条形图"""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # 准备数据
        samples = data["Sample"].tolist()
        reads_data = []
        for chain in chains:
            reads_data.append(data[f"{chain}_reads"].tolist())
        
        # 创建堆叠条形图
        bottom = np.zeros(len(samples))
        for i, (chain, color) in enumerate(zip(chains, colors)):
            ax.bar(samples, reads_data[i], bottom=bottom, label=chain, color=color)
            bottom += reads_data[i]
        
        # 设置标签和标题
        ax.set_xlabel("样本")
        ax.set_ylabel("Reads数")
        ax.set_title("各链测序reads数分布")
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        
        # 显示数值
        if params["show_values"]:
            for i, sample in enumerate(samples):
                y_pos = 0
                for j, chain in enumerate(chains):
                    value = reads_data[j][i]
                    if value > 0:
                        ax.text(i, y_pos + value/2, f"{value:,}", 
                               ha='center', va='center', fontsize=8)
                    y_pos += value
        
        # 调整布局
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        
        # 转换为base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return f"data:image/png;base64,{image_base64}"
    
    def _create_percentage_bar_chart(self, data: pd.DataFrame, chains: List[str], 
                                   colors: List, params: Dict[str, Any]) -> str:
        """创建百分比条形图"""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # 准备数据
        samples = data["Sample"].tolist()
        pct_data = []
        for chain in chains:
            pct_data.append(data[f"{chain}_percent_reads_all"].tolist())
        
        # 创建堆叠条形图
        bottom = np.zeros(len(samples))
        for i, (chain, color) in enumerate(zip(chains, colors)):
            ax.bar(samples, pct_data[i], bottom=bottom, label=chain, color=color)
            bottom += pct_data[i]
        
        # 设置标签和标题
        ax.set_xlabel("样本")
        ax.set_ylabel("百分比 (%)")
        ax.set_title("各链测序reads百分比分布")
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        
        # 显示数值
        if params["show_values"]:
            for i, sample in enumerate(samples):
                y_pos = 0
                for j, chain in enumerate(chains):
                    value = pct_data[j][i]
                    if value > 0.1:  # 只显示大于0.1%的值
                        ax.text(i, y_pos + value/2, f"{value:.1f}%", 
                               ha='center', va='center', fontsize=8)
                    y_pos += value
        
        # 调整布局
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
        chains = params["chains"]
        summary = {
            "total_samples": len(data),
            "chains": chains,
            "chain_stats": {}
        }
        
        # 计算每条链的统计信息
        for chain in chains:
            reads_col = f"{chain}_reads"
            pct_col = f"{chain}_percent_reads_all"
            
            chain_summary = {
                "total_reads": int(data[reads_col].sum()),
                "mean_reads": float(data[reads_col].mean()),
                "std_reads": float(data[reads_col].std()),
                "mean_percentage": float(data[pct_col].mean()) if pct_col in data.columns else None
            }
            
            summary["chain_stats"][chain] = chain_summary
        
        # 找出主导链
        summary["dominant_chain"] = max(chains, 
                                      key=lambda c: data[f"{c}_reads"].sum())
        
        return summary

    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表，返回图表的base64编码字典"""
        # 图表已在analyze方法中生成
        if results.get("success") and "charts" in results:
            return results["charts"]
        return {}

    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        # 图表已在analyze方法中生成
        if results.get("success") and "charts" in results:
            return results["charts"]
        return {}
