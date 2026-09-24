# -*- coding: utf-8 -*-
"""本机 CDP 桥服务（local_browser_bridge.py）生命周期（随 Flask 进程启停）。

- 桥服务在云端部署时是独立 systemd 服务（deploy/badcase-local-bridge.service），
  此处只覆盖「Flask / 桥服务 / 代理同机」的本机开发场景：隧道 URL 指向环回时才托管。
- 若网关端口 /internal/health 已通，则不重复拉起，退出时也不杀（视为外部进程）。
- 环境变量：
  BADCASE_MANAGE_LOCAL_BRIDGE=auto|1|0   默认 auto（隧道 URL 环回 + 密钥已配才管）
  BADCASE_CDP_GATEWAY_PORT / BADCASE_BRIDGE_TUNNEL_PORT  与桥服务一致
  BADCASE_TUNNEL_SECRET                  未配置时隧道不可用，auto 直接跳过
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

_log = logging.getLogger("local_bridge_supervisor")

_lock = threading.Lock()
_proc: Optional[subprocess.Popen] = None
_owned = False
_started_at: Optional[float] = None
_last_error: str = ""


def bridge_gateway_port() -> int:
    try:
        n = int((os.getenv("BADCASE_CDP_GATEWAY_PORT") or "").strip())
        return n if n > 0 else 9888
    except ValueError:
        return 9888


def bridge_health_url() -> str:
    return f"http://127.0.0.1:{bridge_gateway_port()}/internal/health"


def probe_bridge_ok(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(bridge_health_url(), timeout=timeout) as resp:
            raw = (resp.read() or b"").decode("utf-8", errors="replace")
        obj = json.loads(raw)
        return resp.status == 200 and isinstance(obj, dict) and bool(obj.get("ok"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def _manage_mode() -> str:
    raw = (os.getenv("BADCASE_MANAGE_LOCAL_BRIDGE") or "auto").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return "on"
    if raw in ("0", "false", "no", "off"):
        return "off"
    return "auto"


def _tunnel_url() -> str:
    return (os.getenv("BADCASE_TUNNEL_URL") or "").strip()


def _tunnel_url_is_loopback() -> bool:
    """隧道入口在环回 → 桥服务就该跑在本机（本机开发）；指向域名则视为云端部署，不托管。"""
    url = _tunnel_url().lower()
    if not url:
        return False
    if "://" in url:
        _, _, rest = url.partition("://")
    else:
        rest = url
    host = rest.split("/", 1)[0].rsplit("@", 1)[-1]
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    else:
        host = host.split(":", 1)[0]
    return host in ("127.0.0.1", "localhost", "::1") or host.startswith("127.")


def _tunnel_secret_configured() -> bool:
    return bool(
        (os.getenv("BADCASE_TUNNEL_SECRET") or os.getenv("TUNNEL_SECRET") or "").strip()
    )


def _should_manage() -> bool:
    mode = _manage_mode()
    if mode == "off":
        return False
    if mode == "on":
        return True
    if not _tunnel_secret_configured():
        _log.info("[bridge] auto skip: BADCASE_TUNNEL_SECRET 未配置（隧道不可用）")
        return False
    if not _tunnel_url_is_loopback():
        # 隧道走云端域名 → 桥服务在服务器上，本机不管
        return False
    return True


def bridge_script_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_browser_bridge.py")


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
            "gateway_port": bridge_gateway_port(),
            "health_ok": probe_bridge_ok(),
            "tunnel_url": _tunnel_url(),
            "started_at": _started_at,
            "last_error": _last_error,
        }


def stop_managed_bridge(timeout: float = 5.0) -> None:
    global _proc, _owned
    with _lock:
        proc = _proc
        owned = _owned
        _proc = None
        _owned = False
    if not owned or proc is None or proc.poll() is not None:
        return
    _log.info("[bridge] stopping managed process pid=%s", proc.pid)
    try:
        if sys.platform == "win32":
            # venv 的 python.exe 是启动器，真正跑桥服务的是它的子进程 → 杀整棵进程树
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            proc.terminate()
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


def start_managed_bridge() -> Dict[str, Any]:
    """策略允许且未在线时拉起桥服务；返回状态快照。"""
    global _proc, _owned, _started_at, _last_error

    if not _should_manage():
        return {**supervisor_status(), "skipped": "manage_disabled"}
    if probe_bridge_ok():
        _log.info("[bridge] already healthy at %s — not spawning", bridge_health_url())
        return {**supervisor_status(), "skipped": "already_up"}

    script = bridge_script_path()
    if not os.path.isfile(script):
        _last_error = "script_not_found"
        _log.warning("[bridge] %s 不存在，跳过托管", script)
        return {**supervisor_status(), "skipped": "script_not_found"}

    with _lock:
        if _proc is not None and _proc.poll() is None:
            return {**supervisor_status(), "skipped": "already_owned"}

    env = os.environ.copy()
    # 桥服务不读 .env：密钥/端口由本进程（Flask 已 load_dotenv）显式透传
    env.setdefault("BADCASE_TUNNEL_SECRET", (os.getenv("BADCASE_TUNNEL_SECRET") or "").strip())

    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )

    try:
        proc = subprocess.Popen(
            [sys.executable, script],
            cwd=os.path.dirname(script) or None,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception as e:
        _last_error = str(e)
        _log.error("[bridge] spawn failed: %s", e)
        return {**supervisor_status(), "skipped": "spawn_failed"}

    with _lock:
        _proc = proc
        _owned = True
        _started_at = time.time()
        _last_error = ""

    ok = False
    for _ in range(20):
        if proc.poll() is not None:
            _last_error = f"exited_early code={proc.returncode}"
            with _lock:
                _owned = False
                _proc = None
            break
        if probe_bridge_ok():
            ok = True
            break
        time.sleep(0.25)

    if ok:
        _log.info("[bridge] started pid=%s gateway=%s", proc.pid, bridge_gateway_port())
    else:
        _log.warning(
            "[bridge] started pid=%s but health not ok yet (%s)", proc.pid, _last_error or "timeout"
        )

    atexit.register(stop_managed_bridge)
    return supervisor_status()


def ensure_bridge_running() -> Dict[str, Any]:
    """按需确保桥服务在线（供隧道状态接口/前端轮询调用）。"""
    if probe_bridge_ok():
        return {**supervisor_status(), "ensured": "already_up"}
    st = dict(start_managed_bridge() or {})
    st["ensured"] = "started" if probe_bridge_ok() else "failed"
    return st
