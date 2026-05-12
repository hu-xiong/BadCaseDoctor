# -*- coding: utf-8 -*-
"""
ReAct 决策步：Function Calling（OpenAI / 百炼 / 千帆 v2 兼容）与现有 parse_xml_decision 结果对齐。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional


def _tool_desc_max_chars() -> int:
    try:
        return max(0, int(os.getenv("REACT_TOOL_DESC_MAX_CHARS", "0") or "0"))
    except Exception:
        return 0


def _fc_decide_excluded_tool_names() -> frozenset:
    """
    ReAct「每步决策」FC 不应暴露的元工具（避免模型先调 get_tool_description 占一整步，grep/modify 永远不执行）。
    REACT_FC_DECIDE_EXCLUDE_TOOLS：逗号分隔，默认 get_tool_description；设为空则不排除。
    """
    raw = (os.getenv("REACT_FC_DECIDE_EXCLUDE_TOOLS", "get_tool_description") or "").strip()
    if not raw or raw.lower() in ("none", "off", "0", "false", "no"):
        return frozenset()
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def build_react_decision_tools_from_registry(tool_registry: Any) -> List[Dict[str, Any]]:
    """从 ToolRegistry 生成 OpenAI 格式 tools；parameters 宽松 object，与现有 params 合并逻辑兼容。"""
    tools: List[Dict[str, Any]] = []
    max_c = _tool_desc_max_chars()
    excluded = _fc_decide_excluded_tool_names()
    reg = getattr(tool_registry, "tools", None) or {}
    for t in reg.values():
        name = getattr(t, "name", None) or ""
        if not name:
            continue
        if name.strip().lower() in excluded:
            continue
        desc = getattr(t, "description", None) or ""
        if max_c > 0 and len(desc) > max_c:
            desc = desc[:max_c].rstrip() + "…"
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc or f"调用工具 {name}",
                    # 千帆 v2：显式 additionalProperties:true 常触发 invalid jsonSchema；仅用 type=object 即可表示「对象入参」
                    "parameters": {
                        "type": "object",
                        "description": "工具入参，与 ReAct XML 决策中 params 一致；尽量给出 project_id、target、keywords、modifications 等。",
                    },
                },
            }
        )
    return tools


def _tool_call_first_function(tc: Any) -> Optional[tuple]:
    """返回 (name, arguments_str)。"""
    fn = getattr(tc, "function", None)
    if fn is None and isinstance(tc, dict):
        fn = tc.get("function")
    if fn is None:
        return None
    if isinstance(fn, dict):
        name = fn.get("name") or ""
        args = fn.get("arguments")
    else:
        name = getattr(fn, "name", None) or ""
        args = getattr(fn, "arguments", None)
    if not isinstance(name, str):
        name = str(name or "")
    if args is None:
        args = "{}"
    if not isinstance(args, str):
        args = json.dumps(args, ensure_ascii=False)
    return name.strip(), args


def decision_from_assistant_message(msg: Any) -> Optional[Dict[str, Any]]:
    """
    若存在 tool_calls，解析为与 parse_xml_decision 一致的核心字段；
    若无 tool_calls，返回 None（由调用方对 content 走 parse_xml_decision）。
    多路 tool_calls 时仅取第一条（ReAct 每步单工具），并打日志。
    """
    tcs = getattr(msg, "tool_calls", None)
    content = getattr(msg, "content", None) or ""
    if isinstance(msg, dict):
        tcs = msg.get("tool_calls")
        content = msg.get("content") or ""

    if not tcs:
        return None

    if isinstance(tcs, (list, tuple)) and len(tcs) > 1:
        print(f"[REACT-FC] 收到 {len(tcs)} 个 tool_calls，ReAct 单步仅使用第一条")

    tc = tcs[0]
    pair = _tool_call_first_function(tc)
    if not pair:
        return None
    name, arg_str = pair
    name = (name or "").strip().lower()
    try:
        params = json.loads(arg_str) if arg_str.strip() else {}
    except json.JSONDecodeError as e:
        print(f"[REACT-FC] arguments JSON 解析失败: {e} raw={arg_str[:200]!r}")
        return {
            "execute": False,
            "tool": "",
            "params": {},
            "reason": f"function_call_arguments_invalid:{e}",
        }

    if not isinstance(params, dict):
        params = {"value": params}

    out = {
        "execute": True,
        "tool": name,
        "params": params,
        "reason": f"function_call:{name}",
    }
    if name == "modify" and "confirm" not in out["params"]:
        out["params"]["confirm"] = False
    if name == "create" and "confirm" not in out["params"]:
        out["params"]["confirm"] = False
    if name == "delete" and "confirm" not in out["params"]:
        out["params"]["confirm"] = False
    return out


def use_react_decide_function_call() -> bool:
    return os.getenv("REACT_DECIDE_FUNCTION_CALL", "").strip().lower() in ("1", "true", "yes")


def use_react_decide_fc_stream() -> bool:
    """REACT_DECIDE_FC_STREAM=1（默认）：decide 步 FC 用流式 tool_calls，边收边推 agent_thought；需 LLM 实现 chat_completion_with_tools_stream。"""
    return (os.getenv("REACT_DECIDE_FC_STREAM", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


class FcStreamAccumulator:
    """累积 OpenAI 兼容流式 chunk，构建 assistant message（content + tool_calls）。"""

    def __init__(self) -> None:
        self.content_parts: List[str] = []
        self._tc_slots: Dict[int, Dict[str, Any]] = {}

    def _delta_obj(self, chunk: Any) -> Any:
        if chunk is None:
            return None
        if isinstance(chunk, dict):
            ch0 = (chunk.get("choices") or [None])[0] or {}
            return ch0.get("delta") if isinstance(ch0, dict) else None
        try:
            if not chunk.choices:
                return None
            return chunk.choices[0].delta
        except Exception:
            return None

    def feed(self, chunk: Any) -> str:
        """
        处理一条流式 chunk；返回本轮可下发的正文增量（供 agent_thought）。
        """
        delta = self._delta_obj(chunk)
        if delta is None:
            return ""
        out = ""
        # content
        c = getattr(delta, "content", None)
        if c is None and isinstance(delta, dict):
            c = delta.get("content")
        if isinstance(c, str) and c:
            self.content_parts.append(c)
            out = c
        # tool_calls fragments
        tcs = getattr(delta, "tool_calls", None)
        if tcs is None and isinstance(delta, dict):
            tcs = delta.get("tool_calls")
        if not tcs:
            return out
        if not isinstance(tcs, (list, tuple)):
            tcs = [tcs]
        for tc in tcs:
            self._merge_tool_call_fragment(tc)
        return out

    def _merge_tool_call_fragment(self, tc: Any) -> None:
        idx = getattr(tc, "index", None)
        if idx is None and isinstance(tc, dict):
            idx = tc.get("index")
        if idx is None:
            idx = 0
        try:
            idx = int(idx)
        except Exception:
            idx = 0
        slot = self._tc_slots.setdefault(
            idx, {"id": "", "name": "", "arguments": "", "type": "function"}
        )
        tid = getattr(tc, "id", None)
        if tid is None and isinstance(tc, dict):
            tid = tc.get("id")
        if isinstance(tid, str) and tid.strip():
            slot["id"] = tid.strip()
        typ = getattr(tc, "type", None)
        if typ is None and isinstance(tc, dict):
            typ = tc.get("type")
        if isinstance(typ, str) and typ.strip():
            slot["type"] = typ.strip()
        fn = getattr(tc, "function", None)
        if fn is None and isinstance(tc, dict):
            fn = tc.get("function")
        if fn is not None:
            nm = getattr(fn, "name", None)
            if nm is None and isinstance(fn, dict):
                nm = fn.get("name")
            if isinstance(nm, str) and nm.strip():
                slot["name"] = nm.strip()
            arg = getattr(fn, "arguments", None)
            if arg is None and isinstance(fn, dict):
                arg = fn.get("arguments")
            if isinstance(arg, str) and arg:
                slot["arguments"] = str(slot.get("arguments", "")) + arg

    def build_assistant_message(self) -> Dict[str, Any]:
        content = "".join(self.content_parts).strip()
        if not self._tc_slots:
            return {"role": "assistant", "content": content, "tool_calls": None}
        tool_calls: List[Dict[str, Any]] = []
        for idx in sorted(self._tc_slots.keys()):
            s = self._tc_slots[idx]
            name = (s.get("name") or "").strip()
            tid = (s.get("id") or f"call_{idx}").strip()
            args = s.get("arguments")
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False) if args is not None else "{}"
            tool_calls.append(
                {
                    "id": tid,
                    "type": s.get("type") or "function",
                    "function": {"name": name, "arguments": args},
                }
            )
        return {"role": "assistant", "content": content, "tool_calls": tool_calls}


THINK_FC_TOOL = "submit_react_think"
OBSERVE_FC_TOOL = "submit_observe_analysis"


def use_react_think_fc() -> bool:
    """REACT_THINK_FC=1（默认）：首轮 THINK 用 function calling（submit_react_think），不再要求 <todo_list>/[GATE] 正文。"""
    return (os.getenv("REACT_THINK_FC", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def use_react_observe_fc() -> bool:
    """REACT_OBSERVE_FC=1（默认）：observe 步用 submit_observe_analysis，不再要求 <result> XML。"""
    return (os.getenv("REACT_OBSERVE_FC", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def use_react_merge_first_think_into_decide() -> bool:
    """
    REACT_MERGE_FIRST_THINK_INTO_DECIDE=0（默认 1）：跳过独立首轮 THINK；门控与 todo_items（及可选首工具）
    在主循环第 0 步通过 **submit_react_think** 一次 FC 完成，正文三段推断走 agent_thought 流。
    """
    v = (os.getenv("REACT_MERGE_FIRST_THINK_INTO_DECIDE", "1") or "1").strip().lower()
    # 默认启用合并模式，只有明确设置 0/false/no/off 才关闭
    return v not in ("0", "false", "no", "off")


def use_react_decide_xml_fallback() -> bool:
    """REACT_DECIDE_XML_FALLBACK=0（默认）：decide 仅 tool_calls，不回退 parse_xml_decision。"""
    return (os.getenv("REACT_DECIDE_XML_FALLBACK", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def use_react_think_xml_fallback() -> bool:
    """REACT_THINK_XML_FALLBACK=0（默认）：THINK FC 失败时不回退 XML 解析。"""
    return (os.getenv("REACT_THINK_XML_FALLBACK", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def use_react_observe_xml_fallback() -> bool:
    """REACT_OBSERVE_XML_FALLBACK=0（默认）：observe FC 失败时不回退 parse_xml_findings。"""
    return (os.getenv("REACT_OBSERVE_XML_FALLBACK", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def build_react_think_fc_tools() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": THINK_FC_TOOL,
                "description": (
                    "提交本轮 THINK 推断结果（三选一）："
                    "(1) 单步可直驱工具：need_tools=true, need_todo_list=false, todo_items=[]；"
                    "(2) 多步或需展示计划：need_tools=true, need_todo_list=true 且填写 todo_items；"
                    "(3) 闲聊/无需查改项目数据：need_tools=false 且填写 message。"
                    "必须调用且仅调用本函数一次。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "need_tools": {
                            "type": "boolean",
                            "description": (
                                "是否需要查询/修改项目内 Bug/BadCase/测试用例等。false=仅文字闲聊答复（填 message）。"
                            ),
                        },
                        "need_todo_list": {
                            "type": "boolean",
                            "description": (
                                "是否下发用户可见的 Todo/规划备忘。false=单步原子动作已明确，系统直驱工具决策，"
                                "且必须配合 todo_items=[]。true=多步或需展示计划，须填 todo_items。"
                            ),
                        },
                        # 千帆 v2：anyOf / type:null 易报 invalid jsonSchema；未强调 plan UI 时请省略本字段，勿传 null
                        "need_plan_ui": {
                            "type": "boolean",
                            "description": "有 Todo 时是否在侧栏强调展示规划备忘；可与 need_todo_list 独立。",
                        },
                        "message": {
                            "type": "string",
                            "description": "need_tools=false 时必填：2～4 句友好回复（寒暄、无关闲聊、或仅澄清且暂不操作）。",
                        },
                        "todo_items": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 12,
                            "description": "仅当 need_todo_list=true：每步一条可执行描述。need_todo_list=false 时必须为空数组。",
                        },
                        "first_tool": {
                            "type": "string",
                            "description": (
                                "need_tools=true 且已明确首步时填写：即将调用的工具名（如 grep、modify、create、"
                                "database_query、browser_test、search 等），与决策步 FC 一致；未就绪可省略，系统再用首条 Todo 补决策。"
                            ),
                        },
                        # 部分网关不接受 additionalProperties: true；用无 properties 的空 object 表示「任意键值」。
                        "first_params": {
                            "type": "object",
                            "description": "与 first_tool 配套的参数对象（含 project_id、target、keywords 等）；无首步则省略。",
                        },
                    },
                    "required": ["need_tools", "need_todo_list"],
                },
            },
        }
    ]


def build_react_observe_fc_tools() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": OBSERVE_FC_TOOL,
                "description": "提交本步工具结果的结构化观察结论，供下一步决策。必须调用且仅调用本函数一次。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "findings": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "关键发现（若干条短句）。",
                        },
                        "context_update": {
                            "type": "object",
                            "description": "写入后续轮次上下文的键值对象（如 grep 列表、target_id 线索）；可为空对象 {}。",
                        },
                        "next_step": {
                            "type": "string",
                            "description": "对下一步的建议或注意点。",
                        },
                    },
                    "required": ["findings", "context_update", "next_step"],
                },
            },
        }
    ]


def _iter_balanced_brace_objects(text: str):
    """从左到右扫描，产出每个与 {...} 平衡的子串（用于正文内嵌 JSON 兜底）。"""
    if not text:
        return
    start = 0
    n = len(text)
    while start < n:
        j = text.find("{", start)
        if j < 0:
            return
        depth = 0
        for k in range(j, n):
            ch = text[k]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield text[j : k + 1]
                    start = k + 1
                    break
        else:
            return


def think_fc_try_parse_from_content(content: Any) -> Optional[Dict[str, Any]]:
    """
    千帆等偶发只返正文、arguments 写在 content：若含 need_tools + need_todo_list 则视为 submit_react_think 载荷。
    """
    if content is None:
        return None
    if not isinstance(content, str):
        content = str(content)
    text = content.strip()
    if not text:
        return None
    candidates: List[str] = []

    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE):
        inner = (m.group(1) or "").strip()
        if inner.startswith("{"):
            candidates.append(inner)
    for sub in _iter_balanced_brace_objects(text):
        if sub not in candidates:
            candidates.append(sub)
    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        try:
            d = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict):
            continue
        if "need_tools" not in d or "need_todo_list" not in d:
            continue
        return _normalize_think_fc_params_dict(d)
    return None


def _tool_calls_list(msg: Any) -> List[Any]:
    tcs = getattr(msg, "tool_calls", None)
    if isinstance(msg, dict):
        tcs = msg.get("tool_calls")
    if not tcs:
        return []
    if isinstance(tcs, (list, tuple)):
        return list(tcs)
    return [tcs]


def _normalize_think_fc_params_dict(params: Dict[str, Any]) -> Dict[str, Any]:
    ft = params.get("first_tool")
    first_tool = (str(ft).strip() if ft is not None else "") or ""
    fp = params.get("first_params")
    first_params: Dict[str, Any] = fp if isinstance(fp, dict) else {}
    return {
        "need_tools": bool(params.get("need_tools", True)),
        "need_todo_list": bool(params.get("need_todo_list", True)),
        "need_plan_ui": params.get("need_plan_ui"),
        "message": (params.get("message") or "") if isinstance(params.get("message"), str) else "",
        "todo_items": params.get("todo_items") if isinstance(params.get("todo_items"), list) else [],
        "first_tool": first_tool,
        "first_params": first_params,
    }


def think_fc_result_from_assistant_message(msg: Any) -> Optional[Dict[str, Any]]:
    """解析 submit_react_think；无匹配 tool_calls 则尝试从 content 解析 JSON 门控载荷。"""
    for tc in _tool_calls_list(msg):
        pair = _tool_call_first_function(tc)
        if not pair:
            continue
        name, arg_str = pair
        if (name or "").strip().lower() != THINK_FC_TOOL:
            continue
        try:
            params = json.loads(arg_str) if (arg_str or "").strip() else {}
        except json.JSONDecodeError:
            return None
        if not isinstance(params, dict):
            return None
        return _normalize_think_fc_params_dict(params)
    content = getattr(msg, "content", None) or ""
    if isinstance(msg, dict):
        content = msg.get("content") or ""
    return think_fc_try_parse_from_content(content)


def think_fc_payload_from_decision_params(params: Any) -> Optional[Dict[str, Any]]:
    """decision 中 tool=submit_react_think 时 params 字典的直接规范化。"""
    if not isinstance(params, dict):
        return None
    return _normalize_think_fc_params_dict(params)


def observe_fc_result_from_assistant_message(msg: Any) -> Optional[Dict[str, Any]]:
    """解析 submit_observe_analysis → 与 parse_xml_findings 一致的核心字段。"""
    for tc in _tool_calls_list(msg):
        pair = _tool_call_first_function(tc)
        if not pair:
            continue
        name, arg_str = pair
        if name != OBSERVE_FC_TOOL:
            continue
        try:
            params = json.loads(arg_str) if (arg_str or "").strip() else {}
        except json.JSONDecodeError:
            return None
        if not isinstance(params, dict):
            return None
        findings = params.get("findings") or []
        if not isinstance(findings, list):
            findings = [str(findings)]
        else:
            findings = [str(x) for x in findings if x is not None]
        cu = params.get("context_update")
        if not isinstance(cu, dict):
            cu = {}
        ns = params.get("next_step") or ""
        if not isinstance(ns, str):
            ns = str(ns)
        return {"findings": findings, "context_update": cu, "next_step": ns}
    return None
