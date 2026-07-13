# -*- coding: utf-8 -*-
"""CDP 测试任务：一次对话内的浏览器测试 run，持久化步骤与结果。"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .test_intent import detect_cdp_test_intent, extract_testcase_ids_from_context


def cdp_test_task_enabled() -> bool:
    return (os.getenv("CDP_TEST_TASK_ENABLED", "1") or "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _utcnow() -> datetime:
    return datetime.utcnow()


def _resolve_db_session(engine: Any) -> Any:
    """ReAct 引擎本身无 db；从 engine.db / 工具 / Flask session 解析。"""
    db = getattr(engine, "db", None)
    if db is not None:
        return db
    tools = getattr(engine, "tools", None)
    if isinstance(tools, dict):
        for name in ("create", "modify", "grep", "delete", "copy"):
            tool = tools.get(name)
            if tool is not None and getattr(tool, "db", None) is not None:
                return tool.db
    try:
        from flask import has_app_context

        if has_app_context():
            from db_extensions import db as _db

            return _db.session
    except Exception:
        pass
    return None


def _json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    return str(obj)[:2000]


def _load_testcases(
    db: Any,
    *,
    project_id: int,
    plan_id: Optional[int],
    testcase_ids: Optional[List[int]] = None,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    try:
        from models.orm import TestCase
    except ImportError:
        from app import TestCase  # type: ignore

    q = db.query(TestCase).filter(TestCase.project_id == int(project_id))
    if testcase_ids:
        q = q.filter(TestCase.id.in_([int(x) for x in testcase_ids]))
    elif plan_id is not None:
        try:
            q = q.filter(TestCase.plan_id == int(plan_id))
        except (TypeError, ValueError):
            pass
    rows = q.order_by(TestCase.id.asc()).limit(limit).all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        steps = r.steps if isinstance(r.steps, list) else []
        out.append({
            "id": int(r.id),
            "title": str(r.title or ""),
            "plan_id": getattr(r, "plan_id", None),
            "steps": steps,
            "preconditions": str(getattr(r, "preconditions", "") or "")[:500],
        })
    return out


def _task_title(mode: str, user_query: str, testcases: List[Dict[str, Any]]) -> str:
    if testcases:
        if len(testcases) == 1:
            return f"测试：{testcases[0].get('title', '')[:80]}"
        return f"批量测试 {len(testcases)} 条用例"
    q = (user_query or "").strip()[:80]
    if q:
        return f"CDP测试：{q}"
    labels = {"testcase": "迭代计划用例测试", "explore": "探测性测试", "manual": "手动步骤测试"}
    return labels.get(mode, "CDP 浏览器测试")


def open_cdp_test_run(
    *,
    db: Any,
    project_id: Optional[int],
    user_id: Optional[int],
    plan_id: Optional[int] = None,
    chat_session_id: Optional[int] = None,
    react_request_id: Optional[str] = None,
    mode: str = "manual",
    user_query: str = "",
    context: Optional[Dict[str, Any]] = None,
    testcase_ids: Optional[List[int]] = None,
) -> Optional[Dict[str, Any]]:
    if not cdp_test_task_enabled() or not project_id:
        return None
    try:
        from models.orm import CdpTestRun
    except ImportError:
        return None

    ctx = context or {}
    tc_ids = list(testcase_ids or extract_testcase_ids_from_context(ctx))
    effective_plan = plan_id or ctx.get("plan_id") or (ctx.get("grep_result") or {}).get("plan_id")
    try:
        effective_plan = int(effective_plan) if effective_plan is not None else None
    except (TypeError, ValueError):
        effective_plan = None

    testcases: List[Dict[str, Any]] = []
    if mode == "testcase" or tc_ids or (mode != "explore" and effective_plan):
        testcases = _load_testcases(
            db,
            project_id=int(project_id),
            plan_id=effective_plan,
            testcase_ids=tc_ids or None,
        )

    run_id = str(uuid.uuid4())
    spec = {
        "mode": mode,
        "user_query": (user_query or "")[:2000],
        "plan_id": effective_plan,
        "testcase_ids": [t["id"] for t in testcases] or tc_ids,
        "testcases": testcases,
        "manual_steps_hint": (user_query or "")[:3000] if mode == "manual" else "",
    }
    row = CdpTestRun(
        id=run_id,
        chat_session_id=int(chat_session_id) if chat_session_id is not None else None,
        react_request_id=(react_request_id or "")[:64] or None,
        project_id=int(project_id),
        plan_id=effective_plan,
        user_id=int(user_id) if user_id is not None else 0,
        mode=(mode or "manual")[:32],
        title=_task_title(mode, user_query, testcases)[:200],
        status="running",
        spec_json=spec,
        steps_json=[],
        pass_count=0,
        fail_count=0,
    )
    db.add(row)
    db.commit()
    return row.to_dict()


def append_cdp_test_step(
    db: Any,
    run_id: str,
    *,
    action: str,
    params: Optional[Dict[str, Any]],
    observation: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    try:
        from models.orm import CdpTestRun
    except ImportError:
        return None

    row = db.query(CdpTestRun).get(run_id)
    if not row or row.status not in ("running",):
        return None

    steps: List[Dict[str, Any]] = list(row.steps_json or [])
    ok = observation.get("success") is not False and not observation.get("assertion_failed") and not observation.get("has_obvious_issues")
    from agents.cdp.evidence import summarize_step

    summary = observation.get("summary") or summarize_step(action, params, observation)
    step_rec = {
        "index": len(steps) + 1,
        "action": action,
        "success": ok,
        "summary": str(summary or "")[:500],
        "ref": observation.get("ref") or (params or {}).get("ref"),
        "duration_ms": observation.get("duration_ms"),
        "url": (observation.get("page") or {}).get("url") if isinstance(observation.get("page"), dict) else observation.get("url"),
    }
    if observation.get("exploration_issues"):
        step_rec["issues"] = observation.get("exploration_issues")
    steps.append(_json_safe(step_rec))

    row.steps_json = steps
    row.pass_count = sum(1 for s in steps if s.get("success"))
    row.fail_count = sum(1 for s in steps if not s.get("success"))
    sid = observation.get("session_id")
    if sid:
        row.cdp_session_id = str(sid)[:64]
    row.updated_at = _utcnow()
    db.commit()
    payload = row.to_dict()
    payload["last_step"] = step_rec
    return payload


def finalize_cdp_test_run(
    db: Any,
    run_id: str,
    *,
    status_override: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    try:
        from models.orm import CdpTestRun, TestCase
        from models.enums import ExecutionResult
    except ImportError:
        return None

    row = db.query(CdpTestRun).get(run_id)
    if not row:
        return None
    if row.status != "running" and not status_override:
        return row.to_dict()

    steps = list(row.steps_json or [])
    fail = row.fail_count or sum(1 for s in steps if not s.get("success"))
    passed = row.pass_count or sum(1 for s in steps if s.get("success"))

    if status_override:
        status = status_override
    elif fail > 0 and passed > 0:
        status = "partial"
    elif fail > 0:
        status = "failed"
    elif passed > 0:
        status = "passed"
    else:
        status = "passed"

    summaries = [s.get("summary") for s in steps if s.get("summary")]
    row.status = status
    row.summary = (
        f"共 {len(steps)} 步，通过 {passed}，失败 {fail}。"
        + (f" 末步：{summaries[-1][:120]}" if summaries else "")
    )[:2000]
    row.finished_at = _utcnow()
    row.updated_at = _utcnow()
    db.commit()

    spec = row.spec_json if isinstance(row.spec_json, dict) else {}
    tc_ids = spec.get("testcase_ids") or []
    if len(tc_ids) == 1 and user_id:
        try:
            tc = db.query(TestCase).get(int(tc_ids[0]))
            if tc:
                tc.last_executed = _utcnow()
                tc.executed_by = int(user_id)
                tc.execution_result = ExecutionResult.FAIL if fail else ExecutionResult.PASS
                db.commit()
        except Exception:
            pass

    return row.to_dict()


def get_active_run_id(result_context: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(result_context, dict):
        return None
    rid = result_context.get("cdp_test_run_id")
    return str(rid).strip() if rid else None


def buffer_test_task_sse(result_context: Optional[Dict[str, Any]], event: str, **fields: Any) -> None:
    if not isinstance(result_context, dict):
        return
    buf = result_context.setdefault("_cdp_test_task_sse_buffer", [])
    row = {"event": event, **{k: v for k, v in fields.items() if v is not None}}
    buf.append(row)


def pop_test_task_sse_buffer(result_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(result_context, dict):
        return []
    buf = result_context.pop("_cdp_test_task_sse_buffer", [])
    return list(buf) if isinstance(buf, list) else []


def ensure_cdp_test_task(
    engine: Any,
    *,
    user_input: str = "",
    todo: str = "",
    tool_action: str = "",
    params: Optional[Dict[str, Any]] = None,
    project_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    result_context: Optional[Dict[str, Any]] = None,
    chat_session_id: Optional[int] = None,
    react_request_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """若尚未开启且意图命中，创建 cdp_test_run。"""
    if not cdp_test_task_enabled():
        return None
    if get_active_run_id(result_context):
        return None

    intent = detect_cdp_test_intent(
        user_input=user_input,
        todo=todo,
        tool_action=tool_action,
        context=result_context,
        params=params,
    )
    if not intent.get("should_open"):
        return None

    db = _resolve_db_session(engine)
    if db is None:
        return None

    uid = getattr(engine, "user_id", None) or getattr(engine, "_user_id", None)
    try:
        run = open_cdp_test_run(
            db,
            project_id=project_id,
            user_id=int(uid) if uid is not None else None,
            plan_id=plan_id,
            chat_session_id=chat_session_id,
            react_request_id=react_request_id,
            mode=str(intent.get("mode") or "manual"),
            user_query=user_input or todo,
            context=result_context,
        )
    except Exception:
        return None
    if not run:
        return None

    if isinstance(result_context, dict):
        result_context["cdp_test_run_id"] = run["id"]
        result_context["cdp_test_run"] = run

    buffer_test_task_sse(
        result_context,
        "cdp_test_task_opened",
        run_id=run["id"],
        mode=run.get("mode"),
        title=run.get("title"),
        status=run.get("status"),
        testcases=(run.get("spec_json") or {}).get("testcases"),
    )
    return run


def record_cdp_test_task_step(
    engine: Any,
    run_id: str,
    *,
    action: str,
    params: Optional[Dict[str, Any]],
    observation: Dict[str, Any],
    result_context: Optional[Dict[str, Any]] = None,
    finalize: bool = False,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    db = _resolve_db_session(engine)
    if not db or not run_id:
        return None
    try:
        updated = append_cdp_test_step(
            db, run_id, action=action, params=params, observation=observation
        )
    except Exception:
        return None
    if not updated:
        return None

    if isinstance(result_context, dict):
        result_context["cdp_test_run"] = updated

    buffer_test_task_sse(
        result_context,
        "cdp_test_task_step",
        run_id=run_id,
        step=updated.get("last_step"),
        pass_count=updated.get("pass_count"),
        fail_count=updated.get("fail_count"),
        status=updated.get("status"),
    )

    should_finalize = finalize
    if observation.get("assertion_failed") or observation.get("has_obvious_issues"):
        should_finalize = True
    if should_finalize:
        return finalize_cdp_test_task(engine, run_id, result_context=result_context, user_id=user_id)
    return updated


def finalize_cdp_test_task(
    engine: Any,
    run_id: str,
    *,
    result_context: Optional[Dict[str, Any]] = None,
    status_override: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    db = _resolve_db_session(engine)
    if not db or not run_id:
        return None
    uid = user_id or getattr(engine, "user_id", None) or getattr(engine, "_user_id", None)
    try:
        final = finalize_cdp_test_run(
            db, run_id, status_override=status_override, user_id=uid
        )
    except Exception:
        return None
    if not final:
        return None
    if isinstance(result_context, dict):
        result_context["cdp_test_run"] = final
        result_context.pop("cdp_test_run_id", None)
    buffer_test_task_sse(
        result_context,
        "cdp_test_task_done",
        run_id=run_id,
        status=final.get("status"),
        summary=final.get("summary"),
        pass_count=final.get("pass_count"),
        fail_count=final.get("fail_count"),
        steps=final.get("steps_json"),
    )
    return final
