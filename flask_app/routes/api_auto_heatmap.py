"""
API routes for automatic heatmap analysis with folder-based sample detection.
Provides endpoints for scanning folders, detecting files, field mapping,
sample renaming/grouping, heatmap generation, and CDR3 shared list export.
"""

import os
import io
import base64
import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional, Any
from flask import Blueprint, request, jsonify, send_file, current_app, url_for

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
from flask_app.services.path_config import RESULTS_DIR
from flask_app.services.pipeline_comparison_integration_service import get_pipeline_comparison_service
from flask_app.services.similarity_heatmap_report_service import get_similarity_heatmap_report_service
from flask_app.exceptions import ValidationError
from flask_app.services.path_access_service import PathAccessService

try:
    from flask_app.services.cdr3_export_service import get_cdr3_export_service
except ModuleNotFoundError:
    def get_cdr3_export_service():
        raise RuntimeError("CDR3 export service is not available in this build.")

logger = logging.getLogger(__name__)

# Create blueprint
auto_heatmap_bp = Blueprint('auto_heatmap', __name__, url_prefix='/api/auto-heatmap')


def _as_bool(value: Any, default: bool = False) -> bool:
    """Normalize JSON bool-like values."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    return bool(value)


def _json_safe(value: Any) -> Any:
    """Convert numpy/NaN/Inf payloads into strict JSON-safe values."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        float_value = float(value)
        if math.isnan(float_value) or math.isinf(float_value):
            return None
        return float_value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    return value


def _parse_auto_heatmap_samples(samples_data: Any) -> List[SampleFolderInfo]:
    """Build SampleFolderInfo objects from request payload."""
    if not isinstance(samples_data, list) or len(samples_data) < 2:
        raise ValidationError(
            message="Please select at least 2 samples",
            details={'field': 'samples'}
        )

    samples: List[SampleFolderInfo] = []
    for sample_item in samples_data:
        data_files = []
        for data_file in sample_item.get('data_files', []):
            data_files.append(DataFileInfo(
                filename=data_file.get('filename', ''),
                filepath=data_file.get('filepath', ''),
                size=data_file.get('size', 0),
                rows=data_file.get('rows', 0),
                columns=data_file.get('columns', [])
            ))

        samples.append(SampleFolderInfo(
            original_name=sample_item.get('original_name', ''),
            display_name=sample_item.get('display_name', sample_item.get('original_name', '')),
            folder_path=sample_item.get('folder_path', ''),
            data_files=data_files,
            group_name=sample_item.get('group_name')
        ))

    return samples


def _parse_auto_heatmap_field_mapping(field_mapping_data: Any) -> FieldMapping:
    """Build field mapping object from request payload."""
    if not isinstance(field_mapping_data, dict):
        field_mapping_data = {}

    field_mapping = FieldMapping(
        cdr3_column=field_mapping_data.get('cdr3_column', ''),
        copy_column=field_mapping_data.get('copy_column', '')
    )

    if not field_mapping.cdr3_column or not field_mapping.copy_column:
        raise ValidationError(
            message="请设置CDR3和Copy字段映射",
            details={'field': 'field_mapping'}
        )

    return field_mapping


def _load_cdr3_export_sample_data(payload: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
    """Load CDR3 export sample data for direct download or report bundling."""
    samples = _parse_auto_heatmap_samples(payload.get('samples', []))
    field_mapping = _parse_auto_heatmap_field_mapping(payload.get('field_mapping', {}))

    file_pattern = payload.get('file_pattern')
    selected_chains = payload.get('selected_chains')
    if not file_pattern and not selected_chains:
        raise ValidationError(
            message="请选择数据文件类型或链类型",
            details={'field': 'file_pattern/selected_chains'}
        )

    heatmap_service = get_auto_heatmap_service()
    if selected_chains:
        sample_data = heatmap_service.load_sample_data_by_chains(samples, selected_chains, field_mapping)
    else:
        sample_data = heatmap_service.load_sample_data(samples, file_pattern, field_mapping)

    if any(isinstance(value, dict) for value in sample_data.values()):
        has_valid_chain = any(
            isinstance(chain_samples, dict) and len(chain_samples) >= 2
            for chain_samples in sample_data.values()
        )
        if not has_valid_chain:
            raise ValidationError(
                message="至少需要1条链包含2个有效样本才能导出共享CDR3列表",
                details={'loaded_chains': len(sample_data)}
            )
    elif len(sample_data) < 2:
        raise ValidationError(
            message="至少需要2个有效样本才能导出共享CDR3列表",
            details={'loaded_samples': len(sample_data)}
        )

    top_n = int(payload.get('top_n', 100) or 100)
    return sample_data, top_n


def _write_heatmap_report_metadata(metadata_path: Path, metadata: Dict[str, Any]) -> None:
    """Persist updated similarity heatmap metadata."""
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, 'w', encoding='utf-8') as file_obj:
        json.dump(metadata, file_obj, ensure_ascii=False, indent=2)


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
                message="Request body cannot be empty",
                details={'field': 'body'}
            )
        
        base_path = data.get('base_path')
        
        if not base_path:
            raise ValidationError(
                message="请输入分析文件夹路径",
                details={'field': 'base_path'}
            )
        
        # Quick test without service first
        base_path = str(PathAccessService.validate_read_path(base_path))
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
        
        return jsonify(_json_safe(response))
    
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


