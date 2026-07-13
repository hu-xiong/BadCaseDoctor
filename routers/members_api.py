"""members_api（自 app.py 拆出）。"""
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

members_api_bp = Blueprint("members_api", __name__)


def _app():
    import app as _application
    return _application


        if 'status' in data:
            plan.status = data['status']
        if 'priority' in data:
            plan.priority = data['priority']
        if 'start_date' in data:
            plan.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data['start_date'] else None
        if 'end_date' in data:
            plan.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data['end_date'] else None
        if 'progress' in data:
            plan.progress = data['progress']
        if 'assignee_id' in data:
            plan.assignee_id = data['assignee_id']
        
        plan.updated_at = datetime.utcnow()
        db.session.commit()
        _schedule_grep_work_item_index("plan", plan.id)
        
        return jsonify({
            'success': True,
            'message': '计划更新成功',
            'plan': {
                'id': _json_snowflake_id(plan.id),
                'name': plan.name,
                'description': plan.description,
                'status': plan.status,
                'priority': plan.priority,
                'is_default': plan.is_default,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'parent_id': _json_snowflake_id(plan.parent_id),
                'project_id': plan.project_id,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat()
            }
        })
        _redis_cache_invalidate_project(plan.project_id)
        
    except Exception as e:
        db.session.rollback()
        print(f"更新计划失败: {e}")
        return jsonify({'success': False, 'error': '更新计划失败'}), 500

@members_api_bp.route('/api/plans/<int:plan_id>', methods=['DELETE'])
@login_required
def api_delete_plan(plan_id):
    """删除计划"""
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
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 检查是否为默认迭代
        if plan.is_default:
            return jsonify({'success': False, 'error': '默认迭代不能删除'}), 400
        
        # 检查是否有子计划（Plan 模型未定义 children 关系）
        if Plan.query.filter_by(parent_id=plan.id).first() is not None:
            return jsonify({'success': False, 'error': '无法删除包含子计划的计划'}), 400

        detached = _detach_plan_work_items(plan.id)
        if any(detached.values()):
            print(f"[DELETE-PLAN] plan_id={plan.id} 解绑遗留关联: {detached}", flush=True)

        _deleted_plan_project_id = plan.project_id
        db.session.delete(plan)
        db.session.commit()
        _redis_cache_invalidate_project(_deleted_plan_project_id)
        _schedule_grep_work_item_delete("plan", plan_id)
        
        return jsonify({'success': True, 'message': '计划删除成功'})
        
    except Exception as e:
        db.session.rollback()
        print(f"删除计划失败: {e}")
        return jsonify({'success': False, 'error': '删除计划失败'}), 500

