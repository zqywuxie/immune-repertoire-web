"""
Auto Heatmap Analysis Service for the Immune Repertoire Analysis Web Application.
Handles automatic detection of sample folders, file scanning, field detection,
sample grouping, and heatmap generation with group averaging.

Key Features:
1. Scan folder structure to detect sample directories and data files
2. Detect columns/fields in data files for user selection
3. Sample renaming and grouping functionality
4. Group averaging for similarity calculations
"""
import os
import gzip
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set
import logging

import pandas as pd
import numpy as np

from flask_app.exceptions import ValidationError

logger = logging.getLogger(__name__)


@dataclass
class DataFileInfo:
    """Information about a detected data file within a sample folder."""
    filename: str
    filepath: str
    size: int = 0
    rows: int = 0
    columns: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'filename': self.filename,
            'filepath': self.filepath,
            'size': self.size,
            'rows': self.rows,
            'columns': self.columns
        }


@dataclass
class SampleFolderInfo:
    """Information about a detected sample folder."""
    original_name: str  # Original folder name
    display_name: str   # User-customizable display name
    folder_path: str    # Full path to the sample folder
    data_files: List[DataFileInfo] = field(default_factory=list)
    group_name: Optional[str] = None  # Group assignment
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'original_name': self.original_name,
            'display_name': self.display_name,
            'folder_path': self.folder_path,
            'data_files': [f.to_dict() for f in self.data_files],
            'group_name': self.group_name
        }


@dataclass
class FolderScanResult:
    """Result of scanning a base folder for samples."""
    base_path: str
    samples: List[SampleFolderInfo] = field(default_factory=list)
    all_file_types: List[str] = field(default_factory=list)  # Unique file patterns found
    all_chains: List[str] = field(default_factory=list)  # Detected chain types (e.g., TRA, TRB, IGH)
    has_chain_suffix: bool = False  # Whether files use chain suffix pattern
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'base_path': self.base_path,
            'samples': [s.to_dict() for s in self.samples],
            'all_file_types': self.all_file_types,
            'all_chains': self.all_chains,
            'has_chain_suffix': self.has_chain_suffix,
            'summary': self.summary
        }


@dataclass
class FieldMapping:
    """Mapping of required fields to actual column names."""
    cdr3_column: str = ""
    copy_column: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'cdr3_column': self.cdr3_column,
            'copy_column': self.copy_column
        }


@dataclass
class SampleGroup:
    """A group of samples for averaging."""
    name: str
    sample_names: List[str] = field(default_factory=list)
    color: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'sample_names': self.sample_names,
            'color': self.color
        }


