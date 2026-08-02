# -*- coding: utf-8 -*-
"""CDP 工具执行后：证据累积、测试任务、失败自动 create 预览。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.cdp.evidence import get_cdp_evidence_recorder


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

    act = (action or observation.get("action") or "").strip().lower()
    par = params if isinstance(params, dict) else {}

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

            # testcase 模式：session/navigate/login 后自动跑用例 steps
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
    except Exception:
        pass

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

    if act == "explore" and observation.get("exploration_issues"):
        from agents.cdp.auto_create import postprocess_cdp_explore_interaction_creates

        observation = await postprocess_cdp_explore_interaction_creates(
            engine,
            observation,
            project_id=project_id,
            plan_id=plan_id or par.get("plan_id"),
            result_context=result_context,
        )

    if observation.get("assertion_failed") or observation.get("has_obvious_issues"):
        from agents.cdp.auto_create import postprocess_cdp_failure_creates

        observation = await postprocess_cdp_failure_creates(
            engine,
            observation,
            project_id=project_id,
            plan_id=plan_id or par.get("plan_id"),
            result_context=result_context,
        )
    return observation