@members_api_bp.route('/api/plans/<int:plan_id>/pin', methods=['POST'])
@login_required
def api_pin_plan(plan_id):
    """置顶/取消置顶计划"""
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
        print(f"=== 置顶计划API被调用 ===")
        print(f"计划ID: {plan_id}")
        print(f"当前用户ID: {current_user.id}")
        
        # 获取计划
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有权限'}), 403
        
        # 切换置顶状态
        plan.is_pinned = not plan.is_pinned
        db.session.commit()
        
        action = "置顶" if plan.is_pinned else "取消置顶"
        print(f"计划 {plan.name} {action}成功")
        
        return jsonify({
            'success': True,
            'message': f'计划{action}成功',
            'is_pinned': plan.is_pinned
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"置顶计划失败: {e}")
        return jsonify({'success': False, 'error': '置顶计划失败'}), 500


def _plan_api_status_and_type(plan_status):
    """计划列表 API：把库里任意 status 归一为前端侧边栏可用的 status + status_type。
    旧逻辑只有 status=='active' 才算进行中，MySQL/迁移后常见 draft、pending、空串等，会被标成 unplanned，
    导致「进行中计划」整组为空；归档类状态统一归为 archived。"""
    if plan_status is None:
        return 'active', 'in_progress'
    s = str(plan_status).strip()
    if not s:
        return 'active', 'in_progress'
    sl = s.lower()
    archived = frozenset(
        {'archived', 'completed', 'finished', 'done', 'closed', 'cancelled', 'canceled'}
    )
    if sl in archived:
        return s, 'archived'
    ongoing = frozenset(
        {
            'active',
            'in_progress',
            'running',
            'open',
            'doing',
            'draft',
            'pending',
            'new',
            'todo',
            'processing',
            'ongoing',
        }
    )
    if sl in ongoing:
        return s, 'in_progress'
    if s in ('进行中', '未归档'):
        return 'active', 'in_progress'
    # 未知字符串：默认归为进行中，避免侧边栏空白（可按需在后端数据修正）
    return s, 'in_progress'


@members_api_bp.route('/api/projects/<int:project_id>/plans', methods=['GET'])
@login_required
def api_get_project_plans(project_id):
    """获取项目的计划树"""
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
        t_total0 = time.perf_counter()
        # 优先查 Redis 缓存（跨进程共享，10s TTL）
        redis_hit, redis_cached = _redis_cache_get(f'plans:{project_id}')
        if redis_hit:
            print(
                f"[PERF] GET /api/projects/{project_id}/plans redis_hit total={(time.perf_counter()-t_total0)*1000:.1f}ms",
                flush=True,
            )
            return jsonify(redis_cached)
        # 回退到内存缓存
        cache_hit, cached = _cache_get(('plans', project_id), ttl_s=2.0)
        if cache_hit:
            print(
                f"[PERF] GET /api/projects/{project_id}/plans cache_hit total={(time.perf_counter()-t_total0)*1000:.1f}ms",
                flush=True,
            )
            return jsonify(cached)

        # 检查项目权限
        t0 = time.perf_counter()
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        t_perm = (time.perf_counter() - t0) * 1000

        # 计划 + 两种 count 用 1 次查询拿齐（避免 plans + 2 次 group by）
        t0 = time.perf_counter()
        from sqlalchemy import func
        bc_sub = (
            db.session.query(BadCase.plan_id.label('plan_id'), func.count(BadCase.id).label('badcase_count'))
            .group_by(BadCase.plan_id)
            .subquery()
        )
        bug_sub = (
            db.session.query(Bug.plan_id.label('plan_id'), func.count(Bug.id).label('bug_count'))
            .group_by(Bug.plan_id)
            .subquery()
        )
        tc_sub = (
            db.session.query(TestCase.plan_id.label('plan_id'), func.count(TestCase.id).label('test_case_count'))
            .filter(TestCase.plan_id.isnot(None))
            .group_by(TestCase.plan_id)
            .subquery()
        )

        plan_rows = (
            db.session.query(
                Plan,
                func.coalesce(bc_sub.c.badcase_count, 0),
                func.coalesce(bug_sub.c.bug_count, 0),
                func.coalesce(tc_sub.c.test_case_count, 0),
            )
            .outerjoin(bc_sub, bc_sub.c.plan_id == Plan.id)
            .outerjoin(bug_sub, bug_sub.c.plan_id == Plan.id)
            .outerjoin(tc_sub, tc_sub.c.plan_id == Plan.id)
            .filter(Plan.project_id == project_id)
            .all()
        )
        t_sql = (time.perf_counter() - t0) * 1000

        if not plan_rows:
            payload = {'success': True, 'plans': []}
            _cache_set(('plans', project_id), payload)
            _redis_cache_set(f'plans:{project_id}', payload, ttl_s=10)
            print(
                f"[PERF] GET /api/projects/{project_id}/plans perm={t_perm:.1f}ms sql={t_sql:.1f}ms build=0.0ms total={(time.perf_counter()-t_total0)*1000:.1f}ms (empty)",
                flush=True,
            )
            return jsonify(payload)

        t0 = time.perf_counter()
        # 构建 parent_id -> [child_plan] 映射，顺便准备 count map
        children_map = {}
        count_map = {}
        for plan, badcase_cnt, bug_cnt, tc_cnt in plan_rows:
            children_map.setdefault(plan.parent_id, []).append(plan)
            count_map[plan.id] = (int(badcase_cnt or 0), int(bug_cnt or 0), int(tc_cnt or 0))

        # 测试用例数量：按 plan_id 统计（不限制 project_id，避免数据不一致导致漏数）
        plan_ids = list(count_map.keys())
        if plan_ids:
            tc_rows = (
