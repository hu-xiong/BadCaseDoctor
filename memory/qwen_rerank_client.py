"""DashScope / 千问 Text Rerank 客户端（qwen3-vl-rerank 等）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


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
        or getattr(cfg, "DASHSCOPE_API_KEY", "") or ""
        or getattr(cfg, "QWEN_API_KEY", "") or ""
    ).strip()


def rerank_documents(
    query: str,
    documents: List[str],
    *,
    model: str = "qwen3-vl-rerank",
    top_n: Optional[int] = None,
    instruct: Optional[str] = None,
    api_key: Optional[str] = None,
    cfg=None,
) -> Tuple[List[RerankHit], Dict[str, Any]]:
    """
    对 documents 做语义 rerank，返回 (hits 按 score 降序, meta)。
    hits 中 index 为 documents 原始下标。
    """
    meta: Dict[str, Any] = {"model": model}
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

    model_l = (model or "qwen3-vl-rerank").strip()
    use_vl = "vl-rerank" in model_l.lower()

    try:
        import dashscope
        from http import HTTPStatus

        dashscope.api_key = key
        kwargs: Dict[str, Any] = {
            "model": model_l,
            "top_n": n,
            "return_documents": False,
        }
        if use_vl:
            kwargs["query"] = {"text": q}
            kwargs["documents"] = [{"text": d} if d else {"text": " "} for d in docs]
            if instruct and str(instruct).strip():
                kwargs["instruct"] = str(instruct).strip()
        else:
            kwargs["query"] = q
            kwargs["documents"] = docs
            if instruct and str(instruct).strip():
                kwargs["instruct"] = str(instruct).strip()

        resp = dashscope.TextReRank.call(**kwargs)
        if getattr(resp, "status_code", None) not in (None, HTTPStatus.OK, 200):
            meta["status"] = "api_error"
            meta["code"] = getattr(resp, "code", None)
            meta["message"] = getattr(resp, "message", None) or str(resp)
            return [], meta

        output = getattr(resp, "output", None) or {}
        if isinstance(output, dict):
            results = output.get("results") or []
        else:
            results = getattr(output, "results", None) or []

        hits: List[RerankHit] = []
        for row in results:
            if isinstance(row, dict):
                idx = row.get("index")
                score = row.get("relevance_score")
            else:
                idx = getattr(row, "index", None)
                score = getattr(row, "relevance_score", None)
            try:
                i = int(idx)
                s = float(score)
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(docs):
                hits.append(RerankHit(index=i, score=s))

        usage = getattr(resp, "usage", None)
        if usage is not None:
            meta["total_tokens"] = getattr(usage, "total_tokens", None) or (
                usage.get("total_tokens") if isinstance(usage, dict) else None
            )
        meta["status"] = "ok"
        meta["backend"] = "dashscope"
        meta["hits_n"] = len(hits)
        return hits, meta
    except Exception as e:
        meta["status"] = "error"
        meta["error"] = str(e)
        return [], meta
