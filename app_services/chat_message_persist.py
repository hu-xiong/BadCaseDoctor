# -*- coding: utf-8 -*-
"""Chat 助手消息落库：流式 checkpoint 与最终持久化共用字段映射。"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def _json_text(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        return s if s else None
    try:
        return json.dumps(val, ensure_ascii=False, default=str)
    except Exception:
        return None


def assistant_fields_from_client(data: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """将前端 POST/PUT body 转为 ChatMessage 可写字段（JSON 列均为文本）。"""
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Optional[str]] = {}
    for key, col in (
        ("content", "content"),
        ("understanding", "understanding"),
        ("reasoning", "reasoning"),
        ("steps", "steps"),
        ("execution_results", "execution_results"),
        ("agent_result", "agent_result"),
        ("evidences", "evidences"),
        ("navigation", "navigation"),
        ("modify_navigation", "modify_navigation"),
        ("modify_groups", "modify_groups"),
        ("delete_navigation", "delete_navigation"),
        ("final_response", "final_response"),
    ):
        if key in data:
            out[col] = _json_text(data.get(key))
    if "llm_model" in data:
        lm = data.get("llm_model")
        out["llm_model"] = str(lm).strip()[:128] if lm is not None and str(lm).strip() else None
    return out


def apply_assistant_fields_to_message(msg, fields: Dict[str, Optional[str]]) -> None:
    for col, val in fields.items():
        if hasattr(msg, col):
            setattr(msg, col, val)


def upsert_assistant_chat_message(
    *,
    db,
    ChatMessage,
    ChatSession,
    session_id: int,
    user_id: int,
    fields: Dict[str, Optional[str]],
    message_id: Optional[int] = None,
) -> Optional[int]:
    """
    更新已有助手消息，或在该 session 下新建一条 is_user=False 消息。
    返回 message.id。
    """
    session = db.session.get(ChatSession, int(session_id))
    if not session:
        return None
    if int(session.user_id) != int(user_id):
        return None

    msg = None
    if message_id is not None:
        try:
            mid = int(message_id)
        except (TypeError, ValueError):
            mid = None
        if mid is not None:
            msg = db.session.get(ChatMessage, mid)
            if msg and (int(msg.session_id) != int(session_id) or msg.is_user):
                msg = None

    if msg is None:
        msg = ChatMessage(
            session_id=int(session_id),
            user_id=None,
            is_user=False,
        )
        db.session.add(msg)

    apply_assistant_fields_to_message(msg, fields)
    content = (getattr(msg, "content", None) or "").strip()
    final_response = (getattr(msg, "final_response", None) or "").strip()
    if not content and not final_response:
        msg.content = "处理中…"
    session.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    db.session.commit()
    return int(msg.id)
