from memory.grep_es_config import build_embedding_client_from_config


def test_grep_embedding_defaults_doubao():
    class Cfg:
        GREP_EMBEDDING_BACKEND = "doubao"
        DOUBAO_EMBEDDING_MODEL = "doubao-embedding-vision-251215"
        DOUBAO_EMBEDDING_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
        DOUBAO_API_KEY = "ark-key"
        GREP_EMBEDDING_MODEL = ""
        GREP_EMBEDDING_BASE_URL = ""
        GREP_EMBEDDING_API_KEY = ""
        EMBEDDING_MODEL = "other-model"
        EMBEDDING_DIMENSION = 1152
        GREP_EMBEDDING_DIMENSION = 2048

    client = build_embedding_client_from_config(Cfg())
    assert client.cfg.model == "doubao-embedding-vision-251215"
    assert client.cfg.base_url == "https://ark.cn-beijing.volces.com/api/v3"
    assert client.cfg.api_key == "ark-key"
    assert client.cfg.provider == "remote"


def test_grep_embedding_explicit_dashscope():
    class Cfg:
        GREP_EMBEDDING_BACKEND = "dashscope"
        GREP_EMBEDDING_MODEL = "tongyi-embedding-vision-plus-2026-03-06"
        GREP_EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        GREP_EMBEDDING_API_KEY = "ds-key"
        EMBEDDING_API_KEY = "emb-fallback"
        EMBEDDING_MODEL = "other-model"
        EMBEDDING_BASE_URL = "https://example.com/v1"
        EMBEDDING_DIMENSION = 1152
        GREP_EMBEDDING_DIMENSION = 1152

    client = build_embedding_client_from_config(Cfg())
    assert client.cfg.model == "tongyi-embedding-vision-plus-2026-03-06"
    assert client.cfg.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert client.cfg.api_key == "ds-key"
    assert client.cfg.provider == "remote"
    assert client.cfg.dimension == 1152


def test_grep_embedding_qianfan_explicit():
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
