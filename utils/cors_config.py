# -*- coding: utf-8 -*-
"""CORS / Session Cookie 解析（无 Flask 依赖，便于单测与 Electron file://）。"""
from __future__ import annotations

import os
from typing import Iterable, List, Optional


_DEFAULT_DEV_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
)


def env_truthy(name: str, default: str = "") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def cors_origins_list() -> List[str]:
    raw = (os.getenv("CORS_ORIGINS") or "").strip()
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
    else:
        # 生产必须显式配置浏览器源，或至少开启 Electron null origin
        prod = (os.getenv("FLASK_ENV") or "").strip().lower() == "production"
        if prod and not env_truthy("CORS_ALLOW_NULL_ORIGIN"):
            raise RuntimeError(
                "生产环境请设置 CORS_ORIGINS（浏览器 SaaS）或 CORS_ALLOW_NULL_ORIGIN=1（Electron）"
            )
        origins = list(_DEFAULT_DEV_ORIGINS)
    if env_truthy("CORS_ALLOW_NULL_ORIGIN"):
        if "null" not in origins:
            origins.append("null")
    return origins


def cors_origin_allowed(origin: Optional[str], allowed: Optional[Iterable[str]] = None) -> bool:
    """origin 为 None/空：非浏览器同源请求，放行由业务鉴权决定；列表校验时视为不允许回写 ACAO。"""
    allow = list(allowed) if allowed is not None else cors_origins_list()
    if origin is None or origin == "":
        return False
    if origin == "null":
        return "null" in allow or env_truthy("CORS_ALLOW_NULL_ORIGIN")
    return origin in allow


def session_cookie_samesite(default: str = "Lax") -> str:
    raw = (os.getenv("SESSION_COOKIE_SAMESITE") or default).strip()
    # 兼容 none/None
    key = raw.lower()
    if key == "none":
        return "None"
    if key == "strict":
        return "Strict"
    if key == "lax":
        return "Lax"
    return "Lax"
