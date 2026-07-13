"""diff_reviews_api（自 app.py 拆出）。"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, redirect, render_template, request, flash, url_for, Response, current_app
from flask_login import login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

diff_reviews_bp = Blueprint("diff_reviews", __name__)


def _app():
    import app as _application
    return _application


@diff_reviews_bp.route('/api/projects/<int:project_id>/diff-reviews/upsert', methods=['POST'])
@login_required
def api_upsert_diff_review(project_id):
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

    t_req = time.perf_counter()
    try:
        t_perm0 = time.perf_counter()
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        t_perm_ms = (time.perf_counter() - t_perm0) * 1000.0
        data = request.get_json() or {}
        target = data.get('target')
        target_id = data.get('target_id')
        if target is None or target_id is None:
            return jsonify({'success': False, 'error': '缺少 target/target_id'}), 400
        t_up0 = time.perf_counter()
        row, suppressed = _upsert_diff_review_state(
            project_id=project_id,
            target=target,
            target_id=target_id,
            plan_id=data.get('plan_id'),
            diff=data.get('diff') or [],
            modifications=data.get('modifications') or {},
            source_message_id=_safe_mysql_int_fk_id(data.get('message_id')),
            source_session_id=_safe_mysql_int_fk_id(data.get('session_id')),
            operator_id=current_user.id,
        )
        t_up_ms = (time.perf_counter() - t_up0) * 1000.0
        t_commit0 = time.perf_counter()
        db.session.commit()
        t_commit_ms = (time.perf_counter() - t_commit0) * 1000.0
        t_total_ms = (time.perf_counter() - t_req) * 1000.0
        if t_total_ms > 200.0 or os.getenv("PERF_LOG", "").strip() == "1":
            print(
                f"[PERF] POST diff-reviews/upsert project={project_id} "
                f"total={t_total_ms:.0f}ms perm={t_perm_ms:.0f}ms upsert={t_up_ms:.0f}ms "
                f"commit={t_commit_ms:.0f}ms target={target!r} id={target_id!r}",
                flush=True,
            )
        ver = _diff_review_version_token(row)
        item = _diff_review_row_to_item(row)
        _broadcast_diff_review(project_id, 'upsert', item)
        return jsonify({
            'success': True,
            'suppressed': bool(suppressed),
            'adopt_version': ver,
            'item': item,
            'record': {
                'id': row.id,
                'project_id': row.project_id,
                'target': row.target,
                'target_id': _json_snowflake_id(row.target_id),
                'plan_id': _json_snowflake_id(row.plan_id),
                'status': row.status,
                'lifecycle_id': row.lifecycle_id,
                'diff_fingerprint': row.diff_fingerprint,
                'updated_at': row.updated_at.isoformat() if row.updated_at else None,
            }
        })
    except Exception as e:
        db.session.rollback()
        print(f"[DIFF-UPSERT] 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@diff_reviews_bp.route('/api/projects/<int:project_id>/diff-reviews/resolve', methods=['POST'])
@login_required
def api_resolve_diff_review(project_id):
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
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        data = request.get_json() or {}
        target = _normalize_diff_target(data.get('target'))
        target_id = data.get('target_id')
        action = (data.get('action') or '').strip().lower()
        if not target or target_id is None or action not in ('confirm', 'reject'):
            return jsonify({'success': False, 'error': '参数错误'}), 400

        rows = (
            DiffReviewState.query
            .filter_by(project_id=project_id, target=target, target_id=int(str(target_id)))
            .order_by(DiffReviewState.updated_at.desc(), DiffReviewState.id.desc())
            .all()
        )
        if not rows:
            return jsonify({'success': True, 'message': '无可更新记录（幂等）'})
        row = rows[0]

        if row.operator_id is not None and row.operator_id != current_user.id:
            return jsonify({'success': False, 'error': '无权处理他人待确认的变更'}), 403

        # 采纳与拒绝均物理删除；采纳主路径在 POST /modify 内已删，此处幂等兼容旧客户端仅调 resolve 的场景
        for r in rows:
            db.session.delete(r)
        db.session.commit()
        _broadcast_diff_review(
            project_id,
            'resolve',
            {'target': target, 'target_id': _json_snowflake_id(int(str(target_id)))},
        )
        return jsonify({'success': True, 'status': 'deleted'})
    except Exception as e:
        db.session.rollback()
        print(f"[DIFF-RESOLVE] 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@diff_reviews_bp.route('/api/projects/<int:project_id>/diff-reviews/stream', methods=['GET'])
@login_required
def api_diff_reviews_stream(project_id):
    """SSE：后端在 upsert/resolve 后主动推送，前端勿轮询 GET pending。"""
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

    if (os.getenv("DIFF_REVIEW_SSE_ENABLED", "0") or "0").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return jsonify({'success': False, 'error': 'diff review SSE disabled'}), 410
    if not has_project_permission(current_user.id, project_id):
        return jsonify({'success': False, 'error': '无权访问此项目'}), 403

    from memory.diff_review_hub import subscribe, unsubscribe

    uid = int(current_user.id)
    q = subscribe(project_id)

    def generate():
        try:
            items = _list_pending_diff_review_items_for_user(project_id, uid)
            yield (
                'event: snapshot\n'
                f'data: {json.dumps({"items": items}, ensure_ascii=False)}\n\n'
            )
            last_ping = time.time()
            while True:
                try:
                    msg = q.get(timeout=1.0)
                except queue.Empty:
                    msg = None
                now = time.time()
                if msg:
                    ev = msg.get('type') or 'message'
                    payload = msg.get('payload')
                    yield (
                        f'event: {ev}\n'
                        f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'
                    )
                    last_ping = now
                elif now - last_ping >= 25.0:
                    yield ': keepalive\n\n'
                    last_ping = now
        except GeneratorExit:
            pass
        finally:
            unsubscribe(project_id, q)

    resp = Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
    )
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp


@diff_reviews_bp.route('/api/projects/<int:project_id>/diff-reviews', methods=['GET'])
@login_required
def api_list_diff_reviews(project_id):
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

    t0 = time.perf_counter()
    try:
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        status_raw = (request.args.get('status') or 'pending').strip().lower()
        status_filter = {s.strip() for s in status_raw.split(',') if s and s.strip()}
        
        # 使用子查询获取每个 (target, target_id) 组合的最新记录，避免全量查询
        t_sql0 = time.perf_counter()
        latest_subq = (
            db.session.query(
                DiffReviewState.target,
                DiffReviewState.target_id,
                db.func.max(DiffReviewState.updated_at).label('max_updated'),
                db.func.max(DiffReviewState.id).label('max_id')
            )
            .filter(DiffReviewState.project_id == project_id)
            .group_by(DiffReviewState.target, DiffReviewState.target_id)
            .subquery()
        )
        
        rows = (
            DiffReviewState.query
            .join(latest_subq,
                  db.and_(
                      DiffReviewState.target == latest_subq.c.target,
                      DiffReviewState.target_id == latest_subq.c.target_id,
                      DiffReviewState.updated_at == latest_subq.c.max_updated,
                      DiffReviewState.id == latest_subq.c.max_id
                  ))
            .filter(DiffReviewState.project_id == project_id)
            .all()
        )
        t_sql1 = time.perf_counter()
        
        result = []
        version_parts = []
        for r in rows:
            if status_filter and r.status not in status_filter:
                continue
            if r.status in ('pending', 'rejected'):
                if r.operator_id is not None and r.operator_id != current_user.id:
                    continue
            version_parts.append(f"{r.target}:{r.target_id}:{r.status}:{_diff_review_version_token(r)}")
            result.append(_diff_review_row_to_item(r))
        version_raw = "|".join(sorted(version_parts))
        version = hashlib.sha1(version_raw.encode("utf-8")).hexdigest()
        inm = (request.headers.get("If-None-Match") or "").strip().strip('"')
        if inm and inm == version:
            resp = Response(status=304)
            resp.headers["ETag"] = f'"{version}"'
            resp.headers["Cache-Control"] = "private, max-age=3"
            return resp
        t_total = (time.perf_counter() - t0) * 1000
        print(f"[PERF] GET /api/projects/{project_id}/diff-reviews sql={((t_sql1-t_sql0)*1000):.0f}ms total={t_total:.0f}ms rows={len(rows)}", flush=True)
        resp = jsonify({'success': True, 'items': result, 'version': version})
        resp.headers["ETag"] = f'"{version}"'
        resp.headers["Cache-Control"] = "private, max-age=3"
        return resp
    except Exception as e:
        print(f"[DIFF-LIST] 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _normalize_chat_message_id(message_id):
    if message_id is None:
        return None
    try:
        return int(message_id)
    except (TypeError, ValueError):
        return None


# chat_message.id / chat_session.id / diff_review_state.source_* 均为 MySQL INT：前端常用 Date.now() 作临时消息 id，会溢出
_MYSQL_SIGNED_INT_MAX = 2147483647


def _safe_mysql_int_fk_id(value):
    """可写入 INT 列的外键类 id；非法或超范围（含 JS 临时大整数）返回 None，避免 INSERT 1264。"""
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n < 1 or n > _MYSQL_SIGNED_INT_MAX:
        return None
    return n


def _grep_nav_item_record_id(item, target_norm):
    """与 grep_tool 导航项一致：按 target 取 record_id / bug_id / source_id / card_id。"""
    if not isinstance(item, dict):
        return None
    t = str(item.get('target') or '').strip().lower().replace('-', '_')
    if t == 'test_case':
        t = 'testcase'
    if t != target_norm:
        return None
    rid = item.get('record_id')
    if rid is None:
        if target_norm == 'bug':
            rid = item.get('bug_id')
        elif target_norm in ('badcase', 'testcase'):
            rid = item.get('source_id')
        elif target_norm == 'card':
            rid = item.get('card_id') if item.get('card_id') is not None else item.get('id')
    try:
        return int(rid) if rid is not None else None
    except (TypeError, ValueError):
        return None


def _patch_grep_nav_items_list(items, target_norm, entity_id_int, new_title):
    if not isinstance(items, list) or not new_title:
        return False
    changed = False
    for it in items:
        if not isinstance(it, dict):
            continue
        rid = _grep_nav_item_record_id(it, target_norm)
        if rid is None or int(entity_id_int) != int(rid):
            continue
        it['title'] = new_title
        if target_norm == 'bug':
            it['bug_title'] = new_title
        changed = True
    return changed


def _patch_navigation_blob_for_title(nav, target_norm, entity_id_int, new_title):
    if not isinstance(nav, dict) or nav.get('type') != 'multiple':
        return False
    return _patch_grep_nav_items_list(nav.get('items'), target_norm, entity_id_int, new_title)


def _patch_steps_blob_for_title(steps, target_norm, entity_id_int, new_title):
    if not isinstance(steps, list):
        return False
    changed = False
    for step in steps:
        if not isinstance(step, dict):
            continue
        gn = step.get('grepNavigation')
        if isinstance(gn, dict) and gn.get('type') == 'multiple':
            if _patch_grep_nav_items_list(gn.get('items'), target_norm, entity_id_int, new_title):
                changed = True
    return changed


def _patch_execution_results_modify_adopted(obj, target_norm, entity_id_int):
    """采纳后：将 execution_results 内对应 modify 块的 confirmation_required 置为 False，避免前端从 ER 恢复成「仍待确认」沙箱。"""
    changed = False
    if isinstance(obj, dict):
        tid = obj.get('target_id') if obj.get('target_id') is not None else obj.get('targetId')
        if tid is not None:
            try:
                if int(tid) == int(entity_id_int):
                    ot = str(obj.get('target') or '').strip().lower().replace('-', '_')
                    if ot == 'test_case':
                        ot = 'testcase'
                    if not ot or ot == target_norm or (target_norm == 'bug' and ot == 'bug'):
                        if obj.get('confirmation_required') is not False:
                            obj['confirmation_required'] = False
                            obj['success'] = True
                            changed = True
            except (TypeError, ValueError):
                pass
        for v in obj.values():
            if _patch_execution_results_modify_adopted(v, target_norm, entity_id_int):
                changed = True
    elif isinstance(obj, list):
        for x in obj:
            if _patch_execution_results_modify_adopted(x, target_norm, entity_id_int):
                changed = True
    return changed


def _patch_execution_results_modify_titles(obj, target_norm, entity_id_int, new_title):
    """递归修正 modify 相关块里 before/after.title，避免清空 modify_navigation 后仍从 execution_results 恢复旧标题。"""
    changed = False
    if isinstance(obj, dict):
        tid = obj.get('target_id') if obj.get('target_id') is not None else obj.get('targetId')
        if tid is not None:
            try:
                if int(tid) == int(entity_id_int):
                    ot = str(obj.get('target') or '').strip().lower().replace('-', '_')
                    if ot == 'test_case':
                        ot = 'testcase'
                    if not ot or ot == target_norm or (target_norm == 'bug' and ot == 'bug'):
                        for side in ('before', 'after'):
                            sub = obj.get(side)
                            if isinstance(sub, dict) and 'title' in sub:
                                sub['title'] = new_title
                                changed = True
            except (TypeError, ValueError):
                pass
        for v in obj.values():
            if _patch_execution_results_modify_titles(v, target_norm, entity_id_int, new_title):
                changed = True
    elif isinstance(obj, list):
        for x in obj:
            if _patch_execution_results_modify_titles(x, target_norm, entity_id_int, new_title):
                changed = True
    return changed


def _patch_chat_message_record_titles(msg, target, target_id, new_title):
    """将本条助手消息上 grep 导航、步骤内 grep、execution_results 中与 target_id 相关的展示标题统一为 new_title。"""
    import json

    tgt = _normalize_diff_target(target)
    if tgt not in ('bug', 'badcase', 'testcase', 'card'):
        tgt = str(target or '').strip().lower().replace('-', '_')
        if tgt == 'test_case':
            tgt = 'testcase'
    try:
        eid = int(str(target_id).strip())
    except (TypeError, ValueError):
        return
    nt = (new_title or '').strip()
    if not nt:
        return
    if msg.navigation:
        try:
            nav = json.loads(msg.navigation) if isinstance(msg.navigation, str) else msg.navigation
            if _patch_navigation_blob_for_title(nav, tgt, eid, nt):
                msg.navigation = json.dumps(nav, ensure_ascii=False)
        except Exception as e:
            print(f"[MODIFY-BG] patch navigation 失败: {e}")
    if msg.steps:
        try:
            steps = json.loads(msg.steps) if isinstance(msg.steps, str) else msg.steps
            if _patch_steps_blob_for_title(steps, tgt, eid, nt):
                msg.steps = json.dumps(steps, ensure_ascii=False)
        except Exception as e:
            print(f"[MODIFY-BG] patch steps 失败: {e}")
    if msg.execution_results:
        try:
            er = (
                json.loads(msg.execution_results)
                if isinstance(msg.execution_results, str)
                else msg.execution_results
            )
            if _patch_execution_results_modify_titles(er, tgt, eid, nt):
                msg.execution_results = json.dumps(er, ensure_ascii=False)
        except Exception as e:
            print(f"[MODIFY-BG] patch execution_results 失败: {e}")


def _finalize_chat_message_after_modify_adopt(message_id, target=None, target_id=None, modifications=None):
    """采纳落库成功后：若有标题变更则同步修正本条消息上的定位/执行结果文案，再清空沙箱预览字段。"""
    mid = _normalize_chat_message_id(message_id)
    if mid is None:
        return
    try:
        db.session.expire_all()
        msg = db.session.get(ChatMessage, mid)
        if not msg:
            print(f"[MODIFY-BG] ChatMessage id={mid} 不存在，跳过 finalize")
            return
        new_title = None
        if isinstance(modifications, dict):
            tv = modifications.get('title')
            if isinstance(tv, str) and tv.strip():
                new_title = tv.strip()
        if target is not None and target_id is not None:
            tgt = _normalize_diff_target(target)
            try:
                eid = int(str(target_id).strip())
            except (TypeError, ValueError):
                eid = None
            if eid is not None and msg.execution_results:
                try:
                    er = (
                        json.loads(msg.execution_results)
                        if isinstance(msg.execution_results, str)
                        else msg.execution_results
                    )
                    if _patch_execution_results_modify_adopted(er, tgt, eid):
                        msg.execution_results = json.dumps(er, ensure_ascii=False)
                except Exception as e:
                    print(f"[MODIFY-BG] patch execution_results adopted 失败 id={mid}: {e}")
        if new_title and target is not None and target_id is not None:
            try:
                _patch_chat_message_record_titles(msg, target, target_id, new_title)
            except Exception as e:
                print(f"[MODIFY-BG] 记录标题同步失败 id={mid}: {e}")
        msg.modify_groups = None
        msg.modify_navigation = None
        msg.delete_navigation = None
        db.session.commit()
        print(f"[MODIFY-BG] 已 finalize 消息 {mid}（标题同步 + 清空 modify_*）")
    except Exception as e:
        print(f"[MODIFY-BG] finalize 消息失败 id={mid}: {e}")
        db.session.rollback()


def _is_append_comment_only_adopt(modifications) -> bool:
    """采纳 payload 是否仅含侧栏追加评论（可同步落库，避免前端刷新竞态）。"""
    if not modifications or not isinstance(modifications, dict):
        return False
    keys = {
        str(k).strip().lower()
        for k in modifications
        if k is not None and not str(k).startswith("_")
    }
    if not keys:
        return False
    allowed = frozenset({"append_comment", "comment", "remark"})
    if not keys.issubset(allowed):
        return False
    return bool(keys.intersection({"append_comment", "comment", "remark"}))


def _run_modify_in_background(
    project_id,
    target,
    target_id,
    modifications,
    message_id,
    db_uri,
    natural_query=None,
    operator_user_id=None,
):
    """后台线程执行采纳落库，使用独立 app_context 和 db.session，避免阻塞主请求"""
    import asyncio
    import json
    with app.app_context():
        try:
            from agents.tools.modify_tool import ModifyTool
            modify_tool = ModifyTool(db.session, database_uri=db_uri)
            result = asyncio.run(modify_tool.execute(
                target=target,
                target_id=int(target_id),
                modifications=modifications,
                project_id=project_id,
                confirm=True,
                natural_query=natural_query,
                message_id=message_id,
                operator_user_id=operator_user_id,
            ))
            if result.get('success') and message_id:
                _finalize_chat_message_after_modify_adopt(
                    message_id,
                    target=target,
                    target_id=int(target_id),
                    modifications=dict(modifications or {}),
                )
        except Exception as e:
            print(f"[MODIFY-BG] 后台采纳失败: {e}")


def _run_modify_batch_in_background(project_id, target, items, message_id, db_uri):
    """同一线程内顺序采纳多条，仅结束时清理消息预览一次；用于前端单次 HTTP 批量采纳。"""
    import asyncio

    with app.app_context():
        from agents.tools.modify_tool import ModifyTool

        modify_tool = ModifyTool(db.session, database_uri=db_uri)
        any_success = False
        succeeded_items = []
        try:
            for it in items:
                tid = int(it["target_id"])
                modifications = dict(it["modifications"])
                nq = it.get("natural_query")
                result = asyncio.run(
                    modify_tool.execute(
                        target=target,
                        target_id=tid,
                        modifications=modifications,
                        project_id=project_id,
                        confirm=True,
                        natural_query=nq,
                    )
                )
                if result.get("success"):
                    any_success = True
                    succeeded_items.append(it)
        except Exception as e:
            print(f"[MODIFY-BG-BATCH] 批量采纳失败: {e}")
        if any_success and message_id:
            mid = _normalize_chat_message_id(message_id)
            if mid is None:
                return
            try:
                db.session.expire_all()
                msg = db.session.get(ChatMessage, mid)
                if not msg:
                    print(f"[MODIFY-BG-BATCH] ChatMessage id={mid} 不存在，跳过 finalize")
                    return
                for it in succeeded_items:
                    mods = dict(it.get("modifications") or {})
                    tv = mods.get("title")
                    if isinstance(tv, str) and tv.strip():
                        try:
                            _patch_chat_message_record_titles(
                                msg, target, int(it["target_id"]), tv.strip()
                            )
                        except Exception as e:
                            print(f"[MODIFY-BG-BATCH] 标题同步失败 tid={it.get('target_id')}: {e}")
                msg.modify_groups = None
                msg.modify_navigation = None
                msg.delete_navigation = None
                db.session.commit()
                print(f"[MODIFY-BG-BATCH] 已 finalize 消息 {mid}（批量标题同步 + 清空 modify_*）")
            except Exception as e:
                print(f"[MODIFY-BG-BATCH] finalize 失败 id={mid}: {e}")
                db.session.rollback()


@diff_reviews_bp.route('/api/projects/<int:project_id>/modify', methods=['POST'])
@login_required
def api_project_modify(project_id):
    """沙箱确认后应用修改 - 采纳时异步落库，避免阻塞"""
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

    import asyncio
    import json
    import threading
    from agents.tools.modify_tool import ModifyTool
    from flask import current_app
    
    try:
        data = request.get_json() or {}
        target = data.get('target', 'bug')
        target_id = data.get('target_id')
        modifications = data.get('modifications', {})
        confirm = data.get('confirm', True)
        message_id = _normalize_chat_message_id(data.get('message_id'))
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
        natural_query_top = data.get("natural_query")
        if isinstance(natural_query_top, str):
            natural_query_top = natural_query_top.strip() or None
        else:
            natural_query_top = None

        # ---------- 批量采纳：单次 HTTP，body.items = [{ target_id, modifications }, ...] ----------
        raw_items = data.get('items')
        if raw_items is not None:
            if not isinstance(raw_items, list) or len(raw_items) == 0:
                return jsonify({"success": False, "error": "items 必须为非空数组"}), 400
            if not confirm:
                return jsonify({"success": False, "error": "批量仅支持采纳(confirm=true)"}), 400
            nt = _normalize_diff_target(target)
            normalized = []
            for it in raw_items:
                if not isinstance(it, dict):
                    return jsonify({"success": False, "error": "items 元素必须为对象"}), 400
                tid = it.get('target_id')
                mods = it.get('modifications')
                if tid is None or not mods:
                    return jsonify({"success": False, "error": "每项需含 target_id 与 modifications"}), 400
                nq_item = it.get("natural_query")
                if isinstance(nq_item, str):
                    nq_item = nq_item.strip() or None
                else:
                    nq_item = None
                if nq_item is None and natural_query_top:
                    nq_item = natural_query_top
                normalized.append(
                    {
                        "target_id": int(tid),
                        "modifications": dict(mods),
                        "natural_query": nq_item,
                    }
                )
            for it in normalized:
                tid = it['target_id']
                pend = (
                    DiffReviewState.query.filter_by(
                        project_id=project_id, target=nt, target_id=tid
                    )
                    .order_by(DiffReviewState.updated_at.desc(), DiffReviewState.id.desc())
                    .first()
                )
                if pend and pend.status == 'pending':
                    if pend.operator_id is not None and pend.operator_id != current_user.id:
                        return jsonify(
                            {"success": False, "error": f"无权采纳他人待确认的变更 (target_id={tid})"}
                        ), 403
            _delete_diff_review_state_rows(
                project_id,
                target,
                [it["target_id"] for it in normalized],
                current_user.id,
            )
            thread = threading.Thread(
                target=_run_modify_batch_in_background,
                args=(project_id, target, normalized, message_id, db_uri),
                daemon=True,
            )
            thread.start()
            return jsonify({
                "success": True,
                "message": "正在批量保存",
                "async": True,
                "batch": True,
                "count": len(normalized),
            })

        if not target_id or not modifications:
            return jsonify({"success": False, "error": "target_id 和 modifications 不能为空"}), 400
        
        if confirm:
            nt = _normalize_diff_target(target)
            tid = int(target_id)
            pend = (
                DiffReviewState.query.filter_by(
                    project_id=project_id, target=nt, target_id=tid
                )
                .order_by(DiffReviewState.updated_at.desc(), DiffReviewState.id.desc())
                .first()
            )
            adopt_ver_token = _diff_review_version_token(pend) if pend else None
            if pend and pend.status == 'pending':
                if pend.operator_id is not None and pend.operator_id != current_user.id:
                    return jsonify({"success": False, "error": "无权采纳他人待确认的变更"}), 403
            _delete_diff_review_state_rows(project_id, target, [tid], current_user.id)
            mods_dict = dict(modifications)
            # 仅追加评论：同步落库并失效测例详情缓存，避免采纳后评论列表仍读旧缓存
            if _is_append_comment_only_adopt(mods_dict):
                modify_tool = ModifyTool(db.session, database_uri=db_uri)

                async def run_comment_adopt():
                    return await modify_tool.execute(
                        target=target,
                        target_id=int(target_id),
                        modifications=mods_dict,
                        project_id=project_id,
                        confirm=True,
                        natural_query=natural_query_top,
                        message_id=message_id,
                        operator_user_id=current_user.id,
                    )

                result = asyncio.run(run_comment_adopt())
                if result.get("success"):
                    if message_id:
                        _finalize_chat_message_after_modify_adopt(
                            message_id,
                            target=target,
                            target_id=int(target_id),
                            modifications=mods_dict,
                        )
                    adopted_entity = result.get("after")
                    if not isinstance(adopted_entity, dict):
                        adopted_entity = None
                    return jsonify({
                        "success": True,
                        "message": "已保存",
                        "async": False,
                        "before": result.get("before"),
                        "after": adopted_entity,
                        "diff": result.get("diff"),
                        "target": nt,
                        "target_id": _json_snowflake_id(tid),
                        "adopted_entity": adopted_entity,
                    })
                return jsonify({
                    "success": False,
                    "error": result.get("error") or "保存评论失败",
                }), 500

            # 其它字段：默认同步落库并返回 adopted_entity；MODIFY_ADOPT_ASYNC=1 时走后台线程
            import os as _os
            _adopt_async = _os.getenv("MODIFY_ADOPT_ASYNC", "").strip().lower() in (
                "1", "true", "yes", "on",
            )
            if _adopt_async:
                thread = threading.Thread(
                    target=_run_modify_in_background,
                    args=(
                        project_id,
                        target,
                        target_id,
                        mods_dict,
                        message_id,
                        db_uri,
                        natural_query_top,
                        current_user.id,
                    ),
                    daemon=True,
                )
                thread.start()
                etag_async = None
                if adopt_ver_token:
                    etag_async = f'W/"{nt}-{tid}-{adopt_ver_token}"'
                return jsonify({
                    "success": True,
                    "message": "正在保存",
                    "async": True,
                    "target": nt,
                    "target_id": _json_snowflake_id(tid),
                    "before": None,
                    "after": None,
                    "diff": None,
                    "adopted_entity": None,
                    "adopted_fields": mods_dict,
                    "adopt_version": adopt_ver_token,
                    "etag": etag_async,
                })

            modify_tool = ModifyTool(db.session, database_uri=db_uri)

            async def run_sync_adopt():
                return await modify_tool.execute(
                    target=target,
                    target_id=int(target_id),
                    modifications=mods_dict,
                    project_id=project_id,
                    confirm=True,
                    natural_query=natural_query_top,
                    message_id=message_id,
                    operator_user_id=current_user.id,
                )

            result = asyncio.run(run_sync_adopt())
            if result.get("success"):
                if message_id:
                    _finalize_chat_message_after_modify_adopt(
                        message_id,
                        target=target,
                        target_id=int(target_id),
                        modifications=mods_dict,
                    )
                adopted_entity = result.get("after")
                if not isinstance(adopted_entity, dict):
                    adopted_entity = None
                adopt_ver_sync = _diff_review_version_token(pend) if pend else None
                if adopted_entity and adopted_entity.get("updated_at"):
                    adopt_ver_sync = (
                        f"{int((adopted_entity.get('lifecycle_id') or 1))}:"
                        f"{adopted_entity.get('updated_at')}"
                    )
                etag = None
                if adopt_ver_sync:
                    etag = f'W/"{nt}-{tid}-{adopt_ver_sync}"'
                elif adopted_entity and adopted_entity.get("updated_at"):
                    etag = f'W/"{nt}-{tid}-{adopted_entity.get("updated_at")}"'
                return jsonify({
                    "success": True,
                    "message": result.get("message") or "已保存",
                    "async": False,
                    "before": result.get("before"),
                    "after": adopted_entity,
                    "diff": result.get("diff"),
                    "target": nt,
                    "target_id": _json_snowflake_id(tid),
                    "adopted_entity": adopted_entity,
                    "adopt_version": adopt_ver_sync,
                    "etag": etag,
                })
            return jsonify({
                "success": False,
                "error": result.get("error") or "保存失败",
            }), 500
        
        # 沙箱预览：同步执行
        modify_tool = ModifyTool(db.session, database_uri=db_uri)
        async def run_modify():
            return await modify_tool.execute(
                target=target, target_id=target_id, modifications=modifications,
                project_id=project_id, confirm=False
            )
        result = asyncio.run(run_modify())
        
        if result.get('success'):
            # 更新数据库中消息的 modify_navigation 字段
            if message_id:
                try:
                    message = ChatMessage.query.get(message_id)
                    if message and message.modify_navigation:
                        modify_nav = json.loads(message.modify_navigation) if isinstance(message.modify_navigation, str) else message.modify_navigation
                        modify_nav['success'] = True
                        modify_nav['confirmation_required'] = False
                        message.modify_navigation = json.dumps(modify_nav, ensure_ascii=False)
                        db.session.commit()
                        print(f"[MODIFY-API] 已更新消息 {message_id} 的 modify_navigation 状态")
                except Exception as e:
                    print(f"[MODIFY-API] 更新消息状态失败: {e}")
            
            return jsonify({
                "success": True,
                "message": result.get('message', '修改成功'),
                "before": result.get('before'),
                "after": result.get('after'),
                "diff": result.get('diff')
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get('error', '修改失败')
            }), 500
            
    except Exception as e:
        print(f"[MODIFY-API] 修改失败: {e}")
        return jsonify({"success": False, "error": f"修改失败: {str(e)}"}), 500

@diff_reviews_bp.route('/api/agent/bugs/search', methods=['POST'])
@login_required
def api_agent_search_bugs():
    """搜索 Bug（Agent）"""
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
        from agents import BugManagementAgent
        
        data = request.get_json()
        project_id = data.get('project_id')
        keyword = data.get('keyword')
        
        agent = BugManagementAgent()
        result = agent.handle(
            userId=str(current_user.id),
            action="search",
            project_id=project_id,
            keyword=keyword
        )
        
        return jsonify(result)
    except Exception as e:
        print(f"搜索 Bug 失败: {e}")
        return jsonify({"error": f"搜索 Bug 失败: {str(e)}"}), 500
