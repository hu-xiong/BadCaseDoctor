# -*- coding: utf-8 -*-
"""
LangGraph 内运行滚动摘要：langmem SummarizationNode 的薄封装。

- 仅在单轮消息数超阈值时触发；任何异常都静默回退（agent 直接用原始 messages）。
- 摘要视图写入 state["summarized_messages"]，原始 messages 保持追加不动（中断/续跑快照不受影响）。
- freshness 约定：summary_through == message_ids(raw)[-1] 时视图可信，否则丢弃。

环境变量：
- LANGGRAPH_SUMMARIZATION（默认 1）：0/false/off 关闭
- LANGGRAPH_SUMMARY_MAX_TOKENS（默认 6000）：喂给 agent 的消息视图 token 预算
- LANGGRAPH_SUMMARY_MAX_SUMMARY_TOKENS（默认 256）：摘要本身 token 上限（bind max_tokens 强制）
- LANGGRAPH_SUMMARY_MODEL（默认 Config.DASHSCOPE_MODEL）：摘要专用模型
- LANGGRAPH_SUMMARY_MIN_MESSAGES（默认 6）：少于此条数不摘要
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

_TRUE = ("1", "true", "yes", "on")


def summary_enabled() -> bool:
    raw = (os.getenv("LANGGRAPH_SUMMARIZATION") or "1").strip().lower()
    return raw in _TRUE or raw == ""


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int((os.getenv(name) or "").strip() or str(default))
    except ValueError:
        v = default
    return max(lo, min(hi, v))


def summary_max_tokens() -> int:
    return _env_int("LANGGRAPH_SUMMARY_MAX_TOKENS", 6000, 1000, 100000)


def summary_max_summary_tokens() -> int:
    return _env_int("LANGGRAPH_SUMMARY_MAX_SUMMARY_TOKENS", 256, 32, 4096)


def summary_min_messages() -> int:
    return _env_int("LANGGRAPH_SUMMARY_MIN_MESSAGES", 6, 2, 100)


def message_ids(messages: List[Dict[str, Any]]) -> List[str]:
    """确定性消息 id：同一消息列表永远得到同一 id 序列（跨节点/跨轮一致）。"""
    ids: List[str] = []
    for i, m in enumerate(messages or []):
        if not isinstance(m, dict):
            m = {"role": "unknown", "content": str(m)}
        role = str(m.get("role") or "")
        content = m.get("content")
        try:
            c = json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            c = str(content)
        h = hashlib.sha1(f"{role}|{c}".encode("utf-8", "ignore")).hexdigest()[:12]
        ids.append(f"m{i}-{h}")
    return ids


_summary_model_cache: Dict[str, Any] = {}


def _summary_model() -> Any:
    key = "model"
    if key in _summary_model_cache:
        return _summary_model_cache[key]
    from langchain_openai import ChatOpenAI

    from config import Config

    api_key = (getattr(Config, "DASHSCOPE_API_KEY", None) or "").strip()
    base_url = (getattr(Config, "DASHSCOPE_COMPAT_BASE_URL", None) or "").strip()
    if not api_key or not base_url:
        _summary_model_cache[key] = None
        return None
    model_name = (
        (os.getenv("LANGGRAPH_SUMMARY_MODEL") or "").strip()
        or (getattr(Config, "DASHSCOPE_MODEL", None) or "").strip()
    )
    if not model_name:
        _summary_model_cache[key] = None
        return None
    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        max_retries=2,
    )
    llm = llm.bind(max_tokens=summary_max_summary_tokens())
    _summary_model_cache[key] = llm
    return llm


async def summarize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """图节点：messages(dict, OpenAI 风格) → summarized_messages(dict 视图) + summary_context。"""
    raw = list(state.get("messages") or [])
    if len(raw) < summary_min_messages():
        return {}
    model = _summary_model()
    if model is None:
        return {}
    try:
        from langchain_core.messages.utils import (
            convert_to_messages,
            convert_to_openai_messages,
        )
        from langmem.short_term import asummarize_messages

        ids = message_ids(raw)
        lc_messages = convert_to_messages(raw)
        for m, mid in zip(lc_messages, ids):
            if getattr(m, "id", None) is None:
                m.id = mid
        running_summary = (state.get("summary_context") or {}).get("running_summary")
        result = await asummarize_messages(
            lc_messages,
            running_summary=running_summary,
            model=model,
            max_tokens=summary_max_tokens(),
            max_summary_tokens=summary_max_summary_tokens(),
        )
        view = [dict(m) for m in convert_to_openai_messages(result.messages)]
        out: Dict[str, Any] = {
            "summarized_messages": view,
            "summary_through": ids[-1],
        }
        if result.running_summary:
            out["summary_context"] = {"running_summary": result.running_summary}
        if os.getenv("PERF_LOG", "").strip().lower() in _TRUE:
            print(
                f"[SUMMARY] view={len(view)}/{len(raw)} summarized="
                f"{len(result.running_summary.summarized_message_ids) if result.running_summary else 0}",
                flush=True,
            )
        return out
    except Exception as e:
        try:
            print(f"[SUMMARY] skipped (fallback to raw messages): {e}", flush=True)
        except Exception:
            pass
        return {}


async def summarize_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return summarize_state(state)


def summary_view_or_raw(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """agent_node 取消息视图：视图新鲜（summary_through 对上）用视图，否则用原始 messages。"""
    raw = list(state.get("messages") or [])
    view = state.get("summarized_messages")
    through = state.get("summary_through")
    if view and through and raw:
        try:
            if message_ids(raw)[-1] == through:
                return list(view)
        except Exception:
            pass
    return raw
