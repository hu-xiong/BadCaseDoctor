import os

from memory.es_client_pool import _client_cache_key, _connections_per_node, close_es_clients, get_es_client
from memory.es_long_memory import ESConfig


def test_connections_per_node_defaults():
    old = os.environ.pop("ES_CONNECTIONS_PER_NODE", None)
    try:
        assert _connections_per_node() == 50
    finally:
        if old is not None:
            os.environ["ES_CONNECTIONS_PER_NODE"] = old


def test_es_client_singleton_per_config():
    close_es_clients()
    cfg = ESConfig(url="http://127.0.0.1:19200", verify_certs=False)
    key = _client_cache_key(cfg)
    assert "127.0.0.1:19200" in key
