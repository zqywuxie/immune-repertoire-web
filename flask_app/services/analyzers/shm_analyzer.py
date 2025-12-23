"""
SHM Analyzer - 体细胞超突变分析器
分析SHM0和SHM1数据，计算百分比变化

Refactored to use BaseAnalyzer interface.
Requirements: 7.2, 11.2
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


class SHMAnalyzer(BaseAnalyzer):
    """
    SHM体细胞超突变分析器
    
    功能:
    - 验证数据是否包含所需的SHM字段
    - 计算相对于基准样本的百分比变化
    - 生成分析结果数据
    
    Requirements: 7.2, 11.2
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
    
    def get_required_fields(self) -> List[str]:
        """
        获取必需字段列表
        
        Returns:
            必需字段列表
        """
        return ["Sample"] + self.REQUIRED_SHM_COLUMNS
    
    def get_optional_fields(self) -> List[str]:
        """
        获取可选字段列表
        
        Returns:
            可选字段列表
        """
        return ["Group", "Timepoint", "Condition"]
    
    def get_default_parameters(self) -> Dict[str, Any]:
        """
        获取默认参数
        
        Returns:
            默认参数字典
        """
        return {
            "sample_column": "Sample",
            "baseline_sample": None,
            "isotypes": None,  # None means all isotypes
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
        
        # 验证SHM字段
        is_valid, present_fields, missing_fields = self._validate_shm_fields(data)
        
        if not is_valid:
            errors.append(f"缺少必需的SHM字段: {', '.join(missing_fields)}")
        
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings
        )
    
    def _validate_shm_fields(self, data: pd.DataFrame) -> Tuple[bool, List[str], List[str]]:
        """
        验证数据是否包含所需的SHM字段
        
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
    
    def analyze(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行SHM分析
        
        Args:
            data: 输入的DataFrame
            parameters: 分析参数
            
        Returns:
            分析结果字典
            
        Requirements: 7.2
        """
        try:
            # 合并参数
            params = self.merge_parameters(parameters)
            
            sample_column = params.get('sample_column', 'Sample')
            baseline_sample = params.get('baseline_sample')
            sample_order = params.get('sample_order')
            sample_groups = params.get('sample_groups')
            
            # 提取SHM数据
            shm_data = self._extract_shm_data(data, sample_column)
            
            # 获取样本列表
            samples = list(shm_data.keys())
            
            # 应用自定义样本排序
            if sample_order:
                samples = self._apply_sample_order(samples, sample_order)
            
            # 计算百分比变化（如果指定了基准样本）
            percentage_changes = None
            if baseline_sample:
                percentage_changes = self._calculate_percentage_changes(
                    shm_data, baseline_sample
                )
            
            # 计算分组统计
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
            
            # 生成图表
            charts = self._generate_charts(shm_data, samples, isotype_labels, params, baseline_sample)
            
            return {
                "samples": samples,
                "isotype_labels": isotype_labels,
                "shm_data": shm_data,
                "percentage_changes": percentage_changes,
                "baseline_sample": baseline_sample,
                "sample_order": sample_order,
                "group_statistics": group_statistics,
                "table_data": table_data,
                "charts": charts,
                "parameters": params
            }
            
        except Exception as e:
            logger.error(f"Error in SHM analysis: {e}")
            raise RuntimeError(f"SHM analysis failed: {str(e)}")
    
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
    
    def _extract_shm_data(
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
        
        for idx, row in data.iterrows():
            # 获取样本名，确保是单个值而不是Series
            sample_value = row[actual_sample_col]
            if hasattr(sample_value, 'iloc'):
                sample_name = str(sample_value.iloc[0])
            elif hasattr(sample_value, 'values'):
                sample_name = str(sample_value.values[0]) if len(sample_value.values) > 0 else str(idx)
            else:
                sample_name = str(sample_value)
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
    
    def _calculate_percentage_changes(
        self,
        shm_data: Dict[str, Dict[str, Dict[str, float]]],
        baseline_sample: str
    ) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
        """
        计算相对于基准样本的百分比变化
        
        公式: ((sample_value - baseline_value) / baseline_value) * 100
        
        Args:
            shm_data: SHM数据
            baseline_sample: 基准样本名称
            
        Returns:
            字典格式: {sample_name: {isotype_label: {shm0_pct_change: float, shm1_pct_change: float}}}
        """
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
        shm_data: Dict[str, Dict[str, Dict[str, float]]],
        sample_groups: Dict[str, List[str]]
    ) -> Dict[str, Dict[str, Dict[str, Dict[str, float]]]]:
        """计算分组统计"""
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
        """生成可复制的数据表格（只包含原始数据，不包含百分比变化）"""
        # 构建表头
        headers = ["Sample"]
        for _, _, label in self.SHM_FIELDS:
            headers.append(f"{label}_SHM0")
            headers.append(f"{label}_SHM1")
        
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
        shm_data: Dict[str, Dict[str, Dict[str, float]]],
        samples: List[str],
        isotype_labels: List[str],
        params: Dict[str, Any],
        baseline_sample: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """生成SHM分析图表 - 参考Final_Versions_Scripts/extract_shm_fields_final.py"""
        charts = []
        
        try:
            # 设置中文字体
            plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
            plt.rcParams["axes.unicode_minus"] = False
            
            chart_config = params.get('chart_config', {})
            figsize = chart_config.get('figsize', [20, 16])
            baseline_sample = params.get('baseline_sample') or baseline_sample
            
            # 定义颜色
            color_list = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
            
            # 确定基准样本索引
            baseline_idx = None
            if baseline_sample and baseline_sample in samples:
                baseline_idx = samples.index(baseline_sample)
            
            # 创建2x2子图
            fig, axes = plt.subplots(2, 2, figsize=(figsize[0], figsize[1]))
            
            title = "IG Somatic Hypermutation Analysis"
            if baseline_sample and baseline_idx is not None:
                title = f"IG Somatic Hypermutation - Percentage Change from Baseline\n(Baseline: {baseline_sample})"
            
            fig.suptitle(title, fontsize=18, fontweight="bold", y=0.98)
            axes = axes.flatten()
            
            x_pos = np.arange(len(samples))
            bar_width = 0.35
            
            # 为每个isotype创建子图
            for idx, label in enumerate(isotype_labels[:4]):  # 最多4个子图
                ax = axes[idx]
                color = color_list[idx % len(color_list)]
                
                # 获取每个样本的SHM0和SHM1值
                shm0_values = []
                shm1_values = []
                for sample in samples:
                    iso_data = shm_data.get(sample, {}).get(label, {})
                    shm0_values.append(iso_data.get('shm0', 0) or 0)
                    shm1_values.append(iso_data.get('shm1', 0) or 0)
                
                # 如果有基准样本，计算百分比变化
                if baseline_idx is not None:
                    baseline_shm0 = shm0_values[baseline_idx]
                    baseline_shm1 = shm1_values[baseline_idx]
                    
                    if baseline_shm0 != 0:
                        shm0_values = [(v - baseline_shm0) / baseline_shm0 * 100 for v in shm0_values]
                    if baseline_shm1 != 0:
                        shm1_values = [(v - baseline_shm1) / baseline_shm1 * 100 for v in shm1_values]
                    
                    ylabel = "Percentage Change from Baseline (%)"
                else:
                    ylabel = "SHM Value"
                
                # 创建柱状图
                bars0 = ax.bar(
                    x_pos - bar_width / 2,
                    shm0_values,
                    bar_width,
                    label=f"{label} SHM0",
                    color=color,
                    alpha=0.8,
                )
                bars1 = ax.bar(
                    x_pos + bar_width / 2,
                    shm1_values,
                    bar_width,
                    label=f"{label} SHM1",
                    color=color,
                    alpha=0.6,
                    hatch="//",
                )
                
                # 高亮基准样本
                if baseline_idx is not None:
                    bars0[baseline_idx].set_edgecolor("black")
                    bars0[baseline_idx].set_linewidth(2)
                    bars1[baseline_idx].set_edgecolor("black")
                    bars1[baseline_idx].set_linewidth(2)
                    # 添加基准线
                    ax.axhline(y=0, color="gray", linestyle="-", linewidth=1.5, alpha=0.8)
                
                # 设置子图属性
                ax.set_xticks(x_pos)
                ax.set_xticklabels(samples, rotation=45, ha="right", fontsize=9)
                ax.set_ylabel(ylabel, fontsize=11, fontweight="bold")
                ax.set_xlabel("Sample", fontsize=11, fontweight="bold")
                ax.set_title(f"{label} SHM Levels", fontsize=13, fontweight="bold", pad=10)
                ax.legend(fontsize=9, frameon=True)
                ax.grid(axis="y", alpha=0.3, linestyle="--")
                ax.set_facecolor("#f8f9fa")
            
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            
            # 转换为base64
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
            buf.seek(0)
            chart_base64 = base64.b64encode(buf.read()).decode('utf-8')
            plt.close(fig)
            
            charts.append({
                'title': 'IG SHM Analysis',
                'base64': chart_base64
            })
            
        except Exception as e:
            logger.error(f"Error generating charts: {e}", exc_info=True)
        
        return charts
