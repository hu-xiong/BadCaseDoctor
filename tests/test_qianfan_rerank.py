from unittest.mock import patch

from memory.qianfan_rerank_client import RerankHit, rerank_documents


def test_qianfan_rerank_parses_results():
    payload = {
        "results": [
            {"index": 1, "relevance_score": 0.88},
            {"index": 0, "relevance_score": 0.42},
        ]
    }

    with patch(
        "memory.qianfan_rerank_client.qianfan_post_json",
        return_value=(200, payload, None),
    ):
        hits, meta = rerank_documents(
            "收不到验证码",
            ["无关", "登录收不到验证码"],
            model="bce-reranker-base",
            top_n=2,
            api_key="test-key",
        )
    assert meta.get("status") == "ok"
    assert meta.get("backend") == "qianfan"
    assert meta.get("http") == "pool"
    assert len(hits) == 2
    assert hits[0] == RerankHit(index=1, score=0.88)


def test_rerank_router_uses_dashscope_by_default():
    from memory import rerank_client as rc

    fake_resp = type(
        "R",
        (),
        {
            "status_code": 200,
            "output": {"results": [{"index": 0, "relevance_score": 0.9}]},
            "usage": None,
        },
    )()

    class Cfg:
        GREP_RERANK_BACKEND = "dashscope"
        GREP_RERANK_MODEL = "qwen3-vl-rerank"
        GREP_RERANK_API_KEY = "ds-key"
        DASHSCOPE_API_KEY = "ds-fallback"

    with patch("dashscope.TextReRank.call", return_value=fake_resp):
        hits, meta = rc.rerank_documents("q", ["a"], cfg=Cfg())
    assert meta.get("status") == "ok"
    assert meta.get("backend") == "dashscope"
    assert len(hits) == 1


def test_rerank_router_qianfan_explicit():
    from memory import rerank_client as rc

    with patch(
        "memory.qianfan_rerank_client.qianfan_post_json",
        return_value=(200, {"results": [{"index": 0, "relevance_score": 0.9}]}, None),
    ):

        class Cfg:
            GREP_RERANK_BACKEND = "qianfan"
            GREP_RERANK_MODEL = "bce-reranker-base"
            GREP_RERANK_API_KEY = "k"
            GREP_RERANK_BASE_URL = "https://qianfan.baidubce.com/v2"

        hits, meta = rc.rerank_documents("q", ["a"], cfg=Cfg())
    assert meta.get("status") == "ok"
    assert len(hits) == 1
