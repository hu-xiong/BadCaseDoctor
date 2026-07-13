# -*- coding: utf-8 -*-
"""Canonical messages 序列化与 P0～P3 静态前缀片段缓存。"""
from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "content_hash_bytes",
    "content_hash_text",
    "canonical_message_dict",
    "canonical_messages_bytes",
    "StaticPrefixCache",
    "assemble_messages_from_pages",
    "messages_to_prompt",
    "message_content_to_str",
]


def message_content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif item.get("type") == "image_url":
                    parts.append("[image]")
                else:
                    parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    return str(content)


def canonical_message_dict(msg: Dict[str, Any]) -> Dict[str, Any]:
    role = str(msg.get("role") or "user")
    out: Dict[str, Any] = {"role": role, "content": message_content_to_str(msg.get("content"))}
    if msg.get("name"):
        out["name"] = msg["name"]
    if msg.get("tool_calls"):
        out["tool_calls"] = msg["tool_calls"]
    if msg.get("tool_call_id"):
        out["tool_call_id"] = msg["tool_call_id"]
    return out


def canonical_messages_bytes(messages: Sequence[Dict[str, Any]]) -> bytes:
    normalized = [canonical_message_dict(m) for m in messages]
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def content_hash_bytes(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def content_hash_text(text: str) -> str:
    return content_hash_bytes((text or "").encode("utf-8"))


class StaticPrefixCache:
    """按 cache_key 缓存 P0～P3 对应 messages 前缀片段（bytes + hash）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[str, Tuple[bytes, str, List[Dict[str, Any]]]] = {}

    def get(self, cache_key: str) -> Optional[Tuple[bytes, str, List[Dict[str, Any]]]]:
        with self._lock:
            return self._entries.get(cache_key)

    def put(
        self,
        cache_key: str,
        messages: List[Dict[str, Any]],
        blob: bytes,
        digest: str,
    ) -> None:
        with self._lock:
            self._entries[cache_key] = (blob, digest, list(messages))

    def build_key(
        self,
        *,
        locale: str = "",
        tools_version: str = "",
        project_id: str = "",
        template: str = "full",
    ) -> str:
        return "|".join(
            [
                str(locale or ""),
                str(tools_version or ""),
                str(project_id or ""),
                str(template or "full"),
            ]
        )


_GLOBAL_STATIC_PREFIX_CACHE = StaticPrefixCache()


def get_static_prefix_cache() -> StaticPrefixCache:
    return _GLOBAL_STATIC_PREFIX_CACHE


def assemble_messages_from_pages(
    static_messages: Sequence[Dict[str, Any]],
    dynamic_messages: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """逻辑全量：静态前缀 + 动态 tail（均为 OpenAI messages 形态）。"""
    out: List[Dict[str, Any]] = []
    out.extend(canonical_message_dict(m) for m in static_messages)
    out.extend(canonical_message_dict(m) for m in dynamic_messages)
    return out


def messages_to_prompt(messages: Sequence[Dict[str, Any]]) -> str:
    """将 canonical messages 还原为 <system> 包裹的 prompt（供 chat_stream 接口）。"""
    systems: List[str] = []
    users: List[str] = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        content = message_content_to_str(msg.get("content"))
        if role == "system":
            if content:
                systems.append(content)
        elif role == "user":
            if content:
                users.append(content)
        else:
            if content:
                users.append(f"[{role}]\n{content}")
    user = "\n\n".join(users).strip()
    if not systems:
        return user
    system = "\n\n".join(systems).strip()
    if user:
        return f"<system>\n{system}\n</system>\n\n{user}"
    return f"<system>\n{system}\n</system>"
