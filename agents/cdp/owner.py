# -*- coding: utf-8 -*-
"""CDP 浏览器池归属键：按登录用户隔离 Chromium。"""

from __future__ import annotations

from typing import Any, Optional


def resolve_cdp_owner_key(
    *,
    user_id: Any = None,
    userId: Any = None,
    project_id: Any = None,
    **_: Any,
) -> str:
    """同一 owner_key 共享一个 Chromium；优先 user_id，其次 project_id。"""
    for raw in (user_id, userId):
        if raw is None:
            continue
        s = str(raw).strip()
        if not s or s == "system_agent":
            continue
        return f"user:{s}"
    if project_id is not None and str(project_id).strip():
        return f"project:{str(project_id).strip()}"
    return "anonymous"
