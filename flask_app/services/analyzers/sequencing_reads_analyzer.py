"""
Sequencing Reads Chart Analyzer - 测序Reads条形图分析器
分析TCR/IG各链的测序reads数量和百分比
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


class SequencingReadsChartAnalyzer(BaseAnalyzer):
    """
    测序Reads条形图分析器
    
    功能:
    - 分析TCR/IG各链的测序reads数量
    - 生成堆叠条形图展示各链reads分布
    """
    
    # 所有链类型
    ALL_CHAINS = ["TRA", "TRB", "TRD", "TRG", "IGH", "IGK", "IGL"]
    
    # 链颜色映射
    CHAIN_COLORS = {
        "TRA": "#1f77b4",
        "TRB": "#ff7f0e", 
        "TRD": "#2ca02c",
        "TRG": "#d62728",
        "IGH": "#9467bd",
        "IGK": "#8c564b",
        "IGL": "#e377c2"
    }
    
    def __init__(self):
        super().__init__()
        self.name = "Sequencing Reads Chart Analyzer"
        self.description = "分析TCR/IG各链的测序reads数量和百分比"
        self.version = "1.0.0"
        
        self._default_parameters = {
            "sample_column": "Sample",
            "baseline_sample": None,
            "chains": self.ALL_CHAINS,
            "chart_config": {
                "figsize": [20, 16],
                "dpi": 300,
                "show_values": True
            }
        }
    
    def get_default_parameters(self) -> Dict[str, Any]:
        """返回默认参数"""
        return self._default_parameters.copy()
    
    def get_required_fields(self) -> List[str]:
        return ["Sample"]
    
    def get_optional_fields(self) -> List[str]:
        return [f"{chain}_reads" for chain in self.ALL_CHAINS]
    
    def validate_data(self, data: pd.DataFrame, parameters: Dict[str, Any] = None) -> ValidationResult:
        """验证数据是否包含所需字段"""
        errors = []
        warnings = []
        
        # 检查样本列
        sample_col = (parameters or {}).get('sample_column', 'Sample')
        if not self._find_column(data, sample_col):
            errors.append(f"Missing required column: {sample_col}")
        
        # 检查至少有一个reads列
        found_reads = False
        for chain in self.ALL_CHAINS:
            if self._find_column(data, f"{chain}_reads"):
                found_reads = True
                break
        
        if not found_reads:
            warnings.append("No chain reads columns found")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def analyze(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行测序Reads分析"""
        try:
            params = self.merge_parameters(parameters)
            
            sample_column = params.get('sample_column', 'Sample')
            baseline_sample = params.get('baseline_sample')
            chains = params.get('chains', self.ALL_CHAINS)
            
            # 提取reads数据
            reads_data = self._extract_reads_data(data, sample_column, chains)
            
            # 获取样本列表
            samples = list(reads_data.keys())
            
            # 生成表格数据
            table_data = self._generate_table_data(reads_data, samples, chains)
            long_format_table = self._generate_long_format_table(reads_data, samples, chains)
            
            # 生成图表
            charts = self._generate_charts(reads_data, samples, chains, params, baseline_sample)
            
            return {
                "samples": samples,
                "chains": chains,
                "reads_data": reads_data,
                "baseline_sample": baseline_sample,
                "table_data": table_data,
                "long_format_table": long_format_table,
                "charts": charts,
                "parameters": params
            }
            
        except Exception as e:
            logger.error(f"Error in Sequencing Reads analysis: {e}", exc_info=True)
            raise RuntimeError(f"Sequencing Reads analysis failed: {str(e)}")
    
    def _find_column(self, data: pd.DataFrame, target_col: str) -> Optional[str]:
        """查找匹配的列名（大小写不敏感）"""
        for col in data.columns:
            if col.lower() == target_col.lower():
                return col
        return None
    
    def _extract_reads_data(
        self,
        data: pd.DataFrame,
        sample_column: str,
        chains: List[str]
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """提取每个样本的reads数据和百分比"""
        result = {}
        
        actual_sample_col = self._find_column(data, sample_column)
        if not actual_sample_col:
            actual_sample_col = data.columns[0]
        
        for idx, row in data.iterrows():
            sample_value = row[actual_sample_col]
            # 确保获取单个值而不是Series
            if hasattr(sample_value, 'iloc'):
                sample_name = str(sample_value.iloc[0])
            elif hasattr(sample_value, 'values'):
                sample_name = str(sample_value.values[0]) if len(sample_value.values) > 0 else str(idx)
            else:
                sample_name = str(sample_value)
            
            result[sample_name] = {}
            
            for chain in chains:
                reads_col = self._find_column(data, f"{chain}_reads")
                pct_col = self._find_column(data, f"{chain}_percent_reads_all")
                
                reads_value = 0
                pct_value = 0.0
                
                if reads_col:
                    value = row[reads_col]
                    if pd.notna(value):
                        try:
                            reads_value = int(float(value))
                        except (ValueError, TypeError):
                            pass
                
                if pct_col:
                    value = row[pct_col]
                    if pd.notna(value):
                        try:
                            pct_value = float(value)
                        except (ValueError, TypeError):
                            pass
                
                result[sample_name][chain] = {
                    "reads": reads_value,
                    "percent": pct_value
                }
        
        return result
    
    def _generate_table_data(
        self,
        reads_data: Dict[str, Dict[str, Dict[str, Any]]],
        samples: List[str],
        chains: List[str]
    ) -> Dict[str, Any]:
        """生成宽格式表格数据 - 格式: reads (percent%)
        
        输出格式示例:
        | Sample | TRA Reads | TRB Reads | ... | IGL Reads |
        | NW_11_0521CT | 63849 (19.47%) | 104015 (29.24%) | ... | 39208 (11.39%) |
        """
        # 确保链的顺序是 TRA, TRB, TRD, TRG, IGH, IGK, IGL
        ordered_chains = ["TRA", "TRB", "TRD", "TRG", "IGH", "IGK", "IGL"]
        # 只保留实际存在的链
        display_chains = [c for c in ordered_chains if c in chains]
        
        headers = ["Sample"] + [f"{chain} Reads" for chain in display_chains]
        rows = []
        
        for sample in samples:
            row = [sample]
            sample_data = reads_data.get(sample, {})
            for chain in display_chains:
                chain_data = sample_data.get(chain, {})
                reads = chain_data.get("reads", 0)
                pct = chain_data.get("percent", 0)
                # 格式: "42826 (12.45%)"
                row.append(f"{reads:,} ({pct:.2f}%)")
            rows.append(row)
        
        return {
            "headers": headers,
            "rows": rows,
            "tab_separated": self._to_tab_separated(headers, rows)
        }
    
    def _generate_long_format_table(
        self,
        reads_data: Dict[str, Dict[str, Dict[str, Any]]],
        samples: List[str],
        chains: List[str]
    ) -> Dict[str, Any]:
        """生成长格式表格数据"""
        headers = ["Sample", "Chain", "Reads", "Percent"]
        rows = []
        
        for sample in samples:
            sample_data = reads_data.get(sample, {})
            for chain in chains:
                chain_data = sample_data.get(chain, {})
                reads = chain_data.get("reads", 0)
                pct = chain_data.get("percent", 0)
                if reads > 0:
                    rows.append([sample, chain, reads, f"{pct:.2f}%"])
        
        return {
            "headers": headers,
            "rows": rows,
            "tab_separated": self._to_tab_separated(headers, rows)
        }
    
    def _to_tab_separated(self, headers: List[str], rows: List[List[Any]]) -> str:
        """转换为制表符分隔的文本"""
        lines = ["\t".join(str(h) for h in headers)]
        for row in rows:
            lines.append("\t".join(str(v) if v is not None else "" for v in row))
        return "\n".join(lines)
    
    def _generate_charts(
        self,
        reads_data: Dict[str, Dict[str, Dict[str, Any]]],
        samples: List[str],
        chains: List[str],
        params: Dict[str, Any],
        baseline_sample: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """生成测序Reads条形图 - 参考sequencing_reads_bar_chart_final.py"""
        charts = []
        
        try:
            plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
            plt.rcParams["axes.unicode_minus"] = False
            
            chart_config = params.get('chart_config', {})
            figsize = chart_config.get('figsize', [20, 16])
            
            # 分离TCR和IG链
            tcr_chains = [c for c in chains if c.startswith('TR')]
            ig_chains = [c for c in chains if c.startswith('IG')]
            
            # 查找基准样本索引
            baseline_idx = None
            if baseline_sample and baseline_sample in samples:
                baseline_idx = samples.index(baseline_sample)
            
            # 创建TCR图表（如果有TCR链）
            if tcr_chains:
                fig_tcr = self._create_chain_figure(
                    reads_data, samples, tcr_chains, baseline_sample, baseline_idx,
                    "TCR Sequencing Reads - Percentage Change from Baseline"
                )
                if fig_tcr:
                    buf = io.BytesIO()
                    fig_tcr.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
                    buf.seek(0)
                    charts.append({
                        'title': 'TCR Sequencing Reads',
                        'base64': base64.b64encode(buf.read()).decode('utf-8')
                    })
                    plt.close(fig_tcr)
            
            # 创建IG图表（如果有IG链）
            if ig_chains:
                fig_ig = self._create_chain_figure(
                    reads_data, samples, ig_chains, baseline_sample, baseline_idx,
                    "IG Sequencing Reads - Percentage Change from Baseline"
                )
                if fig_ig:
                    buf = io.BytesIO()
                    fig_ig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
                    buf.seek(0)
                    charts.append({
                        'title': 'IG Sequencing Reads',
                        'base64': base64.b64encode(buf.read()).decode('utf-8')
                    })
                    plt.close(fig_ig)
            
        except Exception as e:
            logger.error(f"Error generating charts: {e}", exc_info=True)
        
        return charts
    
    def _create_chain_figure(
        self,
        reads_data: Dict[str, Dict[str, Dict[str, Any]]],
        samples: List[str],
        chains: List[str],
        baseline_sample: Optional[str],
        baseline_idx: Optional[int],
        title: str
    ):
        """创建链类型图表"""
        num_chains = len(chains)
        cols = min(num_chains, 2)
        rows = (num_chains + 1) // 2
        
        fig, axes = plt.subplots(rows, cols, figsize=(10 * cols, 8 * rows))
        if num_chains == 1:
            axes = [axes]
        else:
            axes = axes.flatten()
        
        title_suffix = f"\n(Baseline: {baseline_sample})" if baseline_sample else ""
        fig.suptitle(f"{title}{title_suffix}", fontsize=18, fontweight='bold', y=0.98)
        
        x_pos = np.arange(len(samples))
        bar_width = 0.6
        
        for idx, chain in enumerate(chains):
            if idx >= len(axes):
                break
            ax = axes[idx]
            
            # 获取reads值
            values = [reads_data.get(s, {}).get(chain, {}).get("reads", 0) for s in samples]
            
            # 计算百分比变化
            if baseline_idx is not None and values[baseline_idx] != 0:
                baseline_value = values[baseline_idx]
                pct_change = [(v - baseline_value) / baseline_value * 100 for v in values]
                ylabel = "Percentage Change from Baseline (%)"
            else:
                pct_change = values
                ylabel = "Reads Count"
            
            bars = ax.bar(x_pos, pct_change, bar_width,
                         color=self.CHAIN_COLORS.get(chain, '#999999'), alpha=0.8)
            
            # 高亮基准样本
            if baseline_idx is not None and baseline_idx < len(bars):
                bars[baseline_idx].set_edgecolor('black')
                bars[baseline_idx].set_linewidth(2)
                ax.axhline(y=0, color='gray', linestyle='-', linewidth=1.5, alpha=0.8)
            
            ax.set_xticks(x_pos)
            ax.set_xticklabels(samples, rotation=45, ha='right', fontsize=9)
            ax.set_ylabel(ylabel, fontsize=11, fontweight='bold')
            ax.set_xlabel('Sample', fontsize=11, fontweight='bold')
            ax.set_title(f'{chain} Reads', fontsize=14, fontweight='bold')
            ax.grid(axis='y', alpha=0.3, linestyle='--')
            ax.set_facecolor('#f8f9fa')
        
        # 隐藏多余的子图
        for idx in range(num_chains, len(axes)):
            axes[idx].set_visible(False)
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        return fig
