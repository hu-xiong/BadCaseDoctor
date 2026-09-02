# -*- coding: utf-8 -*-
"""
LiteLLM 传输层：把注册表 model_id 映射为 litellm 调用参数。

业务选模仍走 model_router；此处只负责「怎么发请求 + 故障 fallback」。
启用：LLM_TRANSPORT=litellm
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from config import Config

from .model_registry import get_model


@dataclass(frozen=True)
class LiteLLMEndpoint:
    """一次 completion 所需的传输参数。"""

    business_model_id: str
    litellm_model: str  # 如 openai/qwen3.5-plus
    api_key: str
    api_base: Optional[str] = None
    provider: str = ""


def litellm_transport_enabled() -> bool:
    raw = (os.getenv("LLM_TRANSPORT") or "").strip().lower()
    return raw in ("litellm", "lite", "lt")


def _dashscope_key() -> str:
    return (
        (getattr(Config, "DASHSCOPE_API_KEY", None) or "")
        or (getattr(Config, "QWEN_API_KEY", None) or "")
        or (os.getenv("DASHSCOPE_API_KEY") or "")
        or (os.getenv("QWEN_API_KEY") or "")
    ).strip()


def _dashscope_base() -> str:
    return (
        (getattr(Config, "DASHSCOPE_COMPAT_BASE_URL", None) or "")
        or (os.getenv("DASHSCOPE_COMPAT_BASE_URL") or "")
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ).strip().rstrip("/")


def resolve_litellm_endpoint(model_id: Optional[str]) -> LiteLLMEndpoint:
    """
    将业务 model_id 转为 LiteLLM openai-compatible 调用。
    GLM 在本项目默认走百炼（与 factory 一致）。
    """
    mid = (model_id or getattr(Config, "DASHSCOPE_MODEL", None) or "qwen3.5-plus").strip()
    spec = get_model(mid)
    provider = (spec.provider if spec else "").strip().lower()
    ml = mid.lower()

    # 与 factory 一致：名称含 glm → 百炼
    use_dashscope = (
        "glm" in ml
        or "qwen" in ml
        or provider in ("qwen", "zhipu", "")
    )

    if provider == "deepseek" or ("deepseek" in ml and "glm" not in ml):
        key = (getattr(Config, "DEEPSEEK_API_KEY", None) or os.getenv("DEEPSEEK_API_KEY") or "").strip()
        base = (
            getattr(Config, "DEEPSEEK_API_BASE_URL", None)
            or os.getenv("DEEPSEEK_API_BASE_URL")
            or "https://api.deepseek.com"
        ).strip().rstrip("/")
        return LiteLLMEndpoint(
            business_model_id=mid,
            litellm_model=f"openai/{mid}",
            api_key=key,
            api_base=base,
            provider="deepseek",
        )

    if provider == "doubao" or "doubao" in ml or ml.startswith("ep-"):
        key = (getattr(Config, "DOUBAO_API_KEY", None) or os.getenv("DOUBAO_API_KEY") or "").strip()
        base = (
            getattr(Config, "DOUBAO_API_BASE_URL", None)
            or os.getenv("DOUBAO_API_BASE_URL")
            or "https://ark.cn-beijing.volces.com/api/v3"
        ).strip().rstrip("/")
        return LiteLLMEndpoint(
            business_model_id=mid,
            litellm_model=f"openai/{mid}",
            api_key=key,
            api_base=base,
            provider="doubao",
        )

    if provider == "qianfan" or "ernie" in ml:
        key = (getattr(Config, "QIANFAN_API_KEY", None) or os.getenv("QIANFAN_API_KEY") or "").strip()
        base = (os.getenv("QIANFAN_COMPAT_BASE_URL") or "").strip().rstrip("/") or None
        return LiteLLMEndpoint(
            business_model_id=mid,
            litellm_model=f"openai/{mid}",
            api_key=key,
            api_base=base,
            provider="qianfan",
        )

    if use_dashscope:
        return LiteLLMEndpoint(
            business_model_id=mid,
            litellm_model=f"openai/{mid}",
            api_key=_dashscope_key(),
            api_base=_dashscope_base(),
            provider="qwen",
        )

    # 兜底百炼
    return LiteLLMEndpoint(
        business_model_id=mid,
        litellm_model=f"openai/{mid}",
        api_key=_dashscope_key(),
        api_base=_dashscope_base(),
        provider=provider or "qwen",
    )


def fallback_model_ids(primary: str) -> List[str]:
    """
    LITELLM_FALLBACK_MODELS=qwen3.5-plus,deepseek-v4-flash
    不含 primary 自身；按顺序尝试。
    """
    raw = (os.getenv("LITELLM_FALLBACK_MODELS") or "").strip()
    if not raw:
        return []
    primary_l = (primary or "").strip().lower()
    out: List[str] = []
    for part in raw.split(","):
        m = part.strip()
        if not m or m.lower() == primary_l:
            continue
        if m not in out:
            out.append(m)
    return out


def litellm_num_retries() -> int:
    try:
        return max(0, min(5, int((os.getenv("LITELLM_NUM_RETRIES") or "1").strip() or "1")))
    except ValueError:
        return 1


def endpoints_for_request(model_id: Optional[str]) -> List[LiteLLMEndpoint]:
    primary = resolve_litellm_endpoint(model_id)
    chain = [primary]
    for fb in fallback_model_ids(primary.business_model_id):
        try:
            chain.append(resolve_litellm_endpoint(fb))
        except Exception:
            continue
    return chain
