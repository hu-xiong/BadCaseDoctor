# -*- coding: utf-8 -*-
"""从系统模板项目克隆副本并关联到指定用户。"""
from __future__ import annotations

from typing import Any, Dict, Optional, Type


def _copy_row(
    model_cls: Type,
    src: Any,
    *,
    exclude: frozenset,
    overrides: Dict[str, Any],
) -> Any:
    from utils.flask_runtime import get_db

    db = get_db()
    data: Dict[str, Any] = {}
    for col in model_cls.__table__.columns:
        key = col.key
        if key in exclude:
            continue
        data[key] = getattr(src, key)
    data.update(overrides)
    row = model_cls(**data)
    db.session.add(row)
    db.session.flush()
    return row


def clone_system_project_for_user(template_project_id: int, user_id: int) -> int:
    """
    以 template 为蓝本创建用户专属项目（元数据 + 计划树 + 卡片/work项）。
    新实体主键由雪花 before_insert 钩子分配；外键按映射表重写。
    """
    from utils.flask_runtime import get_app_module, get_db

    mod = get_app_module()
    db = get_db()
    Project = mod.Project
    Plan = mod.Plan
    Card = mod.Card
    Bug = mod.Bug
    BadCase = mod.BadCase
    TestCase = mod.TestCase
    Team = mod.Team
    TeamMember = mod.TeamMember
    PromptTemplate = mod.PromptTemplate
    ProjectPermission = mod.ProjectPermission

    template = db.session.get(Project, int(template_project_id))
    if not template:
        raise ValueError(f"系统模板项目不存在: {template_project_id}")

    new_project = _copy_row(
        Project,
        template,
        exclude=frozenset({"id", "user_id", "created_at", "is_default", "cloned_from_template_id"}),
        overrides={
            "user_id": int(user_id),
            "is_default": True,
            "cloned_from_template_id": int(template_project_id),
        },
    )
    new_pid = int(new_project.id)

    db.session.add(
        ProjectPermission(
            project_id=new_pid,
            user_id=int(user_id),
            role="admin",
        )
    )

    plan_map: Dict[int, int] = {}
    template_plans = (
        Plan.query.filter_by(project_id=int(template_project_id))
        .order_by(Plan.created_at.asc(), Plan.id.asc())
        .all()
    )
    pending = list(template_plans)
    guard = 0
    while pending and guard < len(template_plans) + 5:
        guard += 1
        next_pending = []
        for p in pending:
            old_parent = getattr(p, "parent_id", None)
            if old_parent is not None and int(old_parent) not in plan_map:
                next_pending.append(p)
                continue
            new_parent = plan_map.get(int(old_parent)) if old_parent is not None else None
            np = _copy_row(
                Plan,
                p,
                exclude=frozenset({"id", "project_id", "parent_id", "creator_id", "assignee_id"}),
                overrides={
                    "project_id": new_pid,
                    "parent_id": new_parent,
                    "creator_id": int(user_id),
                    "assignee_id": int(user_id) if getattr(p, "assignee_id", None) else None,
                },
            )
            plan_map[int(p.id)] = int(np.id)
        pending = next_pending

    card_map: Dict[int, int] = {}
    for c in Card.query.filter_by(project_id=int(template_project_id)).all():
        old_plan = getattr(c, "plan_id", None)
        nc = _copy_row(
            Card,
            c,
            exclude=frozenset({"id", "project_id", "plan_id", "creator_id", "assignee_id"}),
            overrides={
                "project_id": new_pid,
                "plan_id": plan_map.get(int(old_plan)) if old_plan is not None else None,
                "creator_id": int(user_id),
                "assignee_id": int(user_id) if getattr(c, "assignee_id", None) else None,
            },
        )
        card_map[int(c.id)] = int(nc.id)

    bug_map: Dict[int, int] = {}
    for b in Bug.query.filter_by(project_id=int(template_project_id)).all():
        old_plan = getattr(b, "plan_id", None)
        old_card = getattr(b, "card_id", None)
        nb = _copy_row(
            Bug,
            b,
            exclude=frozenset({"id", "project_id", "plan_id", "card_id", "creator_id", "assignee_id"}),
            overrides={
                "project_id": new_pid,
                "plan_id": plan_map.get(int(old_plan)) if old_plan is not None else None,
                "card_id": card_map.get(int(old_card)) if old_card is not None else None,
                "creator_id": int(user_id),
                "assignee_id": int(user_id) if getattr(b, "assignee_id", None) else None,
            },
        )
        bug_map[int(b.id)] = int(nb.id)

    for bc in BadCase.query.filter_by(project_id=int(template_project_id)).all():
        old_plan = getattr(bc, "plan_id", None)
        old_card = getattr(bc, "card_id", None)
        _copy_row(
            BadCase,
            bc,
            exclude=frozenset({"id", "project_id", "plan_id", "card_id", "creator_id"}),
            overrides={
                "project_id": new_pid,
                "plan_id": plan_map.get(int(old_plan)) if old_plan is not None else None,
                "card_id": card_map.get(int(old_card)) if old_card is not None else None,
                "creator_id": int(user_id),
            },
        )

    for tc in TestCase.query.filter_by(project_id=int(template_project_id)).all():
        old_plan = getattr(tc, "plan_id", None)
        old_card = getattr(tc, "card_id", None)
        related = getattr(tc, "related_defects", None)
        new_related = related
        if isinstance(related, list):
            new_related = []
            for x in related:
                if isinstance(x, dict):
                    oid = x.get("id") or x.get("bug_id")
                    if oid is not None and int(oid) in bug_map:
                        item = dict(x)
                        item["id"] = bug_map[int(oid)]
                        if "bug_id" in item:
                            item["bug_id"] = bug_map[int(oid)]
                        new_related.append(item)
                    else:
                        new_related.append(x)
                elif x is not None:
                    try:
                        nid = bug_map.get(int(x))
                        new_related.append(nid if nid is not None else x)
                    except (TypeError, ValueError):
                        new_related.append(x)
                else:
                    new_related.append(x)
        _copy_row(
            TestCase,
            tc,
            exclude=frozenset({"id", "project_id", "plan_id", "card_id", "creator_id", "assignee_id", "related_defects"}),
            overrides={
                "project_id": new_pid,
                "plan_id": plan_map.get(int(old_plan)) if old_plan is not None else None,
                "card_id": card_map.get(int(old_card)) if old_card is not None else None,
                "creator_id": int(user_id),
                "assignee_id": int(user_id) if getattr(tc, "assignee_id", None) else None,
                "related_defects": new_related,
            },
        )

    team_map: Dict[int, int] = {}
    for team in Team.query.filter_by(project_id=int(template_project_id)).all():
        nt = _copy_row(
            Team,
            team,
            exclude=frozenset({"id", "project_id", "creator_id"}),
            overrides={"project_id": new_pid, "creator_id": int(user_id)},
        )
        team_map[int(team.id)] = int(nt.id)

    for tm in TeamMember.query.join(Team, Team.id == TeamMember.team_id).filter(
        Team.project_id == int(template_project_id)
    ).all():
        new_team_id = team_map.get(int(tm.team_id))
        if new_team_id is None:
            continue
        _copy_row(
            TeamMember,
            tm,
            exclude=frozenset({"id", "team_id", "user_id"}),
            overrides={"team_id": new_team_id, "user_id": int(user_id)},
        )

    for pt in PromptTemplate.query.filter_by(project_id=int(template_project_id)).all():
        _copy_row(
            PromptTemplate,
            pt,
            exclude=frozenset({"id", "project_id"}),
            overrides={"project_id": new_pid},
        )

    migrate_user_chat_sessions_from_template(
        new_pid,
        int(user_id),
        template_project_id=int(template_project_id),
    )

    ensure_project_admin_permission(new_pid, int(user_id))

    if not plan_map:
        ensure_default_plan_for_project(new_pid, int(user_id))

    return new_pid


