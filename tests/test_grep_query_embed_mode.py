from unittest.mock import MagicMock

from agents.tools import grep_hybrid_search as ghs


def test_should_query_embed_auto_short_keyword_bm25_only():
    cfg = MagicMock()
    cfg.GREP_QUERY_EMBED_MODE = "auto"
    cfg.GREP_QUERY_EMBED_MIN_CHARS = 80
    assert ghs._should_query_embed(cfg, "邮箱验证码", None, None) is False


def test_should_query_embed_auto_long_text():
    cfg = MagicMock()
    cfg.GREP_QUERY_EMBED_MODE = "auto"
    cfg.GREP_QUERY_EMBED_MIN_CHARS = 10
    long_q = "登录失败且邮箱不能收到验证码需要排查SMTP配置与网关限流策略"
    assert ghs._should_query_embed(cfg, long_q, None, None) is True


def test_should_query_embed_never():
    cfg = MagicMock()
    cfg.GREP_QUERY_EMBED_MODE = "never"
    assert ghs._should_query_embed(cfg, "x" * 200, None, None) is False
