"""bugs_api（自 app.py 拆出）。"""
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

bugs_api_bp = Blueprint("bugs_api", __name__)


def _app():
    import app as _application
    return _application


                db.session.query(TestCase.plan_id, func.count(TestCase.id))
                .filter(TestCase.plan_id.in_(plan_ids))
                .group_by(TestCase.plan_id)
                .all()
            )
            tc_direct = {int(pid): int(cnt) for pid, cnt in tc_rows}
            for pid in count_map:
                a, b, _ = count_map[pid]
                count_map[pid] = (a, b, tc_direct.get(int(pid), 0))

        def _sort_key(p: Plan):
            # 置顶优先，其次创建时间倒序（与原接口保持一致）
            # Windows 下 datetime.timestamp() 对极端日期可能抛 OSError([Errno 22] Invalid argument)
            pinned = 1 if getattr(p, "is_pinned", False) else 0
            created = getattr(p, "created_at", None)
            ts = 0
            if created:
                try:
                    ts = int(created.timestamp())
                except Exception:
                    ts = 0
            return (-pinned, -ts)

        # 预查询所有 plan 的 test_case 数量，避免 N+1 问题
        tc_all = dict(
            db.session.query(TestCase.plan_id, func.count(TestCase.id))
            .filter(TestCase.plan_id.in_(plan_ids))
            .group_by(TestCase.plan_id)
            .all()
        )

        def build_plan_tree(plan: Plan):
            """递归构建计划树（children 从 children_map 取）；数量含自身+所有子计划"""
            children = [build_plan_tree(c) for c in sorted(children_map.get(plan.id, []), key=_sort_key)]
            bc = count_map.get(plan.id, (0, 0, 0))[0]
            bug = count_map.get(plan.id, (0, 0, 0))[1]
            # 使用预查询的数据
            tc = tc_all.get(plan.id, 0)
            for c in children:
                bc += c.get('badcase_count', 0)
                bug += c.get('bug_count', 0)
                tc += c.get('test_case_count', 0)
            st, st_type = _plan_api_status_and_type(plan.status)
            return {
                'id': _json_snowflake_id(plan.id),
                'name': plan.name,
                'description': plan.description,
                'status': st,
                'status_type': st_type,
                'priority': plan.priority,
                'is_pinned': plan.is_pinned,
                'start_date': plan.start_date.isoformat() if plan.start_date else None,
                'end_date': plan.end_date.isoformat() if plan.end_date else None,
                'progress': plan.progress,
                'creator_id': plan.creator_id,
                'assignee_id': plan.assignee_id,
                'created_at': plan.created_at.isoformat() if plan.created_at else None,
                'updated_at': plan.updated_at.isoformat() if plan.updated_at else None,
                'children': children,
                'badcase_count': bc,
                'bug_count': bug,
                'test_case_count': tc,
            }

        # 顶级计划：parent_id=None
        root_plans = sorted(children_map.get(None, []), key=_sort_key)
        plans_tree = [build_plan_tree(p) for p in root_plans]
        t_build = (time.perf_counter() - t0) * 1000

        # 二次校验：用一次 GROUP BY 拿到所有 plan 的 test_case 数，再写回树，确保与 DB 一致
        def _collect_ids(nodes, out):
            for n in (nodes if isinstance(nodes, list) else [nodes]):
                pid = n.get('id')
                if pid is not None:
                    try:
                        out.append(int(str(pid)))
                    except (TypeError, ValueError):
                        pass
                if n.get('children'):
                    _collect_ids(n['children'], out)
        plan_ids_tree = []
        _collect_ids(plans_tree, plan_ids_tree)
        if plan_ids_tree:
            tc_patch = dict(
                db.session.query(TestCase.plan_id, func.count(TestCase.id))
                .filter(TestCase.plan_id.in_(plan_ids_tree))
                .group_by(TestCase.plan_id)
                .all()
            )
            def _patch(nodes):
                for n in (nodes if isinstance(nodes, list) else [nodes]):
                    pid = n.get('id')
                    if pid is not None:
                        try:
                            pk = int(str(pid))
                            n['test_case_count'] = int(tc_patch.get(pk, 0))
                        except (TypeError, ValueError):
                            n['test_case_count'] = 0
                    if n.get('children'):
                        _patch(n['children'])
            _patch(plans_tree)

        t0 = time.perf_counter()
        payload = {
            'success': True,
            'plans': plans_tree
        }
        _cache_set(('plans', project_id), payload)
        _redis_cache_set(f'plans:{project_id}', payload, ttl_s=10)
        t_payload = (time.perf_counter() - t0) * 1000
        print(
            f"[PERF] GET /api/projects/{project_id}/plans perm={t_perm:.1f}ms sql={t_sql:.1f}ms build={t_build:.1f}ms payload={t_payload:.1f}ms total={(time.perf_counter()-t_total0)*1000:.1f}ms rows={len(plan_rows)}",
            flush=True,
        )
        return jsonify(payload)
        
    except Exception as e:
        import traceback
        print(f"获取项目计划失败: {e}", flush=True)
        print(f"错误详情: {traceback.format_exc()}", flush=True)
        return jsonify({'success': False, 'error': f'获取项目计划失败: {str(e)}'}), 500

    # 团队管理API接口
