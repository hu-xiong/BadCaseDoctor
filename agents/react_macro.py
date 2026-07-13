# -*- coding: utf-8 -*-
"""
推理 / 执行分离（frozen_macro）：

- **推理阶段**：一次定案多步工具链（task_plan → steps[]）。
- **执行阶段**：顺序跑工具；**有依赖的后继步骤**用轻量 LLM 仅解析该步 params（无 observation/thinking/decide 三段式）。

见 docs/需求文档_下一轮性能优化_推理执行分离总结与响应形态.md §3。
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from agents.intent_guards import user_modify_intent

# plan 文案 → 工具名（顺序扫描 task_plan）
_MACRO_TOOL_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("grep", ("grep", "检索", "搜索", "查找", "定位", "search")),
    ("modify", ("modify", "修改", "更新", "改为", "改成", "状态", "负责人")),
    ("create", ("create", "新建", "创建", "新增")),
    ("delete", ("delete", "删除")),
    ("copy", ("copy", "复制", "拷贝", "duplicate")),
    ("terminal", ("terminal", "shell", "命令行", "终端")),
    ("cdp", ("cdp", "浏览器", "browser", "ui测试", "登录页", "snapshot")),
)


def use_react_macro_grep_modify() -> bool:
    """REACT_MACRO_GREP_MODIFY=1：强制启用；=0 强制关闭。"""
    return (os.getenv("REACT_MACRO_GREP_MODIFY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def macro_execution_separation_enabled(
    plan_steps: Optional[List[str]] = None,
    *,
    has_frozen_macro: bool = False,
) -> bool:
    """
    推理/执行分离总开关：
    - REACT_MACRO_GREP_MODIFY=0 → 关
    - REACT_MACRO_GREP_MODIFY=1 → 开（无 plan 也尝试冻结）
    - 未设置：REACT_MACRO_AUTO=1（默认）且 task_plan 可解析为 ≥2 步工具链 → 开
    """
    if has_frozen_macro:
        return True
    v = (os.getenv("REACT_MACRO_GREP_MODIFY") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    auto = (os.getenv("REACT_MACRO_AUTO", "1") or "1").strip().lower()
    if auto in ("0", "false", "no", "off"):
        return False
    ps = plan_steps if isinstance(plan_steps, list) else []
    return len(plan_steps_to_macro_steps(ps, user_input="")) >= 2


def use_react_frozen_macro(
    plan_steps: Optional[List[str]] = None,
    *,
    has_frozen_macro: bool = False,
) -> bool:
    return macro_execution_separation_enabled(
        plan_steps, has_frozen_macro=has_frozen_macro
    )


def use_react_macro_skip_inter_decide() -> bool:
    """REACT_MACRO_SKIP_INTER_DECIDE=1（默认）：宏步骤之间跳过 unified decide LLM。"""
    return (os.getenv("REACT_MACRO_SKIP_INTER_DECIDE", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def use_react_macro_params_llm() -> bool:
    """REACT_MACRO_PARAMS_LLM=1（默认）：后继步骤用轻量 LLM 仅解析工具 params JSON。"""
    return (os.getenv("REACT_MACRO_PARAMS_LLM", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def macro_params_llm_max_tokens() -> int:
    try:
        v = int((os.getenv("REACT_MACRO_PARAMS_MAX_TOKENS") or "512").strip())
        return max(64, min(v, 1536))
    except (TypeError, ValueError):
        return 512


def use_react_macro_skip_grep_observe() -> bool:
    return (os.getenv("REACT_MACRO_SKIP_GREP_OBSERVE", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# 显式工具名优先序（modify 高于 grep，避免「根据 grep 结果调用 modify」被判成 grep）
_EXPLICIT_TOOL_PRIORITY: Tuple[str, ...] = (
    "modify",
    "create",
    "delete",
    "copy",
    "terminal",
    "grep",
)


def infer_tool_from_plan_line(line: str) -> Optional[str]:
    low = (line or "").lower()
    for tool in _EXPLICIT_TOOL_PRIORITY:
        if re.search(rf"(?<![a-z_]){re.escape(tool)}(?![a-z_])", low):
            return tool
    for tool, kws in _MACRO_TOOL_KEYWORDS:
        if any(k in low for k in kws):
            return tool
    return None


def _coerce_macro_steps_tools(
    steps: List[Dict[str, Any]],
    plan_steps: List[str],
    user_input: str,
) -> List[Dict[str, Any]]:
    """修正 plan 解析错误（常见：第二步文案含 grep 字样却被判成第二步仍 grep）。"""
    if len(steps) < 2:
        return steps
    if steps[0].get("tool") != "grep" or steps[1].get("tool") != "grep":
        return steps
    tail_lines = [str(x or "") for x in (plan_steps or [])[1:]]
    tail_text = " ".join(tail_lines).lower()
    if re.search(r"(?<![a-z_])modify(?![a-z_])", tail_text) or "修改" in tail_text:
        steps[1] = {
            **steps[1],
            "tool": "modify",
            "needs_param_llm": True,
            "depends_on_prev": True,
        }
    elif user_modify_intent(user_input):
        steps[1] = {**steps[1], "tool": "modify", "needs_param_llm": True, "depends_on_prev": True}
    return steps


def plan_steps_to_macro_steps(plan_steps: List[str], *, user_input: str = "") -> List[Dict[str, Any]]:
    """task_plan 文本 → 宏步骤列表；step[0] 参数由推理轮 FC 提供，step[1+] 默认 needs_param_llm。"""
    out: List[Dict[str, Any]] = []
    for i, line in enumerate(plan_steps or []):
        t = infer_tool_from_plan_line(str(line or ""))
        if not t:
            continue
        out.append(
            {
                "tool": t,
                "plan_line": str(line).strip(),
                "needs_param_llm": i > 0,
                "depends_on_prev": i > 0,
            }
        )
    return _coerce_macro_steps_tools(out, plan_steps, user_input)


def plan_steps_imply_grep_then_modify(plan_steps: List[str]) -> bool:
    steps = plan_steps_to_macro_steps(plan_steps, user_input="")
    if len(steps) < 2:
        return False
    return steps[0].get("tool") == "grep" and steps[1].get("tool") == "modify"


def _normalize_modify_field_keys(
    target: str,
    modifications: Dict[str, Any],
    user_input: str = "",
) -> Dict[str, Any]:
    """LLM 字段名与 target 源表不一致时对齐（如 BadCase 的 answer，非 Bug 的 expected_result）。"""
    if not modifications:
        return modifications
    from agents.modify_field_schema import (
        coerce_badcase_modifications_from_user_intent,
        remap_entity_modification_keys,
    )

    out = remap_entity_modification_keys(target, dict(modifications))
    t = (target or "").strip().lower()
    if t in ("badcase", "bad_case") and (user_input or "").strip():
        out = coerce_badcase_modifications_from_user_intent(user_input, out)
    if t == "badcase":
        if "steps_to_reproduce" in out and "reproduction_steps" not in out:
            out["reproduction_steps"] = out.pop("steps_to_reproduce")
        for alias in ("reproduce_steps", "repro_steps"):
            if alias in out and "reproduction_steps" not in out:
                out["reproduction_steps"] = out.pop(alias)
    elif t == "bug":
        for alias in ("reproduction_steps", "reproduce_steps", "repro_steps"):
            if alias in out and "steps_to_reproduce" not in out:
                out["steps_to_reproduce"] = out.pop(alias)
    return out


def _infer_macro_target_hint(
    user_input: str,
    ui_context: Optional[Dict[str, Any]],
) -> str:
    """宏路径 target_hint：UI target 优先，否则从用户话术推断（避免删计划时误写 badcase）。"""
    ui = ui_context if isinstance(ui_context, dict) else {}
    ut = str(ui.get("target") or "").strip().lower()
    if ut in ("bug", "badcase", "testcase", "card", "plan"):
        return ut
    try:
        from agents.intent_guards import infer_modify_target_from_user

        inferred = infer_modify_target_from_user(user_input or "")
        if inferred and inferred != "all":
            return inferred
    except ImportError:
        pass
    return "badcase"


def try_freeze_macro_from_plan(
    *,
    user_input: str,
    ui_context: Optional[Dict[str, Any]],
    plan_steps: List[str],
    round_id: str,
    first_tool: str = "",
    first_tool_params: Optional[Dict[str, Any]] = None,
    intent_hints: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    推理阶段冻结多步宏计划。至少 2 步、可识别工具名；首步须与本轮 FC 工具一致（通常 grep）。
    """
    if not macro_execution_separation_enabled(plan_steps):
        return None

    steps = plan_steps_to_macro_steps(plan_steps, user_input=user_input)
    ui = ui_context if isinstance(ui_context, dict) else {}
    ui_ok = bool(ui.get("record_id") or ui.get("recordId"))

    if len(steps) < 2:
        if not (user_modify_intent(user_input) and ui_ok):
            return None
        steps = [
            {"tool": "grep", "plan_line": "grep", "needs_param_llm": False, "depends_on_prev": False},
            {
                "tool": "modify",
                "plan_line": "modify",
                "needs_param_llm": True,
                "depends_on_prev": True,
            },
        ]

    ft = (first_tool or "").strip().lower()
    if ft and steps and str(steps[0].get("tool") or "").lower() != ft:
        steps[0]["tool"] = ft
    if first_tool_params and steps:
        steps[0]["params_seed"] = dict(first_tool_params)

    hints = dict(intent_hints or {}) if intent_hints else {}

    return {
        "macro_version": 2,
        "source": "plan" if len(plan_steps or []) >= 2 else "rule",
        "macro_phase": "idle",
        "round_id": (round_id or "").strip(),
        "step_index": 0,
        "steps": steps,
        "target_hint": _infer_macro_target_hint(user_input, ui),
        "intent_hints": hints,
        "user_input_snippet": (user_input or "")[:500],
    }


