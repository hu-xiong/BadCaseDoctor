"""Grep ES 命中后 Qwen rerank + 阈值过滤。"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from agents.tools.grep_assignee import resolve_assignee_display
from memory.qianfan_rerank_client import RerankHit
from memory.rerank_client import rerank_documents

_DOC_LOG_MAX_LEN = 320


def _grep_rerank_enabled(cfg=None) -> bool:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return False
    raw = str(getattr(cfg, "GREP_RERANK_ENABLED", "true") or "true").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return bool(getattr(cfg, "GREP_VECTOR_ENABLED", False))


def grep_user_query_text(
    *,
    raw_user_input: Optional[str] = None,
    user_input: Optional[str] = None,
    natural_query: Optional[str] = None,
    max_chars: int = 400,
) -> str:
    """Grep ES/embed 仅用用户对话原话；界面上下文走 ui_context 字段，不进 embedding。"""
    raw = (raw_user_input or "").strip()
    if raw and "[界面上下文]" not in raw:
        return raw[:max_chars]
    if raw:
        cleaned = _user_question_without_ui_context(raw, max_chars=max_chars)
        if cleaned:
            return cleaned
    for src in (user_input, natural_query):
        cleaned = _user_question_without_ui_context(src, max_chars=max_chars)
        if cleaned:
            return cleaned
    return ""


def semantic_text_for_grep_embed(
    text: Optional[str],
    *,
    max_chars: int = 400,
) -> str:
    """兼容旧调用：单参时仍剥离 [界面上下文]。"""
    return _user_question_without_ui_context(text, max_chars=max_chars)


def _user_question_without_ui_context(user_input: Optional[str], *, max_chars: int = 400) -> str:
    """从 user_input 去掉 [界面上下文] 元数据，只保留用户原话。"""
    raw = (user_input or "").strip()
    if not raw:
        return ""
    if "[界面上下文]" not in raw:
        return raw[:max_chars]
    lines: List[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("[界面上下文]"):
            continue
        if s.startswith("- target=") or s.startswith("- record_id=") or s.startswith("- plan_id="):
            continue
        if s.startswith("- card_id=") or s.startswith("- view="):
            continue
        if "authority" in s.lower() and "record_id" in s:
            continue
        lines.append(s)
    q = " ".join(lines).strip()
    if len(q) > max_chars:
        q = q[: max_chars - 3] + "..."
    return q


def _compose_rerank_query(
    *,
    user_input: Optional[str],
    keywords: Optional[str],
    assignee: Optional[str] = None,
    status: Optional[str] = None,
    max_ui_chars: int = 400,
) -> str:
    """Rerank 查询侧：仅用户检索问题（keywords），不拼界面上下文/负责人/状态筛选。"""
    del assignee, status
    kw = (keywords or "").strip()
    if kw and kw not in ("*",):
        return kw[:max_ui_chars]
    return _user_question_without_ui_context(user_input, max_chars=max_ui_chars)


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
    tokens = _keyword_tokens(keywords)
    if not tokens:
        return False
    hay = (title or "").strip().lower()
    if not hay:
        return False
    return all(t.lower() in hay for t in tokens)


def _local_sort_entries_by_keywords(
    entries: List[Tuple[str, Dict[str, Any], int]],
    keywords: Optional[str],
) -> List[Tuple[str, Dict[str, Any], int]]:
    """跳过远端 rerank 时，按标题 token 覆盖 + ES 分本地重排。"""
    tokens = _keyword_tokens(keywords)
    if not tokens or len(entries) <= 1:
        return entries

    def _key(item: Tuple[str, Dict[str, Any], int]) -> Tuple[int, float, int]:
        _et, row, idx = item
        title = str(row.get("title") or "")
        cov = sum(1 for t in tokens if t.lower() in title.lower())
        es = float(row.get("_es_score") or 0.0)
        return (cov, es, -idx)

    return sorted(entries, key=_key, reverse=True)


def _should_skip_rerank_api(
    entries: List[Tuple[str, Dict[str, Any], int]],
    *,
    keywords: Optional[str],
    cfg,
) -> Tuple[bool, str]:
    try:
        skip_le = int(getattr(cfg, "GREP_RERANK_SKIP_IF_LE", 8))
    except (TypeError, ValueError):
        skip_le = 8
    if len(entries) <= max(0, skip_le):
        return True, "skipped_small_set"

    if not bool(getattr(cfg, "GREP_RERANK_SKIP_IF_ES_CONFIDENT", True)):
        return False, ""

    if not entries:
        return False, ""
    _et0, top, _ = entries[0]
    if top.get("keyword_match") or _title_covers_keywords(str(top.get("title") or ""), keywords):
        return True, "skipped_es_confident"
    return False, ""


def _lists_from_sorted_entries(
    entries: List[Tuple[str, Dict[str, Any], int]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    bugs: List[Dict[str, Any]] = []
    bcs: List[Dict[str, Any]] = []
    for et, row, _ in entries:
        if et == "bug":
            bugs.append(row)
        elif et == "badcase":
            bcs.append(row)
    return bugs, bcs


def _grep_search_log_enabled(cfg=None) -> bool:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return True
    return bool(getattr(cfg, "GREP_SEARCH_LOG_ENABLED", True))


def _entry_key(entity_type: str, row: Dict[str, Any]) -> str:
    et = (entity_type or "").strip().lower()
    rid = row.get("id")
    return f"{et}:{rid}" if rid is not None else et


def _truncate_doc(text: str, max_len: int = _DOC_LOG_MAX_LEN) -> str:
    s = " ".join((text or "").split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _log_rerank_recall_docs(
    *,
    query: str,
    entries: List[Tuple[str, Dict[str, Any], int]],
    documents: List[str],
    min_score: float,
    model: str,
) -> None:
    print(
        f"[GREP-RERANK] recall query={query!r} model={model} min_score={min_score} n={len(entries)}",
        flush=True,
    )
    for i, ((et, row, _), doc) in enumerate(zip(entries, documents)):
        title = str(row.get("title") or "").strip() or "-"
        print(
            f"[GREP-RERANK] recall[{i}] {_entry_key(et, row)} title={title!r}",
            flush=True,
        )
        print(f"[GREP-RERANK] recall[{i}] document={_truncate_doc(doc)!r}", flush=True)


def _build_rerank_score_rows(
    entries: List[Tuple[str, Dict[str, Any], int]],
    documents: List[str],
    hits: List[RerankHit],
    *,
    min_score: float,
) -> List[Dict[str, Any]]:
    """按 rerank 分数降序生成全量打分明细（含被阈值过滤的候选）。"""
    rows: List[Dict[str, Any]] = []
    for h in hits:
        if h.index < 0 or h.index >= len(entries):
            continue
        et, row, _ = entries[h.index]
        score = round(float(h.score), 6)
        passed = score >= min_score
        rows.append(
            {
                "rank": 0,
                "entity_type": et,
                "id": row.get("id"),
                "key": _entry_key(et, row),
                "title": str(row.get("title") or "").strip(),
                "score": score,
                "min_score": min_score,
                "passed": passed,
                "verdict": "PASS" if passed else "FILTER",
                "document": _truncate_doc(documents[h.index]),
            }
        )
    rows.sort(key=lambda x: (-float(x["score"]), str(x["key"])))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    reranked_indexes = {h.index for h in hits}
    for i, (et, row, _) in enumerate(entries):
        if i in reranked_indexes:
            continue
        rows.append(
            {
                "rank": len(rows) + 1,
                "entity_type": et,
                "id": row.get("id"),
                "key": _entry_key(et, row),
                "title": str(row.get("title") or "").strip(),
                "score": None,
                "min_score": min_score,
                "passed": False,
                "verdict": "NOT_RERANKED",
                "document": _truncate_doc(documents[i]),
            }
        )
    return rows


def _log_rerank_diagnosis(
    *,
    entries: List[Tuple[str, Dict[str, Any], int]],
    hits: List[RerankHit],
    min_score: float,
    kept_bug: List[Dict[str, Any]],
    kept_bc: List[Dict[str, Any]],
    meta: Dict[str, Any],
) -> None:
    """始终打印：区分 rerank 阈值过滤 vs ES 本身无召回（rerank 仅在 in_n>0 时进入）。"""
    in_n = len(entries)
    out_n = len(kept_bug) + len(kept_bc)
    best_score = max((float(h.score) for h in hits), default=None) if hits else None
    rerank_status = meta.get("rerank") or "-"
    if in_n == 0:
        print("[GREP-RERANK] 诊断: 未进入 rerank（ES 召回列表为空）", flush=True)
        return
    if out_n > 0:
        print(
            f"[GREP-RERANK] 诊断: ES 送入 rerank {in_n} 条 → 通过 {out_n} 条 "
            f"(min_score>={min_score}, rerank={rerank_status})",
            flush=True,
        )
        return
    verdict = "rerank_filtered_all"
    if rerank_status == "fallback":
        verdict = "rerank_api_fail_kept_es_order"
    elif rerank_status in ("ok_fallback_floor", "ok_fallback_top1"):
        verdict = f"rerank_floor_rescue({rerank_status})"
    elif not hits:
        verdict = "rerank_api_no_hits"
    print(
        f"[GREP-RERANK] 诊断: ES 送入 rerank {in_n} 条 → 阈值后 0 条 | "
        f"verdict={verdict} min_score={min_score} best_rerank_score={best_score} "
        f"rerank={rerank_status}",
        flush=True,
    )
    if hits:
        for h in sorted(hits, key=lambda x: -float(x.score))[:8]:
            if h.index < 0 or h.index >= len(entries):
                continue
            et, row, _ = entries[h.index]
            passed = float(h.score) >= min_score
            print(
                f"[GREP-RERANK] 打分 {_entry_key(et, row)} score={float(h.score):.4f} "
                f"{'PASS' if passed else f'FILTER(<{min_score})'} "
                f"title={(str(row.get('title') or '')[:50])!r}",
                flush=True,
            )


def _log_rerank_score_rows(
    *,
    min_score: float,
    rows: List[Dict[str, Any]],
    kept_n: int,
) -> None:
    print(
        f"[GREP-RERANK] scored min_score={min_score} kept={kept_n} total={len(rows)}",
        flush=True,
    )
    for row in rows:
        score = row.get("score")
        score_s = f"{score:.6f}" if isinstance(score, (int, float)) else "-"
        verdict = row.get("verdict") or "-"
        if verdict == "FILTER" and isinstance(score, (int, float)):
            verdict = f"FILTER(<{min_score})"
        print(
            f"[GREP-RERANK] rank={row.get('rank')} "
            f"{row.get('key')} score={score_s} {verdict} "
            f"title={row.get('title') or '-'}",
            flush=True,
        )
        print(
            f"[GREP-RERANK] rank={row.get('rank')} document={row.get('document')!r}",
            flush=True,
        )


def _row_field_text(row: Dict[str, Any], key: str, *, from_fields: bool = True) -> str:
    if from_fields:
        fields = row.get("fields")
        if isinstance(fields, dict):
            v = fields.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
    v = row.get(key)
    if v is None:
        return ""
    return str(v).strip()


def _doc_kv(parts: List[str], label: str, val: Any) -> None:
    s = str(val or "").strip()
    if s:
        parts.append(f"{label}={s}")


def _bug_rerank_document(row: Dict[str, Any]) -> str:
    """候选侧：Bug 类型 + 索引 fields 拼成一段文本供 rerank。"""
    title = str(row.get("title") or "").strip()
    aid = row.get("assignee_id")
    asn = resolve_assignee_display(int(aid)) if aid is not None else ""
    if not asn:
        asn = str(row.get("assignee_display") or "").strip()
    parts: List[str] = ["类型=Bug"]
    _doc_kv(parts, "标题", title)
    _doc_kv(parts, "状态", _row_field_text(row, "status", from_fields=False) or row.get("status"))
    _doc_kv(parts, "优先级", _row_field_text(row, "priority", from_fields=False) or row.get("priority"))
    _doc_kv(parts, "严重程度", _row_field_text(row, "severity"))
    _doc_kv(parts, "缺陷类型", _row_field_text(row, "bug_type"))
    _doc_kv(parts, "负责人", asn)
    _doc_kv(parts, "环境", _row_field_text(row, "environment"))
    _doc_kv(parts, "浏览器", _row_field_text(row, "browser"))
    _doc_kv(parts, "系统", _row_field_text(row, "os"))
    _doc_kv(parts, "复现步骤", _row_field_text(row, "steps_to_reproduce"))
    _doc_kv(parts, "期望结果", _row_field_text(row, "expected_result"))
    _doc_kv(parts, "实际结果", _row_field_text(row, "actual_result"))
    return " ".join(parts)


def _badcase_rerank_document(row: Dict[str, Any]) -> str:
    title = str(row.get("title") or "").strip()
    asn = str(row.get("assignee") or row.get("assignee_display") or "").strip()
    parts: List[str] = ["类型=BadCase"]
    _doc_kv(parts, "标题", title)
    _doc_kv(parts, "状态", _row_field_text(row, "status", from_fields=False) or row.get("status"))
    _doc_kv(parts, "优先级", _row_field_text(row, "priority", from_fields=False) or row.get("priority"))
    _doc_kv(parts, "负责人", asn)
    _doc_kv(parts, "问题分类", _row_field_text(row, "case_category"))
    _doc_kv(parts, "基础问题", _row_field_text(row, "base_problem"))
    _doc_kv(parts, "复现步骤", _row_field_text(row, "reproduction_steps"))
    _doc_kv(parts, "结果", _row_field_text(row, "badcase_result"))
    _doc_kv(parts, "原因", _row_field_text(row, "problem_reason"))
    _doc_kv(parts, "方案", _row_field_text(row, "solution"))
    return " ".join(parts)


def _row_doc_text(row: Dict[str, Any], entity_type: str) -> str:
    et = (entity_type or "").strip().lower()
    if et == "bug":
        return _bug_rerank_document(row)
    if et == "badcase":
        return _badcase_rerank_document(row)
    title = str(row.get("title") or "").strip()
    return f"类型={entity_type} 标题={title}".strip()


def _filter_lists_by_hits(
    bug_list: List[Dict[str, Any]],
    badcase_list: List[Dict[str, Any]],
    entries: List[Tuple[str, Dict[str, Any], int]],
    hits: List[RerankHit],
    *,
    min_score: float,
    top_n: int = 0,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """按分数降序 → 阈值过滤 → 最多保留 top_n 条；返回 (bug_list, badcase_list, score_audit)。"""
    ranked: List[Tuple[float, str, Dict[str, Any]]] = []
    for h in hits:
        if h.score < min_score:
            continue
        if h.index < 0 or h.index >= len(entries):
            continue
        et, row, _ = entries[h.index]
        out = dict(row)
        out["_rerank_score"] = round(float(h.score), 6)
        ranked.append((float(h.score), et, out))

    ranked.sort(key=lambda x: -x[0])
    cap = int(top_n) if top_n and top_n > 0 else len(ranked)
    ranked = ranked[:cap]

    kept_bug: List[Dict[str, Any]] = []
    kept_bc: List[Dict[str, Any]] = []
    audit: List[Dict[str, Any]] = []
    for score, et, out in ranked:
        audit.append(
            {
                "entity_type": et,
                "id": out.get("id"),
                "score": out["_rerank_score"],
            }
        )
        if et == "bug":
            kept_bug.append(out)
        elif et == "badcase":
            kept_bc.append(out)

    return kept_bug, kept_bc, audit


def rerank_es_candidates_sync(
    *,
    bug_list: List[Dict[str, Any]],
    badcase_list: List[Dict[str, Any]],
    user_input: Optional[str] = None,
    keywords: Optional[str] = None,
    assignee: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    meta: Dict[str, Any] = {"rerank": "skipped"}
    try:
        from config import Config as cfg
    except Exception:
        return bug_list, badcase_list, meta

    if not _grep_rerank_enabled(cfg):
        meta["rerank"] = "disabled"
        return bug_list, badcase_list, meta

    entries: List[Tuple[str, Dict[str, Any], int]] = []
    for row in bug_list or []:
        entries.append(("bug", row, len(entries)))
    for row in badcase_list or []:
        entries.append(("badcase", row, len(entries)))

    if not entries:
        meta["rerank"] = "empty_input"
        return bug_list, badcase_list, meta

    skip, skip_reason = _should_skip_rerank_api(entries, keywords=keywords, cfg=cfg)
    if skip:
        sorted_entries = _local_sort_entries_by_keywords(entries, keywords)
        ob, obc = _lists_from_sorted_entries(sorted_entries)
        meta["rerank"] = skip_reason
        meta["in_n"] = len(entries)
        meta["out_n"] = len(ob) + len(obc)
        meta["local_sort"] = True
        print(
            f"[GREP-RERANK] 诊断: 跳过远端 rerank ({skip_reason})，保留 ES 原序 "
            f"in={len(entries)} out={meta['out_n']}",
            flush=True,
        )
        if _grep_search_log_enabled(cfg):
            print(
                f"[GREP-RERANK] skip api reason={skip_reason} n={len(entries)} "
                f"keywords={keywords!r}",
                flush=True,
            )
        return ob, obc, meta

    try:
        max_docs = int(getattr(cfg, "GREP_RERANK_MAX_DOCS", 12))
    except (TypeError, ValueError):
        max_docs = 12
    if max_docs > 0 and len(entries) > max_docs:
        entries = entries[:max_docs]
        bug_list = [row for et, row, _ in entries if et == "bug"]
        badcase_list = [row for et, row, _ in entries if et == "badcase"]

    try:
        q_cap = int(getattr(cfg, "GREP_RERANK_QUERY_MAX_CHARS", 400))
    except (TypeError, ValueError):
        q_cap = 400
    query = _compose_rerank_query(
        user_input=user_input,
        keywords=keywords,
        assignee=assignee,
        status=status,
        max_ui_chars=max(80, q_cap),
    )
    if not query:
        meta["rerank"] = "empty_query"
        return bug_list, badcase_list, meta

    documents = [_row_doc_text(row, et) for et, row, _ in entries]
    log_docs = _grep_search_log_enabled(cfg)
    backend = str(getattr(cfg, "GREP_RERANK_BACKEND", "dashscope") or "dashscope").strip().lower()
    default_model = "bce-reranker-base" if backend == "qianfan" else "qwen3-vl-rerank"
    model = str(getattr(cfg, "GREP_RERANK_MODEL", default_model) or default_model).strip()
    try:
        min_score = float(getattr(cfg, "GREP_RERANK_MIN_SCORE", 0.48))
    except (TypeError, ValueError):
        min_score = 0.48
    try:
        top_n = int(getattr(cfg, "GREP_RERANK_TOP_N", 5))
    except (TypeError, ValueError):
        top_n = 5
    top_n = max(1, top_n)
    instruct = getattr(cfg, "GREP_RERANK_INSTRUCT", None)

    if log_docs:
        _log_rerank_recall_docs(
            query=query,
            entries=entries,
            documents=documents,
            min_score=min_score,
            model=model,
        )

    _t_rr = time.perf_counter()
    hits, rmeta = rerank_documents(
        query,
        documents,
        model=model,
        top_n=min(len(documents), top_n),
        instruct=instruct,
        cfg=cfg,
    )
    meta["perf_ms"] = {"rerank_api": round((time.perf_counter() - _t_rr) * 1000.0, 1)}
    meta.update(rmeta)
    meta["backend"] = backend
    meta["query"] = query[:200]
    meta["min_score"] = min_score
    meta["top_n"] = top_n
    meta["in_n"] = len(entries)

    if rmeta.get("status") != "ok" or not hits:
        print(
            f"[GREP-RERANK] 未生效 status={rmeta.get('status')} in={len(entries)}，保留 ES 原序",
            flush=True,
        )
        meta["rerank"] = "fallback"
        meta["out_n"] = len(bug_list) + len(badcase_list)
        _log_rerank_diagnosis(
            entries=entries,
            hits=hits or [],
            min_score=min_score,
            kept_bug=bug_list,
            kept_bc=badcase_list,
            meta=meta,
        )
        return bug_list, badcase_list, meta

    score_rows = _build_rerank_score_rows(entries, documents, hits, min_score=min_score)

    kept_bug, kept_bc, audit = _filter_lists_by_hits(
        bug_list,
        badcase_list,
        entries,
        hits,
        min_score=min_score,
        top_n=top_n,
    )
    if not kept_bug and not kept_bc and hits:
        try:
            floor = float(getattr(cfg, "GREP_RERANK_FALLBACK_MIN_SCORE", 0.45))
        except (TypeError, ValueError):
            floor = 0.45
        kept_bug, kept_bc, audit_fb = _filter_lists_by_hits(
            bug_list,
            badcase_list,
            entries,
            hits,
            min_score=floor,
            top_n=top_n,
        )
        if kept_bug or kept_bc:
            meta["rerank"] = "ok_fallback_floor"
            meta["fallback_min_score"] = floor
            audit = audit_fb
        else:
            best = max(hits, key=lambda h: h.score)
            if best.index >= 0 and best.index < len(entries):
                et, row, _ = entries[best.index]
                out = dict(row)
                out["_rerank_score"] = round(float(best.score), 6)
                if et == "bug":
                    kept_bug = [out]
                else:
                    kept_bc = [out]
                meta["rerank"] = "ok_fallback_top1"
                meta["fallback_top1_score"] = out["_rerank_score"]
                audit = [
                    {
                        "entity_type": et,
                        "id": out.get("id"),
                        "score": out["_rerank_score"],
                    }
                ]
    if meta.get("rerank") not in ("ok_fallback_floor", "ok_fallback_top1"):
        meta["rerank"] = "ok"
    meta["out_n"] = len(kept_bug) + len(kept_bc)
    if meta["out_n"] == 0:
        meta["low_relevance_empty"] = True
    meta["audit"] = audit[:50]
    meta["score_rows"] = score_rows[:50]
    _log_rerank_diagnosis(
        entries=entries,
        hits=hits,
        min_score=min_score,
        kept_bug=kept_bug,
        kept_bc=kept_bc,
        meta=meta,
    )
    if log_docs:
        _log_rerank_score_rows(
            min_score=min_score,
            rows=score_rows,
            kept_n=len(kept_bug) + len(kept_bc),
        )
    print(
        f"[GREP-RERANK] backend={backend} model={model} in={len(entries)} "
        f"pass>={min_score} top_n={top_n}: bug={len(kept_bug)} badcase={len(kept_bc)}",
        flush=True,
    )
    rr_ms = meta.get("perf_ms", {}).get("rerank_api")
    if rr_ms is not None:
        print(f"[GREP-RERANK-PERF] rerank_api={rr_ms}ms in={len(entries)}", flush=True)
    return kept_bug, kept_bc, meta


async def apply_es_rerank(
    *,
    bug_list: List[Dict[str, Any]],
    badcase_list: List[Dict[str, Any]],
    user_input: Optional[str] = None,
    keywords: Optional[str] = None,
    assignee: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    return await asyncio.to_thread(
        rerank_es_candidates_sync,
        bug_list=bug_list,
        badcase_list=badcase_list,
        user_input=user_input,
        keywords=keywords,
        assignee=assignee,
        status=status,
    )
