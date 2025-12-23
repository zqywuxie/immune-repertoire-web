"""
B Cell Isotype Analyzer Module - B细胞同型分布分析
分析B细胞的6种同型分布数据（IgM, IgD, IgA1/2, IgG1/2, IgG3/4, IgE）

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any, List, Tuple, Optional
import logging

from ..base_module import AnalysisModule
from ..registry import register_module

logger = logging.getLogger(__name__)


class BcellChartConfig:
    """B细胞同型分析图表配置类"""
    
    def __init__(
        self,
        title: str = "",
        figsize: Tuple[int, int] = (16, 8),
        dpi: int = 300,
        expression_colors: List[str] = None,
        cdr3_colors: List[str] = None,
        font_size: int = 12,
        show_values: bool = True
    ):
        self.title = title
        self.figsize = figsize
        self.dpi = dpi
        self.expression_colors = expression_colors or [
            "#2E86AB", "#457B9D", "#5DADE2", "#85C1E9", "#AED6F1", "#D6EAF8"
        ]
        self.cdr3_colors = cdr3_colors or [
            "#A23B72", "#C06C84", "#F67280", "#F8B195", "#F6B352", "#FFA07A"
        ]
        self.font_size = font_size
        self.show_values = show_values
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'BcellChartConfig':
        """从字典创建配置"""
        return cls(
            title=config_dict.get('title', ''),
            figsize=tuple(config_dict.get('figsize', (16, 8))),
            dpi=config_dict.get('dpi', 300),
            expression_colors=config_dict.get('expression_colors'),
            cdr3_colors=config_dict.get('cdr3_colors'),
            font_size=config_dict.get('font_size', 12),
            show_values=config_dict.get('show_values', True)
        )


@register_module
class BcellIsotypeAnalyzer(AnalysisModule):
    """
    B细胞同型分布分析器
    
    功能:
    - 提取6种同型的Expression %和Unique CDR3 %数据
    - 计算相对于基准样本的百分比差异
    - 生成水平柱状图可视化
    - 生成可复制的数据表格
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
    """
    
    # 6种B细胞同型
    ISOTYPES = ["IgM", "IgD", "IgA1/2", "IgG1/2", "IgG3/4", "IgE"]
    
    # 同型字段映射（支持多种命名格式）
    ISOTYPE_FIELD_PATTERNS = {
        "IgM": ["IgM", "IGM", "igm"],
        "IgD": ["IgD", "IGD", "igd"],
        "IgA1/2": ["IgA1/2", "IgA12", "IgA1_2", "IGHA", "IgA"],
        "IgG1/2": ["IgG1/2", "IgG12", "IgG1_2", "IGHG12", "IgG1"],
        "IgG3/4": ["IgG3/4", "IgG34", "IgG3_4", "IGHG34", "IgG3"],
        "IgE": ["IgE", "IGE", "ige"]
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.chart_config = BcellChartConfig()
        if config and 'chart_config' in config:
            self.chart_config = BcellChartConfig.from_dict(config['chart_config'])
    
    def get_name(self) -> str:
        return "bcell_isotype_analyzer"
    
    def get_description(self) -> str:
        return "B细胞同型分布分析 - 分析6种同型的Expression %和Unique CDR3 %"
    
    def get_category(self) -> str:
        return "bcell_analysis"
    
    def get_required_columns(self) -> List[str]:
        # 需要样本列和至少一个同型数据列
        return []
    
    def get_optional_columns(self) -> List[str]:
        return []
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "sample_column": "Sample",
            "baseline_sample": None,
            "sample_order": None,  # 自定义样本排序 (Requirements: 11.1, 11.2)
            "sample_groups": None,  # 样本分组配置 (Requirements: 11.3, 11.4)
            "chart_config": {
                "title": "",
                "figsize": (16, 8),
                "dpi": 300,
                "font_size": 12,
                "show_values": True
            }
        }
    
    def validate_data(self, data: pd.DataFrame) -> Tuple[bool, str]:
        """验证输入数据"""
        if data.empty:
            return False, "数据为空"
        
        # 检查是否有同型相关的列
        has_isotype_data = False
        for isotype in self.ISOTYPES:
            patterns = self.ISOTYPE_FIELD_PATTERNS.get(isotype, [isotype])
            for pattern in patterns:
                for col in data.columns:
                    if pattern.lower() in col.lower():
                        has_isotype_data = True
                        break
                if has_isotype_data:
                    break
            if has_isotype_data:
                break
        
        if not has_isotype_data:
            return False, "数据中没有找到B细胞同型相关的列"
        
        return True, "数据验证通过"

    def _find_isotype_columns(
        self,
        data: pd.DataFrame,
        suffix: str = ""
    ) -> Dict[str, str]:
        """
        查找同型对应的列名
        
        Args:
            data: 输入的DataFrame
            suffix: 列名后缀（如 "_Expression", "_Unique_CDR3"）
            
        Returns:
            字典格式: {isotype: column_name}
        """
        result = {}
        
        for isotype in self.ISOTYPES:
            patterns = self.ISOTYPE_FIELD_PATTERNS.get(isotype, [isotype])
            
            for pattern in patterns:
                for col in data.columns:
                    col_lower = col.lower()
                    pattern_lower = pattern.lower()
                    
                    # 检查列名是否匹配模式
                    if suffix:
                        suffix_lower = suffix.lower()
                        if pattern_lower in col_lower and suffix_lower in col_lower:
                            result[isotype] = col
                            break
                    else:
                        if pattern_lower in col_lower:
                            result[isotype] = col
                            break
                
                if isotype in result:
                    break
        
        return result
    
    def extract_isotype_data(
        self,
        data: pd.DataFrame,
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        提取每个样本的同型分布数据
        
        Requirements: 1.2
        
        Args:
            data: 输入的DataFrame
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {sample_name: {isotype: {expression: float, unique_cdr3: float}}}
        """
        result = {}
        
        # 确保样本列存在
        if sample_column not in data.columns:
            sample_column = data.columns[0]
        
        # 查找Expression和Unique CDR3列
        expression_cols = self._find_isotype_columns(data, "Expression")
        cdr3_cols = self._find_isotype_columns(data, "CDR3")
        
        # 如果没有找到带后缀的列，尝试直接匹配
        if not expression_cols and not cdr3_cols:
            # 尝试查找直接的同型列
            direct_cols = self._find_isotype_columns(data)
            if direct_cols:
                # 假设这些是Expression数据
                expression_cols = direct_cols
        
        for _, row in data.iterrows():
            sample_name = str(row[sample_column])
            result[sample_name] = {}
            
            for isotype in self.ISOTYPES:
                isotype_data = {"expression": None, "unique_cdr3": None}
                
                # 提取Expression值
                if isotype in expression_cols:
                    col = expression_cols[isotype]
                    value = row[col]
                    if pd.notna(value):
                        try:
                            # 处理百分比格式
                            if isinstance(value, str) and '%' in value:
                                value = float(value.replace('%', '').strip())
                            else:
                                value = float(value)
                            isotype_data["expression"] = value
                        except (ValueError, TypeError):
                            pass
                
                # 提取Unique CDR3值
                if isotype in cdr3_cols:
                    col = cdr3_cols[isotype]
                    value = row[col]
                    if pd.notna(value):
                        try:
                            if isinstance(value, str) and '%' in value:
                                value = float(value.replace('%', '').strip())
                            else:
                                value = float(value)
                            isotype_data["unique_cdr3"] = value
                        except (ValueError, TypeError):
                            pass
                
                result[sample_name][isotype] = isotype_data
        
        return result
    
    def calculate_percentage_diff(
        self,
        data: pd.DataFrame,
        baseline_sample: str,
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
        """
        计算相对于基准样本的百分比差异
        
        Requirements: 1.5
        
        公式: ((sample_value - baseline_value) / baseline_value) * 100
        
        Args:
            data: 输入的DataFrame
            baseline_sample: 基准样本名称
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {sample_name: {isotype: {expression_diff: float, cdr3_diff: float}}}
        """
        # 先提取所有同型数据
        isotype_data = self.extract_isotype_data(data, sample_column)
        
        if baseline_sample not in isotype_data:
            logger.warning(f"Baseline sample '{baseline_sample}' not found")
            return {}
        
        baseline_data = isotype_data[baseline_sample]
        result = {}
        
        for sample_name, sample_data in isotype_data.items():
            result[sample_name] = {}
            
            for isotype in self.ISOTYPES:
                diff_data = {"expression_diff": None, "cdr3_diff": None}
                
                sample_isotype = sample_data.get(isotype, {})
                baseline_isotype = baseline_data.get(isotype, {})
                
                # 计算Expression差异
                sample_expr = sample_isotype.get("expression")
                baseline_expr = baseline_isotype.get("expression")
                
                if sample_expr is not None and baseline_expr is not None and baseline_expr != 0:
                    diff_data["expression_diff"] = round(
                        ((sample_expr - baseline_expr) / baseline_expr) * 100, 2
                    )
                
                # 计算Unique CDR3差异
                sample_cdr3 = sample_isotype.get("unique_cdr3")
                baseline_cdr3 = baseline_isotype.get("unique_cdr3")
                
                if sample_cdr3 is not None and baseline_cdr3 is not None and baseline_cdr3 != 0:
                    diff_data["cdr3_diff"] = round(
                        ((sample_cdr3 - baseline_cdr3) / baseline_cdr3) * 100, 2
                    )
                
                result[sample_name][isotype] = diff_data
        
        return result

    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行B细胞同型分析"""
        try:
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            sample_column = analysis_params.get('sample_column', 'Sample')
            baseline_sample = analysis_params.get('baseline_sample')
            sample_order = analysis_params.get('sample_order')  # Requirements: 11.1, 11.2
            sample_groups = analysis_params.get('sample_groups')  # Requirements: 11.3, 11.4
            
            # 提取同型数据
            isotype_data = self.extract_isotype_data(data, sample_column)
            
            # 获取样本列表
            samples = list(isotype_data.keys())
            
            # 应用自定义样本排序 (Requirements: 11.1, 11.2)
            if sample_order:
                samples = self._apply_sample_order(samples, sample_order)
            
            # 计算百分比差异（如果指定了基准样本）
            percentage_diffs = None
            if baseline_sample:
                percentage_diffs = self.calculate_percentage_diff(
                    data, baseline_sample, sample_column
                )
            
            # 计算分组统计 (Requirements: 11.3, 11.4)
            group_statistics = None
            if sample_groups:
                group_statistics = self._calculate_group_statistics(
                    isotype_data, sample_groups
                )
            
            # 生成数据表格
            table_data = self._generate_table_data(
                isotype_data, samples, percentage_diffs
            )
            
            return {
                "samples": samples,
                "isotypes": self.ISOTYPES,
                "isotype_data": isotype_data,
                "percentage_diffs": percentage_diffs,
                "baseline_sample": baseline_sample,
                "sample_order": sample_order,
                "group_statistics": group_statistics,
                "table_data": table_data,
                "params": analysis_params
            }
            
        except Exception as e:
            logger.error(f"Error in B cell isotype analysis: {e}")
            raise
    
    def _apply_sample_order(
        self,
        samples: List[str],
        sample_order: List[str]
    ) -> List[str]:
        """
        应用自定义样本排序
        
        Requirements: 11.1, 11.2
        
        Args:
            samples: 原始样本列表
            sample_order: 自定义排序列表
            
        Returns:
            排序后的样本列表
        """
        # Create order mapping
        order_map = {name: idx for idx, name in enumerate(sample_order)}
        max_order = len(sample_order)
        
        # Sort samples: those in sample_order first (by their order),
        # then remaining samples in their original order
        def get_order(sample):
            if sample in order_map:
                return (0, order_map[sample])
            else:
                return (1, samples.index(sample) if sample in samples else max_order)
        
        return sorted(samples, key=get_order)
    
    def _calculate_group_statistics(
        self,
        isotype_data: Dict[str, Dict[str, Dict[str, float]]],
        sample_groups: Dict[str, List[str]]
    ) -> Dict[str, Dict[str, Dict[str, Dict[str, float]]]]:
        """
        计算分组统计
        
        Requirements: 11.3, 11.4
        
        Args:
            isotype_data: 同型数据 {sample: {isotype: {expression, unique_cdr3}}}
            sample_groups: 样本分组配置 {group_name: [sample_names]}
            
        Returns:
            字典格式: {group_name: {isotype: {expression: {mean, std}, unique_cdr3: {mean, std}}}}
        """
        result = {}
        
        for group_name, sample_list in sample_groups.items():
            result[group_name] = {}
            
            for isotype in self.ISOTYPES:
                expression_values = []
                cdr3_values = []
                
                for sample in sample_list:
                    if sample in isotype_data:
                        iso_data = isotype_data[sample].get(isotype, {})
                        expr = iso_data.get("expression")
                        cdr3 = iso_data.get("unique_cdr3")
                        
                        if expr is not None:
                            expression_values.append(expr)
                        if cdr3 is not None:
                            cdr3_values.append(cdr3)
                
                result[group_name][isotype] = {
                    "expression": self._calc_stats(expression_values),
                    "unique_cdr3": self._calc_stats(cdr3_values)
                }
        
        return result
    
    def _calc_stats(self, values: List[float]) -> Dict[str, Optional[float]]:
        """计算统计值"""
        if not values:
            return {"mean": None, "std": None, "count": 0}
        
        import numpy as np
        return {
            "mean": round(float(np.mean(values)), 4),
            "std": round(float(np.std(values)), 4) if len(values) > 1 else 0.0,
            "count": len(values)
        }
    
    def _generate_table_data(
        self,
        isotype_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        percentage_diffs: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None
    ) -> Dict[str, Any]:
        """
        生成可复制的数据表格
        
        Requirements: 1.4
        """
        # 构建表头
        headers = ["Sample"]
        for isotype in self.ISOTYPES:
            headers.append(f"{isotype}_Expression")
            headers.append(f"{isotype}_Unique_CDR3")
        
        if percentage_diffs:
            for isotype in self.ISOTYPES:
                headers.append(f"{isotype}_Expr_Diff%")
                headers.append(f"{isotype}_CDR3_Diff%")
        
        # 构建数据行
        rows = []
        for sample in samples:
            row = [sample]
            sample_data = isotype_data.get(sample, {})
            
            # 添加原始值
            for isotype in self.ISOTYPES:
                iso_data = sample_data.get(isotype, {})
                expr = iso_data.get("expression")
                cdr3 = iso_data.get("unique_cdr3")
                row.append(f"{expr:.2f}%" if expr is not None else "")
                row.append(f"{cdr3:.2f}%" if cdr3 is not None else "")
            
            # 添加百分比差异
            if percentage_diffs:
                sample_diffs = percentage_diffs.get(sample, {})
                for isotype in self.ISOTYPES:
                    iso_diff = sample_diffs.get(isotype, {})
                    expr_diff = iso_diff.get("expression_diff")
                    cdr3_diff = iso_diff.get("cdr3_diff")
                    row.append(f"{expr_diff:+.2f}%" if expr_diff is not None else "")
                    row.append(f"{cdr3_diff:+.2f}%" if cdr3_diff is not None else "")
            
            rows.append(row)
        
        return {
            "headers": headers,
            "rows": rows,
            "tab_separated": self._to_tab_separated(headers, rows)
        }
    
    def _to_tab_separated(
        self,
        headers: List[str],
        rows: List[List[Any]]
    ) -> str:
        """
        将表格数据转换为制表符分隔格式
        
        Requirements: 7.2, 7.4
        """
        lines = ["\t".join(str(h) for h in headers)]
        for row in rows:
            lines.append("\t".join(str(v) if v is not None else "" for v in row))
        return "\n".join(lines)
    
    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        figures = {}
        
        try:
            analysis_params = results.get("params", {})
            chart_config = BcellChartConfig.from_dict(
                analysis_params.get("chart_config", {})
            )
            
            isotype_data = results.get("isotype_data", {})
            samples = results.get("samples", [])
            percentage_diffs = results.get("percentage_diffs")
            baseline_sample = results.get("baseline_sample")
            
            if not isotype_data or not samples:
                return figures
            
            # 为每个样本生成水平柱状图
            for sample in samples:
                sample_data = isotype_data.get(sample, {})
                fig = self._create_horizontal_bar_chart(
                    sample, sample_data, chart_config
                )
                if fig:
                    figures[f"isotype_{sample}"] = self._figure_to_base64(
                        fig, dpi=chart_config.dpi
                    )
            
            # 如果有百分比差异，生成差异图
            if percentage_diffs and baseline_sample:
                fig = self._create_percentage_diff_chart(
                    percentage_diffs, samples, baseline_sample, chart_config
                )
                if fig:
                    figures["percentage_diff"] = self._figure_to_base64(
                        fig, dpi=chart_config.dpi
                    )
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
            figures["error"] = f"Visualization error: {str(e)}"
        
        return figures

    def generate_horizontal_bar_chart(
        self,
        data: pd.DataFrame,
        sample_name: str,
        sample_column: str = "Sample",
        chart_config: Optional[BcellChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        生成水平柱状图
        
        Requirements: 1.3
        
        Args:
            data: 输入的DataFrame
            sample_name: 要可视化的样本名称
            sample_column: 样本名称所在的列
            chart_config: 图表配置（可选）
            
        Returns:
            Tuple of (PNG bytes, table_data dict)
        """
        if chart_config is None:
            chart_config = self.chart_config
        
        # 提取数据
        isotype_data = self.extract_isotype_data(data, sample_column)
        
        if sample_name not in isotype_data:
            raise ValueError(f"Sample '{sample_name}' not found in data")
        
        sample_data = isotype_data[sample_name]
        
        # 创建图表
        fig = self._create_horizontal_bar_chart(sample_name, sample_data, chart_config)
        
        # 转换为PNG bytes
        import io
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=chart_config.dpi, bbox_inches='tight')
        buffer.seek(0)
        png_bytes = buffer.getvalue()
        buffer.close()
        plt.close(fig)
        
        # 生成表格数据
        table_data = self._generate_table_data(
            isotype_data, [sample_name], None
        )
        
        return png_bytes, table_data
    
    def _create_horizontal_bar_chart(
        self,
        sample_name: str,
        sample_data: Dict[str, Dict[str, float]],
        chart_config: BcellChartConfig
    ) -> plt.Figure:
        """
        创建单个样本的水平柱状图
        
        Requirements: 1.3
        """
        # 准备数据
        expression_values = []
        cdr3_values = []
        
        for isotype in self.ISOTYPES:
            iso_data = sample_data.get(isotype, {})
            expression_values.append(iso_data.get("expression", 0) or 0)
            cdr3_values.append(iso_data.get("unique_cdr3", 0) or 0)
        
        # 按值排序（降序）
        expr_sorted = sorted(
            zip(self.ISOTYPES, expression_values),
            key=lambda x: x[1],
            reverse=True
        )
        cdr3_sorted = sorted(
            zip(self.ISOTYPES, cdr3_values),
            key=lambda x: x[1],
            reverse=True
        )
        
        expr_isotypes, expr_vals = zip(*expr_sorted) if expr_sorted else ([], [])
        cdr3_isotypes, cdr3_vals = zip(*cdr3_sorted) if cdr3_sorted else ([], [])
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=chart_config.figsize)
        fig.suptitle(
            chart_config.title or f"B Cell Isotype Distribution ({sample_name})",
            fontsize=chart_config.font_size + 6,
            fontweight='bold',
            y=0.95
        )
        
        # Expression % 柱状图
        colors1 = chart_config.expression_colors[:len(expr_isotypes)]
        bars1 = ax1.barh(
            range(len(expr_isotypes)),
            expr_vals,
            color=colors1,
            alpha=0.8
        )
        
        ax1.set_xlabel("Percentage (%)", fontsize=chart_config.font_size + 2, fontweight='bold')
        ax1.set_title("Expression %", fontsize=chart_config.font_size + 4, fontweight='bold', pad=20)
        ax1.set_yticks(range(len(expr_isotypes)))
        ax1.set_yticklabels(expr_isotypes, fontsize=chart_config.font_size)
        ax1.grid(axis='x', alpha=0.3, linestyle='--')
        
        # 添加数值标签
        if chart_config.show_values and expr_vals:
            max_val = max(expr_vals) if expr_vals else 1
            for i, (bar, value) in enumerate(zip(bars1, expr_vals)):
                ax1.text(
                    value + max_val * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    f"{value:.2f}%",
                    ha='left',
                    va='center',
                    fontsize=chart_config.font_size - 1,
                    fontweight='bold'
                )
            ax1.set_xlim(0, max_val * 1.15)
        
        # Unique CDR3 % 柱状图
        colors2 = chart_config.cdr3_colors[:len(cdr3_isotypes)]
        bars2 = ax2.barh(
            range(len(cdr3_isotypes)),
            cdr3_vals,
            color=colors2,
            alpha=0.8
        )
        
        ax2.set_xlabel("Percentage (%)", fontsize=chart_config.font_size + 2, fontweight='bold')
        ax2.set_title("Unique CDR3 %", fontsize=chart_config.font_size + 4, fontweight='bold', pad=20)
        ax2.set_yticks(range(len(cdr3_isotypes)))
        ax2.set_yticklabels(cdr3_isotypes, fontsize=chart_config.font_size)
        ax2.grid(axis='x', alpha=0.3, linestyle='--')
        
        # 添加数值标签
        if chart_config.show_values and cdr3_vals:
            max_val = max(cdr3_vals) if cdr3_vals else 1
            for i, (bar, value) in enumerate(zip(bars2, cdr3_vals)):
                ax2.text(
                    value + max_val * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    f"{value:.2f}%",
                    ha='left',
                    va='center',
                    fontsize=chart_config.font_size - 1,
                    fontweight='bold'
                )
            ax2.set_xlim(0, max_val * 1.15)
        
        # 设置背景色
        ax1.set_facecolor('#f8f9fa')
        ax2.set_facecolor('#f8f9fa')
        
        plt.tight_layout()
        plt.subplots_adjust(top=0.88)
        
        return fig

    def _create_percentage_diff_chart(
        self,
        percentage_diffs: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        baseline_sample: str,
        chart_config: BcellChartConfig
    ) -> plt.Figure:
        """
        创建百分比差异图
        
        Requirements: 1.5
        """
        # 创建2x3子图布局（6种同型）
        fig, axes = plt.subplots(2, 3, figsize=(24, 16))
        fig.suptitle(
            f"B Cell Isotype - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
            fontsize=20,
            fontweight='bold',
            y=0.98
        )
        
        axes = axes.flatten()
        
        # 定义颜色
        colors = {
            "IgM": "#1f77b4",
            "IgD": "#ff7f0e",
            "IgA1/2": "#2ca02c",
            "IgG1/2": "#d62728",
            "IgG3/4": "#9467bd",
            "IgE": "#8c564b"
        }
        
        x_pos = np.arange(len(samples))
        bar_width = 0.6
        
        # 找到基准样本的索引
        baseline_index = samples.index(baseline_sample) if baseline_sample in samples else -1
        
        for idx, (isotype, ax) in enumerate(zip(self.ISOTYPES, axes)):
            # 获取CDR3差异值
            values = []
            for sample in samples:
                sample_diffs = percentage_diffs.get(sample, {})
                iso_diff = sample_diffs.get(isotype, {})
                cdr3_diff = iso_diff.get("cdr3_diff", 0)
                values.append(cdr3_diff if cdr3_diff is not None else 0)
            
            values = np.array(values)
            
            # 创建柱状图
            bars = ax.bar(x_pos, values, bar_width, color=colors.get(isotype, "#333333"), alpha=0.8)
            
            # 高亮基准样本
            if baseline_index >= 0:
                bars[baseline_index].set_edgecolor('black')
                bars[baseline_index].set_linewidth(2)
                bars[baseline_index].set_alpha(1.0)
            
            # 添加零线
            ax.axhline(y=0, color='gray', linestyle='-', linewidth=2, alpha=0.8, label='Baseline (0%)')
            
            # 添加数值标签
            if chart_config.show_values:
                max_abs = max(abs(values)) if len(values) > 0 else 1
                for j, bar in enumerate(bars):
                    height = bar.get_height()
                    if j == baseline_index:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height + max_abs * 0.02,
                            "Baseline",
                            ha='center',
                            va='bottom',
                            fontsize=9,
                            fontweight='bold',
                            color='red'
                        )
                    elif height > 0:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height + max_abs * 0.02,
                            f"+{height:.1f}%",
                            ha='center',
                            va='bottom',
                            fontsize=8,
                            fontweight='bold'
                        )
                    elif height < 0:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            height - max_abs * 0.02,
                            f"{height:.1f}%",
                            ha='center',
                            va='top',
                            fontsize=8,
                            fontweight='bold'
                        )
            
            # 设置标签
            ax.set_xticks(x_pos)
            ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=11)
            ax.set_ylabel("Percentage Change from Baseline (%)", fontsize=14, fontweight='bold')
            ax.set_xlabel("Sample", fontsize=14, fontweight='bold')
            ax.set_title(f"{isotype} Unique CDR3", fontsize=16, fontweight='bold', pad=20)
            ax.legend(fontsize=10, frameon=True, fancybox=True, shadow=True)
            ax.grid(axis='y', alpha=0.3, linestyle='--')
            
            # 设置y轴范围
            if len(values) > 0:
                ymin = min(values) * 1.1 if min(values) < 0 else -5
                ymax = max(values) * 1.1 if max(values) > 0 else 5
                ax.set_ylim(ymin, ymax)
            
            ax.set_facecolor('#f8f9fa')
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        
        return fig
    
    def get_data_table(
        self,
        data: pd.DataFrame,
        sample_column: str = "Sample",
        baseline_sample: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取可复制的数据表格
        
        Requirements: 1.4
        
        Args:
            data: 输入的DataFrame
            sample_column: 样本名称所在的列
            baseline_sample: 基准样本（可选，用于计算百分比差异）
            
        Returns:
            包含headers, rows, tab_separated的字典
        """
        # 提取数据
        isotype_data = self.extract_isotype_data(data, sample_column)
        samples = list(isotype_data.keys())
        
        # 计算百分比差异
        percentage_diffs = None
        if baseline_sample:
            percentage_diffs = self.calculate_percentage_diff(
                data, baseline_sample, sample_column
            )
        
        return self._generate_table_data(isotype_data, samples, percentage_diffs)