def try_freeze_macro_grep_modify(
    *,
    user_input: str,
    ui_context: Optional[Dict[str, Any]],
    plan_steps: List[str],
    round_id: str,
    modifications: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """兼容旧调用：等价 try_freeze_macro_from_plan（无 first_tool 时从 plan 推断）。"""
    hints = {"modifications": modifications} if modifications else None
    if not user_modify_intent(user_input) and not plan_steps_imply_grep_then_modify(plan_steps):
        if not (ui_context and (ui_context.get("record_id") or ui_context.get("recordId"))):
            return None
    return try_freeze_macro_from_plan(
        user_input=user_input,
        ui_context=ui_context,
        plan_steps=plan_steps,
        round_id=round_id,
        first_tool="grep",
        intent_hints=hints,
    )


def macro_current_step(frozen_macro: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    steps = frozen_macro.get("steps") or []
    idx = int(frozen_macro.get("step_index") or 0)
    if 0 <= idx < len(steps):
        return steps[idx]
    return None


def macro_next_step_spec(frozen_macro: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    steps = frozen_macro.get("steps") or []
    idx = int(frozen_macro.get("step_index") or 0) + 1
    if 0 <= idx < len(steps):
        return steps[idx]
    return None


def clear_frozen_macro(result_ctx: Dict[str, Any], *, reason: str = "") -> None:
    if not isinstance(result_ctx, dict):
        return
    result_ctx.pop("frozen_macro", None)
    if reason and os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
        print(f"[REACT-MACRO] cleared frozen_macro reason={reason!r}", flush=True)


def macro_params_phase_wait_message(
    ui_locale: Optional[str] = None, *, next_tool: str = ""
) -> str:
    """与前端 agentTask.preparingNextStep 一致：宏路径连续执行，非「思考中」。"""
    _ = (next_tool or "").strip() or "tool"
    try:
        from agents.locale_prompts import is_english_locale

        if is_english_locale(ui_locale):
            return "Preparing next step…"
    except Exception:
        pass
    return "正在准备下一步…"


def macro_grep_has_actionable_hit(result_ctx: Dict[str, Any]) -> bool:
    gr = result_ctx.get("grep_result") or {}
    for k in (
        "first_badcase_id",
        "first_bug_id",
        "first_testcase_id",
        "first_card_id",
    ):
        if gr.get(k) not in (None, "", 0, "0"):
            return True
    for lk in ("badcase_list", "bug_list", "testcase_list"):
        lst = gr.get(lk) if isinstance(gr.get(lk), list) else result_ctx.get(lk)
        if isinstance(lst, list) and len(lst) > 0:
            return True
    return False


def macro_step_execution_ok(
    tool_name: str,
    observation: Dict[str, Any],
    result_ctx: Dict[str, Any],
) -> bool:
    if observation.get("success") is not True:
        return False
    if str(tool_name or "").strip().lower() == "grep":
        return macro_grep_has_actionable_hit(result_ctx)
    return True


def _execution_context_for_prompt(
    result_ctx: Dict[str, Any],
    *,
    last_tool: str,
    last_params: Dict[str, Any],
    last_observation: Dict[str, Any],
) -> Dict[str, Any]:
    gr = result_ctx.get("grep_result") or {}
    ctx: Dict[str, Any] = {
        "last_tool": last_tool,
        "last_params": {
            k: last_params.get(k)
            for k in (
                "target",
                "keywords",
                "project_id",
                "plan_id",
                "target_id",
                "modifications",
            )
            if last_params.get(k) is not None
        },
        "last_observation_summary": (
            (last_observation.get("summary") or last_observation.get("message") or "")[:800]
        ),
        "grep_result": {
            k: gr.get(k)
            for k in (
                "first_badcase_id",
                "first_bug_id",
                "first_testcase_id",
                "first_card_id",
                "navigation_ids",
            )
            if gr.get(k) is not None
        },
    }
    for lk in ("badcase_list", "bug_list", "testcase_list"):
        lst = gr.get(lk)
        if isinstance(lst, list) and lst:
            ctx.setdefault("grep_lists", {})[lk] = [
                {
                    "id": r.get("id"),
                    "title": (str(r.get("title") or ""))[:100],
                    "status": r.get("status"),
                }
                for r in lst[:5]
                if isinstance(r, dict)
            ]
    return ctx


def build_macro_step_params_prompt(
    *,
    tool: str,
    step_spec: Dict[str, Any],
    user_input: str,
    ui_context: Optional[Dict[str, Any]],
    execution_context: Dict[str, Any],
    frozen_macro: Dict[str, Any],
) -> str:
    ui = ui_context if isinstance(ui_context, dict) else {}
    ui_slim = {
        k: ui.get(k)
        for k in ("target", "record_id", "recordId", "title", "plan_id", "card_id", "view")
        if ui.get(k) not in (None, "")
    }
    hints = frozen_macro.get("intent_hints") or {}
    plan_line = step_spec.get("plan_line") or ""
    target_hint = str(
        ui.get("target")
        or (execution_context.get("last_params") or {}).get("target")
        or frozen_macro.get("target_hint")
        or "badcase"
    ).strip().lower()
    field_semantics = ""
    if str(tool or "").strip().lower() == "modify":
        from agents.modify_field_schema import modify_field_semantics_for_llm

        field_semantics = modify_field_semantics_for_llm(target_hint)
    return f"""<system>
你是 ReAct **执行阶段**的工具参数解析器。根据用户目标、界面上下文、已完成步骤的结果，为**下一步工具**生成调用参数。

**禁止**：<observation>、<thinking>、<decision> 等 XML；markdown 围栏外的解释；function calling；多工具 JSON 数组。

**只输出一个 JSON 对象**（即工具 params，不要包一层 tool/execute）：
- 工具名固定为：**{tool}**
- modify/create/delete 预览须 `"confirm": false`
- target / target_id 须与 grep 命中实体类型一致（Bug 字段用 target=bug，勿误写 card）
- modifications 须嵌套在 `modifications` 对象内（modify 时）
- **BadCase 复现步骤** 字段名必须用 `reproduction_steps`（禁止用 `steps`，那是 TestCase 的「测试步骤」）
- **Bug 复现步骤** 用 `steps_to_reproduce`
- **字段必须由 user_request 语义决定**：用户写「答案修改为 X」→ modifications 仅 `{{"answer":"X"}}`（**禁止**用 Bug 字段 `expected_result` / `actual_result`）
- BadCase / Bug / TestCase 列名不同（勿混用）：
  - badcase: `answer`, `correct_answer`, `reproduction_steps`, `base_problem`, `case_category`, `priority`, `status`, `badcase_result`, `solution`, `problem_reason`
  - bug: `expected_result`, `actual_result`, `steps_to_reproduce`, `severity`, `priority`
  - testcase: `steps`, `preconditions`, `case_type`, `test_type`, `execution_result`, `related_defects`, `priority`
- **优先级（必守）**：用户说「优先级」「紧急」「P1/P2/P3/P4」「加急」等 → **仅** `modifications.priority`（值如 `"p1"` 或 `"紧急"`）。**禁止**写入 `badcase_result` 或 `status` 表示紧急程度。详情页「优先级」≠「BadCase结果」。
- `badcase_result` **仅**在用户明确要改详情页「BadCase结果」列时使用（如「BadCase结果改为已解决」）。**禁止**把 grep 的「定位结果」、相似问题、评论正文写入 `badcase_result`。
- **评论（必守）**：用户说「添加/追加/写/留 评论」→ modifications **仅** `{{"append_comment":"<正文>"}}`（侧栏评论记录）。正文是「评论」之后的用户原话（如「帮我添加下评论没有改好」→ `"没有改好"`）。**禁止**同时写 base_problem/title/badcase_result 等其它列。
- 示例：用户「优先级改为紧急」→ `{{"target":"badcase","target_id":<grep_id>,"modifications":{{"priority":"p1"}},"confirm":false}}`
- 示例：用户「帮我添加下评论没有改好」→ `{{"target":"badcase","target_id":<grep_id>,"modifications":{{"append_comment":"没有改好"}},"confirm":false}}`
- modifications **只含用户明确要改的那一列**（由 user_request 语义决定）

{field_semantics}
</system>

<user_request>
{(user_input or "")[:1500]}
</user_request>

<ui_context>
{json.dumps(ui_slim, ensure_ascii=False)}
</ui_context>

<plan_step>
{plan_line}
</plan_step>

<execution_context>
{json.dumps(execution_context, ensure_ascii=False, default=str)}
</execution_context>

<intent_hints>
{json.dumps(hints, ensure_ascii=False, default=str)}
</intent_hints>

只输出 JSON：
"""


def parse_macro_tool_params_json(text: str, tool: str) -> Optional[Dict[str, Any]]:
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s).strip()
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(obj, dict):
        return None
    if "params" in obj and isinstance(obj.get("params"), dict):
        obj = obj["params"]
    tn = str(tool or "").strip().lower()
    if tn == "modify":
        mods = obj.get("modifications")
        if not isinstance(mods, dict) or not mods:
            return None
        obj.setdefault("confirm", False)
    if tn in ("create", "delete"):
        obj.setdefault("confirm", False)
    return obj


def _rule_modify_params(
    *,
    user_input: str,
    result_ctx: Dict[str, Any],
    grep_tool_params: Dict[str, Any],
    frozen_macro: Dict[str, Any],
    project_id: Optional[int],
    plan_id: Optional[int],
    ui_context: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    hints = frozen_macro.get("intent_hints") or {}
    mods = dict(hints.get("modifications") or {})
    if not mods:
        return None
    gr = result_ctx.get("grep_result") or {}
    ui = ui_context if isinstance(ui_context, dict) else {}
    target = (
        str(grep_tool_params.get("target") or frozen_macro.get("target_hint") or ui.get("target") or "badcase")
        .strip()
        .lower()
    )
    from agents.modify_target_resolve import resolve_modify_target_id

    target_id = None
    if target == "plan":
        try:
            fp = gr.get("first_plan_id") or result_ctx.get("first_plan_id")
            target_id = int(fp) if fp is not None else None
        except (TypeError, ValueError):
            target_id = None
    elif target == "card":
        cid = gr.get("first_card_id") or ui.get("card_id") or ui.get("record_id") or ui.get("recordId")
        if cid is not None:
            try:
                return {
                    "target": "card",
                    "card_id": int(cid),
                    "modifications": mods,
                    "confirm": False,
                    **({"project_id": project_id} if project_id is not None else {}),
                    **({"plan_id": plan_id} if plan_id is not None else {}),
                }
            except (TypeError, ValueError):
                pass
    else:
        target_id = resolve_modify_target_id(
            target,
            grep_result=gr,
            result_context=result_ctx,
            ui_context=ui,
            user_input=user_input,
        )
    if target_id is None:
        return None
    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        return None
    mods = _normalize_modify_field_keys(target, mods, user_input=user_input)
    params: Dict[str, Any] = {
        "target": target if target in ("bug", "badcase", "testcase", "plan", "card") else "badcase",
        "target_id": target_id,
        "modifications": mods,
        "confirm": False,
    }
    if project_id is not None:
        params["project_id"] = project_id
    if plan_id is not None:
        params["plan_id"] = plan_id
    return params


def _rule_fallback_step_params(
    tool: str,
    *,
    user_input: str,
    result_ctx: Dict[str, Any],
    last_tool: str,
    last_params: Dict[str, Any],
    frozen_macro: Dict[str, Any],
    ui_context: Optional[Dict[str, Any]],
    project_id: Optional[int],
    plan_id: Optional[int],
) -> Optional[Dict[str, Any]]:
    tn = str(tool or "").strip().lower()
    if tn == "modify":
        return _rule_modify_params(
            user_input=user_input,
            result_ctx=result_ctx,
            grep_tool_params=last_params if str(last_tool).lower() == "grep" else {},
            frozen_macro=frozen_macro,
            project_id=project_id,
            plan_id=plan_id,
            ui_context=ui_context,
        )
    if tn == "grep":
        seed = (frozen_macro.get("steps") or [{}])[0].get("params_seed") or last_params
        return dict(seed) if seed else None
    return {"natural_query": (user_input or "")[:500], "confirm": False} if tn in (
        "create",
        "delete",
        "copy",
    ) else None


def build_macro_modify_decision(
    *,
    user_input: str,
    result_ctx: Dict[str, Any],
    grep_tool_params: Dict[str, Any],
    frozen_macro: Dict[str, Any],
    project_id: Optional[int],
    plan_id: Optional[int],
    ui_context: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    params = _rule_modify_params(
        user_input=user_input,
        result_ctx=result_ctx,
        grep_tool_params=grep_tool_params,
        frozen_macro=frozen_macro,
        project_id=project_id,
        plan_id=plan_id,
        ui_context=ui_context,
    )
    if not params:
        return None
    return {
        "execute": True,
        "tool": "modify",
        "params": params,
        "reason": "frozen_macro_rule",
    }


def parse_macro_modify_params_json(text: str) -> Optional[Dict[str, Any]]:
    return parse_macro_tool_params_json(text, "modify")


async def resolve_macro_step_params_llm(
    llm: Any,
    *,
    tool: str,
    step_spec: Dict[str, Any],
    user_input: str,
    ui_context: Optional[Dict[str, Any]],
    result_ctx: Dict[str, Any],
    last_tool: str,
    last_params: Dict[str, Any],
    last_observation: Dict[str, Any],
    frozen_macro: Dict[str, Any],
    collect_llm_text_fn: Any,
    project_id: Optional[int] = None,
    plan_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """有依赖的后继步骤：轻量 LLM 只产出该工具 params；失败则规则兜底。"""
    exec_ctx = _execution_context_for_prompt(
        result_ctx,
        last_tool=last_tool,
        last_params=last_params,
        last_observation=last_observation,
    )
    tn = str(tool or "").strip().lower()
    needs_llm = bool(step_spec.get("needs_param_llm", True))

    if needs_llm and use_react_macro_params_llm() and llm and collect_llm_text_fn:
        prompt = build_macro_step_params_prompt(
            tool=tn,
            step_spec=step_spec,
            user_input=user_input,
            ui_context=ui_context,
            execution_context=exec_ctx,
            frozen_macro=frozen_macro,
        )
        try:
            from llm.prompt_log import maybe_log_agent_prompt

            maybe_log_agent_prompt(
                "macro_step_params_llm",
                prompt,
                extra={"tool": tn, "plan_line": step_spec.get("plan_line")},
            )
        except Exception:
            pass
        t0 = time.perf_counter()
        try:
            raw = await collect_llm_text_fn(
                prompt,
                max_tokens=macro_params_llm_max_tokens(),
                tag="macro_step_params_llm",
            )
        except TypeError:
            raw = await collect_llm_text_fn(prompt, tag="macro_step_params_llm")
        except Exception as ex:
            if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                print(f"[REACT-MACRO] step_params_llm failed tool={tn}: {ex}", flush=True)
            raw = ""
        wall_ms = (time.perf_counter() - t0) * 1000
        parsed = parse_macro_tool_params_json(raw or "", tn)
        if parsed:
            if tn == "modify" and isinstance(parsed.get("modifications"), dict):
                tgt = str(parsed.get("target") or "badcase").strip().lower()
                parsed["modifications"] = _normalize_modify_field_keys(
                    tgt, dict(parsed["modifications"]), user_input=user_input
                )
            if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                print(
                    f"[REACT-MACRO] step_params_llm ok tool={tn} wall_ms={wall_ms:.0f} "
                    f"keys={list(parsed.keys())[:12]}",
                    flush=True,
                )
            if os.getenv("PERF_LOG", "1") == "1":
                print(f"[PERF][react] macro_step_params_llm_ms={wall_ms:.1f} tool={tn}", flush=True)
            return parsed
        if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
            print(
                f"[REACT-MACRO] step_params_llm parse_miss tool={tn} "
                f"raw={(raw or '')[:180]!r}",
                flush=True,
            )

    return _rule_fallback_step_params(
        tn,
        user_input=user_input,
        result_ctx=result_ctx,
        last_tool=last_tool,
        last_params=last_params,
        frozen_macro=frozen_macro,
        ui_context=ui_context,
        project_id=project_id,
        plan_id=plan_id,
    )


def _finalize_tool_params(
    params: Dict[str, Any],
    *,
    tool: str,
    project_id: Optional[int],
    plan_id: Optional[int],
    user_input: str,
    result_ctx: Optional[Dict[str, Any]] = None,
    ui_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    p = dict(params or {})
    tn = str(tool or "").strip().lower()
    if project_id is not None:
        p.setdefault("project_id", project_id)
    if plan_id is not None:
        p.setdefault("plan_id", plan_id)
    nq = (user_input or "").strip()
    if nq:
        p.setdefault("natural_query", nq[:500])
    p.setdefault("userId", "system_agent")
    if tn in ("modify", "create", "delete"):
        p.setdefault("confirm", False)
    if tn in ("modify", "delete") and isinstance(result_ctx, dict):
        from utils.entity_id import sanitize_tool_entity_ids

        p["_resolve_user_input"] = nq
        sanitize_tool_entity_ids(
            tn,
            p,
            grep_result=(result_ctx or {}).get("grep_result") or {},
            result_context=result_ctx,
            ui_context=ui_context,
        )
        p.pop("_resolve_user_input", None)
    return p


async def schedule_macro_next_step_decision(
    llm: Any,
    *,
    frozen_macro: Dict[str, Any],
    completed_tool: str,
    completed_params: Dict[str, Any],
    observation: Dict[str, Any],
    result_ctx: Dict[str, Any],
    user_input: str,
    ui_context: Optional[Dict[str, Any]],
    project_id: Optional[int],
    plan_id: Optional[int],
    collect_llm_text_fn: Any,
) -> Optional[Dict[str, Any]]:
    """
    当前宏步骤执行成功后：若还有下一步，则 LLM/规则解析其 params 并返回 decision（跳过 unified decide）。
 返回 None 表示宏结束或失败（已 clear frozen_macro）。
    """
    if not use_react_macro_skip_inter_decide():
        return None
    if frozen_macro.get("macro_phase") == "fallback":
        return None

    steps = frozen_macro.get("steps") or []
    cur = int(frozen_macro.get("step_index") or 0)
    if cur >= len(steps):
        clear_frozen_macro(result_ctx, reason="macro_index_oob")
        return None

    exp_tool = str(steps[cur].get("tool") or "").strip().lower()
    if exp_tool and exp_tool != str(completed_tool or "").strip().lower():
        clear_frozen_macro(result_ctx, reason="macro_tool_mismatch")
        return None

    if not macro_step_execution_ok(completed_tool, observation, result_ctx):
        clear_frozen_macro(result_ctx, reason=f"step_{cur}_{completed_tool}_not_ok")
        return None

    next_i = cur + 1
    if next_i >= len(steps):
        clear_frozen_macro(result_ctx, reason="macro_complete")
        return None

    next_spec = steps[next_i]
    next_tool = str(next_spec.get("tool") or "").strip().lower()
    if next_tool == "grep" and str(completed_tool or "").strip().lower() == "grep":
        for j in range(next_i, len(steps)):
            alt = str(steps[j].get("tool") or "").strip().lower()
            if alt and alt != "grep":
                next_i = j
                next_spec = steps[j]
                next_tool = alt
                if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                    print(
                        f"[REACT-MACRO] coerce next step grep→{next_tool!r} at index={j}",
                        flush=True,
                    )
                break
        else:
            clear_frozen_macro(result_ctx, reason="macro_repeat_grep_step")
            return None
    if not next_tool:
        clear_frozen_macro(result_ctx, reason="macro_empty_next_tool")
        return None

    frozen_macro["step_index"] = next_i
    frozen_macro["macro_phase"] = "executing"

    _llm_kw = dict(
        llm=llm,
        tool=next_tool,
        step_spec=next_spec,
        user_input=user_input,
        ui_context=ui_context,
        result_ctx=result_ctx,
        last_tool=completed_tool,
        last_params=completed_params,
        last_observation=observation,
        frozen_macro=frozen_macro,
        collect_llm_text_fn=collect_llm_text_fn,
        project_id=project_id,
        plan_id=plan_id,
    )

    async def _resolve_params() -> Optional[Dict[str, Any]]:
        return await resolve_macro_step_params_llm(**_llm_kw)

    if next_tool == "modify":
        from agents.macro_modify_prefetch import parallel_macro_modify_params_llm

        params = await parallel_macro_modify_params_llm(
            _resolve_params,
            result_ctx=result_ctx,
            grep_tool_params=(
                completed_params if str(completed_tool or "").strip().lower() == "grep" else {}
            ),
            frozen_macro=frozen_macro,
            ui_context=ui_context,
            user_input=user_input,
            project_id=project_id,
        )
    else:
        params = await _resolve_params()
    if not params:
        clear_frozen_macro(result_ctx, reason=f"macro_params_failed_{next_tool}")
        return None

    params = _finalize_tool_params(
        params,
        tool=next_tool,
        project_id=project_id,
        plan_id=plan_id,
        user_input=user_input,
        result_ctx=result_ctx,
        ui_context=ui_context,
    )

    if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
        print(
            f"[REACT-MACRO] schedule step {next_i + 1}/{len(steps)} "
            f"tool={next_tool!r} skip_inter_decide=1",
            flush=True,
        )

    _plan_line = str(next_spec.get("plan_line") or "").strip()
    _display_reason = _plan_line or f"执行 {next_tool}"
    return {
        "execute": True,
        "tool": next_tool,
        "params": params,
        "reason": _display_reason,
        "_macro_step_id": f"frozen_macro_step_{next_i}",
    }


# 兼容旧名
async def build_macro_modify_decision_async(
    llm: Any,
    *,
    user_input: str,
    result_ctx: Dict[str, Any],
    grep_tool_params: Dict[str, Any],
    frozen_macro: Dict[str, Any],
    project_id: Optional[int],
    plan_id: Optional[int],
    ui_context: Optional[Dict[str, Any]],
    collect_llm_text_fn: Any,
) -> Optional[Dict[str, Any]]:
    obs = {"success": True, "summary": "grep done"}
    return await schedule_macro_next_step_decision(
        llm,
        frozen_macro=frozen_macro,
        completed_tool="grep",
        completed_params=grep_tool_params,
        observation=obs,
        result_ctx=result_ctx,
        user_input=user_input,
        ui_context=ui_context,
        project_id=project_id,
        plan_id=plan_id,
        collect_llm_text_fn=collect_llm_text_fn,
    )


def should_schedule_macro_modify_after_grep(
    *,
    frozen_macro: Optional[Dict[str, Any]],
    tool_name: str,
    observation: Dict[str, Any],
    result_ctx: Dict[str, Any],
) -> bool:
    if not frozen_macro:
        return False
    nxt = macro_next_step_spec(frozen_macro)
    return (
        str(tool_name or "").strip().lower() == "grep"
        and nxt is not None
        and macro_step_execution_ok(tool_name, observation, result_ctx)
    )

