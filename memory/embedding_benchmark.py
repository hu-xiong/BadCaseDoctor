# -*- coding: utf-8 -*-
"""DashScope / 百炼向量模型单条文本 embedding 耗时基准（供脚本与 pytest 共用）。"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

from memory.ark_embedding import is_doubao_ark_multimodal_embedding_model
from memory.embedding_client import EmbeddingClient, EmbeddingConfig, is_dashscope_multimodal_embedding_model

DOUBAO_EMBEDDING_MODELS: List[str] = [
    "doubao-embedding-vision-251215",
]

# 与用户 curl 一致的示例图 URL
DOUBAO_SAMPLE_IMAGE_URL = (
    "https://ark-project.tos-cn-beijing.volces.com/images/view.jpeg"
)

# 用户指定 + 控制台「向量模型」页常见项（不含 rerank）
DASHSCOPE_EMBEDDING_MODELS: List[str] = [
    "tongyi-embedding-vision-flash-2026-03-06",
    "tongyi-embedding-vision-flash",
    "tongyi-embedding-vision-plus-2026-03-06",
    "tongyi-embedding-vision-plus",
    "text-embedding-v4",
    "text-embedding-v3",
    "qwen3-vl-embedding",
    "qwen2.5-vl-embedding",
    "multimodal-embedding-v1",
    "text-embedding-v1",
    "text-embedding-v2",
    "text-embedding-async-v1",
    "text-embedding-async-v2",
]

# 仅 rerank，非 embedding API
RERANK_ONLY_MODELS = frozenset(
    {
        "qwen3-vl-rerank",
        "qwen3-rerank",
        "gte-rerank-v2",
    }
)

DEFAULT_BENCHMARK_TEXT = (
    "问登录问题答的不好 复现步骤修改为 提问登录问题即可234456"
)


@dataclass
class EmbeddingBenchmarkResult:
    model: str
    ok: bool
    latency_ms: float
    dims: int
    api_kind: str  # multimodal | openai_compatible
    error: str = ""


def _benchmark_config(*, backend: str = "dashscope"):
    try:
        from config import Config as cfg
    except Exception:
        return None, None, None
    if (backend or "").strip().lower() == "doubao":
        api_key = (
            os.getenv("DOUBAO_EMBEDDING_BENCHMARK_API_KEY", "").strip()
            or getattr(cfg, "DOUBAO_API_KEY", "")
        )
        base_url = (
            os.getenv("DOUBAO_EMBEDDING_BENCHMARK_BASE_URL", "").strip()
            or getattr(cfg, "DOUBAO_EMBEDDING_BASE_URL", "")
            or getattr(cfg, "DOUBAO_API_BASE_URL", "")
        )
        return api_key, base_url, None
    api_key = (
        os.getenv("EMBEDDING_BENCHMARK_API_KEY", "").strip()
        or getattr(cfg, "EMBEDDING_API_KEY", "")
        or getattr(cfg, "DASHSCOPE_API_KEY", "")
        or getattr(cfg, "QWEN_API_KEY", "")
    )
    base_url = (
        os.getenv("EMBEDDING_BENCHMARK_BASE_URL", "").strip()
        or getattr(cfg, "EMBEDDING_BASE_URL", "")
        or getattr(cfg, "DASHSCOPE_COMPAT_BASE_URL", "")
    )
    dimension = getattr(cfg, "EMBEDDING_DIMENSION", None)
    return api_key, base_url, dimension


def benchmark_embedding_once(
    model: str,
    text: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    dimension: Optional[int] = None,
) -> EmbeddingBenchmarkResult:
    backend = "doubao" if is_doubao_ark_multimodal_embedding_model((model or "").strip()) else "dashscope"
    key, url, dim_cfg = _benchmark_config(backend=backend)
    key = (api_key or key or "").strip()
    url = (base_url or url or "").strip() or None
    if not key:
        return EmbeddingBenchmarkResult(
            model=model,
            ok=False,
            latency_ms=0.0,
            dims=0,
            api_kind="",
            error="未配置 API Key（EMBEDDING_API_KEY / DASHSCOPE_API_KEY）",
        )

    m = (model or "").strip()
    if m in RERANK_ONLY_MODELS:
        return EmbeddingBenchmarkResult(
            model=m,
            ok=False,
            latency_ms=0.0,
            dims=0,
            api_kind="rerank_only",
            error="该模型为 rerank，非 embedding",
        )

    if is_doubao_ark_multimodal_embedding_model(m):
        api_kind = "ark_multimodal"
    elif is_dashscope_multimodal_embedding_model(m):
        api_kind = "multimodal"
    else:
        api_kind = "openai_compatible"
    dim_use = dimension if dimension is not None else dim_cfg
    # 仅对已知 vision-plus 系列传 dimension，避免 flash/v4 因维度参数报错
    if dim_use is not None and "vision-plus" not in m.lower():
        dim_use = None

    client = EmbeddingClient(
        EmbeddingConfig(
            api_key=key,
            model=m,
            base_url=url,
            provider="remote",
            dimension=dim_use,
        )
    )
    t0 = time.perf_counter()
    try:
        vec = client.embed(text)
        ms = (time.perf_counter() - t0) * 1000.0
        if not vec:
            return EmbeddingBenchmarkResult(
                model=m,
                ok=False,
                latency_ms=ms,
                dims=0,
                api_kind=api_kind,
                error="返回向量为空",
            )
        return EmbeddingBenchmarkResult(
            model=m,
            ok=True,
            latency_ms=ms,
            dims=len(vec),
            api_kind=api_kind,
        )
    except Exception as ex:
        ms = (time.perf_counter() - t0) * 1000.0
        return EmbeddingBenchmarkResult(
            model=m,
            ok=False,
            latency_ms=ms,
            dims=0,
            api_kind=api_kind,
            error=str(ex)[:500],
        )


def run_embedding_benchmark_suite(
    text: str = DEFAULT_BENCHMARK_TEXT,
    models: Optional[Sequence[str]] = None,
    *,
    repeats: int = 1,
) -> List[EmbeddingBenchmarkResult]:
    """对每个模型测 repeats 次，成功时取中位 latency_ms。"""
    ms_list = list(models) if models else list(DASHSCOPE_EMBEDDING_MODELS)
    out: List[EmbeddingBenchmarkResult] = []
    reps = max(1, int(repeats))
    for model in ms_list:
        samples: List[EmbeddingBenchmarkResult] = []
        for _ in range(reps):
            samples.append(benchmark_embedding_once(model, text))
            if not samples[-1].ok:
                break
        if not samples:
            continue
        last = samples[-1]
        if not last.ok:
            out.append(last)
            continue
        latencies = sorted(s.latency_ms for s in samples if s.ok)
        mid = latencies[len(latencies) // 2]
        out.append(
            EmbeddingBenchmarkResult(
                model=last.model,
                ok=True,
                latency_ms=mid,
                dims=last.dims,
                api_kind=last.api_kind,
            )
        )
    return out


def format_benchmark_table(results: List[EmbeddingBenchmarkResult], text: str) -> str:
    lines = [
        f"文本 ({len(text)} 字): {text!r}",
        "",
        f"{'模型':<42} {'耗时(ms)':>10} {'维度':>6} {'API':<18} {'状态':<6}",
        "-" * 88,
    ]
    ok_rows = [r for r in results if r.ok]
    for r in sorted(results, key=lambda x: (not x.ok, x.latency_ms if x.ok else 1e9)):
        status = "OK" if r.ok else "FAIL"
        lat = f"{r.latency_ms:.1f}" if r.ok else "-"
        dims = str(r.dims) if r.ok else "-"
        lines.append(
            f"{r.model:<42} {lat:>10} {dims:>6} {r.api_kind:<18} {status:<6}"
        )
        if r.error:
            lines.append(f"  └─ {r.error[:200]}")
    if ok_rows:
        best = min(ok_rows, key=lambda x: x.latency_ms)
        lines.extend(
            [
                "",
                f"最快: {best.model} ({best.latency_ms:.1f} ms, dims={best.dims})",
            ]
        )
    return "\n".join(lines)


def benchmark_doubao_multimodal_once(
    text: str,
    *,
    model: Optional[str] = None,
    include_sample_image: bool = False,
    repeats: int = 1,
) -> EmbeddingBenchmarkResult:
    """豆包 Ark 多模态向量：纯文本或 text+官方示例图（与用户 curl 一致）。"""
    try:
        from config import Config as cfg
    except Exception:
        cfg = None  # type: ignore

    m = (
        (model or "").strip()
        or (getattr(cfg, "DOUBAO_EMBEDDING_MODEL", None) if cfg else None)
        or "doubao-embedding-vision-251215"
    )
    key, url, _ = _benchmark_config(backend="doubao")
    if not key:
        return EmbeddingBenchmarkResult(
            model=m,
            ok=False,
            latency_ms=0.0,
            dims=0,
            api_kind="ark_multimodal",
            error="未配置 DOUBAO_API_KEY",
        )

    from memory.ark_embedding import embed_texts_ark_multimodal

    label = f"{m}+image" if include_sample_image else m
    latencies: List[float] = []
    last_dims = 0
    last_err = ""
    reps = max(1, int(repeats))
    for _ in range(reps):
        t0 = time.perf_counter()
        try:
            vecs = embed_texts_ark_multimodal(
                [text],
                api_key=key,
                model=m,
                base_url=url,
                include_sample_image=include_sample_image,
                sample_image_url=DOUBAO_SAMPLE_IMAGE_URL,
            )
            ms = (time.perf_counter() - t0) * 1000.0
            if not vecs or not vecs[0]:
                return EmbeddingBenchmarkResult(
                    model=label,
                    ok=False,
                    latency_ms=ms,
                    dims=0,
                    api_kind="ark_multimodal",
                    error="返回向量为空",
                )
            latencies.append(ms)
            last_dims = len(vecs[0])
        except Exception as ex:
            ms = (time.perf_counter() - t0) * 1000.0
            return EmbeddingBenchmarkResult(
                model=label,
                ok=False,
                latency_ms=ms,
                dims=0,
                api_kind="ark_multimodal",
                error=str(ex)[:500],
            )

    mid = sorted(latencies)[len(latencies) // 2]
    return EmbeddingBenchmarkResult(
        model=label,
        ok=True,
        latency_ms=mid,
        dims=last_dims,
        api_kind="ark_multimodal",
        error=last_err,
    )


def run_doubao_embedding_benchmark(
    text: str = DEFAULT_BENCHMARK_TEXT,
    *,
    repeats: int = 3,
) -> List[EmbeddingBenchmarkResult]:
    """测纯文本与 text+示例图两种模式。"""
    return [
        benchmark_doubao_multimodal_once(text, include_sample_image=False, repeats=repeats),
        benchmark_doubao_multimodal_once(text, include_sample_image=True, repeats=repeats),
    ]
