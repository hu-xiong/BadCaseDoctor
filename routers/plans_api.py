"""计划相关 REST API（自 app.py 拆出）。"""
from __future__ import annotations

import time
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

plans_bp = Blueprint("plans", __name__)


def _app():
    """延迟导入 app 模块（注册 blueprint 时 app 已加载完成）。"""
    import app as _application
    return _application


# 计划相关API接口
@plans_bp.route('/api/plans', methods=['POST'])
@login_required
def api_create_plan():
    """创建计划"""
    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _detach_plan_work_items = a._detach_plan_work_items

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
        try:
            plan_project_id = int(data['project_id'])
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': '无效的 project_id'}), 400

        from utils.project_clone import ensure_project_admin_permission, system_project_template_id

        ensure_project_admin_permission(plan_project_id, int(current_user.id))
        db.session.flush()
        tpl_id = system_project_template_id()
        if tpl_id and plan_project_id == int(tpl_id):
            tpl_proj = Plan.query.get(plan_project_id)
            if tpl_proj and int(tpl_proj.user_id) != int(current_user.id):
                return jsonify({
                    'success': False,
                    'error': '无法直接在系统模板项目上操作，请刷新页面进入您的默认项目',
                }), 403

        if not has_project_permission(current_user.id, plan_project_id):
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

        pid = plan_project_id

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

@plans_bp.route('/api/plans/<int:plan_id>', methods=['GET'])
@login_required
def api_get_plan_detail(plan_id):
    """获取计划详情"""
    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _detach_plan_work_items = a._detach_plan_work_items

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

@plans_bp.route('/api/plans/<int:plan_id>', methods=['PUT'])
@login_required
def api_update_plan(plan_id):
    """更新计划"""
    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _detach_plan_work_items = a._detach_plan_work_items

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

@plans_bp.route('/api/plans/<int:plan_id>', methods=['DELETE'])
@login_required
def api_delete_plan(plan_id):
    """删除计划"""
    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _detach_plan_work_items = a._detach_plan_work_items

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

@plans_bp.route('/api/plans/<int:plan_id>/pin', methods=['POST'])
@login_required
def api_pin_plan(plan_id):
    """置顶/取消置顶计划"""
    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _detach_plan_work_items = a._detach_plan_work_items

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


@plans_bp.route('/api/projects/<int:project_id>/plans', methods=['GET'])
@login_required
def api_get_project_plans(project_id):
    """获取项目的计划树"""
    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _detach_plan_work_items = a._detach_plan_work_items

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


@plans_bp.route('/api/plans/<int:plan_id>/testcases', methods=['GET'])
@login_required
def api_get_plan_testcases(plan_id):
    """获取计划下的所有测试用例（支持 count_only=1 仅返回数量）"""
    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _detach_plan_work_items = a._detach_plan_work_items

    try:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        # 仅返回数量，避免 405 等路由问题
        count_only = request.args.get('count_only')
        if count_only in ('1', 1) or str(count_only) == '1':
            try:
                n = TestCase.query.filter_by(plan_id=plan_id).count()
                return jsonify({'success': True, 'count': n})
            except Exception as ce:
                print(f"获取计划{plan_id}测试用例数量失败: {ce}")
                return jsonify({'success': False, 'error': str(ce)}), 500
        
        testcases = TestCase.query.filter_by(plan_id=plan_id).all()
        
        testcase_list = []
        for tc in testcases:
            testcase_list.append({
                'id': _json_snowflake_id(tc.id),
                'title': tc.title,
                'status': tc.status,
                'case_type': tc.case_type,
                'priority': tc.priority,
                'test_type': tc.test_type,
                'version': tc.version,
                'execution_result': tc.execution_result,
                'created_at': tc.created_at.isoformat(),
                'updated_at': tc.updated_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'testcases': testcase_list
        })
        
    except Exception as e:
        import traceback
        print(f"获取计划TestCase列表失败: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@plans_bp.route('/api/plans/<int:plan_id>/bugs', methods=['GET'])
@login_required
def api_get_plan_bugs(plan_id):
    """获取计划下的所有Bug"""
    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _detach_plan_work_items = a._detach_plan_work_items

    try:
        plan = Plan.query.get(plan_id)
        if not plan:
            return jsonify({'success': False, 'error': '计划不存在'}), 404
        
        # 检查项目权限
        if not has_project_permission(current_user.id, plan.project_id):
            return jsonify({'success': False, 'error': '没有项目权限'}), 403
        
        bugs = Bug.query.filter_by(plan_id=plan_id).all()
        
        bug_list = []
        for bug in bugs:
            bug_list.append({
                'id': _json_snowflake_id(bug.id),
                'title': bug.title,
                'status': bug.status,
                'priority': bug.priority,
                'severity': bug.severity,
                'created_at': bug.created_at.isoformat() if bug.created_at else None,
                'updated_at': bug.updated_at.isoformat() if bug.updated_at else None
            })
        
        return jsonify({
            'success': True,
            'bugs': bug_list
        })
        
    except Exception as e:
        print(f"获取计划Bug列表失败: {e}")
        return jsonify({'success': False, 'error': '获取Bug列表失败'}), 500

