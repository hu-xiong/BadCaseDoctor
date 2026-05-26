"""
千帆 OpenAI 兼容 API 的 HTTP 连接池（rerank / embeddings 共用）。

每次 urlopen 新建 TCP+TLS 约增加数百毫秒；进程内复用 httpx.Client / OpenAI 实例做 keep-alive。
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional, Tuple

_httpx_lock = threading.Lock()
_httpx_clients: Dict[str, Any] = {}

_openai_lock = threading.Lock()
_openai_clients: Dict[Tuple[str, str], Any] = {}


def _pool_limits():
    try:
        keep = int(os.getenv("QIANFAN_HTTP_POOL_MAX_KEEPALIVE", "50"))
    except (TypeError, ValueError):
        keep = 50
    try:
        total = int(os.getenv("QIANFAN_HTTP_POOL_MAX_CONNECTIONS", "400"))
    except (TypeError, ValueError):
        total = 400
    keep = max(2, keep)
    total = max(keep, total)
    return keep, total


def get_qianfan_httpx_client(base_url: str, *, timeout: float = 30.0):
    """按 base_url 复用 httpx.Client（线程安全单例/池）。"""
    import httpx

    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = "https://qianfan.baidubce.com/v2"
    with _httpx_lock:
        client = _httpx_clients.get(base)
        if client is not None:
            return client
        keep, total = _pool_limits()
        limits = httpx.Limits(
            max_keepalive_connections=keep,
            max_connections=total,
            keepalive_expiry=60.0,
        )
        client = httpx.Client(
            base_url=base,
            timeout=httpx.Timeout(timeout, connect=10.0),
            limits=limits,
            headers={"Accept": "application/json"},
        )
        _httpx_clients[base] = client
        return client


def qianfan_post_json(
    path: str,
    payload: Dict[str, Any],
    *,
    api_key: str,
    headers_extra: Optional[Dict[str, str]] = None,
    base_url: str,
    timeout: float = 30.0,
) -> Tuple[int, Dict[str, Any], Optional[str]]:
    """
    POST JSON，走连接池。
    返回 (status_code, body_dict, error_text)。
    """
    key = (api_key or "").strip()
    if not key:
        return 0, {}, "no_api_key"
    client = get_qianfan_httpx_client(base_url, timeout=timeout)
    p = path if path.startswith("/") else f"/{path}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    if headers_extra:
        headers.update(headers_extra)
    try:
        resp = client.post(p, json=payload, headers=headers)
        raw = resp.text or ""
        try:
            data = resp.json() if raw else {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if resp.status_code >= 400:
            return int(resp.status_code), data, raw[:500] or resp.reason_phrase
        return int(resp.status_code), data, None
    except Exception as e:
        return 0, {}, str(e)


def get_openai_compatible_client(api_key: str, base_url: Optional[str] = None, *, timeout: float = 30.0):
    """千帆 / 其他 OpenAI 兼容 embedding 端点：复用 OpenAI SDK（内部 httpx 连接池）。"""
    from openai import OpenAI

    ak = (api_key or "").strip()
    bu = (base_url or "").strip().rstrip("/")
    cache_key = (ak, bu)
    with _openai_lock:
        client = _openai_clients.get(cache_key)
        if client is not None:
            return client
        client = OpenAI(
            api_key=ak,
            base_url=bu or None,
            max_retries=1,
            timeout=timeout,
        )
        _openai_clients[cache_key] = client
        return client


def close_qianfan_http_pools() -> None:
    """测试或进程退出时可选关闭。"""
    global _httpx_clients, _openai_clients
    with _httpx_lock:
        for c in _httpx_clients.values():
            try:
                c.close()
            except Exception:
                pass
        _httpx_clients = {}
    with _openai_lock:
        _openai_clients = {}
