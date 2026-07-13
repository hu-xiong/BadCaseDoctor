"""cards_api（自 app.py 拆出）。"""
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

cards_api_bp = Blueprint("cards_api", __name__)


def _app():
    import app as _application
    return _application


@login_required
def api_create_card():
    """创建卡片"""
    print(f"=== 创建卡片 ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        # 获取参数
        title = data.get('title', '').strip()
        card_type_str = data.get('type', 'badcase')
        project_id = data.get('project_id')
        
        if not title:
            return jsonify({'success': False, 'error': '标题不能为空'}), 400
        
        if not project_id:
            return jsonify({'success': False, 'error': '项目ID不能为空'}), 400
        
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        
        # 将字符串转换为枚举
        try:
            card_type = CardType(card_type_str)
        except ValueError:
            return jsonify({'success': False, 'error': f'无效的卡片类型: {card_type_str}'}), 400
        
        # 创建卡片
        card = Card(
            title=title,
            type=card_type,
            project_id=project_id,
            creator_id=current_user.id,
            priority='p3'
        )
        # 与前端「当前选中迭代」对齐（可选）
        raw_pid = data.get('plan_id')
        if raw_pid is not None and raw_pid != '':
            try:
                pid = int(raw_pid)
                card.plan_id = pid if pid > 0 else None
            except (TypeError, ValueError):
                card.plan_id = None
        else:
            card.plan_id = None
        
        # 根据类型设置特定字段
        if card_type == CardType.BUG:
            card.severity = data.get('severity', 'medium')
            card.steps_to_reproduce = data.get('steps_to_reproduce')
            card.expected_result = data.get('expected_result')
            card.actual_result = data.get('actual_result')
            card.bug_type = data.get('bug_type')
            card.environment = data.get('environment')
            card.browser = data.get('browser')
            card.os = data.get('os')
        elif card_type == CardType.BADCASE:
            card.case_category = data.get('case_category')
            card.base_problem = data.get('base_problem')
            card.reproduction_steps = data.get('reproduction_steps')
            card.badcase_result = data.get('badcase_result')
            card.answer = data.get('answer')
            card.correct_answer = data.get('correct_answer')
            card.problem_reason = data.get('problem_reason')
            card.solution = data.get('solution')
        elif card_type == CardType.TESTCASE:
            card.case_type_test = data.get('case_type_test')
            card.test_type = data.get('test_type')
            card.preconditions = data.get('preconditions')
            card.steps = data.get('steps')
            card.remark = data.get('remark')
            card.requirement_id = data.get('requirement_id')
            card.related_defects = data.get('related_defects')
            card.baseline = data.get('baseline')
            card.estimated_time = data.get('estimated_time')
            card.actual_time = data.get('actual_time')
            card.remaining_time = data.get('remaining_time')
            card.version = data.get('version', 'v1')
        elif card_type == CardType.CARD:
            card.description = data.get('description')

        db.session.add(card)
        db.session.commit()
        _cache_invalidate_cards(project_id)
        _schedule_grep_work_item_index("card", card.id)
        
        print(f"✅ 卡片创建成功: {card.id}")
        return jsonify({'success': True, 'data': card.to_dict()})
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 创建卡片失败: {e}")
        return jsonify({'success': False, 'error': f'创建卡片失败: {str(e)}'}), 500


def _plan_subtree_ids_for_project(project_id: int, root_plan_id: int):
    """
    返回某项目下，以 root_plan_id 为根的迭代子树中全部计划 id（含根自身）。
    列表页选中顶层「迭代」时，前端传的是根计划 id；卡片 plan_id 往往在子计划下，
    仅用 Card.plan_id == 根 id 会漏数据。
    """
    rows = db.session.query(Plan.id, Plan.parent_id).filter(Plan.project_id == project_id).all()
    children_map = {}
    for pid, parent_id in rows:
        if parent_id is not None:
            children_map.setdefault(parent_id, []).append(pid)
    out = []
    stack = [root_plan_id]
    seen = set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        for cid in children_map.get(pid, ()):
            stack.append(cid)
    return out


def _detach_plan_work_items(plan_id: int) -> dict:
    """
    删除迭代前解绑仍挂在该 plan_id 上的工作项与卡片。
    看板按 Card.plan_id 展示；源表 Bug/BadCase/TestCase 可能仍带 plan_id（卡片已删等），
    不解绑会导致「列表为空却无法删计划」。
    """
    pid = int(plan_id)
    n_bc = (
        BadCase.query.filter_by(plan_id=pid)
        .update({BadCase.plan_id: None}, synchronize_session=False)
    )
    n_bug = Bug.query.filter_by(plan_id=pid).update({Bug.plan_id: None}, synchronize_session=False)
    n_tc = (
        TestCase.query.filter_by(plan_id=pid)
        .update({TestCase.plan_id: None}, synchronize_session=False)
    )
    n_card = Card.query.filter_by(plan_id=pid).update({Card.plan_id: None}, synchronize_session=False)
    n_rel = CardPlanRelation.query.filter_by(plan_id=pid).delete(synchronize_session=False)
    return {
        'detached_badcases': int(n_bc or 0),
        'detached_bugs': int(n_bug or 0),
        'detached_testcases': int(n_tc or 0),
        'detached_cards': int(n_card or 0),
        'removed_card_plan_relations': int(n_rel or 0),
    }


@cards_api_bp.route('/api/projects/<int:project_id>/cards', methods=['GET'])
@login_required
def api_get_project_cards(project_id):
    """获取项目的卡片列表"""
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
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403
        
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 获取卡片类型参数
        card_type = request.args.get('type')
        # 迭代计划下卡片列表：与前端 selectedPlan 对齐
        plan_id_param = _parse_query_optional_int64('plan_id')
        
        # 短期缓存 key（须包含 plan 维度，避免错命中）
        cache_key = ('cards', project_id, card_type or '', plan_id_param if plan_id_param is not None else '', page, per_page)
        cache_hit, cached = _cache_get(cache_key, ttl_s=0.5)
        if cache_hit:
            t_total = (time.perf_counter() - t0) * 1000
            print(f"[PERF] GET /api/projects/{project_id}/cards cache_hit total={t_total:.1f}ms", flush=True)
            return jsonify(cached)
        
        # 构建查询条件
        query = Card.query.filter_by(project_id=project_id)
        
        if plan_id_param is not None and plan_id_param > 0:
            plan_ids = _plan_subtree_ids_for_project(project_id, plan_id_param)
            if plan_ids:
                query = query.filter(Card.plan_id.in_(plan_ids))
        
        # 根据类型过滤
        if card_type:
            try:
                ct = CardType(card_type) if isinstance(card_type, str) else card_type
                query = query.filter(Card.type == ct)
            except Exception:
                query = query.filter(Card.type == card_type)
        
        # 分页查询
        pagination = query.order_by(Card.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        cards = [card.to_dict() for card in pagination.items]
        
        payload = {
            'success': True,
            'data': cards,
            'pagination': {
                'total': pagination.total,
                'pages': pagination.pages,
                'current_page': page,
                'per_page': per_page
            }
        }
        _cache_set(cache_key, payload)
        
        t_total = (time.perf_counter() - t0) * 1000
        print(f"[PERF] GET /api/projects/{project_id}/cards sql total={t_total:.1f}ms count={len(cards)}", flush=True)
        return jsonify(payload)
    
    except Exception as e:
        print(f"❌ 获取卡片列表失败: {e}")
        return jsonify({'success': False, 'error': f'获取卡片列表失败: {str(e)}'}), 500


@cards_api_bp.route('/api/projects/<int:project_id>/cards/resolve-source', methods=['GET'])
@login_required
def api_resolve_project_card_by_source(project_id):
    """
    按 Card.source_id（及类型）精确定位卡片，不受「按 plan 分页拉卡」限制。
    用于 Bug/BadCase/TestCase 行缺 card_id 或 Card.plan_id 不在当前迭代子树时的列表 / 沙箱 Tab 导航。
    """
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

    if not has_project_permission(current_user.id, project_id):
        return jsonify({'success': False, 'error': '无权访问此项目'}), 403
    try:
        source_type = (request.args.get('source_type') or '').strip().lower().replace('-', '_')
        source_id = _parse_query_optional_int64('source_id')
        prefer_plan_id = _parse_query_optional_int64('prefer_plan_id')
        if source_id is None or source_id <= 0:
            return jsonify({'success': True, 'data': {'card': None}})
        if source_type in ('test_case',):
            kind = 'testcase'
        elif source_type in ('bad_case',):
            kind = 'badcase'
        elif source_type in ('bug', 'badcase', 'testcase'):
            kind = source_type
        else:
            return jsonify({'success': False, 'error': '无效的 source_type'}), 400
        card = _find_card_linking_source_record(
            project_id, source_id, kind, prefer_plan_id=prefer_plan_id
        )
        if card is None:
            return jsonify({'success': True, 'data': {'card': None}})
        return jsonify({'success': True, 'data': {'card': card.to_dict()}})
    except Exception as e:
        print(f"❌ resolve-source 卡片失败: {e}")
        return jsonify({'success': False, 'error': f'解析卡片失败: {str(e)}'}), 500


@cards_api_bp.route('/api/cards/<int:card_id>', methods=['GET'])
@login_required
def api_get_card_detail(card_id):
    """获取卡片详情"""
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

    print(f"=== 获取卡片详情 {card_id} ===")
    
    try:
        card = Card.query.get_or_404(card_id)
        repair_card_source_link_if_missing(card)
        db.session.refresh(card)

        # 检查权限
        if not has_project_permission(current_user.id, card.project_id):
            return jsonify({'success': False, 'error': '无权访问此卡片'}), 403
        
        return jsonify({'success': True, 'data': card.to_dict()})
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 获取卡片详情失败: {e}")
        return jsonify({'success': False, 'error': f'获取卡片详情失败: {str(e)}'}), 500

@cards_api_bp.route('/api/cards/<int:card_id>', methods=['PUT'])
@login_required
def api_update_card(card_id):
    """更新卡片"""
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

    print(f"=== 更新卡片 {card_id} ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        card = Card.query.get_or_404(card_id)
        
        # 检查权限
        if not has_project_permission(current_user.id, card.project_id):
            return jsonify({'success': False, 'error': '无权修改此卡片'}), 403
        
        old_card_type = card.type
        
        # 更新字段
        if 'title' in data:
            card.title = data['title']
        if 'priority' in data:
            card.priority = data['priority']
        if 'assignee_id' in data:
            card.assignee_id = data['assignee_id']
        if 'plan_id' in data:
            card.plan_id = _coerce_optional_bigint_json(data['plan_id'])
        if 'description' in data:
            card.description = data['description']
        
        # 更新类型字段
        if 'type' in data:
            try:
                new_type_str = data['type']
                # 转换下划线格式
                if new_type_str == 'test_case':
                    new_type_str = 'testcase'
                card.type = CardType(new_type_str)
            except ValueError:
                return jsonify({'success': False, 'error': f'无效的卡片类型: {data["type"]}'}), 400
        
        # 根据类型更新特定字段
        if card.type == CardType.BUG:
            if 'severity' in data:
                card.severity = data['severity']
            if 'steps_to_reproduce' in data:
                card.steps_to_reproduce = data['steps_to_reproduce']
            if 'expected_result' in data:
                card.expected_result = data['expected_result']
            if 'actual_result' in data:
                card.actual_result = data['actual_result']
            if 'bug_type' in data:
                card.bug_type = data['bug_type']
            if 'environment' in data:
                card.environment = data['environment']
            if 'browser' in data:
                card.browser = data['browser']
            if 'os' in data:
                card.os = data['os']
        elif card.type == CardType.BADCASE:
            if 'case_category' in data:
                card.case_category = data['case_category']
            if 'base_problem' in data:
                card.base_problem = data['base_problem']
            if 'reproduction_steps' in data:
                card.reproduction_steps = data['reproduction_steps']
            if 'badcase_result' in data:
                card.badcase_result = data['badcase_result']
            if 'answer' in data:
                card.answer = data['answer']
            if 'correct_answer' in data:
                card.correct_answer = data['correct_answer']
            if 'problem_reason' in data:
                card.problem_reason = data['problem_reason']
            if 'solution' in data:
                card.solution = data['solution']
        elif card.type == CardType.TESTCASE:
            if 'case_type_test' in data:
                card.case_type_test = data['case_type_test']
            if 'test_type' in data:
                card.test_type = data['test_type']
            if 'preconditions' in data:
                card.preconditions = data['preconditions']
            if 'steps' in data:
                card.steps = data['steps']
            if 'remark' in data:
                card.remark = data['remark']
            if 'requirement_id' in data:
                card.requirement_id = data['requirement_id']
            if 'related_defects' in data:
                card.related_defects = data['related_defects']
            if 'baseline' in data:
                card.baseline = data['baseline']
            if 'estimated_time' in data:
                card.estimated_time = data['estimated_time']
            if 'actual_time' in data:
                card.actual_time = data['actual_time']
            if 'remaining_time' in data:
                card.remaining_time = data['remaining_time']
            if 'version' in data:
                card.version = data['version']
        
        _apply_card_type_change_defaults(card, old_card_type)
        
        card.updated_at = datetime.utcnow()
        db.session.commit()
        _cache_invalidate_cards(card.project_id)
        _schedule_grep_work_item_index("card", card.id)
        
        print(f"✅ 卡片更新成功: {card.id}")
        return jsonify({'success': True, 'data': card.to_dict()})
    
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        print(f"❌ 更新卡片失败: {e}")
        return jsonify({'success': False, 'error': f'更新卡片失败: {str(e)}'}), 500

@cards_api_bp.route('/api/cards/<int:card_id>', methods=['DELETE'])
@login_required
def api_delete_card(card_id):
    """删除卡片。Bug / BadCase / TestCase 类型卡片若仍关联源表记录，需二次确认后级联删除。"""
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

    print(f"=== 删除卡片 {card_id} ===")

    try:
        card = Card.query.get_or_404(card_id)

        if not has_project_permission(current_user.id, card.project_id):
            return jsonify({'success': False, 'error': '无权删除此卡片'}), 403

        _pid = card.project_id
        payload = request.get_json(silent=True) or {}
        confirm_cascade = any(
            [
                payload.get('confirm_cascade_sources') is True,
                payload.get('confirm_cascade_badcases') is True,
                payload.get('confirm_cascade_bugs') is True,
                payload.get('confirm_cascade_testcases') is True,
            ]
        )

        ctype = getattr(card, 'type', None)
        linked_badcases = []
        linked_bugs = []
        linked_testcases = []
        source_kind = None

        if ctype == CardType.BADCASE:
            linked_badcases = _collect_badcases_for_badcase_card(card)
            if linked_badcases:
                source_kind = 'badcase'
        elif ctype == CardType.BUG:
            linked_bugs = _collect_bugs_for_bug_card(card)
            if linked_bugs:
                source_kind = 'bug'
        elif ctype == CardType.TESTCASE:
            linked_testcases = _collect_testcases_for_testcase_card(card)
            if linked_testcases:
                source_kind = 'testcase'

        def _linked_items_payload(rows, title_attr='title'):
            out = []
            for r in rows:
                tid = getattr(r, 'id', None)
                if tid is None:
                    continue
                try:
                    tid_s = _json_snowflake_id(int(tid))
                except (TypeError, ValueError):
                    continue
                tv = getattr(r, title_attr, None) or ''
                out.append({'id': tid_s, 'title': (str(tv) or '')[:200]})
            return out

        need_confirm = (
            (linked_badcases or linked_bugs or linked_testcases) and not confirm_cascade
        )
        if need_confirm:
            rows = linked_badcases or linked_bugs or linked_testcases
            n = len(rows)
            sk = source_kind or 'badcase'
            err_cn = {
                'badcase': f'该 BadCase 卡片仍关联 {n} 条 BadCase，删除将永久删除源记录（含评论）及待审核修改。',
                'bug': f'该 Bug 卡片仍关联 {n} 条缺陷，删除将永久删除这些 Bug（含评论）及待审核修改。',
                'testcase': f'该测试用例卡片仍关联 {n} 条用例，删除将永久删除这些 TestCase 及待审核修改。',
            }.get(sk, f'该卡片仍关联 {n} 条源表记录。')
            return (
                jsonify(
                    {
                        'success': False,
                        'code': 'CASCADE_CARD_SOURCES_REQUIRED',
                        'source_kind': sk,
                        'error': err_cn + ' 请确认后请求体带上 confirm_cascade_sources=true 重试。',
                        'count': n,
                        'linked_items': _linked_items_payload(rows),
                        'linked_badcases': _linked_items_payload(linked_badcases)
                        if linked_badcases
                        else [],
                        'linked_bugs': _linked_items_payload(linked_bugs) if linked_bugs else [],
                        'linked_testcases': _linked_items_payload(linked_testcases)
                        if linked_testcases
                        else [],
                    }
                ),
                409,
            )

        deleted_bc = deleted_bug = deleted_tc = 0

        if linked_badcases and confirm_cascade:
            ids = [int(bc.id) for bc in linked_badcases]
            try:
                Comment.query.filter(Comment.badcase_id.in_(ids)).delete(synchronize_session=False)
            except Exception as _ce:
                print(f"[DELETE-CARD] 清理 Comment 失败（继续）: {_ce}", flush=True)
            try:
                _delete_diff_review_state_rows(_pid, 'badcase', ids, None)
            except Exception as _de:
                print(f"[DELETE-CARD] 清理 diff_review_state(badcase) 失败（继续）: {_de}", flush=True)
            try:
                BadCase.query.filter(BadCase.id.in_(ids)).delete(synchronize_session=False)
                deleted_bc = len(ids)
            except Exception as _be:
                db.session.rollback()
                print(f"❌ 级联删除 BadCase 失败: {_be}", flush=True)
                return jsonify({'success': False, 'error': f'级联删除 BadCase 失败: {str(_be)}'}), 500
            print(f"[DELETE-CARD] 卡片 {card_id} 级联删除 {deleted_bc} 条 bad_case", flush=True)

        if linked_bugs and confirm_cascade:
            ids = [int(b.id) for b in linked_bugs]
            try:
                BugComment.query.filter(BugComment.bug_id.in_(ids)).delete(synchronize_session=False)
            except Exception as _ce:
                print(f"[DELETE-CARD] 清理 bug_comment 失败（继续）: {_ce}", flush=True)
            try:
                _delete_diff_review_state_rows(_pid, 'bug', ids, None)
            except Exception as _de:
                print(f"[DELETE-CARD] 清理 diff_review_state(bug) 失败（继续）: {_de}", flush=True)
            try:
                Bug.query.filter(Bug.id.in_(ids)).delete(synchronize_session=False)
                deleted_bug = len(ids)
            except Exception as _be:
                db.session.rollback()
                print(f"❌ 级联删除 Bug 失败: {_be}", flush=True)
                return jsonify({'success': False, 'error': f'级联删除 Bug 失败: {str(_be)}'}), 500
            print(f"[DELETE-CARD] 卡片 {card_id} 级联删除 {deleted_bug} 条 bug", flush=True)

        if linked_testcases and confirm_cascade:
            ids = [int(tc.id) for tc in linked_testcases]
            try:
                TestCaseComment.query.filter(TestCaseComment.test_case_id.in_(ids)).delete(
                    synchronize_session=False
                )
            except Exception as _ce:
                print(f"[DELETE-CARD] 清理 test_case_comment 失败（继续）: {_ce}", flush=True)
            try:
                _delete_diff_review_state_rows(_pid, 'testcase', ids, None)
            except Exception as _de:
                print(f"[DELETE-CARD] 清理 diff_review_state(testcase) 失败（继续）: {_de}", flush=True)
            try:
                TestCase.query.filter(TestCase.id.in_(ids)).delete(synchronize_session=False)
                deleted_tc = len(ids)
            except Exception as _be:
                db.session.rollback()
                print(f"❌ 级联删除 TestCase 失败: {_be}", flush=True)
                return jsonify({'success': False, 'error': f'级联删除 TestCase 失败: {str(_be)}'}), 500
            print(f"[DELETE-CARD] 卡片 {card_id} 级联删除 {deleted_tc} 条 test_case", flush=True)

        try:
            CardPlanRelation.query.filter(CardPlanRelation.card_id == int(card_id)).delete(
                synchronize_session=False
            )
        except Exception as _re:
            print(f"[DELETE-CARD] 清理 card_plan_relation 失败（继续）: {_re}", flush=True)

        db.session.delete(card)
        db.session.commit()
        _cache_invalidate_cards(_pid)
        _cache_invalidate_plans(_pid)
        _schedule_grep_work_item_delete("card", card_id)
        for _bid in ([int(x.id) for x in linked_bugs] if linked_bugs else []):
            _schedule_grep_work_item_delete("bug", _bid)
        for _bcid in ([int(x.id) for x in linked_badcases] if linked_badcases else []):
            _schedule_grep_work_item_delete("badcase", _bcid)
        for _tcid in ([int(x.id) for x in linked_testcases] if linked_testcases else []):
            _schedule_grep_work_item_delete("testcase", _tcid)

        print(f"✅ 卡片删除成功: {card.id}")
        return jsonify(
            {
                'success': True,
                'message': '卡片删除成功',
                'deleted_linked_badcases': deleted_bc,
                'deleted_linked_bugs': deleted_bug,
                'deleted_linked_testcases': deleted_tc,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        print(f"❌ 删除卡片失败: {e}")
        return jsonify({'success': False, 'error': f'删除卡片失败: {str(e)}'}), 500


def _user_name_map(user_ids):
    ids = [int(x) for x in user_ids if x is not None]
    if not ids:
        return {}
    rows = db.session.query(User.id, User.name).filter(User.id.in_(ids)).all()
    return {uid: name for uid, name in rows}


@cards_api_bp.route('/api/projects/<int:project_id>/global-search', methods=['GET'])
@login_required
def api_project_global_search(project_id):
    """项目内全局搜索：计划、卡片、BadCase、Bug、测试用例（单次请求、库内 ilike 过滤）"""
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
        query_text = (request.args.get('query') or '').strip()
        per_type = min(max(request.args.get('per_type', 30, type=int), 1), 50)

        if not query_text:
            return jsonify({'success': True, 'results': []})

        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权访问此项目'}), 403

        pattern = f'%{query_text}%'
        results = []

        # 迭代计划
        plan_rows = (
            Plan.query.filter(Plan.project_id == project_id)
            .filter(db.or_(Plan.name.ilike(pattern), Plan.description.ilike(pattern)))
            .order_by(Plan.updated_at.desc())
            .limit(per_type)
            .all()
        )
        for p in plan_rows:
            results.append(
                {
                    'type': 'plan',
                    'id': _json_snowflake_id(p.id),
                    'title': p.name or f'Plan#{p.id}',
                    'status': p.status or '',
                    'status_text': p.status or '',
                    'details': [],
                }
            )

        # 迭代卡片
        card_rows = (
            Card.query.filter(Card.project_id == project_id)
            .filter(Card.type.in_([CardType.BUG, CardType.BADCASE, CardType.TESTCASE]))
            .filter(db.or_(Card.title.ilike(pattern), Card.description.ilike(pattern)))
            .order_by(Card.updated_at.desc())
            .limit(per_type)
            .all()
        )
        card_assignee_map = _user_name_map([c.assignee_id for c in card_rows])
        for c in card_rows:
            ctype = c.type.value if isinstance(c.type, CardType) else str(c.type or '')
            results.append(
                {
                    'type': 'card',
                    'groupKey': ctype if ctype in ('bug', 'badcase', 'testcase') else 'card',
                    'id': _json_snowflake_id(c.id),
                    'title': c.title,
                    'plan_id': _json_snowflake_id(c.plan_id),
                    'cardType': ctype,
                    'status': '',
                    'status_text': '',
                    'assignee': card_assignee_map.get(c.assignee_id) if c.assignee_id else None,
                    'details': [],
                }
            )

        # BadCase 实体
        bc_rows = (
            BadCase.query.filter(BadCase.project_id == project_id)
            .filter(
                db.or_(
                    BadCase.title.ilike(pattern),
                    BadCase.case_category.ilike(pattern),
                    BadCase.base_problem.ilike(pattern),
                    BadCase.reproduction_steps.ilike(pattern),
                    BadCase.answer.ilike(pattern),
                    BadCase.correct_answer.ilike(pattern),
                )
            )
            .order_by(BadCase.updated_at.desc())
            .limit(per_type)
            .all()
        )
        for bc in bc_rows:
            st = _badcase_status_str(bc)
            results.append(
                {
                    'type': 'badcase',
                    'groupKey': 'badcase',
                    'id': _json_snowflake_id(bc.id),
                    'title': bc.title or bc.case_category or f'BadCase#{bc.id}',
                    'status': st or 'open',
                    'status_text': st,
                    'plan_id': _json_snowflake_id(bc.plan_id),
                    'card_id': _json_snowflake_id(getattr(bc, 'card_id', None)),
                    'details': [],
                }
            )

        # Bug 实体
        bug_rows = (
            Bug.query.filter(Bug.project_id == project_id)
            .filter(
                db.or_(
                    Bug.title.ilike(pattern),
                    Bug.steps_to_reproduce.ilike(pattern),
                    Bug.bug_type.ilike(pattern),
                )
            )
            .order_by(Bug.updated_at.desc())
            .limit(per_type)
            .all()
        )
        bug_assignee_map = _user_name_map([b.assignee_id for b in bug_rows])
        for b in bug_rows:
            results.append(
                {
                    'type': 'bug',
                    'groupKey': 'bug',
                    'id': _json_snowflake_id(b.id),
                    'title': b.title,
                    'status': b.status or 'open',
                    'status_text': b.status or '',
                    'plan_id': _json_snowflake_id(b.plan_id),
                    'card_id': _json_snowflake_id(b.card_id),
                    'assignee': bug_assignee_map.get(b.assignee_id) if b.assignee_id else None,
                    'details': [],
                }
            )

        # 测试用例实体
        tc_rows = (
            TestCase.query.filter(TestCase.project_id == project_id)
            .filter(
                db.or_(
                    TestCase.title.ilike(pattern),
                    TestCase.case_type.ilike(pattern),
                    TestCase.remark.ilike(pattern),
                )
            )
            .order_by(TestCase.updated_at.desc())
            .limit(per_type)
            .all()
        )
        tc_assignee_map = _user_name_map([t.assignee_id for t in tc_rows])
        for t in tc_rows:
            st = _testcase_status_str(t)
            results.append(
                {
                    'type': 'testcase',
                    'groupKey': 'testcase',
                    'id': _json_snowflake_id(t.id),
                    'title': t.title,
                    'status': st or 'active',
                    'status_text': st,
                    'plan_id': _json_snowflake_id(t.plan_id),
                    'card_id': _json_snowflake_id(getattr(t, 'card_id', None)),
                    'assignee': tc_assignee_map.get(t.assignee_id) if t.assignee_id else None,
                    'details': [],
                }
            )

        return jsonify({'success': True, 'results': results})
    except Exception as e:
        print(f'❌ 全局搜索失败: {e}')
        return jsonify({'success': False, 'error': f'搜索失败: {str(e)}'}), 500


@cards_api_bp.route('/api/cards/search', methods=['GET'])
@login_required
def api_search_cards():
    """全局搜索卡片"""
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

    print(f"=== 全局搜索卡片 ===")
    
    try:
        query_text = request.args.get('query', '').strip()
        types_param = request.args.get('types', 'bug,badcase,testcase')
        project_id = request.args.get('project_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        if not query_text:
            return jsonify({
                'success': True,
                'data': {'results': [], 'counts': {}}
            })
        
        # 解析类型
        types = [t.strip() for t in types_param.split(',') if t.strip()]
        
        # 构建基础查询
        base_query = Card.query
        
        # 项目过滤
        if project_id:
            base_query = base_query.filter(Card.project_id == project_id)
        
        # 类型过滤
        if types:
            base_query = base_query.filter(Card.type.in_(types))
        
        # 全文搜索 (标题和描述)
        search_pattern = f'%{query_text}%'
        base_query = base_query.filter(
            db.or_(
                Card.title.ilike(search_pattern),
                Card.description.ilike(search_pattern)
            )
        )
        
        # 分页查询
        pagination = base_query.order_by(Card.updated_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        results = [card.to_dict() for card in pagination.items]
        
        assignee_map = _user_name_map([r.get('assignee_id') for r in results])
        for result in results:
            aid = result.get('assignee_id')
            if aid and assignee_map.get(aid):
                result['assignee'] = assignee_map[aid]

        counts = {}
        if (request.args.get('include_counts') or '').strip().lower() in ('1', 'true', 'yes'):
            counts_query = Card.query
            if project_id:
                counts_query = counts_query.filter(Card.project_id == project_id)
            for t in types:
                counts[t] = counts_query.filter(Card.type == t).filter(
                    db.or_(
                        Card.title.ilike(search_pattern),
                        Card.description.ilike(search_pattern),
                    )
                ).count()
        
        print(f"✅ 搜索完成，找到 {len(results)} 条结果")
        return jsonify({
            'success': True,
            'data': {
                'results': results,
                'counts': counts,
                'pagination': {
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'current_page': page,
                    'per_page': per_page
                }
            }
        })
    
    except Exception as e:
        print(f"❌ 搜索卡片失败: {e}")
        return jsonify({'success': False, 'error': f'搜索卡片失败: {str(e)}'}), 500

@cards_api_bp.route('/api/cards/<int:card_id>/move', methods=['POST'])
@login_required
def api_move_card(card_id):
    """移动卡片到指定计划"""
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

    print(f"=== 移动卡片 {card_id} ===")
    
    try:
        card = Card.query.get_or_404(card_id)
        
        # 检查权限
        if not has_project_permission(current_user.id, card.project_id):
            return jsonify({'success': False, 'error': '无权移动此卡片'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        target_plan_id = data.get('plan_id')  # None表示移至未计划
        
        # 验证目标计划存在（如果指定了）
        if target_plan_id is not None and str(target_plan_id).strip() != '':
            tid = _coerce_optional_bigint_json(target_plan_id)
            plan = Plan.query.get(tid) if tid is not None else None
            if not plan:
                return jsonify({'success': False, 'error': '目标计划不存在'}), 404
            if plan.project_id != card.project_id:
                return jsonify({'success': False, 'error': '目标计划不属于同一项目'}), 400
            target_plan_id = tid
        else:
            target_plan_id = None
        
        old_plan_id = card.plan_id
        card.plan_id = target_plan_id
        card.updated_at = datetime.utcnow()
        
        db.session.commit()
        _cache_invalidate_cards(card.project_id)
        
        print(f"✅ 卡片移动成功: {card.id}, 从计划 {old_plan_id} -> {target_plan_id}")
        return jsonify({
            'success': True,
            'data': card.to_dict(),
            'message': f'卡片已移动至{"计划 " + str(target_plan_id) if target_plan_id else "未计划"}'
        })
    
    except HTTPException:
        raise
    except Exception as e:
        db.session.rollback()
        print(f"❌ 移动卡片失败: {e}")
        return jsonify({'success': False, 'error': f'移动卡片失败: {str(e)}'}), 500

# ==================== 卡片类型管理 API ====================

@cards_api_bp.route('/api/card-types', methods=['GET'])
@login_required
def api_get_card_types():
    """获取卡片类型列表"""
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

    print(f"=== 获取卡片类型列表 ===")
    
    try:
        project_id = request.args.get('project_id', type=int)
        
        query = CardTypeDefinition.query
        
        if project_id:
            query = query.filter(CardTypeDefinition.project_id == project_id)
        
        # 只返回启用的类型
        query = query.filter(CardTypeDefinition.is_active == True)
        
        types = query.order_by(CardTypeDefinition.sort_order.asc()).all()
        
        return jsonify({
            'success': True,
            'data': [t.to_dict() for t in types]
        })
    
    except Exception as e:
        print(f"❌ 获取卡片类型失败: {e}")
        return jsonify({'success': False, 'error': f'获取卡片类型失败: {str(e)}'}), 500

@cards_api_bp.route('/api/card-types', methods=['POST'])
@login_required
def api_create_card_type():
    """创建卡片类型"""
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

    print(f"=== 创建卡片类型 ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        project_id = data.get('project_id')
        name = data.get('name')
        code = data.get('code')
        
        if not all([project_id, name, code]):
            return jsonify({'success': False, 'error': '缺少必填字段'}), 400
        
        # 检查权限
        if not has_project_permission(current_user.id, project_id):
            return jsonify({'success': False, 'error': '无权创建此卡片类型'}), 403
        
        # 检查code唯一性
        existing = CardTypeDefinition.query.filter_by(code=code).first()
        if existing:
            return jsonify({'success': False, 'error': '类型代码已存在'}), 400
        
        card_type = CardTypeDefinition(
            project_id=project_id,
            name=name,
            code=code,
            icon=data.get('icon'),
            color=data.get('color'),
            description=data.get('description'),
            fields_config=data.get('fields_config'),
            status_config=data.get('status_config'),
            sort_order=data.get('sort_order', 0)
        )
        
        db.session.add(card_type)
        db.session.commit()
        
        print(f"✅ 卡片类型创建成功: {card_type.id}")
        return jsonify({
            'success': True,
            'data': card_type.to_dict()
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 创建卡片类型失败: {e}")
        return jsonify({'success': False, 'error': f'创建卡片类型失败: {str(e)}'}), 500

@cards_api_bp.route('/api/card-types/<int:type_id>', methods=['PUT'])
@login_required
def api_update_card_type(type_id):
    """更新卡片类型"""
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

    print(f"=== 更新卡片类型 {type_id} ===")
    
    try:
        card_type = CardTypeDefinition.query.get_or_404(type_id)
        
        if not has_project_permission(current_user.id, card_type.project_id):
            return jsonify({'success': False, 'error': '无权修改此卡片类型'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        # 更新字段
        for field in ['name', 'icon', 'color', 'description', 'fields_config', 'status_config', 'sort_order', 'is_active']:
            if field in data:
                setattr(card_type, field, data[field])
        
        db.session.commit()
        
        print(f"✅ 卡片类型更新成功: {card_type.id}")
        return jsonify({
            'success': True,
            'data': card_type.to_dict()
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 更新卡片类型失败: {e}")
        return jsonify({'success': False, 'error': f'更新卡片类型失败: {str(e)}'}), 500

@cards_api_bp.route('/api/card-types/<int:type_id>', methods=['DELETE'])
@login_required
def api_delete_card_type(type_id):
    """删除卡片类型"""
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

    print(f"=== 删除卡片类型 {type_id} ===")
    
    try:
        card_type = CardTypeDefinition.query.get_or_404(type_id)
        
        if not has_project_permission(current_user.id, card_type.project_id):
            return jsonify({'success': False, 'error': '无权删除此卡片类型'}), 403
        
        # 软删除
        card_type.is_active = False
        db.session.commit()
        
        print(f"✅ 卡片类型删除成功: {card_type.id}")
        return jsonify({
            'success': True,
            'message': '卡片类型删除成功'
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 删除卡片类型失败: {e}")
        return jsonify({'success': False, 'error': f'删除卡片类型失败: {str(e)}'}), 500

# ==================== 卡片计划关联关系 API ====================

@cards_api_bp.route('/api/card-plan-relations', methods=['GET'])
@login_required
def api_get_card_plan_relations():
    """获取卡片与计划的关联关系"""
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

    print(f"=== 获取卡片计划关联关系 ===")
    
    try:
        card_id = _parse_query_optional_int64('card_id')
        plan_id = _parse_query_optional_int64('plan_id')
        include_removed = request.args.get('include_removed', 'false').lower() == 'true'
        
        query = CardPlanRelation.query
        
        if card_id:
            query = query.filter(CardPlanRelation.card_id == card_id)
        if plan_id:
            query = query.filter(CardPlanRelation.plan_id == plan_id)
        if not include_removed:
            query = query.filter(CardPlanRelation.removed_at.is_(None))
        
        relations = query.order_by(CardPlanRelation.sort_order.asc()).all()
        
        return jsonify({
            'success': True,
            'data': [r.to_dict() for r in relations]
        })
    
    except Exception as e:
        print(f"❌ 获取关联关系失败: {e}")
        return jsonify({'success': False, 'error': f'获取关联关系失败: {str(e)}'}), 500

@cards_api_bp.route('/api/card-plan-relations', methods=['POST'])
@login_required
def api_create_card_plan_relation():
    """创建卡片与计划的关联"""
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

    print(f"=== 创建卡片计划关联 ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
        
        card_id = data.get('card_id')
        plan_id = data.get('plan_id')
        
        if not all([card_id, plan_id]):
            return jsonify({'success': False, 'error': '缺少必填字段'}), 400
        
        # 检查卡片是否存在
        card = Card.query.get(card_id)
        if not card:
            return jsonify({'success': False, 'error': '卡片不存在'}), 404
        
        # 检查计划是否存在
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查是否已存在关联
        relation_type = data.get('relation_type', 'primary')
        existing = CardPlanRelation.query.filter_by(
            card_id=card_id,
            plan_id=plan_id,
            relation_type=relation_type
        ).filter(CardPlanRelation.removed_at.is_(None)).first()
        
        if existing:
            return jsonify({'success': False, 'error': '关联关系已存在'}), 400
        
        relation = CardPlanRelation(
            card_id=card_id,
            plan_id=plan_id,
            relation_type=relation_type,
            status_in_plan=data.get('status_in_plan'),
            sort_order=data.get('sort_order', 0)
        )
        
        db.session.add(relation)
        db.session.commit()
        
        print(f"✅ 关联关系创建成功: {relation.id}")
        return jsonify({
            'success': True,
            'data': relation.to_dict()
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 创建关联关系失败: {e}")
        return jsonify({'success': False, 'error': f'创建关联关系失败: {str(e)}'}), 500

@cards_api_bp.route('/api/card-plan-relations/<int:relation_id>', methods=['DELETE'])
@login_required
def api_delete_card_plan_relation(relation_id):
    """删除卡片与计划的关联（软删除）"""
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

    print(f"=== 删除卡片计划关联 {relation_id} ===")
    
    try:
        relation = CardPlanRelation.query.get_or_404(relation_id)
        
        # 软删除
        relation.removed_at = datetime.utcnow()
        db.session.commit()
        
        print(f"✅ 关联关系删除成功: {relation.id}")
        return jsonify({
            'success': True,
            'message': '关联关系删除成功'
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ 删除关联关系失败: {e}")
        return jsonify({'success': False, 'error': f'删除关联关系失败: {str(e)}'}), 500

@cards_api_bp.route('/api/cards/<int:card_id>/history', methods=['GET'])
