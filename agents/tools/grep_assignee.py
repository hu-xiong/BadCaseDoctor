"""Grep 负责人解析：项目内多 user_id、前缀模糊。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AssigneeResolveResult:
    hint: str
    user_ids: List[int] = field(default_factory=list)
    matched_users: List[Dict[str, Any]] = field(default_factory=list)


def resolve_assignee_user_ids(
    hint: str,
    project_id: Optional[int] = None,
    *,
    fuzzy_prefix: bool = True,
) -> AssigneeResolveResult:
    """
    将负责人 hint 解析为全部匹配的 User.id（重名返回并集，不单取第一个）。
    project_id 暂用于未来限定项目成员；当前全库 User 匹配 + 名称展示。
    """
    hint = (hint or "").strip()
    out = AssigneeResolveResult(hint=hint)
    if not hint:
        return out
    try:
        from app import User
    except Exception as e:
        print(f"[GREP-ASSIGNEE] import User 失败: {e}", flush=True)
        return out

    seen: set = set()
    users: List[Any] = []

    def _add(u) -> None:
        if u and u.id not in seen:
            seen.add(int(u.id))
            users.append(u)

    for u in User.query.filter(User.name == hint).limit(20).all():
        _add(u)
    if not users:
        for u in User.query.filter(User.email.ilike(f"{hint}@%")).limit(20).all():
            _add(u)
    if not users and fuzzy_prefix:
        for u in User.query.filter(User.name.ilike(f"{hint}%")).limit(20).all():
            _add(u)
    if not users:
        for u in User.query.filter(User.name.ilike(f"%{hint}%")).limit(20).all():
            _add(u)

    out.user_ids = [int(u.id) for u in users]
    out.matched_users = [{"id": int(u.id), "name": getattr(u, "name", "") or ""} for u in users]
    if out.user_ids:
        print(
            f"[GREP-ASSIGNEE] hint={hint!r} project_id={project_id} -> ids={out.user_ids}",
            flush=True,
        )
    return out


def resolve_assignee_display(user_id: Optional[int]) -> str:
    if user_id is None:
        return ""
    try:
        from app import User

        u = User.query.get(int(user_id))
        return (getattr(u, "name", None) or "").strip() if u else ""
    except Exception:
        return ""
