"""Grep hybrid 空结果时，对会话内 recent_created_ids 做 SQL 小集合兜底（文档 §10.3）。"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

RECENT_CREATED_META_KEY = "recent_created_ids"


def _now_ts() -> float:
    return time.time()


def append_recent_created_entries(
    existing: Optional[List[Dict[str, Any]]],
    *,
    entity_type: str,
    record_id: int,
    project_id: int,
    max_items: int = 30,
    ttl_s: int = 900,
) -> List[Dict[str, Any]]:
    et = (entity_type or "").strip().lower()
    try:
        rid = int(record_id)
        pid = int(project_id)
    except (TypeError, ValueError):
        return list(existing or [])
    if rid <= 0 or pid <= 0 or et not in ("bug", "badcase", "testcase"):
        return list(existing or [])

    now = _now_ts()
    out: List[Dict[str, Any]] = []
    for item in existing or []:
        if not isinstance(item, dict):
            continue
        try:
            ts = float(item.get("ts") or 0)
        except (TypeError, ValueError):
            ts = 0.0
        if ttl_s > 0 and ts and (now - ts) > ttl_s:
            continue
        out.append(dict(item))
    out.append(
        {
            "entity_type": et,
            "record_id": rid,
            "project_id": pid,
            "ts": now,
        }
    )
    # 去重：同 entity+id 保留最新
    dedup: Dict[str, Dict[str, Any]] = {}
    for item in out:
        key = f"{item.get('entity_type')}:{item.get('record_id')}:{item.get('project_id')}"
        prev = dedup.get(key)
        if not prev or float(item.get("ts") or 0) >= float(prev.get("ts") or 0):
            dedup[key] = item
    merged = sorted(dedup.values(), key=lambda x: float(x.get("ts") or 0), reverse=True)
    return merged[: max(1, int(max_items))]


def build_recent_created_patch(
    entity_type: str,
    record_id: int,
    project_id: int,
) -> Dict[str, Any]:
    return {
        "meta": {
            "recent_created_append": [
                {
                    "entity_type": (entity_type or "").strip().lower(),
                    "record_id": int(record_id),
                    "project_id": int(project_id),
                    "ts": _now_ts(),
                }
            ]
        }
    }


def touch_work_items_after_write(
    entity_type: str,
    record_ids: List[int],
    project_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Bug/BadCase 写入后：异步触发 ES 索引，并返回 tool_run_ctx_patch 供 grep SQL 兜底。
    create / modify 共用。
    """
    et = (entity_type or "").strip().lower()
    if et not in ("bug", "badcase"):
        return None
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return None
    ids: List[int] = []
    seen = set()
    for raw in record_ids or []:
        try:
            rid = int(raw)
        except (TypeError, ValueError):
            continue
        if rid <= 0 or rid in seen:
            continue
        seen.add(rid)
        ids.append(rid)
    if not ids:
        return None
    try:
        from memory.work_item_indexer import schedule_work_item_index

        for rid in ids:
            schedule_work_item_index(et, rid)
    except Exception as e:
        print(f"[GREP-TOUCH] schedule index 失败 {et} ids={ids}: {e}", flush=True)
    append: List[Dict[str, Any]] = []
    for rid in ids:
        append.extend(build_recent_created_patch(et, rid, pid)["meta"]["recent_created_append"])
    return {"tool_run_ctx_patch": {"meta": {"recent_created_append": append}}}


def merge_recent_created_meta(meta: Dict[str, Any], patch_meta: Dict[str, Any]) -> None:
    if not isinstance(meta, dict) or not isinstance(patch_meta, dict):
        return
    append = patch_meta.get("recent_created_append")
    if not isinstance(append, list):
        return
    try:
        from config import Config

        max_items = int(getattr(Config, "GREP_RECENT_CREATED_MAX", 30))
        ttl_s = int(getattr(Config, "GREP_RECENT_CREATED_TTL_S", 900))
    except Exception:
        max_items, ttl_s = 30, 900
    cur = meta.get(RECENT_CREATED_META_KEY)
    base = list(cur) if isinstance(cur, list) else []
    for item in append:
        if not isinstance(item, dict):
            continue
        base = append_recent_created_entries(
            base,
            entity_type=str(item.get("entity_type") or ""),
            record_id=int(item.get("record_id") or 0),
            project_id=int(item.get("project_id") or 0),
            max_items=max_items,
            ttl_s=ttl_s,
        )
    meta[RECENT_CREATED_META_KEY] = base


