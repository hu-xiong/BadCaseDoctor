from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ESConfig:
    url: str = ""
    host: str = ""
    port: int = 9200
    username: str = ""
    password: str = ""
    api_key: str = ""
    verify_certs: bool = True


@dataclass(frozen=True)
class LongMemoryConfig:
    index_name: str
    top_k: int = 10
    use_n: int = 4
    min_score: float = 0.0


def _now_ts() -> float:
    return float(time.time())


def _mk_es_client(cfg: ESConfig):
    """进程内复用 ES 客户端 + connections_per_node 连接池（见 memory/es_client_pool.py）。"""
    from memory.es_client_pool import get_es_client

    return get_es_client(cfg)


class ESLongMemoryStore:
    """
    ES 向量长期记忆：
    - 自动建索引（首次写入时按 embedding 维度创建 mapping）
    - 写入/upsert、向量检索、列表、启停、删除、反馈
    """

    def __init__(self, es_cfg: ESConfig, mem_cfg: LongMemoryConfig):
        self.es_cfg = es_cfg
        self.mem_cfg = mem_cfg
        self._es = None
        self._index_ready: Optional[Tuple[str, int]] = None  # (index, dims)

    @property
    def es(self):
        if self._es is None:
            self._es = _mk_es_client(self.es_cfg)
        return self._es

    def ensure_index(self, dims: int) -> None:
        idx = self.mem_cfg.index_name
        if self._index_ready == (idx, int(dims)):
            return
        if self.es.indices.exists(index=idx):
            self._index_ready = (idx, int(dims))
            return

        mapping = {
            "mappings": {
                "dynamic": "false",
                "properties": {
                    "user_id": {"type": "keyword"},
                    "project_id": {"type": "keyword"},
                    "plan_id": {"type": "keyword"},
                    "agent_session_id": {"type": "keyword"},
                    "type": {"type": "keyword"},
                    "memory_text": {"type": "text"},
                    "source": {"type": "keyword"},
                    "source_refs": {"type": "object", "enabled": True},
                    "confidence": {"type": "float"},
                    "enabled": {"type": "boolean"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "last_used_at": {"type": "date"},
                    "use_count": {"type": "integer"},
                    "feedback": {"type": "keyword"},
                    "ttl_days": {"type": "integer"},
                    "embedding": {"type": "dense_vector", "dims": int(dims), "index": True, "similarity": "cosine"},
                },
            }
        }
        self.es.indices.create(index=idx, **mapping)
        self._index_ready = (idx, int(dims))

    def upsert(
        self,
        *,
        user_id: str,
        project_id: Optional[str],
        plan_id: Optional[str],
        agent_session_id: Optional[str],
        memory_type: str,
        memory_text: str,
        embedding: List[float],
        source: str,
        source_refs: Optional[Dict[str, Any]] = None,
        confidence: float = 0.6,
        enabled: bool = True,
        ttl_days: Optional[int] = None,
        memory_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not embedding:
            raise RuntimeError("embedding 为空，无法写入长期记忆。")
            raise RuntimeError("embedding 为空，无法写入长期记忆。")
        self.ensure_index(len(embedding))
        mid = memory_id or str(uuid.uuid4())
        now_ms = int(_now_ts() * 1000)

        doc = {
            "user_id": str(user_id),
            "project_id": str(project_id) if project_id is not None else "",
            "plan_id": str(plan_id) if plan_id is not None else "",
            "agent_session_id": str(agent_session_id) if agent_session_id is not None else "",
            "type": str(memory_type or "fact"),
            "memory_text": str(memory_text or "").strip(),
            "embedding": embedding,
            "source": str(source or "chat"),
            "source_refs": source_refs or {},
            "confidence": float(confidence),
            "enabled": bool(enabled),
            "updated_at": now_ms,
            "created_at": now_ms,
            "last_used_at": 0,
            "use_count": 0,
            "feedback": "none",
            "ttl_days": int(ttl_days) if ttl_days is not None else 0,
        }

        # upsert：若已存在则保留 created_at/use_count 等
        script = {
            "source": """
                if (ctx._source.containsKey('created_at') == false) { ctx._source.created_at = params.doc.created_at; }
                ctx._source.user_id = params.doc.user_id;
                ctx._source.project_id = params.doc.project_id;
                ctx._source.plan_id = params.doc.plan_id;
                ctx._source.agent_session_id = params.doc.agent_session_id;
                ctx._source.type = params.doc.type;
                ctx._source.memory_text = params.doc.memory_text;
                ctx._source.embedding = params.doc.embedding;
                ctx._source.source = params.doc.source;
                ctx._source.source_refs = params.doc.source_refs;
                ctx._source.confidence = params.doc.confidence;
                ctx._source.enabled = params.doc.enabled;
                ctx._source.updated_at = params.doc.updated_at;
                if (ctx._source.containsKey('use_count') == false) { ctx._source.use_count = 0; }
                if (ctx._source.containsKey('feedback') == false) { ctx._source.feedback = 'none'; }
                if (ctx._source.containsKey('ttl_days') == false) { ctx._source.ttl_days = params.doc.ttl_days; }
            """,
            "lang": "painless",
            "params": {"doc": doc},
        }

        resp = self.es.update(
            index=self.mem_cfg.index_name,
            id=mid,
            doc=doc,
            doc_as_upsert=True,
            script=script,
            refresh=False,
        )
        return {"id": mid, "result": resp.get("result", "updated")}

    def _base_filters(
        self,
        *,
        user_id: str,
        project_id: Optional[str],
        plan_id: Optional[str],
        types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        flt: List[Dict[str, Any]] = [
            {"term": {"user_id": str(user_id)}},
            {"term": {"enabled": True}},
        ]
        if project_id is not None:
            flt.append({"term": {"project_id": str(project_id)}})
        if plan_id is not None:
            flt.append({"term": {"plan_id": str(plan_id)}})
        if types:
            flt.append({"terms": {"type": [str(x) for x in types if str(x).strip()]}})
        return flt

    def retrieve(
        self,
        *,
        user_id: str,
        project_id: Optional[str],
        plan_id: Optional[str],
        query_embedding: List[float],
        top_k: Optional[int] = None,
        types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        if not query_embedding:
            return []
        self.ensure_index(len(query_embedding))
        k = int(top_k or self.mem_cfg.top_k or 10)
        flt = self._base_filters(user_id=user_id, project_id=project_id, plan_id=plan_id, types=types)

        body = {
            "size": k,
            "_source": [
                "type",
                "memory_text",
                "source",
                "source_refs",
                "confidence",
                "created_at",
                "updated_at",
                "last_used_at",
                "use_count",
                "feedback",
                "project_id",
                "plan_id",
            ],
            "knn": {
                "field": "embedding",
                "query_vector": query_embedding,
                "k": k,
                "num_candidates": max(50, k * 10),
                "filter": {"bool": {"filter": flt}},
            },
        }

        res = self.es.search(index=self.mem_cfg.index_name, body=body)
        hits = (((res or {}).get("hits") or {}).get("hits") or [])
        out: List[Dict[str, Any]] = []
        for h in hits:
            src = (h or {}).get("_source") or {}
            score = float((h or {}).get("_score") or 0.0)
            out.append(
                {
                    "id": (h or {}).get("_id"),
                    "score": score,
                    **src,
                }
            )
        return out

    def touch_used(self, ids: List[str]) -> None:
        if not ids:
            return
        now_ms = int(_now_ts() * 1000)
        for mid in ids[:200]:
            try:
                self.es.update(
                    index=self.mem_cfg.index_name,
                    id=str(mid),
                    script={
                        "source": """
                            if (ctx._source.containsKey('use_count') == false) { ctx._source.use_count = 0; }
                            ctx._source.use_count += 1;
                            ctx._source.last_used_at = params.now;
                        """,
                        "lang": "painless",
                        "params": {"now": now_ms},
                    },
                    refresh=False,
                )
            except Exception:
                pass

    def list_items(
        self,
        *,
        user_id: str,
        project_id: Optional[str],
        plan_id: Optional[str],
        size: int = 50,
        offset: int = 0,
        types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        size = max(1, min(int(size), 200))
        offset = max(0, int(offset))
        flt = self._base_filters(user_id=user_id, project_id=project_id, plan_id=plan_id, types=types)
        body = {
            "from": offset,
            "size": size,
            "track_total_hits": True,
            "sort": [{"updated_at": "desc"}],
            "_source": ["type", "memory_text", "source", "confidence", "enabled", "updated_at", "created_at", "use_count", "feedback"],
            "query": {"bool": {"filter": flt}},
        }
        res = self.es.search(index=self.mem_cfg.index_name, body=body)
        hits = (((res or {}).get("hits") or {}).get("hits") or [])
        total = (((res or {}).get("hits") or {}).get("total") or {}).get("value", len(hits))
        items = [{"id": h.get("_id"), **(h.get("_source") or {})} for h in hits]
        return {"total": int(total or 0), "items": items}

    def set_enabled(self, *, memory_id: str, enabled: bool) -> None:
        now_ms = int(_now_ts() * 1000)
        self.es.update(
            index=self.mem_cfg.index_name,
            id=str(memory_id),
            doc={"enabled": bool(enabled), "updated_at": now_ms},
            refresh=False,
        )

    def set_feedback(self, *, memory_id: str, feedback: str) -> None:
        now_ms = int(_now_ts() * 1000)
        self.es.update(
            index=self.mem_cfg.index_name,
            id=str(memory_id),
            doc={"feedback": str(feedback or "none"), "updated_at": now_ms},
            refresh=False,
        )

    def delete(self, *, memory_id: str) -> None:
        self.es.delete(index=self.mem_cfg.index_name, id=str(memory_id), ignore=[404])