def resolve_user_default_project(user_id: int) -> tuple[int, bool]:
    """
    解析用户工作台默认项目：仅返回 user_id 拥有的项目；无则自模板克隆。
    不返回仅被分享（协作者只读）的项目，避免新账号落在无写权限的公共项目上。
    返回 (project_id, created)。
    """
    from utils.flask_runtime import get_app_module

    mod = get_app_module()
    Project = mod.Project
    uid = int(user_id)

    default_owned = None
    if hasattr(Project, "is_default"):
        try:
            default_owned = (
                Project.query.filter_by(user_id=uid, is_default=True)
                .order_by(Project.created_at.desc())
                .first()
            )
        except Exception:
            default_owned = None
    if default_owned:
        ensure_project_admin_permission(int(default_owned.id), uid)
        return int(default_owned.id), False

    owned = (
        Project.query.filter_by(user_id=uid)
        .order_by(Project.created_at.desc())
        .first()
    )
    if owned:
        ensure_project_admin_permission(int(owned.id), uid)
        return int(owned.id), False

    tpl_id = system_project_template_id()
    if not tpl_id:
        raise ValueError("未配置系统项目模板")

    new_pid = clone_system_project_for_user(int(tpl_id), uid)
    return int(new_pid), True


def ensure_project_admin_permission(project_id: int, user_id: int) -> bool:
    """
    项目 owner 缺失或权限行异常时补齐 admin（幂等）。
    返回 True 表示当前用户为该项目的 owner。
    """
    from utils.flask_runtime import get_app_module, get_db

    mod = get_app_module()
    db = get_db()
    Project = mod.Project
    ProjectPermission = mod.ProjectPermission

    pid = int(project_id)
    uid = int(user_id)
    proj = db.session.get(Project, pid)
    if not proj or proj.user_id is None:
        return False
    if int(proj.user_id) != uid:
        return False

    existing = ProjectPermission.query.filter_by(project_id=pid, user_id=uid).first()
    if not existing:
        db.session.add(
            ProjectPermission(project_id=pid, user_id=uid, role="admin")
        )
        db.session.flush()
    elif (existing.role or "").strip().lower() not in ("admin", "collaborator"):
        existing.role = "admin"
        db.session.flush()
    return True


