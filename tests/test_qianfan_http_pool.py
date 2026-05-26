from memory.qianfan_http_pool import close_qianfan_http_pools, get_openai_compatible_client, get_qianfan_httpx_client


def test_httpx_client_singleton_per_base_url():
    close_qianfan_http_pools()
    base = "https://qianfan.baidubce.com/v2"
    a = get_qianfan_httpx_client(base)
    b = get_qianfan_httpx_client(base)
    assert a is b
    close_qianfan_http_pools()


def test_openai_client_singleton_per_key_base():
    close_qianfan_http_pools()
    a = get_openai_compatible_client("key-a", "https://qianfan.baidubce.com/v2")
    b = get_openai_compatible_client("key-a", "https://qianfan.baidubce.com/v2")
    c = get_openai_compatible_client("key-b", "https://qianfan.baidubce.com/v2")
    assert a is b
    assert a is not c
    close_qianfan_http_pools()
