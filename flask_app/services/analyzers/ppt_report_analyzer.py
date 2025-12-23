"""
PPT Report Generator - PPT报告生成器
生成测序深度分析PPT报告模块
参考sequencing_depth_ppt_module_final.py
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import logging
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from .base_analyzer import BaseAnalyzer, ValidationResult

logger = logging.getLogger(__name__)


class PPTReportGenerator(BaseAnalyzer):
    """
    PPT报告生成器
    
    功能:
    - 生成测序深度差异表格模块
    - 生成测序深度差异条形图模块
    - 适合PPT插入的紧凑格式
    """
    
    # 测序深度字段 - 与脚本保持一致
    DEPTH_FIELDS = [
        ("Total_Receptor_RNA", "Total Receptor RNA"),
        ("MigsGoodTotal", "MigsGoodTotal"),
        ("ReadsGoodTotal", "ReadsGoodTotal")
    ]
    
    def __init__(self):
        super().__init__()
        self.name = "PPT Report Generator"
        self.description = "生成测序深度分析PPT报告"
        self.version = "1.0.0"
        
        self._default_parameters = {
            "sample_column": "Sample",
            "baseline_sample": None,
            "chart_config": {
                "figsize": [14, 6],
                "dpi": 300
            }
        }
    
    def get_default_parameters(self) -> Dict[str, Any]:
        """返回默认参数"""
        return self._default_parameters.copy()
    
    def get_required_fields(self) -> List[str]:
        return ["Sample"]
    
    def get_optional_fields(self) -> List[str]:
        return [f[0] for f in self.DEPTH_FIELDS]
    
    def validate_data(self, data: pd.DataFrame, parameters: Dict[str, Any] = None) -> ValidationResult:
        """验证数据是否包含所需字段"""
        errors = []
        warnings = []
        
        sample_col = (parameters or {}).get('sample_column', 'Sample')
        if not self._find_column(data, sample_col):
            errors.append(f"Missing required column: {sample_col}")
        
        # 检查至少有一个深度字段
        found_field = False
        for field, _ in self.DEPTH_FIELDS:
            if self._find_column(data, field):
                found_field = True
                break
        
        if not found_field:
            warnings.append("No sequencing depth fields found")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def analyze(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行PPT报告生成"""
        try:
            params = self.merge_parameters(parameters)
            
            sample_column = params.get('sample_column', 'Sample')
            baseline_sample = params.get('baseline_sample')
            
            # 提取深度数据
            depth_data = self._extract_depth_data(data, sample_column)
            
            # 获取样本列表
            samples = list(depth_data.keys())
            
            # 生成表格数据
            table_data = self._generate_table_data(depth_data, samples, baseline_sample)
            
            # 生成图表
            charts = self._generate_charts(depth_data, samples, params, baseline_sample)
            
            return {
                "samples": samples,
                "depth_data": depth_data,
                "baseline_sample": baseline_sample,
                "table_data": table_data,
                "charts": charts,
                "parameters": params
            }
            
        except Exception as e:
            logger.error(f"Error in PPT Report generation: {e}", exc_info=True)
            raise RuntimeError(f"PPT Report generation failed: {str(e)}")
    
    def _find_column(self, data: pd.DataFrame, target_col: str) -> Optional[str]:
        """查找匹配的列名（大小写不敏感）"""
        for col in data.columns:
            if col.lower() == target_col.lower():
                return col
        return None
    
    def _extract_depth_data(
        self,
        data: pd.DataFrame,
        sample_column: str
    ) -> Dict[str, Dict[str, float]]:
        """提取每个样本的测序深度数据"""
        result = {}
        
        actual_sample_col = self._find_column(data, sample_column)
        if not actual_sample_col:
            actual_sample_col = data.columns[0]
        
        for idx, row in data.iterrows():
            sample_value = row[actual_sample_col]
            # 确保获取单个值而不是Series
            if hasattr(sample_value, 'iloc'):
                sample_name = str(sample_value.iloc[0])
            elif hasattr(sample_value, 'values'):
                sample_name = str(sample_value.values[0]) if len(sample_value.values) > 0 else str(idx)
            else:
                sample_name = str(sample_value)
            
            result[sample_name] = {}
            
            for field, label in self.DEPTH_FIELDS:
                actual_col = self._find_column(data, field)
                if actual_col:
                    value = row[actual_col]
                    if pd.notna(value):
                        try:
                            result[sample_name][label] = float(value)
                        except (ValueError, TypeError):
                            result[sample_name][label] = 0.0
                    else:
                        result[sample_name][label] = 0.0
        
        return result
    
    def _generate_table_data(
        self,
        depth_data: Dict[str, Dict[str, float]],
        samples: List[str],
        baseline_sample: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成表格数据"""
        labels = [label for _, label in self.DEPTH_FIELDS]
        headers = ["Sample"] + labels
        rows = []
        
        # 获取基准值
        baseline_values = {}
        if baseline_sample and baseline_sample in depth_data:
            baseline_values = depth_data[baseline_sample]
        
        for sample in samples:
            row = [sample]
            sample_data = depth_data.get(sample, {})
            
            for label in labels:
                value = sample_data.get(label, 0)
                if baseline_sample and sample == baseline_sample:
                    row.append("Baseline")
                elif baseline_sample and label in baseline_values and baseline_values[label] != 0:
                    diff = (value / baseline_values[label] - 1) * 100
                    if diff > 0:
                        row.append(f"+{diff:.1f}%")
                    else:
                        row.append(f"{diff:.1f}%")
                else:
                    row.append(f"{value:,.0f}")
            
            rows.append(row)
        
        return {
            "headers": headers,
            "rows": rows,
            "tab_separated": self._to_tab_separated(headers, rows)
        }
    
    def _to_tab_separated(self, headers: List[str], rows: List[List[Any]]) -> str:
        """转换为制表符分隔的文本"""
        lines = ["\t".join(str(h) for h in headers)]
        for row in rows:
            lines.append("\t".join(str(v) if v is not None else "" for v in row))
        return "\n".join(lines)
    
    def _generate_charts(
        self,
        depth_data: Dict[str, Dict[str, float]],
        samples: List[str],
        params: Dict[str, Any],
        baseline_sample: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """生成PPT报告图表 - 参考sequencing_depth_ppt_module_final.py
        
        自动选择Total Receptor RNA最低的样本作为基准
        """
        charts = []
        
        try:
            plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
            plt.rcParams["axes.unicode_minus"] = False
            
            labels = [label for _, label in self.DEPTH_FIELDS]
            
            # 自动选择Total Receptor RNA最低的样本作为基准
            baseline_sample = None
            baseline_idx = None
            min_rna = float('inf')
            
            for i, sample in enumerate(samples):
                rna_value = depth_data.get(sample, {}).get("Total Receptor RNA", 0)
                if rna_value > 0 and rna_value < min_rna:
                    min_rna = rna_value
                    baseline_sample = sample
                    baseline_idx = i
            
            # 只创建表格模块
            fig1 = self._create_table_module(depth_data, samples, labels, baseline_sample, baseline_idx)
            if fig1:
                buf = io.BytesIO()
                fig1.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
                buf.seek(0)
                charts.append({
                    'title': 'Sequencing Depth Table',
                    'base64': base64.b64encode(buf.read()).decode('utf-8')
                })
                plt.close(fig1)
            
        except Exception as e:
            logger.error(f"Error generating charts: {e}", exc_info=True)
        
        return charts
    
    def _create_table_module(
        self,
        depth_data: Dict[str, Dict[str, float]],
        samples: List[str],
        labels: List[str],
        baseline_sample: Optional[str],
        baseline_idx: Optional[int]
    ):
        """创建表格模块"""
        fig, ax = plt.subplots(1, 1, figsize=(12, max(3.5, len(samples) * 0.4)))
        
        # 获取基准值
        baseline_values = {}
        if baseline_sample and baseline_sample in depth_data:
            baseline_values = depth_data[baseline_sample]
        
        # 准备表格数据
        table_data = []
        for i, sample in enumerate(samples):
            row = [sample]
            sample_data = depth_data.get(sample, {})
            for label in labels:
                value = sample_data.get(label, 0)
                if baseline_sample and i == baseline_idx:
                    row.append("Baseline")
                elif baseline_sample and label in baseline_values and baseline_values[label] != 0:
                    diff = (value / baseline_values[label] - 1) * 100
                    if diff > 0:
                        row.append(f"+{diff:.1f}%")
                    else:
                        row.append(f"{diff:.1f}%")
                else:
                    row.append(f"{value:,.0f}")
            table_data.append(row)
        
        # 创建表格
        col_labels = ["Sample"] + labels
        table = ax.table(
            cellText=table_data,
            colLabels=col_labels,
            cellLoc="center",
            loc="center",
            colWidths=[0.25] + [0.25] * len(labels)
        )
        
        # 设置表格样式
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.5)
        
        # 设置表头颜色
        for i in range(len(col_labels)):
            table[(0, i)].set_facecolor("#34495e")
            table[(0, i)].set_text_props(weight="bold", color="white")
        
        # 突出显示基准样本行
        if baseline_idx is not None:
            for j in range(len(col_labels)):
                table[(baseline_idx + 1, j)].set_facecolor("#ffebee")
                table[(baseline_idx + 1, j)].set_text_props(color="red", weight="bold")
        
        ax.axis("off")
        plt.tight_layout(pad=0)
        
        return fig
    
    def _create_bar_chart(
        self,
        depth_data: Dict[str, Dict[str, float]],
        samples: List[str],
        labels: List[str],
        colors: List[str],
        baseline_sample: Optional[str],
        baseline_idx: Optional[int],
        figsize: List[int]
    ):
        """创建条形图模块"""
        fig, ax = plt.subplots(1, 1, figsize=(figsize[0], figsize[1]))
        
        # 获取基准值
        baseline_values = {}
        if baseline_sample and baseline_sample in depth_data:
            baseline_values = depth_data[baseline_sample]
        
        x = np.arange(len(samples))
        width = 0.25
        
        # 绘制条形图
        for i, (label, color) in enumerate(zip(labels, colors)):
            # 计算百分比差异
            pct_diff = []
            for sample in samples:
                value = depth_data.get(sample, {}).get(label, 0)
                if baseline_sample and label in baseline_values and baseline_values[label] != 0:
                    diff = (value / baseline_values[label] - 1) * 100
                else:
                    diff = 0
                pct_diff.append(diff)
            
            bars = ax.bar(x + i * width, pct_diff, width, label=label, color=color, alpha=0.8)
            
            # 突出显示基准样本
            if baseline_idx is not None and baseline_idx < len(bars):
                bars[baseline_idx].set_edgecolor("black")
                bars[baseline_idx].set_linewidth(2)
                bars[baseline_idx].set_alpha(1.0)
        
        # 添加基准线
        ax.axhline(y=0, color="red", linestyle="--", alpha=0.7, label="Baseline (0%)")
        
        # 设置图表
        title = "Sequencing Depth Differences"
        if baseline_sample:
            title = f"Sequencing Depth Differences (Baseline: {baseline_sample})"
        
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_ylabel("Percentage Difference (%)", fontsize=12)
        ax.set_xlabel("Sample", fontsize=12)
        ax.set_xticks(x + width)
        ax.set_xticklabels(samples, rotation=45, ha="right")
        ax.legend(loc="upper left", fontsize=10)
        ax.grid(axis="y", alpha=0.3)
        
        plt.tight_layout()
        
        return fig
