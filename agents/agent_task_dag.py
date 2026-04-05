"""
Agent 持久化任务与 DAG 编排（需求：docs/需求文档_Agent任务状态管理与DAG并发调度_MySQL.md）

- REACT_AGENT_TASK_DAG=1：每次工具执行写入 agent_tasks（pending→running→done/failed）
- run_dag_async：同一次请求内多任务，按依赖分层 asyncio.gather 并行
- AGENT_TOOL_MAX_ATTEMPTS：单次工具逻辑失败时的最大尝试次数（默认 2，即失败后自动再试 1 次），上限 5

后台全局调度器留作后续；当前与 ReAct 共用进程与 asyncio，避免跨请求无 Engine 上下文。
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from agents.react_simplified import SimplifiedReActEngine


def use_react_agent_task_dag() -> bool:
    return (os.getenv("REACT_AGENT_TASK_DAG", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def append_tool_task_sse(engine: Any, event: str, **fields: Any) -> None:
    """将工具任务生命周期事件写入引擎缓冲，供主循环 yield（event 为 tool_task_created|running|done|failed）。"""
    if not use_react_agent_task_dag():
        return
    buf = getattr(engine, "_tool_task_event_buffer", None)
    if buf is None:
        engine._tool_task_event_buffer = []
        buf = engine._tool_task_event_buffer
    row: Dict[str, Any] = {"event": event}
    for k, v in fields.items():
        if v is not None:
            row[k] = v
    buf.append(row)


def _utcnow():
    return datetime.utcnow()


def _json_safe_params(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (d or {}).items():
        if k in ("progress_queue", "progress_callback"):
            continue
        try:
            import json

            json.dumps(v, default=str)
            out[k] = v
        except Exception:
            out[k] = str(v)[:2000]
    return out


def topological_batches(
    task_ids: Sequence[str],
    id_to_deps: Dict[str, List[str]],
) -> List[List[str]]:
    ids = list(task_ids)
    pending = set(ids)
    rev: Dict[str, List[str]] = defaultdict(list)
    indeg: Dict[str, int] = {i: 0 for i in ids}
    for tid in ids:
        for d in id_to_deps.get(tid) or []:
            if d in pending:
                rev[d].append(tid)
                indeg[tid] = indeg.get(tid, 0) + 1
    batches: List[List[str]] = []
    q = deque([i for i in ids if indeg[i] == 0])
    while q:
        layer = list(q)
        q.clear()
        batches.append(layer)
        for u in layer:
            for v in rev.get(u, []):
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
    if sum(len(b) for b in batches) != len(ids):
        raise ValueError("agent_task_dag: cycle or invalid dependency in task graph")
    return batches


def create_task_row(
    *,
    name: str,
    params: Optional[Dict[str, Any]],
    dependencies: Optional[List[str]],
    session_id: Optional[str],
) -> str:
    from app import AgentTask, db

    task_id = str(uuid.uuid4())
    deps = [str(x) for x in (dependencies or [])]
    for d in deps:
        if not AgentTask.query.get(d):
            db.session.rollback()
            raise ValueError(f"agent_task_dag: dependency task id not found: {d}")
    row = AgentTask(
        id=task_id,
        name=(name or "")[:100],
        status="pending",
        params=_json_safe_params(params or {}),
        result=None,
        error=None,
        dependencies=deps,
        session_id=(session_id or "")[:64] or None,
        created_at=_utcnow(),
        started_at=None,
        finished_at=None,
    )
    db.session.add(row)
    db.session.commit()
    return task_id


def create_task_batch_with_dep_keys(
    specs: List[Dict[str, Any]],
    session_id: Optional[str],
) -> Dict[str, str]:
    """
    specs 顺序即拓扑序；每项含 key(必填), name, params, dep_keys(可选，引用已出现项的 key)。
    返回 key -> task_id。
    """
    key_to_id: Dict[str, str] = {}
    for sp in specs:
        k = str(sp.get("key") or "").strip()
        if not k:
            raise ValueError("agent_task_dag: spec missing key")
        dep_keys = sp.get("dep_keys") if isinstance(sp.get("dep_keys"), list) else []
        deps_uuid = [key_to_id[str(dk)] for dk in dep_keys]
        tid = create_task_row(
            name=str(sp.get("name") or ""),
            params=sp.get("params") if isinstance(sp.get("params"), dict) else {},
            dependencies=deps_uuid,
            session_id=session_id,
        )
        key_to_id[k] = tid
    return key_to_id


def _load_tasks_map(task_ids: Sequence[str]) -> Dict[str, Any]:
    from app import AgentTask

    rows = AgentTask.query.filter(AgentTask.id.in_(list(task_ids))).all()
    return {r.id: r for r in rows}


def mark_failed_dependency_blocked(task_id: str, failed_dep: str) -> None:
    from app import AgentTask, db

    r = AgentTask.query.get(task_id)
    if not r or r.status != "pending":
        return
    r.status = "failed"
    r.error = (f"依赖任务失败或被阻塞: {failed_dep}")[:65000]
    r.finished_at = _utcnow()
    db.session.commit()


def propagate_failed_dependencies(task_ids: Sequence[str]) -> None:
    idset = set(task_ids)
    rows = _load_tasks_map(task_ids)
    for tid in task_ids:
        row = rows.get(tid)
        if not row or row.status != "pending":
            continue
        for dep in row.dependencies or []:
            if dep not in idset:
                continue
            dr = rows.get(dep)
            if dr and dr.status == "failed":
                mark_failed_dependency_blocked(tid, dep)
                break


def atomic_claim_running(task_id: str) -> bool:
    from app import AgentTask, db

    n = (
        AgentTask.query.filter(
            AgentTask.id == task_id,
            AgentTask.status == "pending",
        ).update(
            {"status": "running", "started_at": _utcnow()},
            synchronize_session=False,
        )
    )
    db.session.commit()
    return n == 1


def mark_done(task_id: str, result: Dict[str, Any]) -> None:
    from app import AgentTask, db

    r = AgentTask.query.get(task_id)
    if not r:
        return
    r.status = "done"
    r.result = result
    r.error = None
    r.finished_at = _utcnow()
    db.session.commit()


def mark_failed(task_id: str, err: str) -> None:
    from app import AgentTask, db

    r = AgentTask.query.get(task_id)
    if not r:
        return
    r.status = "failed"
    r.error = (err or "")[:65000]
    r.finished_at = _utcnow()
    db.session.commit()


def deps_all_done(task_id: str, id_to_row: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    row = id_to_row.get(task_id)
    if not row:
        return False, None
    for dep in row.dependencies or []:
        d = id_to_row.get(dep)
        if not d:
            return False, dep
        if d.status == "failed":
            return False, dep
        if d.status != "done":
            return False, dep
    return True, None


def tool_execution_max_attempts() -> int:
    """工具 observation 中 success=false 时自动重试，直至成功或达到本上限。"""
    try:
        n = int((os.getenv("AGENT_TOOL_MAX_ATTEMPTS") or "2").strip())
    except Exception:
        n = 2
    return max(1, min(n, 5))


async def execute_tool_implementation_with_retry(
    engine: "SimplifiedReActEngine",
    decision: Dict[str, Any],
) -> Dict[str, Any]:
    """调用引擎工具实现；失败则按 AGENT_TOOL_MAX_ATTEMPTS 重试（同一逻辑调用，非新建 DB 行）。"""
    last: Optional[Dict[str, Any]] = None
    n = tool_execution_max_attempts()
    for _ in range(n):
        try:
            res = await engine._execute_tool_implementation(decision)
        except Exception as e:
            res = {"success": False, "error": str(e)}
        last = res if isinstance(res, dict) else {"success": False, "error": "invalid_result"}
        if last.get("success") is not False:
            return last
    return last or {"success": False, "error": "unknown_error"}


def _result_preview(res: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(res, dict):
        return None
    prev: Dict[str, Any] = {"success": res.get("success")}
    s = res.get("summary") or res.get("message") or ""
    if isinstance(s, str) and s.strip():
        prev["summary"] = s.strip()[:800]
    return prev


async def run_persisted_single(
    engine: "SimplifiedReActEngine",
    decision: Dict[str, Any],
    session_id: Optional[str],
) -> Dict[str, Any]:
    from app import AgentTask, app

    tool_name = str(decision.get("tool") or "")
    params = decision.get("params") if isinstance(decision.get("params"), dict) else {}
    with app.app_context():
        task_id = create_task_row(
            name=tool_name,
            params=params,
            dependencies=[],
            session_id=session_id,
        )
        append_tool_task_sse(
            engine,
            "tool_task_created",
            task_id=task_id,
            name=tool_name,
            session_id=session_id,
            dependencies=[],
        )
        atomic_claim_running(task_id)
        row = AgentTask.query.get(task_id)
        append_tool_task_sse(
            engine,
            "tool_task_running",
            task_id=task_id,
            name=tool_name,
            started_at=row.started_at.isoformat() if row and row.started_at else None,
        )
    result = await execute_tool_implementation_with_retry(engine, decision)
    with app.app_context():
        if isinstance(result, dict) and result.get("success") is not False:
            mark_done(task_id, result)
            row = AgentTask.query.get(task_id)
            append_tool_task_sse(
                engine,
                "tool_task_done",
                task_id=task_id,
                name=tool_name,
                finished_at=row.finished_at.isoformat() if row and row.finished_at else None,
                result_preview=_result_preview(result),
            )
        else:
            err_t = str((result or {}).get("error") or "unknown_error")
            mark_failed(task_id, err_t)
            row = AgentTask.query.get(task_id)
            append_tool_task_sse(
                engine,
                "tool_task_failed",
                task_id=task_id,
                name=tool_name,
                error=(row.error if row else err_t)[:4000],
                finished_at=row.finished_at.isoformat() if row and row.finished_at else None,
            )
    return result if isinstance(result, dict) else {"success": False, "error": "invalid_result"}


async def run_dag_async(
    engine: "SimplifiedReActEngine",
    specs: List[Dict[str, Any]],
    session_id: Optional[str],
) -> Dict[str, Dict[str, Any]]:
    """
    specs: { key, name, params?, dep_keys? }，须为拓扑序（dep_keys 仅引用前面已定义的 key）。
    返回 task_id -> 工具 observation 字典。
    """
    from app import app

    if not specs:
        return {}

    with app.app_context():
        key_to_id = create_task_batch_with_dep_keys(specs, session_id)
        all_ids = list(key_to_id.values())
        m_all = _load_tasks_map(all_ids)
        id_to_deps = {
            tid: list(m_all[tid].dependencies or [])
            for tid in all_ids
            if tid in m_all
        }
        propagate_failed_dependencies(all_ids)

    batches = topological_batches(all_ids, id_to_deps)
    results: Dict[str, Dict[str, Any]] = {}

    for layer in batches:

        async def _run_one(tid: str) -> Tuple[str, Dict[str, Any]]:
            with app.app_context():
                m = _load_tasks_map(all_ids)
                row = m.get(tid)
                if not row:
                    return tid, {"success": False, "error": "task_missing"}
                if row.status == "failed":
                    return tid, {"success": False, "error": row.error or "blocked"}
                ok, bad = deps_all_done(tid, m)
                if not ok:
                    if bad and m.get(bad) and m[bad].status == "failed":
                        mark_failed_dependency_blocked(tid, bad)
                    return tid, {"success": False, "error": "dependencies_not_satisfied"}
                if row.status == "done" and row.result is not None:
                    return tid, row.result
                if not atomic_claim_running(tid):
                    m2 = _load_tasks_map(all_ids)
                    r2 = m2.get(tid)
                    if r2 and r2.status == "done" and r2.result is not None:
                        return tid, r2.result
                    return tid, {"success": False, "error": "claim_failed"}

            with app.app_context():
                row = _load_tasks_map(all_ids).get(tid)
            if not row:
                return tid, {"success": False, "error": "task_row_missing"}
            decision = {
                "execute": True,
                "tool": row.name,
                "params": dict(row.params or {}),
            }
            obs = await execute_tool_implementation_with_retry(engine, decision)
            with app.app_context():
                if isinstance(obs, dict) and obs.get("success") is not False:
                    mark_done(tid, obs)
                else:
                    mark_failed(tid, str((obs or {}).get("error") or "error"))
            return tid, obs if isinstance(obs, dict) else {"success": False}

        pairs = await asyncio.gather(*[_run_one(tid) for tid in layer])
        for tid, obs in pairs:
            results[tid] = obs
        with app.app_context():
            propagate_failed_dependencies(all_ids)

    return results
