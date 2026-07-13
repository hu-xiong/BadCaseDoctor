"""badcases_api（自 app.py 拆出）。"""
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

badcases_api_bp = Blueprint("badcases_api", __name__)


def _app():
    import app as _application
    return _application


@login_required
def api_create_badcase():
    print("=== 创建BadCase ===")
    print(f"当前用户ID: {current_user.id}")
    
    try:
        data = request.get_json()
        print(f"请求数据: {data}")
        
        if not data:
            return jsonify({'success': False, 'error': '请求数据格式错误'}), 400
        
        project_id = data.get('project_id')
        title = data.get('title')
        case_category = data.get('case_category')
        base_problem = (data.get('base_problem') or '').strip()
        badcase_result = data.get('badcase_result')
        answer = data.get('answer')
        correct_answer = data.get('correct_answer')
        
        # 检查必要字段
        missing_fields = []
        if not project_id:
            missing_fields.append('project_id')
        if not title:
            missing_fields.append('title')
        if not case_category:
            missing_fields.append('case_category')
        if not badcase_result:
            missing_fields.append('badcase_result')
        if not answer:
            missing_fields.append('answer')
            
        if missing_fields:
            return jsonify({
                'success': False, 
                'error': f'缺少必要字段: {", ".join(missing_fields)}'
            }), 400
        
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权在此项目中创建BadCase'}), 403
        
        # 如果提供了 card_id，按卡片类型校验（卡片分类型，计划不分类型）
        raw_card = data.get('card_id')
        card_id_val = None
        if raw_card is not None and str(raw_card).strip() != '':
            try:
                ci = int(raw_card)
                if ci != 0:
                    card_id_val = ci
            except (TypeError, ValueError):
                card_id_val = None
        
        if card_id_val is not None:
            # 按卡片类型校验
            card = Card.query.get(card_id_val)
            if not card:
                return jsonify({'success': False, 'error': '卡片不存在'}), 404
            # 检查卡片类型是否为 badcase
            card_type_value = card.type.value if hasattr(card.type, 'value') else str(card.type)
            if card_type_value != 'badcase':
                return jsonify({'success': False, 'error': '只能在badcase类型卡片中创建badcase'}), 400
        
        # 处理附件数据
        import json
        attachments_json = json.dumps(data.get('attachments', [])) if data.get('attachments') else None
        
        _pid = data.get('plan_id')
        if _pid in (None, '', 0, '0'):
            _pid = None
        else:
            try:
                _pid = int(_pid)
            except (TypeError, ValueError):
                _pid = None
        # 兼容旧前端：只把所选迭代写在 plan（字符串数字）里、未传 plan_id
        if _pid is None:
            _legacy = data.get('plan')
            if _legacy not in (None, '', 'unplanned'):
                s = str(_legacy).strip()
                if s.isdigit():
                    try:
                        _pid = int(s)
                    except ValueError:
                        _pid = None

        badcase = BadCase(
            project_id=project_id,
            plan_id=_pid,
            card_id=card_id_val,
            creator_id=current_user.id,
            title=title,
            case_category=case_category,
            base_problem=base_problem,
            reproduction_steps=data.get('reproduction_steps', ''),
            badcase_result=badcase_result,
            answer=answer,
            correct_answer=correct_answer or '',
            problem_reason=data.get('problem_reason', ''),
            solution=data.get('solution', ''),
            priority=data.get('priority', 'p3'),
            status=data.get('status', 'new'),
            assignee=data.get('assignee', ''),
            plan=data.get('plan', ''),
            document_type=data.get('document_type', '其他文档'),
            attachments=attachments_json,
            assigned_users=data.get('assigned_users', '')
        )
        
        db.session.add(badcase)
        db.session.commit()
        db.session.refresh(badcase)
        _cache_invalidate_plans(project_id)

        linked_cid = ensure_badcase_card_link(badcase, auto_create=(card_id_val is None))
        if linked_cid is None and card_id_val is not None:
            print(
                f"[api_create_badcase] 警告: 已传 card_id={card_id_val} 但未能建立双向关联，"
                f"badcase id={badcase.id}",
                flush=True,
            )
        
        print(f"BadCase创建成功，ID: {badcase.id}, card_id: {getattr(badcase, 'card_id', None)}")
        try:
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_badcase(badcase), badcase.creator_id
            )
            _schedule_workflow_notify(
                "created",
                "badcase",
                badcase.id,
                badcase.title or "",
                badcase.project_id,
                _workflow_project_name(badcase.project_id),
                _badcase_status_str(badcase),
                None,
                _rec,
                actor_id=current_user.id,
                actor_name=getattr(current_user, "name", "") or "",
            )
        except Exception as _e:
            print(f"[workflow_notify] BadCase 创建通知调度失败: {_e}")

        _schedule_grep_work_item_index("badcase", badcase.id)

        return jsonify({
            'success': True,
            'badcase': {
                'id': _json_snowflake_id(badcase.id),
                'title': badcase.title,
                'project_id': badcase.project_id,
                'plan_id': _json_snowflake_id(badcase.plan_id),
                'card_id': _json_snowflake_id(getattr(badcase, 'card_id', None)),
                'creator_id': badcase.creator_id,
                'case_category': badcase.case_category,
                'base_problem': badcase.base_problem,
                'badcase_result': badcase.badcase_result,
                'answer': badcase.answer,
                'correct_answer': badcase.correct_answer,
                'priority': badcase.priority,
                'status': badcase.status.value if hasattr(badcase.status, 'value') else badcase.status,
                'assignee': badcase.assignee,
                'plan': badcase.plan,
                'created_at': badcase.created_at.isoformat()
            }
        })
        
    except Exception as e:
        import traceback
        print(f"创建BadCase失败: {e}")
        print(f"错误堆栈: {traceback.format_exc()}")
        db.session.rollback()
        return jsonify({'success': False, 'error': f'创建BadCase失败: {str(e)}'}), 500

