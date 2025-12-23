"""
Base Analyzer - 分析器基类
所有分析器必须继承此类并实现抽象方法

Requirements: 11.1, 11.5
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import pandas as pd
import logging

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """数据验证结果"""
    is_valid: bool
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class BaseAnalyzer(ABC):
    """
    分析器基类
    
    所有分析器必须继承此类并实现以下抽象方法:
    - analyze(): 执行分析逻辑
    - get_required_fields(): 返回必需字段列表
    - get_default_parameters(): 返回默认参数
    
    可选实现:
    - validate_data(): 验证数据是否满足分析要求（已提供默认实现）
    
    Requirements: 11.1, 11.5
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化分析器
        
        Args:
            config: 分析器配置字典
        """
        self.config = config or {}
        logger.info(f"Initialized {self.__class__.__name__}")
    
    @abstractmethod
    def analyze(self, data: pd.DataFrame, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行分析
        
        Args:
            data: 输入的DataFrame，列名已经过字段映射处理
            parameters: 分析参数字典
            
        Returns:
            分析结果字典，包含:
            - samples: 样本列表
            - data: 分析数据
            - statistics: 统计信息
            - charts: 图表数据（可选）
            - tables: 表格数据（可选）
            
        Raises:
            ValueError: 当数据或参数无效时
            RuntimeError: 当分析执行失败时
        """
        pass
    
    @abstractmethod
    def get_required_fields(self) -> List[str]:
        """
        获取必需字段列表
        
        Returns:
            必需字段名称列表
            
        Note:
            这些字段名是标准化的字段名，会在分析前通过字段映射转换
        """
        pass
    
    @abstractmethod
    def get_default_parameters(self) -> Dict[str, Any]:
        """
        获取默认参数
        
        Returns:
            默认参数字典
            
        Note:
            返回的参数会与用户提供的参数合并，用户参数优先
        """
        pass
    
    def validate_data(self, data: pd.DataFrame) -> ValidationResult:
        """
        验证数据是否满足分析要求
        
        默认实现检查:
        1. 数据不为空
        2. 包含所有必需字段
        
        子类可以重写此方法以添加更多验证逻辑
        
        Args:
            data: 输入的DataFrame
            
        Returns:
            ValidationResult对象，包含验证结果和错误/警告信息
            
        Requirements: 11.5
        """
        errors = []
        warnings = []
        
        # 检查数据是否为空
        if data.empty:
            errors.append("数据为空")
            return ValidationResult(is_valid=False, errors=errors, warnings=warnings)
        
        # 检查必需字段
        required_fields = self.get_required_fields()
        missing_fields = [f for f in required_fields if f not in data.columns]
        
        if missing_fields:
            errors.append(f"缺少必需字段: {', '.join(missing_fields)}")
        
        # 检查数据行数
        if len(data) < 1:
            errors.append("数据行数不足")
        
        # 检查是否有重复的列名
        if len(data.columns) != len(set(data.columns)):
            warnings.append("数据包含重复的列名")
        
        is_valid = len(errors) == 0
        
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings
        )
    
    def get_optional_fields(self) -> List[str]:
        """
        获取可选字段列表
        
        Returns:
            可选字段名称列表
            
        Note:
            默认返回空列表，子类可以重写此方法
        """
        return []
    
    def get_analyzer_info(self) -> Dict[str, Any]:
        """
        获取分析器信息
        
        Returns:
            包含分析器名称、必需字段、可选字段、默认参数的字典
        """
        return {
            "name": self.__class__.__name__,
            "required_fields": self.get_required_fields(),
            "optional_fields": self.get_optional_fields(),
            "default_parameters": self.get_default_parameters()
        }
    
    def preprocess_data(
        self,
        data: pd.DataFrame,
        field_mapping: Dict[str, str]
    ) -> pd.DataFrame:
        """
        数据预处理：应用字段映射
        
        Args:
            data: 原始DataFrame
            field_mapping: 字段映射字典 {标准字段名: 实际列名}
            
        Returns:
            重命名后的DataFrame
            
        Note:
            这个方法通常由分析管道调用，分析器的analyze方法接收的是已经处理过的数据
        """
        # 创建反向映射
        rename_mapping = {v: k for k, v in field_mapping.items() if v in data.columns}
        
        # 重命名列
        processed_data = data.rename(columns=rename_mapping)
        
        logger.debug(f"Applied field mapping: {rename_mapping}")
        
        return processed_data
    
    def merge_parameters(
        self,
        user_parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        合并用户参数和默认参数
        
        Args:
            user_parameters: 用户提供的参数
            
        Returns:
            合并后的参数字典（用户参数优先）
        """
        default_params = self.get_default_parameters()
        merged_params = {**default_params, **user_parameters}
        
        logger.debug(f"Merged parameters: {merged_params}")
        
        return merged_params
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"{self.__class__.__name__}(config={self.config})"
