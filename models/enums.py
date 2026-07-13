"""ORM 状态枚举（自 app.py 拆出）。"""
from __future__ import annotations

import enum
import json

class BugStatus(enum.Enum):
    NEW = 'new'
    REOPENED = 'reopened'
    CLOSED = 'closed'
    RESOLVED = 'resolved'
    HOLD = 'hold'
    NOT_A_BUG = 'not_a_bug'
    NEW_FEATURE = 'new_feature'

class BadCaseStatus(enum.Enum):
    NEW = 'new'
    PENDING = 'pending'
    REOPENED = 'reopened'
    CLOSED = 'closed'
    RESOLVED = 'resolved'
    HOLD = 'hold'
    NOT_BADCASE = 'not_badcase'
    UNPUBLISHED = 'unpublished'  # 兼容遗留数据

class TestCaseStatus(enum.Enum):
    DRAFT = 'draft'        # 草稿
    REVIEW = 'review'      # 评审
    ACTIVE = 'active'      # 生效
    ARCHIVED = 'archived'  # 归档

class CardType(enum.Enum):
    BUG = 'bug'
    BADCASE = 'badcase'
    TESTCASE = 'testcase'
    CARD = 'card'

class ExecutionResult(enum.Enum):
    PASS = 'pass'
    FAIL = 'fail'
    BLOCKED = 'blocked'
    SKIP = 'skip'

class EnumJSONEncoder(json.JSONEncoder):
    """处理 Enum、datetime/date 等不可直接序列化的类型"""
    def default(self, obj):
        if isinstance(obj, enum.Enum):
            return obj.value
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)


class ProposalStatus(enum.Enum):
    """提案状态"""
    PENDING = 'pending'          # 待审核
    APPROVED = 'approved'        # 已审核通过，待执行
    APPLIED = 'applied'          # 已执行
    REJECTED = 'rejected'        # 已拒绝
    ROLLED_BACK = 'rolled_back'  # 标记为回滚
    CONFLICT = 'conflict'        # 与当前数据冲突

