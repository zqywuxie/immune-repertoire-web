"""
Base classes for the modular analysis system.
Provides the foundation for all analysis modules.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional, List
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
import logging

logger = logging.getLogger(__name__)


class PlotConfig:
    """绘图配置工具类，统一管理中文字体和样式设置"""
    
    @staticmethod
    def setup_chinese_font():
        """设置中文字体支持"""
        try:
            import matplotlib as mpl
            # 尝试多种中文字体
            chinese_fonts = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
            for font in chinese_fonts:
                try:
                    mpl.rcParams["font.sans-serif"] = [font] + mpl.rcParams["font.sans-serif"]
                    break
                except:
                    continue
            mpl.rcParams["axes.unicode_minus"] = False
            mpl.rcParams["font.family"] = "sans-serif"
        except Exception as e:
            logger.warning(f"Failed to setup Chinese font: {e}")
    
    @staticmethod
    def get_style_config():
        """获取统一的绘图样式配置"""
        return {
            'figure.figsize': (12, 8),
            'font.size': 12,
            'axes.titlesize': 14,
            'axes.labelsize': 12,
            'xtick.labelsize': 10,
            'ytick.labelsize': 10,
            'legend.fontsize': 11,
            'figure.dpi': 100,
            'savefig.dpi': 300,
            'savefig.bbox': 'tight',
            'axes.grid': True,
            'grid.alpha': 0.3
        }
    
    @staticmethod
    def apply_style():
        """应用统一的绘图样式"""
        config = PlotConfig.get_style_config()
        import matplotlib as mpl
        for key, value in config.items():
            mpl.rcParams[key] = value


class AnalysisModule(ABC):
    """分析模块基类，所有分析模块必须继承此类"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.plot_config = PlotConfig()
        # 初始化时设置中文字体
        PlotConfig.setup_chinese_font()
        PlotConfig.apply_style()
    
    @abstractmethod
    def get_name(self) -> str:
        """返回模块名称"""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """返回模块描述"""
        pass
    
    @abstractmethod
    def get_category(self) -> str:
        """返回模块类别"""
        pass
    
    @abstractmethod
    def get_required_columns(self) -> List[str]:
        """返回分析所需的数据列"""
        pass
    
    @abstractmethod
    def get_optional_columns(self) -> List[str]:
        """返回可选的数据列"""
        pass
    
    def get_default_params(self) -> Dict[str, Any]:
        """返回默认参数"""
        return {}
    
    def validate_data(self, data: pd.DataFrame) -> Tuple[bool, str]:
        """验证输入数据是否符合要求"""
        required_cols = self.get_required_columns()
        missing_cols = [col for col in required_cols if col not in data.columns]
        
        if missing_cols:
            return False, f"缺少必需的列: {', '.join(missing_cols)}"
        
        if data.empty:
            return False, "数据为空"
        
        return True, "数据验证通过"
    
    @abstractmethod
    def analyze(self, data: pd.DataFrame, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行分析，返回分析结果"""
        pass
    
    @abstractmethod
    def visualize(self, results: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
        """生成可视化图表，返回图表的base64编码字典"""
        pass
    
    def _figure_to_base64(self, fig: plt.Figure, format: str = 'png', dpi: int = 300) -> str:
        """将matplotlib图表转换为base64字符串"""
        try:
            buffer = io.BytesIO()
            fig.savefig(buffer, format=format, dpi=dpi, bbox_inches='tight')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            buffer.close()
            plt.close(fig)
            return image_base64
        except Exception as e:
            logger.error(f"Error converting figure to base64: {e}")
            plt.close(fig)
            return ""
    
    def get_info(self) -> Dict[str, Any]:
        """获取模块信息"""
        return {
            'name': self.get_name(),
            'description': self.get_description(),
            'category': self.get_category(),
            'required_columns': self.get_required_columns(),
            'optional_columns': self.get_optional_columns(),
            'default_params': self.get_default_params()
        }


class AnalysisResult:
    """分析结果封装类"""
    
    def __init__(self, module_name: str, analysis_id: str):
        self.module_name = module_name
        self.analysis_id = analysis_id
        self.data = {}
        self.figures = {}
        self.metadata = {}
        self.errors = []
    
    def add_data(self, key: str, value: Any):
        """添加数据结果"""
        self.data[key] = value
    
    def add_figure(self, key: str, figure_base64: str, title: str = None):
        """添加图表结果"""
        self.figures[key] = {
            'image': figure_base64,
            'title': title or key
        }
    
    def add_metadata(self, key: str, value: Any):
        """添加元数据"""
        self.metadata[key] = value
    
    def add_error(self, error: str):
        """添加错误信息"""
        self.errors.append(error)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'module_name': self.module_name,
            'analysis_id': self.analysis_id,
            'data': self.data,
            'figures': self.figures,
            'metadata': self.metadata,
            'errors': self.errors,
            'success': len(self.errors) == 0
        }
