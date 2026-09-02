"""mem0 EmbeddingBase 适配：委托给项目现有 EmbeddingClient。"""

from __future__ import annotations

from typing import List, Literal, Optional

from mem0.configs.embeddings.base import BaseEmbedderConfig
from mem0.embeddings.base import EmbeddingBase

from config import Config
from memory.embedding_client import EmbeddingClient, EmbeddingConfig


class ProjectEmbedder(EmbeddingBase):
    """用 Config.EMBEDDING_* / EmbeddingClient 做向量，兼容 DashScope 多模态模型。"""

    def __init__(self, config: Optional[BaseEmbedderConfig] = None):
        super().__init__(config)
        self._client = EmbeddingClient(
            EmbeddingConfig(
                api_key=getattr(Config, "EMBEDDING_API_KEY", "") or "",
                model=getattr(Config, "EMBEDDING_MODEL", "") or "",
                base_url=(getattr(Config, "EMBEDDING_BASE_URL", "") or "").strip() or None,
                provider=getattr(Config, "EMBEDDING_PROVIDER", "remote") or "remote",
                dimension=getattr(Config, "EMBEDDING_DIMENSION", None),
            )
        )
        dims = getattr(Config, "EMBEDDING_DIMENSION", None)
        if dims is None and self.config.embedding_dims:
            dims = int(self.config.embedding_dims)
        if dims is None:
            # tongyi-embedding-vision-plus 默认 1152；未知时首次 embed 探测
            dims = 1152
        self.config.embedding_dims = int(dims)
        self.config.model = self._client.cfg.model or self.config.model

    def embed(
        self,
        text,
        memory_action: Optional[Literal["add", "search", "update"]] = None,
    ):
        del memory_action  # EmbeddingClient 不区分 action
        raw = (text or "").replace("\n", " ").strip() or " "
        vec = self._client.embed(raw[:4000])
        if not vec:
            raise RuntimeError("EmbeddingClient 返回空向量")
        if self.config.embedding_dims and len(vec) != int(self.config.embedding_dims):
            # 以真实维度为准，避免与探测值不一致
            self.config.embedding_dims = len(vec)
        return [float(x) for x in vec]

    def embed_batch(self, texts, memory_action="add"):
        del memory_action
        cleaned = [((t or "").replace("\n", " ").strip() or " ")[:4000] for t in texts]
        if not cleaned:
            return []
        vecs = self._client.embed_batch(cleaned)
        out: List[List[float]] = []
        for v in vecs:
            if not v:
                raise RuntimeError("EmbeddingClient batch 含空向量")
            out.append([float(x) for x in v])
        if out and self.config.embedding_dims and len(out[0]) != int(self.config.embedding_dims):
            self.config.embedding_dims = len(out[0])
        return out
