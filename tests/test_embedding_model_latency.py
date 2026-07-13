# -*- coding: utf-8 -*-
"""
DashScope 向量模型真实 API 耗时（集成测试）。

默认跳过：未配置 EMBEDDING_BENCHMARK_RUN=1 或无 API Key。
全量跑控制台列表较久，建议用脚本:

  set EMBEDDING_BENCHMARK_RUN=1
  python scripts/benchmark_dashscope_embedding_models.py

或只测当前 grep 模型:

  pytest tests/test_embedding_model_latency.py -v -s
"""
from __future__ import annotations

import os

import pytest

from memory.embedding_benchmark import (
    DEFAULT_BENCHMARK_TEXT,
    benchmark_embedding_once,
    run_embedding_benchmark_suite,
)


def _has_api_key() -> bool:
    from memory.embedding_benchmark import _benchmark_config

    key, _, _ = _benchmark_config()
    return bool((key or "").strip())


@pytest.mark.skipif(
    os.getenv("EMBEDDING_BENCHMARK_RUN", "").strip().lower()
    not in ("1", "true", "yes", "on"),
    or not _has_api_key(),
    reason="需 EMBEDDING_BENCHMARK_RUN=1 且配置 DashScope API Key",
)
def test_grep_default_model_embedding_latency():
    """当前 Config 默认 GREP/EMBEDDING 模型单条耗时（决策用基线）。"""
    from config import Config

    model = Config.GREP_EMBEDDING_MODEL or Config.EMBEDDING_MODEL
    r = benchmark_embedding_once(model, DEFAULT_BENCHMARK_TEXT)
    assert r.ok, r.error
    assert r.dims > 0
    assert r.latency_ms > 0
    print(
        f"\n[EMBED-BENCH] model={r.model} latency_ms={r.latency_ms:.1f} "
        f"dims={r.dims} api={r.api_kind} text_len={len(DEFAULT_BENCHMARK_TEXT)}"
    )


@pytest.mark.skipif(
    os.getenv("EMBEDDING_BENCHMARK_RUN", "").strip().lower()
    not in ("1", "true", "yes", "on"),
    or not _has_api_key(),
    reason="需 EMBEDDING_BENCHMARK_RUN=1 且配置 DashScope API Key",
)
def test_flash_models_embedding_latency():
    """用户关心的 flash 系列。"""
    for model in (
        "tongyi-embedding-vision-flash-2026-03-06",
        "tongyi-embedding-vision-flash",
    ):
        r = benchmark_embedding_once(model, DEFAULT_BENCHMARK_TEXT)
        print(f"\n[EMBED-BENCH] {model}: ok={r.ok} ms={r.latency_ms:.1f} err={r.error!r}")
        if r.ok:
            assert r.dims > 0


@pytest.mark.skipif(
    os.getenv("EMBEDDING_BENCHMARK_FULL", "").strip().lower()
    not in ("1", "true", "yes", "on"),
    or not _has_api_key(),
    reason="全量模型需 EMBEDDING_BENCHMARK_FULL=1（耗时数分钟）",
)
def test_all_dashscope_embedding_models_suite():
    results = run_embedding_benchmark_suite(DEFAULT_BENCHMARK_TEXT, repeats=1)
    from memory.embedding_benchmark import format_benchmark_table

    print("\n" + format_benchmark_table(results, DEFAULT_BENCHMARK_TEXT))
    assert any(r.ok for r in results), "至少应有一个模型成功"
