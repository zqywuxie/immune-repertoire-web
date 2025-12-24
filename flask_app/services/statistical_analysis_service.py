"""
Statistical Analysis Service.
Provides high-level API for statistical comparison analysis.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
import logging
import io
import base64

logger = logging.getLogger(__name__)

_service_instance = None


class StatisticalAnalysisService:
    """统计分析服务 - 提供组间比较和P值计算功能"""
    
    def __init__(self):
        self.module = None
        self._init_module()
    
    def _init_module(self):
        """初始化统计比较模块"""
        try:
            from services.analysis.modules.statistical_comparison import StatisticalComparisonModule
            self.module = StatisticalComparisonModule()
        except Exception as e:
            logger.error(f"Failed to initialize StatisticalComparisonModule: {e}")
    
    def analyze_groups(self, data: pd.DataFrame, 
                       value_column: str,
                       group_column: str = 'category',
                       group_order: List[str] = None,
                       alpha: float = 0.05) -> Dict[str, Any]:
        """
        对分组数据进行统计分析
        
        Args:
            data: 包含数据的DataFrame
            value_column: 数值列名（如 'expression' 或 'count'）
            group_column: 分组列名
            group_order: 分组顺序（可选）
            alpha: 显著性水平
            
        Returns:
            包含统计结果的字典
        """
        if self.module is None:
            return {'success': False, 'error': '统计模块未初始化'}
        
        params = {
            'value_column': value_column,
            'group_column': group_column,
            'group_order': group_order,
            'alpha': alpha
        }
        
        is_valid, msg = self.module.validate_data(data)
        if not is_valid:
            return {'success': False, 'error': msg}
        
        return self.module.analyze(data, params)
    
    def create_boxplot(self, data: pd.DataFrame,
                       value_column: str,
                       group_column: str = 'category',
                       group_order: List[str] = None,
                       title: str = None,
                       palette: Dict[str, str] = None) -> str:
        """
        创建箱线图
        
        Args:
            data: 数据DataFrame
            value_column: 数值列名
            group_column: 分组列名
            group_order: 分组顺序
            title: 图表标题
            palette: 颜色映射
            
        Returns:
            Base64编码的图片字符串
        """
        if self.module is None:
            return ""
        
        params = {
            'value_column': value_column,
            'group_column': group_column,
            'group_order': group_order,
            'palette': palette or {
                'Baseline': '#4C72B0',
                '0-1h': '#55A868',
                '24h': '#C44E52',
                '48h': '#8172B3'
            }
        }
        
        results = self.analyze_groups(data, value_column, group_column, group_order)
        
        return self.module.create_boxplot(data, params, results, title)
    
    def analyze_multiple_datasets(self, datasets: Dict[str, pd.DataFrame],
                                   value_column: str,
                                   group_column: str = 'category',
                                   group_order: List[str] = None,
                                   global_correction: bool = False) -> Dict[str, Any]:
        """
        分析多个数据集
        
        Args:
            datasets: 数据集字典 {name: DataFrame}
            value_column: 数值列名
            group_column: 分组列名
            group_order: 分组顺序
            global_correction: 是否进行全局P值校正（汇总后统一校正）
            
        Returns:
            包含所有数据集分析结果的字典
        """
        all_results = {}
        
        for name, data in datasets.items():
            result = self.analyze_groups(data, value_column, group_column, group_order)
            all_results[name] = result
        
        # 如果启用全局校正，对所有P值进行统一FDR校正
        if global_correction:
            all_results = self._apply_global_correction(all_results)
        
        return {
            'success': True,
            'results': all_results,
            'summary': self._create_summary(all_results),
            'correction_mode': 'global' if global_correction else 'per_dataset'
        }
    
    def _apply_global_correction(self, all_results: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        对所有数据集的P值进行全局FDR校正
        
        收集所有Kruskal-Wallis P值和事后比较P值，统一进行校正
        """
        try:
            from statsmodels.stats.multitest import multipletests
        except ImportError:
            logger.warning("statsmodels not installed, skipping global correction")
            return all_results
        
        # 收集所有P值及其来源信息
        all_p_values = []
        p_value_sources = []  # 记录每个P值的来源 (dataset_name, type, index)
        
        for name, result in all_results.items():
            if not result.get('success', False):
                continue
            
            # Kruskal-Wallis P值
            kw = result.get('kruskal_wallis', {})
            if 'p_value' in kw:
                all_p_values.append(kw['p_value'])
                p_value_sources.append((name, 'kw', None))
            
            # 事后比较P值
            pairwise = result.get('pairwise_comparisons', [])
            for idx, comp in enumerate(pairwise):
                if 'p_value' in comp:
                    all_p_values.append(comp['p_value'])
                    p_value_sources.append((name, 'pairwise', idx))
        
        if not all_p_values:
            return all_results
        
        # 进行全局FDR校正
        try:
            rejected, p_corrected, _, _ = multipletests(all_p_values, method='fdr_bh')
            
            # 将校正后的P值写回结果
            for i, (name, p_type, idx) in enumerate(p_value_sources):
                if p_type == 'kw':
                    all_results[name]['kruskal_wallis']['p_value_corrected'] = float(p_corrected[i])
                    all_results[name]['kruskal_wallis']['significant_corrected'] = bool(rejected[i])
                elif p_type == 'pairwise' and idx is not None:
                    all_results[name]['pairwise_comparisons'][idx]['p_value_global_corrected'] = float(p_corrected[i])
                    all_results[name]['pairwise_comparisons'][idx]['significant_global_corrected'] = bool(rejected[i])
            
            logger.info(f"Applied global FDR correction to {len(all_p_values)} p-values")
            
        except Exception as e:
            logger.error(f"Global correction failed: {e}")
        
        return all_results
    
    def create_summary_boxplot(self, datasets: Dict[str, pd.DataFrame],
                                value_column: str,
                                group_column: str = 'category',
                                group_order: List[str] = None,
                                title: str = "Summary",
                                palette: Dict[str, str] = None) -> str:
        """
        创建汇总箱线图
        
        Args:
            datasets: 数据集字典
            value_column: 数值列名
            group_column: 分组列名
            group_order: 分组顺序
            title: 图表标题
            palette: 颜色映射
            
        Returns:
            Base64编码的图片字符串
        """
        if self.module is None:
            return ""
        
        params = {
            'value_column': value_column,
            'group_column': group_column,
            'group_order': group_order,
            'palette': palette or {
                'Baseline': '#4C72B0',
                '0-1h': '#55A868',
                '24h': '#C44E52',
                '48h': '#8172B3'
            }
        }
        
        all_results = {}
        for name, data in datasets.items():
            all_results[name] = self.analyze_groups(data, value_column, group_column, group_order)
        
        return self.module.create_summary_boxplot(datasets, all_results, params, title)
    
    def _create_summary(self, all_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """创建分析结果摘要"""
        summary = {
            'total_datasets': len(all_results),
            'significant_datasets': 0,
            'datasets_summary': []
        }
        
        for name, result in all_results.items():
            kw = result.get('kruskal_wallis', {})
            is_sig = kw.get('significant', False)
            
            if is_sig:
                summary['significant_datasets'] += 1
            
            summary['datasets_summary'].append({
                'name': name,
                'p_value': kw.get('p_value'),
                'significant': is_sig,
                'n_groups': kw.get('n_groups', 0)
            })
        
        return summary


def get_statistical_analysis_service() -> StatisticalAnalysisService:
    """获取统计分析服务单例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = StatisticalAnalysisService()
    return _service_instance


def init_statistical_analysis_service(app=None):
    """初始化统计分析服务"""
    global _service_instance
    _service_instance = StatisticalAnalysisService()
    logger.info("Statistical analysis service initialized")
    return _service_instance
