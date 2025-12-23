"""
Analysis Pipeline - 分析管道
统一的分析执行管道，处理数据预处理、分析执行和结果生成

Requirements: 7.6, 11.4
"""

import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
import pandas as pd

from services.analyzers.base_analyzer import BaseAnalyzer
from models.database import db, Analysis, AnalysisResult as DBAnalysisResult

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    """
    分析管道
    
    功能:
    - 数据预处理（字段映射、清洗）
    - 执行分析
    - 生成标准化结果
    - 保存历史记录
    
    Requirements: 7.6, 11.4
    """
    
    def __init__(self, save_history: bool = True):
        """
        初始化分析管道
        
        Args:
            save_history: 是否保存分析历史
        """
        self.save_history = save_history
        logger.info("Initialized AnalysisPipeline")
    
    def execute(
        self,
        analyzer: BaseAnalyzer,
        data: pd.DataFrame,
        field_mapping: Dict[str, str],
        parameters: Dict[str, Any],
        file_id: str,
        analysis_type: str,
        mode: str = 'scheme',
        scheme_id: Optional[str] = None,
        scheme_name: Optional[str] = None,
        selected_fields: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        执行分析管道
        
        Requirements: 7.6, 11.4
        
        Args:
            analyzer: 分析器实例
            data: 原始DataFrame
            field_mapping: 字段映射 {标准字段名: 实际列名}
            parameters: 分析参数
            file_id: 文件ID
            analysis_type: 分析类型
            mode: 分析模式 ('scheme' or 'custom')
            scheme_id: 方案ID（可选）
            scheme_name: 方案名称（可选）
            selected_fields: 选择的字段列表（可选）
            
        Returns:
            分析结果字典，包含:
            - analysis_id: 分析ID
            - status: 状态
            - results: 分析结果数据
            - error_message: 错误消息（如果失败）
        """
        analysis_id = str(uuid.uuid4())
        
        try:
            logger.info(f"Starting analysis pipeline: {analysis_id}")
            logger.debug(f"Analyzer: {analyzer.__class__.__name__}")
            logger.debug(f"Field mapping: {field_mapping}")
            logger.debug(f"Parameters: {parameters}")
            
            # 1. 数据预处理
            logger.info("Step 1: Preprocessing data")
            # IG分析方案需要原始列名，跳过重命名
            skip_rename = scheme_id in ['ig_metrics', 'ig_diversity_metrics'] if scheme_id else False
            processed_data = self._preprocess_data(data, field_mapping, skip_rename=skip_rename)
            
            # 验证数据
            validation_result = analyzer.validate_data(processed_data)
            if not validation_result.is_valid:
                error_msg = f"数据验证失败: {', '.join(validation_result.errors)}"
                logger.error(error_msg)
                
                if self.save_history:
                    self._save_failed_analysis(
                        analysis_id=analysis_id,
                        file_id=file_id,
                        analysis_type=analysis_type,
                        mode=mode,
                        scheme_id=scheme_id,
                        scheme_name=scheme_name,
                        selected_fields=selected_fields,
                        field_mapping=field_mapping,
                        parameters=parameters,
                        error_message=error_msg
                    )
                
                return {
                    'analysis_id': analysis_id,
                    'status': 'failed',
                    'error_message': error_msg
                }
            
            # 2. 执行分析
            logger.info("Step 2: Executing analysis")
            analysis_output = analyzer.analyze(processed_data, parameters)
            logger.info(f"Analysis output keys: {analysis_output.keys() if analysis_output else 'None'}")
            
            # 3. 生成结果
            logger.info("Step 3: Generating results")
            result = self._generate_result(
                analysis_id=analysis_id,
                analysis_output=analysis_output,
                parameters=parameters,
                file_id=file_id,
                analysis_type=analysis_type,
                mode=mode,
                scheme_id=scheme_id,
                scheme_name=scheme_name,
                selected_fields=selected_fields,
                field_mapping=field_mapping
            )
            
            # 4. 保存历史
            if self.save_history:
                logger.info("Step 4: Saving to history")
                self._save_to_history(result)
            
            logger.info(f"Analysis pipeline completed successfully: {analysis_id}")
            
            return {
                'analysis_id': analysis_id,
                'status': 'completed',
                'results': result
            }
        
        except Exception as e:
            error_msg = f"分析执行失败: {str(e)}"
            logger.error(f"Analysis pipeline failed: {e}", exc_info=True)
            
            if self.save_history:
                self._save_failed_analysis(
                    analysis_id=analysis_id,
                    file_id=file_id,
                    analysis_type=analysis_type,
                    mode=mode,
                    scheme_id=scheme_id,
                    scheme_name=scheme_name,
                    selected_fields=selected_fields,
                    field_mapping=field_mapping,
                    parameters=parameters,
                    error_message=error_msg
                )
            
            return {
                'analysis_id': analysis_id,
                'status': 'failed',
                'error_message': error_msg
            }
    
    def _preprocess_data(
        self,
        data: pd.DataFrame,
        field_mapping: Dict[str, str],
        skip_rename: bool = False
    ) -> pd.DataFrame:
        """
        数据预处理：重命名列、过滤、清洗
        
        Args:
            data: 原始DataFrame
            field_mapping: 字段映射 {标准字段名: 实际列名}
            skip_rename: 是否跳过列名重命名（用于IG分析等需要原始列名的场景）
            
        Returns:
            处理后的DataFrame
        """
        # 如果字段映射为空或只有少量映射，或者跳过重命名，保留所有列
        if not field_mapping or len(field_mapping) < 2 or skip_rename:
            processed_data = data.copy()
        else:
            # 创建反向映射用于重命名
            rename_mapping = {v: k for k, v in field_mapping.items() if v and v in data.columns}
            
            if rename_mapping:
                # 重命名列
                processed_data = data.rename(columns=rename_mapping)
            else:
                # 没有有效映射，保留原始数据
                processed_data = data.copy()
        
        # 基本清洗：删除全为空的行
        processed_data = processed_data.dropna(how='all')
        
        logger.debug(f"Preprocessed data shape: {processed_data.shape}")
        logger.debug(f"Preprocessed columns: {list(processed_data.columns)}")
        
        return processed_data
    
    def _generate_result(
        self,
        analysis_id: str,
        analysis_output: Dict[str, Any],
        parameters: Dict[str, Any],
        file_id: str,
        analysis_type: str,
        mode: str,
        scheme_id: Optional[str],
        scheme_name: Optional[str],
        selected_fields: Optional[list],
        field_mapping: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        生成标准化的分析结果
        
        Args:
            analysis_id: 分析ID
            analysis_output: 分析器输出
            parameters: 分析参数
            file_id: 文件ID
            analysis_type: 分析类型
            mode: 分析模式
            scheme_id: 方案ID
            scheme_name: 方案名称
            selected_fields: 选择的字段
            field_mapping: 字段映射
            
        Returns:
            标准化的结果字典
        """
        result = {
            'id': analysis_id,
            'file_id': file_id,
            'analysis_type': analysis_type,
            'mode': mode,
            'scheme_id': scheme_id,
            'scheme_name': scheme_name,
            'selected_fields': selected_fields or [],
            'field_mapping': field_mapping,
            'parameters': parameters,
            'status': 'completed',
            'created_at': datetime.now().isoformat(),
            'completed_at': datetime.now().isoformat()
        }
        
        # 提取分析输出中的各个部分
        result['samples'] = analysis_output.get('samples', [])
        result['data'] = analysis_output.get('data', {})
        result['statistics'] = analysis_output.get('statistics', {})
        result['charts'] = analysis_output.get('charts', [])
        
        # 处理表格数据 - 支持多种格式
        tables = analysis_output.get('tables', [])
        if not tables:
            # 根据分析类型选择表格格式
            # IG指标分析使用长格式，其他分析使用宽格式
            if scheme_id == 'ig_metrics':
                table_data = analysis_output.get('long_format_table') or analysis_output.get('table_data')
            else:
                table_data = analysis_output.get('table_data') or analysis_output.get('long_format_table')
            if table_data:
                # 如果是{headers, rows}格式，转换为数组格式
                if isinstance(table_data, dict) and 'headers' in table_data and 'rows' in table_data:
                    headers = table_data['headers']
                    rows = table_data['rows']
                    logger.warning(f"[DEBUG] Converting table: {len(headers)} headers, {len(rows)} rows")
                    # 转换为字典数组格式
                    data_array = []
                    for row in rows:
                        row_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
                        data_array.append(row_dict)
                    # 包含headers顺序信息，让前端按正确顺序显示列
                    tables = [{'title': '分析结果', 'data': data_array, 'headers': headers}]
                elif isinstance(table_data, list):
                    tables = [{'title': '分析结果', 'data': table_data}]
                else:
                    tables = [{'title': '分析结果', 'data': table_data}]
        result['tables'] = tables
        
        return result
    
    def _save_to_history(self, result: Dict[str, Any]):
        """
        保存分析结果到历史记录
        
        Requirements: 7.6, 10.1
        
        Args:
            result: 分析结果字典
        """
        try:
            # 创建Analysis记录
            analysis = Analysis(
                id=result['id'],
                file_id=result['file_id'],
                type=result['analysis_type'],
                status='completed',
                field_mapping=result.get('field_mapping', {}),
                parameters={
                    **result.get('parameters', {})
                },
                chart_config=result.get('parameters', {}).get('chart_config', {}),
                # New fields for unified analysis - Requirements: 7.6, 10.1
                mode=result.get('mode'),
                scheme_id=result.get('scheme_id'),
                scheme_name=result.get('scheme_name'),
                selected_fields=result.get('selected_fields', []),
                created_at=datetime.now(),
                completed_at=datetime.now()
            )
            
            db.session.add(analysis)
            db.session.commit()
            
            logger.info(f"Saved analysis to history: {result['id']}")
        
        except Exception as e:
            logger.error(f"Failed to save analysis to history: {e}", exc_info=True)
            db.session.rollback()
            # 不抛出异常，因为分析已经成功完成
    
    def _save_failed_analysis(
        self,
        analysis_id: str,
        file_id: str,
        analysis_type: str,
        mode: str,
        scheme_id: Optional[str],
        scheme_name: Optional[str],
        selected_fields: Optional[list],
        field_mapping: Dict[str, str],
        parameters: Dict[str, Any],
        error_message: str
    ):
        """
        保存失败的分析记录
        
        Requirements: 7.6, 10.1
        
        Args:
            analysis_id: 分析ID
            file_id: 文件ID
            analysis_type: 分析类型
            mode: 分析模式
            scheme_id: 方案ID
            scheme_name: 方案名称
            selected_fields: 选择的字段
            field_mapping: 字段映射
            parameters: 分析参数
            error_message: 错误消息
        """
        try:
            analysis = Analysis(
                id=analysis_id,
                file_id=file_id,
                type=analysis_type,
                status='failed',
                field_mapping=field_mapping,
                parameters=parameters,
                chart_config=parameters.get('chart_config', {}),
                # New fields for unified analysis - Requirements: 7.6, 10.1
                mode=mode,
                scheme_id=scheme_id,
                scheme_name=scheme_name,
                selected_fields=selected_fields or [],
                error_message=error_message,
                created_at=datetime.now()
            )
            
            db.session.add(analysis)
            db.session.commit()
            
            logger.info(f"Saved failed analysis to history: {analysis_id}")
        
        except Exception as e:
            logger.error(f"Failed to save failed analysis to history: {e}", exc_info=True)
            db.session.rollback()
    
    def validate_before_execution(
        self,
        analyzer: BaseAnalyzer,
        data: pd.DataFrame,
        field_mapping: Dict[str, str]
    ) -> tuple[bool, Optional[str]]:
        """
        在执行前验证数据和配置
        
        Args:
            analyzer: 分析器实例
            data: 数据DataFrame
            field_mapping: 字段映射
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # 预处理数据
            processed_data = self._preprocess_data(data, field_mapping)
            
            # 验证数据
            validation_result = analyzer.validate_data(processed_data)
            
            if not validation_result.is_valid:
                error_msg = f"数据验证失败: {', '.join(validation_result.errors)}"
                return False, error_msg
            
            return True, None
        
        except Exception as e:
            return False, f"验证过程出错: {str(e)}"
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"AnalysisPipeline(save_history={self.save_history})"
