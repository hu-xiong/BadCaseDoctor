# -*- coding: utf-8 -*-
"""
LangGraph 结构化纠错 + 轻量 task_plan。

- RETRY：modify/delete 失败后强制 grep→补参→再执行（不依赖模型自觉）
- REPLAN：强化「禁止原样重复」提示
- task_plan：按用户意图生成启发式步骤，发 plan_init/plan_update
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def structured_recover_enabled() -> bool:
    return (os.getenv("LANGGRAPH_STRUCTURED_RECOVER") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def task_plan_enabled() -> bool:
    return (os.getenv("LANGGRAPH_TASK_PLAN") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _err_text(obs: Dict[str, Any]) -> str:
    parts = [
        str(obs.get("error") or ""),
        str(obs.get("message") or ""),
        str(obs.get("reason") or ""),
    ]
    return " ".join(p for p in parts if p).strip()


def needs_structured_recover(tool_name: str, observation: Dict[str, Any]) -> bool:
    name = (tool_name or "").strip().lower()
    if name not in ("modify", "delete", "copy"):
        return False
    obs = observation if isinstance(observation, dict) else {}
    if obs.get("recovered"):
        return False
    if obs.get("success") and not obs.get("blocked"):
        return False
    if obs.get("blocked") and obs.get("reason") == "grep_required_before_modify":
        return True
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


@dataclass
class RecoverOutcome:
    observation: Dict[str, Any]
    result_context: Dict[str, Any]
    grep_tool_calls: int
    grep_attempts: int
    last_grep_empty: bool
    sse: List[Dict[str, Any]] = field(default_factory=list)
    recovered: bool = False
    ran_grep: bool = False


async def try_structured_recover(
    *,
    engine: Any,
    helpers: Any,
    tool_name: str,
    tool_params: Dict[str, Any],
    observation: Dict[str, Any],
    user_input: str,
    result_context: Dict[str, Any],
    grep_tool_calls: int,
    grep_attempts: int,
    last_grep_empty: bool,
    project_id: Any,
    plan_id: Any,
    user_id: str,
    locale: str,
    ui_context: Optional[Dict[str, Any]],
    client_shell: Optional[Dict[str, Any]],
    pending_diff_context: Optional[List[Dict[str, Any]]],
    round_idx: int = 0,
) -> Optional[RecoverOutcome]:
    """
    modify/delete/copy 失败后：必要时先 grep，再 enrich 并重试一次原工具。
    成功则 observation.recovered=True。
    """
    if not structured_recover_enabled():
        return None
    name = (tool_name or "").strip().lower()
    if not needs_structured_recover(name, observation):
        return None
    if last_grep_empty:
        return None

    from agents.intent_guards import react_context_has_grep_for_mutate
    from agents.langgraph_bridge import enrich_tool_params_for_execute, merge_grep_into_context
    from agents.react_simplified import _grep_observation_empty_lists

    sse: List[Dict[str, Any]] = []
    rc = dict(result_context or {})
    g_calls = int(grep_tool_calls or 0)
    g_attempts = int(grep_attempts or 0)
    g_empty = bool(last_grep_empty)
    ran_grep = False

    has_ctx = react_context_has_grep_for_mutate(rc, None, grep_tool_calls=g_calls)
    if not has_ctx:
        # 强制 grep（与门控 coerce 同源参数）
        try:
            gparams = helpers._unified_prewarm_grep_params_from_user(
                user_input,
                "",
                project_id=project_id,
                plan_id=plan_id,
                ui_context=ui_context if isinstance(ui_context, dict) else None,
            )
        except Exception:
            gparams = {"mode": "locate", "target": "all"}
        if not isinstance(gparams, dict):
            gparams = {"mode": "locate", "target": "all"}
        try:
            from utils.entity_id import inject_ui_record_into_grep_params

            if isinstance(ui_context, dict):
                inject_ui_record_into_grep_params(gparams, ui_context)
            helpers._coerce_grep_target_for_user_intent(
                {"execute": True, "tool": "grep", "params": gparams},
                user_input,
                "",
            )
            helpers._widen_grep_target_to_include_cards_unless_explicit(
                gparams, user_input, ""
            )
            helpers._normalize_grep_plan_scope(gparams)
        except Exception:
            pass
        if project_id is not None:
            gparams["project_id"] = project_id
        gparams = enrich_tool_params_for_execute(
            helpers=helpers,
            tool_name="grep",
            tool_params=gparams,
            user_input=user_input,
            result_context=rc,
            project_id=project_id,
            plan_id=plan_id,
            user_id=user_id,
            locale=locale,
            ui_context=ui_context,
            client_shell=client_shell,
            pending_diff_context=pending_diff_context,
        )
        sse.append(
            {
                "event": "executing",
                "tool": "grep",
                "params": {"keywords": gparams.get("keywords"), "target": gparams.get("target")},
                "reason": "langgraph:structured_recover_grep",
                "index": round_idx,
            }
        )
        grep_obs = await engine._execute_prepared_tool("grep", gparams)
        if not isinstance(grep_obs, dict):
            grep_obs = {"success": False, "raw": grep_obs}
        g_attempts += 1
        ran_grep = True
        empty = (not grep_obs.get("success")) or _grep_observation_empty_lists(grep_obs)
        sse.append(
            {
                "event": "observation",
                "tool": "grep",
                "data": grep_obs,
                "observation": grep_obs,
                "success": bool(grep_obs.get("success")),
                "index": round_idx,
                "summary_nl": "structured recover: grep",
            }
        )
        if empty:
            g_empty = True
            print("[LANGGRAPH] structured_recover grep empty → abort retry", flush=True)
            return RecoverOutcome(
                observation=observation,
                result_context=rc,
                grep_tool_calls=g_calls,
                grep_attempts=g_attempts,
                last_grep_empty=True,
                sse=sse,
                recovered=False,
                ran_grep=True,
            )
        merge_grep_into_context(helpers, grep_obs, gparams, rc)
        g_calls += 1

    # 补参后重试原工具
    retry_params = enrich_tool_params_for_execute(
        helpers=helpers,
        tool_name=name,
        tool_params=dict(tool_params or {}),
        user_input=user_input,
        result_context=rc,
        project_id=project_id,
        plan_id=plan_id,
        user_id=user_id,
        locale=locale,
        ui_context=ui_context,
        client_shell=client_shell,
        pending_diff_context=pending_diff_context,
    )
    if name == "modify" and not (
        retry_params.get("target_id")
        or retry_params.get("card_id")
        or retry_params.get("bug_id")
    ):
        # 仍无 id：让上层走 failure_edge
        print("[LANGGRAPH] structured_recover still missing target_id", flush=True)
        return RecoverOutcome(
            observation=observation,
            result_context=rc,
            grep_tool_calls=g_calls,
            grep_attempts=g_attempts,
            last_grep_empty=g_empty,
            sse=sse,
            recovered=False,
            ran_grep=ran_grep,
        )

    sse.append(
        {
            "event": "executing",
            "tool": name,
            "params": {
                k: retry_params.get(k)
                for k in ("target", "target_id", "modifications")
                if k in retry_params
            },
            "reason": "langgraph:structured_recover_retry",
            "index": round_idx,
        }
    )
    retry_obs = await engine._execute_prepared_tool(name, retry_params)
    if not isinstance(retry_obs, dict):
        retry_obs = {"success": False, "raw": retry_obs}
    if retry_obs.get("success"):
        retry_obs["recovered"] = True
        retry_obs["recovery"] = "structured_grep_enrich_retry"
        print(f"[LANGGRAPH] structured_recover OK tool={name}", flush=True)
        return RecoverOutcome(
            observation=retry_obs,
            result_context=rc,
            grep_tool_calls=g_calls,
            grep_attempts=g_attempts,
            last_grep_empty=g_empty,
            sse=sse,
            recovered=True,
            ran_grep=ran_grep,
        )
    print(
        f"[LANGGRAPH] structured_recover retry still fail: {_err_text(retry_obs)[:200]}",
        flush=True,
    )
    return RecoverOutcome(
        observation=retry_obs if isinstance(retry_obs, dict) else observation,
        result_context=rc,
        grep_tool_calls=g_calls,
        grep_attempts=g_attempts,
        last_grep_empty=g_empty,
        sse=sse,
        recovered=False,
        ran_grep=ran_grep,
    )


def replan_forbid_repeat_hint(
    *,
    tool_name: str,
    tool_params: Optional[Dict[str, Any]],
    base_hint: str,
    locale: str = "zh",
) -> str:
    name = (tool_name or "").strip() or "tool"
    keys = []
    p = tool_params if isinstance(tool_params, dict) else {}
    for k in ("target", "target_id", "title", "keywords", "command"):
        if p.get(k) not in (None, "", []):
            keys.append(f"{k}={p.get(k)!r}")
    fp = ", ".join(keys[:6]) or "(same args)"
    en = (locale or "").lower().startswith("en")
    ban = (
        f" Do NOT repeat `{name}` with identical args ({fp})."
        if en
        else f" 禁止再次用相同参数调用 `{name}`（{fp}）。"
    )
    return ((base_hint or "").rstrip() + ban).strip()


def heuristic_task_plan_steps(user_input: str, *, locale: str = "zh") -> List[Dict[str, Any]]:
    """按意图生成 2–4 步启发式计划（无 LLM）。"""
    text = (user_input or "").strip()
    en = (locale or "").lower().startswith("en")
    low = text.lower()

    def step(i: int, name: str, status: str = "pending") -> Dict[str, Any]:
        return {"id": i, "name": name, "description": name, "status": status}

    # 终端 / 浏览器
    if any(k in text for k in ("终端", "命令", "powershell", "bash", "npm ", "pip ")) or "terminal" in low:
        names = (
            ["Inspect request", "Run local command", "Summarize result"]
            if en
            else ["理解任务", "执行本机命令", "汇报结果"]
        )
    elif (
        any(k in text for k in ("打开", "浏览器", "登录", "点击", "cdp", "网页", "测试", "探测", "访问"))
        or "browser" in low
        or "http://" in low
        or "https://" in low
    ):
        names = (
            ["Open / navigate", "Interact", "Verify outcome"]
            if en
            else ["打开/导航页面", "页面操作", "核对结果"]
        )
    elif any(k in text for k in ("新建", "创建", "添加", "create")):
        names = (
            ["Clarify fields", "Create record", "Confirm preview"]
            if en
            else ["确认字段", "创建记录", "确认预览"]
        )
    elif any(k in text for k in ("删除", "delete", "移除")):
        names = (
            ["Locate target", "Delete / preview", "Confirm"]
            if en
            else ["定位目标", "删除/预览", "确认"]
        )
    elif any(k in text for k in ("改", "修改", "更新", "标记", "resolve", "modify", "status")):
        names = (
            ["Search / locate", "Modify (preview)", "Confirm with user"]
            if en
            else ["检索定位", "修改（预览）", "待确认"]
        )
    elif any(k in text for k in ("查", "搜", "列出", "有哪些", "grep", "search", "list")):
        names = (
            ["Search records", "Summarize hits"]
            if en
            else ["检索记录", "汇总命中"]
        )
    else:
        names = (
            ["Understand goal", "Use tools if needed", "Summarize"]
            if en
            else ["理解目标", "按需调用工具", "汇总"]
        )

    rows = [step(i + 1, n, "in_progress" if i == 0 else "pending") for i, n in enumerate(names)]
    return rows


def advance_task_plan(
    steps: Optional[List[Dict[str, Any]]],
    tool_name: str,
    *,
    success: bool,
) -> List[Dict[str, Any]]:
    """工具完成后推进计划：当前 in_progress → done/failed，下一 pending → in_progress。"""
    rows = [dict(s) for s in (steps or []) if isinstance(s, dict)]
    if not rows:
        return rows
    cur_i = next((i for i, s in enumerate(rows) if s.get("status") == "in_progress"), None)
    if cur_i is None:
        cur_i = next((i for i, s in enumerate(rows) if s.get("status") == "pending"), 0)
    if cur_i is not None and 0 <= cur_i < len(rows):
        rows[cur_i]["status"] = "done" if success else "failed"
        rows[cur_i]["tool"] = tool_name
        nxt = cur_i + 1
        if success and nxt < len(rows) and rows[nxt].get("status") == "pending":
            rows[nxt]["status"] = "in_progress"
    return rows


def plan_init_sse(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "event": "plan_init",
        "steps": steps,
        "mode": "langgraph_heuristic",
        "suppress_plan_ui": True,
    }


def plan_update_sse(steps: List[Dict[str, Any]], reason: str = "") -> Dict[str, Any]:
    return {
        "event": "plan_update",
        "steps": steps,
        "reason": reason or "tool_progress",
        "suppress_plan_ui": True,
    }
