"""
Analysis module package initialization.
"""

from .base_module import AnalysisModule, AnalysisResult, PlotConfig
from .registry import (
    AnalysisRegistry,
    get_registry,
    register_module,
    init_analysis_registry
)

__all__ = [
    'AnalysisModule',
    'AnalysisResult',
    'PlotConfig',
    'AnalysisRegistry',
    'get_registry',
    'register_module',
    'init_analysis_registry'
]
