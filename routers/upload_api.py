"""upload_api（自 app.py 拆出）。"""
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

upload_bp = Blueprint("upload", __name__)


def _app():
    import app as _application
    return _application


@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '未选择文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400
    if file and allowed_file(file.filename):
        # 检查文件大小
        file.seek(0, 2)  # 移动到文件末尾
        file_size = file.tell()
        file.seek(0)  # 重置到文件开头
        
        if file_size > MINIO_CONFIG['max_file_size']:
            return jsonify({'error': f'文件大小超过限制 ({MINIO_CONFIG["max_file_size"] // 1024 // 1024}MB)'}), 400
        
        # 上传到MinIO
        result = upload_file_to_minio(file)
        
        if result['success']:
            return jsonify({
                'success': True,
                'url': result['url'],
                'filename': result['filename'],
                'path': result['path']
            })
        else:
            return jsonify({'error': result['error']}), 500
    else:
        return jsonify({'error': '文件类型不被允许'}), 400


@upload_bp.route('/api/upload', methods=['POST'])
@login_required
def api_upload_file():
    """富文本附件上传：走 /api 前缀以便 Vite 代理与 axios 同源带 Cookie。"""
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

    return upload_file()


@upload_bp.route('/api/uploads/image/<path:file_path>', methods=['GET'])
@login_required
def api_get_upload_image(file_path):
    """富文本/附件图片：经后端从 MinIO 拉取，避免浏览器直连私有桶失败。"""
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
        decoded_path = unquote(file_path).strip().lstrip('/')
        if not decoded_path or '..' in decoded_path.split('/'):
            return jsonify({'error': '无效路径'}), 400

        saas_prefix = (MINIO_CONFIG['saas_file_path'] or '').strip().lstrip('/')
        if saas_prefix and not decoded_path.startswith(saas_prefix):
            full_path = f"{MINIO_CONFIG['saas_file_path']}{decoded_path}"
        else:
            full_path = decoded_path

        cache_key = get_upload_image_cache_key(full_path)
        cached_image_data = get_image_from_cache(cache_key)
        if cached_image_data:
            image_data = cached_image_data
        else:
            client = get_minio_client()
            try:
                client.head_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
            except ClientError as e:
                if e.response.get('Error', {}).get('Code') in ('404', 'NoSuchKey', 'NotFound'):
                    return jsonify({'error': '文件不存在'}), 404
                raise

            raw = client.get_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
            image_data = read_minio_object_bytes(raw)

        lower = decoded_path.lower()
        mime_type = mimetypes.guess_type(decoded_path)[0] or 'application/octet-stream'
        if lower.endswith('.png'):
            mime_type = 'image/png'
        elif lower.endswith('.gif'):
            mime_type = 'image/gif'
        elif lower.endswith('.webp'):
            mime_type = 'image/webp'
        elif lower.endswith(('.jpg', '.jpeg')):
            mime_type = 'image/jpeg'

        if not cached_image_data and mime_type.startswith('image/'):
            set_image_to_cache(cache_key, image_data, 3600)

        resp = app.response_class(image_data, status=200, mimetype=mime_type)
        resp.headers['Cache-Control'] = 'private, max-age=3600'
        resp.headers['Content-Type'] = mime_type
        return resp
    except ClientError as e:
        print(f"获取上传图片失败: {e}")
        return jsonify({'error': '获取图片失败'}), 500
    except Exception as e:
        print(f"获取上传图片异常: {e}")
        return jsonify({'error': '服务器内部错误'}), 500


