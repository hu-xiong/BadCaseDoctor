# agents/react_simplified.py
"""
极简 ReAct 引擎 - 结合 Claude Code 强约束 Prompt + 自我修正 + Skill动态加载 + Text2SQL
核心：单主循环（每条 Todo：decide→执行工具→observe→更新上下文）；非一次性脚本批量执行。
SSE：todos/plan/todo_start/observation 等与前端同步进度。

性能 / 体验（环境变量，可选）：
- REACT_THOUGHT_BRIEF_MS：低于该毫秒数则前端显示「Thought briefly」（默认 800）
- REACT_SKIP_THINK_HINT：首轮 THINK 前是否注入 ``_reasoning_summary_from_user_input`` 说明。**默认 1（跳过）**，略减首包延迟；设为 ``0``/``false`` 恢复注入（不截断工具描述或模型输出）
- REACT_THINK_MAX_TOKENS：>0 且底层 ``chat_stream`` / 流式接口支持 ``max_tokens`` 时，首轮 THINK 输出上限，缩短 ``todos_ready`` 尾延迟；不设则不限制（与 observe/decide 的 max_tokens 开关独立）
- REACT_TOOL_DESC_MAX_CHARS：>0 时截断各工具 description，缩短首轮 THINK prompt（见 prompts.format_tools_for_prompt）。同配置下 ``format_tools_for_prompt`` 默认进程内缓存；``REACT_TOOLS_FORMAT_CACHE=0`` 关闭
- REACT_PROJECT_PLAN_NAME_CACHE_TTL：按 ``(project_id, plan_id)`` 缓存名称秒数（默认 **45**）；``0`` 关闭缓存。查库在 **线程池** 执行，避免阻塞 asyncio 事件循环
- REACT_DECIDE_FUNCTION_CALL=1：决策步走 function calling（Qwen 百炼 OpenAI 兼容、千帆 v2）；失败或无 tools 时回退流式/XML
- REACT_FC_TOOL_CHOICE：auto / none / required，或 JSON 如 {"type":"function","function":{"name":"grep"}}；默认 auto
- REACT_THINK_FC_TOOL_CHOICE：**未设置时**首轮 THINK 流式 FC 强制 ``{"type":"function","function":{"name":"submit_react_think"}}``（避免千帆等 ``auto`` 只出正文、无 tool_calls）；设 ``auto``/``false``/``off`` 则仍用 ``REACT_FC_TOOL_CHOICE``
- REACT_FC_DECIDE_EXCLUDE_TOOLS：决策步 FC 不向模型暴露的工具名（逗号分隔），默认 ``get_tool_description``，避免占步、grep 不执行；设 ``none``/空则不排除
- REACT_FC_PARALLEL_TOOL_CALLS=1：允许模型并行 tool_calls（默认关；ReAct 单步仍只消费第一条）
- REACT_PLAN_SSE_MIN_STEPS：≥该步数才下发完整「计划区」UI（plan 事件仍可省略首包 mirror）；默认 3，见 §6.6
- REACT_PLAN_MEMO_AFTER_THINK：默认 **1**。为 1 时 ``plan_init`` **始终**带 ``suppress_plan_ui``，避免「规划备忘」早于首轮 Agent Thought 正文出现；前端在 THINK 有足够正文后再揭示。设为 ``0``/``false`` 恢复旧行为（与步数阈值无关的首包即展示规划区）
- REACT_INTENT_PLAN_UI_ENABLED=1（默认）：首轮意图 JSON 可含 need_plan_ui；为 false 时**始终**隐藏规划备忘（与步数阈值无关）。为 true 或未返回时仍受 REACT_PLAN_SSE_MIN_STEPS 约束。=0 时忽略 need_plan_ui（与旧版一致，仅步数阈值）
- SSE_V1_EMIT_PHASE=0：关闭 ``type=phase`` 边沿包（默认发）
- GREP_PLAN_TREE_CACHE_TTL：grep 内计划树缓存秒数（默认 60，0 关闭），见 GrepTool._get_plan_tree
- PERF_LOG=1：打印各阶段耗时，便于对比模型与链路瓶颈；grep 后观察链路见 ``[PERF][observe]``（stream_observe_ms / xml_parse_ms / ui_observe_summary_ms / total_ms）；轮次衔接见 ``[PERF][round-bridge]``（观察流结束→todo_end、todo_start→FC/流式 decide）
- 主循环前：技能 match_skill 与首轮 THINK 并行启动，THINK 结束后再 await 收口，减少串行等待
- REACT_OBSERVE_UI_PARALLEL=1（默认）：observe 与 ``react_ui_stream(decision_observe)`` 并行跑 LLM；SSE 在 **ui_lead 首包之后** 与 observe 事件 **交错** 下发（避免 observe 独占总带宽拖慢 UI 首包，也避免整段 UI 发完才 flush observe 导致 Thought 长期空白）；``0`` 为串行
- REACT_OBSERVE_UI_LLM=0：``decision_observe`` 不调用 ``ui_observe_summary`` 专用 LLM，改为使用本步已有的 ``summary_nl``（``_summarize_observation_nl``）分块下发，通常可省数秒～数十秒；默认 ``1`` 保持原行为
- REACT_OBSERVE_FAST_STUB=1（默认）：modify 且沙箱预览/待确认/batch 等场景**跳过大模型 observe_prompt**（``_stream_agent_observe_with_narrative``），用本地 ``<result>`` 占位 + ``summary_nl``，避免预览已出后仍等 10～30s；``0`` 关闭（恢复旧行为、利于排查）
- REACT_GREP_OBSERVE_FAST_STUB=1（默认）：grep 且 ``mode=locate``、``success=true`` 时**跳过 observe_prompt 大模型**（工具已产出 ``summary_nl``/结构化结果，决策与观察阶段不再多等一轮 10s+ 级 LLM）；``associate``/``compare`` 等仍走完整 observe；``0`` 关闭
- REACT_AGENT_TASK_DAG=1：工具执行写入 ``agent_tasks`` 表（pending→running→done/failed），便于审计与后续多任务 DAG；默认 ``0``。会话维度键由 ``agent_session_id``（如 ``react_request_id``）传入
- REACT_OBSERVE_NL_STREAM_CHARS：上项为 ``0`` 时，每条 ``react_ui_stream`` delta 的最大字符数（默认 240）
- REACT_OBSERVE_PROMPT_SHRINK=0：关闭 observe 用 prompt 内对 ``observation`` / ``context`` 的列表与长字符串裁剪（默认开启）
- REACT_OBSERVE_PROMPT_LIST_CAP：裁剪后单列表最大条数（默认 15）；REACT_OBSERVE_PROMPT_STR_CHARS：单字符串最大字符（默认 500）；REACT_OBSERVE_PROMPT_MAX_DEPTH：JSON 递归深度上限（默认 14）
- REACT_OBSERVE_MAX_TOKENS：>0 且底层 ``chat_stream`` 支持 ``max_tokens`` 时（当前 Qwen 兼容实现），observe 流式输出上限，抑制冗长生成
- REACT_DECIDE_PROMPT_SHRINK=0：关闭对 decide 步传入的 ``result_context`` / ``last_observation`` / ``last_analysis`` 的 JSON 裁剪（默认开）；``REACT_DECIDE_PROMPT_LIST_CAP`` / ``REACT_DECIDE_PROMPT_STR_CHARS`` / ``REACT_DECIDE_PROMPT_MAX_DEPTH`` 未设时回落到对应 ``REACT_OBSERVE_PROMPT_*``
- REACT_DECIDE_MAX_TOKENS：流式 decide（非 FC）时可选 ``max_tokens``，同 observe
- REACT_DECIDE_FC_MAX_TOKENS：Function Calling 决策（``chat_completion_with_tools``）可选输出上限；**未设置时回落到** ``REACT_DECIDE_MAX_TOKENS``（仍不设则不传 max_tokens）
- **grep 后下一轮 decide**（缩短观察结束→Thought 间隔）：上一工具为 ``grep`` 时，默认对 decide 侧 JSON 做**更紧裁剪**（``REACT_DECIDE_AFTER_GREP_SHRINK=1`` 默认开，``=0`` 关闭）；``REACT_DECIDE_AFTER_GREP_LIST_CAP``（默认 8）、``REACT_DECIDE_AFTER_GREP_STR_CHARS``（默认 280）、``REACT_DECIDE_AFTER_GREP_MAX_DEPTH``（默认 12），与通用 ``REACT_DECIDE_PROMPT_*`` 取 **更严（更小）** 值。另可设 ``REACT_DECIDE_AFTER_GREP_MAX_TOKENS`` 覆盖该轮流式 decide 输出上限；FC 轮次另可读 ``REACT_DECIDE_AFTER_GREP_FC_MAX_TOKENS``，未设则回落到 ``REACT_DECIDE_AFTER_GREP_MAX_TOKENS``
- P0 体积/延迟（仅环境变量）：首轮说明默认已跳过（``REACT_SKIP_THINK_HINT=0`` 可开）；``REACT_TOOL_DESC_MAX_CHARS`` 等为**截断**，与「尽量不截断」冲突时勿开
- REACT_LONG_MEMORY_QUERY_EACH_MESSAGE：``1`` 时每条对话按当前 ``user_input`` 做向量检索注入；**默认 0**——由前端打开项目时 ``POST /api/memory/retrieve``（``mode: recent``）拉取后，随 ``long_memory_context`` 传入 ``/api/agent/react``。
- REACT_NEED_TODO_LIST_HEURISTIC：模型未给出 ``need_todo_list`` 时的降级；**默认 1**（多步/多工具线索 → 生成计划）；``0`` 时恒按「需要可解析计划」处理（保守）。
- REACT_THINK_JSON_PLAN=1（默认）：THINK 要求一次性输出 ``{"plan":[{id,description,status},...]}``；解析见 ``parse_react_json_plan``。
- REACT_SELF_DRIVE_TOOL_LOOP=1：每步用 ``_extract_todo_params`` 直接决策工具，跳过本步 decide LLM（仍走 observe 等后续）。
- REACT_STOP_AFTER_STEP_FAIL=1（默认）：步骤失败或（严格模式下）grep 空命中后暂停自动推进并发 ``step_failed`` 提示。
- REACT_STRICT_PLAN_FAIL=1（默认）：grep 成功但三类列表均空时视为失败。
- REACT_PLAN_SSE_LIVE_STEPS=1（默认）：每轮同步 ``plan_update``（单 in_progress）；``=0`` 关闭。
- REACT_MERGE_FIRST_THINK_INTO_DECIDE=1：跳过独立首轮 THINK；``todo_items``（及可选 ``first_tool``/``first_params``）在 **主循环第 0 步** 通过 **submit_react_think** 一次 FC 完成（须 ``REACT_DECIDE_FUNCTION_CALL=1`` 且 LLM 支持 FC）。默认 ``0``。
- REACT_THINK_QUEUE_POLL_S：首轮 THINK 从队列取块时的轮询间隔秒数（默认 ``0.03``）；略缩可更快响应首 token，过小占 CPU。范围约 0.02～0.2
- REACT_CHAT_REPLY_STREAM=1（默认）：纯对话路径用 ``summary_stream`` 分块输出；``REACT_CHAT_REPLY_STREAM_CHARS`` 每块字符数（默认 2）
- REACT_SUMMARY_STREAM_GAP_MS：``summary_stream`` / 统一总结 LLM 流等分片之间的暂停毫秒数（默认 22；``0`` 关闭）。单靠 ``asyncio.sleep(0)`` 易与单次 TCP/读缓冲合并，前端像「一次性整块」
- REACT_RUNNING_SUMMARY_STREAM_GAP_MS：终局 ``running_summary_stream`` 分片间隔；**未设置**时与 ``REACT_SUMMARY_STREAM_GAP_MS`` 相同
- REACT_INCREMENTAL_SUMMARY：每步 observation 后合并「增量运行总览」Markdown。**默认开**；``0``/``false``/``off`` 关闭。``REACT_INCREMENTAL_SUMMARY_MAX_TOKENS``（默认 2048）；``REACT_INCREMENTAL_SUMMARY_REPLACE_FINAL=1``（默认）时终局不再跑统一总结 LLM
- REACT_INCREMENTAL_SUMMARY_STREAM_SSE（默认 ``1``）：仅影响 **主循环结束后** 下发运行总览的方式。``1``：发 ``running_summary_done`` 整块（与 REPLACE_FINAL 等配合）；``0``：走 ``final_wire`` 切片重放 ``running_summary_stream``。**中途**每步合并一律 asyncio 后台队列 + 静默 LLM，不阻塞「准备下一步」、不向中途 SSE 推流（函数 ``_merge_running_summary_incremental_to_sse`` 保留供专项实验，主路径不再调用）
- REACT_INCREMENTAL_SUMMARY_BLOCK_LOOP：``1`` 时每步在主循环内 ``await`` 静默合并（排障/复现卡顿用）。**默认 ``0``：后台 worker 串行合并**
- REACT_DECIDE_FC_STREAM=1（默认）：decide 步在支持 ``chat_completion_with_tools_stream`` 的 LLM 上走**流式 FC**（边收 content/tool_calls delta 边 ``agent_thought``）；失败回退整包 ``chat_completion_with_tools``。设为 ``0`` 强制整包 FC。
- REACT_DECIDE_FC_INSTANT_HINT=1（默认）：整包 FC 时在 ``await chat_completion_with_tools`` 前先 ``agent_thought`` 占位；**流式 FC 时仍以真实 delta 为主**，占位可关。设为 ``0`` 关闭占位。

- REACT_GREP_RESULT_CACHE_TTL：>0 时对本引擎内 grep 成功结果做内存缓存（秒，按 project_id/keywords/target/mode/plan_id/userId 键）；短 TTL 内重复查询可省 DB；默认 0 关闭；数据变更后短时内可能读到旧结果
进一步提速方向（需产品/架构取舍，不单靠开关）：
- 合并多步 LLM（decide+observe 合一）、缩短 prompt
- 模型侧：更低延迟 endpoint、适当减小 max_tokens（本仓库不强制改模型）
- 工具侧：DB 索引、grep 范围缩小、异步 I/O
- modify 批量预览：`MODIFY_BATCH_PREVIEW_STREAM=1`（默认）每条 diff 经 progress_queue 推送 `batch_preview_row` SSE，不必等整批结束
- modify 快速落库：`MODIFY_ALLOW_FAST_APPLY=1` 且工具参数 ``skip_preview=true``，且修改字段仅为状态/负责人时，跳过沙箱直接 ORM 落库（返回带 ``fast_apply`` / ``sandbox_skipped``）；**无自动回滚**，需运维/备份兜底
"""

import contextlib
import html
import asyncio
import concurrent.futures
import functools
import copy
import json
import time
import os
import threading
import queue
import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, Iterator, List, Optional, AsyncIterator, Tuple, Union

#原依赖
from .prompts import ReactPromptTemplates, format_tools_for_prompt
from .prompts import (
    parse_xml_todos,
    parse_xml_decision,
    parse_xml_findings,
    parse_react_json_plan,
    parse_opening_decision,
    parse_unified_response,
)
from .react_function_call import (
    use_react_decide_function_call,
    use_react_decide_fc_stream,
    FcStreamAccumulator,
    use_react_observe_fc,
    use_react_decide_xml_fallback,
)
from .self_correction import SelfCorrectionEngine
from .evidence_extractor import EvidenceExtractor

# Skill 动态加载
from .skill_loader import SkillLoader
from .skill_registry import skill_registry
from .skill import Skill
from .skill_integration import get_skill_integration  # Skill 集成管理器（懒加载）
from .sse_react_v1 import (
    ClientWireType,
    engine_dict_to_wire_packets,
    is_wire_v1_packet,
    react_phase_wire_payload,
    sse_v1_emit_phase_packets_enabled,
)
from .intent_guards import (
    is_vague_generic_todo,
    infer_modify_target_from_user,
)
from .locale_prompts import (
    normalize_locale,
    is_english_locale,
    react_tools_chat_fallback_message,
    react_phase_wait_message,
    react_observe_section_header,
    react_decide_fc_first_token_hint,
    react_fallback_decision_line,
    react_findings_bulleted_summary_prompt,
    react_unified_final_summary_prompt,
    incremental_running_summary_prompt,
    wrap_react_user_prompt,
    modify_modifications_kv_summary,
    react_batch_modify_preview_message,
    react_batch_modify_summary,
    react_summarize_observation_nl_skipped_gate,
    react_summarize_observation_nl_skipped_generic,
    react_summarize_observation_nl_tool_failed,
    react_summarize_observation_nl_tool_failed_short,
    react_summarize_grep_done_empty,
    react_summarize_grep_done_hits,
    react_summarize_modify_done,
    react_summarize_tool_done_ok,
    react_executing_modify_about_to,
    react_executing_grep_about_to,
    react_executing_create_about_to,
    react_executing_database_query_about_to,
    react_retry_grep_for_modify,
    react_modify_progress_wait,
    react_modify_executing_fallback_reason,
    react_modify_single_record_reason,
    react_tool_missing_error,
    react_modify_timeout,
)

# Text2SQL
try:
    from .tools.sqlcoder_agent import Text2SQLAgent, LLMBackend
    TEXT2SQL_AVAILABLE = True
except ImportError:
    TEXT2SQL_AVAILABLE = False
    print("[REACT]⚠  Text2SQLAgent 未安装，使用传统查询模式")


_CONTEXT_UPDATE_FROM_LLM_IGNORE_KEYS = frozenset(
    {
        "badcase_list",
        "bug_list",
        "testcase_list",
        "grep_result",
        "first_badcase_id",
        "first_bug_id",
        "first_testcase_id",
        "_last_grep_keywords",
        "_last_grep_target",
        "badcase_analysis",
    }
)


def _scrub_grep_grounded_keys_from_context_update(raw: Any) -> Dict[str, Any]:
    """observe 的 <context_update> 不得覆盖 grep 工具写入的定位列表；modify Observe 后模型常臆造 badcase_list，下一轮会串表。"""
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k not in _CONTEXT_UPDATE_FROM_LLM_IGNORE_KEYS}


def get_text2sql_tool(db_path="instance/badcase_doctor.db"):
    """获取 Text2SQL 工具实例（进程级缓存 + 懒加载）。"""
    if not TEXT2SQL_AVAILABLE:
        return None
    try:
        from .tools.sqlcoder_agent import get_cached_text2sql_agent
        backend_env = (os.getenv("TEXT2SQL_LLM_BACKEND", "glm-4-flash") or "").strip().lower()
        backend = "glm-5" if backend_env in ("glm-5", "glm5") else "glm-4-flash"
        return get_cached_text2sql_agent(
            database_path=db_path,
            llm_backend=backend,
            debug=False,
            execution_mode="direct",
        )
    except Exception as e:
        print(f"[REACT] Text2SQL初始化失败: {e}")
        return None


def robust_parse_todos(raw: Any) -> List[str]:
    """
    健壮解析 LLM 返回的 todos：
    1）优先走现有的 XML 解析（parse_xml_todos）
    2）若失败或为空，再尝试：
       - 解析 <todo_list>...</todo_list> 里的 XML 结构
       - 从文本中用正则抽取 JSON 数组并 json.loads
       - 最后兜底：按行/项目符号提取
    返回：todo 文本列表（字符串列表）
    """
    # 已经是列表就直接兜底规范化
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]

    if raw is None:
        return []

    text = raw if isinstance(raw, str) else str(raw)
    if not text.strip():
        return []

    todos: List[str] = []

    # 1. 先走原有 XML 解析（保持兼容）
    try:
        base = parse_xml_todos(text)
        if base:
            # parse_xml_todos 目前可能返回列表 / dict，这里只关心列表
            if isinstance(base, list):
                todos = [str(x).strip() for x in base if str(x).strip()]
                if todos:
                    return todos
    except Exception as e:
        print(f"[REACT-planing] parse_xml_todos 解析失败，继续尝试增强解析: {e}")

    # 2. 解析 <todo_list>...</todo_list> 里的简单 XML
    try:
        m = re.search(r'<todo_list[^>]*>([\s\S]*?)</todo_list>', text, re.IGNORECASE)
        if m:
            inner = m.group(1).strip()
            # 包一层根节点，容忍模型直接输出 <item> / <todo>
            xml_str = f"<root>{inner}</root>"
            root = ET.fromstring(xml_str)
            xml_todos: List[str] = []
            for node in root.iter():
                tag = (node.tag or "").lower()
                if tag in ("todo", "item", "step"):
                    content = (node.text or "").strip()
                    if content:
                        xml_todos.append(content)
            if xml_todos:
                print(f"[REACT-planing] 从 XML 提取 {len(xml_todos)} 条 todos")
                return xml_todos
    except Exception as e:
        print(f"[REACT-planing] XML todo_list 解析失败，将继续尝试 JSON/文本兜底: {e}")

    # 3. 从文本中抽取 JSON 数组（支持前后有其他文本/标签）
    try:
        # 尽量匹配第一段较“干净”的数组，避免把整个大长串都吃进去
        json_match = re.search(r'\[[\s\S]*?\]', text)
        if json_match:
            json_part = json_match.group(0)
            # 简单剪裁过长内容，防止极端情况
            if len(json_part) > 8000:
                json_part = json_part[:8000]
            arr = json.loads(json_part)
            if isinstance(arr, list):
                json_todos = [str(x).strip() for x in arr if str(x).strip()]
                if json_todos:
                    print(f"[REACT-planing] 从 JSON 数组提取 {len(json_todos)} 条 todos")
                    return json_todos
    except Exception as e:
        print(f"[REACT-planing] JSON 数组解析失败，将继续文本兜底: {e}")

    # 4. 文本兜底：从 <todo_list> 块里按行抽取
    try:
        block = ""
        m = re.search(r'<todo_list[^>]*>([\s\S]*?)</todo_list>', text, re.IGNORECASE)
        if m:
            block = m.group(1)
        else:
            block = text
        lines = [ln.strip() for ln in block.splitlines()]
        for ln in lines:
            if not ln:
                continue
            # 过滤 XML/HTML 标签行
            if ln.startswith("<") and ln.endswith(">"):
                continue
            # 项目符号 / 编号行
            if re.match(r'^[-*•\d]+\s*', ln):
                # 去掉前缀符号
                ln = re.sub(r'^[-*•\d\.\)]+\s*', '', ln).strip()
            if ln:
                todos.append(ln)
        if todos:
            print(f"[REACT-planing] 文本兜底提取 {len(todos)} 条 todos")
            return todos
    except Exception as e:
        print(f"[REACT-planing] 文本兜底解析失败: {e}")

    # 全部失败时，返回空列表，交由上层兜底
    return []


def parse_think_response_for_plan(
    text: Any,
) -> Tuple[List[str], Optional[List[Dict[str, Any]]]]:
    """
    优先解析 THINK 中的一次性 JSON 计划；失败则回退 XML/文本 todos。
    返回 (description 列表, 原始 plan 元数据或 None)。
    """
    if text is None:
        return [], None
    s = text if isinstance(text, str) else str(text)
    jp = parse_react_json_plan(s)
    if jp:
        todos = [str(x.get("description") or "").strip() for x in jp]
        todos = [t for t in todos if t]
        if todos:
            try:
                cap = int((os.getenv("REACT_TODO_MAX_STEPS", "2") or "2").strip())
            except Exception:
                cap = 2
            cap = max(1, cap)
            if len(todos) > cap:
                todos = todos[:cap]
                jp = jp[:cap]
            return todos, jp
    return _cap_todos_for_speed(robust_parse_todos(s)), None


def _cap_todos_for_speed(todos: List[str]) -> List[str]:
    """性能优先：限制首轮 todo 数量，降低整体链路时延。"""
    try:
        cap = int((os.getenv("REACT_TODO_MAX_STEPS", "2") or "2").strip())
    except Exception:
        cap = 2
    cap = max(1, cap)
    if len(todos) > cap:
        if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
            print(f"[REACT-planing] todo_count capped: {len(todos)} -> {cap}")
        return todos[:cap]
    return todos


