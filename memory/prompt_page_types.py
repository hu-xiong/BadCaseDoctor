# -*- coding: utf-8 -*-
"""提示词页类型、压缩上限与标志位（见 docs/需求文档_页表KV_Cache与提示词压缩.md）。"""
from __future__ import annotations

from typing import Dict, FrozenSet, Set

# PTE flags
PAGE_FLAG_PIN = 1 << 0
PAGE_FLAG_RO = 1 << 1
PAGE_FLAG_COMPRESSED = 1 << 2
PAGE_FLAG_CRITICAL = 1 << 3

# 压缩级别：RAW=-1 表示禁止任何压缩
COMPRESSION_RAW = -1
COMPRESSION_L0 = 0
COMPRESSION_L1 = 1
COMPRESSION_L2 = 2
COMPRESSION_L3 = 3

# page_type -> 最高压缩级别（§4.2）
CRITICAL_PAGE_COMPRESSION_MAX: Dict[str, int] = {
    "system_core": COMPRESSION_L0,
    "tools_schema": COMPRESSION_L0,
    "workflow_rules": COMPRESSION_L0,
    "project_ctx": COMPRESSION_L0,
    "tool_param": COMPRESSION_L0,
    "ui_context_core": COMPRESSION_RAW,
    "tool_fact_modify": COMPRESSION_L0,
    "tool_fact_grep": COMPRESSION_L1,
    "tool_fact_create": COMPRESSION_L1,
    "tool_fact_delete": COMPRESSION_L1,
    "tool_fact": COMPRESSION_L1,
    "session_prefix": COMPRESSION_L3,
    "observe_nl": COMPRESSION_L2,
    "user_turn": COMPRESSION_L0,
}

PIN_PAGE_TYPES: FrozenSet[str] = frozenset(
    {"system_core", "tools_schema", "workflow_rules", "project_ctx"}
)

CRITICAL_PAGE_TYPES: FrozenSet[str] = frozenset(
    k for k, v in CRITICAL_PAGE_COMPRESSION_MAX.items() if v <= COMPRESSION_L0
)

MACRO_COMPACT_PAGE_TYPES: FrozenSet[str] = frozenset(
    {
        "system_core",
        "tools_schema",
        "workflow_rules",
        "tool_fact_grep",
        "tool_fact_create",
        "tool_fact_delete",
        "tool_fact",
        "user_turn",
        "ui_context_core",
        "tool_param",
    }
)

SKIPPED_IN_MACRO_COMPACT: FrozenSet[str] = frozenset(
    {"project_ctx", "session_prefix", "observe_nl", "tool_fact_modify"}
)

# 每轮预期变化的页类型：hash 变化不算 prefix 漂移
VARIABLE_PAGE_TYPES: FrozenSet[str] = frozenset({"user_turn"})


def compression_max_for(page_type: str) -> int:
    return CRITICAL_PAGE_COMPRESSION_MAX.get(page_type, COMPRESSION_L2)


def is_critical_page(page_type: str) -> bool:
    mx = compression_max_for(page_type)
    return mx <= COMPRESSION_L0


def default_flags_for(page_type: str) -> int:
    flags = PAGE_FLAG_RO
    if page_type in PIN_PAGE_TYPES:
        flags |= PAGE_FLAG_PIN
    if is_critical_page(page_type):
        flags |= PAGE_FLAG_CRITICAL
    return flags


def allowed_in_template(page_type: str, template: str) -> bool:
    if template != "macro_compact":
        return True
    if page_type in SKIPPED_IN_MACRO_COMPACT:
        return False
    return page_type in MACRO_COMPACT_PAGE_TYPES or page_type.startswith("tool_fact")