@auto_heatmap_bp.route('/scan-pipeline-root', methods=['POST'])
def scan_pipeline_root():
    """
    Scan pipeline-comparison root folder and detect pipeline subfolders + pep files.
    POST /api/auto-heatmap/scan-pipeline-root

    Request body:
        {
            "base_path": "E:\\...\\260125"
        }
    """
    try:
        data = request.get_json() or {}
        base_path = str(data.get('base_path', '')).strip()
        if not base_path:
            raise ValidationError(
                message="base_path is required",
                details={'field': 'base_path'}
            )

        base_path = str(PathAccessService.validate_read_path(base_path))
        results_root = PathAccessService.results_root_for_user(current_app.config.get('RESULTS_FOLDER', str(RESULTS_DIR)))
        service = get_pipeline_comparison_service(results_root=results_root)
        scan_result = service.scan_pipeline_root(base_path=base_path)

        return jsonify({
            'success': True,
            **scan_result
        })

    except ValidationError as e:
        logger.warning(f"Validation error in scan_pipeline_root: {e.message}")
        return jsonify({
            'success': False,
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400

    except Exception as e:
        logger.error(f"Error scanning pipeline root: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'PIPELINE_ROOT_SCAN_ERROR',
            'message': f"Error scanning pipeline root: {str(e)}"
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
                message="Request body cannot be empty",
                details={'field': 'body'}
            )
        
        filepath = data.get('filepath')
        
        if not filepath:
            raise ValidationError(
                message="Please provide filepath",
                details={'field': 'filepath'}
            )
        
        service = get_auto_heatmap_service()
        filepath = str(PathAccessService.validate_read_path(filepath))
        result = service.get_file_columns(filepath)
        
        return jsonify(_json_safe({
            'success': True,
            **result
        }))
    
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
                "plot_type": "heatmap",
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
                message="Request body cannot be empty",
                details={'field': 'body'}
            )
        
        # Parse samples
        samples_data = data.get('samples', [])
        if not samples_data:
            raise ValidationError(
                message="Please select at least one sample",
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
        
        # 必须提供 file_pattern 或 selected_chains 二选一
        if not file_pattern and not selected_chains:
            raise ValidationError(
                message="请选择数据文件类型或链类型",
                details={'field': 'file_pattern/selected_chains'}
            )
        
        metric = data.get('metric', 'r2_inner')
        config_data = data.get('config', {})
        groups_data = data.get('groups', [])
        plot_type = (config_data.get('plot_type') or 'heatmap').lower()

        if plot_type not in HeatmapGenerator.get_available_plot_types():
            raise ValidationError(
                message="不支持的图表类型",
                details={
                    'field': 'config.plot_type',
                    'supported_values': HeatmapGenerator.get_available_plot_types()
                }
            )
        
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
            'plot_type': plot_type,
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
                        plot_type=plot_type,
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
                    message="At least 2 valid samples are required to generate heatmap",
                    details={'loaded_samples': len(sample_data)}
                )
            
            # Calculate all 6 similarity metrics
            all_metrics = service.calculate_all_metrics(sample_data)
            
            # Generate individual heatmap for each metric
            for metric_name, matrix in all_metrics.items():
                title = metric_titles.get(metric_name, metric_name)
                
                metric_config = HeatmapConfig(
                    title=title,
                    plot_type=plot_type,
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
                            plot_type=plot_type,
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
        
        return jsonify(_json_safe(response))
    
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
                message="Request body cannot be empty",
                details={'field': 'body'}
            )
        
        filepath = data.get('filepath')
        field_mapping_data = data.get('field_mapping', {})
        max_rows = data.get('max_rows', 10)
        
        if not filepath:
            raise ValidationError(
                message="Please provide filepath",
                details={'field': 'filepath'}
            )
        
        filepath = str(PathAccessService.validate_read_path(filepath))
        
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
        
        return jsonify(_json_safe({
            'success': True,
            'preview': preview_df.to_dict('records'),
            'total_rows': len(df),
            'unique_cdr3': df[cdr3_col].nunique() if cdr3_col and cdr3_col in df.columns else 0
        }))
    
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
                message="Request body cannot be empty",
                details={'field': 'body'}
            )
        
        return_type = data.get('return_type', 'base64')  # 'base64' or 'download'
        
        export_service = get_cdr3_export_service()
        sample_data, top_n = _load_cdr3_export_sample_data(data)
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


