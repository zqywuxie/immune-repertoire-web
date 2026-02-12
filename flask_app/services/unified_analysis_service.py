"""
Unified Analysis Service - 缁熶竴鍒嗘瀽鏈嶅姟
鍗忚皟鎵€鏈夊垎鏋愭祦绋嬶紝鎻愪緵缁熶竴鐨勫垎鏋愭帴鍙?

Requirements: 1.3, 1.4, 7.1, 7.2, 7.3, 11.1, 11.4
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd

from flask_app.services.scheme_manager import SchemeManager, AnalysisScheme, ValidationResult
from flask_app.services.field_mapping import FieldMappingService

logger = logging.getLogger(__name__)


@dataclass
class AnalysisConfig:
    """鍒嗘瀽閰嶇疆"""
    file_id: str
    mode: str  # 'scheme' or 'custom'
    scheme_id: Optional[str] = None
    selected_fields: Optional[List[str]] = None
    field_mapping: Optional[Dict[str, str]] = None
    parameters: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
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
    """鍒嗘瀽缁撴灉鏁版嵁妯″瀷"""
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
        """Convert to dictionary."""
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
    缁熶竴鍒嗘瀽鏈嶅姟
    
    鍔熻兘:
    - 绠＄悊鍒嗘瀽鏂规
    - 鍗忚皟瀛楁鏄犲皠
    - 鎵ц鍒嗘瀽娴佺▼
    - 鐢熸垚鏍囧噯鍖栫粨鏋?
    
    Requirements: 1.3, 1.4, 7.1, 7.2, 7.3, 11.1, 11.4
    """
    
    def __init__(
        self,
        scheme_manager: Optional[SchemeManager] = None,
        field_mapper: Optional[FieldMappingService] = None
    ):
        """
        鍒濆鍖栫粺涓€鍒嗘瀽鏈嶅姟
        
        Args:
            scheme_manager: 鏂规绠＄悊鍣ㄥ疄渚?
            field_mapper: 瀛楁鏄犲皠鏈嶅姟瀹炰緥
        """
        self.scheme_manager = scheme_manager or SchemeManager()
        self.field_mapper = field_mapper or FieldMappingService()
        
        # 寤惰繜鍔犺浇鍒嗘瀽鍣紝閬垮厤寰幆瀵煎叆
        self._analyzers = None
        
        logger.info("Initialized UnifiedAnalysisService")
    
    def _load_analyzers(self) -> Dict[str, Any]:
        """
        寤惰繜鍔犺浇鍒嗘瀽鍣?
        
        Returns:
            鍒嗘瀽鍣ㄧ被瀛楀吀 {analyzer_class_name: analyzer_class}
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
                'BcellIsotypeAnalyzer': BCellIsotypeAnalyzer,  # 鍏煎鏃ч厤缃?
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
        鑾峰彇鎵€鏈夊彲鐢ㄧ殑鍒嗘瀽鏂规
        
        Requirements: 1.3, 3.1
        
        Returns:
            鏂规鍒楄〃锛屾瘡涓柟妗堝寘鍚熀鏈俊鎭?
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
        鏍规嵁ID鑾峰彇鍒嗘瀽鏂规璇︾粏淇℃伅
        
        Requirements: 1.3, 3.1
        
        Args:
            scheme_id: 鏂规ID
            
        Returns:
            鏂规璇︾粏淇℃伅瀛楀吀锛屽鏋滀笉瀛樺湪鍒欒繑鍥濶one
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
        鏍规嵁鏂囦欢鍒楀悕寤鸿鍚堥€傜殑鍒嗘瀽鏂规
        
        Requirements: 1.3
        
        Args:
            file_columns: 鏂囦欢涓殑鍒楀悕鍒楄〃
            min_confidence: 鏈€灏忕疆淇″害闃堝€?
            
        Returns:
            寤鸿鐨勬柟妗堝垪琛紝鎸夌疆淇″害闄嶅簭鎺掑垪
            姣忎釜鏂规鍖呭惈: id, name, confidence
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
        楠岃瘉鍒嗘瀽閰嶇疆鏄惁鏈夋晥
        
        Requirements: 1.3
        
        Args:
            mode: 鍒嗘瀽妯″紡 ('scheme' or 'custom')
            scheme_id: 鏂规ID锛坰cheme妯″紡蹇呴渶锛?
            selected_fields: 閫夋嫨鐨勫瓧娈靛垪琛紙custom妯″紡蹇呴渶锛?
            file_columns: 鏂囦欢涓殑鍒楀悕鍒楄〃
            field_mapping: 瀛楁鏄犲皠锛堝彲閫夛級
            
        Returns:
            ValidationResult瀵硅薄
        """
        errors = []
        warnings = []
        missing_fields = []
        
        # 楠岃瘉妯″紡
        if mode not in ['scheme', 'custom']:
            errors.append(f"鏃犳晥鐨勫垎鏋愭ā寮? {mode}")
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                missing_fields=missing_fields
            )
        
        # 楠岃瘉scheme妯″紡
        if mode == 'scheme':
            if not scheme_id:
                errors.append("scheme妯″紡涓嬪繀椤绘彁渚泂cheme_id")
            else:
                scheme = self.scheme_manager.get_scheme(scheme_id)
                if not scheme:
                    errors.append(f"鏂规涓嶅瓨鍦? {scheme_id}")
                else:
                    # 楠岃瘉鏂规鏈韩
                    scheme_validation = self.scheme_manager.validate_scheme(scheme)
                    if not scheme_validation.is_valid:
                        errors.extend(scheme_validation.errors)
                        warnings.extend(scheme_validation.warnings)
                    
                    # 楠岃瘉瀛楁鏄犲皠
                    if field_mapping:
                        # 妫€鏌ュ繀闇€瀛楁鏄惁閮藉凡鏄犲皠
                        for field_def in scheme.required_fields:
                            if field_def.field not in field_mapping:
                                missing_fields.append(field_def.field)
                            elif field_mapping[field_def.field] not in file_columns:
                                errors.append(
                                    f"鏄犲皠鐨勫垪涓嶅瓨鍦? {field_mapping[field_def.field]}"
                                )
                    else:
                        # 灏濊瘯鑷姩鏄犲皠
                        auto_mapping, auto_missing = self.scheme_manager.apply_scheme(
                            scheme, file_columns
                        )
                        if auto_missing:
                            missing_fields.extend(auto_missing)
                            warnings.append(
                                f"鏃犳硶鑷姩鏄犲皠浠ヤ笅瀛楁: {', '.join(auto_missing)}"
                            )
        
        # 楠岃瘉custom妯″紡
        elif mode == 'custom':
            if not selected_fields or len(selected_fields) == 0:
                errors.append("Custom mode requires selecting at least one field.")
            else:
                # 楠岃瘉閫夋嫨鐨勫瓧娈垫槸鍚﹀瓨鍦ㄤ簬鏂囦欢涓?
                for field in selected_fields:
                    if field not in file_columns:
                        errors.append(f"閫夋嫨鐨勫瓧娈典笉瀛樺湪浜庢枃浠朵腑: {field}")
        
        # 鍙湁errors鎵嶅鑷撮獙璇佸け璐ワ紝missing_fields鍙槸璀﹀憡
        is_valid = len(errors) == 0
        
        # 灏唌issing_fields娣诲姞鍒皐arnings涓?
        if missing_fields:
            warnings.append(f"浠ヤ笅瀛楁鏈槧灏勶紝灏嗗皾璇曡嚜鍔ㄥ鐞? {', '.join(missing_fields)}")
        
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
        鑷姩鏄犲皠瀛楁
        
        Args:
            scheme_id: 鏂规ID
            file_columns: 鏂囦欢鍒楀悕鍒楄〃
            
        Returns:
            Tuple of (field_mapping, missing_fields, confidence_scores)
            - field_mapping: {鏍囧噯瀛楁鍚? 鏂囦欢鍒楀悕}
            - missing_fields: 缂哄け鐨勫繀闇€瀛楁鍒楄〃
            - confidence_scores: {鏍囧噯瀛楁鍚? 缃俊搴
        """
        scheme = self.scheme_manager.get_scheme(scheme_id)
        
        if not scheme:
            logger.warning(f"Scheme not found: {scheme_id}")
            return {}, [], {}
        
        # 搴旂敤鏂规杩涜鑷姩鏄犲皠
        field_mapping, missing_fields = self.scheme_manager.apply_scheme(
            scheme, file_columns
        )
        
        # 璁＄畻缃俊搴︼紙绠€鍖栫増鏈紝鍩轰簬鏄犲皠鎻愮ず鍖归厤锛?
        confidence_scores = {}
        file_columns_lower = {col.lower(): col for col in file_columns}
        
        for field_def in scheme.required_fields + scheme.optional_fields:
            if field_def.field in field_mapping:
                mapped_col = field_mapping[field_def.field]
                mapped_col_lower = mapped_col.lower()
                
                # 绮剧‘鍖归厤
                if field_def.field.lower() == mapped_col_lower:
                    confidence_scores[field_def.field] = 1.0
                # 鎻愮ず绮剧‘鍖归厤
                elif any(hint.lower() == mapped_col_lower for hint in field_def.mapping_hints):
                    confidence_scores[field_def.field] = 0.95
                # 鎻愮ず閮ㄥ垎鍖归厤
                elif any(hint.lower() in mapped_col_lower for hint in field_def.mapping_hints):
                    confidence_scores[field_def.field] = 0.8
                else:
                    confidence_scores[field_def.field] = 0.6
            else:
                confidence_scores[field_def.field] = 0.0
        
        return field_mapping, missing_fields, confidence_scores
    
    def get_analyzer_for_scheme(self, scheme: AnalysisScheme) -> Optional[Any]:
        """
        鑾峰彇鏂规瀵瑰簲鐨勫垎鏋愬櫒瀹炰緥
        
        Args:
            scheme: 鍒嗘瀽鏂规
            
        Returns:
            鍒嗘瀽鍣ㄥ疄渚嬶紝濡傛灉鎵句笉鍒板垯杩斿洖None
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
        parameters: Optional[Dict[str, Any]] = None,
        check_duplicate: bool = True
    ) -> Dict[str, Any]:
        """
        鎵ц鍒嗘瀽
        
        Requirements: 1.4, 7.1, 7.2, 7.3, 7.4
        
        Args:
            file_id: 鏂囦欢ID
            data: 鏁版嵁DataFrame
            mode: 鍒嗘瀽妯″紡 ('scheme' or 'custom')
            scheme_id: 鏂规ID锛坰cheme妯″紡蹇呴渶锛?
            selected_fields: 閫夋嫨鐨勫瓧娈靛垪琛紙custom妯″紡蹇呴渶锛?
            field_mapping: 瀛楁鏄犲皠锛堝彲閫夛紝濡傛灉涓嶆彁渚涘垯鑷姩鏄犲皠锛?
            parameters: 鍒嗘瀽鍙傛暟锛堝彲閫夛級
            check_duplicate: 鏄惁妫€鏌ラ噸澶嶅垎鏋愶紙榛樿锛歍rue锛?
            
        Returns:
            鍒嗘瀽缁撴灉瀛楀吀
        """
        from services.analysis_pipeline import AnalysisPipeline
        
        try:
            logger.info(f"Executing analysis: mode={mode}, file_id={file_id}")
            # History module removed: duplicate check disabled.

            # 澶勭悊鏂规妯″紡鍒嗘瀽
            if mode == 'scheme':
                return self._execute_scheme_analysis(
                    file_id=file_id,
                    data=data,
                    scheme_id=scheme_id,
                    field_mapping=field_mapping,
                    parameters=parameters
                )
            
            # 澶勭悊鑷畾涔夊瓧娈靛垎鏋?
            elif mode == 'custom':
                return self._execute_custom_analysis(
                    file_id=file_id,
                    data=data,
                    selected_fields=selected_fields,
                    field_mapping=field_mapping,
                    parameters=parameters
                )
            
            else:
                error_msg = f"鏃犳晥鐨勫垎鏋愭ā寮? {mode}"
                logger.error(error_msg)
                return {
                    'status': 'failed',
                    'error_message': error_msg
                }
        
        except Exception as e:
            error_msg = f"鎵ц鍒嗘瀽澶辫触: {str(e)}"
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
        鎵ц鏂规妯″紡鍒嗘瀽
        
        Requirements: 7.1, 7.2, 7.3
        
        Args:
            file_id: 鏂囦欢ID
            data: 鏁版嵁DataFrame
            scheme_id: 鏂规ID
            field_mapping: 瀛楁鏄犲皠锛堝彲閫夛級
            parameters: 鍒嗘瀽鍙傛暟锛堝彲閫夛級
            
        Returns:
            鍒嗘瀽缁撴灉瀛楀吀
        """
        from services.analysis_pipeline import AnalysisPipeline
        
        # 鑾峰彇鏂规
        scheme = self.scheme_manager.get_scheme(scheme_id)
        if not scheme:
            return {
                'status': 'failed',
                'error_message': f"鏂规涓嶅瓨鍦? {scheme_id}"
            }
        
        # 濡傛灉娌℃湁鎻愪緵瀛楁鏄犲皠锛屽垯鑷姩鏄犲皠
        if not field_mapping:
            file_columns = list(data.columns)
            field_mapping, missing_fields, _ = self.auto_map_fields(
                scheme_id, file_columns
            )
            
            if missing_fields:
                return {
                    'status': 'failed',
                    'error_message': f"鏃犳硶鏄犲皠蹇呴渶瀛楁: {', '.join(missing_fields)}"
                }
        
        # 鑾峰彇鍒嗘瀽鍣?
        analyzer = self.get_analyzer_for_scheme(scheme)
        if not analyzer:
            return {
                'status': 'failed',
                'error_message': f"鏃犳硶鍔犺浇鍒嗘瀽鍣? {scheme.analyzer_class}"
            }
        
        # 鍚堝苟鍙傛暟
        merged_parameters = {**scheme.default_parameters}
        if parameters:
            merged_parameters.update(parameters)
        
        # 鍒涘缓鍒嗘瀽绠￠亾骞舵墽琛?
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
        鎵ц鑷畾涔夊瓧娈靛垎鏋?
        
        Requirements: 7.4
        
        Args:
            file_id: 鏂囦欢ID
            data: 鏁版嵁DataFrame
            selected_fields: 閫夋嫨鐨勫瓧娈靛垪琛?
            field_mapping: 瀛楁鏄犲皠锛堝彲閫夛級
            parameters: 鍒嗘瀽鍙傛暟锛堝彲閫夛級
            
        Returns:
            鍒嗘瀽缁撴灉瀛楀吀
        """
        from services.analysis_pipeline import AnalysisPipeline
        
        if not selected_fields or len(selected_fields) == 0:
            return {
                'status': 'failed',
                'error_message': "At least one field must be selected."
            }
        
        # 濡傛灉娌℃湁鎻愪緵瀛楁鏄犲皠锛屽垱寤烘亽绛夋槧灏?
        if not field_mapping:
            field_mapping = {field: field for field in selected_fields}
        
        # 鑾峰彇CustomFieldAnalyzer
        analyzers = self._load_analyzers()
        analyzer_class = analyzers.get('CustomFieldAnalyzer')
        
        if not analyzer_class:
            return {
                'status': 'failed',
                'error_message': "鏃犳硶鍔犺浇CustomFieldAnalyzer"
            }
        
        try:
            analyzer = analyzer_class()
        except Exception as e:
            return {
                'status': 'failed',
                'error_message': f"鏃犳硶瀹炰緥鍖朇ustomFieldAnalyzer: {str(e)}"
            }
        
        # 鍑嗗鍙傛暟
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
        
        # 鍒涘缓鍒嗘瀽绠￠亾骞舵墽琛?
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
            scheme_name='Custom Field Analysis',
            selected_fields=selected_fields
        )
        
        return result
    
    def __repr__(self) -> str:
        """String representation."""
        return f"UnifiedAnalysisService(schemes={len(self.scheme_manager.schemes)})"


# Global service instance
_unified_analysis_service: Optional[UnifiedAnalysisService] = None


def init_unified_analysis_service(
    scheme_manager: Optional[SchemeManager] = None,
    field_mapper: Optional[FieldMappingService] = None
) -> UnifiedAnalysisService:
    """鍒濆鍖栧叏灞€缁熶竴鍒嗘瀽鏈嶅姟瀹炰緥"""
    global _unified_analysis_service
    _unified_analysis_service = UnifiedAnalysisService(
        scheme_manager=scheme_manager,
        field_mapper=field_mapper
    )
    return _unified_analysis_service


def get_unified_analysis_service() -> UnifiedAnalysisService:
    """鑾峰彇鍏ㄥ眬缁熶竴鍒嗘瀽鏈嶅姟瀹炰緥"""
    if _unified_analysis_service is None:
        # 鑷姩鍒濆鍖?
        return init_unified_analysis_service()
    return _unified_analysis_service

