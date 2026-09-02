# -*- coding: utf-8 -*-
"""
LangGraph 执行引擎：图循环 + 旧引擎领域能力桥接
（grep→modify 门控、实体 ID 补全、modify 沙箱预览、skill/cdp 等全工具）。

默认启用：AGENT_ENGINE=langgraph（见 agent_engine_config）。
回退旧引擎：AGENT_ENGINE=react。
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from typing import Any, Dict, List, Optional, TypedDict, Annotated

from agents.agent_engine_config import langgraph_max_rounds, langgraph_tool_allowlist
from agents.langgraph_bridge import (
    enrich_tool_params_for_execute,
    merge_grep_into_context,
    prepare_mutate_or_coerce_grep,
    preview_side_events_from_observation,
    progress_line_to_sse,
    _lazy_helpers,
)
from agents.langgraph_failure import (
    FailureAction,
    classify_tool_failure,
    failure_edge_sse,
)
from agents.langgraph_resume import (
    apply_langgraph_resume,
    build_langgraph_resume_snapshot,
    format_long_memory_block,
    format_project_hint_block,
    langgraph_resume_sse,
    try_persist_langgraph_interrupt,
    user_input_already_has_terminal_block,
)
from agents.langgraph_recover import (
    advance_task_plan,
    heuristic_task_plan_steps,
    plan_init_sse,
    plan_update_sse,
    replan_forbid_repeat_hint,
    task_plan_enabled,
    try_structured_recover,
)
from agents.langsmith_tracing import (
    run_metadata as langsmith_run_metadata,
    setup_langsmith_tracing,
    tracing_context as langsmith_tracing_context,
)
from agents.langgraph_observe import (
    build_observe_note,
    observe_enabled,
    observe_message,
    observe_sse,
)
from agents.langgraph_checkpointer import (
    get_checkpointer,
    graph_has_checkpoint,
    make_thread_id,
    stream_config,
)
from agents.locale_prompts import (
    react_modify_blocked_after_empty_grep,
    react_unified_grep_no_repeat_message,
)
from agents.react_simplified import (
    _grep_observation_empty_lists,
    _react_should_block_repeat_grep,
)
from agents.react_function_call import (
    build_react_decision_tools_from_registry,
    _fc_decide_excluded_tool_names,
)
from agents.skill_loader import SkillLoader
from agents.skill_registry import skill_registry
from agents.sse_react_v1 import (
    ClientWireType,
    engine_dict_to_wire_packets,
    is_wire_v1_packet,
    react_phase_wire_payload,
    sse_v1_emit_phase_packets_enabled,
)
from agents.locale_prompts import normalize_locale, is_english_locale

try:
    from langgraph.graph import END, START, StateGraph

    _LANGGRAPH_OK = True
except ImportError:  # pragma: no cover
    _LANGGRAPH_OK = False
    END = START = StateGraph = None  # type: ignore


def _append_list(left: Optional[List[Any]], right: Optional[List[Any]]) -> List[Any]:
    return list(left or []) + list(right or [])


def _take_right(left: Any, right: Any) -> Any:
    return right if right is not None else left


class LangGraphAgentState(TypedDict, total=False):
    messages: Annotated[List[Dict[str, Any]], _append_list]
    sse_buffer: Annotated[List[Dict[str, Any]], _append_list]
    result_context: Annotated[Dict[str, Any], _take_right]
    grep_tool_calls: Annotated[int, _take_right]
    grep_attempts: Annotated[int, _take_right]
    last_grep_empty: Annotated[bool, _take_right]
    last_tool: Annotated[str, _take_right]
    last_observation: Annotated[Any, _take_right]
    round_idx: int
    done: bool
    project_id: Any
    plan_id: Any
    user_id: str
    locale: str
    last_error: str
    ui_context: Any
    pending_diff_context: Any
    client_shell: Any
    user_input: str
    # 失败边
    failure_action: Annotated[str, _take_right]
    failure_kind: Annotated[str, _take_right]
    failure_retries: Annotated[int, _take_right]
    # 轻量 task_plan
    task_plan_emitted: Annotated[bool, _take_right]
    task_plan_steps: Annotated[Any, _take_right]
    last_observe: Annotated[str, _take_right]


_SYSTEM_PROMPT_ZH = """你是 BadCaseDoctor 项目助手，通过工具管理 Bug / BadCase / 测试用例 / 计划 / 卡片。
规则：
1. 查询、修改、删除必须调用工具；不要空口说「已完成」而不调工具。
2. 修改或删除前必须先 grep 按标题/关键词定位；不要臆造主键 id。
3. modify 默认走沙箱预览（confirm=false）；用户确认落库时再 confirm=true。
4. 每次只调用一个业务工具；可用 skill_executor 跑预定义技能工作流。
5. 主键 id 用十进制字符串，避免精度丢失。
6. 仅在确已通过工具完成目标，或纯闲聊时，才用自然语言收尾且勿再调工具。
7. 浏览器 cdp（OpenClaw 闭环）：先 snapshot 再 click/fill；UI 变化后必须重新 snapshot。
   click/fill 失败时阅读 observation 的 vision_description 与 agent_hint；
   stale ref 用 new_snapshot_id/focus_hints 换新 @eN 重试一次；
   状态不明时调用 screenshot（会返回视觉描述文本）再决策；登录页用 login，验证码等用户。
"""

_SYSTEM_PROMPT_EN = """You are the BadCaseDoctor assistant. Manage bugs, badcases, test cases, plans, and cards via tools.
Rules:
1. Query/modify/delete MUST use tools; never claim done without tool calls.
2. Always grep by title/keywords before modify/delete; never invent primary key ids.
3. modify defaults to sandbox preview (confirm=false); set confirm=true only to commit.
4. Call one business tool per turn; use skill_executor for predefined skill workflows.
5. Use decimal string ids for primary keys.
6. Reply in natural language without tools only after tools finished the goal, or for chitchat.
7. Browser cdp (OpenClaw loop): snapshot before click/fill; re-snapshot after UI changes.
   On click/fill failure, read vision_description and agent_hint;
   on stale ref, retry once with new_snapshot_id/focus_hints;
   when unsure, call screenshot (returns vision text) then decide; use login for auth pages.
