from unittest.mock import MagicMock

from agents.tools import grep_hybrid_search as ghs


def _cfg():
    c = MagicMock()
    c.GREP_QUERY_EMBED_MODE = "auto"
    c.GREP_QUERY_FULL_VECTOR_MIN_CHARS = 8
    return c


def test_short_query_hybrid_vector_plus_bm25():
    need, es_q, title_only, mode = ghs.resolve_grep_es_search_strategy(
        _cfg(), "登录", None
    )
    assert need is True
    assert es_q == "登录"
    assert title_only is False
    assert mode == "hybrid"


def test_three_char_query_hybrid():
    need, es_q, _, mode = ghs.resolve_grep_es_search_strategy(_cfg(), "三个字", None)
    assert need is True
    assert es_q == "三个字"
    assert mode == "hybrid"


def test_eight_chars_vector_only():
    need, es_q, _, mode = ghs.resolve_grep_es_search_strategy(
        _cfg(), "一二三四五六78", None
    )
    assert need is True
    assert es_q is None
    assert mode == "vector_only"


def test_long_user_phrase_vector_only():
    need, es_q, _, mode = ghs.resolve_grep_es_search_strategy(
        _cfg(), "登录bug，密码没有加密模式", None
    )
    assert need is True
    assert es_q is None
    assert mode == "vector_only"


def test_digit_only_keywords_use_vector_when_long_nl():
    need, es_q, _, mode = ghs.resolve_grep_es_search_strategy(
        _cfg(),
        "当前沙箱一次性把之前的diff展示出来了",
        None,
    )
    assert need is True
    assert es_q is None
    assert mode == "vector_only"


def test_should_query_embed_auto_short_keyword_bm25_only():
    cfg = MagicMock()
    cfg.GREP_QUERY_EMBED_MODE = "auto"
    cfg.GREP_QUERY_FULL_VECTOR_MIN_CHARS = 8
    assert ghs._should_query_embed(cfg, "登录", None) is True


def test_should_query_embed_never():
    cfg = MagicMock()
    cfg.GREP_QUERY_EMBED_MODE = "never"
    assert ghs._should_query_embed(cfg, "x" * 200, None) is False


def test_entity_types_for_es_recall_ignores_narrow_target():
    assert ghs._entity_types_for_es_recall("card") == [
        "bug",
        "badcase",
        "testcase",
        "card",
        "plan",
    ]
    assert ghs._entity_types_for_es_recall("bug") == ghs._entity_types_for_es_recall("all")
