"""Grep 用 rerank 路由：默认通义 qwen3-vl-rerank，可选千帆 BCE。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from memory.qianfan_rerank_client import RerankHit


def rerank_documents(
    query: str,
    documents: List[str],
    *,
    model: Optional[str] = None,
    top_n: Optional[int] = None,
    instruct: Optional[str] = None,
    api_key: Optional[str] = None,
    cfg=None,
) -> Tuple[List[RerankHit], Dict[str, Any]]:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            cfg = None
    backend = (
        str(getattr(cfg, "GREP_RERANK_BACKEND", "dashscope") or "dashscope")
        .strip()
        .lower()
    )
    if backend in ("dashscope", "qwen", "aliyun", "tongyi"):
        from memory.qwen_rerank_client import rerank_documents as _ds

        m = model or getattr(cfg, "GREP_RERANK_MODEL", None) or "qwen3-vl-rerank"
        return _ds(
            query,
            documents,
            model=str(m).strip(),
            top_n=top_n,
            instruct=instruct,
            api_key=api_key,
            cfg=cfg,
        )
    from memory.qianfan_rerank_client import rerank_documents as _qf

    m = model or getattr(cfg, "GREP_RERANK_MODEL", None) or "bce-reranker-base"
    return _qf(
        query,
        documents,
        model=str(m).strip(),
        top_n=top_n,
        cfg=cfg,
    )