@bugs_api_bp.route('/api/teams', methods=['POST'])
@login_required
def api_create_team():
    """创建团队"""
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
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['name', 'project_id']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        # 检查项目权限
        if not has_project_permission(current_user.id, data['project_id']):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 创建团队
        team = Team(
            name=data['name'],
            description=data.get('description', ''),
            project_id=data['project_id'],
            creator_id=current_user.id
        )
        
        db.session.add(team)
        db.session.commit()
        
        # 创建者自动成为团队成员
        team_member = TeamMember(
            team_id=team.id,
            user_id=current_user.id,
            role='leader'
        )
        db.session.add(team_member)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'team': {
                'id': team.id,
                'name': team.name,
                'description': team.description,
                'project_id': team.project_id,
                'creator_id': team.creator_id,
                'created_at': team.created_at.isoformat()
            }
        })
        _redis_cache_invalidate_project(data['project_id'])
        
    except Exception as e:
        db.session.rollback()
        print(f"创建团队失败: {e}")
        return jsonify({'success': False, 'error': '创建团队失败'}), 500

@bugs_api_bp.route('/api/teams/<int:team_id>/members', methods=['POST'])
@login_required
def api_add_team_member(team_id):
    """添加团队成员"""
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
        import json
        data = request.get_json()
        
        # 验证必填字段
        if not data.get('user_id'):
            return jsonify({'success': False, 'error': '缺少用户ID'}), 400
        
        # 检查团队是否存在
        team = Team.query.get(team_id)
        if not team:
            return jsonify({'success': False, 'error': '团队不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, team.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 检查用户是否已经是团队成员
        existing_member = TeamMember.query.filter_by(
            team_id=team_id, 
            user_id=data['user_id']
        ).first()
        
        if existing_member:
            return jsonify({'success': False, 'error': '用户已经是团队成员'}), 400
        
        # 添加团队成员
        team_member = TeamMember(
            team_id=team_id,
            user_id=data['user_id'],
            role=data.get('role', 'member'),
            permissions=json.dumps(data.get('permissions', ['view_project']))
        )
        
        db.session.add(team_member)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'member': {
                'id': team_member.id,
                'team_id': team_member.id,
                'user_id': team_member.user_id,
                'role': team_member.role,
                'permissions': json.loads(team_member.permissions) if team_member.permissions else ['view_project'],
                'joined_at': team_member.joined_at.isoformat()
            }
        })
        _redis_cache_invalidate_project(team.project_id)
        
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"添加团队成员失败: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': f'添加团队成员失败: {str(e)}'}), 500

