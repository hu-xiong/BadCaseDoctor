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
from agents.tools.grep_es_rerank import semantic_text_for_grep_embed
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
    """仅 target=plan 专用检索等少数路径；常规定位请用 _entity_types_for_es_recall。"""
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


def _entity_types_for_es_recall(raw_target: str) -> List[str]:
    """
    ES 召回不按 grep target 收窄 entity_type，避免 Agent 误判 target=card 等导致 0 条。
    raw_target=plan 时由 grep_tool 走 plan 专用分支，不经过此处。
    """
    t = (raw_target or "all").strip().lower()
    if t == "plan":
        return ["plan"]
    return ["bug", "badcase", "testcase", "card", "plan"]


def _infer_business_scenario(title: str, keywords: Optional[str]) -> str:
    t = (title or "").strip()
    if not t:
        return "未知场景"
    if keywords and keywords in t:
        return f"与「{keywords}」相关的业务场景"
    return t[:40] + ("…" if len(t) > 40 else "")


def _grep_full_vector_min_chars(cfg) -> int:
    try:
        n = int(
            getattr(
                cfg,
                "GREP_QUERY_FULL_VECTOR_MIN_CHARS",
                80,
            )
        )
    except (TypeError, ValueError):
        n = 80
    return max(1, n)


def _grep_skip_remote_embed_min_chars(cfg) -> int:
    """auto 模式下低于该字数不调远端 embedding，仅 ES BM25（省 300ms～1.5s）。"""
    try:
        n = int(getattr(cfg, "GREP_QUERY_EMBED_MIN_CHARS", 8))
    except (TypeError, ValueError):
        n = 8
    return max(1, n)


def _grep_bm25_title_only_max_chars(cfg) -> int:
    try:
        n = int(getattr(cfg, "GREP_ES_BM25_TITLE_ONLY_MAX_CHARS", 64))
    except (TypeError, ValueError):
        n = 64
    return max(8, n)


def resolve_grep_es_search_strategy(
    cfg,
    qtext: Optional[str],
    assignee: Optional[str],
) -> Tuple[bool, Optional[str], bool, str]:
    """
    决定 ES 检索形态（auto 默认按字数）：
    - 字数 < GREP_QUERY_EMBED_MIN_CHARS（默认 8）：**不调 embedding**，仅 BM25（极短关键词）
    - 已调 embedding 且字数 < GREP_QUERY_FULL_VECTOR_MIN_CHARS：KNN + BM25 混合
    - 字数 >= FULL 阈值：仅 KNN 全语义

    返回 (need_vector, es_bm25_query_text, bm25_title_only, mode_label)。
    """
    mode = str(getattr(cfg, "GREP_QUERY_EMBED_MODE", "auto") or "auto").strip().lower()
    q = (qtext or "").strip()
    has_q = bool(q) and q != "*"
    full_threshold = _grep_full_vector_min_chars(cfg)
    skip_embed_below = _grep_skip_remote_embed_min_chars(cfg)
    title_only_max = _grep_bm25_title_only_max_chars(cfg)

    if mode == "never":
        return False, q if has_q else None, False, "bm25_only"

    if not has_q:
        if assignee and str(assignee).strip():
            return True, None, False, "vector_only"
        return False, None, False, "filter_only"

    if mode == "always":
        if len(q) >= full_threshold:
            return True, None, False, "vector_only"
        return True, q, False, "hybrid"

    # auto：短关键词不走远端 embedding（与历史 90ms 路径一致）
    if len(q) < skip_embed_below:
        title_only = len(q) <= title_only_max
        return False, q, title_only, "bm25_only"

    if len(q) < full_threshold:
        return True, q, False, "hybrid"
    return True, None, False, "vector_only"


def _should_query_embed(cfg, qtext: Optional[str], assignee: Optional[str]) -> bool:
    need_vector, _, _, _ = resolve_grep_es_search_strategy(cfg, qtext, assignee)
    return need_vector


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


def _log_es_recall_diagnosis(
    *,
    hits: List[Dict[str, Any]],
    bug_list: List[Dict[str, Any]],
    badcase_list: List[Dict[str, Any]],
    search_mode: str,
    keywords: Optional[str],
    es_bm25_qtext: Optional[str],
    need_vector: bool,
    assignee: Optional[str],
    status: Optional[str],
    plan_id: Optional[int],
) -> None:
    """区分「ES/向量 0 召回」与后续 rerank 过滤（rerank 在 grep_tool 再打 PIPELINE 日志）。"""
    in_n = len(hits)
    out_bug = len(bug_list or [])
    out_bc = len(badcase_list or [])
    if in_n == 0:
        print(
            f"[GREP-ES-RECALL] 诊断: ES/向量 召回 0 条（未到 rerank） | "
            f"mode={search_mode} plan_id={plan_id} "
            f"keywords={(keywords or '')[:120]!r} bm25_q={(es_bm25_qtext or '')[:80]!r} "
            f"vector={'yes' if need_vector else 'no'} assignee={assignee!r} status={status!r}",
            flush=True,
        )
        return
    print(
        f"[GREP-ES-RECALL] 诊断: ES 召回 {in_n} 条 → 列表 bug={out_bug} badcase={out_bc} | "
        f"mode={search_mode} vector={'yes' if need_vector else 'no'}",
        flush=True,
    )
    for i, h in enumerate(hits[:12]):
        print(
            f"[GREP-ES-RECALL] [{i}] {h.get('entity_type')}:{h.get('record_id')} "
            f"es_score={h.get('score')} title={(str(h.get('title') or '')[:60])!r}",
            flush=True,
        )


