from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from config import Config
from memory.long_memory_manager import LongMemoryManager


memory_bp = Blueprint("memory", __name__, url_prefix="/api/memory")


def _mgr() -> LongMemoryManager:
    return LongMemoryManager()


@memory_bp.route("/retrieve", methods=["POST"])
@login_required
def retrieve_memory():
    if not getattr(Config, "LONG_MEMORY_ENABLED", False):
        return jsonify({"code": 200, "message": "长期记忆未开启", "data": {"memories": []}})
    data = request.get_json() or {}
    query = data.get("query") or data.get("text") or ""
    project_id = data.get("project_id")
    plan_id = data.get("plan_id")
    types = data.get("types")
    mode = str(data.get("mode") or "vector").strip().lower()
    if types is not None and not isinstance(types, list):
        types = None

    mgr = _mgr()
    if mode == "recent" and project_id is not None:
        ctx = mgr.retrieve_recent_for_project(
            user_id=str(current_user.id),
            project_id=str(project_id),
            plan_id=str(plan_id) if plan_id is not None else None,
            types=types,
        )
    else:
        ctx = mgr.retrieve_context(
            user_id=str(current_user.id),
            query=str(query),
            project_id=str(project_id) if project_id is not None else None,
            plan_id=str(plan_id) if plan_id is not None else None,
            types=types,
        )
    return jsonify(
        {
            "code": 200,
            "message": "成功",
            "data": {
                "memories": ctx.get("long_memory_items") or [],
                "merged": ctx.get("long_memory_text") or "",
            },
        }
    )


@memory_bp.route("/write", methods=["POST"])
@login_required
def write_memory():
    data = request.get_json() or {}
    memory_text = data.get("memory_text") or data.get("text") or ""
    memory_type = data.get("type") or data.get("memory_type") or "fact"
    project_id = data.get("project_id")
    plan_id = data.get("plan_id")
    agent_session_id = data.get("agent_session_id")
    confidence = data.get("confidence", 0.7)

    mgr = _mgr()
    try:
        res = mgr.write_simple(
            user_id=str(current_user.id),
            project_id=str(project_id) if project_id is not None else None,
            plan_id=str(plan_id) if plan_id is not None else None,
            agent_session_id=str(agent_session_id) if agent_session_id is not None else None,
            memory_type=str(memory_type),
            memory_text=str(memory_text),
            source="user_explicit",
            confidence=float(confidence),
        )
        return jsonify({"code": 200, "message": "成功", "data": res})
    except Exception as e:
        return jsonify({"code": 400, "message": str(e), "data": None}), 400


@memory_bp.route("/list", methods=["GET"])
@login_required
def list_memory():
    if not getattr(Config, "LONG_MEMORY_ENABLED", False):
        return jsonify({"code": 200, "message": "长期记忆未开启", "data": {"total": 0, "items": []}})
    project_id = request.args.get("project_id")
    plan_id = request.args.get("plan_id")
    size = request.args.get("size", "50")
    offset = request.args.get("offset", "0")
    mgr = _mgr()
    res = mgr.store.list_items(
        user_id=str(current_user.id),
        project_id=str(project_id) if project_id else None,
        plan_id=str(plan_id) if plan_id else None,
        size=int(size),
        offset=int(offset),
    )
    return jsonify({"code": 200, "message": "成功", "data": res})


@memory_bp.route("/disable", methods=["POST"])
@login_required
def disable_memory():
    data = request.get_json() or {}
    memory_id = str(data.get("id") or "")
    if not memory_id:
        return jsonify({"code": 400, "message": "缺少 id", "data": None}), 400
    mgr = _mgr()
    mgr.store.set_enabled(memory_id=memory_id, enabled=False)
    return jsonify({"code": 200, "message": "成功", "data": {"id": memory_id, "enabled": False}})


@memory_bp.route("/enable", methods=["POST"])
@login_required
def enable_memory():
    data = request.get_json() or {}
    memory_id = str(data.get("id") or "")
    if not memory_id:
        return jsonify({"code": 400, "message": "缺少 id", "data": None}), 400
    mgr = _mgr()
    mgr.store.set_enabled(memory_id=memory_id, enabled=True)
    return jsonify({"code": 200, "message": "成功", "data": {"id": memory_id, "enabled": True}})


@memory_bp.route("/feedback", methods=["POST"])
@login_required
def feedback_memory():
    data = request.get_json() or {}
    memory_id = str(data.get("id") or "")
    feedback = str(data.get("feedback") or "none")
    if not memory_id:
        return jsonify({"code": 400, "message": "缺少 id", "data": None}), 400
    mgr = _mgr()
    mgr.store.set_feedback(memory_id=memory_id, feedback=feedback)
    return jsonify({"code": 200, "message": "成功", "data": {"id": memory_id, "feedback": feedback}})


@memory_bp.route("/delete", methods=["POST"])
@login_required
def delete_memory():
    data = request.get_json() or {}
    memory_id = str(data.get("id") or "")
    if not memory_id:
        return jsonify({"code": 400, "message": "缺少 id", "data": None}), 400
    mgr = _mgr()
    mgr.store.delete(memory_id=memory_id)
    return jsonify({"code": 200, "message": "成功", "data": {"id": memory_id}})

