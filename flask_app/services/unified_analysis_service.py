"""
Unified Analysis Service - 统一分析服务
协调所有分析流程，提供统一的分析接口

Requirements: 1.3, 1.4, 7.1, 7.2, 7.3, 11.1, 11.4
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd

from services.scheme_manager import SchemeManager, AnalysisScheme, ValidationResult
from services.field_mapping import FieldMappingService

logger = logging.getLogger(__name__)


@dataclass
class AnalysisConfig:
    """分析配置"""
    file_id: str
    mode: str  # 'scheme' or 'custom'
    scheme_id: Optional[str] = None
    selected_fields: Optional[List[str]] = None
    field_mapping: Optional[Dict[str, str]] = None
    parameters: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'file_id': self.file_id,
            'mode': self.mode,
            'scheme_id': self.scheme_id,
            'selected_fields': self.selected_fields,
            'field_mapping': self.field_mapping,
            'parameters': self.parameters
        }


@dataclass
class AnalysisResult:
    """分析结果数据模型"""
    id: str
    file_id: str
    mode: str  # 'scheme' or 'custom'
    scheme_id: Optional[str]
    scheme_name: Optional[str]
    selected_fields: List[str]
    field_mapping: Dict[str, str]
    parameters: Dict[str, Any]
    charts: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    status: str = 'completed'
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'file_id': self.file_id,
            'mode': self.mode,
            'scheme_id': self.scheme_id,
            'scheme_name': self.scheme_name,
            'selected_fields': self.selected_fields,
            'field_mapping': self.field_mapping,
            'parameters': self.parameters,
            'charts': self.charts,
            'tables': self.tables,
            'statistics': self.statistics,
            'status': self.status,
            'error_message': self.error_message
        }


class UnifiedAnalysisService:
    """
    统一分析服务
    
    功能:
    - 管理分析方案
    - 协调字段映射
    - 执行分析流程
    - 生成标准化结果
    
    Requirements: 1.3, 1.4, 7.1, 7.2, 7.3, 11.1, 11.4
    """
    
    def __init__(
        self,
        scheme_manager: Optional[SchemeManager] = None,
        field_mapper: Optional[FieldMappingService] = None
    ):
        """
        初始化统一分析服务
        
        Args:
            scheme_manager: 方案管理器实例
            field_mapper: 字段映射服务实例
        """
        self.scheme_manager = scheme_manager or SchemeManager()
        self.field_mapper = field_mapper or FieldMappingService()
        
        # 延迟加载分析器，避免循环导入
        self._analyzers = None
        
        logger.info("Initialized UnifiedAnalysisService")
    
    def _load_analyzers(self) -> Dict[str, Any]:
        """
        延迟加载分析器
        
        Returns:
            分析器类字典 {analyzer_class_name: analyzer_class}
        """
        if self._analyzers is not None:
            return self._analyzers
        
        try:
            from services.analyzers.bcell_isotype_analyzer import BCellIsotypeAnalyzer
            from services.analyzers.shm_analyzer import SHMAnalyzer
            from services.analyzers.ig_metrics_analyzer import IGMetricsAnalyzer
            from services.analyzers.custom_field_analyzer import CustomFieldAnalyzer
            from services.analyzers.sequencing_reads_analyzer import SequencingReadsChartAnalyzer
            from services.analyzers.bcell_maturation_analyzer import BcellMaturationAnalyzer
            from services.analyzers.ppt_report_analyzer import PPTReportGenerator
            
            self._analyzers = {
                'BCellIsotypeAnalyzer': BCellIsotypeAnalyzer,
                'BcellIsotypeAnalyzer': BCellIsotypeAnalyzer,  # 兼容旧配置
                'SHMAnalyzer': SHMAnalyzer,
                'IGMetricsAnalyzer': IGMetricsAnalyzer,
                'CustomFieldAnalyzer': CustomFieldAnalyzer,
                'SequencingReadsChartAnalyzer': SequencingReadsChartAnalyzer,
                'BcellMaturationAnalyzer': BcellMaturationAnalyzer,
                'PPTReportGenerator': PPTReportGenerator
            }
            
            logger.debug(f"Loaded {len(self._analyzers)} analyzers")
            return self._analyzers
        
        except ImportError as e:
            logger.error(f"Failed to load analyzers: {e}")
            return {}
    
    def get_available_schemes(self) -> List[Dict[str, Any]]:
        """
        获取所有可用的分析方案
        
        Requirements: 1.3, 3.1
        
        Returns:
            方案列表，每个方案包含基本信息
        """
        schemes = self.scheme_manager.get_all_schemes()
        
        return [
            {
                'id': scheme.id,
                'name': scheme.name,
                'description': scheme.description,
                'icon': scheme.icon,
                'category': scheme.category,
                'is_custom': scheme.is_custom,
                'required_fields_count': len(scheme.required_fields),
                'optional_fields_count': len(scheme.optional_fields)
            }
            for scheme in schemes
        ]
    
    def get_scheme_by_id(self, scheme_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取分析方案详细信息
        
        Requirements: 1.3, 3.1
        
        Args:
            scheme_id: 方案ID
            
        Returns:
            方案详细信息字典，如果不存在则返回None
        """
        scheme = self.scheme_manager.get_scheme(scheme_id)
        
        if not scheme:
            return None
        
        return scheme.to_dict()
    
    def suggest_scheme(
        self,
        file_columns: List[str],
        min_confidence: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        根据文件列名建议合适的分析方案
        
        Requirements: 1.3
        
        Args:
            file_columns: 文件中的列名列表
            min_confidence: 最小置信度阈值
            
        Returns:
            建议的方案列表，按置信度降序排列
            每个方案包含: id, name, confidence
        """
        suggestions = self.scheme_manager.suggest_scheme(
            file_columns,
            min_confidence=min_confidence
        )
        
        result = []
        for scheme_id, confidence in suggestions:
            scheme = self.scheme_manager.get_scheme(scheme_id)
            if scheme:
                result.append({
                    'id': scheme.id,
                    'name': scheme.name,
                    'description': scheme.description,
                    'confidence': confidence
                })
        
        return result
    
    def validate_analysis_config(
        self,
        mode: str,
        scheme_id: Optional[str],
        selected_fields: Optional[List[str]],
        file_columns: List[str],
        field_mapping: Optional[Dict[str, str]] = None
    ) -> ValidationResult:
        """
        验证分析配置是否有效
        
        Requirements: 1.3
        
        Args:
            mode: 分析模式 ('scheme' or 'custom')
            scheme_id: 方案ID（scheme模式必需）
            selected_fields: 选择的字段列表（custom模式必需）
            file_columns: 文件中的列名列表
            field_mapping: 字段映射（可选）
            
        Returns:
            ValidationResult对象
        """
        errors = []
        warnings = []
        missing_fields = []
        
        # 验证模式
        if mode not in ['scheme', 'custom']:
            errors.append(f"无效的分析模式: {mode}")
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                missing_fields=missing_fields
            )
        
        # 验证scheme模式
        if mode == 'scheme':
            if not scheme_id:
                errors.append("scheme模式下必须提供scheme_id")
            else:
                scheme = self.scheme_manager.get_scheme(scheme_id)
                if not scheme:
                    errors.append(f"方案不存在: {scheme_id}")
                else:
                    # 验证方案本身
                    scheme_validation = self.scheme_manager.validate_scheme(scheme)
                    if not scheme_validation.is_valid:
                        errors.extend(scheme_validation.errors)
                        warnings.extend(scheme_validation.warnings)
                    
                    # 验证字段映射
                    if field_mapping:
                        # 检查必需字段是否都已映射
                        for field_def in scheme.required_fields:
                            if field_def.field not in field_mapping:
                                missing_fields.append(field_def.field)
                            elif field_mapping[field_def.field] not in file_columns:
                                errors.append(
                                    f"映射的列不存在: {field_mapping[field_def.field]}"
                                )
                    else:
                        # 尝试自动映射
                        auto_mapping, auto_missing = self.scheme_manager.apply_scheme(
                            scheme, file_columns
                        )
                        if auto_missing:
                            missing_fields.extend(auto_missing)
                            warnings.append(
                                f"无法自动映射以下字段: {', '.join(auto_missing)}"
                            )
        
        # 验证custom模式
        elif mode == 'custom':
            if not selected_fields or len(selected_fields) == 0:
                errors.append("custom模式下必须选择至少一个字段")
            else:
                # 验证选择的字段是否存在于文件中
                for field in selected_fields:
                    if field not in file_columns:
                        errors.append(f"选择的字段不存在于文件中: {field}")
        
        # 只有errors才导致验证失败，missing_fields只是警告
        is_valid = len(errors) == 0
        
        # 将missing_fields添加到warnings中
        if missing_fields:
            warnings.append(f"以下字段未映射，将尝试自动处理: {', '.join(missing_fields)}")
        
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            missing_fields=missing_fields
        )
    
    def auto_map_fields(
        self,
        scheme_id: str,
        file_columns: List[str]
    ) -> Tuple[Dict[str, str], List[str], Dict[str, float]]:
        """
        自动映射字段
        
        Args:
            scheme_id: 方案ID
            file_columns: 文件列名列表
            
        Returns:
            Tuple of (field_mapping, missing_fields, confidence_scores)
            - field_mapping: {标准字段名: 文件列名}
            - missing_fields: 缺失的必需字段列表
            - confidence_scores: {标准字段名: 置信度}
        """
        scheme = self.scheme_manager.get_scheme(scheme_id)
        
        if not scheme:
            logger.warning(f"Scheme not found: {scheme_id}")
            return {}, [], {}
        
        # 应用方案进行自动映射
        field_mapping, missing_fields = self.scheme_manager.apply_scheme(
            scheme, file_columns
        )
        
        # 计算置信度（简化版本，基于映射提示匹配）
        confidence_scores = {}
        file_columns_lower = {col.lower(): col for col in file_columns}
        
        for field_def in scheme.required_fields + scheme.optional_fields:
            if field_def.field in field_mapping:
                mapped_col = field_mapping[field_def.field]
                mapped_col_lower = mapped_col.lower()
                
                # 精确匹配
                if field_def.field.lower() == mapped_col_lower:
                    confidence_scores[field_def.field] = 1.0
                # 提示精确匹配
                elif any(hint.lower() == mapped_col_lower for hint in field_def.mapping_hints):
                    confidence_scores[field_def.field] = 0.95
                # 提示部分匹配
                elif any(hint.lower() in mapped_col_lower for hint in field_def.mapping_hints):
                    confidence_scores[field_def.field] = 0.8
                else:
                    confidence_scores[field_def.field] = 0.6
            else:
                confidence_scores[field_def.field] = 0.0
        
        return field_mapping, missing_fields, confidence_scores
    
    def get_analyzer_for_scheme(self, scheme: AnalysisScheme) -> Optional[Any]:
        """
        获取方案对应的分析器实例
        
        Args:
            scheme: 分析方案
            
        Returns:
            分析器实例，如果找不到则返回None
        """
        analyzers = self._load_analyzers()
        
        analyzer_class = analyzers.get(scheme.analyzer_class)
        if not analyzer_class:
            logger.error(f"Analyzer class not found: {scheme.analyzer_class}")
            return None
        
        try:
            analyzer = analyzer_class()
            return analyzer
        except Exception as e:
            logger.error(f"Failed to instantiate analyzer {scheme.analyzer_class}: {e}")
            return None
    
    def execute_analysis(
        self,
        file_id: str,
        data: pd.DataFrame,
        mode: str,
        scheme_id: Optional[str] = None,
        selected_fields: Optional[List[str]] = None,
        field_mapping: Optional[Dict[str, str]] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行分析
        
        Requirements: 1.4, 7.1, 7.2, 7.3, 7.4
        
        Args:
            file_id: 文件ID
            data: 数据DataFrame
            mode: 分析模式 ('scheme' or 'custom')
            scheme_id: 方案ID（scheme模式必需）
            selected_fields: 选择的字段列表（custom模式必需）
            field_mapping: 字段映射（可选，如果不提供则自动映射）
            parameters: 分析参数（可选）
            
        Returns:
            分析结果字典
        """
        from services.analysis_pipeline import AnalysisPipeline
        
        try:
            logger.info(f"Executing analysis: mode={mode}, file_id={file_id}")
            
            # 处理方案模式分析
            if mode == 'scheme':
                return self._execute_scheme_analysis(
                    file_id=file_id,
                    data=data,
                    scheme_id=scheme_id,
                    field_mapping=field_mapping,
                    parameters=parameters
                )
            
            # 处理自定义字段分析
            elif mode == 'custom':
                return self._execute_custom_analysis(
                    file_id=file_id,
                    data=data,
                    selected_fields=selected_fields,
                    field_mapping=field_mapping,
                    parameters=parameters
                )
            
            else:
                error_msg = f"无效的分析模式: {mode}"
                logger.error(error_msg)
                return {
                    'status': 'failed',
                    'error_message': error_msg
                }
        
        except Exception as e:
            error_msg = f"执行分析失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'status': 'failed',
                'error_message': error_msg
            }
    
    def _execute_scheme_analysis(
        self,
        file_id: str,
        data: pd.DataFrame,
        scheme_id: str,
        field_mapping: Optional[Dict[str, str]],
        parameters: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        执行方案模式分析
        
        Requirements: 7.1, 7.2, 7.3
        
        Args:
            file_id: 文件ID
            data: 数据DataFrame
            scheme_id: 方案ID
            field_mapping: 字段映射（可选）
            parameters: 分析参数（可选）
            
        Returns:
            分析结果字典
        """
        from services.analysis_pipeline import AnalysisPipeline
        
        # 获取方案
        scheme = self.scheme_manager.get_scheme(scheme_id)
        if not scheme:
            return {
                'status': 'failed',
                'error_message': f"方案不存在: {scheme_id}"
            }
        
        # 如果没有提供字段映射，则自动映射
        if not field_mapping:
            file_columns = list(data.columns)
            field_mapping, missing_fields, _ = self.auto_map_fields(
                scheme_id, file_columns
            )
            
            if missing_fields:
                return {
                    'status': 'failed',
                    'error_message': f"无法映射必需字段: {', '.join(missing_fields)}"
                }
        
        # 获取分析器
        analyzer = self.get_analyzer_for_scheme(scheme)
        if not analyzer:
            return {
                'status': 'failed',
                'error_message': f"无法加载分析器: {scheme.analyzer_class}"
            }
        
        # 合并参数
        merged_parameters = {**scheme.default_parameters}
        if parameters:
            merged_parameters.update(parameters)
        
        # 创建分析管道并执行
        pipeline = AnalysisPipeline(save_history=True)
        
        result = pipeline.execute(
            analyzer=analyzer,
            data=data,
            field_mapping=field_mapping,
            parameters=merged_parameters,
            file_id=file_id,
            analysis_type=scheme_id,
            mode='scheme',
            scheme_id=scheme_id,
            scheme_name=scheme.name,
            selected_fields=None
        )
        
        return result
    
    def _execute_custom_analysis(
        self,
        file_id: str,
        data: pd.DataFrame,
        selected_fields: List[str],
        field_mapping: Optional[Dict[str, str]],
        parameters: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        执行自定义字段分析
        
        Requirements: 7.4
        
        Args:
            file_id: 文件ID
            data: 数据DataFrame
            selected_fields: 选择的字段列表
            field_mapping: 字段映射（可选）
            parameters: 分析参数（可选）
            
        Returns:
            分析结果字典
        """
        from services.analysis_pipeline import AnalysisPipeline
        
        if not selected_fields or len(selected_fields) == 0:
            return {
                'status': 'failed',
                'error_message': "必须选择至少一个字段"
            }
        
        # 如果没有提供字段映射，创建恒等映射
        if not field_mapping:
            field_mapping = {field: field for field in selected_fields}
        
        # 获取CustomFieldAnalyzer
        analyzers = self._load_analyzers()
        analyzer_class = analyzers.get('CustomFieldAnalyzer')
        
        if not analyzer_class:
            return {
                'status': 'failed',
                'error_message': "无法加载CustomFieldAnalyzer"
            }
        
        try:
            analyzer = analyzer_class()
        except Exception as e:
            return {
                'status': 'failed',
                'error_message': f"无法实例化CustomFieldAnalyzer: {str(e)}"
            }
        
        # 准备参数
        merged_parameters = {
            'selected_fields': selected_fields,
            'chart_config': {
                'title': '',
                'figsize': [12, 8],
                'dpi': 300,
                'font_size': 12
            }
        }
        
        if parameters:
            merged_parameters.update(parameters)
        
        # 创建分析管道并执行
        pipeline = AnalysisPipeline(save_history=True)
        
        result = pipeline.execute(
            analyzer=analyzer,
            data=data,
            field_mapping=field_mapping,
            parameters=merged_parameters,
            file_id=file_id,
            analysis_type='custom_field_analysis',
            mode='custom',
            scheme_id=None,
            scheme_name='自定义字段分析',
            selected_fields=selected_fields
        )
        
        return result
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"UnifiedAnalysisService(schemes={len(self.scheme_manager.schemes)})"


# Global service instance
_unified_analysis_service: Optional[UnifiedAnalysisService] = None


def init_unified_analysis_service(
    scheme_manager: Optional[SchemeManager] = None,
    field_mapper: Optional[FieldMappingService] = None
) -> UnifiedAnalysisService:
    """初始化全局统一分析服务实例"""
    global _unified_analysis_service
    _unified_analysis_service = UnifiedAnalysisService(
        scheme_manager=scheme_manager,
        field_mapper=field_mapper
    )
    return _unified_analysis_service


def get_unified_analysis_service() -> UnifiedAnalysisService:
    """获取全局统一分析服务实例"""
    if _unified_analysis_service is None:
        # 自动初始化
        return init_unified_analysis_service()
    return _unified_analysis_service
