# -*- coding: utf-8 -*-
"""
modify 字段与 target 源表对齐：跨实体误用列名 remap + 剔除当前 target 不存在的列。

与 locale_prompts.modify_modifiable_fields_rows 保持一致；供 modify_tool、diff_review、macro 共用。
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

# 各 target 可写字段（源表列 / modify 白名单）
BADCASE_FIELDS: FrozenSet[str] = frozenset(
    {
        "title",
        "status",
        "priority",
        "assignee",
        "base_problem",
        "reproduction_steps",
        "answer",
        "correct_answer",
        "badcase_result",
        "solution",
        "problem_reason",
        "case_category",
        "append_comment",
        "plan_id",
        "project_id",
    }
)
BUG_FIELDS: FrozenSet[str] = frozenset(
    {
        "title",
        "status",
        "priority",
        "severity",
        "assignee",
        "assignee_id",
        "steps_to_reproduce",
        "expected_result",
        "actual_result",
        "append_comment",
        "plan_id",
        "project_id",
        "description",
    }
)
TESTCASE_FIELDS: FrozenSet[str] = frozenset(
    {
        "title",
        "status",
        "priority",
        "assignee",
        "assignee_id",
        "preconditions",
        "steps",
        "baseline",
        "case_type",
        "test_type",
        "execution_result",
        "related_defects",
        "append_comment",
        "plan_id",
        "project_id",
        "estimated_time",
        "actual_time",
    }
)

# (误用键, 本 target  canonical 键) — 仅当 canonical 尚未存在时迁移
_BADCASE_REMAPS: Tuple[Tuple[str, str], ...] = (
    ("expected_result", "answer"),
    ("expected", "answer"),
    ("actual_result", "correct_answer"),
    ("actual", "correct_answer"),
    ("steps_to_reproduce", "reproduction_steps"),
    ("reproduce_steps", "reproduction_steps"),
    ("repro_steps", "reproduction_steps"),
    ("reproduction_step", "reproduction_steps"),
    ("steps", "reproduction_steps"),
    ("test_steps", "reproduction_steps"),
    ("test_step", "reproduction_steps"),
    ("severity", "priority"),
    ("similar_questions", "base_problem"),
    ("similar_question", "base_problem"),
    ("related_questions", "base_problem"),
    ("related_problem", "base_problem"),
    ("specific_problem", "base_problem"),
    ("classification", "case_category"),
    ("category", "case_category"),
    ("conect_answer", "answer"),
    ("correct_answer_final", "correct_answer"),
    ("correct_answer_text", "answer"),
)

_BUG_REMAPS: Tuple[Tuple[str, str], ...] = (
    ("answer", "expected_result"),
    ("correct_answer", "actual_result"),
    ("reproduction_steps", "steps_to_reproduce"),
    ("reproduce_steps", "steps_to_reproduce"),
    ("repro_steps", "steps_to_reproduce"),
    ("steps", "steps_to_reproduce"),
    ("test_steps", "steps_to_reproduce"),
    ("test_step", "steps_to_reproduce"),
    ("reproduction_step", "steps_to_reproduce"),
)

_TESTCASE_REMAPS: Tuple[Tuple[str, str], ...] = (
    ("reproduction_steps", "steps"),
    ("steps_to_reproduce", "steps"),
    ("reproduce_steps", "steps"),
    ("repro_steps", "steps"),
    ("reproduction_step", "steps"),
    ("test_step", "steps"),
    ("test_steps", "steps"),
    ("severity", "priority"),
)

# Keys never valid on a target (after remap) — for logging only
_BADCASE_DROP_HINTS = frozenset(
    {"severity", "expected_result", "actual_result", "steps_to_reproduce", "preconditions", "related_defects"}
)
_BUG_DROP_HINTS = frozenset(
    {"answer", "correct_answer", "reproduction_steps", "base_problem", "badcase_result", "solution", "problem_reason", "case_category", "steps", "preconditions"}
)
_TESTCASE_DROP_HINTS = frozenset(
    {"answer", "correct_answer", "expected_result", "actual_result", "reproduction_steps", "steps_to_reproduce", "base_problem", "badcase_result", "severity"}
)


def normalize_target(target: str) -> str:
    t = (target or "").strip().lower().replace("-", "_")
    if t == "test_case":
        return "testcase"
    return t


def allowed_fields_for_target(target: str) -> FrozenSet[str]:
    t = normalize_target(target)
    if t == "badcase":
        return BADCASE_FIELDS
    if t == "bug":
        return BUG_FIELDS
    if t == "testcase":
        return TESTCASE_FIELDS
    return frozenset()


def modify_field_semantics_for_llm(target: str = "badcase") -> str:
    """供 macro / modify 参数 LLM：字段选择仅由 user_request 语义决定。"""
    t = normalize_target(target or "badcase")
    lines = [
        "【字段语义 — 仅根据 user_request 选列；grep/ui 的 record title 仅用于定位，默认勿写 modifications.title】",
        "- append_comment：用户说「添加/追加/写/留 评论」→ **仅** append_comment（侧栏评论记录）；正文取「评论」之后的文字，**禁止**写 base_problem/title/badcase_result",
        "- badcase_result：仅用户明确改详情页「BadCase结果」列；≠ grep 聊天里的「定位结果」，≠ 相似问题，≠ 评论，≠ 流程状态",
        "- status：用户改流程状态/工作流状态（如重新打开、关闭、待处理）→ **仅** status 列；**禁止**写入 badcase_result",
        "- title：仅当用户明确说「改标题 / 重命名 / 标题改为 / 改名为 / 题目改为」",
    ]
    if t == "badcase":
        lines.extend(
            [
                "【BadCase】",
                "- base_problem（相似问题）：用户说「相似问题」，或描述问题现象、问法、答得不好/不完整、应如何提问 → base_problem",
                "  未要求改标题时，「答的不好」「答不完整」「5环6环区别」等 → base_problem 或 correct_answer（看用户指的是哪一列），**不是 title**",
                "- correct_answer：用户明确改「正确答案」",
                "- answer：用户明确改「答案」",
                "- reproduction_steps / priority / assignee：用户明确提到对应列名时",
                "- status：见上文 status 与 badcase_result 区分；流程状态只写 status",
            ]
        )
    elif t == "bug":
        lines.extend(
            [
                "【Bug】expected_result / actual_result / steps_to_reproduce / severity / priority / status",
                "无「改标题」话术时不要写 title",
            ]
        )
    elif t == "testcase":
        lines.extend(
            [
                "【TestCase】steps / preconditions / case_type / test_type / execution_result",
                "无「改标题」话术时不要写 title",
            ]
        )
    return "\n".join(lines)


def _remap_list_for_target(target: str) -> Tuple[Tuple[str, str], ...]:
    t = normalize_target(target)
    if t == "badcase":
        return _BADCASE_REMAPS
    if t == "bug":
        return _BUG_REMAPS
    if t == "testcase":
        return _TESTCASE_REMAPS
    return ()


def remap_entity_modification_keys(
    target: str, modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """按 target 源表 remap 跨实体误用字段，并剔除不可写列。"""
    if not modifications or not isinstance(modifications, dict):
        return modifications
    t = normalize_target(target)
    allowed = allowed_fields_for_target(t)
    if not allowed:
        return dict(modifications)

    out: Dict[str, Any] = {}
    for k, v in modifications.items():
        if str(k).startswith("_"):
            continue
        fk = str(k).strip().lower().replace("-", "_")
        if fk in out:
            continue
        out[fk] = v

    dropped_remap: List[str] = []
    for from_k, to_k in _remap_list_for_target(t):
        if from_k not in out:
            continue
        if to_k in out:
            dropped_remap.append(from_k)
            out.pop(from_k, None)
            continue
        if to_k in allowed:
            out[to_k] = out.pop(from_k)
        else:
            dropped_remap.append(from_k)
            out.pop(from_k, None)

    # assignee_id / assignee 归一：保留 target 常用键
    if t == "badcase":
        if "assignee_id" in out and "assignee" not in out:
            out["assignee"] = out.pop("assignee_id")
        elif "assignee_id" in out and "assignee" in out:
            out.pop("assignee_id", None)
    elif t in ("bug", "testcase"):
        if "assignee" in out and "assignee_id" not in out:
            out["assignee_id"] = out.pop("assignee")
        elif "assignee" in out and "assignee_id" in out:
            out.pop("assignee", None)

    stripped: List[str] = []
    final: Dict[str, Any] = {}
    for k, v in out.items():
        if k in allowed:
            final[k] = v
        else:
            stripped.append(k)

    if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0" and (dropped_remap or stripped):
        print(
            f"[MODIFY-FIELD] target={t!r} remap_dropped={dropped_remap!r} "
            f"stripped_unknown={stripped!r} kept={list(final.keys())!r}",
            flush=True,
        )
    return final


def _modification_value_plain(value: Any) -> Any:
    if isinstance(value, dict) and "new" in value:
        return value.get("new")
    return value


def _value_looks_like_priority_token(value: Any) -> bool:
    if value is None:
        return False
    raw = str(value).strip()
    if not raw:
        return False
    sl = raw.lower().replace(" ", "").replace("_", "")
    if re.fullmatch(r"p[0-4]", sl):
        return True
    if re.search(r"p[0-4]", sl):
        return True
    if any(x in raw for x in ("紧急", "加急", "火急", "立刻", "立即")):
        return True
    if sl in (
        "urgent",
        "critical",
        "high",
        "medium",
        "low",
        "major",
        "minor",
        "normal",
        "moderate",
        "default",
    ):
        return True
    if raw in ("P0", "P1", "P2", "P3", "P4", "p0", "p1", "p2", "p3", "p4"):
        return True
    if "最高" in raw or "高优" in raw:
        return True
    if raw in ("高", "中", "低") or ("高" in raw and "紧急" not in raw):
        return True
    return False


def user_input_mentions_priority(user_input: str) -> bool:
    u = user_input or ""
    if not u.strip():
        return False
    if any(x in u for x in ("优先级", "优先", "紧急", "加急", "火急", "P1", "P2", "P3", "P4")):
        return True
    return bool(re.search(r"\b[Pp][1-4]\b", u))


def user_input_mentions_badcase_result(user_input: str) -> bool:
    u = (user_input or "").lower()
    if "badcase结果" in u or "badcase_result" in u:
        return True
    if "结果字段" in u:
        return True
    # 「BadCase结果」列；勿把「答不完整」里的「结果」误判为 badcase_result
    if re.search(r"(?:bad\s*case\s*)?结果\s*(?:改为|改成|修改为|设为|更新)", u, re.I):
        return True
    return False


def coerce_badcase_modifications_from_user_intent(
    user_input: str, modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """
    LLM 常把「优先级/紧急」误写到 badcase_result 或 status。
    用户话术明确 priority 时，将误键迁到 priority 并删除误键。
    """
    if not modifications or not isinstance(modifications, dict):
        return modifications
    if not user_input_mentions_priority(user_input):
        return dict(modifications)

    out = dict(modifications)
    mentions_bc_res = user_input_mentions_badcase_result(user_input)

    for wrong_key in ("badcase_result", "result", "status"):
        if wrong_key not in out:
            continue
        val = _modification_value_plain(out[wrong_key])
        if not _value_looks_like_priority_token(val):
            continue
        if mentions_bc_res and wrong_key == "badcase_result":
            continue
        if "priority" not in out:
            out["priority"] = out.pop(wrong_key)
        else:
            out.pop(wrong_key, None)

    if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0" and out != modifications:
        print(
            f"[MODIFY-FIELD] coerce_priority_from_intent "
            f"user_snip={(user_input or '')[:80]!r} "
            f"before={list(modifications.keys())!r} after={list(out.keys())!r}",
            flush=True,
        )
    return out


def normalize_field_key_for_target(raw_field: Any, target: str) -> str:
    """diff / diff_review 用：原始 field 或中文 label → 当前 target 的 canonical 列名。"""
    f = str(raw_field or "").strip().lower().replace("-", "_")
    if not f:
        return ""
    t = normalize_target(target)

    # 中文 label（与 modify_tool._map_field_name 对齐的子集）
    _zh = {
        "期望结果": "expected_result",
        "预期结果": "expected_result",
        "实际结果": "actual_result",
        "复现步骤": "reproduction_steps",
        "测试步骤": "steps",
        "相似问题": "base_problem",
        "具体问题": "base_problem",
        "答案": "answer",
        "正确答案": "correct_answer",
        "严重程度": "severity",
        "问题分类": "case_category",
        "优先级": "priority",
        "前置条件": "preconditions",
    }
    if raw_field in _zh:
        f = _zh[str(raw_field)]
    elif f in _zh:
        f = _zh[f]

    if f in ("steps_to_reproduce", "reproduce_steps", "repro_steps", "reproduction_steps", "reproduction_step"):
        return "reproduction_steps" if t == "badcase" else "steps_to_reproduce" if t == "bug" else "steps"
    if f in ("steps", "test_steps", "test_step"):
        if t == "badcase":
            return "reproduction_steps"
        if t == "bug":
            return "steps_to_reproduce"
        return "steps"
    if f in ("expected", "expected_result"):
        return "answer" if t == "badcase" else "expected_result"
    if f in ("actual", "actual_result"):
        return "correct_answer" if t == "badcase" else "actual_result"
    if f == "severity" and t == "badcase":
        return "priority"
    if f == "severity" and t == "testcase":
        return "priority"
    if f in ("classification", "category") and t == "badcase":
        return "case_category"
    if f == "test_case":
        return "testcase"

    single = remap_entity_modification_keys(t, {f: ""})
    if single:
        return next(iter(single.keys()))
    return f
