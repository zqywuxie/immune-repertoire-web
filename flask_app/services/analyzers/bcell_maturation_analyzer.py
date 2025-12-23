"""
B-cell Maturation Analyzer - B细胞成熟状态分析器
分析B细胞的成熟状态分布（Class-Switched, Naive-Mutated, Naive-Unmutated等）
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


class BcellMaturationAnalyzer(BaseAnalyzer):
    """
    B细胞成熟状态分析器
    
    功能:
    - 分析B细胞的成熟状态分布
    - 支持按reads和clones两种计算方式
    - 生成堆叠条形图展示各状态分布
    """
    
    # 成熟状态字段定义
    MATURATION_FIELDS = [
        ("class_switched_percent_by_reads", "Class-Switched"),
        ("naive_mutated_percent_by_reads", "Naive-Mutated"),
        ("naive_unmutated_percent_by_reads", "Naive-Unmutated"),
        ("IGHM_IGHD_mutated_by_reads", "IGHM/IGHD-Mutated")
    ]
    
    MATURATION_FIELDS_CLONE = [
        ("class_switched_percent_by_clone", "Class-Switched"),
        ("naive_mutated_percent_by_clone", "Naive-Mutated"),
        ("naive_unmutated_percent_by_clone", "Naive-Unmutated"),
        ("IGHM_IGHD_mutated_by_clone", "IGHM/IGHD-Mutated")
    ]
    
    # 状态颜色映射
    STATUS_COLORS = {
        "Class-Switched": "#1f77b4",
        "Naive-Mutated": "#ff7f0e",
        "Naive-Unmutated": "#2ca02c",
        "IGHM/IGHD-Mutated": "#d62728"
    }
    
    def __init__(self):
        super().__init__()
        self.name = "B-cell Maturation Analyzer"
        self.description = "分析B细胞的成熟状态分布"
        self.version = "1.0.0"
        
        self._default_parameters = {
            "sample_column": "Sample",
            "baseline_sample": None,
            "chart_config": {
                "figsize": [16, 10],
                "dpi": 300,
                "show_values": True
            }
        }
    
    def get_default_parameters(self) -> Dict[str, Any]:
        """返回默认参数"""
        return self._default_parameters.copy()
    
    def get_required_fields(self) -> List[str]:
        return ["Sample"]
    
    def get_optional_fields(self) -> List[str]:
        fields = [f[0] for f in self.MATURATION_FIELDS]
        fields += [f[0] for f in self.MATURATION_FIELDS_CLONE]
        return fields
    
    def validate_data(self, data: pd.DataFrame, parameters: Dict[str, Any] = None) -> ValidationResult:
        """验证数据是否包含所需字段"""
        errors = []
        warnings = []
        
        sample_col = (parameters or {}).get('sample_column', 'Sample')
        if not self._find_column(data, sample_col):
            errors.append(f"Missing required column: {sample_col}")
        
        # 检查至少有一个成熟状态字段
        found_field = False
        for field, _ in self.MATURATION_FIELDS + self.MATURATION_FIELDS_CLONE:
            if self._find_column(data, field):
                found_field = True
                break
        
        if not found_field:
            warnings.append("No maturation status fields found")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def analyze(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行B细胞成熟状态分析"""
        try:
            params = self.merge_parameters(parameters)
            
            sample_column = params.get('sample_column', 'Sample')
            baseline_sample = params.get('baseline_sample')
            
            # 提取成熟状态数据
            maturation_data = self._extract_maturation_data(data, sample_column)
            
            # 获取样本列表
            samples = list(maturation_data.keys())
            
            # 生成表格数据
            table_data = self._generate_table_data(maturation_data, samples)
            long_format_table = self._generate_long_format_table(maturation_data, samples)
            
            # 生成图表
            charts = self._generate_charts(maturation_data, samples, params, baseline_sample)
            
            return {
                "samples": samples,
                "maturation_data": maturation_data,
                "baseline_sample": baseline_sample,
                "table_data": table_data,
                "long_format_table": long_format_table,
                "charts": charts,
                "parameters": params
            }
            
        except Exception as e:
            logger.error(f"Error in B-cell Maturation analysis: {e}", exc_info=True)
            raise RuntimeError(f"B-cell Maturation analysis failed: {str(e)}")
    
    def _find_column(self, data: pd.DataFrame, target_col: str) -> Optional[str]:
        """查找匹配的列名（大小写不敏感）"""
        for col in data.columns:
            if col.lower() == target_col.lower():
                return col
        return None
    
    def _extract_maturation_data(
        self,
        data: pd.DataFrame,
        sample_column: str
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """提取每个样本的成熟状态数据"""
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
            result[sample_name] = {"by_reads": {}, "by_clone": {}}
            
            # 提取by_reads数据
            for field, label in self.MATURATION_FIELDS:
                actual_col = self._find_column(data, field)
                if actual_col:
                    value = row[actual_col]
                    if pd.notna(value):
                        try:
                            result[sample_name]["by_reads"][label] = float(value)
                        except (ValueError, TypeError):
                            result[sample_name]["by_reads"][label] = 0.0
                    else:
                        result[sample_name]["by_reads"][label] = 0.0
            
            # 提取by_clone数据
            for field, label in self.MATURATION_FIELDS_CLONE:
                actual_col = self._find_column(data, field)
                if actual_col:
                    value = row[actual_col]
                    if pd.notna(value):
                        try:
                            result[sample_name]["by_clone"][label] = float(value)
                        except (ValueError, TypeError):
                            result[sample_name]["by_clone"][label] = 0.0
                    else:
                        result[sample_name]["by_clone"][label] = 0.0
        
        return result
    
    def _generate_table_data(
        self,
        maturation_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str]
    ) -> Dict[str, Any]:
        """生成宽格式表格数据"""
        labels = [label for _, label in self.MATURATION_FIELDS]
        headers = ["Sample"]
        headers += [f"{label} (Reads%)" for label in labels]
        headers += [f"{label} (Clone%)" for label in labels]
        
        rows = []
        for sample in samples:
            row = [sample]
            sample_data = maturation_data.get(sample, {})
            
            # by_reads
            for label in labels:
                value = sample_data.get("by_reads", {}).get(label, 0)
                row.append(round(value, 3) if value else 0)
            
            # by_clone
            for label in labels:
                value = sample_data.get("by_clone", {}).get(label, 0)
                row.append(round(value, 3) if value else 0)
            
            rows.append(row)
        
        return {
            "headers": headers,
            "rows": rows,
            "tab_separated": self._to_tab_separated(headers, rows)
        }
    
    def _generate_long_format_table(
        self,
        maturation_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str]
    ) -> Dict[str, Any]:
        """生成长格式表格数据"""
        headers = ["Sample", "Status", "By_Reads%", "By_Clone%"]
        rows = []
        
        labels = [label for _, label in self.MATURATION_FIELDS]
        
        for sample in samples:
            sample_data = maturation_data.get(sample, {})
            for label in labels:
                by_reads = sample_data.get("by_reads", {}).get(label, 0)
                by_clone = sample_data.get("by_clone", {}).get(label, 0)
                rows.append([sample, label, round(by_reads, 3), round(by_clone, 3)])
        
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
        maturation_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        params: Dict[str, Any],
        baseline_sample: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """生成B细胞成熟状态图表 - 参考extract_ct_shm_classification_final.py"""
        charts = []
        
        try:
            plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
            plt.rcParams["axes.unicode_minus"] = False
            
            chart_config = params.get('chart_config', {})
            figsize = chart_config.get('figsize', [20, 16])
            baseline_sample = params.get('baseline_sample') or baseline_sample
            
            labels = [label for _, label in self.MATURATION_FIELDS]
            colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
            
            # 查找基准样本索引
            baseline_idx = None
            if baseline_sample and baseline_sample in samples:
                baseline_idx = samples.index(baseline_sample)
            
            # 为by_reads和by_clone分别创建图表
            for data_type, title_suffix in [("by_reads", "By Reads"), ("by_clone", "By Clones")]:
                fig, axes = plt.subplots(2, 2, figsize=(figsize[0], figsize[1]))
                
                title = f"SHM Classification {title_suffix}"
                if baseline_sample and baseline_idx is not None:
                    title = f"SHM Classification {title_suffix} - Percentage Change from Baseline\n(Baseline: {baseline_sample})"
                
                fig.suptitle(title, fontsize=18, fontweight="bold", y=0.98)
                axes = axes.flatten()
                
                x_pos = np.arange(len(samples))
                bar_width = 0.6
                
                for idx, label in enumerate(labels[:4]):
                    ax = axes[idx]
                    
                    # 获取值
                    values = [maturation_data.get(s, {}).get(data_type, {}).get(label, 0) for s in samples]
                    
                    # 计算百分比变化
                    if baseline_idx is not None and values[baseline_idx] != 0:
                        baseline_value = values[baseline_idx]
                        pct_change = [(v - baseline_value) / baseline_value * 100 for v in values]
                        ylabel = "Percentage Change from Baseline (%)"
                    else:
                        pct_change = values
                        ylabel = "Percentage (%)"
                    
                    bars = ax.bar(x_pos, pct_change, bar_width, color=colors[idx], alpha=0.8)
                    
                    # 高亮基准样本
                    if baseline_idx is not None and baseline_idx < len(bars):
                        bars[baseline_idx].set_alpha(1.0)
                        bars[baseline_idx].set_edgecolor("black")
                        bars[baseline_idx].set_linewidth(2)
                        ax.axhline(y=0, color="gray", linestyle="-", linewidth=2, alpha=0.8)
                    
                    ax.set_xticks(x_pos)
                    ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=9)
                    ax.set_ylabel(ylabel, fontsize=11, fontweight='bold')
                    ax.set_xlabel('Sample', fontsize=11, fontweight='bold')
                    ax.set_title(label, fontsize=14, fontweight='bold')
                    ax.grid(axis='y', alpha=0.3, linestyle='--')
                    ax.set_facecolor('#f8f9fa')
                    
                    # 设置Y轴范围
                    if pct_change:
                        ymin = min(pct_change) * 1.2 if min(pct_change) < 0 else -5
                        ymax = max(pct_change) * 1.2 if max(pct_change) > 0 else 5
                        ax.set_ylim(ymin, ymax)
                
                plt.tight_layout(rect=[0, 0, 1, 0.96])
                
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
                buf.seek(0)
                chart_base64 = base64.b64encode(buf.read()).decode('utf-8')
                plt.close(fig)
                
                charts.append({
                    'title': f'B-cell Maturation Status ({title_suffix})',
                    'base64': chart_base64
                })
            
        except Exception as e:
            logger.error(f"Error generating charts: {e}", exc_info=True)
        
        return charts
