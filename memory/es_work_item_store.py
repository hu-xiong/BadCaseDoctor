from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from memory.es_long_memory import ESConfig, _mk_es_client
from memory.grep_es_config import physical_work_item_index_name, work_item_alias_name


@dataclass(frozen=True)
class WorkItemSearchConfig:
    alias: str
    top_k: int = 30
    min_score: float = 0.0
    rrf_k: int = 60


class ESWorkItemStore:
    """Bug/BadCase 工作项 ES 索引：BM25 + KNN 混合检索。"""

    _alias_exists_cache: Dict[str, Tuple[bool, float]] = {}
    _alias_exists_cache_lock = threading.Lock()

    @staticmethod
    def _alias_exists_ttl_seconds(exists: bool) -> float:
        """索引已存在时长期缓存，避免每次 grep 打远端 indices.exists（~700ms）。"""
        if exists:
            try:
                return float(os.getenv("GREP_ES_ALIAS_CACHE_OK_TTL_S", "86400"))
            except (TypeError, ValueError):
                return 86400.0
        try:
            return float(os.getenv("GREP_ES_ALIAS_CACHE_MISS_TTL_S", "120"))
        except (TypeError, ValueError):
            return 120.0

    def __init__(self, es_cfg: ESConfig, search_cfg: WorkItemSearchConfig):
        self.es_cfg = es_cfg
        self.search_cfg = search_cfg
        self._es = None
        self._index_ready: Optional[Tuple[str, int]] = None
        self._index_lock = threading.Lock()

    def alias_exists(self, alias: Optional[str] = None) -> bool:
        """indices.exists 走进程内短缓存，避免每次 grep 打两次远端 ES。"""
        name = (alias or self.search_cfg.alias or "").strip()
        if not name:
            return False
        now = time.time()
        with ESWorkItemStore._alias_exists_cache_lock:
            hit = ESWorkItemStore._alias_exists_cache.get(name)
            if hit is not None:
                ok_cached, ts = hit
                ttl = ESWorkItemStore._alias_exists_ttl_seconds(ok_cached)
                if (now - ts) < ttl:
                    return ok_cached
        try:
            ok = bool(self.es.indices.exists(index=name))
        except Exception:
            ok = False
        with ESWorkItemStore._alias_exists_cache_lock:
            ESWorkItemStore._alias_exists_cache[name] = (ok, now)
        return ok

    @property
    def es(self):
        if self._es is None:
            self._es = _mk_es_client(self.es_cfg)
        return self._es

    def _physical_index(self, dims: int) -> str:
        return physical_work_item_index_name(dims)

    def ensure_index(self, dims: int) -> str:
        physical = self._physical_index(dims)
        if self._index_ready == (physical, int(dims)):
            return physical

        with self._index_lock:
            if self._index_ready == (physical, int(dims)):
                return physical

            alias = self.search_cfg.alias
            if self.es.indices.exists(index=physical):
                self._ensure_alias(physical, alias)
                self._index_ready = (physical, int(dims))
                return physical

            mapping = {
                "settings": {
                    "number_of_shards": 1,
                    "analysis": {
                        "analyzer": {
                            "bdc_search": {
                                "type": "custom",
                                "tokenizer": "standard",
                                "filter": ["lowercase", "cjk_width"],
                            }
                        }
                    },
                },
                "mappings": {
                    "dynamic": "false",
                    "properties": {
                        "record_id": {"type": "keyword"},
                        "entity_type": {"type": "keyword"},
                        "project_id": {"type": "integer"},
                        "plan_id": {"type": "long"},
                        "card_id": {"type": "long"},
                        "assignee_id": {"type": "integer"},
                        "assignee_display": {"type": "keyword"},
                        "status": {"type": "keyword"},
                        "priority": {"type": "keyword"},
                        "title": {
                            "type": "text",
                            "analyzer": "bdc_search",
                            "fields": {"keyword": {"type": "keyword"}},
                        },
                        "search_text": {"type": "text", "analyzer": "bdc_search"},
                        "fields": {"type": "object", "enabled": True},
                        "content_hash": {"type": "keyword"},
                        "updated_at": {"type": "date"},
                        "indexed_at": {"type": "date"},
                        "embedding": {
                            "type": "dense_vector",
                            "dims": int(dims),
                            "index": True,
                            "similarity": "cosine",
                        },
                    },
                },
            }
            try:
                self.es.indices.create(index=physical, **mapping)
                print(
                    f"[GREP-ES] 已创建 work_item 索引 physical={physical} alias={alias} dims={dims}",
                    flush=True,
                )
            except Exception as e:
                err = str(e).lower()
                if "resource_already_exists" not in err and "already exists" not in err:
                    raise
            self._ensure_alias(physical, alias)
            self._index_ready = (physical, int(dims))
            return physical

    def _ensure_alias(self, physical: str, alias: str) -> None:
        if not alias or alias == physical:
            return
        try:
            if self.es.indices.exists_alias(name=alias, index=physical):
                return

            actions: List[Dict[str, Any]] = []
            if self.es.indices.exists_alias(name=alias):
                existing = self.es.indices.get_alias(name=alias)
                for idx in existing.keys():
                    if idx != physical:
                        actions.append({"remove": {"index": idx, "alias": alias}})

            actions.append({"add": {"index": physical, "alias": alias}})
            self.es.indices.update_aliases(body={"actions": actions})
        except Exception as e:
            err = str(e).lower()
            if "already exists" in err or "resource_already_exists" in err:
                return
            if self.es.indices.exists_alias(name=alias, index=physical):
                return
            print(f"[GREP-ES] alias 更新失败(忽略): {e}", flush=True)

    def bulk_upsert(self, docs: List[Dict[str, Any]], dims: int) -> int:
        if not docs:
            return 0
        idx = self.ensure_index(dims)
        now_ms = int(time.time() * 1000)
        lines: List[Any] = []
        for doc in docs:
            eid = doc.get("_id") or f"{doc.get('entity_type')}:{doc.get('record_id')}"
            body = dict(doc)
            body.pop("_id", None)
            body["indexed_at"] = now_ms
            lines.append({"index": {"_index": idx, "_id": eid}})
            lines.append(body)
        resp = self.es.bulk(operations=lines, refresh=False)
        errors = resp.get("errors") if isinstance(resp, dict) else False
        if errors:
            print(f"[GREP-ES] bulk 部分失败: {resp}", flush=True)
        return len(docs)

    def delete(self, entity_type: str, record_id: int) -> None:
        alias = self.search_cfg.alias
        eid = f"{entity_type}:{record_id}"
        try:
            if self.es.indices.exists(index=alias):
                self.es.delete(index=alias, id=eid, ignore=[404])
        except Exception as e:
            print(f"[GREP-ES] delete {eid} 失败: {e}", flush=True)

    def _base_filters(
        self,
        *,
        project_id: int,
        entity_types: Optional[List[str]] = None,
        plan_id: Optional[int] = None,
        assignee_ids: Optional[List[int]] = None,
        assignee_display: Optional[str] = None,
        status: Optional[str] = None,
        record_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        flt: List[Dict[str, Any]] = [{"term": {"project_id": int(project_id)}}]
        if entity_types:
            flt.append({"terms": {"entity_type": [str(x) for x in entity_types]}})
        if plan_id is not None:
            try:
                flt.append({"term": {"plan_id": int(plan_id)}})
            except (TypeError, ValueError):
                pass
        if assignee_ids:
            flt.append({"terms": {"assignee_id": [int(x) for x in assignee_ids]}})
        elif assignee_display:
            flt.append({"term": {"assignee_display": str(assignee_display)}})
        if status:
            flt.append({"term": {"status": str(status).lower()}})
        if record_id is not None:
            flt.append({"term": {"record_id": str(record_id)}})
        return flt

    @staticmethod
    def _work_item_source_includes() -> List[str]:
        return [
            "record_id",
            "entity_type",
            "project_id",
            "plan_id",
            "card_id",
            "assignee_id",
            "assignee_display",
            "status",
            "priority",
            "title",
            "fields",
        ]

    def _bm25_must_clause(self, qtext: str, *, title_only: bool) -> Dict[str, Any]:
        if title_only:
            return {"match": {"title": {"query": qtext, "operator": "or"}}}
        return {
            "multi_match": {
                "query": qtext,
                "fields": ["title^3", "search_text"],
                "type": "best_fields",
                "operator": "or",
            }
        }

    def hybrid_search(
        self,
        *,
        project_id: int,
        query_text: Optional[str],
        query_embedding: Optional[List[float]],
        entity_types: Optional[List[str]] = None,
        plan_id: Optional[int] = None,
        assignee_ids: Optional[List[int]] = None,
        assignee_display: Optional[str] = None,
        status: Optional[str] = None,
        record_id: Optional[int] = None,
        top_k: Optional[int] = None,
        alias_checked: bool = False,
        bm25_title_only: bool = False,
        request_timeout_s: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        alias = self.search_cfg.alias
        if not alias_checked and not self.alias_exists(alias):
            return []
        k = int(top_k or self.search_cfg.top_k or 30)
        flt = self._base_filters(
            project_id=project_id,
            entity_types=entity_types,
            plan_id=plan_id,
            assignee_ids=assignee_ids,
            assignee_display=assignee_display,
            status=status,
            record_id=record_id,
        )
        qtext = (query_text or "").strip()
        has_vec = bool(query_embedding)
        has_text = bool(qtext) and qtext not in ("*",)
        src = self._work_item_source_includes()
        req_to = request_timeout_s
        search_kw: Dict[str, Any] = {"index": alias, "body": {}, "track_total_hits": False}
        if req_to is not None and req_to > 0:
            search_kw["request_timeout"] = float(req_to)

        def _do_search(body: Dict[str, Any]) -> Any:
            body["_source"] = {"includes": src}
            if req_to is not None and req_to > 0:
                # ES 只接受整秒，如 "2s"（"2.0s" 会 400 导致整条 hybrid 失败）
                body["timeout"] = f"{max(1, int(round(float(req_to))))}s"
            search_kw["body"] = body
            return self.es.search(**search_kw)

        if not has_vec and not has_text and not assignee_ids and not assignee_display and not status and record_id is None:
            body = {
                "size": k,
                "query": {"bool": {"filter": flt}},
                "sort": [{"updated_at": {"order": "desc"}}],
            }
            res = _do_search(body)
            return self._parse_hits(res, source="filter_only")

        # ES 8.x：knn 必须作为 search 顶层参数，不能嵌在 bool.must/should 里（否则会报 unknown field [k]）
        knn_clause: Optional[Dict[str, Any]] = None
        if has_vec:
            knn_clause = {
                "field": "embedding",
                "query_vector": query_embedding,
                "k": k,
                "num_candidates": max(24, min(80, k * 4)),
                "filter": {"bool": {"filter": flt}},
            }

        text_must = self._bm25_must_clause(qtext, title_only=bool(bm25_title_only))
        if has_vec and has_text:
            body = {
                "size": k,
                "query": {"bool": {"filter": flt, "must": [text_must]}},
                "knn": knn_clause,
            }
        elif has_vec:
            body = {"size": k, "knn": knn_clause}
        else:
            body = {
                "size": k,
                "query": {"bool": {"filter": flt, "must": [text_must]}},
            }
        res = _do_search(body)
        return self._parse_hits(res, source="hybrid")

    def _parse_hits(self, res: Any, *, source: str) -> List[Dict[str, Any]]:
        hits = (((res or {}).get("hits") or {}).get("hits") or [])
        out: List[Dict[str, Any]] = []
        min_score = float(self.search_cfg.min_score or 0.0)
        for h in hits:
            score = float((h or {}).get("_score") or 0.0)
            if min_score > 0 and score < min_score:
                continue
            src = (h or {}).get("_source") or {}
            out.append(
                {
                    "id": (h or {}).get("_id"),
                    "score": score,
                    "search_backend": source,
                    **src,
                }
            )
        return out


_store_singleton: Optional[ESWorkItemStore] = None
_store_singleton_lock = threading.Lock()


def build_work_item_store_from_config(cfg=None) -> ESWorkItemStore:
    global _store_singleton
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            cfg = None
    with _store_singleton_lock:
        if _store_singleton is not None:
            return _store_singleton
        es_cfg = ESConfig(
            url=getattr(cfg, "ES_URL", ""),
            host=getattr(cfg, "ES_HOST", ""),
            port=int(getattr(cfg, "ES_PORT", 9200)),
            username=getattr(cfg, "ES_USERNAME", ""),
            password=getattr(cfg, "ES_PASSWORD", ""),
            api_key=getattr(cfg, "ES_API_KEY", ""),
            verify_certs=bool(getattr(cfg, "ES_VERIFY_CERTS", True)),
        )
        search_cfg = WorkItemSearchConfig(
            alias=work_item_alias_name(cfg),
            top_k=int(getattr(cfg, "GREP_VECTOR_TOP_K", 12)),
            min_score=float(getattr(cfg, "GREP_VECTOR_MIN_SCORE", 0.0)),
            rrf_k=int(getattr(cfg, "GREP_HYBRID_RRF_K", 60)),
        )
        _store_singleton = ESWorkItemStore(es_cfg, search_cfg)
        # 默认跳过同步 ping：首次 grep 的真实 _search 已能验证连接，额外 HEAD 会增加
        # 500ms~1s 冷启动延迟。需要诊断连接时设置 GREP_ES_BUILD_PING=1。
        if (os.getenv("GREP_ES_BUILD_PING", "0") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            try:
                t_ping = time.perf_counter()
                if _store_singleton.es.ping(request_timeout=2):
                    print(
                        f"[GREP-ES] 连接预热 ping ok ms="
                        f"{(time.perf_counter() - t_ping) * 1000.0:.0f}",
                        flush=True,
                    )
            except Exception as _ping_ex:
                print(f"[GREP-ES] 连接预热 ping 失败: {_ping_ex}", flush=True)
        return _store_singleton
