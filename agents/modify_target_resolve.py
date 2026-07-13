# -*- coding: utf-8 -*-
"""
grep→modify：解析将要修改的 (target, target_id)。

优先级（与「改错条」治理一致）：
1. 用户话术与 grep 导航列表标题的匹配（子串 + IDF，如「登录」→ 登录相关 BadCase）
2. 界面聚焦 record_id（须在 navigation_ids 内，且无更强话术匹配）
3. grep_result.first_*_id（merge 时已 rerank）
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from utils.entity_id import _first_id_from_grep, _ui_record_for_target, coerce_plausible_entity_pk

# 用户句子里常见、对「选哪条」无区分度的片段
_QUERY_STOP_TOKENS = frozenset(
    {
        "问题",
        "不好",
        "对话",
        "改为",
        "即可",
        "步骤",
        "复现",
        "提问",
        "回答",
        "不能",
        "很好",
        "完整",
        "状态",
        "修改",
        "更新",
        "这条",
        "这个",
        "一下",
        "即可",
        "把",
        "将",
        "为",
        "的",
        "了",
        "在",
        "是",
        "有",
        "和",
        "与",
        "问",
    }
)

_LIST_KEYS = {
    "bug": "bug_list",
    "badcase": "badcase_list",
    "testcase": "testcase_list",
}

# grep 导航过滤后列表可能只剩当前页一条；modify 选条须与 grep_modify_raw_* 全集一致
_RAW_LIST_KEYS = {
    "bug": "grep_modify_raw_bug_list",
    "badcase": "grep_modify_raw_badcase_list",
    "testcase": "grep_modify_raw_testcase_list",
}

def _query_keyword_weights(query: str) -> Dict[str, float]:
    """
    从用户句滑窗抽取 2~4 字中文关键词；在句中出现多次的词权重大（如「登录」）。
    """
    q = (query or "").strip().lower()
    if not q:
        return {}
    weights: Dict[str, float] = {}
    for length in (4, 3, 2):
        for i in range(len(q) - length + 1):
            w = q[i : i + length]
            if not re.fullmatch(r"[\u4e00-\u9fff]+", w):
                continue
            if w in _QUERY_STOP_TOKENS:
                continue
            weights[w] = weights.get(w, 0.0) + 1.0
    for m in re.finditer(r"[a-z]{2,}", q):
        w = m.group(0)
        weights[w] = weights.get(w, 0.0) + 1.0
    return weights


def _idf_title_scores(items: List[Dict[str, Any]], query: str) -> Dict[int, float]:
    """候选标题上的加权命中分：仅在少数标题出现的词权重大。"""
    kw = _query_keyword_weights(query)
    if not kw:
        return {}
    rows: List[Tuple[int, str]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        rid = coerce_plausible_entity_pk(it.get("id"))
        title = str(it.get("title") or "").strip().lower()
        if rid is None or not title:
            continue
        rows.append((rid, title))
    if not rows:
        return {}
    n = len(rows)
    df: Dict[str, int] = {}
    for w in kw:
        df[w] = sum(1 for _, title in rows if w in title)
    out: Dict[int, float] = {}
    for rid, title in rows:
        s = 0.0
        for w, wt in kw.items():
            if w not in title:
                continue
            s += wt * (math.log((n + 1.0) / (df.get(w, 0) + 1.0)) + 1.0)
        if s > 0:
            out[rid] = s
    return out


def _merge_grep_candidate_items(
    result_context: Dict[str, Any],
    grep_result: Dict[str, Any],
    target: str,
) -> List[Dict[str, Any]]:
    """合并导航可见列表与 grep 原始命中（去重），避免导航过滤后只剩 UI 当前条。"""
    list_key = _LIST_KEYS.get(target)
    raw_key = _RAW_LIST_KEYS.get(target)
    merged: List[Dict[str, Any]] = []
    seen: set = set()
    sources: List[Any] = []
    if list_key:
        sources.append(result_context.get(list_key))
        sources.append(grep_result.get(list_key))
    if raw_key:
        sources.append(result_context.get(raw_key))
    for src in sources:
        if not isinstance(src, list):
            continue
        for it in src:
            if not isinstance(it, dict):
                continue
            rid = coerce_plausible_entity_pk(it.get("id"))
            if rid is None or rid in seen:
                continue
            seen.add(rid)
            merged.append(it)
    return merged


_MODIFY_VERB_RE = r"(?:修改|改为|改成|修改为|更新为|换成)"

# (字段键, 用户话术标签正则) — 用于 modify 长文本局部替换锚点
_FIELD_ANCHOR_RULES: Tuple[Tuple[str, str], ...] = (
    ("reproduction_steps", r"复现步骤|重现步骤"),
    ("answer", r"答案"),
    ("correct_answer", r"正确答案"),
    ("expected_result", r"期望结果|预期结果"),
    ("actual_result", r"实际结果"),
    ("base_problem", r"相似问题|具体问题|基础问题"),
)


def _repro_anchor_from_user_query(query: str) -> Optional[str]:
    """兼容旧名：复现步骤锚点。"""
    return _field_anchor_from_user_query(query, "reproduction_steps")


def _field_anchor_from_user_query(query: str, field: str) -> Optional[str]:
    """
    从「…旧内容… 答案修改为 …」类话术抽取待改片段，用于长文本字段局部替换。
    """
    q = (query or "").strip()
    if not q:
        return None
    fk = (field or "").strip().lower().replace("-", "_")
    for key, label_re in _FIELD_ANCHOR_RULES:
        if key != fk:
            continue
        m = re.search(
            rf"(.+?)\s*(?:{label_re})\s*{_MODIFY_VERB_RE}",
            q,
            flags=re.IGNORECASE,
        )
        if not m:
            return None
        anchor = re.sub(r"^[把将请帮给\s]+", "", m.group(1).strip())
        anchor = re.sub(r"\s+", "", anchor)
        if len(anchor) < 4:
            return None
        return anchor
    return None


def _combined_resolve_scores(
    items: List[Dict[str, Any]],
    user_input: str,
    result_context: Dict[str, Any],
    target: str,
) -> Dict[int, float]:
    del result_context, target  # 保留签名供调用方扩展
    return _idf_title_scores(items, user_input)


def _pick_best_scored_id(
    items: List[Dict[str, Any]],
    user_input: str,
    *,
    min_score: float = 1.0,
    min_gap: float = 0.25,
    extra_scores: Optional[Dict[int, float]] = None,
) -> Optional[int]:
    scored = dict(extra_scores or {})
    for rid, s in _idf_title_scores(items, user_input).items():
        scored[rid] = scored.get(rid, 0.0) + s
    if not scored:
        return None
    ordered_ids = sorted(scored.keys(), key=lambda k: scored[k], reverse=True)
    best_id = ordered_ids[0]
    best_score = scored[best_id]
    if best_score < min_score:
        return None
    if len(ordered_ids) >= 2:
        gap = best_score - scored[ordered_ids[1]]
        if gap < min_gap:
            return None
    return best_id


def _navigation_ids_for(grep_result: Dict[str, Any], target: str) -> List[int]:
    nav = grep_result.get("navigation_ids") if isinstance(grep_result, dict) else None
    if not isinstance(nav, dict):
        return []
    out: List[int] = []
    for rid in nav.get(target) or []:
        pk = coerce_plausible_entity_pk(rid)
        if pk is not None:
            out.append(pk)
    return out


def _id_allowed(pk: int, nav_ids: List[int]) -> bool:
    if not nav_ids:
        return True
    return pk in nav_ids


def _ui_context_title_score(
    ui_context: Optional[Dict[str, Any]], target: str, query: str
) -> Tuple[Optional[int], float]:
    """
    详情页 ui_context.title 与话术匹配分（grep 未命中该条时仍能选对 record_id）。
    """
    if not isinstance(ui_context, dict):
        return None, 0.0
    rid = _ui_record_for_target(ui_context, target)
    if rid is None:
        return None, 0.0
    title = str(ui_context.get("title") or "").strip().lower()
    if not title:
        return rid, 0.0
    score = 0.0
    for w, wt in _query_keyword_weights(query).items():
        if w in title:
            score += wt * 2.0
    anchor = _repro_anchor_from_user_query(query)
    if anchor:
        a = anchor.replace(" ", "").lower()
        t = title.replace(" ", "")
        if a in t or t in a:
            score += 10.0
    return rid, score


def _ui_detail_view(ui_context: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(ui_context, dict):
        return False
    return str(ui_context.get("view") or "").strip().lower() == "detail"


def resolve_modify_target_id(
    target: str,
    *,
    grep_result: Optional[Dict[str, Any]] = None,
    result_context: Optional[Dict[str, Any]] = None,
    ui_context: Optional[Dict[str, Any]] = None,
    user_input: str = "",
    explicit_target_id: Optional[Any] = None,
) -> Optional[int]:
    """
    返回将要 modify 的源表主键；无法解析时返回 None。
    """
    tt = (target or "badcase").strip().lower()
    if tt not in ("bug", "badcase", "testcase", "plan", "card"):
        tt = "badcase"
    gr = grep_result if isinstance(grep_result, dict) else {}
    rc = result_context if isinstance(result_context, dict) else {}
    nav_ids = _navigation_ids_for(gr, tt)
    items = _merge_grep_candidate_items(rc, gr, tt)

    uq = (user_input or "").strip()
    scored = _combined_resolve_scores(items, uq, rc, tt)
    by_query = _pick_best_scored_id(items, uq, extra_scores=scored)
    ui_rid = _ui_record_for_target(ui_context, tt)

    exp = coerce_plausible_entity_pk(explicit_target_id)
    if exp is not None and not _id_allowed(exp, nav_ids):
        exp = None

    _ui_rid2, ui_ctx_score = _ui_context_title_score(ui_context, tt, uq)
    if _ui_rid2 is not None and ui_rid is None:
        ui_rid = _ui_rid2
    ui_score = max(
        scored.get(ui_rid, 0.0) if ui_rid is not None else 0.0,
        ui_ctx_score,
    )
    best_score = scored.get(by_query, 0.0) if by_query is not None else 0.0
    exp_list_score = scored.get(exp, 0.0) if exp is not None else 0.0

    # 详情页正在编辑的记录：话术与 ui title 一致时，优先于 grep 首条 / LLM 填错的 explicit
    if (
        ui_rid is not None
        and ui_ctx_score >= 1.0
        and _ui_detail_view(ui_context)
    ):
        if by_query is None or by_query == ui_rid or best_score < ui_ctx_score + 0.25:
            if exp is None or exp == ui_rid or ui_ctx_score > exp_list_score + 0.2:
                return ui_rid

    # 话术明确指向某条（如「登录」）时，优先于界面当前打开条 / 模型填错的 explicit
    if by_query is not None:
        if exp is None or exp == by_query:
            return by_query
        if exp == ui_rid and ui_rid is not None and by_query != ui_rid:
            if best_score >= ui_score + 0.25:
                return by_query
            # 话术已命中另一条（如「登录」），勿因界面打开条而改错记录
            if best_score >= 1.0 and ui_score <= 0.01:
                return by_query
            if ui_score > best_score and _id_allowed(ui_rid, nav_ids):
                return ui_rid
        if best_score > ui_score + 0.2:
            return by_query

    if exp is not None:
        if (
            ui_rid is not None
            and ui_ctx_score >= 1.0
            and ui_ctx_score > exp_list_score + 0.2
            and (by_query is None or best_score < ui_ctx_score + 0.25)
        ):
            return ui_rid
        return exp

    if by_query is not None:
        return by_query

    if ui_rid is not None and (not nav_ids or _id_allowed(ui_rid, nav_ids) or ui_ctx_score >= 1.0):
        return ui_rid

    return _first_id_from_grep(tt, gr, rc)


def resolve_modify_target_pair(
    *,
    grep_result: Optional[Dict[str, Any]] = None,
    result_context: Optional[Dict[str, Any]] = None,
    ui_context: Optional[Dict[str, Any]] = None,
    user_input: str = "",
    target_hint: str = "badcase",
    explicit_target: Optional[str] = None,
    explicit_target_id: Optional[Any] = None,
) -> Optional[Tuple[str, int]]:
    tt = (explicit_target or target_hint or "badcase").strip().lower()
    tid = resolve_modify_target_id(
        tt,
        grep_result=grep_result,
        result_context=result_context,
        ui_context=ui_context,
        user_input=user_input,
        explicit_target_id=explicit_target_id,
    )
    if tid is None:
        return None
    return tt, int(tid)
