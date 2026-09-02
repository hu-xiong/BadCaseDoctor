# -*- coding: utf-8 -*-
"""
LangGraph 失败边：对工具 observation 分类为 continue / retry / replan / interrupt / stop。

不调 LLM；结构化规则优先。环境变量：
- LANGGRAPH_FAILURE_MAX_RETRIES（默认 2）：retry+replan 合计上限
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class FailureAction(str, Enum):
    CONTINUE = "continue"  # 成功或可自然进入下一轮
    RETRY = "retry"  # 同目标纠错（强制先 grep / 补参）
    REPLAN = "replan"  # 换策略再决策
    INTERRUPT = "interrupt"  # 交还用户纠正
    STOP = "stop"  # 收尾结束（空检索等）


@dataclass
class FailureDecision:
    action: FailureAction
    kind: str
    hint: str = ""
    summary: str = ""


def failure_max_retries() -> int:
    try:
        return max(0, min(6, int((os.getenv("LANGGRAPH_FAILURE_MAX_RETRIES") or "2").strip() or "2")))
    except ValueError:
        return 2


def _err_text(obs: Dict[str, Any]) -> str:
    parts = [
        str(obs.get("error") or ""),
        str(obs.get("message") or ""),
        str(obs.get("reason") or ""),
    ]
    return " ".join(p for p in parts if p).strip()


def _needs_grep_recovery(tool: str, obs: Dict[str, Any]) -> bool:
    if (tool or "").lower() not in ("modify", "delete", "copy"):
        return False
    if obs.get("need_grep_first") is True:
        return True
    err = _err_text(obs).lower()
    keys = (
        "target_id",
        "缺少必要参数",
        "need_grep",
        "未找到",
        "not found",
        "no matching",
        "missing id",
        "invalid id",
    )
    return any(k in err for k in keys)


def classify_tool_failure(
    *,
    tool_name: str,
    observation: Dict[str, Any],
    failure_retries: int = 0,
    grep_empty: bool = False,
    client_pause: bool = False,
    locale: str = "zh",
) -> FailureDecision:
    """
    根据 observation 决定失败边。
    调用方应已处理 client_pause / grep_empty 的 done 收尾；此处仍给出动作供路由统一。
    """
    name = (tool_name or "").strip().lower()
    obs = observation if isinstance(observation, dict) else {"success": False, "raw": observation}
    en = (locale or "").lower().startswith("en")
    retries = int(failure_retries or 0)
    max_r = failure_max_retries()

    if client_pause:
        return FailureDecision(
            action=FailureAction.STOP,
            kind="client_pause",
            summary="awaiting_client",
        )

    if grep_empty:
        return FailureDecision(
            action=FailureAction.STOP,
            kind="empty_grep",
            summary="grep_empty",
        )

    # 登录等人手填凭证 / 验证码：收束，避免空转
    if obs.get("success", True) and (
        obs.get("await_user_credentials") is True
        or obs.get("await_verification_code") is True
    ):
        return FailureDecision(
            action=FailureAction.STOP,
            kind="await_login",
            summary="awaiting_login_input",
            hint=(
                "Waiting for credentials or verification code; do not invent them."
                if en
                else "等待用户提供登录凭证或验证码；勿臆造。"
            ),
        )

    if obs.get("preview_only") or obs.get("confirmation_required"):
        # 沙箱预览成功：停图交给侧栏确认，禁止模型自行 confirm=true
        if obs.get("success", True):
            return FailureDecision(
                action=FailureAction.STOP,
                kind="preview_await_confirm",
                summary="awaiting_preview_confirm",
                hint=(
                    "Sandbox preview ready. Wait for the user to confirm in the list; do not call confirm=true."
                    if en
                    else "沙箱预览已就绪。请等待用户在侧栏确认落库；禁止自行调用 confirm=true。"
                ),
            )

    if obs.get("blocked") and obs.get("reason") == "grep_required_before_modify":
        if retries >= max_r:
            return FailureDecision(
                action=FailureAction.INTERRUPT,
                kind="policy_block_exhausted",
                hint=(
                    "Modify was blocked because grep is required first. Tell the user what to search."
                    if en
                    else "修改被门控拦截（须先检索）。请向用户说明需要先定位哪条记录，或等待用户补充关键词。"
                ),
                summary="blocked_need_grep",
            )
        return FailureDecision(
            action=FailureAction.RETRY,
            kind="policy_need_grep",
            hint=(
                "[Recovery] Previous modify/delete was blocked. Call grep NOW with keywords from the user goal, then modify."
                if en
                else "【纠错-RETRY】上一步 modify/delete 被门控拦截。请立刻调用 grep，用用户目标里的标题/关键词定位，找到后再 modify；禁止臆造 id。"
            ),
            summary="retry_grep_first",
        )

    ok = bool(obs.get("success", True))
    if ok and not obs.get("blocked"):
        return FailureDecision(action=FailureAction.CONTINUE, kind="ok")

    # --- 失败 ---
    if _needs_grep_recovery(name, obs):
        if retries >= max_r:
            return FailureDecision(
                action=FailureAction.INTERRUPT,
                kind="missing_id_exhausted",
                hint=(
                    "Could not recover target id. Ask the user which record to change."
                    if en
                    else "无法自动定位目标记录。请向用户确认要改哪一条（标题/ID/所属计划）。"
                ),
                summary="interrupt_missing_id",
            )
        return FailureDecision(
            action=FailureAction.RETRY,
            kind="missing_id",
            hint=(
                "[Recovery] Tool failed due to missing/invalid id. Call grep with title keywords, then retry modify with the returned id."
                if en
                else "【纠错-RETRY】工具因缺少/无效 id 失败。请先 grep（用标题关键词），再用返回的 id 重试 modify；不要编造主键。"
            ),
            summary="retry_after_missing_id",
        )

    err = _err_text(obs)
    if retries >= max_r:
        return FailureDecision(
            action=FailureAction.INTERRUPT,
            kind="tool_error_exhausted",
            hint=(
                f"[Need user help] Tool `{name}` failed repeatedly: {err[:300]}. Ask how to proceed."
                if en
                else f"【需用户介入】工具 `{name}` 多次失败：{err[:300]}。请简要说明失败原因，并询问用户下一步（换关键词/换目标/取消）。"
            ),
            summary="interrupt_max_retries",
        )

    return FailureDecision(
        action=FailureAction.REPLAN,
        kind="tool_error",
        hint=(
            f"[Replan] Tool `{name}` failed: {err[:400]}. Choose a different approach; do not repeat the exact same failing call."
            if en
            else f"【纠错-REPLAN】工具 `{name}` 失败：{err[:400]}。请换策略继续（例如放宽检索、换 target、先查再改）；不要原样重复失败调用。"
        ),
        summary="replan_after_tool_error",
    )


def failure_edge_sse(decision: FailureDecision) -> Dict[str, Any]:
    return {
        "event": "failure_edge",
        "action": decision.action.value,
        "kind": decision.kind,
        "summary": decision.summary,
        "hint": (decision.hint or "")[:500],
    }