@bugs_api_bp.route('/api/projects/<int:project_id>/teams', methods=['GET'])
@login_required
def api_get_project_teams(project_id):
    """获取项目的团队列表"""
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
        import json
        # 检查项目权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 获取项目下的所有团队
        teams = Team.query.filter_by(project_id=project_id).all()
        
        teams_data = []
        for team in teams:
            # 获取团队成员
            members = TeamMember.query.filter_by(team_id=team.id).all()
            members_data = []
            
            for member in members:
                user = User.query.get(member.user_id)
                if user:
                    members_data.append({
                        'id': member.id,
                        'user_id': member.user_id,
                        'user_name': user.name,
                        'user_email': user.email,
                        'role': member.role,
                        'permissions': json.loads(member.permissions) if member.permissions else ['view_project'],
                        'joined_at': member.joined_at.isoformat()
                    })
            
            teams_data.append({
                'id': team.id,
                'name': team.name,
                'description': team.description,
                'project_id': team.project_id,
                'creator_id': team.creator_id,
                'created_at': team.created_at.isoformat(),
                'members': members_data
            })
        
        return jsonify({
            'success': True,
            'teams': teams_data
        })
        
    except Exception as e:
        print(f"获取项目团队失败: {e}")
        return jsonify({'success': False, 'error': '获取项目团队失败'}), 500

@bugs_api_bp.route('/api/projects/<int:project_id>/members', methods=['GET'])
@login_required
def api_get_project_members(project_id):
    """获取项目的所有成员（包括直接权限和团队成员）"""
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
        redis_hit, redis_cached = _redis_cache_get(f'members:{project_id}')
        if redis_hit:
            print(
                f"[PERF] GET /api/projects/{project_id}/members redis_hit total={(time.perf_counter()-t_total0)*1000:.1f}ms",
                flush=True,
            )
            return jsonify(redis_cached)
        # 回退到内存缓存
        cache_hit, cached = _cache_get(('members', project_id), ttl_s=0.5)
        if cache_hit:
            print(
                f"[PERF] GET /api/projects/{project_id}/members cache_hit total={(time.perf_counter()-t_total0)*1000:.1f}ms",
                flush=True,
            )
            return jsonify(cached)

        # 检查项目权限
        t0 = time.perf_counter()
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        t_perm = (time.perf_counter() - t0) * 1000
        
        # 直接权限 + 团队成员 都用 JOIN（总共 2 次查询）
        t0 = time.perf_counter()
        direct_rows = (
            db.session.query(User.id, User.name, User.email, ProjectPermission.role)
            .join(ProjectPermission, ProjectPermission.user_id == User.id)
            .filter(ProjectPermission.project_id == project_id)
            .all()
        )
        t_sql1 = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        direct_member_map = {}
        for uid, name, email, role in direct_rows:
            direct_member_map[uid] = {
                'id': uid,
                'name': name,
                'email': email,
                'role': role,
                'source': 'direct_permission',
            }
        t_build1 = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        team_rows = (
            db.session.query(User.id, User.name, User.email, TeamMember.role, Team.name)
            .join(TeamMember, TeamMember.user_id == User.id)
            .join(Team, Team.id == TeamMember.team_id)
            .filter(Team.project_id == project_id)
            .all()
        )
        t_sql2 = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        all_members = list(direct_member_map.values())
        seen = set(direct_member_map.keys())
        for uid, name, email, role, team_name in team_rows:
            if uid in seen:
                continue
            seen.add(uid)
            all_members.append({
                'id': uid,
                'name': name,
                'email': email,
                'role': role,
                'source': f'team_{team_name}',
            })
        t_build2 = (time.perf_counter() - t0) * 1000
        
        t0 = time.perf_counter()
        payload = {
            'success': True,
            'members': all_members
        }
        _cache_set(('members', project_id), payload)
        _redis_cache_set(f'members:{project_id}', payload, ttl_s=10)
        t_payload = (time.perf_counter() - t0) * 1000
        print(
            f"[PERF] GET /api/projects/{project_id}/members perm={t_perm:.1f}ms sql1={t_sql1:.1f}ms build1={t_build1:.1f}ms sql2={t_sql2:.1f}ms build2={t_build2:.1f}ms payload={t_payload:.1f}ms total={(time.perf_counter()-t_total0)*1000:.1f}ms direct={len(direct_rows)} team={len(team_rows)}",
            flush=True,
        )
        return jsonify(payload)
        
    except Exception as e:
        print(f"获取项目成员失败: {e}")
        return jsonify({'success': False, 'error': '获取项目成员失败'}), 500

