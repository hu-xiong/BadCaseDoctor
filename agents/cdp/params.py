# -*- coding: utf-8 -*-
"""CDP 工具参数补全：从用户消息推断 URL，并在 blank 页自动导航。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.cdp.credentials import infer_url_from_text


def _is_blank_page_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return not u or u in ("about:blank", "about:srcdoc") or u.startswith("about:")


def resolve_cdp_target_url(
    *,
    params: Optional[Dict[str, Any]] = None,
    user_input: Optional[str] = None,
    result_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """合并 params.url、用户消息 URL、会话上下文中的 cdp_target_url。"""
    par = params if isinstance(params, dict) else {}
    url = str(par.get("url") or "").strip()
    if not url:
        url = str(infer_url_from_text(user_input) or "").strip()
    if not url and isinstance(result_context, dict):
        url = str(result_context.get("cdp_target_url") or "").strip()
    return url or None


def inject_cdp_tool_params(
    tool_params: Dict[str, Any],
    *,
    user_input: Optional[str] = None,
    result_context: Optional[Dict[str, Any]] = None,
    project_id: Optional[int] = None,
) -> None:
    """
    ReAct 调用 CDP 前补全参数：
    - session create 缺 url 时从用户消息/上下文注入
    - 持久化 cdp_target_url 供后续 explore/snapshot 使用
    """
    if not isinstance(tool_params, dict):
        return

    url = resolve_cdp_target_url(
        params=tool_params,
        user_input=user_input,
        result_context=result_context,
    )
    if url and isinstance(result_context, dict):
        result_context["cdp_target_url"] = url

    act = str(
        tool_params.get("action")
        or tool_params.get("tool_action")
        or ""
    ).strip().lower()
    sub = str(
        tool_params.get("sub_action")
        or tool_params.get("session_action")
        or "create"
    ).strip().lower()

    if url and act in ("session", "cdp_session", "") and sub in ("create", ""):
        tool_params.setdefault("url", url)

    if project_id is not None and tool_params.get("project_id") is None:
        try:
            tool_params.setdefault("project_id", int(project_id))
        except (TypeError, ValueError):
            pass

    if user_input and not tool_params.get("natural_query"):
        tool_params.setdefault("natural_query", user_input)
    if user_input and not tool_params.get("user_query"):
        tool_params.setdefault("user_query", user_input)


async def ensure_session_on_target_url(
    mgr: Any,
    session_id: str,
    *,
    url: Optional[str],
    owner_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """会话仍在 about:blank 且已知目标 URL 时自动 navigate。"""
    target = (url or "").strip()
    if not target or not session_id:
        return None
    session = mgr.get_session(session_id, owner_key=owner_key)
    if not session:
        return None
    try:
        cur = session.page.url or ""
    except Exception:
        cur = ""
    if not _is_blank_page_url(cur):
        return None
    return await mgr.navigate(session_id, target, owner_key=owner_key)
