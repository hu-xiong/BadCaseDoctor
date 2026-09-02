# -*- coding: utf-8 -*-
"""
LangSmith 观测：为 LangGraph / ReAct 打开 tracing。

环境变量（与官方一致）：
- LANGSMITH_TRACING=1|true（或兼容 LANGCHAIN_TRACING_V2）
- LANGSMITH_API_KEY=lsv2_…
- LANGSMITH_PROJECT=badcase-doctor（可选，默认 badcase-doctor）
- LANGSMITH_ENDPOINT=（可选，自托管）
- LANGSMITH_WORKSPACE_ID=（可选）

未设 API Key 或 tracing=0 时为 no-op，不影响主路径。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

_setup_done = False


def langsmith_tracing_enabled() -> bool:
    raw = (
        os.getenv("LANGSMITH_TRACING")
        or os.getenv("LANGCHAIN_TRACING_V2")
        or ""
    ).strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    # 有 key 且未显式关闭时默认开（方便本地只填 key）
    return bool((os.getenv("LANGSMITH_API_KEY") or "").strip())


def langsmith_project() -> str:
    return (
        (os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "badcase-doctor")
        .strip()
        or "badcase-doctor"
    )


def setup_langsmith_tracing(*, force: bool = False) -> bool:
    """
    应用启动 / 引擎初始化时调用一次：写入标准 env，供 langchain/langgraph 自动上报。
    返回是否已启用 tracing。
    """
    global _setup_done
    if _setup_done and not force:
        return langsmith_tracing_enabled() and bool((os.getenv("LANGSMITH_API_KEY") or "").strip())

    if not langsmith_tracing_enabled():
        _setup_done = True
        return False

    key = (os.getenv("LANGSMITH_API_KEY") or "").strip()
    if not key:
        print("[LANGSMITH] tracing 已请求但未设置 LANGSMITH_API_KEY，跳过", flush=True)
        _setup_done = True
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ["LANGSMITH_PROJECT"] = langsmith_project()
    os.environ["LANGCHAIN_PROJECT"] = langsmith_project()
    endpoint = (os.getenv("LANGSMITH_ENDPOINT") or "").strip()
    if endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = endpoint

    _setup_done = True
    print(
        f"[LANGSMITH] tracing on project={langsmith_project()}",
        flush=True,
    )
    return True


def run_metadata(
    *,
    agent_session_id: Optional[str] = None,
    project_id: Any = None,
    plan_id: Any = None,
    engine: str = "langgraph",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "engine": engine,
        "app": "badcase_doctor",
    }
    if agent_session_id:
        meta["agent_session_id"] = str(agent_session_id)
    if project_id is not None:
        meta["project_id"] = project_id
    if plan_id is not None:
        meta["plan_id"] = plan_id
    if user_id:
        meta["user_id"] = str(user_id)
    return meta


def tracing_context(
    *,
    name: str = "langgraph_run",
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
):
    """
    可选上下文管理器：包住一轮 run_stream。
    LangSmith 未启用或未安装时退化为 nullcontext。
    """
    from contextlib import nullcontext

    if not setup_langsmith_tracing():
        return nullcontext()
    try:
        from langsmith import trace
    except Exception:
        return nullcontext()

    return trace(
        name=name,
        metadata=dict(metadata or {}),
        tags=list(tags or ["badcase-doctor", "langgraph"]),
        project_name=langsmith_project(),
    )
