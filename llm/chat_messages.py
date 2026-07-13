# -*- coding: utf-8 -*-
"""将 prompt 中的 <system> 分段拆为 Chat API 的 role=system / role=user。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union

from llm.multimodal_content import openai_style_user_content

_SYSTEM_BLOCK_RE = re.compile(
    r"<system>\s*([\s\S]*?)\s*</system>",
    re.IGNORECASE,
)

__all__ = [
    "split_system_user_prompt",
    "build_chat_messages",
    "prompt_to_messages",
    "normalize_chat_messages",
]


def split_system_user_prompt(combined: str) -> Tuple[Optional[str], str]:
    """
    提取所有 <system>...</system> 为 system 正文；其余合并为 user 正文（去掉空行堆积）。
    无 system 块时返回 (None, combined)。
    """
    text = combined if isinstance(combined, str) else str(combined or "")
    if not text.strip():
        return None, ""
    if not _SYSTEM_BLOCK_RE.search(text):
        return None, text.strip()

    systems: List[str] = []

    def _collect(m: re.Match) -> str:
        block = (m.group(1) or "").strip()
        if block:
            systems.append(block)
        return ""

    user = _SYSTEM_BLOCK_RE.sub(_collect, text)
    user = re.sub(r"\n{3,}", "\n\n", user).strip()
    system = "\n\n".join(systems).strip() or None
    return system, user


def build_chat_messages(
    *,
    user: str,
    system: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    images: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []
    if history:
        messages.extend(history)
    if system and str(system).strip():
        messages.append({"role": "system", "content": str(system).strip()})
    u = (user or "").strip()
    if not u:
        u = "请严格按 system 中的规则完成本轮任务。"
    messages.append(
        {
            "role": "user",
            "content": openai_style_user_content(u, images),
        }
    )
    return messages


def prompt_to_messages(
    prompt: str,
    history: Optional[List[Dict[str, Any]]] = None,
    images: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """从整段 prompt（可含 <system> 标签）构建 API messages。"""
    system, user = split_system_user_prompt(prompt)
    return build_chat_messages(system=system, user=user, history=history, images=images)


def _user_content_to_text(content: Union[str, List[Dict[str, Any]], None]) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") == "text":
                parts.append(str(p.get("text") or ""))
        return "\n".join(parts)
    return str(content)


def normalize_chat_messages(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    将仅含 <system> 标签的 user 消息拆成 system + user。
    已有 role=system 时不重复拆分。
    """
    if not messages:
        return messages
    has_system = any(
        str(m.get("role") or "").lower() == "system" for m in messages if isinstance(m, dict)
    )
    if has_system:
        return messages

    out: List[Dict[str, Any]] = []
    changed = False
    for m in messages:
        if not isinstance(m, dict):
            out.append(m)
            continue
        role = str(m.get("role") or "user").lower()
        if role != "user":
            out.append(m)
            continue
        raw = _user_content_to_text(m.get("content"))
        if "<system>" not in raw.lower():
            out.append(m)
            continue
        sys, usr = split_system_user_prompt(raw)
        if not sys:
            out.append(m)
            continue
        changed = True
        out.append({"role": "system", "content": sys})
        new_m = dict(m)
        if isinstance(m.get("content"), list):
            new_parts = [p for p in m["content"] if isinstance(p, dict) and p.get("type") != "text"]
            new_parts.append({"type": "text", "text": usr or "请严格按 system 中的规则完成本轮任务。"})
            new_m["content"] = new_parts
        else:
            new_m["content"] = usr or "请严格按 system 中的规则完成本轮任务。"
        out.append(new_m)

    return out if changed else messages
