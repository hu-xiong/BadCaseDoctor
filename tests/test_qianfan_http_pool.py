import os

from memory.qianfan_http_pool import (
    _pool_limits,
    close_qianfan_http_pools,
    get_openai_compatible_client,
    get_qianfan_httpx_client,
)


def test_httpx_client_singleton_per_base_url():
    close_qianfan_http_pools()
    base = "https://qianfan.baidubce.com/v2"
    a = get_qianfan_httpx_client(base)
    b = get_qianfan_httpx_client(base)
    assert a is b
    close_qianfan_http_pools()


def test_pool_limits_defaults():
    old_k = os.environ.pop("QIANFAN_HTTP_POOL_MAX_KEEPALIVE", None)
    old_t = os.environ.pop("QIANFAN_HTTP_POOL_MAX_CONNECTIONS", None)
    try:
        keep, total = _pool_limits()
        assert keep == 50
        assert total == 500
    finally:
        if old_k is not None:
            os.environ["QIANFAN_HTTP_POOL_MAX_KEEPALIVE"] = old_k
        if old_t is not None:
            os.environ["QIANFAN_HTTP_POOL_MAX_CONNECTIONS"] = old_t


def test_openai_client_singleton_per_key_base():
    close_qianfan_http_pools()
    a = get_openai_compatible_client("key-a", "https://qianfan.baidubce.com/v2")
    b = get_openai_compatible_client("key-a", "https://qianfan.baidubce.com/v2")
    c = get_openai_compatible_client("key-b", "https://qianfan.baidubce.com/v2")
    assert a is b
    assert a is not c
    close_qianfan_http_pools()
