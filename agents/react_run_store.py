"""
ReAct 运行检查点（跨刷新/跨轮对话续作）。

与 react_sse_buffer（同一次 run 的 SSE 续流）互补：
- buffer：连接断开时继续收事件
- checkpoint：用户停止/中断/关 Tab 后，下次发消息时带着上下文接着干
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


def _utcnow():
    return datetime.utcnow()


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _brief_tool_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return None
    out: Dict[str, Any] = {}
    if "success" in result:
        out["success"] = result.get("success")
    for k in ("summary", "message"):
        v = result.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:400]
            break
    return out or None


def snapshot_agent_task_dag(react_request_id: str) -> Optional[Dict[str, Any]]:
    """
    从 agent_tasks 表重建 DAG 快照（节点 + dependencies + 拓扑分层）。
    仅当 REACT_AGENT_TASK_DAG=1 且本轮有落库任务时非空。
    """
    from app import AgentTask

    rid = (react_request_id or "").strip()[:64]
    if not rid:
        return None
    rows = (
        AgentTask.query.filter(AgentTask.session_id == rid)
        .order_by(AgentTask.created_at.asc())
        .all()
    )
    if not rows:
        return None

    nodes: List[Dict[str, Any]] = []
    for r in rows:
        nodes.append(
            {
                "id": r.id,
                "name": r.name,
                "status": r.status,
                "dependencies": list(r.dependencies or []),
                "params": r.params if isinstance(r.params, dict) else {},
                "result_preview": _brief_tool_result(r.result),
                "error": (r.error or "")[:500] if r.error else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
        )
    id_to_deps = {n["id"]: n["dependencies"] for n in nodes}
    all_ids = [n["id"] for n in nodes]
    layers: List[List[str]] = []
    try:
        from agents.agent_task_dag import topological_batches

        layers = topological_batches(all_ids, id_to_deps)
    except Exception:
        layers = [[n["id"]] for n in nodes]

    return {
        "schema_version": 1,
        "react_request_id": rid,
        "nodes": nodes,
        "layers": layers,
        "pending_task_ids": [n["id"] for n in nodes if n["status"] == "pending"],
        "running_task_ids": [n["id"] for n in nodes if n["status"] == "running"],
        "done_count": sum(1 for n in nodes if n["status"] == "done"),
        "failed_count": sum(1 for n in nodes if n["status"] == "failed"),
    }


def enrich_checkpoint_with_agent_dag(
    checkpoint: Dict[str, Any],
    react_request_id: str,
) -> Dict[str, Any]:
    """检查点 v2：合并 UI 扁平字段 + agent_tasks DAG 树（若有）。"""
    ck = dict(checkpoint or {})
    dag = snapshot_agent_task_dag(react_request_id)
    if dag:
        ck["agent_task_dag"] = dag
        ck["version"] = 2
    else:
        ck.setdefault("version", 1)
    return ck


def _is_react_request_still_running(react_request_id: str) -> bool:
    rid = (react_request_id or "").strip()[:64]
    if not rid:
        return False
    try:
        from agents.react_sse_buffer import get_run_status

        st = get_run_status(rid)
        return bool(st.get("running"))
    except Exception:
        return False


def supersede_interrupted_by_react_request(react_request_id: str) -> int:
    """同 react_request_id 的 interrupted 让位于进行中的 SSE 续流。"""
    from app import ReactAgentRun, db

    rid = (react_request_id or "").strip()[:64]
    if not rid:
        return 0
    n = (
        ReactAgentRun.query.filter(
            ReactAgentRun.react_request_id == rid,
            ReactAgentRun.status == "interrupted",
        )
        .update({"status": "superseded", "updated_at": _utcnow()})
    )
    db.session.commit()
    return int(n or 0)


def upsert_interrupted_run(
    *,
    chat_session_id: int,
    project_id: Optional[int],
    user_id: int,
    react_request_id: str,
    user_input: str,
    checkpoint: Dict[str, Any],
    model_name: Optional[str] = None,
) -> Optional[str]:
    """同 Chat Session 仅保留一条 interrupted；后端仍在跑时不写（走 SSE 续流）。"""
    from app import ReactAgentRun, db

    sid = int(chat_session_id)
    rid = (react_request_id or "").strip()[:64]
    if not rid:
        rid = str(uuid.uuid4())

    if _is_react_request_still_running(rid):
        return None

    ReactAgentRun.query.filter(
        ReactAgentRun.chat_session_id == sid,
        ReactAgentRun.status == "interrupted",
    ).update({"status": "superseded", "updated_at": _utcnow()})
    db.session.flush()

    row = ReactAgentRun.query.filter(
        ReactAgentRun.chat_session_id == sid,
        ReactAgentRun.react_request_id == rid,
    ).first()
    if row is None:
        row = ReactAgentRun(
            id=str(uuid.uuid4()),
            chat_session_id=sid,
            project_id=int(project_id) if project_id is not None else None,
            user_id=int(user_id),
            react_request_id=rid,
            status="interrupted",
            user_input=(user_input or "")[:16000],
            model_name=(model_name or "")[:128] or None,
            checkpoint_json=_json_dump(enrich_checkpoint_with_agent_dag(checkpoint or {}, rid)),
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.session.add(row)
    else:
        row.status = "interrupted"
        row.user_input = (user_input or "")[:16000]
        row.model_name = (model_name or "")[:128] or row.model_name
        row.checkpoint_json = _json_dump(
            enrich_checkpoint_with_agent_dag(checkpoint or {}, rid)
        )
        row.updated_at = _utcnow()
        if project_id is not None:
            row.project_id = int(project_id)
    db.session.commit()
    return row.id


def get_resumable_run(
    chat_session_id: int,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    from app import ReactAgentRun

    row = (
        ReactAgentRun.query.filter(
            ReactAgentRun.chat_session_id == int(chat_session_id),
            ReactAgentRun.user_id == int(user_id),
            ReactAgentRun.status == "interrupted",
        )
        .order_by(ReactAgentRun.updated_at.desc())
        .first()
    )
    if row is None:
        return None
    if _is_react_request_still_running(row.react_request_id or ""):
        return None
    try:
        ck = json.loads(row.checkpoint_json or "{}")
    except Exception:
        ck = {}
    return {
        "id": row.id,
        "chat_session_id": row.chat_session_id,
        "project_id": row.project_id,
        "react_request_id": row.react_request_id,
        "status": row.status,
        "user_input": row.user_input,
        "model_name": row.model_name,
        "checkpoint": ck,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def load_run_for_resume(run_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    from app import ReactAgentRun

    row = ReactAgentRun.query.get((run_id or "").strip())
    if row is None or int(row.user_id) != int(user_id):
        return None
    if row.status not in ("interrupted",):
        return None
    try:
        ck = json.loads(row.checkpoint_json or "{}")
    except Exception:
        ck = {}
    return {
        "id": row.id,
        "chat_session_id": row.chat_session_id,
        "project_id": row.project_id,
        "react_request_id": row.react_request_id,
        "user_input": row.user_input,
        "model_name": row.model_name,
        "checkpoint": ck,
    }


def dismiss_interrupted_run(run_id: str, user_id: int) -> bool:
    from app import ReactAgentRun, db

    row = ReactAgentRun.query.get((run_id or "").strip())
    if row is None or int(row.user_id) != int(user_id):
        return False
    if row.status != "interrupted":
        return False
    row.status = "dismissed"
    row.updated_at = _utcnow()
    db.session.commit()
    return True


def mark_run_resumed(run_id: str, user_id: int) -> bool:
    from app import ReactAgentRun, db

    row = ReactAgentRun.query.get((run_id or "").strip())
    if row is None or int(row.user_id) != int(user_id):
        return False
    row.status = "resumed"
    row.updated_at = _utcnow()
    db.session.commit()
    return True


def mark_run_completed_by_request(react_request_id: str) -> None:
    from app import ReactAgentRun, db

    rid = (react_request_id or "").strip()[:64]
    if not rid:
        return
    ReactAgentRun.query.filter(
        ReactAgentRun.react_request_id == rid,
        ReactAgentRun.status == "interrupted",
    ).update({"status": "completed", "updated_at": _utcnow()})
    db.session.commit()


def build_resume_user_input(
    *,
    checkpoint: Dict[str, Any],
    original_user_input: str,
    new_user_input: str,
) -> str:
    """把中断检查点拼进新一轮 user_input，供 ReAct 续作。"""
    ck = checkpoint or {}
    reason = ck.get("interrupt_reason") or "interrupted"
    steps = ck.get("steps") or []
    plan = ck.get("plan_steps") or []
    exec_res = ck.get("execution_results") or []
    pending = ck.get("pending_confirmations") or []

    lines: List[str] = [
        "【续作中断任务】",
        f"中断原因：{reason}",
        f"原始用户目标：{original_user_input or ck.get('original_user_input') or ''}",
    ]
    if plan:
        lines.append(f"计划步骤（共 {len(plan)} 步）：" + "；".join(str(x) for x in plan[:20]))
    if steps:
        brief = []
        for s in steps[:12]:
            if isinstance(s, dict):
                brief.append(f"{s.get('title') or s.get('name') or 'step'}:{s.get('status') or '?'}")
            else:
                brief.append(str(s)[:80])
        lines.append("已完成/进行中步骤：" + "；".join(brief))
    if exec_res:
        lines.append(f"工具执行结果条数：{len(exec_res)}（请在此基础上继续，勿重复已成功操作）")
    if pending:
        lines.append(f"待用户确认项：{len(pending)} 个（优先处理或等待确认）")
    dag = ck.get("agent_task_dag")
    if isinstance(dag, dict) and dag.get("nodes"):
        pend = dag.get("pending_task_ids") or []
        run_ids = dag.get("running_task_ids") or []
        fail_n = int(dag.get("failed_count") or 0)
        done_n = int(dag.get("done_count") or 0)
        lines.append(
            f"并发工具 DAG（react_request_id={dag.get('react_request_id', '')}）："
            f"已完成 {done_n}、失败 {fail_n}、待执行 {len(pend)}、执行中 {len(run_ids)}。"
        )
        if pend or run_ids:
            id_to_name = {
                n.get("id"): n.get("name")
                for n in (dag.get("nodes") or [])
                if isinstance(n, dict)
            }
            hint_ids = (pend + run_ids)[:8]
            names = [f"{id_to_name.get(i, i)}" for i in hint_ids]
            lines.append("须优先续跑的工具任务：" + "、".join(names))
        layers = dag.get("layers")
        if isinstance(layers, list) and layers:
            lines.append(f"DAG 拓扑共 {len(layers)} 层（续作时应从最早未完成层继续，勿重复 done 节点）。")
    lines.append(f"用户本轮指令：{new_user_input}")
    lines.append("请从断点继续执行，避免重复已完成工具调用。")
    return "\n".join(lines)
