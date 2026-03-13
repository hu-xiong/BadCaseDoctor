"""
通用 Text2SQL 沙箱预览模块

支持 MySQL / Oracle 等方言，通过 SQLite + 方言适配 + 回退机制实现预览：
- 90% 简单 SQL → SQLite 精确预览
- 9% 复杂 SQL → 带警告的预览（可能不准）
- 1% 极端 SQL → 无法预览，提示人工确认

使用方式：
    from agents.tools.sql_preview import preview_select
    result = preview_select(sql, src_dialect="mysql", data_source_config={...})
"""

from .dialect_adapter import SqlDialectAdapter, SUPPORTED_DIALECTS
from .complexity import SqlComplexityAnalyzer, SqlComplexityLevel
from .dml_preview import DmlImpactQuery, parse_single_table_update_or_delete
from .executor import SqlPreviewExecutor
from .sampler import DataSourceSampler
from .preview import preview_select

__all__ = [
    "SqlDialectAdapter",
    "SqlComplexityAnalyzer",
    "SqlComplexityLevel",
    "DmlImpactQuery",
    "parse_single_table_update_or_delete",
    "SqlPreviewExecutor",
    "DataSourceSampler",
    "preview_select",
    "SUPPORTED_DIALECTS",
]
