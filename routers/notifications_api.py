"""notifications_api（自 app.py 拆出）。"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

notifications_bp = Blueprint("notifications", __name__)


def _app():
    import app as _application
    return _application


@login_required
def api_list_workflow_notifications():
    """当前用户站内通知列表（分页 + 关键词 + 类型 + 项目 + 未读）。

    同时接受 GET 与 POST：部分代理/客户端会把带查询的请求发成 POST，此前仅注册 GET 会导致 405。
    分页与筛选参数一律从 query string 读取（axios.post(url, null, { params }) 亦走 query）。"""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("per_page", 20, type=int), 100)
        q = (request.args.get("q") or "").strip()
        entity_type = (request.args.get("entity_type") or "").strip()
        project_id = request.args.get("project_id", type=int)
        unread_only = str(request.args.get("unread_only", "")).lower() in ("1", "true", "yes", "on")

        qry = WorkflowInAppNotification.query.filter(
            WorkflowInAppNotification.user_id == current_user.id
        )
        if project_id is not None and project_id > 0:
            qry = qry.filter(WorkflowInAppNotification.project_id == project_id)
        if entity_type:
            qry = qry.filter(WorkflowInAppNotification.entity_type == entity_type)
        if unread_only:
            qry = qry.filter(WorkflowInAppNotification.read_at.is_(None))
        if q:
            like = f"%{q}%"
            qry = qry.filter(
                or_(
                    WorkflowInAppNotification.title.like(like),
                    WorkflowInAppNotification.project_name.like(like),
                    WorkflowInAppNotification.search_blob.like(like),
                    WorkflowInAppNotification.event.like(like),
                    WorkflowInAppNotification.entity_type.like(like),
                )
            )

        qry = qry.order_by(WorkflowInAppNotification.created_at.desc())
        pagination = qry.paginate(page=page, per_page=per_page, error_out=False)
        items = []
        for row in pagination.items:
            items.append(
                {
                    "id": row.id,
                    "event": row.event,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "title": row.title,
                    "project_id": row.project_id,
                    "project_name": row.project_name,
                    "status": row.status,
                    "previous_status": row.previous_status,
                    "actor_id": row.actor_id,
                    "actor_name": row.actor_name,
                    "read_at": row.read_at.isoformat() if row.read_at else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        return jsonify(
            {
                "success": True,
                "items": items,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "has_next": pagination.has_next,
                    "has_prev": pagination.has_prev,
                },
            }
        )
    except Exception as e:
        print(f"[notifications] list failed: {e}")
        return jsonify({"success": False, "error": "获取通知列表失败"}), 500


@notifications_bp.route("/api/notifications/<int:nid>/read", methods=["POST"])
@login_required
def api_mark_workflow_notification_read(nid):
    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    Card = a.Card
    User = a.User
    Project = a.Project
    ProjectPermission = a.ProjectPermission
    Team = a.Team
    TeamMember = a.TeamMember
    ChatSession = a.ChatSession
    ChatMessage = a.ChatMessage
    CardPlanRelation = a.CardPlanRelation
    CardTypeDefinition = a.CardTypeDefinition
    WorkflowInAppNotification = a.WorkflowInAppNotification
    DiffReviewState = a.DiffReviewState
    AgentTask = a.AgentTask
    Comment = a.Comment
    BugComment = a.BugComment
    TestCaseComment = a.TestCaseComment
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _json_snowflake_ids_in_list = a._json_snowflake_ids_in_list
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _schedule_workflow_notify = a._schedule_workflow_notify
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _cache_invalidate_plans = a._cache_invalidate_plans
    _cache_invalidate_cards = a._cache_invalidate_cards
    _detach_plan_work_items = a._detach_plan_work_items
    _plan_subtree_ids_for_project = a._plan_subtree_ids_for_project
    _parse_query_optional_int64 = a._parse_query_optional_int64
    _parse_query_int_optional = a._parse_query_int_optional
    _coerce_optional_bigint_json = a._coerce_optional_bigint_json
    _badcase_status_str = a._badcase_status_str
    _testcase_status_str = a._testcase_status_str
    _try_repair_badcase_plan_id_from_legacy_plan_string = a._try_repair_badcase_plan_id_from_legacy_plan_string
    ensure_badcase_card_link = a.ensure_badcase_card_link
    repair_card_source_link_if_missing = a.repair_card_source_link_if_missing
    send_email = a.send_email
    generate_verification_code = a.generate_verification_code
    upload_file_to_minio = a.upload_file_to_minio
    allowed_file = a.allowed_file
    compress_image = a.compress_image
    build_upload_image_proxy_url = a.build_upload_image_proxy_url
    get_upload_image_cache_key = a.get_upload_image_cache_key
    get_image_from_cache = a.get_image_from_cache
    set_image_to_cache = a.set_image_to_cache
    read_minio_object_bytes = a.read_minio_object_bytes
    get_minio_client = a.get_minio_client
    check_avatar_access_rate = a.check_avatar_access_rate
    get_image_cache_key = a.get_image_cache_key
    _gzip_large_json_response = a._gzip_large_json_response
    _submit_entity_comment_via_queue = a._submit_entity_comment_via_queue
    _comment_author_name = a._comment_author_name
    _append_bug_comment_row = a._append_bug_comment_row
    _append_badcase_comment_row = a._append_badcase_comment_row
    _append_testcase_comment_row = a._append_testcase_comment_row
    mail = a.mail

    try:
        row = WorkflowInAppNotification.query.get(nid)
        if not row or row.user_id != current_user.id:
            return jsonify({"success": False, "error": "记录不存在"}), 404
        row.read_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        print(f"[notifications] mark read failed: {e}")
        return jsonify({"success": False, "error": "操作失败"}), 500


@notifications_bp.route("/api/notifications/mark-all-read", methods=["POST"])
@login_required
def api_mark_all_workflow_notifications_read():
    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    Card = a.Card
    User = a.User
    Project = a.Project
    ProjectPermission = a.ProjectPermission
    Team = a.Team
    TeamMember = a.TeamMember
    ChatSession = a.ChatSession
    ChatMessage = a.ChatMessage
    CardPlanRelation = a.CardPlanRelation
    CardTypeDefinition = a.CardTypeDefinition
    WorkflowInAppNotification = a.WorkflowInAppNotification
    DiffReviewState = a.DiffReviewState
    AgentTask = a.AgentTask
    Comment = a.Comment
    BugComment = a.BugComment
    TestCaseComment = a.TestCaseComment
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _json_snowflake_ids_in_list = a._json_snowflake_ids_in_list
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _schedule_workflow_notify = a._schedule_workflow_notify
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _cache_invalidate_plans = a._cache_invalidate_plans
    _cache_invalidate_cards = a._cache_invalidate_cards
    _detach_plan_work_items = a._detach_plan_work_items
    _plan_subtree_ids_for_project = a._plan_subtree_ids_for_project
    _parse_query_optional_int64 = a._parse_query_optional_int64
    _parse_query_int_optional = a._parse_query_int_optional
    _coerce_optional_bigint_json = a._coerce_optional_bigint_json
    _badcase_status_str = a._badcase_status_str
    _testcase_status_str = a._testcase_status_str
    _try_repair_badcase_plan_id_from_legacy_plan_string = a._try_repair_badcase_plan_id_from_legacy_plan_string
    ensure_badcase_card_link = a.ensure_badcase_card_link
    repair_card_source_link_if_missing = a.repair_card_source_link_if_missing
    send_email = a.send_email
    generate_verification_code = a.generate_verification_code
    upload_file_to_minio = a.upload_file_to_minio
    allowed_file = a.allowed_file
    compress_image = a.compress_image
    build_upload_image_proxy_url = a.build_upload_image_proxy_url
    get_upload_image_cache_key = a.get_upload_image_cache_key
    get_image_from_cache = a.get_image_from_cache
    set_image_to_cache = a.set_image_to_cache
    read_minio_object_bytes = a.read_minio_object_bytes
    get_minio_client = a.get_minio_client
    check_avatar_access_rate = a.check_avatar_access_rate
    get_image_cache_key = a.get_image_cache_key
    _gzip_large_json_response = a._gzip_large_json_response
    _submit_entity_comment_via_queue = a._submit_entity_comment_via_queue
    _comment_author_name = a._comment_author_name
    _append_bug_comment_row = a._append_bug_comment_row
    _append_badcase_comment_row = a._append_badcase_comment_row
    _append_testcase_comment_row = a._append_testcase_comment_row
    mail = a.mail

    try:
        project_id = request.args.get("project_id", type=int)
        qry = WorkflowInAppNotification.query.filter(
            WorkflowInAppNotification.user_id == current_user.id,
            WorkflowInAppNotification.read_at.is_(None),
        )
        if project_id is not None and project_id > 0:
            qry = qry.filter(WorkflowInAppNotification.project_id == project_id)
        now = datetime.utcnow()
        qry.update({WorkflowInAppNotification.read_at: now}, synchronize_session=False)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        print(f"[notifications] mark all read failed: {e}")
        return jsonify({"success": False, "error": "操作失败"}), 500


# 计划相关API接口
@notifications_bp.route('/api/plans', methods=['POST'])
