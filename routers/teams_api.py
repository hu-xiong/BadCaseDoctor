"""teams_api（自 app.py 拆出）。"""
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

teams_api_bp = Blueprint("teams_api", __name__)


def _app():
    import app as _application
    return _application


@login_required
def api_create_plan():
    """创建计划"""
    try:
        print("=== 创建计划API被调用 ===")
        data = request.get_json()
        print(f"接收到的数据: {data}")
        print(f"当前用户ID: {current_user.id}")
            
        # 验证必填字段
        required_fields = ['name', 'start_date', 'end_date', 'project_id']
        for field in required_fields:
            if not data.get(field):
                print(f"缺少必填字段: {field}")
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
            
        # 检查项目权限
        print(f"检查项目权限: 用户ID={current_user.id}, 项目 ID={data['project_id']}")
        if not has_project_permission(current_user.id, data['project_id']):
            print("权限检查失败")
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        print("权限检查通过")
            
        # 检查父计划是否存在；子计划必须与父计划同一内容类型（BadCase / Bug / 测试用例）
        if data.get('parent_id'):
            parent_plan = Plan.query.get(data['parent_id'])
            if not parent_plan:
                return jsonify({'success': False, 'error': '父计划不存在'}), 404
            # 计划类型字段已移除：不再做“子计划类型必须与父计划一致”的校验

        # 验证日期格式
        try:
            start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data.get('start_date') else None
            end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data.get('end_date') else None
        except ValueError:
            return jsonify({'success': False, 'error': '日期格式错误，请使用 YYYY-MM-DD 格式'}), 400
            
        try:
            pid = int(data['project_id'])
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': '无效的 project_id'}), 400

        # 创建计划（Plan 表已移除 cycle / plan_count 等字段，勿再传入）
        plan = Plan(
            name=data['name'],
            description=data.get('description', ''),
            status=data.get('status', 'active'),
            priority=data.get('priority', 'medium'),
            start_date=start_date,
            end_date=end_date,
            scope_notification=data.get('scope_notification', False),
            parent_id=data.get('parent_id'),
            project_id=pid,
            creator_id=current_user.id,
            assignee_id=data.get('assignee_id')
        )
            
        db.session.add(plan)
        db.session.commit()
        _schedule_grep_work_item_index("plan", plan.id)
            
        result = jsonify({
            'success': True,
            'message': '计划创建成功',
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
                'scope_notification': plan.scope_notification,
                'parent_id': _json_snowflake_id(plan.parent_id),
                'project_id': plan.project_id,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat()
            }
        })
        _redis_cache_invalidate_project(plan.project_id)
        return result
            
    except Exception as e:
        db.session.rollback()
        print(f"创建计划失败: {e}")
        return jsonify({'success': False, 'error': '创建计划失败'}), 500

@teams_api_bp.route('/api/plans/<int:plan_id>', methods=['GET'])
@login_required
def api_get_plan_detail(plan_id):
    """获取计划详情"""
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
        
        # 获取子计划（Plan 模型未定义 children 关系，这里用 parent_id 反查）
        child_rows = Plan.query.filter_by(parent_id=plan.id).all()
        children = [
            {
                'id': _json_snowflake_id(child.id),
                'name': child.name,
                'status': child.status,
                'progress': child.progress,
                'created_at': child.created_at.isoformat() if child.created_at else None,
            }
            for child in (child_rows or [])
        ]

        # 获取工作项列表（避免依赖 plan.badcases / plan.bugs 关系）
        items = []
        # 计划类型字段已移除：计划详情不再按类型回填 items（卡片/列表视图负责按 card_id/type 展示）
        
        return jsonify({
            'success': True,
            'plan': {
                'id': _json_snowflake_id(plan.id),
                'name': plan.name,
                'description': plan.description,
                'status': plan.status,
                'priority': plan.priority,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'parent_id': _json_snowflake_id(plan.parent_id),
                'project_id': plan.project_id,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat(),
                'children': children,
                'items': items
            }
        })
        
    except Exception as e:
        print(f"获取计划详情失败: {e}")
        return jsonify({'success': False, 'error': '获取计划详情失败'}), 500

@teams_api_bp.route('/api/plans/<int:plan_id>', methods=['PUT'])
@login_required
def api_update_plan(plan_id):
    """更新计划"""
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
        
        data = request.get_json()
        
        # 更新字段
        if 'name' in data:
            plan.name = data['name']
        if 'description' in data:
            plan.description = data['description']
