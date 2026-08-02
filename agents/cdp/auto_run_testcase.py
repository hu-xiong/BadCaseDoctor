# -*- coding: utf-8 -*-
"""testcase 模式：session/navigate/login 就绪后自动执行 run_testcase。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def cdp_auto_run_testcase_enabled() -> bool:
    return (os.getenv("CDP_AUTO_RUN_TESTCASE", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _get_cdp_tool(engine: Any) -> Any:
    tools = getattr(engine, "tools", None)
    if tools is None:
        return None
    if hasattr(tools, "get"):
        return tools.get("cdp")
    if isinstance(tools, dict):
        return tools.get("cdp")
    return None


async def maybe_auto_run_testcases(
    engine: Any,
    observation: Dict[str, Any],
    *,
    action: str = "",
    params: Optional[Dict[str, Any]] = None,
    project_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    result_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    当 cdp_test_run.mode=testcase 且已有用例 steps 时，
    在 session/navigate/login 成功后自动跑 run_testcase，并把结果并入 observation。
    """
    if not isinstance(observation, dict):
        return observation
    if not cdp_auto_run_testcase_enabled():
        return observation
    if not isinstance(result_context, dict):
        return observation
    if result_context.get("_cdp_testcase_auto_ran"):
        return observation

    act = (action or observation.get("action") or "").strip().lower()
    if act in ("run_testcase", "run_step", "testcase_run", "testcase_step"):
        result_context["_cdp_testcase_auto_ran"] = True
        return observation

    # 仅在会话/导航/登录就绪后自动跑，避免无页面时误跑
    if act not in ("session", "navigate", "login", "open", "focus"):
        return observation
    if observation.get("success") is False:
        return observation

    run = result_context.get("cdp_test_run")
    if not isinstance(run, dict):
        return observation
    mode = str(run.get("mode") or "").lower()
    if mode != "testcase":
        return observation

    spec = run.get("spec_json") if isinstance(run.get("spec_json"), dict) else {}
    if not spec:
        # to_dict 可能扁平化
        spec = {
            "testcases": run.get("testcases") or [],
            "testcase_ids": run.get("testcase_ids") or [],
        }
    testcases: List[Dict[str, Any]] = list(spec.get("testcases") or [])
    if not testcases:
        return observation

    tool = _get_cdp_tool(engine)
    if tool is None or not hasattr(tool, "execute"):
        observation["cdp_auto_run_skipped"] = "no_cdp_tool"
        return observation

    sid = (
        observation.get("session_id")
        or (params or {}).get("session_id")
        or result_context.get("cdp_session_id")
    )
    if sid:
        result_context["cdp_session_id"] = sid

    result_context["_cdp_testcase_auto_ran"] = True
    batch: List[Dict[str, Any]] = []
    total_pass = total_fail = 0

    from agents.cdp.test_task import record_cdp_test_task_step, get_active_run_id, finalize_cdp_test_task

    run_id = get_active_run_id(result_context)
    owner_kw = {
        "project_id": project_id,
        "plan_id": plan_id,
        "user_id": getattr(engine, "user_id", None) or getattr(engine, "_user_id", None),
        "result_context": result_context,
    }
    if sid:
        owner_kw["session_id"] = sid

    for tc in testcases:
        if not isinstance(tc, dict):
            continue
        steps = tc.get("steps") if isinstance(tc.get("steps"), list) else []
        tc_id = tc.get("id")
        if not steps and tc_id is None:
            continue
        try:
            call_kw = {
                k: v
                for k, v in owner_kw.items()
                if k not in ("session_id", "result_context") and v is not None
            }
            if sid:
                call_kw["session_id"] = sid
            if isinstance(result_context, dict):
                call_kw["result_context"] = result_context
            out = await tool.execute(
                action="run_testcase",
                steps=steps or None,
                testcase_id=tc_id,
                stop_on_fail=True,
                **call_kw,
            )
        except Exception as e:
            out = {"success": False, "error": str(e), "testcase_id": tc_id}

        if isinstance(out, dict) and out.get("session_id"):
            sid = out.get("session_id")
            result_context["cdp_session_id"] = sid
            owner_kw["session_id"] = sid

        batch.append(out if isinstance(out, dict) else {"success": False, "error": "invalid"})
        p = int((out or {}).get("pass_count") or 0)
        f = int((out or {}).get("fail_count") or 0)
        total_pass += p
        total_fail += f

        if run_id and isinstance(out, dict):
            # 把整用例结果记为一步
            try:
                record_cdp_test_task_step(
                    engine,
                    run_id,
                    action="run_testcase",
                    params={"testcase_id": tc_id},
                    observation={
                        **out,
                        "success": bool(out.get("success")),
                        "summary": out.get("summary")
                        or f"testcase#{tc_id} pass={p} fail={f}",
                    },
                    result_context=result_context,
                    finalize=False,
                )
            except Exception:
                pass

        # 失败则停（批量默认）
        if f > 0 or (isinstance(out, dict) and not out.get("success")):
            break

    observation["cdp_auto_run_testcase"] = {
        "ran": True,
        "count": len(batch),
        "pass_count": total_pass,
        "fail_count": total_fail,
        "results": batch,
    }
    observation["summary"] = (
        (observation.get("summary") or "")
        + f" | 自动执行用例：通过 {total_pass}，失败 {total_fail}"
    ).strip(" |")

    if total_fail > 0:
        observation["assertion_failed"] = True
        observation["has_obvious_issues"] = True
        # 附带简要证据供 auto_create
        last = batch[-1] if batch else {}
        observation.setdefault("cdp_test_evidence", {})
        if isinstance(observation["cdp_test_evidence"], dict):
            observation["cdp_test_evidence"].update({
                "test_failed": True,
                "suggested_create_target": "bug",
                "suggested_create_fields": {
                    "title": f"自动用例执行失败（{total_fail} 步失败）",
                    "reproduction_steps": str(last.get("summary") or last)[:2000],
                    "actual_result": str(last)[:1500],
                    "expected_result": "用例 steps 的 expected 全部通过",
                },
            })

    if run_id and (total_fail > 0 or len(batch) >= len(testcases)):
        try:
            final = finalize_cdp_test_task(engine, run_id, result_context=result_context)
            if final:
                observation["cdp_test_run"] = final
        except Exception:
            pass

    return observation
