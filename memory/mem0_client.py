"""mem0 Memory 单例：本地 Qdrant + 项目 Embedding + 现有 LLM 网关。"""

from __future__ import annotations

import os
import threading
from typing import Any, Optional

from config import Config

_lock = threading.Lock()
_memory: Any = None
_dims_resolved: Optional[int] = None


def _resolve_embedding_dims() -> int:
    global _dims_resolved
    if _dims_resolved is not None:
        return int(_dims_resolved)
    cfg_dim = getattr(Config, "EMBEDDING_DIMENSION", None)
    if cfg_dim is not None:
        try:
            _dims_resolved = int(cfg_dim)
            return int(_dims_resolved)
        except Exception:
            pass
    try:
        from memory.mem0_project_embedder import ProjectEmbedder

        emb = ProjectEmbedder()
        vec = emb.embed("dim-probe", memory_action="add")
        _dims_resolved = len(vec) if vec else 1152
    except Exception:
        _dims_resolved = 1152
    return int(_dims_resolved)


def _ensure_dirs() -> None:
    qpath = getattr(Config, "MEM0_QDRANT_PATH", "") or ""
    if qpath:
        os.makedirs(qpath, exist_ok=True)
    hist = getattr(Config, "MEM0_HISTORY_DB", "") or ""
    if hist:
        parent = os.path.dirname(hist)
        if parent:
            os.makedirs(parent, exist_ok=True)


def build_mem0_config() -> dict:
    """
    embedder 先填 openai 占位（通过 pydantic 校验），随后在 get_mem0_memory
    里替换为 ProjectEmbedder（项目 EmbeddingClient）。
    """
    dims = _resolve_embedding_dims()
    collection = getattr(Config, "MEM0_COLLECTION", "bdc_long_memory") or "bdc_long_memory"
    qpath = getattr(Config, "MEM0_QDRANT_PATH", "") or os.path.join("data", "mem0_qdrant")
    hist = getattr(Config, "MEM0_HISTORY_DB", "") or os.path.join("data", "mem0_history.db")
    llm_key = getattr(Config, "MEM0_LLM_API_KEY", "") or ""
    llm_base = getattr(Config, "MEM0_LLM_BASE_URL", "") or ""
    llm_model = getattr(Config, "MEM0_LLM_MODEL", "") or "qwen-plus"
    # 占位：避免 MemoryConfig 校验失败；真实向量由 ProjectEmbedder 提供
    emb_key = getattr(Config, "EMBEDDING_API_KEY", "") or llm_key or "unused"
    emb_base = getattr(Config, "EMBEDDING_BASE_URL", "") or llm_base or "http://127.0.0.1"
    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": collection,
                "path": qpath,
                "on_disk": True,
                "embedding_model_dims": dims,
            },
        },
        "llm": {
            "provider": "openai",
            "config": {
                "model": llm_model,
                "api_key": llm_key,
                "openai_base_url": llm_base,
                "temperature": 0.1,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "api_key": emb_key,
                "openai_base_url": emb_base,
                "embedding_dims": dims,
            },
        },
        "history_db_path": hist,
        "version": "v1.1",
    }


def get_mem0_memory():
    """进程内单例 Memory；未开启长期记忆时仍可构建（由上层门禁）。"""
    global _memory
    if _memory is not None:
        return _memory
    with _lock:
        if _memory is not None:
            return _memory
        # 关闭 mem0 匿名遥测（避免启动时打 PostHog）
        os.environ.setdefault("MEM0_TELEMETRY", "False")
        _ensure_dirs()
        from mem0 import Memory
        from mem0.configs.embeddings.base import BaseEmbedderConfig

        from memory.mem0_project_embedder import ProjectEmbedder

        dims = _resolve_embedding_dims()
        mem = Memory.from_config(build_mem0_config())
        mem.embedding_model = ProjectEmbedder(
            BaseEmbedderConfig(embedding_dims=dims)
        )
        _memory = mem
        return _memory


def reset_mem0_memory_for_tests() -> None:
    global _memory, _dims_resolved
    with _lock:
        if _memory is not None:
            try:
                _memory.close()
            except Exception:
                pass
        _memory = None
        _dims_resolved = None
