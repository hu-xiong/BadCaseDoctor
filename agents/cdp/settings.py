# -*- coding: utf-8 -*-
"""CDP 运行时配置（环境变量 / Config）。"""

from __future__ import annotations

import os
import time
from typing import Dict, List, Optional, Tuple


def _bool(val: str, default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def cdp_enabled() -> bool:
    try:
        from config import Config

        return bool(getattr(Config, "CDP_ENABLED", False))
    except Exception:
        return _bool(os.getenv("CDP_ENABLED", "1"), True)


def cdp_headless() -> bool:
    """默认有头（可见浏览器）；服务器/CI 设 CDP_HEADLESS=1。"""
    try:
        from config import Config

        return bool(getattr(Config, "CDP_HEADLESS", False))
    except Exception:
        return _bool(os.getenv("CDP_HEADLESS", "0"), False)


def cdp_default_timeout_ms() -> int:
    try:
        from config import Config

        return int(getattr(Config, "CDP_DEFAULT_TIMEOUT_MS", 30000))
    except Exception:
        return int(os.getenv("CDP_DEFAULT_TIMEOUT_MS", "30000"))


def cdp_snapshot_max_nodes() -> int:
    try:
        from config import Config

        return int(getattr(Config, "CDP_SNAPSHOT_MAX_NODES", 200))
    except Exception:
        return int(os.getenv("CDP_SNAPSHOT_MAX_NODES", "200"))


def cdp_stale_ref_auto_snapshot() -> bool:
    try:
        from config import Config

        return bool(getattr(Config, "CDP_STALE_REF_AUTO_SNAPSHOT", True))
    except Exception:
        return _bool(os.getenv("CDP_STALE_REF_AUTO_SNAPSHOT", "1"), True)


def cdp_session_ttl_sec() -> int:
    try:
        from config import Config

        return int(getattr(Config, "CDP_SESSION_TTL_SEC", 1800))
    except Exception:
        return int(os.getenv("CDP_SESSION_TTL_SEC", "1800"))


def cdp_max_sessions() -> int:
    try:
        from config import Config

        return int(getattr(Config, "CDP_MAX_SESSIONS", 8))
    except Exception:
        return int(os.getenv("CDP_MAX_SESSIONS", "8"))


def cdp_browser_warmup_enabled() -> bool:
    try:
        from config import Config

        return bool(getattr(Config, "CDP_BROWSER_WARMUP", True))
    except Exception:
        return _bool(os.getenv("CDP_BROWSER_WARMUP", "1"), True)


def cdp_browser_idle_sec() -> int:
    """无活跃 session 时保留共享 Chromium 的秒数；0 表示一直保留。"""
    try:
        from config import Config

        return int(getattr(Config, "CDP_BROWSER_IDLE_SEC", 600))
    except Exception:
        return int(os.getenv("CDP_BROWSER_IDLE_SEC", "600"))


def cdp_allowed_hosts() -> Optional[List[str]]:
    raw = os.getenv("CDP_ALLOWED_HOSTS", "").strip()
    if not raw:
        return None
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def assert_url_allowed(url: str) -> None:
    from urllib.parse import urlparse

    hosts = cdp_allowed_hosts()
    if not hosts:
        return
    netloc = urlparse(url).netloc.lower()
    if not netloc:
        raise ValueError(f"无效 URL: {url}")
    ok = any(netloc == h or netloc.endswith("." + h) for h in hosts)
    if not ok:
        raise ValueError(f"URL 主机 {netloc} 不在 CDP_ALLOWED_HOSTS 允许列表中")


# ---------------------------------------------------------------- 本机 CDP 通道（跨网隧道）

def cdp_connection_mode() -> str:
    """CDP 连接模式：auto（默认）/ local（强制本机通道）/ launch（强制云端启动）。

    - auto：桥服务隧道在线 → 走本机浏览器；离线时公网 URL 回退云端 launch、
      私网 URL 显式失败不降级（设计 D8，防云端访问不了内网造成假完成）。
    - local：必须走本机通道，通道不可用直接报错。
    - launch：沿用旧的云端 chromium.launch 行为。
    """
    raw = ""
    try:
        from config import Config

        raw = str(getattr(Config, "CDP_CONNECTION_MODE", "") or "")
    except Exception:
        pass
    if not raw:
        raw = os.getenv("CDP_CONNECTION_MODE", "") or ""
    raw = raw.strip().lower()
    return raw if raw in ("auto", "local", "launch") else "auto"


def cdp_bridge_base_url() -> str:
    """桥服务 internal API 基址（与桥服务同机环回，部署时固定）。"""
    raw = ""
    try:
        from config import Config

        raw = str(getattr(Config, "CDP_BRIDGE_BASE_URL", "") or "")
    except Exception:
        pass
    if not raw:
        raw = os.getenv("BADCASE_BRIDGE_BASE_URL", "") or ""
    raw = raw.strip()
    if raw:
        return raw.rstrip("/")
    port = (os.getenv("BADCASE_CDP_GATEWAY_PORT", "") or "").strip() or "9888"
    return f"http://127.0.0.1:{port}"


def cdp_bridge_internal_key() -> str:
    """internal API 的 X-Bridge-Key 头（与桥服务 BADCASE_BRIDGE_INTERNAL_KEY 一致）。"""
    raw = ""
    try:
        from config import Config

        raw = str(getattr(Config, "CDP_BRIDGE_INTERNAL_KEY", "") or "")
    except Exception:
        pass
    if not raw:
        raw = os.getenv("BADCASE_BRIDGE_INTERNAL_KEY", "") or ""
    return raw.strip()


def cdp_bridge_timeout_sec() -> float:
    try:
        return max(0.5, float(os.getenv("CDP_BRIDGE_TIMEOUT_SEC", "") or 3.0))
    except ValueError:
        return 3.0


def cdp_channel_wait_sec() -> float:
    """通道 ensure 的等待上限（秒）；0 表示只查一次不等待。"""
    try:
        return max(0.0, float(os.getenv("CDP_CHANNEL_WAIT_SEC", "") or 20.0))
    except ValueError:
        return 20.0


def cdp_private_hosts() -> List[str]:
    """显式私网域名/后缀标记（逗号分隔），如内网域名 corp.example.com。"""
    raw = (os.getenv("CDP_PRIVATE_HOSTS", "") or "").strip()
    if not raw:
        return []
    return [h.strip().lower().lstrip("*.") for h in raw.split(",") if h.strip()]


def _ip_is_private(ip: str) -> bool:
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return True
    # CGNAT（100.64/10）在旧版 Python 的 is_private 中未覆盖，显式兜底
    try:
        return addr in ipaddress.ip_network("100.64.0.0/10")
    except (ValueError, TypeError):
        return False


_DNS_PRIVATE_CACHE: Dict[str, Tuple[float, bool]] = {}


def _host_resolves_private(host: str) -> bool:
    """DNS 解析域名，任一地址为私网即视为内网（结果缓存 300s，失败视为公网）。"""
    import socket

    now = time.time()
    hit = _DNS_PRIVATE_CACHE.get(host)
    if hit is not None and hit[0] > now:
        return hit[1]
    val = False
    try:
        for info in socket.getaddrinfo(host, None):
            ip = str((info[4] or [""])[0] or "")
            if ip and _ip_is_private(ip):
                val = True
                break
    except Exception:
        val = False
    _DNS_PRIVATE_CACHE[host] = (now + 300.0, val)
    return val


def is_private_url(url: str) -> bool:
    """URL 是否指向内网（RFC1918 / CGNAT / link-local / localhost / .local / 显式标记 / DNS 解析）。

    宁可误判为内网（local 不可用时显式失败并提示唤起），也不放过内网（防云端 launch 假完成）。
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".local") or host.endswith(".localhost"):
        return True
    if _ip_is_private(host):
        return True
    for suffix in cdp_private_hosts():
        if host == suffix or host.endswith("." + suffix):
            return True
    return _host_resolves_private(host)
