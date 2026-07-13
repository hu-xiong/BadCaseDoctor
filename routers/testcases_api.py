"""testcases_api（自 app.py 拆出）。"""
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

testcases_api_bp = Blueprint("testcases_api", __name__)


def _app():
    import app as _application
    return _application


        title = _truncate_db_str(title, 200, '')
        project_raw = data.get('project_id')
        project_id_val = _coerce_non_negative_int(project_raw)
        if project_id_val is None or project_id_val <= 0:
            return jsonify({'success': False, 'error': '缺少或无效的 project_id'}), 400

        # 验证必填字段（plan_id 可选：未指定则归入「未计划的 Bug」）
        if not title:
            return jsonify({'success': False, 'error': '缺少必填字段: title 或 project_id'}), 400
        
        # 检查项目权限
        if not has_project_permission(current_user.id, project_id_val):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        raw_plan = data.get('plan_id')
        plan_id_val = None
        if raw_plan is not None and str(raw_plan).strip() != '':
            try:
                pi = int(raw_plan)
                if pi != 0:
                    plan_id_val = pi
            except (TypeError, ValueError):
                plan_id_val = None
        
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
            # 检查卡片类型是否为 bug
            card_type_value = card.type.value if hasattr(card.type, 'value') else str(card.type)
            if card_type_value != 'bug':
                return jsonify({'success': False, 'error': '只能在bug类型卡片中创建bug'}), 400
        elif plan_id_val is not None:
            # 兜底：按计划类型校验（向后兼容）
            plan = Plan.query.get(plan_id_val)
            if not plan:
                return jsonify({'success': False, 'error': '计划不存在'}), 404
            # 计划类型字段已移除：不再按计划类型限制创建 bug

        steps_raw = data.get('steps_to_reproduce')
        if steps_raw is None or (isinstance(steps_raw, str) and steps_raw.strip() == ''):
            steps_raw = data.get('reproduce_steps', '')
        steps_to_reproduce = '' if steps_raw is None else str(steps_raw)

        bug = Bug(
            title=title,
            steps_to_reproduce=steps_to_reproduce,
            expected_result=_truncate_db_str(data.get('expected_result', ''), 65535, ''),
            actual_result=_truncate_db_str(data.get('actual_result', ''), 65535, ''),
            severity=_truncate_db_str(data.get('severity', 'medium'), 20, 'medium'),
            priority=_normalize_bug_priority_for_db(data.get('priority')),
            status=_truncate_db_str(data.get('status', 'new'), 20, 'new'),
            bug_type=_truncate_db_str(data.get('bug_type', ''), 50, ''),
            environment=_truncate_db_str(data.get('environment', ''), 100, ''),
            browser=_truncate_db_str(data.get('browser', ''), 50, ''),
            os=_truncate_db_str(data.get('os', ''), 50, ''),
            plan_id=plan_id_val,
            card_id=card_id_val,
            project_id=project_id_val,
            creator_id=current_user.id,
            assignee_id=_coerce_positive_int_or_none(data.get('assignee_id')),
            attachments=_attachments_to_text(data.get('attachments', ''))
        )
        
        db.session.add(bug)
        db.session.commit()
        db.session.refresh(bug)

        # 与 agents CreateTool 一致：迭代看板按 Card 展示；仅插入 Bug 而无 Card 时左侧列表不可见
        if bug.card_id is None:
            try:
                _card = Card(
                    title=bug.title or "",
                    type=CardType.BUG,
                    priority=bug.priority or "p3",
                    assignee_id=bug.assignee_id,
                    project_id=project_id_val,
                    creator_id=bug.creator_id,
                    plan_id=bug.plan_id,
                    description=None,
                    source_type="bug",
                    source_id=int(bug.id),
                )
                db.session.add(_card)
                db.session.commit()
                db.session.refresh(_card)
                bug.card_id = int(_card.id)
                db.session.commit()
                db.session.refresh(bug)
            except Exception as _card_ex:
                db.session.rollback()
                print(f"[api_create_bug] 同步创建 Card 失败: {_card_ex}")

        try:
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_bug(bug), bug.creator_id
            )
            _schedule_workflow_notify(
                "created",
                "bug",
                bug.id,
                bug.title or "",
                bug.project_id,
                _workflow_project_name(bug.project_id),
                bug.status,
                None,
                _rec,
                actor_id=current_user.id,
                actor_name=getattr(current_user, "name", "") or "",
            )
        except Exception as _e:
            print(f"[workflow_notify] Bug 创建通知失败: {_e}")

        _schedule_grep_work_item_index("bug", bug.id)

        return jsonify({
            'success': True,
            'message': 'Bug创建成功',
            'bug': {
                'id': _json_snowflake_id(bug.id),
                'title': bug.title,
                'severity': bug.severity,
                'priority': bug.priority,
                'status': bug.status,
                'bug_type': bug.bug_type,
                'plan_id': _json_snowflake_id(bug.plan_id),
                'card_id': _json_snowflake_id(bug.card_id),
                'project_id': bug.project_id,
                'creator_id': bug.creator_id,
                'assignee_id': bug.assignee_id,
                'created_at': bug.created_at.isoformat(),
                'updated_at': bug.updated_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"创建Bug失败: {e}")
        import traceback
        traceback.print_exc()
        err_msg = str(e) if e else 'unknown'
        return jsonify({'success': False, 'error': f'创建Bug失败: {err_msg}'}), 500

@testcases_api_bp.route('/api/projects/<int:project_id>/bugs', methods=['GET'])
@login_required
def api_get_project_bugs(project_id):
    """获取项目的Bug列表（分页）"""
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
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 获取计划ID参数
        plan_id = _parse_query_int_optional('plan_id')
        
        # 获取卡片ID参数（优先使用card_id过滤，因为卡片分类型）
        card_id = _parse_query_optional_int64('card_id')
        
        # 获取状态类型参数
        status_type = request.args.get('status_type')
        
        # 构建查询条件
        query = Bug.query.filter_by(project_id=project_id)
        
        # 处理card_id过滤（优先，因为卡片分类型，计划不分类型）
        if card_id is not None:
            query = query.filter_by(card_id=card_id)
            print(f"按卡片ID过滤Bug: card_id={card_id}")
        elif status_type == 'unplanned':
            # 未计划的Bug：没有关联计划的Bug
            query = query.filter(Bug.plan_id.is_(None))
            print(f"过滤未计划的Bug (status_type=unplanned)")
        elif plan_id is not None:
            query = query.filter_by(plan_id=plan_id)
            # 迭代计划下列表：默认只返回已挂卡片的 Bug，避免出现「计划根下直接挂 Bug」的孤儿行（与看板 Card 层对齐）。
            # 数据修复/排查需包含无卡记录时：GET ...&include_cardless_bugs=1
            _inc_cardless = (request.args.get('include_cardless_bugs') or '').strip().lower() in (
                '1',
                'true',
                'yes',
                'on',
            )
            if not _inc_cardless:
                query = query.filter(Bug.card_id.isnot(None))
                print(f"按 plan_id={plan_id} 过滤 Bug，且排除 card_id 为空的记录（include_cardless_bugs 未开启）")
            else:
                print(f"按 plan_id={plan_id} 过滤 Bug，包含无卡片关联记录（include_cardless_bugs=1）")
        
        # 分页查询Bug
        pagination = query.order_by(Bug.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        bugs = []
        for bug in pagination.items:
            # 获取负责人姓名
            assignee_name = '未指派'
            if bug.assignee_id:
                user = User.query.get(bug.assignee_id)
                if user:
                    assignee_name = user.name
            
            bugs.append({
                'id': _json_snowflake_id(bug.id),
                'title': bug.title,
                'bug_type': bug.bug_type,
                'priority': bug.priority,
                'status': bug.status,
                'assignee': assignee_name,
                'plan_id': _json_snowflake_id(bug.plan_id),
                'card_id': _json_snowflake_id(bug.card_id),
                'created_at': bug.created_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'badcases': bugs, # 为了兼容前端 filteredBadcases，这里暂时使用 badcases 键名
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
        print(f"获取项目Bug列表失败: {e}")
        return jsonify({'success': False, 'error': '获取Bug列表失败'}), 500

@testcases_api_bp.route('/api/bugs/<int:bug_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_bug_detail(bug_id):
    """Bug详情接口：GET查询，PUT更新"""
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

    if request.method == 'GET':
        try:
            bug, access_err = _model_for_user_collaborator_access(Bug, bug_id, current_user.id)
            if access_err == 'not_found':
                return jsonify({'success': False, 'error': 'Bug不存在'}), 404
            if access_err == 'forbidden':
                return jsonify({'success': False, 'error': '没有项目权限'}), 403

            # 评论 + 用户名一次 JOIN，避免 bug_comment 与 user 各查一遍
            comment_rows = (
                db.session.query(BugComment, User.name)
                .outerjoin(User, User.id == BugComment.user_id)
                .filter(BugComment.bug_id == bug_id)
                .order_by(BugComment.created_at.asc())
                .all()
            )
            comments = []
            for comment, uname in comment_rows:
                comments.append({
                    'id': comment.id,
                    'content': comment.content,
                    'user_id': comment.user_id,
                    'user_name': uname or '未知',
                    'source_message_id': comment.source_message_id,
                    'created_at': comment.created_at.isoformat()
                })
            
            cid = getattr(bug, 'card_id', None)
            navigation_plan_id = bug.plan_id
            if cid:
                cp = db.session.query(Card.plan_id).filter(Card.id == int(cid)).scalar()
                if cp is not None and int(cp or 0) > 0:
                    navigation_plan_id = cp

            return jsonify({
                'success': True,
                'bug': {
                    'id': _json_snowflake_id(bug.id),
                    'title': bug.title,
                    'steps_to_reproduce': bug.steps_to_reproduce,
                    'expected_result': bug.expected_result,
                    'actual_result': bug.actual_result,
                    'severity': bug.severity,
                    'priority': bug.priority,
                    'status': bug.status,
                    'bug_type': bug.bug_type,
                    'environment': bug.environment,
                    'browser': bug.browser,
                    'os': bug.os,
                    'plan_id': _json_snowflake_id(bug.plan_id),
                    'navigation_plan_id': _json_snowflake_id(navigation_plan_id),
                    'card_id': _json_snowflake_id(cid),
                    'project_id': bug.project_id,
                    'creator_id': bug.creator_id,
                    'assignee_id': bug.assignee_id,
                    'attachments': bug.attachments,
                    'created_at': bug.created_at.isoformat(),
                    'updated_at': bug.updated_at.isoformat(),
                    'comments': comments
                }
            })
            
        except Exception as e:
            print(f"获取Bug详情失败: {e}")
            return jsonify({'success': False, 'error': '获取Bug详情失败'}), 500
    
    elif request.method == 'PUT':
        try:
            bug = Bug.query.get(bug_id)
            if not bug:
                return jsonify({'success': False, 'error': 'Bug不存在'}), 404
            
            # 检查项目权限
            if not has_project_permission(current_user.id, bug.project_id):
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            data = request.json
            old_bug_status = bug.status
            
            # 更新字段
            if 'title' in data:
                bug.title = data['title']
            if 'steps_to_reproduce' in data:
                bug.steps_to_reproduce = data['steps_to_reproduce']
            if 'expected_result' in data:
                bug.expected_result = data['expected_result']
            if 'actual_result' in data:
                bug.actual_result = data['actual_result']
            if 'severity' in data:
                bug.severity = data['severity']
            if 'priority' in data:
                bug.priority = data['priority']
            if 'status' in data:
                bug.status = data['status']
            if 'bug_type' in data:
                bug.bug_type = data['bug_type']
            if 'environment' in data:
                bug.environment = data['environment']
            if 'browser' in data:
                bug.browser = data['browser']
            if 'os' in data:
                bug.os = data['os']
            if 'plan_id' in data:
                # 处理plan_id为None的情况，确保不会设置为NULL
                plan_id_value = data['plan_id']
                if plan_id_value is not None and plan_id_value != '':
                    try:
                        bug.plan_id = int(plan_id_value)
                    except (TypeError, ValueError):
                        # 如果无法转换为整数，保持原有值
                        pass
                else:
                    # 如果plan_id为空，保持原有值
                    pass
            if 'assignee_id' in data:
                bug.assignee_id = data['assignee_id']
            if 'attachments' in data:
                bug.attachments = data['attachments']
            
            bug.updated_at = datetime.now()
            db.session.commit()
            try:
                _rec = _workflow_merge_creator_if_empty(
                    _workflow_recipients_bug(bug), bug.creator_id
                )
                _ns = bug.status
                _ev = (
                    "status_changed"
                    if "status" in data and old_bug_status != _ns
                    else "updated"
                )
                _prev = (
                    old_bug_status
                    if ("status" in data and old_bug_status != _ns)
                    else None
                )
                _schedule_workflow_notify(
                    _ev,
                    "bug",
                    bug.id,
                    bug.title or "",
                    bug.project_id,
                    _workflow_project_name(bug.project_id),
                    _ns,
                    _prev,
                    _rec,
                    actor_id=current_user.id,
                    actor_name=getattr(current_user, "name", "") or "",
