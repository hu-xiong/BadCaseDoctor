"""
Elasticsearch 进程内单例 + 每节点 HTTP 连接池（elasticsearch-py 内置 urllib3 keep-alive）。

与 memory/qianfan_http_pool 类似：复用同一客户端，避免每次 grep/search 新建 TCP+TLS。
"""
from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional, Tuple

from memory.es_long_memory import ESConfig

_pool_lock = threading.Lock()
_es_clients: Dict[str, Any] = {}


def _connections_per_node() -> int:
    """每 ES 节点并发 HTTP 连接上限（urllib3 池）；默认 50，上限 500。"""
    try:
        n = int(os.getenv("ES_CONNECTIONS_PER_NODE", "50"))
    except (TypeError, ValueError):
        n = 50
    return max(2, min(n, 500))


def _client_cache_key(cfg: ESConfig) -> str:
    url = (cfg.url or "").strip()
    if url:
        host_part = url
    else:
        host_part = f"{(cfg.host or '').strip()}:{int(cfg.port)}"
    auth = "apikey" if (cfg.api_key or "").strip() else f"basic:{cfg.username or ''}"
    return f"{host_part}|{auth}|v={int(bool(cfg.verify_certs))}"


def get_es_client(cfg: ESConfig):
    """按 ES 连接参数复用 Elasticsearch 客户端（带 connections_per_node 连接池）。"""
    key = _client_cache_key(cfg)
    with _pool_lock:
        existing = _es_clients.get(key)
        if existing is not None:
            return existing

        try:
            from elasticsearch import Elasticsearch
        except Exception as e:
            raise RuntimeError(
                f"缺少依赖 elasticsearch：请先安装 requirements.txt（elasticsearch）。{e}"
            ) from e

        url = (cfg.url or "").strip()
        if url:
            kwargs: Dict[str, Any] = {
                "hosts": [url],
                "verify_certs": bool(cfg.verify_certs),
            }
        else:
            host = (cfg.host or "").strip()
            if not host:
                raise RuntimeError("ES 未配置：请设置 ES_URL 或 ES_HOST。")
            kwargs = {
                "hosts": [{"scheme": "http", "host": host, "port": int(cfg.port)}],
                "verify_certs": bool(cfg.verify_certs),
            }

        if cfg.api_key:
            kwargs["api_key"] = cfg.api_key
        elif cfg.username:
            kwargs["basic_auth"] = (cfg.username, cfg.password or "")

        conn_n = _connections_per_node()
        kwargs["connections_per_node"] = conn_n
        try:
            kwargs["request_timeout"] = float(os.getenv("ES_CLIENT_REQUEST_TIMEOUT_S", "30"))
        except (TypeError, ValueError):
            kwargs["request_timeout"] = 30

        client = Elasticsearch(**kwargs)
        _es_clients[key] = client
        print(
            f"[GREP-ES] 客户端连接池已就绪 connections_per_node={conn_n} "
            f"hosts={kwargs.get('hosts')!r}",
            flush=True,
        )
        return client


def close_es_clients() -> None:
    """测试或进程退出时关闭所有池化客户端。"""
    global _es_clients
    with _pool_lock:
        for c in _es_clients.values():
            try:
                c.close()
            except Exception:
                pass
        _es_clients = {}
