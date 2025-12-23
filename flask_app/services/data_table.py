"""
Data Table Service for the Immune Repertoire Analysis Web Application.
Handles matrix data conversion to table format for display and clipboard copy.
Requirements: 2.5, 2.6
"""
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np


class DataTableService:
    """
    Service for converting analysis results to table format.
    Supports matrix-to-table conversion and clipboard-friendly formatting.
    Requirements: 2.5, 2.6
    """
    
    @staticmethod
    def matrix_to_table(
        matrix: pd.DataFrame,
        precision: int = 4,
        include_index: bool = True
    ) -> Dict[str, Any]:
        """
        Convert a similarity matrix to a table format suitable for display.
        
        Args:
            matrix: Similarity matrix as DataFrame
            precision: Number of decimal places for values
            include_index: Whether to include row index as first column
            
        Returns:
            Dictionary with columns, data, and metadata
            
        Requirements: 2.5
        """
        if matrix.empty:
            return {
                'columns': [],
                'data': [],
                'row_count': 0,
                'column_count': 0
            }
        
        # Round values to specified precision
        rounded_matrix = matrix.round(precision)
        
        # Build column list
        columns = []
        if include_index:
            columns.append({'name': 'Sample', 'type': 'string'})
        
        for col in rounded_matrix.columns:
            columns.append({'name': str(col), 'type': 'number'})
        
        # Build data rows
        data = []
        for idx, row in rounded_matrix.iterrows():
            row_data = {}
            if include_index:
                row_data['Sample'] = str(idx)
            for col in rounded_matrix.columns:
                row_data[str(col)] = row[col]
            data.append(row_data)
        
        return {
            'columns': columns,
            'data': data,
            'row_count': len(data),
            'column_count': len(columns)
        }
    
    @staticmethod
    def matrix_to_clipboard_text(
        matrix: pd.DataFrame,
        precision: int = 4,
        delimiter: str = '\t'
    ) -> str:
        """
        Convert a similarity matrix to tab-delimited text for clipboard copy.
        
        Args:
            matrix: Similarity matrix as DataFrame
            precision: Number of decimal places for values
            delimiter: Column delimiter (default: tab)
            
        Returns:
            Tab-delimited string suitable for pasting into spreadsheets
            
        Requirements: 2.6
        """
        if matrix.empty:
            return ""
        
        # Round values
        rounded_matrix = matrix.round(precision)
        
        lines = []
        
        # Header row
        header = [''] + [str(col) for col in rounded_matrix.columns]
        lines.append(delimiter.join(header))
        
        # Data rows
        for idx, row in rounded_matrix.iterrows():
            row_values = [str(idx)] + [str(row[col]) for col in rounded_matrix.columns]
            lines.append(delimiter.join(row_values))
        
        return '\n'.join(lines)
    
    @staticmethod
    def matrix_to_csv(
        matrix: pd.DataFrame,
        precision: int = 4
    ) -> str:
        """
        Convert a similarity matrix to CSV format.
        
        Args:
            matrix: Similarity matrix as DataFrame
            precision: Number of decimal places for values
            
        Returns:
            CSV string
            
        Requirements: 2.5, 6.2
        """
        if matrix.empty:
            return ""
        
        rounded_matrix = matrix.round(precision)
        return rounded_matrix.to_csv()
    
    @staticmethod
    def dataframe_to_table(
        df: pd.DataFrame,
        precision: int = 4,
        max_rows: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Convert a general DataFrame to table format.
        
        Args:
            df: DataFrame to convert
            precision: Number of decimal places for numeric values
            max_rows: Maximum number of rows to include (None for all)
            
        Returns:
            Dictionary with columns, data, and metadata
        """
        if df.empty:
            return {
                'columns': [],
                'data': [],
                'row_count': 0,
                'column_count': 0,
                'truncated': False
            }
        
        # Limit rows if specified
        truncated = False
        if max_rows is not None and len(df) > max_rows:
            df = df.head(max_rows)
            truncated = True
        
        # Build column list with type information
        columns = []
        for col in df.columns:
            col_type = 'number' if pd.api.types.is_numeric_dtype(df[col]) else 'string'
            columns.append({'name': str(col), 'type': col_type})
        
        # Build data rows
        data = []
        for _, row in df.iterrows():
            row_data = {}
            for col in df.columns:
                value = row[col]
                if pd.isna(value):
                    row_data[str(col)] = None
                elif isinstance(value, (float, np.floating)):
                    row_data[str(col)] = round(value, precision)
                else:
                    row_data[str(col)] = value
            data.append(row_data)
        
        return {
            'columns': columns,
            'data': data,
            'row_count': len(data),
            'column_count': len(columns),
            'truncated': truncated
        }
    
    @staticmethod
    def get_table_statistics(matrix: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate statistics for a similarity matrix.
        
        Args:
            matrix: Similarity matrix as DataFrame
            
        Returns:
            Dictionary with statistical measures
        """
        if matrix.empty:
            return {}
        
        # Get values excluding diagonal
        values = matrix.values.copy()
        np.fill_diagonal(values, np.nan)
        flat_values = values[~np.isnan(values)]
        
        if len(flat_values) == 0:
            return {}
        
        return {
            'min': float(np.min(flat_values)),
            'max': float(np.max(flat_values)),
            'mean': float(np.mean(flat_values)),
            'median': float(np.median(flat_values)),
            'std': float(np.std(flat_values)),
            'n_samples': len(matrix),
            'n_comparisons': len(flat_values)
        }
