# -*- coding: utf-8 -*-
"""火山方舟 Ark 多模态向量 API（/api/v3/embeddings/multimodal）。"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

_DOUBAO_ARK_MULTIMODAL_MARKERS = (
    "doubao-embedding",
    "doubao-embed",
)


def is_doubao_ark_multimodal_embedding_model(model: str) -> bool:
    m = (model or "").strip().lower()
    return any(marker in m for marker in _DOUBAO_ARK_MULTIMODAL_MARKERS)


def _default_ark_base_url() -> str:
    try:
        from config import Config as cfg

        u = (
            os.getenv("DOUBAO_EMBEDDING_BASE_URL", "").strip()
            or getattr(cfg, "DOUBAO_EMBEDDING_BASE_URL", "")
            or getattr(cfg, "DOUBAO_API_BASE_URL", "")
            or "https://ark.cn-beijing.volces.com/api/v3"
        )
        return u.strip().rstrip("/")
    except Exception:
        return "https://ark.cn-beijing.volces.com/api/v3"


def _parse_embedding_vector(body: Dict[str, Any]) -> List[float]:
    """兼容 data 为对象或列表、embedding 在 data / data[0]。"""
    data = body.get("data")
    row: Any = None
    if isinstance(data, list) and data:
        row = data[0]
    elif isinstance(data, dict):
        row = data
    if row is None:
        out = body.get("output") or {}
        if isinstance(out, dict):
            rows = out.get("embeddings")
            if isinstance(rows, list) and rows:
                row = rows[0]
    if row is None:
        raise RuntimeError(f"Ark multimodal embedding 响应无 data: {list(body.keys())}")

    if isinstance(row, dict):
        vec = row.get("embedding")
    else:
        vec = getattr(row, "embedding", None)
    if not isinstance(vec, list) or not vec:
        raise RuntimeError("Ark multimodal embedding 向量格式异常")
    return [float(x) for x in vec]


def embed_texts_ark_multimodal(
    texts: List[str],
    *,
    api_key: str,
    model: str,
    base_url: Optional[str] = None,
    timeout: float = 60.0,
    include_sample_image: bool = False,
    sample_image_url: Optional[str] = None,
) -> List[List[float]]:
    """
    对每条文本单独请求 multimodal embedding（文本态）。
    include_sample_image=True 时复现官方 curl：同一条 input 含 text + image_url（测图文融合耗时）。
    """
    from memory.qianfan_http_pool import qianfan_post_json

    key = (api_key or "").strip()
    if not key:
        raise RuntimeError("DOUBAO_API_KEY / ARK API key 未配置")
    m = (model or "").strip()
    if not m:
        raise RuntimeError("豆包 embedding model 未配置")
    base = (base_url or _default_ark_base_url()).strip().rstrip("/")
    img_url = (sample_image_url or "").strip() or (
        "https://ark-project.tos-cn-beijing.volces.com/images/view.jpeg"
    )

    out: List[List[float]] = []
    for text in texts:
        t = (text or "").strip() or " "
        inp: List[Dict[str, Any]] = [{"type": "text", "text": t}]
        if include_sample_image:
            inp.append({"type": "image_url", "image_url": {"url": img_url}})
        payload = {"model": m, "input": inp}
        status, body, err = qianfan_post_json(
            "/embeddings/multimodal",
            payload,
            api_key=key,
            base_url=base,
            timeout=timeout,
        )
        if err or status >= 400:
            detail = err or body.get("error") or body.get("message") or body
            raise RuntimeError(f"Ark multimodal embedding HTTP {status}: {detail}")
        out.append(_parse_embedding_vector(body))
    return out