@badcases_api_bp.route('/api/badcases/<int:badcase_id>', methods=['GET'])
@login_required
def api_get_badcase_detail(badcase_id):
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

    badcase, access_err = _model_for_user_collaborator_access(BadCase, badcase_id, current_user.id)
    if access_err == 'not_found':
        return jsonify({'success': False, 'error': 'BadCase不存在'}), 404
    if access_err == 'forbidden':
        return jsonify({'success': False, 'error': '无权访问此BadCase'}), 403
    
    # 评论 + 用户名一次 JOIN；负责人姓名仍按需补查（常与评论用户不重叠）
    comment_rows = (
        db.session.query(
            Comment.id,
            Comment.content,
            Comment.user_id,
            Comment.created_at,
            Comment.source_message_id,
            User.name,
        )
        .outerjoin(User, User.id == Comment.user_id)
        .filter(Comment.badcase_id == badcase_id)
        .order_by(Comment.created_at.asc())
        .all()
    )
    
    # 解析附件数据
    import json
    attachments = []
    if badcase.attachments:
        try:
            attachments = json.loads(badcase.attachments)
        except:
            attachments = []
    
    # 解析负责人字段（支持单个/逗号分隔 ID），并批量查 user_map，避免 N+1
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

    assignee_ids = _parse_assignee_ids(badcase.assignee)
    assignee_id = assignee_ids[0] if assignee_ids else None

    user_name_map = {}
    for (_cid, _content, uid, _dt, uname) in comment_rows:
        if uid and uid not in user_name_map:
            user_name_map[uid] = uname or ''
    missing_assignee = set(assignee_ids) - set(user_name_map.keys())
    if missing_assignee:
        rows = db.session.query(User.id, User.name).filter(User.id.in_(list(missing_assignee))).all()
        for uid, name in rows:
            user_name_map[uid] = name or ''

    if assignee_ids:
        first_name = user_name_map.get(assignee_ids[0])
        if first_name:
            assignee_name = first_name if len(assignee_ids) == 1 else f"{first_name}..."
        else:
            assignee_name = str(badcase.assignee)
    else:
        assignee_name = str(badcase.assignee) if badcase.assignee else ''

    if _try_repair_badcase_plan_id_from_legacy_plan_string(badcase):
        db.session.commit()
        _cache_invalidate_plans(badcase.project_id)

    if _try_repair_badcase_card_id_from_source_card(badcase):
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"[BadCase详情] card_id 反查补写失败: {e}", flush=True)

    return jsonify({
        'success': True,
        'badcase': {
            'id': _json_snowflake_id(badcase.id),
            'project_id': badcase.project_id,  # 添加项目ID字段
            'plan_id': _json_snowflake_id(badcase.plan_id),
            'card_id': _json_snowflake_id(getattr(badcase, 'card_id', None)),
            'title': badcase.title,
            'case_category': badcase.case_category,
            'base_problem': badcase.base_problem,
            'reproduction_steps': badcase.reproduction_steps,
            'badcase_result': badcase.badcase_result,
            'answer': badcase.answer,
            'correct_answer': badcase.correct_answer,
            'problem_reason': badcase.problem_reason,
            'solution': badcase.solution,
            'priority': badcase.priority,
            'status': badcase.status.value if hasattr(badcase.status, 'value') else badcase.status,  # 枚举类型转换为值
            'assignee': assignee_name,  # 用户名用于显示
            'assignee_id': assignee_id,  # 用户ID用于下拉框选中
            'plan': badcase.plan,
            'document_type': badcase.document_type,
            'attachments': attachments,
            'assigned_users': badcase.assigned_users,
            'created_at': badcase.created_at.isoformat(),
            'updated_at': badcase.updated_at.isoformat(),
            'comments': [{
                'id': cid,
                'content': content,
                'user_id': uid,
                'user_name': uname or '',
                'source_message_id': smid,
                'created_at': created_at.isoformat()
            } for (cid, content, uid, created_at, smid, uname) in comment_rows]
        }
    })