@bugs_api_bp.route('/api/users/available', methods=['GET'])
@login_required
def api_get_available_users():
    """获取所有可用的注册用户（用于添加团队成员）"""
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
        # 获取所有已注册的用户
        users = User.query.filter_by(is_verified=True).all()
        
        users_data = []
        for user in users:
            users_data.append({
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': user.role if hasattr(user, 'role') else None
            })
        
        return jsonify({
            'success': True,
            'users': users_data
        })
        
    except Exception as e:
        print(f"获取可用用户失败: {e}")
        return jsonify({'success': False, 'error': '获取可用用户失败'}), 500

@bugs_api_bp.route('/api/projects/<int:project_id>/add_user', methods=['POST'])
@login_required
def api_add_project_user(project_id):
    """添加用户到项目（需要管理员权限）"""
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
        data = request.get_json()
        
        # 验证必填字段
        if not data.get('user_id') or not data.get('role'):
            return jsonify({'success': False, 'error': '缺少必填字段'}), 400
        
        # 检查项目权限
        if not has_project_permission(current_user.id, project_id, 'admin'):
            return jsonify({'success': False, 'error': '需要管理员权限'}), 403
        
        # 检查用户是否存在
        user = User.query.get(data['user_id'])
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404
        
        # 检查是否已经有权限
        existing_permission = ProjectPermission.query.filter_by(
            project_id=project_id, 
            user_id=data['user_id']
        ).first()
        
        if existing_permission:
            return jsonify({'success': False, 'error': '用户已有项目权限'}), 400
        
        # 添加权限
        permission = ProjectPermission(
            project_id=project_id,
            user_id=data['user_id'],
            role=data['role']
        )
        
        db.session.add(permission)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'permission': {
                'id': permission.id,
                'project_id': permission.project_id,
                'user_id': permission.user_id,
                'role': permission.role,
                'created_at': permission.created_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"添加项目用户失败: {e}")
        return jsonify({'success': False, 'error': '添加项目用户失败'}), 500

def _coerce_non_negative_int(v):
    """转为非负整数；无效返回 None。"""
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    try:
        i = int(float(v))
        return i if i >= 0 else None
    except (TypeError, ValueError):
        return None


def _coerce_positive_int_or_none(v):
    """转为正整数；无效或非正返回 None（用于 assignee_id）。"""
    if v is None:
        return None
    if isinstance(v, str) and not str(v).strip():
        return None
    try:
        i = int(float(v))
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None


def _truncate_db_str(value, max_len, default=''):
    if value is None:
        return default
    s = str(value)
    return s[:max_len] if len(s) > max_len else s


def _normalize_bug_priority_for_db(raw):
    """Bug.priority 列为 VARCHAR(10)，create 工具可能产出中文「高/中/低」或过长英文。"""
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        return 'p3'
    s = str(raw).strip()
    zh_map = {
        '高': 'p1', '中': 'p2', '低': 'p3',
        '紧急': 'p1', '一般': 'p2',
        '极高': 'p1',
    }
    if s in zh_map:
        return zh_map[s]
    low = s.lower()
    if low in ('p1', 'p2', 'p3'):
        return low
    if s in ('P1', 'P2', 'P3'):
        return s.lower()
    if s in ('1', '2', '3'):
        return 'p' + s
    # 未知值截断，避免超过 10 字符写库失败
    return _truncate_db_str(s, 10, 'p3') or 'p3'


def _attachments_to_text(raw):
    if raw is None:
        return ''
    if isinstance(raw, (dict, list)):
        try:
            return json.dumps(raw, ensure_ascii=False)
        except Exception:
            return str(raw)
    return str(raw)


# Bug相关API接口
@bugs_api_bp.route('/api/bugs', methods=['POST'])
@login_required
def api_create_bug():
    """创建Bug"""
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
        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({'success': False, 'error': '请求体必须是 JSON 对象'}), 400

        title = (data.get('title') or '').strip()
        title = ' '.join(title.split())  # 合并任意空白，与 create 工具一致
