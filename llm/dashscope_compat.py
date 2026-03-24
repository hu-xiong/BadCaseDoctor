# 阿里云百炼 OpenAI 兼容模式：POST /compatible-mode/v1/chat/completions
from __future__ import annotations

from openai import OpenAI

from config import Config

DEFAULT_COMPAT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def get_dashscope_compat_client() -> OpenAI:
    api_key = getattr(Config, "DASHSCOPE_API_KEY", None) or getattr(Config, "QWEN_API_KEY", None)
    if not api_key:
        raise ValueError("未配置 DASHSCOPE_API_KEY 或 QWEN_API_KEY")
    base = (
        getattr(Config, "DASHSCOPE_COMPAT_BASE_URL", None)
        or DEFAULT_COMPAT_BASE
    )
    return OpenAI(api_key=api_key, base_url=base.rstrip("/"))