@badcases_api_bp.route('/api/badcases/<int:badcase_id>/status', methods=['POST'])
@login_required
def api_update_badcase_status(badcase_id):
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

    badcase = BadCase.query.get_or_404(badcase_id)
    
    if not has_project_permission(current_user.id, badcase.project_id):
        return jsonify({'success': False, 'error': '无权操作此BadCase'}), 403
    
    data = request.get_json()
    status = data.get('status')
    assigned_users = data.get('assigned_users')
    old_status = _badcase_status_str(badcase)
    
    if status:
        badcase.status = status
    if assigned_users is not None:
        badcase.assigned_users = assigned_users
    
    db.session.commit()
    new_status = _badcase_status_str(badcase)
    try:
        _rec = _workflow_merge_creator_if_empty(
            _workflow_recipients_badcase(badcase), badcase.creator_id
        )
        _ev = (
            "status_changed"
            if status and old_status != new_status
            else "updated"
        )
        _prev = old_status if (status and old_status != new_status) else None
        _schedule_workflow_notify(
            _ev,
            "badcase",
            badcase.id,
            badcase.title or "",
            badcase.project_id,
            _workflow_project_name(badcase.project_id),
            new_status,
            _prev,
            _rec,
            actor_id=current_user.id,
            actor_name=getattr(current_user, "name", "") or "",
        )
    except Exception as _e:
        print(f"[workflow_notify] BadCase 状态接口通知失败: {_e}")
    
    return jsonify({'success': True})

@badcases_api_bp.route('/api/badcases/<int:badcase_id>/comment', methods=['POST'])
@login_required
def api_add_badcase_comment(badcase_id):
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

    badcase = BadCase.query.get_or_404(badcase_id)
    
    if not has_project_permission(current_user.id, badcase.project_id):
        return jsonify({'success': False, 'error': '无权操作此BadCase'}), 403
    
    data = request.get_json()
    content = data.get('content')
    
    if not content:
        return jsonify({'success': False, 'error': '评论内容不能为空'}), 400
    
    try:
        comment = _append_badcase_comment_row(
            badcase,
            content,
            current_user.id,
            source_message_id=data.get('message_id'),
        )
        db.session.commit()
        return jsonify({'success': True, 'comment': comment})
    except Exception as e:
        db.session.rollback()
        print(f"[API] 追加 BadCase 评论失败: {e}", flush=True)
        return jsonify({'success': False, 'error': '追加评论失败'}), 500