def get_recent_created_entries(
    tool_run_ctx: Optional[Dict[str, Any]],
    *,
    project_id: int,
    entity_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(tool_run_ctx, dict):
        return []
    meta = tool_run_ctx.get("meta")
    if not isinstance(meta, dict):
        return []
    raw = meta.get(RECENT_CREATED_META_KEY)
    if not isinstance(raw, list):
        return []
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return []
    et_filter = (entity_type or "").strip().lower() or None
    try:
        from config import Config

        ttl_s = int(getattr(Config, "GREP_RECENT_CREATED_TTL_S", 900))
    except Exception:
        ttl_s = 900
    now = _now_ts()
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            if int(item.get("project_id") or 0) != pid:
                continue
            et = str(item.get("entity_type") or "").strip().lower()
            if et_filter and et != et_filter:
                continue
            ts = float(item.get("ts") or 0)
            if ttl_s > 0 and ts and (now - ts) > ttl_s:
                continue
            rid = int(item.get("record_id") or 0)
            if rid <= 0:
                continue
            out.append({"entity_type": et, "record_id": rid, "project_id": pid, "ts": ts})
        except (TypeError, ValueError):
            continue
    return out


def _ids_missing_from_list(items: List[Dict[str, Any]], candidate_ids: List[int]) -> List[int]:
    present = set()
    for it in items or []:
        try:
            present.add(int(it.get("id")))
        except (TypeError, ValueError):
            pass
    out: List[int] = []
    seen = set()
    for cid in candidate_ids:
        if cid in seen:
            continue
        seen.add(cid)
        if cid not in present:
            out.append(cid)
    return out


async def merge_recent_created_sql_fallback(
    grep_tool: Any,
    *,
    project_id: str,
    bug_list: List[Dict[str, Any]],
    badcase_list: List[Dict[str, Any]],
    hybrid_bug: bool,
    hybrid_bc: bool,
    raw_target: str,
    keywords: Optional[str],
    assignee: Optional[str],
    status: Optional[str],
    plan_id: Optional[str],
    tool_run_ctx: Optional[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    hybrid 已走 ES 但结果未含 recent_created 时，按 id 小集合 SQL 补全。
    返回 (bug_list, badcase_list, meta_fragment)。
    """
    meta: Dict[str, Any] = {"sql_fallback": {"bug": [], "badcase": []}}
    try:
        from config import Config

        if not getattr(Config, "GREP_RECENT_CREATED_FALLBACK", True):
            return bug_list, badcase_list, meta
    except Exception:
        pass

    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return bug_list, badcase_list, meta

    t = (raw_target or "all").strip().lower()
    recent_bug = get_recent_created_entries(tool_run_ctx, project_id=pid, entity_type="bug")
    recent_bc = get_recent_created_entries(tool_run_ctx, project_id=pid, entity_type="badcase")

    if hybrid_bug and t in ("all", "bug") and recent_bug:
        bug_ids = [int(x["record_id"]) for x in recent_bug]
        missing = _ids_missing_from_list(bug_list, bug_ids)
        if missing and (not bug_list or missing):
            rows = await grep_tool._get_bug_list_by_ids(
                project_id,
                missing,
                keywords=keywords,
                status=status,
                plan_id=plan_id,
                assignee=assignee,
                skip_keyword_filter=True,
            )
            if rows:
                bug_list = list(bug_list) + rows
                meta["sql_fallback"]["bug"] = [int(r.get("id")) for r in rows if r.get("id") is not None]
                print(
                    f"[GREP-FALLBACK] recent_created bug ids={missing} merged={len(rows)}",
                    flush=True,
                )

    if hybrid_bc and t in ("all", "badcase") and recent_bc:
        bc_ids = [int(x["record_id"]) for x in recent_bc]
        missing = _ids_missing_from_list(badcase_list, bc_ids)
        if missing and (not badcase_list or missing):
            rows = await grep_tool._get_badcase_list_by_ids(
                project_id,
                missing,
                keywords=keywords,
                status=status,
                plan_id=plan_id,
                assignee=assignee,
                skip_keyword_filter=True,
            )
            if rows:
                badcase_list = list(badcase_list) + rows
                meta["sql_fallback"]["badcase"] = [int(r.get("id")) for r in rows if r.get("id") is not None]
                print(
                    f"[GREP-FALLBACK] recent_created badcase ids={missing} merged={len(rows)}",
                    flush=True,
                )

    return bug_list, badcase_list, meta
