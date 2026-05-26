from __future__ import annotations



from dataclasses import dataclass

from typing import List, Optional



_DASHSCOPE_MULTIMODAL_MARKERS = (

    "tongyi-embedding-vision",

    "multimodal-embedding",

    "qwen3-vl-embedding",

    "qwen2.5-vl-embedding",

)

_MULTIMODAL_BATCH_SIZE = 10





def is_dashscope_multimodal_embedding_model(model: str) -> bool:

    m = (model or "").strip().lower()

    return any(marker in m for marker in _DASHSCOPE_MULTIMODAL_MARKERS)





@dataclass(frozen=True)

class EmbeddingConfig:

    api_key: str

    model: str

    base_url: Optional[str] = None

    provider: str = "remote"  # remote | local

    dimension: Optional[int] = None





class EmbeddingClient:

    """

    统一 Embedding 客户端：

    - text-embedding-v* 等：OpenAI SDK + compatible-mode

    - tongyi-embedding-vision* / qwen*-vl-embedding：DashScope MultiModalEmbedding 原生 API

  """



    def __init__(self, cfg: EmbeddingConfig):

        self.cfg = cfg

        self._local_model = None



    def _embed_local(self, texts: List[str]) -> List[List[float]]:

        try:

            if self._local_model is None:

                from sentence_transformers import SentenceTransformer



                self._local_model = SentenceTransformer(self.cfg.model)

            vecs = self._local_model.encode(texts, normalize_embeddings=True)

            return [[float(x) for x in row] for row in vecs]

        except Exception as e:

            raise RuntimeError(f"本地 Embedding 失败({self.cfg.model}): {e}") from e



    def _embed_dashscope_multimodal(self, texts: List[str]) -> List[List[float]]:

        try:

            import dashscope

            from http import HTTPStatus

        except Exception as e:

            raise RuntimeError(f"dashscope SDK 不可用: {e}") from e



        if not self.cfg.api_key:

            raise RuntimeError("Embedding API key 未配置")

        if not self.cfg.model:

            raise RuntimeError("Embedding model 未配置")



        out: List[List[float]] = []

        for start in range(0, len(texts), _MULTIMODAL_BATCH_SIZE):

            chunk = texts[start : start + _MULTIMODAL_BATCH_SIZE]

            payload = [{"text": t or " "} for t in chunk]

            kwargs = {}

            if self.cfg.dimension is not None:

                kwargs["dimension"] = int(self.cfg.dimension)



            resp = dashscope.MultiModalEmbedding.call(

                model=self.cfg.model,

                input=payload,

                api_key=self.cfg.api_key,

                **kwargs,

            )

            if getattr(resp, "status_code", None) not in (None, HTTPStatus.OK, 200):

                code = getattr(resp, "code", None)

                message = getattr(resp, "message", None) or str(resp)

                raise RuntimeError(f"DashScope MultiModalEmbedding 失败: {code} {message}")



            output = getattr(resp, "output", None) or {}

            rows = output.get("embeddings") if isinstance(output, dict) else getattr(output, "embeddings", None)

            if not rows:

                raise RuntimeError("DashScope MultiModalEmbedding 返回为空")



            chunk_vecs: List[List[float]] = []

            for row in rows:

                if isinstance(row, dict):

                    vec = row.get("embedding")

                else:

                    vec = getattr(row, "embedding", None)

                if not isinstance(vec, list):

                    raise RuntimeError("DashScope MultiModalEmbedding 向量格式异常")

                chunk_vecs.append([float(x) for x in vec])



            if len(chunk_vecs) != len(chunk):

                raise RuntimeError(

                    f"DashScope MultiModalEmbedding batch 返回不完整: expect={len(chunk)} got={len(chunk_vecs)}"

                )

            out.extend(chunk_vecs)



        if len(out) != len(texts):

            raise RuntimeError(f"DashScope MultiModalEmbedding 返回不完整: expect={len(texts)} got={len(out)}")

        return out



    def _embed_openai_compatible(self, texts: List[str]) -> List[List[float]]:

        try:

            from memory.qianfan_http_pool import get_openai_compatible_client

        except Exception as e:

            raise RuntimeError(f"openai SDK 不可用: {e}") from e

        client = get_openai_compatible_client(
            self.cfg.api_key,
            self.cfg.base_url,
        )

        resp = client.embeddings.create(model=self.cfg.model, input=texts)

        out: List[List[float]] = [[] for _ in texts]

        for item in resp.data:

            idx = int(getattr(item, "index", 0))

            vec = getattr(item, "embedding", None)

            if isinstance(vec, list) and 0 <= idx < len(out):

                out[idx] = [float(x) for x in vec]

        if any(not v for v in out):

            raise RuntimeError("Embedding batch 返回不完整")

        return out



    def embed_batch(self, texts: List[str]) -> List[List[float]]:

        cleaned = [(t or "").strip() for t in texts]

        if not cleaned:

            return []

        if all(not t for t in cleaned):

            return [[] for _ in cleaned]

        if (self.cfg.provider or "remote").lower() == "local":

            return self._embed_local(cleaned)

        if not self.cfg.api_key:

            raise RuntimeError("Embedding API key 未配置")

        if not self.cfg.model:

            raise RuntimeError("Embedding model 未配置")

        if is_dashscope_multimodal_embedding_model(self.cfg.model):

            return self._embed_dashscope_multimodal(cleaned)

        return self._embed_openai_compatible(cleaned)



    def embed(self, text: str) -> List[float]:

        vecs = self.embed_batch([text])

        return vecs[0] if vecs else []


