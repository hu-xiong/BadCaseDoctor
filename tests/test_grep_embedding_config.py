from memory.grep_es_config import build_embedding_client_from_config


def test_grep_embedding_defaults_qianfan():
    class Cfg:
        GREP_EMBEDDING_BACKEND = "qianfan"
        GREP_EMBEDDING_MODEL = "bge-large-zh"
        GREP_EMBEDDING_BASE_URL = "https://qianfan.baidubce.com/v2"
        GREP_EMBEDDING_API_KEY = "qf-key"
        QIANFAN_API_KEY = "qf-fallback"
        EMBEDDING_DIMENSION = None
        GREP_EMBEDDING_DIMENSION = None

    client = build_embedding_client_from_config(Cfg())
    assert client.cfg.model == "bge-large-zh"
    assert client.cfg.base_url == "https://qianfan.baidubce.com/v2"
    assert client.cfg.api_key == "qf-key"
    assert client.cfg.provider == "remote"
