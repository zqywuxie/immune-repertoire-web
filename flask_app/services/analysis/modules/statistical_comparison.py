"""
Statistical Comparison Analysis Module.
Performs Kruskal-Wallis test and Dunn's post-hoc test for comparing groups.
Generates boxplots with P-values.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from scipy.stats import kruskal
from typing import Dict, Any, List, Tuple, Optional
import logging

from flask_app.services.analysis.base_module import AnalysisModule, AnalysisResult

logger = logging.getLogger(__name__)


class StatisticalComparisonModule(AnalysisModule):
    """统计比较分析模块 - 组间差异比较与P值计算"""
    
    def get_name(self) -> str:
        return "statistical_comparison"
    
    def get_display_name(self) -> str:
        return "统计比较分析"
    
    def get_description(self) -> str:
        return "对不同分组进行统计比较，计算P值并生成箱线图可视化"
    
    def get_category(self) -> str:
        return "统计分析"
    
    def get_required_columns(self) -> List[str]:
        return ['category']
    
    def get_optional_columns(self) -> List[str]:
        return ['sample', 'expression', 'count']
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            'value_column': 'expression',
            'group_column': 'category',
            'group_order': None,
            'alpha': 0.05,
            'correction_method': 'fdr_bh',
            'palette': {
                'Baseline': '#4C72B0',
                '0-1h': '#55A868',
                '24h': '#C44E52',
                '48h': '#8172B3'
            }
        }
    
    def validate_data(self, data: pd.DataFrame) -> Tuple[bool, str]:
        """验证输入数据"""
        if data.empty:
            return False, "数据为空"
        
        required_cols = self.get_required_columns()
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            return False, f"缺少必需的列: {', '.join(missing_cols)}"
        
        return True, "数据验证通过"
    
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行统计分析"""
        value_col = params.get('value_column', 'expression')
        group_col = params.get('group_column', 'category')
        alpha = params.get('alpha', 0.05)
        
        if value_col not in data.columns:
            return {
                'success': False,
                'error': f"数值列 '{value_col}' 不存在于数据中"
            }
        
        results = {
            'success': True,
            'value_column': value_col,
            'group_column': group_col,
            'groups': [],
            'kruskal_wallis': {},
            'pairwise_comparisons': [],
            'descriptive_stats': [],
            'normality_tests': []
        }
        
        groups = data[group_col].unique().tolist()
        results['groups'] = groups
        
        group_data = {g: data[data[group_col] == g][value_col].dropna().values 
                      for g in groups}
        
        valid_groups = {k: v for k, v in group_data.items() if len(v) >= 2}
        
        if len(valid_groups) < 2:
            return {
                'success': False,
                'error': "需要至少2个有效分组（每组至少2个样本）进行统计比较"
            }
        
        for group_name, values in valid_groups.items():
            desc_stat = {
                'group': group_name,
                'n': len(values),
                'mean': float(np.mean(values)),
                'std': float(np.std(values, ddof=1)) if len(values) > 1 else 0,
                'median': float(np.median(values)),
                'min': float(np.min(values)),
                'max': float(np.max(values)),
                'q1': float(np.percentile(values, 25)),
                'q3': float(np.percentile(values, 75))
            }
            results['descriptive_stats'].append(desc_stat)
            
            if len(values) >= 3:
                try:
                    stat, p_val = stats.shapiro(values)
                    results['normality_tests'].append({
                        'group': group_name,
                        'statistic': float(stat),
                        'p_value': float(p_val),
                        'is_normal': bool(p_val > alpha)
                    })
                except Exception as e:
                    logger.warning(f"Shapiro-Wilk test failed for {group_name}: {e}")
        
        try:
            group_values = list(valid_groups.values())
            statistic, p_value = kruskal(*group_values)
            results['kruskal_wallis'] = {
                'statistic': float(statistic),
                'p_value': float(p_value),
                'significant': bool(p_value < alpha),
                'n_groups': len(valid_groups)
            }
        except Exception as e:
            logger.error(f"Kruskal-Wallis test failed: {e}")
            results['kruskal_wallis'] = {
                'error': str(e)
            }
            return results
        
        if p_value < alpha:
            try:
                from scikit_posthocs import posthoc_dunn
                
                analysis_df = data[[group_col, value_col]].dropna()
                analysis_df = analysis_df[analysis_df[group_col].isin(valid_groups.keys())]
                
                dunn_results = posthoc_dunn(
                    analysis_df, 
                    val_col=value_col, 
                    group_col=group_col, 
                    p_adjust=None
                )
                
                group_list = list(valid_groups.keys())
                for i, g1 in enumerate(group_list):
                    for j, g2 in enumerate(group_list):
                        if i < j:
                            try:
                                p_val = dunn_results.loc[g1, g2]
                                results['pairwise_comparisons'].append({
                                    'group1': g1,
                                    'group2': g2,
                                    'p_value': float(p_val),
                                    'significant': bool(p_val < alpha)
                                })
                            except Exception as e:
                                logger.warning(f"Failed to get p-value for {g1} vs {g2}: {e}")
                
                if results['pairwise_comparisons']:
                    p_values = [c['p_value'] for c in results['pairwise_comparisons']]
                    correction_method = params.get('correction_method', 'fdr_bh')
                    
                    try:
                        from statsmodels.stats.multitest import multipletests
                        rejected, p_corrected, _, _ = multipletests(
                            p_values, 
                            method=correction_method
                        )
                        
                        for idx, comp in enumerate(results['pairwise_comparisons']):
                            comp['p_value_corrected'] = float(p_corrected[idx])
                            comp['significant_corrected'] = bool(rejected[idx])
                    except Exception as e:
                        logger.warning(f"Multiple testing correction failed: {e}")
                        
            except ImportError:
                logger.warning("scikit-posthocs not installed, skipping post-hoc tests")
            except Exception as e:
                logger.error(f"Post-hoc test failed: {e}")
        
        return results
    
    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        figures = {}
        
        if not results.get('success', False):
            return figures
        
        return figures
    
    def create_boxplot(self, data: pd.DataFrame, params: Dict[str, Any], 
                       results: Dict[str, Any], title: str = None) -> str:
        """创建箱线图并返回base64编码"""
        value_col = params.get('value_column', 'expression')
        group_col = params.get('group_column', 'category')
        group_order = params.get('group_order')
        palette = params.get('palette', {})
        
        if group_order is None:
            group_order = data[group_col].unique().tolist()
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        if palette:
            plot_palette = {k: v for k, v in palette.items() if k in group_order}
        else:
            plot_palette = None
        
        sns.boxplot(
            data=data, 
            x=group_col, 
            y=value_col,
            order=group_order,
            palette=plot_palette,
            showfliers=False,
            ax=ax
        )
        
        sns.stripplot(
            data=data, 
            x=group_col, 
            y=value_col,
            order=group_order,
            color='black', 
            alpha=0.7, 
            jitter=0.2, 
            size=6,
            ax=ax
        )
        
        kw_result = results.get('kruskal_wallis', {})
        p_value = kw_result.get('p_value', 1.0)
        
        if title:
            plot_title = f"{title}\nKruskal-Wallis p = {p_value:.4f}"
        else:
            plot_title = f"Kruskal-Wallis p = {p_value:.4f}"
        
        ax.set_title(plot_title, fontsize=12)
        ax.set_xlabel(group_col, fontsize=11)
        ax.set_ylabel(value_col, fontsize=11)
        ax.tick_params(axis='x', rotation=0, labelsize=10)
        
        plt.tight_layout()
        
        base64_str = self._figure_to_base64(fig)
        return base64_str
    
    def create_summary_boxplot(self, all_data: Dict[str, pd.DataFrame], 
                                all_results: Dict[str, Dict[str, Any]],
                                params: Dict[str, Any],
                                title: str = "Summary") -> str:
        """创建汇总箱线图（多个子图）"""
        value_col = params.get('value_column', 'expression')
        group_col = params.get('group_column', 'category')
        group_order = params.get('group_order')
        palette = params.get('palette', {})
        
        n_plots = len(all_data)
        if n_plots == 0:
            return ""
        
        ncols = min(2, n_plots)
        nrows = (n_plots + ncols - 1) // ncols
        
        fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 5 * nrows))
        
        if n_plots == 1:
            axes = [axes]
        else:
            axes = axes.ravel() if hasattr(axes, 'ravel') else [axes]
        
        for idx, (name, df) in enumerate(all_data.items()):
            ax = axes[idx]
            
            if group_order is None:
                order = df[group_col].unique().tolist()
            else:
                order = group_order
            
            if palette:
                plot_palette = {k: v for k, v in palette.items() if k in order}
            else:
                plot_palette = None
            
            sns.boxplot(
                data=df, 
                x=group_col, 
                y=value_col,
                order=order,
                palette=plot_palette,
                showfliers=False,
                ax=ax
            )
            
            sns.stripplot(
                data=df, 
                x=group_col, 
                y=value_col,
                order=order,
                color='black', 
                alpha=0.7, 
                jitter=0.2, 
                size=5,
                ax=ax
            )
            
            result = all_results.get(name, {})
            kw_result = result.get('kruskal_wallis', {})
            p_value = kw_result.get('p_value', 1.0)
            
            ax.set_title(f"{name}\np = {p_value:.4f}", fontsize=11)
            ax.set_xlabel(group_col, fontsize=10)
            ax.set_ylabel(value_col, fontsize=10)
            ax.tick_params(axis='x', rotation=0, labelsize=9)
        
        for idx in range(len(all_data), len(axes)):
            axes[idx].set_visible(False)
        
        fig.suptitle(title, fontsize=14, fontweight='bold', y=1.02)
        plt.tight_layout()
        
        base64_str = self._figure_to_base64(fig)
        return base64_str


def get_statistical_comparison_module(config: Dict[str, Any] = None) -> StatisticalComparisonModule:
    """获取统计比较模块实例"""
    return StatisticalComparisonModule(config)
