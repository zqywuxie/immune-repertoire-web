"""
IG Metrics Analyzer - 免疫球蛋白指标分析器
分析IGH、IGK、IGL链的5种指标（Reads, UCDR3, D50, Gini_index, Shannon）

Refactored to use BaseAnalyzer interface.
Requirements: 7.3, 11.2
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
import logging
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from .base_analyzer import BaseAnalyzer, ValidationResult

logger = logging.getLogger(__name__)


class IGMetricsAnalyzer(BaseAnalyzer):
    """
    IG指标分析器
    
    功能:
    - 验证数据是否包含所需的IG指标字段
    - 提取IGH、IGK、IGL链的5种指标
    - 计算相对于基准样本的百分比变化
    - 生成分析结果数据
    
    Requirements: 7.3, 11.2
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
    
    def get_required_fields(self) -> List[str]:
        """
        获取必需字段列表
        
        Returns:
            必需字段列表
        """
        return ["Sample", "Chain"]
    
    def get_optional_fields(self) -> List[str]:
        """
        获取可选字段列表
        
        Returns:
            可选字段列表
        """
        # 新格式：每行包含 Sample, Chain, Reads, UCDR3, D50, Gini_index, Shannon
        optional = ["Reads", "UCDR3", "D50", "Gini_index", "Shannon"]
        # 也支持旧格式：每个链的指标作为单独的列
        for chain in self.CHAINS:
            for metric in self.METRICS:
                optional.append(f"{chain}_{metric}")
        optional.extend(["Group", "Timepoint", "Condition"])
        return optional
    
    def get_default_parameters(self) -> Dict[str, Any]:
        """
        获取默认参数
        
        Returns:
            默认参数字典
        """
        return {
            "sample_column": "Sample",
            "chains": ["IGH", "IGK", "IGL"],
            "metrics": ["Reads", "UCDR3", "D50", "Gini_index", "Shannon"],
            "baseline_sample": None,
            "sample_order": None,
            "sample_groups": None
        }
    
    def validate_data(self, data: pd.DataFrame) -> ValidationResult:
        """
        验证输入数据
        
        Args:
            data: 输入的DataFrame
            
        Returns:
            ValidationResult对象
        """
        errors = []
        warnings = []
        
        # 检查数据是否为空
        if data.empty:
            errors.append("数据为空")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)
        
        # 检查数据格式：新格式（Sample, Chain, Reads...）或旧格式（IGH_Reads...）
        cols_lower = [c.lower() for c in data.columns]
        
        # 新格式检查：有Chain列和指标列
        has_chain_col = any('chain' in c for c in cols_lower)
        has_metric_cols = any(m.lower() in cols_lower for m in self.METRICS)
        
        # 旧格式检查：有链_指标格式的列
        has_old_format = False
        for chain in self.CHAINS:
            for metric in self.METRICS:
                for col in data.columns:
                    if chain.lower() in col.lower() and metric.lower() in col.lower():
                        has_old_format = True
                        break
                if has_old_format:
                    break
            if has_old_format:
                break
        
        if not (has_chain_col and has_metric_cols) and not has_old_format:
            errors.append("数据中没有找到IG指标相关的列。支持两种格式：1) Sample, Chain, Reads, UCDR3... 2) IGH_Reads, IGH_UCDR3...")
        
        is_valid = len(errors) == 0
        
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings
        )
    
    def analyze(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行IG指标分析
        
        Args:
            data: 输入的DataFrame
            parameters: 分析参数
            
        Returns:
            分析结果字典
            
        Requirements: 7.3
        """
        try:
            # 合并参数
            params = self.merge_parameters(parameters)
            
            sample_column = params.get('sample_column', 'Sample')
            chains = params.get('chains', self.CHAINS)
            metrics = params.get('metrics', self.METRICS)
            baseline_sample = params.get('baseline_sample')
            sample_order = params.get('sample_order')
            sample_groups = params.get('sample_groups')
            
            # 提取指标数据
            logger.info(f"Data columns: {list(data.columns)}")
            logger.info(f"Data shape: {data.shape}")
            logger.info(f"Sample column: {sample_column}")
            logger.info(f"Chains to extract: {chains}")
            
            metrics_data = self._extract_metrics(data, chains, sample_column)
            
            # 获取样本列表
            samples = list(metrics_data.keys())
            logger.info(f"Extracted samples: {samples}")
            logger.info(f"Metrics data keys: {list(metrics_data.keys())}")
            
            # 应用自定义样本排序
            if sample_order:
                samples = self._apply_sample_order(samples, sample_order)
            
            # 计算百分比变化（如果指定了基准样本）
            percentage_changes = None
            if baseline_sample:
                percentage_changes = self._calculate_percentage_changes(
                    metrics_data, baseline_sample
                )
            
            # 计算分组统计
            group_statistics = None
            if sample_groups:
                group_statistics = self._calculate_group_statistics(
                    metrics_data, sample_groups, chains, metrics
                )
            
            # 生成数据表格（宽格式：每行一个样本）
            table_data = self._generate_table_data(
                metrics_data, samples, chains, metrics, percentage_changes
            )
            
            # 生成长格式表格（每行一条链数据：Sample, Chain, Reads...）
            long_format_table = self._generate_long_format_table(
                metrics_data, samples, chains, metrics
            )
            
            # 生成图表
            charts = self._generate_charts(metrics_data, samples, chains, metrics, params, baseline_sample)
            
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
                "long_format_table": long_format_table,
                "charts": charts,
                "parameters": params
            }
            
        except Exception as e:
            logger.error(f"Error in IG metrics analysis: {e}")
            raise RuntimeError(f"IG metrics analysis failed: {str(e)}")
    
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
    
    def _extract_metrics(
        self,
        data: pd.DataFrame,
        chains: List[str],
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        提取指定链的所有指标
        
        支持两种数据格式：
        1. 新格式：每行包含 Sample, Chain, Reads, UCDR3, D50, Gini_index, Shannon
        2. 旧格式：每行包含 Sample, IGH_Reads, IGH_UCDR3, IGK_Reads, ...
        
        Args:
            data: 输入的DataFrame
            chains: 要提取的链列表
            sample_column: 样本名称所在的列
            
        Returns:
            字典格式: {sample: {chain: {metric: value}}}
        """
        result = {}
        
        logger.warning(f"[DEBUG] _extract_metrics called with columns: {list(data.columns)}")
        logger.warning(f"[DEBUG] Data shape: {data.shape}, sample_column: {sample_column}")
        
        # 确保样本列存在
        actual_sample_col = None
        for col in data.columns:
            if col.lower() == sample_column.lower():
                actual_sample_col = col
                break
        if not actual_sample_col:
            actual_sample_col = data.columns[0]
        
        logger.warning(f"[DEBUG] Using sample column: {actual_sample_col}")
        
        # 检测数据格式：检查是否有链_指标格式的列（旧格式）
        has_old_format_cols = False
        found_col = None
        for chain in chains:
            for metric in self.METRICS:
                col = self._find_column(data, chain, metric)
                if col:
                    has_old_format_cols = True
                    found_col = col
                    logger.warning(f"[DEBUG] Found old format column: {col} for {chain}_{metric}")
                    break
            if has_old_format_cols:
                break
        
        if not has_old_format_cols:
            logger.warning(f"[DEBUG] No old format columns found for chains={chains}, metrics={self.METRICS}")
        
        # 检测数据格式：是否有Chain列且Chain列包含有效的链值
        chain_col = None
        has_valid_chain_values = False
        for col in data.columns:
            if col.lower() == 'chain':
                chain_col = col
                # 检查Chain列是否包含有效的链值（IGH, IGK, IGL等）
                unique_values = data[col].dropna().unique()
                valid_chains = set([v.upper() for v in unique_values if isinstance(v, str)])
                has_valid_chain_values = bool(valid_chains & set(chains))
                break
        
        # 优先使用旧格式（如果存在链_指标格式的列）
        if has_old_format_cols:
            logger.warning(f"[DEBUG] Using OLD format (found chain_metric columns)")
            result = self._extract_metrics_old_format(data, chains, actual_sample_col)
        elif chain_col and has_valid_chain_values:
            # 新格式：每行包含 Sample, Chain, Reads, UCDR3...
            logger.warning(f"[DEBUG] Using NEW format with chain_col: {chain_col}")
            result = self._extract_metrics_new_format(data, chains, actual_sample_col, chain_col)
        else:
            # 默认尝试旧格式
            logger.warning(f"[DEBUG] Using OLD format (default)")
            result = self._extract_metrics_old_format(data, chains, actual_sample_col)
        
        logger.warning(f"[DEBUG] Extracted {len(result)} samples: {list(result.keys())[:5]}...")
        
        return result
    
    def _extract_metrics_new_format(
        self,
        data: pd.DataFrame,
        chains: List[str],
        sample_col: str,
        chain_col: str
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        从新格式数据中提取指标（每行包含 Sample, Chain, Reads...）
        """
        result = {}
        
        # 找到指标列
        metric_cols = {}
        for metric in self.METRICS:
            for col in data.columns:
                if col.lower() == metric.lower():
                    metric_cols[metric] = col
                    break
        
        for _, row in data.iterrows():
            sample_name = str(row[sample_col])
            chain_name = str(row[chain_col]).upper()
            
            # 只处理选中的链
            if chain_name not in chains:
                continue
            
            if sample_name not in result:
                result[sample_name] = {}
            
            chain_data = {}
            for metric in self.METRICS:
                if metric in metric_cols:
                    value = row[metric_cols[metric]]
                    if pd.notna(value):
                        try:
                            chain_data[metric] = float(value)
                        except (ValueError, TypeError):
                            chain_data[metric] = None
                    else:
                        chain_data[metric] = None
                else:
                    chain_data[metric] = None
            
            result[sample_name][chain_name] = chain_data
        
        return result
    
    def _extract_metrics_old_format(
        self,
        data: pd.DataFrame,
        chains: List[str],
        sample_col: str
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        从旧格式数据中提取指标（每行包含 Sample, IGH_Reads, IGH_UCDR3...）
        """
        result = {}
        
        for _, row in data.iterrows():
            sample_name = str(row[sample_col])
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
    
    def _calculate_percentage_changes(
        self,
        metrics_data: Dict[str, Dict[str, Dict[str, float]]],
        baseline_sample: str
    ) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
        """
        计算相对于基准样本的百分比变化
        
        公式: ((sample_value - baseline_value) / baseline_value) * 100
        
        Args:
            metrics_data: 指标数据
            baseline_sample: 基准样本名称
            
        Returns:
            字典格式: {sample: {chain: {metric: pct_change}}}
        """
        # 尝试精确匹配
        actual_baseline = None
        if baseline_sample in metrics_data:
            actual_baseline = baseline_sample
        else:
            # 尝试模糊匹配（去除空格、大小写不敏感）
            baseline_lower = baseline_sample.lower().strip()
            for sample_name in metrics_data.keys():
                if sample_name.lower().strip() == baseline_lower:
                    actual_baseline = sample_name
                    break
        
        if not actual_baseline:
            logger.warning(f"Baseline sample '{baseline_sample}' not found in samples: {list(metrics_data.keys())}")
            return {}
        
        baseline_data = metrics_data[actual_baseline]
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
    
    def _apply_sample_order(
        self,
        samples: List[str],
        sample_order: List[str]
    ) -> List[str]:
        """应用自定义样本排序"""
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
        """计算分组统计"""
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
        """生成可复制的数据表格（不包含百分比变化列）"""
        # 构建表头 - 只包含原始值，不包含百分比变化
        headers = ["Sample"]
        for chain in chains:
            for metric in metrics:
                headers.append(f"{chain}_{metric}")
        
        # 构建数据行
        rows = []
        for sample in samples:
            row = [sample]
            sample_data = metrics_data.get(sample, {})
            
            # 添加原始值，保留3位小数
            for chain in chains:
                chain_data = sample_data.get(chain, {})
                for metric in metrics:
                    value = chain_data.get(metric)
                    if value is not None:
                        # 根据指标类型格式化，保留3位小数
                        if metric in ["Reads", "UCDR3"]:
                            row.append(int(value))
                        else:
                            row.append(round(value, 3))
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
        """将表格数据转换为制表符分隔格式"""
        lines = ["\t".join(str(h) for h in headers)]
        for row in rows:
            lines.append("\t".join(str(v) if v is not None else "" for v in row))
        return "\n".join(lines)
    
    def _generate_long_format_table(
        self,
        metrics_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        chains: List[str],
        metrics: List[str]
    ) -> Dict[str, Any]:
        """
        生成长格式数据表格（每行一条链数据）
        
        输出格式: Sample, Chain, Reads, UCDR3, D50, Gini_index, Shannon
        """
        headers = ["Sample", "Chain"] + metrics
        rows = []
        
        for sample in samples:
            sample_data = metrics_data.get(sample, {})
            for chain in chains:
                chain_data = sample_data.get(chain, {})
                row = [sample, chain]
                
                for metric in metrics:
                    value = chain_data.get(metric)
                    if value is not None:
                        if metric in ["Reads", "UCDR3"]:
                            row.append(int(value))
                        else:
                            row.append(round(value, 3))
                    else:
                        row.append("")
                
                rows.append(row)
        
        return {
            "headers": headers,
            "rows": rows,
            "tab_separated": self._to_tab_separated(headers, rows)
        }
    
    def _generate_charts(
        self,
        metrics_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        chains: List[str],
        metrics: List[str],
        params: Dict[str, Any],
        baseline_sample: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """生成IG指标分析图表 - 每个指标一个图，显示百分比变化"""
        charts = []
        
        try:
            plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
            plt.rcParams["axes.unicode_minus"] = False
            
            chart_config = params.get('chart_config', {})
            show_values = chart_config.get('show_values', True)
            
            # 定义颜色
            chain_colors = {"IGH": "#1f77b4", "IGK": "#ff7f0e", "IGL": "#2ca02c"}
            
            # 查找基准样本索引
            baseline_idx = None
            actual_baseline = None
            if baseline_sample:
                # 模糊匹配基准样本
                baseline_lower = baseline_sample.lower().strip()
                for i, s in enumerate(samples):
                    if s.lower().strip() == baseline_lower:
                        baseline_idx = i
                        actual_baseline = s
                        break
                if baseline_idx is None and baseline_sample in samples:
                    baseline_idx = samples.index(baseline_sample)
                    actual_baseline = baseline_sample
            
            # 为每个指标创建一个图表（每个图包含3个子图，每个链一个）
            for metric in metrics:
                num_chains = len(chains)
                fig, axes = plt.subplots(1, num_chains, figsize=(8 * num_chains, 8))
                if num_chains == 1:
                    axes = [axes]
                
                title_suffix = f"\n(Baseline: {actual_baseline})" if actual_baseline else ""
                fig.suptitle(
                    f"IG {self.METRIC_DISPLAY_NAMES.get(metric, metric)} - Percentage Change from Baseline{title_suffix}",
                    fontsize=18, fontweight="bold", y=0.98
                )
                
                x_pos = np.arange(len(samples))
                bar_width = 0.6
                
                for chain_idx, chain in enumerate(chains):
                    ax = axes[chain_idx]
                    
                    # 获取该链该指标的所有样本值
                    values = []
                    for sample in samples:
                        sample_data = metrics_data.get(sample, {})
                        chain_data = sample_data.get(chain, {})
                        values.append(chain_data.get(metric, 0) or 0)
                    
                    # 计算百分比变化
                    if actual_baseline and baseline_idx is not None:
                        baseline_value = values[baseline_idx]
                        if baseline_value and baseline_value != 0:
                            pct_change = [(v - baseline_value) / baseline_value * 100 if v else 0 for v in values]
                        else:
                            pct_change = [0] * len(values)
                    else:
                        # 没有基准样本时显示原始值
                        pct_change = values
                    
                    # 绘制柱状图
                    bars = ax.bar(x_pos, pct_change, bar_width, 
                                  label=chain, color=chain_colors.get(chain, f'C{chain_idx}'), alpha=0.8)
                    
                    # 高亮基准样本
                    if baseline_idx is not None and baseline_idx < len(bars):
                        bars[baseline_idx].set_alpha(1.0)
                        bars[baseline_idx].set_edgecolor('black')
                        bars[baseline_idx].set_linewidth(2)
                    
                    # 添加0%基准线
                    if actual_baseline:
                        ax.axhline(y=0, color='gray', linestyle='-', linewidth=2, alpha=0.8)
                    
                    # 添加值标签
                    if show_values:
                        for j, bar in enumerate(bars):
                            height = bar.get_height()
                            if height != 0:
                                label = f"+{height:.1f}%" if height > 0 else f"{height:.1f}%"
                                va = 'bottom' if height >= 0 else 'top'
                                offset = abs(max(pct_change) - min(pct_change)) * 0.02 if pct_change else 1
                                y_pos = height + offset if height >= 0 else height - offset
                                ax.text(bar.get_x() + bar.get_width() / 2, y_pos, label,
                                       ha='center', va=va, fontsize=8, fontweight='bold',
                                       color=chain_colors.get(chain, 'black'))
                    
                    ax.set_xticks(x_pos)
                    ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=10)
                    ax.set_ylabel('Percentage Change from Baseline (%)' if actual_baseline else metric, 
                                 fontsize=12, fontweight='bold')
                    ax.set_xlabel('Sample', fontsize=12, fontweight='bold')
                    ax.set_title(f'{chain} Chain', fontsize=14, fontweight='bold', pad=10)
                    ax.grid(axis='y', alpha=0.3, linestyle='--')
                    ax.set_facecolor('#f8f9fa')
                    
                    # 设置Y轴范围
                    if pct_change:
                        ymin = min(pct_change) * 1.2 if min(pct_change) < 0 else -5
                        ymax = max(pct_change) * 1.2 if max(pct_change) > 0 else 5
                        ax.set_ylim(ymin, ymax)
                
                plt.tight_layout(rect=[0, 0, 1, 0.94])
                
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
                buf.seek(0)
                chart_base64 = base64.b64encode(buf.read()).decode('utf-8')
                plt.close(fig)
                
                charts.append({
                    'title': f'IG {self.METRIC_DISPLAY_NAMES.get(metric, metric)}',
                    'base64': chart_base64
                })
            
        except Exception as e:
            logger.error(f"Error generating charts: {e}", exc_info=True)
        
        return charts
