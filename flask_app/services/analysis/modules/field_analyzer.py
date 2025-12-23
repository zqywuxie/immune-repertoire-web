"""
Field Analyzer Module - Generic Field Data Analysis
通用字段数据分析模块 - 识别字段、提取数据、计算百分比差异、生成可视化

Requirements: 5.1, 5.3, 5.4, 5.5, 5.6
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any, List, Tuple, Optional
import logging

from ..base_module import AnalysisModule, AnalysisResult
from ..registry import register_module

logger = logging.getLogger(__name__)


class ChartConfig:
    """图表配置类"""
    
    def __init__(
        self,
        title: str = "",
        figsize: Tuple[int, int] = (12, 8),
        dpi: int = 300,
        color_scheme: str = "viridis",
        bar_width: float = 0.8,
        font_size: int = 12,
        show_values: bool = True
    ):
        self.title = title
        self.figsize = figsize
        self.dpi = dpi
        self.color_scheme = color_scheme
        self.bar_width = bar_width
        self.font_size = font_size
        self.show_values = show_values
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ChartConfig':
        """从字典创建配置"""
        return cls(
            title=config_dict.get('title', ''),
            figsize=tuple(config_dict.get('figsize', (12, 8))),
            dpi=config_dict.get('dpi', 300),
            color_scheme=config_dict.get('color_scheme', 'viridis'),
            bar_width=config_dict.get('bar_width', 0.8),
            font_size=config_dict.get('font_size', 12),
            show_values=config_dict.get('show_values', True)
        )


@register_module
class FieldAnalyzerModule(AnalysisModule):
    """
    通用字段数据分析模块
    
    功能:
    - 识别数据文件中的所有数值字段
    - 提取指定字段的数据
    - 计算相对于基准样本的百分比差异
    - 生成可视化图表（柱状图、折线图等）
    - 生成可复制的数据表格
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.chart_config = ChartConfig()
        if config and 'chart_config' in config:
            self.chart_config = ChartConfig.from_dict(config['chart_config'])
    
    def get_name(self) -> str:
        return "field_analyzer"
    
    def get_description(self) -> str:
        return "通用字段数据分析 - 识别数值字段、提取数据、计算百分比差异"
    
    def get_category(self) -> str:
        return "field_analysis"
    
    def get_required_columns(self) -> List[str]:
        # 字段分析器不需要特定列，只需要有样本列和至少一个数值列
        return []
    
    def get_optional_columns(self) -> List[str]:
        return []
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "sample_column": "Sample",
            "fields": [],  # 要分析的字段列表
            "selected_samples": [],  # 选中的样本列表 (Requirements: 21.3, 21.5)
            "baseline_sample": None,  # 基准样本
            "sample_order": None,  # 自定义样本排序 (Requirements: 11.1, 11.2)
            "sample_groups": None,  # 样本分组配置 (Requirements: 11.3, 11.4)
            "plot_type": "bar",  # bar, line, grouped_bar
            "show_percentage_diff": False,
            "chart_config": {
                "title": "",
                "figsize": (12, 8),
                "dpi": 300,
                "color_scheme": "viridis",
                "bar_width": 0.8,
                "font_size": 12,
                "show_values": True
            }
        }
    
    def validate_data(self, data: pd.DataFrame) -> Tuple[bool, str]:
        """验证输入数据"""
        if data.empty:
            return False, "数据为空"
        
        # 检查是否有数值列
        numeric_cols = self.identify_numeric_fields(data)
        if not numeric_cols:
            return False, "数据中没有数值类型的列"
        
        return True, "数据验证通过"
    
    def identify_numeric_fields(self, data: pd.DataFrame) -> List[str]:
        """
        识别数据中的所有数值类型字段
        
        Requirements: 5.1
        
        Args:
            data: 输入的DataFrame
            
        Returns:
            数值类型列名列表
        """
        numeric_fields = []
        
        for col in data.columns:
            # 检查列是否为数值类型
            if pd.api.types.is_numeric_dtype(data[col]):
                numeric_fields.append(col)
            else:
                # 尝试转换为数值类型
                try:
                    converted = pd.to_numeric(data[col], errors='coerce')
                    # 如果超过50%的值可以转换为数值，则认为是数值列
                    if converted.notna().sum() / len(converted) > 0.5:
                        numeric_fields.append(col)
                except (ValueError, TypeError):
                    continue
        
        return numeric_fields
    
    def extract_field_data(
        self,
        data: pd.DataFrame,
        fields: List[str],
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, float]]:
        """
        提取指定字段的数据
        
        Requirements: 5.3
        
        Args:
            data: 输入的DataFrame
            fields: 要提取的字段列表
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {sample_name: {field_name: value}}
        """
        result = {}
        
        # 确保样本列存在
        if sample_column not in data.columns:
            # 尝试使用第一列作为样本列
            sample_column = data.columns[0]
        
        for _, row in data.iterrows():
            sample_name = str(row[sample_column])
            result[sample_name] = {}
            
            for field in fields:
                if field in data.columns:
                    value = row[field]
                    # 转换为数值
                    if pd.notna(value):
                        try:
                            result[sample_name][field] = float(value)
                        except (ValueError, TypeError):
                            result[sample_name][field] = None
                    else:
                        result[sample_name][field] = None
        
        return result
    
    def calculate_percentage_diff(
        self,
        data: pd.DataFrame,
        field: str,
        baseline_sample: str,
        sample_column: str = "Sample"
    ) -> Dict[str, Optional[float]]:
        """
        计算指定字段相对于基准样本的百分比差异
        
        Requirements: 5.6
        
        公式: ((sample_value - baseline_value) / baseline_value) * 100
        
        Args:
            data: 输入的DataFrame
            field: 要计算的字段名
            baseline_sample: 基准样本名称
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {sample_name: percentage_diff}
        """
        result = {}
        
        # 确保样本列存在
        if sample_column not in data.columns:
            sample_column = data.columns[0]
        
        # 获取基准值
        baseline_row = data[data[sample_column] == baseline_sample]
        if baseline_row.empty:
            logger.warning(f"Baseline sample '{baseline_sample}' not found")
            return result
        
        baseline_value = baseline_row[field].iloc[0]
        
        # 检查基准值是否有效
        if pd.isna(baseline_value) or baseline_value == 0:
            logger.warning(f"Baseline value for field '{field}' is invalid (NA or 0)")
            return result
        
        baseline_value = float(baseline_value)
        
        # 计算每个样本的百分比差异
        for _, row in data.iterrows():
            sample_name = str(row[sample_column])
            value = row[field]
            
            if pd.notna(value):
                try:
                    sample_value = float(value)
                    pct_diff = ((sample_value - baseline_value) / baseline_value) * 100
                    result[sample_name] = round(pct_diff, 2)
                except (ValueError, TypeError, ZeroDivisionError):
                    result[sample_name] = None
            else:
                result[sample_name] = None
        
        return result
    
    def calculate_all_percentage_diffs(
        self,
        data: pd.DataFrame,
        fields: List[str],
        baseline_sample: str,
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, Optional[float]]]:
        """
        计算所有字段相对于基准样本的百分比差异
        
        Args:
            data: 输入的DataFrame
            fields: 要计算的字段列表
            baseline_sample: 基准样本名称
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {sample_name: {field_name: percentage_diff}}
        """
        result = {}
        
        for field in fields:
            field_diffs = self.calculate_percentage_diff(
                data, field, baseline_sample, sample_column
            )
            
            for sample_name, pct_diff in field_diffs.items():
                if sample_name not in result:
                    result[sample_name] = {}
                result[sample_name][field] = pct_diff
        
        return result
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行字段数据分析"""
        try:
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            sample_column = analysis_params.get('sample_column', 'Sample')
            fields = analysis_params.get('fields', [])
            selected_samples = analysis_params.get('selected_samples', [])  # Requirements: 21.3, 21.5
            baseline_sample = analysis_params.get('baseline_sample')
            sample_order = analysis_params.get('sample_order')  # Requirements: 11.1, 11.2
            sample_groups = analysis_params.get('sample_groups')  # Requirements: 11.3, 11.4
            
            # Filter data by selected samples if provided (Requirements: 21.3, 21.5)
            if selected_samples and len(selected_samples) > 0:
                if sample_column in data.columns:
                    data = data[data[sample_column].isin(selected_samples)].copy()
                    logger.info(f"Filtered data to {len(selected_samples)} selected samples")
            
            # 如果没有指定字段，使用所有数值字段
            if not fields:
                fields = self.identify_numeric_fields(data)
                # 排除样本列
                fields = [f for f in fields if f != sample_column]
            
            # 提取字段数据
            field_data = self.extract_field_data(data, fields, sample_column)
            
            # 获取样本列表
            samples = data[sample_column].tolist() if sample_column in data.columns else []
            
            # 应用自定义样本排序 (Requirements: 11.1, 11.2)
            if sample_order:
                samples = self._apply_sample_order(samples, sample_order)
            
            # 计算百分比差异（如果指定了基准样本）
            percentage_diffs = None
            if baseline_sample:
                percentage_diffs = self.calculate_all_percentage_diffs(
                    data, fields, baseline_sample, sample_column
                )
            
            # 计算分组统计 (Requirements: 11.3, 11.4)
            group_statistics = None
            if sample_groups:
                group_statistics = self._calculate_group_statistics(
                    data, sample_groups, fields, sample_column
                )
            
            # 生成数据表格
            table_data = self._generate_table_data(
                field_data, fields, samples, percentage_diffs
            )
            
            return {
                "samples": samples,
                "fields": fields,
                "field_data": field_data,
                "percentage_diffs": percentage_diffs,
                "baseline_sample": baseline_sample,
                "sample_order": sample_order,
                "group_statistics": group_statistics,
                "table_data": table_data,
                "params": analysis_params
            }
            
        except Exception as e:
            logger.error(f"Error in field analysis: {e}")
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
        data: pd.DataFrame,
        sample_groups: Dict[str, List[str]],
        fields: List[str],
        sample_column: str
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        计算分组统计
        
        Requirements: 11.3, 11.4
        
        Args:
            data: 输入的DataFrame
            sample_groups: 样本分组配置 {group_name: [sample_names]}
            fields: 要计算统计的字段列表
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {group_name: {field_name: {mean, std, min, max, median, count}}}
        """
        result = {}
        
        for group_name, sample_list in sample_groups.items():
            result[group_name] = {}
            
            # Filter data for this group
            group_data = data[data[sample_column].isin(sample_list)]
            
            for field in fields:
                if field not in data.columns:
                    continue
                
                values = pd.to_numeric(group_data[field], errors='coerce')
                valid_values = values.dropna()
                
                if len(valid_values) == 0:
                    result[group_name][field] = {
                        'mean': None,
                        'std': None,
                        'min': None,
                        'max': None,
                        'median': None,
                        'count': 0
                    }
                else:
                    result[group_name][field] = {
                        'mean': round(float(valid_values.mean()), 4),
                        'std': round(float(valid_values.std()), 4) if len(valid_values) > 1 else 0.0,
                        'min': round(float(valid_values.min()), 4),
                        'max': round(float(valid_values.max()), 4),
                        'median': round(float(valid_values.median()), 4),
                        'count': len(valid_values)
                    }
        
        return result
    
    def _generate_table_data(
        self,
        field_data: Dict[str, Dict[str, float]],
        fields: List[str],
        samples: List[str],
        percentage_diffs: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Dict[str, Any]:
        """
        生成可复制的数据表格
        
        Requirements: 5.5
        """
        # 构建表头
        headers = ["Sample"] + fields
        if percentage_diffs:
            headers += [f"{f}_Diff%" for f in fields]
        
        # 构建数据行
        rows = []
        for sample in samples:
            row = [sample]
            
            # 添加原始值
            for field in fields:
                value = field_data.get(sample, {}).get(field)
                row.append(value if value is not None else "")
            
            # 添加百分比差异
            if percentage_diffs:
                for field in fields:
                    diff = percentage_diffs.get(sample, {}).get(field)
                    row.append(diff if diff is not None else "")
            
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
            plot_type = analysis_params.get("plot_type", "bar")
            chart_config = ChartConfig.from_dict(
                analysis_params.get("chart_config", {})
            )
            
            field_data = results.get("field_data", {})
            fields = results.get("fields", [])
            samples = results.get("samples", [])
            percentage_diffs = results.get("percentage_diffs")
            baseline_sample = results.get("baseline_sample")
            
            if not field_data or not fields:
                return figures
            
            # 根据plot_type生成不同的图表
            if plot_type == "bar":
                figures.update(self._create_bar_chart(
                    field_data, fields, samples, chart_config
                ))
            elif plot_type == "line":
                figures.update(self._create_line_chart(
                    field_data, fields, samples, chart_config
                ))
            elif plot_type == "grouped_bar":
                figures.update(self._create_grouped_bar_chart(
                    field_data, fields, samples, chart_config
                ))
            
            # 如果有百分比差异，生成差异图
            if percentage_diffs and baseline_sample:
                figures.update(self._create_percentage_diff_chart(
                    percentage_diffs, fields, samples, baseline_sample, chart_config
                ))
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
            figures["error"] = f"Visualization error: {str(e)}"
        
        return figures
    
    def generate_visualization(
        self,
        data: pd.DataFrame,
        fields: List[str],
        sample_column: str = "Sample",
        baseline_sample: Optional[str] = None,
        chart_config: Optional[ChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        生成可视化图表
        
        Requirements: 5.4
        
        Args:
            data: 输入的DataFrame
            fields: 要可视化的字段列表
            sample_column: 样本名称所在的列
            baseline_sample: 基准样本（可选）
            chart_config: 图表配置（可选）
            
        Returns:
            Tuple of (PNG bytes, table_data dict)
        """
        if chart_config is None:
            chart_config = self.chart_config
        
        # 提取数据
        field_data = self.extract_field_data(data, fields, sample_column)
        samples = data[sample_column].tolist() if sample_column in data.columns else list(field_data.keys())
        
        # 计算百分比差异
        percentage_diffs = None
        if baseline_sample:
            percentage_diffs = self.calculate_all_percentage_diffs(
                data, fields, baseline_sample, sample_column
            )
        
        # 创建图表
        fig, ax = plt.subplots(figsize=chart_config.figsize)
        
        # 准备数据
        x = np.arange(len(samples))
        width = chart_config.bar_width / len(fields) if len(fields) > 1 else chart_config.bar_width
        
        # 获取颜色
        colors = plt.cm.get_cmap(chart_config.color_scheme)(
            np.linspace(0, 1, len(fields))
        )
        
        # 绘制柱状图
        for i, field in enumerate(fields):
            values = [field_data.get(s, {}).get(field, 0) or 0 for s in samples]
            offset = (i - len(fields) / 2 + 0.5) * width
            bars = ax.bar(x + offset, values, width, label=field, color=colors[i], alpha=0.8)
            
            # 显示数值
            if chart_config.show_values:
                for bar, val in zip(bars, values):
                    if val != 0:
                        ax.annotate(
                            f'{val:.2f}',
                            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                            xytext=(0, 3),
                            textcoords="offset points",
                            ha='center', va='bottom',
                            fontsize=chart_config.font_size - 2
                        )
        
        # 设置标签
        ax.set_xlabel('Sample', fontsize=chart_config.font_size)
        ax.set_ylabel('Value', fontsize=chart_config.font_size)
        ax.set_title(
            chart_config.title or 'Field Data Analysis',
            fontsize=chart_config.font_size + 2,
            fontweight='bold'
        )
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=45, ha='right')
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
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
            field_data, fields, samples, percentage_diffs
        )
        
        return png_bytes, table_data
    
    def get_data_table(
        self,
        data: pd.DataFrame,
        fields: List[str],
        sample_column: str = "Sample",
        baseline_sample: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取可复制的数据表格
        
        Requirements: 5.5
        
        Args:
            data: 输入的DataFrame
            fields: 要包含的字段列表
            sample_column: 样本名称所在的列
            baseline_sample: 基准样本（可选，用于计算百分比差异）
            
        Returns:
            包含headers, rows, tab_separated的字典
        """
        # 提取数据
        field_data = self.extract_field_data(data, fields, sample_column)
        samples = data[sample_column].tolist() if sample_column in data.columns else list(field_data.keys())
        
        # 计算百分比差异
        percentage_diffs = None
        if baseline_sample:
            percentage_diffs = self.calculate_all_percentage_diffs(
                data, fields, baseline_sample, sample_column
            )
        
        return self._generate_table_data(field_data, fields, samples, percentage_diffs)
    
    def _create_bar_chart(
        self,
        field_data: Dict[str, Dict[str, float]],
        fields: List[str],
        samples: List[str],
        chart_config: ChartConfig
    ) -> Dict[str, str]:
        """创建柱状图"""
        figures = {}
        
        for field in fields:
            fig, ax = plt.subplots(figsize=chart_config.figsize)
            
            values = [field_data.get(s, {}).get(field, 0) or 0 for s in samples]
            colors = plt.cm.get_cmap(chart_config.color_scheme)(
                np.linspace(0.2, 0.8, len(samples))
            )
            
            bars = ax.bar(samples, values, color=colors, alpha=0.8, width=chart_config.bar_width)
            
            if chart_config.show_values:
                for bar, val in zip(bars, values):
                    if val != 0:
                        ax.annotate(
                            f'{val:.2f}',
                            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                            xytext=(0, 3),
                            textcoords="offset points",
                            ha='center', va='bottom',
                            fontsize=chart_config.font_size - 2
                        )
            
            ax.set_xlabel('Sample', fontsize=chart_config.font_size)
            ax.set_ylabel(field, fontsize=chart_config.font_size)
            ax.set_title(
                chart_config.title or f'{field} by Sample',
                fontsize=chart_config.font_size + 2,
                fontweight='bold'
            )
            ax.tick_params(axis='x', rotation=45)
            ax.grid(True, alpha=0.3, axis='y')
            
            plt.tight_layout()
            figures[f"bar_{field}"] = self._figure_to_base64(fig, dpi=chart_config.dpi)
        
        return figures
    
    def _create_line_chart(
        self,
        field_data: Dict[str, Dict[str, float]],
        fields: List[str],
        samples: List[str],
        chart_config: ChartConfig
    ) -> Dict[str, str]:
        """创建折线图"""
        figures = {}
        
        fig, ax = plt.subplots(figsize=chart_config.figsize)
        
        colors = plt.cm.get_cmap(chart_config.color_scheme)(
            np.linspace(0, 1, len(fields))
        )
        
        for i, field in enumerate(fields):
            values = [field_data.get(s, {}).get(field, 0) or 0 for s in samples]
            ax.plot(samples, values, 'o-', label=field, color=colors[i], linewidth=2, markersize=8)
        
        ax.set_xlabel('Sample', fontsize=chart_config.font_size)
        ax.set_ylabel('Value', fontsize=chart_config.font_size)
        ax.set_title(
            chart_config.title or 'Field Data Trend',
            fontsize=chart_config.font_size + 2,
            fontweight='bold'
        )
        ax.tick_params(axis='x', rotation=45)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        figures["line_chart"] = self._figure_to_base64(fig, dpi=chart_config.dpi)
        
        return figures
    
    def _create_grouped_bar_chart(
        self,
        field_data: Dict[str, Dict[str, float]],
        fields: List[str],
        samples: List[str],
        chart_config: ChartConfig
    ) -> Dict[str, str]:
        """创建分组柱状图"""
        figures = {}
        
        fig, ax = plt.subplots(figsize=chart_config.figsize)
        
        x = np.arange(len(samples))
        width = chart_config.bar_width / len(fields)
        
        colors = plt.cm.get_cmap(chart_config.color_scheme)(
            np.linspace(0, 1, len(fields))
        )
        
        for i, field in enumerate(fields):
            values = [field_data.get(s, {}).get(field, 0) or 0 for s in samples]
            offset = (i - len(fields) / 2 + 0.5) * width
            bars = ax.bar(x + offset, values, width, label=field, color=colors[i], alpha=0.8)
            
            if chart_config.show_values:
                for bar, val in zip(bars, values):
                    if val != 0:
                        ax.annotate(
                            f'{val:.1f}',
                            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                            xytext=(0, 3),
                            textcoords="offset points",
                            ha='center', va='bottom',
                            fontsize=max(6, chart_config.font_size - 4)
                        )
        
        ax.set_xlabel('Sample', fontsize=chart_config.font_size)
        ax.set_ylabel('Value', fontsize=chart_config.font_size)
        ax.set_title(
            chart_config.title or 'Field Comparison',
            fontsize=chart_config.font_size + 2,
            fontweight='bold'
        )
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=45, ha='right')
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        figures["grouped_bar"] = self._figure_to_base64(fig, dpi=chart_config.dpi)
        
        return figures
    
    def _create_percentage_diff_chart(
        self,
        percentage_diffs: Dict[str, Dict[str, float]],
        fields: List[str],
        samples: List[str],
        baseline_sample: str,
        chart_config: ChartConfig
    ) -> Dict[str, str]:
        """创建百分比差异图"""
        figures = {}
        
        fig, ax = plt.subplots(figsize=chart_config.figsize)
        
        x = np.arange(len(samples))
        width = chart_config.bar_width / len(fields)
        
        colors = plt.cm.get_cmap(chart_config.color_scheme)(
            np.linspace(0, 1, len(fields))
        )
        
        for i, field in enumerate(fields):
            values = [percentage_diffs.get(s, {}).get(field, 0) or 0 for s in samples]
            offset = (i - len(fields) / 2 + 0.5) * width
            bars = ax.bar(x + offset, values, width, label=field, color=colors[i], alpha=0.8)
        
        # 添加零线
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        ax.set_xlabel('Sample', fontsize=chart_config.font_size)
        ax.set_ylabel('Percentage Difference (%)', fontsize=chart_config.font_size)
        ax.set_title(
            f'Percentage Difference from Baseline ({baseline_sample})',
            fontsize=chart_config.font_size + 2,
            fontweight='bold'
        )
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=45, ha='right')
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        figures["percentage_diff"] = self._figure_to_base64(fig, dpi=chart_config.dpi)
        
        return figures