"""


def _truncate_obs(obj: Any, max_chars: int = 12000) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 20] + "…(truncated)"


def _assistant_message_from_resp(resp: Any) -> Any:
    """兼容 OpenAI ChatCompletion 对象，以及 DeepSeek/Qwen 等返回的 assistant dict。"""
    if isinstance(resp, dict):
        # {"role":"assistant","content":...,"tool_calls":[...]} 或 {"choices":[...]}
        if "tool_calls" in resp or resp.get("role") == "assistant" or "content" in resp:
            return resp
        try:
            ch0 = (resp.get("choices") or [None])[0]
            if isinstance(ch0, dict):
                return ch0.get("message") or ch0
        except Exception:
            pass
        return resp
    try:
        return resp.choices[0].message
    except Exception:
        return None


def _tool_call_parts(resp: Any) -> List[Dict[str, Any]]:
    msg = _assistant_message_from_resp(resp)
    if msg is None:
        return []
    if isinstance(msg, dict):
        raw = msg.get("tool_calls") or []
    else:
        raw = getattr(msg, "tool_calls", None) or []
    if not raw:
        return []
    out: List[Dict[str, Any]] = []
    for tc in raw:
        fn = getattr(tc, "function", None) if not isinstance(tc, dict) else None
        if fn is None and isinstance(tc, dict):
            fn = tc.get("function") or {}
            name = (fn.get("name") or "") if isinstance(fn, dict) else ""
            args = (fn.get("arguments") or "{}") if isinstance(fn, dict) else "{}"
            tid = tc.get("id") or ""
        else:
            name = getattr(fn, "name", None) or ""
            args = getattr(fn, "arguments", None) or "{}"
            tid = getattr(tc, "id", None) or ""
        if not isinstance(args, str):
            try:
                args = json.dumps(args, ensure_ascii=False)
            except Exception:
                args = "{}"
        name_s = str(name or "").strip()
        if not name_s:
            continue
        out.append({"id": str(tid or f"call_{len(out)}"), "name": name_s, "arguments": args})
    return out


def _message_content(resp: Any) -> str:
    msg = _assistant_message_from_resp(resp)
    if msg is None:
        return ""
    try:
        if isinstance(msg, dict):
            c = msg.get("content")
        else:
            c = getattr(msg, "content", None)
        return (c or "").strip() if isinstance(c, str) else str(c or "").strip()
    except Exception:
        return ""


class LangGraphReactEngine:
    """与 SimplifiedReActEngine 对齐的流式接口 + LangGraph 循环。"""

    def __init__(self, llm, tool_registry, skill_dir: str = ".qoder/skills"):
        if not _LANGGRAPH_OK:
            raise ImportError(
                "未安装 langgraph，请执行: pip install langgraph\n"
                "或设置 AGENT_ENGINE=react 使用旧引擎"
            )
        self.llm = llm
        self.tools = tool_registry
        self.project_id = None
        self.plan_id = None
        self.db = None
        self.user_id = ""
        self._user_id = ""
        self._ui_locale = "zh"
        self._ui_context: Optional[Dict[str, Any]] = None
        self._agent_session_id: Optional[str] = None
        self._client_shell = None
        self._pending_diff_context_raw: Optional[List[Dict[str, Any]]] = None
        self.skill_loader = SkillLoader(skill_dir)
        self.skill_registry = skill_registry
        self._graph = None
        self._helpers = None
        self._thread_id: Optional[str] = None
        # 与旧引擎 CDP finalize 对齐：routers/agent 读 react_engine._unified_result_ctx
        self._unified_result_ctx: Dict[str, Any] = {}
        try:
            setup_langsmith_tracing()
        except Exception as _ls_ex:
            print(f"[LANGGRAPH] LangSmith setup skipped: {_ls_ex}", flush=True)
        print(f"[LANGGRAPH] 引擎已初始化（含门控/ID补全/沙箱预览/skill），Skill目录: {skill_dir}", flush=True)

    @property
    def helpers(self):
        if self._helpers is None:
            self._helpers = _lazy_helpers(self.llm, self.tools)
            self._helpers.db = self.db
            self._helpers.project_id = self.project_id
            self._helpers.plan_id = self.plan_id
            self._helpers.user_id = self.user_id or self._user_id
            self._helpers._ui_locale = self._ui_locale
            self._helpers._ui_context = self._ui_context
            self._helpers._client_shell = self._client_shell
        else:
            self._helpers.db = self.db
            self._helpers.project_id = self.project_id
            self._helpers.plan_id = self.plan_id
            self._helpers.user_id = self.user_id or self._user_id
            self._helpers._ui_locale = self._ui_locale
            self._helpers._ui_context = self._ui_context
            self._helpers._client_shell = self._client_shell
        return self._helpers

    def _cancel_requested(self) -> bool:
        try:
            from agents.react_simplified import _REACT_STREAM_CANCEL_EVENTS

            aid = self._agent_session_id
            if not aid:
                return False
            ev = _REACT_STREAM_CANCEL_EVENTS.get(str(aid).strip())
            return bool(ev is not None and ev.is_set())
        except Exception:
            return False

    def _register_cancel(self) -> None:
        try:
            from agents.react_simplified import _REACT_STREAM_CANCEL_EVENTS

            aid = (self._agent_session_id or "").strip()
            if aid:
                _REACT_STREAM_CANCEL_EVENTS[aid] = threading.Event()
        except Exception:
            pass

    def _unregister_cancel(self) -> None:
        try:
            from agents.react_simplified import _REACT_STREAM_CANCEL_EVENTS

            aid = (self._agent_session_id or "").strip()
            if aid:
                _REACT_STREAM_CANCEL_EVENTS.pop(aid, None)
        except Exception:
            pass

    def _openai_tools(self) -> List[Dict[str, Any]]:
        allow = langgraph_tool_allowlist()
        excluded = set(_fc_decide_excluded_tool_names())
        # 仍排除「占一步只读说明」的元工具；skill/cdp/terminal 默认放开
        excluded |= {"get_tool_description"}
        tools = build_react_decision_tools_from_registry(self.tools)
        filtered: List[Dict[str, Any]] = []
        for t in tools:
            fn = (t.get("function") or {}) if isinstance(t, dict) else {}
            name = str(fn.get("name") or "").strip().lower()
            if not name or name in excluded:
                continue
            if allow is not None and name not in allow:
                continue
            filtered.append(t)
        return filtered

    def _system_prompt(self, locale: Optional[str]) -> str:
        if is_english_locale(normalize_locale(locale)):
            return _SYSTEM_PROMPT_EN
        return _SYSTEM_PROMPT_ZH

    async def _llm_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Any:
        import inspect

        fn = getattr(self.llm, "chat_completion_with_tools", None)
        if fn is None:
            raise RuntimeError(f"LLM {type(self.llm).__name__} 不支持 chat_completion_with_tools")
        imgs = getattr(self, "_react_stream_images", None)
        kw: Dict[str, Any] = {"tool_choice": "auto", "parallel_tool_calls": False}
        try:
            sig = inspect.signature(fn)
            if imgs and "images" in sig.parameters:
                kw["images"] = imgs
        except Exception:
            pass

        def _call():
            return fn(messages, tools, **kw)

        return await asyncio.to_thread(_call)

    def _snapshot_and_emit_resume(
        self,
        sse: List[Dict[str, Any]],
        state: Dict[str, Any],
        *,
        messages_delta: List[Dict[str, Any]],
        result_context: Dict[str, Any],
        grep_tool_calls: int,
        grep_attempts: int,
        last_grep_empty: bool,
        failure_retries: int,
        failure_action: str,
        failure_kind: str,
        reason: str,
        task_plan_steps: Any = None,
    ) -> Dict[str, Any]:
        prior = list(state.get("messages") or [])
        full_msgs = prior + list(messages_delta or [])
        snap = build_langgraph_resume_snapshot(
            messages=full_msgs,
            result_context=result_context,
            grep_tool_calls=grep_tool_calls,
            grep_attempts=grep_attempts,
            last_grep_empty=last_grep_empty,
            failure_retries=failure_retries,
            failure_action=failure_action,
            failure_kind=failure_kind,
            round_idx=int(state.get("round_idx") or 0),
            user_input=str(state.get("user_input") or ""),
            reason=reason,
            task_plan_steps=task_plan_steps
            if task_plan_steps is not None
            else state.get("task_plan_steps"),
            thread_id=getattr(self, "_thread_id", None),
        )
        sse.append(langgraph_resume_sse(snap, reason=reason))
        self._last_resume_snapshot = snap
        return snap

    async def _execute_prepared_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        *,
        progress_q: Optional[queue.Queue] = None,
    ) -> Dict[str, Any]:
        name = (tool_name or "").strip().lower()
        tool = self.tools.get(name) if self.tools else None
        if tool is None:
            return {"success": False, "error": f"工具不存在: {tool_name}"}
        p = dict(params or {})
        if progress_q is not None and name == "modify":
            p["progress_queue"] = progress_q
        try:
            if name == "skill_executor":
                # SkillExecutorTool.execute(params: dict)
                return await tool.execute(p)
            return await tool.execute(**p)
        except TypeError:
            # 兼容个别工具签名
            try:
                return await tool.execute(params=p)
            except Exception as e:
                return {"success": False, "error": str(e), "message": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e), "message": str(e)}

    def _build_graph(self):
        engine = self

        async def agent_node(state: LangGraphAgentState) -> Dict[str, Any]:
            if state.get("done"):
                return {"sse_buffer": []}
            messages = list(state.get("messages") or [])
            tools = engine._openai_tools()
            round_i = int(state.get("round_idx") or 0)
            sse: List[Dict[str, Any]] = []
            plan_extra: Dict[str, Any] = {}
            if (
                task_plan_enabled()
                and round_i == 0
                and not state.get("task_plan_emitted")
            ):
                _ui = str(state.get("user_input") or "")
                _steps = heuristic_task_plan_steps(_ui, locale=str(state.get("locale") or "zh"))
                sse.append(plan_init_sse(_steps))
                plan_extra = {"task_plan_emitted": True, "task_plan_steps": _steps}

            def _agent_out(d: Dict[str, Any]) -> Dict[str, Any]:
                if plan_extra:
                    d.update(plan_extra)
                return d

            # CDP 续登：用户已提供验证码/凭证时跳过 LLM，直接再调 login
            try:
                from agents.cdp.login_flow import (
                    inject_cdp_login_resume_params,
                    should_auto_resume_cdp_login,
                )

                _rc_login = (
                    state.get("result_context")
                    if isinstance(state.get("result_context"), dict)
                    else {}
                )
                _ui_login = str(state.get("user_input") or "")
                if should_auto_resume_cdp_login(
                    _ui_login,
                    result_context=_rc_login,
                    chat_session_id=getattr(engine, "_chat_session_id", None),
                    project_id=state.get("project_id"),
                ):
                    _login_params: Dict[str, Any] = {"action": "login"}
                    if state.get("project_id") is not None:
                        _login_params["project_id"] = state.get("project_id")
                    inject_cdp_login_resume_params(
                        _login_params,
                        result_context=_rc_login,
                        user_input=_ui_login,
                        chat_session_id=getattr(engine, "_chat_session_id", None),
                        project_id=state.get("project_id"),
                    )
                    _args = json.dumps(_login_params, ensure_ascii=False)
                    _tc_id = f"call_cdp_login_{int(time.time() * 1000) % 1000000}"
                    _hint = (
                        "Resuming CDP login with user-provided credentials/code…"
                        if is_english_locale(state.get("locale"))
                        else "检测到登录凭证/验证码，自动续登…"
                    )
                    sse.append(
                        {
                            "event": "agent_thought",
                            "delta": _hint,
                            "index": round_i,
                        }
                    )
                    sse.append({"event": "agent_thought_done", "index": round_i})
                    sse.append(
                        {
                            "event": "executing",
                            "tool": "cdp",
                            "params": {"action": "login"},
                            "reason": "langgraph:auto_resume_cdp_login",
                            "index": round_i,
                        }
                    )
                    print("[LANGGRAPH] auto resume cdp action=login", flush=True)
                    return _agent_out(
                        {
                            "messages": [
                                {
                                    "role": "assistant",
                                    "content": _hint,
                                    "tool_calls": [
                                        {
                                            "id": _tc_id,
                                            "type": "function",
                                            "function": {
                                                "name": "cdp",
                                                "arguments": _args,
                                            },
                                        }
                                    ],
                                }
                            ],
                            "sse_buffer": sse,
                        }
                    )
            except Exception as _auto_login_ex:
                print(f"[LANGGRAPH] auto resume cdp skipped: {_auto_login_ex}", flush=True)

            # 「测试/打开 + URL」首轮直接开浏览器，避免模型空回复 → 前端「处理完成」
            if round_i == 0:
                try:
                    from agents.cdp.test_intent import detect_browser_url_test_bootstrap

                    _boot = detect_browser_url_test_bootstrap(
                        str(state.get("user_input") or "")
                    )
                    if isinstance(_boot, dict) and _boot.get("url"):
                        _rc_boot = (
                            state.get("result_context")
                            if isinstance(state.get("result_context"), dict)
                            else None
                        )
                        if isinstance(_rc_boot, dict):
                            _rc_boot["_cdp_force_auto_explore"] = True
                            _rc_boot["cdp_target_url"] = _boot["url"]
                        _sess_params: Dict[str, Any] = {
                            "action": "session",
                            "sub_action": "create",
                            "url": _boot["url"],
                            "auto_login": True,
                        }
                        if state.get("project_id") is not None:
                            _sess_params["project_id"] = state.get("project_id")
                        _args = json.dumps(_sess_params, ensure_ascii=False)
                        _tc_id = f"call_cdp_session_{int(time.time() * 1000) % 1000000}"
                        _hint = (
                            f"Opening browser and starting exploratory test for {_boot['url']}…"
                            if is_english_locale(state.get("locale"))
                            else f"正在打开页面并开始探测性测试：{_boot['url']}"
                        )
                        sse.append(
                            {
                                "event": "agent_thought",
                                "delta": _hint,
                                "index": round_i,
                            }
                        )
                        sse.append({"event": "agent_thought_done", "index": round_i})
                        sse.append(
                            {
                                "event": "executing",
                                "tool": "cdp",
                                "params": {
                                    "action": "session",
                                    "url": _boot["url"],
                                },
                                "reason": "langgraph:browser_url_test_bootstrap",
                                "index": round_i,
                            }
                        )
                        print(
                            f"[LANGGRAPH] bootstrap cdp session url={_boot['url']}",
                            flush=True,
                        )
                        _boot_out: Dict[str, Any] = {
                            "messages": [
                                {
                                    "role": "assistant",
                                    "content": _hint,
                                    "tool_calls": [
                                        {
                                            "id": _tc_id,
                                            "type": "function",
                                            "function": {
                                                "name": "cdp",
                                                "arguments": _args,
                                            },
                                        }
                                    ],
                                }
                            ],
                            "sse_buffer": sse,
                        }
                        if isinstance(_rc_boot, dict):
                            _boot_out["result_context"] = _rc_boot
                        return _agent_out(_boot_out)
                except Exception as _boot_ex:
                    print(
                        f"[LANGGRAPH] browser url bootstrap skipped: {_boot_ex}",
                        flush=True,
                    )

            t_llm0 = time.perf_counter()
            try:
                resp = await engine._llm_with_tools(messages, tools)
            except Exception as e:
                return _agent_out({
                    "done": True,
                    "last_error": str(e),
                    "sse_buffer": [
                        {"event": "error", "message": f"LLM 调用失败: {e}"},
                        {"event": "finished", "success": False},
                        {"event": "done"},
                    ],
                })
            think_ms = max(0, int((time.perf_counter() - t_llm0) * 1000))
            content = (_message_content(resp) or "").strip()
            tcs = _tool_call_parts(resp)
            # FC 模型常无 content：补一句「准备调用 xxx」，并下发 reasoning_timing 供前端「思考 Xs」
            thought_text = content
            if not thought_text and tcs:
                tc0n = str(tcs[0].get("name") or "tool").strip() or "tool"
                if is_english_locale(state.get("locale")):
                    thought_text = f"Calling {tc0n}…"
                else:
                    thought_text = f"准备调用 {tc0n}…"
            if thought_text:
                sse.append(
                    {
                        "event": "agent_thought",
                        "delta": thought_text,
                        "index": round_i,
                    }
                )
                sse.append({"event": "agent_thought_done", "index": round_i})
            brief_ms = 800
            sse.append(
                {
                    "event": "reasoning_timing",
                    "segment": "think",
                    "duration_ms": think_ms,
                    "kind": "brief" if think_ms < brief_ms else "normal",
                    "brief_threshold_ms": brief_ms,
                    "index": round_i,
                }
            )
            if not tcs:
                summary = content or ("Done." if is_english_locale(state.get("locale")) else "已完成。")
                sse.extend(
                    [
                        {"event": "summary_stream", "delta": summary},
                        {"event": "finished", "success": True, "summary": summary},
                        {"event": "done"},
                    ]
                )
                return _agent_out({
                    "messages": [{"role": "assistant", "content": content or summary}],
                    "done": True,
                    "sse_buffer": sse,
                })

            tc = tcs[0]
            # 空检索后禁止再 grep（与旧 ReAct REACT_GREP_NO_REPEAT_AFTER_EMPTY 对齐）
            if str(tc.get("name") or "").strip().lower() == "grep":
                prev_obs = state.get("last_observation") if isinstance(state.get("last_observation"), dict) else {}
                prev_act = {"tool": state.get("last_tool") or ""}
                attempts = int(state.get("grep_attempts") or 0)
                # success=false 的空结果不会抬高 grep_tool_calls，用 attempts 兜底
                block, reason = _react_should_block_repeat_grep(
                    prev_observation=prev_obs,
                    prev_action=prev_act,
                    grep_call_count=max(int(state.get("grep_tool_calls") or 0), attempts),
                )
                if state.get("last_grep_empty") or block:
                    loc = state.get("locale")
                    summary = react_unified_grep_no_repeat_message(
                        loc, reason=reason or "empty"
                    )
                    if state.get("last_grep_empty") and not reason:
                        summary = react_modify_blocked_after_empty_grep(loc)
                    sse.extend(
                        [
                            {"event": "agent_thought", "delta": summary + "\n\n", "index": int(state.get("round_idx") or 0)},
                            {"event": "summary_stream", "delta": summary},
                            {"event": "finished", "success": False, "summary": summary},
                            {"event": "done"},
                        ]
                    )
                    return _agent_out({
                        "messages": [{"role": "assistant", "content": summary}],
                        "done": True,
                        "sse_buffer": sse,
                    })
            try:
                exec_params = json.loads(tc["arguments"]) if isinstance(tc.get("arguments"), str) and tc["arguments"].strip() else {}
            except json.JSONDecodeError:
                exec_params = {}
            if not isinstance(exec_params, dict):
                exec_params = {}
            asst_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                ],
            }
            # 注意：本轮不递增 round_idx；tools_node 用同一 index 发 observation，结束后再 +1。
            # 若在此 +1，grep 的 observation 会落到下一格，随后被 modify 标题覆盖，定位结果会挂到 modify 下。
            sse.append(
                {
                    "event": "executing",
                    "tool": tc["name"],
                    "params": exec_params,
                    "reason": thought_text or content or f"调用 {tc['name']}",
                    "index": round_i,
                }
            )
            return _agent_out({
                "messages": [asst_msg],
                "sse_buffer": sse,
            })

        async def tools_node(state: LangGraphAgentState) -> Dict[str, Any]:
            messages = list(state.get("messages") or [])
            if not messages:
                return {"done": True, "sse_buffer": [{"event": "done"}]}
            last = messages[-1]
            tcs = last.get("tool_calls") if isinstance(last, dict) else None
            if not tcs:
                return {"done": True, "sse_buffer": [{"event": "done"}]}
            tc0 = tcs[0]
            fn = tc0.get("function") if isinstance(tc0, dict) else {}
            name = str((fn or {}).get("name") or "").strip()
            arg_str = (fn or {}).get("arguments") or "{}"
            try:
                params = json.loads(arg_str) if isinstance(arg_str, str) and arg_str.strip() else {}
            except json.JSONDecodeError:
                params = {}
            if not isinstance(params, dict):
                params = {"value": params}

            user_input = str(state.get("user_input") or "")
            if not user_input:
                for m in messages:
                    if isinstance(m, dict) and m.get("role") == "user":
                        user_input = str(m.get("content") or "")
                        break

            result_context = dict(state.get("result_context") or {})
            grep_calls = int(state.get("grep_tool_calls") or 0)
            grep_attempts = int(state.get("grep_attempts") or 0)
            last_grep_empty = bool(state.get("last_grep_empty"))
            project_id = state.get("project_id")
            plan_id = state.get("plan_id")
            locale = normalize_locale(state.get("locale"))
            ui_context = state.get("ui_context") if isinstance(state.get("ui_context"), dict) else None
            pending = state.get("pending_diff_context")
            client_shell = state.get("client_shell") if isinstance(state.get("client_shell"), dict) else None
            user_id = str(state.get("user_id") or "")

            # 1) grep→modify 门控（可同轮 coerce 为 grep；空结果后禁止再 coerce）
            name, params, block_msg = prepare_mutate_or_coerce_grep(
                helpers=engine.helpers,
                tool_name=name,
                tool_params=params,
                user_input=user_input,
                result_context=result_context,
                grep_tool_calls=grep_calls,
                project_id=project_id,
                plan_id=plan_id,
                ui_context=ui_context,
                locale=locale,
                grep_attempts=grep_attempts,
                last_grep_empty=last_grep_empty,
            )
            sse: List[Dict[str, Any]] = []
            if block_msg:
                sse.append({"event": "agent_thought", "delta": block_msg + "\n\n", "index": int(state.get("round_idx") or 0)})
                obs = {
                    "success": False,
                    "blocked": True,
                    "reason": "grep_required_before_modify",
                    "message": block_msg,
                    "attempted_tool": name,
                }
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": str(tc0.get("id") or "call_0"),
                    "name": name,
                    "content": _truncate_obs(obs),
                }
                sse.append(
                    {
                        "event": "observation",
                        "tool": name,
                        "data": obs,
                        "observation": obs,
                        "success": False,
                        "index": int(state.get("round_idx") or 0),
                    }
                )
                # 空结果阻断：直接收尾，勿再回 agent 空转
                stop_empty = last_grep_empty or "未命中" in block_msg or "no matching" in block_msg.lower()
                prev_fail_retries = int(state.get("failure_retries") or 0)
                out_block: Dict[str, Any] = {
                    "messages": [tool_msg],
                    "sse_buffer": sse,
                    "last_tool": name,
                    "last_observation": obs,
                    "failure_retries": prev_fail_retries,
                }
                if stop_empty:
                    out_block["done"] = True
                    out_block["failure_action"] = FailureAction.STOP.value
                    out_block["failure_kind"] = "empty_grep"
                    sse.extend(
                        [
                            {"event": "summary_stream", "delta": block_msg},
                            {"event": "finished", "success": False, "summary": block_msg},
                            {"event": "done"},
                        ]
                    )
                else:
                    # 门控拦截但尚可纠错 → retry / 耗尽则 interrupt
                    decision = classify_tool_failure(
                        tool_name=name,
                        observation=obs,
                        failure_retries=prev_fail_retries,
                        grep_empty=False,
                        client_pause=False,
                        locale=locale,
                    )
                    out_block["failure_action"] = decision.action.value
                    out_block["failure_kind"] = decision.kind
                    if decision.action in (FailureAction.RETRY, FailureAction.REPLAN):
                        out_block["failure_retries"] = prev_fail_retries + 1
                        if decision.hint:
                            out_block["messages"] = [
                                tool_msg,
                                {"role": "user", "content": decision.hint},
                            ]
                        sse.append(failure_edge_sse(decision))
                        print(
                            f"[LANGGRAPH] failure_edge(block) action={decision.action.value} "
                            f"kind={decision.kind} retries={out_block['failure_retries']}",
                            flush=True,
                        )
                    elif decision.action == FailureAction.INTERRUPT:
                        out_block["done"] = True
                        out_block["failure_retries"] = prev_fail_retries + 1
                        _ih = decision.hint or block_msg
                        _msgs_d = list(out_block.get("messages") or [tool_msg])
                        engine._snapshot_and_emit_resume(
                            sse,
                            state,
                            messages_delta=_msgs_d,
                            result_context=dict(state.get("result_context") or {}),
                            grep_tool_calls=int(state.get("grep_tool_calls") or 0),
                            grep_attempts=int(state.get("grep_attempts") or 0),
                            last_grep_empty=bool(state.get("last_grep_empty")),
                            failure_retries=out_block["failure_retries"],
                            failure_action=decision.action.value,
                            failure_kind=decision.kind,
                            reason=decision.kind,
                        )
                        sse.append(failure_edge_sse(decision))
                        sse.extend(
                            [
                                {
                                    "event": "interrupt",
                                    "reason": decision.kind,
                                    "summary": _ih,
                                },
                                {"event": "summary_stream", "delta": _ih},
                                {"event": "finished", "success": False, "summary": _ih},
                                {"event": "done"},
                            ]
                        )
                return out_block

            # 若 coerce 改了工具名，更新 executing 提示
            if str((fn or {}).get("name") or "").strip().lower() != name:
                sse.append(
                    {
                        "event": "executing",
                        "tool": name,
                        "params": {},
                        "reason": "langgraph:coerced_grep_before_modify",
                        "index": int(state.get("round_idx") or 0),
                    }
                )

            # 2) ID 补全 + modify 默认预览 + skill context + cdp 续登参数
            params = enrich_tool_params_for_execute(
                helpers=engine.helpers,
                tool_name=name,
                tool_params=params,
                user_input=user_input,
                result_context=result_context,
                project_id=project_id,
                plan_id=plan_id,
                user_id=user_id,
                locale=locale,
                ui_context=ui_context,
                client_shell=client_shell,
                pending_diff_context=pending if isinstance(pending, list) else None,
                chat_session_id=getattr(engine, "_chat_session_id", None),
            )
            executed_name = name
            executed_params = dict(params)

            # 3) 执行（modify 带 progress_queue 透出沙箱预览行）
            progress_q: queue.Queue = queue.Queue()
            exec_task = asyncio.create_task(
                engine._execute_prepared_tool(name, params, progress_q=progress_q)
            )
            while not exec_task.done():
                try:
                    while True:
                        line = progress_q.get_nowait()
                        ev = progress_line_to_sse(str(line))
                        if ev:
                            sse.append(ev)
                except queue.Empty:
                    pass
                await asyncio.sleep(0.05)
            obs = await exec_task
            # drain leftover
            try:
                while True:
                    line = progress_q.get_nowait()
                    ev = progress_line_to_sse(str(line))
                    if ev:
                        sse.append(ev)
            except queue.Empty:
                pass

            if not isinstance(obs, dict):
                obs = {"success": False, "raw": obs}

            # 4) grep 结果写入上下文；空结果/失败则熔断，禁止下一轮再检索
            grep_empty_now = False
            if name == "grep":
                grep_attempts += 1
                grep_empty_now = (not obs.get("success")) or _grep_observation_empty_lists(obs)
                if obs.get("success") and not grep_empty_now:
                    merge_grep_into_context(engine.helpers, obs, params, result_context)
                    grep_calls += 1
                elif grep_empty_now:
                    last_grep_empty = True
                    print(
                        f"[LANGGRAPH] grep empty/fail → stop loop attempts={grep_attempts}",
                        flush=True,
                    )

            # CDP 登录 pending：跨轮验证码/凭证续登
            if name == "cdp":
                try:
                    from agents.cdp.login_flow import update_login_pending_context

                    update_login_pending_context(
                        result_context,
                        obs,
                        chat_session_id=getattr(engine, "_chat_session_id", None),
                        project_id=project_id,
                    )
                except Exception as _cdp_pend_ex:
                    print(f"[LANGGRAPH] cdp login pending update skipped: {_cdp_pend_ex}", flush=True)
                # 与旧引擎对齐：开测试任务 + session 后自动 explore/testcase
                try:
                    from agents.cdp.postprocess import enrich_cdp_observation
                    from agents.cdp.test_task import pop_test_task_sse_buffer

                    _cdp_act = (
                        executed_params.get("action")
                        or executed_params.get("tool_action")
                        or obs.get("action")
                        or ""
                    )
                    obs = await enrich_cdp_observation(
                        engine,
                        obs,
                        action=str(_cdp_act),
                        params=executed_params,
                        project_id=project_id,
                        plan_id=plan_id or executed_params.get("plan_id"),
                        user_query=user_input or "",
                        result_context=result_context,
                        todo="",
                        chat_session_id=getattr(engine, "_chat_session_id", None),
                        react_request_id=getattr(engine, "_agent_session_id", None),
                    )
                    for _tt_ev in pop_test_task_sse_buffer(result_context):
                        if isinstance(_tt_ev, dict):
                            sse.append(_tt_ev)
                    # session 后已自动探测：直接收口，避免模型再说「请等待」
                    _auto_ex = obs.get("cdp_auto_explore") if isinstance(obs, dict) else None
                    if isinstance(_auto_ex, dict) and _auto_ex.get("ran"):
                        _ex_sum = str(
                            obs.get("summary")
                            or _auto_ex.get("summary")
                            or ""
                        ).strip()
                        if not _ex_sum or _ex_sum in (
                            "Exploratory test finished.",
                            "Done.",
                            "已完成。",
                        ):
                            from agents.cdp.auto_run_explore import _build_explore_report

                            _ex_sum = _build_explore_report(
                                obs if isinstance(obs, dict) else {},
                                url=str(
                                    (executed_params or {}).get("url")
                                    or result_context.get("cdp_target_url")
                                    or ""
                                ),
                            )
                        _n_issues = len(
                            obs.get("exploration_issues")
                            or _auto_ex.get("issues")
                            or []
                        )
                        sse.append(
                            {
                                "event": "observation",
                                "tool": "cdp",
                                "data": obs,
                                "observation": obs,
                                "success": bool(
                                    _auto_ex.get("success", obs.get("explore_success", True))
                                ),
                                "index": int(state.get("round_idx") or 0),
                            }
                        )
                        sse.append({"event": "summary_stream", "delta": _ex_sum})
                        sse.append(
                            {
                                "event": "finished",
                                "success": True,
                                "summary": _ex_sum,
                            }
                        )
                        sse.append({"event": "done"})
                        print(
                            f"[LANGGRAPH] auto explore finished → stop loop issues={_n_issues}",
                            flush=True,
                        )
                        return {
                            "messages": [
                                {
                                    "role": "tool",
                                    "tool_call_id": str(tc0.get("id") or "call_0"),
                                    "name": "cdp",
                                    "content": _truncate_obs(obs),
                                }
                            ],
                            "sse_buffer": sse,
                            "result_context": result_context,
                            "last_tool": "cdp",
                            "last_observation": obs,
                            "done": True,
                            "failure_action": FailureAction.STOP.value,
                            "failure_kind": "cdp_auto_explore_done",
                        }
                    if isinstance(obs, dict) and obs.get("cdp_auto_explore_skipped"):
                        print(
                            f"[LANGGRAPH] auto explore skipped: {obs.get('cdp_auto_explore_skipped')}",
                            flush=True,
                        )
                except Exception as _cdp_pp_ex:
                    print(f"[LANGGRAPH] cdp postprocess skipped: {_cdp_pp_ex}", flush=True)

            for side in preview_side_events_from_observation(name, obs):
                sse.append(side)

            # 客户端本机终端 / 本地桥
            if isinstance(obs.get("client_terminal_exec"), dict):
                sse.append({"event": "client_terminal_exec", **obs["client_terminal_exec"]})
            if obs.get("terminal_pause_for_client") and isinstance(obs.get("command"), str):
                sse.append(
                    {
                        "event": "client_terminal_exec",
                        "command": obs.get("command"),
                        "cwd": obs.get("cwd"),
                    }
                )
            if isinstance(obs.get("client_local_run"), dict):
                sse.append({"event": "client_local_run", **obs["client_local_run"]})
            if obs.get("browser_pause_for_client") and isinstance(obs.get("client_browser"), dict):
                sse.append({"event": "client_browser", **obs})

            _client_pause = bool(
                (obs.get("terminal_pause_for_client") and isinstance(obs.get("command"), str))
                or (obs.get("browser_pause_for_client") and isinstance(obs.get("client_browser"), dict))
                or isinstance(obs.get("client_local_run"), dict)
            )

            # 3b) 结构化纠错：modify/delete 失败 → 强制 grep + 补参再执行（不依赖模型）
            ok = bool(obs.get("success", True)) and not obs.get("blocked")
            if (not ok) and (not _client_pause) and (not grep_empty_now):
                _rec = await try_structured_recover(
                    engine=engine,
                    helpers=engine.helpers,
                    tool_name=executed_name,
                    tool_params=executed_params,
                    observation=obs,
                    user_input=user_input,
                    result_context=result_context,
                    grep_tool_calls=grep_calls,
                    grep_attempts=grep_attempts,
                    last_grep_empty=last_grep_empty,
                    project_id=project_id,
                    plan_id=plan_id,
                    user_id=user_id,
                    locale=locale,
                    ui_context=ui_context,
                    client_shell=client_shell,
                    pending_diff_context=pending if isinstance(pending, list) else None,
                    round_idx=int(state.get("round_idx") or 0),
                )
                if _rec is not None:
                    sse.extend(_rec.sse)
                    result_context = _rec.result_context
                    grep_calls = _rec.grep_tool_calls
                    grep_attempts = _rec.grep_attempts
                    last_grep_empty = _rec.last_grep_empty
                    obs = _rec.observation
                    if _rec.recovered:
                        ok = True
                        name = executed_name
                        for side in preview_side_events_from_observation(executed_name, obs):
                            sse.append(side)
                    else:
                        ok = bool(obs.get("success", True)) and not obs.get("blocked")
                        if last_grep_empty:
                            grep_empty_now = True

            # 结构化纠错后可能换成预览/登录等待结果，重新判定停图条件
            _preview_await = bool(
                obs.get("success", True)
                and not obs.get("blocked")
                and (
                    obs.get("confirmation_required") is True
                    or obs.get("preview_only") is True
                )
            )
            _cdp_await_login = bool(
                obs.get("success", True)
                and (
                    obs.get("await_user_credentials") is True
                    or obs.get("await_verification_code") is True
                )
            )

            # 空命中时给模型明确停手指令（即便本轮已 done，也便于日志/前端）
            tool_content_obs = dict(obs)
            if name == "grep" and grep_empty_now:
                tool_content_obs["stop_retry"] = True
                tool_content_obs["agent_hint"] = (
                    "检索无命中，请停止再次调用 grep/modify，直接用自然语言告知用户未找到。"
                )

            tool_msg = {
                "role": "tool",
                "tool_call_id": str(tc0.get("id") or "call_0"),
                "name": name,
                "content": _truncate_obs(tool_content_obs),
            }
            # 推进启发式 task_plan
            _plan_steps = state.get("task_plan_steps")
            _plan_update: Dict[str, Any] = {}
            if isinstance(_plan_steps, list) and _plan_steps:
                _new_plan = advance_task_plan(
                    _plan_steps, name, success=bool(ok) and not grep_empty_now
                )
                sse.append(plan_update_sse(_new_plan, reason=f"after_{name}"))
                _plan_update["task_plan_steps"] = _new_plan

            sse.append(
                {
                    "event": "observation",
                    "tool": name,
                    # 与 SimplifiedReActEngine 对齐：SSE v1 打包读 data=
                    "data": obs,
                    "observation": obs,
                    "success": ok,
                    "index": int(state.get("round_idx") or 0),
                }
            )

            next_round = int(state.get("round_idx") or 0) + 1
            prev_fail_retries = int(state.get("failure_retries") or 0)
            out: Dict[str, Any] = {
                "messages": [tool_msg],
                "sse_buffer": sse,
                "result_context": result_context,
                "grep_tool_calls": grep_calls,
                "grep_attempts": grep_attempts,
                "last_grep_empty": last_grep_empty,
                "last_tool": name,
                "last_observation": obs,
                "round_idx": next_round,
                "failure_action": FailureAction.CONTINUE.value,
                "failure_kind": "ok",
                "failure_retries": prev_fail_retries,
            }
            if _plan_update:
                out.update(_plan_update)
            max_r = langgraph_max_rounds()
            if _client_pause and not grep_empty_now:
                # 交还前端子 Agent：本机终端 / 浏览器；执行完后带 client_terminal_results 续跑
                out["done"] = True
                out["failure_action"] = FailureAction.STOP.value
                out["failure_kind"] = "client_pause"
                result_context["awaiting_client"] = True
                if obs.get("terminal_pause_for_client"):
                    result_context["awaiting_client_terminal"] = True
                    result_context["pending_terminal"] = {
                        "command": obs.get("command"),
                        "cwd": obs.get("cwd"),
                        "timeout": obs.get("timeout"),
                    }
                _pause_sum = str(obs.get("message") or obs.get("summary") or "").strip() or (
                    "等待本机终端子 Agent 完成操作后继续。"
                )
                _pause_reason = (
                    "awaiting_client_terminal"
                    if obs.get("terminal_pause_for_client")
                    else "awaiting_client"
                )
                engine._snapshot_and_emit_resume(
                    sse,
                    state,
                    messages_delta=[tool_msg],
                    result_context=result_context,
                    grep_tool_calls=grep_calls,
                    grep_attempts=grep_attempts,
                    last_grep_empty=last_grep_empty,
                    failure_retries=prev_fail_retries,
                    failure_action=FailureAction.STOP.value,
                    failure_kind=_pause_reason,
                    reason=_pause_reason,
                )
                sse.extend(
                    [
                        {
                            "event": "client_pause",
                            "reason": "terminal" if obs.get("terminal_pause_for_client") else "client",
                            "summary": _pause_sum,
                            "pending_terminal": result_context.get("pending_terminal"),
                        },
                        {"event": "summary_stream", "delta": _pause_sum},
                        {"event": "finished", "success": True, "summary": _pause_sum},
                        {"event": "done"},
                    ]
                )
                out["result_context"] = result_context
            elif _preview_await and not grep_empty_now:
                # 金路径：沙箱预览后停图，侧栏确认落库；禁止模型空转或自行 confirm=true
                out["done"] = True
                out["failure_action"] = FailureAction.STOP.value
                out["failure_kind"] = "preview_await_confirm"
                result_context["awaiting_human"] = True
                result_context["interrupt_reason"] = "preview_await_confirm"
                if isinstance(obs.get("diff"), dict):
                    result_context["pending_modify_preview"] = {
                        "tool": name,
                        "target": obs.get("target") or params.get("target"),
                        "target_id": obs.get("target_id") or params.get("target_id"),
                        "preview_only": True,
                    }
                _prev_sum = str(obs.get("message") or "").strip() or (
                    "预览已生成，请在侧栏确认或拒绝后再继续。"
                    if not locale.lower().startswith("en")
                    else "Preview ready — confirm or reject in the list before continuing."
                )
                engine._snapshot_and_emit_resume(
                    sse,
                    state,
                    messages_delta=[tool_msg],
                    result_context=result_context,
                    grep_tool_calls=grep_calls,
                    grep_attempts=grep_attempts,
                    last_grep_empty=last_grep_empty,
                    failure_retries=prev_fail_retries,
                    failure_action=FailureAction.STOP.value,
                    failure_kind="preview_await_confirm",
                    reason="preview_await_confirm",
                )
                sse.extend(
                    [
                        {
                            "event": "interrupt",
                            "reason": "preview_await_confirm",
                            "summary": _prev_sum,
                        },
                        {"event": "summary_stream", "delta": _prev_sum},
                        {"event": "finished", "success": True, "summary": _prev_sum},
                        {"event": "done"},
                    ]
                )
                out["result_context"] = result_context
                print("[LANGGRAPH] preview_await_confirm → stop for UI confirm", flush=True)
            elif _cdp_await_login and not grep_empty_now:
                # 登录等人手填 / 验证码：停图并写 resume，下一轮续登
                out["done"] = True
                out["failure_action"] = FailureAction.STOP.value
                out["failure_kind"] = "await_login"
                result_context["awaiting_human"] = True
                result_context["interrupt_reason"] = "await_login"
                _login_sum = str(obs.get("message") or "").strip() or (
                    "请在对话中提供登录凭证或验证码后继续。"
                    if not locale.lower().startswith("en")
                    else "Provide credentials or verification code in chat to continue."
                )
                engine._snapshot_and_emit_resume(
                    sse,
                    state,
                    messages_delta=[tool_msg],
                    result_context=result_context,
                    grep_tool_calls=grep_calls,
                    grep_attempts=grep_attempts,
                    last_grep_empty=last_grep_empty,
                    failure_retries=prev_fail_retries,
                    failure_action=FailureAction.STOP.value,
                    failure_kind="await_login",
                    reason="await_login",
                )
                sse.extend(
                    [
                        {
                            "event": "interrupt",
                            "reason": "await_login",
                            "summary": _login_sum,
                        },
                        {"event": "summary_stream", "delta": _login_sum},
                        {"event": "finished", "success": True, "summary": _login_sum},
                        {"event": "done"},
                    ]
                )
                out["result_context"] = result_context
                print("[LANGGRAPH] await_login → stop for user credentials/code", flush=True)
            elif grep_empty_now:
                summary = react_modify_blocked_after_empty_grep(locale)
                out["done"] = True
                out["failure_action"] = FailureAction.STOP.value
                out["failure_kind"] = "empty_grep"
                sse.extend(
                    [
                        {"event": "agent_thought", "delta": summary + "\n\n", "index": int(state.get("round_idx") or 0)},
                        {"event": "summary_stream", "delta": summary},
                        {"event": "finished", "success": False, "summary": summary},
                        {"event": "done"},
                    ]
                )
            elif next_round >= max_r:
                out["done"] = True
                out["failure_action"] = FailureAction.STOP.value
                out["failure_kind"] = "max_rounds"
                sse.extend(
                    [
                        {"event": "summary_stream", "delta": "已达最大工具轮次，停止。"},
                        {"event": "finished", "success": ok},
                        {"event": "done"},
                    ]
                )
            else:
                # 失败边：retry / replan / interrupt
                decision = classify_tool_failure(
                    tool_name=name,
                    observation=obs,
                    failure_retries=prev_fail_retries,
                    grep_empty=False,
                    client_pause=False,
                    locale=locale,
                )
                out["failure_action"] = decision.action.value
                out["failure_kind"] = decision.kind
                if decision.action in (FailureAction.RETRY, FailureAction.REPLAN):
                    out["failure_retries"] = prev_fail_retries + 1
                    _hint = decision.hint or ""
                    if decision.action == FailureAction.REPLAN:
                        _hint = replan_forbid_repeat_hint(
                            tool_name=name,
                            tool_params=executed_params,
                            base_hint=_hint,
                            locale=locale,
                        )
                    if _hint:
                        out["messages"] = [
                            tool_msg,
                            {"role": "user", "content": _hint},
                        ]
                    sse.append(failure_edge_sse(decision))
                    sse.append(
                        {
                            "event": "agent_thought",
                            "delta": f"[{decision.action.value}] {decision.kind}\n",
                            "index": int(state.get("round_idx") or 0),
                        }
                    )
                    print(
                        f"[LANGGRAPH] failure_edge action={decision.action.value} "
                        f"kind={decision.kind} retries={out['failure_retries']}",
                        flush=True,
                    )
                elif decision.action == FailureAction.INTERRUPT:
                    out["done"] = True
                    out["failure_retries"] = prev_fail_retries + 1
                    result_context["awaiting_human"] = True
                    result_context["interrupt_reason"] = decision.kind
                    out["result_context"] = result_context
                    _ih = decision.hint or "需要您补充信息后继续。"
                    _msgs_d = list(out.get("messages") or [tool_msg])
                    engine._snapshot_and_emit_resume(
                        sse,
                        state,
                        messages_delta=_msgs_d,
                        result_context=result_context,
                        grep_tool_calls=grep_calls,
                        grep_attempts=grep_attempts,
                        last_grep_empty=last_grep_empty,
                        failure_retries=out["failure_retries"],
                        failure_action=decision.action.value,
                        failure_kind=decision.kind,
                        reason=decision.kind,
                    )
                    sse.append(failure_edge_sse(decision))
                    sse.extend(
                        [
                            {
                                "event": "interrupt",
                                "reason": decision.kind,
                                "summary": _ih,
                            },
                            {"event": "summary_stream", "delta": _ih},
                            {"event": "finished", "success": False, "summary": _ih},
                            {"event": "done"},
                        ]
                    )
                    print(
                        f"[LANGGRAPH] failure_edge INTERRUPT kind={decision.kind}",
                        flush=True,
                    )
                elif decision.action == FailureAction.STOP:
                    # 兜底：classify 判定 STOP（预览/登录等）但未走上方专用分支
                    out["done"] = True
                    out["failure_retries"] = 0
                    result_context["awaiting_human"] = True
                    result_context["interrupt_reason"] = decision.kind
                    out["result_context"] = result_context
                    _sh = decision.hint or str(obs.get("message") or "已暂停，等待确认。")
                    engine._snapshot_and_emit_resume(
                        sse,
                        state,
                        messages_delta=list(out.get("messages") or [tool_msg]),
                        result_context=result_context,
                        grep_tool_calls=grep_calls,
                        grep_attempts=grep_attempts,
                        last_grep_empty=last_grep_empty,
                        failure_retries=0,
                        failure_action=decision.action.value,
                        failure_kind=decision.kind,
                        reason=decision.kind,
                    )
                    sse.append(failure_edge_sse(decision))
                    sse.extend(
                        [
                            {
                                "event": "interrupt",
                                "reason": decision.kind,
                                "summary": _sh,
                            },
                            {"event": "summary_stream", "delta": _sh},
                            {"event": "finished", "success": True, "summary": _sh},
                            {"event": "done"},
                        ]
                    )
                elif decision.action == FailureAction.CONTINUE:
                    # 成功或无需干预：清零连续失败计数
                    out["failure_retries"] = 0
            return out

        def _route_after_agent(state: LangGraphAgentState) -> str:
            if state.get("done"):
                return "end"
            messages = state.get("messages") or []
            if not messages:
                return "end"
            last = messages[-1]
            if isinstance(last, dict) and last.get("tool_calls"):
                return "tools"
            return "end"

        def _route_after_tools(state: LangGraphAgentState) -> str:
            if state.get("done"):
                return "end"
            fa = str(state.get("failure_action") or FailureAction.CONTINUE.value).lower()
            if fa in (FailureAction.INTERRUPT.value, FailureAction.STOP.value):
                return "end"
            if fa in (
                FailureAction.RETRY.value,
                FailureAction.REPLAN.value,
                FailureAction.CONTINUE.value,
            ):
                return "observe" if observe_enabled() else "agent"
            return "observe" if observe_enabled() else "agent"

        async def observe_node(state: LangGraphAgentState) -> Dict[str, Any]:
            """工具后结构化观察 → 再回 agent（默认不调 LLM）。"""
            if state.get("done") or not observe_enabled():
                return {"sse_buffer": []}
            locale = normalize_locale(state.get("locale"))
            name = str(state.get("last_tool") or "")
            obs = state.get("last_observation")
            fa = str(state.get("failure_action") or FailureAction.CONTINUE.value)
            fk = str(state.get("failure_kind") or "")
            note = build_observe_note(
                tool_name=name,
                observation=obs,
                failure_action=fa,
                failure_kind=fk,
                result_context=state.get("result_context")
                if isinstance(state.get("result_context"), dict)
                else {},
                locale=locale,
            )
            if not note:
                return {"sse_buffer": []}
            # 避免与 tools 刚注入的 RETRY/REPLAN hint 完全重复
            msgs = list(state.get("messages") or [])
            last_c = ""
            if msgs:
                last = msgs[-1]
                if isinstance(last, dict) and last.get("role") == "user":
                    last_c = str(last.get("content") or "")
            inject = True
            if fa in (FailureAction.RETRY.value, FailureAction.REPLAN.value) and last_c:
                # 已有纠错 hint：只发 SSE，不再叠一条几乎相同的 user
                inject = False
            sse: List[Dict[str, Any]] = [
                observe_sse(note, tool_name=name, failure_action=fa),
                {
                    "event": "agent_thought",
                    "delta": f"[observe] {note}\n",
                    "index": max(0, int(state.get("round_idx") or 1) - 1),
                },
            ]
            out: Dict[str, Any] = {"sse_buffer": sse, "last_observe": note}
            if inject:
                out["messages"] = [observe_message(note, locale=locale)]
            return out

        def _route_after_observe(state: LangGraphAgentState) -> str:
            return "end" if state.get("done") else "agent"

        g = StateGraph(LangGraphAgentState)
        g.add_node("agent", agent_node)
        g.add_node("tools", tools_node)
        g.add_node("observe", observe_node)
        g.add_edge(START, "agent")
        g.add_conditional_edges("agent", _route_after_agent, {"tools": "tools", "end": END})
        g.add_conditional_edges(
            "tools", _route_after_tools, {"observe": "observe", "agent": "agent", "end": END}
        )
        g.add_conditional_edges("observe", _route_after_observe, {"agent": "agent", "end": END})
        cp = get_checkpointer()
        if cp is not None:
            return g.compile(checkpointer=cp)
        return g.compile()

    def _ensure_graph(self):
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    async def run(
        self,
        user_input: str,
        project_id: int = None,
        locale: Optional[str] = None,
    ) -> Dict[str, Any]:
        final: Dict[str, Any] = {"success": False, "findings": [], "summary": ""}
        async for pkt in self.run_stream(user_input, project_id=project_id, locale=locale):
            if isinstance(pkt, dict) and pkt.get("type") == "tail":
                pl = pkt.get("payload") or {}
                if isinstance(pl, dict):
                    final["success"] = True
                    final["summary"] = pl.get("summary") or final["summary"]
        return final

    async def run_stream(
        self,
        user_input: str,
        project_id: int = None,
        plan_id: int = None,
        locale: Optional[str] = None,
        pending_diff_context: Optional[List[Dict[str, Any]]] = None,
        agent_session_id: Optional[str] = None,
        chat_session_id: Optional[int] = None,
        long_memory_prefetch: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        hint_project_name: Optional[str] = None,
        hint_plan_name: Optional[str] = None,
        client_shell: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
        ui_context: Optional[Dict[str, Any]] = None,
        raw_user_input: Optional[str] = None,
        client_terminal_results: Optional[List[Dict[str, Any]]] = None,
        langgraph_resume: Optional[Dict[str, Any]] = None,
    ):
        self.project_id = project_id
        self.plan_id = plan_id
        self._ui_locale = normalize_locale(locale)
        self._ui_context = ui_context if isinstance(ui_context, dict) else None
        self._agent_session_id = (agent_session_id or "").strip() or None
        self._chat_session_id = chat_session_id
        self._client_shell = client_shell if isinstance(client_shell, dict) else None
        self._pending_diff_context_raw = (
            pending_diff_context if isinstance(pending_diff_context, list) else None
        )
        self._react_stream_images = images if isinstance(images, list) and images else None
        self._raw_user_input = raw_user_input if raw_user_input is not None else user_input
        self._unified_result_ctx = {}
        self._last_resume_snapshot = None
        self._register_cancel()
        t0 = time.perf_counter()
        _resume_on = isinstance(langgraph_resume, dict) and bool(langgraph_resume.get("messages"))
        print(
            f"[LANGGRAPH] run_stream start project_id={project_id} plan_id={plan_id} "
            f"session={self._agent_session_id} tools={len(self._openai_tools())} "
            f"resume={_resume_on}",
            flush=True,
        )

        _last_wire_phase: Optional[str] = None
        _ls_cm = langsmith_tracing_context(
            name="langgraph_run_stream",
            metadata=langsmith_run_metadata(
                agent_session_id=self._agent_session_id,
                project_id=project_id,
                plan_id=plan_id,
                engine="langgraph",
                user_id=str(self.user_id or self._user_id or "") or None,
            ),
            tags=["badcase-doctor", "langgraph", "run_stream"],
        )
        _ls_cm.__enter__()

        async def _yield_raw(raw: Dict[str, Any]):
            nonlocal _last_wire_phase
            if not isinstance(raw, dict):
                return
            pkts = [raw] if is_wire_v1_packet(raw) else list(engine_dict_to_wire_packets(raw))
            for pkt in pkts:
                if sse_v1_emit_phase_packets_enabled():
                    pl = pkt.get("payload")
                    if isinstance(pl, dict):
                        rp = pl.get("react_phase")
                        if isinstance(rp, str) and rp and rp != _last_wire_phase:
                            yield {
                                "type": ClientWireType.PHASE.value,
                                "payload": react_phase_wire_payload(rp),
                            }
                            _last_wire_phase = rp
                yield pkt

        try:
            if self._cancel_requested():
                async for pkt in _yield_raw({"event": "error", "message": "cancelled"}):
                    yield pkt
                async for pkt in _yield_raw({"event": "done"}):
                    yield pkt
                return

            graph = self._ensure_graph()
            locale_n = normalize_locale(locale)
            from agents.conversation_history import (
                history_as_chat_messages,
                normalize_conversation_history,
            )
            from agents.client_terminal_resume import format_terminal_results_prompt

            _sys = self._system_prompt(locale_n)
            _hint_blk = format_project_hint_block(
                hint_project_name=hint_project_name,
                hint_plan_name=hint_plan_name,
                locale=locale_n,
            )
            _lm_blk = format_long_memory_block(long_memory_prefetch, locale=locale_n)
            if _hint_blk or _lm_blk:
                _sys = _sys + "\n\n" + "\n".join(x for x in (_hint_blk, _lm_blk) if x)

            _term_block = format_terminal_results_prompt(
                client_terminal_results or [], locale=locale_n
            )
            _user_content = user_input
            if _term_block:
                if user_input_already_has_terminal_block(user_input or ""):
                    # 外层 Agent 已拼过终端块：保留完整 user_input，避免丢掉原任务
                    _user_content = user_input
                else:
                    _user_content = f"{_term_block}\n\n---\n\n{user_input}"
                print(
                    f"[LANGGRAPH] inject client_terminal_results n={len(client_terminal_results or [])}",
                    flush=True,
                )

            _resume_tid = ""
            if isinstance(langgraph_resume, dict):
                _resume_tid = str(langgraph_resume.get("thread_id") or "").strip()
            self._thread_id = make_thread_id(
                chat_session_id=chat_session_id,
                agent_session_id=self._agent_session_id,
                resume_thread_id=_resume_tid or None,
            )
            _lg_config = stream_config(self._thread_id)
            _lg_config["metadata"] = langsmith_run_metadata(
                agent_session_id=self._agent_session_id,
                project_id=project_id,
                plan_id=plan_id,
                engine="langgraph",
                user_id=str(self.user_id or self._user_id or "") or None,
            )
            _lg_config["tags"] = ["badcase-doctor", "langgraph"]
            _use_cp_resume = bool(
                _resume_on
                and get_checkpointer() is not None
                and graph_has_checkpoint(graph, self._thread_id)
            )

            init: LangGraphAgentState
            if _use_cp_resume:
                # checkpointer 已有图状态：只追加本轮用户消息，避免 messages reducer 重复整链
                init = {
                    "messages": [{"role": "user", "content": _user_content}],
                    "sse_buffer": [],
                    "done": False,
                    "project_id": project_id,
                    "plan_id": plan_id,
                    "user_id": str(self.user_id or self._user_id or ""),
                    "locale": locale_n,
                    "ui_context": self._ui_context,
                    "pending_diff_context": self._pending_diff_context_raw,
                    "client_shell": self._client_shell,
                    "user_input": _user_content,
                    "failure_action": FailureAction.CONTINUE.value,
                    "failure_kind": "resumed_checkpoint",
                    "last_observe": "",
                }
                try:
                    _st = graph.get_state(_lg_config)
                    _vals = getattr(_st, "values", None) or {}
                    if isinstance(_vals.get("result_context"), dict):
                        self._unified_result_ctx = dict(_vals["result_context"])
                except Exception:
                    pass
                print(
                    f"[LANGGRAPH] checkpoint resume thread_id={self._thread_id}",
                    flush=True,
                )
            elif _resume_on:
                restored = apply_langgraph_resume(
                    system_prompt=_sys,
                    resume_state=langgraph_resume or {},
                    new_user_content=_user_content,
                )
                init = {
                    "messages": restored["messages"],
                    "sse_buffer": [],
                    "result_context": dict(restored.get("result_context") or {}),
                    "grep_tool_calls": restored.get("grep_tool_calls") or 0,
                    "grep_attempts": restored.get("grep_attempts") or 0,
                    "last_grep_empty": bool(restored.get("last_grep_empty")),
                    "last_tool": "",
                    "last_observation": None,
                    "round_idx": int(restored.get("round_idx") or 0),
                    "done": False,
                    "project_id": project_id,
                    "plan_id": plan_id,
                    "user_id": str(self.user_id or self._user_id or ""),
                    "locale": locale_n,
                    "ui_context": self._ui_context,
                    "pending_diff_context": self._pending_diff_context_raw,
                    "client_shell": self._client_shell,
                    "user_input": restored.get("user_input") or _user_content,
                    "failure_action": FailureAction.CONTINUE.value,
                    "failure_kind": "resumed",
                    "failure_retries": int(restored.get("failure_retries") or 0),
                    "task_plan_emitted": bool(restored.get("task_plan_emitted")),
                    "task_plan_steps": restored.get("task_plan_steps"),
                    "last_observe": "",
                }
                self._unified_result_ctx = dict(init.get("result_context") or {})
                try:
                    from agents.cdp.login_pending_store import load_login_pending

                    _cdp_p = load_login_pending(
                        chat_session_id=chat_session_id,
                        project_id=project_id,
                    )
                    if _cdp_p:
                        init.setdefault("result_context", {})["cdp_login_pending"] = _cdp_p
                        self._unified_result_ctx["cdp_login_pending"] = _cdp_p
                except Exception:
                    pass
                print(
                    f"[LANGGRAPH] snapshot resume msgs={len(init['messages'])} "
                    f"thread_id={self._thread_id} grep_calls={init['grep_tool_calls']}",
                    flush=True,
                )
            else:
                _hist = normalize_conversation_history(conversation_history)
                _msgs: List[Dict[str, Any]] = [{"role": "system", "content": _sys}]
                _msgs.extend(history_as_chat_messages(_hist))
                _msgs.append({"role": "user", "content": _user_content})
                if _hist:
                    print(f"[LANGGRAPH] inject conversation_history n={len(_hist)}", flush=True)
                _rc0: Dict[str, Any] = {}
                if isinstance(long_memory_prefetch, dict) and long_memory_prefetch:
                    _lmt = str(
                        long_memory_prefetch.get("long_memory_text")
                        or long_memory_prefetch.get("merged")
                        or ""
                    ).strip()
                    _lmi = long_memory_prefetch.get("long_memory_items") or long_memory_prefetch.get(
                        "memories"
                    )
                    if _lmt:
                        _rc0["long_memory_text"] = _lmt
                    if isinstance(_lmi, list) and _lmi:
                        _rc0["long_memory_items"] = _lmi
                try:
                    from agents.cdp.login_pending_store import load_login_pending

                    _cdp_pending = load_login_pending(
                        chat_session_id=chat_session_id,
                        project_id=project_id,
                    )
                    if _cdp_pending:
                        _rc0["cdp_login_pending"] = _cdp_pending
                except Exception:
                    pass
                init = {
                    "messages": _msgs,
                    "sse_buffer": [],
                    "result_context": _rc0,
                    "grep_tool_calls": 0,
                    "grep_attempts": 0,
                    "last_grep_empty": False,
                    "last_tool": "",
                    "last_observation": None,
                    "round_idx": 0,
                    "done": False,
                    "project_id": project_id,
                    "plan_id": plan_id,
                    "user_id": str(self.user_id or self._user_id or ""),
                    "locale": locale_n,
                    "ui_context": self._ui_context,
                    "pending_diff_context": self._pending_diff_context_raw,
                    "client_shell": self._client_shell,
                    "user_input": _user_content,
                    "failure_action": FailureAction.CONTINUE.value,
                    "failure_kind": "ok",
                    "failure_retries": 0,
                    "task_plan_emitted": False,
                    "task_plan_steps": None,
                    "last_observe": "",
                }

            _astream_kw: Dict[str, Any] = {"stream_mode": "updates"}
            if get_checkpointer() is not None:
                _astream_kw["config"] = _lg_config
                print(f"[LANGGRAPH] astream thread_id={self._thread_id}", flush=True)

            # 累计状态：用户取消时仍可写断点供续跑
            _acc_msgs: List[Dict[str, Any]] = list(init.get("messages") or [])
            _acc_rc: Dict[str, Any] = dict(init.get("result_context") or {})
            _acc_grep_calls = int(init.get("grep_tool_calls") or 0)
            _acc_grep_attempts = int(init.get("grep_attempts") or 0)
            _acc_last_empty = bool(init.get("last_grep_empty"))
            _acc_fail_retries = int(init.get("failure_retries") or 0)
            _acc_round = int(init.get("round_idx") or 0)
            _acc_plan = init.get("task_plan_steps")
            _astream_updates = 0

            async for update in graph.astream(init, **_astream_kw):
                _astream_updates += 1
                if self._cancel_requested():
                    _cancel_snap = self._last_resume_snapshot
                    if not isinstance(_cancel_snap, dict) or not _cancel_snap.get("messages"):
                        _fake_state = {
                            "messages": _acc_msgs,
                            "round_idx": _acc_round,
                            "user_input": str(init.get("user_input") or user_input or ""),
                            "task_plan_steps": _acc_plan,
                        }
                        _sse_cancel: List[Dict[str, Any]] = []
                        _cancel_snap = self._snapshot_and_emit_resume(
                            _sse_cancel,
                            _fake_state,
                            messages_delta=[],
                            result_context=_acc_rc,
                            grep_tool_calls=_acc_grep_calls,
                            grep_attempts=_acc_grep_attempts,
                            last_grep_empty=_acc_last_empty,
                            failure_retries=_acc_fail_retries,
                            failure_action=FailureAction.STOP.value,
                            failure_kind="cancelled",
                            reason="cancelled",
                        )
                        for _ev in _sse_cancel:
                            if isinstance(_ev, dict):
                                async for pkt in _yield_raw(_ev):
                                    yield pkt
                    if isinstance(_cancel_snap, dict):
                        try_persist_langgraph_interrupt(
                            chat_session_id=self._chat_session_id,
                            project_id=project_id,
                            user_id=self.user_id or self._user_id,
                            react_request_id=self._agent_session_id,
                            user_input=str(self._raw_user_input or user_input or ""),
                            snapshot=_cancel_snap,
                            interrupt_reason="cancelled",
                        )
                        print(
                            "[LANGGRAPH] cancel → persisted resume snapshot",
                            flush=True,
                        )
                    async for pkt in _yield_raw({"event": "error", "message": "cancelled"}):
                        yield pkt
                    async for pkt in _yield_raw({"event": "done"}):
                        yield pkt
                    return
                if not isinstance(update, dict):
                    continue
                for _node, delta in update.items():
                    if not isinstance(delta, dict):
                        continue
                    _rc = delta.get("result_context")
                    if isinstance(_rc, dict):
                        self._unified_result_ctx = dict(_rc)
                        _acc_rc = dict(_rc)
                    _dm = delta.get("messages")
                    if isinstance(_dm, list) and _dm:
                        _acc_msgs.extend([m for m in _dm if isinstance(m, dict)])
                    if "grep_tool_calls" in delta:
                        _acc_grep_calls = int(delta.get("grep_tool_calls") or 0)
                    if "grep_attempts" in delta:
                        _acc_grep_attempts = int(delta.get("grep_attempts") or 0)
                    if "last_grep_empty" in delta:
                        _acc_last_empty = bool(delta.get("last_grep_empty"))
                    if "failure_retries" in delta:
                        _acc_fail_retries = int(delta.get("failure_retries") or 0)
                    if "round_idx" in delta:
                        _acc_round = int(delta.get("round_idx") or 0)
                    if "task_plan_steps" in delta:
                        _acc_plan = delta.get("task_plan_steps")
                    for ev in delta.get("sse_buffer") or []:
                        if isinstance(ev, dict):
                            if ev.get("event") == "langgraph_resume" and isinstance(
                                ev.get("state"), dict
                            ):
                                try_persist_langgraph_interrupt(
                                    chat_session_id=self._chat_session_id,
                                    project_id=project_id,
                                    user_id=self.user_id or self._user_id,
                                    react_request_id=self._agent_session_id,
                                    user_input=str(
                                        self._raw_user_input or user_input or ""
                                    ),
                                    snapshot=ev["state"],
                                    interrupt_reason=str(ev.get("reason") or ""),
                                )
                            async for pkt in _yield_raw(ev):
                                yield pkt

            if _astream_updates <= 0:
                print(
                    "[LANGGRAPH] astream produced 0 updates — emit error+done "
                    f"thread_id={getattr(self, '_thread_id', '')}",
                    flush=True,
                )
                async for pkt in _yield_raw(
                    {
                        "event": "error",
                        "message": "LangGraph 未产生任何步骤（可能被中断或引擎异常提前结束）",
                    }
                ):
                    yield pkt
                async for pkt in _yield_raw({"event": "done"}):
                    yield pkt

            print(
                f"[LANGGRAPH] run_stream done ms={(time.perf_counter() - t0) * 1000:.1f} "
                f"updates={_astream_updates}",
                flush=True,
            )
        except Exception as e:
            print(f"[LANGGRAPH] run_stream error: {e}", flush=True)
            async for pkt in _yield_raw({"event": "error", "message": str(e)}):
                yield pkt
            async for pkt in _yield_raw({"event": "done"}):
                yield pkt
        finally:
            self._unregister_cancel()
            try:
                _ls_cm.__exit__(None, None, None)
            except Exception:
                pass
