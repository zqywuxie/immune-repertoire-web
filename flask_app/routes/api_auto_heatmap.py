"""
API routes for automatic heatmap analysis with folder-based sample detection.
Provides endpoints for scanning folders, detecting files, field mapping,
sample renaming/grouping, heatmap generation, and CDR3 shared list export.
"""

import os
import io
import base64
import logging
from typing import Dict, List, Optional, Any
from flask import Blueprint, request, jsonify, send_file

import pandas as pd
import numpy as np

from flask_app.services.auto_heatmap_service import (
    get_auto_heatmap_service,
    SampleFolderInfo,
    FieldMapping,
    SampleGroup,
    DataFileInfo
)
from flask_app.services.heatmap_generator import HeatmapGenerator, HeatmapConfig
from flask_app.exceptions import ValidationError

try:
    from flask_app.services.cdr3_export_service import get_cdr3_export_service
except ModuleNotFoundError:
    def get_cdr3_export_service():
        raise RuntimeError("CDR3 export service is not available in this build.")

logger = logging.getLogger(__name__)

# Create blueprint
auto_heatmap_bp = Blueprint('auto_heatmap', __name__, url_prefix='/api/auto-heatmap')


@auto_heatmap_bp.route('/scan-folder', methods=['POST'])
def scan_folder():
    """
    Scan a base folder to detect sample subfolders and their data files.
    POST /api/auto-heatmap/scan-folder
    
    Request body:
        {
            "base_path": "D:\\...\\AnalysisFilesUMI"
        }
    
    Returns:
        {
            "success": true,
            "base_path": "...",
            "samples": [
                {
                    "original_name": "PosCtrl_iR1298C",
                    "display_name": "PosCtrl_iR1298C",
                    "folder_path": "...",
                    "data_files": [
                        {"filename": "..._pep.csv", "filepath": "...", "columns": [...]}
                    ]
                }
            ],
            "all_file_types": ["..._pep.csv", "..._CDR3_list_1.csv"],
            "summary": "找到 8 个样本文件夹，共 5 种数据文件"
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="请求体不能为空",
                details={'field': 'body'}
            )
        
        base_path = data.get('base_path')
        
        if not base_path:
            raise ValidationError(
                message="请输入分析文件夹路径",
                details={'field': 'base_path'}
            )
        
        # Quick test without service first
        quick_result = {
            'path_exists': os.path.exists(base_path),
            'is_directory': os.path.isdir(base_path) if os.path.exists(base_path) else False
        }
        
        if not quick_result['path_exists']:
            return jsonify({
                'success': False,
                'error': 'PATH_NOT_EXISTS',
                'message': f"路径不存在: {base_path}",
                'quick_test': quick_result
            }), 400
        
        if not quick_result['is_directory']:
            return jsonify({
                'success': False,
                'error': 'NOT_DIRECTORY',
                'message': f"路径不是目录: {base_path}",
                'quick_test': quick_result
            }), 400
        
        service = get_auto_heatmap_service()
        
        # Debug logging
        logger.info(f"Scanning base path: {base_path}")
        logger.info(f"Path exists: {os.path.exists(base_path)}")
        
        scan_result = service.scan_base_folder(base_path)
        
        # Debug the result
        logger.info(f"Scan result - samples: {len(scan_result.samples)}, file types: {len(scan_result.all_file_types)}")
        
        response = {
            'success': True,
            **scan_result.to_dict()
        }
        
        # Add debug info to response (remove in production)
        response['_debug'] = {
            'base_path': base_path,
            'samples_found': len(scan_result.samples),
            'file_types_found': len(scan_result.all_file_types),
            'quick_test': quick_result
        }
        
        return jsonify(response)
    
    except ValidationError as e:
        logger.warning(f"Validation error in scan_folder: {e.message}")
        return jsonify({
            'success': False,
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400
    
    except Exception as e:
        logger.error(f"Error scanning folder: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'SCAN_ERROR',
            'message': f"扫描文件夹时发生错误: {str(e)}"
        }), 500


@auto_heatmap_bp.route('/get-file-columns', methods=['POST'])
def get_file_columns():
    """
    Get columns from a specific file for field mapping.
    POST /api/auto-heatmap/get-file-columns
    
    Request body:
        {
            "filepath": "D:\\...\\sample\\data.csv"
        }
    
    Returns:
        {
            "success": true,
            "columns": ["CDR3(pep)", "V", "J", "copy", ...],
            "suggested_cdr3": "CDR3(pep)",
            "suggested_copy": "copy",
            "sample_data": [[...], [...], ...]
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="请求体不能为空",
                details={'field': 'body'}
            )
        
        filepath = data.get('filepath')
        
        if not filepath:
            raise ValidationError(
                message="请提供文件路径",
                details={'field': 'filepath'}
            )
        
        service = get_auto_heatmap_service()
        result = service.get_file_columns(filepath)
        
        return jsonify({
            'success': True,
            **result
        })
    
    except ValidationError as e:
        logger.warning(f"Validation error in get_file_columns: {e.message}")
        return jsonify({
            'success': False,
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400
    
    except Exception as e:
        logger.error(f"Error getting file columns: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'FILE_ERROR',
            'message': f"读取文件列时发生错误: {str(e)}"
        }), 500


@auto_heatmap_bp.route('/generate-heatmap', methods=['POST'])
def generate_heatmap():
    """
    Generate similarity heatmap from selected samples with optional grouping.
    POST /api/auto-heatmap/generate-heatmap
    
    Request body:
        {
            "samples": [
                {
                    "original_name": "PosCtrl_iR1298C",
                    "display_name": "Sample 1",
                    "folder_path": "...",
                    "data_files": [...],
                    "group_name": "Group A"
                }
            ],
            "file_pattern": "..._pep.csv",
            "field_mapping": {
                "cdr3_column": "CDR3(pep)",
                "copy_column": "copy"
            },
            "groups": [
                {"name": "Group A", "sample_names": ["Sample 1", "Sample 2"]},
                {"name": "Group B", "sample_names": ["Sample 3", "Sample 4"]}
            ],
            "metric": "r2_inner",  // Options: r2_inner, r2_outer, cdr3_sharing, expression_sharing, morisita_horn, sorensen
            "config": {
                "title": "Similarity Heatmap",
                "color_scheme": "viridis",
                "annotation": true
            }
        }
    
    Returns:
        {
            "success": true,
            "heatmap_image": "base64_encoded_png",
            "matrix_data": {
                "samples": [...],
                "values": [[...], ...]
            },
            "grouped_heatmap_image": "base64_encoded_png",
            "grouped_matrix_data": {...}
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="请求体不能为空",
                details={'field': 'body'}
            )
        
        # Parse samples
        samples_data = data.get('samples', [])
        if not samples_data:
            raise ValidationError(
                message="请选择至少一个样本",
                details={'field': 'samples'}
            )
        
        samples = []
        for s in samples_data:
            data_files = []
            for df in s.get('data_files', []):
                data_files.append(DataFileInfo(
                    filename=df.get('filename', ''),
                    filepath=df.get('filepath', ''),
                    size=df.get('size', 0),
                    rows=df.get('rows', 0),
                    columns=df.get('columns', [])
                ))
            
            samples.append(SampleFolderInfo(
                original_name=s.get('original_name', ''),
                display_name=s.get('display_name', s.get('original_name', '')),
                folder_path=s.get('folder_path', ''),
                data_files=data_files,
                group_name=s.get('group_name')
            ))
        
        # Parse field mapping
        field_mapping_data = data.get('field_mapping', {})
        field_mapping = FieldMapping(
            cdr3_column=field_mapping_data.get('cdr3_column', ''),
            copy_column=field_mapping_data.get('copy_column', '')
        )
        
        if not field_mapping.cdr3_column or not field_mapping.copy_column:
            raise ValidationError(
                message="请设置CDR3和Copy字段映射",
                details={'field': 'field_mapping'}
            )
        
        file_pattern = data.get('file_pattern')
        selected_chains = data.get('selected_chains')
        
        # 验证：必须提供file_pattern或selected_chains之一
        if not file_pattern and not selected_chains:
            raise ValidationError(
                message="请选择数据文件类型或链类型",
                details={'field': 'file_pattern/selected_chains'}
            )
        
        metric = data.get('metric', 'r2_inner')
        config_data = data.get('config', {})
        groups_data = data.get('groups', [])
        
        # Get service
        service = get_auto_heatmap_service()
        generator = HeatmapGenerator()
        
        # Metric display names for titles
        metric_titles = {
            'expression_sharing': 'Expression',
            'morisita_horn': 'Morisita-Horn',
            'cdr3_sharing': 'uCDR3',
            'r2_inner': 'R^2 Inner',
            'r2_outer': 'R^2 Outer',
            'sorensen': 'Sorensen'
        }
        
        # Prepare response
        response = {
            'success': True,
            'mode': 'chain' if selected_chains else 'traditional',
            'chains': {},  # For chain mode: {chain: {metrics, images}}
            'metrics': {},  # For traditional mode
            'images': {}   # For traditional mode
        }
        
        if selected_chains:
            # 链模式：为每条链单独生成热图
            chain_data = service.load_sample_data_by_chains(samples, selected_chains, field_mapping)
            
            if not chain_data:
                raise ValidationError(
                    message="没有找到有效的链数据",
                    details={'selected_chains': selected_chains}
                )
            
            for chain, sample_data in chain_data.items():
                if len(sample_data) < 2:
                    logger.warning(f"Chain {chain}: insufficient samples, skipping")
                    continue
                
                # Calculate all metrics for this chain
                all_metrics = service.calculate_all_metrics(sample_data)
                
                chain_result = {
                    'metrics': {},
                    'images': {},
                    'sample_count': len(sample_data)
                }
                
                # Generate heatmap for each metric
                for metric_name, matrix in all_metrics.items():
                    # Title format: "Chain - Metric"
                    title = f"{chain} - {metric_titles.get(metric_name, metric_name)}"
                    
                    metric_config = HeatmapConfig(
                        title=title,
                        color_scheme=config_data.get('color_scheme', 'viridis'),
                        annotation=config_data.get('annotation', True),
                        figure_width=config_data.get('figure_width', 10),
                        figure_height=config_data.get('figure_height', 8),
                        dpi=config_data.get('dpi', 150)
                    )
                    
                    heatmap_bytes, metadata = generator.generate_heatmap(
                        matrix,
                        metric_config,
                        metric_name=metric_name
                    )
                    
                    # Build table data for frontend display
                    table_data = {
                        'columns': ['Sample'] + matrix.columns.tolist(),
                        'rows': []
                    }
                    for idx, row_name in enumerate(matrix.index):
                        row = [row_name] + [round(v, 4) if v is not None else None for v in matrix.iloc[idx].tolist()]
                        table_data['rows'].append(row)
                    
                    chain_result['images'][metric_name] = base64.b64encode(heatmap_bytes).decode('utf-8')
                    chain_result['metrics'][metric_name] = {
                        'matrix_data': {
                            'samples': matrix.index.tolist(),
                            'columns': matrix.columns.tolist(),
                            'values': matrix.values.tolist()
                        },
                        'table_data': table_data
                    }
                
                response['chains'][chain] = chain_result
            
            if not response['chains']:
                raise ValidationError(
                    message="所有链的样本数量都不足2个，无法生成热图",
                    details={'selected_chains': selected_chains}
                )
        
        else:
            # 传统模式：按文件模式加载
            sample_data = service.load_sample_data(samples, file_pattern, field_mapping)
            
            if len(sample_data) < 2:
                raise ValidationError(
                    message="至少需要2个有效样本才能生成热图",
                    details={'loaded_samples': len(sample_data)}
                )
            
            # Calculate all 6 similarity metrics
            all_metrics = service.calculate_all_metrics(sample_data)
            
            # Generate individual heatmap for each metric
            for metric_name, matrix in all_metrics.items():
                title = metric_titles.get(metric_name, metric_name)
                
                metric_config = HeatmapConfig(
                    title=title,
                    color_scheme=config_data.get('color_scheme', 'viridis'),
                    annotation=config_data.get('annotation', True),
                    figure_width=config_data.get('figure_width', 10),
                    figure_height=config_data.get('figure_height', 8),
                    dpi=config_data.get('dpi', 150)
                )
                
                heatmap_bytes, metadata = generator.generate_heatmap(
                    matrix,
                    metric_config,
                    metric_name=metric_name
                )
                
                # Build table data for frontend display
                table_data = {
                    'columns': ['Sample'] + matrix.columns.tolist(),
                    'rows': []
                }
                for idx, row_name in enumerate(matrix.index):
                    row = [row_name] + [round(v, 4) if v is not None else None for v in matrix.iloc[idx].tolist()]
                    table_data['rows'].append(row)
                
                response['images'][metric_name] = base64.b64encode(heatmap_bytes).decode('utf-8')
                response['metrics'][metric_name] = {
                    'matrix_data': {
                        'samples': matrix.index.tolist(),
                        'columns': matrix.columns.tolist(),
                        'values': matrix.values.tolist()
                    },
                    'table_data': table_data
                }
        
        # Generate grouped heatmaps if groups are provided (only for traditional mode)
        if groups_data and not selected_chains:
            groups = [
                SampleGroup(
                    name=g.get('name', ''),
                    sample_names=g.get('sample_names', []),
                    color=g.get('color')
                )
                for g in groups_data
                if g.get('sample_names')  # Only include groups with samples
            ]
            
            if groups:
                # Calculate group averages for all metrics
                grouped_metrics = {}
                for metric_name, matrix in all_metrics.items():
                    grouped_matrix = service.calculate_group_averages(matrix, groups)
                    if not grouped_matrix.empty:
                        grouped_metrics[metric_name] = grouped_matrix
                
                if grouped_metrics:
                    response['grouped_metrics'] = {}
                    response['grouped_images'] = {}
                    
                    # Generate individual grouped heatmaps
                    for metric_name, matrix in grouped_metrics.items():
                        grouped_title = f"{metric_titles.get(metric_name, metric_name)} (分组平均)"
                        
                        grouped_config = HeatmapConfig(
                            title=grouped_title,
                            color_scheme=config_data.get('color_scheme', 'viridis'),
                            annotation=True,
                            figure_width=config_data.get('figure_width', 10),
                            figure_height=config_data.get('figure_height', 8),
                            dpi=config_data.get('dpi', 150)
                        )
                        
                        grouped_bytes, _ = generator.generate_heatmap(
                            matrix,
                            grouped_config,
                            metric_name=metric_name
                        )
                        
                        # Build table data for grouped results
                        table_data = {
                            'columns': ['Group'] + matrix.columns.tolist(),
                            'rows': []
                        }
                        for idx, row_name in enumerate(matrix.index):
                            row = [row_name] + [round(v, 4) if v is not None else None for v in matrix.iloc[idx].tolist()]
                            table_data['rows'].append(row)
                        
                        response['grouped_images'][metric_name] = base64.b64encode(grouped_bytes).decode('utf-8')
                        response['grouped_metrics'][metric_name] = {
                            'matrix_data': {
                                'groups': matrix.index.tolist(),
                                'values': matrix.values.tolist()
                            },
                            'table_data': table_data
                        }
        
        return jsonify(response)
    
    except ValidationError as e:
        logger.warning(f"Validation error in generate_heatmap: {e.message}")
        return jsonify({
            'success': False,
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400
    
    except Exception as e:
        logger.error(f"Error generating heatmap: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'HEATMAP_ERROR',
            'message': f"生成热图时发生错误: {str(e)}"
        }), 500


@auto_heatmap_bp.route('/preview-data', methods=['POST'])
def preview_data():
    """
    Preview data from a sample file with field mapping applied.
    POST /api/auto-heatmap/preview-data
    
    Request body:
        {
            "filepath": "...",
            "field_mapping": {
                "cdr3_column": "CDR3(pep)",
                "copy_column": "copy"
            },
            "max_rows": 10
        }
    
    Returns:
        {
            "success": true,
            "preview": [
                {"cdr3": "ASSIGSSYNEQF", "copy": 1},
                ...
            ],
            "total_rows": 46104,
            "unique_cdr3": 44527
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="请求体不能为空",
                details={'field': 'body'}
            )
        
        filepath = data.get('filepath')
        field_mapping_data = data.get('field_mapping', {})
        max_rows = data.get('max_rows', 10)
        
        if not filepath:
            raise ValidationError(
                message="请提供文件路径",
                details={'field': 'filepath'}
            )
        
        if not os.path.exists(filepath):
            raise ValidationError(
                message=f"文件不存在: {filepath}",
                details={'filepath': filepath}
            )
        
        service = get_auto_heatmap_service()
        sep = service._detect_separator(filepath)
        
        df = pd.read_csv(filepath, sep=sep)
        
        cdr3_col = field_mapping_data.get('cdr3_column', '')
        copy_col = field_mapping_data.get('copy_column', '')
        
        if cdr3_col and cdr3_col in df.columns:
            if copy_col and copy_col in df.columns:
                preview_df = df[[cdr3_col, copy_col]].head(max_rows)
                preview_df.columns = ['cdr3', 'copy']
            else:
                preview_df = df[[cdr3_col]].head(max_rows)
                preview_df.columns = ['cdr3']
                preview_df['copy'] = 0
        else:
            preview_df = df.head(max_rows)
        
        return jsonify({
            'success': True,
            'preview': preview_df.to_dict('records'),
            'total_rows': len(df),
            'unique_cdr3': df[cdr3_col].nunique() if cdr3_col and cdr3_col in df.columns else 0
        })
    
    except ValidationError as e:
        logger.warning(f"Validation error in preview_data: {e.message}")
        return jsonify({
            'success': False,
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400
    
    except Exception as e:
        logger.error(f"Error previewing data: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'PREVIEW_ERROR',
            'message': f"预览数据时发生错误: {str(e)}"
        }), 500


@auto_heatmap_bp.route('/export-shared-cdr3', methods=['POST'])
def export_shared_cdr3():
    """
    Export shared CDR3 sequences between sample pairs as Excel file.
    POST /api/auto-heatmap/export-shared-cdr3
    
    Request body:
        {
            "samples": [
                {
                    "original_name": "Sample1",
                    "display_name": "Sample 1",
                    "folder_path": "...",
                    "data_files": [...]
                }
            ],
            "file_pattern": "..._pep.csv",
            "field_mapping": {
                "cdr3_column": "CDR3(pep)",
                "copy_column": "copy"
            }
        }
    
    Returns:
        Excel file download or JSON with base64 encoded data
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="请求体不能为空",
                details={'field': 'body'}
            )
        
        # Parse samples
        samples_data = data.get('samples', [])
        if not samples_data or len(samples_data) < 2:
            raise ValidationError(
                message="请选择至少2个样本",
                details={'field': 'samples'}
            )
        
        samples = []
        for s in samples_data:
            data_files = []
            for df in s.get('data_files', []):
                data_files.append(DataFileInfo(
                    filename=df.get('filename', ''),
                    filepath=df.get('filepath', ''),
                    size=df.get('size', 0),
                    rows=df.get('rows', 0),
                    columns=df.get('columns', [])
                ))
            
            samples.append(SampleFolderInfo(
                original_name=s.get('original_name', ''),
                display_name=s.get('display_name', s.get('original_name', '')),
                folder_path=s.get('folder_path', ''),
                data_files=data_files,
                group_name=s.get('group_name')
            ))
        
        # Parse field mapping
        field_mapping_data = data.get('field_mapping', {})
        field_mapping = FieldMapping(
            cdr3_column=field_mapping_data.get('cdr3_column', ''),
            copy_column=field_mapping_data.get('copy_column', '')
        )
        
        if not field_mapping.cdr3_column or not field_mapping.copy_column:
            raise ValidationError(
                message="请设置CDR3和Copy字段映射",
                details={'field': 'field_mapping'}
            )
        
        file_pattern = data.get('file_pattern')
        selected_chains = data.get('selected_chains')
        
        # 验证：必须提供file_pattern或selected_chains之一
        if not file_pattern and not selected_chains:
            raise ValidationError(
                message="请选择数据文件类型或链类型",
                details={'field': 'file_pattern/selected_chains'}
            )
        
        return_type = data.get('return_type', 'base64')  # 'base64' or 'download'
        
        # Get services
        heatmap_service = get_auto_heatmap_service()
        export_service = get_cdr3_export_service()
        
        # Load sample data based on mode
        if selected_chains:
            # 链模式：加载所有选中链的数据
            sample_data = heatmap_service.load_sample_data_by_chains(samples, selected_chains, field_mapping)
        else:
            # 传统模式：按文件模式加载
            sample_data = heatmap_service.load_sample_data(samples, file_pattern, field_mapping)
        
        if len(sample_data) < 2:
            raise ValidationError(
                message="至少需要2个有效样本才能导出共享CDR3列表",
                details={'loaded_samples': len(sample_data)}
            )
        
        # Generate complete ZIP file (Excel + CSV abundance matrices)
        top_n = data.get('top_n', 100)
        zip_bytes = export_service.generate_complete_export_zip(sample_data, include_summary=True, top_n=top_n)
        
        # Return based on return_type
        if return_type == 'base64':
            # Return as base64 encoded JSON
            import base64
            return jsonify({
                'success': True,
                'data': base64.b64encode(zip_bytes).decode('utf-8'),
                'filename': 'CDR3_Export.zip'
            })
        else:
            # Return as file download
            return send_file(
                io.BytesIO(zip_bytes),
                mimetype='application/zip',
                as_attachment=True,
                download_name='CDR3_Export.zip'
            )
    
    except ValidationError as e:
        logger.warning(f"Validation error in export_shared_cdr3: {e.message}")
        return jsonify({
            'success': False,
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400
    
    except Exception as e:
        logger.error(f"Error exporting shared CDR3: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'EXPORT_ERROR',
            'message': f"导出CDR3共享列表时发生错误: {str(e)}"
        }), 500
