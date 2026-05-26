from __future__ import annotations

import re
from typing import List, Optional

from memory.embedding_client import EmbeddingClient, EmbeddingConfig


def _slug_model(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "model").strip()).strip("_").lower()
    return s[:48] or "model"


def _grep_embedding_backend(cfg) -> str:
    return (
        str(getattr(cfg, "GREP_EMBEDDING_BACKEND", "qianfan") or "qianfan")
        .strip()
        .lower()
    )


def build_embedding_client_from_config(cfg=None) -> EmbeddingClient:
    """Grep / work_item 索引用 embedding；默认千帆 BGE（快），可改 dashscope 多模态或 local。"""
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            cfg = None
    backend = _grep_embedding_backend(cfg)
    dimension = getattr(cfg, "GREP_EMBEDDING_DIMENSION", None)
    if dimension is None:
        dimension = getattr(cfg, "EMBEDDING_DIMENSION", None)

    if backend == "local":
        local_model = getattr(cfg, "GREP_EMBEDDING_LOCAL_MODEL", "") or getattr(
            cfg, "EMBEDDING_LOCAL_MODEL", "BAAI/bge-small-zh-v1.5"
        )
        return EmbeddingClient(
            EmbeddingConfig(
                api_key="",
                model=local_model,
                base_url=None,
                provider="local",
                dimension=dimension,
            )
        )

    if backend in ("dashscope", "qwen", "aliyun", "tongyi"):
        api_key = getattr(cfg, "EMBEDDING_API_KEY", "") or ""
        model = getattr(cfg, "EMBEDDING_MODEL", "") or "tongyi-embedding-vision-plus-2026-03-06"
        base_url = getattr(cfg, "EMBEDDING_BASE_URL", "") or None
        return EmbeddingClient(
            EmbeddingConfig(
                api_key=api_key,
                model=model,
                base_url=base_url,
                provider="remote",
                dimension=dimension,
            )
        )

    # 默认 qianfan：OpenAI 兼容 /v2/embeddings + bge-large-zh
    api_key = (
        getattr(cfg, "GREP_EMBEDDING_API_KEY", "") or ""
        or getattr(cfg, "QIANFAN_API_KEY", "") or ""
    )
    model = getattr(cfg, "GREP_EMBEDDING_MODEL", "") or "bge-large-zh"
    base_url = (
        getattr(cfg, "GREP_EMBEDDING_BASE_URL", "") or "https://qianfan.baidubce.com/v2"
    ).strip()
    return EmbeddingClient(
        EmbeddingConfig(
            api_key=api_key,
            model=model,
            base_url=base_url,
            provider="remote",
            dimension=dimension,
        )
    )


def physical_work_item_index_name(dims: int, cfg=None) -> str:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            cfg = None
    explicit = getattr(cfg, "GREP_WORK_ITEM_INDEX", "") or ""
    if explicit:
        return explicit
    prefix = getattr(cfg, "ES_INDEX_PREFIX", "bdc_dev_")
    model = getattr(cfg, "GREP_EMBEDDING_MODEL", "") or getattr(cfg, "EMBEDDING_MODEL", "embed")
    slug = _slug_model(model)
    return f"{prefix}work_item_{slug}_v1_{int(dims)}"


def work_item_alias_name(cfg=None) -> str:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            cfg = None
    return getattr(cfg, "GREP_WORK_ITEM_ALIAS", "") or f"{getattr(cfg, 'ES_INDEX_PREFIX', 'bdc_dev_')}work_item"
