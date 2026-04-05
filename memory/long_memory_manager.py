from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import Config
from memory.embedding_client import EmbeddingClient, EmbeddingConfig
from memory.es_long_memory import ESConfig, ESLongMemoryStore, LongMemoryConfig


_SENSITIVE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),  # OpenAI-like
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key
    re.compile(r"mysql\+pymysql://[^ \n]+", re.IGNORECASE),
    re.compile(r"\bpassword\s*=\s*[^ \n]+", re.IGNORECASE),
    re.compile(r"\bsecret\s*=\s*[^ \n]+", re.IGNORECASE),
    re.compile(r"\btoken\s*=\s*[^ \n]+", re.IGNORECASE),
]


def _looks_sensitive(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return any(p.search(t) for p in _SENSITIVE_PATTERNS)


@dataclass
class RetrievedMemory:
    id: str
    type: str
    text: str
    score: float


class LongMemoryManager:
    def __init__(self):
        self.enabled = bool(getattr(Config, "LONG_MEMORY_ENABLED", False))
        self.store = ESLongMemoryStore(
            ESConfig(
                url=getattr(Config, "ES_URL", ""),
                host=getattr(Config, "ES_HOST", ""),
                port=getattr(Config, "ES_PORT", 9200),
                username=getattr(Config, "ES_USERNAME", ""),
                password=getattr(Config, "ES_PASSWORD", ""),
                api_key=getattr(Config, "ES_API_KEY", ""),
                verify_certs=bool(getattr(Config, "ES_VERIFY_CERTS", True)),
            ),
            LongMemoryConfig(
                index_name=getattr(Config, "ES_LONG_MEMORY_INDEX", "bdc_long_memory"),
                top_k=int(getattr(Config, "LONG_MEMORY_TOP_K", 10)),
                use_n=int(getattr(Config, "LONG_MEMORY_USE_N", 4)),
                min_score=float(getattr(Config, "LONG_MEMORY_MIN_SCORE", 0.0)),
            ),
        )
        self.embedder = EmbeddingClient(
            EmbeddingConfig(
                api_key=getattr(Config, "EMBEDDING_API_KEY", "") or "",
                model=getattr(Config, "EMBEDDING_MODEL", "") or "",
                base_url=(getattr(Config, "EMBEDDING_BASE_URL", "") or "").strip() or None,
            )
        )

    def retrieve_context(
        self,
        *,
        user_id: str,
        query: str,
        project_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        返回适合直接塞进 ReAct context 的结构：
        - long_memory_items: [{id,type,text,score}]
        - long_memory_text: 供提示词注入的合并文本（短）
        """
        if not self.enabled:
            return {"long_memory_items": [], "long_memory_text": ""}
        q = (query or "").strip()
        if not q:
            return {"long_memory_items": [], "long_memory_text": ""}

        qvec = self.embedder.embed(q[:4000])
        hits = self.store.retrieve(
            user_id=str(user_id),
            project_id=str(project_id) if project_id is not None else None,
            plan_id=str(plan_id) if plan_id is not None else None,
            query_embedding=qvec,
            top_k=self.store.mem_cfg.top_k,
            types=types,
        )

        # 简单裁剪：只取前 use_n 条，且过滤敏感/空文本
        use_n = int(self.store.mem_cfg.use_n or 4)
        items: List[RetrievedMemory] = []
        used_ids: List[str] = []
        for h in hits:
            if len(items) >= use_n:
                break
            mid = str(h.get("id") or "")
            mtype = str(h.get("type") or "fact")
            txt = str(h.get("memory_text") or "").strip()
            score = float(h.get("score") or 0.0)
            if not mid or not txt:
                continue
            if _looks_sensitive(txt):
                continue
            if score < float(self.store.mem_cfg.min_score or 0.0):
                continue
            items.append(RetrievedMemory(id=mid, type=mtype, text=txt[:800], score=score))
            used_ids.append(mid)

        # 异步不做：这里是同步 touch，失败无所谓
        try:
            self.store.touch_used(used_ids)
        except Exception:
            pass

        merged_lines = []
        for i, it in enumerate(items, start=1):
            merged_lines.append(f"{i}. [{it.type}] {it.text}")
        merged = "\n".join(merged_lines)
        return {
            "long_memory_items": [it.__dict__ for it in items],
            "long_memory_text": merged,
        }

    def retrieve_recent_for_project(
        self,
        *,
        user_id: str,
        project_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        按项目拉最近更新的记忆（不跑向量），供「打开项目」时注入；避免每条用户消息都 embed+检索 ES。
        """
        if not self.enabled or not (project_id or "").strip():
            return {"long_memory_items": [], "long_memory_text": ""}
        use_n = int(self.store.mem_cfg.use_n or 4)
        raw = self.store.list_items(
            user_id=str(user_id),
            project_id=str(project_id),
            plan_id=str(plan_id) if plan_id else None,
            size=max(use_n, 8),
            offset=0,
            types=types,
        )
        items: List[RetrievedMemory] = []
        for row in (raw.get("items") or []):
            if len(items) >= use_n:
                break
            if row.get("enabled") is False:
                continue
            mid = str(row.get("id") or "")
            mtype = str(row.get("type") or "fact")
            txt = str(row.get("memory_text") or "").strip()
            if not mid or not txt or _looks_sensitive(txt):
                continue
            items.append(RetrievedMemory(id=mid, type=mtype, text=txt[:800], score=1.0))
        merged_lines = [f"{i}. [{it.type}] {it.text}" for i, it in enumerate(items, start=1)]
        merged = "\n".join(merged_lines)
        return {
            "long_memory_items": [it.__dict__ for it in items],
            "long_memory_text": merged,
        }

    def write_simple(
        self,
        *,
        user_id: str,
        project_id: Optional[str],
        plan_id: Optional[str],
        agent_session_id: Optional[str],
        memory_type: str,
        memory_text: str,
        source: str = "user_explicit",
        confidence: float = 0.7,
    ) -> Dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("长期记忆未开启（LONG_MEMORY_ENABLED=false）。")
        txt = (memory_text or "").strip()
        if not txt:
            raise RuntimeError("memory_text 不能为空。")
        if _looks_sensitive(txt):
            raise RuntimeError("检测到敏感信息，拒绝写入长期记忆。")

        vec = self.embedder.embed(txt[:4000])
        return self.store.upsert(
            user_id=str(user_id),
            project_id=str(project_id) if project_id is not None else None,
            plan_id=str(plan_id) if plan_id is not None else None,
            agent_session_id=str(agent_session_id) if agent_session_id is not None else None,
            memory_type=str(memory_type or "fact"),
            memory_text=txt,
            embedding=vec,
            source=source,
            confidence=float(confidence),
            enabled=True,
        )

