# -*- coding: utf-8 -*-
"""
OpenAI 兼容多模态：user.content 为 [{type:text}, {type:image_url,...}, ...]
前端 images 项形如 { data: dataURL|https URL|纯 base64, url?: 同 data, filename?: str }
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

__all__ = ["openai_style_user_content"]


def openai_style_user_content(
    prompt: str,
    images: Optional[List[Dict[str, Any]]],
    *,
    max_images: int = 8,
) -> Union[str, List[Dict[str, Any]]]:
    """
    无图时返回纯文本 str；有图时返回 content parts 列表（最后一项为全文 prompt 的 text）。
    """
    if not images:
        return prompt or ""
    parts: List[Dict[str, Any]] = []
    n = 0
    for img in images[:max_images]:
        if not isinstance(img, dict):
            continue
        raw = img.get("data") or img.get("url") or ""
        s = str(raw).strip()
        if not s:
            continue
        if s.startswith("data:"):
            url = s
        elif s.startswith("http://") or s.startswith("https://"):
            url = s
        else:
            url = f"data:image/jpeg;base64,{s}"
        parts.append({"type": "image_url", "image_url": {"url": url}})
        n += 1
    text = (prompt or "").strip() or "(请结合上图回答)"
    parts.append({"type": "text", "text": text})
    if n == 0:
        return prompt or ""
    return parts
