from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict, List, Optional, Tuple

from agents.tools.grep_assignee import resolve_assignee_display
from memory.embed_batch_queue import EmbedBatchQueue, _PendingEmbed
from memory.embedding_client import EmbeddingClient
from memory.es_work_item_store import ESWorkItemStore, build_work_item_store_from_config
from memory.grep_es_config import build_embedding_client_from_config


def _s(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _join_search_text(parts: List[str]) -> str:
    return "\n".join(p for p in parts if p and str(p).strip())


def _json_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v).strip()


def _enum_s(v: Any) -> str:
    return v.value if hasattr(v, "value") else _s(v)


def content_hash_for_doc(entity_type: str, record_id: int, search_text: str, meta: Dict[str, Any]) -> str:
    payload = {
        "entity_type": entity_type,
        "record_id": record_id,
        "search_text": search_text,
        "meta": meta,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_bug_es_doc(bug) -> Tuple[str, Dict[str, Any], str]:
    assignee_display = resolve_assignee_display(getattr(bug, "assignee_id", None))
    status_val = bug.status.value if hasattr(bug.status, "value") else str(getattr(bug, "status", "") or "")
    fields = {
        "steps_to_reproduce": _s(getattr(bug, "steps_to_reproduce", "")),
        "expected_result": _s(getattr(bug, "expected_result", "")),
        "actual_result": _s(getattr(bug, "actual_result", "")),
        "severity": _s(getattr(bug, "severity", "")),
        "bug_type": _s(getattr(bug, "bug_type", "")),
        "environment": _s(getattr(bug, "environment", "")),
        "browser": _s(getattr(bug, "browser", "")),
        "os": _s(getattr(bug, "os", "")),
    }
    search_text = _join_search_text(
        [
            _s(getattr(bug, "title", "")),
            fields["steps_to_reproduce"],
            fields["expected_result"],
            fields["actual_result"],
            status_val,
            _s(getattr(bug, "priority", "")),
            fields["severity"],
            fields["bug_type"],
            fields["environment"],
            f"assignee:{assignee_display}" if assignee_display else "",
        ]
    )
    meta = {
        "status": status_val,
        "priority": _s(getattr(bug, "priority", "")),
        "assignee_id": getattr(bug, "assignee_id", None),
        "assignee_display": assignee_display,
    }
    ch = content_hash_for_doc("bug", int(bug.id), search_text, meta)
    doc = {
        "record_id": str(int(bug.id)),
        "entity_type": "bug",
        "project_id": int(bug.project_id),
        "plan_id": int(bug.plan_id) if getattr(bug, "plan_id", None) is not None else None,
        "card_id": int(bug.card_id) if getattr(bug, "card_id", None) is not None else None,
        "assignee_id": int(bug.assignee_id) if getattr(bug, "assignee_id", None) is not None else None,
        "assignee_display": assignee_display or None,
        "status": status_val or None,
        "priority": _s(getattr(bug, "priority", "")) or None,
        "title": _s(getattr(bug, "title", "")),
        "search_text": search_text,
        "fields": fields,
        "content_hash": ch,
        "updated_at": int(bug.updated_at.timestamp() * 1000) if getattr(bug, "updated_at", None) else None,
    }
    return f"bug:{bug.id}", doc, search_text


def build_badcase_es_doc(bc) -> Tuple[str, Dict[str, Any], str]:
    assignee_display = _s(getattr(bc, "assignee", ""))
    status_val = bc.status.value if hasattr(bc.status, "value") else str(getattr(bc, "status", "") or "")
    fields = {
        "case_category": _s(getattr(bc, "case_category", "")),
        "base_problem": _s(getattr(bc, "base_problem", "")),
        "reproduction_steps": _s(getattr(bc, "reproduction_steps", "")),
        "badcase_result": _s(getattr(bc, "badcase_result", "")),
        "answer": _s(getattr(bc, "answer", "")),
        "correct_answer": _s(getattr(bc, "correct_answer", "")),
        "problem_reason": _s(getattr(bc, "problem_reason", "")),
        "solution": _s(getattr(bc, "solution", "")),
    }
    search_text = _join_search_text(
        [
            _s(getattr(bc, "title", "")),
            fields["case_category"],
            fields["base_problem"],
            fields["reproduction_steps"],
            fields["badcase_result"],
            fields["answer"],
            fields["problem_reason"],
            fields["solution"],
            status_val,
            _s(getattr(bc, "priority", "")),
            f"assignee:{assignee_display}" if assignee_display else "",
        ]
    )
    meta = {
        "status": status_val,
        "priority": _s(getattr(bc, "priority", "")),
        "assignee_display": assignee_display,
    }
    ch = content_hash_for_doc("badcase", int(bc.id), search_text, meta)
    doc = {
        "record_id": str(int(bc.id)),
        "entity_type": "badcase",
        "project_id": int(bc.project_id),
        "plan_id": int(bc.plan_id) if getattr(bc, "plan_id", None) is not None else None,
        "card_id": int(bc.card_id) if getattr(bc, "card_id", None) is not None else None,
        "assignee_id": None,
        "assignee_display": assignee_display or None,
        "status": status_val or None,
        "priority": _s(getattr(bc, "priority", "")) or None,
        "title": _s(getattr(bc, "title", "")),
        "search_text": search_text,
        "fields": fields,
        "content_hash": ch,
        "updated_at": int(bc.updated_at.timestamp() * 1000) if getattr(bc, "updated_at", None) else None,
    }
    return f"badcase:{bc.id}", doc, search_text


def build_testcase_es_doc(tc) -> Tuple[str, Dict[str, Any], str]:
    assignee_display = resolve_assignee_display(getattr(tc, "assignee_id", None))
    status_val = _enum_s(getattr(tc, "status", ""))
    execution_result = _enum_s(getattr(tc, "execution_result", ""))
    fields = {
        "case_type": _s(getattr(tc, "case_type", "")),
        "test_type": _s(getattr(tc, "test_type", "")),
        "preconditions": _s(getattr(tc, "preconditions", "")),
        "steps": _json_text(getattr(tc, "steps", None)),
        "remark": _s(getattr(tc, "remark", "")),
        "baseline": _s(getattr(tc, "baseline", "")),
        "version": _s(getattr(tc, "version", "")),
        "related_defects": _json_text(getattr(tc, "related_defects", None)),
        "execution_result": execution_result,
    }
    search_text = _join_search_text([
        _s(getattr(tc, "title", "")),
        fields["case_type"],
        fields["test_type"],
        fields["preconditions"],
        fields["steps"],
        fields["remark"],
        fields["baseline"],
        fields["version"],
        fields["related_defects"],
        fields["execution_result"],
        status_val,
        _s(getattr(tc, "priority", "")),
        f"assignee:{assignee_display}" if assignee_display else "",
    ])
    meta = {
        "status": status_val,
        "priority": _s(getattr(tc, "priority", "")),
        "assignee_id": getattr(tc, "assignee_id", None),
        "assignee_display": assignee_display,
    }
    ch = content_hash_for_doc("testcase", int(tc.id), search_text, meta)
    doc = {
        "record_id": str(int(tc.id)),
        "entity_type": "testcase",
        "project_id": int(tc.project_id),
        "plan_id": int(tc.plan_id) if getattr(tc, "plan_id", None) is not None else None,
        "card_id": int(tc.card_id) if getattr(tc, "card_id", None) is not None else None,
        "assignee_id": int(tc.assignee_id) if getattr(tc, "assignee_id", None) is not None else None,
        "assignee_display": assignee_display or None,
        "status": status_val or None,
        "priority": _s(getattr(tc, "priority", "")) or None,
        "title": _s(getattr(tc, "title", "")),
        "search_text": search_text,
        "fields": fields,
        "content_hash": ch,
        "updated_at": int(tc.updated_at.timestamp() * 1000) if getattr(tc, "updated_at", None) else None,
    }
    return f"testcase:{tc.id}", doc, search_text


def build_card_es_doc(card) -> Tuple[str, Dict[str, Any], str]:
    assignee_display = resolve_assignee_display(getattr(card, "assignee_id", None))
    card_type = _enum_s(getattr(card, "type", ""))
    execution_result = _enum_s(getattr(card, "execution_result", ""))
    fields = {
        "type": card_type,
        "description": _s(getattr(card, "description", "")),
        "severity": _s(getattr(card, "severity", "")),
        "steps_to_reproduce": _s(getattr(card, "steps_to_reproduce", "")),
        "expected_result": _s(getattr(card, "expected_result", "")),
        "actual_result": _s(getattr(card, "actual_result", "")),
        "bug_type": _s(getattr(card, "bug_type", "")),
        "environment": _s(getattr(card, "environment", "")),
        "browser": _s(getattr(card, "browser", "")),
        "os": _s(getattr(card, "os", "")),
        "case_category": _s(getattr(card, "case_category", "")),
        "base_problem": _s(getattr(card, "base_problem", "")),
        "reproduction_steps": _s(getattr(card, "reproduction_steps", "")),
        "badcase_result": _s(getattr(card, "badcase_result", "")),
        "answer": _s(getattr(card, "answer", "")),
        "correct_answer": _s(getattr(card, "correct_answer", "")),
        "problem_reason": _s(getattr(card, "problem_reason", "")),
        "solution": _s(getattr(card, "solution", "")),
        "case_type_test": _s(getattr(card, "case_type_test", "")),
        "test_type": _s(getattr(card, "test_type", "")),
        "preconditions": _s(getattr(card, "preconditions", "")),
        "steps": _json_text(getattr(card, "steps", None)),
        "remark": _s(getattr(card, "remark", "")),
        "baseline": _s(getattr(card, "baseline", "")),
        "version": _s(getattr(card, "version", "")),
        "related_defects": _json_text(getattr(card, "related_defects", None)),
        "execution_result": execution_result,
        "source_type": _s(getattr(card, "source_type", "")),
        "source_id": _s(getattr(card, "source_id", "")),
    }
    search_text = _join_search_text([
        _s(getattr(card, "title", "")),
        card_type,
        _s(getattr(card, "priority", "")),
        f"assignee:{assignee_display}" if assignee_display else "",
        *fields.values(),
    ])
    meta = {
        "status": card_type,
        "priority": _s(getattr(card, "priority", "")),
        "assignee_id": getattr(card, "assignee_id", None),
        "assignee_display": assignee_display,
    }
    ch = content_hash_for_doc("card", int(card.id), search_text, meta)
    doc = {
        "record_id": str(int(card.id)),
        "entity_type": "card",
        "project_id": int(card.project_id),
        "plan_id": int(card.plan_id) if getattr(card, "plan_id", None) is not None else None,
        "card_id": int(card.id),
        "assignee_id": int(card.assignee_id) if getattr(card, "assignee_id", None) is not None else None,
        "assignee_display": assignee_display or None,
        "status": card_type or None,
        "priority": _s(getattr(card, "priority", "")) or None,
        "title": _s(getattr(card, "title", "")),
        "search_text": search_text,
        "fields": fields,
        "content_hash": ch,
        "updated_at": int(card.updated_at.timestamp() * 1000) if getattr(card, "updated_at", None) else None,
    }
    return f"card:{card.id}", doc, search_text


def build_plan_es_doc(plan) -> Tuple[str, Dict[str, Any], str]:
    assignee_display = resolve_assignee_display(getattr(plan, "assignee_id", None))
    fields = {
        "name": _s(getattr(plan, "name", "")),
        "description": _s(getattr(plan, "description", "")),
        "start_date": _s(getattr(plan, "start_date", "")),
        "end_date": _s(getattr(plan, "end_date", "")),
        "progress": _s(getattr(plan, "progress", "")),
        "parent_id": _s(getattr(plan, "parent_id", "")),
        "is_default": _s(getattr(plan, "is_default", "")),
        "is_pinned": _s(getattr(plan, "is_pinned", "")),
    }
    status_val = _s(getattr(plan, "status", ""))
    search_text = _join_search_text([
        fields["name"],
        fields["description"],
        status_val,
        _s(getattr(plan, "priority", "")),
        fields["start_date"],
        fields["end_date"],
        f"assignee:{assignee_display}" if assignee_display else "",
    ])
    meta = {
        "status": status_val,
        "priority": _s(getattr(plan, "priority", "")),
        "assignee_id": getattr(plan, "assignee_id", None),
        "assignee_display": assignee_display,
    }
    ch = content_hash_for_doc("plan", int(plan.id), search_text, meta)
    doc = {
        "record_id": str(int(plan.id)),
        "entity_type": "plan",
        "project_id": int(plan.project_id),
        "plan_id": int(plan.id),
        "card_id": None,
        "assignee_id": int(plan.assignee_id) if getattr(plan, "assignee_id", None) is not None else None,
        "assignee_display": assignee_display or None,
        "status": status_val or None,
        "priority": _s(getattr(plan, "priority", "")) or None,
        "title": fields["name"],
        "search_text": search_text,
        "fields": fields,
        "content_hash": ch,
        "updated_at": int(plan.updated_at.timestamp() * 1000) if getattr(plan, "updated_at", None) else None,
    }
    return f"plan:{plan.id}", doc, search_text


class WorkItemIndexer:
    def __init__(
        self,
        store: ESWorkItemStore,
        embed_client: EmbeddingClient,
        *,
        batch_size: int = 16,
        flush_ms: int = 500,
        async_mode: bool = True,
    ):
        self.store = store
        self.embed_client = embed_client
        self.async_mode = async_mode
        self._hash_cache: Dict[str, str] = {}
        self._queue = EmbedBatchQueue(
            batch_size=batch_size,
            flush_ms=flush_ms,
            embed_fn=self.embed_client.embed_batch,
            upsert_fn=self.store.bulk_upsert,
        )

    def _should_skip(self, doc_id: str, content_hash: str) -> bool:
        prev = self._hash_cache.get(doc_id)
        if prev == content_hash:
            return True
        self._hash_cache[doc_id] = content_hash
        return False

    def index_entity(self, entity_type: str, record_id: int, *, sync: bool = False) -> bool:
        try:
            from app import BadCase, Bug, Card, Plan, TestCase
        except Exception as e:
            print(f"[GREP-INDEX] import ORM 失败: {e}", flush=True)
            return False
        et = (entity_type or "").strip().lower()
        if et == "test_case":
            et = "testcase"
        if et == "bug":
            row = Bug.query.get(int(record_id))
            if not row:
                self.store.delete("bug", int(record_id))
                return False
            doc_id, doc, search_text = build_bug_es_doc(row)
        elif et == "badcase":
            row = BadCase.query.get(int(record_id))
            if not row:
                self.store.delete("badcase", int(record_id))
                return False
            doc_id, doc, search_text = build_badcase_es_doc(row)
        elif et == "testcase":
            row = TestCase.query.get(int(record_id))
            if not row:
                self.store.delete("testcase", int(record_id))
                return False
            doc_id, doc, search_text = build_testcase_es_doc(row)
        elif et == "card":
            row = Card.query.get(int(record_id))
            if not row:
                self.store.delete("card", int(record_id))
                return False
            doc_id, doc, search_text = build_card_es_doc(row)
        elif et == "plan":
            row = Plan.query.get(int(record_id))
            if not row:
                self.store.delete("plan", int(record_id))
                return False
            doc_id, doc, search_text = build_plan_es_doc(row)
        else:
            return False
        if self._should_skip(doc_id, doc["content_hash"]):
            return True
        if sync or not self.async_mode:
            return self._index_sync(doc_id, doc, search_text)
        self._queue.enqueue(
            _PendingEmbed(
                doc_id=doc_id,
                search_text=search_text,
                doc_body=doc,
                content_hash=doc["content_hash"],
            )
        )
        self._queue.maybe_flush_idle()
        return True

    def _index_sync(self, doc_id: str, doc: Dict[str, Any], search_text: str) -> bool:
        try:
            vec = self.embed_client.embed(search_text)
            if not vec:
                return False
            body = dict(doc)
            body["embedding"] = vec
            body["_id"] = doc_id
            self.store.bulk_upsert([body], len(vec))
            return True
        except Exception as e:
            print(f"[GREP-INDEX] sync index 失败 {doc_id}: {e}", flush=True)
            return False

    def flush(self) -> int:
        return self._queue.flush()

    def delete_entity(self, entity_type: str, record_id: int) -> None:
        et = (entity_type or "").strip().lower()
        if et == "test_case":
            et = "testcase"
        self.store.delete(et, int(record_id))
        self._hash_cache.pop(f"{et}:{record_id}", None)


_indexer_singleton: Optional[WorkItemIndexer] = None
_indexer_lock = threading.Lock()


def get_work_item_indexer(cfg=None) -> Optional[WorkItemIndexer]:
    global _indexer_singleton
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return None
    if not getattr(cfg, "GREP_VECTOR_ENABLED", False):
        return None
    with _indexer_lock:
        if _indexer_singleton is None:
            try:
                _indexer_singleton = WorkItemIndexer(
                    build_work_item_store_from_config(cfg),
                    build_embedding_client_from_config(cfg),
                    batch_size=int(getattr(cfg, "GREP_EMBED_BATCH_SIZE", 16)),
                    flush_ms=int(getattr(cfg, "GREP_EMBED_BATCH_FLUSH_MS", 500)),
                    async_mode=bool(getattr(cfg, "GREP_INDEX_ASYNC", True)),
                )
            except Exception as e:
                print(f"[GREP-INDEX] indexer 初始化失败: {e}", flush=True)
                return None
        return _indexer_singleton


def schedule_work_item_index(entity_type: str, record_id: int, *, sync: bool = False) -> None:
    try:
        from config import Config

        if not getattr(Config, "GREP_VECTOR_ENABLED", False):
            return
        indexer = get_work_item_indexer(Config)
        if not indexer:
            return
        do_sync = sync or not getattr(Config, "GREP_INDEX_ASYNC", True)

        def _run():
            try:
                from app import app

                with app.app_context():
                    indexer.index_entity(entity_type, int(record_id), sync=do_sync)
            except Exception as ex:
                print(f"[GREP-INDEX] 后台索引失败 {entity_type}:{record_id}: {ex}", flush=True)

        if do_sync:
            _run()
        else:
            threading.Thread(target=_run, daemon=True).start()
    except Exception as e:
        print(f"[GREP-INDEX] schedule 失败: {e}", flush=True)


def schedule_work_item_delete(entity_type: str, record_id: int) -> None:
    try:
        from config import Config

        if not getattr(Config, "GREP_VECTOR_ENABLED", False):
            return

        def _run():
            try:
                from app import app

                with app.app_context():
                    indexer = get_work_item_indexer(Config)
                    if indexer:
                        indexer.delete_entity(entity_type, int(record_id))
            except Exception as ex:
                print(f"[GREP-INDEX] 删除索引失败 {entity_type}:{record_id}: {ex}", flush=True)

        if getattr(Config, "GREP_INDEX_ASYNC", True):
            threading.Thread(target=_run, daemon=True).start()
        else:
            _run()
    except Exception as e:
        print(f"[GREP-INDEX] schedule delete 失败: {e}", flush=True)
