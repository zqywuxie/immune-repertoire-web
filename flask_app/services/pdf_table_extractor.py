"""
PDF Table Extractor Service

This service provides functionality to extract tables from PDF files using
both tabula-py and pdfplumber libraries.
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import pdfplumber
import tabula

logger = logging.getLogger(__name__)


class PDFTableExtractor:
    """Service for extracting tables from PDF files"""
    
    def __init__(self):
        """Initialize the PDF table extractor"""
        self.supported_methods = ['pdfplumber', 'tabula']
    
    def detect_tables(self, pdf_path: str, method: str = 'pdfplumber') -> Dict[str, Any]:
        """
        Detect tables in a PDF file
        
        Args:
            pdf_path: Path to the PDF file
            method: Extraction method ('pdfplumber' or 'tabula')
            
        Returns:
            Dictionary containing:
                - success: bool
                - table_count: int
                - pages_with_tables: List[int]
                - error: Optional[str]
        """
        try:
            # Validate method first
            if method not in self.supported_methods:
                return {
                    'success': False,
                    'error': f'不支持的提取方法: {method}'
                }
            
            if not os.path.exists(pdf_path):
                return {
                    'success': False,
                    'error': f'PDF文件不存在: {pdf_path}'
                }
            
            if method == 'pdfplumber':
                return self._detect_tables_pdfplumber(pdf_path)
            elif method == 'tabula':
                return self._detect_tables_tabula(pdf_path)
                
        except Exception as e:
            logger.error(f"Error detecting tables in PDF: {str(e)}")
            return {
                'success': False,
                'error': f'检测表格时出错: {str(e)}'
            }
    
    def _detect_tables_pdfplumber(self, pdf_path: str) -> Dict[str, Any]:
        """Detect tables using pdfplumber"""
        pages_with_tables = []
        table_count = 0
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                if tables:
                    pages_with_tables.append(page_num)
                    table_count += len(tables)
        
        return {
            'success': True,
            'table_count': table_count,
            'pages_with_tables': pages_with_tables,
            'method': 'pdfplumber'
        }
    
    def _detect_tables_tabula(self, pdf_path: str) -> Dict[str, Any]:
        """Detect tables using tabula"""
        try:
            # Use tabula to detect tables on all pages
            tables = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True)
            
            # Get pages with tables (tabula doesn't directly provide this)
            # We'll estimate based on table count
            table_count = len(tables)
            
            return {
                'success': True,
                'table_count': table_count,
                'pages_with_tables': list(range(1, table_count + 1)),  # Estimate
                'method': 'tabula'
            }
        except Exception as e:
            logger.error(f"Tabula detection error: {str(e)}")
            return {
                'success': False,
                'error': f'Tabula检测失败: {str(e)}'
            }
    
    def extract_tables(
        self, 
        pdf_path: str, 
        method: str = 'pdfplumber',
        pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Extract tables from a PDF file
        
        Args:
            pdf_path: Path to the PDF file
            method: Extraction method ('pdfplumber' or 'tabula')
            pages: Optional list of page numbers to extract from (1-indexed)
            
        Returns:
            Dictionary containing:
                - success: bool
                - tables: List[Dict] with table data
                - error: Optional[str]
        """
        try:
            if not os.path.exists(pdf_path):
                return {
                    'success': False,
                    'error': f'PDF文件不存在: {pdf_path}'
                }
            
            if method == 'pdfplumber':
                return self._extract_tables_pdfplumber(pdf_path, pages)
            elif method == 'tabula':
                return self._extract_tables_tabula(pdf_path, pages)
            else:
                return {
                    'success': False,
                    'error': f'不支持的提取方法: {method}'
                }
                
        except Exception as e:
            logger.error(f"Error extracting tables from PDF: {str(e)}")
            return {
                'success': False,
                'error': f'提取表格时出错: {str(e)}'
            }
    
    def _extract_tables_pdfplumber(
        self, 
        pdf_path: str, 
        pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Extract tables using pdfplumber"""
        extracted_tables = []
        
        with pdfplumber.open(pdf_path) as pdf:
            pages_to_process = pages if pages else range(1, len(pdf.pages) + 1)
            
            for page_num in pages_to_process:
                if page_num < 1 or page_num > len(pdf.pages):
                    continue
                    
                page = pdf.pages[page_num - 1]  # Convert to 0-indexed
                tables = page.extract_tables()
                
                for table_idx, table in enumerate(tables):
                    if table:
                        # Convert to DataFrame
                        df = pd.DataFrame(table[1:], columns=table[0])
                        
                        extracted_tables.append({
                            'page': page_num,
                            'table_index': table_idx,
                            'data': df.to_dict('records'),
                            'columns': df.columns.tolist(),
                            'row_count': len(df),
                            'col_count': len(df.columns)
                        })
        
        return {
            'success': True,
            'tables': extracted_tables,
            'table_count': len(extracted_tables),
            'method': 'pdfplumber'
        }
    
    def _extract_tables_tabula(
        self, 
        pdf_path: str, 
        pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Extract tables using tabula"""
        try:
            # Prepare pages parameter for tabula
            if pages:
                pages_str = ','.join(map(str, pages))
            else:
                pages_str = 'all'
            
            # Extract tables
            tables = tabula.read_pdf(
                pdf_path, 
                pages=pages_str, 
                multiple_tables=True,
                pandas_options={'header': 'infer'}
            )
            
            extracted_tables = []
            for table_idx, df in enumerate(tables):
                if not df.empty:
                    extracted_tables.append({
                        'page': table_idx + 1,  # Estimate page number
                        'table_index': table_idx,
                        'data': df.to_dict('records'),
                        'columns': df.columns.tolist(),
                        'row_count': len(df),
                        'col_count': len(df.columns)
                    })
            
            return {
                'success': True,
                'tables': extracted_tables,
                'table_count': len(extracted_tables),
                'method': 'tabula'
            }
        except Exception as e:
            logger.error(f"Tabula extraction error: {str(e)}")
            return {
                'success': False,
                'error': f'Tabula提取失败: {str(e)}'
            }
    
    def preview_table(
        self, 
        pdf_path: str, 
        page: int, 
        table_index: int = 0,
        method: str = 'pdfplumber',
        max_rows: int = 10
    ) -> Dict[str, Any]:
        """
        Preview a specific table from a PDF
        
        Args:
            pdf_path: Path to the PDF file
            page: Page number (1-indexed)
            table_index: Index of the table on the page (0-indexed)
            method: Extraction method
            max_rows: Maximum number of rows to preview
            
        Returns:
            Dictionary containing:
                - success: bool
                - preview_data: List[Dict] with preview rows
                - columns: List[str]
                - total_rows: int
                - error: Optional[str]
        """
        try:
            if not os.path.exists(pdf_path):
                return {
                    'success': False,
                    'error': f'PDF文件不存在: {pdf_path}'
                }
            
            # Extract the specific table
            result = self.extract_tables(pdf_path, method=method, pages=[page])
            
            if not result['success']:
                return result
            
            # Find the requested table
            tables = result['tables']
            matching_tables = [t for t in tables if t['page'] == page and t['table_index'] == table_index]
            
            if not matching_tables:
                return {
                    'success': False,
                    'error': f'在第{page}页未找到索引为{table_index}的表格'
                }
            
            table = matching_tables[0]
            preview_data = table['data'][:max_rows]
            
            return {
                'success': True,
                'preview_data': preview_data,
                'columns': table['columns'],
                'total_rows': table['row_count'],
                'total_cols': table['col_count'],
                'showing_rows': len(preview_data)
            }
            
        except Exception as e:
            logger.error(f"Error previewing table: {str(e)}")
            return {
                'success': False,
                'error': f'预览表格时出错: {str(e)}'
            }
    
    def extract_table_to_csv(
        self,
        pdf_path: str,
        output_path: str,
        page: int,
        table_index: int = 0,
        method: str = 'pdfplumber'
    ) -> Dict[str, Any]:
        """
        Extract a specific table and save it as CSV
        
        Args:
            pdf_path: Path to the PDF file
            output_path: Path to save the CSV file
            page: Page number (1-indexed)
            table_index: Index of the table on the page (0-indexed)
            method: Extraction method
            
        Returns:
            Dictionary containing:
                - success: bool
                - output_path: str
                - row_count: int
                - col_count: int
                - error: Optional[str]
        """
        try:
            # Extract the specific table
            result = self.extract_tables(pdf_path, method=method, pages=[page])
            
            if not result['success']:
                return result
            
            # Find the requested table
            tables = result['tables']
            matching_tables = [t for t in tables if t['page'] == page and t['table_index'] == table_index]
            
            if not matching_tables:
                return {
                    'success': False,
                    'error': f'在第{page}页未找到索引为{table_index}的表格'
                }
            
            table = matching_tables[0]
            
            # Convert to DataFrame and save
            df = pd.DataFrame(table['data'])
            df.to_csv(output_path, index=False, encoding='utf-8-sig')
            
            return {
                'success': True,
                'output_path': output_path,
                'row_count': table['row_count'],
                'col_count': table['col_count']
            }
            
        except Exception as e:
            logger.error(f"Error extracting table to CSV: {str(e)}")
            return {
                'success': False,
                'error': f'导出表格到CSV时出错: {str(e)}'
            }


# Create a singleton instance
pdf_table_extractor = PDFTableExtractor()
