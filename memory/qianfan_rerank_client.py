"""千帆 v2 Rerank API（bce-reranker-base 等），供 Grep ES 召回精排。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from memory.qianfan_http_pool import qianfan_post_json


@dataclass(frozen=True)
class RerankHit:
    index: int
    score: float


def _resolve_api_key(cfg=None) -> str:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return ""
    return (
        getattr(cfg, "GREP_RERANK_API_KEY", "") or ""
        or getattr(cfg, "QIANFAN_API_KEY", "") or ""
    ).strip()


def _resolve_base_url(cfg=None) -> str:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return "https://qianfan.baidubce.com/v2"
    return (
        getattr(cfg, "GREP_RERANK_BASE_URL", None)
        or "https://qianfan.baidubce.com/v2"
    ).strip().rstrip("/")


def rerank_documents(
    query: str,
    documents: List[str],
    *,
    model: str = "bce-reranker-base",
    top_n: Optional[int] = None,
    instruct: Optional[str] = None,
    api_key: Optional[str] = None,
    cfg=None,
) -> Tuple[List[RerankHit], Dict[str, Any]]:
    """对 documents 做千帆 rerank；hits 按 score 降序，index 为原始下标。"""
    del instruct  # 千帆 BCE rerank 无 instruct 参数
    meta: Dict[str, Any] = {"model": model, "backend": "qianfan", "http": "pool"}
    q = (query or "").strip()
    docs = [(d or "").strip() for d in (documents or [])]
    if not q or not docs or not any(docs):
        meta["status"] = "empty_input"
        return [], meta

    key = (api_key or _resolve_api_key(cfg)).strip()
    if not key:
        meta["status"] = "no_api_key"
        return [], meta

    n = top_n if top_n is not None else len(docs)
    n = max(1, min(int(n), len(docs)))
    base = _resolve_base_url(cfg)
    payload = {
        "model": (model or "bce-reranker-base").strip(),
        "query": q,
        "documents": [d if d else " " for d in docs],
        "top_n": n,
    }
    try:
        timeout = float(getattr(cfg, "GREP_RERANK_HTTP_TIMEOUT", 30) if cfg else 30)
    except (TypeError, ValueError):
        timeout = 30.0
    status, data, err = qianfan_post_json(
        "/rerank",
        payload,
        api_key=key,
        base_url=base,
        timeout=timeout,
    )
    if err:
        if status >= 400:
            meta["status"] = "api_error"
            meta["http_code"] = status
            meta["error"] = err
        else:
            meta["status"] = "error"
            meta["error"] = err
        return [], meta

    rows = data.get("results") if isinstance(data, dict) else []
    if not rows and isinstance(data, dict):
        rows = data.get("data") or []
    hits: List[RerankHit] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("index"))
            score = float(row.get("relevance_score", row.get("score", 0)))
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(docs):
            hits.append(RerankHit(index=idx, score=score))
    hits.sort(key=lambda h: -h.score)
    meta["status"] = "ok"
    meta["hits_n"] = len(hits)
    if isinstance(data, dict) and data.get("usage"):
        meta["usage"] = data.get("usage")
    return hits, meta
