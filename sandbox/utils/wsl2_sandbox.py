"""
Windows 上通过 WSL2 跑 Linux 沙箱（NsJail + sqlite3），与本地 Linux 实现一致。

- 仅 Windows 可用；需已安装 WSL2，且 WSL 内已安装 nsjail、sqlite3。
- 环境变量：SANDBOX_USE_WSL2=1 启用；SANDBOX_WSL2_TIMEOUT_S 超时（默认 10）。
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional


def _is_windows() -> bool:
    return sys.platform == "win32"


def windows_path_to_wsl(win_path: str) -> str:
    """将 Windows 路径转为 WSL 内可访问的路径。如 C:\\Users\\foo\\db.sqlite -> /mnt/c/Users/foo/db.sqlite"""
    p = os.path.abspath(win_path)
    p = p.replace("\\", "/")
    # C: -> /mnt/c, D: -> /mnt/d
    m = re.match(r"^([A-Za-z]):(.*)$", p)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2) or ""
        if rest.startswith("/"):
            rest = rest[1:]
        return f"/mnt/{drive}/{rest}"
    if p.startswith("/"):
        return p
    return "/mnt/c/" + p.lstrip("/")


def is_available() -> bool:
    """本机是否可用 WSL2 执行 SQL（仅 Windows 且 wsl 可用）。"""
    if not _is_windows():
        return False
    try:
        r = subprocess.run(
            ["wsl", "-e", "true"],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _to_int(v: str, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _parse_sqlite_json_stdout(stdout: str) -> tuple[List[Dict[str, Any]], List[str]]:
    """与 nsjail_sandbox 一致的 JSON 解析。"""
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
    cols = list(rows[0].keys()) if rows else []
    return rows, cols


def execute_sqlite_readonly(
    db_path: str,
    sql: str,
    timeout_s: Optional[int] = None,
) -> Dict[str, Any]:
    """
    在 WSL2 内用 NsJail + sqlite3 执行只读 SQL，返回与 _execute_sqlite_direct 一致的结构。

    - db_path: Windows 上的 SQLite 文件路径（会转为 WSL 路径）。
    - sql: 单条只读 SQL；调用方需已校验。
    - timeout_s: 超时秒数，默认 SANDBOX_WSL2_TIMEOUT_S 或 10。
    """
    out = {
        "success": False,
        "error": "",
        "data": [],
        "columns": [],
        "row_count": 0,
    }
    if not _is_windows():
        out["error"] = "WSL2 沙箱仅支持 Windows"
        return out
    if not is_available():
        out["error"] = "WSL 不可用（请安装/启动 WSL2，并在 WSL 内安装 nsjail、sqlite3）"
        return out
    db_path = os.path.abspath(db_path)
    if not os.path.isfile(db_path):
        out["error"] = f"数据库文件不存在: {db_path}"
        return out
    timeout_s = timeout_s or _to_int(os.getenv("SANDBOX_WSL2_TIMEOUT_S", "10"), 10)
    timeout_s = max(1, min(timeout_s, 60))
    wsl_db = windows_path_to_wsl(db_path)
    sql_b64 = base64.b64encode(sql.strip().rstrip(";").encode("utf-8")).decode("ascii")

    # 在 WSL 内：$1=sql_b64, $2=wsl_db；用 nsjail 跑 sqlite3；/lib64 可选（ARM 无此目录）
    script = (
        'sql=$(echo "$1" | base64 -d); db="$2"; '
        'R64=""; [ -d /lib64 ] && R64="-R /lib64 "; '
        'nsjail -Mo -q -R /usr -R /bin -R /lib $R64 '
        f'--time_limit {timeout_s} --rlimit_nproc 4 '
        '--bindmount_ro "$db":/db/current.db -- '
        '/usr/bin/sqlite3 -batch -cmd ".mode json" -cmd ".headers on" /db/current.db "$sql"'
    )
    try:
        proc = subprocess.run(
            ["wsl", "-e", "bash", "-c", script, "--", sql_b64, wsl_db],
            capture_output=True,
            timeout=timeout_s + 5,
            text=True,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0:
            out["error"] = stderr or f"WSL 内执行退出 {proc.returncode}"
            return out
        if not stdout:
            out["success"] = True
            out["row_count"] = 0
            return out
        rows, cols = _parse_sqlite_json_stdout(stdout)
        out["success"] = True
        out["data"] = rows
        out["columns"] = cols
        out["row_count"] = len(rows)
        return out
    except subprocess.TimeoutExpired:
        out["error"] = "WSL2 沙箱执行超时"
        return out
    except FileNotFoundError:
        out["error"] = "未找到 wsl 命令"
        return out
    except Exception as e:
        out["error"] = str(e)
        return out
