"""
app_services/cache.py
"""
from __future__ import annotations

import json
import time
from collections import defaultdict

    """返回 (hit: bool, value: any)"""
    try:
        entry = _PROJECT_CTX_CACHE.get(key)
        if entry is None:
            return False, None
        ts, value = entry
        if (time.time() - ts) <= ttl_s:
            return True, value
        # 已过期，删除并返回 miss
        _PROJECT_CTX_CACHE.pop(key, None)
        return False, None
    except Exception:
        return False, None

def _cache_set(key, value):
    _PROJECT_CTX_CACHE[key] = (time.time(), value)


def _cache_invalidate_plans(project_id: int):
    """测试用例/Bug/BadCase 变更后使计划列表缓存失效（内存 + Redis 双清）"""
    to_del = [k for k in _PROJECT_CTX_CACHE if isinstance(k, tuple) and len(k) >= 2 and k[0] == 'plans' and k[1] == project_id]
    for k in to_del:
        _PROJECT_CTX_CACHE.pop(k, None)
    # 同步清除 Redis 中该项目的所有相关缓存
    _redis_cache_invalidate_project(project_id)


def _cache_invalidate_cards(project_id: int):
    """卡片列表短缓存失效；避免返回旧 JSON（含错误 number id）。"""
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return
    to_del = [
        k
        for k in list(_PROJECT_CTX_CACHE.keys())
        if isinstance(k, tuple) and len(k) >= 2 and k[0] == 'cards' and k[1] == pid
    ]
    for k in to_del:
        _PROJECT_CTX_CACHE.pop(k, None)


def _parse_query_optional_int64(arg_name: str):
    """从 request.args 解析可选雪花 id（查询串用字符串，避免依赖 type=int）。"""
    raw = request.args.get(arg_name)
    if raw is None or str(raw).strip() == '':
        return None
    try:
        v = int(str(raw).strip())
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_query_int_optional(arg_name: str):
    """读取 query 中的整数（含 0）；缺失为 None。用于 plan_id=0 表示未计划等。"""
    raw = request.args.get(arg_name)
    if raw is None or str(raw).strip() == '':
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _coerce_optional_bigint_json(val):
    """请求 JSON 中的可选雪花 id，写入 ORM BigInteger 列。"""
    if val is None or val == '':
        return None
    try:
        v = int(str(val).strip())
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


# ==================== Redis 缓存层 ====================
# 对 projects / plans / members / edit-context 等高频只读接口做 Redis 缓存，
# 写操作时主动失效；projects 列表另见进程内短缓存 api_projects。

import json as _json

REDIS_CACHE_PREFIX = 'bcd:cache:'

def _redis_cache_get(key: str):
    """从 Redis 获取缓存，返回 (hit: bool, value: any)"""
    try:
        rc = get_redis_client()
        if rc is None:
            return False, None
        raw = rc.get(REDIS_CACHE_PREFIX + key)
        if raw is None:
            return False, None
        return True, _json.loads(raw)
    except Exception:
        return False, None


def _redis_cache_set(key: str, value, ttl_s: int = 10):
    """写入 Redis 缓存，默认 10 秒过期"""
    try:
        rc = get_redis_client()
        if rc is None:
            return
        rc.setex(REDIS_CACHE_PREFIX + key, ttl_s, _json.dumps(value, ensure_ascii=False))
    except Exception:
        pass


def _redis_cache_delete(key: str):
    """删除单条 Redis 缓存"""
    try:
        rc = get_redis_client()
        if rc is None:
            return
        rc.delete(REDIS_CACHE_PREFIX + key)
    except Exception:
        pass


def _redis_cache_invalidate_project(project_id: int):
    """项目数据变更时，清除该项目相关的所有 Redis 缓存（plans/members/edit-context/cards）"""
    for suffix in ('plans', 'members', 'edit-context', 'cards'):
        _redis_cache_delete(f'{suffix}:{project_id}')


def _redis_cache_invalidate_projects(user_id: int):
    """项目列表变更时，清除 /api/projects 的 Redis 与进程内缓存"""
    _redis_cache_delete(f'projects:{user_id}')
    try:
        _PROJECT_CTX_CACHE.pop(('api_projects', user_id), None)
    except Exception:
        pass


