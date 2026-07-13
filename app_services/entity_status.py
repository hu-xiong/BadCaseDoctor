"""实体 status 字符串与 plan_id 修复。"""
from __future__ import annotations


def _get_models():
    from app import Plan
    return Plan


def _badcase_status_str(badcase):
    s = getattr(badcase, "status", None)
    if s is None:
        return ""
    return s.value if hasattr(s, "value") else str(s)


def _try_repair_badcase_plan_id_from_legacy_plan_string(badcase):
    """plan_id 为空但 plan 列是纯数字计划 id 时写回 plan_id（旧数据或异常 PUT 体）。"""
    if badcase.plan_id is not None:
        return False
    raw = getattr(badcase, "plan", None)
    if raw is None:
        return False
    s = str(raw).strip()
    if not s.isdigit():
        return False
    try:
        pid = int(s)
        if pid <= 0:
            return False
    except ValueError:
        return False
    row = _get_models().query.get(pid)
    if not row or row.project_id != badcase.project_id:
        return False
    badcase.plan_id = pid
    return True


def _testcase_status_str(testcase):
    s = getattr(testcase, "status", None)
    if s is None:
        return ""
