# -*- coding: utf-8
from memory.prefix_cache_client import parse_engine_prefix_cache, record_engine_prefix_cache


def test_record_engine_prefix_cache_disabled(monkeypatch):
    monkeypatch.setenv("PROMPT_PAGE_TABLE_ENABLED", "0")
    out = record_engine_prefix_cache(
        "s1",
        {"prompt_cache_hit_tokens": 10, "prompt_cache_miss_tokens": 0},
        tag="test",
    )
    assert out["engine_prefix_cache_hit_tokens"] == 10
