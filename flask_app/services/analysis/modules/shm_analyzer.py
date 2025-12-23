"""
SHM Analyzer Module - 体细胞超突变分析器
分析SHM0和SHM1数据，计算百分比变化，生成分组柱状图

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any, List, Tuple, Optional
import logging
import io
import base64

from ..base_module import AnalysisModule
from ..registry import register_module

logger = logging.getLogger(__name__)


class SHMChartConfig:
    """SHM分析图表配置类"""
    
    def __init__(
        self,
        title: str = "",
        figsize: Tuple[int, int] = (16, 10),
        dpi: int = 300,
        shm0_color: str = "#2E86AB",
        shm1_color: str = "#A23B72",
        font_size: int = 12,
        show_values: bool = True,
        bar_width: float = 0.35
    ):
        self.title = title
        self.figsize = figsize
        self.dpi = dpi
        self.shm0_color = shm0_color
        self.shm1_color = shm1_color
        self.font_size = font_size
        self.show_values = show_values
        self.bar_width = bar_width
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'SHMChartConfig':
        """从字典创建配置"""
        return cls(
            title=config_dict.get('title', ''),
            figsize=tuple(config_dict.get('figsize', (16, 10))),
            dpi=config_dict.get('dpi', 300),
            shm0_color=config_dict.get('shm0_color', '#2E86AB'),
            shm1_color=config_dict.get('shm1_color', '#A23B72'),
            font_size=config_dict.get('font_size', 12),
            show_values=config_dict.get('show_values', True),
            bar_width=config_dict.get('bar_width', 0.35)
        )


@register_module
class SHMAnalyzer(AnalysisModule):
    """
    SHM体细胞超突变分析器
    
    功能:
    - 验证数据是否包含所需的SHM字段
    - 计算相对于基准样本的百分比变化
    - 生成分组柱状图（SHM0和SHM1对比）
    - 生成可复制的数据表格
    
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
    """
    
    # SHM字段定义 (shm0_field, shm1_field, display_label)
    SHM_FIELDS = [
        ("IGHA_SHM0", "IGHA_SHM1", "IgA"),
        ("IGHG12_SHM0", "IGHG12_SHM1", "IgG1/2"),
        ("IGHG34_SHM0", "IGHG34_SHM1", "IgG3/4"),
        ("IGHM_IGHD_SHM0", "IGHM_IGHD_SHM1", "IgM/IgD"),
        ("IGH_SHM0", "IGH_SHM1", "IGH"),
    ]
    
    # 所有必需的SHM列名
    REQUIRED_SHM_COLUMNS = [
        "IGHA_SHM0", "IGHA_SHM1",
        "IGHG12_SHM0", "IGHG12_SHM1",
        "IGHG34_SHM0", "IGHG34_SHM1",
        "IGHM_IGHD_SHM0", "IGHM_IGHD_SHM1",
        "IGH_SHM0", "IGH_SHM1"
    ]
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.chart_config = SHMChartConfig()
        if config and 'chart_config' in config:
            self.chart_config = SHMChartConfig.from_dict(config['chart_config'])
    
    def get_name(self) -> str:
        return "shm_analyzer"
    
    def get_description(self) -> str:
        return "SHM体细胞超突变分析 - 分析SHM0和SHM1数据，计算百分比变化"
    
    def get_category(self) -> str:
        return "mutation_analysis"
    
    def get_required_columns(self) -> List[str]:
        return ["Sample"]
    
    def get_optional_columns(self) -> List[str]:
        return self.REQUIRED_SHM_COLUMNS + ["Group", "Timepoint", "Condition"]
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "sample_column": "Sample",
            "baseline_sample": None,
            "isotypes": None,  # None means all isotypes
            "sample_order": None,  # 自定义样本排序 (Requirements: 11.1, 11.2)
            "sample_groups": None,  # 样本分组配置 (Requirements: 11.3, 11.4)
            "chart_config": {
                "title": "",
                "figsize": (16, 10),
                "dpi": 300,
                "font_size": 12,
                "show_values": True,
                "bar_width": 0.35
            }
        }
    
    def validate_shm_fields(self, data: pd.DataFrame) -> Tuple[bool, List[str], List[str]]:
        """
        验证数据是否包含所需的SHM字段
        
        Requirements: 2.1
        
        Args:
            data: 输入的DataFrame
            
        Returns:
            Tuple of (is_valid, present_fields, missing_fields)
        """
        present_fields = []
        missing_fields = []
        
        for col in self.REQUIRED_SHM_COLUMNS:
            # 支持大小写不敏感匹配
            found = False
            for data_col in data.columns:
                if data_col.upper() == col.upper():
                    present_fields.append(data_col)
                    found = True
                    break
            if not found:
                missing_fields.append(col)
        
        is_valid = len(missing_fields) == 0
        return is_valid, present_fields, missing_fields
    
    def validate_data(self, data: pd.DataFrame) -> Tuple[bool, str]:
        """验证输入数据"""
        if data.empty:
            return False, "数据为空"
        
        is_valid, present_fields, missing_fields = self.validate_shm_fields(data)
        
        if not is_valid:
            return False, f"缺少必需的SHM字段: {', '.join(missing_fields)}"
        
        return True, "数据验证通过"

    def _find_column(self, data: pd.DataFrame, target_col: str) -> Optional[str]:
        """
        查找匹配的列名（大小写不敏感）
        
        Args:
            data: DataFrame
            target_col: 目标列名
            
        Returns:
            实际的列名，如果未找到则返回None
        """
        for col in data.columns:
            if col.upper() == target_col.upper():
                return col
        return None
    
    def extract_shm_data(
        self,
        data: pd.DataFrame,
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        提取每个样本的SHM数据
        
        Args:
            data: 输入的DataFrame
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {sample_name: {isotype_label: {shm0: float, shm1: float}}}
        """
        result = {}
        
        # 确保样本列存在
        actual_sample_col = self._find_column(data, sample_column)
        if not actual_sample_col:
            actual_sample_col = data.columns[0]
        
        for _, row in data.iterrows():
            sample_name = str(row[actual_sample_col])
            result[sample_name] = {}
            
            for shm0_col, shm1_col, label in self.SHM_FIELDS:
                actual_shm0_col = self._find_column(data, shm0_col)
                actual_shm1_col = self._find_column(data, shm1_col)
                
                shm_data = {"shm0": None, "shm1": None}
                
                if actual_shm0_col:
                    value = row[actual_shm0_col]
                    if pd.notna(value):
                        try:
                            shm_data["shm0"] = float(value)
                        except (ValueError, TypeError):
                            pass
                
                if actual_shm1_col:
                    value = row[actual_shm1_col]
                    if pd.notna(value):
                        try:
                            shm_data["shm1"] = float(value)
                        except (ValueError, TypeError):
                            pass
                
                result[sample_name][label] = shm_data
        
        return result
    
    def calculate_percentage_changes(
        self,
        data: pd.DataFrame,
        baseline_sample: str,
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
        """
        计算相对于基准样本的百分比变化
        
        Requirements: 2.2
        
        公式: ((sample_value - baseline_value) / baseline_value) * 100
        
        Args:
            data: 输入的DataFrame
            baseline_sample: 基准样本名称
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {sample_name: {isotype_label: {shm0_pct_change: float, shm1_pct_change: float}}}
        """
        # 先提取所有SHM数据
        shm_data = self.extract_shm_data(data, sample_column)
        
        if baseline_sample not in shm_data:
            logger.warning(f"Baseline sample '{baseline_sample}' not found")
            return {}
        
        baseline_data = shm_data[baseline_sample]
        result = {}
        
        for sample_name, sample_data in shm_data.items():
            result[sample_name] = {}
            
            for shm0_col, shm1_col, label in self.SHM_FIELDS:
                pct_change_data = {"shm0_pct_change": None, "shm1_pct_change": None}
                
                sample_isotype = sample_data.get(label, {})
                baseline_isotype = baseline_data.get(label, {})
                
                # 计算SHM0百分比变化
                sample_shm0 = sample_isotype.get("shm0")
                baseline_shm0 = baseline_isotype.get("shm0")
                
                if sample_shm0 is not None and baseline_shm0 is not None and baseline_shm0 != 0:
                    pct_change_data["shm0_pct_change"] = round(
                        ((sample_shm0 - baseline_shm0) / baseline_shm0) * 100, 2
                    )
                
                # 计算SHM1百分比变化
                sample_shm1 = sample_isotype.get("shm1")
                baseline_shm1 = baseline_isotype.get("shm1")
                
                if sample_shm1 is not None and baseline_shm1 is not None and baseline_shm1 != 0:
                    pct_change_data["shm1_pct_change"] = round(
                        ((sample_shm1 - baseline_shm1) / baseline_shm1) * 100, 2
                    )
                
                result[sample_name][label] = pct_change_data
        
        return result
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行SHM分析"""
        try:
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            sample_column = analysis_params.get('sample_column', 'Sample')
            baseline_sample = analysis_params.get('baseline_sample')
            sample_order = analysis_params.get('sample_order')  # Requirements: 11.1, 11.2
            sample_groups = analysis_params.get('sample_groups')  # Requirements: 11.3, 11.4
            
            # 提取SHM数据
            shm_data = self.extract_shm_data(data, sample_column)
            
            # 获取样本列表
            samples = list(shm_data.keys())
            
            # 应用自定义样本排序 (Requirements: 11.1, 11.2)
            if sample_order:
                samples = self._apply_sample_order(samples, sample_order)
            
            # 计算百分比变化（如果指定了基准样本）
            percentage_changes = None
            if baseline_sample:
                percentage_changes = self.calculate_percentage_changes(
                    data, baseline_sample, sample_column
                )
            
            # 计算分组统计 (Requirements: 11.3, 11.4)
            group_statistics = None
            if sample_groups:
                group_statistics = self._calculate_group_statistics(
                    shm_data, sample_groups
                )
            
            # 获取同型标签列表
            isotype_labels = [label for _, _, label in self.SHM_FIELDS]
            
            # 生成数据表格
            table_data = self._generate_table_data(
                shm_data, samples, percentage_changes
            )
            
            return {
                "samples": samples,
                "isotype_labels": isotype_labels,
                "shm_data": shm_data,
                "percentage_changes": percentage_changes,
                "baseline_sample": baseline_sample,
                "sample_order": sample_order,
                "group_statistics": group_statistics,
                "table_data": table_data,
                "params": analysis_params
            }
            
        except Exception as e:
            logger.error(f"Error in SHM analysis: {e}")
            raise
    
    def _apply_sample_order(
        self,
        samples: List[str],
        sample_order: List[str]
    ) -> List[str]:
        """
        应用自定义样本排序
        
        Requirements: 11.1, 11.2
        """
        order_map = {name: idx for idx, name in enumerate(sample_order)}
        max_order = len(sample_order)
        
        def get_order(sample):
            if sample in order_map:
                return (0, order_map[sample])
            else:
                return (1, samples.index(sample) if sample in samples else max_order)
        
        return sorted(samples, key=get_order)
    
    def _calculate_group_statistics(
        self,
        shm_data: Dict[str, Dict[str, Dict[str, float]]],
        sample_groups: Dict[str, List[str]]
    ) -> Dict[str, Dict[str, Dict[str, Dict[str, float]]]]:
        """
        计算分组统计
        
        Requirements: 11.3, 11.4
        """
        import numpy as np
        result = {}
        
        for group_name, sample_list in sample_groups.items():
            result[group_name] = {}
            
            for _, _, label in self.SHM_FIELDS:
                shm0_values = []
                shm1_values = []
                
                for sample in sample_list:
                    if sample in shm_data:
                        iso_data = shm_data[sample].get(label, {})
                        shm0 = iso_data.get("shm0")
                        shm1 = iso_data.get("shm1")
                        
                        if shm0 is not None:
                            shm0_values.append(shm0)
                        if shm1 is not None:
                            shm1_values.append(shm1)
                
                result[group_name][label] = {
                    "shm0": self._calc_stats(shm0_values),
                    "shm1": self._calc_stats(shm1_values)
                }
        
        return result
    
    def _calc_stats(self, values: List[float]) -> Dict[str, Optional[float]]:
        """计算统计值"""
        import numpy as np
        if not values:
            return {"mean": None, "std": None, "count": 0}
        
        return {
            "mean": round(float(np.mean(values)), 4),
            "std": round(float(np.std(values)), 4) if len(values) > 1 else 0.0,
            "count": len(values)
        }

    def _generate_table_data(
        self,
        shm_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        percentage_changes: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None
    ) -> Dict[str, Any]:
        """
        生成可复制的数据表格
        
        Requirements: 2.4
        """
        # 构建表头
        headers = ["Sample"]
        for _, _, label in self.SHM_FIELDS:
            headers.append(f"{label}_SHM0")
            headers.append(f"{label}_SHM1")
        
        if percentage_changes:
            for _, _, label in self.SHM_FIELDS:
                headers.append(f"{label}_SHM0_Change%")
                headers.append(f"{label}_SHM1_Change%")
        
        # 构建数据行
        rows = []
        for sample in samples:
            row = [sample]
            sample_data = shm_data.get(sample, {})
            
            # 添加原始值
            for _, _, label in self.SHM_FIELDS:
                iso_data = sample_data.get(label, {})
                shm0 = iso_data.get("shm0")
                shm1 = iso_data.get("shm1")
                row.append(f"{shm0:.4f}" if shm0 is not None else "")
                row.append(f"{shm1:.4f}" if shm1 is not None else "")
            
            # 添加百分比变化
            if percentage_changes:
                sample_changes = percentage_changes.get(sample, {})
                for _, _, label in self.SHM_FIELDS:
                    iso_change = sample_changes.get(label, {})
                    shm0_change = iso_change.get("shm0_pct_change")
                    shm1_change = iso_change.get("shm1_pct_change")
                    row.append(f"{shm0_change:+.2f}%" if shm0_change is not None else "")
                    row.append(f"{shm1_change:+.2f}%" if shm1_change is not None else "")
            
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
    
    def get_data_table(
        self,
        data: pd.DataFrame,
        sample_column: str = "Sample",
        baseline_sample: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取可复制的数据表格
        
        Requirements: 2.4
        
        Args:
            data: 输入的DataFrame
            sample_column: 样本名称所在的列
            baseline_sample: 基准样本（可选，用于计算百分比变化）
            
        Returns:
            包含headers, rows, tab_separated的字典
        """
        # 提取数据
        shm_data = self.extract_shm_data(data, sample_column)
        samples = list(shm_data.keys())
        
        # 计算百分比变化
        percentage_changes = None
        if baseline_sample:
            percentage_changes = self.calculate_percentage_changes(
                data, baseline_sample, sample_column
            )
        
        return self._generate_table_data(shm_data, samples, percentage_changes)
    
    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        figures = {}
        
        try:
            analysis_params = results.get("params", {})
            chart_config = SHMChartConfig.from_dict(
                analysis_params.get("chart_config", {})
            )
            
            shm_data = results.get("shm_data", {})
            samples = results.get("samples", [])
            percentage_changes = results.get("percentage_changes")
            baseline_sample = results.get("baseline_sample")
            
            if not shm_data or not samples:
                return figures
            
            # 为每个同型生成分组柱状图
            for shm0_col, shm1_col, label in self.SHM_FIELDS:
                fig = self._create_grouped_bar_chart(
                    shm_data, samples, label, chart_config
                )
                if fig:
                    figures[f"shm_{label.replace('/', '_')}"] = self._figure_to_base64(
                        fig, dpi=chart_config.dpi
                    )
            
            # 如果有百分比变化，生成百分比变化图
            if percentage_changes and baseline_sample:
                fig = self._create_percentage_change_chart(
                    percentage_changes, samples, baseline_sample, chart_config
                )
                if fig:
                    figures["percentage_change"] = self._figure_to_base64(
                        fig, dpi=chart_config.dpi
                    )
            
            # 生成综合对比图
            fig = self._create_overview_chart(shm_data, samples, chart_config)
            if fig:
                figures["overview"] = self._figure_to_base64(fig, dpi=chart_config.dpi)
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
            figures["error"] = f"Visualization error: {str(e)}"
        
        return figures

    def generate_grouped_bar_chart(
        self,
        data: pd.DataFrame,
        isotype_label: str,
        sample_column: str = "Sample",
        chart_config: Optional[SHMChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        生成分组柱状图（SHM0和SHM1对比）
        
        Requirements: 2.3
        
        Args:
            data: 输入的DataFrame
            isotype_label: 同型标签（如 "IgA", "IgG1/2" 等）
            sample_column: 样本名称所在的列
            chart_config: 图表配置（可选）
            
        Returns:
            Tuple of (PNG bytes, table_data dict)
        """
        if chart_config is None:
            chart_config = self.chart_config
        
        # 提取数据
        shm_data = self.extract_shm_data(data, sample_column)
        samples = list(shm_data.keys())
        
        # 创建图表
        fig = self._create_grouped_bar_chart(shm_data, samples, isotype_label, chart_config)
        
        # 转换为PNG bytes
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=chart_config.dpi, bbox_inches='tight')
        buffer.seek(0)
        png_bytes = buffer.getvalue()
        buffer.close()
        plt.close(fig)
        
        # 生成表格数据
        table_data = self._generate_table_data(shm_data, samples, None)
        
        return png_bytes, table_data
    
    def _create_grouped_bar_chart(
        self,
        shm_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        isotype_label: str,
        chart_config: SHMChartConfig
    ) -> plt.Figure:
        """
        创建单个同型的分组柱状图
        
        Requirements: 2.3
        """
        # 准备数据
        shm0_values = []
        shm1_values = []
        
        for sample in samples:
            sample_data = shm_data.get(sample, {})
            iso_data = sample_data.get(isotype_label, {})
            shm0_values.append(iso_data.get("shm0", 0) or 0)
            shm1_values.append(iso_data.get("shm1", 0) or 0)
        
        # 创建图表
        fig, ax = plt.subplots(figsize=chart_config.figsize)
        
        x = np.arange(len(samples))
        width = chart_config.bar_width
        
        # 绘制柱状图
        bars1 = ax.bar(x - width/2, shm0_values, width, 
                       label='SHM0', color=chart_config.shm0_color, alpha=0.8)
        bars2 = ax.bar(x + width/2, shm1_values, width, 
                       label='SHM1', color=chart_config.shm1_color, alpha=0.8)
        
        # 设置标题和标签
        title = chart_config.title or f"{isotype_label} SHM Analysis"
        ax.set_title(title, fontsize=chart_config.font_size + 4, fontweight='bold', pad=20)
        ax.set_xlabel("Sample", fontsize=chart_config.font_size + 2, fontweight='bold')
        ax.set_ylabel("SHM Value", fontsize=chart_config.font_size + 2, fontweight='bold')
        
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=chart_config.font_size)
        ax.legend(fontsize=chart_config.font_size, loc='upper right')
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        
        # 添加数值标签
        if chart_config.show_values:
            max_val = max(max(shm0_values) if shm0_values else 0, 
                         max(shm1_values) if shm1_values else 0)
            if max_val > 0:
                for bar, value in zip(bars1, shm0_values):
                    if value > 0:
                        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max_val * 0.01,
                               f'{value:.3f}', ha='center', va='bottom', 
                               fontsize=chart_config.font_size - 2, fontweight='bold')
                
                for bar, value in zip(bars2, shm1_values):
                    if value > 0:
                        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max_val * 0.01,
                               f'{value:.3f}', ha='center', va='bottom', 
                               fontsize=chart_config.font_size - 2, fontweight='bold')
        
        ax.set_facecolor('#f8f9fa')
        plt.tight_layout()
        
        return fig
    
    def _create_percentage_change_chart(
        self,
        percentage_changes: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        baseline_sample: str,
        chart_config: SHMChartConfig
    ) -> plt.Figure:
        """
        创建百分比变化图
        
        Requirements: 2.2, 2.5
        """
        # 创建子图布局
        n_isotypes = len(self.SHM_FIELDS)
        n_cols = 3
        n_rows = (n_isotypes + n_cols - 1) // n_cols
        
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(20, 6 * n_rows))
        fig.suptitle(
            f"SHM Percentage Change from Baseline\n(Baseline: {baseline_sample})",
            fontsize=16,
            fontweight='bold',
            y=0.98
        )
        
        axes = axes.flatten() if n_rows > 1 else [axes] if n_cols == 1 else axes.flatten()
        
        x_pos = np.arange(len(samples))
        bar_width = 0.35
        
        # 找到基准样本的索引
        baseline_index = samples.index(baseline_sample) if baseline_sample in samples else -1
        
        for idx, (shm0_col, shm1_col, label) in enumerate(self.SHM_FIELDS):
            ax = axes[idx]
            
            # 获取SHM0和SHM1的百分比变化
            shm0_changes = []
            shm1_changes = []
            
            for sample in samples:
                sample_changes = percentage_changes.get(sample, {})
                iso_change = sample_changes.get(label, {})
                shm0_changes.append(iso_change.get("shm0_pct_change", 0) or 0)
                shm1_changes.append(iso_change.get("shm1_pct_change", 0) or 0)
            
            # 绘制柱状图
            bars1 = ax.bar(x_pos - bar_width/2, shm0_changes, bar_width,
                          label='SHM0', color=chart_config.shm0_color, alpha=0.8)
            bars2 = ax.bar(x_pos + bar_width/2, shm1_changes, bar_width,
                          label='SHM1', color=chart_config.shm1_color, alpha=0.8)
            
            # 添加零线
            ax.axhline(y=0, color='gray', linestyle='-', linewidth=1.5, alpha=0.8)
            
            # 高亮基准样本
            if baseline_index >= 0:
                bars1[baseline_index].set_edgecolor('black')
                bars1[baseline_index].set_linewidth(2)
                bars2[baseline_index].set_edgecolor('black')
                bars2[baseline_index].set_linewidth(2)
            
            # 设置标签
            ax.set_xticks(x_pos)
            ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=10)
            ax.set_ylabel("Percentage Change (%)", fontsize=11, fontweight='bold')
            ax.set_xlabel("Sample", fontsize=11, fontweight='bold')
            ax.set_title(f"{label}", fontsize=13, fontweight='bold', pad=10)
            ax.legend(fontsize=9, loc='upper right')
            ax.grid(axis='y', alpha=0.3, linestyle='--')
            ax.set_facecolor('#f8f9fa')
        
        # 隐藏多余的子图
        for idx in range(len(self.SHM_FIELDS), len(axes)):
            axes[idx].set_visible(False)
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        
        return fig
    
    def _create_overview_chart(
        self,
        shm_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        chart_config: SHMChartConfig
    ) -> plt.Figure:
        """
        创建综合对比图
        """
        # 创建子图布局
        n_isotypes = len(self.SHM_FIELDS)
        n_cols = 3
        n_rows = (n_isotypes + n_cols - 1) // n_cols
        
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(18, 5 * n_rows))
        fig.suptitle(
            "SHM Analysis Overview",
            fontsize=16,
            fontweight='bold',
            y=0.98
        )
        
        axes = axes.flatten() if n_rows > 1 else [axes] if n_cols == 1 else axes.flatten()
        
        for idx, (shm0_col, shm1_col, label) in enumerate(self.SHM_FIELDS):
            ax = axes[idx]
            
            # 准备数据
            shm0_values = []
            shm1_values = []
            
            for sample in samples:
                sample_data = shm_data.get(sample, {})
                iso_data = sample_data.get(label, {})
                shm0_values.append(iso_data.get("shm0", 0) or 0)
                shm1_values.append(iso_data.get("shm1", 0) or 0)
            
            x = np.arange(len(samples))
            width = 0.35
            
            # 绘制柱状图
            ax.bar(x - width/2, shm0_values, width, 
                   label='SHM0', color=chart_config.shm0_color, alpha=0.8)
            ax.bar(x + width/2, shm1_values, width, 
                   label='SHM1', color=chart_config.shm1_color, alpha=0.8)
            
            ax.set_title(f"{label}", fontsize=13, fontweight='bold')
            ax.set_xlabel("Sample", fontsize=10)
            ax.set_ylabel("SHM Value", fontsize=10)
            ax.set_xticks(x)
            ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=9)
            ax.legend(fontsize=9)
            ax.grid(axis='y', alpha=0.3, linestyle='--')
            ax.set_facecolor('#f8f9fa')
        
        # 隐藏多余的子图
        for idx in range(len(self.SHM_FIELDS), len(axes)):
            axes[idx].set_visible(False)
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        
        return fig
