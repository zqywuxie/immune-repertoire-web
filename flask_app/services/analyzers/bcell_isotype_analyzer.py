"""
B Cell Isotype Analyzer - B细胞同型分布分析器
分析B细胞的6种同型分布数据（IgM, IgD, IgA1/2, IgG1/2, IgG3/4, IgE）

Refactored to use BaseAnalyzer interface.
Requirements: 7.1, 11.2
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


class BCellIsotypeAnalyzer(BaseAnalyzer):
    """
    B细胞同型分布分析器
    
    功能:
    - 提取6种同型的Expression %和Unique CDR3 %数据
    - 计算相对于基准样本的百分比差异
    - 生成分析结果数据
    
    Requirements: 7.1, 11.2
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
    
    def get_required_fields(self) -> List[str]:
        """
        获取必需字段列表
        
        Returns:
            必需字段列表（样本列）
        """
        return ["Sample"]
    
    def get_optional_fields(self) -> List[str]:
        """
        获取可选字段列表
        
        Returns:
            可选字段列表（同型相关字段）
        """
        optional = []
        for isotype in self.ISOTYPES:
            optional.append(f"{isotype}_Expression")
            optional.append(f"{isotype}_Unique_CDR3")
        return optional
    
    def get_default_parameters(self) -> Dict[str, Any]:
        """
        获取默认参数
        
        Returns:
            默认参数字典
        """
        return {
            "sample_column": "Sample",
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
        # 调用父类的基本验证
        result = super().validate_data(data)
        
        if not result.is_valid:
            return result
        
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
            result.errors.append("数据中没有找到B细胞同型相关的列")
            result.is_valid = False
        
        return result
    
    def analyze(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行B细胞同型分析
        
        Args:
            data: 输入的DataFrame
            parameters: 分析参数
            
        Returns:
            分析结果字典
            
        Requirements: 7.1
        """
        try:
            # 合并参数
            params = self.merge_parameters(parameters)
            
            sample_column = params.get('sample_column', 'Sample')
            baseline_sample = params.get('baseline_sample')
            sample_order = params.get('sample_order')
            sample_groups = params.get('sample_groups')
            
            # 提取同型数据
            isotype_data = self._extract_isotype_data(data, sample_column)
            
            # 获取样本列表
            samples = list(isotype_data.keys())
            
            # 应用自定义样本排序
            if sample_order:
                samples = self._apply_sample_order(samples, sample_order)
            
            # 计算百分比差异（如果指定了基准样本）
            percentage_diffs = None
            if baseline_sample:
                percentage_diffs = self._calculate_percentage_diff(
                    isotype_data, baseline_sample
                )
            
            # 计算分组统计
            group_statistics = None
            if sample_groups:
                group_statistics = self._calculate_group_statistics(
                    isotype_data, sample_groups
                )
            
            # 生成数据表格
            table_data = self._generate_table_data(
                isotype_data, samples, percentage_diffs
            )
            
            # 生成图表
            charts = self._generate_charts(isotype_data, samples, params, baseline_sample)
            
            return {
                "samples": samples,
                "isotypes": self.ISOTYPES,
                "isotype_data": isotype_data,
                "percentage_diffs": percentage_diffs,
                "baseline_sample": baseline_sample,
                "sample_order": sample_order,
                "group_statistics": group_statistics,
                "table_data": table_data,
                "charts": charts,
                "parameters": params
            }
            
        except Exception as e:
            logger.error(f"Error in B cell isotype analysis: {e}")
            raise RuntimeError(f"B cell isotype analysis failed: {str(e)}")
    
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
    
    def _extract_isotype_data(
        self,
        data: pd.DataFrame,
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        提取每个样本的同型分布数据
        
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
            direct_cols = self._find_isotype_columns(data)
            if direct_cols:
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
    
    def _calculate_percentage_diff(
        self,
        isotype_data: Dict[str, Dict[str, Dict[str, float]]],
        baseline_sample: str
    ) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
        """
        计算相对于基准样本的百分比差异
        
        公式: ((sample_value - baseline_value) / baseline_value) * 100
        
        Args:
            isotype_data: 同型数据
            baseline_sample: 基准样本名称
            
        Returns:
            字典格式: {sample_name: {isotype: {expression_diff: float, cdr3_diff: float}}}
        """
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
        isotype_data: Dict[str, Dict[str, Dict[str, float]]],
        sample_groups: Dict[str, List[str]]
    ) -> Dict[str, Dict[str, Dict[str, Dict[str, float]]]]:
        """计算分组统计"""
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
        """生成可复制的数据表格"""
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
        """将表格数据转换为制表符分隔格式"""
        lines = ["\t".join(str(h) for h in headers)]
        for row in rows:
            lines.append("\t".join(str(v) if v is not None else "" for v in row))
        return "\n".join(lines)
    
    def _generate_charts(
        self,
        isotype_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        params: Dict[str, Any],
        baseline_sample: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """生成B细胞同型分布图表 - 参考extract_bcell_isotype_final.py"""
        charts = []
        
        try:
            plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
            plt.rcParams["axes.unicode_minus"] = False
            
            # 同型颜色
            isotype_colors = {
                "IgM": "#1f77b4",
                "IgD": "#ff7f0e",
                "IgA1/2": "#2ca02c",
                "IgG1/2": "#d62728",
                "IgG3/4": "#9467bd",
                "IgE": "#8c564b"
            }
            
            # 查找基准样本索引
            baseline_idx = None
            if baseline_sample and baseline_sample in samples:
                baseline_idx = samples.index(baseline_sample)
            
            # 创建Expression图表
            fig_expr = self._create_isotype_chart(
                isotype_data, samples, "expression", 
                "B Cell Isotype Expression %", isotype_colors, baseline_sample, baseline_idx
            )
            if fig_expr:
                buf = io.BytesIO()
                fig_expr.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
                buf.seek(0)
                charts.append({
                    'title': 'B Cell Isotype Expression',
                    'base64': base64.b64encode(buf.read()).decode('utf-8')
                })
                plt.close(fig_expr)
            
            # 创建Unique CDR3图表
            fig_cdr3 = self._create_isotype_chart(
                isotype_data, samples, "unique_cdr3",
                "B Cell Isotype Unique CDR3 %", isotype_colors, baseline_sample, baseline_idx
            )
            if fig_cdr3:
                buf = io.BytesIO()
                fig_cdr3.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
                buf.seek(0)
                charts.append({
                    'title': 'B Cell Isotype Unique CDR3',
                    'base64': base64.b64encode(buf.read()).decode('utf-8')
                })
                plt.close(fig_cdr3)
            
        except Exception as e:
            logger.error(f"Error generating charts: {e}", exc_info=True)
        
        return charts
    
    def _create_isotype_chart(
        self,
        isotype_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        data_type: str,
        title: str,
        colors: Dict[str, str],
        baseline_sample: Optional[str],
        baseline_idx: Optional[int]
    ):
        """创建同型分布图表"""
        num_isotypes = len(self.ISOTYPES)
        cols = min(num_isotypes, 3)
        rows = (num_isotypes + 2) // 3
        
        fig, axes = plt.subplots(rows, cols, figsize=(8 * cols, 6 * rows))
        axes = axes.flatten() if num_isotypes > 1 else [axes]
        
        title_suffix = f"\n(Baseline: {baseline_sample})" if baseline_sample else ""
        fig.suptitle(f"{title}{title_suffix}", fontsize=18, fontweight='bold', y=0.98)
        
        x_pos = np.arange(len(samples))
        bar_width = 0.6
        
        for idx, isotype in enumerate(self.ISOTYPES):
            if idx >= len(axes):
                break
            ax = axes[idx]
            
            # 获取值
            values = []
            for sample in samples:
                sample_data = isotype_data.get(sample, {})
                iso_data = sample_data.get(isotype, {})
                value = iso_data.get(data_type, 0)
                values.append(value if value is not None else 0)
            
            # 计算百分比变化
            if baseline_idx is not None and values[baseline_idx] != 0:
                baseline_value = values[baseline_idx]
                pct_change = [(v - baseline_value) / baseline_value * 100 if baseline_value != 0 else 0 for v in values]
                ylabel = "Percentage Change from Baseline (%)"
            else:
                pct_change = values
                ylabel = "Percentage (%)"
            
            bars = ax.bar(x_pos, pct_change, bar_width, color=colors.get(isotype, '#999999'), alpha=0.8)
            
            # 高亮基准样本
            if baseline_idx is not None and baseline_idx < len(bars):
                bars[baseline_idx].set_edgecolor("black")
                bars[baseline_idx].set_linewidth(2)
                ax.axhline(y=0, color="gray", linestyle="-", linewidth=1.5, alpha=0.8)
            
            ax.set_xticks(x_pos)
            ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=9)
            ax.set_ylabel(ylabel, fontsize=11, fontweight='bold')
            ax.set_xlabel('Sample', fontsize=11, fontweight='bold')
            ax.set_title(isotype, fontsize=14, fontweight='bold')
            ax.grid(axis='y', alpha=0.3, linestyle='--')
            ax.set_facecolor('#f8f9fa')
        
        # 隐藏多余的子图
        for idx in range(num_isotypes, len(axes)):
            axes[idx].set_visible(False)
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        return fig
