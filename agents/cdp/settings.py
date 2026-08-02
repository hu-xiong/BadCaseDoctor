# -*- coding: utf-8 -*-
"""CDP 运行时配置（环境变量 / Config）。"""

from __future__ import annotations

import os
from typing import List, Optional


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
