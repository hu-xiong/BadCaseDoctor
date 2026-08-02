# -*- coding: utf-8 -*-
"""
本机 go-local-proxy 生命周期（随 Flask 进程启停）。

- 仅在本机开发/本机部署场景有意义；云端服务器默认不启动。
- 若 8794 /health 已通，则不重复拉起，退出时也不杀（视为外部进程）。
- 环境变量：
  BADCASE_MANAGE_LOCAL_PROXY=auto|1|0   默认 auto（环回监听且找到二进制才管）
  BADCASE_LOCAL_PROXY_EXE=绝对路径       指定可执行文件
  LISTEN / BADCASE_LOCAL_PROXY_LISTEN    代理监听，默认 127.0.0.1:8794
"""
from __future__ import annotations

import atexit
import logging
import os
import platform
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from badcase_client_binaries import client_binaries_dir

_log = logging.getLogger("local_proxy_supervisor")

_lock = threading.Lock()
_proc: Optional[subprocess.Popen] = None
_owned = False  # 是否由本模块拉起（仅 owned 时退出杀进程）
_started_at: Optional[float] = None
_last_error: str = ""
_exe_used: str = ""


def local_proxy_listen_addr() -> str:
    return (
        (os.getenv("BADCASE_LOCAL_PROXY_LISTEN") or os.getenv("LISTEN") or "127.0.0.1:8794")
        .strip()
        or "127.0.0.1:8794"
    )


def local_proxy_health_url() -> str:
    addr = local_proxy_listen_addr()
    if "://" in addr:
        return addr.rstrip("/") + "/health"
    return f"http://{addr}/health"


def probe_local_proxy_ok(timeout: float = 1.2) -> bool:
    url = local_proxy_health_url()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = (resp.read() or b"").decode("utf-8", errors="replace").strip()
            return resp.status == 200 and body == "ok"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def _platform_binary_name() -> str:
    system = platform.system().lower()
    machine = (platform.machine() or "").lower()
    arm = "arm" in machine or "aarch64" in machine
    if system == "windows":
        return "badcase-local-proxy.exe"
    if system == "darwin":
        return "badcase-local-proxy-darwin-arm64" if arm else "badcase-local-proxy-darwin-amd64"
    return "badcase-local-proxy-linux-arm64" if arm else "badcase-local-proxy-linux-amd64"


def resolve_local_proxy_exe() -> str:
    explicit = (os.getenv("BADCASE_LOCAL_PROXY_EXE") or "").strip().strip('"')
    if explicit and os.path.isfile(explicit):
        return os.path.abspath(explicit)

    root = os.path.dirname(os.path.abspath(__file__))
    name = _platform_binary_name()
    candidates = [
        os.path.join(client_binaries_dir(), name),
        os.path.join(root, "client_binaries", name),
        os.path.join(root, "go-local-proxy", name),
        os.path.join(root, "go-local-proxy", "badcase-local-proxy.exe"),
        os.path.join(root, "go-local-proxy", "badcase-local-proxy"),
    ]
    # Windows 上也常见无 arch 后缀的构建名
    if platform.system().lower() != "windows":
        candidates.append(os.path.join(client_binaries_dir(), "badcase-local-proxy"))
    for p in candidates:
        if p and os.path.isfile(p):
            return os.path.abspath(p)
    return ""


def _manage_mode() -> str:
    raw = (os.getenv("BADCASE_MANAGE_LOCAL_PROXY") or "auto").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return "on"
    if raw in ("0", "false", "no", "off"):
        return "off"
    return "auto"