def ensure_default_plan_for_project(project_id: int, user_id: int) -> tuple[Optional[int], bool]:
    """
    项目下无任何迭代时创建默认「迭代 1」（与 POST /api/projects 行为一致）。
    返回 (plan_id, created)。
    """
    from utils.flask_runtime import get_app_module, get_db

    mod = get_app_module()
    db = get_db()
    Plan = mod.Plan

    pid = int(project_id)
    existing = (
        Plan.query.filter_by(project_id=pid)
        .order_by(Plan.is_default.desc(), Plan.created_at.asc(), Plan.id.asc())
        .first()
    )
    if existing:
        return int(existing.id), False

    default_plan = Plan(
        name="迭代 1",
        description="项目默认迭代",
        status="active",
        project_id=pid,
        creator_id=int(user_id),
        is_default=True,
    )
    db.session.add(default_plan)
    db.session.flush()
    return int(default_plan.id), True


def migrate_user_chat_sessions_from_template(
    target_project_id: int,
    user_id: int,
    *,
    template_project_id: Optional[int] = None,
) -> int:
    """
    将用户在系统模板项目上的聊天会话迁移到其克隆默认项目。
    克隆前若用户曾在模板项目上对话，project_id 仍指向模板，会导致新默认项目查不到历史。
    """
    from utils.flask_runtime import get_app_module, get_db

    mod = get_app_module()
    db = get_db()
    ChatSession = mod.ChatSession
    Project = mod.Project

    tpl_id = template_project_id
    if tpl_id is None:
        proj = db.session.get(Project, int(target_project_id))
        tpl_id = getattr(proj, "cloned_from_template_id", None) if proj else None
    if not tpl_id or int(tpl_id) == int(target_project_id):
        return 0

    moved = (
        ChatSession.query.filter_by(project_id=int(tpl_id), user_id=int(user_id))
        .update({"project_id": int(target_project_id)}, synchronize_session=False)
    )
    if moved:
        db.session.flush()
    return int(moved or 0)


def system_project_template_id() -> Optional[int]:
    import os

    from config import Config

    raw = (os.getenv("SYSTEM_PROJECT_TEMPLATE_ID") or "").strip()
    if not raw:
        raw = str(getattr(Config, "SYSTEM_PROJECT_TEMPLATE_ID", 1) or "1").strip()
    try:
        n = int(raw)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None
