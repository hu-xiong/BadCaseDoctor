"""
云端沙盒服务接口（用于本项目对接云端执行）

接口约定（与需求文档一致）：
- GET  /healthz
- POST /api/v1/execute
- GET  /api/v1/jobs/<job_id>

当前实现聚焦 text2sql 的只读 SQL 执行（task_type=sql_readonly）。

云端 Docker 失败原因与修复：
1. 原因：执行器使用 llm-sandbox 的 Docker 后端，云端未装 docker/llm-sandbox[docker] 或 Docker 未启动时会返回错误。
2. 修复方式（任选其一）：
   - 在云端设置 SANDBOX_USE_DIRECT_SQLITE=1，直接用 sqlite3 执行只读 SQL，不依赖 Docker。
   - 或在云端安装 pip install llm-sandbox[docker] 并保证 Docker 可用。
3. 未设置上述时：若执行器返回“Docker/llm-sandbox”相关错误，会自动回退到本模块内的 sqlite 直接执行。
"""

from __future__ import annotations

import os
import sys
import time
import uuid
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

# 注意：云端最小镜像可能不包含完整的 text2sql 依赖。
# 为避免容器在 import 阶段崩溃，这里不在模块顶部强制导入 text2sql；
# 仅在需要走 llm-sandbox 执行时再按需导入。


sandbox_bp = Blueprint("sandbox", __name__)


@dataclass
class Job:
    id: str
    status: str = "queued"  # queued|running|succeeded|failed
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    error: str = ""


_jobs_lock = threading.Lock()
_jobs: Dict[str, Job] = {}
_JOB_MAX_KEEP = 5000


def _job_retention_finished_s() -> int:
    """已结束 job 保留秒数，本地可设短（如 60）实现用完即清理。"""
    try:
        return max(10, int(os.getenv("SANDBOX_JOB_RETENTION_FINISHED_S", "3600")))
    except Exception:
        return 3600


def _prune_old_jobs():
    """清理已结束且过期的 job，避免内存无限增长。"""
    global _jobs
    now = time.time()
    retention = _job_retention_finished_s()
    to_del = [
        jid for jid, j in _jobs.items()
        if j.status in ("succeeded", "failed") and (j.finished_at or 0) > 0 and (now - j.finished_at) > retention
    ]
    for jid in to_del:
        _jobs.pop(jid, None)
    if len(_jobs) > _JOB_MAX_KEEP:
        by_created = sorted(_jobs.items(), key=lambda x: x[1].created_at)
        for jid, _ in by_created[: len(_jobs) - _JOB_MAX_KEEP]:
            _jobs.pop(jid, None)

_rate_lock = threading.Lock()
_rate_state: Dict[str, Dict[str, Any]] = {}

# Redis 限流：SANDBOX_REDIS_URL 存在时使用，否则回退到内存
_redis_client: Optional[Any] = None
_redis_rate_script_sha: Optional[str] = None

# 令牌桶 Lua：KEYS[1]=key, ARGV[1]=now, ARGV[2]=refill_per_s, ARGV[3]=burst
_REDIS_RATE_LUA = """
local tokens = tonumber(redis.call("HGET", KEYS[1], "tokens") or ARGV[3])
local ts = tonumber(redis.call("HGET", KEYS[1], "ts") or ARGV[1])
local now = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local burst = tonumber(ARGV[3])
tokens = math.min(burst, tokens + (now - ts) * refill)
if tokens < 1 then
  return 0
end
tokens = tokens - 1
redis.call("HSET", KEYS[1], "tokens", tostring(tokens), "ts", tostring(now))
redis.call("EXPIRE", KEYS[1], 120)
return 1
"""


def _get_redis_client():
    """按需创建 Redis 客户端；连接失败时返回 None，后续走内存限流。"""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = (os.getenv("SANDBOX_REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis as redis_lib
        _redis_client = redis_lib.from_url(url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def _rate_limit_ok_redis(tenant_id: str, action: str, rpm: int, burst: int) -> bool:
    """使用 Redis 的令牌桶限流（多实例共享）。"""
    global _redis_rate_script_sha  # noqa: PLW0603
    client = _get_redis_client()
    if not client:
        return True
    key = f"sandbox:rate:{tenant_id}:{action}"
    now = time.time()
    refill_per_s = rpm / 60.0
    try:
        if _redis_rate_script_sha is None:
            _redis_rate_script_sha = client.script_load(_REDIS_RATE_LUA)
        n = client.evalsha(_redis_rate_script_sha, 1, key, str(now), str(refill_per_s), str(float(burst)))
        return n == 1
    except Exception as e:
        if "NOSCRIPT" in str(e):
            try:
                _redis_rate_script_sha = client.script_load(_REDIS_RATE_LUA)
                n = client.evalsha(_redis_rate_script_sha, 1, key, str(now), str(refill_per_s), str(float(burst)))
                return n == 1
            except Exception:
                return True
        return True


def _auth_required() -> bool:
    return (os.getenv("SANDBOX_AUTH_REQUIRED", "") or "").strip().lower() == "true"


def _rate_limit_ok(tenant_id: str, action: str) -> bool:
    """
    租户级限流（令牌桶）：
    - 若设置 SANDBOX_REDIS_URL 则用 Redis 实现（多实例共享）；
    - 否则使用内存实现（单实例）。
    - SANDBOX_RATE_RPM: 每租户每分钟请求数（默认 120）
    - SANDBOX_RATE_BURST: 突发桶大小（默认 60）
    """
    def _to_int(v: str, default: int) -> int:
        try:
            return int(v)
        except Exception:
            return default

    rpm = _to_int(os.getenv("SANDBOX_RATE_RPM", "120"), 120)
    burst = _to_int(os.getenv("SANDBOX_RATE_BURST", "60"), 60)
    if rpm <= 0:
        return True

    if _get_redis_client() is not None:
        return _rate_limit_ok_redis(tenant_id, action, rpm, burst)

    key = f"{tenant_id}:{action}"
    now = time.time()
    refill_per_s = rpm / 60.0
    with _rate_lock:
        st = _rate_state.get(key)
        if not st:
            st = {"tokens": float(burst), "ts": now}
            _rate_state[key] = st
        dt = max(0.0, now - float(st.get("ts") or now))
        st["tokens"] = min(float(burst), float(st.get("tokens") or 0.0) + dt * refill_per_s)
        st["ts"] = now
        if st["tokens"] < 1.0:
            return False
        st["tokens"] -= 1.0
        return True


def _get_tenant_id(req) -> str:
    tenant_id = (req.headers.get("X-Tenant-Id") or "").strip()
    return tenant_id if tenant_id else "default"


def _execution_backend() -> str:
    """当前 SQL 执行后端：wsl2 | nsjail | direct_sqlite | llm_sandbox"""
    use_wsl2 = (os.getenv("SANDBOX_USE_WSL2", "") or "").strip().lower() in ("1", "true", "yes")
    if use_wsl2 and sys.platform == "win32":
        try:
            from sandbox.utils.wsl2_sandbox import is_available
            if is_available():
                return "wsl2"
        except Exception:
            pass
    use_nsjail = (os.getenv("SANDBOX_USE_NSJAIL", "") or "").strip().lower() in ("1", "true", "yes")
    if use_nsjail:
        try:
            from sandbox.utils.nsjail_sandbox import is_available
            if is_available():
                return "nsjail"
        except Exception:
            pass
    if (os.getenv("SANDBOX_USE_DIRECT_SQLITE", "") or "").strip().lower() in ("1", "true", "yes"):
        return "direct_sqlite"
    return "llm_sandbox"


def _tenant_db_dir(tenant_id: str) -> str:
    base = os.getenv("SANDBOX_DB_DIR", "/opt/sandbox_db")
    return os.path.join(base, tenant_id)


def _tenant_current_db_path(tenant_id: str) -> str:
    # 兼容单租户老配置：若设置 SANDBOX_DB_PATH，则对 default 租户优先使用它
    if tenant_id == "default":
        legacy = os.getenv("SANDBOX_DB_PATH", "") or ""
        if legacy:
            return legacy
    return os.path.join(_tenant_db_dir(tenant_id), "current.db")


def _tenant_versions_dir(tenant_id: str) -> str:
    return os.path.join(_tenant_db_dir(tenant_id), "versions")


def _ensure_dirs(tenant_id: str):
    os.makedirs(_tenant_versions_dir(tenant_id), exist_ok=True)


def _list_versions(tenant_id: str) -> List[Dict[str, Any]]:
    versions_dir = _tenant_versions_dir(tenant_id)
    if not os.path.isdir(versions_dir):
        return []
    items: List[Dict[str, Any]] = []
    for name in os.listdir(versions_dir):
        if not name.lower().endswith(".db"):
            continue
        p = os.path.join(versions_dir, name)
        try:
            st = os.stat(p)
            items.append(
                {
                    "name": name,
                    "path": p,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                }
            )
        except Exception:
            continue
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def _cleanup_versions(tenant_id: str, keep_last: int = 10, max_age_hours: int = 72) -> Dict[str, Any]:
    """
    清理某租户的历史版本：
    - 保留最近 keep_last 个版本
    - 其余若超过 max_age_hours 则删除
    """
    versions = _list_versions(tenant_id)
    now = time.time()
    keep = set(v["name"] for v in versions[: max(0, int(keep_last))])
    deleted = []
    errors = []
    for v in versions:
        name = v.get("name")
        path = v.get("path")
        mtime = float(v.get("mtime") or 0.0)
        if not name or not path:
            continue
        if name in keep:
            continue
        age_h = (now - mtime) / 3600.0 if mtime else 0.0
        if max_age_hours is not None and age_h < float(max_age_hours):
            continue
        try:
            if os.path.exists(path):
                os.remove(path)
                deleted.append({"name": name, "path": path, "age_hours": age_h})
        except Exception as e:
            errors.append({"name": name, "path": path, "error": str(e)})
    return {"tenant_id": tenant_id, "deleted": deleted, "errors": errors, "kept": list(keep)}


def _list_tenants() -> List[str]:
    base = os.getenv("SANDBOX_DB_DIR", "/opt/sandbox_db")
    if not os.path.isdir(base):
        return []
    out = []
    for name in os.listdir(base):
        p = os.path.join(base, name)
        if os.path.isdir(p):
            out.append(name)
    out.sort()
    return out


def _atomic_replace(src: str, dst: str):
    # Windows/Unix 兼容：先写到临时文件再 replace
    tmp = f"{dst}.tmp.{uuid.uuid4().hex[:8]}"
    import shutil

    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _auth_ok(req) -> bool:
    """
    最小鉴权（可选）：
    - SANDBOX_AUTH_REQUIRED=true 时强制鉴权：要求 Authorization: Bearer <token>
    - SANDBOX_AUTH_REQUIRED!=true 时不强制（便于先跑通/内网自测）
    - token 从 SANDBOX_SERVER_TOKEN 读取
    """
    required = _auth_required()
    if not required:
        return True

    expected = os.getenv("SANDBOX_SERVER_TOKEN", "") or ""
    if not expected:
        return False

    auth = req.headers.get("Authorization", "") or ""
    if not auth.lower().startswith("bearer "):
        return False
    got = auth.split(" ", 1)[1].strip()
    return got == expected


@sandbox_bp.route("/healthz", methods=["GET"])
def healthz():
    return jsonify(
        {
            "status": "ok",
            "service": "badcase-doctor-sandbox",
            "time": int(time.time()),
            "auth_required": _auth_required(),
            "rate_limit": {
                "rpm": int(os.getenv("SANDBOX_RATE_RPM", "120") or 120),
                "burst": int(os.getenv("SANDBOX_RATE_BURST", "60") or 60),
                "backend": "redis" if _get_redis_client() else "memory",
            },
            "max_db_mb": int(os.getenv("SANDBOX_MAX_DB_MB", "200") or 200),
            "execution_backend": _execution_backend(),
        }
    )


def _is_readonly_sql(sql: str) -> bool:
    """简单检查 SQL 是否只读（仅 SELECT）"""
    upper = sql.strip().upper()
    if not upper.startswith("SELECT"):
        return False
    forbidden = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE")
    for kw in forbidden:
        if f" {kw} " in upper or upper.endswith(f" {kw}") or upper.startswith(f"{kw} "):
            return False
    return True


def _is_docker_or_sandbox_error(err: Optional[str]) -> bool:
    """判断是否为 Docker/llm-sandbox 不可用导致的错误（可回退到直接 sqlite）"""
    if not err:
        return False
    s = err.lower()
    return "docker" in s or "llm-sandbox" in s or "llm_sandbox" in s


def _execute_sqlite_direct(db_path: str, sql: str) -> Dict[str, Any]:
    """在 SQLite 上直接执行只读 SQL（无 Docker 依赖，用于 Docker 不可用时的回退）"""
    import sqlite3
    if not _is_readonly_sql(sql):
        return {"success": False, "error": "仅允许 SELECT 只读 SQL", "data": [], "columns": [], "row_count": 0}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return {"success": True, "data": rows, "columns": cols, "row_count": len(rows)}
    except Exception as e:
        return {"success": False, "error": str(e), "data": [], "columns": [], "row_count": 0}


def _execute_sqlite_nsjail(db_path: str, sql: str, timeout_s: Optional[int] = None) -> Dict[str, Any]:
    """使用 NsJail 轻量沙箱执行只读 SQL（仅 Linux，适合桌面/内网）"""
    if not _is_readonly_sql(sql):
        return {"success": False, "error": "仅允许 SELECT 只读 SQL", "data": [], "columns": [], "row_count": 0}
    try:
        from sandbox.utils.nsjail_sandbox import is_available, execute_sqlite_readonly
    except ImportError:
        return {"success": False, "error": "NsJail 不可用（仅 Linux 且需安装 nsjail）", "data": [], "columns": [], "row_count": 0}
    if not is_available():
        return {"success": False, "error": "NsJail 不可用（仅 Linux 且需安装 nsjail）", "data": [], "columns": [], "row_count": 0}
    return execute_sqlite_readonly(db_path, sql, timeout_s=timeout_s)


def _execute_sqlite_wsl2(db_path: str, sql: str, timeout_s: Optional[int] = None) -> Dict[str, Any]:
    """Windows 上通过 WSL2 跑 Linux 沙箱（NsJail + sqlite3）执行只读 SQL"""
    if not _is_readonly_sql(sql):
        return {"success": False, "error": "仅允许 SELECT 只读 SQL", "data": [], "columns": [], "row_count": 0}
    try:
        from sandbox.utils.wsl2_sandbox import is_available, execute_sqlite_readonly
    except ImportError:
        return {"success": False, "error": "WSL2 沙箱不可用（仅 Windows 且需安装 WSL2）", "data": [], "columns": [], "row_count": 0}
    if not is_available():
        return {"success": False, "error": "WSL2 沙箱不可用（请安装 WSL2，并在 WSL 内安装 nsjail、sqlite3）", "data": [], "columns": [], "row_count": 0}
    return execute_sqlite_readonly(db_path, sql, timeout_s=timeout_s)


def _execute_via_llm_sandbox(sql: str, db_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    走 llm-sandbox（本地/云端容器内 Docker）执行只读 SQL。
    该依赖在最小镜像里可能不存在，因此必须延迟导入。
    """
    from agents.tools.text2sql.sandbox_executor import SecurityConfig, get_sandbox_executor

    sec = SecurityConfig(db_read_only=True, db_use_copy=False)
    executor = get_sandbox_executor(security_config=sec, fallback_to_local=False)
    return executor.execute_sql(sql, db_config=db_config)


def _run_job(job_id: str, task_type: str, payload: Dict[str, Any], timeout_ms: int, tenant_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = time.time()

    try:
        if task_type != "sql_readonly":
            raise ValueError(f"unsupported task_type: {task_type}")

        sql = (payload or {}).get("sql") or ""
        if not sql.strip():
            raise ValueError("payload.sql 不能为空")

        db = (payload or {}).get("db") or {}
        db_type = db.get("type") or "sqlite"

        # 云端执行默认使用"租户 current.db"（或 legacy SANDBOX_DB_PATH）
        db_path = _tenant_current_db_path(tenant_id)
        if db_type == "sqlite" and not db_path:
            raise ValueError("未配置 SANDBOX_DB_PATH（云端 SQLite 副本路径）")
        if db_type == "sqlite" and not os.path.exists(db_path):
            raise ValueError(f"数据库副本不存在: {db_path}")

        db_config = {"type": db_type}
        if db_type == "sqlite":
            db_config["path"] = db_path

        # 执行优先级：Windows 用 WSL2 > Linux 用 NsJail > direct_sqlite > llm-sandbox
        use_wsl2 = (os.getenv("SANDBOX_USE_WSL2", "") or "").strip().lower() in ("1", "true", "yes")
        use_nsjail = (os.getenv("SANDBOX_USE_NSJAIL", "") or "").strip().lower() in ("1", "true", "yes")
        use_direct_sqlite = (os.getenv("SANDBOX_USE_DIRECT_SQLITE", "") or "").strip().lower() in ("1", "true", "yes")
        timeout_s = min(60, max(1, timeout_ms // 1000)) if timeout_ms else 10

        result = None
        if use_wsl2 and sys.platform == "win32" and db_type == "sqlite":
            result = _execute_sqlite_wsl2(db_path, sql, timeout_s=timeout_s)
            if not result.get("success") and "不可用" in (result.get("error") or ""):
                result = None
        if result is None and use_nsjail and db_type == "sqlite":
            result = _execute_sqlite_nsjail(db_path, sql, timeout_s=timeout_s)
            if not result.get("success") and "不可用" in (result.get("error") or ""):
                result = None
        if result is None and use_direct_sqlite and db_type == "sqlite":
            result = _execute_sqlite_direct(db_path, sql)
        if result is None:
            try:
                result = _execute_via_llm_sandbox(sql, db_config=db_config)
            except Exception as e:
                err_str = str(e).lower()
                if _is_docker_or_sandbox_error(err_str):
                    if db_type == "sqlite":
                        result = _execute_sqlite_direct(db_path, sql)
                    else:
                        raise
                else:
                    raise
        # 执行器可能返回 success=False（例如 Docker 未安装），此时也尝试 sqlite 回退
        if result is not None and not result.get("success") and db_type == "sqlite":
            if _is_docker_or_sandbox_error(result.get("error")):
                result = _execute_sqlite_direct(db_path, sql)
        if result is None:
            raise RuntimeError("executor.execute_sql 返回空")

        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job:
                return
            job.result = {
                "data": result.get("data", []),
                "columns": result.get("columns", []),
                "row_count": result.get("row_count", 0),
                "sql": sql,
            }
            job.stdout = result.get("stdout", "") or ""
            job.stderr = result.get("stderr", "") or ""
            if result.get("success"):
                job.status = "succeeded"
            else:
                job.status = "failed"
                job.error = result.get("error") or "execution failed"
            job.finished_at = time.time()

    except Exception as e:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job:
                return
            job.status = "failed"
            job.error = str(e)
            job.finished_at = time.time()


@sandbox_bp.route("/api/v1/execute", methods=["POST"])
def execute():
    if not _auth_ok(request):
        return jsonify({"error": "unauthorized"}), 401
    tenant_id = _get_tenant_id(request)
    if not _rate_limit_ok(tenant_id, "execute"):
        return jsonify({"error": "rate_limited"}), 429

    data = request.get_json(silent=True) or {}
    task_type = data.get("task_type") or ""
    timeout_ms = int(data.get("timeout_ms") or 30000)
    payload = data.get("payload") or {}

    job_id = str(uuid.uuid4())
    job = Job(id=job_id, status="queued", created_at=time.time())
    with _jobs_lock:
        _prune_old_jobs()
        _jobs[job_id] = job

    t = threading.Thread(target=_run_job, args=(job_id, task_type, payload, timeout_ms, tenant_id), daemon=True)
    t.start()

    return jsonify({"job_id": job_id, "status": "queued"})


@sandbox_bp.route("/api/v1/jobs/<job_id>", methods=["GET"])
def job_detail(job_id: str):
    if not _auth_ok(request):
        return jsonify({"error": "unauthorized"}), 401
    tenant_id = _get_tenant_id(request)
    if not _rate_limit_ok(tenant_id, "jobs"):
        return jsonify({"error": "rate_limited"}), 429

    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"error": "not_found"}), 404
        finished = job.status in ("succeeded", "failed")
        resp = jsonify(
            {
                "job_id": job.id,
                "status": job.status,
                "stdout": job.stdout,
                "stderr": job.stderr,
                "result": job.result,
                "error": job.error or None,
                "timing": {
                    "created_at": job.created_at,
                    "started_at": job.started_at or None,
                    "finished_at": job.finished_at or None,
                },
            }
        )
    if finished:
        _prune_old_jobs()
    return resp


@sandbox_bp.route("/api/v1/db/versions", methods=["GET"])
def db_versions():
    if not _auth_ok(request):
        return jsonify({"error": "unauthorized"}), 401

    tenant_id = _get_tenant_id(request)
    if not _rate_limit_ok(tenant_id, "versions"):
        return jsonify({"error": "rate_limited"}), 429
    return jsonify(
        {
            "tenant_id": tenant_id,
            "current_db": _tenant_current_db_path(tenant_id),
            "versions": _list_versions(tenant_id),
        }
    )


@sandbox_bp.route("/api/v1/db/sync", methods=["POST"])
def db_sync():
    """
    DB 副本同步/切换（最小可用）：
    - 支持上传 sqlite db 文件（multipart/form-data file=...），保存为版本并切换 current.db
    - 或者 JSON 模式指定服务器已有文件路径：{"server_path": "/opt/sandbox_db/default/versions/xxx.db"}

    说明：
    - 多租户通过 X-Tenant-Id 隔离目录
    - 切换通过 os.replace 原子完成，失败可回滚到旧 current.db
    """
    if not _auth_ok(request):
        return jsonify({"error": "unauthorized"}), 401

    tenant_id = _get_tenant_id(request)
    if not _rate_limit_ok(tenant_id, "db_sync"):
        return jsonify({"error": "rate_limited"}), 429
    _ensure_dirs(tenant_id)

    versions_dir = _tenant_versions_dir(tenant_id)
    current_path = _tenant_current_db_path(tenant_id)

    def _migrate_bad_case_fields_sqlite(db_path: str):
        """
        沙箱副本字段同步：将旧字段名迁移到新命名
        - bad_case.correct_answer       -> bad_case.answer
        - bad_case.correct_answer_final -> bad_case.correct_answer
        仅在字段存在且目标字段不存在时执行；失败不阻断 sync（但会在执行 SQL 时暴露问题）。
        """
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bad_case'")
            if cur.fetchone() is None:
                conn.close()
                return
            cur.execute("PRAGMA table_info(bad_case)")
            cols = [r[1] for r in cur.fetchall()]
            if "correct_answer" in cols and "answer" not in cols:
                cur.execute("ALTER TABLE bad_case RENAME COLUMN correct_answer TO answer")
                conn.commit()
                cur.execute("PRAGMA table_info(bad_case)")
                cols = [r[1] for r in cur.fetchall()]
            if "correct_answer_final" in cols and "correct_answer" not in cols:
                cur.execute("ALTER TABLE bad_case RENAME COLUMN correct_answer_final TO correct_answer")
                conn.commit()
            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    # 1) multipart 上传
    if request.files and "file" in request.files:
        f = request.files["file"]
        if not f or not f.filename:
            return jsonify({"error": "missing_file"}), 400

        filename = secure_filename(f.filename)
        if not filename.lower().endswith(".db"):
            return jsonify({"error": "only_sqlite_db_allowed"}), 400

        # 上传大小限制（MB）；必须带 Content-Length，避免流式写爆磁盘
        if request.content_length is None:
            return jsonify({"error": "content_length_required"}), 411
        try:
            max_mb = int(os.getenv("SANDBOX_MAX_DB_MB", "200"))
        except Exception:
            max_mb = 200
        max_bytes = max_mb * 1024 * 1024
        if int(request.content_length) > max_bytes:
            return jsonify({"error": "file_too_large", "max_mb": max_mb}), 413

        version_name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{filename}"
        version_path = os.path.join(versions_dir, version_name)
        f.save(version_path)

        # 字段迁移（沙箱副本内也要与主库一致）
        _migrate_bad_case_fields_sqlite(version_path)

        # 切换 current.db
        _atomic_replace(version_path, current_path)
        if (os.getenv("SANDBOX_CLEANUP_AFTER_SYNC", "") or "").strip().lower() in ("1", "true", "yes"):
            try:
                keep = max(1, int(os.getenv("SANDBOX_CLEANUP_KEEP_AFTER_SYNC", "2")))
                _cleanup_versions(tenant_id, keep_last=keep, max_age_hours=0)
            except Exception:
                pass
        return jsonify(
            {
                "tenant_id": tenant_id,
                "status": "succeeded",
                "current_db": current_path,
                "version": {"name": version_name, "path": version_path},
            }
        )

    # 2) JSON 指定 server_path（文件已在服务器，且必须在租户目录内，防止路径穿越）
    data = request.get_json(silent=True) or {}
    server_path = (data.get("server_path") or "").strip()
    if not server_path:
        return jsonify({"error": "missing_file_or_server_path"}), 400
    try:
        real_path = os.path.realpath(server_path)
        tenant_root = os.path.realpath(_tenant_db_dir(tenant_id))
        if not (real_path == tenant_root or real_path.startswith(tenant_root + os.sep)):
            return jsonify({"error": "server_path_must_be_under_tenant_dir"}), 400
    except Exception:
        return jsonify({"error": "invalid_server_path"}), 400
    if not os.path.exists(server_path):
        return jsonify({"error": f"server_path_not_found: {server_path}"}), 400
    if not server_path.lower().endswith(".db"):
        return jsonify({"error": "only_sqlite_db_allowed"}), 400

    # 复制进 versions（保留版本），再切换
    import shutil

    base_name = os.path.basename(server_path)
    version_name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{base_name}"
    version_path = os.path.join(versions_dir, version_name)
    shutil.copy2(server_path, version_path)

    # 字段迁移（沙箱副本内也要与主库一致）
    _migrate_bad_case_fields_sqlite(version_path)

    _atomic_replace(version_path, current_path)

    if (os.getenv("SANDBOX_CLEANUP_AFTER_SYNC", "") or "").strip().lower() in ("1", "true", "yes"):
        try:
            keep = max(1, int(os.getenv("SANDBOX_CLEANUP_KEEP_AFTER_SYNC", "2")))
            _cleanup_versions(tenant_id, keep_last=keep, max_age_hours=0)
        except Exception:
            pass
    return jsonify(
        {
            "tenant_id": tenant_id,
            "status": "succeeded",
            "current_db": current_path,
            "version": {"name": version_name, "path": version_path},
        }
    )


@sandbox_bp.route("/api/v1/db/cleanup", methods=["POST"])
def db_cleanup():
    """
    清理云端沙箱历史副本（建议定时任务调用）：
    - 指定 tenant_id（header X-Tenant-Id）则只清理该租户
    - 或者 JSON: {"all_tenants": true} 清理全部租户（需要开启鉴权）

    JSON 参数（可选）：
    - keep_last: 保留最近 N 个版本（默认 10）
    - max_age_hours: 删除超过 N 小时的旧版本（默认 72）
    - all_tenants: true 时清理所有租户（默认 false）
    """
    if not _auth_ok(request):
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    try:
        keep_last = max(1, int(data.get("keep_last", 10)))
        max_age_hours = max(0, int(data.get("max_age_hours", 72)))
    except (TypeError, ValueError):
        keep_last, max_age_hours = 10, 72
    all_tenants = bool(data.get("all_tenants", False))

    # all_tenants 清理必须开启鉴权（避免误操作/被滥用）
    if all_tenants and not _auth_required():
        return jsonify({"error": "auth_required_for_all_tenants"}), 403

    if all_tenants:
        tenants = _list_tenants()
    else:
        tenants = [_get_tenant_id(request)]

    results = []
    for t in tenants:
        if not _rate_limit_ok(t, "cleanup"):
            results.append({"tenant_id": t, "deleted": [], "errors": [{"error": "rate_limited"}], "kept": []})
            continue
        try:
            results.append(_cleanup_versions(t, keep_last=keep_last, max_age_hours=max_age_hours))
        except Exception as e:
            results.append({"tenant_id": t, "deleted": [], "errors": [{"error": str(e)}], "kept": []})

    return jsonify({"success": True, "results": results})