@auto_heatmap_bp.route('/generate-pipeline-report', methods=['POST'])
def generate_pipeline_report():
    """
    Generate integrated pipeline-comparison outputs and HTML report.
    POST /api/auto-heatmap/generate-pipeline-report

    Request body (minimum):
        {
            "base_path": "E:\\...\\260125"
        }

    Optional fields:
        - pipelines: ["YXJ", "DW", "YPL"] or "YXJ,DW,YPL"
        - pipeline_configs: custom pipeline config object/list
        - samples: ["DBY", "GRD", ...]
        - selected_chains / chains: ["IGH", "IGK", ...]
        - output_name: "custom_job_name"
        - enable_heatmap: true/false
        - enable_venn: true/false
        - enable_html_report: true/false
        - include_cdr3_analysis: true/false
        - embed_images: true/false
    """
    try:
        data = request.get_json() or {}
        base_path = str(data.get('base_path', '')).strip()
        if not base_path:
            raise ValidationError(
                message="base_path is required",
                details={'field': 'base_path'}
            )

        base_path = str(PathAccessService.validate_read_path(base_path))
        pipelines = data.get('pipelines')
        if isinstance(pipelines, str):
            pipelines = [item.strip() for item in pipelines.split(',') if item.strip()]

        selected_chains = data.get('selected_chains')
        if selected_chains is None:
            selected_chains = data.get('chains')

        results_root = PathAccessService.results_root_for_user(current_app.config.get('RESULTS_FOLDER', str(RESULTS_DIR)))
        service = get_pipeline_comparison_service(results_root=results_root)

        run_result = service.generate_pipeline_comparison(
            base_path=base_path,
            pipelines=pipelines,
            pipeline_configs=data.get('pipeline_configs'),
            samples=data.get('samples'),
            chains=selected_chains,
            output_name=data.get('output_name'),
            enable_heatmap=_as_bool(data.get('enable_heatmap'), True),
            enable_venn=_as_bool(data.get('enable_venn'), True),
            enable_html_report=_as_bool(data.get('enable_html_report'), True),
            include_cdr3_analysis=_as_bool(data.get('include_cdr3_analysis'), False),
            embed_images=_as_bool(data.get('embed_images'), False),
        )

        report_url = None
        if run_result.report_path is not None:
            report_url = url_for(
                'auto_heatmap.get_pipeline_comparison_result_file',
                job_id=run_result.job_id,
                relative_path='pipeline_comparison_report.html'
            )

        metadata_url = url_for(
            'auto_heatmap.get_pipeline_comparison_result_file',
            job_id=run_result.job_id,
            relative_path='metadata.json'
        )

        return jsonify({
            'success': True,
            'job_id': run_result.job_id,
            'output_base': str(run_result.output_base),
            'report_path': str(run_result.report_path) if run_result.report_path else None,
            'report_url': report_url,
            'metadata_url': metadata_url,
            'metadata': run_result.metadata
        })

    except ValidationError as e:
        logger.warning(f"Validation error in generate_pipeline_report: {e.message}")
        return jsonify({
            'success': False,
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400

    except Exception as e:
        logger.error(f"Error generating pipeline report: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'PIPELINE_REPORT_ERROR',
            'message': f"Error generating pipeline comparison report: {str(e)}"
        }), 500


@auto_heatmap_bp.route('/generate-heatmap-report', methods=['POST'])
def generate_heatmap_report():
    """
    Generate a web report directly from the current similarity heatmap result payload.
    POST /api/auto-heatmap/generate-heatmap-report

    Request body (minimum):
        {
            "heatmap_result": {...}
        }

    Optional fields:
        - output_name: "custom_report_name"
        - embed_images: true/false
        - report_context: object
    """
    try:
        data = request.get_json() or {}
        heatmap_result = data.get('heatmap_result')
        if not isinstance(heatmap_result, dict):
            raise ValidationError(
                message="heatmap_result is required",
                details={'field': 'heatmap_result'}
            )

        report_context = data.get('report_context')
        if not isinstance(report_context, dict):
            report_context = {}
        cdr3_export_request = data.get('cdr3_export_request')
        create_archive = _as_bool(data.get('create_archive'), False)

        results_root = PathAccessService.results_root_for_user(current_app.config.get('RESULTS_FOLDER', str(RESULTS_DIR)))
        service = get_similarity_heatmap_report_service(results_root=results_root)

        run_result = service.generate_report(
            heatmap_result=heatmap_result,
            output_name=data.get('output_name'),
            embed_images=_as_bool(data.get('embed_images'), False),
            context=report_context,
        )

        if isinstance(cdr3_export_request, dict):
            export_service = get_cdr3_export_service()
            sample_data, top_n = _load_cdr3_export_sample_data(cdr3_export_request)
            cdr3_output_dir = run_result.output_base / 'CDR3_Shared_List'
            export_service.write_complete_export_directory(
                output_dir=cdr3_output_dir,
                sample_data=sample_data,
                include_summary=True,
                top_n=top_n,
            )
            run_result.metadata['cdr3_shared_list_path'] = str(cdr3_output_dir.relative_to(run_result.output_base))

        archive_url = None
        archive_path = None
        if create_archive:
            archive_name = 'shared_analysis.zip'
            created_archive = service.create_archive(run_result.job_id, archive_name=archive_name)
            archive_path = str(created_archive)
            archive_relative_path = created_archive.relative_to(run_result.output_base).as_posix()
            run_result.metadata['archive_path'] = archive_relative_path
            archive_url = url_for(
                'auto_heatmap.get_similarity_heatmap_report_result_file',
                job_id=run_result.job_id,
                relative_path=archive_relative_path
            )

        _write_heatmap_report_metadata(run_result.metadata_path, run_result.metadata)

        report_url = url_for(
            'auto_heatmap.get_similarity_heatmap_report_result_file',
            job_id=run_result.job_id,
            relative_path='similarity_heatmap_report.html'
        )
        metadata_url = url_for(
            'auto_heatmap.get_similarity_heatmap_report_result_file',
            job_id=run_result.job_id,
            relative_path='metadata.json'
        )

        return jsonify({
            'success': True,
            'job_id': run_result.job_id,
            'output_base': str(run_result.output_base),
            'report_path': str(run_result.report_path),
            'report_url': report_url,
            'metadata_url': metadata_url,
            'archive_path': archive_path,
            'archive_url': archive_url,
            'metadata': run_result.metadata
        })

    except ValidationError as e:
        logger.warning(f"Validation error in generate_heatmap_report: {e.message}")
        return jsonify({
            'success': False,
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400

    except Exception as e:
        logger.error(f"Error generating heatmap report: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'HEATMAP_REPORT_ERROR',
            'message': f"Error generating heatmap web report: {str(e)}"
        }), 500


@auto_heatmap_bp.route('/pipeline-comparison/results/<job_id>/<path:relative_path>', methods=['GET'])
def get_pipeline_comparison_result_file(job_id: str, relative_path: str):
    """
    Serve generated pipeline-comparison report assets.
    GET /api/auto-heatmap/pipeline-comparison/results/<job_id>/<path:relative_path>
    """
    try:
        results_root = PathAccessService.results_root_for_user(current_app.config.get('RESULTS_FOLDER', str(RESULTS_DIR)))
        service = get_pipeline_comparison_service(results_root=results_root)
        target_file = service.resolve_result_file(job_id, relative_path)
        return send_file(target_file)

    except ValidationError as e:
        logger.warning(f"Validation error in get_pipeline_comparison_result_file: {e.message}")
        return jsonify({
            'success': False,
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400

    except FileNotFoundError:
        return jsonify({
            'success': False,
            'error': 'NOT_FOUND',
            'message': 'Report file not found'
        }), 404

    except Exception as e:
        logger.error(f"Error serving pipeline comparison result file: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'FILE_SERVE_ERROR',
            'message': f"Error reading report file: {str(e)}"
        }), 500


@auto_heatmap_bp.route('/similarity-report/results/<job_id>/<path:relative_path>', methods=['GET'])
def get_similarity_heatmap_report_result_file(job_id: str, relative_path: str):
    """
    Serve generated similarity heatmap report assets.
    GET /api/auto-heatmap/similarity-report/results/<job_id>/<path:relative_path>
    """
    try:
        results_root = PathAccessService.results_root_for_user(current_app.config.get('RESULTS_FOLDER', str(RESULTS_DIR)))
        service = get_similarity_heatmap_report_service(results_root=results_root)
        target_file = service.resolve_result_file(job_id, relative_path)
        return send_file(target_file)

    except ValidationError as e:
        logger.warning(f"Validation error in get_similarity_heatmap_report_result_file: {e.message}")
        return jsonify({
            'success': False,
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400

    except FileNotFoundError:
        return jsonify({
            'success': False,
            'error': 'NOT_FOUND',
            'message': 'Report file not found'
        }), 404

    except Exception as e:
        logger.error(f"Error serving similarity heatmap report file: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'FILE_SERVE_ERROR',
            'message': f"Error reading report file: {str(e)}"
        }), 500

