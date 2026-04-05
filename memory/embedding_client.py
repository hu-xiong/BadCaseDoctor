from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class EmbeddingConfig:
    api_key: str
    model: str
    base_url: Optional[str] = None


class EmbeddingClient:
    """
    统一 Embedding 客户端：
    - 使用 openai SDK（项目已依赖），支持 OpenAI 官方或 OpenAI-compatible base_url（如 DashScope compatible-mode）。
    """

    def __init__(self, cfg: EmbeddingConfig):
        self.cfg = cfg

    def embed(self, text: str) -> List[float]:
        text = (text or "").strip()
        if not text:
            return []
        if not self.cfg.api_key:
            raise RuntimeError("Embedding API key 未配置：请设置 EMBEDDING_API_KEY（或 OPENAI_API_KEY/DASHSCOPE_API_KEY）。")
        if not self.cfg.model:
            raise RuntimeError("Embedding model 未配置：请设置 EMBEDDING_MODEL。")

        try:
            from openai import OpenAI
        except Exception as e:
            raise RuntimeError(f"openai SDK 不可用: {e}")

        client = OpenAI(
            api_key=self.cfg.api_key,
            base_url=self.cfg.base_url or None,
        )
        resp = client.embeddings.create(model=self.cfg.model, input=text)
        data0 = resp.data[0]
        vec = getattr(data0, "embedding", None)
        if not isinstance(vec, list) or not vec:
            raise RuntimeError("Embedding 返回为空或格式不正确。")
        return [float(x) for x in vec]

