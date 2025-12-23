"""
Custom Field Analyzer - 自定义字段分析器
支持灵活的字段选择和多种图表类型

Requirements: 7.4
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
import logging

from .base_analyzer import BaseAnalyzer, ValidationResult

logger = logging.getLogger(__name__)


class CustomFieldAnalyzer(BaseAnalyzer):
    """
    自定义字段分析器
    
    功能:
    - 支持用户自定义选择任意数值字段进行分析
    - 提取指定字段的数据
    - 计算相对于基准样本的百分比差异
    - 支持多种图表类型（柱状图、折线图、分组柱状图等）
    - 生成分析结果数据
    
    Requirements: 7.4
    """
    
    # 支持的图表类型
    SUPPORTED_CHART_TYPES = ["bar", "line", "grouped_bar", "scatter", "heatmap"]
    
    def get_required_fields(self) -> List[str]:
        """
        获取必需字段列表
        
        Returns:
            必需字段列表（样本列）
            
        Note:
            自定义字段分析器只需要样本列，其他字段由用户指定
        """
        return ["Sample"]
    
    def get_optional_fields(self) -> List[str]:
        """
        获取可选字段列表
        
        Returns:
            空列表（所有字段都是可选的，由用户指定）
        """
        return []
    
    def get_default_parameters(self) -> Dict[str, Any]:
        """
        获取默认参数
        
        Returns:
            默认参数字典
        """
        return {
            "sample_column": "Sample",
            "fields": [],  # 要分析的字段列表（必须由用户指定）
            "baseline_sample": None,
            "sample_order": None,
            "sample_groups": None,
            "chart_type": "bar",  # bar, line, grouped_bar, scatter, heatmap
            "show_percentage_diff": False,
            "aggregation_method": "mean"  # mean, median, sum, min, max
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
        
        # 检查是否有数值列
        numeric_cols = self._identify_numeric_fields(data)
        if not numeric_cols:
            errors.append("数据中没有数值类型的列")
        
        is_valid = len(errors) == 0
        
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings
        )
    
    def analyze(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行自定义字段分析
        
        Args:
            data: 输入的DataFrame
            parameters: 分析参数，必须包含 'fields' 参数
            
        Returns:
            分析结果字典
            
        Raises:
            ValueError: 当未指定字段或字段无效时
            
        Requirements: 7.4
        """
        try:
            # 合并参数
            params = self.merge_parameters(parameters)
            
            sample_column = params.get('sample_column', 'Sample')
            fields = params.get('fields', [])
            baseline_sample = params.get('baseline_sample')
            sample_order = params.get('sample_order')
            sample_groups = params.get('sample_groups')
            chart_type = params.get('chart_type', 'bar')
            show_percentage_diff = params.get('show_percentage_diff', False)
            
            # 验证字段参数
            if not fields:
                raise ValueError("必须指定要分析的字段列表（fields参数）")
            
            # 验证字段是否存在
            missing_fields = [f for f in fields if f not in data.columns]
            if missing_fields:
                raise ValueError(f"以下字段在数据中不存在: {', '.join(missing_fields)}")
            
            # 验证图表类型
            if chart_type not in self.SUPPORTED_CHART_TYPES:
                logger.warning(f"不支持的图表类型 '{chart_type}'，使用默认类型 'bar'")
                chart_type = "bar"
            
            # 提取字段数据
            field_data = self._extract_field_data(data, fields, sample_column)
            
            # 获取样本列表
            samples = list(field_data.keys())
            
            # 应用自定义样本排序
            if sample_order:
                samples = self._apply_sample_order(samples, sample_order)
            
            # 计算百分比差异（如果指定了基准样本）
            percentage_diffs = None
            if baseline_sample and show_percentage_diff:
                percentage_diffs = self._calculate_percentage_diffs(
                    field_data, fields, baseline_sample
                )
            
            # 计算分组统计
            group_statistics = None
            if sample_groups:
                group_statistics = self._calculate_group_statistics(
                    field_data, sample_groups, fields
                )
            
            # 识别字段类型
            field_types = self._identify_field_types(data, fields)
            
            # 生成数据表格
            table_data = self._generate_table_data(
                field_data, fields, samples, percentage_diffs
            )
            
            return {
                "samples": samples,
                "fields": fields,
                "field_types": field_types,
                "field_data": field_data,
                "percentage_diffs": percentage_diffs,
                "baseline_sample": baseline_sample,
                "sample_order": sample_order,
                "group_statistics": group_statistics,
                "chart_type": chart_type,
                "table_data": table_data,
                "parameters": params
            }
            
        except Exception as e:
            logger.error(f"Error in custom field analysis: {e}")
            raise RuntimeError(f"Custom field analysis failed: {str(e)}")
    
    def _identify_numeric_fields(self, data: pd.DataFrame) -> List[str]:
        """
        识别数据中的所有数值类型字段
        
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
    
    def _identify_field_types(
        self,
        data: pd.DataFrame,
        fields: List[str]
    ) -> Dict[str, str]:
        """
        识别字段的数据类型
        
        Args:
            data: 输入的DataFrame
            fields: 字段列表
            
        Returns:
            字段类型字典 {field_name: type}
        """
        field_types = {}
        
        for field in fields:
            if field not in data.columns:
                field_types[field] = "unknown"
                continue
            
            dtype = data[field].dtype
            
            if pd.api.types.is_integer_dtype(dtype):
                field_types[field] = "integer"
            elif pd.api.types.is_float_dtype(dtype):
                field_types[field] = "float"
            elif pd.api.types.is_bool_dtype(dtype):
                field_types[field] = "boolean"
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                field_types[field] = "datetime"
            else:
                field_types[field] = "string"
        
        return field_types
    
    def _extract_field_data(
        self,
        data: pd.DataFrame,
        fields: List[str],
        sample_column: str = "Sample"
    ) -> Dict[str, Dict[str, float]]:
        """
        提取指定字段的数据
        
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
    
    def _calculate_percentage_diffs(
        self,
        field_data: Dict[str, Dict[str, float]],
        fields: List[str],
        baseline_sample: str
    ) -> Dict[str, Dict[str, Optional[float]]]:
        """
        计算所有字段相对于基准样本的百分比差异
        
        公式: ((sample_value - baseline_value) / baseline_value) * 100
        
        Args:
            field_data: 字段数据
            fields: 字段列表
            baseline_sample: 基准样本名称
            
        Returns:
            字典格式: {sample_name: {field_name: percentage_diff}}
        """
        if baseline_sample not in field_data:
            logger.warning(f"Baseline sample '{baseline_sample}' not found")
            return {}
        
        baseline_data = field_data[baseline_sample]
        result = {}
        
        for sample_name, sample_data in field_data.items():
            result[sample_name] = {}
            
            for field in fields:
                sample_value = sample_data.get(field)
                baseline_value = baseline_data.get(field)
                
                if (sample_value is not None and 
                    baseline_value is not None and 
                    baseline_value != 0):
                    pct_diff = ((sample_value - baseline_value) / baseline_value) * 100
                    result[sample_name][field] = round(pct_diff, 2)
                else:
                    result[sample_name][field] = None
        
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
        field_data: Dict[str, Dict[str, float]],
        sample_groups: Dict[str, List[str]],
        fields: List[str]
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        计算分组统计
        
        Args:
            field_data: 字段数据
            sample_groups: 样本分组配置 {group_name: [sample_names]}
            fields: 字段列表
            
        Returns:
            字典格式: {group_name: {field_name: {mean, std, min, max, median, count}}}
        """
        result = {}
        
        for group_name, sample_list in sample_groups.items():
            result[group_name] = {}
            
            for field in fields:
                values = []
                
                for sample in sample_list:
                    if sample in field_data:
                        value = field_data[sample].get(field)
                        if value is not None:
                            values.append(value)
                
                if values:
                    result[group_name][field] = {
                        'mean': round(float(np.mean(values)), 4),
                        'std': round(float(np.std(values)), 4) if len(values) > 1 else 0.0,
                        'min': round(float(np.min(values)), 4),
                        'max': round(float(np.max(values)), 4),
                        'median': round(float(np.median(values)), 4),
                        'count': len(values)
                    }
                else:
                    result[group_name][field] = {
                        'mean': None,
                        'std': None,
                        'min': None,
                        'max': None,
                        'median': None,
                        'count': 0
                    }
        
        return result
    
    def _generate_table_data(
        self,
        field_data: Dict[str, Dict[str, float]],
        fields: List[str],
        samples: List[str],
        percentage_diffs: Optional[Dict[str, Dict[str, float]]] = None
    ) -> Dict[str, Any]:
        """生成可复制的数据表格"""
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
                if value is not None:
                    row.append(f"{value:.4f}")
                else:
                    row.append("")
            
            # 添加百分比差异
            if percentage_diffs:
                for field in fields:
                    diff = percentage_diffs.get(sample, {}).get(field)
                    if diff is not None:
                        row.append(f"{diff:+.2f}%")
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
    
    def get_available_fields(self, data: pd.DataFrame) -> Dict[str, List[str]]:
        """
        获取数据中可用的字段列表（按类型分组）
        
        Args:
            data: 输入的DataFrame
            
        Returns:
            字段列表字典 {type: [field_names]}
        """
        numeric_fields = self._identify_numeric_fields(data)
        all_fields = list(data.columns)
        non_numeric_fields = [f for f in all_fields if f not in numeric_fields]
        
        return {
            "numeric": numeric_fields,
            "non_numeric": non_numeric_fields,
            "all": all_fields
        }
