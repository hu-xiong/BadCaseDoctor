# -*- coding: utf-8 -*-
"""
LangGraph 与旧 ReAct 领域逻辑桥接：
grep→modify 门控、实体 ID 补全、pending diff、grep 结果合并、modify 沙箱预览参数。
复用 SimplifiedReActEngine 已验证方法，避免再写一套。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from agents.intent_guards import (
    react_context_has_grep_for_mutate,
    react_delete_plan_may_skip_grep,
    react_grep_before_modify_coerce,
    react_require_grep_before_modify,
)
from agents.locale_prompts import (
    react_modify_blocked_after_empty_grep,
    react_unified_modify_requires_grep_first,
)
from utils.entity_id import (
    inject_ui_record_into_grep_params,
    sanitize_tool_entity_ids,
)


def _lazy_helpers(llm, tool_registry):
    """
    借 SimplifiedReActEngine 的领域方法，避免完整 __init__（Windows 控制台 emoji、双份 Skill 加载）。
    """
    from agents.react_simplified import SimplifiedReActEngine

    eng = SimplifiedReActEngine.__new__(SimplifiedReActEngine)
    eng.llm = llm
    eng.tools = tool_registry
    eng.project_id = None
    eng.plan_id = None
    eng.db = None
    eng.user_id = ""
    eng._user_id = ""
    eng._ui_locale = "zh"
    eng._ui_context = None
    eng._client_shell = None
    eng._pending_diff_context = {}
    eng._grep_result_cache = {}
    eng._agent_session_id = None
    eng._chat_session_id = None
    eng._react_stream_user_query = None
    eng._react_stream_user_input = None
    return eng


def prepare_mutate_or_coerce_grep(
    *,
    helpers: Any,
    tool_name: str,
    tool_params: Dict[str, Any],
    user_input: str,
    result_context: Dict[str, Any],
    grep_tool_calls: int,
    project_id: Any,
    plan_id: Any,
    ui_context: Optional[Dict[str, Any]],
    locale: Optional[str],
    grep_attempts: int = 0,
    last_grep_empty: bool = False,
) -> Tuple[str, Dict[str, Any], Optional[str]]:
    """
    modify/delete 前门控。
    返回 (effective_tool, params, block_message)。
    block_message 非空表示阻断（不 coerce 时）。
    """
    name = (tool_name or "").strip().lower()
    params = dict(tool_params or {})
    if name not in ("modify", "delete"):
        return name, params, None

    skip = name == "delete" and react_delete_plan_may_skip_grep(
        params,
        ui_context=ui_context,
        sidebar_plan_id=plan_id,
    )
    if skip:
        return name, params, None
    if not react_require_grep_before_modify():
        return name, params, None
    # 已检索但空结果：禁止再 coerce 成 grep，避免死循环
    if last_grep_empty or (int(grep_attempts or 0) > 0 and int(grep_tool_calls or 0) <= 0):
        return name, params, react_modify_blocked_after_empty_grep(locale)
    if react_context_has_grep_for_mutate(
        result_context, None, grep_tool_calls=grep_tool_calls
    ):
        return name, params, None

    if react_grep_before_modify_coerce():
        gparams = helpers._unified_prewarm_grep_params_from_user(
            user_input,
            "",
            project_id=project_id,
            plan_id=plan_id,
            ui_context=ui_context if isinstance(ui_context, dict) else None,
        )
        if not isinstance(gparams, dict):
            gparams = {"mode": "locate", "target": "all"}
        if isinstance(ui_context, dict):
            inject_ui_record_into_grep_params(gparams, ui_context)
        helpers._coerce_grep_target_for_user_intent(
            {"execute": True, "tool": "grep", "params": gparams},
            user_input,
            "",
        )
        # 与旧 ReAct 执行前一致：未明示实体类型时扩到 all，并去掉侧栏 plan_id 锁死
        helpers._widen_grep_target_to_include_cards_unless_explicit(
            gparams, user_input, ""
        )
        helpers._normalize_grep_plan_scope(gparams)
        if project_id is not None:
            gparams["project_id"] = project_id
        print(
            f"[LANGGRAPH] coerce {name} → grep target={gparams.get('target')!r} "
            f"plan_id={gparams.get('plan_id')!r} kw={gparams.get('keywords')!r} "
            f"(grep_calls={grep_tool_calls})",
            flush=True,
        )
        return "grep", gparams, None

    msg = react_unified_modify_requires_grep_first(locale)
    return name, params, msg


def enrich_tool_params_for_execute(
    *,
    helpers: Any,
    tool_name: str,
    tool_params: Dict[str, Any],
    user_input: str,
    result_context: Dict[str, Any],
    project_id: Any,
    plan_id: Any,
    user_id: str,
    locale: str,
    ui_context: Optional[Dict[str, Any]],
    client_shell: Optional[Dict[str, Any]],
    pending_diff_context: Optional[List[Dict[str, Any]]],
    chat_session_id: Optional[int] = None,
) -> Dict[str, Any]:
    """注入 project/user、实体 ID 补全、modify 默认沙箱预览（confirm=False）。"""
    name = (tool_name or "").strip().lower()
    params = dict(tool_params or {})
    # 会话 project_id 权威：模型常把 plan_id 误填进 project_id，导致 grep 命中后 modify ORM 查不到。
    if project_id is not None:
        prev_pid = params.get("project_id")
        try:
            same = prev_pid is not None and int(prev_pid) == int(project_id)
        except (TypeError, ValueError):
            same = False
        if prev_pid not in (None, "", 0, "0") and not same:
            print(
                f"[LANGGRAPH] overwrite tool project_id {prev_pid!r} → {project_id!r} "
                f"(tool={name})",
                flush=True,
            )
        params["project_id"] = project_id
    if not params.get("userId"):
        params["userId"] = user_id or "system_agent"
    params["ui_locale"] = locale
    if isinstance(ui_context, dict):
        params.setdefault("ui_context", ui_context)
    if isinstance(client_shell, dict):
        params.setdefault("client_shell", client_shell)
        if name == "terminal" and not str(params.get("cwd") or "").strip():
            from agents.client_terminal_resume import merge_client_shell_cwd

            params = merge_client_shell_cwd(params, client_shell)

    if name == "grep":
        if user_input and not params.get("natural_query"):
            params["natural_query"] = user_input
        if isinstance(ui_context, dict):
            inject_ui_record_into_grep_params(params, ui_context)
        helpers._coerce_grep_target_for_user_intent(
            {"execute": True, "tool": "grep", "params": params},
            user_input,
            "",
        )
        helpers._widen_grep_target_to_include_cards_unless_explicit(
            params, user_input, ""
        )
        try:
            helpers._force_grep_card_layer_only_if_requested(params, user_input, "")
        except Exception:
            pass
        helpers._normalize_grep_plan_scope(params)
        return params

    if name == "modify":
        # 默认沙箱预览：未显式 confirm=true 时走 preview
        if "confirm" not in params:
            params["confirm"] = False
        if user_input and not params.get("_resolve_user_input"):
            params["_resolve_user_input"] = user_input
        tgt = params.get("target") or helpers._infer_modify_target(user_input, "")
        params["target"] = tgt
        try:
            helpers._enrich_modify_params_target_ids(
                params,
                result_context,
                tgt,
                log_prefix="[LANGGRAPH] ",
                user_hint=user_input or str(params.get("_resolve_user_input") or ""),
            )
        except Exception as e:
            print(f"[LANGGRAPH] enrich modify target_ids failed: {e}", flush=True)
        # pending diff 合并（多轮预览叠加）
        try:
            helpers._index_pending_context(pending_diff_context)
            tid = params.get("target_id") or params.get("card_id")
            if tid is not None:
                _diff, _mods = helpers._merge_with_pending(
                    tgt, tid, params.get("diff"), params.get("modifications")
                )
                if _mods:
                    params["modifications"] = _mods
                if _diff:
                    params["diff"] = _diff
        except Exception as e:
            print(f"[LANGGRAPH] pending_diff merge skipped: {e}", flush=True)
        sanitize_tool_entity_ids(
            name,
            params,
            grep_result=(result_context or {}).get("grep_result") or {},
            result_context=result_context,
            ui_context=ui_context,
        )
        return params

    if name in ("create", "copy", "delete"):
        if name == "create":
            params.setdefault("target", "bug")
            params.setdefault("fields", {})
            if "confirm" not in params:
                params["confirm"] = False
        if name == "copy":
            params.setdefault("target", "bug")
            gr = (result_context or {}).get("grep_result") or {}
            tt = str(params.get("target") or "bug").strip().lower()
            if not params.get("source_id"):
                key = {
                    "bug": "first_bug_id",
                    "badcase": "first_badcase_id",
                    "testcase": "first_testcase_id",
                    "card": "first_card_id",
                }.get(tt)
                if key and (gr.get(key) or result_context.get(key)):
                    params["source_id"] = gr.get(key) or result_context.get(key)
        if name == "delete":
            gr = (result_context or {}).get("grep_result") or {}
            tt = str(params.get("target") or "bug").strip().lower()
            if tt == "plan" and not params.get("plan_id"):
                fp = gr.get("first_plan_id") or result_context.get("first_plan_id") or plan_id
                if fp is not None:
                    params["plan_id"] = fp
            elif tt == "card" and not params.get("card_id") and not params.get("target_id"):
                cid = gr.get("first_card_id") or result_context.get("first_card_id")
                if cid:
                    params["card_id"] = cid
            elif not params.get("target_id"):
                key = {
                    "bug": "first_bug_id",
                    "badcase": "first_badcase_id",
                    "testcase": "first_testcase_id",
                }.get(tt)
                if key:
                    tid = gr.get(key) or result_context.get(key)
                    if tid:
                        params["target_id"] = tid
        sanitize_tool_entity_ids(
            name,
            params,
            grep_result=(result_context or {}).get("grep_result") or {},
            result_context=result_context,
            ui_context=ui_context,
        )
        return params

    if name == "skill_executor":
        if user_input and not params.get("user_input"):
            params["user_input"] = user_input
        ctx = params.get("context") if isinstance(params.get("context"), dict) else {}
        ctx = dict(ctx)
        ctx.setdefault("grep_result", (result_context or {}).get("grep_result") or {})
        ctx.setdefault("project_id", project_id)
        params["context"] = ctx
        if project_id is not None:
            params.setdefault("project_id", project_id)
        return params

    if name == "cdp":
        try:
            from agents.cdp.login_flow import inject_cdp_login_resume_params

            inject_cdp_login_resume_params(
                params,
                result_context=result_context or {},
                user_input=user_input or "",
                chat_session_id=chat_session_id,
                project_id=project_id,
            )
        except Exception as e:
            print(f"[LANGGRAPH] cdp login resume inject skipped: {e}", flush=True)
        return params

    return params


def merge_grep_into_context(
    helpers: Any,
    observation: Dict[str, Any],
    params: Dict[str, Any],
    result_context: Dict[str, Any],
) -> None:
    try:
        helpers._merge_grep_observation_into_context(observation, params, result_context)
    except Exception as e:
        print(f"[LANGGRAPH] merge grep context failed: {e}", flush=True)


def preview_side_events_from_observation(
    tool_name: str, observation: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    从 modify 预览结果抽出前端可消费的附加事件。
    modify 工具在 confirm=False 时返回 preview_only / sandbox_preview / diff。
    """
    if (tool_name or "").strip().lower() != "modify":
        return []
    if not isinstance(observation, dict):
        return []
    evs: List[Dict[str, Any]] = []
    # 批量行预览
    rows = observation.get("batch_preview_rows") or observation.get("preview_rows")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                evs.append({"event": "batch_preview_row", **row})
    data = observation.get("data") if isinstance(observation.get("data"), dict) else {}
    # 单条预览导航（部分返回挂在 observation 顶层）
    nav = (
        observation.get("navigation")
        or data.get("navigation")
        or (observation.get("sandbox_preview") or {}).get("navigation")
    )
    if nav and not any(e.get("event") == "observation" for e in evs):
        # 已在主 observation 中带全量；这里无需重复。保留 hook 便于扩展。
        _ = nav
    if observation.get("preview_only") or data.get("preview_only"):
        print(
            "[LANGGRAPH] modify sandbox preview ready "
            f"preview_only={observation.get('preview_only') or data.get('preview_only')}",
            flush=True,
        )
    return evs


def progress_line_to_sse(line: str) -> Optional[Dict[str, Any]]:
    """modify progress_queue 文本行 → 引擎事件（兼容 BATCH_PREVIEW_ROW 前缀）。"""
    if not line or not isinstance(line, str):
        return None
    raw = line.strip()
    if not raw:
        return None
    prefix = os.getenv("MODIFY_BATCH_PREVIEW_SSE_PREFIX", "BATCH_PREVIEW_ROW:")
    if raw.startswith(prefix):
        import json

        try:
            payload = json.loads(raw[len(prefix) :])
            if isinstance(payload, dict):
                return {"event": "batch_preview_row", **payload}
        except Exception:
            pass
    return {"event": "reasoning", "content": raw}
