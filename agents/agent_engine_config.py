# -*- coding: utf-8 -*-
"""Agent 执行引擎选择（旧 ReAct / LangGraph）。"""
from __future__ import annotations

import os
from typing import Optional, FrozenSet


def agent_engine_backend() -> str:
    """
    返回 ``langgraph``（默认）或 ``react``（旧 SimplifiedReActEngine）。

    环境变量：
    - ``AGENT_ENGINE=langgraph|react``（推荐）
    - 兼容别名 ``REACT_ENGINE``
    未设置时默认 ``langgraph``；需回退旧引擎时设 ``AGENT_ENGINE=react``。
    """
    raw = (
        os.getenv("AGENT_ENGINE")
        or os.getenv("REACT_ENGINE")
        or "langgraph"
    ).strip().lower()
    if raw in ("react", "legacy", "old", "simplified"):
        return "react"
    return "langgraph"


def langgraph_max_rounds() -> int:
    try:
        return max(1, min(40, int(os.getenv("AGENT_LANGGRAPH_MAX_ROUNDS", "12") or "12")))
    except Exception:
        return 12


def langgraph_tool_allowlist() -> Optional[FrozenSet[str]]:
    """
    逗号分隔工具名。
    默认 ``*``：注册表内全部工具（skill/cdp/terminal 等均可用）。
    仍会排除 FC 决策元工具（如 get_tool_description）。
    """
    raw = (os.getenv("AGENT_LANGGRAPH_TOOLS") or "*").strip()
    if not raw or raw.lower() in ("*", "all", "any"):
        return None
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
