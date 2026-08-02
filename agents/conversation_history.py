# -*- coding: utf-8 -*-
"""同会话短时对话历史：供 LangGraph / ReAct 注入近期轮次（区别于 mem0 长期记忆）。"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def conversation_history_max_messages() -> int:
    try:
        n = int(os.getenv("REACT_CONVERSATION_HISTORY_MAX", "8"))
    except (TypeError, ValueError):
        n = 8
    return max(0, min(n, 24))


def conversation_history_max_chars() -> int:
    try:
        n = int(os.getenv("REACT_CONVERSATION_HISTORY_CHARS", "2400"))
    except (TypeError, ValueError):
        n = 2400
    return max(200, min(n, 12000))


def normalize_conversation_history(
    raw: Any,
    *,
    max_messages: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> List[Dict[str, str]]:
    """清洗前端传来的 history，保留最近若干条 user/assistant 文本。"""
    if not isinstance(raw, list) or not raw:
        return []
    cap = conversation_history_max_messages() if max_messages is None else max_messages
    char_cap = conversation_history_max_chars() if max_chars is None else max_chars
    if cap <= 0:
        return []

    cleaned: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = item.get("content")
        if content is None:
            content = item.get("finalResponse") or item.get("understanding") or ""
        text = str(content or "").replace("\u200b", "").strip()
        if not text:
            continue
        if len(text) > char_cap:
            text = text[: char_cap - 20] + "…(truncated)"
        cleaned.append({"role": role, "content": text})

    if len(cleaned) > cap:
        cleaned = cleaned[-cap:]
    return cleaned


def extract_last_url_from_history(history: List[Dict[str, str]]) -> Optional[str]:
    for item in reversed(history or []):
        m = _URL_RE.search(str(item.get("content") or ""))
        if m:
            return m.group(0).rstrip(".,;，。；）)")
    return None


def history_as_chat_messages(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """转为 OpenAI messages 片段（不含 system / 当前 user）。"""
    return [{"role": h["role"], "content": h["content"]} for h in history or []]


def build_recent_url_hint(history: List[Dict[str, str]], *, locale: Optional[str] = None) -> Optional[str]:
    url = extract_last_url_from_history(history)
    if not url:
        return None
    if (locale or "").lower().startswith("en"):
        return f"[Session context] Most recently mentioned URL in this chat: {url}"
    return f"[会话上下文] 本对话近期提到的网址：{url}"
