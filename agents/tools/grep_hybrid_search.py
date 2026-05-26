"""Grep ES 混合检索：ES 召回 + ORM hydrate 为 grep_tool 列表格式。"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

# (model, semantic_text) -> (vector, monotonic expiry)
_QUERY_EMBED_CACHE: Dict[Tuple[str, str], Tuple[List[float], float]] = {}
_QUERY_EMBED_CACHE_MAX = 128
_QUERY_EMBED_TTL_S = 300.0

# project+keywords+target+plan… -> (expiry_mono, bug_list, badcase_list, meta)
_HYBRID_RESULT_CACHE: Dict[str, Tuple[float, Any]] = {}
_HYBRID_RESULT_CACHE_MAX = 64

from agents.tools.grep_assignee import resolve_assignee_user_ids
from memory.grep_es_config import build_embedding_client_from_config
from memory.es_work_item_store import build_work_item_store_from_config


def _grep_vector_enabled(cfg=None) -> bool:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return False
    return bool(getattr(cfg, "GREP_VECTOR_ENABLED", False))


def _entity_types_for_target(raw_target: str) -> Optional[List[str]]:
    """ES work_item 索引覆盖 Bug/BadCase 源表；target=card 时仍走 ES type 混合检索。"""
    t = (raw_target or "all").strip().lower()
    if t == "bug":
        return ["bug"]
    if t == "badcase":
        return ["badcase"]
    if t in ("testcase", "test_case"):
        return ["testcase"]
    if t == "card":
        return ["card"]
    if t == "plan":
        return ["plan"]
    if t == "all":
        return ["bug", "badcase", "testcase", "card", "plan"]
    return None


def _infer_business_scenario(title: str, keywords: Optional[str]) -> str:
    t = (title or "").strip()
    if not t:
        return "未知场景"
    if keywords and keywords in t:
        return f"与「{keywords}」相关的业务场景"
    return t[:40] + ("…" if len(t) > 40 else "")


def _should_query_embed(cfg, qtext: Optional[str], assignee: Optional[str], record_id: Optional[int]) -> bool:
    """
    是否调用远端 embedding。auto 下短关键词只走 ES BM25（省 300~800ms）。
    """
    mode = str(getattr(cfg, "GREP_QUERY_EMBED_MODE", "auto") or "auto").strip().lower()
    if mode == "never":
        return False
    if mode == "always":
        return True
    q = (qtext or "").strip()
    if q and q not in ("*",):
        try:
            min_len = int(getattr(cfg, "GREP_QUERY_EMBED_MIN_CHARS", 80))
        except (TypeError, ValueError):
            min_len = 80
        return len(q) >= min_len
    if assignee and str(assignee).strip() and not q:
        return True
    if record_id is not None:
        return False
    return False


def _cached_query_embedding(embed_client, model: str, semantic: str) -> List[float]:
    key = (str(model or ""), (semantic or "").strip())
    if not key[1]:
        return embed_client.embed(semantic)
    now = time.monotonic()
    hit = _QUERY_EMBED_CACHE.get(key)
    if hit is not None and hit[1] > now:
        return hit[0]
    vec = embed_client.embed(semantic)
    if len(_QUERY_EMBED_CACHE) >= _QUERY_EMBED_CACHE_MAX:
        _QUERY_EMBED_CACHE.clear()
    _QUERY_EMBED_CACHE[key] = (vec, now + _QUERY_EMBED_TTL_S)
    return vec


def _extract_keywords(title: str) -> List[str]:
    t = (title or "").strip()
    return [t[:20]] if t else []


def _keyword_tokens(keywords: Optional[str]) -> List[str]:
    raw = (keywords or "").strip()
    if not raw or raw == "*":
        return []
    parts: List[str] = []
    for chunk in raw.replace("，", " ").replace(",", " ").split():
        t = chunk.strip()
        if len(t) >= 1:
            parts.append(t)
    return parts


def _title_covers_keywords(title: str, keywords: Optional[str]) -> bool:
    """标题是否覆盖 keywords 中每个 token（用于跳过远端 rerank）。"""
    tokens = _keyword_tokens(keywords)
    if not tokens:
        return False
    hay = (title or "").strip().lower()
    if not hay:
        return False
    return all(t.lower() in hay for t in tokens)


def _grep_skip_alias_exists(cfg=None) -> bool:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return True
    return bool(getattr(cfg, "GREP_ES_SKIP_ALIAS_EXISTS", True))


def _grep_hydrate_from_es_source(cfg=None) -> bool:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return True
    return bool(getattr(cfg, "GREP_ES_HYDRATE_FROM_SOURCE", True))


def _coerce_int_id(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _hit_to_bug_dict_from_es(hit: Dict[str, Any], keywords: Optional[str]) -> Dict[str, Any]:
    title = str(hit.get("title") or "").strip()
    rid = _coerce_int_id(hit.get("record_id"))
    return {
        "id": rid,
        "title": title,
        "status": str(hit.get("status") or "").strip() or "new",
        "severity": hit.get("severity"),
        "priority": hit.get("priority") or "medium",
        "assignee_id": hit.get("assignee_id"),
        "plan_id": _coerce_int_id(hit.get("plan_id")),
        "card_id": _coerce_int_id(hit.get("card_id")),
        "created_at": None,
        "business_scenario": _infer_business_scenario(title, keywords),
        "extracted_keywords": _extract_keywords(title),
        "keyword_match": _title_covers_keywords(title, keywords),
        "_search_backend": "es_hybrid",
        "_es_score": hit.get("score"),
        "fields": hit.get("fields") if isinstance(hit.get("fields"), dict) else None,
    }


def _hit_to_badcase_dict_from_es(hit: Dict[str, Any], keywords: Optional[str]) -> Dict[str, Any]:
    title = str(hit.get("title") or "").strip()
    rid = _coerce_int_id(hit.get("record_id"))
    asn = str(hit.get("assignee_display") or hit.get("assignee") or "").strip() or None
    return {
        "id": rid,
        "title": title,
        "status": str(hit.get("status") or "").strip() or "new",
        "priority": hit.get("priority") or "p3",
        "assignee": asn,
        "plan_id": _coerce_int_id(hit.get("plan_id")),
        "card_id": _coerce_int_id(hit.get("card_id")),
        "created_at": None,
        "business_scenario": _infer_business_scenario(title, keywords),
        "extracted_keywords": _extract_keywords(title),
        "keyword_match": _title_covers_keywords(title, keywords),
        "_search_backend": "es_hybrid",
        "_es_score": hit.get("score"),
        "fields": hit.get("fields") if isinstance(hit.get("fields"), dict) else None,
    }


def _hit_to_testcase_dict_from_es(hit: Dict[str, Any], keywords: Optional[str]) -> Dict[str, Any]:
    title = str(hit.get("title") or "").strip()
    rid = _coerce_int_id(hit.get("record_id"))
    return {
        "id": rid,
        "title": title,
        "status": str(hit.get("status") or "").strip() or "draft",
        "priority": hit.get("priority") or "P3",
        "assignee_id": hit.get("assignee_id"),
        "plan_id": _coerce_int_id(hit.get("plan_id")),
        "card_id": _coerce_int_id(hit.get("card_id")),
        "created_at": None,
        "business_scenario": _infer_business_scenario(title, keywords),
        "extracted_keywords": _extract_keywords(title),
        "keyword_match": _title_covers_keywords(title, keywords),
        "_search_backend": "es_hybrid",
        "_es_score": hit.get("score"),
        "fields": hit.get("fields") if isinstance(hit.get("fields"), dict) else None,
    }


def _hit_to_card_dict_from_es(hit: Dict[str, Any], keywords: Optional[str]) -> Dict[str, Any]:
    title = str(hit.get("title") or "").strip()
    rid = _coerce_int_id(hit.get("record_id"))
    fields = hit.get("fields") if isinstance(hit.get("fields"), dict) else {}
    return {
        "id": rid,
        "title": title,
        "description": str(fields.get("description") or "")[:800],
        "plan_id": _coerce_int_id(hit.get("plan_id")),
        "source_type": fields.get("source_type"),
        "source_id": _coerce_int_id(fields.get("source_id")),
        "card_id": _coerce_int_id(hit.get("card_id")) or rid,
        "created_at": None,
        "business_scenario": _infer_business_scenario(title, keywords),
        "extracted_keywords": _extract_keywords(title),
        "keyword_match": _title_covers_keywords(title, keywords),
        "_search_backend": "es_hybrid",
        "_es_score": hit.get("score"),
        "fields": fields,
    }


def _hit_to_plan_dict_from_es(hit: Dict[str, Any], keywords: Optional[str]) -> Dict[str, Any]:
    title = str(hit.get("title") or "").strip()
    rid = _coerce_int_id(hit.get("record_id"))
    fields = hit.get("fields") if isinstance(hit.get("fields"), dict) else {}
    return {
        "id": rid,
        "name": title,
        "title": title,
        "description": str(fields.get("description") or "")[:800],
        "status": str(hit.get("status") or "").strip(),
        "priority": hit.get("priority"),
        "project_id": hit.get("project_id"),
        "parent_id": _coerce_int_id(fields.get("parent_id")),
        "plan_id": rid,
        "is_default": str(fields.get("is_default") or "").lower() == "true",
        "business_scenario": _infer_business_scenario(title, keywords),
        "extracted_keywords": _extract_keywords(title),
        "keyword_match": _title_covers_keywords(title, keywords),
        "_search_backend": "es_hybrid",
        "_es_score": hit.get("score"),
        "fields": fields,
    }


def _lists_from_es_hits(
    hits: List[Dict[str, Any]],
    *,
    entity_types: Optional[List[str]],
    keywords: Optional[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    bug_list: List[Dict[str, Any]] = []
    badcase_list: List[Dict[str, Any]] = []
    testcase_list: List[Dict[str, Any]] = []
    card_list: List[Dict[str, Any]] = []
    plan_list: List[Dict[str, Any]] = []
    for h in hits:
        et = str(h.get("entity_type") or "").strip().lower()
        rid = _coerce_int_id(h.get("record_id"))
        if rid is None:
            continue
        if et == "bug" and entity_types and "bug" in entity_types:
            row = _hit_to_bug_dict_from_es(h, keywords)
            if row.get("title"):
                bug_list.append(row)
        elif et == "badcase" and entity_types and "badcase" in entity_types:
            row = _hit_to_badcase_dict_from_es(h, keywords)
            if row.get("title"):
                badcase_list.append(row)
        elif et == "testcase" and entity_types and "testcase" in entity_types:
            row = _hit_to_testcase_dict_from_es(h, keywords)
            if row.get("title"):
                testcase_list.append(row)
        elif et == "card" and entity_types and "card" in entity_types:
            row = _hit_to_card_dict_from_es(h, keywords)
            if row.get("title"):
                card_list.append(row)
        elif et == "plan" and entity_types and "plan" in entity_types:
            row = _hit_to_plan_dict_from_es(h, keywords)
            if row.get("title"):
                plan_list.append(row)
    return bug_list, badcase_list, testcase_list, card_list, plan_list


def _hit_to_bug_dict(row, keywords: Optional[str]) -> Dict[str, Any]:
    title = getattr(row, "title", "") or ""
    return {
        "id": row.id,
        "title": title,
        "status": row.status.value if hasattr(row.status, "value") else row.status,
        "severity": getattr(row, "severity", None),
        "priority": getattr(row, "priority", "medium"),
        "assignee_id": getattr(row, "assignee_id", None),
        "plan_id": getattr(row, "plan_id", None),
        "card_id": getattr(row, "card_id", None),
        "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
        "business_scenario": _infer_business_scenario(title, keywords),
        "extracted_keywords": _extract_keywords(title),
        "keyword_match": _title_covers_keywords(title, keywords),
        "_search_backend": "es_hybrid",
    }


def _hit_to_badcase_dict(row, keywords: Optional[str]) -> Dict[str, Any]:
    title = getattr(row, "title", "") or ""
    return {
        "id": row.id,
        "title": title,
        "status": row.status.value if hasattr(row.status, "value") else row.status,
        "priority": getattr(row, "priority", "p3"),
        "assignee": getattr(row, "assignee", None),
        "plan_id": getattr(row, "plan_id", None),
        "card_id": getattr(row, "card_id", None),
        "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
        "business_scenario": _infer_business_scenario(title, keywords),
        "extracted_keywords": _extract_keywords(title),
        "keyword_match": _title_covers_keywords(title, keywords),
        "_search_backend": "es_hybrid",
    }


def _hybrid_cache_ttl_s(cfg) -> float:
    try:
        return float(getattr(cfg, "GREP_HYBRID_CACHE_TTL_S", 45))
    except (TypeError, ValueError):
        return 45.0


def _hybrid_cache_key(
    *,
    project_id: str,
    keywords: Optional[str],
    assignee: Optional[str],
    status: Optional[str],
    plan_id: Optional[str],
    raw_target: str,
    record_id: Optional[int],
) -> str:
    payload = {
        "p": str(project_id),
        "k": (keywords or "").strip(),
        "a": (assignee or "").strip(),
        "s": (status or "").strip(),
        "pl": str(plan_id or ""),
        "t": (raw_target or "all").strip().lower(),
        "r": record_id,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def hybrid_search_work_items(
    *,
    project_id: str,
    keywords: Optional[str],
    assignee: Optional[str],
    status: Optional[str],
    plan_id: Optional[str],
    raw_target: str,
    record_id: Optional[int] = None,
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[List[Dict[str, Any]]], Dict[str, Any]]:
    """
    返回 (bug_list|None, badcase_list|None, meta)。
    None 表示未走向量路径，调用方应回落 SQL。
    """
    meta: Dict[str, Any] = {"search_backend": "es_hybrid"}
    perf_ms: Dict[str, float] = {}
    meta["perf_ms"] = perf_ms
    t_wall0 = time.perf_counter()
    t_seg = t_wall0

    def _mark(name: str) -> None:
        nonlocal t_seg
        now = time.perf_counter()
        perf_ms[name] = round((now - t_seg) * 1000.0, 1)
        t_seg = now

    try:
        from config import Config as cfg
    except Exception:
        return None, None, meta

    cache_ttl = _hybrid_cache_ttl_s(cfg)
    cache_key = _hybrid_cache_key(
        project_id=project_id,
        keywords=keywords,
        assignee=assignee,
        status=status,
        plan_id=plan_id,
        raw_target=raw_target,
        record_id=record_id,
    )
    if cache_ttl > 0:
        hit = _HYBRID_RESULT_CACHE.get(cache_key)
        if hit is not None:
            exp, cached = hit
            if exp > time.monotonic():
                ob, obc, cmeta = cached
                cmeta = dict(cmeta)
                cmeta["cache_hit"] = True
                perf_ms["total"] = round((time.perf_counter() - t_wall0) * 1000.0, 1)
                cmeta["perf_ms"] = perf_ms
                print(
                    f"[GREP-HYBRID] cache_hit project={project_id} "
                    f"bug={len(ob or [])} badcase={len(obc or [])} ms={perf_ms['total']}",
                    flush=True,
                )
                return ob, obc, cmeta

    if not _grep_vector_enabled(cfg):
        meta["skipped"] = "vector_disabled"
        return None, None, meta

    entity_types = _entity_types_for_target(raw_target)
    if entity_types is None:
        meta["skipped"] = "unsupported_target"
        return None, None, meta

    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return None, None, meta

    emb_backend = str(getattr(cfg, "GREP_EMBEDDING_BACKEND", "qianfan") or "qianfan").strip()
    meta["embedding_backend"] = emb_backend
    meta["embedding_model"] = str(
        getattr(cfg, "GREP_EMBEDDING_MODEL", "") or getattr(cfg, "EMBEDDING_MODEL", "")
    ).strip()

    assignee_ids: Optional[List[int]] = None
    assignee_display: Optional[str] = None
    if assignee and str(assignee).strip():
        fuzzy = bool(getattr(cfg, "GREP_ASSIGNEE_FUZZY_PREFIX", True))
        resolved = resolve_assignee_user_ids(str(assignee).strip(), pid, fuzzy_prefix=fuzzy)
        meta["assignee_resolved"] = {
            "hint": resolved.hint,
            "user_ids": resolved.user_ids,
            "matched_users": resolved.matched_users,
        }
        if resolved.user_ids:
            assignee_ids = resolved.user_ids
        else:
            assignee_display = str(assignee).strip()
    _mark("assignee_resolve")

    plid: Optional[int] = None
    if plan_id is not None and str(plan_id).strip() != "":
        try:
            pi = int(plan_id)
            if pi != pid:
                plid = pi
        except (TypeError, ValueError):
            plid = None

    qtext = (keywords or "").strip() or None
    query_embedding = None
    need_vector = _should_query_embed(cfg, qtext, assignee, record_id)
    meta["query_embed"] = "yes" if need_vector else "bm25_only"
    if need_vector:
        try:
            embed_client = build_embedding_client_from_config(cfg)
            semantic = qtext or str(assignee).strip()
            model = str(
                getattr(cfg, "GREP_EMBEDDING_MODEL", "")
                or getattr(cfg, "EMBEDDING_MODEL", "")
                or ""
            )
            query_embedding = _cached_query_embedding(embed_client, model, semantic)
        except Exception as e:
            print(f"[GREP-HYBRID] query embed 失败(仅 BM25/filter): {e}", flush=True)
    _mark("query_embed")

    es_ran = False
    hits: List[Dict[str, Any]] = []
    try:
        store = build_work_item_store_from_config(cfg)
        alias = store.search_cfg.alias
        _mark("es_store_get")
        skip_alias = _grep_skip_alias_exists(cfg)
        meta["skip_alias_exists"] = skip_alias
        if not skip_alias and not store.alias_exists(alias):
            print(
                f"[GREP-HYBRID] 索引 {alias!r} 不存在，回落 SQL（可先运行 scripts/backfill_grep_index.py）",
                flush=True,
            )
            perf_ms["total"] = round((time.perf_counter() - t_wall0) * 1000.0, 1)
            return None, None, meta
        _mark("es_alias_exists")
        try:
            title_only_max = int(getattr(cfg, "GREP_ES_BM25_TITLE_ONLY_MAX_CHARS", 64))
        except (TypeError, ValueError):
            title_only_max = 64
        bm25_title_only = bool(
            qtext and not need_vector and len(qtext) <= max(8, title_only_max)
        )
        meta["bm25_title_only"] = bm25_title_only
        try:
            es_timeout = float(getattr(cfg, "GREP_ES_SEARCH_TIMEOUT_S", 3))
        except (TypeError, ValueError):
            es_timeout = 3.0
        hits = store.hybrid_search(
            project_id=pid,
            query_text=qtext,
            query_embedding=query_embedding,
            entity_types=entity_types,
            plan_id=plid,
            assignee_ids=assignee_ids,
            assignee_display=assignee_display,
            status=status,
            record_id=record_id,
            top_k=int(getattr(cfg, "GREP_VECTOR_TOP_K", 8)),
            alias_checked=True,
            bm25_title_only=bm25_title_only,
            request_timeout_s=es_timeout,
        )
        _mark("es_hybrid_search")
        es_ran = True
        meta["es_ran"] = True
    except Exception as e:
        print(f"[GREP-HYBRID] ES 检索失败，回落 SQL: {e}", flush=True)
        perf_ms["total"] = round((time.perf_counter() - t_wall0) * 1000.0, 1)
        return None, None, meta

    # ES 已执行时优先使用 ES 结果（含 0 条），不再回落 SQL
    if not es_ran:
        return None, None, meta

    if _grep_hydrate_from_es_source(cfg):
        bug_list, badcase_list, testcase_list, card_list, plan_list = _lists_from_es_hits(
            hits, entity_types=entity_types, keywords=keywords
        )
        meta["hydrate"] = "es_source"
        _mark("es_hydrate")
    else:
        from app import BadCase, Bug, db

        bug_ids: List[int] = []
        bc_ids: List[int] = []
        for h in hits:
            et = str(h.get("entity_type") or "")
            rid = _coerce_int_id(h.get("record_id"))
            if rid is None:
                continue
            if et == "bug":
                bug_ids.append(rid)
            elif et == "badcase":
                bc_ids.append(rid)

        bug_list = []
        badcase_list = []
        testcase_list = []
        card_list = []
        plan_list = []
        if bug_ids and entity_types and "bug" in entity_types:
            rows = db.session.query(Bug).filter(Bug.id.in_(bug_ids), Bug.project_id == pid).all()
            by_id = {int(r.id): r for r in rows}
            for bid in bug_ids:
                if bid in by_id:
                    bug_list.append(_hit_to_bug_dict(by_id[bid], keywords))
        if bc_ids and entity_types and "badcase" in entity_types:
            rows = db.session.query(BadCase).filter(
                BadCase.id.in_(bc_ids), BadCase.project_id == pid
            ).all()
            by_id = {int(r.id): r for r in rows}
            for bid in bc_ids:
                if bid in by_id:
                    badcase_list.append(_hit_to_badcase_dict(by_id[bid], keywords))
        meta["hydrate"] = "orm"
        _mark("orm_hydrate")
    perf_ms["total"] = round((time.perf_counter() - t_wall0) * 1000.0, 1)
    meta["hits_n"] = len(hits)
    meta["bug_n"] = len(bug_list)
    meta["badcase_n"] = len(badcase_list)
    meta["testcase_n"] = len(testcase_list)
    meta["card_n"] = len(card_list)
    meta["plan_n"] = len(plan_list)
    meta["extra_lists"] = {
        "testcase_list": testcase_list if "testcase" in entity_types else None,
        "card_list": card_list if "card" in entity_types else None,
        "plan_list": plan_list if "plan" in entity_types else None,
    }
    parts = " ".join(
        f"{k}={v}ms" for k, v in sorted(perf_ms.items(), key=lambda x: -x[1]) if k != "total"
    )
    print(
        f"[GREP-HYBRID] project={pid} hits={len(hits)} bug={len(bug_list)} "
        f"badcase={len(badcase_list)} testcase={len(testcase_list)} "
        f"card={len(card_list)} plan={len(plan_list)}",
        flush=True,
    )
    print(f"[GREP-HYBRID-PERF] total={perf_ms['total']}ms {parts}", flush=True)

    out_bug = bug_list if "bug" in entity_types else None
    out_bc = badcase_list if "badcase" in entity_types else None
    if cache_ttl > 0 and meta.get("es_ran"):
        if len(_HYBRID_RESULT_CACHE) >= _HYBRID_RESULT_CACHE_MAX:
            _HYBRID_RESULT_CACHE.clear()
        _HYBRID_RESULT_CACHE[cache_key] = (
            time.monotonic() + cache_ttl,
            (out_bug, out_bc, dict(meta)),
        )
    return out_bug, out_bc, meta
