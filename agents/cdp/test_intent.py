# -*- coding: utf-8 -*-
"""识别对话是否应开启 CDP 测试任务（手动步骤 / 迭代计划用例）。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_MANUAL_TEST_MARKERS = (
    "怎么测", "如何测", "测试步骤", "按以下", "按如下", "执行测试", "跑一下",
    "验证一下", "测一下", "端到端", "ui测试", "界面测试", "探测性", "探索性",
    "先打开", "然后点击", "再点击", "步骤1", "步骤 1", "1.", "2.",
)

_TESTCASE_MARKERS = (
    "测试用例", "testcase", "test case", "用例测试", "跑用例", "执行用例",
    "按用例", "用这个用例", "用迭代", "计划里的用例", "计划下的用例",
)

_CDP_ACTIONS_WITH_TASK = frozenset({
    "explore", "assert", "navigate", "click", "fill", "wait", "get_text",
})


def _blob(*parts: Optional[str]) -> str:
    return " ".join(str(p or "") for p in parts).strip()


def detect_cdp_test_intent(
    *,
    user_input: str = "",
    todo: str = "",
    tool_action: str = "",
    context: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    返回是否应开启 cdp_test_run 及模式。

    mode: manual | testcase | explore | None
    """
    ctx = context or {}
    par = params or {}
    if par.get("test_task") is False or par.get("open_test_task") is False:
        return {"should_open": False, "mode": None, "reason": "explicit_off"}

    act = (tool_action or par.get("action") or "").strip().lower()
    if act in ("session", "close", "list", "list_sessions", "login"):
        if act != "login" or not _mentions_test(_blob(user_input, todo)):
            return {"should_open": False, "mode": None}

    text = _blob(user_input, todo, ctx.get("matched_skill") or "")
    lower = text.lower()

    if par.get("test_task") is True or par.get("open_test_task") is True:
        return {
            "should_open": True,
            "mode": _infer_mode(text, act, ctx),
            "reason": "explicit_on",
        }

    testcase_mode = _implies_testcase_run(text, lower, ctx)
    manual_mode = _implies_manual_test(text, lower)
    explore_mode = act == "explore" or "探测" in text or "explore" in lower

    if testcase_mode:
        return {
            "should_open": True,
            "mode": "testcase",
            "reason": "testcase_intent",
            "load_plan_testcases": True,
        }
    if explore_mode and act in _CDP_ACTIONS_WITH_TASK:
        return {"should_open": True, "mode": "explore", "reason": "explore_action"}
    if manual_mode and act in _CDP_ACTIONS_WITH_TASK.union({"login", ""}):
        return {"should_open": True, "mode": "manual", "reason": "manual_test_description"}
    if act in ("assert", "explore"):
        return {"should_open": True, "mode": act, "reason": f"action_{act}"}
    if _mentions_test(text) and act in _CDP_ACTIONS_WITH_TASK:
        return {"should_open": True, "mode": "manual", "reason": "cdp_with_test_wording"}

    return {"should_open": False, "mode": None}


def _mentions_test(text: str) -> bool:
    t = text.lower()
    if "测试" in text or "test" in t:
        return True
    return any(m in text or m in t for m in _MANUAL_TEST_MARKERS)


def _implies_testcase_run(text: str, lower: str, ctx: Dict[str, Any]) -> bool:
    if any(m in text or m in lower for m in _TESTCASE_MARKERS):
        if any(v in text for v in ("执行", "跑", "用", "按", "测试", "测")):
            return True
        if ctx.get("first_testcase_id") or ctx.get("grep_result", {}).get("first_testcase_id"):
            return True
    if "迭代" in text and "测试用例" in text:
        return True
    return False


def _implies_manual_test(text: str, lower: str) -> bool:
    if any(m in text or m in lower for m in _MANUAL_TEST_MARKERS):
        return True
    if re.search(r"^\s*\d+[.、)]\s*\S+", text, re.M):
        return True
    if re.search(r"(先|然后|接着|最后).{0,20}(打开|点击|输入|登录|访问)", text):
        return True
    return False


def _infer_mode(text: str, action: str, ctx: Dict[str, Any]) -> str:
    lower = text.lower()
    if _implies_testcase_run(text, lower, ctx):
        return "testcase"
    if action == "explore":
        return "explore"
    return "manual"


def extract_testcase_ids_from_context(context: Optional[Dict[str, Any]]) -> List[int]:
    ctx = context or {}
    ids: List[int] = []
    for key in ("testcase_ids", "target_testcase_ids"):
        raw = ctx.get(key)
        if isinstance(raw, list):
            for x in raw:
                try:
                    ids.append(int(x))
                except (TypeError, ValueError):
                    pass
    for key in ("first_testcase_id",):
        try:
            v = ctx.get(key) or (ctx.get("grep_result") or {}).get(key)
            if v is not None:
                ids.append(int(v))
        except (TypeError, ValueError):
            pass
    out: List[int] = []
    seen = set()
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
