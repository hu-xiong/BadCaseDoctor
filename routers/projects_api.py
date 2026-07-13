"""projects_api（自 app.py 拆出）。"""
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

projects_api_bp = Blueprint("projects_api", __name__)


def _app():
    import app as _application
    return _application


@projects_api_bp.route('/api/projects', methods=['GET'])
@login_required
def api_get_projects():
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
        # Redis 缓存（按用户维度）；无 Redis 时走下方进程内短缓存 + 轻量 SQL
        redis_hit, redis_cached = _redis_cache_get(f'projects:{current_user.id}')
        if redis_hit:
            t_total = (time.perf_counter() - t0) * 1000
            if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
                print(f"[PERF] GET /api/projects redis_hit total={t_total:.1f}ms", flush=True)
            return jsonify(redis_cached)

        mem_hit, mem_cached = _cache_get(('api_projects', current_user.id), ttl_s=20.0)
        if mem_hit:
            t_total = (time.perf_counter() - t0) * 1000
            if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
                print(f"[PERF] GET /api/projects mem_hit total={t_total:.1f}ms", flush=True)
            return jsonify(mem_cached)

        uid = current_user.id
        t1 = time.perf_counter()
        # 拆成两次窄查询：均走 user_id / (user_id,project_id) 索引友好路径，且只取列表字段，避免 ORM 加载 login_configs、intro 等大列
        owned_rows = (
            db.session.query(
                Project.id,
                Project.name,
                Project.description,
                Project.avatar,
                Project.owner,
                Project.status,
                Project.created_at,
            )
            .filter(Project.user_id == uid)
            .order_by(Project.created_at.desc())
            .limit(100)
            .all()
        )
        shared_rows = (
            db.session.query(
                Project.id,
                Project.name,
                Project.description,
                Project.avatar,
                Project.owner,
                Project.status,
                Project.created_at,
                ProjectPermission.role,
            )
            .join(ProjectPermission, Project.id == ProjectPermission.project_id)
            .filter(ProjectPermission.user_id == uid, Project.user_id != uid)
            .order_by(Project.created_at.desc())
            .limit(100)
            .all()
        )
        t_q = (time.perf_counter() - t1) * 1000

        by_pid = {}
        for rid, name, desc, av, ow, st, cat in owned_rows:
            by_pid[rid] = {
                'id': rid,
                'name': name,
                'description': desc,
                'avatar': av,
                'owner': ow,
                'status': st,
                'created_at': cat.isoformat() if cat else '',
                'role': 'admin',
            }
        for rid, name, desc, av, ow, st, cat, role in shared_rows:
            if rid in by_pid:
                continue
            by_pid[rid] = {
                'id': rid,
                'name': name,
                'description': desc,
                'avatar': av,
                'owner': ow,
                'status': st,
                'created_at': cat.isoformat() if cat else '',
                'role': role or 'collaborator',
            }

        user_projects = list(by_pid.values())
        user_projects.sort(key=lambda x: x['created_at'], reverse=True)

        t_total = (time.perf_counter() - t0) * 1000
        if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
            print(
                f"[PERF] GET /api/projects total={t_total:.1f}ms q={t_q:.1f}ms "
                f"owned={len(owned_rows)} shared={len(shared_rows)} merged={len(user_projects)}",
                flush=True,
            )
        result = {'success': True, 'projects': user_projects}
        _redis_cache_set(f'projects:{current_user.id}', result, ttl_s=60)
        _cache_set(('api_projects', current_user.id), result)
        return jsonify(result)
        
    except Exception as e:
        print(f"获取项目列表时发生错误: {str(e)}")
        return jsonify({'success': False, 'error': '获取项目列表失败'}), 500

