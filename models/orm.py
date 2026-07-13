"""SQLAlchemy ORM 实体（自 app.py 拆出；通过 app 模块 re-export）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from flask_login import UserMixin
from sqlalchemy import Enum, Text, and_, event, inspect, or_, text
from sqlalchemy.dialects.mysql import LONGTEXT

from db_extensions import db
from models.enums import (
    BadCaseStatus,
    BugStatus,
    CardType,
    ExecutionResult,
    ProposalStatus,
    TestCaseStatus,
)

# 数据模型
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='collaborator')  # admin, collaborator
    is_verified = db.Column(db.Boolean, default=False)  # 邮箱验证状态
    verification_code = db.Column(db.String(10))  # 邮箱验证码
    verification_expires = db.Column(db.DateTime)  # 验证码过期时间
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserCredits(db.Model):
    """用户额度表"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    credits = db.Column(db.Integer, default=0)  # 剩余使用次数
    total_purchased = db.Column(db.Integer, default=0)  # 累计购买次数
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class PaymentHistory(db.Model):
    """支付历史记录"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    plan_id = db.Column(db.String(50), nullable=False)  # basic/standard/professional/enterprise
    credits = db.Column(db.Integer, nullable=False)  # 购买的额度
    amount = db.Column(db.Integer, nullable=False)  # 支付金额(美分)
    stripe_session_id = db.Column(db.String(200))  # Stripe 会话ID
    status = db.Column(db.String(20), default='pending')  # pending/completed/failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    avatar = db.Column(db.String(500))  # 项目头像URL
    owner = db.Column(db.String(100))  # 负责人名称
    intro = db.Column(db.Text)  # 项目介绍语
    status = db.Column(db.String(20), default='published')  # published, unpublished
    login_configs = db.Column(db.Text)  # 网站登录配置 JSON: [{"url": "...", "username": "...", "password": "..."}]
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, nullable=False)
    # 用户从系统模板克隆的「默认项目」副本；与模板 project（SYSTEM_PROJECT_TEMPLATE_ID）区分
    is_default = db.Column(db.Boolean, default=False, nullable=False, index=True)
    cloned_from_template_id = db.Column(db.Integer, nullable=True)

class ProjectPermission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, collaborator
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    project_id = db.Column(db.Integer, nullable=False)
    creator_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    role = db.Column(db.String(20), default='member')  # leader, member
    permissions = db.Column(db.Text)  # 权限JSON字符串
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 不使用 backref，避免依赖外键


def _json_snowflake_id(value):
    """超过 JS Number.MAX_SAFE_INTEGER 的整型主键/外键：JSON 输出为字符串，避免前端精度丢失。"""
    if value is None:
        return None
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return value


def _json_snowflake_ids_in_list(seq):
    """JSON 列中雪花 id 列表（如 related_defects）统一为字符串。"""
    if seq is None:
        return None
    if isinstance(seq, (list, tuple)):
        out = []
        for x in seq:
            if isinstance(x, dict):
                out.append(x)
            else:
                out.append(_json_snowflake_id(x) if x is not None else None)
        return out
    return seq


def _testcase_related_defects_detail_payload(testcase) -> list:
    """测例详情 API：关联缺陷返回 {id, title, plan_id}，供前端展示 Bug 标题而非纯 id。"""
    raw = getattr(testcase, "related_defects", None) or []
    ids = _json_snowflake_ids_in_list(raw)
    if not ids:
        return []
    if not isinstance(ids, list):
        return []
    id_strs = []
    for x in ids:
        if isinstance(x, dict):
            sid = _json_snowflake_id(x.get("id"))
            if sid:
                id_strs.append(str(sid))
        else:
            sid = _json_snowflake_id(x)
            if sid:
                id_strs.append(str(sid))
    if not id_strs:
        return []
    try:
        id_ints = [int(x) for x in id_strs]
        rows = (
            db.session.query(Bug)
            .filter(Bug.project_id == testcase.project_id, Bug.id.in_(id_ints))
            .all()
        )
        by_id = {}
        for b in rows:
            bid = _json_snowflake_id(b.id)
            if not bid:
                continue
            by_id[str(bid)] = {
                "id": str(bid),
                "title": (b.title or "").strip(),
                "plan_id": _json_snowflake_id(b.plan_id),
            }
        return [by_id.get(bid, {"id": bid, "title": "", "plan_id": None}) for bid in id_strs]
    except Exception as ex:
        print(f"[API] related_defects 标题补全失败: {ex}", flush=True)
        return [{"id": bid, "title": "", "plan_id": None} for bid in id_strs]


def _testcase_comments_detail_payload(test_case_id: int) -> list:
    """测例评论列表（只读展示，按时间升序）。"""
    try:
        rows = (
            db.session.query(TestCaseComment, User.name)
            .outerjoin(User, User.id == TestCaseComment.user_id)
            .filter(TestCaseComment.test_case_id == int(test_case_id))
            .order_by(TestCaseComment.created_at.asc())
            .all()
        )
        return _comments_detail_payload(rows)
    except Exception as ex:
        print(f"[_testcase_comments_detail_payload] {ex}", flush=True)
        return []


def _comment_author_name(user_id: int) -> str:
    try:
        u = User.query.get(int(user_id))
        if u:
            return (u.name or "").strip()
    except Exception:
        pass
    return ""


def _invalidate_testcase_detail_cache(test_case_id) -> None:
    try:
        _redis_cache_delete(f"testcase-detail:{int(test_case_id)}")
    except Exception:
        pass


def _comment_row_to_dict(row, user_name='', parent_user_name='', *, pending=False, client_temp_id=None):
    created = row.created_at.isoformat() if getattr(row, 'created_at', None) else None
    if pending and client_temp_id:
        row_id = client_temp_id
    else:
        row_id = row.id if hasattr(row, 'id') and row.id is not None else client_temp_id
    pid = getattr(row, 'parent_id', None)
    return {
        'id': row_id,
        'content': row.content if hasattr(row, 'content') else '',
        'user_id': getattr(row, 'user_id', None),
        'user_name': user_name or '',
        'parent_id': int(pid) if pid else None,
        'parent_user_name': parent_user_name or '',
        'source_message_id': getattr(row, 'source_message_id', None),
        'created_at': created,
        'pending': bool(pending),
    }


def _comment_parent_user_name_map(rows):
    """rows: [(comment_obj, user_name), ...]"""
    by_id = {}
    for c, uname in rows:
        by_id[c.id] = uname or ''
    out = {}
    for c, _uname in rows:
        pid = getattr(c, 'parent_id', None)
        if pid:
            out[c.id] = by_id.get(pid, '')
    return out


def _comments_detail_payload(rows):
    parent_names = _comment_parent_user_name_map(rows)
    out = []
    for c, uname in rows:
        out.append(
            _comment_row_to_dict(
                c,
                uname or '',
                parent_user_name=parent_names.get(c.id, ''),
            )
        )
    return out


def _validate_comment_parent(entity_type: str, entity_id: int, parent_id):
    if parent_id in (None, '', 0):
        return None, None
    try:
        pid = int(parent_id)
    except (TypeError, ValueError):
        return '无效的回复目标', None
    if entity_type == 'bug':
        parent = BugComment.query.filter_by(id=pid, bug_id=int(entity_id)).first()
    elif entity_type == 'badcase':
        parent = Comment.query.filter_by(id=pid, badcase_id=int(entity_id)).first()
    elif entity_type == 'testcase':
        parent = TestCaseComment.query.filter_by(id=pid, test_case_id=int(entity_id)).first()
    else:
        return '未知实体类型', None
    if not parent:
        return '回复的评论不存在或不属于当前记录', None
    return None, _comment_author_name(parent.user_id)


def _persist_comment_from_queue_job(job: dict) -> dict:
    entity_type = (job.get('entity_type') or '').strip()
    entity_id = int(job['entity_id'])
    user_id = int(job['user_id'])
    content = (job.get('content') or '').strip()
    if not content:
        raise ValueError('评论内容不能为空')
    parent_id = job.get('parent_id')
    source_message_id = _safe_mysql_int_fk_id(job.get('source_message_id'))
    err, parent_user_name = _validate_comment_parent(entity_type, entity_id, parent_id)
    if err:
        raise ValueError(err)
    pid = int(parent_id) if parent_id else None

    if entity_type == 'bug':
        if not Bug.query.get(entity_id):
            raise ValueError('Bug不存在')
        row = BugComment(
            bug_id=entity_id,
            user_id=user_id,
            content=content,
            parent_id=pid,
            source_message_id=source_message_id,
        )
    elif entity_type == 'badcase':
        if not BadCase.query.get(entity_id):
            raise ValueError('BadCase不存在')
        row = Comment(
            badcase_id=entity_id,
            user_id=user_id,
            content=content,
            parent_id=pid,
            source_message_id=source_message_id,
        )
    elif entity_type == 'testcase':
        testcase = TestCase.query.get(entity_id)
        if not testcase:
            raise ValueError('测试用例不存在')
        row = TestCaseComment(
            test_case_id=entity_id,
            user_id=user_id,
            content=content,
            parent_id=pid,
            source_message_id=source_message_id,
        )
    else:
        raise ValueError('未知实体类型')

    db.session.add(row)
    db.session.flush()
    if entity_type == 'testcase':
        _invalidate_testcase_detail_cache(entity_id)
    uname = _comment_author_name(user_id)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return _comment_row_to_dict(row, uname, parent_user_name=parent_user_name or '')


def _submit_entity_comment_via_queue(
    entity_type: str,
    entity_id: int,
    content: str,
    user_id: int,
    user_name: str,
    *,
    parent_id=None,
    source_message_id=None,
):
    text = (content or '').strip()
    if not text:
        return {'success': False, 'error': '评论内容不能为空'}, 400
    err, parent_user_name = _validate_comment_parent(entity_type, entity_id, parent_id)
    if err:
        return {'success': False, 'error': err}, 400

    from utils import comment_queue as cq

    client_temp_id = cq.new_client_temp_id()
    job = {
        'entity_type': entity_type,
        'entity_id': int(entity_id),
        'user_id': int(user_id),
        'content': text,
        'parent_id': int(parent_id) if parent_id else None,
        'source_message_id': _safe_mysql_int_fk_id(source_message_id),
        'client_temp_id': client_temp_id,
    }

    class _PendingRow:
        def __init__(self):
            self.id = client_temp_id
            self.content = text
            self.user_id = user_id
            self.parent_id = int(parent_id) if parent_id else None
            self.source_message_id = _safe_mysql_int_fk_id(source_message_id)
            self.created_at = datetime.utcnow()

    optimistic = _comment_row_to_dict(
        _PendingRow(),
        user_name or '',
        parent_user_name=parent_user_name or '',
        pending=True,
        client_temp_id=client_temp_id,
    )

    redis_client = get_redis_client()
    if cq.enqueue(redis_client, job):
        return {
            'success': True,
            'async': True,
            'message': '评论已提交，正在落库',
            'comment': optimistic,
            'client_temp_id': client_temp_id,
        }, 200

    try:
        comment = _persist_comment_from_queue_job(job)
        return {
            'success': True,
            'async': False,
            'message': '评论添加成功',
            'comment': comment,
        }, 200
    except Exception as e:
        db.session.rollback()
        print(f"[API] 评论落库失败({entity_type}): {e}", flush=True)
        return {'success': False, 'error': '追加评论失败'}, 500


def _append_testcase_comment_row(
    testcase,
    content: str,
    user_id: int,
    source_message_id=None,
    parent_id=None,
) -> dict:
    """向测例追加一条评论（不可修改历史评论）。"""
    text = (content or "").strip()
    if not text:
        raise ValueError("评论内容不能为空")
    err, parent_user_name = _validate_comment_parent('testcase', int(testcase.id), parent_id)
    if err:
        raise ValueError(err)
    row = TestCaseComment(
        test_case_id=int(testcase.id),
        user_id=int(user_id),
        content=text,
        parent_id=int(parent_id) if parent_id else None,
        source_message_id=_safe_mysql_int_fk_id(source_message_id),
    )
    db.session.add(row)
    db.session.flush()
    _invalidate_testcase_detail_cache(testcase.id)
    uname = _comment_author_name(user_id)
    return _comment_row_to_dict(row, uname, parent_user_name=parent_user_name or '')


def _append_bug_comment_row(bug, content: str, user_id: int, source_message_id=None, parent_id=None) -> dict:
    text = (content or "").strip()
    if not text:
        raise ValueError("评论内容不能为空")
    err, parent_user_name = _validate_comment_parent('bug', int(bug.id), parent_id)
    if err:
        raise ValueError(err)
    row = BugComment(
        bug_id=int(bug.id),
        user_id=int(user_id),
        content=text,
        parent_id=int(parent_id) if parent_id else None,
        source_message_id=_safe_mysql_int_fk_id(source_message_id),
    )
    db.session.add(row)
    db.session.flush()
    uname = _comment_author_name(user_id)
    return _comment_row_to_dict(row, uname, parent_user_name=parent_user_name or '')


def _append_badcase_comment_row(badcase, content: str, user_id: int, source_message_id=None, parent_id=None) -> dict:
    text = (content or "").strip()
    if not text:
        raise ValueError("评论内容不能为空")
    err, parent_user_name = _validate_comment_parent('badcase', int(badcase.id), parent_id)
    if err:
        raise ValueError(err)
    row = Comment(
        badcase_id=int(badcase.id),
        user_id=int(user_id),
        content=text,
        parent_id=int(parent_id) if parent_id else None,
        source_message_id=_safe_mysql_int_fk_id(source_message_id),
    )
    db.session.add(row)
    db.session.flush()
    uname = _comment_author_name(user_id)
    return _comment_row_to_dict(row, uname, parent_user_name=parent_user_name or '')


class BadCase(db.Model):
    __tablename__ = 'bad_case'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    project_id = db.Column(db.Integer, nullable=False)
    plan_id = db.Column(db.BigInteger)  # 关联计划
    creator_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200))  # BadCase标题
    case_category = db.Column(db.String(100), nullable=False)  # 问题分类
    base_problem = db.Column(db.Text, nullable=False)  # 具体问题
    reproduction_steps = db.Column(db.Text)  # 复现步骤
    badcase_result = db.Column(db.Text, nullable=False)  # badcase问题结果
    answer = db.Column(db.Text, nullable=False)  # 答案（原 correct_answer）
    correct_answer = db.Column(db.Text)  # 正确答案（原 correct_answer_final）
    problem_reason = db.Column(db.Text)  # 问题原因
    needs_processing = db.Column(db.Boolean, default=True)  # 是否需要处理
    solution = db.Column(db.Text)  # 解决方式
    is_verified = db.Column(db.Boolean, default=False)  # 是否验证
    priority = db.Column(db.String(10), default='p3')  # p1, p2, p3
    status = db.Column(Enum(BadCaseStatus, values_callable=lambda obj: [e.value for e in obj]), default=BadCaseStatus.NEW, nullable=False)
    assignee = db.Column(db.String(100))  # 负责人
    plan = db.Column(db.String(100))  # 所属计划（保留字段，用于向后兼容）
    document_type = db.Column(db.String(100))  # 文档类型
    attachments = db.Column(db.Text)  # 附件信息，JSON格式存储
    assigned_users = db.Column(db.Text)  # 指派的人员，JSON格式存储
    card_id = db.Column(db.BigInteger, nullable=True)  # 关联迭代卡片 Card.id（与 Bug.card_id 一致）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


    
    def to_dict(self):
        """序列化为字典，处理枚举值"""
        return {
            'id': _json_snowflake_id(self.id),
            'project_id': self.project_id,
            'plan_id': _json_snowflake_id(self.plan_id),
            'creator_id': self.creator_id,
            'title': self.title,
            'case_category': self.case_category,
            'base_problem': self.base_problem,
            'reproduction_steps': self.reproduction_steps,
            'badcase_result': self.badcase_result,
            'answer': self.answer,
            'correct_answer': self.correct_answer,
            'problem_reason': self.problem_reason,
            'needs_processing': self.needs_processing,
            'solution': self.solution,
            'is_verified': self.is_verified,
            'priority': self.priority,
            'status': self.status.value if isinstance(self.status, BadCaseStatus) else self.status,
            'assignee': self.assignee,
            'plan': self.plan,
            'document_type': self.document_type,
            'attachments': self.attachments,
            'assigned_users': self.assigned_users,
            'card_id': _json_snowflake_id(getattr(self, 'card_id', None)),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    badcase_id = db.Column(db.BigInteger, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)  # 富文本内容
    parent_id = db.Column(db.Integer, nullable=True, index=True)
    source_message_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Plan(db.Model):
    __tablename__ = 'plan'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    name = db.Column(db.String(200), nullable=False)  # 计划名称
    description = db.Column(db.Text)  # 计划描述
    status = db.Column(db.String(20), default='active')  # active, archived, completed
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    is_pinned = db.Column(db.Boolean, default=False)  # 是否置顶
    is_default = db.Column(db.Boolean, default=False)  # 是否为默认迭代
    start_date = db.Column(db.Date)  # 开始日期
    end_date = db.Column(db.Date)  # 结束日期
    progress = db.Column(db.Float, default=0.0)  # 进度百分比 0-100
    parent_id = db.Column(db.BigInteger)  # 父计划ID，支持递归
    project_id = db.Column(db.Integer, nullable=False)
    creator_id = db.Column(db.Integer, nullable=False)
    assignee_id = db.Column(db.Integer)  # 负责人
    scope_notification = db.Column(db.Boolean, default=False)  # 范围变更通知
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class Bug(db.Model):
    __tablename__ = 'bug'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    title = db.Column(db.String(200), nullable=False)  # Bug标题
    steps_to_reproduce = db.Column(db.Text)  # 复现步骤
    expected_result = db.Column(db.Text)  # 期望结果
    actual_result = db.Column(db.Text)  # 实际结果
    severity = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    priority = db.Column(db.String(10), default='p3')  # p1, p2, p3
    status = db.Column(db.String(20), default='new')  # new, assigned, in_progress, resolved, closed, reopened
    bug_type = db.Column(db.String(50))  # 功能缺陷, 性能问题, 界面问题, 兼容性问题, 安全问题, 其他
    environment = db.Column(db.String(100))  # 测试环境
    browser = db.Column(db.String(50))  # 浏览器
    os = db.Column(db.String(50))  # 操作系统
    # 可为空：与「未计划的 Bug」列表（plan_id IS NULL）一致
    plan_id = db.Column(db.BigInteger, nullable=True)
    project_id = db.Column(db.Integer, nullable=False)
    creator_id = db.Column(db.Integer, nullable=False)
    assignee_id = db.Column(db.Integer)  # 负责人
    attachments = db.Column(db.Text)  # 附件信息，JSON格式存储
    card_id = db.Column(db.BigInteger, nullable=True)  # 关联的卡片ID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class TestCase(db.Model):
    __tablename__ = 'test_case'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    title = db.Column(db.String(200), nullable=False)  # 用例标题
    status = db.Column(Enum(TestCaseStatus, values_callable=lambda obj: [e.value for e in obj]), default=TestCaseStatus.DRAFT, nullable=False)
    case_type = db.Column(db.String(50))  # 用例类型：功能测试/接口测试/性能测试/安全测试
    priority = db.Column(db.String(10), default='P3')  # P0/P1/P2/P3
    test_type = db.Column(db.String(50))  # 测试类型：手动/自动/探索
    
    # 基本信息
    preconditions = db.Column(db.Text)  # 前置条件
    steps = db.Column(db.JSON)  # 用例步骤，JSON格式: [{"step": "步骤描述", "expected": "预期结果"}]
    remark = db.Column(db.Text)  # 备注
    
    # 产品需求
    requirement_id = db.Column(db.Integer)  # 关联需求ID
    
    # 工作项
    related_defects = db.Column(db.JSON)  # 关联缺陷，JSON格式: [bug_id1, bug_id2]
    
    # 缺陷（执行信息）
    last_executed = db.Column(db.DateTime)  # 最后执行时间
    executed_by = db.Column(db.Integer)  # 执行人
    execution_result = db.Column(Enum(ExecutionResult, values_callable=lambda obj: [e.value for e in obj]), nullable=True)  # 执行结果：pass/fail/blocked/skip，NULL 表示未执行
    
    # 执行（测试集）
    baseline = db.Column(db.String(100))  # 基线管理
    
    # 工时
    estimated_time = db.Column(db.Float)  # 预估工时（小时）
    actual_time = db.Column(db.Float)  # 实际工时（小时）
    remaining_time = db.Column(db.Float)  # 剩余工时（小时）
    
    # 关联信息
    plan_id = db.Column(db.BigInteger)  # 所属计划
    project_id = db.Column(db.Integer, nullable=False)
    creator_id = db.Column(db.Integer, nullable=False)
    assignee_id = db.Column(db.Integer)  # 维护人
    card_id = db.Column(db.BigInteger, nullable=True)  # 关联迭代卡片 Card.id

    # 版本信息
    version = db.Column(db.String(20), default='v1')  # 版本号
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    

    
    def to_dict(self):
        """序列化为字典，处理枚举值"""
        return {
            'id': _json_snowflake_id(self.id),
            'title': self.title,
            'status': self.status.value if isinstance(self.status, TestCaseStatus) else self.status,
            'case_type': self.case_type,
            'priority': self.priority,
            'test_type': self.test_type,
            'preconditions': self.preconditions,
            'steps': self.steps,
            'remark': self.remark,
            'requirement_id': self.requirement_id,
            'related_defects': _json_snowflake_ids_in_list(self.related_defects),
            'last_executed': self.last_executed.isoformat() if self.last_executed else None,
            'executed_by': self.executed_by,
            'execution_result': self.execution_result.value if self.execution_result and isinstance(self.execution_result, ExecutionResult) else self.execution_result,
            'baseline': self.baseline,
            'estimated_time': self.estimated_time,
            'actual_time': self.actual_time,
            'remaining_time': self.remaining_time,
            'plan_id': _json_snowflake_id(self.plan_id),
            'project_id': self.project_id,
            'creator_id': self.creator_id,
            'assignee_id': self.assignee_id,
            'card_id': _json_snowflake_id(getattr(self, 'card_id', None)),
            'version': self.version,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Card(db.Model):
    """统一的卡片模型，支持Bug、BadCase、TestCase三种类型"""
    __tablename__ = 'card'
    
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=False)
    title = db.Column(db.String(200), nullable=False)
    type = db.Column(Enum(CardType, values_callable=lambda obj: [e.value for e in obj]), default=CardType.BADCASE, nullable=False)
    priority = db.Column(db.String(10), default='p3')
    assignee_id = db.Column(db.Integer)
    project_id = db.Column(db.Integer, nullable=False)
    plan_id = db.Column(db.BigInteger, nullable=True)
    creator_id = db.Column(db.Integer, nullable=True)  # 与 POST /api/cards、to_dict 一致；历史行可为 NULL
    description = db.Column(db.Text)
    
    # Bug特有字段
    severity = db.Column(db.String(20))
    steps_to_reproduce = db.Column(db.Text)
    expected_result = db.Column(db.Text)
    actual_result = db.Column(db.Text)
    bug_type = db.Column(db.String(50))
    environment = db.Column(db.String(100))
    browser = db.Column(db.String(50))
    os = db.Column(db.String(50))
    
    # BadCase特有字段
    case_category = db.Column(db.String(100))
    base_problem = db.Column(db.Text)
    reproduction_steps = db.Column(db.Text)
    badcase_result = db.Column(db.Text)
    answer = db.Column(db.Text)
    correct_answer = db.Column(db.Text)
    problem_reason = db.Column(db.Text)
    solution = db.Column(db.Text)
    
    # TestCase特有字段
    case_type_test = db.Column(db.String(50))
    test_type = db.Column(db.String(50))
    preconditions = db.Column(db.Text)
    steps = db.Column(db.JSON)
    remark = db.Column(db.Text)
    requirement_id = db.Column(db.Integer)
    related_defects = db.Column(db.JSON)
    last_executed = db.Column(db.DateTime)
    executed_by = db.Column(db.Integer)
    execution_result = db.Column(Enum(ExecutionResult, values_callable=lambda obj: [e.value for e in obj]))
    baseline = db.Column(db.String(100))
    estimated_time = db.Column(db.Float)
    actual_time = db.Column(db.Float)
    remaining_time = db.Column(db.Float)
    version = db.Column(db.String(20), default='v1')
    
    # 数据迁移追溯字段
    source_type = db.Column(db.String(30), nullable=True)  # 'bug', 'bad_case', 'test_case', NULL表示新创建的卡片
    source_id = db.Column(db.BigInteger, nullable=True)  # 源表中的ID
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    

    
    def to_dict(self):
        """序列化为字典，处理枚举值"""
        # id / plan_id / source_id 可能超过 JS Number.MAX_SAFE_INTEGER，JSON 数字会被截断，必须作字符串返回
        result = {
            'id': _json_snowflake_id(self.id),
            'title': self.title,
            'type': self.type.value if isinstance(self.type, CardType) else self.type,
            'priority': self.priority,
            'assignee_id': self.assignee_id,
            'project_id': self.project_id,
            'creator_id': self.creator_id,
            'plan_id': _json_snowflake_id(self.plan_id),
            'description': self.description,
            'source_type': self.source_type,
            'source_id': _json_snowflake_id(self.source_id),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        
        # 根据类型添加特定字段
        if self.type == CardType.BUG:
            result.update({
                'severity': self.severity,
                'steps_to_reproduce': self.steps_to_reproduce,
                'expected_result': self.expected_result,
                'actual_result': self.actual_result,
                'bug_type': self.bug_type,
                'environment': self.environment,
                'browser': self.browser,
                'os': self.os
            })
        elif self.type == CardType.BADCASE:
            result.update({
                'case_category': self.case_category,
                'base_problem': self.base_problem,
                'reproduction_steps': self.reproduction_steps,
                'badcase_result': self.badcase_result,
                'answer': self.answer,
                'correct_answer': self.correct_answer,
                'problem_reason': self.problem_reason,
                'solution': self.solution
            })
        elif self.type == CardType.TESTCASE:
            result.update({
                'case_type_test': self.case_type_test,
                'test_type': self.test_type,
                'preconditions': self.preconditions,
                'steps': self.steps,
                'remark': self.remark,
                'requirement_id': self.requirement_id,
                'related_defects': self.related_defects,
                'last_executed': self.last_executed.isoformat() if self.last_executed else None,
                'executed_by': self.executed_by,
                'execution_result': self.execution_result.value if self.execution_result and isinstance(self.execution_result, ExecutionResult) else self.execution_result,
                'baseline': self.baseline,
                'estimated_time': self.estimated_time,
                'actual_time': self.actual_time,
                'remaining_time': self.remaining_time,
                'version': self.version
            })
        
        return result


_ENTITY_SNOWFLAKE_PK_REGISTERED = False


def _register_entity_snowflake_pk_hooks() -> None:
    """Bug / BadCase / TestCase / Card / Plan 主键共用雪花 id（同一序列空间，跨表不撞号）。"""
    global _ENTITY_SNOWFLAKE_PK_REGISTERED
    if _ENTITY_SNOWFLAKE_PK_REGISTERED:
        return
    from utils.snowflake import next_entity_snowflake_id

    def _assign_snowflake_pk(mapper, connection, target) -> None:
        if getattr(target, "id", None) in (None, 0):
            setattr(target, "id", int(next_entity_snowflake_id()))

    for _m in (Bug, BadCase, TestCase, Card, Plan):
        event.listen(_m, "before_insert", _assign_snowflake_pk, propagate=True)
    _ENTITY_SNOWFLAKE_PK_REGISTERED = True


_register_entity_snowflake_pk_hooks()


def _apply_card_type_change_defaults(card: Card, old_type: CardType) -> None:
    """
    行内切换 Card.type（无 Bug/BadCase/TestCase 源表行时）补全新类型常用字段，
    避免 MySQL NOT NULL / 业务必填导致 commit 失败。
    """
    if old_type == card.type:
        return
    new_t = card.type
    if not isinstance(new_t, CardType):
        return
    if new_t == CardType.BUG:
        if not (getattr(card, 'severity', None) or '').strip():
            card.severity = 'medium'
        if not (getattr(card, 'bug_type', None) or '').strip():
            card.bug_type = '其他'
    elif new_t == CardType.BADCASE:
        if not (getattr(card, 'case_category', None) or '').strip():
            card.case_category = '未分类'
        if not (getattr(card, 'base_problem', None) or '').strip():
            card.base_problem = (card.title or '').strip() or '（待补充）'
        if not (getattr(card, 'badcase_result', None) or '').strip():
            card.badcase_result = '（待补充）'
        if not (getattr(card, 'answer', None) or '').strip():
            card.answer = '（待补充）'
    elif new_t == CardType.TESTCASE:
        if not (getattr(card, 'version', None) or '').strip():
            card.version = 'v1'
        if not (getattr(card, 'case_type_test', None) or '').strip():
            card.case_type_test = '功能测试'
        if not (getattr(card, 'test_type', None) or '').strip():
            card.test_type = '手动'


def repair_card_source_link_if_missing(card) -> bool:
    """
    数据补全：源表行已用 card_id 指向本卡，但 Card.source_type/source_id 为空时反填。
    支持 Bug / BadCase / TestCase 卡片（与 Card.type 一致）；幂等；成功则 commit。
    """
    if card is None:
        return False
    try:
        st = (getattr(card, "source_type", None) or "").strip()
        sid = getattr(card, "source_id", None)
    except Exception:
        return False
    if (st or "").strip() and sid is not None:
        return False
    ctype = getattr(card, "type", None)
    pid = getattr(card, "project_id", None)
    if pid is None:
        return False
    try:
        cid = int(card.id)
        pid = int(pid)
    except (TypeError, ValueError):
        return False

    src_type_val = None
    src_id_val = None

    if ctype == CardType.BUG:
        row = Bug.query.filter(Bug.card_id == cid, Bug.project_id == pid).first()
        if row is not None:
            src_type_val, src_id_val = "bug", int(row.id)
    elif ctype == CardType.BADCASE:
        row = BadCase.query.filter(BadCase.card_id == cid, BadCase.project_id == pid).first()
        if row is not None:
            src_type_val, src_id_val = "badcase", int(row.id)
    elif ctype == CardType.TESTCASE:
        row = TestCase.query.filter(TestCase.card_id == cid, TestCase.project_id == pid).first()
        if row is not None:
            src_type_val, src_id_val = "testcase", int(row.id)
    else:
        return False

    if not src_type_val or src_id_val is None or int(src_id_val) <= 0:
        return False
    try:
        card.source_type = src_type_val
        card.source_id = int(src_id_val)
        db.session.add(card)
        db.session.commit()
        print(
            f"[Card] repair_card_source_link: card.id={cid} project={pid} -> "
            f"{src_type_val}.id={src_id_val}",
            flush=True,
        )
        return True
    except Exception as e:
        db.session.rollback()
        print(f"[Card] repair_card_source_link 失败: {e}", flush=True)
        return False


# 兼容旧调用名
repair_card_bug_source_if_missing = repair_card_source_link_if_missing


def _find_card_linking_source_record(project_id, source_id, entity_kind, prefer_plan_id=None):
    """
    源表 card_id 为空时，用 Card.source_id 反查看板卡片（迁移/历史数据常见）。
    entity_kind: 'bug' | 'badcase' | 'testcase'
    """
    if project_id is None or source_id is None:
        return None
    try:
        pid = int(project_id)
        sid = int(source_id)
    except (TypeError, ValueError):
        return None
    if pid <= 0 or sid <= 0:
        return None
    ek = str(entity_kind or '').strip().lower()
    st_expect = {
        'bug': {'bug'},
        'badcase': {'bad_case', 'badcase'},
        'testcase': {'test_case', 'testcase'},
    }.get(ek, set())
    ctype_expect = {
        'bug': CardType.BUG,
        'badcase': CardType.BADCASE,
        'testcase': CardType.TESTCASE,
    }.get(ek)

    rows = (
        Card.query.filter(Card.project_id == pid, Card.source_id == sid)
        .order_by(Card.id.desc())
        .all()
    )
    if not rows:
        return None

    def _norm_st(val):
        return str(val or '').strip().lower().replace('-', '_')

    if prefer_plan_id is not None:
        try:
            pp = int(prefer_plan_id)
            for c in rows:
                cp = getattr(c, 'plan_id', None)
                if cp is not None and int(cp) == pp:
                    return c
        except (TypeError, ValueError):
            pass

    for c in rows:
        st = _norm_st(getattr(c, 'source_type', None))
        if st in st_expect:
            return c
    if ctype_expect is not None:
        for c in rows:
            if getattr(c, 'type', None) == ctype_expect:
                return c
    return rows[0] if len(rows) == 1 else None


def _try_repair_badcase_card_id_from_source_card(bc):
    """若 bad_case.card_id 为空但 Card 已挂 source_id，则写回 ORM。返回是否修改（调用方 commit）。"""
    if bc is None:
        return False
    cid = getattr(bc, 'card_id', None)
    try:
        if cid is not None and int(cid) > 0:
            return False
    except (TypeError, ValueError):
        pass
    card = _find_card_linking_source_record(
        bc.project_id, bc.id, 'badcase', prefer_plan_id=getattr(bc, 'plan_id', None)
    )
    if card is None:
        return False
    try:
        bc.card_id = int(card.id)
        return True
    except (TypeError, ValueError):
        return False


def _badcase_assignee_id_for_card(badcase):
    """BadCase.assignee 常为 user id 字符串，转为 Card.assignee_id。"""
    av = getattr(badcase, 'assignee', None)
    if av is not None and str(av).strip().isdigit():
        try:
            return int(str(av).strip())
        except (TypeError, ValueError):
            pass
    return None


def _link_card_source_to_badcase(card, badcase):
    """已有 Card 行时补写 source_type/source_id（创建自卡片 Tab 时常见）。"""
    if card is None or badcase is None:
        return False
    changed = False
    try:
        bid = int(badcase.id)
    except (TypeError, ValueError):
        return False
    st = (getattr(card, 'source_type', None) or '').strip()
    sid = getattr(card, 'source_id', None)
    if not st or sid is None:
        card.source_type = 'badcase'
        card.source_id = bid
        changed = True
    elif int(sid) != bid:
        print(
            f"[BadCase] Card id={card.id} 已关联 source_id={sid}，"
            f"跳过绑定 badcase id={bid}",
            flush=True,
        )
    return changed


def ensure_badcase_card_link(badcase, auto_create=False, commit=True):
    """
    确保 BadCase 与 Card 双向关联，返回 card_id 或 None。
    auto_create=True 时若无任何关联则新建 Card（与 api_create_bug 一致；仅用于创建 API，
    勿在 modify 预览/取数路径开启，否则会改写 card_id 导致从原卡片 Tab 消失）。
    """
    if badcase is None:
        return None
    cid_raw = getattr(badcase, 'card_id', None)
    try:
        if cid_raw is not None and int(cid_raw) > 0:
            card = Card.query.get(int(cid_raw))
            if card is not None:
                if _link_card_source_to_badcase(card, badcase):
                    db.session.add(card)
                    if commit:
                        db.session.commit()
                return int(cid_raw)
    except (TypeError, ValueError):
        pass

    if _try_repair_badcase_card_id_from_source_card(badcase):
        if commit:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"[BadCase] card_id 反查补写 commit 失败: {e}", flush=True)
                return None
        try:
            return int(badcase.card_id)
        except (TypeError, ValueError):
            pass

    if not auto_create:
        return None

    # 避免重复建卡：同计划下已有同标题、未挂 source 的 BadCase 卡片则复用
    try:
        pid = int(badcase.project_id)
        pp = getattr(badcase, 'plan_id', None)
        title_key = (badcase.title or '').strip()
        orphan_q = Card.query.filter(
            Card.project_id == pid,
            Card.type == CardType.BADCASE,
            or_(Card.source_id.is_(None), Card.source_id == 0),
        )
        if pp is not None:
            try:
                orphan_q = orphan_q.filter(Card.plan_id == int(pp))
            except (TypeError, ValueError):
                pass
        if title_key:
            orphan_q = orphan_q.filter(Card.title == title_key)
        orphan = orphan_q.order_by(Card.id.desc()).first()
        if orphan is not None:
            badcase.card_id = int(orphan.id)
            if _link_card_source_to_badcase(orphan, badcase):
                db.session.add(orphan)
            if commit:
                db.session.commit()
            print(
                f"[BadCase] 复用已有 Card id={orphan.id} 绑定 badcase id={badcase.id}",
                flush=True,
            )
            return int(orphan.id)
    except Exception as e:
        print(f"[BadCase] 复用 Card 失败: {e}", flush=True)

    try:
        _card = Card(
            title=badcase.title or '',
            type=CardType.BADCASE,
            priority=badcase.priority or 'p3',
            assignee_id=_badcase_assignee_id_for_card(badcase),
            project_id=badcase.project_id,
            creator_id=badcase.creator_id,
            plan_id=badcase.plan_id,
            description=badcase.base_problem,
            case_category=badcase.case_category,
            base_problem=badcase.base_problem,
            reproduction_steps=badcase.reproduction_steps,
            badcase_result=badcase.badcase_result,
            answer=badcase.answer,
            correct_answer=badcase.correct_answer,
            problem_reason=badcase.problem_reason,
            solution=badcase.solution,
            source_type='badcase',
            source_id=int(badcase.id),
        )
        db.session.add(_card)
        if commit:
            db.session.commit()
            db.session.refresh(_card)
        else:
            db.session.flush()
        badcase.card_id = int(_card.id)
        if commit:
            db.session.commit()
            db.session.refresh(badcase)
        print(
            f"[BadCase] 已为 id={badcase.id} 自动创建 Card id={_card.id}",
            flush=True,
        )
        return int(_card.id)
    except Exception as e:
        db.session.rollback()
        print(f"[BadCase] 自动创建 Card 失败 id={getattr(badcase, 'id', None)}: {e}", flush=True)
        return None


class CardTypeDefinition(db.Model):
    """卡片类型定义表 - 支持自定义卡片类型扩展"""
    __tablename__ = 'card_type'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(50), nullable=False)  # 类型名称
    code = db.Column(db.String(30), nullable=False, unique=True)  # 类型代码 (bug, badcase, testcase, 或自定义)
    icon = db.Column(db.String(50))  # 图标
    color = db.Column(db.String(20))  # 颜色
    description = db.Column(db.Text)  # 描述
    
    # 字段配置 (JSON格式，定义该类型支持的字段)
    fields_config = db.Column(db.JSON)  # {'severity': {'type': 'select', 'options': [...]}, ...}
    
    # 状态配置 (JSON格式，定义该类型的可用状态)
    status_config = db.Column(db.JSON)  # ['open', 'in_progress', 'resolved', 'closed']
    
    is_active = db.Column(db.Boolean, default=True)  # 是否启用
    sort_order = db.Column(db.Integer, default=0)  # 排序
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    

    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'code': self.code,
            'icon': self.icon,
            'color': self.color,
            'description': self.description,
            'fields_config': self.fields_config,
            'status_config': self.status_config,
            'is_active': self.is_active,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class CardPlanRelation(db.Model):
    """卡片与计划的关联关系表 - 支持卡片在多个计划之间移动"""
    __tablename__ = 'card_plan_relation'
    
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, nullable=False)  # 对应 Card.id；与 __table_args__ / to_dict 一致
    plan_id = db.Column(db.BigInteger, nullable=False)
    
    # 关联关系类型
    relation_type = db.Column(db.String(20), default='primary')  # primary(主要), related(关联), blocked_by(被阻塞)
    
    # 在计划中的状态
    status_in_plan = db.Column(db.String(20))  # 该卡片在该计划中的状态
    
    # 添加时间
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    removed_at = db.Column(db.DateTime, nullable=True)  # 移除时间 (软删除)
    
    # 排序
    sort_order = db.Column(db.Integer, default=0)
    

    
    # 复合唯一索引
    __table_args__ = (
        db.UniqueConstraint('card_id', 'plan_id', 'relation_type', name='uix_card_plan_type'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'card_id': _json_snowflake_id(self.card_id),
            'plan_id': _json_snowflake_id(self.plan_id),
            'relation_type': self.relation_type,
            'status_in_plan': self.status_in_plan,
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'removed_at': self.removed_at.isoformat() if self.removed_at else None,
            'sort_order': self.sort_order
        }


class Proposal(db.Model):
    """Text2SQL 修改提案元数据"""
    __tablename__ = 'proposal'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)

    tenant_id = db.Column(db.String(64), nullable=False, index=True)
    target_table = db.Column(db.String(64), nullable=False)
    summary = db.Column(db.String(255), nullable=False)
    sql_text = db.Column(db.Text, nullable=False)
    affected_rows_estimate = db.Column(db.Integer)

    status = db.Column(Enum(ProposalStatus, values_callable=lambda obj: [e.value for e in obj]),
                       default=ProposalStatus.PENDING,
                       nullable=False,
                       index=True)
    has_conflict = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    approved_at = db.Column(db.DateTime)
    applied_at = db.Column(db.DateTime)
    rejected_at = db.Column(db.DateTime)
    rolled_back_at = db.Column(db.DateTime)
    meta = db.Column(db.JSON)


class ProposalSnapshot(db.Model):
    """提案快照：记录修改前的行数据，用于精确 diff 与并发控制"""
    __tablename__ = 'proposal_snapshot'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    proposal_id = db.Column(db.Integer,
                            nullable=False, index=True)

    tenant_id = db.Column(db.String(64), nullable=False, index=True)
    target_table = db.Column(db.String(64), nullable=False)

    # 被修改行的主键值（默认使用 id 列）
    row_id = db.Column(db.Integer, nullable=False, index=True)

    # 修改前整行数据（字段 -> 值），使用 JSON 存储
    before_data = db.Column(db.JSON, nullable=False)

    # 乐观锁字段：记录快照时行的 updated_at，用于 apply 前冲突检查
    row_updated_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)



class ChatSession(db.Model):
    __tablename__ = 'chat_session'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    project_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    memory_enabled = db.Column(db.Boolean, default=True)
    memory_data = db.Column(db.Text)  # JSON格式存储
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    


class ChatMessage(db.Model):
    __tablename__ = 'chat_message'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer)
    is_user = db.Column(db.Boolean, default=True)
    content = db.Column(db.Text)
    understanding = db.Column(db.Text)
    reasoning = db.Column(db.Text)  # 思考过程（推理内容）
    steps = db.Column(db.Text)  # JSON格式存储
    execution_results = db.Column(db.Text)  # JSON格式存储executionResults
    agent_result = db.Column(db.Text)  # JSON格式存储agentResult
    evidences = db.Column(db.Text)  # JSON格式存储evidences
    navigation = db.Column(db.Text)  # JSON格式存储navigation（点击跳转Bug）
    modify_navigation = db.Column(db.Text)  # JSON格式存储modifyNavigation（修改预览导航）
    modify_groups = db.Column(db.Text)  # JSON格式存储modifyGroups（分组修改预览）
    delete_navigation = db.Column(db.Text)  # JSON：delete 工具 confirm=false 预览（与前端 deleteNavigation 对齐）
    final_response = db.Column(db.Text)
    # 本条消息发起请求时选用的模型 id（用户消息=所选模型；助手消息=生成该条回复的请求模型，便于排查效果问题）
    llm_model = db.Column(db.String(128))
    # 用户消息附图：JSON 字符串，项为 { data: dataURL|base64, filename? }；MySQL 用 LONGTEXT 避免单图超 TEXT 64KB
    images = db.Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 不使用 backref，避免依赖外键


class DiffReviewState(db.Model):
    """主表仅保留 pending；采纳/拒绝后在业务路径上物理删除，避免膨胀与状态双写"""
    __tablename__ = 'diff_review_state'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False, index=True)
    target = db.Column(db.String(32), nullable=False, index=True)  # badcase/bug/testcase
    target_id = db.Column(db.BigInteger, nullable=False, index=True)
    plan_id = db.Column(db.BigInteger, nullable=True, index=True)
    lifecycle_id = db.Column(db.Integer, default=1, nullable=False)
    diff_fingerprint = db.Column(db.String(64), nullable=False, default='')
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    diff_payload = db.Column(db.Text, nullable=True)  # JSON string
    modifications_payload = db.Column(db.Text, nullable=True)  # JSON string
    source_message_id = db.Column(db.Integer, nullable=True)
    source_session_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    adopted_at = db.Column(db.DateTime, nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    # 待采纳/待拒绝 Diff 的操作者：仅该用户可见 pending 与可执行采纳/拒绝（NULL 为历史数据兼容）
    operator_id = db.Column(db.Integer, nullable=True, index=True)

    # 不使用 backref，避免依赖外键

class BugComment(db.Model):
    __tablename__ = 'bug_comment'
    id = db.Column(db.Integer, primary_key=True)
    bug_id = db.Column(db.BigInteger, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)  # 富文本内容
    parent_id = db.Column(db.Integer, nullable=True, index=True)
    source_message_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TestCaseComment(db.Model):
    __tablename__ = 'test_case_comment'
    id = db.Column(db.Integer, primary_key=True)
    test_case_id = db.Column(db.BigInteger, nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    parent_id = db.Column(db.Integer, nullable=True, index=True)
    source_message_id = db.Column(db.Integer, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PromptTemplate(db.Model):
    __tablename__ = 'prompt_template'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    project_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AgentTask(db.Model):
    """ReAct 工具调用的持久化任务单元，支持 DAG 依赖与恢复（见 docs/需求文档_Agent任务状态管理与DAG并发调度_MySQL.md）。"""
    __tablename__ = 'agent_tasks'

    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    params = db.Column(db.JSON, nullable=True)
    result = db.Column(db.JSON, nullable=True)
    error = db.Column(db.Text, nullable=True)
    dependencies = db.Column(db.JSON, nullable=True)
    session_id = db.Column(db.String(64), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)


class ReactAgentRun(db.Model):
    """ReAct 整轮运行检查点：中断后可跨轮对话续作（见 session 文档 §5.2.2）。"""
    __tablename__ = 'react_agent_runs'

    id = db.Column(db.String(36), primary_key=True)
    chat_session_id = db.Column(db.Integer, nullable=False, index=True)
    project_id = db.Column(db.Integer, nullable=True, index=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    react_request_id = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='interrupted', index=True)
    user_input = db.Column(db.Text, nullable=True)
    model_name = db.Column(db.String(128), nullable=True)
    checkpoint_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class CdpTestRun(db.Model):
    """CDP 浏览器测试任务：一次对话内手动/用例/探测测试的步骤与结果汇总。"""
    __tablename__ = 'cdp_test_runs'

    id = db.Column(db.String(36), primary_key=True)
    chat_session_id = db.Column(db.Integer, nullable=True, index=True)
    react_request_id = db.Column(db.String(64), nullable=True, index=True)
    project_id = db.Column(db.Integer, nullable=False, index=True)
    plan_id = db.Column(db.BigInteger, nullable=True, index=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    mode = db.Column(db.String(32), nullable=False, default='manual')
    title = db.Column(db.String(200), nullable=False, default='CDP 测试')
    status = db.Column(db.String(20), nullable=False, default='running', index=True)
    spec_json = db.Column(db.JSON, nullable=True)
    steps_json = db.Column(db.JSON, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    pass_count = db.Column(db.Integer, default=0)
    fail_count = db.Column(db.Integer, default=0)
    cdp_session_id = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "chat_session_id": self.chat_session_id,
            "react_request_id": self.react_request_id,
            "project_id": self.project_id,
            "plan_id": self.plan_id,
            "user_id": self.user_id,
            "mode": self.mode,
            "title": self.title,
            "status": self.status,
            "spec_json": self.spec_json,
            "steps_json": self.steps_json,
            "summary": self.summary,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "cdp_session_id": self.cdp_session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class TerminalAudit(db.Model):
    """嵌入式终端审计：会话开始、AI 建议等（不含逐键记录）。"""
    __tablename__ = 'terminal_audit'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    project_id = db.Column(db.Integer, nullable=True, index=True)
    event_type = db.Column(db.String(40), nullable=False)
    client_session_id = db.Column(db.String(64), nullable=True, index=True)
    detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class QuickCommand(db.Model):
    """用户快速命令：云端同步，支持多项目。"""
    __tablename__ = 'quick_command'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    project_id = db.Column(db.Integer, nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    command = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WorkflowInAppNotification(db.Model):
    """站内工作流通知：与邮件/CLI 同源 payload 落库，供用户检索。"""
    __tablename__ = 'workflow_in_app_notification'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    actor_id = db.Column(db.Integer, nullable=True)
    actor_name = db.Column(db.String(120), nullable=True)
    event = db.Column(db.String(40), nullable=False)
    entity_type = db.Column(db.String(20), nullable=False, index=True)
    entity_id = db.Column(db.BigInteger, nullable=False, index=True)
    title = db.Column(db.String(500), nullable=True)
    project_id = db.Column(db.Integer, nullable=True, index=True)
    project_name = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(64), nullable=True)
    previous_status = db.Column(db.String(64), nullable=True)
    search_blob = db.Column(db.Text, nullable=True)
    read_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
