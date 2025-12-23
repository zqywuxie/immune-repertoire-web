"""
B Cell Isotype PDF Extraction Module
从PDF报告中提取B细胞同种型分布数据
"""

import pdfplumber
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import re
import io
import base64
from typing import Dict, Any, List, Optional
import logging

from ..base_module import AnalysisModule
from ..registry import register_module

logger = logging.getLogger(__name__)


@register_module
class BCellIsotypePDFModule(AnalysisModule):
    """从PDF报告中提取B细胞同种型分布数据的分析模块"""
    
    def get_name(self) -> str:
        return "bcell_isotype_pdf"
    
    def get_display_name(self) -> str:
        return "B细胞同种型分析 (PDF提取)"
    
    def get_description(self) -> str:
        return "从PDF报告中提取B细胞同种型分布数据（IgM、IgD、IgA、IgG、IgE）并生成可视化图表"
    
    def get_category(self) -> str:
        return "pdf_extraction"
    
    def get_required_columns(self) -> List[str]:
        return []  # PDF extraction doesn't require CSV columns
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "isotypes": ["IgM", "IgD", "IgA1/2", "IgG1/2", "IgG3/4", "IgE"],
            "plot_type": "horizontal_bar",
            "color_scheme": "Set3",
            "show_values": True,
            "figure_width": 12,
            "figure_height": 8
        }
    
    def validate_data(self, data: Any, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """验证PDF文件"""
        if not isinstance(data, dict) or 'pdf_files' not in data:
            return False, "需要提供PDF文件"
        
        pdf_files = data.get('pdf_files', [])
        if not pdf_files:
            return False, "至少需要一个PDF文件"
        
        return True, None
    
    def execute(self, data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行PDF提取和分析"""
        try:
            logger.info(f"Starting B-cell isotype PDF extraction with params: {params}")
            
            # 合并参数
            analysis_params = {**self.get_default_params(), **params}
            
            # 提取PDF数据
            extracted_data = self._extract_from_pdfs(data, analysis_params)
            
            if not extracted_data:
                raise ValueError("无法从PDF文件中提取数据")
            
            # 转换为DataFrame
            df = self._create_dataframe(extracted_data, analysis_params)
            
            # 生成可视化
            figures = self._create_visualizations(df, analysis_params)
            
            # 生成统计摘要
            summary = self._generate_summary(df, analysis_params)
            
            return {
                "success": True,
                "data": df.to_dict('records'),
                "figures": figures,
                "summary": summary,
                "sample_count": len(df),
                "params": analysis_params
            }
            
        except Exception as e:
            logger.error(f"Error in B-cell isotype PDF extraction: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "figures": {},
                "summary": f"分析失败: {str(e)}"
            }
    
    def _extract_from_pdfs(self, data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Dict]:
        """从PDF文件中提取同种型数据"""
        pdf_files = data.get('pdf_files', [])
        extracted_data = {}
        
        for pdf_info in pdf_files:
            sample_name = pdf_info.get('sample_name')
            pdf_path = pdf_info.get('path')
            
            if not sample_name or not pdf_path:
                continue
            
            logger.info(f"Processing PDF for sample: {sample_name}")
            
            try:
                isotype_data = self._extract_isotype_data_from_pdf(pdf_path, params)
                if isotype_data:
                    extracted_data[sample_name] = isotype_data
                    logger.info(f"Successfully extracted data from {sample_name}")
                else:
                    logger.warning(f"No data extracted from {sample_name}")
            except Exception as e:
                logger.error(f"Error processing {sample_name}: {e}")
        
        return extracted_data
    
    def _extract_isotype_data_from_pdf(self, pdf_path: str, params: Dict[str, Any]) -> Optional[Dict]:
        """从单个PDF文件中提取同种型数据"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                # 搜索所有页面查找B细胞同种型分布表
                for page in pdf.pages:
                    text = page.extract_text()
                    
                    # 查找包含B细胞同种型分布的部分
                    if "B cell Isotype Distribution" in text or "Isotype Distribution" in text:
                        tables = page.extract_tables()
                        
                        for table in tables:
                            if table and len(table) > 0:
                                header_row = table[0] if table else []
                                
                                # 查找同种型列
                                isotype_cols = []
                                for col in header_row:
                                    if col and any(iso in str(col) for iso in ["IgM", "IgD", "IgA", "IgG", "IgE"]):
                                        isotype_cols.append(col)
                                
                                if len(isotype_cols) >= 5:  # 找到同种型数据
                                    # 查找Expression %和Unique CDR3 %行
                                    expression_row = None
                                    cdr3_row = None
                                    
                                    for row in table[1:]:
                                        if row and len(row) > 0:
                                            row_text = " ".join([str(cell) for cell in row if cell])
                                            if "Expression" in row_text and "%" in row_text:
                                                expression_row = row
                                            elif "Unique" in row_text and "CDR3" in row_text:
                                                cdr3_row = row
                                    
                                    if expression_row and cdr3_row:
                                        # 提取数值
                                        expression_values = []
                                        cdr3_values = []
                                        
                                        for cell in expression_row:
                                            if cell and "%" in str(cell):
                                                match = re.search(r"(\d+\.?\d*)", str(cell))
                                                if match:
                                                    expression_values.append(float(match.group(1)))
                                        
                                        for cell in cdr3_row:
                                            if cell and "%" in str(cell):
                                                match = re.search(r"(\d+\.?\d*)", str(cell))
                                                if match:
                                                    cdr3_values.append(float(match.group(1)))
                                        
                                        if len(expression_values) >= 5 and len(cdr3_values) >= 5:
                                            return {
                                                "expression": expression_values[:6],
                                                "unique_cdr3": cdr3_values[:6]
                                            }
                
                # 备用方法：模糊匹配
                for page in pdf.pages:
                    tables = page.extract_tables()
                    
                    for table in tables:
                        if table and len(table) > 2:
                            table_text = []
                            for row in table:
                                table_text.append(" ".join([str(cell) for cell in row if cell]))
                            
                            full_text = " ".join(table_text).lower()
                            
                            if any(iso.lower() in full_text for iso in ["igm", "igd", "iga", "igg"]) and "%" in full_text:
                                expression_values = []
                                cdr3_values = []
                                
                                for row_text in table_text:
                                    if "expression" in row_text.lower():
                                        percentages = re.findall(r"(\d+\.?\d*)%", row_text)
                                        expression_values = [float(p) for p in percentages]
                                    elif "unique" in row_text.lower() and "cdr3" in row_text.lower():
                                        percentages = re.findall(r"(\d+\.?\d*)%", row_text)
                                        cdr3_values = [float(p) for p in percentages]
                                
                                if len(expression_values) >= 5 and len(cdr3_values) >= 5:
                                    return {
                                        "expression": expression_values[:6],
                                        "unique_cdr3": cdr3_values[:6]
                                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting from PDF {pdf_path}: {e}")
            return None
    
    def _create_dataframe(self, extracted_data: Dict[str, Dict], params: Dict[str, Any]) -> pd.DataFrame:
        """将提取的数据转换为DataFrame"""
        rows = []
        isotypes = params["isotypes"]
        
        for sample_name, data in extracted_data.items():
            row = {"Sample": sample_name}
            
            # Expression数据
            for i, iso in enumerate(isotypes):
                if i < len(data["expression"]):
                    row[f"{iso}_Expression"] = data["expression"][i]
            
            # Unique CDR3数据
            for i, iso in enumerate(isotypes):
                if i < len(data["unique_cdr3"]):
                    row[f"{iso}_UCDR3"] = data["unique_cdr3"][i]
            
            rows.append(row)
        
        return pd.DataFrame(rows)
    
    def _create_visualizations(self, df: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表"""
        figures = {}
        
        try:
            # 为每个样本创建水平柱状图
            for _, row in df.iterrows():
                sample_name = row["Sample"]
                fig = self._create_sample_plot(row, params)
                figures[f"sample_{sample_name}"] = self._figure_to_base64(fig)
                plt.close(fig)
            
            # 创建汇总对比图
            if len(df) > 1:
                fig = self._create_comparison_plot(df, params)
                figures["comparison"] = self._figure_to_base64(fig)
                plt.close(fig)
            
        except Exception as e:
            logger.error(f"Error creating visualizations: {e}")
        
        return figures
    
    def _create_sample_plot(self, row: pd.Series, params: Dict[str, Any]) -> plt.Figure:
        """为单个样本创建水平柱状图"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(params["figure_width"], params["figure_height"]))
        
        isotypes = params["isotypes"]
        colors = plt.cm.get_cmap(params["color_scheme"])(np.linspace(0, 1, len(isotypes)))
        
        # Expression图
        expression_values = [row.get(f"{iso}_Expression", 0) for iso in isotypes]
        y_pos = np.arange(len(isotypes))
        
        bars1 = ax1.barh(y_pos, expression_values, color=colors, alpha=0.8)
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels(isotypes)
        ax1.set_xlabel("Expression (%)", fontsize=12)
        ax1.set_title(f"{row['Sample']} - Expression", fontsize=14, fontweight='bold')
        ax1.grid(True, alpha=0.3, axis='x')
        
        if params["show_values"]:
            for i, (bar, val) in enumerate(zip(bars1, expression_values)):
                ax1.text(val + 0.5, i, f'{val:.1f}%', va='center', fontsize=10)
        
        # Unique CDR3图
        cdr3_values = [row.get(f"{iso}_UCDR3", 0) for iso in isotypes]
        bars2 = ax2.barh(y_pos, cdr3_values, color=colors, alpha=0.8)
        ax2.set_yticks(y_pos)
        ax2.set_yticklabels(isotypes)
        ax2.set_xlabel("Unique CDR3 (%)", fontsize=12)
        ax2.set_title(f"{row['Sample']} - Unique CDR3", fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='x')
        
        if params["show_values"]:
            for i, (bar, val) in enumerate(zip(bars2, cdr3_values)):
                ax2.text(val + 0.5, i, f'{val:.1f}%', va='center', fontsize=10)
        
        plt.tight_layout()
        return fig
    
    def _create_comparison_plot(self, df: pd.DataFrame, params: Dict[str, Any]) -> plt.Figure:
        """创建多样本对比图"""
        fig, ax = plt.subplots(figsize=(params["figure_width"], params["figure_height"]))
        
        isotypes = params["isotypes"]
        x = np.arange(len(isotypes))
        width = 0.8 / len(df)
        colors = plt.cm.tab10(np.linspace(0, 1, len(df)))
        
        for i, (_, row) in enumerate(df.iterrows()):
            expression_values = [row.get(f"{iso}_Expression", 0) for iso in isotypes]
            offset = (i - len(df)/2) * width + width/2
            ax.bar(x + offset, expression_values, width, label=row['Sample'], 
                   color=colors[i], alpha=0.8)
        
        ax.set_xlabel('Isotype', fontsize=12)
        ax.set_ylabel('Expression (%)', fontsize=12)
        ax.set_title('B细胞同种型表达对比', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(isotypes)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        return fig
    
    def _generate_summary(self, df: pd.DataFrame, params: Dict[str, Any]) -> str:
        """生成分析摘要"""
        summary = f"成功从 {len(df)} 个PDF文件中提取B细胞同种型数据。\n\n"
        
        summary += "样本列表：\n"
        for sample in df['Sample'].values:
            summary += f"  - {sample}\n"
        
        summary += "\n各同种型平均表达百分比：\n"
        for iso in params["isotypes"]:
            col = f"{iso}_Expression"
            if col in df.columns:
                mean_val = df[col].mean()
                std_val = df[col].std()
                summary += f"  - {iso}: {mean_val:.2f}% ± {std_val:.2f}%\n"
        
        return summary
    
    def _figure_to_base64(self, fig: plt.Figure) -> str:
        """将matplotlib图表转换为base64字符串"""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()
        return f"data:image/png;base64,{img_base64}"
