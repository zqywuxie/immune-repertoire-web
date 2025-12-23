"""
API routes for the modular analysis system and unified analysis.
Provides endpoints for scheme management, analysis execution, and field mapping.

Requirements: 1.3, 3.1, 3.3, 12.1, 12.2
"""

import uuid
import logging
from flask import Blueprint, request, jsonify, current_app
from typing import Dict, Any
from pathlib import Path

from services.analysis.registry import get_registry
from services.analysis.base_module import AnalysisResult
from services.unified_analysis_service import get_unified_analysis_service
from services.scheme_manager import SchemeManager
from services.field_mapping import FieldMappingService
from services.file_parser import FileParserService
from models.database import db, File
from exceptions import (
    ValidationError,
    FileNotFoundError as AppFileNotFoundError,
    StorageError
)

logger = logging.getLogger(__name__)

# Create blueprint
analysis_bp = Blueprint('analysis', __name__, url_prefix='/api/analysis')


@analysis_bp.route('/modules', methods=['GET'])
def get_modules():
    """获取所有可用的分析模块"""
    try:
        registry = get_registry()
        modules_info = registry.get_modules_info()
        
        return jsonify({
            'success': True,
            'modules': modules_info,
            'categories': registry.get_categories()
        })
        
    except Exception as e:
        logger.error(f"Error getting modules: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@analysis_bp.route('/modules/available', methods=['POST'])
def get_available_modules():
    """根据数据列获取可用的分析模块"""
    try:
        data = request.get_json()
        columns = data.get('columns', [])
        
        registry = get_registry()
        available_modules = registry.get_available_modules_for_data(columns)
        
        return jsonify({
            'success': True,
            'modules': available_modules
        })
        
    except Exception as e:
        logger.error(f"Error getting available modules: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@analysis_bp.route('/validate', methods=['POST'])
def validate_data_for_module():
    """验证数据是否满足模块要求"""
    try:
        data = request.get_json()
        module_name = data.get('module_name')
        columns = data.get('columns', [])
        
        if not module_name:
            return jsonify({
                'success': False,
                'error': 'Module name is required'
            }), 400
        
        registry = get_registry()
        is_valid, message = registry.validate_data_for_module(module_name, columns)
        
        return jsonify({
            'success': True,
            'valid': is_valid,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Error validating data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@analysis_bp.route('/execute', methods=['POST'])
def execute_analysis():
    """执行分析"""
    try:
        data = request.get_json()
        
        # 获取必需参数
        module_name = data.get('module_name')
        analysis_data = data.get('data')
        params = data.get('params', {})
        
        if not module_name or not analysis_data:
            return jsonify({
                'success': False,
                'error': 'Module name and data are required'
            }), 400
        
        # 获取分析模块
        registry = get_registry()
        module = registry.get_module(module_name, create_new=True)
        
        if not module:
            return jsonify({
                'success': False,
                'error': f'Module {module_name} not found'
            }), 404
        
        # 创建分析结果对象
        analysis_id = str(uuid.uuid4())
        result = AnalysisResult(module_name, analysis_id)
        
        # 转换数据为DataFrame
        import pandas as pd
        df = pd.DataFrame(analysis_data)
        
        # 验证数据
        is_valid, message = module.validate_data(df)
        if not is_valid:
            result.add_error(message)
            return jsonify({
                'success': False,
                'error': message,
                'analysis_id': analysis_id
            }), 400
        
        # 执行分析
        try:
            analysis_results = module.analyze(df, params)
            result.add_data('analysis', analysis_results)
            
            # 生成可视化
            figures = module.visualize(analysis_results, params)
            for fig_name, fig_data in figures.items():
                result.add_figure(fig_name, fig_data)
            
            # 添加元数据
            result.add_metadata('module_info', module.get_info())
            result.add_metadata('data_shape', df.shape)
            result.add_metadata('columns', df.columns.tolist())
            
        except Exception as e:
            logger.error(f"Error during analysis execution: {e}")
            result.add_error(str(e))
        
        # 返回结果
        return jsonify({
            'success': result.success,
            'analysis_id': analysis_id,
            'results': result.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error executing analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@analysis_bp.route('/module/<module_name>/info', methods=['GET'])
def get_module_info(module_name: str):
    """获取特定模块的详细信息"""
    try:
        registry = get_registry()
        module = registry.get_module(module_name)
        
        if not module:
            return jsonify({
                'success': False,
                'error': f'Module {module_name} not found'
            }), 404
        
        return jsonify({
            'success': True,
            'module': module.get_info()
        })
        
    except Exception as e:
        logger.error(f"Error getting module info: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@analysis_bp.route('/batch', methods=['POST'])
def execute_batch_analysis():
    """执行批量分析"""
    try:
        data = request.get_json()
        
        # 获取参数
        module_names = data.get('modules', [])
        analysis_data = data.get('data')
        params_list = data.get('params_list', [])
        
        if not module_names or not analysis_data:
            return jsonify({
                'success': False,
                'error': 'Modules and data are required'
            }), 400
        
        # 确保参数列表长度匹配模块数量
        if params_list and len(params_list) != len(module_names):
            # 使用默认参数填充
            default_params = {}
            for module_name in module_names:
                registry = get_registry()
                module = registry.get_module(module_name)
                if module:
                    default_params[module_name] = module.get_default_params()
            
            params_list = [default_params.get(name, {}) for name in module_names]
        
        # 转换数据
        import pandas as pd
        df = pd.DataFrame(analysis_data)
        
        # 执行批量分析
        results = {}
        registry = get_registry()
        
        for i, module_name in enumerate(module_names):
            try:
                module = registry.get_module(module_name, create_new=True)
                if not module:
                    results[module_name] = {
                        'success': False,
                        'error': f'Module {module_name} not found'
                    }
                    continue
                
                # 验证数据
                is_valid, message = module.validate_data(df)
                if not is_valid:
                    results[module_name] = {
                        'success': False,
                        'error': message
                    }
                    continue
                
                # 执行分析
                analysis_results = module.analyze(df, params_list[i] if i < len(params_list) else {})
                figures = module.visualize(analysis_results, params_list[i] if i < len(params_list) else {})
                
                results[module_name] = {
                    'success': True,
                    'analysis': analysis_results,
                    'figures': figures
                }
                
            except Exception as e:
                logger.error(f"Error in batch analysis for module {module_name}: {e}")
                results[module_name] = {
                    'success': False,
                    'error': str(e)
                }
        
        return jsonify({
            'success': True,
            'batch_id': str(uuid.uuid4()),
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error in batch analysis: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# Unified Analysis API - Scheme Management
# Requirements: 3.1, 10.4, 10.5, 10.6
# =============================================================================

@analysis_bp.route('/schemes', methods=['GET'])
def get_schemes():
    """
    获取所有可用的分析方案
    GET /api/analysis/schemes
    
    Requirements: 3.1
    
    Returns:
        {
            "schemes": [
                {
                    "id": "bcell_isotype",
                    "name": "B细胞同型分析",
                    "description": "...",
                    "icon": "bi-pie-chart",
                    "category": "immunology",
                    "is_custom": false,
                    "required_fields_count": 3,
                    "optional_fields_count": 1
                },
                ...
            ],
            "total": 5
        }
    """
    try:
        service = get_unified_analysis_service()
        schemes = service.get_available_schemes()
        
        return jsonify({
            'schemes': schemes,
            'total': len(schemes)
        })
    
    except Exception as e:
        logger.error(f"Error getting schemes: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to retrieve schemes',
            'message': str(e)
        }), 500


@analysis_bp.route('/schemes/<scheme_id>', methods=['GET'])
def get_scheme(scheme_id: str):
    """
    获取特定方案的详细信息
    GET /api/analysis/schemes/<scheme_id>
    
    Requirements: 3.1
    
    Returns:
        {
            "id": "bcell_isotype",
            "name": "B细胞同型分析",
            "description": "...",
            "icon": "bi-pie-chart",
            "category": "immunology",
            "required_fields": [...],
            "optional_fields": [...],
            "default_parameters": {...},
            "analyzer_class": "BcellIsotypeAnalyzer",
            "is_custom": false
        }
    """
    try:
        service = get_unified_analysis_service()
        scheme = service.get_scheme_by_id(scheme_id)
        
        if not scheme:
            return jsonify({
                'error': 'Scheme not found',
                'message': f'No scheme found with id: {scheme_id}'
            }), 404
        
        return jsonify(scheme)
    
    except Exception as e:
        logger.error(f"Error getting scheme {scheme_id}: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to retrieve scheme',
            'message': str(e)
        }), 500


@analysis_bp.route('/schemes/custom', methods=['POST'])
def create_custom_scheme():
    """
    创建自定义方案
    POST /api/analysis/schemes/custom
    
    Requirements: 10.4
    
    Request body:
        {
            "name": "我的自定义方案",
            "description": "方案描述",
            "fields": ["field1", "field2", "field3"],
            "parameters": {
                "chart_type": "bar",
                "group_by": "field1"
            },
            "icon": "bi-sliders",
            "category": "custom"
        }
    
    Returns:
        {
            "scheme_id": "custom_abc123",
            "success": true,
            "message": "Custom scheme created successfully"
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="Request body is required",
                details={'field': 'body'}
            )
        
        # 验证必需字段
        name = data.get('name')
        description = data.get('description')
        fields = data.get('fields')
        parameters = data.get('parameters', {})
        
        if not name:
            raise ValidationError(
                message="Scheme name is required",
                details={'field': 'name'}
            )
        
        if not description:
            raise ValidationError(
                message="Scheme description is required",
                details={'field': 'description'}
            )
        
        if not fields or not isinstance(fields, list) or len(fields) == 0:
            raise ValidationError(
                message="At least one field is required",
                details={'field': 'fields'}
            )
        
        # 获取可选参数
        icon = data.get('icon', 'bi-sliders')
        category = data.get('category', 'custom')
        created_by = data.get('created_by')
        
        # 创建自定义方案
        scheme_manager = SchemeManager()
        scheme = scheme_manager.create_custom_scheme(
            name=name,
            description=description,
            fields=fields,
            parameters=parameters,
            icon=icon,
            category=category,
            created_by=created_by
        )
        
        return jsonify({
            'scheme_id': scheme.id,
            'success': True,
            'message': 'Custom scheme created successfully',
            'scheme': scheme.to_dict()
        }), 201
    
    except ValidationError as e:
        return jsonify({
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400
    
    except Exception as e:
        logger.error(f"Error creating custom scheme: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to create custom scheme',
            'message': str(e)
        }), 500


@analysis_bp.route('/schemes/custom/<scheme_id>', methods=['DELETE'])
def delete_custom_scheme(scheme_id: str):
    """
    删除自定义方案
    DELETE /api/analysis/schemes/custom/<scheme_id>
    
    Requirements: 10.6
    
    Returns:
        {
            "success": true,
            "message": "Custom scheme deleted successfully"
        }
    """
    try:
        # 验证是否为自定义方案
        if not scheme_id.startswith('custom_'):
            return jsonify({
                'error': 'Invalid scheme',
                'message': 'Only custom schemes can be deleted'
            }), 400
        
        # 删除方案
        scheme_manager = SchemeManager()
        success = scheme_manager.delete_custom_scheme(scheme_id)
        
        if not success:
            return jsonify({
                'error': 'Scheme not found',
                'message': f'No custom scheme found with id: {scheme_id}'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Custom scheme deleted successfully'
        })
    
    except Exception as e:
        logger.error(f"Error deleting custom scheme {scheme_id}: {e}", exc_info=True)
        return jsonify({
            'error': 'Failed to delete custom scheme',
            'message': str(e)
        }), 500



# =============================================================================
# Unified Analysis API - Analysis Execution
# Requirements: 1.4, 7.5
# =============================================================================

@analysis_bp.route('/execute-unified', methods=['POST'])
def execute_unified_analysis():
    """
    执行统一分析
    POST /api/analysis/execute-unified
    
    Requirements: 1.4, 7.5
    
    Request body:
        {
            "file_id": "uuid",
            "mode": "scheme",  // or "custom"
            "scheme_id": "bcell_isotype",  // required if mode is "scheme"
            "selected_fields": ["field1", "field2"],  // required if mode is "custom"
            "field_mapping": {
                "Sample_Name": "Sample_ID",
                "Isotype": "C_CALL"
            },
            "parameters": {
                "chart_type": "pie"
            }
        }
    
    Returns:
        {
            "analysis_id": "uuid",
            "status": "completed",
            "results": {
                "charts": [...],
                "tables": [...],
                "statistics": {...}
            }
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="Request body is required",
                details={'field': 'body'}
            )
        
        # 获取必需参数
        file_id = data.get('file_id')
        mode = data.get('mode')
        
        if not file_id:
            raise ValidationError(
                message="File ID is required",
                details={'field': 'file_id'}
            )
        
        if not mode:
            raise ValidationError(
                message="Analysis mode is required",
                details={'field': 'mode'}
            )
        
        if mode not in ['scheme', 'custom']:
            raise ValidationError(
                message=f"Invalid analysis mode: {mode}",
                details={'field': 'mode', 'valid_values': ['scheme', 'custom']}
            )
        
        # 获取文件
        file_record = File.query.get(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # 读取文件数据
        storage_path = Path(file_record.storage_path)
        if not storage_path.exists():
            raise StorageError(
                message=f"File not found in storage: {file_id}",
                details={'file_id': file_id, 'path': str(storage_path)}
            )
        
        try:
            with open(storage_path, 'rb') as f:
                file_content = f.read()
            df, _, _ = FileParserService.parse_file(file_content, file_record.original_name)
        except Exception as e:
            raise ValidationError(
                message=f"Failed to parse file: {str(e)}",
                details={'file_id': file_id}
            )
        
        # 获取可选参数
        scheme_id = data.get('scheme_id')
        selected_fields = data.get('selected_fields')
        field_mapping = data.get('field_mapping')
        parameters = data.get('parameters', {})
        
        # 验证模式特定参数
        if mode == 'scheme' and not scheme_id:
            raise ValidationError(
                message="Scheme ID is required for scheme mode",
                details={'field': 'scheme_id'}
            )
        
        if mode == 'custom' and not selected_fields:
            raise ValidationError(
                message="Selected fields are required for custom mode",
                details={'field': 'selected_fields'}
            )
        
        # 验证分析配置
        service = get_unified_analysis_service()
        validation_result = service.validate_analysis_config(
            mode=mode,
            scheme_id=scheme_id,
            selected_fields=selected_fields,
            file_columns=list(df.columns),
            field_mapping=field_mapping
        )
        
        if not validation_result.is_valid:
            return jsonify({
                'error': 'Invalid analysis configuration',
                'validation_errors': validation_result.errors,
                'warnings': validation_result.warnings,
                'missing_fields': validation_result.missing_fields
            }), 400
        
        # 执行分析
        logger.info(f"Executing unified analysis: mode={mode}, file_id={file_id}")
        
        result = service.execute_analysis(
            file_id=file_id,
            data=df,
            mode=mode,
            scheme_id=scheme_id,
            selected_fields=selected_fields,
            field_mapping=field_mapping,
            parameters=parameters
        )
        
        # 检查分析状态
        logger.info(f"Analysis result keys: {result.keys()}")
        logger.info(f"Analysis result: {result}")
        
        if result.get('status') == 'failed':
            return jsonify({
                'error': 'Analysis execution failed',
                'message': result.get('error_message', 'Unknown error'),
                'analysis_id': result.get('analysis_id')
            }), 500
        
        # 从results中提取数据
        results_data = result.get('results', {})
        logger.info(f"Results data keys: {results_data.keys() if isinstance(results_data, dict) else 'not a dict'}")
        
        return jsonify({
            'success': True,
            'analysis_id': result.get('analysis_id'),
            'status': result.get('status'),
            'results': {
                'charts': results_data.get('charts', []),
                'tables': results_data.get('tables', []),
                'statistics': results_data.get('statistics', {})
            },
            'metadata': {
                'mode': results_data.get('mode'),
                'scheme_id': results_data.get('scheme_id'),
                'scheme_name': results_data.get('scheme_name'),
                'selected_fields': results_data.get('selected_fields'),
                'field_mapping': results_data.get('field_mapping')
            }
        })
    
    except ValidationError as e:
        return jsonify({
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400
    
    except AppFileNotFoundError as e:
        return jsonify({
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 404
    
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error executing unified analysis: {e}\n{error_traceback}")
        return jsonify({
            'error': 'Analysis execution failed',
            'message': str(e),
            'traceback': error_traceback
        }), 500



# =============================================================================
# Unified Analysis API - Field Mapping
# Requirements: 12.1, 12.2, 12.3
# =============================================================================

@analysis_bp.route('/auto-map', methods=['POST'])
def auto_map_fields():
    """
    自动字段映射
    POST /api/analysis/auto-map
    
    Requirements: 12.1, 12.2, 12.3
    
    Request body:
        {
            "file_id": "uuid",
            "scheme_id": "bcell_isotype"
        }
    
    Returns:
        {
            "mappings": {
                "Sample_Name": {
                    "source_column": "Sample_ID",
                    "confidence": 0.95
                },
                "Isotype": {
                    "source_column": "C_CALL",
                    "confidence": 0.90
                }
            },
            "missing_fields": [],
            "warnings": []
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="Request body is required",
                details={'field': 'body'}
            )
        
        # 获取必需参数
        file_id = data.get('file_id')
        scheme_id = data.get('scheme_id')
        
        if not file_id:
            raise ValidationError(
                message="File ID is required",
                details={'field': 'file_id'}
            )
        
        if not scheme_id:
            raise ValidationError(
                message="Scheme ID is required",
                details={'field': 'scheme_id'}
            )
        
        # 获取文件
        file_record = File.query.get(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # 获取文件列名
        file_columns = file_record.columns or []
        
        if not file_columns:
            raise ValidationError(
                message="File has no columns",
                details={'file_id': file_id}
            )
        
        # 执行自动映射
        service = get_unified_analysis_service()
        field_mapping, missing_fields, confidence_scores = service.auto_map_fields(
            scheme_id=scheme_id,
            file_columns=file_columns
        )
        
        # 构建响应
        mappings = {}
        for field_name, source_column in field_mapping.items():
            mappings[field_name] = {
                'source_column': source_column,
                'confidence': confidence_scores.get(field_name, 0.0)
            }
        
        # 生成警告
        warnings = []
        if missing_fields:
            warnings.append(f"无法自动映射以下必需字段: {', '.join(missing_fields)}")
        
        # 检查低置信度映射
        low_confidence_fields = [
            field for field, score in confidence_scores.items()
            if score < 0.7 and field in field_mapping
        ]
        if low_confidence_fields:
            warnings.append(
                f"以下字段的映射置信度较低，建议手动确认: {', '.join(low_confidence_fields)}"
            )
        
        return jsonify({
            'mappings': mappings,
            'missing_fields': missing_fields,
            'warnings': warnings,
            'file_columns': file_columns
        })
    
    except ValidationError as e:
        return jsonify({
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400
    
    except AppFileNotFoundError as e:
        return jsonify({
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 404
    
    except Exception as e:
        logger.error(f"Error in auto field mapping: {e}", exc_info=True)
        return jsonify({
            'error': 'Auto mapping failed',
            'message': str(e)
        }), 500


@analysis_bp.route('/suggest-scheme', methods=['POST'])
def suggest_scheme():
    """
    根据文件列名建议合适的分析方案
    POST /api/analysis/suggest-scheme
    
    Request body:
        {
            "file_id": "uuid",
            "min_confidence": 0.5  // optional, default 0.5
        }
    
    Returns:
        {
            "suggestions": [
                {
                    "id": "bcell_isotype",
                    "name": "B细胞同型分析",
                    "description": "...",
                    "confidence": 0.95
                },
                ...
            ]
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="Request body is required",
                details={'field': 'body'}
            )
        
        # 获取必需参数
        file_id = data.get('file_id')
        
        if not file_id:
            raise ValidationError(
                message="File ID is required",
                details={'field': 'file_id'}
            )
        
        # 获取可选参数
        min_confidence = data.get('min_confidence', 0.5)
        
        # 获取文件
        file_record = File.query.get(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # 获取文件列名
        file_columns = file_record.columns or []
        
        if not file_columns:
            raise ValidationError(
                message="File has no columns",
                details={'file_id': file_id}
            )
        
        # 获取方案建议
        service = get_unified_analysis_service()
        suggestions = service.suggest_scheme(
            file_columns=file_columns,
            min_confidence=min_confidence
        )
        
        return jsonify({
            'suggestions': suggestions,
            'file_columns': file_columns
        })
    
    except ValidationError as e:
        return jsonify({
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400
    
    except AppFileNotFoundError as e:
        return jsonify({
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 404
    
    except Exception as e:
        logger.error(f"Error suggesting scheme: {e}", exc_info=True)
        return jsonify({
            'error': 'Scheme suggestion failed',
            'message': str(e)
        }), 500


@analysis_bp.route('/validate-config', methods=['POST'])
def validate_analysis_config():
    """
    验证分析配置
    POST /api/analysis/validate-config
    
    Request body:
        {
            "file_id": "uuid",
            "mode": "scheme",
            "scheme_id": "bcell_isotype",
            "selected_fields": ["field1", "field2"],
            "field_mapping": {...}
        }
    
    Returns:
        {
            "is_valid": true,
            "errors": [],
            "warnings": [],
            "missing_fields": []
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            raise ValidationError(
                message="Request body is required",
                details={'field': 'body'}
            )
        
        # 获取必需参数
        file_id = data.get('file_id')
        mode = data.get('mode')
        
        if not file_id:
            raise ValidationError(
                message="File ID is required",
                details={'field': 'file_id'}
            )
        
        if not mode:
            raise ValidationError(
                message="Analysis mode is required",
                details={'field': 'mode'}
            )
        
        # 获取文件
        file_record = File.query.get(file_id)
        if not file_record:
            raise AppFileNotFoundError(
                message=f"File not found: {file_id}",
                details={'file_id': file_id}
            )
        
        # 获取文件列名
        file_columns = file_record.columns or []
        
        # 获取可选参数
        scheme_id = data.get('scheme_id')
        selected_fields = data.get('selected_fields')
        field_mapping = data.get('field_mapping')
        
        # 验证配置
        service = get_unified_analysis_service()
        validation_result = service.validate_analysis_config(
            mode=mode,
            scheme_id=scheme_id,
            selected_fields=selected_fields,
            file_columns=file_columns,
            field_mapping=field_mapping
        )
        
        return jsonify({
            'is_valid': validation_result.is_valid,
            'errors': validation_result.errors,
            'warnings': validation_result.warnings,
            'missing_fields': validation_result.missing_fields
        })
    
    except ValidationError as e:
        return jsonify({
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 400
    
    except AppFileNotFoundError as e:
        return jsonify({
            'error': e.error_code,
            'message': e.message,
            'details': e.details
        }), 404
    
    except Exception as e:
        logger.error(f"Error validating config: {e}", exc_info=True)
        return jsonify({
            'error': 'Configuration validation failed',
            'message': str(e)
        }), 500
