# -*- coding: utf-8 -*-
"""CDP 工具执行后：证据累积、测试任务、失败自动 create 预览。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.cdp.evidence import get_cdp_evidence_recorder


def _normalize_cdp_action(action: str, observation: Dict[str, Any], params: Dict[str, Any]) -> str:
    act = (action or observation.get("action") or params.get("action") or "").strip().lower()
    # session.create 返回 action=create，与工具入参 action=session 对齐
    if act == "create" or (
        act in ("", "create")
        and str(params.get("sub_action") or "").strip().lower() in ("create", "")
        and (params.get("url") or observation.get("session_id"))
    ):
        if str(params.get("action") or "").strip().lower() == "session" or observation.get(
            "session_id"
        ):
            return "session"
    return act


async def enrich_cdp_observation(
    engine: Any,
    observation: Dict[str, Any],
    *,
    action: str,
    params: Optional[Dict[str, Any]] = None,
    project_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    user_query: Optional[str] = None,
    result_context: Optional[Dict[str, Any]] = None,
    todo: str = "",
    chat_session_id: Optional[int] = None,
    react_request_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not isinstance(observation, dict):
        return observation

    par = params if isinstance(params, dict) else {}
    act = _normalize_cdp_action(action, observation, par)

    # 1) 测试任务：失败不影响后续自动探测
    try:
        from agents.cdp.test_task import (
            ensure_cdp_test_task,
            get_active_run_id,
            record_cdp_test_task_step,
        )

        ensure_cdp_test_task(
            engine,
            user_input=user_query or "",
            todo=todo,
            tool_action=act,
            params=par,
            project_id=project_id,
            plan_id=plan_id,
            result_context=result_context,
            chat_session_id=chat_session_id,
            react_request_id=react_request_id,
        )
        run_id = get_active_run_id(result_context)
        if run_id:
            if act in ("session", "list", "list_sessions"):
                pass
            elif act == "close":
                from agents.cdp.test_task import finalize_cdp_test_task

                final = finalize_cdp_test_task(engine, run_id, result_context=result_context)
                if final:
                    observation["cdp_test_run"] = final
            else:
                record_cdp_test_task_step(
                    engine,
                    run_id,
                    action=act or "cdp",
                    params=par,
                    observation=observation,
                    result_context=result_context,
                    finalize=act in ("explore", "assert"),
                )
                if isinstance(result_context, dict) and result_context.get("cdp_test_run"):
                    observation["cdp_test_run"] = result_context["cdp_test_run"]
    except Exception as ex:
        print(f"[CDP] test_task enrich skipped: {ex}", flush=True)

    # 2) 自动跑用例 / 探测：不依赖 run_id（任务表失败时仍要探测）
    try:
        from agents.cdp.auto_run_testcase import maybe_auto_run_testcases

        observation = await maybe_auto_run_testcases(
            engine,
            observation,
            action=act,
            params=par,
            project_id=project_id,
            plan_id=plan_id,
            result_context=result_context,
        )
    except Exception as ex:
        print(f"[CDP] auto_run_testcase skipped: {ex}", flush=True)

    try:
        from agents.cdp.auto_run_explore import maybe_auto_run_explore

        observation = await maybe_auto_run_explore(
            engine,
            observation,
            action=act,
            params=par,
            project_id=project_id,
            plan_id=plan_id,
            user_query=user_query or "",
            result_context=result_context,
        )
    except Exception as ex:
        print(f"[CDP] auto_run_explore skipped: {ex}", flush=True)

    recorder = get_cdp_evidence_recorder()
    if act in ("explore",) and observation.get("cdp_test_evidence"):
        observation.setdefault("action", act)
    elif act and act not in ("session", "list", "list_sessions", "close"):
        observation = recorder.attach_to_observation(
            observation,
            action=act,
            params=params,
            user_query=user_query,
        )

    if (act == "explore" or observation.get("cdp_auto_explore")) and observation.get(
        "exploration_issues"
    ):
        try:
            from agents.cdp.auto_create import postprocess_cdp_explore_interaction_creates

            observation = await postprocess_cdp_explore_interaction_creates(
                engine,
                observation,
                project_id=project_id,
                plan_id=plan_id or par.get("plan_id"),
                result_context=result_context,
            )
        except Exception as ex:
            print(f"[CDP] explore create postprocess skipped: {ex}", flush=True)

    if observation.get("assertion_failed") or observation.get("has_obvious_issues"):
        try:
            from agents.cdp.auto_create import postprocess_cdp_failure_creates

            observation = await postprocess_cdp_failure_creates(
                engine,
                observation,
                project_id=project_id,
                plan_id=plan_id or par.get("plan_id"),
                result_context=result_context,
            )
        except Exception as ex:
            print(f"[CDP] failure create postprocess skipped: {ex}", flush=True)
    return observation
