"""
Analysis module registry for managing all available analysis modules.
"""

import logging
from typing import Dict, List, Optional, Type, Tuple
from .base_module import AnalysisModule

logger = logging.getLogger(__name__)


class AnalysisRegistry:
    """分析模块注册中心，管理所有可用的分析模块"""
    
    def __init__(self):
        self._modules: Dict[str, AnalysisModule] = {}
        self._module_classes: Dict[str, Type[AnalysisModule]] = {}
        self._categories: Dict[str, List[str]] = {}
    
    def register(self, module_class: Type[AnalysisModule]):
        """注册分析模块类"""
        try:
            # 创建模块实例获取信息
            module = module_class()
            name = module.get_name()
            category = module.get_category()
            
            # 注册模块类和实例
            self._module_classes[name] = module_class
            self._modules[name] = module
            
            # 更新分类索引
            if category not in self._categories:
                self._categories[category] = []
            if name not in self._categories[category]:
                self._categories[category].append(name)
            
            logger.info(f"Successfully registered analysis module: {name} (category: {category})")
            
        except Exception as e:
            logger.error(f"Failed to register module {module_class}: {e}")
            raise
    
    def get_module(self, name: str, create_new: bool = False) -> Optional[AnalysisModule]:
        """获取指定的分析模块"""
        if create_new and name in self._module_classes:
            try:
                return self._module_classes[name]()
            except Exception as e:
                logger.error(f"Failed to create new instance of module {name}: {e}")
                return None
        return self._modules.get(name)
    
    def get_all_modules(self) -> Dict[str, AnalysisModule]:
        """获取所有已注册的模块"""
        return self._modules.copy()
    
    def get_modules_info(self) -> List[Dict]:
        """获取所有模块的信息"""
        return [module.get_info() for module in self._modules.values()]
    
    def get_modules_by_category(self, category: str) -> List[AnalysisModule]:
        """根据类别获取模块"""
        module_names = self._categories.get(category, [])
        return [self._modules[name] for name in module_names if name in self._modules]
    
    def get_categories(self) -> Dict[str, List[str]]:
        """获取所有分类及其包含的模块"""
        return self._categories.copy()
    
    def unregister(self, name: str) -> bool:
        """注销模块"""
        if name in self._modules:
            module = self._modules[name]
            category = module.get_category()
            
            # 从注册表中移除
            del self._modules[name]
            if name in self._module_classes:
                del self._module_classes[name]
            
            # 从分类中移除
            if category in self._categories and name in self._categories[category]:
                self._categories[category].remove(name)
                if not self._categories[category]:
                    del self._categories[category]
            
            logger.info(f"Successfully unregistered analysis module: {name}")
            return True
        
        return False
    
    def validate_data_for_module(self, module_name: str, data_columns: List[str]) -> Tuple[bool, str]:
        """验证数据是否满足模块要求"""
        module = self.get_module(module_name)
        if not module:
            return False, f"Module {module_name} not found"
        
        required_cols = module.get_required_columns()
        missing_cols = [col for col in required_cols if col not in data_columns]
        
        if missing_cols:
            return False, f"缺少必需的列: {', '.join(missing_cols)}"
        
        return True, "数据验证通过"
    
    def get_available_modules_for_data(self, data_columns: List[str]) -> List[Dict]:
        """根据数据列获取可用的分析模块"""
        available_modules = []
        
        for name, module in self._modules.items():
            required_cols = module.get_required_columns()
            if all(col in data_columns for col in required_cols):
                module_info = module.get_info()
                # 标记可选列是否可用
                optional_available = [col for col in module.get_optional_columns() if col in data_columns]
                module_info['optional_available'] = optional_available
                available_modules.append(module_info)
        
        return available_modules


# 全局注册中心实例
_global_registry: Optional[AnalysisRegistry] = None


def get_registry() -> AnalysisRegistry:
    """获取全局注册中心实例"""
    global _global_registry
    if _global_registry is None:
        _global_registry = AnalysisRegistry()
    return _global_registry


def register_module(module_class: Type[AnalysisModule]):
    """装饰器：自动注册分析模块"""
    registry = get_registry()
    registry.register(module_class)
    return module_class


def init_analysis_registry():
    """初始化分析模块注册中心，导入并注册所有模块"""
    logger.info("Initializing analysis module registry...")
    
    # 导入所有分析模块
    try:
        from .modules.ig_metrics import IGMetricsModule
        from .modules.sequencing_depth import SequencingDepthModule
        from .modules.sequencing_reads import SequencingReadsModule
        from .modules.bcell_isotype import BCellIsotypeModule
        # Temporarily disabled - incomplete implementation
        # from .modules.bcell_isotype_pdf import BCellIsotypePDFModule
        from .modules.shm_analysis import SHMAnalysisModule
        from .modules.chain_analysis import ChainAnalysisModule
        
        logger.info("All analysis modules imported and registered successfully")
        
    except ImportError as e:
        logger.warning(f"Some analysis modules could not be imported: {e}")
    
    except Exception as e:
        logger.error(f"Failed to initialize analysis registry: {e}")
        raise
    
    registry = get_registry()
    logger.info(f"Registry initialized with {len(registry.get_all_modules())} modules")
    
    return registry
