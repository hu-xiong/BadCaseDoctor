# -*- coding: utf-8 -*-
"""
LangGraph observe：工具执行后、下一轮 agent 前的结构化观察（默认不调 LLM）。

环境变量：LANGGRAPH_OBSERVE=1（默认开）
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def observe_enabled() -> bool:
    return (os.getenv("LANGGRAPH_OBSERVE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _brief_ids(rc: Dict[str, Any]) -> str:
    bits: List[str] = []
    for k in (
        "first_bug_id",
        "first_badcase_id",
        "first_testcase_id",
        "first_card_id",
        "first_plan_id",
    ):
        v = rc.get(k)
        if v is not None and str(v).strip():
            bits.append(f"{k}={v}")
    return ", ".join(bits[:4])


def build_observe_note(
    *,
    tool_name: str,
    observation: Any,
    failure_action: str = "continue",
    failure_kind: str = "",
    result_context: Optional[Dict[str, Any]] = None,
    locale: str = "zh",
) -> str:
    """根据工具结果生成短观察，供下一轮决策。"""
    name = (tool_name or "").strip() or "tool"
    obs = observation if isinstance(observation, dict) else {"raw": observation}
    en = (locale or "").lower().startswith("en")
    fa = (failure_action or "continue").strip().lower()
    kind = (failure_kind or "").strip()
    rc = result_context if isinstance(result_context, dict) else {}
    ok = bool(obs.get("success", True)) and not obs.get("blocked")

    if obs.get("terminal_pause_for_client") or obs.get("browser_pause_for_client"):
        return (
            "Waiting for client terminal/browser; do not invent results."
            if en
            else "已交还本机终端/浏览器，等待结果回传；勿臆造执行结果。"
        )

    if obs.get("await_user_credentials") or obs.get("await_verification_code"):
        return (
            "Login paused for credentials/verification code. Wait for user; do not invent secrets."
            if en
            else "登录等待凭证/验证码。请等用户提供；勿臆造密码或验证码。"
        )

    if obs.get("preview_only") or obs.get("confirmation_required"):
        tid = obs.get("target_id") or rc.get("first_bug_id") or ""
        return (
            f"Sandbox preview ready for `{name}` (id={tid}). Stop; user confirms in the list (never confirm=true yourself)."
            if en
            else f"`{name}` 沙箱预览已就绪（id={tid}）。已停图，请用户在侧栏确认；禁止自行 confirm=true。"
        )

    if obs.get("recovered"):
        return (
            f"Structured recovery succeeded for `{name}`; continue from current context."
            if en
            else f"`{name}` 已通过结构化纠错恢复成功；请基于当前上下文继续，勿重复失败步骤。"
        )

    ids = _brief_ids(rc)
    if ok:
        if name == "grep":
            return (
                f"grep succeeded. Located: {ids or 'see tool result'}. Next: modify/delete with returned id, or summarize."
                if en
                else f"grep 成功。定位：{ids or '见工具结果'}。下一步用返回 id 做 modify/delete，或向用户汇总。"
            )
        return (
            f"`{name}` succeeded. Context ids: {ids or 'n/a'}. Decide next tool or finish."
            if en
            else f"`{name}` 成功。上下文 id：{ids or '无'}。请决定下一步工具或收尾。"
        )

    err = str(obs.get("error") or obs.get("message") or obs.get("reason") or "")[:220]
    if fa == "retry":
        return (
            f"RETRY `{name}` ({kind or 'fail'}): {err}. Prefer grep then retry with real id."
            if en
            else f"【观察-RETRY】`{name}` 失败（{kind or 'fail'}）：{err}。优先 grep 定位真实 id 再重试。"
        )
    if fa == "replan":
        return (
            f"REPLAN after `{name}` ({kind or 'fail'}): {err}. Change strategy; do not repeat same call."
            if en
            else f"【观察-REPLAN】`{name}` 失败（{kind or 'fail'}）：{err}。请换策略，勿原样重复。"
        )
    if fa == "interrupt":
        return (
            f"Need user input after `{name}`: {err}"
            if en
            else f"【观察】`{name}` 需用户介入：{err}"
        )
    return (
        f"`{name}` failed: {err}"
        if en
        else f"【观察】`{name}` 失败：{err}"
    )


def observe_message(note: str, *, locale: str = "zh") -> Dict[str, Any]:
    en = (locale or "").lower().startswith("en")
    prefix = "[Observe] " if en else "【观察】"
    body = (note or "").strip()
    if body.startswith("【观察") or body.startswith("[Observe"):
        content = body
    else:
        content = prefix + body
    return {"role": "user", "content": content}


def observe_sse(note: str, *, tool_name: str = "", failure_action: str = "") -> Dict[str, Any]:
    return {
        "event": "observe",
        "summary": (note or "")[:800],
        "tool": tool_name or "",
        "action": failure_action or "",
    }
