"""
app_services/workflow_notify.py
"""
from __future__ import annotations

import random
import string
import threading

from workflow_notify import (
    build_email_body_cn,
    build_email_subject_cn,
    schedule_workflow_notification,
)

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
    row = Plan.query.get(pid)
    if not row or row.project_id != badcase.project_id:
        return False
    badcase.plan_id = pid
    return True


def _testcase_status_str(testcase):
    s = getattr(testcase, "status", None)
    if s is None:
        return ""
    return s.value if hasattr(s, "value") else str(s)


def _workflow_recipients_from_user_ids(user_ids):
    ids = []
    for x in user_ids or []:
        if x is None:
            continue
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    ids = list({i for i in ids if i > 0})
    if not ids:
        return []
    rows = db.session.query(User.id, User.email, User.name).filter(User.id.in_(ids)).all()
    return [{"user_id": r.id, "email": r.email, "name": r.name} for r in rows]


def _workflow_recipients_badcase(badcase):
    raw = getattr(badcase, "assignee", None)
    if not raw:
        return []
    s = str(raw).strip()
    if not s:
        return []
    ids = []
    try:
        if "," in s:
            for p in s.split(","):
                p = p.strip()
                if p:
                    ids.append(int(p))
        else:
            ids.append(int(s))
    except (ValueError, TypeError):
        return []
    return _workflow_recipients_from_user_ids(ids)


def _workflow_recipients_bug(bug):
    if getattr(bug, "assignee_id", None):
        return _workflow_recipients_from_user_ids([bug.assignee_id])
    return []


def _workflow_recipients_testcase(tc):
    if getattr(tc, "assignee_id", None):
        return _workflow_recipients_from_user_ids([tc.assignee_id])
    return []


def _workflow_merge_creator_if_empty(recipients, creator_id):
    if recipients:
        return recipients
    if creator_id:
        return _workflow_recipients_from_user_ids([creator_id])
    return []


def _workflow_project_name(project_id):
    p = Project.query.get(project_id)
    return p.name if p else str(project_id)


def _persist_workflow_inapp_rows(payload):
    """每位收件人一条站内通知；独立 commit，失败不影响邮件/CLI 异步发送。"""
    recs = payload.get("recipients") or []
    if not recs:
        return
    parts = [
        payload.get("event"),
        payload.get("entity_type"),
        payload.get("entity_id"),
        payload.get("title"),
        payload.get("project_name"),
        payload.get("status"),
        payload.get("previous_status"),
        payload.get("actor_name"),
    ]
    search_blob = " ".join(str(p) for p in parts if p is not None and str(p) != "")
    rows = []
    for r in recs:
        uid = r.get("user_id")
        if uid is None:
            continue
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            continue
        if uid <= 0:
            continue
        rows.append(
            WorkflowInAppNotification(
                user_id=uid,
                actor_id=payload.get("actor_id"),
                actor_name=(payload.get("actor_name") or "")[:120] or None,
                event=str(payload.get("event") or "")[:40],
                entity_type=str(payload.get("entity_type") or "")[:20],
                entity_id=int(payload.get("entity_id") or 0),
                title=(payload.get("title") or "")[:500] or None,
                project_id=payload.get("project_id"),
                project_name=(payload.get("project_name") or "")[:200] or None,
                status=(str(payload.get("status"))[:64] if payload.get("status") is not None else None),
                previous_status=(
                    str(payload.get("previous_status"))[:64]
                    if payload.get("previous_status") is not None
                    else None
                ),
                search_blob=search_blob[:65000] if search_blob else None,
            )
        )
    if not rows:
        return
    db.session.add_all(rows)
    db.session.commit()


def _schedule_grep_work_item_index(entity_type: str, record_id: int, *, sync: bool = False) -> None:
    try:
        from memory.work_item_indexer import schedule_work_item_index

        schedule_work_item_index(entity_type, int(record_id), sync=sync)
    except Exception as e:
        print(f"[GREP-INDEX] API hook skip {entity_type}:{record_id}: {e}")


def _schedule_grep_work_item_delete(entity_type: str, record_id: int) -> None:
    try:
        from memory.work_item_indexer import schedule_work_item_delete

        schedule_work_item_delete(entity_type, int(record_id))
    except Exception as e:
        print(f"[GREP-INDEX] API delete hook skip {entity_type}:{record_id}: {e}")


def _schedule_workflow_notify(
    event,
    entity_type,
    entity_id,
    title,
    project_id,
    project_name,
    status,
    previous_status,
    recipients,
    *,
    actor_id,
    actor_name,
):
    """异步：站内通知落库 + 飞书/钉钉 CLI + 邮件；无收件人则跳过。

    站内通知落库若在请求线程中 commit，会明显拉长接口耗时，因此这里统一后台化。
    actor / project_name 须在请求线程内传入（避免后台线程再查 DB）。
    """
    if not recipients:
        return
    payload = {
        "event": event,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": title or "",
        "status": status,
        "previous_status": previous_status,
        "project_id": project_id,
        "project_name": project_name or str(project_id),
        "actor_id": actor_id,
        "actor_name": actor_name,
        "recipients": recipients,
    }
    payload["email_subject"] = build_email_subject_cn(payload)
    payload["email_body"] = build_email_body_cn(payload)

    # 站内通知落库：后台线程，避免阻塞 HTTP 请求
    try:
        from flask import current_app
        import threading

        app_obj = current_app._get_current_object()

        def _persist_job():
            try:
                with app_obj.app_context():
                    _persist_workflow_inapp_rows(payload)
            except Exception as _pe:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(f"[workflow_notify] 站内通知落库失败: {_pe}")

        threading.Thread(target=_persist_job, daemon=True).start()
    except Exception as _e:
        print(f"[workflow_notify] 站内通知异步调度失败: {_e}")

    # 外部通知（CLI/邮件）本身已异步
    schedule_workflow_notification(payload, send_email_fn=send_email)


# 生成验证码
def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def _model_for_user_collaborator_access(model_cls, entity_id: int, user_id: int):
    """
    单次 SQL：实体 + 项目 owner + 当前用户 ProjectPermission，
    与 has_project_permission(user_id, project_id, 'collaborator') 一致。
    返回 (instance|None, err)，err 为 None | 'not_found' | 'forbidden'。
    """
    row = (
        db.session.query(model_cls, Project.user_id, ProjectPermission.role)
        .join(Project, Project.id == model_cls.project_id)
        .outerjoin(
            ProjectPermission,
            and_(ProjectPermission.project_id == Project.id, ProjectPermission.user_id == user_id),
        )
        .filter(model_cls.id == entity_id)
        .first()
    )
    if not row:
        return None, 'not_found'
    entity, owner_id, role = row
    allowed = owner_id == user_id or (role in ('admin', 'collaborator'))
    if not allowed:
        return None, 'forbidden'
    return entity, None


def _project_for_user_collaborator_access(project_id: int, user_id: int):
    """
    编辑上下文等：一次 SQL 取 Project + 当前用户 ProjectPermission。
    与历史 edit-context 一致：负责人任意；非负责人只要在 project_permission 有记录即可访问。
