"""
IG Metrics Analyzer Module - 免疫球蛋白指标分析器
分析IGH、IGK、IGL链的5种指标（Reads, UCDR3, D50, Gini_index, Shannon）
计算百分比变化，生成对比图表

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any, List, Tuple, Optional
import logging
import io

from ..base_module import AnalysisModule
from ..registry import register_module

logger = logging.getLogger(__name__)


class IGMetricsChartConfig:
    """IG指标分析图表配置类"""
    
    def __init__(
        self,
        title: str = "",
        figsize: Tuple[int, int] = (16, 10),
        dpi: int = 300,
        colors: Dict[str, str] = None,
        font_size: int = 12,
        show_values: bool = True,
        bar_width: float = 0.25
    ):
        self.title = title
        self.figsize = figsize
        self.dpi = dpi
        self.colors = colors or {
            "IGH": "#2E86AB",
            "IGK": "#A23B72",
            "IGL": "#F18F01"
        }
        self.font_size = font_size
        self.show_values = show_values
        self.bar_width = bar_width

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'IGMetricsChartConfig':
        """从字典创建配置"""
        return cls(
            title=config_dict.get('title', ''),
            figsize=tuple(config_dict.get('figsize', (16, 10))),
            dpi=config_dict.get('dpi', 300),
            colors=config_dict.get('colors'),
            font_size=config_dict.get('font_size', 12),
            show_values=config_dict.get('show_values', True),
            bar_width=config_dict.get('bar_width', 0.25)
        )


@register_module
class IGMetricsAnalyzer(AnalysisModule):
    """
    IG指标分析器
    
    功能:
    - 验证数据是否包含所需的IG指标字段
    - 提取IGH、IGK、IGL链的5种指标
    - 计算相对于基准样本的百分比变化
    - 生成指标对比图表
    - 生成可复制的数据表格
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
    """
    
    # 支持的链类型
    CHAINS = ["IGH", "IGK", "IGL"]
    
    # 5种指标
    METRICS = ["Reads", "UCDR3", "D50", "Gini_index", "Shannon"]
    
    # 指标显示名称
    METRIC_DISPLAY_NAMES = {
        "Reads": "Reads",
        "UCDR3": "Unique CDR3",
        "D50": "D50 Index",
        "Gini_index": "Gini Index",
        "Shannon": "Shannon Entropy"
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.chart_config = IGMetricsChartConfig()
        if config and 'chart_config' in config:
            self.chart_config = IGMetricsChartConfig.from_dict(config['chart_config'])

    def get_name(self) -> str:
        return "ig_metrics_analyzer"
    
    def get_description(self) -> str:
        return "IG指标分析 - 分析IGH、IGK、IGL链的Reads、UCDR3、D50、Gini指数、Shannon熵"
    
    def get_category(self) -> str:
        return "diversity_analysis"
    
    def get_required_columns(self) -> List[str]:
        return ["Sample"]
    
    def get_optional_columns(self) -> List[str]:
        # 生成所有可能的列名组合
        optional = []
        for chain in self.CHAINS:
            for metric in self.METRICS:
                optional.append(f"{chain}_{metric}")
        optional.extend(["Chain", "Group", "Timepoint", "Condition"])
        return optional
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "sample_column": "Sample",
            "chains": ["IGH", "IGK", "IGL"],
            "metrics": ["Reads", "UCDR3", "D50", "Gini_index", "Shannon"],
            "baseline_sample": None,
            "sample_order": None,  # 自定义样本排序 (Requirements: 11.1, 11.2)
            "sample_groups": None,  # 样本分组配置 (Requirements: 11.3, 11.4)
            "chart_config": {
                "title": "",
                "figsize": (16, 10),
                "dpi": 300,
                "font_size": 12,
                "show_values": True,
                "bar_width": 0.25
            }
        }

    def validate_ig_fields(
        self,
        data: pd.DataFrame,
        chains: List[str] = None
    ) -> Tuple[bool, Dict[str, List[str]], List[str]]:
        """
        验证数据是否包含所需的IG指标字段
        
        Requirements: 3.1
        
        Args:
            data: 输入的DataFrame
            chains: 要验证的链列表（默认为所有链）
            
        Returns:
            Tuple of (is_valid, present_fields_by_chain, missing_fields)
        """
        if chains is None:
            chains = self.CHAINS
        
        present_fields = {}
        missing_fields = []
        
        for chain in chains:
            present_fields[chain] = []
            for metric in self.METRICS:
                # 尝试多种列名格式
                possible_names = [
                    f"{chain}_{metric}",
                    f"{chain.lower()}_{metric}",
                    f"{chain}_{metric.lower()}",
                    f"{chain.lower()}_{metric.lower()}",
                    metric if chain == "IGH" else None  # 有些数据可能没有链前缀
                ]
                
                found = False
                for name in possible_names:
                    if name and name in data.columns:
                        present_fields[chain].append(name)
                        found = True
                        break
                    # 大小写不敏感匹配
                    if name:
                        for col in data.columns:
                            if col.lower() == name.lower():
                                present_fields[chain].append(col)
                                found = True
                                break
                    if found:
                        break
                
                if not found:
                    missing_fields.append(f"{chain}_{metric}")
        
        # 如果至少有一个链有完整的指标数据，则认为有效
        has_valid_chain = any(
            len(fields) >= len(self.METRICS) 
            for fields in present_fields.values()
        )
        
        return has_valid_chain, present_fields, missing_fields

    def validate_data(self, data: pd.DataFrame) -> Tuple[bool, str]:
        """验证输入数据"""
        if data.empty:
            return False, "数据为空"
        
        # 检查是否有IG指标相关的列
        has_ig_data = False
        for chain in self.CHAINS:
            for metric in self.METRICS:
                for col in data.columns:
                    if chain.lower() in col.lower() and metric.lower() in col.lower():
                        has_ig_data = True
                        break
                if has_ig_data:
                    break
            if has_ig_data:
                break
        
        if not has_ig_data:
            return False, "数据中没有找到IG指标相关的列"
        
        return True, "数据验证通过"

    def _find_column(
        self,
        data: pd.DataFrame,
        chain: str,
        metric: str
    ) -> Optional[str]:
        """
        查找匹配的列名（大小写不敏感）
        
        Args:
            data: DataFrame
            chain: 链名（IGH, IGK, IGL）
            metric: 指标名
            
        Returns:
            实际的列名，如果未找到则返回None
        """
        # 尝试多种列名格式
        possible_names = [
            f"{chain}_{metric}",
            f"{chain.lower()}_{metric}",
            f"{chain}_{metric.lower()}",
            f"{chain.lower()}_{metric.lower()}",
            f"{chain}{metric}",
            f"{chain.lower()}{metric.lower()}"
        ]
        
        for name in possible_names:
            if name in data.columns:
                return name
            # 大小写不敏感匹配
            for col in data.columns:
                if col.lower() == name.lower():
                    return col
        
        return None

    def extract_metrics(
        self,
        data: pd.DataFrame,
        chains: List[str] = None,
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        提取指定链的所有指标
        
        Requirements: 3.2
        
        Args:
            data: 输入的DataFrame
            chains: 要提取的链列表（默认为所有链）
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {sample: {chain: {metric: value}}}
        """
        if chains is None:
            chains = self.CHAINS
        
        result = {}
        
        # 确保样本列存在
        actual_sample_col = None
        for col in data.columns:
            if col.lower() == sample_column.lower():
                actual_sample_col = col
                break
        if not actual_sample_col:
            actual_sample_col = data.columns[0]
        
        for _, row in data.iterrows():
            sample_name = str(row[actual_sample_col])
            result[sample_name] = {}
            
            for chain in chains:
                chain_data = {}
                
                for metric in self.METRICS:
                    col = self._find_column(data, chain, metric)
                    
                    if col:
                        value = row[col]
                        if pd.notna(value):
                            try:
                                chain_data[metric] = float(value)
                            except (ValueError, TypeError):
                                chain_data[metric] = None
                        else:
                            chain_data[metric] = None
                    else:
                        chain_data[metric] = None
                
                result[sample_name][chain] = chain_data
        
        return result

    def calculate_percentage_changes(
        self,
        data: pd.DataFrame,
        baseline_sample: str,
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
        """
        计算相对于基准样本的百分比变化
        
        Requirements: 3.5
        
        公式: ((sample_value - baseline_value) / baseline_value) * 100
        
        Args:
            data: 输入的DataFrame
            baseline_sample: 基准样本名称
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {sample: {chain: {metric: pct_change}}}
        """
        # 先提取所有指标数据
        metrics_data = self.extract_metrics(data, sample_column=sample_column)
        
        if baseline_sample not in metrics_data:
            logger.warning(f"Baseline sample '{baseline_sample}' not found")
            return {}
        
        baseline_data = metrics_data[baseline_sample]
        result = {}
        
        for sample_name, sample_data in metrics_data.items():
            result[sample_name] = {}
            
            for chain in self.CHAINS:
                pct_changes = {}
                
                sample_chain = sample_data.get(chain, {})
                baseline_chain = baseline_data.get(chain, {})
                
                for metric in self.METRICS:
                    sample_value = sample_chain.get(metric)
                    baseline_value = baseline_chain.get(metric)
                    
                    if (sample_value is not None and 
                        baseline_value is not None and 
                        baseline_value != 0):
                        pct_changes[metric] = round(
                            ((sample_value - baseline_value) / baseline_value) * 100, 2
                        )
                    else:
                        pct_changes[metric] = None
                
                result[sample_name][chain] = pct_changes
        
        return result

    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行IG指标分析"""
        try:
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            sample_column = analysis_params.get('sample_column', 'Sample')
            chains = analysis_params.get('chains', self.CHAINS)
            metrics = analysis_params.get('metrics', self.METRICS)
            baseline_sample = analysis_params.get('baseline_sample')
            sample_order = analysis_params.get('sample_order')  # Requirements: 11.1, 11.2
            sample_groups = analysis_params.get('sample_groups')  # Requirements: 11.3, 11.4
            
            # 提取指标数据
            metrics_data = self.extract_metrics(data, chains, sample_column)
            
            # 获取样本列表
            samples = list(metrics_data.keys())
            
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
                    metrics_data, sample_groups, chains, metrics
                )
            
            # 生成数据表格
            table_data = self._generate_table_data(
                metrics_data, samples, chains, metrics, percentage_changes
            )
            
            return {
                "samples": samples,
                "chains": chains,
                "metrics": metrics,
                "metrics_data": metrics_data,
                "percentage_changes": percentage_changes,
                "baseline_sample": baseline_sample,
                "sample_order": sample_order,
                "group_statistics": group_statistics,
                "table_data": table_data,
                "params": analysis_params
            }
            
        except Exception as e:
            logger.error(f"Error in IG metrics analysis: {e}")
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
        metrics_data: Dict[str, Dict[str, Dict[str, float]]],
        sample_groups: Dict[str, List[str]],
        chains: List[str],
        metrics: List[str]
    ) -> Dict[str, Dict[str, Dict[str, Dict[str, float]]]]:
        """
        计算分组统计
        
        Requirements: 11.3, 11.4
        """
        result = {}
        
        for group_name, sample_list in sample_groups.items():
            result[group_name] = {}
            
            for chain in chains:
                result[group_name][chain] = {}
                
                for metric in metrics:
                    values = []
                    
                    for sample in sample_list:
                        if sample in metrics_data:
                            chain_data = metrics_data[sample].get(chain, {})
                            value = chain_data.get(metric)
                            if value is not None:
                                values.append(value)
                    
                    result[group_name][chain][metric] = self._calc_stats(values)
        
        return result
    
    def _calc_stats(self, values: List[float]) -> Dict[str, Optional[float]]:
        """计算统计值"""
        if not values:
            return {"mean": None, "std": None, "count": 0}
        
        return {
            "mean": round(float(np.mean(values)), 4),
            "std": round(float(np.std(values)), 4) if len(values) > 1 else 0.0,
            "count": len(values)
        }

    def _generate_table_data(
        self,
        metrics_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        chains: List[str],
        metrics: List[str],
        percentage_changes: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None
    ) -> Dict[str, Any]:
        """
        生成可复制的数据表格
        
        Requirements: 3.4
        """
        # 构建表头
        headers = ["Sample"]
        for chain in chains:
            for metric in metrics:
                headers.append(f"{chain}_{metric}")
        
        if percentage_changes:
            for chain in chains:
                for metric in metrics:
                    headers.append(f"{chain}_{metric}_Change%")
        
        # 构建数据行
        rows = []
        for sample in samples:
            row = [sample]
            sample_data = metrics_data.get(sample, {})
            
            # 添加原始值
            for chain in chains:
                chain_data = sample_data.get(chain, {})
                for metric in metrics:
                    value = chain_data.get(metric)
                    if value is not None:
                        # 根据指标类型格式化
                        if metric in ["Reads", "UCDR3"]:
                            row.append(f"{int(value):,}")
                        elif metric == "D50":
                            row.append(f"{value:.0f}")
                        else:
                            row.append(f"{value:.4f}")
                    else:
                        row.append("")
            
            # 添加百分比变化
            if percentage_changes:
                sample_changes = percentage_changes.get(sample, {})
                for chain in chains:
                    chain_changes = sample_changes.get(chain, {})
                    for metric in metrics:
                        change = chain_changes.get(metric)
                        if change is not None:
                            row.append(f"{change:+.2f}%")
                        else:
                            row.append("")
            
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
        chains: List[str] = None,
        metrics: List[str] = None,
        sample_column: str = "Sample",
        baseline_sample: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取可复制的数据表格
        
        Requirements: 3.4
        
        Args:
            data: 输入的DataFrame
            chains: 要包含的链列表
            metrics: 要包含的指标列表
            sample_column: 样本名称所在的列
            baseline_sample: 基准样本（可选，用于计算百分比变化）
            
        Returns:
            包含headers, rows, tab_separated的字典
        """
        if chains is None:
            chains = self.CHAINS
        if metrics is None:
            metrics = self.METRICS
        
        # 提取数据
        metrics_data = self.extract_metrics(data, chains, sample_column)
        samples = list(metrics_data.keys())
        
        # 计算百分比变化
        percentage_changes = None
        if baseline_sample:
            percentage_changes = self.calculate_percentage_changes(
                data, baseline_sample, sample_column
            )
        
        return self._generate_table_data(
            metrics_data, samples, chains, metrics, percentage_changes
        )

    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        figures = {}
        
        try:
            analysis_params = results.get("params", {})
            chart_config = IGMetricsChartConfig.from_dict(
                analysis_params.get("chart_config", {})
            )
            
            metrics_data = results.get("metrics_data", {})
            samples = results.get("samples", [])
            chains = results.get("chains", self.CHAINS)
            metrics = results.get("metrics", self.METRICS)
            percentage_changes = results.get("percentage_changes")
            baseline_sample = results.get("baseline_sample")
            
            if not metrics_data or not samples:
                return figures
            
            # 为每个指标生成对比图
            for metric in metrics:
                fig = self._create_metric_comparison_chart(
                    metrics_data, samples, chains, metric, chart_config
                )
                if fig:
                    figures[f"metric_{metric}"] = self._figure_to_base64(
                        fig, dpi=chart_config.dpi
                    )
            
            # 如果有百分比变化，生成百分比变化图
            if percentage_changes and baseline_sample:
                fig = self._create_percentage_change_chart(
                    percentage_changes, samples, chains, metrics, 
                    baseline_sample, chart_config
                )
                if fig:
                    figures["percentage_change"] = self._figure_to_base64(
                        fig, dpi=chart_config.dpi
                    )
            
            # 生成综合概览图
            fig = self._create_overview_chart(
                metrics_data, samples, chains, metrics, chart_config
            )
            if fig:
                figures["overview"] = self._figure_to_base64(fig, dpi=chart_config.dpi)
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
            figures["error"] = f"Visualization error: {str(e)}"
        
        return figures

    def generate_metric_comparison_chart(
        self,
        data: pd.DataFrame,
        metric: str,
        chains: List[str] = None,
        sample_column: str = "Sample",
        baseline_sample: Optional[str] = None,
        chart_config: Optional[IGMetricsChartConfig] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        生成指标对比图
        
        Requirements: 3.3
        
        Args:
            data: 输入的DataFrame
            metric: 要可视化的指标名称
            chains: 要包含的链列表
            sample_column: 样本名称所在的列
            baseline_sample: 基准样本（可选）
            chart_config: 图表配置（可选）
            
        Returns:
            Tuple of (PNG bytes, table_data dict)
        """
        if chart_config is None:
            chart_config = self.chart_config
        if chains is None:
            chains = self.CHAINS
        
        # 提取数据
        metrics_data = self.extract_metrics(data, chains, sample_column)
        samples = list(metrics_data.keys())
        
        # 创建图表
        fig = self._create_metric_comparison_chart(
            metrics_data, samples, chains, metric, chart_config
        )
        
        # 转换为PNG bytes
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=chart_config.dpi, bbox_inches='tight')
        buffer.seek(0)
        png_bytes = buffer.getvalue()
        buffer.close()
        plt.close(fig)
        
        # 生成表格数据
        percentage_changes = None
        if baseline_sample:
            percentage_changes = self.calculate_percentage_changes(
                data, baseline_sample, sample_column
            )
        
        table_data = self._generate_table_data(
            metrics_data, samples, chains, [metric], percentage_changes
        )
        
        return png_bytes, table_data

    def _create_metric_comparison_chart(
        self,
        metrics_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        chains: List[str],
        metric: str,
        chart_config: IGMetricsChartConfig
    ) -> plt.Figure:
        """
        创建单个指标的对比图
        
        Requirements: 3.3
        """
        # 准备数据
        chain_values = {chain: [] for chain in chains}
        
        for sample in samples:
            sample_data = metrics_data.get(sample, {})
            for chain in chains:
                chain_data = sample_data.get(chain, {})
                value = chain_data.get(metric, 0)
                chain_values[chain].append(value if value is not None else 0)
        
        # 创建图表
        fig, ax = plt.subplots(figsize=chart_config.figsize)
        
        x = np.arange(len(samples))
        width = chart_config.bar_width
        n_chains = len(chains)
        
        # 计算每个链的偏移量
        offsets = np.linspace(-(n_chains-1)/2 * width, (n_chains-1)/2 * width, n_chains)
        
        # 绘制柱状图
        bars_list = []
        for i, chain in enumerate(chains):
            bars = ax.bar(
                x + offsets[i], 
                chain_values[chain], 
                width,
                label=chain, 
                color=chart_config.colors.get(chain, f'C{i}'),
                alpha=0.8
            )
            bars_list.append(bars)
        
        # 设置标题和标签
        display_name = self.METRIC_DISPLAY_NAMES.get(metric, metric)
        title = chart_config.title or f"{display_name} Comparison"
        ax.set_title(title, fontsize=chart_config.font_size + 4, fontweight='bold', pad=20)
        ax.set_xlabel("Sample", fontsize=chart_config.font_size + 2, fontweight='bold')
        ax.set_ylabel(display_name, fontsize=chart_config.font_size + 2, fontweight='bold')
        
        ax.set_xticks(x)
        ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=chart_config.font_size)
        ax.legend(fontsize=chart_config.font_size, loc='upper right')
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        
        # 添加数值标签
        if chart_config.show_values:
            all_values = [v for chain_vals in chain_values.values() for v in chain_vals]
            max_val = max(all_values) if all_values else 1
            
            for bars, chain in zip(bars_list, chains):
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        # 根据指标类型格式化
                        if metric in ["Reads", "UCDR3"]:
                            label = f'{int(height):,}'
                        elif metric == "D50":
                            label = f'{height:.0f}'
                        else:
                            label = f'{height:.3f}'
                        
                        ax.text(
                            bar.get_x() + bar.get_width()/2, 
                            height + max_val * 0.01,
                            label, 
                            ha='center', 
                            va='bottom',
                            fontsize=chart_config.font_size - 3,
                            fontweight='bold',
                            rotation=45
                        )
        
        ax.set_facecolor('#f8f9fa')
        plt.tight_layout()
        
        return fig

    def _create_percentage_change_chart(
        self,
        percentage_changes: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        chains: List[str],
        metrics: List[str],
        baseline_sample: str,
        chart_config: IGMetricsChartConfig
    ) -> plt.Figure:
        """
        创建百分比变化图
        
        Requirements: 3.5
        """
        # 创建子图布局
        n_metrics = len(metrics)
        n_cols = min(3, n_metrics)
        n_rows = (n_metrics + n_cols - 1) // n_cols
        
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 5 * n_rows))
        fig.suptitle(
            f"IG Metrics - Percentage Change from Baseline\n(Baseline: {baseline_sample})",
            fontsize=16,
            fontweight='bold',
            y=0.98
        )
        
        # 确保axes是数组
        if n_metrics == 1:
            axes = np.array([axes])
        axes = axes.flatten() if hasattr(axes, 'flatten') else [axes]
        
        x_pos = np.arange(len(samples))
        width = chart_config.bar_width
        n_chains = len(chains)
        offsets = np.linspace(-(n_chains-1)/2 * width, (n_chains-1)/2 * width, n_chains)
        
        # 找到基准样本的索引
        baseline_index = samples.index(baseline_sample) if baseline_sample in samples else -1
        
        for idx, metric in enumerate(metrics):
            ax = axes[idx]
            
            # 获取每个链的百分比变化
            for i, chain in enumerate(chains):
                values = []
                for sample in samples:
                    sample_changes = percentage_changes.get(sample, {})
                    chain_changes = sample_changes.get(chain, {})
                    change = chain_changes.get(metric, 0)
                    values.append(change if change is not None else 0)
                
                bars = ax.bar(
                    x_pos + offsets[i], 
                    values, 
                    width,
                    label=chain, 
                    color=chart_config.colors.get(chain, f'C{i}'),
                    alpha=0.8
                )
                
                # 高亮基准样本
                if baseline_index >= 0:
                    bars[baseline_index].set_edgecolor('black')
                    bars[baseline_index].set_linewidth(2)
            
            # 添加零线
            ax.axhline(y=0, color='gray', linestyle='-', linewidth=1.5, alpha=0.8)
            
            # 设置标签
            display_name = self.METRIC_DISPLAY_NAMES.get(metric, metric)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=10)
            ax.set_ylabel("Percentage Change (%)", fontsize=11, fontweight='bold')
            ax.set_xlabel("Sample", fontsize=11, fontweight='bold')
            ax.set_title(f"{display_name}", fontsize=13, fontweight='bold', pad=10)
            ax.legend(fontsize=9, loc='upper right')
            ax.grid(axis='y', alpha=0.3, linestyle='--')
            ax.set_facecolor('#f8f9fa')
        
        # 隐藏多余的子图
        for idx in range(len(metrics), len(axes)):
            axes[idx].set_visible(False)
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        
        return fig

    def _create_overview_chart(
        self,
        metrics_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        chains: List[str],
        metrics: List[str],
        chart_config: IGMetricsChartConfig
    ) -> plt.Figure:
        """
        创建综合概览图
        """
        # 创建子图布局
        n_metrics = len(metrics)
        n_cols = min(3, n_metrics)
        n_rows = (n_metrics + n_cols - 1) // n_cols
        
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 5 * n_rows))
        fig.suptitle(
            "IG Metrics Overview",
            fontsize=16,
            fontweight='bold',
            y=0.98
        )
        
        # 确保axes是数组
        if n_metrics == 1:
            axes = np.array([axes])
        axes = axes.flatten() if hasattr(axes, 'flatten') else [axes]
        
        for idx, metric in enumerate(metrics):
            ax = axes[idx]
            
            # 准备数据
            for chain in chains:
                values = []
                for sample in samples:
                    sample_data = metrics_data.get(sample, {})
                    chain_data = sample_data.get(chain, {})
                    value = chain_data.get(metric, 0)
                    values.append(value if value is not None else 0)
                
                ax.plot(
                    samples, 
                    values, 
                    marker='o', 
                    label=chain,
                    color=chart_config.colors.get(chain, None),
                    linewidth=2,
                    markersize=8
                )
            
            display_name = self.METRIC_DISPLAY_NAMES.get(metric, metric)
            ax.set_title(f"{display_name}", fontsize=13, fontweight='bold')
            ax.set_xlabel("Sample", fontsize=10)
            ax.set_ylabel(display_name, fontsize=10)
            ax.tick_params(axis='x', rotation=45)
            ax.legend(fontsize=9)
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.set_facecolor('#f8f9fa')
        
        # 隐藏多余的子图
        for idx in range(len(metrics), len(axes)):
            axes[idx].set_visible(False)
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        
        return fig
