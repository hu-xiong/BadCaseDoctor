"""auth_api（自 app.py 拆出）。"""
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

auth_api_bp = Blueprint("auth_api", __name__)


def _app():
    import app as _application
    return _application


def api_login():
    try:
        start_time = time.time()
        print(f"\n[LOGIN] === 开始处理登录请求 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
        
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        print(f"[LOGIN] 收到请求: email={email}")
        
        if not email or not password:
            print("[LOGIN] 错误: 邮箱或密码为空")
            return jsonify({'success': False, 'error': '邮箱和密码不能为空'}), 400
        
        print("[LOGIN] 正在查询数据库...")
        db_start = time.time()
        user = User.query.filter_by(email=email).first()
        print(f"[LOGIN] 数据库查询耗时: {time.time() - db_start:.4f}s")
        
        if user:
            print("[LOGIN] 用户存在，正在校验密码...")
            pwd_start = time.time()
            is_valid = check_password_hash(user.password_hash, password)
            print(f"[LOGIN] 密码校验耗时: {time.time() - pwd_start:.4f}s")
            
            if is_valid:
                print(f"[LOGIN] 校验成功，正在执行 login_user(id={user.id})...")
                login_user(user)

                project_id = None
                try:
                    from utils.project_clone import resolve_user_default_project
                    project_id, _ = resolve_user_default_project(int(user.id))
                except Exception as e:
                    print(f"[LOGIN] 获取默认项目失败: {e}")

                print(f"[LOGIN] === 登录处理成功，总耗时: {time.time() - start_time:.4f}s ===\n")
                return jsonify({
                    'success': True, 
                    'user': {
                        'id': user.id,
                        'email': user.email,
                        'name': user.name,
                        'role': user.role
                    },
                    'project_id': project_id,
                })
            else:
                print("[LOGIN] 错误: 密码校验失败")
        else:
            print(f"[LOGIN] 错误: 未找到该用户 ({email})")
            
        print(f"[LOGIN] === 登录处理结束 (401)，总耗时: {time.time() - start_time:.4f}s ===\n")
        return jsonify({'success': False, 'error': '邮箱或密码错误'}), 401
    except Exception as e:
        print(f"[LOGIN] !!! 发生异常: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': '服务器内部错误'}), 500

@auth_api_bp.route('/api/register', methods=['POST'])
def api_register():
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

    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    verification_code = data.get('verification_code')
    
    if not all([email, password, name, verification_code]):
        return jsonify({'success': False, 'error': '所有字段都是必填的'}), 400
    
    # 检查邮箱是否已存在
    existing_user = User.query.filter_by(email=email).first()
    if existing_user and existing_user.is_verified:
        return jsonify({'success': False, 'error': '邮箱已被注册'}), 400
    
    # 验证验证码
    user = User.query.filter_by(email=email, verification_code=verification_code).first()
    if not user or user.verification_expires < datetime.utcnow():
        return jsonify({'success': False, 'error': '验证码无效或已过期'}), 400
    
    # 更新用户信息
    user.password_hash = generate_password_hash(password)
    user.name = name
    user.is_verified = True
    user.verification_code = None
    user.verification_expires = None
    
    db.session.commit()
    login_user(user)

    project_id = None
    try:
        from utils.project_clone import resolve_user_default_project, ensure_default_plan_for_project

        project_id, _ = resolve_user_default_project(int(user.id))
        ensure_default_plan_for_project(int(project_id), int(user.id))
        db.session.commit()
        a._redis_cache_invalidate_projects(user.id)
    except Exception as e:
        db.session.rollback()
        print(f"[REGISTER] 默认项目初始化失败: {e}")

    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'role': user.role
        },
        'project_id': project_id,
    })

@auth_api_bp.route('/api/user', methods=['GET'])
@login_required
def api_get_user():
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

    return jsonify({
        'success': True,
        'user': {
            'id': current_user.id,
            'email': current_user.email,
            'name': current_user.name,
            'role': current_user.role
        }
    })

@auth_api_bp.route('/api/send_verification_code', methods=['POST'])
def api_send_verification_code():
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

    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'success': False, 'error': '邮箱不能为空'}), 400
    
    # 生成验证码
    verification_code = generate_verification_code()
    expires = datetime.utcnow() + timedelta(minutes=10)
    
    # 检查用户是否已存在
    user = User.query.filter_by(email=email).first()
    if user:
        # 更新现有用户的验证码
        user.verification_code = verification_code
        user.verification_expires = expires
    else:
        # 创建新用户
        user = User(
            email=email,
            verification_code=verification_code,
            verification_expires=expires
        )
        db.session.add(user)
    
    db.session.commit()
    
    # 发送邮件
    try:
        send_email(
            to=email,
            subject='BadCase Doctor - 邮箱验证码',
            body=f'您的验证码是: {verification_code}，有效期10分钟。'
        )
        return jsonify({'success': True, 'message': '验证码已发送'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'发送邮件失败: {str(e)}'}), 500


def _safe_parse_project_login_configs(raw):
    """解析 project.login_configs；迁移/脏数据下可能不是合法 JSON，避免拖垮项目详情接口。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    s = str(raw).strip()
    if not s:
        return []
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            return [v]
        return []
    except (json.JSONDecodeError, TypeError, ValueError):
        print(f"[_safe_parse_project_login_configs] 无效 JSON，已置空 preview={s[:160]!r}")
        return []


# API端点 - 项目管理