def _pre_rerank_min_score(cfg, *, need_vector: bool, search_mode: str) -> float:
    """向量召回后在 rerank 前按 ES score 过滤；BM25-only / filter_only 不启用。"""
    mode = (search_mode or "").strip().lower()
    if not need_vector or mode in ("bm25_only", "filter_only"):
        return 0.0
    try:
        return max(0.0, float(getattr(cfg, "GREP_PRE_RERANK_MIN_SCORE", 0.90)))
    except (TypeError, ValueError):
        return 0.90


def _filter_es_hits_pre_rerank(
    hits: List[Dict[str, Any]], min_score: float
) -> Tuple[List[Dict[str, Any]], int]:
    if min_score <= 0 or not hits:
        return hits, 0
    kept: List[Dict[str, Any]] = []
    dropped = 0
    for h in hits:
        try:
            s = float(h.get("score") or 0.0)
        except (TypeError, ValueError):
            s = 0.0
        if s >= min_score:
            kept.append(h)
        else:
            dropped += 1
    if dropped:
        print(
            f"[GREP-ES] pre_rerank_score_filter min={min_score} "
            f"raw={len(hits)} kept={len(kept)} dropped={dropped}",
            flush=True,
        )
    return kept, dropped


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
) -> str:
    rt = (raw_target or "all").strip().lower()
    # ES 召回与 grep target 解耦：缓存键不按 bug/card 等 target 分裂
    t_key = "plan" if rt == "plan" else "es_all"
    payload = {
        "p": str(project_id),
        "k": (keywords or "").strip(),
        "a": (assignee or "").strip(),
        "s": (status or "").strip(),
        "pl": str(plan_id or ""),
        "t": t_key,
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

    entity_types = _entity_types_for_es_recall(raw_target)
    meta["grep_target_nav"] = (raw_target or "all").strip().lower()
    meta["es_entity_types"] = list(entity_types)
    if raw_target not in ("plan",) and not entity_types:
        meta["skipped"] = "unsupported_target"
        return None, None, meta

    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return None, None, meta

    emb_backend = str(getattr(cfg, "GREP_EMBEDDING_BACKEND", "dashscope") or "dashscope").strip()
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

    qtext_raw = (keywords or "").strip() or None
    qtext_semantic = semantic_text_for_grep_embed(qtext_raw) or qtext_raw
    need_vector, es_bm25_qtext, bm25_title_only, search_mode = resolve_grep_es_search_strategy(
        cfg, qtext_semantic, assignee
    )
    meta["grep_search_mode"] = search_mode
    meta["query_embed"] = "yes" if need_vector else "bm25_only"
    meta["embed_semantic_len"] = len(qtext_semantic or "")
    query_embedding = None
    if need_vector:
        try:
            embed_client = build_embedding_client_from_config(cfg)
            semantic = qtext_semantic or str(assignee).strip()
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
        meta["bm25_title_only"] = bm25_title_only
        try:
            es_timeout = float(getattr(cfg, "GREP_ES_SEARCH_TIMEOUT_S", 10))
        except (TypeError, ValueError):
            es_timeout = 3.0
        hits = store.hybrid_search(
            project_id=pid,
            query_text=es_bm25_qtext,
            query_embedding=query_embedding,
            entity_types=entity_types,
            plan_id=plid,
            assignee_ids=assignee_ids,
            assignee_display=assignee_display,
            status=status,
            top_k=int(getattr(cfg, "GREP_VECTOR_TOP_K", 8)),
            alias_checked=True,
            bm25_title_only=bm25_title_only,
            request_timeout_s=es_timeout,
        )
        _mark("es_hybrid_search")
        _pr_min = _pre_rerank_min_score(cfg, need_vector=need_vector, search_mode=search_mode)
        if _pr_min > 0 and hits:
            hits, _pr_drop = _filter_es_hits_pre_rerank(hits, _pr_min)
            meta["pre_rerank_min_score"] = _pr_min
            meta["pre_rerank_dropped"] = _pr_drop
        es_ran = True
        meta["es_ran"] = True
    except Exception as e:
        print(f"[GREP-HYBRID] ES 检索失败，回落 SQL: {e}", flush=True)
        meta["es_ran"] = False
        meta["es_error"] = str(e)[:240]
        meta["es_fallback"] = "sql"
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
        "testcase_list": testcase_list,
        "card_list": card_list,
        "plan_list": plan_list,
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
    _log_es_recall_diagnosis(
        hits=hits,
        bug_list=bug_list,
        badcase_list=badcase_list,
        search_mode=search_mode,
        keywords=keywords,
        es_bm25_qtext=es_bm25_qtext,
        need_vector=need_vector,
        assignee=assignee,
        status=status,
        plan_id=plid,
    )

    # ES 已跑则返回各类列表（可为 []）；不再按 grep target 丢弃 bug/badcase 命中
    out_bug = bug_list if meta.get("es_ran") else None
    out_bc = badcase_list if meta.get("es_ran") else None
    if cache_ttl > 0 and meta.get("es_ran"):
        if len(_HYBRID_RESULT_CACHE) >= _HYBRID_RESULT_CACHE_MAX:
            _HYBRID_RESULT_CACHE.clear()
        _HYBRID_RESULT_CACHE[cache_key] = (
            time.monotonic() + cache_ttl,
            (out_bug, out_bc, dict(meta)),
        )
    return out_bug, out_bc, meta