@projects_api_bp.route('/api/projects', methods=['POST'])
@login_required
def api_create_project():
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
        
        if not data:
            return jsonify({'success': False, 'error': '请求数据格式错误'}), 400
            
        name = data.get('name')
        description = data.get('description', '')
        avatar = data.get('avatar', '')
        owner = data.get('owner', '')
        intro = data.get('intro', '')
        
        if not name:
            return jsonify({'success': False, 'error': '项目名称不能为空'}), 400
        
        project = Project(
            name=name,
            description=description,
            avatar=avatar,
            owner=owner,
            intro=intro,
            user_id=current_user.id
        )
        
        db.session.add(project)
        db.session.commit()
        print(f"项目保存成功，ID: {project.id}")
        
        # 为项目创建者添加管理员权限
        permission = ProjectPermission(
            project_id=project.id,
            user_id=current_user.id,
            role='admin'
        )
        db.session.add(permission)
        
        # 创建默认迭代
        default_plan = Plan(
            name='迭代 1',
            description='项目默认迭代',
            status='active',
            project_id=project.id,
            creator_id=current_user.id,
            is_default=True
        )
        db.session.add(default_plan)
        db.session.commit()
        print(f"已为用户 {current_user.id} 添加项目 {project.id} 的管理员权限")
        print(f"已为项目 {project.id} 创建默认迭代，ID: {default_plan.id}")
        
        result = {
            'success': True,
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'avatar': project.avatar,
                'owner': project.owner,
                'intro': project.intro,
                'status': project.status,
                'created_at': project.created_at.isoformat()
            }
        }
        print(f"返回结果: {result}")
        _redis_cache_invalidate_projects(current_user.id)
        return jsonify(result)
    except Exception as e:
        print(f"创建项目时发生异常: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@projects_api_bp.route('/api/projects/ensure-default', methods=['POST'])
@login_required
def api_ensure_default_project():
    """进入工作台后：用户无任何可访问项目时，从系统模板克隆默认项目副本。"""
    a = _app()
    db = a.db
    Project = a.Project
    ProjectPermission = a.ProjectPermission
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_invalidate_projects = a._redis_cache_invalidate_projects

    try:
        uid = current_user.id

        def _finish(project_id: int, created: bool):
            from utils.project_clone import ensure_default_plan_for_project, ensure_project_admin_permission

            ensure_project_admin_permission(int(project_id), int(uid))
            plan_id, plan_created = ensure_default_plan_for_project(int(project_id), int(uid))
            db.session.commit()
            _redis_cache_invalidate_projects(uid)
            _redis_cache_invalidate_project(int(project_id))
            try:
                _cache_invalidate_plans(int(project_id))
            except Exception:
                pass
            return jsonify({
                'success': True,
                'project_id': str(int(project_id)),
                'created': created,
                'default_plan_id': plan_id,
                'default_plan_created': plan_created,
            })

        from utils.project_clone import resolve_user_default_project

        project_id, created = resolve_user_default_project(int(uid))
        return _finish(project_id, created)
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        print(f"ensure-default 失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': '确保默认项目失败'}), 500

@projects_api_bp.route('/api/projects/<int:project_id>', methods=['GET'])
@login_required
def api_get_project_detail(project_id):
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

    print(f"=== 获取项目详情 {project_id} ===")
    print(f"当前用户ID: {current_user.id}")
    
    try:
        # 只获取项目基本信息，不包含BadCase列表（并避免重复查询 Project）
        # 勿用 get_or_404：NotFound 会被下方 except Exception 吞掉并误返回 500
        project = Project.query.get(project_id)
        if not project:
            return jsonify({'success': False, 'error': '项目不存在'}), 404
        if project.user_id != current_user.id:
            has_perm = ProjectPermission.query.filter_by(
                user_id=current_user.id,
                project_id=project_id
            ).first() is not None
            if not has_perm:
                print(f"权限检查失败: 用户 {current_user.id} 无权访问项目 {project_id}")
                return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        print(f"项目信息获取成功: {project.name}")
        
        # 获取BadCase统计信息（快速统计）；状态与 BadCaseStatus 枚举对齐（closed 非 close）
        total_bc = pending_bc = resolved_bc = closed_bc = 0
        try:
            st = db.session.query(
                db.func.count(BadCase.id),
                db.func.sum(db.case((BadCase.status == BadCaseStatus.PENDING, 1), else_=0)),
                db.func.sum(db.case((BadCase.status == BadCaseStatus.RESOLVED, 1), else_=0)),
                db.func.sum(db.case((BadCase.status == BadCaseStatus.CLOSED, 1), else_=0)),
            ).filter(BadCase.project_id == project_id).first()
            if st:
                total_bc = int(st[0] or 0)
                pending_bc = int(st[1] or 0)
                resolved_bc = int(st[2] or 0)
                closed_bc = int(st[3] or 0)
        except Exception as se:
            print(f"[api_get_project_detail] BadCase 统计查询失败(已降级为0): {se}")
            import traceback
            traceback.print_exc()

        print(
            f"BadCase统计完成: 总计={total_bc}, 待处理={pending_bc}, "
            f"已解决={resolved_bc}, 已关闭={closed_bc}"
        )

        return jsonify({
            'success': True,
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'avatar': project.avatar,
                'owner': project.owner,
                'intro': project.intro,
                'status': project.status,
                'login_configs': _safe_parse_project_login_configs(project.login_configs),
                'created_at': project.created_at.isoformat() if project.created_at else None,
                'badcase_stats': {
                    'total': total_bc,
                    'pending': pending_bc,
                    'resolved': resolved_bc,
                    'close': closed_bc,
                }
            }
        })
    except Exception as e:
        print(f"获取项目详情失败: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'error': '获取项目信息失败'}), 500

@projects_api_bp.route('/api/projects/<int:project_id>/edit-context', methods=['GET'])
@login_required
def api_get_project_edit_context(project_id):
    """编辑页专用：一次性返回最小必要上下文（project + plans + members）"""
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
        lite = (request.args.get('lite') or '').strip().lower() in ('1', 'true', 'yes', 'on')
        cache_suffix = ':lite' if lite else ''
        # Redis 缓存检查（优先于内存缓存，跨进程共享）
        redis_hit, redis_cached = _redis_cache_get(f'edit-context:{project_id}{cache_suffix}')
        if redis_hit:
            t_total = (time.perf_counter() - t0) * 1000
            if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
                print(f"[PERF] GET /api/projects/{project_id}/edit-context redis_hit total={t_total:.1f}ms", flush=True)
            return jsonify(redis_cached)

        t_access0 = time.perf_counter()
        project, access_err = _project_for_user_collaborator_access(project_id, current_user.id)
        if access_err == 'not_found':
            return jsonify({'success': False, 'error': '项目不存在'}), 404
        if access_err == 'forbidden':
            return jsonify({'success': False, 'error': '没有项目权限'}), 403

        t_plans0 = time.perf_counter()
        # plans：沿用 /plans 的批量统计逻辑（无 N+1）
        plans = Plan.query.filter_by(project_id=project_id).all()
        children_map = {}
        plan_by_id = {}
        for p in plans:
            plan_by_id[p.id] = p
            children_map.setdefault(p.parent_id, []).append(p)

        plan_ids = list(plan_by_id.keys())
        badcase_counts = {}
        bug_counts = {}
        testcase_counts = {}
        t_counts0 = time.perf_counter()
        if plan_ids and not lite:
            # 单次 RTT：bad_case / bug / test_case 三个聚合（原为 3 条独立查询）
            ids_sql = ','.join(str(int(x)) for x in plan_ids)
            cnt_rows = db.session.execute(
                text(
                    "SELECT 'bc' AS k, plan_id, COUNT(*) AS c FROM bad_case "
                    f"WHERE plan_id IN ({ids_sql}) GROUP BY plan_id "
                    "UNION ALL SELECT 'bug', plan_id, COUNT(*) FROM bug "
                    f"WHERE plan_id IN ({ids_sql}) GROUP BY plan_id "
                    "UNION ALL SELECT 'tc', plan_id, COUNT(*) FROM test_case "
                    f"WHERE plan_id IN ({ids_sql}) GROUP BY plan_id"
                )
            ).fetchall()
            for row in cnt_rows:
                k, pid, c = row[0], row[1], int(row[2])
                if k == 'bc':
                    badcase_counts[pid] = c
                elif k == 'bug':
                    bug_counts[pid] = c
                else:
                    testcase_counts[pid] = c
        t_counts1 = time.perf_counter()

        def _sort_key(p: Plan):
            pinned = 1 if getattr(p, "is_pinned", False) else 0
            created = getattr(p, "created_at", None)
            ts = 0
            if created:
                try:
                    ts = int(created.timestamp())
                except Exception:
                    ts = 0
            return (-pinned, -ts)

        def build_plan_tree(plan: Plan):
            children = [build_plan_tree(c) for c in sorted(children_map.get(plan.id, []), key=_sort_key)]
            bc = int(badcase_counts.get(plan.id, 0))
            bug = int(bug_counts.get(plan.id, 0))
            tc = int(testcase_counts.get(plan.id, 0))
            for c in children:
                bc += c.get('badcase_count', 0)
                bug += c.get('bug_count', 0)
                tc += c.get('test_case_count', 0)
            return {
                'id': _json_snowflake_id(plan.id),
                'name': plan.name,
                'description': plan.description,
                'status': plan.status,
                'priority': plan.priority,
                'is_pinned': plan.is_pinned,
                'is_default': plan.is_default,
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

        root_plans = sorted(children_map.get(None, []), key=_sort_key)
        plans_tree = [build_plan_tree(p) for p in root_plans]

        t_mem0 = time.perf_counter()
        # 直接成员 + 团队成员合并为 1 次 UNION；字符串列显式 COLLATE，避免 MySQL 1271 Illegal mix of collations
        _pid = int(project_id)
        _ut = User.__table__.name
        _ppt = ProjectPermission.__table__.name
        _tmt = TeamMember.__table__.name
        _tt = Team.__table__.name

        def _qb(n):
            return f'`{n}`' if n else n

        _cs = "utf8mb4_general_ci"
        mem_sql = text(
            f"SELECT CONVERT('direct' USING utf8mb4) COLLATE {_cs} AS src, u.id, "
            f"CONVERT(u.name USING utf8mb4) COLLATE {_cs} AS name, "
            f"CONVERT(u.email USING utf8mb4) COLLATE {_cs} AS email, "
            f"CONVERT(pp.role USING utf8mb4) COLLATE {_cs} AS role, "
            f"CAST(NULL AS CHAR(200) CHARACTER SET utf8mb4) COLLATE {_cs} AS team_name "
            f"FROM {_qb(_ut)} u INNER JOIN {_qb(_ppt)} pp ON pp.user_id = u.id WHERE pp.project_id = :pid "
            f"UNION ALL "
            f"SELECT CONVERT('team' USING utf8mb4) COLLATE {_cs} AS src, u.id, "
            f"CONVERT(u.name USING utf8mb4) COLLATE {_cs}, "
            f"CONVERT(u.email USING utf8mb4) COLLATE {_cs}, "
            f"CONVERT(tm.role USING utf8mb4) COLLATE {_cs}, "
            f"CONVERT(t.name USING utf8mb4) COLLATE {_cs} AS team_name "
            f"FROM {_qb(_ut)} u INNER JOIN {_qb(_tmt)} tm ON tm.user_id = u.id "
            f"INNER JOIN {_qb(_tt)} t ON t.id = tm.team_id WHERE t.project_id = :pid"
        )
        mem_rows = db.session.execute(mem_sql, {'pid': _pid}).fetchall()
        t_mem_fetch = time.perf_counter()
        direct_member_map = {}
        team_candidates = []
        for row in mem_rows:
            src, uid, name, email, role, team_name = (
                row[0], row[1], row[2], row[3], row[4], row[5]
            )
            if src == 'direct':
                direct_member_map[uid] = {
                    'id': uid,
                    'name': name,
                    'email': email,
                    'role': role,
                    'source': 'direct_permission',
                }
            else:
                team_candidates.append((uid, name, email, role, team_name))
        team_members = []
        for uid, name, email, role, team_name in team_candidates:
            if uid in direct_member_map:
                continue
            team_members.append({
                'id': uid,
                'name': name,
                'email': email,
                'role': role,
                'source': f'team_{team_name}',
            })

        t_mem1 = time.perf_counter()
        t_total = (time.perf_counter() - t0) * 1000
        if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
            print(
                f"[PERF] GET /api/projects/{project_id}/edit-context total={t_total:.1f}ms "
                f"access={(t_plans0 - t_access0) * 1000:.1f}ms "
                f"plans={(t_counts0 - t_plans0) * 1000:.1f}ms "
                f"counts={(t_counts1 - t_counts0) * 1000:.1f}ms "
                f"tree={(t_mem0 - t_counts1) * 1000:.1f}ms "
                f"members={(t_mem1 - t_mem0) * 1000:.1f}ms "
                f"(members_sql={(t_mem_fetch - t_mem0) * 1000:.1f}ms members_py={(t_mem1 - t_mem_fetch) * 1000:.1f}ms)",
                flush=True,
            )
        result = {
            'success': True,
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'status': project.status,
            },
            'plans': plans_tree,
            'members': list(direct_member_map.values()) + team_members,
        }
        _redis_cache_set(f'edit-context:{project_id}{cache_suffix}', result, ttl_s=30)
        return jsonify(result)

    except Exception as e:
        import traceback
        print(f"获取编辑页上下文失败: {e}")
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': '获取编辑页上下文失败'}), 500

@projects_api_bp.route('/api/projects/<int:project_id>', methods=['PUT'])
@login_required
def api_update_project(project_id):
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

    print(f"=== 开始更新项目 {project_id} ===")
    print(f"当前用户ID: {current_user.id}")
    print(f"当前用户邮箱: {current_user.email}")
    
    try:
        # 检查权限
        print("检查项目权限...")
        if not has_project_permission(current_user.id, project_id):
            print(f"权限检查失败: 用户 {current_user.id} 无权修改项目 {project_id}")
            return jsonify({'success': False, 'error': '无权修改此项目'}), 403
        print("权限检查通过")
        
        # 获取项目
        print(f"获取项目信息...")
        project = Project.query.get_or_404(project_id)
        print(f"项目信息: ID={project.id}, 名称={project.name}, 创建者={project.user_id}")
        
        # 获取请求数据
        print("解析请求数据...")
        data = request.get_json()
        print(f"请求数据: {data}")
        
        if not data:
            print("请求数据为空")
            return jsonify({'success': False, 'error': '请求数据格式错误'}), 400
        
        # 记录更新前的项目信息
        print("更新前的项目信息:")
        print(f"  - 名称: {project.name}")
        print(f"  - 描述: {project.description}")
        print(f"  - 头像: {project.avatar}")
        print(f"  - 负责人: {project.owner}")
        print(f"  - 介绍: {project.intro}")
        print(f"  - 状态: {project.status}")
        print(f"  - 登录配置: {project.login_configs}")
        
        # 更新项目信息
        print("开始更新项目字段...")
        if 'name' in data:
            old_name = project.name
            project.name = data['name']
            print(f"  更新名称: {old_name} -> {project.name}")
        if 'description' in data:
            old_desc = project.description
            project.description = data['description']
            print(f"  更新描述: {old_desc} -> {project.description}")
        if 'avatar' in data:
            old_avatar = project.avatar
            # 检查是否是base64数据，如果是则跳过（避免数据过大）
            if data['avatar'] and data['avatar'].startswith('data:'):
                print(f"  跳过base64头像数据，保持原有头像: {old_avatar}")
            else:
                project.avatar = data['avatar']
                print(f"  更新头像: {old_avatar} -> {project.avatar}")
        if 'owner' in data:
            old_owner = project.owner
            project.owner = data['owner']
            print(f"  更新负责人: {old_owner} -> {project.owner}")
        if 'intro' in data:
            old_intro = project.intro
            project.intro = data['intro']
            print(f"  更新介绍: {old_intro} -> {project.intro}")
        if 'login_configs' in data:
            old_login_configs = project.login_configs
            # login_configs 是列表，需要序列化为 JSON 字符串
            if isinstance(data['login_configs'], list):
                project.login_configs = json.dumps(data['login_configs'], ensure_ascii=False)
            else:
                project.login_configs = data['login_configs']
            print(f"  更新登录配置: {old_login_configs} -> {project.login_configs}")
        
        # 提交到数据库
        print("提交数据库更改...")
        db.session.commit()
        print("数据库提交成功")
        
        # 返回更新后的项目信息
        response_data = {
            'success': True,
            'message': '项目更新成功',
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'avatar': project.avatar,
                'owner': project.owner,
                'intro': project.intro,
                'status': project.status,
                'login_configs': json.loads(project.login_configs) if project.login_configs else []
            }
        }
        print(f"返回响应: {response_data}")
        print(f"=== 项目 {project_id} 更新完成 ===")
        _redis_cache_invalidate_project(project_id)
        _redis_cache_invalidate_projects(current_user.id)
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"更新项目时发生错误: {str(e)}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        db.session.rollback()
        print("数据库回滚完成")
        return jsonify({'success': False, 'error': str(e)}), 500

@projects_api_bp.route('/api/projects/<int:project_id>/publish', methods=['POST'])
@login_required
def api_publish_project(project_id):
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

    print(f"=== 开始发布项目 {project_id} ===")
    print(f"当前用户ID: {current_user.id}")
    print(f"当前用户邮箱: {current_user.email}")
    
    try:
        # 检查权限
        print("检查项目权限...")
        if not has_project_permission(current_user.id, project_id):
            print(f"权限检查失败: 用户 {current_user.id} 无权发布项目 {project_id}")
            return jsonify({'success': False, 'error': '无权发布此项目'}), 403
        print("权限检查通过")
        
        # 获取项目
        print(f"获取项目信息...")
        project = Project.query.get_or_404(project_id)
        print(f"项目信息: ID={project.id}, 名称={project.name}, 当前状态={project.status}")
        
        # 更新状态
        old_status = project.status
        project.status = 'published'
        print(f"更新项目状态: {old_status} -> {project.status}")
        
        # 提交到数据库
        print("提交数据库更改...")
        db.session.commit()
        print("数据库提交成功")
        
        response_data = {
            'success': True,
            'message': '项目发布成功',
            'project': {
                'id': project.id,
                'name': project.name,
                'status': project.status
            }
        }
        print(f"返回响应: {response_data}")
        print(f"=== 项目 {project_id} 发布完成 ===")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"发布项目时发生错误: {str(e)}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        db.session.rollback()
        print("数据库回滚完成")
        return jsonify({'success': False, 'error': str(e)}), 500

@projects_api_bp.route('/api/projects/<int:project_id>/badcases', methods=['GET'])
@login_required
def api_get_project_badcases(project_id):
    """获取项目的BadCase列表（分页）"""
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

    print(f"=== 获取项目BadCase列表 {project_id} ===")
    
    try:
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 获取计划ID参数
        plan_id = _parse_query_int_optional('plan_id')
        card_id = _parse_query_optional_int64('card_id')
        
        # 获取状态类型和内容类型参数
        status_type = request.args.get('status_type')
        content_type = request.args.get('content_type')
        
        # 构建查询条件
        query = BadCase.query.filter_by(project_id=project_id)
        
        # 卡片分类型：优先按 card_id 过滤（与 Bug 列表一致）
        if card_id is not None:
            query = query.filter(BadCase.card_id == card_id)
            print(f"按卡片ID过滤BadCase: card_id={card_id}", flush=True)
        # 处理status_type和content_type参数
        elif status_type == 'unplanned':
            # 未计划的BadCase：没有关联计划的BadCase
            query = query.filter(BadCase.plan_id.is_(None))
            print(f"过滤未计划的BadCase (status_type=unplanned)")
        elif plan_id is not None:
            # 如果指定了计划ID，添加计划过滤条件
            if plan_id == 0:  # plan_id=0 表示未计划的BadCase
                query = query.filter(BadCase.plan_id.is_(None))
                print(f"过滤未计划的BadCase (plan_id=0)")
            else:
                query = query.filter_by(plan_id=plan_id)
                print(f"过滤计划ID为 {plan_id} 的BadCase")
        else:
            print("不进行计划过滤，显示所有BadCase")
        
        # 分页查询BadCase
        pagination = query.order_by(BadCase.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)

        # 自动修补：plan_id 为空但 plan 列为数字 id 时写回（避免一直落在「未计划」列表）
        _repaired = False
        for _bc in pagination.items:
            if _try_repair_badcase_plan_id_from_legacy_plan_string(_bc):
                _repaired = True
        if _repaired:
            db.session.commit()
            _cache_invalidate_plans(project_id)

        _card_repaired = False
        for _bc in pagination.items:
            if _try_repair_badcase_card_id_from_source_card(_bc):
                _card_repaired = True
        if _card_repaired:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"[BadCase列表] card_id 反查补写 commit 失败: {e}", flush=True)

        # 批量解析 assignee -> user.name，避免 N+1
        def _parse_assignee_ids(raw):
            if raw is None:
                return []
            s = str(raw).strip()
            if not s:
                return []
            try:
                if ',' in s:
                    return [int(x.strip()) for x in s.split(',') if x.strip()]
                return [int(s)]
            except (ValueError, TypeError):
                return []

        all_user_ids = set()
        assignee_id_lists = {}
        for bc in pagination.items:
            ids = _parse_assignee_ids(bc.assignee)
            assignee_id_lists[bc.id] = ids
            all_user_ids.update(ids)

        user_name_map = {}
        if all_user_ids:
            rows = db.session.query(User.id, User.name).filter(User.id.in_(list(all_user_ids))).all()
            user_name_map = {uid: name for uid, name in rows}

        badcases = []
        for bc in pagination.items:
            assignee_display = '未指派'
            ids = assignee_id_lists.get(bc.id) or []
            if ids:
                # 兼容单选/多选展示
                first_name = user_name_map.get(ids[0])
                if first_name:
                    assignee_display = first_name if len(ids) == 1 else f"{first_name}..."
                else:
                    assignee_display = str(bc.assignee)
            elif bc.assignee:
                # 非法格式直接回显
                assignee_display = str(bc.assignee)

            badcases.append({
                'id': _json_snowflake_id(bc.id),
                'title': bc.title,
                'case_category': bc.case_category,
                'base_problem': (bc.base_problem[:100] + '...') if bc.base_problem and len(bc.base_problem) > 100 else (bc.base_problem or ''),
                'priority': bc.priority,
                'status': bc.status.value if hasattr(bc.status, 'value') else bc.status,  # 枚举类型转换为值
                'assignee': assignee_display,
                'plan_id': _json_snowflake_id(bc.plan_id),  # 添加计划ID字段
                'card_id': _json_snowflake_id(getattr(bc, 'card_id', None)),
                'created_at': bc.created_at.isoformat()
            })
        
        print(f"BadCase列表获取成功: 第{page}页，共{per_page}条，总计{pagination.total}条")
        
        return jsonify({
            'success': True,
            'badcases': badcases,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })
    except Exception as e:
        import traceback
        print(f"获取项目BadCase列表失败: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        db.session.rollback()
        return jsonify({'success': False, 'error': '获取BadCase列表失败'}), 500

@projects_api_bp.route('/api/projects/<int:project_id>/revoke', methods=['POST'])
@login_required
def api_revoke_project(project_id):
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

    print(f"=== 开始撤销发布项目 {project_id} ===")
    print(f"当前用户ID: {current_user.id}")
    print(f"当前用户邮箱: {current_user.email}")
    
    try:
        # 检查权限
        print("检查项目权限...")
        if not has_project_permission(current_user.id, project_id):
            print(f"权限检查失败: 用户 {current_user.id} 无权撤销发布项目 {project_id}")
            return jsonify({'success': False, 'error': '无权撤销发布此项目'}), 403
        print("权限检查通过")
        
        # 获取项目
        print(f"获取项目信息...")
        project = Project.query.get_or_404(project_id)
        print(f"项目信息: ID={project.id}, 名称={project.name}, 当前状态={project.status}")
        
        # 更新状态
        old_status = project.status
        project.status = 'unpublished'
        print(f"更新项目状态: {old_status} -> {project.status}")
        
        # 提交到数据库
        print("提交数据库更改...")
        db.session.commit()
        print("数据库提交成功")
        
        response_data = {
            'success': True,
            'message': '项目撤销发布成功',
            'project': {
                'id': project.id,
                'name': project.name,
                'status': project.status
            }
        }
        print(f"返回响应: {response_data}")
        print(f"=== 项目 {project_id} 撤销发布完成 ===")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"撤销发布项目时发生错误: {str(e)}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        db.session.rollback()
        print("数据库回滚完成")
        return jsonify({'success': False, 'error': str(e)}), 500

@projects_api_bp.route('/api/projects/<int:project_id>', methods=['DELETE'])
@login_required
def api_delete_project(project_id):
    """删除项目"""
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

    print(f"=== 开始删除项目 {project_id} ===")
    print(f"当前用户ID: {current_user.id}")
    print(f"当前用户邮箱: {current_user.email}")
    
    try:
        # 先获取项目信息检查是否是所有者
        project = Project.query.get_or_404(project_id)
        print(f"项目所有者(user_id): {project.user_id}, 当前用户: {current_user.id}")
        
        # 检查是否是项目所有者(user_id)，或者有管理员权限
        is_owner = project.user_id == current_user.id
        has_admin = has_project_permission(current_user.id, project_id, 'admin')
        
        print(f"是否所有者: {is_owner}, 是否有管理员权限: {has_admin}")
        
        if not is_owner and not has_admin:
            print(f"权限检查失败: 用户 {current_user.id} 无权删除项目 {project_id}")
            return jsonify({'success': False, 'error': '无权删除此项目，只有项目创建者或管理员可以删除'}), 403
        print("权限检查通过")
        
        print(f"项目信息: ID={project.id}, 名称={project.name}")
        project_name = project.name
        
        # 手动删除所有关联数据
        print("开始删除关联数据...")
        
        from sqlalchemy import text
        
        # 使用原生 SQL 删除，避免 SQLAlchemy 关系行为干扰
        
        # 删除关联的 BadCase
        result = db.session.execute(text("DELETE FROM bad_case WHERE project_id = :pid"), {"pid": project_id})
        print(f"删除 {result.rowcount} 个 BadCase...")
        
        # 删除关联的 TestCase
        result = db.session.execute(text("DELETE FROM test_case WHERE project_id = :pid"), {"pid": project_id})
        print(f"删除 {result.rowcount} 个 TestCase...")
        
        # 删除关联的 Bug（包括关联到该项目下所有 Plan 的 Bug）
        result = db.session.execute(text("""
            DELETE FROM bug WHERE project_id = :pid OR plan_id IN (
                SELECT id FROM plan WHERE project_id = :pid
            )
        """), {"pid": project_id})
        print(f"删除 {result.rowcount} 个 Bug...")
        
        # 删除关联的 Plan
        result = db.session.execute(text("DELETE FROM plan WHERE project_id = :pid"), {"pid": project_id})
        print(f"删除 {result.rowcount} 个 Plan...")
        
        # 删除关联的 Team
        teams = Team.query.filter_by(project_id=project_id).all()
        print(f"删除 {len(teams)} 个 Team...")
        for team in teams:
            # 删除团队成员
            TeamMember.query.filter_by(team_id=team.id).delete()
            db.session.delete(team)
        
        # 删除关联的 ProjectPermission
        permissions = ProjectPermission.query.filter_by(project_id=project_id).all()
        print(f"删除 {len(permissions)} 个 ProjectPermission...")
        for perm in permissions:
            db.session.delete(perm)
        
        # 最后删除项目本身
        print("删除项目本身...")
        db.session.delete(project)
        print(f"项目已标记删除: {project_name}")
        
        # 提交到数据库
        print("提交数据库更改...")
        db.session.commit()
        print("数据库提交成功")
        
        response_data = {
            'success': True,
            'message': f'项目 "{project_name}" 删除成功'
        }
        print(f"返回响应: {response_data}")
        print(f"=== 项目 {project_id} 删除完成 ===")
        _redis_cache_invalidate_project(project_id)
        _redis_cache_invalidate_projects(current_user.id)
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"删除项目时发生错误: {str(e)}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        print(f"错误堆栈: {traceback.format_exc()}")
        db.session.rollback()
        print("数据库回滚完成")
        return jsonify({'success': False, 'error': str(e)}), 500

# API端点 - BadCase管理
@projects_api_bp.route('/api/badcases', methods=['POST'])