class AutoHeatmapService:
    """
    Service for automatic heatmap analysis with folder-based sample detection.
    
    Workflow:
    1. Scan base folder to detect sample subfolders
    2. For each sample folder, detect available data files
    3. User selects which file type to use
    4. Detect columns in selected files for field mapping
    5. User maps cdr3 and copy columns
    6. User can rename samples and create groups
    7. Generate similarity heatmap with optional group averaging
    """
    
    # Common data file extensions to look for
    SUPPORTED_EXTENSIONS = ['.csv', '.tsv', '.txt', '.csv.gz', '.tsv.gz', '.txt.gz']
    
    # Directories to skip during scanning
    SKIP_DIRECTORIES = [
        '.git', '__pycache__', 'node_modules', '.hypothesis',
        '.pytest_cache', '.vscode', '.idea', '__MACOSX', '.DS_Store'
    ]
    
    # Common CDR3 column name patterns
    CDR3_COLUMN_PATTERNS = [
        'cdr3', 'cdr3(pep)', 'cdr3_pep', 'cdr3_aa', 'cdr3_amino',
        'aminoacid', 'amino_acid', 'aa_sequence', 'sequence'
    ]
    
    # Common copy/count column name patterns
    COPY_COLUMN_PATTERNS = [
        'copy', 'copies', 'count', 'counts', 'reads', 'freq',
        'frequency', 'abundance', 'expression'
    ]
    
    # Common chain types for immune repertoire analysis
    CHAIN_TYPES = [
        'TRA', 'TRB', 'TRG', 'TRD',  # T cell receptor chains
        'IGH', 'IGK', 'IGL',          # B cell receptor chains
        'TCRA', 'TCRB', 'TCRG', 'TCRD'  # Alternative naming
    ]
    
    def __init__(self):
        """Initialize the auto heatmap service."""
        pass
    
    def _extract_chain_from_filename(self, filename: str) -> Optional[str]:
        """
        从文件名中提取链类型。
        支持的模式：
        - Sample__TRA.csv
        - Sample_001__IGH.csv.gz
        - Sample__TCRA.csv
        
        Args:
            filename: 文件名
            
        Returns:
            链类型（如'TRA', 'IGH'），如果未找到则返回None
        """
        # 移除扩展名
        name = filename
        for ext in ['.csv.gz', '.tsv.gz', '.txt.gz', '.csv', '.tsv', '.txt']:
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
                break
        
        # 检查是否包含双下划线分隔的链后缀
        if '__' in name:
            # 获取最后一个双下划线后的部分
            parts = name.split('__')
            potential_chain = parts[-1].upper()
            
            # 检查是否是已知的链类型
            if potential_chain in self.CHAIN_TYPES:
                return potential_chain
        
        # 检查单下划线分隔的链后缀（作为备选）
        if '_' in name:
            parts = name.split('_')
            potential_chain = parts[-1].upper()
            
            if potential_chain in self.CHAIN_TYPES:
                return potential_chain
        
        return None
    
    def _extract_sample_name_from_chain_file(self, filename: str) -> Optional[str]:
        """
        从链后缀文件名中提取样本名。
        例如：
        - Sample_001__TRA.csv -> Sample_001
        - Patient_A__IGH.csv.gz -> Patient_A
        - CT_001__TRB.csv -> CT_001
        
        Args:
            filename: 文件名
            
        Returns:
            样本名，如果无法提取则返回None
        """
        # 移除扩展名
        name = filename
        for ext in ['.csv.gz', '.tsv.gz', '.txt.gz', '.csv', '.tsv', '.txt']:
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
                break
        
        # 检查双下划线分隔
        if '__' in name:
            parts = name.split('__')
            # 检查最后一部分是否是链类型
            if len(parts) >= 2 and parts[-1].upper() in self.CHAIN_TYPES:
                # 返回除最后一部分外的所有部分
                return '__'.join(parts[:-1])
        
        # 检查单下划线分隔
        if '_' in name:
            parts = name.split('_')
            # 检查最后一部分是否是链类型
            if len(parts) >= 2 and parts[-1].upper() in self.CHAIN_TYPES:
                # 返回除最后一部分外的所有部分
                return '_'.join(parts[:-1])
        
        return None

    def _filename_matches_chain(self, filename: str, chain: str) -> bool:
        """Match chain suffixes case-insensitively after stripping supported extensions."""
        name = filename
        for ext in ['.csv.gz', '.tsv.gz', '.txt.gz', '.csv', '.tsv', '.txt']:
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
                break

        normalized_name = name.upper()
        normalized_chain = (chain or '').upper()
        return (
            normalized_name.endswith(f'__{normalized_chain}')
            or normalized_name.endswith(f'_{normalized_chain}')
        )
    
    def scan_base_folder(self, base_path: str) -> FolderScanResult:
        """
        Scan a base folder to detect sample subfolders and their data files.
        Supports nested directory structures with deeper recursion.
        
        Args:
            base_path: Path to the base folder containing sample subfolders
            
        Returns:
            FolderScanResult with detected samples and file types
        """
        # Validate path
        if not base_path:
            raise ValidationError(
                message="请输入分析文件夹路径",
                details={'path': base_path}
            )
        
        # Normalize path - handle Windows paths properly
        base_path = os.path.normpath(base_path.strip())
        
        # Debug: Log the path
        logger.info(f"Original path: {base_path}")
        logger.info(f"Path type: {type(base_path)}")
        logger.info(f"Path bytes: {base_path.encode('utf-8')}")
        
        path = Path(base_path)
        
        if not path.exists():
            raise ValidationError(
                message=f"指定路径不存在: {base_path}",
                details={'path': base_path}
            )
        
        if not path.is_dir():
            raise ValidationError(
                message=f"指定路径不是目录: {base_path}",
                details={'path': base_path}
            )
        
        samples: List[SampleFolderInfo] = []
        all_file_types: Set[str] = set()
        all_chains: Set[str] = set()
        chain_suffix_count = 0
        total_files = 0
        
        try:
            # Use os.walk for more robust directory traversal
            sample_dict = {}  # Use dict to avoid duplicates
            
            for root, dirs, files in os.walk(base_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in self.SKIP_DIRECTORIES]
                
                # Check if we have data files in this directory
                data_files_in_dir = []
                for file in files:
                    if self._is_data_file(file):
                        file_path = os.path.join(root, file)
                        file_info = self._get_file_info(file, file_path)
                        data_files_in_dir.append(file_info)
                        all_file_types.add(file)
                        total_files += 1
                        
                        # 检测链后缀
                        chain = self._extract_chain_from_filename(file)
                        if chain:
                            all_chains.add(chain)
                            chain_suffix_count += 1
                
                # If we found data files, determine the sample name
                if data_files_in_dir:
                    # 检查是否为链后缀模式
                    chain_files = [f for f in data_files_in_dir if self._extract_chain_from_filename(f.filename)]
                    
                    if chain_files and len(chain_files) == len(data_files_in_dir):
                        # 所有文件都是链后缀文件，从文件名提取样本名
                        for file_info in data_files_in_dir:
                            sample_name = self._extract_sample_name_from_chain_file(file_info.filename)
                            if sample_name:
                                # Use dict to avoid duplicates
                                if sample_name in sample_dict:
                                    # Merge data files
                                    sample_dict[sample_name].data_files.append(file_info)
                                else:
                                    sample_info = SampleFolderInfo(
                                        original_name=sample_name,
                                        display_name=sample_name,
                                        folder_path=root,
                                        data_files=[file_info]
                                    )
                                    sample_dict[sample_name] = sample_info
                    else:
                        # 传统模式：使用目录名作为样本名
                        rel_path = os.path.relpath(root, base_path)
                        if rel_path == '.':
                            # Files are in the base directory itself
                            sample_name = os.path.basename(base_path)
                        else:
                            # Use the first directory level as sample name
                            sample_name = rel_path.split(os.sep)[0]
                        
                        # Use dict to avoid duplicates
                        if sample_name in sample_dict:
                            # Merge data files
                            sample_dict[sample_name].data_files.extend(data_files_in_dir)
                        else:
                            sample_info = SampleFolderInfo(
                                original_name=sample_name,
                                display_name=sample_name,
                                folder_path=root,
                                data_files=data_files_in_dir
                            )
                            sample_dict[sample_name] = sample_info
            
            # Convert dict to list
            samples = list(sample_dict.values())
            
            # 判断是否大部分文件都使用链后缀模式（超过50%）
            has_chain_suffix = total_files > 0 and (chain_suffix_count / total_files) > 0.5
        
        except PermissionError as e:
            raise ValidationError(
                message=f"无法访问该路径，请检查权限设置: {base_path}",
                details={'path': base_path}
            )
        except Exception as e:
            # Log the error but don't fail completely
            logger.error(f"Error scanning directory {base_path}: {e}")
            raise ValidationError(
                message=f"扫描目录时出错: {str(e)}",
                details={'path': base_path, 'error': str(e)}
            )
        
        # Sort samples by name
        samples.sort(key=lambda s: s.original_name.lower())
        
        # Generate summary
        if samples:
            if has_chain_suffix and all_chains:
                summary = f"找到 {len(samples)} 个样本，检测到 {len(all_chains)} 种链类型：{', '.join(sorted(all_chains))}"
            else:
                summary = f"找到 {len(samples)} 个样本文件夹，共 {len(all_file_types)} 种数据文件"
        else:
            summary = "未在该路径下找到样本目录，请确认路径格式。提示：请选择包含样本子文件夹的根目录"
        
        return FolderScanResult(
            base_path=base_path,
            samples=samples,
            all_file_types=sorted(list(all_file_types)),
            all_chains=sorted(list(all_chains)),
            has_chain_suffix=has_chain_suffix,
            summary=summary
        )
    
    def _scan_sample_folder(self, folder_name: str, folder_path: str) -> SampleFolderInfo:
        """
        Scan a single sample folder for data files.
        Recursively searches subdirectories.
        """
        sample_info = SampleFolderInfo(
            original_name=folder_name,
            display_name=folder_name,  # Default display name is the folder name
            folder_path=folder_path
        )
        
        data_files = self._find_data_files_recursive(folder_path)
        sample_info.data_files = data_files
        
        return sample_info
    
    def _find_data_files_recursive(self, directory: str, max_depth: int = 5) -> List[DataFileInfo]:
        """
        Recursively find data files in a directory.
        Increased max_depth to 5 to handle deeper nested structures.
        
        Args:
            directory: Directory to search
            max_depth: Maximum recursion depth (default 5)
            
        Returns:
            List of DataFileInfo objects
        """
        data_files: List[DataFileInfo] = []
        
        if max_depth <= 0:
            return data_files
        
        try:
            entries = os.listdir(directory)
            logger.debug(f"Scanning directory: {directory}, found {len(entries)} entries")
            
            for entry in entries:
                if entry in self.SKIP_DIRECTORIES or entry.startswith('.'):
                    continue
                
                entry_path = os.path.join(directory, entry)
                
                if os.path.isfile(entry_path):
                    if self._is_data_file(entry):
                        file_info = self._get_file_info(entry, entry_path)
                        data_files.append(file_info)
                        logger.debug(f"Added data file: {entry}")
                elif os.path.isdir(entry_path):
                    # Recurse into subdirectory
                    sub_files = self._find_data_files_recursive(entry_path, max_depth - 1)
                    data_files.extend(sub_files)
        
        except PermissionError as e:
            logger.warning(f"Permission denied accessing {directory}: {e}")
        except OSError as e:
            logger.warning(f"OS error accessing {directory}: {e}")
        
        logger.debug(f"Returning {len(data_files)} data files from {directory}")
        return data_files
    
    def _is_data_file(self, filename: str) -> bool:
        """Check if a file is a supported data file."""
        lower_name = filename.lower()
        return any(lower_name.endswith(ext) for ext in self.SUPPORTED_EXTENSIONS)

    @staticmethod
    def _is_gzip_file(filepath: str) -> bool:
        """Check whether a file path points to a gzip-compressed text file."""
        return str(filepath).lower().endswith('.gz')

    def _open_text_file(self, filepath: str):
        """Open plain-text and gzip-text files in one place."""
        if self._is_gzip_file(filepath):
            return gzip.open(filepath, 'rt', encoding='utf-8', errors='ignore')
        return open(filepath, 'r', encoding='utf-8', errors='ignore')
    
    def _get_file_info(self, filename: str, filepath: str) -> DataFileInfo:
        """Get information about a data file."""
        file_info = DataFileInfo(
            filename=filename,
            filepath=filepath
        )
        
        try:
            file_info.size = os.path.getsize(filepath)
            
            # Try to read columns - but don't fail if we can't
            try:
                # Detect separator
                sep = self._detect_separator(filepath)
                df = pd.read_csv(
                    filepath,
                    sep=sep,
                    nrows=5,
                    encoding='utf-8',
                    on_bad_lines='skip',
                    compression='infer'
                )
                file_info.columns = df.columns.tolist()
                
                # For gzip files, skip full row counting to avoid expensive decompression during scan.
                if self._is_gzip_file(filepath):
                    file_info.rows = 0
                else:
                    try:
                        with self._open_text_file(filepath) as f:
                            file_info.rows = sum(1 for _ in f) - 1
                        if file_info.rows < 0:
                            file_info.rows = 0
                    except Exception:
                        file_info.rows = 0
            except Exception as e:
                # Even if we can't read the file, still return the file info
                logger.debug(f"Could not read columns from {filepath}: {e}")
                file_info.columns = []
                file_info.rows = 0
        
        except Exception as e:
            logger.warning(f"Could not get file size for {filepath}: {e}")
        
        return file_info
    
    def _detect_separator(self, filepath: str) -> str:
        """Detect the separator used in a file."""
        try:
            with self._open_text_file(filepath) as f:
                first_line = f.readline()
                if '\t' in first_line:
                    return '\t'
                elif ',' in first_line:
                    return ','
        except Exception:
            pass
        return ','
    
    def get_file_columns(self, filepath: str) -> Dict[str, Any]:
        """
        Get columns from a specific file for field mapping.
        
        Returns:
            Dictionary with columns list and suggested mappings
        """
        if not os.path.exists(filepath):
            raise ValidationError(
                message=f"文件不存在: {filepath}",
                details={'filepath': filepath}
            )
        
        try:
            sep = self._detect_separator(filepath)
            df = pd.read_csv(
                filepath,
                sep=sep,
                nrows=5,
                encoding='utf-8',
                on_bad_lines='skip',
                compression='infer'
            )
            columns = df.columns.tolist()
            
            # Try to auto-detect CDR3 and copy columns
            suggested_cdr3 = self._find_matching_column(columns, self.CDR3_COLUMN_PATTERNS)
            suggested_copy = self._find_matching_column(columns, self.COPY_COLUMN_PATTERNS)
            
            # Get sample data for preview, replacing pandas NaN with JSON-safe None
            preview_df = df.head(5)
            sample_data = preview_df.where(pd.notna(preview_df), None).values.tolist()
            
            return {
                'columns': columns,
                'suggested_cdr3': suggested_cdr3,
                'suggested_copy': suggested_copy,
                'sample_data': sample_data,
                'rows': len(df)
            }
        
        except Exception as e:
            raise ValidationError(
                message=f"无法读取文件: {str(e)}",
                details={'filepath': filepath, 'error': str(e)}
            )
    
    def _find_matching_column(self, columns: List[str], patterns: List[str]) -> Optional[str]:
        """Find a column that matches any of the given patterns."""
        for col in columns:
            col_lower = col.lower().strip()
            for pattern in patterns:
                if pattern in col_lower or col_lower == pattern:
                    return col
        return None
    
    def load_sample_data(
        self,
        samples: List[SampleFolderInfo],
        file_pattern: str,
        field_mapping: FieldMapping
    ) -> Dict[str, pd.DataFrame]:
        """
        Load data from selected samples using the specified file pattern and field mapping.
        
        Args:
            samples: List of sample folder info
            file_pattern: Filename pattern to look for in each sample
            field_mapping: Mapping of cdr3 and copy columns
            
        Returns:
            Dictionary mapping sample display name to DataFrame with cdr3 and copy columns
        """
        sample_data: Dict[str, pd.DataFrame] = {}
        
        for sample in samples:
            # Find the matching file in this sample
            matching_file = None
            for df_info in sample.data_files:
                if df_info.filename == file_pattern or file_pattern in df_info.filename:
                    matching_file = df_info
                    break
            
            if not matching_file:
                logger.warning(f"No matching file found for sample {sample.display_name}")
                continue
            
            try:
                sep = self._detect_separator(matching_file.filepath)
                df = pd.read_csv(
                    matching_file.filepath,
                    sep=sep,
                    compression='infer',
                    low_memory=False
                )
                
                # Extract only the needed columns
                cdr3_col = field_mapping.cdr3_column
                copy_col = field_mapping.copy_column
                
                if cdr3_col not in df.columns:
                    logger.warning(f"CDR3 column '{cdr3_col}' not found in {matching_file.filepath}")
                    continue
                
                if copy_col not in df.columns:
                    logger.warning(f"Copy column '{copy_col}' not found in {matching_file.filepath}")
                    continue
                
                # Create normalized DataFrame
                normalized_df = pd.DataFrame({
                    'cdr3': df[cdr3_col],
                    'copy': pd.to_numeric(df[copy_col], errors='coerce').fillna(0)
                })
                
                sample_data[sample.display_name] = normalized_df
                
            except Exception as e:
                logger.error(f"Error loading data for sample {sample.display_name}: {e}")
                continue
        
        return sample_data
    
    def load_sample_data_for_single_chain(
        self,
        samples: List[SampleFolderInfo],
        chain: str,
        field_mapping: FieldMapping
    ) -> Dict[str, pd.DataFrame]:
        """
        为单条链加载样本数据。
        
        Args:
            samples: 样本文件夹信息列表
            chain: 链类型（如'TRA', 'IGH'）
            field_mapping: 字段映射
            
        Returns:
            字典，映射样本显示名称到DataFrame
        """
        sample_data: Dict[str, pd.DataFrame] = {}
        
        for sample in samples:
            # 查找匹配此链的文件
            matching_file = None
            for df_info in sample.data_files:
                if self._filename_matches_chain(df_info.filename, chain):
                    matching_file = df_info
                    break
            
            if matching_file:
                try:
                    sep = self._detect_separator(matching_file.filepath)
                    df = pd.read_csv(
                        matching_file.filepath,
                        sep=sep,
                        compression='infer',
                        low_memory=False
                    )
                    
                    # 提取需要的列
                    cdr3_col = field_mapping.cdr3_column
                    copy_col = field_mapping.copy_column
                    
                    if cdr3_col in df.columns and copy_col in df.columns:
                        # 创建规范化的DataFrame
                        normalized_df = pd.DataFrame({
                            'cdr3': df[cdr3_col],
                            'copy': pd.to_numeric(df[copy_col], errors='coerce').fillna(0)
                        })
                        sample_data[sample.display_name] = normalized_df
                        logger.info(f"Loaded chain {chain} for sample {sample.display_name}, {len(normalized_df)} CDR3s")
                    else:
                        logger.warning(f"Required columns not found in {matching_file.filepath}")
                
                except Exception as e:
                    logger.error(f"Error loading chain {chain} for sample {sample.display_name}: {e}")
                    continue
        
        return sample_data
    
    def load_sample_data_by_chains(
        self,
        samples: List[SampleFolderInfo],
        selected_chains: List[str],
        field_mapping: FieldMapping
    ) -> Dict[str, Dict[str, pd.DataFrame]]:
        """
        按链类型加载样本数据（链模式）。
        为每条链分别加载数据，返回按链分组的数据。
        
        Args:
            samples: 样本文件夹信息列表
            selected_chains: 选中的链类型列表（如['TRA', 'TRB', 'IGH']）
            field_mapping: 字段映射
            
        Returns:
            字典，映射链类型到样本数据字典
            例如: {'TRA': {'Sample1': df1, 'Sample2': df2}, 'IGH': {...}}
        """
        chain_data: Dict[str, Dict[str, pd.DataFrame]] = {}
        
        for chain in selected_chains:
            sample_data = self.load_sample_data_for_single_chain(samples, chain, field_mapping)
            if sample_data and len(sample_data) >= 2:
                chain_data[chain] = sample_data
                logger.info(f"Chain {chain}: loaded {len(sample_data)} samples")
            else:
                logger.warning(f"Chain {chain}: insufficient samples ({len(sample_data) if sample_data else 0})")
        
        return chain_data
    
    def calculate_all_metrics(
        self,
        sample_data: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.DataFrame]:
        """
        Calculate all 6 similarity metrics at once.
        
        Args:
            sample_data: Dictionary mapping sample name to DataFrame with 'cdr3' and 'copy' columns
            
        Returns:
            Dictionary mapping metric names to similarity matrices
        """
        return {
            'r2_inner': self.calculate_similarity_matrix(sample_data, 'r2_inner'),
            'r2_outer': self.calculate_similarity_matrix(sample_data, 'r2_outer'),
            'cdr3_sharing': self.calculate_similarity_matrix(sample_data, 'cdr3_sharing'),
            'expression_sharing': self.calculate_similarity_matrix(sample_data, 'expression_sharing'),
            'morisita_horn': self.calculate_similarity_matrix(sample_data, 'morisita_horn'),
            'sorensen': self.calculate_similarity_matrix(sample_data, 'sorensen')
        }
    
    def calculate_similarity_matrix(
        self,
        sample_data: Dict[str, pd.DataFrame],
        metric: str = 'r2_inner'
    ) -> pd.DataFrame:
        """
        Calculate similarity matrix between samples using specified metric.
        Supports all 6 metrics from SimilarityAnalyzer:
        - r2_inner: Inner join R² correlation
        - r2_outer: Outer join R² correlation
        - cdr3_sharing: Unique CDR3 sharing (directional)
        - expression_sharing: Expression-based sharing (directional)
        - morisita_horn: Morisita-Horn ecological index
        - sorensen: Sorensen-Dice coefficient
        
        Args:
            sample_data: Dictionary mapping sample name to DataFrame with 'cdr3' and 'copy' columns
            metric: Similarity metric to use
            
        Returns:
            Similarity matrix as DataFrame
        """
        sample_names = list(sample_data.keys())
        n = len(sample_names)
        
        if n == 0:
            return pd.DataFrame()
        
        # Build CDR3 sets and abundance dictionaries
        cdr3_sets: Dict[str, Set[str]] = {}
        abundance: Dict[str, Dict[str, float]] = {}
        
        for name, df in sample_data.items():
            cdr3_sets[name] = set(df['cdr3'].dropna().unique())
            abundance[name] = df.groupby('cdr3')['copy'].sum().to_dict()
        
        # Calculate similarity matrix based on metric
        matrix = np.ones((n, n))  # Diagonal is always 1.0
        
        for i in range(n):
            for j in range(i + 1, n):
                name_i = sample_names[i]
                name_j = sample_names[j]
                
                if metric == 'r2_inner':
                    sim = self._calculate_r2_inner(abundance[name_i], abundance[name_j])
                    matrix[i, j] = sim
                    matrix[j, i] = sim
                elif metric == 'r2_outer':
                    sim = self._calculate_r2_outer(abundance[name_i], abundance[name_j])
                    matrix[i, j] = sim
                    matrix[j, i] = sim
                elif metric == 'cdr3_sharing':
                    # Directional metric
                    sim_i_to_j, sim_j_to_i = self._calculate_cdr3_sharing_directional(
                        cdr3_sets[name_i], cdr3_sets[name_j]
                    )
                    matrix[i, j] = sim_j_to_i  # B→A (column to row)
                    matrix[j, i] = sim_i_to_j  # A→B (row to column)
                elif metric == 'expression_sharing':
                    # Directional metric
                    sim_i_to_j, sim_j_to_i = self._calculate_expression_sharing(
                        abundance[name_i], abundance[name_j]
                    )
                    matrix[i, j] = sim_j_to_i  # B→A (column to row)
                    matrix[j, i] = sim_i_to_j  # A→B (row to column)
                elif metric == 'morisita_horn':
                    sim = self._calculate_morisita_horn(abundance[name_i], abundance[name_j])
                    matrix[i, j] = sim
                    matrix[j, i] = sim
                elif metric == 'sorensen':
                    sim = self._calculate_sorensen(cdr3_sets[name_i], cdr3_sets[name_j])
                    matrix[i, j] = sim
                    matrix[j, i] = sim
                else:
                    # Default to r2_inner
                    sim = self._calculate_r2_inner(abundance[name_i], abundance[name_j])
                    matrix[i, j] = sim
                    matrix[j, i] = sim
        
        return pd.DataFrame(matrix, index=sample_names, columns=sample_names)
    
    def _calculate_r2_inner(
        self,
        abundance_a: Dict[str, float],
        abundance_b: Dict[str, float]
    ) -> float:
        """
        Calculate R² inner (inner join correlation coefficient).
        
        Formula: R² = corr(abundance_A[shared], abundance_B[shared])²
        Only uses CDR3 sequences present in both samples.
        
        Boundary cases:
        - shared CDR3 < 2: return 0.0
        - std_a > 0 and std_b > 0: normal calculation
        - std_a = 0 and std_b = 0: return 1.0 (both constant)
        - only one std = 0: return 0.0
        """
        if not abundance_a or not abundance_b:
            return 0.0
        
        # Inner join: only shared CDR3
        shared_cdr3 = set(abundance_a.keys()) & set(abundance_b.keys())
        
        if len(shared_cdr3) < 2:
            return 0.0
        
        # Extract abundances for shared CDR3
        shared_list = sorted(shared_cdr3)
        values_a = np.array([abundance_a[cdr3] for cdr3 in shared_list])
        values_b = np.array([abundance_b[cdr3] for cdr3 in shared_list])
        
        # Calculate standard deviations
        std_a = np.std(values_a)
        std_b = np.std(values_b)
        
        # Handle boundary cases
        if std_a > 0 and std_b > 0:
            corr = np.corrcoef(values_a, values_b)[0, 1]
            return corr ** 2 if not np.isnan(corr) else 0.0
        elif std_a == 0 and std_b == 0:
            return 1.0  # Both constant, perfect correlation
        else:
            return 0.0  # One constant, no correlation
    
    def _calculate_r2_outer(
        self,
        abundance_a: Dict[str, float],
        abundance_b: Dict[str, float]
    ) -> float:
        """
        Calculate R² outer (outer join correlation coefficient).
        
        Formula: R² = corr(abundance_A[all], abundance_B[all])²
        Uses all CDR3 from both samples, missing values set to 0.
        
        Boundary cases:
        - total CDR3 < 2: return 0.0
        - std_a > 0 and std_b > 0: normal calculation
        - std_a = 0 and std_b = 0: return 1.0 (both constant)
        - only one std = 0: return 0.0
        """
        if not abundance_a or not abundance_b:
            return 0.0
        
        # Outer join: all CDR3
        all_cdr3 = set(abundance_a.keys()) | set(abundance_b.keys())
        
        if len(all_cdr3) < 2:
            return 0.0
        
        # Extract abundances, using 0 for missing CDR3
        all_list = sorted(all_cdr3)
        values_a = np.array([abundance_a.get(cdr3, 0) for cdr3 in all_list])
        values_b = np.array([abundance_b.get(cdr3, 0) for cdr3 in all_list])
        
        # Calculate standard deviations
        std_a = np.std(values_a)
        std_b = np.std(values_b)
        
        # Handle boundary cases
        if std_a > 0 and std_b > 0:
            corr = np.corrcoef(values_a, values_b)[0, 1]
            return corr ** 2 if not np.isnan(corr) else 0.0
        elif std_a == 0 and std_b == 0:
            return 1.0  # Both constant, perfect correlation
        else:
            return 0.0  # One constant, no correlation
    
    def _calculate_cdr3_sharing_directional(
        self,
        set_a: Set[str],
        set_b: Set[str]
    ) -> Tuple[float, float]:
        """
        Calculate CDR3 sharing (directional).
        
        Formula:
        - A→B: intersection / |A|
        - B→A: intersection / |B|
        
        Returns:
            Tuple of (A→B, B→A)
        """
        if not set_a or not set_b:
            return 0.0, 0.0
        
        intersection = len(set_a & set_b)
        
        sim_a_to_b = intersection / len(set_a) if len(set_a) > 0 else 0.0
        sim_b_to_a = intersection / len(set_b) if len(set_b) > 0 else 0.0
        
        return sim_a_to_b, sim_b_to_a
    
    def _calculate_expression_sharing(
        self,
        abundance_a: Dict[str, float],
        abundance_b: Dict[str, float]
    ) -> Tuple[float, float]:
        """
        Directional expression sharing
        
        A→B: fraction of reads in A that belong to CDR3s also present in B
        B→A: fraction of reads in B that belong to CDR3s also present in A
        """
        if not abundance_a or not abundance_b:
            return 0.0, 0.0
        
        set_a = set(abundance_a.keys())
        set_b = set(abundance_b.keys())
        shared_cdr3 = set_a & set_b

        total_reads_a = sum(abundance_a.values())
        total_reads_b = sum(abundance_b.values())

        shared_reads_a = sum(abundance_a[c] for c in shared_cdr3)
        shared_reads_b = sum(abundance_b[c] for c in shared_cdr3)

        a_to_b = shared_reads_a / total_reads_a if total_reads_a > 0 else 0.0
        b_to_a = shared_reads_b / total_reads_b if total_reads_b > 0 else 0.0

        return a_to_b, b_to_a
    
    def _calculate_sorensen(self, set_a: Set[str], set_b: Set[str]) -> float:
        """
        Calculate Sorensen-Dice coefficient.
        
        Formula: S = 2 * |A ∩ B| / (|A| + |B|)
        """
        if not set_a or not set_b:
            return 0.0
        
        intersection = len(set_a & set_b)
        size_sum = len(set_a) + len(set_b)
        
        return (2 * intersection) / size_sum if size_sum > 0 else 0.0
    
    def _calculate_morisita_horn(
        self,
        abundance_a: Dict[str, float],
        abundance_b: Dict[str, float]
    ) -> float:
        """
        Calculate Morisita-Horn ecological similarity index.
        
        Formula: MH = 2 * Σ(n_Ai * n_Bi) / [(D_A + D_B) * N_A * N_B]
        
        Where:
        - n_Ai = abundance of clone i in sample A
        - N_A = total reads in sample A
        - D_A = Simpson diversity index = Σ(n_Ai² / N_A²)
        """
        if not abundance_a or not abundance_b:
            return 0.0
        
        # Get all CDR3s (union)
        all_cdr3 = set(abundance_a.keys()) | set(abundance_b.keys())
        
        # Extract abundance vectors
        all_list = sorted(all_cdr3)
        n_A = np.array([abundance_a.get(cdr3, 0) for cdr3 in all_list])
        n_B = np.array([abundance_b.get(cdr3, 0) for cdr3 in all_list])
        
        N_A = np.sum(n_A)  # Total reads in sample A
        N_B = np.sum(n_B)  # Total reads in sample B
        
        if N_A == 0 or N_B == 0:
            return 0.0
        
        # Calculate Simpson diversity index
        D_A = np.sum((n_A / N_A) ** 2)
        D_B = np.sum((n_B / N_B) ** 2)
        
        # Calculate Morisita-Horn index
        numerator = 2 * np.sum(n_A * n_B)
        denominator = (D_A + D_B) * N_A * N_B
        
        if denominator > 0:
            return numerator / denominator
        else:
            return 0.0
    
    def calculate_group_averages(
        self,
        similarity_matrix: pd.DataFrame,
        groups: List[SampleGroup]
    ) -> pd.DataFrame:
        """
        Calculate group average similarity matrix.
        
        For each pair of groups, calculate the average similarity
        between all samples in group A and all samples in group B.
        
        Args:
            similarity_matrix: Original sample-level similarity matrix
            groups: List of sample groups
            
        Returns:
            Group-level similarity matrix
        """
        if not groups:
            return pd.DataFrame()
        
        # Filter groups to only include samples that exist in the matrix
        valid_groups: List[SampleGroup] = []
        for group in groups:
            valid_samples = [s for s in group.sample_names if s in similarity_matrix.index]
            if valid_samples:
                valid_groups.append(SampleGroup(
                    name=group.name,
                    sample_names=valid_samples,
                    color=group.color
                ))
        
        if not valid_groups:
            return pd.DataFrame()
        
        n_groups = len(valid_groups)
        group_names = [g.name for g in valid_groups]
        
        group_matrix = np.zeros((n_groups, n_groups))
        
        for i, group_a in enumerate(valid_groups):
            for j, group_b in enumerate(valid_groups):
                if i == j:
                    # Within-group average (excluding diagonal)
                    avg = self._calculate_within_group_average(
                        similarity_matrix, group_a.sample_names
                    )
                else:
                    # Between-group average
                    avg = self._calculate_between_group_average(
                        similarity_matrix, group_a.sample_names, group_b.sample_names
                    )
                group_matrix[i, j] = avg
        
        return pd.DataFrame(group_matrix, index=group_names, columns=group_names)
    
    def _calculate_within_group_average(
        self,
        matrix: pd.DataFrame,
        samples: List[str]
    ) -> float:
        """Calculate average similarity within a group (excluding diagonal)."""
        if len(samples) < 2:
            return 1.0  # Single sample has perfect self-similarity
        
        values = []
        for i, s1 in enumerate(samples):
            for j, s2 in enumerate(samples):
                if i < j:  # Only upper triangle, excluding diagonal
                    values.append(matrix.loc[s1, s2])
        
        return np.mean(values) if values else 1.0
    
    def _calculate_between_group_average(
        self,
        matrix: pd.DataFrame,
        samples_a: List[str],
        samples_b: List[str]
    ) -> float:
        """Calculate average similarity between two groups."""
        values = []
        for s1 in samples_a:
            for s2 in samples_b:
                values.append(matrix.loc[s1, s2])
        
        return np.mean(values) if values else 0.0


# Singleton instance
_auto_heatmap_service: Optional[AutoHeatmapService] = None


def get_auto_heatmap_service() -> AutoHeatmapService:
    """Get the singleton AutoHeatmapService instance."""
    global _auto_heatmap_service
    if _auto_heatmap_service is None:
        _auto_heatmap_service = AutoHeatmapService()
    return _auto_heatmap_service
