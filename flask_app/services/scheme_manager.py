"""
Scheme Manager Service - 分析方案管理服务
管理分析方案的加载、验证和应用

Requirements: 3.1, 3.4, 4.7
"""

import json
import os
import logging
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FieldDefinition:
    """字段定义"""
    field: str
    display_name: str
    type: str
    mapping_hints: List[str] = field(default_factory=list)
    description: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FieldDefinition':
        """从字典创建字段定义"""
        return cls(
            field=data['field'],
            display_name=data['display_name'],
            type=data['type'],
            mapping_hints=data.get('mapping_hints', []),
            description=data.get('description')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class AnalysisScheme:
    """分析方案数据模型"""
    id: str
    name: str
    description: str
    icon: str
    category: str
    required_fields: List[FieldDefinition]
    optional_fields: List[FieldDefinition]
    default_parameters: Dict[str, Any]
    analyzer_class: str
    is_custom: bool = False
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AnalysisScheme':
        """从字典创建分析方案"""
        required_fields = [
            FieldDefinition.from_dict(f) for f in data.get('required_fields', [])
        ]
        optional_fields = [
            FieldDefinition.from_dict(f) for f in data.get('optional_fields', [])
        ]
        
        created_at = None
        if data.get('created_at'):
            if isinstance(data['created_at'], str):
                created_at = datetime.fromisoformat(data['created_at'])
            else:
                created_at = data['created_at']
        
        return cls(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            icon=data['icon'],
            category=data['category'],
            required_fields=required_fields,
            optional_fields=optional_fields,
            default_parameters=data.get('default_parameters', {}),
            analyzer_class=data['analyzer_class'],
            is_custom=data.get('is_custom', False),
            created_by=data.get('created_by'),
            created_at=created_at
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'category': self.category,
            'required_fields': [f.to_dict() for f in self.required_fields],
            'optional_fields': [f.to_dict() for f in self.optional_fields],
            'default_parameters': self.default_parameters,
            'analyzer_class': self.analyzer_class,
            'is_custom': self.is_custom,
            'created_by': self.created_by
        }
        
        if self.created_at:
            result['created_at'] = self.created_at.isoformat()
        
        return result


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class SchemeManager:
    """
    分析方案管理器
    
    功能:
    - 加载预设分析方案
    - 管理自定义分析方案
    - 验证方案配置
    - 应用方案到数据
    
    Requirements: 3.1, 3.4, 4.7
    """
    
    def __init__(
        self,
        config_path: str = None,
        custom_schemes_dir: str = None
    ):
        """
        初始化方案管理器
        
        Args:
            config_path: 预设方案配置文件路径
            custom_schemes_dir: 自定义方案存储目录
        """
        # 设置默认路径
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, 'config', 'analysis_schemes.json')
        
        if custom_schemes_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            custom_schemes_dir = os.path.join(base_dir, 'data', 'custom_schemes')
        
        self.config_path = config_path
        self.custom_schemes_dir = custom_schemes_dir
        
        # 确保自定义方案目录存在
        os.makedirs(self.custom_schemes_dir, exist_ok=True)
        
        # 加载方案
        self.schemes: Dict[str, AnalysisScheme] = {}
        self._load_schemes()
    
    def _load_schemes(self):
        """加载所有方案（预设+自定义）"""
        # 加载预设方案
        self._load_preset_schemes()
        
        # 加载自定义方案
        self._load_custom_schemes()
        
        logger.info(f"Loaded {len(self.schemes)} analysis schemes")
    
    def _load_preset_schemes(self):
        """加载预设方案"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Preset schemes config not found: {self.config_path}")
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            for scheme_data in config.get('schemes', []):
                try:
                    scheme = AnalysisScheme.from_dict(scheme_data)
                    self.schemes[scheme.id] = scheme
                    logger.debug(f"Loaded preset scheme: {scheme.id}")
                except Exception as e:
                    logger.error(f"Error loading preset scheme: {e}")
        
        except Exception as e:
            logger.error(f"Error loading preset schemes: {e}")
    
    def _load_custom_schemes(self):
        """加载自定义方案"""
        try:
            if not os.path.exists(self.custom_schemes_dir):
                return
            
            for filename in os.listdir(self.custom_schemes_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.custom_schemes_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            scheme_data = json.load(f)
                        
                        scheme = AnalysisScheme.from_dict(scheme_data)
                        scheme.is_custom = True
                        self.schemes[scheme.id] = scheme
                        logger.debug(f"Loaded custom scheme: {scheme.id}")
                    except Exception as e:
                        logger.error(f"Error loading custom scheme {filename}: {e}")
        
        except Exception as e:
            logger.error(f"Error loading custom schemes: {e}")
    
    def get_all_schemes(self) -> List[AnalysisScheme]:
        """
        获取所有方案（预设+自定义）
        
        Requirements: 3.1
        
        Returns:
            方案列表
        """
        return list(self.schemes.values())
    
    def get_scheme(self, scheme_id: str) -> Optional[AnalysisScheme]:
        """
        获取指定方案
        
        Requirements: 3.1
        
        Args:
            scheme_id: 方案ID
            
        Returns:
            方案对象，如果不存在则返回None
        """
        return self.schemes.get(scheme_id)
    
    def create_custom_scheme(
        self,
        name: str,
        description: str,
        fields: List[str],
        parameters: Dict[str, Any],
        analyzer_class: str = "CustomFieldAnalyzer",
        icon: str = "bi-sliders",
        category: str = "custom",
        created_by: Optional[str] = None
    ) -> AnalysisScheme:
        """
        创建自定义方案
        
        Requirements: 10.4
        
        Args:
            name: 方案名称
            description: 方案描述
            fields: 字段列表
            parameters: 参数配置
            analyzer_class: 分析器类名
            icon: 图标
            category: 分类
            created_by: 创建者
            
        Returns:
            创建的方案对象
        """
        # 生成唯一ID
        import uuid
        scheme_id = f"custom_{uuid.uuid4().hex[:8]}"
        
        # 创建字段定义
        field_definitions = []
        for field_name in fields:
            field_def = FieldDefinition(
                field=field_name,
                display_name=field_name,
                type="string",
                mapping_hints=[field_name.lower()]
            )
            field_definitions.append(field_def)
        
        # 创建方案
        scheme = AnalysisScheme(
            id=scheme_id,
            name=name,
            description=description,
            icon=icon,
            category=category,
            required_fields=[],
            optional_fields=field_definitions,
            default_parameters=parameters,
            analyzer_class=analyzer_class,
            is_custom=True,
            created_by=created_by,
            created_at=datetime.now()
        )
        
        # 保存到文件
        self._save_custom_scheme(scheme)
        
        # 添加到内存
        self.schemes[scheme_id] = scheme
        
        logger.info(f"Created custom scheme: {scheme_id}")
        return scheme
    
    def _save_custom_scheme(self, scheme: AnalysisScheme):
        """保存自定义方案到文件"""
        filepath = os.path.join(self.custom_schemes_dir, f"{scheme.id}.json")
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(scheme.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved custom scheme to: {filepath}")
        except Exception as e:
            logger.error(f"Error saving custom scheme: {e}")
            raise
    
    def delete_custom_scheme(self, scheme_id: str) -> bool:
        """
        删除自定义方案
        
        Requirements: 10.6
        
        Args:
            scheme_id: 方案ID
            
        Returns:
            是否删除成功
        """
        scheme = self.schemes.get(scheme_id)
        
        if not scheme:
            logger.warning(f"Scheme not found: {scheme_id}")
            return False
        
        if not scheme.is_custom:
            logger.warning(f"Cannot delete preset scheme: {scheme_id}")
            return False
        
        # 删除文件
        filepath = os.path.join(self.custom_schemes_dir, f"{scheme_id}.json")
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            
            # 从内存中移除
            del self.schemes[scheme_id]
            
            logger.info(f"Deleted custom scheme: {scheme_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error deleting custom scheme: {e}")
            return False
    
    def apply_scheme(
        self,
        scheme: AnalysisScheme,
        file_columns: List[str]
    ) -> Tuple[Dict[str, str], List[str]]:
        """
        应用方案，返回字段映射和缺失字段
        
        Requirements: 3.4, 4.7
        
        Args:
            scheme: 分析方案
            file_columns: 文件中的列名列表
            
        Returns:
            Tuple of (field_mapping, missing_fields)
            - field_mapping: {标准字段名: 文件列名}
            - missing_fields: 缺失的必需字段列表
        """
        field_mapping = {}
        missing_fields = []
        
        # 转换文件列名为小写以便匹配
        file_columns_lower = {col.lower(): col for col in file_columns}
        
        # 处理必需字段
        for field_def in scheme.required_fields:
            mapped_col = self._find_matching_column(
                field_def, file_columns_lower
            )
            
            if mapped_col:
                field_mapping[field_def.field] = mapped_col
            else:
                missing_fields.append(field_def.field)
        
        # 处理可选字段
        for field_def in scheme.optional_fields:
            mapped_col = self._find_matching_column(
                field_def, file_columns_lower
            )
            
            if mapped_col:
                field_mapping[field_def.field] = mapped_col
        
        return field_mapping, missing_fields
    
    def _find_matching_column(
        self,
        field_def: FieldDefinition,
        file_columns_lower: Dict[str, str]
    ) -> Optional[str]:
        """
        查找匹配的列名
        
        Args:
            field_def: 字段定义
            file_columns_lower: {小写列名: 原始列名}
            
        Returns:
            匹配的原始列名，如果未找到则返回None
        """
        # 首先尝试精确匹配（忽略大小写）
        field_lower = field_def.field.lower()
        if field_lower in file_columns_lower:
            return file_columns_lower[field_lower]
        
        # 尝试使用映射提示
        for hint in field_def.mapping_hints:
            hint_lower = hint.lower()
            
            # 精确匹配
            if hint_lower in file_columns_lower:
                return file_columns_lower[hint_lower]
            
            # 部分匹配（提示包含在列名中）
            for col_lower, col_original in file_columns_lower.items():
                if hint_lower in col_lower:
                    return col_original
        
        return None
    
    def validate_scheme(self, scheme: AnalysisScheme) -> ValidationResult:
        """
        验证方案配置
        
        Requirements: 4.7
        
        Args:
            scheme: 分析方案
            
        Returns:
            验证结果
        """
        errors = []
        warnings = []
        
        # 验证必需字段
        if not scheme.id:
            errors.append("方案ID不能为空")
        
        if not scheme.name:
            errors.append("方案名称不能为空")
        
        if not scheme.analyzer_class:
            errors.append("分析器类名不能为空")
        
        # 验证字段定义
        if not scheme.required_fields and not scheme.optional_fields:
            warnings.append("方案没有定义任何字段")
        
        # 检查字段名重复
        all_field_names = (
            [f.field for f in scheme.required_fields] +
            [f.field for f in scheme.optional_fields]
        )
        
        if len(all_field_names) != len(set(all_field_names)):
            errors.append("存在重复的字段名")
        
        # 验证字段定义完整性
        for field_def in scheme.required_fields + scheme.optional_fields:
            if not field_def.field:
                errors.append("字段名不能为空")
            if not field_def.display_name:
                warnings.append(f"字段 {field_def.field} 缺少显示名称")
            if not field_def.type:
                warnings.append(f"字段 {field_def.field} 缺少类型定义")
        
        is_valid = len(errors) == 0
        
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings
        )
    
    def suggest_scheme(
        self,
        file_columns: List[str],
        min_confidence: float = 0.5
    ) -> List[Tuple[str, float]]:
        """
        根据文件列名建议合适的分析方案
        
        Args:
            file_columns: 文件中的列名列表
            min_confidence: 最小置信度阈值
            
        Returns:
            [(scheme_id, confidence), ...] 按置信度降序排列
        """
        suggestions = []
        
        for scheme_id, scheme in self.schemes.items():
            confidence = self._calculate_scheme_confidence(scheme, file_columns)
            
            if confidence >= min_confidence:
                suggestions.append((scheme_id, confidence))
        
        # 按置信度降序排序
        suggestions.sort(key=lambda x: x[1], reverse=True)
        
        return suggestions
    
    def _calculate_scheme_confidence(
        self,
        scheme: AnalysisScheme,
        file_columns: List[str]
    ) -> float:
        """
        计算方案与文件的匹配置信度
        
        Args:
            scheme: 分析方案
            file_columns: 文件列名列表
            
        Returns:
            置信度 (0.0 - 1.0)
        """
        if not scheme.required_fields and not scheme.optional_fields:
            return 0.0
        
        file_columns_lower = {col.lower(): col for col in file_columns}
        
        # 计算必需字段匹配率
        required_matched = 0
        for field_def in scheme.required_fields:
            if self._find_matching_column(field_def, file_columns_lower):
                required_matched += 1
        
        # 如果必需字段不全匹配，置信度为0
        if scheme.required_fields and required_matched < len(scheme.required_fields):
            return 0.0
        
        # 计算可选字段匹配率
        optional_matched = 0
        for field_def in scheme.optional_fields:
            if self._find_matching_column(field_def, file_columns_lower):
                optional_matched += 1
        
        # 计算总体置信度
        total_fields = len(scheme.required_fields) + len(scheme.optional_fields)
        total_matched = required_matched + optional_matched
        
        if total_fields == 0:
            return 0.0
        
        confidence = total_matched / total_fields
        
        # 如果所有必需字段都匹配，给予额外加分
        if scheme.required_fields and required_matched == len(scheme.required_fields):
            confidence = min(1.0, confidence + 0.1)
        
        return round(confidence, 2)
    
    def get_scheme_summary(self, scheme_id: str) -> Optional[Dict[str, Any]]:
        """
        获取方案摘要信息
        
        Args:
            scheme_id: 方案ID
            
        Returns:
            方案摘要字典
        """
        scheme = self.get_scheme(scheme_id)
        
        if not scheme:
            return None
        
        return {
            'id': scheme.id,
            'name': scheme.name,
            'description': scheme.description,
            'icon': scheme.icon,
            'category': scheme.category,
            'is_custom': scheme.is_custom,
            'required_fields_count': len(scheme.required_fields),
            'optional_fields_count': len(scheme.optional_fields),
            'analyzer_class': scheme.analyzer_class
        }
