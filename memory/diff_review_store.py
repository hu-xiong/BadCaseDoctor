"""
modify 沙箱预览成功后写入 diff_review_state（账本 B），并广播 diff-review-push。

与 app.api_upsert_diff_review 共用 _upsert_diff_review_state，避免前端点沙箱跳转才落库。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def _env_enabled(name: str, default: str = "1") -> bool:
    return (os.getenv(name, default) or default).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _normalize_field_key(raw_field: Any, target: str) -> str:
    from agents.modify_field_schema import normalize_field_key_for_target

    return normalize_field_key_for_target(raw_field, target)


def _row_field_text(row: Optional[Dict[str, Any]], field_key: str) -> str:
    if not isinstance(row, dict):
        return ""
    v = row.get(field_key)
    if v is None:
        if field_key == "assignee":
            v = row.get("assignee_display") or row.get("assignee_id")
        elif field_key in ("steps_to_reproduce", "reproduction_steps"):
            v = row.get("steps_to_reproduce") or row.get("reproduction_steps")
    if v is None:
        return ""
    return str(v)


def _is_bug_repro_field(field_key: str, raw_label: Any = None) -> bool:
    f = str(field_key or "").lower()
    lab = str(raw_label or "")
    return f in (
        "reproduction_steps",
        "steps_to_reproduce",
        "reproduce_steps",
        "repro_steps",
        "steps",
    ) or "复现步骤" in lab


def build_modifications_payload(
    *,
    target: str,
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
    modifications: Optional[Dict[str, Any]],
    diff: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """与前端 buildModifyDataFromShowModifyDetail 对齐的 {field: {old,new}} 结构（简化版）。"""
    tgt = str(target or "").strip().lower().replace("-", "_")
    if tgt == "test_case":
        tgt = "testcase"
    out: Dict[str, Any] = {}
    before = before if isinstance(before, dict) else {}
    after = after if isinstance(after, dict) else {}

    if isinstance(diff, list) and diff:
        for field_diff in diff:
            if not isinstance(field_diff, dict):
                continue
            raw_field = field_diff.get("field") or field_diff.get("field_label")
            field_key = _normalize_field_key(raw_field, tgt)
            lines = field_diff.get("lines") or []
            old_line = next((l for l in lines if isinstance(l, dict) and l.get("type") == "delete"), None)
            new_line = next((l for l in lines if isinstance(l, dict) and l.get("type") == "add"), None)
            if old_line and new_line:
                old_c = old_line.get("content", "")
                new_c = new_line.get("content", "")
                if field_key == "priority" and (before or after):
                    bo, ao = before.get("priority"), after.get("priority")
                    if bo is not None and str(bo).strip():
                        old_c = bo
                    if ao is not None and str(ao).strip():
                        new_c = ao
                if tgt == "bug" and _is_bug_repro_field(field_key, raw_field):
                    bo = _row_field_text(before, "steps_to_reproduce")
                    ao = _row_field_text(after, "steps_to_reproduce")
                    if bo:
                        old_c = bo
                    if ao:
                        new_c = ao
                if tgt == "badcase" and _is_bug_repro_field(field_key, raw_field):
                    bo = _row_field_text(before, "reproduction_steps")
                    ao = _row_field_text(after, "reproduction_steps")
                    if bo:
                        old_c = bo
                    if ao:
                        new_c = ao
                for snap_key in ("status", "title", "assignee", "case_category"):
                    if field_key == snap_key:
                        if not str(old_c or "").strip():
                            bo = _row_field_text(before, snap_key)
                            if bo:
                                old_c = bo
                        if not str(new_c or "").strip():
                            ao = _row_field_text(after, snap_key)
                            if ao:
                                new_c = ao
                if str(old_c) != str(new_c):
                    out[field_key] = {"old": old_c, "new": new_c}
        if out:
            return out

    mods = modifications if isinstance(modifications, dict) else {}
    for field, value in mods.items():
        if str(field).startswith("_"):
            continue
        fk = _normalize_field_key(field, tgt)
        if isinstance(value, dict) and "new" in value:
            entry = {"old": value.get("old", ""), "new": value.get("new", "")}
        else:
            old_v = _row_field_text(before, fk)
            if tgt == "bug" and _is_bug_repro_field(fk, field) and not old_v:
                old_v = _row_field_text(before, "steps_to_reproduce")
            entry = {"old": old_v, "new": value}
        if str(entry.get("old", "")) != str(entry.get("new", "")):
            out[fk] = entry
    return out


def persist_modify_sandbox_diff_review(
    *,
    project_id: int,
    target: str,
    target_id: Any,
    plan_id: Any = None,
    diff: Optional[List[Dict[str, Any]]] = None,
    modifications: Optional[Dict[str, Any]] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    operator_id: Optional[int] = None,
    source_message_id: Optional[int] = None,
    source_session_id: Optional[int] = None,
) -> bool:
    """沙箱预览成功时 upsert pending 并 broadcast；失败仅打日志，不影响 modify 主流程。"""
    if not _env_enabled("MODIFY_AUTO_DIFF_REVIEW_UPSERT", "1"):
        return False
    try:
        pid = int(project_id)
        tid = int(str(target_id).strip())
    except (TypeError, ValueError):
        return False
    if pid < 1 or tid < 1:
        return False

    mods_payload = build_modifications_payload(
        target=target,
        before=before,
        after=after,
        modifications=modifications,
        diff=diff,
    )
    if not mods_payload and not (diff or []):
        return False

    try:
        from app import (
            _broadcast_diff_review,
            _diff_review_row_to_item,
            _safe_mysql_int_fk_id,
            _upsert_diff_review_state,
            db,
        )

        row, _suppressed = _upsert_diff_review_state(
            project_id=pid,
            target=target,
            target_id=tid,
            plan_id=plan_id,
            diff=diff or [],
            modifications=mods_payload,
            source_message_id=_safe_mysql_int_fk_id(source_message_id),
            source_session_id=_safe_mysql_int_fk_id(source_session_id),
            operator_id=operator_id,
        )
        db.session.commit()
        item = _diff_review_row_to_item(row)
        _broadcast_diff_review(pid, "upsert", item)
        if os.getenv("PERF_LOG", "").strip() == "1":
            print(
                f"[DIFF-UPSERT][auto] project={pid} target={target!r} id={tid} "
                f"fields={list(mods_payload.keys())}",
                flush=True,
            )
        return True
    except Exception as ex:
        try:
            from app import db

            db.session.rollback()
        except Exception:
            pass
        print(f"[DIFF-UPSERT][auto] 失败 project={project_id} target={target} id={target_id}: {ex}", flush=True)
        return False


def persist_modify_preview_observation(
    *,
    project_id: Optional[int],
    preview: Dict[str, Any],
    operator_user_id: Optional[int] = None,
    source_message_id: Optional[int] = None,
    source_session_id: Optional[int] = None,
    plan_id: Optional[Any] = None,
) -> bool:
    """从 modify 单条 preview dict 写入 pending。"""
    if not isinstance(preview, dict):
        return False
    if not preview.get("success") or not preview.get("confirmation_required"):
        return False
    if project_id is None:
        return False
    tgt = preview.get("target")
    tid = preview.get("target_id")
    if tgt is None or tid is None:
        return False
    resolved_plan = plan_id
    if resolved_plan is None:
        resolved_plan = preview.get("plan_id")
        if resolved_plan is None and isinstance(preview.get("before"), dict):
            resolved_plan = preview["before"].get("plan_id")
    return persist_modify_sandbox_diff_review(
        project_id=int(project_id),
        target=str(tgt),
        target_id=tid,
        plan_id=resolved_plan,
        diff=preview.get("diff") or [],
        modifications=preview.get("modifications") or {},
        before=preview.get("before"),
        after=preview.get("after"),
        operator_id=operator_user_id,
        source_message_id=source_message_id,
        source_session_id=source_session_id,
    )