def _should_manage(flask_host: str = "") -> bool:
    mode = _manage_mode()
    if mode == "off":
        return False
    if mode == "on":
        return True
    # auto：仅环回监听的本机后端
    host = (flask_host or os.getenv("FLASK_HOST") or "127.0.0.1").strip().lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        return True
    # 明确本机开发标记
    if (os.getenv("BADCASE_LOCAL_DEV") or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return False


def _is_reloader_parent() -> bool:
    """Flask/Werkzeug 热重载：父进程不要拉起代理，避免双开/退出杀错。"""
    return (os.environ.get("WERKZEUG_RUN_MAIN") or "").strip().lower() == "false"


def supervisor_status() -> Dict[str, Any]:
    with _lock:
        alive = False
        pid = None
        if _proc is not None:
            pid = _proc.pid
            alive = _proc.poll() is None
        return {
            "manage_mode": _manage_mode(),
            "owned": _owned,
            "running_child": alive,
            "pid": pid,
            "exe": _exe_used or resolve_local_proxy_exe(),
            "listen": local_proxy_listen_addr(),
            "health_ok": probe_local_proxy_ok(),
            "started_at": _started_at,
            "last_error": _last_error,
        }


def stop_managed_local_proxy(timeout: float = 5.0) -> None:
    global _proc, _owned, _last_error
    with _lock:
        proc = _proc
        owned = _owned
        _proc = None
        _owned = False
    if not owned or proc is None:
        return
    if proc.poll() is not None:
        return
    _log.info("[local-proxy] stopping managed process pid=%s", proc.pid)
    try:
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
    except Exception as e:
        _last_error = str(e)
    deadline = time.time() + max(0.5, timeout)
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.1)
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception as e:
            _last_error = str(e)


def start_managed_local_proxy(flask_host: str = "") -> Dict[str, Any]:
    """
    若策略允许且二进制存在：探测 health，未在线则拉起子进程。
    返回 supervisor_status() 快照。
    """
    global _proc, _owned, _started_at, _last_error, _exe_used

    if _is_reloader_parent():
        return {**supervisor_status(), "skipped": "reloader_parent"}

    if not _should_manage(flask_host):
        return {**supervisor_status(), "skipped": "manage_disabled"}

    if probe_local_proxy_ok():
        _log.info("[local-proxy] already healthy at %s — not spawning", local_proxy_health_url())
        return {**supervisor_status(), "skipped": "already_up"}

    exe = resolve_local_proxy_exe()
    if not exe:
        _last_error = "binary_not_found"
        _log.warning(
            "[local-proxy] no binary found under client_binaries/ or BADCASE_LOCAL_PROXY_EXE; skip autostart"
        )
        return {**supervisor_status(), "skipped": "binary_not_found"}

    with _lock:
        if _proc is not None and _proc.poll() is None:
            return {**supervisor_status(), "skipped": "already_owned"}

    env = os.environ.copy()
    env.setdefault("LISTEN", local_proxy_listen_addr())

    creationflags = 0
    if sys.platform == "win32":
        # 独立进程组，便于 terminate；不弹控制台窗口
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )

    try:
        proc = subprocess.Popen(
            [exe],
            cwd=os.path.dirname(exe) or None,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception as e:
        _last_error = str(e)
        _log.error("[local-proxy] spawn failed: %s", e)
        return {**supervisor_status(), "skipped": "spawn_failed"}

    with _lock:
        _proc = proc
        _owned = True
        _started_at = time.time()
        _exe_used = exe
        _last_error = ""

    # 短暂等待 health
    ok = False
    for _ in range(20):
        if proc.poll() is not None:
            _last_error = f"exited_early code={proc.returncode}"
            with _lock:
                _owned = False
                _proc = None
            break
        if probe_local_proxy_ok():
            ok = True
            break
        time.sleep(0.25)

    if ok:
        _log.info("[local-proxy] started pid=%s exe=%s", proc.pid, exe)
    else:
        _log.warning("[local-proxy] started pid=%s but health not ok yet (%s)", proc.pid, _last_error or "timeout")

    atexit.register(stop_managed_local_proxy)
    return supervisor_status()


def ensure_stop_hooks() -> None:
    """重复 register 无害；供显式调用。"""
    atexit.register(stop_managed_local_proxy)