# 项目头像上传
@upload_bp.route('/api/upload/avatar', methods=['POST'])
@login_required
def api_upload_avatar():
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

    print("=== 开始头像上传 ===")
    
    if 'file' not in request.files:
        print("错误: 未选择文件")
        return jsonify({'success': False, 'error': '未选择文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        print("错误: 文件名为空")
        return jsonify({'success': False, 'error': '未选择文件'}), 400
    
    print(f"接收到的文件: {file.filename}, 大小: {file.content_length if hasattr(file, 'content_length') else '未知'}")
    
    # 只允许图片文件
    allowed_image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
    if not (file and '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_image_extensions):
        print(f"错误: 不支持的文件类型 {file.filename}")
        return jsonify({'success': False, 'error': '只支持图片文件'}), 400
    
    # 检查文件大小 - 头像文件限制为5MB
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    
    print(f"文件大小: {file_size} 字节")
    
    # 头像文件大小限制为1MB
    max_avatar_size = 1 * 1024 * 1024  # 1MB
    if file_size > max_avatar_size:
        print(f"错误: 头像文件大小超过限制")
        return jsonify({'success': False, 'error': f'头像文件大小不能超过1MB，当前大小: {file_size // 1024 // 1024}MB'}), 400
    
    # 压缩头像图片
    print("开始压缩头像图片...")
    compressed_file = compress_image(file, max_size=(800, 800), quality=85)
    original_size = file_size
    compressed_file.seek(0, 2)
    compressed_size = compressed_file.tell()
    compressed_file.seek(0)
    
    print(f"图片压缩完成: {original_size} -> {compressed_size} 字节 (压缩率: {((original_size - compressed_size) / original_size * 100):.1f}%)")
    
    # 上传到MinIO的avatar文件夹
    print("开始上传到MinIO...")
    start_time = datetime.now()
    result = upload_file_to_minio(compressed_file, 'avatar')
    end_time = datetime.now()
    upload_duration = (end_time - start_time).total_seconds()
    
    print(f"上传耗时: {upload_duration:.2f}秒")
    print(f"上传结果: {result}")
    
    if result['success']:
        print(f"头像上传成功，URL: {result['url']}")
        return jsonify({
            'success': True,
            'url': result['url'],
            'filename': result['filename'],
            'path': result['path'],
            'upload_time': upload_duration
        })
    else:
        print(f"头像上传失败: {result['error']}")
        return jsonify({'success': False, 'error': result['error']}), 500

# 获取头像URL的API端点（带防盗刷）
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

@upload_bp.route('/api/avatar/<path:file_path>', methods=['GET'])
@login_required  # 需要登录才能获取头像URL
def api_get_avatar(file_path):
    """动态获取头像URL，支持预签名URL，带防盗刷功能"""
    try:
        # 检查访问频率限制
        if not check_avatar_access_rate(current_user.id):
            print(f"用户 {current_user.id} 头像访问频率过高，疑似盗刷")
            return jsonify({
                'success': False,
                'error': '访问频率过高，请稍后再试'
            }), 429  # Too Many Requests
        
        # 检查用户权限 - 只有项目成员才能访问项目头像
        import urllib.parse
        decoded_path = urllib.parse.unquote(file_path)
        
        # 从文件名中提取项目ID进行权限检查
        filename_parts = decoded_path.split('_')
        if len(filename_parts) >= 3 and filename_parts[0] == 'project':
            try:
                project_id = int(filename_parts[1])
                # 检查用户是否有权限访问该项目
                if not has_project_permission(current_user.id, project_id):
                    print(f"用户 {current_user.id} 尝试访问无权限的项目 {project_id} 的头像")
                    return jsonify({
                        'success': False,
                        'error': '无权限访问该头像'
                    }), 403
            except (ValueError, IndexError):
                # 如果无法解析项目ID，记录警告但允许访问
                print(f"警告: 无法从文件名 {decoded_path} 解析项目ID")
        else:
            # 如果文件名格式不符合预期，记录警告
            print(f"警告: 头像文件名格式异常: {decoded_path}")
        
        # 构建完整的MinIO路径
        full_path = f"{MINIO_CONFIG['saas_file_path']}avatar/{decoded_path}"
        
        # 检查文件是否存在
        client = get_minio_client()
        try:
            client.head_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return jsonify({
                    'success': False,
                    'error': '头像文件不存在'
                }), 404
            else:
                raise e
        
        # 生成新的预签名URL，设置较长的有效期以支持浏览器缓存
        presigned_url = client.generate_presigned_url(
            'get_object',
            Params={'Bucket': MINIO_CONFIG['bucket_name'], 'Key': full_path},
            ExpiresIn=86400  # 24小时有效期，支持浏览器缓存
        )
        
        # 记录访问日志
        print(f"用户 {current_user.id} ({current_user.email}) 访问头像: {decoded_path}")
        
        return jsonify({
            'success': True,
            'url': presigned_url
        })
        
    except Exception as e:
        print(f"获取头像URL失败: {e}")
        return jsonify({
            'success': False,
            'error': f'获取头像URL失败: {str(e)}'
        }), 500

# 获取头像图片数据的API端点（带Redis缓存）
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

@upload_bp.route('/api/avatar/image/<path:file_path>', methods=['GET'])
@login_required  # 需要登录才能获取头像
def api_get_avatar_image(file_path):
    """获取头像图片数据，支持Redis缓存，10分钟有效期"""
    try:
        # 速率限制检查
        if not check_avatar_access_rate(current_user.id):
            return jsonify({'error': '访问过于频繁，请稍后再试'}), 429
        
        # URL解码文件名
        decoded_path = unquote(file_path)
        print(f"用户 {current_user.id} ({current_user.email}) 请求头像图片: {decoded_path}")
        
        # 生成缓存键
        cache_key = get_image_cache_key(decoded_path)
        
        # 尝试从Redis缓存获取图片数据
        cached_image_data = get_image_from_cache(cache_key)
        if cached_image_data:
            print(f"从Redis缓存返回头像: {decoded_path}")
            response = app.response_class(
                cached_image_data,
                status=200,
                mimetype='image/jpeg'  # Default MIME type
            )
            response.headers['Cache-Control'] = 'public, max-age=600'  # Browser cache 10 minutes
            return response
        
        # Cache miss, fetch from MinIO
        print(f"从MinIO获取头像: {decoded_path}")
        full_path = f"{MINIO_CONFIG['saas_file_path']}avatar/{decoded_path}"
        
        client = get_minio_client()
        response = client.get_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
        image_data = response.read()
        response.close()
        
        # Cache image data to Redis, 10 minutes expiry
        set_image_to_cache(cache_key, image_data, 600)
        
        # Determine MIME type and return response
        mime_type = 'image/jpeg'  # Default
        if decoded_path.lower().endswith('.png'):
            mime_type = 'image/png'
        elif decoded_path.lower().endswith('.gif'):
            mime_type = 'image/gif'
        elif decoded_path.lower().endswith('.webp'):
            mime_type = 'image/webp'
        
        response = app.response_class(
            image_data,
            status=200,
            mimetype=mime_type
        )
        response.headers['Cache-Control'] = 'public, max-age=600'  # Browser cache 10 minutes
        response.headers['Content-Type'] = mime_type
        
        print(f"用户 {current_user.id} ({current_user.email}) 访问头像图片: {decoded_path}")
        
        return response
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            print(f"头像文件不存在: {decoded_path}")
            return jsonify({'error': '头像文件不存在'}), 404
        else:
            print(f"获取头像失败: {e}")
            return jsonify({'error': '获取头像失败'}), 500
    except Exception as e:
        print(f"获取头像时发生错误: {e}")
        return jsonify({'error': '服务器内部错误'}), 500

@upload_bp.route('/api/avatar/base64/<path:file_path>', methods=['GET'])
def api_get_avatar_base64(file_path):
    """获取头像图片的base64数据，支持Redis缓存，10分钟有效期"""
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
        # 移除速率限制检查，允许匿名访问
        
        # URL解码文件名
        decoded_path = unquote(file_path)
        
        # 生成缓存键
        cache_key = get_image_cache_key(decoded_path)
        
        # 尝试从Redis缓存获取图片数据
        redis_client = get_redis_client()
        cached_image_data = get_image_from_cache(cache_key)
        if cached_image_data:
            # 转换为base64
            base64_data = base64.b64encode(cached_image_data).decode('utf-8')
            
            # 确定MIME类型
            mime_type = 'image/jpeg'  # Default
            if decoded_path.lower().endswith('.png'):
                mime_type = 'image/png'
            elif decoded_path.lower().endswith('.gif'):
                mime_type = 'image/gif'
            elif decoded_path.lower().endswith('.webp'):
                mime_type = 'image/webp'
            
            return jsonify({
                'data': f'data:{mime_type};base64,{base64_data}',
                'cached': True
            })
        
        # Cache miss, fetch from MinIO
        full_path = f"{MINIO_CONFIG['saas_file_path']}avatar/{decoded_path}"
        
        client = get_minio_client()
        response = client.get_object(Bucket=MINIO_CONFIG['bucket_name'], Key=full_path)
        
        # 检查响应类型并获取正确的文件对象
        if isinstance(response, dict):
            if 'Body' in response:
                file_obj = response['Body']
            else:
                raise Exception(f"MinIO响应缺少Body字段")
        elif hasattr(response, 'read'):
            file_obj = response
        else:
            raise Exception(f"MinIO响应类型不支持: {type(response)}")
        
        image_data = file_obj.read()
        file_obj.close()
        
        # Cache image data to Redis, 10 minutes expiry
        set_image_to_cache(cache_key, image_data, 600)
        
        # 转换为base64
        base64_data = base64.b64encode(image_data).decode('utf-8')
        
        # 确定MIME类型
        mime_type = 'image/jpeg'  # Default
        if decoded_path.lower().endswith('.png'):
            mime_type = 'image/png'
        elif decoded_path.lower().endswith('.gif'):
            mime_type = 'image/gif'
        elif decoded_path.lower().endswith('.webp'):
            mime_type = 'image/webp'
        
        return jsonify({
            'data': f'data:{mime_type};base64,{base64_data}',
            'cached': False
        })
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return jsonify({'error': '头像文件不存在'}), 404
        else:
            print(f"MinIO错误: {e}")
            return jsonify({'error': '获取头像失败'}), 500
    except Exception as e:
        print(f"获取头像时发生未知错误: {e}")
        return jsonify({'error': '服务器内部错误'}), 500

# 测试MinIO连接
@upload_bp.route('/api/test/minio', methods=['GET'])
@login_required
def api_test_minio():
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
        client = get_minio_client()
        
        # 测试列出存储桶中的对象
        response = client.list_objects_v2(
            Bucket=MINIO_CONFIG['bucket_name'],
            MaxKeys=5
        )
        
        objects = []
        if 'Contents' in response:
            for obj in response['Contents']:
                objects.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat()
                })
        
        return jsonify({
            'success': True,
            'bucket': MINIO_CONFIG['bucket_name'],
            'endpoint': MINIO_CONFIG['endpoint'],
            'objects': objects,
            'message': 'MinIO连接正常'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'MinIO连接失败: {str(e)}'
        }), 500

# 获取项目成员及角色
@upload_bp.route('/api/project/<int:project_id>/members', methods=['GET'])
@login_required
def api_project_members(project_id):
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
    project = Project.query.get_or_404(project_id)
    if not has_project_permission(current_user.id, project_id):
        return jsonify({'success': False, 'error': '无权访问'}), 403
    
    # 使用 JOIN 一次性查询，避免 N+1 问题
    rows = (
        db.session.query(User.id, User.name, User.email, ProjectPermission.role)
        .join(ProjectPermission, User.id == ProjectPermission.user_id)
        .filter(ProjectPermission.project_id == project_id)
        .all()
    )
    
    members = [{'id': r.id, 'name': r.name, 'email': r.email, 'role': r.role} for r in rows]
    
    t_total = (time.perf_counter() - t0) * 1000
    print(f"[PERF] GET /api/project/{project_id}/members total={t_total:.1f}ms count={len(members)}", flush=True)
    return jsonify({'success': True, 'data': members})

# 邀请成员
@upload_bp.route('/api/project/<int:project_id>/invite', methods=['POST'])
@login_required
def api_invite_user(project_id):
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

    project = Project.query.get_or_404(project_id)
    if not has_project_permission(current_user.id, project_id, 'admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403
    data = request.get_json()
    email = data.get('email')
    role = data.get('role', 'collaborator')
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404
    existing_permission = ProjectPermission.query.filter_by(project_id=project_id, user_id=user.id).first()
    if existing_permission:
        return jsonify({'success': False, 'error': '用户已有项目权限'}), 400
    permission = ProjectPermission(project_id=project_id, user_id=user.id, role=role)
    db.session.add(permission)
    db.session.commit()
    _redis_cache_invalidate_project(project_id)
    return jsonify({'success': True})

# 移除成员
@upload_bp.route('/api/project/<int:project_id>/remove_user', methods=['POST'])
@login_required
def api_remove_user(project_id):
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

    project = Project.query.get_or_404(project_id)
    if not has_project_permission(current_user.id, project_id, 'admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403
    data = request.get_json()
    user_id = data.get('user_id')
    permission = ProjectPermission.query.filter_by(project_id=project_id, user_id=user_id).first()
    if permission:
        db.session.delete(permission)
        db.session.commit()
    _redis_cache_invalidate_project(project_id)
    return jsonify({'success': True})

# 修改成员角色
@upload_bp.route('/api/project/<int:project_id>/change_role', methods=['POST'])
@login_required
def api_change_role(project_id):
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

    project = Project.query.get_or_404(project_id)
    if not has_project_permission(current_user.id, project_id, 'admin'):
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403
    data = request.get_json()
    user_id = data.get('user_id')
    new_role = data.get('role')
    permission = ProjectPermission.query.filter_by(project_id=project_id, user_id=user_id).first()
    if not permission:
        return jsonify({'success': False, 'error': '用户无项目权限'}), 404
    permission.role = new_role
    db.session.commit()
    _redis_cache_invalidate_project(project_id)
    return jsonify({'success': True})

# 获取所有可邀请用户（不在该项目的已注册用户）
@upload_bp.route('/api/users', methods=['GET'])
@login_required
def api_all_users():
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

    project_id = request.args.get('project_id', type=int)
    users = User.query.filter(User.is_verified==True).all()
    if project_id:
        permissions = ProjectPermission.query.filter_by(project_id=project_id).all()
        member_ids = {p.user_id for p in permissions}
        users = [u for u in users if u.id not in member_ids]
    user_list = [{'id': u.id, 'name': u.name, 'email': u.email} for u in users]
    return jsonify({'success': True, 'data': user_list})

@upload_bp.route('/api/import/excel', methods=['POST'])
@login_required
def api_import_excel():
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

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有选择文件'}), 400
    file = request.files['file']
    project_id = request.form.get('project_id')
    if not project_id:
        return jsonify({'success': False, 'error': '缺少project_id'}), 400
    if not has_project_permission(current_user.id, project_id):
        return jsonify({'success': False, 'error': '无权访问此项目'}), 403
    if file.filename == '' or not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'error': '文件格式错误'}), 400
    try:
        df = pd.read_excel(file)
        success_count = 0
        fail_count = 0
        fail_rows = []
        for idx, row in df.iterrows():
            try:
                badcase = BadCase(
                    project_id=project_id,
                    creator_id=current_user.id,
                    case_category=row.get('case_category', ''),
                    base_problem=row.get('base_problem', ''),
                    badcase_result=row.get('badcase_result', ''),
                    answer=row.get('answer', row.get('correct_answer', '')),
                    correct_answer=row.get('correct_answer', ''),
                    problem_reason=row.get('problem_reason', ''),
                    needs_processing=row.get('needs_processing', True),
                    priority=row.get('priority', 'p3')
                )
                db.session.add(badcase)
                success_count += 1
            except Exception as e:
                fail_count += 1
                fail_rows.append({'row': idx+2, 'error': str(e)})
        db.session.commit()
        return jsonify({'success': True, 'imported': success_count, 'failed': fail_count, 'fail_rows': fail_rows})
    except Exception as e:
        return jsonify({'success': False, 'error': f'导入失败: {str(e)}'}), 500

@upload_bp.route('/api/import/database', methods=['POST'])
@login_required
def api_import_database():
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

    data = request.json if request.is_json else request.form
    host = data.get('host')
    port = data.get('port')
    database_name = data.get('database')
    username = data.get('username')
    password = data.get('password')
    table_name = data.get('table_name')
    project_id = data.get('project_id')
    if not all([host, port, database_name, username, password, table_name, project_id]):
        return jsonify({'success': False, 'error': '参数不完整'}), 400
    if not has_project_permission(current_user.id, project_id):
        return jsonify({'success': False, 'error': '无权访问此项目'}), 403
    try:
        connection = pymysql.connect(
            host=host,
            port=int(port),
            user=username,
            password=password,
            database=database_name
        )
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql(query, connection)
        connection.close()
        success_count = 0
        fail_count = 0
        fail_rows = []
        for idx, row in df.iterrows():
            try:
                badcase = BadCase(
                    project_id=project_id,
                    creator_id=current_user.id,
                    case_category=row.get('case_category', ''),
                    base_problem=row.get('base_problem', ''),
                    badcase_result=row.get('badcase_result', ''),
                    answer=row.get('answer', row.get('correct_answer', '')),
                    correct_answer=row.get('correct_answer', ''),
                    problem_reason=row.get('problem_reason', ''),
                    needs_processing=row.get('needs_processing', True),
                    priority=row.get('priority', 'p3')
                )
                db.session.add(badcase)
                success_count += 1
            except Exception as e:
                fail_count += 1
                fail_rows.append({'row': idx+2, 'error': str(e)})
        db.session.commit()
        return jsonify({'success': True, 'imported': success_count, 'failed': fail_count, 'fail_rows': fail_rows})
    except Exception as e:
        return jsonify({'success': False, 'error': f'数据库导入失败: {str(e)}'}), 500

# API端点 - 用户认证