@badcases_api_bp.route('/api/badcases/<int:badcase_id>', methods=['PUT', 'DELETE'])
@login_required
def api_update_badcase(badcase_id):
    """更新BadCase信息"""
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

    print(f"=== 更新/删除 BadCase {badcase_id} ===")
    
    # 删除
    if request.method == 'DELETE':
        try:
            badcase = BadCase.query.get_or_404(badcase_id)
            
            if not has_project_permission(current_user.id, badcase.project_id):
                return jsonify({'success': False, 'error': '无权删除此BadCase'}), 403
            
            _pid = badcase.project_id
            _title = badcase.title or ""
            _st = _badcase_status_str(badcase)
            _pn = _workflow_project_name(_pid)
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_badcase(badcase), badcase.creator_id
            )
            db.session.delete(badcase)
            db.session.commit()
            _cache_invalidate_plans(_pid)
            try:
                _schedule_workflow_notify(
                    "deleted",
                    "badcase",
                    badcase_id,
                    _title,
                    _pid,
                    _pn,
                    _st,
                    None,
                    _rec,
                    actor_id=current_user.id,
                    actor_name=getattr(current_user, "name", "") or "",
                )
            except Exception as _e:
                print(f"[workflow_notify] BadCase 删除通知失败: {_e}")

            _schedule_grep_work_item_delete("badcase", badcase_id)

            return jsonify({'success': True, 'message': 'BadCase删除成功'})
        except Exception as e:
            db.session.rollback()
            print(f"删除BadCase失败: {e}")
            return jsonify({'success': False, 'error': '删除BadCase失败'}), 500
    
    # 更新
    print(f"=== 更新BadCase {badcase_id} ===")
    
    try:
        badcase = BadCase.query.get_or_404(badcase_id)
        
        if not has_project_permission(current_user.id, badcase.project_id):
            return jsonify({'success': False, 'error': '无权操作此BadCase'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据格式错误'}), 400
        
        print(f"更新数据: {data}")
        
        old_status = _badcase_status_str(badcase)
        
        # 更新BadCase字段
        if 'title' in data:
            badcase.title = data['title']
        if 'case_category' in data:
            badcase.case_category = data['case_category']
        if 'base_problem' in data:
            badcase.base_problem = (data['base_problem'] or '').strip()
        if 'badcase_result' in data:
            badcase.badcase_result = data['badcase_result']
        if 'answer' in data:
            badcase.answer = data['answer']
        if 'correct_answer' in data:
            badcase.correct_answer = data['correct_answer']
        if 'reproduction_steps' in data:
            badcase.reproduction_steps = data['reproduction_steps']
        if 'problem_reason' in data:
            badcase.problem_reason = data['problem_reason']
        if 'solution' in data:
            badcase.solution = data['solution']
        if 'priority' in data:
            badcase.priority = data['priority']
        if 'status' in data:
            badcase.status = data['status']
        if 'assignee' in data:
            badcase.assignee = data['assignee']
        if 'plan_id' in data:
            _pid = data.get('plan_id')
            if _pid in (None, '', 0, '0'):
                badcase.plan_id = None
            else:
                try:
                    badcase.plan_id = int(_pid)
                except (TypeError, ValueError):
                    pass
        if 'plan' in data:
            badcase.plan = data['plan']
            # 前端常同时传 plan 与 plan_id；若 plan_id 显式为空，仍应用 plan 里的数字 id
            _pid_missing = 'plan_id' not in data
            _pid_empty = (not _pid_missing) and data.get('plan_id') in (None, '', 0, '0')
            if _pid_missing or _pid_empty:
                pv = data.get('plan')
                if pv in (None, '', 'unplanned'):
                    badcase.plan_id = None
                else:
                    s = str(pv).strip()
                    if s.isdigit():
                        try:
                            badcase.plan_id = int(s)
                        except ValueError:
                            pass
        _try_repair_badcase_plan_id_from_legacy_plan_string(badcase)
        if 'document_type' in data:
            badcase.document_type = data['document_type']
        if 'attachments' in data:
            import json
            badcase.attachments = json.dumps(data['attachments']) if data['attachments'] else None
        if 'assigned_users' in data:
            badcase.assigned_users = data['assigned_users']
        
        db.session.commit()
        _cache_invalidate_plans(badcase.project_id)
        print("BadCase更新成功")
        try:
            new_status = _badcase_status_str(badcase)
            _ev = (
                "status_changed"
                if "status" in data and old_status != new_status
                else "updated"
            )
            _prev = (
                old_status
                if ("status" in data and old_status != new_status)
                else None
            )
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_badcase(badcase), badcase.creator_id
            )
            _schedule_workflow_notify(
                _ev,
                "badcase",
                badcase.id,
                badcase.title or "",
                badcase.project_id,
                _workflow_project_name(badcase.project_id),
                new_status,
                _prev,
                _rec,
                actor_id=current_user.id,
                actor_name=getattr(current_user, "name", "") or "",
            )
        except Exception as _e:
            print(f"[workflow_notify] BadCase 更新通知失败: {_e}")

        _schedule_grep_work_item_index("badcase", badcase.id)

        return jsonify({'success': True, 'message': 'BadCase更新成功'})
        
    except Exception as e:
        print(f"更新BadCase失败: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': '更新BadCase失败'}), 500

@badcases_api_bp.route('/api/badcases/<int:badcase_id>/close', methods=['POST'])
@login_required
def api_close_badcase(badcase_id):
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

    badcase = BadCase.query.get_or_404(badcase_id)
    
    if not has_project_permission(current_user.id, badcase.project_id):
        return jsonify({'success': False, 'error': '无权操作此BadCase'}), 403
    
    old_status = _badcase_status_str(badcase)
    badcase.status = 'close'
    db.session.commit()
    try:
        _rec = _workflow_merge_creator_if_empty(
            _workflow_recipients_badcase(badcase), badcase.creator_id
        )
        _schedule_workflow_notify(
            "closed",
            "badcase",
            badcase.id,
            badcase.title or "",
            badcase.project_id,
            _workflow_project_name(badcase.project_id),
            "close",
            old_status,
            _rec,
            actor_id=current_user.id,
            actor_name=getattr(current_user, "name", "") or "",
        )
    except Exception as _e:
        print(f"[workflow_notify] BadCase 关闭通知失败: {_e}")

    _schedule_grep_work_item_index("badcase", badcase.id)

    return jsonify({'success': True})

# Card相关的API端点
@badcases_api_bp.route('/api/cards', methods=['POST'])
