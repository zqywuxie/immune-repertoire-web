"""
File Parser Service for the Immune Repertoire Analysis Web Application.
Handles parsing of CSV, Excel, and gzip-compressed files.
Requirements: 1.2, 11.1, 4.1, 4.2, 4.3, 4.4, 10.1, 10.2, 10.4
"""
import gzip
import io
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional, Union

import numpy as np
import pandas as pd

from exceptions import FileParseError, FileFormatInvalidError


class FileParserService:
    """
    Service for parsing uploaded data files.
    Supports CSV, Excel (.xlsx), and gzip-compressed CSV (.csv.gz) formats.
    Requirements: 1.2, 11.1, 4.1, 4.2, 4.3, 4.4
    """
    
    SUPPORTED_EXTENSIONS = {'.csv', '.xlsx', '.csv.gz', '.pdf'}
    
    # Known chain names for filename parsing
    KNOWN_CHAINS = ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG']
    
    @classmethod
    def validate_extension(cls, filename: str) -> bool:
        """
        Validate if the file extension is supported.
        
        Args:
            filename: Name of the file to validate
            
        Returns:
            True if extension is supported, False otherwise
        """
        filename_lower = filename.lower()
        
        # Check for .csv.gz first (compound extension)
        if filename_lower.endswith('.csv.gz'):
            return True
        
        # Check single extensions
        ext = Path(filename_lower).suffix
        return ext in {'.csv', '.xlsx', '.pdf'}
    
    @classmethod
    def get_extension(cls, filename: str) -> str:
        """
        Get the file extension (handling compound extensions like .csv.gz).
        
        Args:
            filename: Name of the file
            
        Returns:
            File extension (e.g., '.csv', '.xlsx', '.csv.gz', '.pdf')
        """
        filename_lower = filename.lower()
        
        if filename_lower.endswith('.csv.gz'):
            return '.csv.gz'
        
        return Path(filename_lower).suffix

    @classmethod
    def get_mime_type(cls, filename: str) -> str:
        """
        Get the MIME type for a file based on its extension.
        
        Args:
            filename: Name of the file
            
        Returns:
            MIME type string
        """
        ext = cls.get_extension(filename)
        mime_types = {
            '.csv': 'text/csv',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.csv.gz': 'application/gzip',
            '.pdf': 'application/pdf'
        }
        return mime_types.get(ext, 'application/octet-stream')
    
    @classmethod
    def parse_file(
        cls, 
        file_content: bytes, 
        filename: str
    ) -> Tuple[pd.DataFrame, List[str], int]:
        """
        Parse file content and extract data.
        
        Args:
            file_content: Raw file content as bytes
            filename: Original filename (used to determine format)
            
        Returns:
            Tuple of (DataFrame, column_names, row_count)
            
        Raises:
            FileFormatInvalidError: If file format is not supported
            FileParseError: If file content cannot be parsed
        """
        if not cls.validate_extension(filename):
            ext = Path(filename).suffix
            raise FileFormatInvalidError(
                message=f"Unsupported file format: {ext}",
                details={
                    'provided_extension': ext,
                    'supported_extensions': list(cls.SUPPORTED_EXTENSIONS)
                }
            )
        
        ext = cls.get_extension(filename)
        
        try:
            if ext == '.csv':
                df = cls._parse_csv(file_content)
            elif ext == '.xlsx':
                df = cls._parse_excel(file_content)
            elif ext == '.csv.gz':
                df = cls._parse_gzip_csv(file_content)
            elif ext == '.pdf':
                # PDF files don't have tabular data, return empty DataFrame
                df = pd.DataFrame()
                columns = []
                row_count = 0
                return df, columns, row_count
            else:
                raise FileFormatInvalidError(
                    message=f"Unsupported file format: {ext}"
                )
            
            columns = df.columns.tolist()
            row_count = len(df)
            
            return df, columns, row_count
            
        except FileFormatInvalidError:
            raise
        except Exception as e:
            raise FileParseError(
                message=f"Failed to parse file: {str(e)}",
                details={
                    'filename': filename,
                    'error_type': type(e).__name__
                }
            )
    
    @classmethod
    def _parse_csv(cls, content: bytes) -> pd.DataFrame:
        """Parse CSV file content."""
        # Try different encodings
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        
        for encoding in encodings:
            try:
                return pd.read_csv(io.BytesIO(content), encoding=encoding)
            except UnicodeDecodeError:
                continue
            except Exception as e:
                # If it's not an encoding error, raise it
                if 'codec' not in str(e).lower():
                    raise
        
        raise FileParseError(
            message="Could not decode CSV file with any supported encoding",
            details={'tried_encodings': encodings}
        )
    
    @classmethod
    def _parse_excel(cls, content: bytes) -> pd.DataFrame:
        """Parse Excel file content."""
        return pd.read_excel(io.BytesIO(content), engine='openpyxl')
    
    @classmethod
    def _parse_gzip_csv(cls, content: bytes) -> pd.DataFrame:
        """Parse gzip-compressed CSV file content."""
        try:
            decompressed = gzip.decompress(content)
            return cls._parse_csv(decompressed)
        except gzip.BadGzipFile:
            raise FileParseError(
                message="Invalid gzip file format",
                details={'error': 'File is not a valid gzip archive'}
            )
    
    @classmethod
    def get_sample_data(
        cls, 
        df: pd.DataFrame, 
        n_rows: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get sample data from DataFrame for preview.
        
        Args:
            df: DataFrame to sample from
            n_rows: Number of rows to return
            
        Returns:
            List of dictionaries representing rows
        """
        sample_df = df.head(n_rows)
        # Replace NaN with None before converting to records
        sample_df = sample_df.replace({np.nan: None})
        return sample_df.to_dict('records')
    
    @classmethod
    def get_file_info(
        cls, 
        file_content: bytes, 
        filename: str
    ) -> Dict[str, Any]:
        """
        Get comprehensive file information.
        
        Args:
            file_content: Raw file content as bytes
            filename: Original filename
            
        Returns:
            Dictionary with file information
        """
        df, columns, row_count = cls.parse_file(file_content, filename)
        
        return {
            'filename': filename,
            'size': len(file_content),
            'mime_type': cls.get_mime_type(filename),
            'columns': columns,
            'column_count': len(columns),
            'row_count': row_count,
            'sample_data': cls.get_sample_data(df)
        }
    
    @classmethod
    def read_csv_or_gzip(cls, filepath: str) -> pd.DataFrame:
        """
        Read CSV or GZIP-compressed CSV file from a filepath.
        Automatically detects file format based on extension and decompresses if needed.
        
        Requirements: 4.1, 4.2, 4.4
        
        Args:
            filepath: Path to the file (can be .csv or .csv.gz)
            
        Returns:
            DataFrame with the file contents
            
        Raises:
            FileFormatInvalidError: If file format is not supported
            FileParseError: If file content cannot be parsed
        """
        path = Path(filepath)
        filename = path.name
        
        if not cls.validate_extension(filename):
            ext = path.suffix
            raise FileFormatInvalidError(
                message=f"Unsupported file format: {ext}",
                details={
                    'provided_extension': ext,
                    'supported_extensions': ['.csv', '.csv.gz']
                }
            )
        
        ext = cls.get_extension(filename)
        
        if ext not in ['.csv', '.csv.gz']:
            raise FileFormatInvalidError(
                message=f"read_csv_or_gzip only supports CSV and CSV.GZ files, got: {ext}",
                details={'provided_extension': ext}
            )
        
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            
            if ext == '.csv.gz':
                return cls._parse_gzip_csv(content)
            else:
                return cls._parse_csv(content)
                
        except FileParseError:
            raise
        except FileNotFoundError:
            raise FileParseError(
                message=f"File not found: {filepath}",
                details={'filepath': filepath}
            )
        except Exception as e:
            raise FileParseError(
                message=f"Failed to read file: {str(e)}",
                details={
                    'filepath': filepath,
                    'error_type': type(e).__name__
                }
            )
    
    @classmethod
    def parse_filename(cls, filename: str) -> Dict[str, str]:
        """
        Parse filename to extract sample name and chain name.
        Supports formats: {sample_name}{chain_name}.csv or {sample_name}{chain_name}.csv.gz
        
        Requirements: 4.3
        
        The chain name is expected to be one of the known chains (IGH, IGK, IGL, TRA, TRB, TRD, TRG)
        appearing at the end of the filename before the extension.
        
        Args:
            filename: Name of the file (e.g., "Sample1IGH.csv", "Patient_A_IGK.csv.gz")
            
        Returns:
            Dictionary with keys:
                - sample_name: Extracted sample name
                - chain_name: Extracted chain name (or empty string if not found)
                - format: File format ('.csv' or '.csv.gz')
                
        Examples:
            >>> FileParserService.parse_filename("Sample1IGH.csv")
            {'sample_name': 'Sample1', 'chain_name': 'IGH', 'format': '.csv'}
            
            >>> FileParserService.parse_filename("Patient_A_IGK.csv.gz")
            {'sample_name': 'Patient_A_', 'chain_name': 'IGK', 'format': '.csv.gz'}
            
            >>> FileParserService.parse_filename("data_file.csv")
            {'sample_name': 'data_file', 'chain_name': '', 'format': '.csv'}
        """
        # Get the file extension
        file_format = cls.get_extension(filename)
        
        # Remove extension to get the base name
        if file_format == '.csv.gz':
            base_name = filename[:-7]  # Remove '.csv.gz'
        elif file_format == '.csv':
            base_name = filename[:-4]  # Remove '.csv'
        else:
            # For other formats, just use the filename without extension
            base_name = Path(filename).stem
            file_format = Path(filename).suffix
        
        # Try to find a known chain name at the end of the base name
        sample_name = base_name
        chain_name = ''
        
        # Build a regex pattern to match chain names at the end
        # Chain names can be preceded by underscore, hyphen, or nothing
        chain_pattern = r'^(.+?)[-_]?(' + '|'.join(cls.KNOWN_CHAINS) + r')$'
        match = re.match(chain_pattern, base_name, re.IGNORECASE)
        
        if match:
            sample_name = match.group(1)
            chain_name = match.group(2).upper()  # Normalize to uppercase
        
        return {
            'sample_name': sample_name,
            'chain_name': chain_name,
            'format': file_format
        }
    
    @classmethod
    def read_excel_sheets(
        cls,
        filepath_or_content: Union[str, bytes],
        sheet_names: Optional[List[str]] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Read all or specified sheets from an Excel file.
        
        Requirements: 10.1, 10.2
        
        Args:
            filepath_or_content: Path to the Excel file or file content as bytes
            sheet_names: Optional list of sheet names to read. If None, reads all sheets.
            
        Returns:
            Dictionary mapping sheet names to DataFrames
            
        Raises:
            FileFormatInvalidError: If file format is not supported
            FileParseError: If file content cannot be parsed
            
        Examples:
            >>> sheets = FileParserService.read_excel_sheets("data.xlsx")
            >>> print(sheets.keys())
            dict_keys(['Sheet1', 'Sheet2', 'Summary'])
            
            >>> sheets = FileParserService.read_excel_sheets("data.xlsx", ["Sheet1", "Summary"])
            >>> print(sheets.keys())
            dict_keys(['Sheet1', 'Summary'])
        """
        try:
            # Determine if input is filepath or content
            if isinstance(filepath_or_content, str):
                # It's a filepath
                path = Path(filepath_or_content)
                if not path.exists():
                    raise FileParseError(
                        message=f"File not found: {filepath_or_content}",
                        details={'filepath': filepath_or_content}
                    )
                
                ext = cls.get_extension(path.name)
                if ext != '.xlsx':
                    raise FileFormatInvalidError(
                        message=f"read_excel_sheets only supports .xlsx files, got: {ext}",
                        details={'provided_extension': ext}
                    )
                
                excel_file = pd.ExcelFile(filepath_or_content, engine='openpyxl')
            else:
                # It's bytes content
                excel_file = pd.ExcelFile(io.BytesIO(filepath_or_content), engine='openpyxl')
            
            # Get available sheet names
            available_sheets = excel_file.sheet_names
            
            # Determine which sheets to read
            if sheet_names is None:
                sheets_to_read = available_sheets
            else:
                # Validate requested sheets exist
                missing_sheets = set(sheet_names) - set(available_sheets)
                if missing_sheets:
                    raise FileParseError(
                        message=f"Sheets not found: {missing_sheets}",
                        details={
                            'requested_sheets': sheet_names,
                            'available_sheets': available_sheets,
                            'missing_sheets': list(missing_sheets)
                        }
                    )
                sheets_to_read = sheet_names
            
            # Read each sheet
            result = {}
            for sheet_name in sheets_to_read:
                result[sheet_name] = pd.read_excel(
                    excel_file,
                    sheet_name=sheet_name,
                    engine='openpyxl'
                )
            
            return result
            
        except FileParseError:
            raise
        except FileFormatInvalidError:
            raise
        except Exception as e:
            raise FileParseError(
                message=f"Failed to read Excel file: {str(e)}",
                details={
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                }
            )
    
    @classmethod
    def get_excel_sheet_names(
        cls,
        filepath_or_content: Union[str, bytes]
    ) -> List[str]:
        """
        Get all sheet names from an Excel file without reading the data.
        
        Requirements: 10.2
        
        Args:
            filepath_or_content: Path to the Excel file or file content as bytes
            
        Returns:
            List of sheet names
            
        Raises:
            FileParseError: If file cannot be read
        """
        try:
            if isinstance(filepath_or_content, str):
                excel_file = pd.ExcelFile(filepath_or_content, engine='openpyxl')
            else:
                excel_file = pd.ExcelFile(io.BytesIO(filepath_or_content), engine='openpyxl')
            
            return excel_file.sheet_names
            
        except Exception as e:
            raise FileParseError(
                message=f"Failed to read Excel sheet names: {str(e)}",
                details={'error_type': type(e).__name__}
            )
    
    @classmethod
    def filter_samples_by_pattern(
        cls,
        df: pd.DataFrame,
        pattern: str,
        sample_column: str = "Sample"
    ) -> pd.DataFrame:
        """
        Filter DataFrame rows by matching sample names against a regex pattern.
        
        Requirements: 10.4
        
        Args:
            df: Input DataFrame
            pattern: Regular expression pattern to match sample names
            sample_column: Name of the column containing sample names
            
        Returns:
            Filtered DataFrame containing only rows where sample name matches the pattern
            
        Raises:
            FileParseError: If sample column doesn't exist or pattern is invalid
            
        Examples:
            >>> df = pd.DataFrame({'Sample': ['S1_A', 'S2_A', 'S1_B', 'S2_B'], 'value': [1, 2, 3, 4]})
            >>> filtered = FileParserService.filter_samples_by_pattern(df, r'S1_.*')
            >>> print(filtered['Sample'].tolist())
            ['S1_A', 'S1_B']
            
            >>> filtered = FileParserService.filter_samples_by_pattern(df, r'.*_A$')
            >>> print(filtered['Sample'].tolist())
            ['S1_A', 'S2_A']
        """
        # Check if sample column exists
        if sample_column not in df.columns:
            raise FileParseError(
                message=f"Sample column '{sample_column}' not found in DataFrame",
                details={
                    'sample_column': sample_column,
                    'available_columns': df.columns.tolist()
                }
            )
        
        try:
            # Compile the regex pattern
            compiled_pattern = re.compile(pattern)
            
            # Filter rows where sample name matches the pattern
            mask = df[sample_column].astype(str).apply(
                lambda x: bool(compiled_pattern.search(x))
            )
            
            return df[mask].reset_index(drop=True)
            
        except re.error as e:
            raise FileParseError(
                message=f"Invalid regex pattern: {pattern}",
                details={
                    'pattern': pattern,
                    'error': str(e)
                }
            )
    
    @classmethod
    def identify_sample_column(
        cls,
        df: pd.DataFrame,
        candidate_names: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Identify the sample column in a DataFrame.
        
        Requirements: 10.3
        
        Args:
            df: Input DataFrame
            candidate_names: Optional list of candidate column names to check.
                           Defaults to common sample column names.
            
        Returns:
            Name of the identified sample column, or None if not found
            
        Examples:
            >>> df = pd.DataFrame({'Sample': ['S1', 'S2'], 'value': [1, 2]})
            >>> FileParserService.identify_sample_column(df)
            'Sample'
        """
        if candidate_names is None:
            candidate_names = [
                'Sample', 'sample', 'SAMPLE',
                'Sample_Name', 'sample_name', 'SampleName',
                'ID', 'id', 'Id',
                'Name', 'name', 'NAME',
                'Subject', 'subject', 'SUBJECT'
            ]
        
        # Check for exact matches first
        for name in candidate_names:
            if name in df.columns:
                return name
        
        # Check for case-insensitive matches
        columns_lower = {col.lower(): col for col in df.columns}
        for name in candidate_names:
            if name.lower() in columns_lower:
                return columns_lower[name.lower()]
        
        # If no match found, return the first non-numeric column
        for col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                return col
        
        return None
    
    @classmethod
    def identify_numeric_columns(
        cls,
        df: pd.DataFrame,
        exclude_columns: Optional[List[str]] = None
    ) -> List[str]:
        """
        Identify all numeric columns in a DataFrame.
        
        Requirements: 10.3
        
        Args:
            df: Input DataFrame
            exclude_columns: Optional list of column names to exclude
            
        Returns:
            List of numeric column names
        """
        if exclude_columns is None:
            exclude_columns = []
        
        numeric_columns = []
        
        for col in df.columns:
            if col in exclude_columns:
                continue
            
            # Check if column is numeric
            if pd.api.types.is_numeric_dtype(df[col]):
                numeric_columns.append(col)
            else:
                # Try to convert to numeric
                try:
                    converted = pd.to_numeric(df[col], errors='coerce')
                    # If more than 50% of values are numeric, consider it numeric
                    if converted.notna().sum() / len(converted) > 0.5:
                        numeric_columns.append(col)
                except (ValueError, TypeError):
                    continue
        
        return numeric_columns
