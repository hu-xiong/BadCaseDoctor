"""chat_sessions_api（自 app.py 拆出）。"""
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

chat_sessions_bp = Blueprint("chat_sessions", __name__)


def _app():
    import app as _application
    return _application


                )
            except Exception as _e:
                print(f"[workflow_notify] Bug 更新通知失败: {_e}")

            _schedule_grep_work_item_index("bug", bug.id)

            return jsonify({
                'success': True,
                'message': 'Bug更新成功',
                'bug': {
                    'id': _json_snowflake_id(bug.id),
                    'title': bug.title,
                    'status': bug.status,
                    'updated_at': bug.updated_at.isoformat()
                }
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"更新Bug失败: {e}")
            return jsonify({'success': False, 'error': '更新Bug失败'}), 500
    elif request.method == 'DELETE':
        try:
            bug = Bug.query.get_or_404(bug_id)

            if not has_project_permission(current_user.id, bug.project_id):
                return jsonify({'success': False, 'error': '无权删除此Bug'}), 403

            _pid = bug.project_id
            _title = bug.title or ""
            _st = bug.status
            _pn = _workflow_project_name(_pid)
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_bug(bug), bug.creator_id
            )
            # 先清依赖行，避免 MySQL 外键 / 孤儿约束导致 delete bug 500
            try:
                BugComment.query.filter(BugComment.bug_id == int(bug_id)).delete(
                    synchronize_session=False
                )
            except Exception as _e:
                print(f"[DELETE-BUG] 清理 bug_comment 失败（继续）: {_e}")
            try:
                nt_bug = _normalize_diff_target("bug")
                for _dr in DiffReviewState.query.filter(
                    DiffReviewState.project_id == _pid,
                    DiffReviewState.target == nt_bug,
                    DiffReviewState.target_id == int(bug_id),
                ).all():
                    db.session.delete(_dr)
            except Exception as _e:
                print(f"[DELETE-BUG] 清理 diff_review_state 失败（继续）: {_e}")
            _cid = getattr(bug, "card_id", None)
            if _cid:
                try:
                    bug.card_id = None
                    db.session.flush()
                except Exception as _e:
                    print(f"[DELETE-BUG] 解除 bug.card_id 失败（继续）: {_e}")
                try:
                    CardPlanRelation.query.filter(
                        CardPlanRelation.card_id == int(_cid)
                    ).delete(synchronize_session=False)
                except Exception as _e:
                    print(f"[DELETE-BUG] 清理 card_plan_relation 失败（继续）: {_e}")
                try:
                    _card = Card.query.get(int(_cid))
                    if _card is not None:
                        db.session.delete(_card)
                except Exception as _e:
                    print(f"[DELETE-BUG] 删除关联 Card id={_cid} 失败（继续）: {_e}")

            db.session.delete(bug)
            db.session.commit()
            _cache_invalidate_plans(_pid)
            try:
                _schedule_workflow_notify(
                    "deleted",
                    "bug",
                    bug_id,
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
                print(f"[workflow_notify] Bug 删除通知失败: {_e}")

            _schedule_grep_work_item_delete("bug", bug_id)

            return jsonify({'success': True, 'message': 'Bug删除成功'})
        except Exception as e:
            db.session.rollback()
            print(f"删除Bug失败: {e}")
            return jsonify({'success': False, 'error': '删除Bug失败'}), 500

@chat_sessions_bp.route('/api/bugs/<int:bug_id>/comment', methods=['POST'])
@login_required
def api_add_bug_comment(bug_id):
    """为Bug添加评论"""
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
        bug = Bug.query.get(bug_id)
        if not bug:
            return jsonify({'success': False, 'error': 'Bug不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, bug.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        data = request.get_json()
        if not data.get('content'):
            return jsonify({'success': False, 'error': '评论内容不能为空'}), 400
        
        comment = _append_bug_comment_row(
            bug,
            data['content'],
            current_user.id,
            source_message_id=data.get('message_id'),
        )
        db.session.commit()
        return jsonify({
            'success': True,
            'message': '评论添加成功',
            'comment': comment,
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"添加Bug评论失败: {e}")
        return jsonify({'success': False, 'error': '添加评论失败'}), 500

# ==================== TestCase API ====================

@chat_sessions_bp.route('/api/testcases', methods=['POST'])
@login_required
def api_create_testcase():
    """创建TestCase"""
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

    print('[TESTCASE-CREATE] 请求进入 (新代码已加载)')
    try:
        data = request.get_json()
        
        # 验证必填字段
        if not data.get('title'):
            print('[TESTCASE] 400: 缺少 title, data=', {k: v for k, v in (data or {}).items() if k in ('title', 'project_id')})
            return jsonify({'success': False, 'error': '缺少必填字段: title'}), 400
        if not data.get('project_id'):
            print('[TESTCASE] 400: 缺少 project_id, data=', {k: v for k, v in (data or {}).items() if k in ('title', 'project_id')})
            return jsonify({'success': False, 'error': '缺少必填字段: project_id'}), 400
        
        # 检查项目权限
        if not has_project_permission(current_user.id, data['project_id']):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 如果提供了 card_id，按卡片类型校验（卡片分类型，计划不分类型）
        card_id_val = _coerce_optional_bigint_json(data.get('card_id'))
        
        if card_id_val is not None:
            # 按卡片类型校验
            card = Card.query.get(card_id_val)
            if not card:
                return jsonify({'success': False, 'error': '卡片不存在'}), 404
            # 检查卡片类型是否为 testcase
            card_type_value = card.type.value if hasattr(card.type, 'value') else str(card.type)
            if card_type_value != 'testcase':
                return jsonify({'success': False, 'error': '只能在testcase类型卡片中创建测试用例'}), 400
        
        # plan_id：若存在则使用（不再校验计划类型）
        plan_id = _coerce_optional_bigint_json(data.get('plan_id'))
        if plan_id:
            plan = Plan.query.get(plan_id)
            if not plan:
                plan_id = None
        # 未显式传 plan_id 时，继承卡片所属迭代
        if plan_id is None and card_id_val is not None:
            card_for_plan = Card.query.get(card_id_val)
            if card_for_plan and card_for_plan.plan_id:
                plan_id = int(card_for_plan.plan_id)
        
        # 创建TestCase
        testcase = TestCase(
            title=data['title'],
            status=data.get('status', 'draft'),
            case_type=data.get('case_type', '功能测试'),
            priority=data.get('priority', 'P3'),
            test_type=data.get('test_type', '手动'),
            preconditions=data.get('preconditions', ''),
            steps=data.get('steps', []),
            remark=data.get('remark', ''),
            requirement_id=data.get('requirement_id'),
            related_defects=data.get('related_defects', []),
            baseline=data.get('baseline', ''),
            estimated_time=data.get('estimated_time', 0),
            version=data.get('version', 'v1'),
            plan_id=plan_id,
            project_id=data['project_id'],
            creator_id=current_user.id,
            assignee_id=data.get('assignee_id'),
            card_id=card_id_val,
        )
        
        db.session.add(testcase)
        db.session.commit()
        _cache_invalidate_plans(data['project_id'])
        _schedule_grep_work_item_index("testcase", testcase.id)
        try:
            _rec = _workflow_merge_creator_if_empty(
                _workflow_recipients_testcase(testcase), testcase.creator_id
            )
            _schedule_workflow_notify(
                "created",
                "testcase",
                testcase.id,
                testcase.title or "",
                testcase.project_id,
                _workflow_project_name(testcase.project_id),
                _testcase_status_str(testcase),
                None,
                _rec,
                actor_id=current_user.id,
                actor_name=getattr(current_user, "name", "") or "",
            )
        except Exception as _e:
            print(f"[workflow_notify] TestCase 创建通知失败: {_e}")
        
        # 确保枚举/日期等可 JSON 序列化
        _s = testcase.status
        _st = getattr(_s, 'value', None) or str(_s) if _s else 'draft'
        _ct = testcase.created_at.isoformat() if testcase.created_at else None
        return jsonify({
            'success': True,
            'message': '测试用例创建成功',
            'testcase': {
                'id': _json_snowflake_id(testcase.id),
                'title': str(testcase.title),
                'status': _st,
                'priority': str(testcase.priority) if testcase.priority else 'P3',
                'created_at': _ct
            }
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        err_msg = str(e)
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'创建TestCase失败: {err_msg}'}), 500

@chat_sessions_bp.route('/api/testcases/<int:testcase_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_testcase_detail(testcase_id):
    """测试用例详情接口：GET查询，PUT更新，DELETE删除"""
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
            t0 = time.perf_counter()
            redis_hit, redis_cached = _redis_cache_get(f'testcase-detail:{testcase_id}')
            if redis_hit and isinstance(redis_cached, dict) and redis_cached.get('success'):
                if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
                    print(
                        f"[PERF] GET /api/testcases/{testcase_id} redis_hit total={(time.perf_counter() - t0) * 1000:.1f}ms",
                        flush=True,
                    )
                return jsonify(redis_cached)

            testcase, access_err = _model_for_user_collaborator_access(TestCase, testcase_id, current_user.id)
            if access_err == 'not_found':
                return jsonify({'success': False, 'error': '测试用例不存在'}), 404
            if access_err == 'forbidden':
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            _status = testcase.status
            if hasattr(_status, 'value'):
                _status = _status.value
            _exec = testcase.execution_result
            if _exec is not None and hasattr(_exec, 'value'):
                _exec = _exec.value
            payload = {
                'success': True,
                'testcase': {
                    'id': _json_snowflake_id(testcase.id),
                    'title': testcase.title,
                    'status': _status,
                    'case_type': testcase.case_type,
                    'priority': testcase.priority,
                    'test_type': testcase.test_type,
                    'preconditions': testcase.preconditions,
                    'steps': testcase.steps,
                    'remark': testcase.remark,
                    'requirement_id': testcase.requirement_id,
                    'related_defects': _testcase_related_defects_detail_payload(testcase),
                    'baseline': testcase.baseline,
                    'estimated_time': testcase.estimated_time,
                    'actual_time': testcase.actual_time,
                    'remaining_time': testcase.remaining_time,
                    'last_executed': testcase.last_executed.isoformat() if testcase.last_executed else None,
                    'executed_by': testcase.executed_by,
                    'execution_result': _exec,
                    'version': testcase.version,
                    'plan_id': _json_snowflake_id(testcase.plan_id),
                    'project_id': testcase.project_id,
                    'creator_id': testcase.creator_id,
                    'assignee_id': testcase.assignee_id,
                    'card_id': _json_snowflake_id(getattr(testcase, 'card_id', None)),
                    'created_at': testcase.created_at.isoformat(),
                    'updated_at': testcase.updated_at.isoformat(),
                    'comments': _testcase_comments_detail_payload(testcase.id),
                }
            }
            _redis_cache_set(f'testcase-detail:{testcase_id}', payload, ttl_s=60)
            if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
                print(
                    f"[PERF] GET /api/testcases/{testcase_id} total={(time.perf_counter() - t0) * 1000:.1f}ms",
                    flush=True,
                )
            return jsonify(payload)
            
        except Exception as e:
            print(f"获取TestCase详情失败: {e}")
            return jsonify({'success': False, 'error': '获取TestCase详情失败'}), 500
    
    elif request.method == 'PUT':
        try:
            testcase = TestCase.query.get(testcase_id)
            if not testcase:
                return jsonify({'success': False, 'error': '测试用例不存在'}), 404
            
            # 检查项目权限
            if not has_project_permission(current_user.id, testcase.project_id):
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            data = request.json
            old_tc_status = _testcase_status_str(testcase)
            
            # 更新字段
            if 'title' in data:
                testcase.title = data['title']
            if 'status' in data:
                testcase.status = data['status']
            if 'case_type' in data:
                testcase.case_type = data['case_type']
            if 'priority' in data:
                testcase.priority = data['priority']
            if 'test_type' in data:
                testcase.test_type = data['test_type']
            if 'preconditions' in data:
                testcase.preconditions = data['preconditions']
            if 'steps' in data:
                testcase.steps = data['steps']
            if 'remark' in data:
                testcase.remark = data['remark']
            if 'requirement_id' in data:
                testcase.requirement_id = data['requirement_id']
            if 'related_defects' in data:
                testcase.related_defects = data['related_defects']
            if 'baseline' in data:
                testcase.baseline = data['baseline']
            if 'estimated_time' in data:
                testcase.estimated_time = data['estimated_time']
            if 'actual_time' in data:
                testcase.actual_time = data['actual_time']
            if 'remaining_time' in data:
                testcase.remaining_time = data['remaining_time']
            if 'last_executed' in data:
                testcase.last_executed = data['last_executed']
            if 'executed_by' in data:
                testcase.executed_by = data['executed_by']
            if 'execution_result' in data:
                er = data['execution_result']
                if er is None or (isinstance(er, str) and er.strip() == ''):
                    testcase.execution_result = None
                else:
                    try:
                        testcase.execution_result = ExecutionResult(er) if isinstance(er, str) else er
                    except (ValueError, TypeError):
                        testcase.execution_result = None
            if 'version' in data:
                testcase.version = data['version']
            if 'plan_id' in data:
                testcase.plan_id = data['plan_id']
            if 'assignee_id' in data:
                testcase.assignee_id = data['assignee_id']
            
            testcase.updated_at = datetime.now()
            db.session.commit()
            _cache_invalidate_plans(testcase.project_id)
            _schedule_grep_work_item_index("testcase", testcase.id)
            try:
                _rec = _workflow_merge_creator_if_empty(
                    _workflow_recipients_testcase(testcase), testcase.creator_id
                )
                _ns = _testcase_status_str(testcase)
                _ev = (
                    "status_changed"
                    if "status" in data and old_tc_status != _ns
                    else "updated"
                )
                _prev = (
                    old_tc_status
                    if ("status" in data and old_tc_status != _ns)
                    else None
                )
                _schedule_workflow_notify(
                    _ev,
                    "testcase",
                    testcase.id,
                    testcase.title or "",
                    testcase.project_id,
                    _workflow_project_name(testcase.project_id),
                    _ns,
                    _prev,
                    _rec,
                    actor_id=current_user.id,
                    actor_name=getattr(current_user, "name", "") or "",
                )
            except Exception as _e:
                print(f"[workflow_notify] TestCase 更新通知失败: {_e}")
            
            # 处理 status 枚举值
            status_val = testcase.status
            if hasattr(status_val, 'value'):
                status_val = status_val.value
            
            _redis_cache_delete(f'testcase-detail:{testcase_id}')
            return jsonify({
                'success': True,
                'message': '测试用例更新成功',
                'testcase': {
                    'id': _json_snowflake_id(testcase.id),
                    'title': testcase.title,
                    'status': status_val,
                    'updated_at': testcase.updated_at.isoformat()
                }
            })
            
        except Exception as e:
            db.session.rollback()
            err_msg = str(e)
            print(f"更新TestCase失败: {e}")
            return jsonify({'success': False, 'error': f'更新TestCase失败: {err_msg}'}), 500
    
    elif request.method == 'DELETE':
        try:
            testcase = TestCase.query.get(testcase_id)
            if not testcase:
                return jsonify({'success': False, 'error': '测试用例不存在'}), 404
            
            # 检查项目权限
            if not has_project_permission(current_user.id, testcase.project_id):
                return jsonify({'success': False, 'error': '没有项目权限'}), 403
            
            pid = testcase.project_id
            _title = testcase.title or ""
            _st = _testcase_status_str(testcase)
            _pn = _workflow_project_name(pid)
            _rec = _workflow_merge_creator_if_empty(
