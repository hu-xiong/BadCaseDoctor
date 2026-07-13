"""
确定性 modify 目标解析（歧义可走轻量 LLM；`MODIFY_INTENT_LLM=0` 关闭）。

已绑定源表 `target_id` 且无 `card_id`、用户未明示改卡片层时，对 title/description 等歧义字段
**直接走源表、不调用 LLM**（与雪花 id 及列表 flag 无关）。

主入口：resolve_modify_target_and_id(modifications, user_input, context)

调试：终端搜 `[MODIFY-RESOLVE]`。
- 失败行以 `FAIL` 开头，**始终**打印（无需环境变量）。
- 完整进入/分支跟踪：设置环境变量 `MODIFY_RESOLVE_LOG=1`。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

import agents.intent.modify_intent_llm as _modify_intent_llm

SOURCE = "source"
CARD = "card"
AMBIGUOUS = "ambiguous"

FIELD_TO_TABLE: Dict[str, str] = {
    "status": SOURCE,
    "severity": SOURCE,
    "priority": SOURCE,
    "steps_to_reproduce": SOURCE,
    "expected_result": SOURCE,
    "actual_result": SOURCE,
    "assignee_id": SOURCE,
    "assignee": SOURCE,
    "description": AMBIGUOUS,
    "title": AMBIGUOUS,
    "reproduction_steps": SOURCE,
    "answer": SOURCE,
    "correct_answer": SOURCE,
    "badcase_result": SOURCE,
    "base_problem": SOURCE,
    "case_category": SOURCE,
    "case_type": SOURCE,
    "test_type": SOURCE,
    "preconditions": SOURCE,
    "steps": SOURCE,
    "execution_result": SOURCE,
    "estimated_time": SOURCE,
    "actual_time": SOURCE,
    "baseline": SOURCE,
    "executed_by": SOURCE,
    "card_title": CARD,
    "card_description": CARD,
    "plan_id": CARD,
}

SOURCE_TABLES: FrozenSet[str] = frozenset({"bug", "badcase", "testcase"})

_TESTCASE_HINT_KEYS: FrozenSet[str] = frozenset(
    {
        "case_type",
        "test_type",
        "preconditions",
        "steps",
        "execution_result",
        "estimated_time",
        "actual_time",
        "baseline",
        "executed_by",
    }
)
_BADCASE_HINT_KEYS: FrozenSet[str] = frozenset(
    {
        "reproduction_steps",
        "answer",
        "correct_answer",
        "badcase_result",
        "base_problem",
        "case_category",
    }
)

_KEY_ALIASES: Dict[str, str] = {
    "状态": "status",
    "标题": "title",
    "描述": "description",
    "严重程度": "severity",
    "优先级": "priority",
    "负责人": "assignee",
    "指派人": "assignee",
    "复现步骤": "steps_to_reproduce",
    "期望结果": "expected_result",
    "实际结果": "actual_result",
}


class ModifyResolutionError(ValueError):
    """意图解析无法继续（如改卡片但未选中卡片）。"""


def _modify_resolve_trace_enabled() -> bool:
    """设为 MODIFY_RESOLVE_LOG=1 打印完整歧义解析路径（默认关，避免刷屏）。"""
    return (os.getenv("MODIFY_RESOLVE_LOG", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _log_resolve(msg: str) -> None:
    if _modify_resolve_trace_enabled():
        print("[MODIFY-RESOLVE] " + msg, flush=True)


def _log_resolve_fail(msg: str) -> None:
    """失败时始终打印一行，便于对照终端定位（与 MODIFY_RESOLVE_LOG 无关）。"""
    print("[MODIFY-RESOLVE] FAIL " + msg, flush=True)


@dataclass
class ModifyResolutionContext:
    """结构化上下文（无 LLM）；enrich 负责填充。"""

    last_grep_target: Optional[str] = None
    card_id: Optional[int] = None
    target_id: Optional[int] = None
    has_raw_bug_list: bool = False
    editing_surface: Optional[str] = None
    # enrich 可传入，用于源表类型推断与 card_id 反查
    has_raw_badcase_list: bool = False
    has_raw_testcase_list: bool = False
    card_rows: Optional[List[Dict[str, Any]]] = None
    #: modify_tool 在 resolve 前用 DB 做的源表消歧（同 project 下雪花生 id 唯一命中），避免仅 status 等字段时误默认 bug
    db_reconciled_target: Optional[str] = None


def canonical_modify_field_name(key: str) -> str:
    k0 = str(key or "").strip()
    if not k0:
        return ""
    kl = k0.lower()
    if kl in _KEY_ALIASES.values():
        return kl
    if k0 in _KEY_ALIASES:
        return _KEY_ALIASES[k0]
    if kl in _KEY_ALIASES:
        return _KEY_ALIASES[kl]
    return re.sub(r"\s+", "_", kl)


def normalize_modification_key_set(modifications: Optional[Dict[str, Any]]) -> FrozenSet[str]:
    if not modifications or not isinstance(modifications, dict):
        return frozenset()
    out: Set[str] = set()
    for k in modifications.keys():
        c = canonical_modify_field_name(str(k))
        if c:
            out.add(c)
    return frozenset(out)


def remap_card_layer_modification_keys(modifications: Dict[str, Any]) -> Dict[str, Any]:
    if not modifications or not isinstance(modifications, dict):
        return modifications
    out = dict(modifications)
    if "card_title" in out and "title" not in out:
        out["title"] = out.pop("card_title")
    if "card_description" in out and "description" not in out:
        out["description"] = out.pop("card_description")
    return out


def remap_entity_modification_keys(
    target: str, modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """按 target 源表 remap 跨实体误用字段并剔除不可写列（实现见 modify_field_schema）。"""
    from agents.modify_field_schema import remap_entity_modification_keys as _impl

    return _impl(target, modifications)


def find_card_id_for_bug_source_id(
    card_rows: Optional[List[Dict[str, Any]]],
    bug_id: int,
) -> Optional[int]:
    if not card_rows:
        return None
    for row in card_rows:
        if not isinstance(row, dict):
            continue
        st = str(row.get("source_type") or "").strip().lower().replace("-", "_")
        if st not in ("bug", "defect", ""):
            continue
        sid_raw = row.get("source_id")
        try:
            sid = int(sid_raw) if sid_raw is not None and str(sid_raw).strip() != "" else None
        except (TypeError, ValueError):
            sid = None
        if sid is None or sid != int(bug_id):
            continue
        pk = row.get("card_id") if row.get("card_id") is not None else row.get("id")
        if pk is None:
            continue
        try:
            cid = int(pk)
        except (TypeError, ValueError):
            continue
        if cid > 0:
            return cid
    return None


def _as_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        i = int(v)
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None


def _disambiguate_title(user_input: str, context: ModifyResolutionContext) -> str:
    """返回 'card' 或 'source'（歧义 title/description 层）。"""
    t = user_input or ""
    # 「修改卡片 xxx 的标题」中间可有计划名等，未必出现连续「卡片标题」；与 intent_guards 对齐
    from agents.intent_guards import (
        user_text_implies_bug_entity_type,
        user_text_implies_card_entity_type,
    )

    if user_text_implies_card_entity_type(t):
        return CARD
    # 明确谈 Bug/缺陷 的标题时，不得因上一步 grep 用了 card 就判成改 Card.title
    if user_text_implies_bug_entity_type(t):
        return SOURCE
    if "卡片标题" in t or "看板标题" in t:
        return CARD
    if any(x in t for x in ("缺陷标题", "Bug标题", "bug标题", "案例标题")):
        return SOURCE
    es = (context.editing_surface or "").strip().lower()
    if es == "card_title":
        return CARD
    if es == "bug_title":
        return SOURCE
    lgt = (context.last_grep_target or "").strip().lower()
    if lgt == "card":
        tid = _as_int(context.target_id)
        cid = _as_int(context.card_id)
        # 引擎已解析出源表主键（如 Bug.id）、但未选卡片层 card_id 时，常见于「合并 grep / last_grep=card」；
        # 此时若仍判 CARD，会误要求「请先选中卡片」。改 Bug 标题应走源表。
        if tid is not None and cid is None:
            _log_resolve("disambig_title: last_grep=card, tid set, cid empty -> SOURCE")
            return SOURCE
        _log_resolve("disambig_title: last_grep=card -> CARD (需 ctx.card_id 或唯一 card_rows)")
        return CARD
    if lgt in SOURCE_TABLES:
        return SOURCE
    cid = _as_int(context.card_id)
    tid = _as_int(context.target_id)
    if cid is not None and tid is None:
        return CARD
    # 二者同时存在时：不再仅凭「缺 target_id」判卡片；话术已在上文用 user_text_implies_card_entity_type 处理
    return SOURCE


def _user_implies_card_layer(text: Optional[str]) -> bool:
    """用户话术是否明确要求改统一卡片层（与 _disambiguate_title 首步一致）。"""
    from agents.intent_guards import user_text_implies_card_entity_type

    return user_text_implies_card_entity_type(text or "")


def _infer_source_table(keys: FrozenSet[str], context: ModifyResolutionContext) -> str:
    if keys & _TESTCASE_HINT_KEYS:
        return "testcase"
    if keys & _BADCASE_HINT_KEYS:
        return "badcase"
    # 已由上层用 Bug/BadCase/TestCase 表做过「该 id 唯一落在哪张源表」的判定（与 grep 列表 flag 无关）
    db_rt = getattr(context, "db_reconciled_target", None)
    if isinstance(db_rt, str):
        rtl = db_rt.strip().lower()
        if rtl in SOURCE_TABLES:
            return rtl
    if context.has_raw_testcase_list and not context.has_raw_bug_list and not context.has_raw_badcase_list:
        return "testcase"
    if context.has_raw_badcase_list and not context.has_raw_bug_list and not context.has_raw_testcase_list:
        return "badcase"
    if context.has_raw_bug_list:
        return "bug"
    return "bug"


def resolve_modify_target_and_id(
    modifications: Dict[str, Any],
    user_input: str,
    context: ModifyResolutionContext,
) -> Tuple[str, Optional[int], Optional[int]]:
    """
    主决策：根据 modifications 字段归属 + 用户话术 + context 决定 target 与主键。

    返回 (target, pk, card_id)：
    - target 为源表时 pk 为源表主键，card_id 可为回跳用 Card.id（若能从 card_rows 反查）。
    - target 为 card 时 pk 为 None，card_id 为卡片主键。
    """
    mods = remap_card_layer_modification_keys(dict(modifications or {}))
    keys = normalize_modification_key_set(mods)
    if not keys:
        _log_resolve_fail(
            "modifications 为空或无可识别字段 | "
            f"raw_mod_keys={list((modifications or {}).keys())[:40]!r}"
        )
        raise ModifyResolutionError("modifications 为空或无可识别字段")

    tables_needed: Set[str] = set()
    for k in keys:
        layer = FIELD_TO_TABLE.get(k)
        if layer is not None:
            tables_needed.add(layer)

    if not tables_needed:
        tables_needed.add(SOURCE)

    # Step 2：源表字段与卡片字段同时出现 → 强制源表
    if SOURCE in tables_needed and CARD in tables_needed:
        tables_needed = {SOURCE}

    target: str
    pk: Optional[int]
    out_card: Optional[int] = _as_int(context.card_id)

    _nrows = len(context.card_rows) if isinstance(context.card_rows, list) else 0
    _log_resolve(
        "enter "
        f"keys={sorted(keys)!r} tables_needed={sorted(tables_needed)!r} "
        f"last_grep={context.last_grep_target!r} ctx_target_id={context.target_id!r} ctx_card_id={context.card_id!r} "
        f"flags_bug/bc/tc={context.has_raw_bug_list}/{context.has_raw_badcase_list}/{context.has_raw_testcase_list} "
        f"editing_surface={context.editing_surface!r} user_len={len(user_input or '')} "
        f"user_head={(user_input or '')[:180]!r} card_rows_n={_nrows}"
    )

    if tables_needed == {CARD}:
        target = "card"
        _log_resolve("branch tables_needed=={CARD} -> target=card（如仅 plan_id / card_title 等）")
    elif SOURCE in tables_needed:
        target = _infer_source_table(keys, context)
    elif tables_needed <= {AMBIGUOUS} or keys == frozenset({"title"}):
        es0 = (context.editing_surface or "").strip().lower()
        if es0 == "card_title":
            target = "card"
        elif es0 == "bug_title":
            target = _infer_source_table(keys, context)
        else:
            # 仅有 title/description 等歧义字段时：若上下文已绑定源表主键且无卡片层 id，
            # 可执行的只能是改源表记录，不必再走 LLM（雪花 id 与列表 flag 无关）。
            # 用户若明示「改卡片标题」等，仍走下方 disambig，最终 target=card 并提示选卡。
            _tid_early = _as_int(context.target_id)
            _cid_early = _as_int(context.card_id)
            if (
                _tid_early is not None
                and _cid_early is None
                and not _user_implies_card_layer(user_input)
            ):
                target = _infer_source_table(keys, context)
                _log_resolve(
                    "ambiguous + target_id 已设且无 card_id、未明示卡片层："
                    f"直接源表 target={target!r}（不调 LLM）"
                )
            elif _disambiguate_title(user_input, context) == CARD:
                _tid_d = _as_int(context.target_id)
                _cid_d = _as_int(context.card_id)
                if (
                    _tid_d is not None
                    and _cid_d is None
                    and not _user_implies_card_layer(user_input)
                ):
                    target = _infer_source_table(keys, context)
                    _log_resolve(
                        "disambig_title=CARD 但 ctx.target_id 已设且无 card_id、未明示卡片层，"
                        f"覆盖为源表 target={target!r}"
                    )
                else:
                    target = "card"
            else:
                llm_target: Optional[str] = None
                if _modify_intent_llm.modify_intent_llm_enabled():
                    llm_target = _modify_intent_llm.llm_classify_modify_ambiguous_target(
                        user_input,
                        last_grep_target=context.last_grep_target,
                        editing_surface=context.editing_surface,
                        card_id=context.card_id,
                        target_id=context.target_id,
                        has_raw_bug_list=context.has_raw_bug_list,
                        has_raw_badcase_list=context.has_raw_badcase_list,
                        has_raw_testcase_list=context.has_raw_testcase_list,
                        keys=keys,
                    )
                if llm_target in ("card", "bug", "badcase", "testcase"):
                    _tid_llm = _as_int(context.target_id)
                    _cid_llm = _as_int(context.card_id)
                    # 已绑定源表主键、未选卡片层时，LLM 常误判为 card（无 user 文本时尤甚），会导致「请先选中卡片」
                    if (
                        llm_target == "card"
                        and _tid_llm is not None
                        and _cid_llm is None
                        and not _user_implies_card_layer(user_input)
                    ):
                        target = _infer_source_table(keys, context)
                        _log_resolve(
                            f"llm_target=card 但 ctx.target_id={_tid_llm} 且无 card_id、未明示卡片层，"
                            f"覆盖为源表 target={target!r}（忽略误判 card）"
                        )
                    else:
                        target = llm_target
                else:
                    target = _infer_source_table(keys, context)
    else:
        target = _infer_source_table(keys, context)

    _log_resolve(f"target_chosen={target!r} tables_needed={sorted(tables_needed)!r}")

    if target == "card":
        cid = _as_int(context.card_id)
        if cid is None and context.card_rows and len(context.card_rows) == 1:
            row0 = context.card_rows[0]
            if isinstance(row0, dict):
                cid = _as_int(row0.get("card_id")) or _as_int(row0.get("id"))
        if cid is None:
            row0_dbg = None
            if isinstance(context.card_rows, list) and len(context.card_rows) == 1:
                row0_dbg = context.card_rows[0]
            _log_resolve_fail(
                "请先选中卡片 | cause=歧义或字段归属已定为 target=card，但 ctx.card_id 为空且无法从唯一 card_rows 取 id | "
                f"mods_keys={sorted(keys)} tables_needed={sorted(tables_needed)} target={target!r} "
                f"last_grep={context.last_grep_target!r} ctx_target_id={context.target_id!r} ctx_card_id={context.card_id!r} "
                f"editing_surface={context.editing_surface!r} user_head={(user_input or '')[:200]!r} "
                f"single_row={row0_dbg!r}"
            )
            raise ModifyResolutionError("请先选中卡片")
        pk = None
        out_card = cid
        return target, pk, out_card

    # 源表
    pk = _as_int(context.target_id)
    if pk is None:
        _log_resolve_fail(
            "请先选中要修改的记录（缺少源表 target_id） | "
            f"target={target!r} mods_keys={sorted(keys)} tables_needed={sorted(tables_needed)} "
            f"last_grep={context.last_grep_target!r} ctx_card_id={context.card_id!r} "
            f"user_head={(user_input or '')[:200]!r}"
        )
        raise ModifyResolutionError("请先选中要修改的记录（缺少源表 target_id）")

    rows = context.card_rows or []
    if target == "bug":
        linked = find_card_id_for_bug_source_id(rows, pk)
        if linked is not None:
            out_card = linked
    return target, pk, out_card


def infer_source_tuple_from_card_dict(row: Any) -> Optional[Tuple[str, int, Optional[int]]]:
    """
    从单条 grep 卡片行反推 (源表 target, source_id, card_pk)；无关联则 None。
    供少量仍需要「从卡片行取 id」的代码路径使用。
    """
    if not isinstance(row, dict):
        return None

    def _card_pk() -> Optional[int]:
        for k in ("card_id", "id"):
            v = row.get(k)
            c = _as_int(v)
            if c is not None:
                return c
        return None

    card_pk = _card_pk()
    st = str(row.get("source_type") or "").strip().lower()
    sid_raw = row.get("source_id")
    try:
        sid = int(sid_raw) if sid_raw is not None and str(sid_raw).strip() != "" else None
    except (TypeError, ValueError):
        sid = None
    if sid is not None and sid > 0:
        if st in ("bug", "defect"):
            return "bug", sid, card_pk
        if st in ("bad_case", "badcase", "bad-case"):
            return "badcase", sid, card_pk
        if st in ("test_case", "testcase", "test-case"):
            return "testcase", sid, card_pk
    tp = str(row.get("type") or "").strip().lower()
    if sid is not None and sid > 0:
        if tp in ("bug", "defect"):
            return "bug", sid, card_pk
        if tp in ("badcase", "bad_case"):
            return "badcase", sid, card_pk
        if tp in ("testcase", "test_case"):
            return "testcase", sid, card_pk
    return None