def _use_react_unified_xml() -> bool:
    """检查是否启用三段式 XML 模式（替代 FC）。"""
    return (os.getenv("REACT_UNIFIED_XML", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _iter_direct_chat_reply_stream_chunks(text: str):
    """纯对话回复按小块产出，走 summary_stream 车道供前端拼接 finalResponse（打字机）。"""
    s = text if isinstance(text, str) else ""
    if not s:
        return
    raw = (os.getenv("REACT_CHAT_REPLY_STREAM") or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        yield s
        return
    try:
        step = max(1, int((os.getenv("REACT_CHAT_REPLY_STREAM_CHARS") or "2").strip()))
    except Exception:
        step = 2
    for i in range(0, len(s), step):
        yield s[i : i + step]


def react_plan_steps_payload(
    todos: List[str],
    *,
    json_plan_meta: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    SSE「plan」事件：与「todos」同步的结构化列表，供前端静态概览与 step_id 对齐。
    json_plan_meta：THINK 一次性 JSON 计划中的条目（含 id/description/status）。
    """
    if json_plan_meta:
        steps: List[Dict[str, Any]] = []
        for idx, it in enumerate(json_plan_meta):
            if not isinstance(it, dict):
                continue
            try:
                sid = int(it.get("id", idx + 1))
            except Exception:
                sid = idx + 1
            desc = str(it.get("description") or it.get("name") or "").strip()
            if not desc and idx < len(todos):
                desc = str(todos[idx])
            st = str(it.get("status") or "pending").lower()
            steps.append({"id": sid, "name": desc, "description": desc, "status": st})
        if steps:
            steps[0]["status"] = "in_progress"
            return steps
    return [{"id": i + 1, "name": str(t), "description": str(t), "status": "pending"} for i, t in enumerate(todos)]


def _plan_rows_from_json_or_todos(
    todos: List[str],
    json_plan_meta: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """task_state['plan'] 行：与 react_plan_steps_payload 字段对齐，供 plan_init / plan_update。"""
    payload = react_plan_steps_payload(todos, json_plan_meta=json_plan_meta)
    rows: List[Dict[str, Any]] = []
    for i, row in enumerate(payload):
        rows.append(
            {
                "id": row.get("id", i + 1),
                "name": row.get("name") or row.get("description") or "",
                "tool": None,
                "params": {},
                "status": row.get("status") or "pending",
                "result": None,
            }
        )
    return rows


def _normalize_plan_rows_for_sse(plan_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in plan_rows:
        out.append(
            {
                "id": r.get("id"),
                "name": r.get("name") or "",
                "description": r.get("name") or "",
                "status": r.get("status") or "pending",
            }
        )
    return out


def _grep_observation_empty_lists(observation: Dict[str, Any]) -> bool:
    """grep locate 成功但三类列表均为空时视为无命中。"""
    if not isinstance(observation, dict):
        return True
    data = observation.get("data") or {}
    if not isinstance(data, dict):
        return True
    n = 0
    for k in ("bug_location", "badcase_analysis", "testcase_location"):
        x = data.get(k)
        if isinstance(x, list):
            n += len(x)
    return n == 0


def _sync_plan_single_in_progress(plan_rows: List[Dict[str, Any]], current_index: int) -> None:
    """全局仅一个 in_progress，其余非终态为 pending。"""
    for j, row in enumerate(plan_rows):
        st = str(row.get("status") or "pending").lower()
        if st in ("failed", "complete", "done"):
            continue
        if j < current_index:
            row["status"] = "complete"
        elif j == current_index:
            row["status"] = "in_progress"
        else:
            row["status"] = "pending"


def new_task_state(mode: str) -> Dict[str, Any]:
    """统一任务状态（与规格对齐）：mode / plan / current_step / observations / finished。"""
    return {
        "mode": mode,
        "plan": [],
        "current_step": 0,
        "observations": [],
        "finished": False,
    }


def _react_plan_sse_suppress_ui(todos_count: int) -> bool:
    """§6.6：待办步数少于阈值时不发「计划区」首包 mirror，plan_init 带 suppress_plan_ui。"""
    try:
        min_steps = int(os.getenv("REACT_PLAN_SSE_MIN_STEPS", "3"))
    except Exception:
        min_steps = 3
    return min_steps > 0 and todos_count < min_steps


def _plan_memo_defer_until_after_think() -> bool:
    """首轮流式思考前不暴露「规划备忘」SSE 镜像：plan_init 强制 suppress，由前端 THINK 就绪后揭示。"""
    v = (os.getenv("REACT_PLAN_MEMO_AFTER_THINK", "1") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _should_suppress_plan_ui(
    todos_count: int, intent_wants_plan_ui: Optional[bool]
) -> bool:
    """
    统一「规划备忘」是否隐藏：
    - 步数 < REACT_PLAN_SSE_MIN_STEPS（默认 3）时隐藏。
    """
    plan_ui_enabled = (os.getenv("REACT_INTENT_PLAN_UI_ENABLED", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    npu = intent_wants_plan_ui if plan_ui_enabled else None
    if npu is False:
        return True
    return _react_plan_sse_suppress_ui(todos_count)


def use_react_observe_ui_llm() -> bool:
    """REACT_OBSERVE_UI_LLM=0 时 decision_observe 走 summary_nl，不调 ui_observe_summary LLM。"""
    v = (os.getenv("REACT_OBSERVE_UI_LLM", "1") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def use_react_incremental_running_summary() -> bool:
    """默认开启；REACT_INCREMENTAL_SUMMARY=0/false/off 关闭。"""
    v = (os.getenv("REACT_INCREMENTAL_SUMMARY", "1") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def use_react_incremental_running_summary_block_loop() -> bool:
    """REACT_INCREMENTAL_SUMMARY_BLOCK_LOOP=1 时主循环内 await 每步静默合并（旧行为）。"""
    v = (os.getenv("REACT_INCREMENTAL_SUMMARY_BLOCK_LOOP", "0") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def use_react_incremental_running_summary_stream_sse() -> bool:
    """
    REACT_INCREMENTAL_SUMMARY_STREAM_SSE=0 关闭；默认 1：
    仅影响「主循环结束」后下发方式（running_summary_done 整块 vs final_wire 切片重放）。
    每步中途合并默认走后台队列静默 LLM，不阻塞主循环、不在中途占用 SSE（与底部隐藏策略一致）。
    """
    v = (os.getenv("REACT_INCREMENTAL_SUMMARY_STREAM_SSE", "1") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


_react_project_plan_name_cache_lock = threading.Lock()
# (project_id, plan_id) -> (project_name, plan_name, monotonic_ts)
# 进程级内存缓存作为 L1，Redis 作为 L2
_react_project_plan_name_cache: Dict[Tuple[int, int], Tuple[Optional[str], Optional[str], float]] = {}


def _react_project_plan_name_cache_ttl_s() -> float:
    """项目/计划名称缓存秒数；<=0 表示不缓存。默认 300（5分钟），见 REACT_PROJECT_PLAN_NAME_CACHE_TTL。"""
    try:
        v = float((os.getenv("REACT_PROJECT_PLAN_NAME_CACHE_TTL") or "300").strip())
    except Exception:
        v = 300.0
    return v


def _get_redis_client_for_cache():
    """获取 Redis 客户端（用于缓存），失败返回 None。"""
    try:
        from app import get_redis_client
        return get_redis_client()
    except Exception:
        return None


def _sync_load_project_plan_names(
    project_id: Optional[int],
    plan_id: Optional[int],
    perf: bool,
) -> Tuple[Optional[str], Optional[str]]:
    """在 app_context 内查 Project/Plan 名称；优先 Redis 缓存，其次进程内存缓存，最后查库。"""
    v_lookup = (os.getenv("REACT_PROJECT_PLAN_NAME_LOOKUP", "1") or "1").strip().lower()
    if v_lookup in ("0", "false", "no", "off"):
        if perf:
            print("[PERF][react] project_plan_lookup_skipped=1")
        return None, None
    
    if plan_id is None or (isinstance(plan_id, (int, str)) and str(plan_id).strip() in ("", "0", "None", "null")):
        plan_id = 0
    pid = int(project_id) if project_id is not None else 0
    plid = int(plan_id) if plan_id is not None else 0
    if pid <= 0 and plid <= 0:
        return None, None
    
    key = (pid, plid)
    redis_key = f"react:project_plan_name:{pid}:{plid}"
    ttl = _react_project_plan_name_cache_ttl_s()
    now = time.monotonic()
    
    # L1: 进程内存缓存
    if ttl > 0:
        with _react_project_plan_name_cache_lock:
            hit = _react_project_plan_name_cache.get(key)
            if hit is not None:
                pn0, pln0, t0 = hit
                if now - t0 < ttl:
                    if perf:
                        print("[PERF][react] project_plan_lookup_memory_cache_hit=1")
                    return pn0, pln0
    
    # L2: Redis 缓存
    redis_client = _get_redis_client_for_cache()
    if redis_client is not None:
        try:
            cached = redis_client.get(redis_key)
            if cached:
                import json
                data = json.loads(cached)
                project_name = data.get("project_name")
                plan_name = data.get("plan_name")
                if perf:
                    print("[PERF][react] project_plan_lookup_redis_cache_hit=1")
                # 写入 L1 内存缓存
                if ttl > 0:
                    with _react_project_plan_name_cache_lock:
                        _react_project_plan_name_cache[key] = (project_name, plan_name, now)
                return project_name, plan_name
        except Exception as e:
            if perf:
                print(f"[PERF][react] project_plan_lookup_redis_error={e}")
    
    # L3: 查库
    project_name: Optional[str] = None
    plan_name: Optional[str] = None
    try:
        from app import app, db, Project, Plan

        with app.app_context():
            t_db0 = time.perf_counter()
            if pid > 0:
                project = db.session.get(Project, pid)
                if project is not None:
                    project_name = project.name
            if plid > 0:
                plan = db.session.get(Plan, plid)
                if plan is not None:
                    plan_name = plan.name
            if perf:
                print(f"[PERF][react] project_plan_lookup_db_ms={(time.perf_counter()-t_db0)*1000:.1f}")
    except Exception as e:
        print(f"[REACT] 获取项目/计划名称失败：{e}")
    
    # 写入 L1 内存缓存
    if ttl > 0:
        with _react_project_plan_name_cache_lock:
            _dead = [
                k
                for k, (_, _, t0) in _react_project_plan_name_cache.items()
                if now - t0 >= ttl
            ]
            for k in _dead:
                del _react_project_plan_name_cache[k]
            _react_project_plan_name_cache[key] = (project_name, plan_name, now)
    
    # 写入 L2 Redis 缓存
    if redis_client is not None and ttl > 0:
        try:
            import json
            redis_client.setex(redis_key, int(ttl), json.dumps({
                "project_name": project_name,
                "plan_name": plan_name,
            }))
        except Exception:
            pass
    
    return project_name, plan_name


def _react_think_queue_poll_s() -> float:
    """首轮 THINK 流式队列轮询 sleep；默认 0.03s，见 REACT_THINK_QUEUE_POLL_S。"""
    try:
        v = float((os.getenv("REACT_THINK_QUEUE_POLL_S") or "0.03").strip())
    except Exception:
        v = 0.03
    return max(0.02, min(v, 0.2))


def _summary_stream_yield_gap_s() -> float:
    """summary 类 SSE 分片之间的墙钟暂停，便于浏览器逐帧显示。REACT_SUMMARY_STREAM_GAP_MS，默认 22ms。"""
    try:
        ms = int((os.getenv("REACT_SUMMARY_STREAM_GAP_MS") or "22").strip())
    except Exception:
        ms = 22
    return max(0, ms) / 1000.0


def _running_summary_wire_yield_gap_s() -> float:
    """终局 running_summary_stream 分片间隔；未单独设置时与 _summary_stream_yield_gap_s 一致。"""
    raw = (os.getenv("REACT_RUNNING_SUMMARY_STREAM_GAP_MS") or "").strip()
    if raw:
        try:
            ms = int(raw)
        except Exception:
            ms = 22
        return max(0, ms) / 1000.0
    return _summary_stream_yield_gap_s()


def react_think_max_tokens() -> Optional[int]:
    """REACT_THINK_MAX_TOKENS：正整数则限制首轮规划流式输出长度；否则 None（不传）。"""
    raw = (os.getenv("REACT_THINK_MAX_TOKENS") or "").strip()
    if raw.isdigit():
        v = int(raw)
        return v if v > 0 else None
    return None


def prefer_nl_observe_summary(tool: Optional[str], observation: Any) -> bool:
    """沙箱预览/待确认等场景优先走 summary_nl，避免 observe 总结首字等待。"""
    t = str(tool or "").strip().lower()
    d = observation if isinstance(observation, dict) else {}
    dd = d.get("data") if isinstance(d.get("data"), dict) else {}
    batch_results = d.get("batch_results") if isinstance(d.get("batch_results"), list) else []
    # modify + 预览确认场景：用现成 summary_nl 即可，没必要再等一轮 LLM 总结
    if t == "modify":
        if d.get("confirmation_required") or dd.get("confirmation_required"):
            return True
        if d.get("batch_modify") or dd.get("batch_modify") or len(batch_results) > 0:
            return True
        if d.get("sandbox_preview") or dd.get("sandbox_preview"):
            return True
    # grep 定位结果已有高质量 summary（含数量/目标等），不再额外调用一轮 UI 总结 LLM，
    # 否则会在「决策与观察」阶段引入显著等待（常见 10s+）。
    if t == "grep":
        return True
    # 通用兜底：只要出现 sandbox 预览结构，也优先直出
    if d.get("sandbox_preview") or dd.get("sandbox_preview"):
        return True
    return False


def prefer_fast_observe_stub(tool: Optional[str], observation: Any) -> bool:
    """
    modify 且沙箱预览/待确认/批量：跳过大模型 observe_prompt，用本地 <result> 占位。
    与 prefer_nl_observe_summary 不同：后者只省 UI 总结 LLM；本开关省整条 observe 分析流。
    """
    v = (os.getenv("REACT_OBSERVE_FAST_STUB", "1") or "1").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    t = str(tool or "").strip().lower()
    if t != "modify":
        return False
    d = observation if isinstance(observation, dict) else {}
    dd = d.get("data") if isinstance(d.get("data"), dict) else {}
    dr = d.get("result") if isinstance(d.get("result"), dict) else {}
    if (
        d.get("sandbox_preview")
        or dd.get("sandbox_preview")
        or dr.get("sandbox_preview")
    ):
        return True
    if (
        d.get("confirmation_required")
        or dd.get("confirmation_required")
        or dr.get("confirmation_required")
    ):
        return True
    if d.get("batch_modify") or dd.get("batch_modify") or dr.get("batch_modify"):
        return True
    br = d.get("batch_results")
    if isinstance(br, list) and len(br) > 0:
        return True
    return False


def prefer_fast_observe_stub_grep(tool: Optional[str], observation: Any) -> bool:
    """
    grep 定位（locate）成功时跳过 observe_prompt LLM，用 summary_nl 生成最小 <result>。
    associate/compare 等仍走完整观察分析，避免丢合并/对比类结论。
    """
    v = (os.getenv("REACT_GREP_OBSERVE_FAST_STUB", "1") or "1").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if str(tool or "").strip().lower() != "grep":
        return False
    d = observation if isinstance(observation, dict) else {}
    if d.get("success") is False:
        return False
    mode = str(d.get("mode") or "locate").strip().lower()
    if mode != "locate":
        return False
    return True


def stub_observe_result_xml(nl: str) -> str:
    """供 parse_xml_findings 解析的最小 <result>，正文来自 summary_nl。"""
    safe = (nl or "").strip()
    if not safe:
        safe = "沙箱预览已生成，请确认变更。"
    safe = html.escape(safe, quote=False)
    return (
        "<result><key_findings>"
        f'<finding type="info">{safe}</finding>'
        "</key_findings>"
        "<context_update>{}</context_update>"
        "<next_step></next_step>"
        "</result>"
    )


def use_react_merge_observe_decide() -> bool:
    """已下线：observe+decide 合并链路，固定关闭。"""
    return False


def observe_prompt_shrink_enabled() -> bool:
    v = (os.getenv("REACT_OBSERVE_PROMPT_SHRINK", "1") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def decide_prompt_shrink_enabled() -> bool:
    v = (os.getenv("REACT_DECIDE_PROMPT_SHRINK", "1") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _shrink_json_payload(
    obj: Any, *, cap_list: int, cap_str: int, max_depth: int
) -> Any:
    def _walk(x: Any, depth: int) -> Any:
        if depth <= 0:
            return "…"
        if isinstance(x, str):
            if len(x) > cap_str:
                return x[:cap_str] + f"…(截断,len={len(x)})"
            return x
        if isinstance(x, list):
            if len(x) > cap_list:
                x = x[:cap_list]
            return [_walk(y, depth - 1) for y in x]
        if isinstance(x, dict):
            return {str(k): _walk(v, depth - 1) for k, v in x.items()}
        if isinstance(x, (int, float, bool)) or x is None:
            return x
        return str(x)[:cap_str]

    try:
        clone = json.loads(json.dumps(obj, ensure_ascii=False, default=str))
    except Exception:
        return obj
    return _walk(clone, max_depth)


def shrink_payload_for_observe_prompt(obj: Any) -> Any:
    """缩小 observe_prompt / ui_observe_summary 中的 JSON，降 prompt 体积与 TTFT。"""
    if not observe_prompt_shrink_enabled() or obj is None:
        return obj
    try:
        cap_list = max(1, int((os.getenv("REACT_OBSERVE_PROMPT_LIST_CAP") or "15").strip()))
    except Exception:
        cap_list = 15
    try:
        cap_str = max(32, int((os.getenv("REACT_OBSERVE_PROMPT_STR_CHARS") or "500").strip()))
    except Exception:
        cap_str = 500
    try:
        max_depth = max(1, int((os.getenv("REACT_OBSERVE_PROMPT_MAX_DEPTH") or "14").strip()))
    except Exception:
        max_depth = 14
    return _shrink_json_payload(obj, cap_list=cap_list, cap_str=cap_str, max_depth=max_depth)


def decide_prompt_shrink_caps_base() -> Tuple[int, int, int]:
    """通用 decide 裁剪参数（与原先 shrink_payload_for_decide_prompt 一致）。"""
    try:
        cl_o = max(1, int((os.getenv("REACT_OBSERVE_PROMPT_LIST_CAP") or "15").strip()))
    except Exception:
        cl_o = 15
    raw_cl = (os.getenv("REACT_DECIDE_PROMPT_LIST_CAP") or "").strip()
    try:
        cap_list = max(1, int(raw_cl)) if raw_cl else cl_o
    except Exception:
        cap_list = cl_o
    try:
        cs_o = max(32, int((os.getenv("REACT_OBSERVE_PROMPT_STR_CHARS") or "500").strip()))
    except Exception:
        cs_o = 500
    raw_cs = (os.getenv("REACT_DECIDE_PROMPT_STR_CHARS") or "").strip()
    try:
        cap_str = max(32, int(raw_cs)) if raw_cs else cs_o
    except Exception:
        cap_str = cs_o
    try:
        md_o = max(1, int((os.getenv("REACT_OBSERVE_PROMPT_MAX_DEPTH") or "14").strip()))
    except Exception:
        md_o = 14
    raw_md = (os.getenv("REACT_DECIDE_PROMPT_MAX_DEPTH") or "").strip()
    try:
        max_depth = max(1, int(raw_md)) if raw_md else md_o
    except Exception:
        max_depth = md_o
    return cap_list, cap_str, max_depth


def use_react_decide_after_grep_tight_shrink() -> bool:
    """上一工具为 grep 时是否对 decide prompt 再收紧列表/字符串/深度（默认开）。"""
    v = (os.getenv("REACT_DECIDE_AFTER_GREP_SHRINK", "1") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def decide_prompt_shrink_caps_for_prev_tool(prev_tool: Optional[str]) -> Tuple[int, int, int]:
    bl, bs, bd = decide_prompt_shrink_caps_base()
    if str(prev_tool or "").strip().lower() != "grep":
        return bl, bs, bd
    if not use_react_decide_after_grep_tight_shrink():
        return bl, bs, bd
    try:
        tg_l = max(1, int((os.getenv("REACT_DECIDE_AFTER_GREP_LIST_CAP") or "8").strip()))
    except Exception:
        tg_l = 8
    try:
        tg_s = max(32, int((os.getenv("REACT_DECIDE_AFTER_GREP_STR_CHARS") or "280").strip()))
    except Exception:
        tg_s = 280
    try:
        tg_d = max(1, int((os.getenv("REACT_DECIDE_AFTER_GREP_MAX_DEPTH") or "12").strip()))
    except Exception:
        tg_d = 12
    return min(bl, tg_l), min(bs, tg_s), min(bd, tg_d)


def shrink_payload_for_decide_prompt(
    obj: Any, prev_tool: Optional[str] = None
) -> Any:
    """缩小 decide_prompt 中的上下文与上一步观察/分析。prev_tool 为上一执行工具名（如 grep）时可收紧裁剪。"""
    if not decide_prompt_shrink_enabled() or obj is None:
        return obj
    cap_list, cap_str, max_depth = decide_prompt_shrink_caps_for_prev_tool(prev_tool)
    return _shrink_json_payload(obj, cap_list=cap_list, cap_str=cap_str, max_depth=max_depth)


def resolve_decide_max_tokens_for_prev_tool(prev_tool: Optional[str]) -> Optional[int]:
    """流式 decide 的 max_tokens：grep 后一轮可读 REACT_DECIDE_AFTER_GREP_MAX_TOKENS 覆盖。"""
    mt_raw = (os.getenv("REACT_DECIDE_MAX_TOKENS") or "").strip()
    out: Optional[int] = int(mt_raw) if mt_raw.isdigit() else None
    if out is not None and out <= 0:
        out = None
    if str(prev_tool or "").strip().lower() != "grep":
        return out
    ag = (os.getenv("REACT_DECIDE_AFTER_GREP_MAX_TOKENS") or "").strip()
    if ag.isdigit():
        v = int(ag)
        if v > 0:
            return v
    return out


async def merge_observe_parallel_ui_first(
    gen_observe: AsyncIterator[Dict[str, Any]],
    gen_ui: AsyncIterator[Dict[str, Any]],
    *,
    ui_lead: Optional[List[Dict[str, Any]]] = None,
    timings_ms: Optional[Dict[str, float]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    observe 与 decision_observe 并行跑 LLM。先发 ui_lead（首包标题等仍优先），
    之后 **交错** 下发：在等新 UI token 前先 flush 已到达的 observe 事件，
    避免「整段 UI 总结发完后才 flush observe」——合并流里靠后的 agent_thought
    会让 Thought 区长时间空白（主卡片已显示观察结论）。
    """
    q: asyncio.Queue = asyncio.Queue()
    SENT = object()

    async def pump_observe() -> None:
        t0 = time.perf_counter()
        try:
            async for ev in gen_observe:
                await q.put(ev)
        finally:
            if timings_ms is not None:
                timings_ms["observe_stream"] = (time.perf_counter() - t0) * 1000.0
            await q.put(SENT)

    obs_task = asyncio.create_task(pump_observe())
    try:
        t_ui = time.perf_counter()
        if ui_lead:
            for ev in ui_lead:
                yield ev

        ui_it = gen_ui.__aiter__()
        obs_closed = False
        _pending_ui: Optional[Dict[str, Any]] = None

        def _flush_ob_nowait() -> Iterator[Dict[str, Any]]:
            nonlocal obs_closed
            while True:
                try:
                    item = q.get_nowait()
                except asyncio.QueueEmpty:
                    return
                if item is SENT:
                    obs_closed = True
                    return
                yield item

        while True:
            if _pending_ui is not None:
                yield _pending_ui
                _pending_ui = None
                for ev in _flush_ob_nowait():
                    yield ev
                if obs_closed:
                    try:
                        async for ev in ui_it:
                            yield ev
                    except StopAsyncIteration:
                        pass
                    break
                continue

            for ev in _flush_ob_nowait():
                yield ev
            if obs_closed:
                try:
                    async for ev in ui_it:
                        yield ev
                except StopAsyncIteration:
                    pass
                break

            get_t = asyncio.create_task(q.get())
            ui_t = asyncio.create_task(ui_it.__anext__())
            done, _ = await asyncio.wait(
                {get_t, ui_t}, return_when=asyncio.FIRST_COMPLETED
            )

            if get_t in done:
                item = get_t.result()
                if ui_t in done:
                    try:
                        _pending_ui = ui_t.result()
                    except StopAsyncIteration:
                        _pending_ui = None
                else:
                    ui_t.cancel()
                    try:
                        await ui_t
                    except asyncio.CancelledError:
                        pass
                if item is SENT:
                    obs_closed = True
                    if _pending_ui is not None:
                        yield _pending_ui
                        _pending_ui = None
                    try:
                        async for ev in ui_it:
                            yield ev
                    except StopAsyncIteration:
                        pass
                    break
                yield item
                continue

            get_t.cancel()
            try:
                await get_t
            except asyncio.CancelledError:
                pass
            try:
                ev = ui_t.result()
                yield ev
            except StopAsyncIteration:
                while True:
                    item = await q.get()
                    if item is SENT:
                        break
                    yield item
                break

        if timings_ms is not None:
            timings_ms["ui_summary"] = (time.perf_counter() - t_ui) * 1000.0
        await obs_task
    finally:
        if not obs_task.done():
            obs_task.cancel()
            try:
                await obs_task
            except asyncio.CancelledError:
                pass


def _modify_wait_heartbeat_should_emit(
    last_emitted_bucket: Optional[int], waited_s: float
) -> Tuple[bool, int]:
    """
    modify 轮询「修改中…已等待 Ns」：同一整数 N 只下发一次，避免 0.28s 一轮时 N 秒重复刷多行。
    返回 (是否下发, 用于展示的 N)。last_emitted_bucket 为 None 表示尚未下发过心跳。
    """
    b = int(max(0.0, waited_s))
    if last_emitted_bucket is None:
        return True, b
    if b > last_emitted_bucket:
        return True, b
    return False, b


def _modify_progress_to_stream_event(
    msg: Union[str, Any], step_index: int, reason: str
) -> Dict[str, Any]:
    """modify 进度队列：普通进度文案，或批量预览结构化事件（前缀见 modify_tool.MODIFY_BATCH_ROW_PREFIX）。"""
    from agents.tools.modify_tool import MODIFY_BATCH_ROW_PREFIX

    sm = str(msg)
    if sm.startswith(MODIFY_BATCH_ROW_PREFIX):
        try:
            row = json.loads(sm[len(MODIFY_BATCH_ROW_PREFIX) :])
        except Exception:
            row = None
        if isinstance(row, dict):
            return {
                "event": "batch_preview_row",
                "tool": "modify",
                "reason": reason,
                "index": step_index,
                "row": row,
            }
    return {
        "event": "executing",
        "tool": "modify",
        "reason": reason,
        "index": step_index,
        "message": sm,
    }


class SimplifiedReActEngine:
    """增强版极简 ReAct 引擎 -集 Skill + Text2SQL"""
    
    def __init__(self, llm, tool_registry, skill_dir=".qoder/skills"):
        """初始化"""
        self.llm = llm
        self.tools = tool_registry
        self.correction_engine = SelfCorrectionEngine(llm)  # 自我修正引擎
        self.project_id = None  # 当前项目 ID
        
        # Skill动态加载
        self.skill_loader = SkillLoader(skill_dir)
        self.skill_registry = skill_registry
        print(f"[REACT]💡引擎已初始化，Skill目录: {skill_dir}")
        
        # Text2SQL
        # Text2SQL 懒加载：只在真正需要自然语言SQL时再初始化（避免每次请求前置 1s+）
        self.text2sql_tool = None
        if TEXT2SQL_AVAILABLE:
            print("[REACT] ✅ Text2SQL可用（懒加载）")
        else:
            print("[REACT] ⚠️  Text2SQL 不可用")
        # 线程池：modify 等工具内部有同步 DB（Flask/SQLAlchemy），在事件循环中会阻塞，导致流式“修改中...”卡住
        self._tool_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="react_tool")
        self._ui_locale = "zh"
        self._pending_diff_context = {}
        self._grep_result_cache: Dict[str, Tuple[float, Any]] = {}

    @staticmethod
    def _normalize_modify_target(target: Any) -> str:
        t = (str(target or "badcase")).strip().lower().replace("-", "_")
        if t in ("test_case", "testcase"):
            return "testcase"
        if t in ("bug", "badcase"):
            return t
        return "badcase"

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

    @staticmethod
    def _has_effective_change(diff: Any, modifications: Any) -> bool:
        if isinstance(modifications, dict):
            for _, v in modifications.items():
                if isinstance(v, dict) and ("old" in v or "new" in v):
                    if str(v.get("old", "")) != str(v.get("new", "")):
                        return True
                elif v not in (None, ""):
                    return True
        if isinstance(diff, list):
            for fd in diff:
                if not isinstance(fd, dict):
                    continue
                lines = fd.get("lines") or []
                old_line = next((l for l in lines if isinstance(l, dict) and l.get("type") == "delete"), None)
                new_line = next((l for l in lines if isinstance(l, dict) and l.get("type") == "add"), None)
                if str((old_line or {}).get("content", "")) != str((new_line or {}).get("content", "")):
                    return True
        return False

    def _relevant_pending_for_llm(self, user_input: str) -> List[Dict[str, Any]]:
        """仅挑选与当前对话相关的 pending diff，避免把无关记录给大模型。"""
        items = list(self._pending_diff_context.values())
        if not items:
            return []
        # 仅保留有实际改动的项
        items = [x for x in items if self._has_effective_change(x.get("diff"), x.get("modifications"))]
        if not items:
            return []

        text = str(user_input or "")
        lower = text.lower()
        # 1) 用户明确提到 ID 时，仅保留这些 ID
        ids = set()
        for m in re.findall(r"\d+", text):
            try:
                ids.add(int(m))
            except Exception:
                pass
        if ids:
            by_id = [x for x in items if int(x.get("target_id")) in ids]
            if by_id:
                items = by_id

        # 2) 用户意图目标类型过滤（bug / badcase / testcase）
        inferred = infer_modify_target_from_user(text) or ""
        inferred = self._normalize_modify_target(inferred)
        if inferred in ("bug", "badcase", "testcase"):
            by_t = [x for x in items if self._normalize_modify_target(x.get("target")) == inferred]
            if by_t:
                items = by_t
        else:
            # 关键词弱过滤（未明确意图时）
            if "bug" in lower:
                by_t = [x for x in items if self._normalize_modify_target(x.get("target")) == "bug"]
                if by_t:
                    items = by_t
            elif ("测试用例" in text) or ("testcase" in lower) or ("test case" in lower):
                by_t = [x for x in items if self._normalize_modify_target(x.get("target")) == "testcase"]
                if by_t:
                    items = by_t
            elif "badcase" in lower:
                by_t = [x for x in items if self._normalize_modify_target(x.get("target")) == "badcase"]
                if by_t:
                    items = by_t

        # 防止上下文过大，截断条数；信息用于 think/decide 提示，不需要全量
        return items[:8]

    def _wrap_prompt(self, prompt: str) -> str:
        return wrap_react_user_prompt(prompt, getattr(self, "_ui_locale", None))

    @contextlib.contextmanager
    def _llm_no_thinking(self):
        """与 run_stream 内 _NoThinking 一致：modify 决策/提取 modifications 时临时关闭思考模式。"""
        try:
            if hasattr(self.llm, "force_disable_thinking"):
                setattr(self.llm, "force_disable_thinking", True)
            yield
        finally:
            if hasattr(self.llm, "force_disable_thinking"):
                setattr(self.llm, "force_disable_thinking", False)

    @contextlib.contextmanager
    def _react_force_thinking_ctx(self, stream_kind: str):
        """占位：历史代码用 with 包裹；不再开启模型侧深度思考（enable_thinking）。"""
        del stream_kind  # unused
        yield

    def _resolve_chat_stream_iter(
        self,
        prompt: str,
        history: Optional[list] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        统一流式迭代：优先 chat_stream_with_reasoning，否则 chat_stream_fallback_chunks（直连 prompt，禁止 parse_intent 聚合）。
        max_tokens：若被调用方签名支持则传入（如部分 Qwen 实现）；否则忽略。
        """
        import inspect

        fn = getattr(self.llm, "chat_stream_with_reasoning", None)
        if callable(fn):
            _kw: Dict[str, Any] = {}
            if max_tokens is not None:
                try:
                    if "max_tokens" in inspect.signature(fn).parameters:
                        _kw["max_tokens"] = max_tokens
                except (TypeError, ValueError):
                    pass
            return fn(prompt, history, **_kw) if _kw else fn(prompt, history)
        fb = getattr(self.llm, "chat_stream_fallback_chunks", None)
        if callable(fb):
            _kw2: Dict[str, Any] = {}
            if max_tokens is not None:
                try:
                    if "max_tokens" in inspect.signature(fb).parameters:
                        _kw2["max_tokens"] = max_tokens
                except (TypeError, ValueError):
                    pass
            return fb(prompt, history, **_kw2) if _kw2 else fb(prompt, history)
        raise RuntimeError(
            f"LLM {type(self.llm).__name__} 须实现 chat_stream_with_reasoning 或 chat_stream_fallback_chunks"
        )

    def _resolve_chat_stream_iter_content_only(
        self,
        prompt: str,
        history: Optional[list] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        仅正文流：不启用模型侧 enable_thinking / reasoning_delta，用于 Agent 自然语言与 decide/observe 正文。
        首轮 ReAct think 在 REACT_THINK_CONTENT_ONLY=1 时走本方法：上游无 reasoning_delta，SSE 侧以 todos_stream 承载主文流。
        max_tokens：若 LLM.chat_stream 签名支持则传入（如 Qwen 兼容）；否则忽略。
        """
        import inspect

        # 须在实际迭代 LLM 流时保持 force_disable_thinking：若用外层 with + return generator，
        # 会在首次 next 之前 __exit__，导致 Qwen 仍带 enable_thinking、千帆仍用 X1 推理模型。
        fn = getattr(self.llm, "chat_stream", None)
        if callable(fn):
            stream_kw: Dict[str, Any] = {}
            if max_tokens is not None:
                try:
                    if "max_tokens" in inspect.signature(fn).parameters:
                        stream_kw["max_tokens"] = max_tokens
                except (TypeError, ValueError):
                    pass

            def _gen():
                try:
                    if hasattr(self.llm, "force_disable_thinking"):
                        setattr(self.llm, "force_disable_thinking", True)
                    try:
                        for piece in fn(prompt, history, **stream_kw):
                            if isinstance(piece, str) and piece:
                                yield {"type": "content_delta", "delta": piece}
                    except Exception as e:
                        yield {"type": "content_delta", "delta": f"Error: {e}"}
                    yield {"type": "done"}
                finally:
                    if hasattr(self.llm, "force_disable_thinking"):
                        setattr(self.llm, "force_disable_thinking", False)

            return _gen()
        fn2 = getattr(self.llm, "chat_stream_with_reasoning", None)
        if callable(fn2):

            def _gen2():
                try:
                    if hasattr(self.llm, "force_disable_thinking"):
                        setattr(self.llm, "force_disable_thinking", True)
                    try:
                        _f2_kw: Dict[str, Any] = {}
                        if max_tokens is not None:
                            try:
                                if "max_tokens" in inspect.signature(fn2).parameters:
                                    _f2_kw["max_tokens"] = max_tokens
                            except (TypeError, ValueError):
                                pass
                        _it2 = (
                            fn2(prompt, history, **_f2_kw)
                            if _f2_kw
                            else fn2(prompt, history)
                        )
                        for item in _it2:
                            if isinstance(item, dict) and item.get("type") == "content_delta":
                                yield item
                    except Exception as e:
                        yield {"type": "content_delta", "delta": f"Error: {e}"}
                    yield {"type": "done"}
                finally:
                    if hasattr(self.llm, "force_disable_thinking"):
                        setattr(self.llm, "force_disable_thinking", False)

            return _gen2()
        raise RuntimeError(
            f"LLM {type(self.llm).__name__} 须实现 chat_stream 或 chat_stream_with_reasoning"
        )

    async def _collect_llm_text(self, prompt: str) -> str:
        """
        仅聚合正文（不向前端 yield），用于内部 JSON/参数提取等。
        与界面同源：只走 _resolve_chat_stream_iter（禁止 parse_intent）。
        """
        def _sync_collect():
            parts: List[str] = []
            try:
                for item in self._resolve_chat_stream_iter(prompt):
                    if not isinstance(item, dict):
                        continue
                    if item.get('type') == 'content_delta':
                        d = item.get('delta') or ''
                        if d:
                            parts.append(d)
            except Exception as e:
                return f'Error: {e}'
            return ''.join(parts).strip()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._tool_executor, _sync_collect)

    async def _stream_llm_text(self, prompt: str):
        """
        流式收集 LLM 文本输出，边收边 yield。
        用于合并模式下首轮决定。
        """
        q: asyncio.Queue = asyncio.Queue()
        DONE = object()
        # 在主线程获取事件循环，避免子线程中获取失败（Python 3.12）
        main_loop = asyncio.get_running_loop()
        
        def _sync_producer():
            try:
                for item in self._resolve_chat_stream_iter(prompt):
                    if not isinstance(item, dict):
                        continue
                    if item.get('type') == 'content_delta':
                        d = item.get('delta') or ''
                        if d:
                            # 使用主线程的事件循环
                            asyncio.run_coroutine_threadsafe(q.put(d), main_loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(q.put(f'Error: {e}'), main_loop)
            finally:
                asyncio.run_coroutine_threadsafe(q.put(DONE), main_loop)
        
        # 启动生产者线程
        threading.Thread(target=_sync_producer, daemon=True).start()
        
        # 异步消费
        while True:
            item = await q.get()
            if item is DONE:
                break
            if isinstance(item, str):
                yield item

    async def _collect_llm_text_content_only(
        self, prompt: str, max_tokens: Optional[int] = None
    ) -> str:
        """与 observe 流式同源：仅正文 + 可选 max_tokens（Qwen chat_stream 等）。用于同步 run() observe。"""
        def _sync_collect():
            parts: List[str] = []
            try:
                for item in self._resolve_chat_stream_iter_content_only(
                    prompt, None, max_tokens
                ):
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "content_delta":
                        d = item.get("delta") or ""
                        if d:
                            parts.append(d)
            except Exception as e:
                return f"Error: {e}"
            return "".join(parts).strip()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._tool_executor, _sync_collect)

    @staticmethod
    def _grep_cache_key(params: Dict[str, Any]) -> str:
        facet = {
            k: params.get(k)
            for k in (
                "project_id",
                "keywords",
                "target",
                "mode",
                "plan_id",
                "userId",
            )
        }
        return json.dumps(facet, sort_keys=True, ensure_ascii=False, default=str)

    def _parse_react_fc_tool_choice(self) -> Any:
        raw = os.getenv("REACT_FC_TOOL_CHOICE", "auto").strip() or "auto"
        if raw.startswith("{"):
            try:
                return json.loads(raw)
            except Exception:
                return "auto"
        return raw

    @staticmethod
    def _fc_normalize_assistant_message(resp: Any) -> Any:
        if resp is None:
            return None
        if isinstance(resp, dict):
            ch = resp.get("choices")
            if isinstance(ch, (list, tuple)) and ch:
                m = (ch[0] or {}).get("message")
                if m is not None:
                    return m
            return resp
        ch = getattr(resp, "choices", None)
        if ch and len(ch) > 0:
            return getattr(ch[0], "message", None) or ch[0]
        return resp

    async def _react_decide_function_call(
        self,
        decision_prompt: str,
        *,
        step_index: int,
        prev_tool: Optional[str] = None,
        opening_merge: bool = False,
    ) -> Tuple[Dict[str, Any], str]:
        from .react_function_call import (
            build_react_decision_tools_from_registry,
            decision_from_assistant_message,
        )

        # 合并模式：不使用 FC 工具，直接让 LLM 输出 JSON
        if opening_merge:
            text = await self._collect_llm_text(decision_prompt)
            # 使用新的解析函数
            _parsed = parse_opening_decision(text)
            _type = _parsed.get("type")
            
            if _type == "single":
                decision = {
                    "execute": True,
                    "tool": _parsed.get("tool", ""),
                    "params": _parsed.get("params", {}),
                    "reason": "opening_single_step_fc",
                }
            elif _type == "multi":
                decision = {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": "opening_multi_step",
                    "plan": _parsed.get("plan", []),
                }
            elif _type == "chat":
                decision = {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": "chat",
                    "message": _parsed.get("message", ""),
                }
            else:
                # unknown 类型，尝试从原始文本解析
                decision = parse_xml_decision(text) if use_react_decide_xml_fallback() else {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": "opening_unknown",
                }
            
            return decision, text

        # 非合并模式：使用 FC 工具
        tools = build_react_decision_tools_from_registry(self.tools)
        if not tools:
            text = await self._collect_llm_text(decision_prompt)
            return (
                parse_xml_decision(text)
                if use_react_decide_xml_fallback()
                else {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": "decide_fc_empty_registry",
                },
                text,
            )

        _xml_hint = (
            "若无法调用函数，可输出 <decision>...</decision>。"
            if use_react_decide_xml_fallback()
            else ""
        )
        prompt_fc = (
            decision_prompt
            + "\n\n（请用 function calling 指定工具与参数；不要输出 <decision> XML。"
            + (_xml_hint and " " + _xml_hint)
            + "）"
        )
        messages = [{"role": "user", "content": prompt_fc}]
        llm = self.llm
        tool_choice = self._parse_react_fc_tool_choice()
        parallel = os.getenv("REACT_FC_PARALLEL_TOOL_CALLS", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        max_tok_fc: Optional[int] = None
        for _k in ("REACT_DECIDE_FC_MAX_TOKENS", "REACT_DECIDE_MAX_TOKENS"):
            _raw_mt = (os.getenv(_k) or "").strip()
            if _raw_mt.isdigit():
                _v = int(_raw_mt)
                if _v > 0:
                    max_tok_fc = _v
                    break
        if str(prev_tool or "").strip().lower() == "grep":
            _ag_fc = (
                (os.getenv("REACT_DECIDE_AFTER_GREP_FC_MAX_TOKENS") or "").strip()
                or (os.getenv("REACT_DECIDE_AFTER_GREP_MAX_TOKENS") or "").strip()
            )
            if _ag_fc.isdigit():
                _v_ag = int(_ag_fc)
                if _v_ag > 0:
                    max_tok_fc = _v_ag

        import inspect

        try:
            fn = getattr(llm, "chat_completion_with_tools")
            _fc_kw: Dict[str, Any] = {
                "tool_choice": tool_choice,
                "parallel_tool_calls": parallel,
            }
            if max_tok_fc is not None:
                try:
                    if "max_tokens" in inspect.signature(fn).parameters:
                        _fc_kw["max_tokens"] = max_tok_fc
                except (TypeError, ValueError):
                    pass
            if asyncio.iscoroutinefunction(fn):
                raw = await fn(messages, tools, **_fc_kw)
            else:
                loop = asyncio.get_event_loop()
                raw = await loop.run_in_executor(
                    self._tool_executor,
                    functools.partial(fn, messages, tools, **_fc_kw),
                )
        except Exception as e:
            print(
                f"[REACT-FC] step={step_index} chat_completion_with_tools 失败，回退流式+XML: {e}"
            )
            text = await self._collect_llm_text(decision_prompt)
            return (
                parse_xml_decision(text)
                if use_react_decide_xml_fallback()
                else {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": f"decide_fc_exception:{e}",
                },
                text,
            )

        msg = self._fc_normalize_assistant_message(raw)
        if msg is None:
            text = await self._collect_llm_text(decision_prompt)
            return (
                parse_xml_decision(text)
                if use_react_decide_xml_fallback()
                else {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": "decide_fc_no_message",
                },
                text,
            )

        content = ""
        if isinstance(msg, dict):
            content = msg.get("content") or ""
        else:
            content = getattr(msg, "content", None) or ""

        decision = decision_from_assistant_message(msg)
        if decision is None:
            decision = (
                parse_xml_decision(content)
                if use_react_decide_xml_fallback()
                else {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": "decide_fc_no_tool_calls",
                }
            )

        raw_log = (content or "").strip()
        try:
            tcs = (
                msg.get("tool_calls")
                if isinstance(msg, dict)
                else getattr(msg, "tool_calls", None)
            )
            if tcs:
                raw_log = (
                    f"{raw_log} | tool_calls={len(tcs)}"
                    if raw_log
                    else f"tool_calls={len(tcs)}"
                )
        except Exception:
            pass

        print(
            f"[REACT-FC] step={step_index} tool={decision.get('tool')!r} "
            f"execute={decision.get('execute')!r}"
        )
        return decision, raw_log or (content or "")

    async def _iter_fc_decide_stream(
        self,
        decision_prompt: str,
        *,
        step_index: int,
        prev_tool: Optional[str] = None,
        result_out: List[Tuple[Dict[str, Any], str]],
        opening_merge: bool = False,
    ):
        """
        流式 FC：边收模型 delta 边 yield agent_thought；结束后写入 result_out[0] = (decision, raw_log)。
        合并模式下：直接收集文本输出，使用 parse_opening_decision 解析。
        """
        import inspect

        result_out.clear()
        
        # 合并模式：不使用 FC，直接流式收集文本
        if opening_merge:
            content_parts = []
            try:
                async for chunk in self._stream_llm_text(decision_prompt):
                    if chunk:
                        content_parts.append(chunk)
                        yield {"event": "agent_thought", "delta": chunk, "index": step_index}
            except Exception as e:
                print(f"[REACT-FC-STREAM] opening_merge 流式失败: {e}")
            
            text = "".join(content_parts)
            _parsed = parse_opening_decision(text)
            _type = _parsed.get("type")
            
            if _type == "single":
                decision = {
                    "execute": True,
                    "tool": _parsed.get("tool", ""),
                    "params": _parsed.get("params", {}),
                    "reason": "opening_single_step_stream",
                }
            elif _type == "multi":
                # 多步任务：提取 plan 和首个工具调用
                _plan_list = _parsed.get("plan", [])
                _first_tool = _parsed.get("first_tool", "")
                _first_params = _parsed.get("first_params", {})
                if _first_tool:
                    decision = {
                        "execute": True,
                        "tool": _first_tool,
                        "params": _first_params or {},
                        "reason": "opening_multi_step_stream",
                        "plan": _plan_list,
                    }
                else:
                    decision = {
                        "execute": False,
                        "tool": "",
                        "params": {},
                        "reason": "opening_multi_step_no_first_tool",
                        "plan": _plan_list,
                    }
            elif _type == "chat":
                decision = {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": "chat",
                    "message": _parsed.get("message", ""),
                }
            else:
                decision = parse_xml_decision(text) if use_react_decide_xml_fallback() else {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": "opening_unknown",
                }
            
            result_out.append((decision, text))
            print(f"[REACT-FC-STREAM] opening_merge type={_type} tool={decision.get('tool')!r}")
            return

        # 非合并模式：使用 FC 工具
        from .react_function_call import (
            build_react_decision_tools_from_registry,
            decision_from_assistant_message,
        )
        
        tools = build_react_decision_tools_from_registry(self.tools)
        assert tools, "流式 FC 要求非空 tools（调用方应先降级）"

        _xml_hint = (
            "若无法调用函数，可输出 <decision>...</decision>。"
            if use_react_decide_xml_fallback()
            else ""
        )
        prompt_fc = (
            decision_prompt
            + "\n\n（请用 function calling 指定工具与参数；不要输出 <decision> XML。"
            + (_xml_hint and " " + _xml_hint)
            + "）"
        )
        messages = [{"role": "user", "content": prompt_fc}]
        llm = self.llm
        tool_choice = self._parse_react_fc_tool_choice()
        parallel = os.getenv("REACT_FC_PARALLEL_TOOL_CALLS", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        max_tok_fc: Optional[int] = None
        for _k in ("REACT_DECIDE_FC_MAX_TOKENS", "REACT_DECIDE_MAX_TOKENS"):
            _raw_mt = (os.getenv(_k) or "").strip()
            if _raw_mt.isdigit():
                _v = int(_raw_mt)
                if _v > 0:
                    max_tok_fc = _v
                    break
        if str(prev_tool or "").strip().lower() == "grep":
            _ag_fc = (
                (os.getenv("REACT_DECIDE_AFTER_GREP_FC_MAX_TOKENS") or "").strip()
                or (os.getenv("REACT_DECIDE_AFTER_GREP_MAX_TOKENS") or "").strip()
            )
            if _ag_fc.isdigit():
                _v_ag = int(_ag_fc)
                if _v_ag > 0:
                    max_tok_fc = _v_ag

        stream_fn = getattr(llm, "chat_completion_with_tools_stream", None)
        if stream_fn is None:
            raise RuntimeError("LLM 无 chat_completion_with_tools_stream")
        _fc_kw: Dict[str, Any] = {
            "tool_choice": tool_choice,
            "parallel_tool_calls": parallel,
        }
        if max_tok_fc is not None:
            try:
                if "max_tokens" in inspect.signature(stream_fn).parameters:
                    _fc_kw["max_tokens"] = max_tok_fc
            except (TypeError, ValueError):
                pass

        it = stream_fn(messages, tools, **_fc_kw)
        acc = FcStreamAccumulator()
        loop = asyncio.get_event_loop()

        def _next_or_stop(gen):
            try:
                return next(gen)
            except StopIteration:
                return None

        while True:
            chunk = await loop.run_in_executor(self._tool_executor, _next_or_stop, it)
            if chunk is None:
                break
            piece = acc.feed(chunk)
            if piece:
                yield {"event": "agent_thought", "delta": piece, "index": step_index}

        msg = acc.build_assistant_message()
        msg = self._fc_normalize_assistant_message(msg)
        if msg is None:
            text = await self._collect_llm_text(decision_prompt)
            d = parse_xml_decision(text) if use_react_decide_xml_fallback() else {
                "execute": False,
                "tool": "",
                "params": {},
                "reason": "decide_fc_no_message",
            }
            result_out.append((d, text))
            return

        content = ""
        if isinstance(msg, dict):
            content = msg.get("content") or ""
        else:
            content = getattr(msg, "content", None) or ""

        decision = decision_from_assistant_message(msg)
        if decision is None:
            decision = (
                parse_xml_decision(content)
                if use_react_decide_xml_fallback()
                else {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": "decide_fc_no_tool_calls",
                }
            )

        raw_log = (content or "").strip()
        try:
            tcs = (
                msg.get("tool_calls")
                if isinstance(msg, dict)
                else getattr(msg, "tool_calls", None)
            )
            if tcs:
                raw_log = (
                    f"{raw_log} | tool_calls={len(tcs)}"
                    if raw_log
                    else f"tool_calls={len(tcs)}"
                )
        except Exception:
            pass

        print(
            f"[REACT-FC-STREAM] step={step_index} tool={decision.get('tool')!r} "
            f"execute={decision.get('execute')!r}"
        )
        result_out.append((decision, raw_log or (content or "")))



    async def _iter_observe_fc_stream(
        self,
        observe_prompt: str,
        *,
        step_index: int,
        full_text_sink: List[str],
        analysis_out: List[Optional[Dict[str, Any]]],
    ):
        from .react_function_call import (
            build_react_observe_fc_tools,
            observe_fc_result_from_assistant_message,
            use_react_observe_xml_fallback,
        )
        import inspect

        analysis_out.clear()
        analysis_out.append(None)
        full_text_sink.clear()
        full_text_sink.append("")

        tools = build_react_observe_fc_tools()
        prompt_fc = (
            observe_prompt
            + "\n\n（必须 function calling 调用 submit_observe_analysis；不要输出 <result>。）"
        )
        messages = [{"role": "user", "content": prompt_fc}]
        stream_fn = getattr(self.llm, "chat_completion_with_tools_stream", None)
        if stream_fn is None:
            raise RuntimeError("LLM 无 chat_completion_with_tools_stream")
        tool_choice = self._parse_react_fc_tool_choice()
        parallel = os.getenv("REACT_FC_PARALLEL_TOOL_CALLS", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        max_tok_fc: Optional[int] = None
        _raw_mt = (os.getenv("REACT_OBSERVE_MAX_TOKENS") or "").strip()
        if _raw_mt.isdigit():
            _v = int(_raw_mt)
            if _v > 0:
                max_tok_fc = _v
        _fc_kw: Dict[str, Any] = {
            "tool_choice": tool_choice,
            "parallel_tool_calls": parallel,
        }
        if max_tok_fc is not None:
            try:
                if "max_tokens" in inspect.signature(stream_fn).parameters:
                    _fc_kw["max_tokens"] = max_tok_fc
            except (TypeError, ValueError):
                pass

        it = stream_fn(messages, tools, **_fc_kw)
        acc = FcStreamAccumulator()
        loop = asyncio.get_event_loop()

        def _next_or_stop(gen):
            try:
                return next(gen)
            except StopIteration:
                return None

        while True:
            chunk = await loop.run_in_executor(self._tool_executor, _next_or_stop, it)
            if chunk is None:
                break
            piece = acc.feed(chunk)
            if piece:
                yield {
                    "event": "reasoning_step",
                    "content": piece,
                    "segment": "observe",
                    "index": step_index,
                }

        msg = acc.build_assistant_message()
        msg = self._fc_normalize_assistant_message(msg)
        content = ""
        if isinstance(msg, dict):
            content = msg.get("content") or ""
        else:
            content = getattr(msg, "content", None) or ""
        full_text_sink[0] = content

        parsed = observe_fc_result_from_assistant_message(msg)
        if parsed is None:
            analysis_out[0] = (
                parse_xml_findings(content) if use_react_observe_xml_fallback() else {"findings": [], "context_update": {}, "next_step": ""}
            )
        else:
            analysis_out[0] = parsed

    async def _react_observe_fc_sync(
        self, observe_prompt: str, max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """同步跑 observe 的 FC（无流式），供非 SSE run 路径使用。"""
        from .react_function_call import (
            build_react_observe_fc_tools,
            observe_fc_result_from_assistant_message,
            use_react_observe_xml_fallback,
        )
        import inspect

        tools = build_react_observe_fc_tools()
        prompt_fc = (
            observe_prompt
            + "\n\n（必须 function calling 调用 submit_observe_analysis；不要输出 <result>。）"
        )
        messages = [{"role": "user", "content": prompt_fc}]
        fn = getattr(self.llm, "chat_completion_with_tools", None)
        if fn is None:
            return {"findings": [], "context_update": {}, "next_step": ""}
        tool_choice = self._parse_react_fc_tool_choice()
        parallel = os.getenv("REACT_FC_PARALLEL_TOOL_CALLS", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        _fc_kw: Dict[str, Any] = {
            "tool_choice": tool_choice,
            "parallel_tool_calls": parallel,
        }
        if max_tokens is not None:
            try:
                if "max_tokens" in inspect.signature(fn).parameters:
                    _fc_kw["max_tokens"] = max_tokens
            except (TypeError, ValueError):
                pass
        try:
            if asyncio.iscoroutinefunction(fn):
                raw = await fn(messages, tools, **_fc_kw)
            else:
                loop = asyncio.get_event_loop()
                raw = await loop.run_in_executor(
                    self._tool_executor,
                    functools.partial(fn, messages, tools, **_fc_kw),
                )
        except Exception as _e:
            print(f"[REACT-OBSERVE-FC] sync FC 失败: {_e}")
            return {"findings": [], "context_update": {}, "next_step": ""}
        msg = self._fc_normalize_assistant_message(raw)
        parsed = observe_fc_result_from_assistant_message(msg) if msg else None
        if parsed is not None:
            return parsed
        content = ""
        if isinstance(msg, dict):
            content = msg.get("content") or ""
        else:
            content = getattr(msg, "content", None) or ""
        return (
            parse_xml_findings(content)
            if use_react_observe_xml_fallback()
            else {"findings": [], "context_update": {}, "next_step": ""}
        )

    async def _stream_llm_prompt_collect(
        self,
        prompt: str,
        *,
        step_index: Optional[int] = None,
        stream_kind: str = "think",
        full_text_sink: Optional[List[str]] = None,
        suppress_content_stream: bool = False,
        content_only_max_tokens: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        统一流式：复用 chat_stream_with_reasoning，边收边 yield。
        - think：reasoning + todos_stream（+ 可选 todos_partial）
        - decide/observe/summary 等：reasoning + llm_text_stream（带 index/kind）
        最终拼接正文：传入 full_text_sink（单元素 list），消费结束后 sink[0] 为全文（async generator 不能 return 值）。
        suppress_content_stream=True：仍收集全文供解析，但不向前端推送原始 XML/JSON 正文（由 react_ui_stream 替代）。
        """
        try:
            _brief_ms_fb = max(0, int(os.getenv("REACT_THOUGHT_BRIEF_MS", "800")))
        except Exception:
            _brief_ms_fb = 800
        with self._react_force_thinking_ctx(stream_kind):
            content_parts: List[str] = []
            q: 'queue.Queue[object]' = queue.Queue()
            DONE = object()
            _t_stream_start = time.time()
            _t_first_reasoning_fb = None
            _reasoning_buf_fb = ""
            _reasoning_timing_sent_fb = False
            _timing_kinds = frozenset({"think", "decide", "observe"})
            _n_reasoning_delta_chunks = 0
            _n_content_delta_chunks = 0

            def _worker():
                try:
                    _use_co = stream_kind in ("observe", "summary")
                    _think_mt = (
                        react_think_max_tokens() if stream_kind == "think" else None
                    )
                    _stream_it = (
                        self._resolve_chat_stream_iter_content_only(
                            prompt, None, content_only_max_tokens
                        )
                        if _use_co
                        else self._resolve_chat_stream_iter(
                            prompt, None, _think_mt
                        )
                    )
                    for it in _stream_it:
                        q.put(it)
                except Exception as e:
                    q.put({'type': 'content_delta', 'delta': f'Error: {e}'})
                finally:
                    q.put(DONE)

            threading.Thread(target=_worker, daemon=True).start()
            _todo_buf = ''
            _partial_parse_tick = 0
            _last_partial_n = 0

            while True:
                item = q.get()
                if item is DONE:
                    break
                if not isinstance(item, dict):
                    continue
                if item.get('type') == 'done':
                    continue
                if item.get('type') == 'reasoning_delta':
                    delta = item.get('delta')
                    if delta is not None and isinstance(delta, str):
                        _n_reasoning_delta_chunks += 1
                        if stream_kind in _timing_kinds:
                            _reasoning_buf_fb += delta
                            if _t_first_reasoning_fb is None and _reasoning_buf_fb.strip():
                                _t_first_reasoning_fb = time.time()
                        if stream_kind in ('decide', 'observe') and step_index is not None:
                            yield {
                                'event': 'reasoning_step',
                                'content': delta,
                                'segment': stream_kind,
                                'index': step_index,
                            }
                        else:
                            yield {'event': 'reasoning', 'content': delta}
                elif item.get('type') == 'content_delta':
                    delta = item.get('delta') or ''
                    if not delta:
                        continue
                    _n_content_delta_chunks += 1
                    if stream_kind in _timing_kinds and not _reasoning_timing_sent_fb:
                        now = time.time()
                        if _t_first_reasoning_fb is not None:
                            duration_ms = int((now - _t_first_reasoning_fb) * 1000)
                            had_r = True
                        else:
                            duration_ms = int((now - _t_stream_start) * 1000)
                            had_r = False
                        _seg = stream_kind
                        _ev_rt: Dict[str, Any] = {
                            'event': 'reasoning_timing',
                            'segment': _seg,
                            'duration_ms': duration_ms,
                            'kind': 'brief' if duration_ms < _brief_ms_fb else 'normal',
                            'had_reasoning': had_r,
                            'brief_threshold_ms': _brief_ms_fb,
                        }
                        if step_index is not None:
                            _ev_rt['index'] = step_index
                        yield _ev_rt
                        _reasoning_timing_sent_fb = True
                    content_parts.append(delta)
                    if suppress_content_stream:
                        # ReAct Thought：深度思考里 reasoning（reasoning_delta）与正文（content_delta）分路；
                        # 前端 Thought 区块浅色展示推理、亮色展示 content（含 decide/observe 的 XML 等，仅作过程可见性）
                        if stream_kind in ('decide', 'observe') and step_index is not None:
                            yield {
                                'event': 'thought_content_step',
                                'delta': delta,
                                'index': step_index,
                                'segment': stream_kind,
                            }
                        continue
                    if stream_kind == 'think':
                        yield {'event': 'todos_stream', 'delta': delta}
                        _todo_buf += delta
                        _partial_parse_tick += len(delta)
                        _should_try = (
                            _partial_parse_tick >= 96
                            or '</todo' in _todo_buf.lower()
                            or '</item>' in _todo_buf.lower()
                        )
                        if _should_try:
                            _partial_parse_tick = 0
                            try:
                                _pt = robust_parse_todos(_todo_buf)
                                if _pt and len(_pt) > _last_partial_n:
                                    _last_partial_n = len(_pt)
                                    yield {'event': 'todos_partial', 'data': _pt}
                                    # 真·SSE 流式规划备忘：随着 todos_partial 增量下发 plan_update（steps 逐步增长）
                                    if len(_pt) >= 1:
                                        yield {
                                            'event': 'plan_update',
                                            'steps': react_plan_steps_payload(_pt),
                                            'reason': 'todos_partial_stream',
                                            'suppress_plan_ui': False,
                                        }
                            except Exception:
                                pass
                    elif stream_kind == "summary":
                        try:
                            _slice = int(
                                (os.getenv("REACT_SUMMARY_STREAM_SLICE_CHARS") or "24").strip()
                            )
                        except Exception:
                            _slice = 24
                        _slice = max(8, _slice)
                        # 按片下发，避免整段只在一次事件里到达、前端像「一次性出来」
                        if _slice > 0 and len(delta) > 0:
                            _sgap = _summary_stream_yield_gap_s()
                            for i in range(0, len(delta), _slice):
                                yield {
                                    "event": "summary_stream",
                                    "delta": delta[i : i + _slice],
                                }
                                if _sgap > 0:
                                    await asyncio.sleep(_sgap)
                        else:
                            yield {"event": "summary_stream", "delta": delta}
                    else:
                        ev: Dict[str, Any] = {
                            'event': 'llm_text_stream',
                            'delta': delta,
                            'kind': stream_kind,
                        }
                        if step_index is not None:
                            ev['index'] = step_index
                        yield ev
            if stream_kind in _timing_kinds and not _reasoning_timing_sent_fb and _reasoning_buf_fb.strip():
                if _t_first_reasoning_fb is not None:
                    duration_ms = int((time.time() - _t_first_reasoning_fb) * 1000)
                else:
                    duration_ms = int((time.time() - _t_stream_start) * 1000)
                _ev_edge: Dict[str, Any] = {
                    'event': 'reasoning_timing',
                    'segment': stream_kind,
                    'duration_ms': duration_ms,
                    'kind': 'brief' if duration_ms < _brief_ms_fb else 'normal',
                    'had_reasoning': True,
                    'brief_threshold_ms': _brief_ms_fb,
                }
                if step_index is not None:
                    _ev_edge['index'] = step_index
                yield _ev_edge
            text = ''.join(content_parts).strip()
            if full_text_sink is not None:
                full_text_sink.clear()
                full_text_sink.append(text)
            # 主循环调试：Thought 无正文时核对是否收到 reasoning_delta / content_delta
            try:
                _llm_dbg = getattr(self, "llm", None)
                _model = getattr(_llm_dbg, "model", None) if _llm_dbg is not None else None
                _force_th = getattr(_llm_dbg, "force_disable_thinking", None) if _llm_dbg is not None else None
            except Exception:
                _model, _force_th = None, None
            if (
                os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0"
                and stream_kind in ("decide", "observe", "think")
            ):
                print(
                    f"[REACT-thought] kind={stream_kind!r} step_index={step_index} "
                    f"model={_model!r} force_disable_thinking={_force_th!r} "
                    f"suppress_content_stream={suppress_content_stream} "
                    f"reasoning_delta_chunks={_n_reasoning_delta_chunks} reasoning_chars={len(_reasoning_buf_fb)} "
                    f"content_delta_chunks={_n_content_delta_chunks} content_chars={len(text)} "
                    f"had_timing_event={_reasoning_timing_sent_fb}"
                )

    async def _stream_agent_decide_with_narrative(
        self,
        prompt: str,
        *,
        step_index: int,
        full_text_sink: List[str],
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        两阶段：先自然语言（agent_thought 流式），再 <decision>...</decision> 一次性缓冲解析。
        在接收闭合标签前下发 phase_wait，供前端展示「处理中」类等待态。
        """
        _dec_open = re.compile(r"<\s*decision\b", re.IGNORECASE)
        _dec_close = re.compile(r"<\s*/\s*decision\s*>", re.IGNORECASE)
        q: "queue.Queue[object]" = queue.Queue()
        DONE = object()

        def _worker():
            try:
                max_tok: Optional[int] = max_tokens
                if max_tok is None:
                    mt_raw = (os.getenv("REACT_DECIDE_MAX_TOKENS") or "").strip()
                    max_tok = int(mt_raw) if mt_raw.isdigit() else None
                    if max_tok is not None and max_tok <= 0:
                        max_tok = None
                for it in self._resolve_chat_stream_iter_content_only(
                    prompt, None, max_tok
                ):
                    q.put(it)
            except Exception as e:
                q.put({"type": "content_delta", "delta": f"Error: {e}"})
            finally:
                q.put(DONE)

        threading.Thread(target=_worker, daemon=True).start()
        buf = ""
        emitted = 0
        wait_decision_xml = False
        _wait_stream_active = False
        _last_wait_emit = 0.0
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                now_w = time.time()
                if now_w - _last_wait_emit >= 0.8:
                    _last_wait_emit = now_w
                    _wait_stream_active = True
                    yield {
                        "event": "phase_wait",
                        "kind": "decision_stream",
                        "active": True,
                        "index": step_index,
                        "message": "正在生成决策思考…",
                    }
                await asyncio.sleep(0.12)
                continue
            if _wait_stream_active:
                _wait_stream_active = False
                yield {
                    "event": "phase_wait",
                    "kind": "decision_stream",
                    "active": False,
                    "index": step_index,
                }
            if item is DONE:
                break
            if not isinstance(item, dict):
                continue
            if item.get("type") == "done":
                continue
            if item.get("type") != "content_delta":
                continue
            d = item.get("delta") or ""
            if not d:
                continue
            buf += d
            m = _dec_open.search(buf)
            if m:
                pos = m.start()
                nar = buf[:pos]
                if len(nar) > emitted:
                    yield {"event": "agent_thought", "delta": nar[emitted:], "index": step_index}
                    emitted = len(nar)
                if _dec_close.search(buf):
                    # decision XML 闭合后，加载效果消失
                    if wait_decision_xml:
                        yield {
                            "event": "phase_wait",
                            "kind": "decision_xml",
                            "active": False,
                            "index": step_index,
                        }
                        wait_decision_xml = False
                else:
                    # decision XML 开始输出，显示加载效果
                    if not wait_decision_xml:
                        wait_decision_xml = True
                        yield {
                            "event": "phase_wait",
                            "kind": "decision_xml",
                            "active": True,
                            "index": step_index,
                            "message": "正在接收决策结构…",
                        }
            else:
                if len(buf) > emitted:
                    yield {"event": "agent_thought", "delta": buf[emitted:], "index": step_index}
                    emitted = len(buf)
        # 确保 phase_wait 被清除
        if wait_decision_xml:
            yield {
                "event": "phase_wait",
                "kind": "decision_xml",
                "active": False,
                "index": step_index,
            }
        full_text_sink.clear()
        full_text_sink.append(buf)
        yield {"event": "agent_thought_done", "index": step_index}

    async def _stream_agent_observe_with_narrative(
        self,
        prompt: str,
        *,
        step_index: int,
        full_text_sink: List[str],
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        观察阶段两阶段：先自然语言分析（reasoning_step segment=observe），再 <result>...</result> 供 parse_xml_findings。
        """
        _res_open = re.compile(r"<\s*result\b", re.IGNORECASE)
        _res_close = re.compile(r"<\s*/\s*result\s*>", re.IGNORECASE)
        q: "queue.Queue[object]" = queue.Queue()
        DONE = object()

        def _worker():
            try:
                mt_raw = (os.getenv("REACT_OBSERVE_MAX_TOKENS") or "").strip()
                max_tok: Optional[int] = int(mt_raw) if mt_raw.isdigit() else None
                if max_tok is not None and max_tok <= 0:
                    max_tok = None
                for it in self._resolve_chat_stream_iter_content_only(
                    prompt, None, max_tok
                ):
                    q.put(it)
            except Exception as e:
                q.put({"type": "content_delta", "delta": f"Error: {e}"})
            finally:
                q.put(DONE)

        threading.Thread(target=_worker, daemon=True).start()
        buf = ""
        emitted = 0
        wait_result_xml = False
        _wait_stream_active = False
        _last_wait_emit = 0.0
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                now_w = time.time()
                if now_w - _last_wait_emit >= 0.8:
                    _last_wait_emit = now_w
                    _wait_stream_active = True
                    yield {
                        "event": "phase_wait",
                        "kind": "observe_stream",
                        "active": True,
                        "index": step_index,
                        "message": "正在生成观察分析…",
                    }
                await asyncio.sleep(0.12)
                continue
            if _wait_stream_active:
                _wait_stream_active = False
                yield {
                    "event": "phase_wait",
                    "kind": "observe_stream",
                    "active": False,
                    "index": step_index,
                }
            if item is DONE:
                break
            if not isinstance(item, dict):
                continue
            if item.get("type") == "done":
                continue
            if item.get("type") != "content_delta":
                continue
            d = item.get("delta") or ""
            if not d:
                continue
            buf += d
            m = _res_open.search(buf)
            if m:
                nar = buf[: m.start()]
                if len(nar) > emitted:
                    piece = nar[emitted:]
                    yield {
                        "event": "reasoning_step",
                        "content": piece,
                        "segment": "observe",
                        "index": step_index,
                    }
                    emitted = len(nar)
                if _res_close.search(buf):
                    if wait_result_xml:
                        yield {
                            "event": "phase_wait",
                            "kind": "result_xml",
                            "active": False,
                            "index": step_index,
                        }
                        wait_result_xml = False
                else:
                    if not wait_result_xml:
                        wait_result_xml = True
                        yield {
                            "event": "phase_wait",
                            "kind": "result_xml",
                            "active": True,
                            "index": step_index,
                            "message": "正在接收分析结果…",
                        }
            else:
                if len(buf) > emitted:
                    piece = buf[emitted:]
                    yield {
                        "event": "reasoning_step",
                        "content": piece,
                        "segment": "observe",
                        "index": step_index,
                    }
                    emitted = len(buf)
        if wait_result_xml:
            yield {
                "event": "phase_wait",
                "kind": "result_xml",
                "active": False,
                "index": step_index,
            }
        full_text_sink.clear()
        full_text_sink.append(buf)

    async def _stream_observe_stub_quick(
        self,
        stub_xml: str,
        *,
        step_index: int,
        full_text_sink: List[str],
    ) -> AsyncIterator[Dict[str, Any]]:
        """不调用 observe_prompt 大模型；仅写入占位 XML，供 parse_xml_findings 与后续轮次使用。"""
        full_text_sink.clear()
        full_text_sink.append(stub_xml)
        yield {
            "event": "reasoning_step",
            "content": "",
            "segment": "observe",
            "index": step_index,
        }

    async def _stream_react_ui_text(
        self,
        prompt: str,
        *,
        step_index: int,
        channel: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """面向用户的短说明流：仅正文 delta，无 reasoning；用于替换原始 XML/JSON 面板。"""
        q: 'queue.Queue[object]' = queue.Queue()
        DONE = object()

        def _worker():
            try:
                with self._llm_no_thinking():
                    for it in self._resolve_chat_stream_iter(prompt):
                        q.put(it)
            except Exception as e:
                q.put({'type': 'content_delta', 'delta': f'（说明生成失败：{e}）'})
            finally:
                q.put(DONE)

        threading.Thread(target=_worker, daemon=True).start()
        _wait_stream_active = False
        _last_wait_emit = 0.0
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                now_w = time.time()
                if now_w - _last_wait_emit >= 0.8:
                    _last_wait_emit = now_w
                    _wait_stream_active = True
                    yield {
                        "event": "phase_wait",
                        "kind": "agent_thought_stream",
                        "active": True,
                        "index": step_index,
                        "message": "正在生成步骤思考…",
                    }
                await asyncio.sleep(0.12)
                continue
            if _wait_stream_active:
                _wait_stream_active = False
                yield {
                    "event": "phase_wait",
                    "kind": "agent_thought_stream",
                    "active": False,
                    "index": step_index,
                }
            if item is DONE:
                break
            if not isinstance(item, dict):
                continue
            if item.get('type') == 'content_delta':
                delta = item.get('delta') or ''
                if delta:
                    yield {
                        'event': 'react_ui_stream',
                        'channel': channel,
                        'delta': delta,
                        'index': step_index,
                    }

    async def _stream_decision_observe_from_nl(
        self,
        summary_nl: str,
        *,
        step_index: int,
    ) -> AsyncIterator[Dict[str, Any]]:
        """无 LLM：用 observation 的 summary_nl 充当前端 decision_observe。"""
        raw = (summary_nl or "").strip()
        if not raw:
            raw = (
                "（本步无简要结论文案，详见上方工具输出。）"
                if not is_english_locale(self._ui_locale)
                else "(No brief summary; see tool output above.)"
            )
        try:
            chunk_sz = max(1, int((os.getenv("REACT_OBSERVE_NL_STREAM_CHARS") or "240").strip()))
        except Exception:
            chunk_sz = 240
        for start in range(0, len(raw), chunk_sz):
            yield {
                "event": "react_ui_stream",
                "channel": "decision_observe",
                "delta": raw[start : start + chunk_sz],
                "index": step_index,
            }
            await asyncio.sleep(0)

    async def _merge_running_summary_incremental_silent(
        self,
        state: Dict[str, Any],
        step_index: int,
        tool: str,
        todo: str,
        nl_obs: str,
    ) -> None:
        """每步结束后仅后台合并运行总览，更新 state；不向 SSE 推流（避免中途半篇展示）。"""
        if not use_react_incremental_running_summary():
            return
        try:
            next_ver = int(state.get("version") or 0) + 1
        except Exception:
            next_ver = 1
        prev = str(state.get("text") or "")
        prompt = incremental_running_summary_prompt(
            self._ui_locale,
            prev,
            step_index,
            tool,
            todo,
            nl_obs,
        )
        q: "queue.Queue[object]" = queue.Queue()
        DONE = object()

        def _worker():
            try:
                with self._llm_no_thinking():
                    try:
                        _mt = int(
                            (os.getenv("REACT_INCREMENTAL_SUMMARY_MAX_TOKENS") or "2048").strip()
                        )
                    except Exception:
                        _mt = 2048
                    _mt_kw = _mt if _mt > 0 else None
                    for it in self._resolve_chat_stream_iter_content_only(
                        prompt, None, max_tokens=_mt_kw
                    ):
                        q.put(it)
            except Exception as e:
                _em = f"（运行总览生成失败：{e}）" if not is_english_locale(self._ui_locale) else f"(Running summary failed: {e})"
                q.put({"type": "content_delta", "delta": _em})
            finally:
                q.put(DONE)

        threading.Thread(target=_worker, daemon=True).start()
        full_parts: List[str] = []
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.12)
                continue
            if item is DONE:
                break
            if not isinstance(item, dict):
                continue
            if item.get("type") != "content_delta":
                continue
            delta = item.get("delta") or ""
            if delta:
                full_parts.append(str(delta))
        full_text = "".join(full_parts).strip()
        if full_text:
            state["text"] = full_text
            state["version"] = next_ver

    async def _merge_running_summary_incremental_to_sse(
        self,
        state: Dict[str, Any],
        step_index: int,
        tool: str,
        todo: str,
        nl_obs: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """增量运行总览：LLM 流式产出时即 yield running_summary_stream（真·后端 SSE）。"""
        if not use_react_incremental_running_summary():
            return
        try:
            next_ver = int(state.get("version") or 0) + 1
        except Exception:
            next_ver = 1
        prev = str(state.get("text") or "")
        prompt = incremental_running_summary_prompt(
            self._ui_locale,
            prev,
            step_index,
            tool,
            todo,
            nl_obs,
        )
        yield {"event": "running_summary_stream_reset", "version": next_ver}

        q: "queue.Queue[object]" = queue.Queue()
        DONE = object()

        def _worker():
            try:
                with self._llm_no_thinking():
                    try:
                        _mt = int(
                            (os.getenv("REACT_INCREMENTAL_SUMMARY_MAX_TOKENS") or "2048").strip()
                        )
                    except Exception:
                        _mt = 2048
                    _mt_kw = _mt if _mt > 0 else None
                    for it in self._resolve_chat_stream_iter_content_only(
                        prompt, None, max_tokens=_mt_kw
                    ):
                        q.put(it)
            except Exception as e:
                _em = (
                    f"（运行总览生成失败：{e}）"
                    if not is_english_locale(self._ui_locale)
                    else f"(Running summary failed: {e})"
                )
                q.put({"type": "content_delta", "delta": _em})
            finally:
                q.put(DONE)

        threading.Thread(target=_worker, daemon=True).start()

        try:
            _slice = int((os.getenv("REACT_SUMMARY_STREAM_SLICE_CHARS") or "24").strip())
        except Exception:
            _slice = 24
        _slice = max(8, _slice)
        _sgap = _running_summary_wire_yield_gap_s()

        full_parts: List[str] = []
        while True:
            item = await asyncio.to_thread(q.get)
            if item is DONE:
                break
            if not isinstance(item, dict):
                continue
            if item.get("type") != "content_delta":
                continue
            delta = item.get("delta") or ""
            if not delta:
                continue
            s = str(delta)
            full_parts.append(s)
            if _slice > 0 and len(s) > 0:
                for j in range(0, len(s), _slice):
                    yield {
                        "event": "running_summary_stream",
                        "delta": s[j : j + _slice],
                        "version": next_ver,
                        "index": step_index,
                    }
                    if _sgap > 0:
                        await asyncio.sleep(_sgap)
            else:
                yield {
                    "event": "running_summary_stream",
                    "delta": s,
                    "version": next_ver,
                    "index": step_index,
                }

        full_text = "".join(full_parts).strip()
        if full_text:
            state["text"] = full_text
            state["version"] = next_ver

    async def _shutdown_incr_sum_background_worker(
        self,
        q: Optional[asyncio.Queue],
        task: Optional[asyncio.Task],
    ) -> None:
        """收口异步静默运行总览 worker：先发完队列内任务再结束协程。"""
        if q is None or task is None:
            return
        try:
            await q.join()
            await q.put(None)
            await q.join()
        except Exception as e:
            if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                print(f"[REACT] incr_sum queue shutdown: {e}")
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                print(f"[REACT] incr_sum worker: {e}")

    async def _stream_running_summary_final_wire(
        self,
        state: Dict[str, Any],
        *,
        last_step_index: int,
    ) -> AsyncIterator[Dict[str, Any]]:
        """主循环已全部结束后，将最终运行总览按块流式下发（仅此时走 SSE）。"""
        text = str(state.get("text") or "").strip()
        if not text:
            return
        try:
            ver = int(state.get("version") or 0)
        except Exception:
            ver = 1
        yield {"event": "running_summary_stream_reset", "version": ver}
        try:
            _slice = int((os.getenv("REACT_SUMMARY_STREAM_SLICE_CHARS") or "24").strip())
        except Exception:
            _slice = 24
        _slice = max(1, _slice)
        _rgap = _running_summary_wire_yield_gap_s()
        _first_chunk = True
        for j in range(0, len(text), _slice):
            if _first_chunk:
                yield {"event": "unified_summary_loading", "active": False}
                _first_chunk = False
            yield {
                "event": "running_summary_stream",
                "delta": text[j : j + _slice],
                "version": ver,
                "index": last_step_index,
            }
            if _rgap > 0:
                await asyncio.sleep(_rgap)
        yield {
            "event": "running_summary_done",
            "full_text": text,
            "version": ver,
            "index": last_step_index,
        }

    async def _stream_skill_plan_thought(
        self, prompt: str, *, step_index: int
    ) -> AsyncIterator[Dict[str, Any]]:
        """技能计划步：自然语言思考说明（流式 agent_thought）。"""
        q: "queue.Queue[object]" = queue.Queue()
        DONE = object()

        def _worker():
            try:
                with self._llm_no_thinking():
                    for it in self._resolve_chat_stream_iter(prompt):
                        q.put(it)
            except Exception as e:
                q.put({"type": "content_delta", "delta": f"（思考生成失败：{e}）"})
            finally:
                q.put(DONE)

        threading.Thread(target=_worker, daemon=True).start()
        while True:
            item = q.get()
            if item is DONE:
                break
            if not isinstance(item, dict):
                continue
            if item.get("type") == "content_delta":
                delta = item.get("delta") or ""
                if delta:
                    yield {
                        "event": "agent_thought",
                        "delta": delta,
                        "index": step_index,
                    }

    async def _skill_plan_step_stream_prepare(
        self,
        *,
        i: int,
        todo: str,
        user_input: str,
        todos: List[str],
        skill_ref: Skill,
        fallback_workflow_tools: List[str],
        result_context: Dict[str, Any],
        project_id: Optional[int],
        last_observation: Optional[Dict[str, Any]],
        out: Dict[str, Any],
    ) -> AsyncIterator[Dict[str, Any]]:
        """技能匹配后的单步：先思考流，再按 todo/workflow 解析为 decision（与主循环共用执行与观察）。"""
        overview = "\n".join(f"{j + 1}. {t}" for j, t in enumerate(todos))
        last_obs = ""
        if last_observation and isinstance(last_observation, dict):
            last_obs = (last_observation.get("summary") or last_observation.get("message") or "")[:2000]
        elif last_observation:
            last_obs = str(last_observation)[:2000]
        thought_prompt = self._wrap_prompt(
            (
                f"你是任务执行助手。当前为计划中的第 {i + 1} 步（共 {len(todos)} 步）。\n"
                f"用户目标：{user_input}\n"
                f"完整计划：\n{overview}\n"
                f"当前步骤：{todo}\n"
                f"上一步观察摘要：{last_obs or '（无）'}\n\n"
                f"请用 3–6 句中文说明：1) 为何要执行这一步；2) 打算如何执行；3) 预期结果。"
                f"不要输出 XML/JSON，不要用列表符号。"
            )
        )
        async for ev in self._stream_skill_plan_thought(thought_prompt, step_index=i):
            yield ev

        
        # 从 todo 中提取关键词和状态
        todo_params = await self._extract_todo_params(todo, user_input)
        tool_name = todo_params['tool']

        # 兜底：如果 todo 解析不出工具，用技能 workflow 的对应步骤工具补齐（不改 todo 文本，只改执行工具）
        if tool_name == 'unknown' and fallback_workflow_tools:
            mapped = fallback_workflow_tools[i] if i < len(fallback_workflow_tools) else fallback_workflow_tools[-1]
            if mapped in ('grep', 'modify', 'create'):
                tool_name = mapped
                todo_params['tool'] = mapped
                # 尽量补齐 grep/modify 的必要参数
                params = todo_params.get('params') or {}
                inferred_target = params.get('target')
                if not inferred_target:
                    skill_name_lower = (skill_ref.name or '').lower()
                    if 'bug' in skill_name_lower:
                        inferred_target = 'bug'
                    elif 'testcase' in skill_name_lower or 'test_case' in skill_name_lower:
                        inferred_target = 'testcase'
                    elif user_input and ('测试用例' in user_input or 'test case' in user_input.lower()):
                        inferred_target = 'testcase'
                    elif user_input and ('bug' in user_input or '缺陷' in user_input or 'Bug' in user_input):
                        inferred_target = 'all'  # 兜底：在所有计划、不分类型查一遍
                    else:
                        inferred_target = 'badcase'
                    params['target'] = inferred_target
                if mapped == 'grep':
                    params.setdefault('mode', 'locate')
                    params.setdefault('keywords', self._extract_title_keywords_for_grep(user_input, todo) or '')
                    # 修改流程的 grep 用 target=all 搜全计划，确保同名记录全部命中
                    if 'modify' in fallback_workflow_tools:
                        params['target'] = 'all'
                elif mapped == 'modify':
                    params.setdefault('confirm', False)
                    if 'modifications' not in params or not params.get('modifications'):
                        params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                elif mapped == 'create':
                    params.setdefault('target', 'bug')
                    params.setdefault('fields', {})
                    params['confirm'] = False
                todo_params['params'] = params
                print(f"[REACT-planing] 🔧 todo 工具兜底映射: index={i}, unknown -> {mapped}")
        
        # secondary fallback: if parser still returns unknown, infer by todo text
        if tool_name == 'unknown':
            t = (todo or '').lower()
            if 'create' in t:
                tool_name = 'create'
                todo_params['tool'] = 'create'
                p = todo_params.get('params') or {}
                p.setdefault('target', 'bug')
                p.setdefault('fields', {})
                p['confirm'] = False
                todo_params['params'] = p
            elif 'grep' in t or 'search' in t:
                tool_name = 'grep'
                todo_params['tool'] = 'grep'
                p = todo_params.get('params') or {}
                p.setdefault('mode', 'locate')
                todo_params['params'] = p
            elif 'modify' in t or 'update' in t:
                tool_name = 'modify'
                todo_params['tool'] = 'modify'
                p = todo_params.get('params') or {}
                p.setdefault('confirm', False)
                p.setdefault('modifications', {})
                todo_params['params'] = p

        print(f"[REACT-planing] Todo[{i}] 提取参数: tool={tool_name}, params={todo_params}")
        
        # 确保必要参数
        params = todo_params['params']
        if 'project_id' not in params and project_id:
            params['project_id'] = project_id
        if 'userId' not in params:
            params['userId'] = 'system_agent'
        # 兜底：grep target=all 时在所有迭代计划查，不传 plan_id
        if tool_name == 'grep' and params.get('target') == 'all':
            params.pop('plan_id', None)
        
        # 如果是 modify 工具，需要从 grep 结果中获取 target_id（含 testcase）
        # 用户说「修改bug」时必须用 target=bug 和 first_bug_id，不能默认 badcase 导致改错
        if tool_name == 'modify':
            grep_result = result_context.get('grep_result', {})
            target_type = params.get('target') or self._infer_modify_target(user_input, todo)
            params['target'] = target_type
            if target_type == 'bug':
                target_id = grep_result.get('first_bug_id')
            elif target_type == 'testcase':
                target_id = grep_result.get('first_testcase_id')
            else:
                target_id = grep_result.get('first_badcase_id')
            if not target_id:
                tid_m = self._try_target_id_from_merged_lists(
                    result_context, target_type, user_input, todo
                )
                if tid_m is not None:
                    target_id = tid_m
                    print(
                        f"[REACT-thought] 从合并列表注入 target_id={target_id}, target={target_type}"
                    )
            if target_id:
                params['target_id'] = target_id
                print(f"[REACT-thought] 从 grep 结果获取 target_id={target_id}, target={target_type}")
            else:
                print(f"[REACT-thought] ⚠️ 无法从 grep 结果获取 target_id (target={target_type})，尝试补救 grep…")
                kw = self._extract_title_keywords_for_grep(user_input, todo) or ''
                gparams: Dict[str, Any] = {
                    'project_id': project_id,
                    'keywords': kw,
                    'mode': 'locate',
                    'target': target_type if target_type in ('bug', 'badcase', 'testcase') else 'all',
                    'userId': 'system_agent',
                }
                if self.plan_id is not None and gparams.get('target') != 'all':
                    gparams['plan_id'] = self.plan_id
                if gparams.get('target') == 'all':
                    gparams.pop('plan_id', None)
                yield {
                    'event': 'executing',
                    'tool': 'grep',
                    'reason': f'Todo步骤 {i+1}',
                    'index': i,
                    'message': '正在补充定位记录（用于修改）…',
                }
                grep_obs = await self._execute_tool({'execute': True, 'tool': 'grep', 'params': gparams})
                for _tte in self._drain_tool_task_sse_buffer_list():
                    yield _tte
                if grep_obs.get('success'):
                    self._merge_grep_observation_into_context(grep_obs, gparams, result_context)
                    grep_result = result_context.get('grep_result', {})
                    if target_type == 'bug':
                        target_id = grep_result.get('first_bug_id')
                    elif target_type == 'testcase':
                        target_id = grep_result.get('first_testcase_id')
                    else:
                        target_id = grep_result.get('first_badcase_id')
                    if target_id:
                        params['target_id'] = target_id
                        print(f"[REACT-thought] 补救 grep 后 target_id={target_id}")
                    if not params.get('target_id'):
                        tid_s = self._try_target_id_from_merged_lists(
                            result_context, target_type, user_input, todo
                        )
                        if tid_s is not None:
                            params['target_id'] = tid_s
                            target_id = tid_s
                            print(f"[REACT-thought] 技能分支补救 grep 后从列表注入 target_id={tid_s}")
            
            # 思考意图 + 探索记录（类似 Cursor 探索文件）：有 target_id 时先探索当前记录与用户列表，再让大模型基于探索结果确认 modifications
            if target_id and (not params.get('modifications') or len(params.get('modifications', {})) == 0):
                modify_tool = self.tools.get('modify')
                if modify_tool and getattr(modify_tool, 'explore_record', None):
                    try:
                        loop = asyncio.get_event_loop()
                        exploration = await asyncio.wait_for(
                            loop.run_in_executor(
                                self._tool_executor,
                                lambda: modify_tool.explore_record(
                                    target_type,
                                    target_id,
                                    params.get("project_id") or self.project_id,
                                    getattr(self, "_ui_locale", None),
                                ),
                            ),
                            timeout=15,
                        )
                        if exploration and exploration.get('current_record'):
                            yield {'event': 'exploring', 'message': '正在结合当前记录确认修改意图…'}
                            # modify 步骤：所有模型都强制不带思考
                            with self._llm_no_thinking():
                                params['modifications'] = await self._extract_modifications_with_llm(todo, user_input, exploration=exploration)
                            if not params.get('modifications') and user_input:
                                params['modifications'] = self._extract_modifications_with_regex(user_input)
                            print(f"[REACT-thought] 探索后提取的 modifications: {params.get('modifications')}")
                    except Exception as e:
                        print(f"[REACT-thought] 探索记录失败，回退到仅 LLM 提取: {e}")
                        if not params.get('modifications'):
                            with self._llm_no_thinking():
                                params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                            if not params.get('modifications'):
                                params['modifications'] = self._extract_modifications_with_regex(user_input)
                elif not params.get('modifications'):
                    with self._llm_no_thinking():
                        params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                    if not params.get('modifications'):
                        params['modifications'] = self._extract_modifications_with_regex(user_input)

        if tool_name == 'create':
            grep_result = result_context.get('grep_result', {})
            target_type = params.get('target') or self._infer_create_target(user_input, todo)
            params['target'] = target_type
            fields = params.get('fields') or {}
            title_key = 'name' if target_type == 'plan' else 'title'
            extracted_title = self._extract_create_title(user_input, todo)
            if extracted_title and not fields.get(title_key):
                fields[title_key] = extracted_title

            wants_copy = any(token in (user_input or '') for token in ('复制', '一样', '相同')) or any(token in (todo or '') for token in ('复制', '一样', '相同'))
            if wants_copy:
                if target_type == 'bug':
                    source_id = grep_result.get('first_bug_id') or result_context.get('first_bug_id')
                    if source_id and not fields.get('copy_from_bug_id'):
                        fields['copy_from_bug_id'] = source_id
                elif target_type == 'badcase':
                    source_id = grep_result.get('first_badcase_id') or result_context.get('first_badcase_id')
                    if source_id and not fields.get('copy_from_badcase_id'):
                        fields['copy_from_badcase_id'] = source_id
                elif target_type == 'testcase':
                    source_id = grep_result.get('first_testcase_id') or result_context.get('first_testcase_id')
                    if source_id and not fields.get('copy_from_testcase_id'):
                        fields['copy_from_testcase_id'] = source_id

            params['fields'] = fields
            params.setdefault('confirm', False)
            params.setdefault('natural_query', user_input)
            print(f"[REACT-planing] create 参数补齐: target={target_type}, fields={fields}")

        # 技能分支：与主循环一致，执行 modify 前再 enrich + last_resort，避免仅有 modifications 却无 target_id 直接调工具报错
        skill_skip_modify = False
        if tool_name == 'modify':
            decision_skill = {'execute': True, 'tool': 'modify', 'params': params}
            decision_skill, _pre_ev = await self._enrich_modify_decision_for_main_loop(
                decision_skill, todo, user_input, result_context, project_id, step_index=i
            )
            for _ev in _pre_ev:
                yield _ev
            if not self._modify_params_ready(decision_skill.get('params')):
                decision_skill, _lr_ev = await self._last_resort_modify_fill(
                    decision_skill, todo, user_input, result_context, project_id, step_index=i
                )
                for _ev in _lr_ev:
                    yield _ev
            params = decision_skill['params']
            if not self._modify_params_ready(params):
                nq = (user_input or todo or '').strip()
                if nq:
                    params['natural_query'] = nq[:2000]
            if not self._modify_params_ready(params):
                skill_skip_modify = True
                print(
                    "[REACT-thought] 技能分支 stability_gate: modify 仍缺 target_id/natural_query 或 modifications"
                )
        out['decision'] = {'execute': True, 'tool': tool_name, 'params': params}
        out['skill_skip'] = skill_skip_modify

    def _summarize_observation_nl(self, tool: Optional[str], observation: Any) -> str:
        """将工具结果转为简短自然语言观察（供 task_state.observations 与可选展示）。"""
        loc = getattr(self, "_ui_locale", None)
        if not isinstance(observation, dict):
            return (str(observation) or "")[:800]
        if observation.get("skipped"):
            why = str(observation.get("stability_gate") or observation.get("error") or "").strip()
            if why:
                return react_summarize_observation_nl_skipped_gate(why, loc)
            return react_summarize_observation_nl_skipped_generic(loc)
        if isinstance(observation.get("summary"), str) and observation["summary"].strip():
            return observation["summary"].strip()[:2000]
        if isinstance(observation.get("message"), str) and observation["message"].strip():
            return observation["message"].strip()[:2000]
        ok = observation.get("success")
        err = str(observation.get("error") or "").strip()
        if ok is False:
            # 严格模式将「grep 成功但零命中」标为失败；对用户应说明是未命中而非工具异常
            if (tool or "").lower() == "grep" and err == "grep_empty_hits":
                return react_summarize_grep_done_empty(loc)
            if err:
                return react_summarize_observation_nl_tool_failed(tool, err, loc)
            return react_summarize_observation_nl_tool_failed_short(tool, loc)
        if (tool or "").lower() == "grep":
            data = observation.get("data") or {}
            bug_n = len(data.get("bug_location") or []) if isinstance(data.get("bug_location"), list) else 0
            bc_n = len(data.get("badcase_analysis") or []) if isinstance(data.get("badcase_analysis"), list) else 0
            tc_n = len(data.get("testcase_location") or []) if isinstance(data.get("testcase_location"), list) else 0
            n = bug_n + bc_n + tc_n
            if n == 0:
                return react_summarize_grep_done_empty(loc)
            return react_summarize_grep_done_hits(n, bug_n, bc_n, tc_n, loc)
        if (tool or "").lower() == "modify":
            diff_n = len(observation.get("diff") or []) if isinstance(observation.get("diff"), list) else 0
            return react_summarize_modify_done(
                ok, observation.get("confirmation_required"), diff_n, loc
            )
        return react_summarize_tool_done_ok(tool, ok, loc)

    async def _build_structured_plan_rows(
        self,
        todos: List[str],
        user_input: str,
        *,
        skill_guided: bool,
        skill_ref: Optional[Any],
        fallback_workflow_tools: List[str],
    ) -> List[Dict[str, Any]]:
        """从 todos 解析出每步 tool/params（技能引导时对齐 workflow 兜底 unknown）。"""
        rows: List[Dict[str, Any]] = []
        for i, todo in enumerate(todos):
            tp = await self._extract_todo_params(todo, user_input)
            tool_name = (tp.get("tool") or "unknown").strip()
            params = dict(tp.get("params") or {})
            if skill_guided and tool_name == "unknown" and fallback_workflow_tools:
                mapped = fallback_workflow_tools[i] if i < len(fallback_workflow_tools) else fallback_workflow_tools[-1]
                if mapped in ("grep", "modify", "create"):
                    tool_name = mapped
                    if mapped == "grep":
                        params.setdefault("mode", "locate")
                        params.setdefault("keywords", self._extract_title_keywords_for_grep(user_input, todo) or "")
                        skill_name_lower = (getattr(skill_ref, "name", None) or "").lower()
                        if "bug" in skill_name_lower:
                            params.setdefault("target", "bug")
                        elif "testcase" in skill_name_lower or "test_case" in skill_name_lower:
                            params.setdefault("target", "testcase")
                        elif user_input and ("测试用例" in user_input or "test case" in user_input.lower()):
                            params.setdefault("target", "testcase")
                        elif user_input and ("bug" in user_input or "缺陷" in user_input):
                            params.setdefault("target", "all")
                        else:
                            params.setdefault("target", "badcase")
                        if "modify" in (fallback_workflow_tools or []):
                            params["target"] = "all"
                    elif mapped == "modify":
                        params.setdefault("confirm", False)
                        params.setdefault("modifications", {})
            rows.append(
                {
                    "id": i + 1,
                    "name": str(todo)[:2000],
                    "tool": tool_name,
                    "params": params,
                    "status": "pending",
                    "result": None,
                }
            )
        return rows

    def _decide_next_step(self, task_state: Dict[str, Any], observation: Dict[str, Any], step_index: int, tool: Optional[str], todos_len: int) -> str:
        """技能引导：返回 next | adjust | finish；普通模式恒为 next。"""
        if task_state.get("mode") != "skill_guided":
            return "next"
        if step_index >= todos_len - 1:
            return "finish"
        if (tool or "").lower() == "grep" and isinstance(observation, dict) and not observation.get("success"):
            data = observation.get("data") or {}
            n = 0
            for k in ("bug_location", "badcase_analysis", "testcase_location"):
                x = data.get(k)
                if isinstance(x, list):
                    n += len(x)
            if n == 0 and step_index + 1 < todos_len:
                return "adjust"
        return "next"

    async def _adjust_plan_skill(
        self,
        task_state: Dict[str, Any],
        user_input: str,
        todos: List[str],
        *,
        step_index: int,
        result_context: Dict[str, Any],
        project_id: Optional[int],
    ) -> Optional[List[str]]:
        """
        计划调整：根据当前状态重新生成剩余步骤。初版占位，返回 None 表示不调整（由主循环继续 next）。
        """
        del task_state, user_input, todos, step_index, result_context, project_id
        return None

    async def _run_stream_raw(
        self,
        user_input: str,
        project_id: int = None,
        plan_id: int = None,
        locale: Optional[str] = None,
        pending_diff_context: Optional[List[Dict[str, Any]]] = None,
        agent_session_id: Optional[str] = None,
        long_memory_prefetch: Optional[Dict[str, Any]] = None,
    ):
        """内部实现：yield 带 ``event`` 的引擎字典；对外请用 ``run_stream``（出口统一 v1）。"""
        print(f"\n[REACT] ReAct Stream Loop Start")
        perf = (os.getenv("PERF_LOG") == "1")
        t0 = time.perf_counter()
        self._ui_locale = normalize_locale(locale)
        self._agent_session_id = (agent_session_id or "").strip() or None
        self._tool_task_event_buffer = []
        self.project_id = project_id
        self.plan_id = plan_id  # 当前迭代计划，供 grep 按计划检索
        self._index_pending_context(pending_diff_context or [])
        self.use_todo = True
        start_time = time.time()

        preloop_skill_task: Optional[asyncio.Task] = None
        result_context = {}
        try:
            # pending 摘要仅依赖已索引的 diff + user_input；名称查库走线程池 + 可选短缓存，避免阻塞事件循环
            _t_names = asyncio.create_task(asyncio.to_thread(_sync_load_project_plan_names, project_id, plan_id, perf))
            _t_tools = asyncio.create_task(asyncio.to_thread(format_tools_for_prompt, self.tools))
            _t_pending = asyncio.create_task(asyncio.to_thread(self._relevant_pending_for_llm, user_input))

            # 合并首轮时：在 await gather 前先给前端一个可见 thought，避免前置阶段空白。
            try:
                yield {
                    "event": "agent_thought",
                    "delta": "正在准备上下文并生成执行计划…\n",
                    "index": 0,
                }
            except Exception:
                pass

            (project_name, plan_name), tools_info, _pending_for_llm = await asyncio.gather(
                _t_names,
                _t_tools,
                _t_pending,
            )
        except BaseException:
            raise
        if perf:
            print(f"[PERF][react] gather_names_tools_pending_parallel=1")
        if plan_id is not None:
            result_context['plan_id'] = plan_id  # 供 LLM 传给 grep，先检索本计划再阅读
            if plan_name:
                result_context['plan_name'] = plan_name

        # 长期记忆：默认不在每条消息做向量检索；优先用请求带入的 prefetch（项目打开时拉取）
        _lm_each_msg = (os.getenv("REACT_LONG_MEMORY_QUERY_EACH_MESSAGE", "0") or "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if isinstance(long_memory_prefetch, dict) and long_memory_prefetch:
            _lmt = str(
                long_memory_prefetch.get("long_memory_text")
                or long_memory_prefetch.get("merged")
                or ""
            ).strip()
            _lmi = long_memory_prefetch.get("long_memory_items") or long_memory_prefetch.get("memories")
            if _lmt:
                result_context["long_memory_text"] = _lmt
            if isinstance(_lmi, list) and _lmi:
                result_context["long_memory_items"] = _lmi
        elif _lm_each_msg:
            await self._inject_long_memory_into_context(
                user_input=user_input,
                result_context=result_context,
                project_id=project_id,
                plan_id=plan_id,
                agent_session_id=self._agent_session_id,
            )

        # modify 流程要求不带思考：为支持的 LLM 提供一个临时开关
        def _set_force_disable_thinking(v: bool):
            try:
                if hasattr(self.llm, "force_disable_thinking"):
                    setattr(self.llm, "force_disable_thinking", bool(v))
            except Exception:
                pass

        class _NoThinking:
            def __enter__(self_nonlocal):
                _set_force_disable_thinking(True)
                return self_nonlocal
            def __exit__(self_nonlocal, exc_type, exc, tb):
                _set_force_disable_thinking(False)
                return False
        if project_id is not None:
            result_context['project_id'] = project_id
            if project_name:
                result_context['project_name'] = project_name

        # 仅把“与本次对话相关 + 有实际改动”的 pending diff 摘要注入给大模型（已在 gather 中与查库/工具表并行算好）
        if _pending_for_llm:
            result_context['pending_diff_summary'] = [
                {
                    "target": x.get("target"),
                    "target_id": x.get("target_id"),
                    "modifications": x.get("modifications") or {},
                }
                for x in _pending_for_llm
            ]
            
        findings = []
        steps = []

        def _cancel_preloop_tasks() -> None:
            nonlocal preloop_skill_task
            if preloop_skill_task is not None and not preloop_skill_task.done():
                preloop_skill_task.cancel()
            preloop_skill_task = None

        try:
            _incr_merge_q: Optional[asyncio.Queue] = None
            _incr_worker_task: Optional[asyncio.Task] = None
            # ===== 极简两步循环：思考+行动合并，每次只决策一步 =====
            if preloop_skill_task is None:
                preloop_skill_task = asyncio.create_task(
                    asyncio.to_thread(
                        get_skill_integration().match_skill, user_input, result_context
                    )
                )
            if perf:
                print("[PERF][react] preloop_parallel=skill_match")
            # 不再预先生成 todos，每次只决策一步，观察结果后再决定下一步
            todos, json_plan_meta = [], None
            thinking_time = 0.0
            
            # ===== SKILL 匹配：检查是否有匹配的技能工作流 =====
            skill_guided = False
            skill_matched_ref = None
            fallback_workflow_tools: List[str] = []
            matched_skill, skill_score = None, 0.0
            if preloop_skill_task is not None:
                try:
                    matched_skill, skill_score = await preloop_skill_task
                except asyncio.CancelledError:
                    matched_skill, skill_score = get_skill_integration().match_skill(
                        user_input, result_context
                    )
                except Exception as _se:
                    print(f"[REACT] preloop skill_match task failed: {_se}")
                    matched_skill, skill_score = get_skill_integration().match_skill(
                        user_input, result_context
                    )
            else:
                matched_skill, skill_score = get_skill_integration().match_skill(
                    user_input, result_context
                )
            preloop_skill_task = None
            
            if matched_skill and skill_score >= 0.3:
                fallback_workflow_tools = []
                try:
                    wf = sorted(getattr(matched_skill, 'workflow', []) or [], key=lambda s: getattr(s, 'step', 0))
                    fallback_workflow_tools = [((getattr(s, 'tool', '') or '').strip()) for s in wf if (getattr(s, 'tool', '') or '').strip()]
                except Exception as e:
                    print(f"[REACT-planing] ⚠️ 读取技能 workflow 失败: {e}")
                # 合并模式：技能仅作上下文提示，由主循环 submit_react_think 定稿
                result_context["opening_skill_name"] = matched_skill.name
                if fallback_workflow_tools:
                    result_context["opening_skill_workflow"] = ", ".join(fallback_workflow_tools)
                print(
                    f"[REACT-planing] 合并首轮：技能 {matched_skill.name} 仅作上下文提示，由主循环 submit_react_think 定稿"
                )
                skill_guided = False
                skill_matched_ref = None
            else:
                skill_guided = False
                skill_matched_ref = None

            # 合并模式下不需要从技能工作流生成 Todo，由主循环 FC 返回

            # ===== MAIN LOOP: ACT（技能匹配时亦走同循环：思考流 + todo 解析 → 执行 → 观察）=====

            task_state = new_task_state("skill_guided" if skill_guided else "normal")
            if skill_guided:
                assert skill_matched_ref is not None
                task_state["plan"] = await self._build_structured_plan_rows(
                    todos,
                    user_input,
                    skill_guided=True,
                    skill_ref=skill_matched_ref,
                    fallback_workflow_tools=fallback_workflow_tools,
                )
            else:
                task_state["plan"] = _plan_rows_from_json_or_todos(todos, json_plan_meta)
            _suppress_plan_init_ui = _should_suppress_plan_ui(len(todos), None)
            if _plan_memo_defer_until_after_think():
                _suppress_plan_init_ui = True
            yield {
                "event": "plan_init",
                "mode": task_state["mode"],
                "steps": task_state["plan"],
                **({"suppress_plan_ui": True} if _suppress_plan_init_ui else {}),
            }

            try:
                _max_rounds = int(os.getenv("REACT_MAX_ROUNDS", "20"))
            except Exception:
                _max_rounds = 20
            _max_rounds = max(_max_rounds, len(todos))
            last_observation: Optional[Dict[str, Any]] = None
            last_analysis: Optional[Dict[str, Any]] = None
            round_idx = 0
            _prev_round_prepare_wait_idx: Optional[int] = None
            pending_next_decision: Optional[Dict[str, Any]] = None
            _incr_sum_state: Dict[str, Any] = {"text": "", "version": 0}
            if use_react_incremental_running_summary() and (
                not use_react_incremental_running_summary_block_loop()
            ):
                # 中途运行总览一律后台静默合并，避免卡在「正在准备下一步」等整段 LLM
                _incr_merge_q = asyncio.Queue()

                async def _incr_sum_bg_worker():
                    assert _incr_merge_q is not None
                    while True:
                        job = await _incr_merge_q.get()
                        try:
                            if job is None:
                                break
                            _st, _si, _tl, _td, _nl = job
                            await self._merge_running_summary_incremental_silent(
                                _st,
                                int(_si),
                                str(_tl),
                                str(_td),
                                str(_nl),
                            )
                        finally:
                            _incr_merge_q.task_done()

                _incr_worker_task = asyncio.create_task(_incr_sum_bg_worker())

            # modify 的 target_id / modifications 以服务端 _enrich_modify_decision_for_main_loop 补全为准，不依赖模型 XML 完整性。
            # 主循环：动态 ReAct（每轮根据观察再决策）；初始 todos 仅作 plan 概览，不强制逐步绑定。
            while not task_state["finished"] and round_idx < _max_rounds:
                i = round_idx
                _step_failed = False
                _t_round_bridge: Optional[float] = None
                _t_todo_start_wall: Optional[float] = None
                task_state["current_step"] = round_idx
                # 上一轮已进入“准备下一步”等待态：在本轮开始即关闭，避免一直转圈
                if _prev_round_prepare_wait_idx is not None:
                    yield {
                        "event": "phase_wait",
                        "kind": "next_round_prepare",
                        "active": False,
                        "index": _prev_round_prepare_wait_idx,
                    }
                    _prev_round_prepare_wait_idx = None
                if (not skill_guided) and task_state.get("plan"):
                    _sync_plan_single_in_progress(task_state["plan"], i)
                    if (os.getenv("REACT_PLAN_SSE_LIVE_STEPS", "1") or "1").strip().lower() not in (
                        "0",
                        "false",
                        "no",
                        "off",
                    ):
                        yield {
                            "event": "plan_update",
                            "steps": _normalize_plan_rows_for_sse(task_state["plan"]),
                            "reason": "in_progress_sync",
                            "index": i,
                        }
                elif round_idx < len(task_state["plan"]):
                    task_state["plan"][round_idx]["status"] = "running"
                # 区分规划任务与额外轮次：i < len(todos) 是规划内的任务，否则是动态决策轮次
                is_planned_step = i < len(todos)
                todo = todos[i] if is_planned_step else ""
                if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                    print(
                        f"[REACT-planing] ===== round {i + 1}/{_max_rounds} todo={todo[:200]!r} planned={is_planned_step} ====="
                    )
                # 发送 todo_start：planned=False 表示不在规划备忘中显示
                yield {'event': 'todo_start', 'index': i, 'step_id': i + 1, 'todo': todo, 'planned': is_planned_step}
                if len(todos) >= 1:
                    yield {'event': 'step_status', 'index': i, 'step_id': i + 1, 'status': 'running'}
                # 合并首轮时：不要让 UI 空白等待模型首包，先推一条可见的 agent_thought 占位。
                # 真实的 agent_thought delta（流式或整包 hint）到来后会自然续写/覆盖用户感知。
                if i == 0 and (not skill_guided):
                    yield {
                        "event": "agent_thought",
                        "delta": "正在生成执行计划并确定首步工具调用…\n",
                        "index": i,
                    }
                if perf:
                    _t_todo_start_wall = time.perf_counter()

                if skill_guided and round_idx >= len(todos):
                    break

                decision_response = ""
                if skill_guided:
                    out_sd: Dict[str, Any] = {}
                    assert skill_matched_ref is not None
                    if perf and _t_todo_start_wall is not None:
                        print(
                            f"[PERF][round-bridge] step={i} todo_start→skill_plan_prepare_ms="
                            f"{(time.perf_counter() - _t_todo_start_wall) * 1000:.1f}"
                        )
                    async for _se in self._skill_plan_step_stream_prepare(
                        i=i,
                        todo=todo,
                        user_input=user_input,
                        todos=todos,
                        skill_ref=skill_matched_ref,
                        fallback_workflow_tools=fallback_workflow_tools,
                        result_context=result_context,
                        project_id=project_id,
                        last_observation=last_observation,
                        out=out_sd,
                    ):
                        yield _se
                    decision = out_sd.get("decision") or {"execute": False, "tool": "", "params": {}}
                    skip_modify_exec = bool(out_sd.get("skill_skip"))
                else:
                    _decision_from_merge_pending = False
                    if pending_next_decision is None:
                        _sd_dec = await self._maybe_self_drive_decision_from_todo(
                            todo, user_input, i, len(todos)
                        )
                        if _sd_dec is not None:
                            pending_next_decision = _sd_dec
                    if pending_next_decision is None:
                        # 决策：默认流式叙事 + <decision>；REACT_DECIDE_FUNCTION_CALL=1 且 LLM 支持时走 FC 非流式
                        _prev_tool_for_decide: Optional[str] = None
                        if steps:
                            _tpt = str(
                                (steps[-1].get("decision") or {}).get("tool") or ""
                            ).strip().lower()
                            _prev_tool_for_decide = _tpt if _tpt else None
                        _ctx_d = shrink_payload_for_decide_prompt(
                            result_context, prev_tool=_prev_tool_for_decide
                        )
                        _lo_d = shrink_payload_for_decide_prompt(
                            last_observation, prev_tool=_prev_tool_for_decide
                        )
                        _la_d = shrink_payload_for_decide_prompt(
                            last_analysis, prev_tool=_prev_tool_for_decide
                        )
                        _decide_mt = resolve_decide_max_tokens_for_prev_tool(
                            _prev_tool_for_decide
                        )
                        _opening_merge_round = bool(
                            i == 0
                            and (not skill_guided)
                            and use_react_decide_function_call()
                            and hasattr(self.llm, "chat_completion_with_tools")
                        )
                        if _opening_merge_round:
                            decision_prompt = self._wrap_prompt(
                                ReactPromptTemplates.merged_opening_decide_prompt_fc(
                                    user_input,
                                    tools_info,
                                    _ctx_d,
                                    ui_locale=self._ui_locale,
                                )
                            )
                        else:
                            decision_prompt = self._wrap_prompt(
                                ReactPromptTemplates.decide_prompt_react_dynamic(
                                    user_input,
                                    tools_info,
                                    _ctx_d,
                                    round_idx=i,
                                    last_observation=_lo_d,
                                    last_analysis=_la_d,
                                    current_todo=todo,
                                )
                            )
                        use_fc = use_react_decide_function_call() and hasattr(
                            self.llm, "chat_completion_with_tools"
                        )
                        use_fc_stream = (
                            use_fc
                            and use_react_decide_fc_stream()
                            and hasattr(self.llm, "chat_completion_with_tools_stream")
                        )
                        if use_fc_stream:
                            from .react_function_call import build_react_decision_tools_from_registry, build_react_think_fc_tools

                            if _opening_merge_round:
                                if not build_react_think_fc_tools():
                                    use_fc_stream = False
                            elif not build_react_decision_tools_from_registry(self.tools):
                                use_fc_stream = False
                        if use_fc:
                            # 整包 FC：首字取决于 API；流式 FC：首字来自真实 delta。占位可关 REACT_DECIDE_FC_INSTANT_HINT=0
                            _hint_fc = (os.getenv("REACT_DECIDE_FC_INSTANT_HINT", "1") or "1").strip().lower()
                            if _hint_fc not in ("0", "false", "no", "off"):
                                yield {
                                    "event": "agent_thought",
                                    "delta": react_decide_fc_first_token_hint(self._ui_locale),
                                    "index": i,
                                }
                            # 非流式 FC 时并行「行动前说明」辅助流；流式 FC 时由真实 token 替代，默认不再并行第二条流
                            # 合并首轮 opening_merge 时禁止并行 hint：否则会出现「计划已定稿但 thought 还在续写」的错觉。
                            _fc_stream_hint = (os.getenv("REACT_DECIDE_FC_STREAM_HINT", "1") or "1").strip().lower()
                            if _opening_merge_round:
                                _fc_stream_hint = "0"
                            _stream_task = None
                            _stream_q: "asyncio.Queue[object]" = asyncio.Queue()
                            _STREAM_DONE = object()
                            if _fc_stream_hint not in ("0", "false", "no", "off") and not use_fc_stream:
                                _hint_prompt = (
                                    "用 2～4 句中文，简要说明你接下来要做什么（可能会调用哪个工具、为什么）。"
                                    "不要输出 XML/JSON/代码块。"
                                    f"\n\n用户请求：{user_input}\n本轮任务：{todo}\n"
                                )

                                async def _pump_fc_hint():
                                    try:
                                        async for _e in self._stream_react_ui_text(
                                            self._wrap_prompt(_hint_prompt),
                                            step_index=i,
                                            channel="__fc_decide_hint__",
                                        ):
                                            d = _e.get("delta") if isinstance(_e, dict) else ""
                                            if isinstance(d, str) and d:
                                                await _stream_q.put(
                                                    {"event": "agent_thought", "delta": d, "index": i}
                                                )
                                    except Exception:
                                        pass
                                    finally:
                                        await _stream_q.put(_STREAM_DONE)

                                _stream_task = asyncio.create_task(_pump_fc_hint())
                            yield {
                                "event": "phase_wait",
                                "kind": "decision_function_call",
                                "active": True,
                                "index": i,
                                "message": react_phase_wait_message(
                                    "decision_function_call", self._ui_locale
                                ),
                            }
                            if perf and _t_todo_start_wall is not None:
                                print(
                                    f"[PERF][round-bridge] step={i} todo_start→fc_invoke_ms="
                                    f"{(time.perf_counter() - _t_todo_start_wall) * 1000:.1f}"
                                )
                            _t_fc0 = time.perf_counter()
                            _result_fc: List[Tuple[Dict[str, Any], str]] = []
                            if use_fc_stream:
                                try:
                                    async for _ev in self._iter_fc_decide_stream(
                                        decision_prompt,
                                        step_index=i,
                                        prev_tool=_prev_tool_for_decide,
                                        result_out=_result_fc,
                                        opening_merge=_opening_merge_round,
                                    ):
                                        yield _ev
                                    decision, decision_response = _result_fc[0]
                                except Exception as _e_fc_s:
                                    print(
                                        f"[REACT-FC-STREAM] step={i} 失败，回退整包 FC: {_e_fc_s!r}"
                                    )
                                    decision, decision_response = await self._react_decide_function_call(
                                        decision_prompt,
                                        step_index=i,
                                        prev_tool=_prev_tool_for_decide,
                                        opening_merge=_opening_merge_round,
                                    )
                            else:
                                _fc_task = asyncio.create_task(
                                    self._react_decide_function_call(
                                        decision_prompt,
                                        step_index=i,
                                        prev_tool=_prev_tool_for_decide,
                                        opening_merge=_opening_merge_round,
                                    )
                                )
                                while True:
                                    done, _pending = await asyncio.wait(
                                        [t for t in (_fc_task, _stream_task) if t is not None],
                                        timeout=0.25,
                                        return_when=asyncio.FIRST_COMPLETED,
                                    )
                                    while True:
                                        try:
                                            item = _stream_q.get_nowait()
                                        except Exception:
                                            break
                                        if item is _STREAM_DONE:
                                            _stream_task = None
                                            break
                                        if isinstance(item, dict):
                                            yield item
                                    if _fc_task in done:
                                        break
                                decision, decision_response = await _fc_task
                                if _stream_task is not None and not _stream_task.done():
                                    _stream_task.cancel()
                                    try:
                                        await _stream_task
                                    except Exception:
                                        pass
                            if perf:
                                print(
                                    f"[PERF][react] fc_decide_roundtrip_ms="
                                    f"{(time.perf_counter() - _t_fc0) * 1000:.1f} step={i} stream={int(use_fc_stream)}"
                                )
                            yield {
                                "event": "phase_wait",
                                "kind": "decision_function_call",
                                "active": False,
                                "index": i,
                            }
                            print(f"[REACT-planing] LLM决策(FC): {decision_response}")
                        else:
                            if perf and _t_todo_start_wall is not None:
                                print(
                                    f"[PERF][round-bridge] step={i} todo_start→stream_decide_start_ms="
                                    f"{(time.perf_counter() - _t_todo_start_wall) * 1000:.1f}"
                                )
                            _sink_d: List[str] = []
                            _dg = self._stream_agent_decide_with_narrative(
                                decision_prompt,
                                step_index=i,
                                full_text_sink=_sink_d,
                                max_tokens=_decide_mt,
                            )
                            _dit = _dg.__aiter__()
                            while True:
                                try:
                                    _de = await _dit.__anext__()
                                    yield _de
                                except StopAsyncIteration:
                                    break
                            decision_response = _sink_d[0] if _sink_d else ""
                            print(f"[REACT-planing] LLM决策原始响应: {decision_response}")
                            yield {
                                "event": "phase_wait",
                                "kind": "decision_xml_parse",
                                "active": True,
                                "index": i,
                                "message": react_phase_wait_message(
                                    "decision_xml_parse", self._ui_locale
                                ),
                            }
                            decision = parse_xml_decision(decision_response)
                            yield {
                                "event": "phase_wait",
                                "kind": "decision_xml_parse",
                                "active": False,
                                "index": i,
                            }
                        # <decision> 前无自然语言或模型只吐 XML 时，流式可能无 agent_thought；用 reason / 合成一行兜底
                        try:
                            _dr = (decision_response or "").strip()
                            _m_pre = re.search(r"<\s*decision\b", _dr, re.IGNORECASE)
                            _pre_dec = (_dr[: _m_pre.start()].strip() if _m_pre else _dr)
                            _reason_fb = (decision.get("reason") or "").strip()
                            if len(_pre_dec) < 4:
                                _line = _reason_fb or react_fallback_decision_line(
                                    decision.get("tool") or "?",
                                    decision.get("execute"),
                                    self._ui_locale,
                                )
                                if _line.strip():
                                    yield {
                                        "event": "agent_thought",
                                        "delta": _line,
                                        "index": i,
                                    }
                        except Exception:
                            pass
                    else:
                        _decision_from_merge_pending = True
                        decision = pending_next_decision
                        pending_next_decision = None
                        try:
                            decision_response = json.dumps(
                                decision, ensure_ascii=False, default=str
                            )[:4000]
                        except Exception:
                            decision_response = ""
                        _r_m = (decision.get("reason") or "").strip()
                        if _r_m:
                            yield {
                                "event": "agent_thought",
                                "delta": _r_m + "\n\n",
                                "index": i,
                            }
                        if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                            print(
                                f"[REACT-merge] step={i} pending_next_decision "
                                f"tool={decision.get('tool')!r} execute={decision.get('execute')!r}"
                            )
                    _llm = getattr(self, "llm", None)
                    print(
                        f"[REACT-planing] step={i} llm_class={type(_llm).__name__} "
                        f"llm_model={getattr(_llm, 'model', None)!r} "
                        f"parsed_tool={decision.get('tool')!r} execute={decision.get('execute')!r} "
                        f"params_keys={list((decision.get('params') or {}).keys())}"
                    )
                    # 用户明显在改已有记录，但模型选 create 时打警告（便于区分「模型蠢」与「没用上 Qwen」）
                    _ui = user_input or ""
                    if (
                        decision.get("execute")
                        and decision.get("tool") == "create"
                        and any(
                            k in _ui
                            for k in (
                                "修改",
                                "改为",
                                "变成",
                                "变为",
                                "更新",
                                "改状态",
                                "状态改",
                                "草稿",
                                "生效",
                            )
                        )
                    ):
                        print(
                            f"[REACT-planing] 用户表述偏「修改/改状态」，但 LLM 决策为 create。"
                            f" todo={todo!r} user_input[:160]={_ui[:160]!r}"
                        )

                    print(f"[REACT-planing] 决策结果: {decision}")
                    if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                        print(
                            f"[REACT-planing] step={i} decide_done raw_len={len(decision_response)} "
                            f"tool={decision.get('tool')!r} execute={decision.get('execute')!r}"
                        )

                    # 合并首轮：解析 LLM 输出的三种格式（闲聊/单步/多步计划）
                    if i == 0 and (not skill_guided):
                        _parsed = parse_opening_decision(decision_response)
                        _parsed_type = _parsed.get("type")
                        print(f"[REACT-merge-opening] 解析类型={_parsed_type} parsed={_parsed}")
                        
                        # 类型 1: 闲聊
                        if _parsed_type == "chat":
                            _cancel_preloop_tasks()
                            msg = _parsed.get("message", "你好！有什么可以帮你的？")
                            yield {"event": "intent_clarification", "message": msg, "kind": "llm_chat_only"}
                            _chat_sum_gap = _summary_stream_yield_gap_s()
                            for _chunk in _iter_direct_chat_reply_stream_chunks(msg):
                                yield {"event": "summary_stream", "delta": _chunk}
                                if _chat_sum_gap > 0:
                                    await asyncio.sleep(_chat_sum_gap)
                            yield {
                                "event": "done",
                                "findings": [],
                                "steps_count": 0,
                                "duration": time.time() - start_time,
                                "summary": msg,
                                "direct_reply": True,
                            }
                            return
                        
                        # 类型 2: 单步任务（简单任务，不生成规划备忘）
                        elif _parsed_type == "single":
                            _tool_name = _parsed.get("tool", "")
                            _tool_params = _parsed.get("params", {})
                            if _tool_name:
                                decision = {
                                    "execute": True,
                                    "tool": _tool_name,
                                    "params": _tool_params,
                                    "reason": "opening_single_step",
                                }
                                if _tool_name == "modify" and "confirm" not in decision["params"]:
                                    decision["params"]["confirm"] = False
                                if _tool_name == "create" and "confirm" not in decision["params"]:
                                    decision["params"]["confirm"] = False
                                # 单步任务：不生成规划备忘，清空计划
                                task_state["plan"] = []
                                print(f"[REACT-merge-opening] 单步任务 tool={_tool_name} params={_tool_params}，不生成规划备忘")
                        
                        # 类型 3: 多步任务（复杂任务，显示规划备忘）
                        elif _parsed_type == "multi":
                            _plan_list = _parsed.get("plan", [])
                            _first_tool = _parsed.get("first_tool", "")
                            _first_params = _parsed.get("first_params", {})
                            if _plan_list and len(_plan_list) >= 2:
                                # 更新 todos 和 task_state["plan"]（原地修改避免 nonlocal）
                                new_todos = [str(p) for p in _plan_list if p]
                                todos.clear()
                                todos.extend(new_todos)
                                task_state["plan"] = _plan_rows_from_json_or_todos(todos, None)
                                # 发送不带 suppress 的 plan_update 以显示规划备忘
                                yield {
                                    "event": "plan_update",
                                    "steps": task_state["plan"],
                                    "reason": "multi_step_plan",
                                    "suppress_plan_ui": False,
                                }
                                # 设置首轮工具调用
                                if _first_tool:
                                    decision = {
                                        "execute": True,
                                        "tool": _first_tool,
                                        "params": _first_params or {},
                                        "reason": "opening_multi_step_first",
                                    }
                                    if _first_tool == "modify" and "confirm" not in decision["params"]:
                                        decision["params"]["confirm"] = False
                                print(f"[REACT-merge-opening] 多步任务 plan={todos} first_tool={_first_tool}")
                            else:
                                # plan 不足2步，降级为单步
                                print(f"[REACT-merge-opening] plan 不足2步，降级为单步: {_plan_list}")
                        
                        # 类型 unknown: 检查是否已通过 FC 获得工具
                        elif _parsed_type == "unknown":
                            if decision.get("tool") and decision.get("execute"):
                                print(f"[REACT-merge-opening] unknown 类型但有 tool={decision.get('tool')}")
                            else:
                                print(f"[REACT-merge-opening] unknown 类型，无工具调用")
                
                    # 兜底逻辑：当 LLM 返回空响应但 Todo包含 modify 关键词时
                    if not decision['execute'] and 'modify' in todo.lower():
                        print(f"[REACT-planing] 检测到 modify 任务但 LLM 返回空响应，尝试自动推断参数...")
                        decision = self._infer_modify_params(todo, result_context)
                        print(f"[REACT-planing] 自动推断的决策: {decision}")
                
                    # Skill工具优化：智能任务处理
                    if decision['execute']:
                        decision = await self._optimize_with_skill_tool(decision, user_input, result_context, project_id)

                    # 面向用户：流式说明入参与决策（不展示原始 XML/JSON）；注入完整待办列表供「对照」
                    if decision['execute'] and not _decision_from_merge_pending:
                        try:
                            _todos_ov = (
                                "\n".join(f"{j + 1}. {t}" for j, t in enumerate(todos))
                                if len(todos) >= 1
                                else ""
                            )
                            _pp = self._wrap_prompt(
                                ReactPromptTemplates.ui_params_summary_prompt(
                                    todo,
                                    str(decision.get('tool') or ''),
                                    decision.get('params')
                                    if isinstance(decision.get('params'), dict)
                                    else {},
                                    str(decision.get('reason') or ''),
                                    todos_overview=_todos_ov,
                                )
                            )
                            async for _ue in self._stream_react_ui_text(_pp, step_index=i, channel='params'):
                                yield _ue
                            _dp = self._wrap_prompt(
                                ReactPromptTemplates.ui_decision_summary_prompt(
                                    todo, decision, todos_overview=_todos_ov
                                )
                            )
                            async for _ue in self._stream_react_ui_text(_dp, step_index=i, channel='decision_observe'):
                                yield _ue
                        except Exception as _ui_e:
                            print(f"[REACT-thought] params/decision summary stream failed: {_ui_e}")
                
                if not decision['execute']:
                    print(f"[REACT-planing] 跳过任务（execute=False）")
                    if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                        print(f"[REACT-planing] step={i} round_done skipped=execute_false")
                    yield {'event': 'skip', 'todo': todo, 'index': i}
                    if len(todos) >= 1:
                        yield {'event': 'step_status', 'index': i, 'step_id': i + 1, 'status': 'done'}
                    yield {'event': 'todo_end', 'index': i, 'step_id': i + 1}
                    _stop_r = str(decision.get('reason') or '')
                    if any(
                        k in _stop_r
                        for k in ('任务已完成', '已完成', '无需再执行', '不需要再执行', '目标已达成')
                    ):
                        break
                    round_idx += 1
                    continue
                
                # Text2SQL 优化：数据库查询优先使用自然语言
                if decision['execute'] and decision['tool'] == 'database_query':
                    natural_query = self._extract_natural_query(todo, user_input)
                    if natural_query and self.text2sql_tool is None:
                        self.text2sql_tool = get_text2sql_tool("instance/badcase_doctor.db")
                    if natural_query and self.text2sql_tool:
                        print(f"[REACT-execution] 优先使用 Text2SQL执行: {natural_query}")
                        decision['params']['natural_query'] = natural_query
                
                # Todo 文案与 LLM 决策对齐：避免「步骤标题是 create、executing 里却是 grep」导致前端展示矛盾
                if (not skill_guided) and decision.get('execute') and decision.get('tool'):
                    todo_params_aligned = await self._extract_todo_params(todo, user_input)
                    t_from_todo = todo_params_aligned.get('tool')
                    if (
                        t_from_todo
                        and t_from_todo != 'unknown'
                        and t_from_todo != decision.get('tool')
                        and t_from_todo in ('create', 'grep', 'modify')
                        and decision.get('tool') in ('create', 'grep', 'modify')
                    ):
                        print(
                            f"[REACT-thought] Todo 与 LLM 工具不一致，按 Todo 纠正: "
                            f"{decision.get('tool')} -> {t_from_todo} | todo={todo!r}"
                        )
                        decision['tool'] = t_from_todo
                        new_params = dict(todo_params_aligned.get('params') or {})
                        old_p = decision.get('params') or {}
                        if isinstance(old_p, dict):
                            for k, v in old_p.items():
                                if v is None or v == '' or v == {}:
                                    continue
                                if k not in new_params or new_params.get(k) in (None, '', {}):
                                    new_params[k] = v
                        decision['params'] = new_params
                    if decision.get('tool') == 'create':
                        dp = decision.setdefault('params', {})
                        dp.setdefault('natural_query', user_input)

                if (not skill_guided) and decision.get('execute') and decision.get('tool') == 'grep':
                    self._coerce_grep_target_for_user_intent(decision, user_input, todo)

                if not skill_guided:
                    skip_modify_exec = False
                # 主循环 modify：补全 target_id / modifications（与技能分支一致），并可选下发补救 grep 事件
                if (not skill_guided) and decision.get('execute') and decision.get('tool') == 'modify':
                    decision, _pre_yield_modify = await self._enrich_modify_decision_for_main_loop(
                        decision, todo, user_input, result_context, project_id, step_index=i
                    )
                    for _ev in _pre_yield_modify:
                        yield _ev
                    if not self._modify_params_ready(decision.get('params')):
                        decision, _lr_ev = await self._last_resort_modify_fill(
                            decision, todo, user_input, result_context, project_id, step_index=i
                        )
                        for _ev in _lr_ev:
                            yield _ev
                    if not self._modify_params_ready(decision.get('params')):
                        nq = (user_input or todo or '').strip()
                        if nq:
                            decision.setdefault('params', {})['natural_query'] = nq[:2000]
                    if not self._modify_params_ready(decision.get('params')):
                        skip_modify_exec = True
                        print(
                            "[REACT-thought] stability_gate: modify 仍缺 target_id/natural_query 或 modifications，"
                            "跳过执行以避免无效调用"
                        )

                if skip_modify_exec:
                    observation = {
                        'success': False,
                        'skipped': True,
                        'stability_gate': 'modify_params_incomplete',
                        'error': '缺少必要参数：modify 需要 target_id（或 natural_query）与非空 modifications，已尝试 enrich/最后手段补全仍不足，请明确要改的记录与字段。',
                        'message': 'modify 未执行（参数未就绪）',
                    }
                    print(f"[REACT-execution] 执行工具: {decision['tool']} (stability_gate 跳过)")
                else:
                    print(f"[REACT-execution] 执行工具: {decision['tool']}")

                    # 执行前先给出一条可读说明，帮助前端在工具真正运行前展示「即将执行」文案
                    executing_payload = {
                        'event': 'executing',
                        'tool': decision['tool'],
                        'reason': decision.get('reason', '') or f'Todo步骤 {i + 1}',
                        'index': i,
                    }
                    _pp = decision.get('params') or {}
                    _pub = {}
                    for _k in ('keywords', 'target', 'mode', 'fields', 'modifications', 'target_id'):
                        if _k in _pp and _pp[_k] not in (None, '', {}):
                            _pub[_k] = _pp[_k]
                    if _pub:
                        executing_payload['params'] = _pub
                    if decision['tool'] == 'grep':
                        executing_payload['message'] = react_executing_grep_about_to(
                            _pp.get("keywords"),
                            _pp.get("target"),
                            _pp.get("mode"),
                            self._ui_locale,
                        )
                    elif decision['tool'] == 'create':
                        executing_payload['message'] = react_executing_create_about_to(
                            _pp.get("target"),
                            _pp.get("natural_query"),
                            self._ui_locale,
                        )
                    elif decision['tool'] == 'database_query':
                        executing_payload['message'] = react_executing_database_query_about_to(
                            _pp.get("natural_query"),
                            _pp.get("query"),
                            _pp.get("sql"),
                            self._ui_locale,
                        )
                    elif decision['tool'] == 'modify':
                        mods = _pp.get('modifications') or {}
                        _target = _pp.get('target')
                        _target_id = _pp.get('target_id')
                        if isinstance(mods, dict) and mods:
                            executing_payload['fields'] = list(mods.keys())
                        _keys_zh = (
                            "、".join(list(mods.keys())[:6])
                            if isinstance(mods, dict) and mods
                            else ""
                        )
                        _mods_en = (
                            modify_modifications_kv_summary(mods, self._ui_locale)
                            if isinstance(mods, dict) and mods
                            else ""
                        )
                        executing_payload['message'] = react_executing_modify_about_to(
                            _target,
                            _target_id,
                            _mods_en,
                            _keys_zh,
                            self._ui_locale,
                        )

                    yield executing_payload

                    # 批量修改逻辑：如果是 modify 工具，检查是否有候选列表（badcase/bug/testcase）
                    # 按用户意图选择类型：说「修改bug」用 bug_list，避免误用 badcase_list
                    if decision['tool'] == 'modify':
                        badcase_list = result_context.get('badcase_list', [])
                        bug_list = result_context.get('bug_list', [])
                        testcase_list = result_context.get('testcase_list', [])
                        explicit = self._infer_modify_target_explicit(user_input, todo)
                        user_infer = self._infer_modify_target(user_input, todo)
                        if explicit:
                            mod_target = explicit
                        else:
                            mod_target = (decision.get('params') or {}).get('target') or user_infer
                        # 模型常把 target 写成默认 badcase；用户明说「测试用例」且上下文有 testcase 时不得误用 badcase 列表
                        if user_infer == 'testcase' and testcase_list:
                            mod_target = 'testcase'
                        elif user_infer == 'bug' and bug_list:
                            mod_target = 'bug'
                        elif user_infer == 'badcase' and badcase_list:
                            mod_target = 'badcase'
                        # 本轮定位仅命中一类记录时，直接与列表对齐（避免 todo 里写错 badcase 等）
                        if (
                            testcase_list
                            and not badcase_list
                            and not bug_list
                        ):
                            mod_target = 'testcase'
                        elif badcase_list and not testcase_list and not bug_list:
                            mod_target = 'badcase'
                        elif bug_list and not testcase_list and not badcase_list:
                            mod_target = 'bug'
                        _lgt = str(result_context.get('_last_grep_target') or '').lower()
                        if _lgt == 'testcase' and testcase_list:
                            mod_target = 'testcase'
                        elif _lgt == 'badcase' and badcase_list:
                            mod_target = 'badcase'
                        elif _lgt == 'bug' and bug_list:
                            mod_target = 'bug'
                        if mod_target == 'bug' and bug_list:
                            target_list, target_type = bug_list, 'bug'
                        elif mod_target == 'testcase' and testcase_list:
                            target_list, target_type = testcase_list, 'testcase'
                        elif badcase_list and explicit != 'testcase':
                            target_list, target_type = badcase_list, 'badcase'
                        elif bug_list:
                            target_list, target_type = bug_list, 'bug'
                        elif testcase_list:
                            target_list, target_type = testcase_list, 'testcase'
                        else:
                            _fallback_t = (
                                mod_target
                                if mod_target in ('badcase', 'bug', 'testcase')
                                else 'badcase'
                            )
                            target_list, target_type = [], _fallback_t

                        _tl_ids = [x.get("id") for x in target_list if isinstance(x, dict)]
                        _dec_tid = (decision.get("params") or {}).get("target_id")
                        print(
                            f"[MODIFY-TRACE] 主循环 modify 前: mod_target={mod_target!r}, "
                            f"选用 target_type={target_type}, target_list_len={len(target_list)}, "
                            f"target_list_ids={_tl_ids}, decision.params.target_id={_dec_tid}, "
                            f"context lens bug/bc/tc={len(bug_list)}/{len(badcase_list)}/{len(testcase_list)}"
                        )

                        # grep 的 bug_location 可能比「可跳转 navigation」多（如无 plan_id 被导航丢弃）；
                        # 批量 modify 必须与导航候选一致，避免「界面定位 2 条、批量改 3 条」。
                        if target_list and len(target_list) > 1:
                            target_list = self._constrain_modify_target_list_by_grep_navigation(
                                target_list,
                                target_type,
                                result_context,
                                trace_phase="main_loop",
                            )

                        # 仅一条候选时与 enrich 对齐：直接从列表写 target_id（grep_result.first_* 可能为空）
                        if (
                            decision.get('tool') == 'modify'
                            and target_list
                            and len(target_list) == 1
                            and not (decision.get('params') or {}).get('target_id')
                        ):
                            only = target_list[0]
                            oid = only.get('id') if isinstance(only, dict) else None
                            if oid is not None:
                                decision.setdefault('params', {})['target_id'] = oid
                                decision['params']['target'] = target_type
                                print(f"[REACT-execution] 主循环从单条候选注入 target_id={oid} ({target_type})")
                        
                        if target_list and len(target_list) > 1:
                            print(
                                f"[MODIFY-TRACE] 主循环 → 批量 modify: 共 {len(target_list)} 条 {target_type}"
                            )
                            batch_ids = [
                                item.get("id")
                                for item in target_list
                                if item.get("id") is not None
                            ]
                            if not batch_ids:
                                observation = {
                                    "success": False,
                                    "error": "批量修改缺少有效 id",
                                    "batch_modify": True,
                                }
                            else:
                                modify_decision = decision.copy()
                                mp = dict(modify_decision.get("params") or {})
                                modify_decision["params"] = mp
                                mp["target_ids"] = batch_ids
                                mp["target"] = target_type
                                mp["batch_items"] = [
                                    {"id": x.get("id"), "plan_id": x.get("plan_id")}
                                    for x in target_list
                                    if x.get("id") is not None
                                ]
                                mp.pop("target_id", None)
                                print(
                                    f"[REACT-execution] 批量 modify 单次工具调用: {len(batch_ids)} 条 {target_type} ids={batch_ids}"
                                )
                                started = time.time()
                                task = asyncio.create_task(self._execute_tool(modify_decision))
                                await asyncio.sleep(0.1)
                                _mbr = react_modify_executing_fallback_reason(self._ui_locale)
                                _mod_hb_bucket: Optional[int] = None
                                while not task.done():
                                    waited = time.time() - started
                                    got_any = False
                                    try:
                                        pq = (modify_decision.get("params") or {}).get("progress_queue")
                                        if pq:
                                            while True:
                                                msg = pq.get_nowait()
                                                got_any = True
                                                yield _modify_progress_to_stream_event(msg, i, _mbr)
                                                print(
                                                    f"[REACT-execution] modify 批量进度: {str(msg)[:240]}",
                                                    flush=True,
                                                )
                                    except Exception:
                                        pass
                                    if not got_any:
                                        _emit_hb, _hb_sec = _modify_wait_heartbeat_should_emit(
                                            _mod_hb_bucket, waited
                                        )
                                        if _emit_hb:
                                            _mod_hb_bucket = _hb_sec
                                            yield {
                                                "event": "executing",
                                                "tool": "modify",
                                                "reason": _mbr,
                                                "index": i,
                                                "message": react_modify_progress_wait(
                                                    float(_hb_sec), self._ui_locale
                                                ),
                                            }
                                    await asyncio.sleep(0.12 if got_any else 0.28)
                                observation = await task
                                for _tte in self._drain_tool_task_sse_buffer_list():
                                    yield _tte
                        else:
                            # 单个修改：modify 可能执行较久，持续下发分步进度/心跳
                            if decision.get('tool') == 'modify':
                                print(
                                    f"[MODIFY-TRACE] 主循环 → 单次 modify: target_list_len={len(target_list)}, "
                                    f"将执行 decision.params.target_id={(decision.get('params') or {}).get('target_id')}"
                                )
                                started = time.time()
                                task = asyncio.create_task(self._execute_tool(decision))
                                await asyncio.sleep(0.1)
                                _mod_hb_bucket_sr: Optional[int] = None
                                while not task.done():
                                    waited = time.time() - started
                                    got_any = False
                                    try:
                                        pq = (decision.get('params') or {}).get('progress_queue')
                                        if pq:
                                            while True:
                                                msg = pq.get_nowait()
                                                got_any = True
                                                yield _modify_progress_to_stream_event(
                                                    msg,
                                                    i,
                                                    react_modify_single_record_reason(self._ui_locale),
                                                )
                                                print(f"[REACT-execution] modify 进度: {msg}", flush=True)
                                    except Exception:
                                        pass
                                    if not got_any:
                                        _emit_hb, _hb_sec = _modify_wait_heartbeat_should_emit(
                                            _mod_hb_bucket_sr, waited
                                        )
                                        if _emit_hb:
                                            _mod_hb_bucket_sr = _hb_sec
                                            yield {
                                                'event': 'executing',
                                                'tool': 'modify',
                                                'reason': react_modify_single_record_reason(
                                                    self._ui_locale
                                                ),
                                                'index': i,
                                                'message': react_modify_progress_wait(
                                                    float(_hb_sec), self._ui_locale
                                                ),
                                            }
                                    await asyncio.sleep(0.12 if got_any else 0.28)
                                observation = await task
                                for _tte in self._drain_tool_task_sse_buffer_list():
                                    yield _tte
                            else:
                                observation = await self._execute_tool(decision)
                                for _tte in self._drain_tool_task_sse_buffer_list():
                                    yield _tte
                    else:
                        if decision.get('tool') == 'modify':
                            started = time.time()
                            task = asyncio.create_task(self._execute_tool(decision))
                            await asyncio.sleep(0.1)
                            _mod_hb_bucket_else: Optional[int] = None
                            while not task.done():
                                waited = time.time() - started
                                got_any = False
                                try:
                                    pq = (decision.get('params') or {}).get('progress_queue')
                                    if pq:
                                        while True:
                                            msg = pq.get_nowait()
                                            got_any = True
                                            yield _modify_progress_to_stream_event(
                                                msg,
                                                i,
                                                decision.get("reason")
                                                or react_modify_executing_fallback_reason(self._ui_locale),
                                            )
                                            print(f"[REACT-execution] modify 进度: {msg}", flush=True)
                                except Exception:
                                    pass
                                if not got_any:
                                    _emit_hb, _hb_sec = _modify_wait_heartbeat_should_emit(
                                        _mod_hb_bucket_else, waited
                                    )
                                    if _emit_hb:
                                        _mod_hb_bucket_else = _hb_sec
                                        yield {
                                            'event': 'executing',
                                            'tool': 'modify',
                                            'reason': decision.get('reason')
                                            or react_modify_executing_fallback_reason(self._ui_locale),
                                            'index': i,
                                            'message': react_modify_progress_wait(
                                                float(_hb_sec), self._ui_locale
                                            ),
                                        }
                                await asyncio.sleep(0.12 if got_any else 0.28)
                            observation = await task
                            for _tte in self._drain_tool_task_sse_buffer_list():
                                yield _tte
                        else:
                            observation = await self._execute_tool(decision)
                            for _tte in self._drain_tool_task_sse_buffer_list():
                                yield _tte
                
                print(f"[REACT-execution] 工具执行结果:")
                print(f"[REACT-execution]   成功: {observation.get('success', False)}")
                if 'results' in observation:
                    results = observation.get('results', [])
                    print(f"[REACT-execution]   结果条数: {len(results)}")
                    if results:
                        print(f"[REACT-execution] === 搜索结果详情 ===")
                        for idx, item in enumerate(results[:3], 1):
                            if isinstance(item, dict):
                                title = item.get('title') or item.get('text') or str(item)[:80]
                            else:
                                title = str(item)[:80]
                            print(f"[REACT-thought]   [{idx}] {title}")
                        if len(results) > 3:
                            print(f"[REACT-thought]   ... 还有 {len(results)-3} 条结果")
                if 'query' in observation:
                    print(f"[REACT-execution]   查询: {observation.get('query')}")
                if 'engine' in observation:
                    print(f"[REACT-execution]   引擎: {observation.get('engine')}")
                if 'error' in observation:
                    print(f"[REACT-thought]   错误: {observation.get('error')}")
                print(f"[REACT-execution]   完整结果: {observation}")
                
                # 智能重试：如果 modify 缺少 target_id，自动执行 grep 查询
                if (
                    not skip_modify_exec
                    and decision['tool'] == 'modify'
                    and observation.get('need_grep_first')
                ):
                    print(f"[REACT-execution] modify 缺少 target_id，自动执行 grep 查询...")
                    yield {
                        'event': 'retry',
                        'message': react_retry_grep_for_modify(self._ui_locale),
                    }
                    
                    suggested_params = observation.get('suggested_params', {})
                    # 从用户输入/ todo 中提取要查找的标题作为 keywords（拆分模糊匹配由 grep 内部处理）
                    keywords = self._extract_title_keywords_for_grep(user_input, todo)
                    # 兜底：在所有迭代计划、不分类型查一遍（target=all，不传 plan_id）
                    grep_params = {
                        'target': 'all',
                        'project_id': suggested_params.get('project_id', self.project_id),
                        'userId': 'system_agent'
                    }
                    if keywords:
                        grep_params['keywords'] = keywords
                        print(f"[REACT-execution] 从用户输入提取 grep keywords: '{keywords}'")
                    # 不传 plan_id，grep 查全项目所有计划
                    grep_decision = {
                        'execute': True,
                        'tool': 'grep',
                        'params': grep_params
                    }
                    grep_observation = await self._execute_tool(grep_decision)
                    for _tte in self._drain_tool_task_sse_buffer_list():
                        yield _tte
                    print(f"[REACT-execution] grep 结果: success={grep_observation.get('success')}")
                    
                    # 从 grep 结果中提取 target_id（rerank 分高的选一条；支持 badcase/bug/testcase）
                    if grep_observation.get('success'):
                        # 复用统一合并逻辑：优先以 grep_tool 的 navigation 作为唯一候选集，避免「grep 2 条、modify 批量 3 条」
                        try:
                            self._merge_grep_observation_into_context(grep_observation, grep_params, result_context)
                        except Exception as _e:
                            print(f"[REACT-execution] 合并 grep 结果失败（将回退旧逻辑）: {_e}")
                            grep_data = grep_observation.get('data', {})
                            result_context['badcase_list'] = grep_data.get('badcase_analysis', []) or []
                            result_context['bug_list'] = grep_data.get('bug_location', []) or []
                            result_context['testcase_list'] = grep_data.get('testcase_location', []) or []
                            # 用 rerank 选中一个 id 作为兜底
                            if result_context['badcase_list']:
                                best = self._pick_best_match_from_list(result_context['badcase_list'], keywords, key_title='title')
                                result_context['first_badcase_id'] = best.get('id') if best else None
                            if result_context['bug_list']:
                                best = self._pick_best_match_from_list(result_context['bug_list'], keywords, key_title='title')
                                result_context['first_bug_id'] = best.get('id') if best else None
                            if result_context['testcase_list']:
                                best = self._pick_best_match_from_list(result_context['testcase_list'], keywords, key_title='title')
                                result_context['first_testcase_id'] = best.get('id') if best else None

                        # 兼容下游：仍写入旧字段 first_*_id（优先使用 merge 后的 grep_result）
                        _gr = result_context.get('grep_result') or {}
                        if _gr.get('first_badcase_id') is not None:
                            result_context['first_badcase_id'] = _gr.get('first_badcase_id')
                        if _gr.get('first_bug_id') is not None:
                            result_context['first_bug_id'] = _gr.get('first_bug_id')
                        if _gr.get('first_testcase_id') is not None:
                            result_context['first_testcase_id'] = _gr.get('first_testcase_id')
                        
                        yield {'event': 'observation', 'data': grep_observation, 'index': i, 'step_id': i + 1}
                        
                        # 按用户意图选类型：说「修改bug」用 bug_list；勿信模型单写 badcase
                        suggested = (decision.get('params') or {}).get('target') or suggested_params.get('target')
                        if not suggested:
                            suggested = self._infer_modify_target(user_input, '')
                        user_infer = self._infer_modify_target(user_input, '')
                        if user_infer == 'testcase' and result_context.get('testcase_list'):
                            suggested = 'testcase'
                        elif user_infer == 'bug' and result_context.get('bug_list'):
                            suggested = 'bug'
                        elif user_infer == 'badcase' and result_context.get('badcase_list'):
                            suggested = 'badcase'
                        if suggested == 'bug' and result_context.get('bug_list'):
                            target_list, target_type = result_context['bug_list'], 'bug'
                        elif suggested == 'testcase' and result_context.get('testcase_list'):
                            target_list, target_type = result_context['testcase_list'], 'testcase'
                        elif result_context.get('badcase_list'):
                            target_list, target_type = result_context['badcase_list'], 'badcase'
                        elif result_context.get('bug_list'):
                            target_list, target_type = result_context['bug_list'], 'bug'
                        elif result_context.get('testcase_list'):
                            target_list, target_type = result_context['testcase_list'], 'testcase'
                        else:
                            target_list = []
                            target_type = 'badcase'
                        if target_list:
                            if len(target_list) > 1:
                                target_list = self._constrain_modify_target_list_by_grep_navigation(
                                    target_list,
                                    target_type,
                                    result_context,
                                    trace_phase="retry",
                                )
                            best_match = self._pick_best_match_from_list(target_list, keywords, key_title='title')
                            result_context['first_badcase_id' if target_type == 'badcase' else ('first_bug_id' if target_type == 'bug' else 'first_testcase_id')] = best_match.get('id') if best_match else None
                            # 使用完整 target_list 批量修改，不缩减为单条
                            if len(target_list) > 1:
                                print(
                                    f"[REACT-execution] 重试批量修改（单次工具）{len(target_list)} 条 {target_type}"
                                )
                                retry_decision = decision.copy()
                                rparams = dict(retry_decision.get("params") or {})
                                retry_decision["params"] = rparams
                                if not rparams.get("modifications"):
                                    rparams["modifications"] = self._extract_modifications_with_regex(
                                        user_input
                                    )
                                if not rparams.get("modifications"):
                                    with self._llm_no_thinking():
                                        rparams["modifications"] = await self._extract_modifications_with_llm(
                                            todo, user_input
                                        )
                                rparams["target_ids"] = [
                                    x.get("id") for x in target_list if x.get("id") is not None
                                ]
                                rparams["target"] = target_type
                                rparams["batch_items"] = [
                                    {"id": x.get("id"), "plan_id": x.get("plan_id")}
                                    for x in target_list
                                    if x.get("id") is not None
                                ]
                                rparams.pop("target_id", None)
                                observation = await self._execute_tool(retry_decision)
                                for _tte in self._drain_tool_task_sse_buffer_list():
                                    yield _tte
                            else:
                                # 单个修改
                                retry_decision = decision.copy()
                                retry_decision['params']['target_id'] = target_list[0].get('id')
                                retry_decision['params']['target'] = target_type
                                if not retry_decision['params'].get('modifications'):
                                    retry_decision['params']['modifications'] = self._extract_modifications_with_regex(user_input)
                                if not retry_decision['params'].get('modifications'):
                                    with self._llm_no_thinking():
                                        retry_decision['params']['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                                print(f"[REACT-execution] 重试单个修改: target_id={retry_decision['params']['target_id']}")
                                observation = await self._execute_tool(retry_decision)
                                for _tte in self._drain_tool_task_sse_buffer_list():
                                    yield _tte

                # 结构化纠错：modify 失败后 grep+补参并重试（早于 LLM correct_and_retry）
                if (
                    decision.get('tool') == 'modify'
                    and not observation.get('success')
                    and not observation.get('skipped')
                ):
                    observation, _rec_ev = await self._recover_modify_after_failure(
                        decision,
                        observation,
                        todo,
                        user_input,
                        result_context,
                        project_id,
                    )
                    for _ev in _rec_ev:
                        yield _ev

                # 自动修正（最多1次）
                if (
                    not observation.get('success')
                    and not observation.get('corrected')
                    and not observation.get('skipped')
                ):
                    yield {'event': 'retry', 'message': '执行失败，正在尝试自动修正...'}
                    observation = await self.correction_engine.correct_and_retry(
                        todo=todo,
                        action=decision,
                        observation=observation,
                        context=result_context,
                        available_tools=tools_info,
                        execute_fn=self._execute_tool
                    )
                    for _tte in self._drain_tool_task_sse_buffer_list():
                        yield _tte

                # Diff Review 闭环：基于“未采纳 pending + 当前 delta”统一推导新的 diff（以后端合并结果为准）
                if decision.get("tool") == "modify" and isinstance(observation, dict):
                    params = decision.get("params") or {}
                    # 批量修改
                    if observation.get("batch_modify") and isinstance(observation.get("batch_results"), list):
                        merged_batch = []
                        for br in observation.get("batch_results") or []:
                            if not isinstance(br, dict):
                                merged_batch.append(br)
                                continue
                            tgt = br.get("target") or observation.get("target") or params.get("target") or "badcase"
                            tid = br.get("target_id")
                            merged_diff, merged_mods = self._merge_with_pending(
                                tgt,
                                tid,
                                br.get("diff") or [],
                                br.get("modifications") or params.get("modifications") or {},
                            )
                            br["diff"] = merged_diff
                            br["modifications"] = merged_mods
                            # 同步到 result 里，避免前端读取 result.diff 时不一致
                            if isinstance(br.get("result"), dict):
                                br["result"]["diff"] = merged_diff
                                br["result"]["modifications"] = merged_mods
                            merged_batch.append(br)
                        observation["batch_results"] = merged_batch
                    else:
                        tgt = observation.get("target") or params.get("target") or "badcase"
                        tid = observation.get("target_id") or params.get("target_id")
                        if tid is not None:
                            merged_diff, merged_mods = self._merge_with_pending(
                                tgt,
                                tid,
                                observation.get("diff") or [],
                                observation.get("modifications") or params.get("modifications") or {},
                            )
                            observation["diff"] = merged_diff
                            observation["modifications"] = merged_mods
                
                _strict_fail = (os.getenv("REACT_STRICT_PLAN_FAIL", "1") or "1").strip().lower() not in (
                    "0",
                    "false",
                    "no",
                    "off",
                )
                _step_failed = bool(observation.get("skipped")) or (
                    observation.get("success") is False
                )
                if (
                    _strict_fail
                    and not _step_failed
                    and str(decision.get("tool") or "").lower() == "grep"
                    and isinstance(observation, dict)
                    and observation.get("success")
                    and _grep_observation_empty_lists(observation)
                ):
                    _step_failed = True
                    observation = dict(observation)
                    observation["success"] = False
                    observation.setdefault("error", "grep_empty_hits")
                _nl_obs = self._summarize_observation_nl(decision.get("tool"), observation)
                task_state["observations"].append({"step": i + 1, "tool": decision.get("tool"), "text": _nl_obs})
                if i < len(task_state["plan"]):
                    task_state["plan"][i]["status"] = "failed" if _step_failed else "complete"
                    task_state["plan"][i]["result"] = {
                        "success": (False if _step_failed else observation.get("success"))
                        if isinstance(observation, dict)
                        else None
                    }
                if (not skill_guided) and task_state.get("plan"):
                    yield {
                        "event": "plan_update",
                        "steps": _normalize_plan_rows_for_sse(task_state["plan"]),
                        "reason": "step_outcome",
                        "index": i,
                        "failed": _step_failed,
                    }
                yield {
                    "event": "observation",
                    "data": observation,
                    "summary_nl": _nl_obs,
                    "index": i,
                    "step_id": i + 1,
                    "tool": decision.get("tool"),
                }
                print(f"[REACT-execution] Observation: {observation}")  # 调试日志
                
                # 提取执行证据并发送
                evidence = EvidenceExtractor.extract_from_observation(
                    decision['tool'],
                    decision.get('params', {}),
                    observation
                )
                # 直接发送 evidence 对象给前端
                yield {'event': 'evidence', 'data': evidence}
                
                # 将 evidence 转换为 findings 用于后续分析
                evidence_findings = EvidenceExtractor.format_as_findings(evidence)
                findings.extend(evidence_findings)
                
                # 分析：流式 observe_prompt（或合并下一轮 <decision>）
                _perf_observe = os.getenv("PERF_LOG") == "1"
                _t_observe_pipe0 = time.perf_counter()
                _stream_observe_ms = 0.0
                _xml_parse_ms = 0.0
                _ui_summary_ms = 0.0
                _merged_observe_ui = False
                _merge_observe_stream_used = False

                _obs_pr = shrink_payload_for_observe_prompt(observation)
                _ctx_pr = shrink_payload_for_observe_prompt(result_context)

                analyze_response = ""
                _obs_fc_holder: List[Optional[Dict[str, Any]]] = []

                if not (analyze_response or "").strip():
                    _t_so = time.perf_counter()
                    _sink_o: List[str] = []
                    _use_merge_observe = (
                        use_react_merge_observe_decide() and not skill_guided
                    )
                    if _use_merge_observe:
                        _merge_observe_stream_used = True
                        analyze_prompt = self._wrap_prompt(
                            ReactPromptTemplates.observe_prompt_merge_next_decide(
                                todo,
                                decision,
                                _obs_pr,
                                _ctx_pr,
                                user_input,
                                todos,
                                i,
                            )
                        )
                        _og = self._stream_observe_merge_next_decide(
                            analyze_prompt,
                            step_index=i,
                            full_text_sink=_sink_o,
                        )
                    else:
                        analyze_prompt = self._wrap_prompt(
                            ReactPromptTemplates.observe_prompt(
                                todo, decision, _obs_pr, _ctx_pr
                            )
                        )
                        if prefer_fast_observe_stub(decision.get("tool"), observation):
                            _stub_xml = stub_observe_result_xml(_nl_obs)
                            _og = self._stream_observe_stub_quick(
                                _stub_xml,
                                step_index=i,
                                full_text_sink=_sink_o,
                            )
                            if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                                print(
                                    f"[REACT-observe] step={i} tool=modify "
                                    f"REACT_OBSERVE_FAST_STUB=1 skip observe_prompt LLM"
                                )
                        elif prefer_fast_observe_stub_grep(decision.get("tool"), observation):
                            _stub_xml = stub_observe_result_xml(_nl_obs)
                            _og = self._stream_observe_stub_quick(
                                _stub_xml,
                                step_index=i,
                                full_text_sink=_sink_o,
                            )
                            if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                                print(
                                    f"[REACT-observe] step={i} tool=grep "
                                    f"REACT_GREP_OBSERVE_FAST_STUB=1 skip observe_prompt LLM"
                                )
                        else:
                            if (
                                use_react_observe_fc()
                                and getattr(self.llm, "chat_completion_with_tools_stream", None)
                            ):
                                _og = self._iter_observe_fc_stream(
                                    analyze_prompt,
                                    step_index=i,
                                    full_text_sink=_sink_o,
                                    analysis_out=_obs_fc_holder,
                                )
                            else:
                                _og = self._stream_agent_observe_with_narrative(
                                    analyze_prompt,
                                    step_index=i,
                                    full_text_sink=_sink_o,
                                )
                    _parallel_ui = os.getenv("REACT_OBSERVE_UI_PARALLEL", "1") != "0"
                    if _parallel_ui:
                        _todos_ov_o = (
                            "\n".join(f"{j + 1}. {t}" for j, t in enumerate(todos))
                            if len(todos) >= 1
                            else ""
                        )
                        _use_ui_llm = use_react_observe_ui_llm() and not prefer_nl_observe_summary(
                            decision.get("tool"), observation
                        )
                        if _use_ui_llm:
                            _op_sum = self._wrap_prompt(
                                ReactPromptTemplates.ui_observe_summary_prompt(
                                    todo,
                                    str(decision.get('tool') or ''),
                                    _obs_pr,
                                    todos_overview=_todos_ov_o,
                                )
                            )
                            _ui_gen = self._stream_react_ui_text(
                                _op_sum, step_index=i, channel='decision_observe'
                            )
                        else:
                            _ui_gen = self._stream_decision_observe_from_nl(
                                _nl_obs, step_index=i
                            )
                        _timings_par: Dict[str, float] = {}
                        _header_ev = [
                            {
                                'event': 'react_ui_stream',
                                'channel': 'decision_observe',
                                'delta': react_observe_section_header(self._ui_locale),
                                'index': i,
                            }
                        ]
                        async for _oe in merge_observe_parallel_ui_first(
                            _og,
                            _ui_gen,
                            ui_lead=_header_ev,
                            timings_ms=_timings_par,
                        ):
                            yield _oe
                        analyze_response = _sink_o[0] if _sink_o else ""
                        _stream_observe_ms = float(_timings_par.get("observe_stream", 0.0))
                        _ui_summary_ms = float(_timings_par.get("ui_summary", 0.0))
                        _merged_observe_ui = True
                    else:
                        _oit = _og.__aiter__()
                        while True:
                            try:
                                _oe = await _oit.__anext__()
                                yield _oe
                            except StopAsyncIteration:
                                break
                        analyze_response = _sink_o[0] if _sink_o else ""
                        _stream_observe_ms = (time.perf_counter() - _t_so) * 1000.0

                if perf:
                    _t_round_bridge = time.perf_counter()
                yield {
                    "event": "phase_wait",
                    "kind": "result_xml_parse",
                    "active": True,
                    "index": i,
                    "message": react_phase_wait_message("result_xml_parse", self._ui_locale),
                }
                _t_xml = time.perf_counter()
                if _obs_fc_holder and _obs_fc_holder[0] is not None:
                    analysis = _obs_fc_holder[0]
                else:
                    analysis = parse_xml_findings(analyze_response)
                _xml_parse_ms = (time.perf_counter() - _t_xml) * 1000.0
                yield {
                    "event": "phase_wait",
                    "kind": "result_xml_parse",
                    "active": False,
                    "index": i,
                }
                if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                    print(
                        f"[REACT-planing] step={i} observe_done analyze_len={len(analyze_response)} "
                        f"findings={len(analysis.get('findings') or [])} "
                        f"context_keys={list((analysis.get('context_update') or {}).keys())}"
                    )

                if _merge_observe_stream_used and re.search(
                    r"<\s*decision\b", analyze_response or "", re.IGNORECASE
                ):
                    pending_next_decision = parse_xml_decision(analyze_response)
                    if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                        print(
                            f"[REACT-merge] step={i} pending_next_decision queued "
                            f"tool={pending_next_decision.get('tool')!r} "
                            f"execute={pending_next_decision.get('execute')!r}"
                        )

                # 面向用户：观察阶段说明（不展示原始 XML）；已与流式 observe 并发时跳过
                if not _merged_observe_ui:
                    try:
                        yield {
                            'event': 'react_ui_stream',
                            'channel': 'decision_observe',
                            'delta': react_observe_section_header(self._ui_locale),
                            'index': i,
                        }
                        _t_ui = time.perf_counter()
                        _use_ui_llm = use_react_observe_ui_llm() and not prefer_nl_observe_summary(
                            decision.get("tool"), observation
                        )
                        if _use_ui_llm:
                            _todos_ov_o = (
                                "\n".join(f"{j + 1}. {t}" for j, t in enumerate(todos))
                                if len(todos) >= 1
                                else ""
                            )
                            _op = self._wrap_prompt(
                                ReactPromptTemplates.ui_observe_summary_prompt(
                                    todo,
                                    str(decision.get('tool') or ''),
                                    _obs_pr,
                                    todos_overview=_todos_ov_o,
                                )
                            )
                            async for _ue in self._stream_react_ui_text(_op, step_index=i, channel='decision_observe'):
                                yield _ue
                        else:
                            async for _ue in self._stream_decision_observe_from_nl(
                                _nl_obs, step_index=i
                            ):
                                yield _ue
                        _ui_summary_ms = (time.perf_counter() - _t_ui) * 1000.0
                    except Exception as _uo_e:
                        print(f"[REACT-thought] observe summary stream failed: {_uo_e}")

                if perf and _t_round_bridge is not None:
                    print(
                        f"[PERF][round-bridge] step={i} observe_ui_collected→post_observe_block_ms="
                        f"{(time.perf_counter() - _t_round_bridge) * 1000:.1f}"
                    )

                if _perf_observe:
                    _tot = (time.perf_counter() - _t_observe_pipe0) * 1000.0
                    _tool_nm = str(decision.get("tool") or "")
                    print(
                        f"[PERF][observe] step={i} tool={_tool_nm!r} "
                        f"total_ms={_tot:.1f} "
                        f"stream_observe_ms={_stream_observe_ms:.1f} "
                        f"xml_parse_ms={_xml_parse_ms:.1f} "
                        f"ui_observe_summary_ms={_ui_summary_ms:.1f} "
                        f"analyze_chars={len(analyze_response or '')}"
                    )

                # 体验优化：observe 已结束但下一轮 decide 可能要等待（构造 prompt / FC 往返 / skill 优化等）。
                # 先进入“准备下一步”等待态，确保 2s 内前端必有可见状态而非沉默。
                try:
                    yield {
                        "event": "phase_wait",
                        "kind": "next_round_prepare",
                        "active": True,
                        "index": i,
                        "message": "正在准备下一步…" if not is_english_locale(self._ui_locale) else "Preparing next step…",
                    }
                    _prev_round_prepare_wait_idx = i
                except Exception:
                    pass

                # 更新状态
                if perf:
                    _t_ctx_slice = time.perf_counter()
                result_context.update(_scrub_grep_grounded_keys_from_context_update(analysis.get("context_update")))
                # 模型在 <context_update> 里可能臆造 badcase_list；必须以本轮 grep 工具返回为准覆盖
                if (
                    decision.get('tool') == 'grep'
                    and isinstance(observation, dict)
                    and observation.get('success')
                ):
                    try:
                        self._merge_grep_observation_into_context(
                            observation,
                            decision.get('params') or {},
                            result_context,
                        )
                    except Exception as _mg_e:
                        print(f"[REACT-execution] observe 后 merge_grep 覆盖 context 失败: {_mg_e}")

                # 兜底逻辑：如果 context 中没有 bug_list/badcase_list 但 observation 中有，自动添加。
                # grep 已成功且已写入 grep_result 时，列表已按 navigation 收敛，禁止再用全量 bug_location 覆盖，
                # 否则会出现「界面/导航 2 条、批量 modify 仍吃 3 条」。
                if decision['tool'] == 'grep' and isinstance(observation, dict):
                    _grep_merged_ok = bool(
                        observation.get('success')
                        and isinstance(result_context.get('grep_result'), dict)
                    )
                    if not _grep_merged_ok:
                        # 多种可能的数据位置
                        obs_data = observation.get('data', observation)
                        if not isinstance(obs_data, dict):
                            obs_data = {}

                        # Bug 列表 - 从多个可能的位置提取
                        if 'bug_list' not in result_context:
                            bug_location = obs_data.get('bug_location', []) or observation.get('bug_location', [])
                            if bug_location and isinstance(bug_location, list) and len(bug_location) > 0:
                                result_context['bug_list'] = bug_location
                                kw = result_context.get('_last_grep_keywords', '')
                                best = self._pick_best_match_from_list(bug_location, kw, 'title') if kw else (bug_location[0] if isinstance(bug_location[0], dict) else None)
                                result_context['first_bug_id'] = best.get('id') if isinstance(best, dict) else (bug_location[0].get('id') if isinstance(bug_location[0], dict) else None)
                                print(f"[REACT-execution] 自动将 bug_location 添加到 context: {len(bug_location)} 条")

                        # BadCase 列表 - 从多个可能的位置提取
                        if 'badcase_list' not in result_context:
                            badcase_analysis = obs_data.get('badcase_analysis', []) or observation.get('badcase_analysis', [])
                            if badcase_analysis and isinstance(badcase_analysis, list) and len(badcase_analysis) > 0:
                                # 提取为简化列表格式
                                badcase_list = []
                                for bc in badcase_analysis:
                                    if not isinstance(bc, dict):
                                        continue
                                    bc_id = bc.get('id')
                                    if bc_id is None:
                                        continue
                                    badcase_list.append({
                                        'id': bc_id,
                                        'title': bc.get('title', ''),
                                        'status': bc.get('status'),
                                        'plan_id': bc.get('plan_id')
                                    })

                                if badcase_list:
                                    result_context['badcase_list'] = badcase_list
                                    result_context['badcase_analysis'] = badcase_analysis
                                    kw = result_context.get('_last_grep_keywords', '')
                                    best = self._pick_best_match_from_list(badcase_list, kw, 'title') if kw else badcase_list[0]
                                    result_context['first_badcase_id'] = best.get('id')
                                    print(f"[REACT-execution] 自动将 badcase_list 添加到 context: {len(badcase_list)} 条")

                        if 'testcase_list' not in result_context:
                            testcase_location = obs_data.get('testcase_location', []) or observation.get('testcase_location', [])
                            if testcase_location and isinstance(testcase_location, list) and len(testcase_location) > 0:
                                testcase_list = [{'id': tc.get('id'), 'title': tc.get('title'), 'plan_id': tc.get('current_plan_id')} for tc in testcase_location if isinstance(tc, dict) and tc.get('id') is not None]
                                if testcase_list:
                                    result_context['testcase_list'] = testcase_list
                                    kw = result_context.get('_last_grep_keywords', '')
                                    best = self._pick_best_match_from_list(testcase_list, kw, 'title') if kw else testcase_list[0]
                                    result_context['first_testcase_id'] = best.get('id')
                                    print(f"[REACT-execution] 自动将 testcase_list 添加到 context: {len(testcase_list)} 条")

                    print(
                        f"[REACT-execution] Context 更新后: bug_list={len(result_context.get('bug_list', []))}条, "
                        f"badcase_list={len(result_context.get('badcase_list', []))}条, "
                        f"testcase_list={len(result_context.get('testcase_list', []))}条"
                    )
                
                if perf:
                    print(
                        f"[PERF][round-bridge] step={i} context_update_and_grep_merge_ms="
                        f"{(time.perf_counter() - _t_ctx_slice) * 1000:.1f}"
                    )

                if analysis.get('findings'):
                    findings.extend(analysis['findings'])
                    for f in analysis['findings']:
                        print(f"[REACT-execution] Finding: {f}")  # 调试日志
                        yield {'event': 'finding', 'data': f}
                
                steps.append({
                    'todo': todo,
                    'decision': decision,
                    'observation': observation,
                    'analysis': analysis
                })

                if use_react_incremental_running_summary():
                    try:
                        if _incr_merge_q is not None:
                            await _incr_merge_q.put(
                                (
                                    _incr_sum_state,
                                    i,
                                    str(decision.get("tool") or ""),
                                    # 动态轮次时生成有意义的描述
                                    str(todo or f"执行 {decision.get('tool', '工具')} 操作"),
                                    _nl_obs,
                                )
                            )
                            if perf:
                                print(
                                    f"[PERF][incr-sum] enqueue_async step={i} "
                                    f"qsize≈{_incr_merge_q.qsize()}"
                                )
                        else:
                            await self._merge_running_summary_incremental_silent(
                                _incr_sum_state,
                                step_index=i,
                                tool=str(decision.get("tool") or ""),
                                # 动态轮次时生成有意义的描述
                                todo=str(todo or f"执行 {decision.get('tool', '工具')} 操作"),
                                nl_obs=_nl_obs,
                            )
                    except Exception as _irs_ex:
                        print(f"[REACT] incremental running summary: {_irs_ex}")
                
                # 动态添加批量修改任务（仅当没有已有的modify任务时）
                if (not skill_guided) and decision['tool'] == 'grep':
                    # 批量修改待办：与 modify 主循环一致，按用户意图选表，避免 badcase 恒优先于测试用例
                    _ui_td = self._infer_modify_target(user_input, '')
                    if _ui_td == 'testcase' and result_context.get('testcase_list'):
                        target_list = result_context['testcase_list']
                        target_type = 'testcase'
                    elif _ui_td == 'bug' and result_context.get('bug_list'):
                        target_list = result_context['bug_list']
                        target_type = 'bug'
                    elif result_context.get('badcase_list'):
                        target_list = result_context['badcase_list']
                        target_type = 'badcase'
                    elif result_context.get('bug_list'):
                        target_list = result_context['bug_list']
                        target_type = 'bug'
                    elif result_context.get('testcase_list'):
                        target_list = result_context['testcase_list']
                        target_type = 'testcase'
                    else:
                        target_list = []
                        target_type = 'badcase'

                    if target_list and len(target_list) > 1:
                        target_list = self._constrain_modify_target_list_by_grep_navigation(
                            target_list,
                            target_type,
                            result_context,
                            trace_phase="planning",
                        )

                    # 检测用户是否有批量修改意图
                    modify_keywords = ['修改', '改成', '更新', '设为', '状态', '关闭', 'closed', 'resolved']
                    has_modify_intent = any(kw in user_input for kw in modify_keywords)
                    
                    # 检查是否已有 modify 任务（避免重复添加）
                    existing_modify_count = sum(1 for t in todos if 'modify' in t.lower())
                    
                    if has_modify_intent and target_list and len(target_list) > 1 and existing_modify_count == 0:
                        print(f"[REACT-planing] 检测到批量修改意图，{len(target_list)} 个 {target_type}，使用批量模式")
                        
                        # 只添加一个批量修改任务（后端会处理全部）
                        ids_str = ', '.join([str(item['id']) for item in target_list])
                        new_todo = f"使用 modify 工具批量修改 {len(target_list)} 个 {target_type} (ID: {ids_str}) 的状态"
                        todos.append(new_todo)
                        task_state["plan"].append(
                            {
                                "id": len(todos),
                                "name": new_todo[:2000],
                                "tool": None,
                                "params": {},
                                "status": "pending",
                                "result": None,
                            }
                        )
                        print(f"[REACT-planing] 添加批量修改任务: {new_todo}")
                        
                        # 通知前端任务列表已更新
                        yield {'event': 'todos', 'data': todos}
                        if len(todos) >= 1 and not _should_suppress_plan_ui(len(todos), None):
                            yield {
                                'event': 'plan',
                                'steps': react_plan_steps_payload(todos),
                                'overview_only': len(todos) >= 3,
                            }
                        yield {
                            'event': 'plan_update',
                            'steps': react_plan_steps_payload(todos),
                            'reason': 'grep_batch_modify',
                            **(
                                {'suppress_plan_ui': True}
                                if _should_suppress_plan_ui(len(todos), None)
                                else {}
                            ),
                        }
                
                if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                    print(
                        f"[REACT-planing] step={i} round_done success={observation.get('success')} "
                        f"skipped={observation.get('skipped')}"
                    )
                last_observation = observation
                last_analysis = analysis
                if len(todos) >= 1:
                    yield {
                        'event': 'step_status',
                        'index': i,
                        'step_id': i + 1,
                        'status': 'failed' if _step_failed else 'done',
                    }
                yield {'event': 'todo_end', 'index': i, 'step_id': i + 1}
                if perf and _t_round_bridge is not None:
                    print(
                        f"[PERF][round-bridge] step={i} observe_ui_collected→todo_end_ms="
                        f"{(time.perf_counter() - _t_round_bridge) * 1000:.1f}"
                    )
                if skill_guided:
                    dn = self._decide_next_step(task_state, observation, i, decision.get("tool"), len(todos))
                    if dn == "finish":
                        task_state["finished"] = True
                    elif dn == "adjust":
                        adj = await self._adjust_plan_skill(
                            task_state,
                            user_input,
                            todos,
                            step_index=i,
                            result_context=result_context,
                            project_id=project_id,
                        )
                        if adj is not None and skill_matched_ref is not None:
                            todos.clear()
                            todos.extend(adj)
                            task_state["plan"] = await self._build_structured_plan_rows(
                                todos,
                                user_input,
                                skill_guided=True,
                                skill_ref=skill_matched_ref,
                                fallback_workflow_tools=fallback_workflow_tools,
                            )
                            yield {
                                "event": "plan_update",
                                "steps": task_state["plan"],
                                "reason": "skill_adjust",
                                **(
                                    {"suppress_plan_ui": True}
                                    if _should_suppress_plan_ui(len(todos), None)
                                    else {}
                                ),
                            }
                            _max_rounds = max(_max_rounds, len(todos))
                        else:
                            print("[REACT-planing] adjust 占位：未生成新计划，继续下一步。")
                if _step_failed and (os.getenv("REACT_STOP_AFTER_STEP_FAIL", "1") or "1").strip().lower() not in (
                    "0",
                    "false",
                    "no",
                    "off",
                ):
                    _fail_hint = (
                        "该步骤执行失败或结果为空，已暂停自动推进。你可回复「重试」重试本步，或说明如何跳过/调整后续计划。"
                        if not is_english_locale(self._ui_locale)
                        else "This step failed or returned empty results; auto-advance is paused. Reply retry to retry, or describe how to skip or adjust."
                    )
                    yield {"event": "intent_clarification", "message": _fail_hint, "kind": "step_failed"}
                    task_state["finished"] = True
                    break
                
                # 非 skill_guided 模式：检查所有规划任务是否已完成
                if (not skill_guided) and len(todos) > 0:
                    _all_planned_done = all(
                        task_state["plan"][j].get("status") in ("complete", "done", "failed")
                        for j in range(min(len(todos), len(task_state["plan"])))
                    )
                    if _all_planned_done:
                        print(f"[REACT-planing] 所有 {len(todos)} 个规划任务已完成，退出主循环")
                        task_state["finished"] = True
                        break
                
                round_idx += 1

            # 主循环已结束：先收口后台静默运行总览，保证终局流式与 REPLACE_FINAL 读到最新 text
            await self._shutdown_incr_sum_background_worker(
                _incr_merge_q, _incr_worker_task
            )

            # 主循环已结束：立即发 finished，便于前端结束「处理中」占位；后续仍有 LLM 总结流式，勿与 done 混淆
            _duration_after_loop = time.time() - start_time
            yield {
                "event": "finished",
                "mode": task_state["mode"],
                "finished": True,
                "steps_count": len(steps),
                "duration": _duration_after_loop,
                "thinking_time": thinking_time,
                "observations": task_state["observations"][-50:],
                "plan_snapshot": [
                    {
                        "id": s.get("id"),
                        "name": (s.get("name") or "")[:200],
                        "tool": s.get("tool"),
                        "status": s.get("status"),
                    }
                    for s in (task_state.get("plan") or [])[:50]
                ],
            }

            if (
                use_react_incremental_running_summary()
                and (_incr_sum_state.get("text") or "").strip()
                and not use_react_incremental_running_summary_stream_sse()
            ):
                yield {"event": "unified_summary_loading", "active": True}
                _last_si = len(steps) - 1 if steps else 0
                try:
                    async for _rf in self._stream_running_summary_final_wire(
                        _incr_sum_state,
                        last_step_index=max(0, _last_si),
                    ):
                        yield _rf
                except Exception as _rf_e:
                    print(f"[REACT] running_summary final wire: {_rf_e}")
            elif (
                use_react_incremental_running_summary_stream_sse()
                and use_react_incremental_running_summary()
                and (_incr_sum_state.get("text") or "").strip()
            ):
                try:
                    _v = int(_incr_sum_state.get("version") or 0)
                except Exception:
                    _v = 0
                _last_si2 = len(steps) - 1 if steps else 0
                yield {
                    "event": "running_summary_done",
                    "full_text": str(_incr_sum_state["text"]).strip(),
                    "version": _v,
                    "index": max(0, _last_si2),
                }

            # 在结束前：可选「条目标注」LLM（额外一轮，较慢）；默认跳过，直接进入一段话统一总结
            summarized_findings = []
            _skip_bullets = os.getenv(
                "REACT_UNIFIED_SUMMARY_SKIP_BULLETS", "1"
            ).strip().lower() in ("1", "true", "yes", "on")
            if findings and not _skip_bullets:
                print(f"[REACT] 开始总结 {len(findings)} 条原始发现（条目标注 LLM）…")
                try:
                    _bullet_max = None
                    try:
                        _bm = int(
                            (os.getenv("REACT_FINDINGS_BULLET_MAX_TOKENS") or "384").strip()
                        )
                        if _bm > 0:
                            _bullet_max = _bm
                    except Exception:
                        pass
                    summary_prompt = react_findings_bulleted_summary_prompt(
                        self._ui_locale,
                        chr(10).join(f"{i + 1}. {f}" for i, f in enumerate(findings)),
                    )

                    _sink_s = []
                    _sg = self._stream_llm_prompt_collect(
                        summary_prompt,
                        stream_kind="summary",
                        full_text_sink=_sink_s,
                        content_only_max_tokens=_bullet_max,
                    )
                    _sit = _sg.__aiter__()
                    while True:
                        try:
                            _se = await _sit.__anext__()
                            yield _se
                        except StopAsyncIteration:
                            break
                    summary_response = _sink_s[0] if _sink_s else ""
                    summarized_findings = [
                        line.strip()
                        for line in summary_response.strip().split("\n")
                        if line.strip()
                    ]
                    print(f"[REACT] 条目标注完成: {len(summarized_findings)} 条")
                    yield {"event": "summary_stream_reset"}
                except Exception as e:
                    print(f"[REACT] 条目标注失败: {e}，回退原始发现")
                    summarized_findings = findings[:5]
            elif findings and _skip_bullets:
                print(
                    f"[REACT] 跳过条目标注（REACT_UNIFIED_SUMMARY_SKIP_BULLETS），"
                    f"原始发现 {len(findings)} 条 → 统一总结"
                )

            # 使用总结后的findings
            final_findings = summarized_findings if summarized_findings else findings
            # 兜底：若关键发现仍为空，从各步的 observation 中提取 summary，避免前端「关键发现」无内容
            if not final_findings and steps:
                for s in steps:
                    obs = s.get('observation') or {}
                    if not isinstance(obs, dict):
                        continue
                    summary = obs.get('summary')
                    if not summary and isinstance(obs.get('data'), dict):
                        summary = (obs['data'] or {}).get('summary')
                    if summary and isinstance(summary, str) and summary.strip():
                        summary = summary.strip()
                        if summary not in final_findings:
                            final_findings.append(summary)
            
            duration = time.time() - start_time
            # 大模型统一总结：一段话概括关键发现+执行统计（Cursor 式，供前端「耗时 Xs」下打字机展示）
            summary_text = ""
            _replace_final = (os.getenv("REACT_INCREMENTAL_SUMMARY_REPLACE_FINAL", "1") or "1").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            _use_running_as_final = (
                _replace_final
                and use_react_incremental_running_summary()
                and (_incr_sum_state.get("text") or "").strip()
            )
            if _use_running_as_final:
                summary_text = str(_incr_sum_state["text"]).strip()
                print("[REACT] 终局总结：沿用增量运行总览（已跳过统一总结 LLM）")
            else:
                try:
                    yield {"event": "unified_summary_loading", "active": True}
                    _none = "None" if is_english_locale(self._ui_locale) else "无"
                    _flines = chr(10).join(f"- {f}" for f in (final_findings[:8] or [_none]))
                    summary_prompt = react_unified_final_summary_prompt(
                        self._ui_locale, _flines, len(steps), duration
                    )
                    _sum_max = None
                    try:
                        _sm = int(
                            (os.getenv("REACT_UNIFIED_SUMMARY_MAX_TOKENS") or "512").strip()
                        )
                        if _sm > 0:
                            _sum_max = _sm
                    except Exception:
                        _sum_max = 512
                    _sink_u = []
                    _ug = self._stream_llm_prompt_collect(
                        summary_prompt,
                        stream_kind="summary",
                        full_text_sink=_sink_u,
                        content_only_max_tokens=_sum_max,
                    )
                    _uit = _ug.__aiter__()
                    while True:
                        try:
                            _ue = await _uit.__anext__()
                            yield _ue
                        except StopAsyncIteration:
                            break
                    summary_text = (_sink_u[0] if _sink_u else "").strip()
                    if summary_text:
                        print(f"[REACT] 统一总结: {summary_text[:80]}...")
                except Exception as e:
                    print(f"[REACT] 统一总结失败: {e}")
                    yield {"event": "unified_summary_loading", "active": False}
            
            yield {
                'event': 'done',
                'findings': final_findings,
                'steps_count': len(steps),
                'duration': duration,
                'thinking_time': thinking_time,
                'summary': summary_text
            }

        except Exception as e:
            _cancel_preloop_tasks()
            try:
                await self._shutdown_incr_sum_background_worker(
                    _incr_merge_q, _incr_worker_task
                )
            except Exception:
                pass
            yield {'event': 'error', 'message': str(e)}

    async def run_stream(
        self,
        user_input: str,
        project_id: int = None,
        plan_id: int = None,
        locale: Optional[str] = None,
        pending_diff_context: Optional[List[Dict[str, Any]]] = None,
        agent_session_id: Optional[str] = None,
        long_memory_prefetch: Optional[Dict[str, Any]] = None,
    ):
        """
        流式执行 ReAct（Skill 工具）。plan_id 为当前迭代计划 ID，传入则 grep 可只检索该计划下记录。
        内部仍用 ``event`` 字典；本方法在出口统一转为 SSE v1（``type`` + ``payload``），上层无需再映射。
        """
        # 三段式 XML 模式：委托给专用流式方法
        if _use_react_unified_xml():
            async for pkt in self._run_unified_xml_stream(
                user_input,
                project_id=project_id,
                plan_id=plan_id,
                locale=locale,
                pending_diff_context=pending_diff_context,
                agent_session_id=agent_session_id,
                long_memory_prefetch=long_memory_prefetch,
            ):
                yield pkt
            return
        
        _last_wire_phase: Optional[str] = None
        async for raw in self._run_stream_raw(
            user_input,
            project_id=project_id,
            plan_id=plan_id,
            locale=locale,
            pending_diff_context=pending_diff_context,
            agent_session_id=agent_session_id,
            long_memory_prefetch=long_memory_prefetch,
        ):
            if not isinstance(raw, dict):
                continue
            if is_wire_v1_packet(raw):
                pkts: List[Dict[str, Any]] = [raw]
            else:
                pkts = list(engine_dict_to_wire_packets(raw))
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

    async def _inject_long_memory_into_context(
        self,
        *,
        user_input: str,
        result_context: Dict[str, Any],
        project_id: int = None,
        plan_id: int = None,
        agent_session_id: Optional[str] = None,
    ) -> None:
        """
        在 ReAct context 注入长期记忆（ES 向量检索）。
        设计原则：
        - 不影响主流程：失败则静默降级为空
        - 体积可控：只注入短文本（long_memory_text）与少量条目摘要（long_memory_items）
        """
        try:
            from config import Config
            if not getattr(Config, "LONG_MEMORY_ENABLED", False):
                return
            # user_id 从上层 tool params 传入时才可靠；这里优先读取引擎字段
            user_id = getattr(self, "user_id", None) or getattr(self, "_user_id", None)
            if not user_id:
                return
            from memory.long_memory_manager import LongMemoryManager

            mgr = LongMemoryManager()
            ctx = mgr.retrieve_context(
                user_id=str(user_id),
                query=str(user_input or ""),
                project_id=str(project_id) if project_id is not None else None,
                plan_id=str(plan_id) if plan_id is not None else None,
                types=None,
            )
            items = ctx.get("long_memory_items") or []
            text = (ctx.get("long_memory_text") or "").strip()
            if items:
                result_context["long_memory_items"] = items
            if text:
                # 供提示词直接引用的短块
                result_context["long_memory_text"] = text
        except Exception:
            # 降级：不让记忆影响主链路
            return

    async def _run_unified_xml_stream(
        self,
        user_input: str,
        project_id: int = None,
        plan_id: int = None,
        locale: Optional[str] = None,
        pending_diff_context: Optional[List[Dict[str, Any]]] = None,
        agent_session_id: Optional[str] = None,
        long_memory_prefetch: Optional[Dict[str, Any]] = None,
    ):
        """
        三段式 XML 流式主循环：yield SSE 事件
        """
        print(f"\n[REACT-UNIFIED] ReAct Loop Start (三段式XML Stream)")
        print(f"[REACT-UNIFIED] Input: {user_input[:60]}...\n")
        self._ui_locale = normalize_locale(locale)
        self.project_id = project_id
        start_time = time.time()
        
        result = {
            'status': 'success',
            'steps': [],
            'context': {},
            'findings': [],
            'duration': 0,
            'error': None
        }
        
        try:
            # 注入长记忆
            if isinstance(long_memory_prefetch, dict) and long_memory_prefetch:
                _lmt = str(long_memory_prefetch.get("long_memory_text") or "").strip()
                if _lmt:
                    result["context"]["long_memory_text"] = _lmt
            
            # ===== STEP 1: THINK（生成 todos）=====
            print(f"[REACT-UNIFIED] STEP 1: THINK")
            tools_info = format_tools_for_prompt(self.tools)
            
            # 发送思考开始事件
            yield {"event": "agent_thought", "delta": "正在规划任务...", "index": 0}
            
            prompt = self._wrap_prompt(
                ReactPromptTemplates.think_prompt(
                    user_input,
                    tools_info,
                    result['context'],
                    [],
                )
            )
            
            # 流式收集 THINK 响应
            think_parts = []
            async for chunk in self._stream_llm_text(prompt):
                think_parts.append(chunk)
                yield {"event": "agent_thought", "delta": chunk, "index": 0}
            response = "".join(think_parts)
            todos = _cap_todos_for_speed(robust_parse_todos(response))
            
            if not todos:
                # 闲聊模式
                print(f"[REACT-UNIFIED] No todos, chat mode")
                yield {"event": "agent_thought", "delta": response, "index": 0}
                yield {"event": "done", "status": "success"}
                return
            
            print(f"[REACT-UNIFIED] Generated {len(todos)} Todos: {todos}\n")
            
            # 发送计划事件
            plan_steps = [{"id": i+1, "description": t, "status": "pending"} for i, t in enumerate(todos)]
            yield {"event": "plan", "steps": plan_steps}
            
            # ===== MAIN LOOP: 三段式决策 =====
            prev_observation = None
            prev_action = None
            max_rounds = 20
            
            for round_idx in range(max_rounds):
                print(f"[REACT-UNIFIED] ===== round {round_idx + 1}/{max_rounds} =====")
                
                # 发送步骤开始事件
                yield {"event": "todo_start", "index": round_idx, "todo": todos[0] if round_idx < len(todos) else ""}
                yield {"event": "agent_thought", "delta": "\n正在分析...", "index": round_idx}
                
                # 构建三段式 prompt
                unified_prompt = self._wrap_prompt(
                    ReactPromptTemplates.react_unified_prompt(
                        user_input=user_input,
                        available_tools=tools_info,
                        context=result['context'],
                        round_idx=round_idx,
                        prev_observation=prev_observation,
                        prev_action=prev_action,
                        todo=todos[0] if round_idx < len(todos) else "",
                    )
                )
                
                # 调用 LLM（流式）
                llm_parts = []
                async for chunk in self._stream_llm_text(unified_prompt):
                    llm_parts.append(chunk)
                    yield {"event": "agent_thought", "delta": chunk, "index": round_idx}
                llm_response = "".join(llm_parts)
                print(f"[REACT-UNIFIED] LLM response length: {len(llm_response)}")
                
                # 解析三段式响应
                parsed = parse_unified_response(llm_response)
                observation_text = parsed.get("observation", "")
                thinking_text = parsed.get("thinking", "")
                decision = parsed.get("decision", {})
                
                print(f"[REACT-UNIFIED] Decision: execute={decision.get('execute')}, tool={decision.get('tool')}")
                
                # 检查是否终止
                if not decision.get('execute') or not decision.get('tool'):
                    print(f"[REACT-UNIFIED] Task completed")
                    yield {"event": "agent_thought", "delta": "\n任务完成。", "index": round_idx}
                    break
                
                # 执行工具
                tool_name = decision.get('tool', '')
                tool_params = decision.get('params', {})
                
                # 确保 modify/create 的 confirm 默认为 False
                if tool_name in ('modify', 'create') and 'confirm' not in tool_params:
                    tool_params['confirm'] = False
                
                if tool_name == 'modify':
                    if not tool_params.get('target_id') and not tool_params.get('natural_query'):
                        tool_params['natural_query'] = user_input[:500]
                    if not tool_params.get('project_id'):
                        tool_params['project_id'] = project_id
                
                # 发送工具执行事件
                yield {"event": "tool_call", "tool": tool_name, "params": tool_params}
                print(f"[REACT-UNIFIED] Executing tool: {tool_name}")
                
                try:
                    observation = await self._execute_tool({
                        'tool': tool_name,
                        'params': tool_params
                    })
                except Exception as e:
                    print(f"[REACT-UNIFIED] Tool execution failed: {e}")
                    observation = {'success': False, 'error': str(e)}
                
                
                print(f"[REACT-UNIFIED] Observation result: success={observation.get('success')}")
                
                # 发送观察结果事件
                obs_summary = observation.get('summary', '') or observation.get('message', '') or ('成功' if observation.get('success') else '失败')
                yield {"event": "observation", "summary": obs_summary, "success": observation.get('success', False)}
                
                # 如果是 modify 预览，发送 diff 事件
                if tool_name == 'modify' and observation.get('success') and observation.get('batch_results'):
                    yield {
                        "event": "modify_preview",
                        "results": observation.get('batch_results', []),
                        "confirmation_required": observation.get('confirmation_required', False)
                    }
                
                
                # 保存观察结果供下一轮使用
                prev_observation = observation
                prev_action = {'tool': tool_name, 'params': tool_params}
                
                # 更新上下文
                if observation.get('success'):
                    for key in ['bug_list', 'badcase_list', 'testcase_list', 'grep_result']:
                        if key in observation:
                            result['context'][key] = observation[key]
                
                
                # modify 成功后终止
                if tool_name == 'modify' and observation.get('success'):
                    print(f"[REACT-UNIFIED] Modify completed successfully")
                    break
            
            
            # 发送完成事件
            yield {"event": "done", "status": "success"}
            
        except Exception as e:
            print(f"[REACT-UNIFIED] Error: {e}")
            yield {"event": "error", "message": str(e)}

    async def _run_unified_xml(
        self,
        user_input: str,
        project_id: int = None,
        locale: Optional[str] = None,
        long_memory_prefetch: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        三段式 XML 主循环：一次 LLM 输出 observation + thinking + decision
        适用于千帆等 FC 不稳定的模型。
        """
        print(f"\n[REACT-UNIFIED] ReAct Loop Start (三段式XML)")
        print(f"[REACT-UNIFIED] Input: {user_input[:60]}...\n")
        self._ui_locale = normalize_locale(locale)
        self.project_id = project_id
        start_time = time.time()
        
        result = {
            'status': 'success',
            'steps': [],
            'context': {},
            'findings': [],
            'duration': 0,
            'error': None
        }
        
        try:
            # 注入长记忆
            if isinstance(long_memory_prefetch, dict) and long_memory_prefetch:
                _lmt = str(long_memory_prefetch.get("long_memory_text") or "").strip()
                if _lmt:
                    result["context"]["long_memory_text"] = _lmt
            
            # ===== STEP 1: THINK（生成 todos）=====
            print(f"[REACT-UNIFIED] STEP 1: THINK")
            tools_info = format_tools_for_prompt(self.tools)
            prompt = self._wrap_prompt(
                ReactPromptTemplates.think_prompt(
                    user_input,
                    tools_info,
                    result['context'],
                    [],
                )
            )
            response = await self._collect_llm_text(prompt)
            todos = _cap_todos_for_speed(robust_parse_todos(response))
            
            if not todos:
                # 没有 todos 可能是闲聊
                print(f"[REACT-UNIFIED] No todos generated, treating as chat")
                result['status'] = 'success'
                result['chat_reply'] = response
                result['duration'] = time.time() - start_time
                return result
            
            print(f"[REACT-UNIFIED] Generated {len(todos)} Todos: {todos}\n")
            
            # ===== MAIN LOOP: 三段式决策 =====
            prev_observation = None
            prev_action = None
            max_rounds = 20
            
            for round_idx in range(max_rounds):
                print(f"[REACT-UNIFIED] ===== round {round_idx + 1}/{max_rounds} =====")
                
                # 构建三段式 prompt
                unified_prompt = self._wrap_prompt(
                    ReactPromptTemplates.react_unified_prompt(
                        user_input=user_input,
                        available_tools=tools_info,
                        context=result['context'],
                        round_idx=round_idx,
                        prev_observation=prev_observation,
                        prev_action=prev_action,
                        todo=todos[0] if round_idx < len(todos) else "",
                    )
                )
                
                # 调用 LLM
                llm_response = await self._collect_llm_text(unified_prompt)
                print(f"[REACT-UNIFIED] LLM response length: {len(llm_response)}")
                
                # 解析三段式响应
                parsed = parse_unified_response(llm_response)
                observation_text = parsed.get("observation", "")
                thinking_text = parsed.get("thinking", "")
                decision = parsed.get("decision", {})
                
                print(f"[REACT-UNIFIED] Observation: {observation_text[:100]}..." if observation_text else "[REACT-UNIFIED] No observation")
                print(f"[REACT-UNIFIED] Thinking: {thinking_text[:100]}..." if thinking_text else "[REACT-UNIFIED] No thinking")
                print(f"[REACT-UNIFIED] Decision: execute={decision.get('execute')}, tool={decision.get('tool')}")
                
                # 检查是否终止
                if not decision.get('execute') or not decision.get('tool'):
                    print(f"[REACT-UNIFIED] Task completed or chat reply")
                    result['chat_reply'] = thinking_text or llm_response
                    break
                
                # 执行工具
                tool_name = decision.get('tool', '')
                tool_params = decision.get('params', {})
                
                # 确保 modify/create 的 confirm 默认为 False
                if tool_name in ('modify', 'create') and 'confirm' not in tool_params:
                    tool_params['confirm'] = False
                
                
                if tool_name == 'modify':
                    # modify 参数补全逻辑
                    if not tool_params.get('target_id') and not tool_params.get('natural_query'):
                        tool_params['natural_query'] = user_input[:500]
                    if not tool_params.get('project_id'):
                        tool_params['project_id'] = project_id
                
                
                print(f"[REACT-UNIFIED] Executing tool: {tool_name}")
                
                try:
                    observation = await self._execute_tool({
                        'tool': tool_name,
                        'params': tool_params
                    })
                except Exception as e:
                    print(f"[REACT-UNIFIED] Tool execution failed: {e}")
                    observation = {'success': False, 'error': str(e)}
                
                
                print(f"[REACT-UNIFIED] Observation result: success={observation.get('success')}")
                
                # 保存观察结果供下一轮使用
                prev_observation = observation
                prev_action = {'tool': tool_name, 'params': tool_params}
                
                # 更新上下文
                if observation.get('success'):
                    # 提取关键信息到 context
                    for key in ['bug_list', 'badcase_list', 'testcase_list', 'grep_result']:
                        if key in observation:
                            result['context'][key] = observation[key]
                
                
                # 检查是否需要继续（任务是否完成）
                # 简单策略：modify 成功后终止
                if tool_name == 'modify' and observation.get('success'):
                    print(f"[REACT-UNIFIED] Modify completed successfully")
                    break
                
            
            result['duration'] = time.time() - start_time
            return result
            
        except Exception as e:
            print(f"[REACT-UNIFIED] Error: {e}")
            result['status'] = 'error'
            result['error'] = str(e)
            result['duration'] = time.time() - start_time
            return result

    async def run(
        self,
        user_input: str,
        project_id: int = None,
        locale: Optional[str] = None,
        long_memory_prefetch: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        极简主循环 - 三步：THINK / ACT-LOOP / RESULT
        """
        # 三段式 XML 模式：委托给专用方法
        if _use_react_unified_xml():
            return await self._run_unified_xml(
                user_input, project_id, locale, long_memory_prefetch
            )
        
        print(f"\n[REACT] ReAct Loop Start")
        print(f"[REACT] Input: {user_input[:60]}...\n")
        self._ui_locale = normalize_locale(locale)
        self.project_id = project_id  # 保存项目ID
        start_time = time.time()
        
        result = {
            'status': 'success',
            'steps': [],
            'context': {},
            'findings': [],
            'duration': 0,
            'error': None
        }
        
        try:
            _lm_each_msg = (os.getenv("REACT_LONG_MEMORY_QUERY_EACH_MESSAGE", "0") or "0").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if isinstance(long_memory_prefetch, dict) and long_memory_prefetch:
                _lmt = str(
                    long_memory_prefetch.get("long_memory_text")
                    or long_memory_prefetch.get("merged")
                    or ""
                ).strip()
                _lmi = long_memory_prefetch.get("long_memory_items") or long_memory_prefetch.get("memories")
                if _lmt:
                    result["context"]["long_memory_text"] = _lmt
                if isinstance(_lmi, list) and _lmi:
                    result["context"]["long_memory_items"] = _lmi
            elif _lm_each_msg:
                await self._inject_long_memory_into_context(
                    user_input=user_input,
                    result_context=result["context"],
                    project_id=project_id,
                    plan_id=None,
                    agent_session_id=None,
                )

            # ===== STEP 1: THINK =====
            print(f"[REACT] STEP 1: THINK - Claude Prompt")
            
            tools_info = format_tools_for_prompt(self.tools)
            prompt = self._wrap_prompt(
                ReactPromptTemplates.think_prompt(
                    user_input,
                    tools_info,
                    result['context'],
                    [],
                )
            )
            
            response = await self._collect_llm_text(prompt)
            # 统一使用健壮版解析
            todos = _cap_todos_for_speed(robust_parse_todos(response))
            
            if not todos:
                result['error'] = 'LLM 无法生成 Todo'
                result['status'] = 'error'
                return result
            
            print(f"[REACT]   Generated {len(todos)} Todos\n")
            
            # STREAM_V1 对齐：observe 合并 <decision> 时缓存，下一轮省一次 decide LLM
            pending_next_decision: Optional[Dict[str, Any]] = None
            _prev_tool_sync: Optional[str] = None

            # ===== MAIN LOOP: ACT =====
            print(f"[REACT] MAIN LOOP: Executing Todos\n")
            
            for i, todo in enumerate(todos):
                print(f"[REACT] Todo {i+1}/{len(todos)}: {todo}")
                
                # 决策（ACT）
                decision_response = ""
                if pending_next_decision is None:
                    _ctx_run_d = shrink_payload_for_decide_prompt(
                        result["context"], prev_tool=_prev_tool_sync
                    )
                    decision_prompt = self._wrap_prompt(
                        ReactPromptTemplates.decide_prompt(
                            todo,
                            user_input,
                            tools_info,
                            _ctx_run_d,
                        )
                    )
                    use_fc = use_react_decide_function_call() and hasattr(
                        self.llm, "chat_completion_with_tools"
                    )
                    if use_fc:
                        decision, decision_response = await self._react_decide_function_call(
                            decision_prompt,
                            step_index=i,
                            prev_tool=_prev_tool_sync,
                        )
                    else:
                        _mxdec = resolve_decide_max_tokens_for_prev_tool(
                            _prev_tool_sync
                        )
                        decision_response = await self._collect_llm_text_content_only(
                            decision_prompt, _mxdec
                        )
                        decision = parse_xml_decision(decision_response)
                else:
                    decision = pending_next_decision
                    pending_next_decision = None
                    try:
                        decision_response = json.dumps(
                            decision, ensure_ascii=False, default=str
                        )[:4000]
                    except Exception:
                        decision_response = ""
                    if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                        print(
                            f"[REACT-merge] (sync) step={i} pending_next_decision "
                            f"tool={decision.get('tool')!r} execute={decision.get('execute')!r}"
                        )
                _llm = getattr(self, "llm", None)
                print(
                    f"[REACT-planing] (sync) step={i} llm_class={type(_llm).__name__} "
                    f"llm_model={getattr(_llm, 'model', None)!r} "
                    f"parsed_tool={decision.get('tool')!r} execute={decision.get('execute')!r}"
                )
                
                if not decision['execute']:
                    print(f"[REACT]   Skip")
                    continue
                
                skip_modify_exec = False
                if decision.get('tool') == 'modify':
                    decision, _ = await self._enrich_modify_decision_for_main_loop(
                        decision, todo, user_input, result['context'], project_id, step_index=i
                    )
                    if not self._modify_params_ready(decision.get('params')):
                        decision, _ = await self._last_resort_modify_fill(
                            decision, todo, user_input, result['context'], project_id, step_index=i
                        )
                    if not self._modify_params_ready(decision.get('params')):
                        nq = (user_input or todo or '').strip()
                        if nq:
                            decision.setdefault('params', {})['natural_query'] = nq[:2000]
                    if not self._modify_params_ready(decision.get('params')):
                        skip_modify_exec = True
                        print("[REACT] stability_gate: modify 参数未就绪，跳过执行")

                # 执行工具
                print(f"[REACT]   Tool: {decision['tool']}")
                if skip_modify_exec:
                    observation = {
                        'success': False,
                        'skipped': True,
                        'stability_gate': 'modify_params_incomplete',
                        'error': '缺少必要参数：modify 需要 target_id（或 natural_query）与非空 modifications。',
                        'message': 'modify 未执行（参数未就绪）',
                    }
                else:
                    observation = await self._execute_tool(decision)
                    _ = self._drain_tool_task_sse_buffer_list()

                if (
                    decision.get('tool') == 'modify'
                    and not observation.get('success')
                    and not observation.get('skipped')
                ):
                    observation, _ = await self._recover_modify_after_failure(
                        decision,
                        observation,
                        todo,
                        user_input,
                        result['context'],
                        project_id,
                    )
                    _ = self._drain_tool_task_sse_buffer_list()

                # 自我修正：如果执行失败，尝试自动修正
                if not observation.get('success') and not observation.get('skipped'):
                    print(f"[REACT]   Execution failed, retrying with correction")
                    
                    tools_info = format_tools_for_prompt(self.tools)
                    observation = await self.correction_engine.correct_and_retry(
                        todo=todo,
                        action=decision,
                        observation=observation,
                        context=result['context'],
                        available_tools=tools_info,
                        execute_fn=self._execute_tool
                    )
                    _ = self._drain_tool_task_sse_buffer_list()
                
                # 分析结果（OBSERVE）：单轮 observe_prompt（可合并下一轮 <decision>）
                analyze_response = ""
                _merge_observe_used_run = False

                if not (analyze_response or "").strip():
                    _obs_sync = shrink_payload_for_observe_prompt(observation)
                    _ctx_sync2 = shrink_payload_for_observe_prompt(result["context"])
                    if use_react_merge_observe_decide():
                        _merge_observe_used_run = True
                        analyze_prompt = self._wrap_prompt(
                            ReactPromptTemplates.observe_prompt_merge_next_decide(
                                todo,
                                decision,
                                _obs_sync,
                                _ctx_sync2,
                                user_input,
                                todos,
                                i,
                            )
                        )
                        _mt_o = (
                            os.getenv("REACT_MERGE_OBSERVE_MAX_TOKENS")
                            or os.getenv("REACT_OBSERVE_MAX_TOKENS")
                            or ""
                        ).strip()
                    else:
                        analyze_prompt = self._wrap_prompt(
                            ReactPromptTemplates.observe_prompt(
                                todo,
                                decision,
                                _obs_sync,
                                _ctx_sync2,
                            )
                        )
                        _mt_o = (os.getenv("REACT_OBSERVE_MAX_TOKENS") or "").strip()
                    _max_ob = int(_mt_o) if _mt_o.isdigit() else None
                    if _max_ob is not None and _max_ob <= 0:
                        _max_ob = None
                    if (
                        use_react_observe_fc()
                        and not _merge_observe_used_run
                        and getattr(self.llm, "chat_completion_with_tools", None)
                    ):
                        analysis = await self._react_observe_fc_sync(analyze_prompt, _max_ob)
                        analyze_response = json.dumps(analysis, ensure_ascii=False)
                    else:
                        analyze_response = await self._collect_llm_text_content_only(
                            analyze_prompt, _max_ob
                        )
                        analysis = parse_xml_findings(analyze_response)
                else:
                    analysis = parse_xml_findings(analyze_response)
                if _merge_observe_used_run and re.search(
                    r"<\s*decision\b", analyze_response or "", re.IGNORECASE
                ):
                    pending_next_decision = parse_xml_decision(analyze_response)
                    if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                        print(
                            f"[REACT-merge] (sync) step={i} pending_next_decision queued "
                            f"tool={pending_next_decision.get('tool')!r} "
                            f"execute={pending_next_decision.get('execute')!r}"
                        )
                
                # 记录
                result['steps'].append({
                    'todo': todo,
                    'decision': decision,
                    'observation': observation,
                    'analysis': analysis
                })
                _tps = str(decision.get("tool") or "").strip().lower()
                _prev_tool_sync = _tps if _tps else None

                # 更新上下文（与流式主循环一致：勿让 observe 覆盖 grep 写入的定位列表）
                result["context"].update(
                    _scrub_grep_grounded_keys_from_context_update(analysis.get("context_update"))
                )
                
                # 提取发现
                if analysis.get('findings'):
                    result['findings'].extend(analysis['findings'])
                    for f in analysis['findings']:
                        print(f"[REACT]   Found: {f}")
        
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            print(f"[REACT] Error: {str(e)}")
        
        result['duration'] = time.time() - start_time
        print(f"\n[REACT] Done | Steps: {len(result['steps'])} | Findings: {len(result['findings'])} | Duration: {result['duration']:.2f}s\n")
        return result
    
    async def _optimize_with_skill_tool(self, decision: Dict[str, Any], user_input: str, context: Dict[str, Any], project_id: int = None) -> Dict[str, Any]:
        """
        使用Skill工具优化决策
        当检测到复杂任务时，建议使用skill_executor工具
        """
        tool_name = decision['tool']
        
        # 识别需要Skill处理的复杂任务
        complex_task_keywords = [
            '修改缺陷', '创建缺陷', '查询缺陷',
            '修改badcase', '创建badcase', '查询badcase',
            '批量处理', '多步骤操作', '完整流程'
        ]
        
        #检查是否为复杂任务
        is_complex_task = any(keyword in user_input.lower() or keyword in decision.get('reason', '').lower() 
                            for keyword in complex_task_keywords)
        
        if is_complex_task and tool_name in ['grep', 'modify', 'create']:
            print(f"[REACT-planing] 🎯检测到复杂任务，建议使用Skill工具优化")
            
            # 重定向到skill_executor工具
            return {
                'execute': True,
                'tool': 'skill_executor',
                'params': {
                    'user_input': user_input,
                    'context': context,
                    'project_id': project_id
                },
                'reason': f'检测到复杂任务"{user_input}"，使用Skill工具进行智能处理'
            }
        
        # Text2SQL优化：数据库查询优先使用自然语言
        if tool_name == 'database_query':
            natural_query = self._extract_natural_query(user_input, user_input)
            if natural_query and self.text2sql_tool is None:
                self.text2sql_tool = get_text2sql_tool("instance/badcase_doctor.db")
            if natural_query and self.text2sql_tool:
                print(f"[REACT-planing]📊优先使用 Text2SQL执行: {natural_query}")
                decision['params']['natural_query'] = natural_query
        
        return decision
    
    def _generate_todos_from_skill_workflow(self, skill: Skill, user_input: str) -> List[str]:
        """根据技能工作流生成 Todo列表（按 step 排序，与 fallback_workflow_tools 一致）"""
        todos = []
        wf = sorted(getattr(skill, 'workflow', []) or [], key=lambda s: getattr(s, 'step', 0))
        for workflow_step in wf:
            # 生成人性化的 Todo描述
            if workflow_step.description and workflow_step.description != workflow_step.tool:
                todo_desc = workflow_step.description
            else:
                # 使用默认描述
                todo_desc = f"执行 {workflow_step.tool} 操作"
            
            todos.append(todo_desc)
        
        return todos
    
    async def _execute_tool_with_text2sql(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """使用 Text2SQL执行数据库工具"""
        if tool_name == 'database_query' and self.text2sql_tool is None:
            self.text2sql_tool = get_text2sql_tool("instance/badcase_doctor.db")
        if tool_name == 'database_query' and self.text2sql_tool:
            natural_query = params.get('natural_query')
            if natural_query:
                print(f"[REACT] Text2SQL执行: {natural_query}")
                return self.text2sql_tool.query(natural_query, params)
        
        # 回到传统工具执行
        return await self._execute_tool(
            {"execute": True, "tool": tool_name, "params": params}
        )
    
    def _extract_natural_query(self, todo: str, user_input: str) -> str:
        """从 Todo中提取自然语言查询"""
        # 关键词匹配
        query_keywords = ['查询', '搜索', '查找', '显示', '列出', '统计']
        
        for keyword in query_keywords:
            if keyword in todo or keyword in user_input:
                #构造自然语言查询
                if '登录' in todo or '登录' in user_input:
                    return "查询登录相关的缺陷"
                elif '未解决' in todo or '未解决' in user_input:
                    return "查询所有未解决的缺陷"
                elif '统计' in todo or '统计' in user_input:
                    return "统计缺陷数量"
                else:
                    return user_input  # 使用原始用户输入
        
        return ""

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
        kw = (params.get('keywords') or result_context.get('_last_grep_keywords') or '')
        result_context['_last_grep_keywords'] = kw or params.get('keywords') or ''
        _gtt = str(params.get('target') or '').strip().lower()
        if _gtt:
            result_context['_last_grep_target'] = _gtt

        # 优先使用 grep_tool 生成的 navigation（它已按计划/权限/可跳转过滤），避免后续 modify 误选到列表里“碰巧更像”的其它记录
        nav_ids: Dict[str, List[int]] = {"bug": [], "badcase": [], "testcase": []}
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
            f"testcase={nav_ids['testcase']} (n={len(nav_ids['testcase'])}); "
            f"raw_location_counts: badcase_analysis={len(badcase_list)}, bug_location={len(bug_list)}, "
            f"testcase_location={len(testcase_list)}; has_navigation={has_nav}"
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
            return [x for x in (lst or []) if isinstance(x, dict) and x.get("id") in idset]

        badcase_list_nav = _restrict_by_nav(badcase_list, nav_ids.get("badcase") or [])
        bug_list_nav = _restrict_by_nav(bug_list, nav_ids.get("bug") or [])
        testcase_list_nav = _restrict_by_nav(testcase_list, nav_ids.get("testcase") or [])

        result_context['grep_result'] = {
            'first_badcase_id': first_id(badcase_list_nav, kw),
            'first_bug_id': first_id(bug_list_nav, kw),
            'first_testcase_id': first_id(testcase_list_nav, kw),
            'badcase_list': badcase_list_nav,
            'bug_list': bug_list_nav,
            'testcase_list': testcase_list_nav,
            'navigation_ids': nav_ids,
        }
        result_context['badcase_list'] = badcase_list_nav
        result_context['bug_list'] = bug_list_nav
        result_context['testcase_list'] = testcase_list_nav
        print(
            f"[REACT-execution] grep 结果: {len(badcase_list)} badcase, {len(bug_list)} bug, {len(testcase_list)} testcase"
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

    async def _enrich_modify_decision_for_main_loop(
        self,
        decision: Dict[str, Any],
        todo: str,
        user_input: str,
        result_context: Dict[str, Any],
        project_id: Optional[int],
        step_index: int,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        主循环（未走技能匹配分支）在解析 LLM 的 decide 结果后，补齐 modify 的 target_id / modifications。

        **可靠性口径**：真正执行 modify_tool 以前，以本函数补全/合并后的 params 为准；
        parse_xml_decision 仅提供 tool 选择与「有则更好」的初值，模型常省略参数，属预期行为。

        与技能分支内逻辑对齐：grep 上下文 → 必要时补救 grep → explore_record + LLM 提取 modifications
        → 正则兜底 → _infer_modify_params 合并。
        """
        events: List[Dict[str, Any]] = []
        params = decision.setdefault('params', {})
        if not isinstance(params, dict):
            params = {}
            decision['params'] = params
        if project_id is not None and 'project_id' not in params:
            params['project_id'] = project_id
        if 'userId' not in params:
            params['userId'] = 'system_agent'
        params.setdefault('confirm', False)

        grep_result = result_context.get('grep_result', {})
        tc_l = result_context.get('testcase_list') or []
        bc_l = result_context.get('badcase_list') or []
        bg_l = result_context.get('bug_list') or []
        explicit = self._infer_modify_target_explicit(user_input, todo)
        user_infer = self._infer_modify_target(user_input, todo)
        if explicit:
            target_type = explicit
        else:
            target_type = str(params.get('target') or '').strip().lower() or user_infer
        if tc_l and not bc_l and not bg_l:
            target_type = 'testcase'
        elif bc_l and not tc_l and not bg_l:
            target_type = 'badcase'
        elif bg_l and not tc_l and not bc_l:
            target_type = 'bug'
        _lgt = str(result_context.get('_last_grep_target') or '').lower()
        if _lgt == 'testcase' and tc_l:
            target_type = 'testcase'
        elif _lgt == 'badcase' and bc_l:
            target_type = 'badcase'
        elif _lgt == 'bug' and bg_l:
            target_type = 'bug'
        params['target'] = target_type
        # modify_tool 会优先使用 target_ids 做批量；模型常臆造 badcase id 列表，必须清掉由下方/grep 重填
        params.pop('target_ids', None)

        target_id = params.get('target_id')
        if target_id is not None:
            try:
                target_id = int(target_id)
                params['target_id'] = target_id
            except (TypeError, ValueError):
                params.pop('target_id', None)
                target_id = None

        _ctx_rows = bg_l if target_type == 'bug' else tc_l if target_type == 'testcase' else bc_l
        if target_id is not None and _ctx_rows:
            _ok = False
            for x in _ctx_rows:
                if not isinstance(x, dict) or x.get('id') is None:
                    continue
                try:
                    if int(x.get('id')) == int(target_id):
                        _ok = True
                        break
                except (TypeError, ValueError):
                    continue
            if not _ok:
                print(
                    f"[REACT-planing] enrich 丢弃与 {target_type} 候选列表不一致的 target_id={target_id}（避免串表）"
                )
                params.pop('target_id', None)
                target_id = None

        if not target_id:
            if target_type == 'bug':
                target_id = grep_result.get('first_bug_id') or result_context.get('first_bug_id')
            elif target_type == 'testcase':
                target_id = grep_result.get('first_testcase_id') or result_context.get('first_testcase_id')
            else:
                target_id = grep_result.get('first_badcase_id') or result_context.get('first_badcase_id')
            if target_id is not None:
                try:
                    params['target_id'] = int(target_id)
                    target_id = params['target_id']
                except (TypeError, ValueError):
                    target_id = None

        if not params.get('target_id'):
            tid_m = self._try_target_id_from_merged_lists(
                result_context, target_type, user_input, todo
            )
            if tid_m is not None:
                params['target_id'] = tid_m
                print(f"[REACT-planing] enrich 从合并列表注入 target_id={tid_m} ({target_type})")

        if not params.get('target_id'):
            print(
                f"[REACT-thought] ⚠️ 主循环 modify：无法从上下文获取 target_id (target={target_type})，尝试补救 grep…"
            )
            kw = self._extract_title_keywords_for_grep(user_input, todo) or ''
            gparams: Dict[str, Any] = {
                'project_id': project_id,
                'keywords': kw,
                'mode': 'locate',
                'target': target_type if target_type in ('bug', 'badcase', 'testcase') else 'all',
                'userId': 'system_agent',
            }
            if self.plan_id is not None and gparams.get('target') != 'all':
                gparams['plan_id'] = self.plan_id
            if gparams.get('target') == 'all':
                gparams.pop('plan_id', None)
            events.append(
                {
                    'event': 'executing',
                    'tool': 'grep',
                    'reason': f'Todo步骤 {step_index + 1}',
                    'index': step_index,
                    'message': '正在补充定位记录（用于修改）…',
                }
            )
            grep_obs = await self._execute_tool({'execute': True, 'tool': 'grep', 'params': gparams})
            events.extend(self._drain_tool_task_sse_buffer_list())
            if grep_obs.get('success'):
                self._merge_grep_observation_into_context(grep_obs, gparams, result_context)
                grep_result = result_context.get('grep_result', {})
                if target_type == 'bug':
                    target_id = grep_result.get('first_bug_id')
                elif target_type == 'testcase':
                    target_id = grep_result.get('first_testcase_id')
                else:
                    target_id = grep_result.get('first_badcase_id')
                if target_id is not None:
                    try:
                        params['target_id'] = int(target_id)
                        print(f"[REACT-execution] 主循环补救 grep 后 target_id={params['target_id']}")
                    except (TypeError, ValueError):
                        pass
            if not params.get('target_id'):
                tid2 = self._try_target_id_from_merged_lists(
                    result_context, target_type, user_input, todo
                )
                if tid2 is not None:
                    params['target_id'] = tid2
                    print(f"[REACT-planing] enrich 补救 grep 后从列表注入 target_id={tid2}")

        tid = params.get('target_id')
        mods = params.get('modifications')
        _proj_for_explore = params.get('project_id') or self.project_id
        if tid and (not mods or (isinstance(mods, dict) and len(mods) == 0)):
            modify_tool = self.tools.get('modify')
            if modify_tool and getattr(modify_tool, 'explore_record', None) and _proj_for_explore is not None:
                try:
                    loop = asyncio.get_event_loop()
                    _eid = int(tid)
                    _epid = int(_proj_for_explore)
                    exploration = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._tool_executor,
                            lambda: modify_tool.explore_record(
                                target_type, _eid, _epid, getattr(self, "_ui_locale", None)
                            ),
                        ),
                        timeout=15,
                    )
                    if exploration and exploration.get('current_record'):
                        with self._llm_no_thinking():
                            params['modifications'] = await self._extract_modifications_with_llm(
                                todo, user_input, exploration=exploration
                            )
                        if not params.get('modifications') and user_input:
                            params['modifications'] = self._extract_modifications_with_regex(user_input)
                except Exception as e:
                    print(f"[REACT-execution] 主循环 explore_record 失败: {e}")
                    if not params.get('modifications'):
                        with self._llm_no_thinking():
                            params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                        if not params.get('modifications'):
                            params['modifications'] = self._extract_modifications_with_regex(user_input)
            elif not params.get('modifications'):
                with self._llm_no_thinking():
                    params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                if not params.get('modifications'):
                    params['modifications'] = self._extract_modifications_with_regex(user_input)

        if (not params.get('target_id')) or (not params.get('modifications')):
            infer = self._infer_modify_params(todo, result_context)
            if infer.get('execute') and isinstance(infer.get('params'), dict):
                ip = infer['params']
                for k in ('target_id', 'target', 'modifications', 'project_id', 'confirm'):
                    if k not in params or params.get(k) in (None, '', {}):
                        v = ip.get(k)
                        if v is not None and v != '' and v != {}:
                            params[k] = v
                print(f"[REACT-execution] 主循环 modify 已合并 _infer_modify_params 兜底: keys={list(params.keys())}")

        return decision, events

    @staticmethod
    def _modify_params_ready(params: Optional[Dict[str, Any]]) -> bool:
        """
        modify 执行前需：非空 modifications，且满足其一：
        - 已有 target_id；或
        - 提供 natural_query（交给 modify_tool 用 Text2SQL/ORM 解析 id）
        """
        if not params or not isinstance(params, dict):
            return False
        m = params.get('modifications')
        if not m or not isinstance(m, dict) or len(m) == 0:
            return False
        if params.get('target_id') not in (None, ''):
            return True
        nq = (params.get('natural_query') or '').strip()
        return bool(nq)

    async def _last_resort_modify_fill(
        self,
        decision: Dict[str, Any],
        todo: str,
        user_input: str,
        result_context: Dict[str, Any],
        project_id: Optional[int],
        step_index: int,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        最后手段：全库/宽关键词 grep → 合并列表 → 按 bug/testcase/badcase 顺序取 id → 正则+LLM 补 modifications。
        用于主循环 enrich 与单条注入后仍缺参的情况。
        """
        events: List[Dict[str, Any]] = []
        params = decision.setdefault('params', {})
        if not isinstance(params, dict):
            params = {}
            decision['params'] = params
        kw = (self._extract_title_keywords_for_grep(user_input, todo) or '').strip()
        if not kw and user_input:
            kw = (user_input[:200] or '').strip()
        if not kw and todo:
            kw = (todo[:200] or '').strip()
        if not kw:
            kw = ' '

        gparams: Dict[str, Any] = {
            'project_id': project_id,
            'keywords': kw,
            'mode': 'locate',
            'target': 'all',
            'userId': 'system_agent',
        }
        events.append(
            {
                'event': 'executing',
                'tool': 'grep',
                'reason': f'Todo步骤 {step_index + 1}',
                'index': step_index,
                'message': '最后手段：全库检索以定位修改目标…',
            }
        )
        grep_obs = await self._execute_tool({'execute': True, 'tool': 'grep', 'params': gparams})
        events.extend(self._drain_tool_task_sse_buffer_list())
        if grep_obs.get('success'):
            self._merge_grep_observation_into_context(grep_obs, gparams, result_context)
            for tt in ('bug', 'testcase', 'badcase'):
                tid = self._try_target_id_from_merged_lists(
                    result_context, tt, user_input, todo
                )
                if tid is not None:
                    params['target_id'] = tid
                    params['target'] = tt
                    print(f"[REACT-planing] last_resort 从列表选定 target_id={tid}, target={tt}")
                    break
        if not params.get('modifications') or (
            isinstance(params.get('modifications'), dict) and len(params.get('modifications')) == 0
        ):
            params['modifications'] = self._extract_modifications_with_regex(user_input or '')
            if not params.get('modifications'):
                with self._llm_no_thinking():
                    params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
            if not params.get('modifications'):
                params['modifications'] = self._extract_modifications_with_regex(todo or '')
        return decision, events

    async def _recover_modify_after_failure(
        self,
        decision: Dict[str, Any],
        observation: Dict[str, Any],
        todo: str,
        user_input: str,
        result_context: Dict[str, Any],
        project_id: Optional[int],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        modify 失败后的结构化纠错（在 LLM correct_and_retry 之前）：
        缺参 / need_grep_first 时：全库 grep + 列表 + 补 modifications → 再执行一次 modify。
        返回 (observation, 需在主循环中 yield 的事件列表)。
        """
        empty_ev: List[Dict[str, Any]] = []
        if observation.get('success'):
            return observation, empty_ev
        if decision.get('tool') != 'modify':
            return observation, empty_ev
        if observation.get('corrected'):
            return observation, empty_ev
        err = str(observation.get('error') or '')
        need = observation.get('need_grep_first') or '缺少必要参数' in err or 'target_id' in err.lower()
        if not need:
            return observation, empty_ev
        if self._modify_params_ready(decision.get('params')):
            # 参数已齐仍失败，交给上层修正
            return observation, empty_ev
        print(f"[REACT-planing] 🛠 结构化纠错：modify 失败后尝试 grep+补参并重试")
        try:
            decision2 = {
                'execute': True,
                'tool': 'modify',
                'params': dict(decision.get('params') or {}),
            }
            decision2, ev = await self._last_resort_modify_fill(
                decision2,
                todo,
                user_input,
                result_context,
                project_id,
                step_index=-1,
            )
            if not self._modify_params_ready(decision2.get('params')):
                nq = (user_input or todo or '').strip()
                if nq:
                    decision2.setdefault('params', {})['natural_query'] = nq[:2000]
            if not self._modify_params_ready(decision2.get('params')):
                return observation, ev
            retry_obs = await self._execute_tool(decision2)
            ev.extend(self._drain_tool_task_sse_buffer_list())
            if retry_obs.get('success'):
                retry_obs['recovered'] = True
                retry_obs['recovery'] = 'structured_grep_after_failure'
            return retry_obs, ev
        except Exception as e:
            print(f"[REACT-planing] 结构化纠错异常: {e}")
            return observation, empty_ev

    def _try_target_id_from_merged_lists(
        self,
        result_context: Dict[str, Any],
        target_type: str,
        user_input: str,
        todo: str,
    ) -> Optional[int]:
        """
        grep_result.first_bug_id 等可能为空，但 _merge_grep_observation_into_context 已写入
        bug_list/badcase_list/testcase_list 时，从列表 rerank 取一条 id。
        """
        kw = self._extract_title_keywords_for_grep(user_input, todo) or ''
        if target_type == 'bug':
            lst = result_context.get('bug_list') or []
        elif target_type == 'testcase':
            lst = result_context.get('testcase_list') or []
        else:
            lst = result_context.get('badcase_list') or []
        if not lst:
            return None
        pick = self._pick_best_match_from_list(lst, kw, 'title') if kw else lst[0]
        if not isinstance(pick, dict):
            return None
        tid = pick.get('id')
        if tid is None:
            return None
        try:
            return int(tid)
        except (TypeError, ValueError):
            return None

    def _pick_best_match_from_list(self, items: List[Dict], keywords: str, key_title: str = 'title') -> Dict:
        """Rerank 后取分最高的那一条（兼容旧调用）。"""
        picked = self._rerank_and_pick(items, keywords, key_title, top_k=1)
        return picked[0] if picked else {}

    def _constrain_modify_target_list_by_grep_navigation(
        self,
        target_list: List[Dict],
        target_type: str,
        result_context: Dict[str, Any],
        *,
        trace_phase: str = "batch",
    ) -> List[Dict]:
        """当 grep 已写入 navigation_ids 时，批量 modify 仅保留这些 id，与列表可跳转条数一致。"""
        if not target_list or len(target_list) <= 1:
            return target_list
        merge_after_ids = [
            x.get("id")
            for x in target_list
            if isinstance(x, dict) and x.get("id") is not None
        ]
        _gr_nav = result_context.get("grep_result") or {}
        _nav_map = _gr_nav.get("navigation_ids") or {}
        _nk = (
            "bug"
            if target_type == "bug"
            else ("badcase" if target_type == "badcase" else "testcase")
        )
        nav_authoritative_ids = list(_nav_map.get(_nk) or [])
        _allowed_ids = nav_authoritative_ids
        if not _allowed_ids:
            print(
                f"[MODIFY-TRACE] WARNING phase={trace_phase} target_type={_nk} "
                f"grep navigation_ids[{_nk}] empty; merge_after_ids={merge_after_ids} "
                f"final_target_ids={merge_after_ids} (no nav constrain, fallback)"
            )
            return target_list
        _aset = set()
        for _aid in _allowed_ids:
            try:
                _aset.add(int(_aid))
            except (TypeError, ValueError):
                if _aid is not None:
                    _aset.add(_aid)
        _fil: List[Dict] = []
        for x in target_list:
            if not isinstance(x, dict):
                continue
            rid = x.get("id")
            if rid is None:
                continue
            try:
                match = int(rid) in _aset
            except (TypeError, ValueError):
                match = rid in _aset
            if match:
                _fil.append(x)
        if not _fil:
            print(
                f"[MODIFY-TRACE] ERROR phase={trace_phase} target_type={_nk} "
                f"merge_after_ids={merge_after_ids} nav_authoritative_ids={nav_authoritative_ids} "
                f"intersection empty; keeping target_list unchanged (check mod_target vs grep context)"
            )
            return target_list
        final_target_ids = [
            x.get("id")
            for x in _fil
            if isinstance(x, dict) and x.get("id") is not None
        ]
        try:
            _ma = set(merge_after_ids)
            _fi = set(final_target_ids)
            if _ma != _fi:
                print(
                    f"[MODIFY-TRACE] WARNING phase={trace_phase} target_type={_nk} "
                    f"narrowed merge_after_ids={merge_after_ids} -> final_target_ids={final_target_ids} "
                    f"nav_authoritative_ids={nav_authoritative_ids}"
                )
            else:
                print(
                    f"[MODIFY-TRACE] phase={trace_phase} target_type={_nk} "
                    f"merge_after_ids={merge_after_ids} final_target_ids={final_target_ids} "
                    f"nav_authoritative_ids={nav_authoritative_ids} (aligned)"
                )
        except Exception as _ex:
            print(f"[MODIFY-TRACE] trace log failed: {_ex}")
        return _fil

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
        if ('bug' in text or '缺陷' in text_raw) and 'badcase' not in text and 'bad case' not in text:
            return 'bug'
        if 'badcase' in text or 'bad case' in text:
            return 'badcase'
        return None

    def _infer_modify_target(self, user_input: str, todo: str) -> str:
        """
        从用户输入/todo 推断 modify 的 target：用户说「修改bug」则用 bug，避免误改 BadCase。
        """
        exp = self._infer_modify_target_explicit(user_input, todo)
        if exp:
            return exp
        text = ((user_input or '') + ' ' + (todo or '')).lower()
        if not text.strip():
            return 'badcase'
        if 'bug' in text and 'badcase' not in text and 'bad case' not in text:
            return 'bug'
        if '测试用例' in text or 'testcase' in text or 'test_case' in text:
            return 'testcase'
        if 'badcase' in text or 'bad case' in text:
            return 'badcase'
        return 'badcase'

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

    def _infer_create_target(self, user_input: str, todo: str) -> str:
        text = f"{todo or ''} {user_input or ''}"
        text_lower = text.lower()
        if 'testcase' in text_lower or 'test_case' in text_lower or '测试用例' in text:
            return 'testcase'
        if 'plan' in text_lower or '计划' in text or '迭代' in text:
            return 'plan'
        if 'bug' in text_lower or '缺陷' in text:
            return 'bug'
        if 'badcase' in text_lower or 'bad case' in text_lower or 'BadCase' in text:
            return 'badcase'
        return 'bug'

    def _extract_create_title(self, user_input: str, todo: str) -> str:
        import re

        for text in (todo or '', user_input or ''):
            if not text:
                continue
            patterns = [
                r'标题\s*[=:：]\s*[\"“”‘’「]?([^，。,；;」\"“”‘’]+)',
                r'标题(?:叫|是|为)\s*[\"“”‘’「]?([^，。,；;」\"“”‘’]+)',
                r'叫做\s*[\"“”‘’「]?([^，。,；;」\"“”‘’]+)',
                r'叫\s*[\"“”‘’「]?([^，。,；;」\"“”‘’]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    title = (match.group(1) or '').strip()
                    if title:
                        return title
        return ''

    def _infer_modify_params(self, todo: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        从 Todo 和 Context 中推断 modify工具参数
        当 LLM 返回空响应时作为兜底逻辑
        优先使用技能匹配，回退到标准逻辑
        """
        import re
        
        result = {
            'execute': False,
            'tool': '',
            'params': {},
            'reason': ''
        }
        
        # 检查是否包含 modify 关键词
        if 'modify' not in todo.lower():
            return result
        
        #检查是否包含 modify 关键词
        if 'modify' not in todo.lower():
            return result
        
        #先尝匹配技能
        matched_skill, score = get_skill_integration().match_skill(todo, context)
        
        if matched_skill and score >= 0.3:
            #使用技能工作流参数
            for workflow_step in matched_skill.workflow:
                if workflow_step.tool == 'modify':
                    # 从技能配置中提取参数模板
                    tool_def = next((t for t in matched_skill.tools if t.name == 'modify'), None)
                    if tool_def:
                        params = tool_def.params.copy()
                        # 解析参数变量
                        for key, value in list(params.items()):  # 使用 list 避免迭代时修改
                            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                                var_name = value[2:-1]  #去除${}
                                
                                # 支持嵌套变量：grep_result.first_bug_id
                                resolved_value = None
                                
                                if '.' in var_name:
                                    # 嵌套变量解析
                                    parts = var_name.split('.')
                                    base_var = parts[0]  # grep_result
                                    field_path = parts[1:]  # ['first_bug_id']
                                    
                                    # 从 context 中获取基础变量
                                    base_value = context.get(base_var)
                                    if base_value and isinstance(base_value, dict):
                                        # 递归获取嵌套字段
                                        current = base_value
                                        for field in field_path:
                                            if isinstance(current, dict) and field in current:
                                                current = current[field]
                                            else:
                                                current = None
                                                break
                                        resolved_value = current
                                else:
                                    # 简单变量解析
                                    if var_name == 'user_modifications':
                                        resolved_value = self._extract_modifications_from_todo(todo)
                                    elif var_name == 'target_id':
                                        resolved_value = (context.get('first_bug_id') or context.get('first_badcase_id') or context.get('first_testcase_id'))
                                    elif var_name == 'project_id':
                                        resolved_value = context.get('project_id', '1')
                                    elif var_name in context:
                                        resolved_value = context[var_name]
                                
                                # 更新参数或删除无法解析的变量
                                if resolved_value is not None:
                                    params[key] = resolved_value
                                else:
                                    # 无法解析，删除该参数或跳过
                                    print(f"[REACT-planing] ⚠️ 无法解析变量: {var_name}")
                                    # 如果是 target_id，尝试从其他来源获取
                                    if key == 'target_id':
                                        target_id = (context.get('first_bug_id') or 
                                                    context.get('first_badcase_id') or 
                                                    context.get('first_testcase_id') or
                                                    context.get('target_id'))
                                        if target_id:
                                            params[key] = target_id
                                        else:
                                            # 没有有效的 target_id，不执行
                                            print(f"[REACT-planing] ❌ 缺少有效的 target_id，跳过执行")
                                            return result
                                    else:
                                        del params[key]  # 删除无法解析的参数
                        
                        # 检查必要参数是否完整
                        if 'target_id' not in params or params.get('target_id') is None:
                            print(f"[REACT-thought] ❌ 缺少 target_id，无法执行 modify")
                            return result
                        
                        result = {
                            'execute': True,
                            'tool': 'modify',
                            'params': params,
                            'reason': f'基于匹配技能 {matched_skill.name} 的工作流参数'
                        }
                        return result
        
        # 如果技能匹配失败，回到标准流程（含 testcase）
        bug_list = context.get('bug_list', [])
        badcase_list = context.get('badcase_list', [])
        testcase_list = context.get('testcase_list', [])
        if not bug_list and 'bug_location' in context:
            bug_list = context.get('bug_location', [])
        if not badcase_list and 'badcase_analysis' in context:
            badcase_analysis = context.get('badcase_analysis', [])
            if badcase_analysis and isinstance(badcase_analysis, list):
                badcase_list = badcase_analysis
        if not testcase_list and 'testcase_location' in context:
            testcase_list = context.get('testcase_location', [])
        _inf_t = self._infer_modify_target('', todo)
        if _inf_t == 'testcase' and testcase_list:
            target_list, target_type = testcase_list, 'testcase'
        elif _inf_t == 'bug' and bug_list:
            target_list, target_type = bug_list, 'bug'
        elif _inf_t == 'badcase' and badcase_list:
            target_list, target_type = badcase_list, 'badcase'
        elif bug_list:
            target_list, target_type = bug_list, 'bug'
        elif badcase_list:
            target_list, target_type = badcase_list, 'badcase'
        elif testcase_list:
            target_list, target_type = testcase_list, 'testcase'
        else:
            target_list, target_type = [], None
        
        if not target_list or not isinstance(target_list, list) or len(target_list) == 0:
            print(f"[REACT-thought] 无法从 context 中获取有效的 bug_list 或 badcase_list")
            print(f"[REACT-thought] context keys: {list(context.keys())}")
            return result
        
        # 获取第一个目标的 ID
        first_item = target_list[0]
        if not isinstance(first_item, dict):
            print(f"[REACT-thought] target_list[0] 不是字典: {type(first_item)}")
            return result
        
        target_id = first_item.get('id')
        if target_id is None:
            print(f"[REACT-thought] 无法从 target_list 中提取 id")
            return result
        
        # 从 Todo 中提取要修改的字段
        # 例如：修改Bug的状态字段为'resolved' -> modifications: {status: 'resolved'}
        modifications = {}
        
        # 匹配状态修改
        status_match = re.search(r"状态.*?['\"](\w+)['\"]|status.*?['\"](\w+)['\"]|状态.*?(resolved|已解决|closed|关闭)", todo, re.IGNORECASE)
        if status_match:
            status_value = status_match.group(1) or status_match.group(2) or status_match.group(3)
            modifications['status'] = status_value
        
        # 匹配优先级修改
        priority_match = re.search(r"优先级.*?['\"](\w+)['\"]|priority.*?['\"](\w+)['\"]", todo, re.IGNORECASE)
        if priority_match:
            modifications['priority'] = priority_match.group(1)
        
        # 如果没有提取到修改内容，默认修改状态
        if not modifications:
            modifications['status'] = 'resolved'
        
        # 状态值标准化（确保使用英文）
        status_normalize = {
            '关闭': 'closed', '已关闭': 'closed', 'close': 'closed',
            '解决': 'resolved', '已解决': 'resolved',
            '重新打开': 'reopened', '重开': 'reopened', 'reopen': 'reopened',
            '新建': 'new', '新': 'new',
            '待处理': 'pending',
            '搁置': 'hold',
        }
        if 'status' in modifications:
            modifications['status'] = status_normalize.get(modifications['status'].lower(), modifications['status'])
        
        # 获取 project_id
        project_id = context.get('project_id') or self.project_id or '1'
        
        result = {
            'execute': True,
            'tool': 'modify',
            'params': {
                'target': target_type or 'badcase',  # 使用推断的目标类型
                'target_id': target_id,
                'modifications': modifications,
                'project_id': project_id,
                'confirm': False  # 默认使用沙箱预览模式，需要用户确认后才执行
            },
            'reason': f'基于 todo内容和 context推断的 modify 参数，target={target_type}, target_id={target_id}'
        }
        
        print(f"[REACT-thought] _infer_modify_params 返回: {result}")
        return result
    
    def _resolve_skill_params(self, param_template: Dict[str, Any], context: Dict[str, Any], user_input: str, project_id: int = None) -> Dict[str, Any]:
        """
        解析技能参数模板中的变量
        
        支持：
        - ${user_keywords}: 从用户输入提取关键词
        - ${user_modifications}: 从用户输入提取修改内容
        - ${grep_result.first_badcase_id}: 从上下文获取嵌套值
        - ${project_id}: 项目ID
        """
        import re
        params = {}
        
        for key, value in param_template.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                var_name = value[2:-1]  # 去除 ${}
                
                # 特殊变量处理
                if var_name == 'user_keywords':
                    # 从用户输入提取关键词
                    # 优先匹配“标题为XXX”或“标题是XXX”的模式
                    title_match = re.search(r'标题[是为]([^，。,]+)', user_input)
                    if title_match:
                        keywords = title_match.group(1).strip()
                        print(f"[REACT] 从用户输入提取标题关键词: '{keywords}'")
                    else:
                        # 回退：去除常见动词
                        keywords = re.sub(r'(修改|更新|调整|所有|状态|改成|设为|标题|为|是)', '', user_input).strip()
                    params[key] = keywords if keywords else ''
                
                elif var_name == 'user_modifications':
                    # 从用户输入提取修改内容
                    modifications = self._extract_modifications_from_todo(user_input)
                    params[key] = modifications if modifications else {}
                
                elif var_name == 'project_id':
                    params[key] = project_id or context.get('project_id', '1')
                
                elif '.' in var_name:
                    # 嵌套变量解析：grep_result.first_badcase_id
                    parts = var_name.split('.')
                    base_var = parts[0]
                    field_path = parts[1:]
                    
                    base_value = context.get(base_var)
                    if base_value:
                        current = base_value
                        for field in field_path:
                            if isinstance(current, dict) and field in current:
                                current = current[field]
                            else:
                                current = None
                                break
                        params[key] = current
                    else:
                        params[key] = None
                
                else:
                    # 简单变量
                    params[key] = context.get(var_name)
            
            else:
                # 非变量，直接使用
                params[key] = value
        
        return params
    
    def _extract_modifications_from_todo(self, todo: str) -> Dict[str, Any]:
        """
        从 todo描述中提取修改内容
        """
        import re
        modifications = {}
        
        # 中文状态映射
        status_map = {
            '重新打开': 'reopened', '重开': 'reopened', 'reopen': 'reopened',
            '已关闭': 'closed', '关闭': 'closed', 'close': 'closed',
            '新建': 'new', '新': 'new',
            '待处理': 'pending', '等待': 'pending',
            '已解决': 'resolved', '解决': 'resolved',
            '搁置': 'hold', '暂停': 'hold',
        }
        
        # 状态修改 - 支持中文
        status_value = None
        
        # 检查中文状态关键词
        for cn_status, en_status in status_map.items():
            if cn_status in todo:
                status_value = en_status
                print(f"[REACT] 从 todo 提取状态: '{cn_status}' -> '{en_status}'")
                break
        
        # 正则匹配英文状态
        if not status_value:
            status_match = re.search(r"status.*?['\"](\w+)['\"]|设为(\w+)", todo, re.IGNORECASE)
            if status_match:
                status_value = status_match.group(1) or status_match.group(2)
        
        if status_value:
            modifications['status'] = status_value
        
        # 优先级修改
        priority_match = re.search(r"优先级.*?(\w+)", todo, re.IGNORECASE)
        if priority_match:
            modifications['priority'] = priority_match.group(1)
        
        # 如果没有提取到任何内容，返回空
        if not modifications:
            print(f"[REACT] 无法从 todo 提取修改内容: {todo}")
            return {}
            
        return modifications
    
    async def _extract_modifications_with_llm(self, todo: str, user_input: str = '', exploration: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        使用大模型从 todo 中提取修改参数。可选传入 exploration（当前记录+用户列表），
        让模型先「探索」再思考意图（类似 Cursor 探索文件后再决定修改）。
        
        Args:
            todo: todo 描述文本
            user_input: 原始用户输入
            exploration: 可选，{ current_record, users }，来自 modify_tool.explore_record
            
        Returns:
            modifications: {字段名: 新值}
        """
        import re
        import json
        
        # 兜底：从用户输入直接解析「标题为/改成/改为 XXX」，避免 LLM 返回空
        text = (user_input or '').strip()
        if text:
            m = re.search(r'标题[为改成改为]+[：:\s]*([^\s，,。]+(?:\s+[^\s，,。]+)*)', text)
            if m:
                title_val = m.group(1).strip()
                if title_val and len(title_val) <= 200:
                    fallback = {'title': title_val}
                    print(f"[REACT-planing] 从用户输入兜底解析标题: {fallback}")
                    return self._normalize_modifications_for_bug_expected_result(fallback, user_input)
        
        # 由大模型识别用户修改意图，归纳为工具参数。若有 exploration，先结合「当前记录+表可修改字段+用户列表」思考再输出。
        exploration_block = ""
        if exploration:
            cur = exploration.get('current_record') or {}
            users = exploration.get('users') or []
            fields = exploration.get('modifiable_fields') or []
            users_str = ", ".join([f"id={u.get('id')} name={u.get('name', '')}" for u in users[:30]])
            fields_str = "、".join([f"{f.get('field', '')}({f.get('label', '')})" for f in fields])
            exploration_block = f"""
【探索到的上下文】（类似 Cursor 探索文件：先看表记录与字段再决定改什么）
当前记录：{json.dumps(cur, ensure_ascii=False)}
本表可修改字段（仅可输出以下 field 名）：{fields_str}
可选用户（id/名称）：{users_str}
请结合上述记录、可修改字段与用户列表思考用户意图（例如负责人「33」对应用户列表中的谁）；只输出上述可修改字段中的 field 名作为 key，负责人用 assignee、值为用户名称，系统会按名称解析为 id。
"""
        
        prompt = f"""
原始用户请求：{user_input}
任务步骤描述：{todo}
{exploration_block}
请由你识别用户的具体修改意图，将意图归纳为「修改字段 → 值」的 JSON，作为 modify 工具的参数。

识别规则：用户表述方式多样（如「为」「改为」「改成」「设为」「调整为」等），只要语义是「把某字段改成某值」就输出对应字段与值。只返回与用户所述类型相符的字段（改 Bug 只出现 Bug 字段，改 BadCase 只出现 BadCase 字段，改测试用例只出现 TestCase 字段）。负责人：用户说的值一律视为对外属性（名称/展示名），输出 assignee 键即可，如「负责人为33」「的负责人为33」「负责人改成33」均输出 {{"assignee": "33"}}；系统会按名称解析为 id。不可修改字段勿返回：类型、id、project_id、plan_id、created_at、updated_at、creator_id；若用户仅要求改「类型」则返回 {{}}。

【Bug 字段映射】仅当用户明确在改 Bug 时使用：
- "标题" -> title
- "描述" -> description
- "状态" -> status（值：new/assigned/in_progress/resolved/closed/reopened）
- "优先级" -> priority（值：p1/p2/p3）
- "严重程度" -> severity
- "负责人" -> assignee（内部映射为 assignee_id）
- "复现步骤" -> steps_to_reproduce
- "期望结果"、"预期结果" -> expected_result
- "实际结果" -> actual_result

【BadCase 字段映射】仅当用户明确在改 BadCase 时使用：
- "标题" -> title
- "状态" -> status
- "优先级" -> priority
- "负责人" -> assignee
- "相似问题"、"具体问题"、"问题" -> base_problem
- "复现步骤" -> reproduction_steps
- "答案" -> answer（注意：不是"正确答案"）
- "正确答案" -> correct_answer
- "BadCase结果" -> badcase_result
- "解决方式" -> solution
- "问题原因" -> problem_reason

【TestCase 字段映射】仅当用户明确在改测试用例时使用：
- "标题" -> title
- "状态" -> status（值：draft/review/active/archived）
- "优先级" -> priority
- "负责人" -> assignee（内部映射为 assignee_id）
- "前置条件" -> preconditions
- "测试步骤" -> steps
- "备注" -> remark
- "基线" -> baseline
- "用例类型" -> case_type
- "测试类型" -> test_type
- "执行结果" -> execution_result
- "预估工时" -> estimated_time
- "实际工时" -> actual_time

示例（意图 → JSON）：
- "修改登录bug的期望结果为能正常登录" -> {{"expected_result": "能正常登录"}}
- "修改相似问题为XXX" -> {{"base_problem": "XXX"}}
- "状态改为已解决" -> {{"status": "resolved"}}
- "标题改成测试标题" -> {{"title": "测试标题"}}
- "修改创建测试用例7的负责人为33" / "的负责人为33" / "负责人改成33" -> {{"assignee": "33"}}

请直接返回 JSON，不要包含其他内容。"""
        
        try:
            response = await self._collect_llm_text(prompt)
            print(f"[REACT-planing] 提取修改参数响应: {response}")
            
            # _collect_llm_text 一般为字符串；若以后改为结构化再处理 dict
            if isinstance(response, dict):
                print(f"[REACT-planing] 提取的修改参数: {response}")
                return self._normalize_modifications_for_bug_expected_result(response, user_input)
            
            # 如果是字符串，提取 JSON 部分
            if isinstance(response, str):
                json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
                if json_match:
                    modifications = json.loads(json_match.group())
                    print(f"[REACT-planing] 提取的修改参数: {modifications}")
                    return self._normalize_modifications_for_bug_expected_result(modifications, user_input)
        except Exception as e:
            print(f"[REACT-planing] 提取修改参数失败: {e}")
        
        return {}
    
    def _user_facing_reasoning_summary(self, user_input: str, raw_reasoning: str) -> str:
        """将模型内部思考转为给用户看的说明。不截取深度思考文本，仅做 ID 转名称与内部词过滤。
        若包含工具名等内部词则回退为根据用户意图生成的简短说明。
        """
        if not raw_reasoning or not isinstance(raw_reasoning, str):
            return self._reasoning_summary_from_user_input(user_input)
        
        raw = raw_reasoning.strip()
        converted_reasoning = self._convert_ids_to_names(raw)
        
        internal_jargon = (
            'grep', 'modify', 'create', 'keywords', 'target', 'project_id', 'modifications',
            'Todo', 'todo', 'JSON', '必填', '可选', 'skill', '技能', 'workflow'
        )
        if any(j in converted_reasoning for j in internal_jargon):
            return self._reasoning_summary_from_user_input(user_input)
        cleaned = converted_reasoning.strip()
        return cleaned if cleaned else self._reasoning_summary_from_user_input(user_input)
    
    def _convert_ids_to_names(self, reasoning_text: str) -> str:
        """将 reasoning 中的内部 ID（project_id, plan_id, target_id）转换为用户可读的名称。
        
        转换规则：
        - project_id=1 → "A 计划项目"
        - plan_id=34 → "一个测试用例的计划"
        - target_id=6 → "创建测试用例"（从数据库中查找标题）
        """
        if not reasoning_text:
            return reasoning_text
        
        result = reasoning_text
        
        # 1. 转换 project_id（需在 app_context 内查库）
        # 2. 转换 plan_id
        import re
        try:
            from app import app, db, Project, Plan
            with app.app_context():
                if self.project_id:
                    project = db.session.query(Project).filter(Project.id == self.project_id).first()
                    if project:
                        result = re.sub(
                            rf'project_id[=：\s]*{self.project_id}',
                            f'"{project.name}"项目',
                            result
                        )
                        result = re.sub(
                            rf'项目 ID[=：\s]*{self.project_id}',
                            f'"{project.name}"项目',
                            result
                        )
                if self.plan_id:
                    plan = db.session.query(Plan).filter(Plan.id == self.plan_id).first()
                    if plan:
                        result = re.sub(
                            rf'plan_id[=：\s]*{self.plan_id}',
                            f'"{plan.name}"计划',
                            result
                        )
                        result = re.sub(
                            rf'迭代计划 ID[=：\s]*{self.plan_id}',
                            f'"{plan.name}"计划',
                            result
                        )
        except Exception as e:
            print(f"[REACT] 转换 project_id/plan_id 失败：{e}")
        
        # 3. 转换 target_id（需在 app_context 内查库）
        target_id_matches = re.findall(r'target_id[=：\s]*(\d+)', result)
        if target_id_matches:
            try:
                from app import app, db, Bug, BadCase, TestCase
                with app.app_context():
                    for match in target_id_matches:
                        target_id = int(match)
                        title = None
                        bug = db.session.query(Bug).filter(Bug.id == target_id).first()
                        if bug:
                            title = bug.title
                        else:
                            badcase = db.session.query(BadCase).filter(BadCase.id == target_id).first()
                            if badcase:
                                title = badcase.title
                            else:
                                testcase = db.session.query(TestCase).filter(TestCase.id == target_id).first()
                                if testcase:
                                    title = testcase.title
                        if title:
                            result = re.sub(
                                rf'target_id[=：\s]*{target_id}',
                                f'"{title}"记录',
                                result
                            )
            except Exception as e:
                print(f"[REACT] 转换 target_id 失败：{e}")
        
        return result
    
    def _user_requested_type_modification(self, user_input: str) -> bool:
        """检测用户是否在要求修改「类型」字段（类型不可修改，需提前拦截）。"""
        if not user_input or not isinstance(user_input, str):
            return False
        u = user_input.strip()
        # 修改...类型 / 类型改为 / 类型改成 / 把类型 / 将类型 / type 改为
        if '类型' in u and any(k in u for k in ('修改', '改', '改成', '改为', '设为', '更新')):
            return True
        if 'type' in u.lower() and any(k in u for k in ('修改', '改', '改成', '改为', '设为', '更新')):
            return True
        return False
    
    def _reasoning_summary_from_user_input(self, user_input: str) -> str:
        """根据用户输入生成一句给用户看的思考说明（不暴露内部参数）。"""
        loc = getattr(self, "_ui_locale", None)
        if is_english_locale(loc):
            if not user_input:
                return "Analyzing your request and planning the next steps."
            u = user_input.strip()
            if any(k in u for k in ('修改', '改', '更新', '改成', '设为', '变为')):
                if any(k in u for k in ('期望结果', '预期结果')):
                    return "Locate the relevant bug, then update the expected result."
                if any(
                    k in u
                    for k in ('状态', '关闭', '解决', 'resolved', 'closed', '草稿', '评审')
                ):
                    if '测试用例' in u or 'testcase' in u.lower() or 'test case' in u.lower():
                        return "Locate the test case, then update its status."
                    return "Locate the record, then update its status."
            if 'bug' in u.lower() or '缺陷' in u:
                return "Find the relevant bug, then apply the change."
            if 'badcase' in u.lower() or 'bad case' in u:
                return "Find the relevant BadCase, then apply the change."
            if any(k in u for k in ('修改', '改', '更新', '改成', '设为', '变为')):
                return "Locate the record, then apply the change."
            if any(k in u for k in ('查询', '搜索', '找', '列出', '显示', 'search', 'find', 'list')):
                return "Searching for matching records."
            if any(k in u for k in ('创建', '新建', '添加', 'create', 'add', 'new')):
                return "Preparing to create a new record."
            return "Analyzing your request and planning the next steps."
        if not user_input:
            return "正在分析您的请求并规划操作步骤。"
        u = user_input.strip()
        # 「变为/草稿/评审」等常见改状态说法，不含「改」字也要命中
        if any(k in u for k in ('修改', '改', '更新', '改成', '设为', '变为')):
            if any(k in u for k in ('期望结果', '预期结果')):
                return "先查找相关 Bug，再修改其期望结果。"
            if any(k in u for k in ('状态', '关闭', '解决', 'resolved', 'closed', '草稿', '评审')):
                if '测试用例' in u or 'testcase' in u.lower() or 'test case' in u.lower():
                    return "先定位相关测试用例，再修改状态。"
                return "先定位相关记录，再修改状态。"
            if 'bug' in u.lower() or '缺陷' in u:
                return "先查找相关 Bug，再执行修改。"
            if 'badcase' in u.lower() or 'bad case' in u:
                return "先查找相关 BadCase，再执行修改。"
            return "先定位相关记录，再执行修改。"
        if any(k in u for k in ('查询', '搜索', '找', '列出', '显示')):
            return "正在查找相关记录。"
        if any(k in u for k in ('创建', '新建', '添加')):
            return "正在准备创建新记录。"
        return "正在分析您的请求并规划操作步骤。"
    
    def _normalize_modifications_for_bug_expected_result(self, modifications: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """兜底：用户说的是「期望结果」但 LLM 误提成 base_problem 时，改为 expected_result，避免沙箱预览显示为「相似问题」。"""
        if not modifications or not user_input:
            return modifications
        if 'expected_result' in modifications:
            return modifications
        if 'base_problem' not in modifications:
            return modifications
        if '期望结果' in user_input or '预期结果' in user_input:
            modifications = dict(modifications)
            modifications['expected_result'] = modifications.pop('base_problem')
            print(f"[REACT-planing] 兜底：用户说期望结果，将 base_problem 改为 expected_result")
        return modifications
    
    def _extract_modifications_with_regex(self, user_input: str) -> Dict[str, Any]:
        """
        LLM 失败时的极简兜底（如解析异常、网络错误），仅做最宽松的匹配。
        主路径应由大模型识别意图并归纳为工具参数，不依赖写死的句式。
        """
        import re
        modifications = {}
        if not (user_input or '').strip():
            return modifications
        # 仅当明显包含「某字段 + 为/改为/改成 + 值」时，取最后一个这样的片段做极简推断，避免写死多种说法
        loose = re.search(r'(负责人|标题|状态)[为改成设为调整为]*\s*[：:\s]*([^\s，,。]+)', user_input)
        if loose:
            field_name = loose.group(1)
            value = loose.group(2).strip().rstrip('。，')
            key = 'assignee' if field_name == '负责人' else ('title' if field_name == '标题' else 'status')
            modifications[key] = value
            print(f"[REACT-REGEX] 兜底（极简）：{field_name} -> {key} = {value}")
        if not modifications and '负责人' in user_input:
            m2 = re.search(
                r'负责人\s*(?:修改|改|改为|设为|调整为|为)?\s*[：:\s]*([^\s，,。]+)',
                user_input,
            )
            if m2:
                modifications['assignee'] = m2.group(1).strip().rstrip('。，')
                print(f"[REACT-REGEX] 兜底（负责人句式）：assignee = {modifications['assignee']}")
        return modifications
    
    async def _maybe_self_drive_decision_from_todo(
        self,
        todo: str,
        user_input: str,
        step_index: int,
        todos_len: int,
    ) -> Optional[Dict[str, Any]]:
        """REACT_SELF_DRIVE_TOOL_LOOP=1：由 Todo 文案解析工具，跳过本步 decide LLM。"""
        if (os.getenv("REACT_SELF_DRIVE_TOOL_LOOP", "0") or "0").strip().lower() not in (
            "1",
            "true",
            "yes",
            "on",
        ):
            return None
        if step_index >= todos_len:
            return None
        try:
            tp = await self._extract_todo_params(todo, user_input)
        except Exception:
            return None
        tname = (tp.get("tool") or "").strip()
        if not tname or tname == "unknown":
            return None
        return {
            "execute": True,
            "tool": tname,
            "params": dict(tp.get("params") or {}),
            "reason": "self_drive_todo_extract",
        }

    async def _extract_todo_params(self, todo: str, user_input: str) -> Dict[str, Any]:
        """
        从 todo 中提取工具名称和参数
        
        支持的 todo 格式:
        - "使用 grep 工具搜索标题为XXX的BadCase，keywords=XXX，target=badcase"
        - "使用 modify 工具将标题为XXX的BadCase状态修改为resolved"
        """
        import re
        result = {'tool': None, 'params': {}}
        
        # 1. 确定工具类型 - 优先匹配 modify，因为 modify 的 todo 中可能包含"搜索"关键词
        # 例如："使用 modify 工具将搜索到的 BadCase 状态修改为 resolved"
                
        # 先检查是否明确指定了 modify 工具或包含修改意图
        modify_keywords = ['modify', '修改', '改成', '改为', '更新', '设为', '调整']
        has_modify_intent = any(kw in todo.lower() for kw in modify_keywords)
                
        if has_modify_intent and 'grep' not in todo.lower():
            result['tool'] = 'modify'
                    
            # 使用大模型提取修改参数（更准确）
            modifications = await self._extract_modifications_with_llm(todo, user_input)
                    
            # 如果 LLM 调用失败，使用正则表达式兜底提取
            if not modifications and user_input:
                modifications = self._extract_modifications_with_regex(user_input)
                    
            # 提取目标类型：优先检查 testcase，再检查 bug，最后 badcase
            if 'testcase' in todo.lower() or 'test_case' in todo.lower() or '测试用例' in todo:
                target = 'testcase'
            elif 'bug' in todo.lower() or '缺陷' in todo or 'Bug' in todo:
                target = 'bug'
            elif 'badcase' in todo.lower() or 'bad case' in todo.lower() or 'bad 案例' in todo:
                target = 'badcase'
            else:
                target = 'badcase'  # 默认
                    
            result['params'] = {
                'target': target,
                'modifications': modifications,
                'confirm': False,
            }
            print(f"[REACT] 从 todo 提取 modify 参数：modifications={modifications}, target={target}")
        
        # 必须先于 create：todo 文案里常含标题「一个新增的 bug」，子串「新增」会误匹配 create
        elif 'grep' in todo.lower() or '搜索' in todo or '查找' in todo or '定位' in todo:
            result['tool'] = 'grep'
            
            # 提取关键词 - 优先匹配 keywords=XXX 格式
            keywords_match = re.search(r'keywords[=：]\s*([^，,]+)', todo, re.IGNORECASE)
            if keywords_match:
                keywords = keywords_match.group(1).strip()
            else:
                # 回退：匹配“标题为XXX”格式
                title_match = re.search(r'标题[是为]([^，。,]+)', todo)
                keywords = title_match.group(1).strip() if title_match else ''
            # 关键词兜底：从用户输入提取（如「修改登录bug的期望结果」->「登录」）
            if not keywords and user_input:
                keywords = self._extract_title_keywords_for_grep(user_input, todo)
            
            # 提取目标类型：todo 优先，否则结合用户输入（用户说「修改创建测试用例的前提条件」应查测试用例表）
            if 'bug' in todo.lower() or 'target=bug' in todo.lower():
                target = 'bug'
            elif 'testcase' in todo.lower() or 'test_case' in todo.lower() or 'target=testcase' in todo.lower():
                target = 'testcase'
            elif 'badcase' in todo.lower() or 'bad case' in todo.lower():
                target = 'badcase'
            elif user_input and ('测试用例' in user_input or 'test case' in user_input.lower()):
                # 兜底：用户提到测试用例但 todo 未写 target=testcase 时，按测试用例查
                target = 'testcase'
            elif user_input and ('bug' in user_input or '缺陷' in user_input or 'Bug' in user_input):
                # 兜底：用户提到 bug/缺陷但 todo 未写类型时，按 bug 查（避免默认 badcase 导致定位错表）
                target = 'bug'
            else:
                target = 'badcase'  # 默认
            
            result['params'] = {
                'target': target,
                'mode': 'locate',
                'keywords': keywords or None,
            }
            print(f"[REACT] 从 todo 提取 grep 参数: keywords='{keywords}', target={target}")

        elif 'create' in todo.lower() or '创建' in todo or '新增' in todo or '新建' in todo:
            result['tool'] = 'create'
            target = self._infer_create_target(user_input, todo)
            title = self._extract_create_title(user_input, todo)
            fields = {}
            if title:
                fields['name' if target == 'plan' else 'title'] = title
            result['params'] = {
                'target': target,
                'fields': fields,
                'confirm': False,
            }
            print(f"[REACT] 从 todo 提取 create 参数: target={target}, fields={fields}")
        
        else:
            # 未知工具，返回空
            print(f"[REACT] 无法从 todo 识别工具: {todo}")
            result['tool'] = 'unknown'
        
        return result

    def _drain_tool_task_sse_buffer_list(self) -> List[Dict[str, Any]]:
        """REACT_AGENT_TASK_DAG：冲刷 ``run_persisted_single`` 写入的 ``tool_task_*`` 引擎事件。"""
        buf = getattr(self, "_tool_task_event_buffer", None)
        if not buf:
            return []
        out = list(buf)
        buf.clear()
        return out
    
    async def _execute_tool(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具（可选经 agent_tasks 持久化，见 REACT_AGENT_TASK_DAG）。"""
        try:
            from agents.agent_task_dag import use_react_agent_task_dag, run_persisted_single

            if use_react_agent_task_dag():
                return await run_persisted_single(
                    self,
                    decision,
                    getattr(self, "_agent_session_id", None),
                )
        except Exception as e:
            print(f"[REACT] agent_task_dag 包装失败，回退直连执行: {e}")
        try:
            from agents.agent_task_dag import execute_tool_implementation_with_retry

            return await execute_tool_implementation_with_retry(self, decision)
        except Exception:
            return await self._execute_tool_implementation(decision)

    async def _execute_tool_implementation(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具（核心实现，供 DAG 层与直连路径复用）。"""
        tool_name = decision['tool']
        original_tool_name = tool_name
        # FC/XML 可能返回 Grep、Modify 等与注册名大小写不一致
        if isinstance(tool_name, str) and tool_name.strip():
            _tn_low = tool_name.strip().lower()
            if self.tools.get(tool_name) is None and self.tools.get(_tn_low) is not None:
                tool_name = _tn_low
                decision["tool"] = _tn_low
        
        # 增加模糊匹配映射
        if 'bug' in tool_name.lower() and 'management' in tool_name.lower():
            tool_name = 'bug_management'
        elif 'browser' in tool_name.lower():
            tool_name = 'browser_test'
        elif 'search' in tool_name.lower():
            tool_name = 'search'
        
        print(f"[REACT] 正在执行工具: {original_tool_name} -> {tool_name}")
            
        tool = self.tools.get(tool_name)
        
        if not tool:
            print(f"[REACT] ❌ 工具不存在: {tool_name}")
            return {
                "success": False,
                "error": react_tool_missing_error(
                    tool_name, getattr(self, "_ui_locale", None)
                ),
            }
        
        params = decision.get('params') or {}
        try:
            # 确保传入 userId 和 project_id；并保证 params 与 decision['params'] 同引用，便于 run_stream 轮询 progress_queue
            if 'params' not in decision:
                decision['params'] = params
            if 'userId' not in params:
                params['userId'] = 'system_agent'
            if self.project_id and 'project_id' not in params:
                params['project_id'] = self.project_id
            params["ui_locale"] = normalize_locale(getattr(self, "_ui_locale", None))
            
            print(f"[REACT] 工具参数: {params}")
            print(f"[REACT] 正在执行工具: {tool_name}")

            grep_cache_ttl = 0.0
            grep_ck: Optional[str] = None
            if tool_name == "grep":
                try:
                    grep_cache_ttl = float(
                        (os.getenv("REACT_GREP_RESULT_CACHE_TTL") or "0").strip()
                    )
                except Exception:
                    grep_cache_ttl = 0.0
                if grep_cache_ttl > 0:
                    grep_ck = self._grep_cache_key(params)
                    now_g = time.time()
                    hit = self._grep_result_cache.get(grep_ck)
                    if hit and hit[0] > now_g:
                        if os.getenv("PERF_LOG") == "1":
                            print(
                                f"[PERF][grep_cache] hit ttl_left≈{hit[0]-now_g:.1f}s "
                                f"key={grep_ck[:120]}…"
                            )
                        return copy.deepcopy(hit[1])
                    self._grep_result_cache.pop(grep_ck, None)

            # modify 工具内部使用 Flask/SQLAlchemy 同步 DB，会阻塞 asyncio 事件循环，导致流式一直“修改中...”
            # 放到线程池中执行，在独立线程里跑新事件循环，避免阻塞主循环，并增加超时保护
            if tool_name == 'modify':
                print(
                    f"[REACT] modify 进入线程池执行（target_id={params.get('target_id')}, "
                    f"target_ids={params.get('target_ids')}, target={params.get('target')}）…"
                )
                loop = asyncio.get_event_loop()
                import queue as _queue
                progress_q: "_queue.Queue[str]" = _queue.Queue()
                # 暴露给上层 run_stream 轮询，向前端实时下发分步进度
                params['progress_queue'] = progress_q

                def _progress_cb(msg: str):
                    try:
                        progress_q.put(str(msg))
                    except Exception:
                        pass

                def _run_modify_in_thread():
                    thread_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(thread_loop)
                    try:
                        # 把进度回调传给 modify_tool（工具内分步上报）
                        params['progress_callback'] = _progress_cb
                        # Agent 调用 modify 默认先预览（confirm=False），用户在列表确认后再落库
                        if 'confirm' not in params:
                            params['confirm'] = False
                        return thread_loop.run_until_complete(tool.execute(**params))
                    finally:
                        thread_loop.close()

                # 工具级超时时间（秒），可通过环境变量调整，默认 120s
                tool_timeout = int(os.getenv("AGENT_TOOL_TIMEOUT", "120"))
                try:
                    res = await asyncio.wait_for(
                        loop.run_in_executor(self._tool_executor, _run_modify_in_thread),
                        timeout=tool_timeout,
                    )
                except asyncio.TimeoutError:
                    print(f"[REACT] ❌ modify 工具执行超时（>{tool_timeout}s）")
                    return {
                        "success": False,
                        "error": react_modify_timeout(
                            tool_timeout, getattr(self, "_ui_locale", None)
                        ),
                    }
            else:
                res = await tool.execute(**params)
            
            print(f"[REACT] ✅ 工具执行完成: {tool_name}")
            print(f"[REACT] 工具返回数据类型: {type(res).__name__}")
            if isinstance(res, dict) and 'results' in res:
                print(f"[REACT] 搜索结果数量: {len(res.get('results', []))}")
            if res is None:
                res = {'success': False, 'error': '工具返回空结果'}
            elif 'success' not in res:
                res['success'] = True # 默认成功
            if (
                tool_name == "grep"
                and grep_cache_ttl > 0
                and grep_ck
                and isinstance(res, dict)
                and res.get("success")
            ):
                self._grep_result_cache[grep_ck] = (
                    time.time() + grep_cache_ttl,
                    copy.deepcopy(res),
                )
            if (
                tool_name in ("modify", "create")
                and isinstance(res, dict)
                and res.get("success")
                and self._grep_result_cache
            ):
                self._grep_result_cache.clear()
                if os.getenv("PERF_LOG") == "1":
                    print("[PERF][grep_cache] cleared after modify/create success")
            return res
        except Exception as e:
            print(f"[REACT] ❌ 工具执行异常: {str(e)}")
            return {'success': False, 'error': str(e)}
        finally:
            # 临时执行字段仅用于运行期心跳；必须清理，避免后续 JSON 序列化（observe_prompt/UI）报错
            if isinstance(params, dict):
                params.pop('progress_queue', None)
                params.pop('progress_callback', None)
