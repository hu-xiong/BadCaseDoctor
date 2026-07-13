# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import pytest

from memory.ark_embedding import is_doubao_ark_multimodal_embedding_model
from memory.embedding_benchmark import benchmark_doubao_multimodal_once


def test_is_doubao_ark_model():
    assert is_doubao_ark_multimodal_embedding_model("doubao-embedding-vision-251215")
    assert not is_doubao_ark_multimodal_embedding_model("text-embedding-v3")


@pytest.mark.skipif(
    not (os.getenv("DOUBAO_API_KEY") or "").strip(),
    reason="未配置 DOUBAO_API_KEY，跳过线上耗时测试",
)
def test_doubao_embedding_latency_live():
    r = benchmark_doubao_multimodal_once("天很蓝，海很深", include_sample_image=False, repeats=1)
    assert r.ok, r.error
    assert r.dims > 0
    assert r.latency_ms > 0
    print(f"\n[doubao text] {r.latency_ms:.1f} ms dims={r.dims}")
