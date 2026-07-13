# -*- coding: utf-8 -*-
"""跨轮对话保存 CDP 验证码登录待续状态。"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

_STATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "tmp",
    "login_states",
    "pending",
)
_TTL_SEC = 30 * 60


def _ensure_dir() -> None:
    os.makedirs(_STATE_DIR, exist_ok=True)


def _key(chat_session_id: Optional[int], project_id: Optional[int]) -> str:
    cs = int(chat_session_id) if chat_session_id else 0
    pid = int(project_id) if project_id else 0
    return f"chat{cs}_proj{pid}.json"


def save_login_pending(
    *,
    chat_session_id: Optional[int],
    project_id: Optional[int],
    pending: Dict[str, Any],
) -> None:
    _ensure_dir()
    path = os.path.join(_STATE_DIR, _key(chat_session_id, project_id))
    payload = {
        "saved_at": time.time(),
        "chat_session_id": chat_session_id,
        "project_id": project_id,
        **pending,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def load_login_pending(
    *,
    chat_session_id: Optional[int],
    project_id: Optional[int],
) -> Optional[Dict[str, Any]]:
    path = os.path.join(_STATE_DIR, _key(chat_session_id, project_id))
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        saved_at = float(data.get("saved_at") or 0)
        if saved_at and time.time() - saved_at > _TTL_SEC:
            clear_login_pending(chat_session_id=chat_session_id, project_id=project_id)
            return None
        return {
            "session_id": data.get("session_id"),
            "snapshot_id": data.get("snapshot_id"),
            "login_type": data.get("login_type"),
            "await_type": data.get("await_type"),
            "url": data.get("url"),
        }
    except Exception:
        return None


def clear_login_pending(
    *,
    chat_session_id: Optional[int],
    project_id: Optional[int],
) -> None:
    path = os.path.join(_STATE_DIR, _key(chat_session_id, project_id))
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass
