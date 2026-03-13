"""
NsJail 轻量级沙箱：在 Linux 上用 namespace/cgroup 隔离执行只读 SQL，适合桌面端/内网。

- 仅 Linux 可用；Windows 下 is_available() 为 False，走 direct_sqlite 或 Docker。
- 需预装：nsjail、sqlite3（系统包）。可选环境变量 SANDBOX_NSJAIL_BIN、SANDBOX_NSJAIL_TIMEOUT_S。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional

# NsJail 仅 Linux 支持
def _is_linux() -> bool:
    return sys.platform == "linux"


def _nsjail_bin() -> Optional[str]:
    v = (os.getenv("SANDBOX_NSJAIL_BIN") or "").strip()
    if v and os.path.isfile(v):
        return v
    return shutil.which("nsjail")


def is_available() -> bool:
    """本机是否可用 NsJail 执行 SQL（仅 Linux 且 nsjail 在 PATH 或 SANDBOX_NSJAIL_BIN）。"""
    if not _is_linux():
        return False
    return _nsjail_bin() is not None


def _to_int(v: str, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def execute_sqlite_readonly(
    db_path: str,
    sql: str,
    timeout_s: Optional[int] = None,
) -> Dict[str, Any]:
    """
    在 NsJail 内用 sqlite3 执行只读 SQL，返回与 _execute_sqlite_direct 一致的结构。

    - db_path: 宿主机上 SQLite 文件绝对路径（会以只读方式挂进 jail）。
    - sql: 单条只读 SQL（仅 SELECT）；调用方需已校验。
    - timeout_s: 超时秒数，默认 SANDBOX_NSJAIL_TIMEOUT_S 或 10。
    """
    out = {
        "success": False,
        "error": "",
        "data": [],
        "columns": [],
        "row_count": 0,
    }
    if not _is_linux():
        out["error"] = "NsJail 仅支持 Linux"
        return out
    bin_nsjail = _nsjail_bin()
    if not bin_nsjail:
        out["error"] = "未找到 nsjail（请安装或设置 SANDBOX_NSJAIL_BIN）"
        return out
    db_path = os.path.abspath(db_path)
    if not os.path.isfile(db_path):
        out["error"] = f"数据库文件不存在: {db_path}"
        return out
    timeout_s = timeout_s or _to_int(os.getenv("SANDBOX_NSJAIL_TIMEOUT_S", "10"), 10)
    timeout_s = max(1, min(timeout_s, 60))

    # sqlite3 在 jail 内输出 JSON：-batch -cmd ".mode json" -cmd ".headers on"
    # 需要把 db 只读挂到 jail 内；jail 内要有 sqlite3，用 -R 挂载 /usr /bin /lib 等
    jail_db = "/db/current.db"
    args_nsjail = [
        bin_nsjail,
        "-Mo",
        "-q",
        "-R", "/usr",
        "-R", "/bin",
        "-R", "/lib",
    ]
    if os.path.exists("/lib64"):
        args_nsjail.extend(["-R", "/lib64"])
    args_nsjail.extend([
        "--time_limit", str(timeout_s),
        "--rlimit_nproc", "4",
        "--bindmount_ro", f"{db_path}:{jail_db}",
        "--", "/usr/bin/sqlite3", "-batch",
        "-cmd", ".mode json",
        "-cmd", ".headers on",
        jail_db,
        sql.strip().rstrip(";"),
    ])
    try:
        proc = subprocess.run(
            args_nsjail,
            capture_output=True,
            timeout=timeout_s + 2,
            text=True,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0:
            out["error"] = stderr or f"nsjail exit {proc.returncode}"
            return out
        if not stdout:
            out["success"] = True
            out["row_count"] = 0
            return out
        # sqlite3 .mode json 输出多行时每行一个 JSON 对象；单行可能是数组
        rows: List[Dict[str, Any]] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, list):
                    rows.extend(obj)
                elif isinstance(obj, dict):
                    rows.append(obj)
            except json.JSONDecodeError:
                continue
        if not rows:
            out["success"] = True
            return out
        cols = list(rows[0].keys())
        out["success"] = True
        out["data"] = rows
        out["columns"] = cols
        out["row_count"] = len(rows)
        return out
    except subprocess.TimeoutExpired:
        out["error"] = "NsJail 执行超时"
        return out
    except FileNotFoundError:
        out["error"] = "未找到 nsjail 或 sqlite3"
        return out
    except Exception as e:
        out["error"] = str(e)
        return out
