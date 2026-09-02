# -*- coding: utf-8 -*-
"""
LangGraph 断点快照：messages + result_context + 计数器。

与 react_run_store 检查点配合：checkpoint.langgraph_resume 供下一轮恢复图状态。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# result_context 中值得跨 pause 保留的键（定位 / 门控 / 人机）
_RC_KEEP_KEYS = (
    "grep_result",
    "first_bug_id",
    "first_badcase_id",
    "first_testcase_id",
    "first_card_id",
    "first_plan_id",
    "bug_list",
    "badcase_list",
    "testcase_list",
    "card_list",
    "plan_list",
    "navigation",
    "awaiting_client",
    "awaiting_client_terminal",
    "awaiting_human",
    "interrupt_reason",
    "pending_terminal",
    "long_memory_text",
    "long_memory_items",
    "client_os",
    "cdp_resolved_plan_id",
    "cdp_login_pending",
    "pending_modify_preview",
    "project_id",
    "plan_id",
)


def user_input_already_has_terminal_block(text: str) -> bool:
    t = text or ""
    return "【本机终端" in t or "[Client terminal" in t


def _trunc(s: Any, n: int = 4000) -> str:
    t = str(s if s is not None else "")
    return t if len(t) <= n else t[: n - 1] + "…"


def compact_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(msg, dict):
        return None
    role = str(msg.get("role") or "").strip()
    if role not in ("system", "user", "assistant", "tool"):
        return None
    out: Dict[str, Any] = {"role": role}
    content = msg.get("content")
    if content is not None:
        out["content"] = _trunc(content, 6000 if role == "system" else 4000)
    if role == "assistant" and msg.get("tool_calls"):
        tcs = []
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            tcs.append(
                {
                    "id": tc.get("id"),
                    "type": tc.get("type") or "function",
                    "function": {
                        "name": (fn or {}).get("name") or tc.get("name"),
                        "arguments": _trunc((fn or {}).get("arguments") or tc.get("arguments") or "{}", 2000),
                    },
                }
            )
        if tcs:
            out["tool_calls"] = tcs
    if role == "tool":
        if msg.get("tool_call_id") is not None:
            out["tool_call_id"] = msg.get("tool_call_id")
        if msg.get("name"):
            out["name"] = msg.get("name")
    return out


def compact_messages(messages: Optional[List[Any]], *, max_n: int = 40) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for m in messages or []:
        c = compact_message(m) if isinstance(m, dict) else None
        if c:
            rows.append(c)
    if len(rows) > max_n:
        # 保留首条 system + 最近 N-1
        head = [rows[0]] if rows and rows[0].get("role") == "system" else []
        tail = rows[-(max_n - len(head)) :]
        rows = head + [m for m in tail if m not in head] if head else rows[-max_n:]
        if head and rows and rows[0] is not head[0]:
            rows = head + rows
            if len(rows) > max_n:
                rows = [rows[0]] + rows[-(max_n - 1) :]
    return rows


def compact_result_context(rc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(rc, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in _RC_KEEP_KEYS:
        if k not in rc:
            continue
        v = rc[k]
        if isinstance(v, list) and len(v) > 30:
            out[k] = v[:30]
        elif isinstance(v, str) and len(v) > 4000:
            out[k] = _trunc(v, 4000)
        else:
            out[k] = v
    # 额外：以 first_/grep_ 前缀的小标量
    for k, v in rc.items():
        if k in out:
            continue
        if k.startswith("first_") or k.startswith("grep_"):
            if isinstance(v, (str, int, float, bool)) or v is None:
                out[k] = v
            elif isinstance(v, list) and len(v) <= 20:
                out[k] = v
    return out


def compact_task_plan_steps(steps: Any) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(steps, list) or not steps:
        return None
    out: List[Dict[str, Any]] = []
    for s in steps[:12]:
        if not isinstance(s, dict):
            continue
        out.append(
            {
                "id": s.get("id"),
                "name": _trunc(s.get("name") or s.get("description") or "", 200),
                "status": str(s.get("status") or "pending")[:32],
                "tool": s.get("tool"),
            }
        )
    return out or None


def build_langgraph_resume_snapshot(
    *,
    messages: List[Dict[str, Any]],
    result_context: Optional[Dict[str, Any]] = None,
    grep_tool_calls: int = 0,
    grep_attempts: int = 0,
    last_grep_empty: bool = False,
    failure_retries: int = 0,
    failure_action: str = "",
    failure_kind: str = "",
    round_idx: int = 0,
    user_input: str = "",
    reason: str = "",
    task_plan_steps: Any = None,
    thread_id: str = "",
) -> Dict[str, Any]:
    snap: Dict[str, Any] = {
        "schema_version": 1,
        "reason": (reason or "")[:120],
        "messages": compact_messages(messages),
        "result_context": compact_result_context(result_context),
        "grep_tool_calls": int(grep_tool_calls or 0),
        "grep_attempts": int(grep_attempts or 0),
        "last_grep_empty": bool(last_grep_empty),
        "failure_retries": int(failure_retries or 0),
        "failure_action": str(failure_action or "")[:40],
        "failure_kind": str(failure_kind or "")[:80],
        "round_idx": int(round_idx or 0),
        "user_input": _trunc(user_input, 2000),
    }
    plan = compact_task_plan_steps(task_plan_steps)
    if plan:
        snap["task_plan_steps"] = plan
    tid = (thread_id or "").strip()
    if tid:
        snap["thread_id"] = tid[:240]
    return snap


def langgraph_resume_sse(snapshot: Dict[str, Any], *, reason: str = "") -> Dict[str, Any]:
    return {
        "event": "langgraph_resume",
        "reason": reason or snapshot.get("reason") or "",
        "state": snapshot,
    }


def format_long_memory_block(prefetch: Optional[Dict[str, Any]], *, locale: str = "zh") -> str:
    if not isinstance(prefetch, dict) or not prefetch:
        return ""
    text = str(
        prefetch.get("long_memory_text") or prefetch.get("merged") or ""
    ).strip()
    items = prefetch.get("long_memory_items") or prefetch.get("memories")
    lines: List[str] = []
    en = (locale or "").lower().startswith("en")
    if text:
        lines.append(("Long-term memory:\n" if en else "长期记忆：\n") + _trunc(text, 2500))
    if isinstance(items, list) and items:
        bits = []
        for it in items[:8]:
            if isinstance(it, dict):
                bits.append(_trunc(it.get("content") or it.get("text") or it, 200))
            else:
                bits.append(_trunc(it, 200))
        if bits:
            lines.append(("Memory items: " if en else "记忆条目：") + " | ".join(bits))
    return "\n".join(lines).strip()


def format_project_hint_block(
    *,
    hint_project_name: Optional[str],
    hint_plan_name: Optional[str],
    locale: str = "zh",
) -> str:
    hp = (str(hint_project_name).strip() if hint_project_name else "") or ""
    hpl = (str(hint_plan_name).strip() if hint_plan_name else "") or ""
    if not hp and not hpl:
        return ""
    en = (locale or "").lower().startswith("en")
    if en:
        parts = []
        if hp:
            parts.append(f"project={hp}")
        if hpl:
            parts.append(f"plan/iteration={hpl}")
        return "Context names: " + ", ".join(parts)
    parts = []
    if hp:
        parts.append(f"项目={hp}")
    if hpl:
        parts.append(f"计划/迭代={hpl}")
    return "上下文名称：" + "，".join(parts)


def apply_langgraph_resume(
    *,
    system_prompt: str,
    resume_state: Dict[str, Any],
    new_user_content: str,
) -> Dict[str, Any]:
    """
    从快照恢复 init 字段；刷新 system；追加本轮用户指令。
    返回可 merge 进 LangGraphAgentState 的 dict。
    """
    snap = resume_state if isinstance(resume_state, dict) else {}
    msgs = compact_messages(snap.get("messages") or [])
    # 去掉旧 system，换当前系统提示
    msgs = [m for m in msgs if m.get("role") != "system"]
    out_msgs: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    out_msgs.extend(msgs)
    nu = (new_user_content or "").strip()
    if nu:
        # 避免与末条完全相同的 user 重复
        last = out_msgs[-1] if out_msgs else None
        if not (
            isinstance(last, dict)
            and last.get("role") == "user"
            and str(last.get("content") or "").strip() == nu
        ):
            out_msgs.append({"role": "user", "content": nu})
    rc = compact_result_context(snap.get("result_context") if isinstance(snap.get("result_context"), dict) else {})
    rc.pop("awaiting_client", None)
    rc.pop("awaiting_client_terminal", None)
    # awaiting_human 保留到模型可见，但可清 interrupt 等待标
    plan = compact_task_plan_steps(snap.get("task_plan_steps"))
    return {
        "messages": out_msgs,
        "result_context": rc,
        "grep_tool_calls": int(snap.get("grep_tool_calls") or 0),
        "grep_attempts": int(snap.get("grep_attempts") or 0),
        "last_grep_empty": bool(snap.get("last_grep_empty")),
        "failure_retries": int(snap.get("failure_retries") or 0),
        "failure_action": "continue",
        "failure_kind": "resumed",
        "round_idx": int(snap.get("round_idx") or 0),
        "user_input": nu or str(snap.get("user_input") or ""),
        "done": False,
        "task_plan_steps": plan,
        "task_plan_emitted": bool(plan),
    }


def try_persist_langgraph_interrupt(
    *,
    chat_session_id: Optional[int],
    project_id: Any,
    user_id: Any,
    react_request_id: Optional[str],
    user_input: str,
    snapshot: Dict[str, Any],
    interrupt_reason: str,
    model_name: Optional[str] = None,
) -> Optional[str]:
    """尽力写入 ReactAgentRun interrupted；无 session/request 时跳过。"""
    try:
        sid = int(chat_session_id) if chat_session_id is not None else 0
    except (TypeError, ValueError):
        sid = 0
    if sid <= 0:
        return None
    rid = (react_request_id or "").strip()
    if not rid:
        return None
    try:
        uid = int(user_id) if user_id is not None and str(user_id).strip() else 0
    except (TypeError, ValueError):
        uid = 0
    if uid <= 0:
        return None
    try:
        from agents.react_run_store import upsert_interrupted_run

        ck = {
            "interrupt_reason": interrupt_reason or snapshot.get("reason") or "langgraph_interrupt",
            "original_user_input": (user_input or "")[:4000],
            "langgraph_resume": snapshot,
            "summary": (snapshot.get("reason") or "")[:500],
        }
        return upsert_interrupted_run(
            chat_session_id=sid,
            project_id=int(project_id) if project_id is not None else None,
            user_id=uid,
            react_request_id=rid,
            user_input=user_input or "",
            checkpoint=ck,
            model_name=model_name,
        )
    except Exception as e:
        print(f"[LANGGRAPH] persist interrupt failed: {e}", flush=True)
        return None
