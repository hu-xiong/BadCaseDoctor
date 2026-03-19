"""
共享 HTTP Session（连接池/Keep-Alive）用于各类 LLM Provider。

说明：
- requests.Session 会复用 TCP/TLS 连接，显著降低 p95 延迟。
- 这里做成进程级单例，避免每次请求重新建连。
"""

from __future__ import annotations

import os
import threading
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

try:
    # urllib3 在 requests 里依赖；不同版本 Retry 所在位置不同
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None  # type: ignore


_LOCK = threading.Lock()
_SESSION: Optional[requests.Session] = None


def get_session() -> requests.Session:
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    with _LOCK:
        if _SESSION is not None:
            return _SESSION

        pool_connections = int(os.getenv("LLM_HTTP_POOL_CONNECTIONS", "20"))
        pool_maxsize = int(os.getenv("LLM_HTTP_POOL_MAXSIZE", "50"))

        s = requests.Session()

        if Retry is not None:
            retries = Retry(
                total=int(os.getenv("LLM_HTTP_RETRY_TOTAL", "2")),
                connect=int(os.getenv("LLM_HTTP_RETRY_CONNECT", "2")),
                read=int(os.getenv("LLM_HTTP_RETRY_READ", "1")),
                backoff_factor=float(os.getenv("LLM_HTTP_RETRY_BACKOFF", "0.2")),
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]),
                raise_on_status=False,
            )
        else:  # pragma: no cover
            retries = 0

        adapter = HTTPAdapter(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            max_retries=retries,
        )
        s.mount("http://", adapter)
        s.mount("https://", adapter)

        _SESSION = s
        return s

