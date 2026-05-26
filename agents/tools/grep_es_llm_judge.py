"""ES 混合检索命中后，由 LLM 逐条判定候选是否真正符合用户检索意图。"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from agents.tools.grep_assignee import resolve_assignee_display


def _config_flag(cfg, name: str, default: bool = False) -> bool:
    val = getattr(cfg, name, default)
    if isinstance(val, bool):
        return val
    raw = str(val if val is not None else default).strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return bool(default)


def _should_skip_llm_judge(rerank_meta: Optional[Dict[str, Any]], cfg=None) -> Tuple[bool, str]:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return False, ""
    if not isinstance(rerank_meta, dict):
        return False, ""
    rr = str(rerank_meta.get("rerank") or "")
    if _config_flag(cfg, "GREP_SKIP_LLM_JUDGE_IF_RERANKED", True) and rr == "ok":
        return True, "skipped_after_rerank"
    if _config_flag(cfg, "GREP_SKIP_LLM_JUDGE_IF_NO_RERANK_API", True) and rr.startswith("skipped"):
        return True, "skipped_no_rerank_api"
    return False, ""


def _grep_es_llm_judge_enabled(cfg=None) -> bool:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return False
    if not _config_flag(cfg, "GREP_ES_LLM_JUDGE", False):
        return False
    return bool(getattr(cfg, "GREP_VECTOR_ENABLED", False))


def _candidate_key(entity_type: str, record_id: Any) -> str:
    try:
        rid = int(record_id)
    except (TypeError, ValueError):
        return ""
    et = (entity_type or "").strip().lower()
    if et not in ("bug", "badcase"):
        return ""
    return f"{et}:{rid}"


def _build_candidate_lines(
    bug_list: List[Dict[str, Any]],
    badcase_list: List[Dict[str, Any]],
    *,
    max_n: int,
) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    lines: List[str] = []
    by_key: Dict[str, Dict[str, Any]] = {}
    idx = 0
    for et, lst in (("bug", bug_list or []), ("badcase", badcase_list or [])):
        for row in lst:
            if idx >= max_n:
                break
            try:
                rid = int(row.get("id"))
            except (TypeError, ValueError):
                continue
            key = _candidate_key(et, rid)
            if not key:
                continue
            by_key[key] = row
            assignee_label = ""
            if et == "bug":
                aid = row.get("assignee_id")
                if aid is not None:
                    assignee_label = resolve_assignee_display(int(aid)) or str(aid)
            else:
                assignee_label = str(row.get("assignee") or "").strip()
            title = str(row.get("title") or "").strip()
            status = str(row.get("status") or "").strip()
            plan_id = row.get("plan_id")
            idx += 1
            lines.append(
                f"{idx}. [{key}] 标题={title!r} 负责人={assignee_label or '-'} "
                f"状态={status or '-'} plan_id={plan_id}"
            )
    return lines, by_key


def _parse_match_ids(raw: str) -> Set[str]:
    out: Set[str] = set()
    if not raw or not str(raw).strip():
        return out
    s = str(raw).strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s).strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            ids = obj.get("match_ids") or obj.get("matched") or obj.get("ids") or []
            if isinstance(ids, list):
                for x in ids:
                    t = str(x or "").strip().lower()
                    if re.match(r"^(bug|badcase):\d+$", t):
                        out.add(t)
                return out
    except json.JSONDecodeError:
        pass
    for m in re.finditer(r"\b(bug|badcase):(\d+)\b", s, re.I):
        out.add(f"{m.group(1).lower()}:{m.group(2)}")
    return out


def _compose_user_intent(
    *,
    user_input: Optional[str],
    keywords: Optional[str],
    assignee: Optional[str],
    status: Optional[str],
) -> str:
    parts: List[str] = []
    ui = (user_input or "").strip()
    if ui:
        parts.append(f"用户原话：{ui}")
    if assignee and str(assignee).strip():
        parts.append(f"负责人筛选：{str(assignee).strip()}")
    if status and str(status).strip():
        parts.append(f"状态筛选：{str(status).strip()}")
    if keywords and str(keywords).strip() and str(keywords).strip() not in ("*",):
        parts.append(f"关键词：{str(keywords).strip()}")
    return "\n".join(parts) if parts else "（未提供额外意图，请根据候选字段判断）"


def llm_judge_es_candidates_sync(
    *,
    bug_list: List[Dict[str, Any]],
    badcase_list: List[Dict[str, Any]],
    user_input: Optional[str] = None,
    keywords: Optional[str] = None,
    assignee: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    meta: Dict[str, Any] = {"llm_judge": "skipped"}
    try:
        from config import Config as cfg
    except Exception:
        return bug_list, badcase_list, meta
    if not _grep_es_llm_judge_enabled(cfg):
        meta["llm_judge"] = "disabled"
        return bug_list, badcase_list, meta

    total_in = len(bug_list or []) + len(badcase_list or [])
    if total_in <= 0:
        meta["llm_judge"] = "empty_input"
        return bug_list, badcase_list, meta

    max_n = int(getattr(cfg, "GREP_ES_LLM_JUDGE_MAX_CANDIDATES", 30))
    lines, by_key = _build_candidate_lines(bug_list, badcase_list, max_n=max_n)
    if not lines:
        meta["llm_judge"] = "no_valid_candidates"
        return bug_list, badcase_list, meta

    api_key = (getattr(cfg, "DEEPSEEK_API_KEY", None) or "").strip()
    if not api_key:
        meta["llm_judge"] = "no_api_key"
        return bug_list, badcase_list, meta

    intent = _compose_user_intent(
        user_input=user_input,
        keywords=keywords,
        assignee=assignee,
        status=status,
    )
    system = (
        "你是检索结果审核员。ES 已召回候选工作项，你需要判断哪些条目真正符合用户检索意图。"
        "只输出 JSON，不要 Markdown、不要解释。"
        '格式：{"match_ids":["bug:123","badcase:456"]}；若无符合项则 {"match_ids":[]}。'
        "match_ids 必须来自候选列表中的 [bug:id] / [badcase:id]，不要编造 id。"
    )
    user_block = intent + "\n\n候选列表：\n" + "\n".join(lines)

    model = (
        getattr(cfg, "GREP_ES_LLM_JUDGE_MODEL", None)
        or getattr(cfg, "MODIFY_INTENT_LLM_MODEL", None)
        or "deepseek-v4-flash"
    )
    model = str(model).strip() or "deepseek-v4-flash"
    try:
        timeout = float(getattr(cfg, "GREP_ES_LLM_JUDGE_TIMEOUT", 12.0))
    except (TypeError, ValueError):
        timeout = 12.0
    timeout = max(3.0, min(timeout, 60.0))

    try:
        from openai import OpenAI

        base = (getattr(cfg, "DEEPSEEK_API_BASE_URL", None) or "https://api.deepseek.com").strip().rstrip("/")
        client = OpenAI(api_key=api_key, base_url=base, timeout=timeout, max_retries=0)
        _t_llm = time.perf_counter()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_block},
            ],
            temperature=0,
            max_tokens=int(getattr(cfg, "GREP_ES_LLM_JUDGE_MAX_TOKENS", 512)),
            stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )
        meta["perf_ms"] = {"llm_judge_api": round((time.perf_counter() - _t_llm) * 1000.0, 1)}
        ch0 = resp.choices[0] if resp.choices else None
        msg = getattr(ch0, "message", None) if ch0 else None
        raw = (getattr(msg, "content", None) or "").strip() if msg is not None else ""
    except Exception as e:
        print(f"[GREP-LLM-JUDGE] LLM 调用失败，保留 ES 原结果: {e}", flush=True)
        meta.update({"llm_judge": "error", "error": str(e), "in_n": total_in})
        return bug_list, badcase_list, meta

    matched = _parse_match_ids(raw)
    meta.update(
        {
            "llm_judge": "ok",
            "in_n": total_in,
            "out_n": len(matched),
            "model": model,
        }
    )
    if not matched:
        print(
            f"[GREP-LLM-JUDGE] LLM 判定 0 条符合意图（ES in={total_in}）",
            flush=True,
        )
        return [], [], meta

    out_bug: List[Dict[str, Any]] = []
    out_bc: List[Dict[str, Any]] = []
    for key, row in by_key.items():
        if key not in matched:
            continue
        if key.startswith("bug:"):
            out_bug.append(row)
        elif key.startswith("badcase:"):
            out_bc.append(row)

    bug_order = [_candidate_key("bug", r.get("id")) for r in (bug_list or [])]
    bc_order = [_candidate_key("badcase", r.get("id")) for r in (badcase_list or [])]
    out_bug.sort(
        key=lambda r: bug_order.index(_candidate_key("bug", r.get("id")))
        if _candidate_key("bug", r.get("id")) in bug_order
        else 9999
    )
    out_bc.sort(
        key=lambda r: bc_order.index(_candidate_key("badcase", r.get("id")))
        if _candidate_key("badcase", r.get("id")) in bc_order
        else 9999
    )

    j_ms = (meta.get("perf_ms") or {}).get("llm_judge_api")
    print(
        f"[GREP-LLM-JUDGE] ES in={total_in} LLM matched={len(out_bug)+len(out_bc)} "
        f"(bug={len(out_bug)} badcase={len(out_bc)})"
        + (f" llm_ms={j_ms}" if j_ms is not None else ""),
        flush=True,
    )
    if j_ms is not None:
        print(
            f"[GREP-LLM-JUDGE-PERF] llm_judge_api={j_ms}ms model={model} candidates={len(lines)}",
            flush=True,
        )
    return out_bug, out_bc, meta


async def apply_es_llm_judge(
    *,
    bug_list: List[Dict[str, Any]],
    badcase_list: List[Dict[str, Any]],
    user_input: Optional[str] = None,
    keywords: Optional[str] = None,
    assignee: Optional[str] = None,
    status: Optional[str] = None,
    rerank_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    try:
        from config import Config as cfg
    except Exception:
        cfg = None
    skip, reason = _should_skip_llm_judge(rerank_meta, cfg)
    if skip:
        print(f"[GREP-LLM-JUDGE] 跳过 LLM 二审 reason={reason}", flush=True)
        return bug_list, badcase_list, {"llm_judge": reason}
    return await asyncio.to_thread(
        llm_judge_es_candidates_sync,
        bug_list=bug_list,
        badcase_list=badcase_list,
        user_input=user_input,
        keywords=keywords,
        assignee=assignee,
        status=status,
    )
