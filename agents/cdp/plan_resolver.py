# -*- coding: utf-8 -*-
"""CDP 测试失败时解析/建议迭代计划归属。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple
import re


def _positive_int(v: Any) -> Optional[int]:
    try:
        n = int(v)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def plan_exists_in_project(db: Any, project_id: int, plan_id: int) -> bool:
    try:
        from models.orm import Plan

        row = (
            db.query(Plan)
            .filter(Plan.id == int(plan_id), Plan.project_id == int(project_id))
            .first()
        )
        return row is not None
    except Exception:
        return False


def default_explore_plan_name(*, prefix: str = "CDP探测测试") -> str:
    return f"{prefix}-{date.today().isoformat()}"


def build_suggested_plan_fields(
    *,
    project_id: int,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    today = date.today()
    return {
        "name": (name or default_explore_plan_name()).strip(),
        "description": "CDP 探测性测试自动创建的迭代计划",
        "status": "active",
        "project_id": int(project_id),
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=14)).isoformat(),
    }


def resolve_plan_for_cdp_issue(
    *,
    project_id: Optional[int],
    plan_id: Optional[Any] = None,
    db: Any = None,
    auto_create_plan: bool = True,
) -> Dict[str, Any]:
    """
    返回 CDP 发现问题时应使用的 plan_id 及是否需要先建迭代计划预览。

    - 侧栏/参数 plan_id 有效 → 直接用于 Bug
    - 无效或未指定且 auto_create_plan → suggested_plan_create
    """
    pid = _positive_int(project_id)
    out: Dict[str, Any] = {
        "project_id": pid,
        "plan_id": None,
        "plan_resolved": False,
        "needs_plan_create": False,
        "suggested_plan_create": None,
    }
    if not pid:
        return out

    explicit = _positive_int(plan_id)
    if explicit and db is not None and plan_exists_in_project(db, pid, explicit):
        out["plan_id"] = explicit
        out["plan_resolved"] = True
        return out

    if not auto_create_plan:
        return out

    fields = build_suggested_plan_fields(project_id=pid)
    out["needs_plan_create"] = True
    out["suggested_plan_create"] = {
        "target": "plan",
        "fields": fields,
        "project_id": pid,
        "confirm": False,
        "natural_query": fields["name"],
    }
    return out


def resolve_cdp_project_plan_ids(
    *,
    project_id: Optional[Any] = None,
    plan_id: Optional[Any] = None,
    engine: Any = None,
    result_context: Optional[Dict[str, Any]] = None,
    observation: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[int], Optional[int]]:
    """从对话上下文 / 引擎 / 页面 URL 解析 project_id、plan_id。"""
    pid = _positive_int(project_id)
    plid = _positive_int(plan_id)

    if isinstance(result_context, dict):
        if not pid:
            pid = _positive_int(result_context.get("project_id"))
        if not plid:
            plid = _positive_int(
                result_context.get("plan_id") or result_context.get("cdp_resolved_plan_id")
            )
        uic = result_context.get("ui_context")
        if isinstance(uic, dict):
            if not pid:
                pid = _positive_int(uic.get("project_id"))
            if not plid:
                plid = _positive_int(uic.get("plan_id"))

    if engine is not None:
        if not pid:
            pid = _positive_int(getattr(engine, "project_id", None))
        if not plid:
            plid = _positive_int(getattr(engine, "plan_id", None))

    if not pid and isinstance(observation, dict):
        page = observation.get("page") if isinstance(observation.get("page"), dict) else {}
        url = str(page.get("url") or observation.get("url") or "")
        m = re.search(r"project-detail/(\d+)", url, re.I)
        if m:
            pid = _positive_int(m.group(1))

    return pid, plid


def cdp_explore_force_new_plan() -> bool:
    import os

    return (os.getenv("CDP_EXPLORE_FORCE_NEW_PLAN", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
