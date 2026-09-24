# -*- coding: utf-8 -*-
"""
从已退役的自研 ReAct 引擎（agents/react_simplified.py）抽取的、LangGraph 现役路径仍在使用的助手。

内容：
- _REACT_STREAM_CANCEL_EVENTS / request_react_stream_cancel：SSE 会话级取消事件总线
- _react_should_block_repeat_grep / _grep_observation_empty_lists：grep 空结果与重复拦截守卫
- LegacyReActHelpers：grep 意图纠正、modify target 补全、pending diff 合并、grep 结果并入上下文等
"""
import os
import threading
from .intent_guards import user_text_implies_bug_entity_type, user_text_implies_card_entity_type, user_text_implies_plan_entity_type
from typing import Any, Dict, List, Optional, Tuple

_REACT_STREAM_CANCEL_EVENTS: Dict[str, threading.Event] = {}

def request_react_stream_cancel(agent_session_id: str) -> bool:
    if not agent_session_id or not str(agent_session_id).strip():
        return False
    key = str(agent_session_id).strip()
    ev = _REACT_STREAM_CANCEL_EVENTS.get(key)
    if ev is None:
        return False
    ev.set()
    return True


def _react_grep_no_repeat_after_empty_enabled() -> bool:
    return (os.getenv("REACT_GREP_NO_REPEAT_AFTER_EMPTY", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _react_grep_no_repeat_if_hits_enabled() -> bool:
    return (os.getenv("REACT_GREP_NO_REPEAT_IF_HITS", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _react_should_block_repeat_grep(
    *,
    prev_observation: Optional[Dict[str, Any]],
    prev_action: Optional[Dict[str, Any]],
    grep_call_count: int,
) -> Tuple[bool, str]:
    """
    无命中或已有命中后禁止再次 grep（避免换词空转多轮 LLM+检索）。
    返回 (是否拦截, reason 码：empty / has_hits)。
    """
    if grep_call_count < 1:
        return False, ""
    if str((prev_action or {}).get("tool") or "").strip().lower() != "grep":
        return False, ""
    if _react_grep_no_repeat_after_empty_enabled():
        if _grep_observation_empty_lists(prev_observation or {}):
            return True, "empty"
        _data = (prev_observation or {}).get("data") or {}
        if isinstance(_data, dict):
            _meta = _data.get("grep_search_meta") or {}
            if isinstance(_meta, dict) and _meta.get("low_relevance_empty"):
                return True, "empty"
    if _react_grep_no_repeat_if_hits_enabled() and not _grep_observation_empty_lists(
        prev_observation or {}
    ):
        return True, "has_hits"
    return False, ""


def _grep_observation_empty_lists(observation: Dict[str, Any]) -> bool:
    """grep locate 成功但四类工作项列表均为空时视为无命中。"""
    if not isinstance(observation, dict):
        return True
    data = observation.get("data") or {}
    if not isinstance(data, dict):
        return True
    n = 0
    for k in ("bug_location", "badcase_analysis", "testcase_location", "card_location"):
        x = data.get(k)
        if isinstance(x, list):
            n += len(x)
    return n == 0


class LegacyReActHelpers:
    """grep/modify 领域助手，逐行抽取自旧引擎（行为不变）。"""

    def __init__(self, llm=None, tool_registry=None):
        self.llm = llm
        self.tools = tool_registry
        self.project_id = None
        self.plan_id = None
        self.db = None
        self.user_id = ""
        self._user_id = ""
        self._ui_locale = "zh"
        self._ui_context = None
        self._client_shell = None
        self._pending_diff_context = {}
        self._grep_result_cache = {}
        self._agent_session_id = None
        self._chat_session_id = None
        self._react_stream_user_query = None
        self._react_stream_user_input = None

    @staticmethod
    def _normalize_modify_target(target: Any) -> str:
        t = (str(target or "badcase")).strip().lower().replace("-", "_")
        if t in ("test_case", "testcase"):
            return "testcase"
        if t in ("bug", "badcase", "card", "plan"):
            return t
        return "badcase"

    @staticmethod
    def _react_modify_grep_multi_batch_enabled() -> bool:
        v = (os.getenv("REACT_MODIFY_GREP_MULTI_BATCH", "1") or "1").strip().lower()
        return v not in ("0", "false", "no", "off", "")

    @staticmethod
    def _react_modify_grep_expand_single_id_to_batch_enabled() -> bool:
        """
        grep 多条命中但模型只传 target_id 为其中一条时，是否扩展为整批 target_ids。
        默认关：用户常点名单条标题，模型已选对 id，扩批会导致沙箱预览与 modify 对不上。
        需要「改这一批」时设 REACT_MODIFY_GREP_EXPAND_SINGLE_ID_TO_BATCH=1。
        """
        v = (
            os.getenv("REACT_MODIFY_GREP_EXPAND_SINGLE_ID_TO_BATCH", "0") or "0"
        ).strip().lower()
        return v in ("1", "true", "yes", "on")

    @staticmethod
    def _coerce_modify_id_list(raw: Any) -> List[int]:
        if raw is None:
            return []
        if isinstance(raw, (list, tuple, set)):
            vals = list(raw)
        elif isinstance(raw, str):
            vals = [x.strip() for x in raw.split(",") if x.strip()]
        else:
            vals = [raw]
        out: List[int] = []
        for v in vals:
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                continue
        return out

    def _context_row_ids_for_modify_target(
        self, result_context: Dict[str, Any], target_type: str
    ) -> List[int]:
        """优先用 grep 原始命中行（含无 plan_id 的 Bug），避免 navigation 过滤后只剩一条导致无法批量 modify。"""
        if target_type == "bug":
            rows = result_context.get("grep_modify_raw_bug_list")
            if not isinstance(rows, list) or len(rows) == 0:
                rows = result_context.get("bug_list") or []
        elif target_type == "testcase":
            rows = result_context.get("grep_modify_raw_testcase_list")
            if not isinstance(rows, list) or len(rows) == 0:
                rows = result_context.get("testcase_list") or []
        elif target_type == "card":
            rows = result_context.get("grep_modify_raw_card_list")
            if not isinstance(rows, list) or len(rows) == 0:
                rows = result_context.get("card_list") or []
        elif target_type == "plan":
            rows = result_context.get("grep_modify_raw_plan_list")
            if not isinstance(rows, list) or len(rows) == 0:
                rows = result_context.get("plan_list") or []
        else:
            rows = result_context.get("grep_modify_raw_badcase_list")
            if not isinstance(rows, list) or len(rows) == 0:
                rows = result_context.get("badcase_list") or []
        out: List[int] = []
        seen: set = set()
        for x in rows or []:
            if not isinstance(x, dict):
                continue
            raw_id = x.get("id")
            if raw_id is None and target_type == "card":
                raw_id = x.get("card_id")
            if raw_id is None:
                continue
            try:
                ix = int(raw_id)
            except (TypeError, ValueError):
                continue
            if ix not in seen:
                seen.add(ix)
                out.append(ix)
        return out

    def _pick_best_modify_id_by_user_title(
        self,
        result_context: Dict[str, Any],
        target_type: str,
        user_hint: str,
        cand_ids: List[int],
    ) -> Optional[int]:
        """用户话术含具体标题时，从 grep 命中里选最匹配的一条，避免误批量。"""
        hint = (user_hint or "").strip()
        if not hint or not cand_ids:
            return None
        title_kw = (self._extract_title_keywords_for_grep(hint, "") or "").strip()
        if not title_kw or len(title_kw) < 2:
            return None
        if target_type == "bug":
            rows = result_context.get("grep_modify_raw_bug_list") or result_context.get("bug_list") or []
        elif target_type == "testcase":
            rows = result_context.get("grep_modify_raw_testcase_list") or result_context.get("testcase_list") or []
        elif target_type == "card":
            rows = result_context.get("grep_modify_raw_card_list") or result_context.get("card_list") or []
        else:
            rows = result_context.get("grep_modify_raw_badcase_list") or result_context.get("badcase_list") or []
        best_id = None
        best_score = -1
        cand_set = set(int(x) for x in cand_ids)
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            try:
                rid = int(row.get("id") or row.get("card_id") or 0)
            except (TypeError, ValueError):
                continue
            if rid not in cand_set:
                continue
            title = str(row.get("title") or "")
            score = 0
            if title_kw and title_kw in title:
                score = 100 + len(title_kw)
            elif title and title in hint:
                score = 80 + min(len(title), 40)
            else:
                # 分词弱匹配
                hits = sum(1 for ch in title_kw if ch and ch in title)
                if hits >= max(2, len(title_kw) // 2):
                    score = hits
            if score > best_score:
                best_score = score
                best_id = rid
        return best_id if best_score > 0 else None

    def _enrich_modify_params_target_ids(
        self,
        params: Dict[str, Any],
        result_context: Dict[str, Any],
        target_type: str,
        *,
        log_prefix: str = "",
        user_hint: str = "",
    ) -> None:
        """
        白名单模型传入的 target_ids / target_id 数组；grep 列表非空时只保留列表内 id。
        grep 多条命中时：未带 id 则优先按用户标题选单条，否则才注入整批 target_ids；
        仅带一条 target_id 时默认不扩批（REACT_MODIFY_GREP_EXPAND_SINGLE_ID_TO_BATCH=1 可开）。
        """
        ctx_ids = self._context_row_ids_for_modify_target(result_context, target_type)
        ctx_set = set(ctx_ids)
        hint = (
            user_hint
            or str(params.get("_resolve_user_input") or params.get("natural_query") or "")
        ).strip()

        def _filt(cand: List[int]) -> List[int]:
            if not ctx_set:
                return cand
            return [i for i in cand if i in ctx_set]

        if params.get("target_ids") is not None:
            cand = _filt(self._coerce_modify_id_list(params.get("target_ids")))
            if len(cand) >= 2:
                params["target_ids"] = cand
                params.pop("target_id", None)
            elif len(cand) == 1:
                params["target_id"] = cand[0]
                params.pop("target_ids", None)
            else:
                params.pop("target_ids", None)
        else:
            params.pop("target_ids", None)

        tid_raw = params.get("target_id")
        if isinstance(tid_raw, (list, tuple, set)):
            cand = _filt(self._coerce_modify_id_list(tid_raw))
            params.pop("target_id", None)
            if len(cand) >= 2:
                params["target_ids"] = cand
            elif len(cand) == 1:
                params["target_id"] = cand[0]
        elif tid_raw is not None:
            try:
                iv = int(tid_raw)
                if ctx_set and iv not in ctx_set:
                    params.pop("target_id", None)
                else:
                    params["target_id"] = iv
            except (TypeError, ValueError):
                params.pop("target_id", None)

        if (
            not params.get("target_ids")
            and params.get("target_id") is None
            and len(ctx_ids) >= 2
        ):
            picked = self._pick_best_modify_id_by_user_title(
                result_context, target_type, hint, ctx_ids
            )
            if picked is not None:
                params["target_id"] = picked
                params.pop("target_ids", None)
                print(
                    f"{log_prefix}grep 多条命中 → 按标题选单条 target_id={picked}",
                    flush=True,
                )
            elif self._react_modify_grep_multi_batch_enabled():
                params["target_ids"] = sorted(ctx_ids)
                print(
                    f"{log_prefix}grep 多条命中 → 单次批量 modify target_ids={params['target_ids']}",
                    flush=True,
                )
        elif (
            self._react_modify_grep_multi_batch_enabled()
            and self._react_modify_grep_expand_single_id_to_batch_enabled()
            and len(ctx_ids) >= 2
            and params.get("target_ids") is None
            and params.get("target_id") is not None
        ):
            try:
                one = int(params["target_id"])
            except (TypeError, ValueError):
                one = None
            if one is not None and ctx_set and one in ctx_set:
                params["target_ids"] = sorted(ctx_ids)
                params.pop("target_id", None)
                print(
                    f"{log_prefix}grep 多条命中且仅传 target_id={one} "
                    f"→ 扩展为批量 target_ids={params['target_ids']}",
                    flush=True,
                )

    @classmethod
    def _pending_key(cls, target: Any, target_id: Any) -> str:
        try:
            tid = int(target_id)
        except Exception:
            tid = target_id
        return f"{cls._normalize_modify_target(target)}:{tid}"

    @staticmethod
    def _mods_from_diff(diff: Any) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        if not isinstance(diff, list):
            return out
        for fd in diff:
            if not isinstance(fd, dict):
                continue
            f = fd.get("field") or fd.get("field_label")
            if not f:
                continue
            lines = fd.get("lines") or []
            old_line = next((l for l in lines if isinstance(l, dict) and l.get("type") == "delete"), None)
            new_line = next((l for l in lines if isinstance(l, dict) and l.get("type") == "add"), None)
            unchanged = next((l for l in lines if isinstance(l, dict) and l.get("type") == "unchanged"), None)
            old_v = old_line.get("content") if old_line else (unchanged.get("content") if unchanged else "")
            new_v = new_line.get("content") if new_line else (unchanged.get("content") if unchanged else "")
            out[str(f)] = {"old": old_v, "new": new_v}
        return out

    def _mods_normalize(self, mods: Any, diff: Any) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        if isinstance(mods, dict):
            for k, v in mods.items():
                if isinstance(v, dict) and ("new" in v or "old" in v):
                    out[str(k)] = {"old": v.get("old", ""), "new": v.get("new", "")}
                else:
                    out[str(k)] = {"old": "", "new": v}
        # 用 diff 补 old/new
        dmods = self._mods_from_diff(diff)
        for f, dv in dmods.items():
            if f in out:
                if out[f].get("old", "") in ("", None):
                    out[f]["old"] = dv.get("old", "")
                if out[f].get("new", "") in ("", None):
                    out[f]["new"] = dv.get("new", "")
            else:
                out[f] = {"old": dv.get("old", ""), "new": dv.get("new", "")}
        return out

    def _merge_with_pending(self, target: Any, target_id: Any, diff: Any, mods: Any) -> Tuple[Any, Any]:
        key = self._pending_key(target, target_id)
        pending = self._pending_diff_context.get(key)
        if not pending:
            return diff, mods
        pending_mods = self._mods_normalize(pending.get("modifications"), pending.get("diff"))
        delta_mods = self._mods_normalize(mods, diff)
        merged: Dict[str, Dict[str, Any]] = {k: {"old": v.get("old", ""), "new": v.get("new", "")} for k, v in pending_mods.items()}
        for f, dv in delta_mods.items():
            if f in merged:
                # old 保持生命周期起点，new 以后者覆盖
                merged[f]["new"] = dv.get("new", merged[f].get("new", ""))
            else:
                merged[f] = {"old": dv.get("old", ""), "new": dv.get("new", "")}
        labels = {}
        for fd in (pending.get("diff") or []):
            if isinstance(fd, dict):
                fk = fd.get("field") or fd.get("field_label")
                if fk:
                    labels[str(fk)] = fd.get("field_label") or str(fk)
        for fd in (diff or []):
            if isinstance(fd, dict):
                fk = fd.get("field") or fd.get("field_label")
                if fk:
                    labels[str(fk)] = fd.get("field_label") or str(fk)
        merged_diff = [
            {
                "field": f,
                "field_label": labels.get(f, f),
                "lines": [
                    {"type": "delete", "content": v.get("old", "")},
                    {"type": "add", "content": v.get("new", "")},
                ],
            }
            for f, v in merged.items()
        ]
        return merged_diff, merged

    def _index_pending_context(self, pending_diff_context: Any) -> None:
        self._pending_diff_context = {}
        if not isinstance(pending_diff_context, list):
            return
        for item in pending_diff_context:
            if not isinstance(item, dict):
                continue
            tid = item.get("target_id")
            try:
                tid = int(tid)
            except Exception:
                continue
            target = self._normalize_modify_target(item.get("target"))
            key = self._pending_key(target, tid)
            self._pending_diff_context[key] = {
                "target": target,
                "target_id": tid,
                "diff": item.get("diff") or [],
                "modifications": item.get("modifications") or {},
            }

    def _normalize_rerank_keywords(self, raw: Any) -> str:
        """grep / FC 可能传入字符串或关键词列表，统一成单个检索串供 rerank。"""
        if raw is None:
            return ''
        if isinstance(raw, (list, tuple)):
            parts = [str(x).strip() for x in raw if x is not None and str(x).strip()]
            return ' '.join(parts)
        if isinstance(raw, str):
            return raw
        return str(raw)

    def _rerank_score(self, item: Dict, keywords: str, key_title: str = 'title') -> float:
        """
        Rerank 打分：分高的优先。关键词命中数×10 + 整句命中加 50，便于选最相关的一条。
        """
        if not keywords or not keywords.strip():
            return 1.0
        import re
        title = (item.get(key_title) or '').strip()
        text = re.sub(r'[和与]', ' ', keywords.strip())
        parts = [p.strip() for p in text.split() if p.strip()]
        stop = {'的', '为', '与', '和', '或', '及'}
        terms = [p for p in parts if p not in stop and (len(p) > 1 or p not in stop)]
        if not terms:
            return 50.0 if keywords.strip() in title else 0.0
        score = sum(10 for t in terms if t in title)
        if keywords.strip() in title:
            score += 50
        return float(score)

    def _rerank_and_pick(self, items: List[Dict], keywords: str, key_title: str = 'title', top_k: int = 1) -> List[Dict]:
        """
        Rerank 后取分高的：按 _rerank_score 排序，返回 top_k 条（分高的就都可以，默认取 1 条）。
        """
        if not items:
            return []
        keywords = self._normalize_rerank_keywords(keywords)
        if not keywords or not keywords.strip():
            return items[:top_k]
        scored = [(item, self._rerank_score(item, keywords, key_title)) for item in items]
        scored.sort(key=lambda x: -x[1])
        # 同分都算「分高的」：取所有与最高分相同的项，再截 top_k
        if not scored:
            return []
        best_score = scored[0][1]
        top = [item for item, s in scored if s == best_score][:top_k]
        return top if top else [scored[0][0]]

    def _merge_grep_observation_into_context(
        self,
        observation: Dict[str, Any],
        params: Dict[str, Any],
        result_context: Dict[str, Any],
    ) -> None:
        """将 grep 成功的 observation 合并进 result_context，供后续 modify 使用。"""
        if not observation or not observation.get('success'):
            return
        grep_data = observation.get('data', {}) or {}
        badcase_list = grep_data.get('badcase_analysis', [])
        bug_list = grep_data.get('bug_location', [])
        testcase_list = grep_data.get('testcase_location', [])
        card_list = grep_data.get('card_location', [])
        plan_list_raw = grep_data.get('plan_location', []) or []
        # 无 plan_id 的记录不会进入 navigation，_restrict_by_nav 后 bug_list 可能只剩 1 条，
        # 但 modify 批量应与「grep 关键词命中」的全集一致，故单独保留原始列表供 target_ids 推断。
        result_context["grep_modify_raw_badcase_list"] = list(badcase_list or [])
        result_context["grep_modify_raw_bug_list"] = list(bug_list or [])
        result_context["grep_modify_raw_testcase_list"] = list(testcase_list or [])
        result_context["grep_modify_raw_card_list"] = list(card_list or [])
        result_context["grep_modify_raw_plan_list"] = list(plan_list_raw or [])
        _kw_raw = params.get('keywords') or result_context.get('_last_grep_keywords') or ''
        kw = self._normalize_rerank_keywords(_kw_raw)
        result_context['_last_grep_keywords'] = kw or ''
        _gtt = str(params.get('target') or '').strip().lower()
        if _gtt:
            result_context['_last_grep_target'] = _gtt
            try:
                setattr(self, "_session_last_grep_target", _gtt)
            except Exception:
                pass

        # 优先使用 grep_tool 生成的 navigation（它已按计划/权限/可跳转过滤），避免后续 modify 误选到列表里“碰巧更像”的其它记录
        nav_ids: Dict[str, List[int]] = {
            "bug": [],
            "badcase": [],
            "testcase": [],
            "card": [],
            "plan": [],
        }
        nav_items: List[Dict[str, Any]] = []
        _nav = grep_data.get("navigation")
        has_nav = _nav is not None
        if isinstance(_nav, dict):
            if _nav.get("type") == "multiple" and isinstance(_nav.get("items"), list):
                nav_items = [x for x in (_nav.get("items") or []) if isinstance(x, dict)]
            elif _nav.get("type") == "expand_and_locate":
                nav_items = [_nav]
        for it in nav_items:
            t = (it.get("target") or "").strip().lower()
            rid = it.get("record_id") or it.get("bug_id") or it.get("id")
            try:
                rid_int = int(rid)
            except Exception:
                continue
            if t in nav_ids:
                nav_ids[t].append(rid_int)
        # 去重保序
        for k in nav_ids:
            seen = set()
            uniq = []
            for x in nav_ids[k]:
                if x in seen:
                    continue
                seen.add(x)
                uniq.append(x)
            nav_ids[k] = uniq

        _total_nav = sum(len(nav_ids[k]) for k in nav_ids)
        print(
            f"[GREP-NAV] navigation_ids: bug={nav_ids['bug']} (n={len(nav_ids['bug'])}), "
            f"badcase={nav_ids['badcase']} (n={len(nav_ids['badcase'])}), "
            f"testcase={nav_ids['testcase']} (n={len(nav_ids['testcase'])}), "
            f"card={nav_ids['card']} (n={len(nav_ids['card'])}), "
            f"plan={nav_ids['plan']} (n={len(nav_ids['plan'])}); "
            f"raw_location_counts: badcase_analysis={len(badcase_list)}, bug_location={len(bug_list)}, "
            f"testcase_location={len(testcase_list)}, card_location={len(card_list)}, "
            f"plan_location={len(plan_list_raw)}; has_navigation={has_nav}"
        )
        if has_nav and _total_nav == 0:
            print(
                "[GREP-NAV] WARNING: navigation present but parsed navigation_ids are all empty; "
                "restricted lists may be empty — check navigation payload shape vs parser "
                "(e.g. type/items vs expand_and_locate)."
            )
        for _label, _raw, _key in (
            ("bug", bug_list, "bug"),
            ("badcase", badcase_list, "badcase"),
            ("testcase", testcase_list, "testcase"),
        ):
            _nav_n = len(nav_ids[_key])
            _raw_n = len(_raw or [])
            if has_nav and _raw_n > _nav_n and _raw_n > 0:
                print(
                    f"[GREP-NAV] WARNING: {_label} raw_location={_raw_n} > navigable ids={_nav_n}; "
                    f"extra rows likely lack plan_id or were filtered from navigation."
                )

        def first_id(lst, kws):
            if not lst:
                return None
            picked = self._rerank_and_pick(lst, kws, 'title', 1)
            return picked[0].get('id') if picked else lst[0].get('id')

        def _restrict_by_nav(lst: List[Dict[str, Any]], ids: List[int]) -> List[Dict[str, Any]]:
            # grep_tool 的 navigation 是前端可见/可跳转的“官方候选集”。
            # 如果 grep 返回了 navigation，但解析不到对应 ids，则宁可返回空，也不要退回全量列表导致误选/多选。
            if not ids:
                return [] if has_nav else (lst or [])
            idset = set(ids)

            def _row_id_in_nav_set(xid: Any) -> bool:
                if xid is None:
                    return False
                try:
                    return int(xid) in idset
                except (TypeError, ValueError):
                    return False

            return [x for x in (lst or []) if isinstance(x, dict) and _row_id_in_nav_set(x.get("id"))]

        badcase_list_nav = _restrict_by_nav(badcase_list, nav_ids.get("badcase") or [])
        bug_list_nav = _restrict_by_nav(bug_list, nav_ids.get("bug") or [])
        testcase_list_nav = _restrict_by_nav(testcase_list, nav_ids.get("testcase") or [])
        card_list_nav = _restrict_by_nav(card_list, nav_ids.get("card") or [])
        plan_list_nav = _restrict_by_nav(plan_list_raw, nav_ids.get("plan") or [])

        result_context['grep_result'] = {
            'first_badcase_id': first_id(badcase_list_nav, kw),
            'first_bug_id': first_id(bug_list_nav, kw),
            'first_testcase_id': first_id(testcase_list_nav, kw),
            'first_card_id': first_id(card_list_nav, kw),
            'first_plan_id': first_id(plan_list_nav, kw),
            'badcase_list': badcase_list_nav,
            'bug_list': bug_list_nav,
            'testcase_list': testcase_list_nav,
            'card_list': card_list_nav,
            'plan_list': plan_list_nav,
            'navigation_ids': nav_ids,
        }
        result_context['badcase_list'] = badcase_list_nav
        result_context['bug_list'] = bug_list_nav
        result_context['testcase_list'] = testcase_list_nav
        result_context['card_list'] = card_list_nav
        result_context['plan_list'] = plan_list_nav
        print(
            f"[REACT-execution] grep 结果: {len(badcase_list)} badcase, {len(bug_list)} bug, "
            f"{len(testcase_list)} testcase, {len(card_list)} card, {len(plan_list_raw)} plan"
        )
        # merge 后候选（写入 context）与 [GREP-NAV] 对照
        try:
            _bug_ids = [b.get("id") for b in bug_list_nav if isinstance(b, dict)]
            _bc_ids = [b.get("id") for b in badcase_list_nav if isinstance(b, dict)]
            _tc_ids = [b.get("id") for b in testcase_list_nav if isinstance(b, dict)]
            _nav = grep_data.get("navigation")
            if not _nav:
                _nav_n = 0
            elif isinstance(_nav, dict) and _nav.get("type") == "multiple":
                _nav_n = len(_nav.get("items") or [])
            else:
                _nav_n = 1
            print(
                f"[MODIFY-TRACE] merge_grep → context merge_after_ids: "
                f"bug={_bug_ids}, badcase={_bc_ids}, testcase={_tc_ids}; "
                f"bug_list_len={len(bug_list_nav)}, first_bug_id={result_context['grep_result'].get('first_bug_id')}, "
                f"navigation_items≈{_nav_n}, keywords_kw={kw!r}"
            )
            for _kind, _merged, _auth in (
                ("bug", _bug_ids, nav_ids.get("bug") or []),
                ("badcase", _bc_ids, nav_ids.get("badcase") or []),
                ("testcase", _tc_ids, nav_ids.get("testcase") or []),
            ):
                if not _auth:
                    continue
                try:
                    _ms, _as = set(_merged), set(_auth)
                except Exception:
                    continue
                if _ms != _as:
                    print(
                        f"[MODIFY-TRACE] WARNING: merge_grep merge_after_ids({_kind})={sorted(_ms)} "
                        f"!= navigation_ids={sorted(_as)}"
                    )
        except Exception as _e:
            print(f"[MODIFY-TRACE] merge_grep 附加日志失败: {_e}")

    def _unified_prewarm_grep_params_from_user(
        self,
        user_input: str,
        todo: str,
        *,
        project_id: Optional[int] = None,
        plan_id: Optional[int] = None,
        ui_context: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """首轮误选 modify 时同轮改写为 grep 的参数（与 _last_resort_modify_fill 的 grep 段对齐）。"""
        kw = (self._extract_title_keywords_for_grep(user_input, todo) or "").strip()
        if not kw and user_input:
            kw = (user_input or "")[:200].strip()
        if not kw and todo:
            kw = (todo or "")[:200].strip()
        if not kw:
            kw = " "
        # 默认 all：标题修改常落在 BadCase/Card，且避免被侧栏 plan_id 锁死在空迭代
        target = "all"
        exp = self._infer_modify_target_explicit(user_input, todo)
        if exp:
            target = exp
        elif isinstance(ui_context, dict):
            ut = str(ui_context.get("target") or "").strip().lower()
            if ut in ("bug", "badcase", "testcase", "card", "plan"):
                target = ut
        params: Dict[str, Any] = {
            "project_id": project_id,
            "keywords": kw,
            "mode": "locate",
            "target": target,
            "userId": "system_agent",
        }
        if plan_id is not None:
            params["plan_id"] = plan_id
        elif getattr(self, "plan_id", None) is not None:
            params["plan_id"] = self.plan_id
        return params

    def _infer_modify_target_explicit(self, user_input: str, todo: str) -> Optional[str]:
        """
        用户话术里能否**明确**到实体类型；若能则优先于模型给的 params.target（常见误填 badcase）。
        无法从字面判断时返回 None，交由模型参数 + 默认推断。
        """
        text_raw = f"{user_input or ''} {todo or ''}".strip()
        if not text_raw:
            return None
        text = text_raw.lower()
        if (
            '测试用例' in text_raw
            or '测例' in text_raw
            or 'testcase' in text
            or 'test case' in text
            or 'test_case' in text
        ):
            return 'testcase'
        # 改状态/负责人：源表字段；未明示卡片层时不应按 Card 表 grep（Card.title 常与 Bug.title 不同步）
        if not user_text_implies_card_entity_type(text_raw):
            import re as _re_exp

            if _re_exp.search(
                r"(?:状态|status).{0,24}(?:改|修改|变更|设为|改为|调整)"
                r"|[改修改变更].{0,20}(?:状态|status)",
                text_raw,
                _re_exp.IGNORECASE,
            ):
                return "bug"
        if user_text_implies_card_entity_type(text_raw):
            return 'card'
        if user_text_implies_plan_entity_type(text_raw):
            return 'plan'
        if 'badcase' in text or 'bad case' in text:
            return 'badcase'
        if user_text_implies_bug_entity_type(text_raw):
            return 'bug'
        return None

    def _infer_modify_target(self, user_input: str, todo: str) -> str:
        """
        从用户输入/todo 推断 modify 的 target：用户说「修改bug」则用 bug，避免误改 BadCase。
        """
        exp = self._infer_modify_target_explicit(user_input, todo)
        if exp:
            return exp
        combined = f"{user_input or ''} {todo or ''}"
        text = combined.lower()
        if not text.strip():
            return 'badcase'
        if user_text_implies_card_entity_type(combined):
            return 'card'
        if user_text_implies_plan_entity_type(combined):
            return 'plan'
        if 'badcase' in text or 'bad case' in text:
            return 'badcase'
        if user_text_implies_bug_entity_type(combined):
            return 'bug'
        if '测试用例' in combined or 'testcase' in text or 'test_case' in text:
            return 'testcase'
        return 'badcase'

    def _widen_grep_target_to_include_cards_unless_explicit(
        self, params: Dict[str, Any], user_input: str, todo: str
    ) -> None:
        """
        主界面列表数据在 Card 表；模型常误填 target=bug 等仅查源表，导致 Card 命中为 0。
        若用户话术未**明确**限定 Bug/BadCase/测例源表，则将 target 升为 all（含 Card）。
        """
        if not isinstance(params, dict):
            return
        t = str(params.get("target") or "").strip().lower()
        if not t:
            params["target"] = "all"
            return
        if t in ("all", "card", "plan"):
            return
        if t not in ("bug", "badcase", "testcase"):
            return
        exp = self._infer_modify_target_explicit(user_input or "", todo or "")
        if exp is not None:
            return
        print(
            f"[REACT-execution] grep.params.target 泛查放宽: {t!r} -> all "
            f"（用户未明确仅限某一源表类型，需检索 Card 层）"
        )
        params["target"] = "all"

    def _coerce_grep_target_for_user_intent(
        self, decision: Dict[str, Any], user_input: str, todo: str
    ) -> None:
        """grep 阶段：用户已明说测例/Bug/BadCase 时，纠正模型窄化的 target，避免只查 badcase 导致 testcase_list 为空。"""
        if not decision.get('execute') or decision.get('tool') != 'grep':
            return
        exp = self._infer_modify_target_explicit(user_input, todo)
        if not exp:
            return
        params = decision.setdefault('params', {})
        if not isinstance(params, dict):
            return
        t = str(params.get('target') or '').strip().lower()
        ui_ctx = params.get("ui_context")
        if isinstance(ui_ctx, dict):
            ut = str(ui_ctx.get("target") or "").strip().lower()
            if ut in ("bug", "badcase", "testcase") and t in ("card", "all", ""):
                print(
                    f"[REACT-execution] grep.params.target 界面聚焦 {ut}，纠正: {t!r} -> {ut}"
                )
                params["target"] = ut
                return
        _raw = f"{user_input or ''} {todo or ''}"
        if user_text_implies_bug_entity_type(_raw) and t in ("card", "badcase"):
            print(
                f"[REACT-execution] grep.params.target 用户明确 bug，纠正: {t!r} -> bug"
            )
            params["target"] = "bug"
            return
        # 反向保护：模型已给 bug 时，若真实用户话术明确「Bug」，不因 todo/界面上下文里的 Card/BadCase 字样
        # 把 target 覆盖为 card/badcase（否则导航只剩卡片层命中，与总结展示的源表结果不对应）
        if (
            t == "bug"
            and exp in ("card", "badcase")
            and user_text_implies_bug_entity_type(user_input or "")
        ):
            print(
                f"[REACT-execution] grep.params.target 用户话术明确 Bug，保留: 'bug'（忽略 exp={exp!r} 推断）"
            )
            return
        if t in ('all', exp):
            return
        if exp == 'testcase' and t not in ('testcase', 'all'):
            print(f"[REACT-execution] grep.params.target 按用户测例意图纠正: {t!r} -> testcase")
            params['target'] = 'testcase'
        elif exp == 'bug' and t not in ('bug', 'all'):
            print(f"[REACT-execution] grep.params.target 按用户缺陷意图纠正: {t!r} -> bug")
            params['target'] = 'bug'
        elif exp == 'badcase' and t not in ('badcase', 'all'):
            print(f"[REACT-execution] grep.params.target 按用户 BadCase 意图纠正: {t!r} -> badcase")
            params['target'] = 'badcase'
        elif exp == 'card' and t not in ('card', 'all'):
            import re as _re_gc

            _raw = f"{user_input or ''} {todo or ''}"
            if (
                not user_text_implies_card_entity_type(_raw)
                and _re_gc.search(
                    r"(?:状态|status).{0,24}(?:改|修改|变更|设为|改为)"
                    r"|[改修改变更].{0,20}(?:状态|status)",
                    _raw,
                    _re_gc.IGNORECASE,
                )
            ):
                print(
                    f"[REACT-execution] grep.params.target 状态修改优先源表: {t!r} -> bug"
                )
                params["target"] = "bug"
            else:
                print(
                    f"[REACT-execution] grep.params.target 按用户卡片意图纠正: {t!r} -> card"
                )
                params["target"] = "card"
        elif exp == 'plan' and t not in ('plan', 'all'):
            print(f"[REACT-execution] grep.params.target 按用户计划意图纠正: {t!r} -> plan")
            params['target'] = 'plan'

    def _normalize_grep_plan_scope(self, params: Dict[str, Any]) -> None:
        """
        grep 计划范围：优先使用当前侧栏迭代 self.plan_id；并剔除模型将 project_id 误填为 plan_id 的情况。
        """
        if not isinstance(params, dict):
            return
        t = str(params.get("target") or "all").strip().lower()
        if t in ("all", "plan"):
            params.pop("plan_id", None)
            return

        proj = params.get("project_id") or getattr(self, "project_id", None)
        raw = params.get("plan_id")
        if raw is not None and proj is not None:
            try:
                if int(raw) == int(proj):
                    print(
                        f"[REACT] grep 移除误填 plan_id={raw}（与 project_id 相同）"
                    )
                    params.pop("plan_id", None)
                    raw = None
            except (TypeError, ValueError):
                pass

        agent_pid = getattr(self, "plan_id", None)
        if agent_pid in (None, "", 0, "0"):
            return
        try:
            ap = int(agent_pid)
        except (TypeError, ValueError):
            return
        if ap <= 0:
            return
        if raw is None:
            params["plan_id"] = ap
            print(f"[REACT] grep 注入当前迭代 plan_id={ap}")
            return
        try:
            rp = int(raw)
        except (TypeError, ValueError):
            params["plan_id"] = ap
            print(f"[REACT] grep 注入当前迭代 plan_id={ap}（原 plan_id 非法）")
            return
        if rp != ap:
            print(f"[REACT] grep 用当前迭代 plan_id={ap} 覆盖模型 plan_id={rp}")
            params["plan_id"] = ap

    def _force_grep_card_layer_only_if_requested(
        self, params: Dict[str, Any], user_input: str, todo: str
    ) -> None:
        """
        用户明确要「查卡片 / 搜迭代列表上的卡片」时，只查 Card 表（target=card），
        不要 bug/badcase/testcase 源表与 all（避免出现「只查 bug 记录」而看不到卡片层口径）。
        本规则在 _coerce、_widen 之后执行，覆盖模型误填的 all/bug。
        """
        if not isinstance(params, dict):
            return
        raw = f"{user_input or ''} {todo or ''}".strip()
        if not raw:
            return
        raw_lower = raw.lower()
        # 中文：查/搜/找/列出 + 卡片；迭代列表上的卡片；仅卡片层
        markers_cn = (
            '查卡片',
            '查询卡片',
            '搜卡片',
            '找卡片',
            '卡片搜索',
            '列出卡片',
            '卡片列表',
            '统一卡片',
            '仅查卡片',
            '只看卡片',
            '只要卡片',
            '卡片层',
            '迭代里的卡片',
            '迭代卡片',
            '列表里的卡片',
            '主界面卡片',
        )
        markers_en = (
            'query card',
            'list card',
            'search card',
            'card list',
            'cards only',
            'only cards',
        )
        if not any(m in raw for m in markers_cn) and not any(
            m in raw_lower for m in markers_en
        ):
            return
        print(
            "[REACT-execution] grep 用户意图为「仅卡片层 Card 表」: "
            f"target {params.get('target')!r} -> card"
        )
        params['target'] = 'card'
        # 与 prompts 一致：查当前迭代卡片时带上 plan_id
        if getattr(self, 'plan_id', None) and not params.get('plan_id'):
            params['plan_id'] = self.plan_id

    def _extract_title_keywords_for_grep(self, user_input: str, todo: str) -> str:
        """
        从用户输入或 todo 中提取要修改的 BadCase/Bug 标题，用于 grep 的 keywords 参数。
        例如：「修改雪碧和七喜的正确答案为理解正确」 -> 「雪碧和七喜」
        """
        import re
        text = (user_input or '') + ' ' + (todo or '')
        if not text.strip():
            return ''
        # 优先识别显式关键词参数（用户常用：keywords=登录 / 关键词：登录 / 关键字=登录）
        for pattern in [
            r'keywords\s*[=:：]\s*([^\s,，。;；\n]+)',
            r'(?:关键词|关键字)\s*[=:：]\s*([^\s,，。;；\n]+)',
        ]:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                kw = (m.group(1) or '').strip().strip('"“”\'‘’')
                if kw and len(kw) <= 50:
                    return kw
        # 「<旧标题> 这个/bug标题修改成 <新标题>」：用户给的是旧标题，取它去定位
        # （必须先于下面的「修改/把/将 XXX 的」分支，否则会把新标题当关键词）
        m = re.search(
            r'^(.+?)\s*(?:这个|该|此)\s*\w{0,10}?标题\s*'
            r'(?:修改|变更|更改|更换|更名|改名|改|换)\s*(?:成|为)',
            text,
            flags=re.IGNORECASE,
        )
        if m:
            kw = (m.group(1) or '').strip().strip('，,。;；:：')
            kw = re.sub(r'^(?:请|帮忙|麻烦|帮我|把|将)\s*', '', kw).strip()
            if 4 <= len(kw) <= 50:
                return kw
        # 优先：修改/把/将 XXX 的优先级|状态|负责人…（标题里可含「的」）
        for pattern in [
            r'修改\s*(.+?)\s*的\s*(?:优先级|priority|状态|status|负责人|指派|标题|严重|等级)',
            r'把\s*(.+?)\s*的\s*(?:优先级|priority|状态|status|负责人|指派|标题|严重|等级)',
            r'将\s*(.+?)\s*的\s*(?:优先级|priority|状态|status|负责人|指派|标题|严重|等级)',
        ]:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                kw = m.group(1).strip()
                if kw and len(kw) <= 80:
                    return kw
        # 修改/把/将 XXX 的 … -> XXX（非贪婪，取到第一个「的」为止）
        for pattern in [
            r'修改\s*(.+?)\s*的',
            r'把\s*(.+?)\s*的',
            r'将\s*(.+?)\s*的',
            r'标题[是为]\s*([^，。\n]+)',
        ]:
            m = re.search(pattern, text)
            if m:
                kw = m.group(1).strip()
                if kw and len(kw) <= 50:  # 避免整句当关键词
                    return kw
        # grep/定位/查找 场景的兜底：提取最可能的短关键词（优先中文，其次英文数字串）
        if any(k in text for k in ('grep', '定位', '查找', '搜索')):
            m = re.search(r'[\u4e00-\u9fff]{1,8}', text)
            if m:
                return m.group(0)
            m = re.search(r'[A-Za-z_]{2,20}', text)
            if m:
                return m.group(0)
        return ''

