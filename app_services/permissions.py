"""
app_services/permissions.py
"""
from __future__ import annotations

from sqlalchemy import and_

    row = (
        db.session.query(Project, ProjectPermission.role)
        .outerjoin(
            ProjectPermission,
            and_(ProjectPermission.project_id == Project.id, ProjectPermission.user_id == user_id),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not row:
        return None, 'not_found'
    project, role = row
    # 与历史 edit-context 一致：负责人任意；非负责人只要有权限表记录即可（不按 role 细筛）
    allowed = project.user_id == user_id or role is not None
    if not allowed:
        return None, 'forbidden'
    return project, None


# 检查用户是否有项目权限
def has_project_permission(user_id, project_id, required_role='collaborator'):
    """
    权限检查带 2 秒缓存，同一用户对同一项目的权限在短时间内不会变。
    """
    # 先检查缓存
    cache_key = (user_id, project_id, required_role)
    cache_hit, cached = _cache_get(('perm',) + cache_key, ttl_s=2.0)
    if cache_hit:
        if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
            print(f"[PERF] has_project_permission(project_id={project_id}, user_id={user_id}) cache_hit", flush=True)
        return cached
    
    # 尽量只做 1 次查询：同时拿到 owner_id + 当前用户在该项目的权限 role
    t0 = time.perf_counter()
    row = (
        db.session.query(Project.user_id, ProjectPermission.role)
        .outerjoin(
            ProjectPermission,
            and_(ProjectPermission.project_id == Project.id, ProjectPermission.user_id == user_id),
        )
        .filter(Project.id == project_id)
        .first()
    )
    dt_ms = (time.perf_counter() - t0) * 1000
    if (os.getenv("PERF_LOG", "") or "").strip().lower() in ("1", "true", "yes", "on"):
        print(
            f"[PERF] has_project_permission(project_id={project_id}, user_id={user_id}, required_role={required_role}) db={dt_ms:.1f}ms",
            flush=True,
        )
    if not row:
        _cache_set(('perm',) + cache_key, False)
        return False
    owner_id, role = row
    result = True if owner_id == user_id else (role in (['admin', 'collaborator'] if required_role != 'admin' else ['admin']))
    _cache_set(('perm',) + cache_key, result)
    return result


# 轻量缓存：降低同页重复请求的耗时（plans/members 变更不频繁，短 TTL 足够）
_PROJECT_CTX_CACHE = {}

