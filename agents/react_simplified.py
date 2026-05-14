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
- REACT_PROJECT_PLAN_NAME_CACHE_TTL：按 ``(project_id, plan_id)`` 缓存名称秒数（默认 **300**）；``0`` 关闭缓存。查库在 **线程池** 执行，避免阻塞 asyncio 事件循环
- ``POST /api/agent/react`` 可选 ``project_display_name`` / ``plan_display_name``（或 ``context_project_name`` / ``context_plan_name``）：与当前 ``project_id``/``plan_id`` 所需字段齐全时 **跳过 Redis 与 MySQL 名称查询**，将统一流前置 gather 压在 1s 内（项目页聊天由前端传入已拉取的项目名）
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
- PERF_LOG=1：打印各阶段耗时，便于对比模型与链路瓶颈；grep 后观察链路见 ``[PERF][observe]``（stream_observe_ms / xml_parse_ms / ui_observe_summary_ms / total_ms）；轮次衔接见 ``[PERF][round-bridge]``（观察流结束→todo_end、todo_start→FC/流式 decide）；统一流启动见 ``[PERF][react] unified_gather_task_*`` 与 ``project_plan_lookup_*``（L1/L2/L3、``db_session_get_project`` 等）
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
- REACT_UNIFIED_THINK_SSE_MIN_CHARS：统一流里 ``agent_thought`` 合并下发前的最小字符数（默认 **4**，至少 **1**）。过小会增加 SSE 条数；过大则首轮思考区长时间空白、末段「一整块冒出」。内部仍按字符解析 ``<decision>``/``<observation>``。
- REACT_PLAN_SSE_LIVE_STEPS=1（默认）：每轮同步 ``plan_update``（单 in_progress）；``=0`` 关闭。
- REACT_UNIFIED_FIRST_ROUND_TASK_PLAN=1（默认）：统一流首轮提示词允许模型**仅在复杂多步**时在 ``<thinking>`` 内输出 ``<task_plan>``；简单单步不应输出。有输出则解析并注入后续轮 ``<current_todo>``、下发 ``plan_init``/``plan_update``。``=0`` 关闭。
- REACT_UNIFIED_PLAN_MAX_STEPS：首轮 ``task_plan`` 最大步数（默认 **12**，上限 32）。
- REACT_UNIFIED_SNAPSHOT_ROUNDS：统一流在拼 LLM prompt **前**打印 ``result_ctx`` / ``prev_*`` 摘要的轮次（**1-based**，逗号分隔；默认 **3**；``0``/``off`` 关闭；``all``=每轮）。
- REACT_UNIFIED_ERROR_DIAG：统一流 ``stream error`` 时是否打印 traceback + 同上摘要（默认 **1**；``0`` 关闭）。
- REACT_UNIFIED_PARSE_RETRY：统一流若无法解析三段式（如缺少 ``</decision>``），是否追加严格格式提示并**再请求一次** LLM；默认 **1**（多一次）；``0`` 关闭；额外次数上限 **2**。
- REACT_MAX_ROUNDS：统一流主循环硬性上限（默认 **30**，上限 500）；用尽后 ``done.status=partial``、``stop_reason=max_rounds``。
- REACT_DUPLICATE_ACTION_WINDOW：连续相同工具+参数签名达到此次数后中断（默认 **3**，范围 2～8）；``done.stop_reason=duplicate_action``。
- REACT_PLAN_STEP_MAX_RETRIES：存在 ``task_plan`` 时单步连续失败达到此次数则跳过该步（默认 **3**）。
- REACT_MERGE_FIRST_THINK_INTO_DECIDE=1：跳过独立首轮 THINK；``todo_items``（及可选 ``first_tool``/``first_params``）在 **主循环第 0 步** 通过 **submit_react_think** 一次 FC 完成（须 ``REACT_DECIDE_FUNCTION_CALL=1`` 且 LLM 支持 FC）。默认 ``0``。
- REACT_THINK_QUEUE_POLL_S：首轮 THINK 从队列取块时的轮询间隔秒数（默认 ``0.03``）；略缩可更快响应首 token，过小占 CPU。范围约 0.02～0.2
- REACT_CHAT_REPLY_STREAM=1（默认）：纯对话路径用 ``summary_stream`` 分块输出；``REACT_CHAT_REPLY_STREAM_CHARS`` 每块字符数（默认 2）
- REACT_SUMMARY_STREAM_GAP_MS：``summary_stream`` / 统一总结 LLM 流等分片之间的暂停毫秒数（默认 22；``0`` 关闭）。单靠 ``asyncio.sleep(0)`` 易与单次 TCP/读缓冲合并，前端像「一次性整块」
- REACT_RUNNING_SUMMARY_STREAM_GAP_MS：终局 ``running_summary_stream`` 分片间隔；**未设置**时与 ``REACT_SUMMARY_STREAM_GAP_MS`` 相同
- REACT_INCREMENTAL_SUMMARY：每步 observation 后合并「增量运行总览」Markdown。**默认开**；``0``/``false``/``off`` 关闭。``REACT_INCREMENTAL_SUMMARY_MAX_TOKENS``（默认 2048）；``REACT_INCREMENTAL_SUMMARY_REPLACE_FINAL=1``（默认）时终局不再跑统一总结 LLM
- REACT_BACKGROUND_SUMMARY_JOIN_TIMEOUT：主循环结束时等待**后台增量总结线程**的最长秒数（默认 **90**）。旧逻辑仅等 3s 即读队列，LLM 仍在输出时会把「关键发现」裁成半句；可调大或配合 ``REACT_INCREMENTAL_SUMMARY_MAX_TOKENS``
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
from collections import deque
import concurrent.futures
import functools
import copy
import json
import time
import traceback
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
from .evidence_extractor import EvidenceExtractor, _json_safe_tool_params, deep_sse_json_safe
from llm.multimodal_content import openai_style_user_content

# 与 SSE 信封 request_id（agent_session_id）对齐：前端停止时合作式打断主循环
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


# Skill 动态加载
from .skill_loader import SkillLoader
from .skill_registry import skill_registry
from .skill import Skill
from .skill_integration import get_skill_integration  # Skill 集成管理器（懒加载）
from .sse_react_v1 import (
    ClientWireType,
    PROCESS_TYPE_END,
    PROCESS_TYPE_STREAMING,
    REACT_PHASE_ACT,
    REACT_PHASE_DECIDE,
    REACT_PHASE_OBSERVE,
    REACT_PHASE_THINK,
    THINK_STREAM_STATUS_END,
    THINK_STREAM_STATUS_START,
    engine_dict_to_wire_packets,
    is_wire_v1_packet,
    react_phase_wire_payload,
    sse_v1_emit_phase_packets_enabled,
)
from .unified_think_stream_sanitize import create_unified_think_sanitizer
from .intent_guards import (
    is_vague_generic_todo,
    infer_modify_target_from_user,
    user_text_implies_bug_entity_type,
    user_text_implies_card_entity_type,
    user_text_implies_plan_entity_type,
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
    react_unified_sse_xml_markers,
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
    react_unified_strict_format_retry_suffix,
    react_unified_duplicate_action_stall_message,
    react_unified_partial_max_rounds_message,
    react_unified_plan_step_skip_failures_message,
    react_summarize_grep_done_hits,
    enrich_grep_observation_nl_with_plan_names,
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
        "card_list",
        "plan_list",
        "grep_result",
        "first_badcase_id",
        "first_bug_id",
        "first_testcase_id",
        "first_card_id",
        "first_plan_id",
        "grep_modify_raw_plan_list",
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


def _unified_first_round_task_plan_enabled() -> bool:
    return (os.getenv("REACT_UNIFIED_FIRST_ROUND_TASK_PLAN", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _cap_unified_task_plan_steps(steps: List[str]) -> List[str]:
    try:
        cap = int((os.getenv("REACT_UNIFIED_PLAN_MAX_STEPS", "12") or "12").strip())
    except Exception:
        cap = 12
    cap = max(2, min(cap, 32))
    if len(steps) > cap:
        if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
            print(f"[REACT-UNIFIED] task_plan capped {len(steps)} -> {cap}")
        return steps[:cap]
    return list(steps)


def _react_plan_sse_live_steps_enabled() -> bool:
    return (os.getenv("REACT_PLAN_SSE_LIVE_STEPS", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _unified_error_diag_enabled() -> bool:
    """流异常时是否打印 traceback + 不可 JSON 字段路径。``REACT_UNIFIED_ERROR_DIAG=0`` 关闭。"""
    return (os.getenv("REACT_UNIFIED_ERROR_DIAG", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _unified_plan_diag_enabled() -> bool:
    """统一流首轮是否打印 plan/task_plan 解析诊断（原文长度、是否含标签、parsed 步列表）。``REACT_UNIFIED_PLAN_DIAG=0`` 关闭。"""
    return (os.getenv("REACT_UNIFIED_PLAN_DIAG", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _unified_parse_retry_max() -> int:
    """统一流：解析失败时的最大 LLM 调用次数（含首次）。``REACT_UNIFIED_PARSE_RETRY=0`` 不重试；默认 ``1`` 表示额外再调一次。"""
    raw = (os.getenv("REACT_UNIFIED_PARSE_RETRY", "1") or "1").strip().lower()
    if raw in ("0", "false", "no", "off", "none"):
        return 1
    try:
        extra = int(raw)
    except ValueError:
        extra = 1
    extra = max(0, min(extra, 2))
    return 1 + extra


def _unified_should_retry_parse(
    parsed: Dict[str, Any],
    attempt_idx: int,
    max_attempts: int,
) -> bool:
    if attempt_idx + 1 >= max_attempts:
        return False
    pm = parsed.get("parse_meta") or {}
    return bool(pm.get("retry_recommended"))


def _react_max_rounds_cap() -> int:
    """主循环硬性轮次上限；``REACT_MAX_ROUNDS`` 默认 30，夹在 [1, 500]。"""
    try:
        return max(1, min(int(os.getenv("REACT_MAX_ROUNDS", "30")), 500))
    except Exception:
        return 30


def _react_duplicate_action_window() -> int:
    """连续相同 (tool, params) 签名达到此次数则视为卡死；``REACT_DUPLICATE_ACTION_WINDOW`` 默认 3。"""
    try:
        w = int(os.getenv("REACT_DUPLICATE_ACTION_WINDOW", "3") or "3")
        return max(2, min(w, 8))
    except Exception:
        return 3


def _react_plan_step_max_retries() -> int:
    """有计划步时，单步连续失败次数上限，超过则跳过该步；``REACT_PLAN_STEP_MAX_RETRIES`` 默认 3。"""
    try:
        r = int(os.getenv("REACT_PLAN_STEP_MAX_RETRIES", "3") or "3")
        return max(1, min(r, 20))
    except Exception:
        return 3


def _tool_params_signature(tool: str, params: Dict[str, Any]) -> str:
    """用于重复动作检测的稳定签名（排除易变字段）。"""
    skip = frozenset({"ui_locale", "progress_queue", "progress_callback", "userId"})
    d: Dict[str, Any] = {}
    for k in sorted((params or {}).keys()):
        if k in skip:
            continue
        d[k] = (params or {}).get(k)
    try:
        return f"{(tool or '').strip()}\t{json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)}"
    except Exception:
        return f"{tool}\t{repr(d)}"


def _unified_snapshot_rounds_1based() -> Optional[set]:
    """
    在构建统一流 prompt **之前**打印快照的轮次（1-based）。
    默认 ``REACT_UNIFIED_SNAPSHOT_ROUNDS=3``（仅第 3 轮）；设 ``0``/``off``/空字符串关闭；``all`` 表示每一轮。
    """
    raw = os.getenv("REACT_UNIFIED_SNAPSHOT_ROUNDS", "3")
    rs = (raw or "").strip().lower()
    if rs in ("0", "false", "no", "off", "none"):
        return None
    if rs == "all":
        return set(range(1, 10_000))
    out: set = set()
    for p in (raw or "").split(","):
        p = p.strip()
        if not p:
            continue
        try:
            out.add(int(p))
        except ValueError:
            pass
    return out if out else None


def _diag_non_json_paths(
    obj: Any,
    path: str = "$",
    depth: int = 0,
    max_depth: int = 22,
) -> List[str]:
    """递归标出 Queue / callable / json.dumps 失败的字段路径，便于排查 stream error。"""
    out: List[str] = []
    cap = 100

    def walk(o: Any, p: str, d: int) -> None:
        nonlocal out
        if len(out) >= cap:
            return
        if d > max_depth:
            out.append(f"{p}…(max_depth)")
            return
        if o is None or isinstance(o, (bool, int, float, str)):
            return
        try:
            if isinstance(o, (queue.Queue, queue.SimpleQueue)):
                out.append(f"{p}: {type(o).__name__}")
                return
            if isinstance(o, asyncio.Queue):
                out.append(f"{p}: asyncio.Queue")
                return
        except Exception:
            pass
        try:
            if callable(o) and not isinstance(o, type):
                nm = getattr(o, "__name__", type(o).__name__)
                out.append(f"{p}: callable({nm})")
                return
        except Exception:
            pass
        if isinstance(o, dict):
            for k, v in list(o.items())[:280]:
                if len(out) >= cap:
                    return
                walk(v, f"{p}.{str(k)[:72]}", d + 1)
            return
        if isinstance(o, (list, tuple)):
            for i, v in enumerate(o[:130]):
                if len(out) >= cap:
                    return
                walk(v, f"{p}[{i}]", d + 1)
            return
        try:
            json.dumps(o)
        except TypeError:
            out.append(f"{p}: {type(o).__name__} (json.dumps TypeError)")

    walk(obj, path, depth)
    return out


def _print_unified_round_prompt_snapshot(
    round_idx: int,
    result_ctx: Dict[str, Any],
    prev_observation: Optional[Dict[str, Any]],
    prev_action: Optional[Dict[str, Any]],
    *,
    tag: str = "prompt 前",
) -> None:
    """在指定轮次构建 LLM prompt 前（或异常时）打印上下文摘要（控制台）。"""
    r1 = max(1, round_idx + 1)
    print(f"[REACT-UNIFIED][snapshot] ── 第 {r1} 轮 {tag} ──", flush=True)
    try:
        rk = list((result_ctx or {}).keys())[:40]
        print(f"[REACT-UNIFIED][snapshot] result_ctx keys ({len(rk)}): {rk}", flush=True)
        bad_c = _diag_non_json_paths(result_ctx or {}, "result_ctx")
        if bad_c:
            print(f"[REACT-UNIFIED][snapshot] result_ctx 可疑路径: {bad_c[:60]}", flush=True)
    except Exception as ex:
        print(f"[REACT-UNIFIED][snapshot] result_ctx 摘要失败: {ex}", flush=True)
    if prev_observation is None:
        print("[REACT-UNIFIED][snapshot] prev_observation: (无)", flush=True)
    else:
        try:
            if isinstance(prev_observation, dict):
                pk = list(prev_observation.keys())[:50]
                print(
                    f"[REACT-UNIFIED][snapshot] prev_observation keys ({len(pk)}): {pk}",
                    flush=True,
                )
            else:
                print(
                    f"[REACT-UNIFIED][snapshot] prev_observation type={type(prev_observation).__name__}",
                    flush=True,
                )
            bad_o = _diag_non_json_paths(prev_observation, "prev_observation")
            if bad_o:
                print(
                    f"[REACT-UNIFIED][snapshot] prev_observation 可疑路径: {bad_o[:60]}",
                    flush=True,
                )
        except Exception as ex:
            print(f"[REACT-UNIFIED][snapshot] prev_observation 摘要失败: {ex}", flush=True)
    if not prev_action:
        print("[REACT-UNIFIED][snapshot] prev_action: (无)", flush=True)
    else:
        try:
            print(
                f"[REACT-UNIFIED][snapshot] prev_action tool={prev_action.get('tool')!r} "
                f"params_keys={list((prev_action.get('params') or {}).keys()) if isinstance(prev_action.get('params'), dict) else 'n/a'}",
                flush=True,
            )
            bad_a = _diag_non_json_paths(prev_action.get("params"), "prev_action.params")
            if bad_a:
                print(
                    f"[REACT-UNIFIED][snapshot] prev_action.params 可疑路径: {bad_a[:60]}",
                    flush=True,
                )
        except Exception as ex:
            print(f"[REACT-UNIFIED][snapshot] prev_action 摘要失败: {ex}", flush=True)


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
    hint_project_name: Optional[str] = None,
    hint_plan_name: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """在 app_context 内查 Project/Plan 名称；优先 Redis 缓存，其次进程内存缓存，最后查库。

    若请求体传入 ``hint_project_name`` / ``hint_plan_name`` 且与当前 pid/plid 所需字段齐全，
    则直接写入 L1 并返回，**跳过 Redis 与 DB**（满足首包 gather <1s，避免远程 Redis/MySQL 冷路径）。
    """
    _t_fn0 = time.perf_counter()

    def _elapsed_ms() -> float:
        return (time.perf_counter() - _t_fn0) * 1000.0

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
        if perf:
            print(
                f"[PERF][react] project_plan_lookup_noop pid={pid} plid={plid} "
                f"cumulative_ms={_elapsed_ms():.1f}"
            )
        return None, None
    
    key = (pid, plid)
    redis_key = f"react:project_plan_name:{pid}:{plid}"
    ttl = _react_project_plan_name_cache_ttl_s()
    now = time.monotonic()
    if perf:
        try:
            th = threading.current_thread()
            th_label = f"{th.name} ident={getattr(th, 'native_id', None) or th.ident}"
        except Exception:
            th_label = "?"
        print(
            f"[PERF][react] project_plan_lookup_begin pid={pid} plid={plid} ttl_s={ttl} "
            f"thread={th_label} cumulative_ms={_elapsed_ms():.1f}"
        )
    
    # L1: 进程内存缓存
    if ttl > 0:
        _t_l1 = time.perf_counter()
        with _react_project_plan_name_cache_lock:
            hit = _react_project_plan_name_cache.get(key)
            if hit is not None:
                pn0, pln0, t0 = hit
                if now - t0 < ttl:
                    if perf:
                        print(
                            f"[PERF][react] project_plan_lookup_l1_hit "
                            f"lock_and_lookup_ms={(time.perf_counter()-_t_l1)*1000:.1f} "
                            f"cumulative_ms={_elapsed_ms():.1f}"
                        )
                    return pn0, pln0
        if perf:
            print(
                f"[PERF][react] project_plan_lookup_l1_miss "
                f"lock_ms={(time.perf_counter()-_t_l1)*1000:.1f} cumulative_ms={_elapsed_ms():.1f}"
            )

    # 客户端已带齐展示名：跳过 L2/L3（常见于项目页聊天，ProjectDetail 已拉过 project.name）
    _need_p = pid > 0
    _need_pl = plid > 0
    _hp = (str(hint_project_name).strip() if hint_project_name else "") or ""
    _hpl = (str(hint_plan_name).strip() if hint_plan_name else "") or ""
    if (_need_p or _need_pl) and (not _need_p or _hp) and (not _need_pl or _hpl):
        _pn = _hp if _need_p else None
        _pln = _hpl if _need_pl else None
        if perf:
            print(
                f"[PERF][react] project_plan_lookup_client_hint_fast "
                f"cumulative_ms={_elapsed_ms():.1f} (skip_redis_db)"
            )
        if ttl > 0:
            _now2 = time.monotonic()
            with _react_project_plan_name_cache_lock:
                _react_project_plan_name_cache[key] = (_pn, _pln, _now2)
        if perf:
            print(
                f"[PERF][react] project_plan_lookup_total_ms={_elapsed_ms():.1f} "
                f"project_name={'set' if _pn else 'none'} plan_name={'set' if _pln else 'none'} (hint)"
            )
        return _pn, _pln
    
    # L2: Redis 缓存
    _t_rclient = time.perf_counter()
    redis_client = _get_redis_client_for_cache()
    if perf:
        print(
            f"[PERF][react] project_plan_lookup_redis_client "
            f"ms={(time.perf_counter()-_t_rclient)*1000:.1f} ok={redis_client is not None} "
            f"cumulative_ms={_elapsed_ms():.1f}"
        )
    if redis_client is not None:
        try:
            _t_rget = time.perf_counter()
            cached = redis_client.get(redis_key)
            if perf:
                print(
                    f"[PERF][react] project_plan_lookup_redis_get "
                    f"ms={(time.perf_counter()-_t_rget)*1000:.1f} hit={bool(cached)} "
                    f"cumulative_ms={_elapsed_ms():.1f}"
                )
            if cached:
                import json
                data = json.loads(cached)
                project_name = data.get("project_name")
                plan_name = data.get("plan_name")
                if perf:
                    print(
                        f"[PERF][react] project_plan_lookup_l2_hit redis_key={redis_key} "
                        f"cumulative_ms={_elapsed_ms():.1f}"
                    )
                # 写入 L1 内存缓存
                if ttl > 0:
                    with _react_project_plan_name_cache_lock:
                        _react_project_plan_name_cache[key] = (project_name, plan_name, now)
                return project_name, plan_name
        except Exception as e:
            if perf:
                print(
                    f"[PERF][react] project_plan_lookup_redis_error={e} "
                    f"cumulative_ms={_elapsed_ms():.1f}"
                )
    
    # L3: 查库
    project_name: Optional[str] = None
    plan_name: Optional[str] = None
    try:
        _t_imp0 = time.perf_counter()
        from app import app, db, Project, Plan

        if perf:
            print(
                f"[PERF][react] project_plan_lookup_l3_import_app_ms="
                f"{(time.perf_counter()-_t_imp0)*1000:.1f} cumulative_ms={_elapsed_ms():.1f}"
            )

        with app.app_context():
            if perf:
                print(
                    f"[PERF][react] project_plan_lookup_app_context_entered cumulative_ms={_elapsed_ms():.1f}"
                )
            t_db0 = time.perf_counter()
            if pid > 0:
                t_pg0 = time.perf_counter()
                project = db.session.get(Project, pid)
                t_pg1 = time.perf_counter()
                if perf:
                    print(
                        f"[PERF][react] project_plan_lookup_db_session_get_project "
                        f"ms={(t_pg1-t_pg0)*1000:.1f} pid={pid} found={project is not None} "
                        f"cumulative_ms={_elapsed_ms():.1f}"
                    )
                if project is not None:
                    t_attr0 = time.perf_counter()
                    project_name = project.name
                    if perf:
                        print(
                            f"[PERF][react] project_plan_lookup_read_project_name_attr "
                            f"ms={(time.perf_counter()-t_attr0)*1000:.1f} cumulative_ms={_elapsed_ms():.1f}"
                        )
            if plid > 0:
                t_plan0 = time.perf_counter()
                plan = db.session.get(Plan, plid)
                t_plan1 = time.perf_counter()
                if perf:
                    print(
                        f"[PERF][react] project_plan_lookup_db_session_get_plan "
                        f"ms={(t_plan1-t_plan0)*1000:.1f} plid={plid} found={plan is not None} "
                        f"cumulative_ms={_elapsed_ms():.1f}"
                    )
                if plan is not None:
                    t_pln0 = time.perf_counter()
                    plan_name = plan.name
                    if perf:
                        print(
                            f"[PERF][react] project_plan_lookup_read_plan_name_attr "
                            f"ms={(time.perf_counter()-t_pln0)*1000:.1f} cumulative_ms={_elapsed_ms():.1f}"
                        )
            if perf:
                _db_inner = (time.perf_counter() - t_db0) * 1000.0
                print(
                    f"[PERF][react] project_plan_lookup_db_ms={_db_inner:.1f} "
                    f"(app_context 内 Project/Plan 查询与读 name 合计，与旧字段同名)"
                )
    except Exception as e:
        print(f"[REACT] 获取项目/计划名称失败：{e}")
        if perf:
            print(f"[PERF][react] project_plan_lookup_l3_exception cumulative_ms={_elapsed_ms():.1f}")
    
    # 写入 L1 内存缓存
    if ttl > 0:
        _t_l1w = time.perf_counter()
        with _react_project_plan_name_cache_lock:
            _dead = [
                k
                for k, (_, _, t0) in _react_project_plan_name_cache.items()
                if now - t0 >= ttl
            ]
            for k in _dead:
                del _react_project_plan_name_cache[k]
            _react_project_plan_name_cache[key] = (project_name, plan_name, now)
        if perf:
            print(
                f"[PERF][react] project_plan_lookup_l1_write_ms="
                f"{(time.perf_counter()-_t_l1w)*1000:.1f} cumulative_ms={_elapsed_ms():.1f}"
            )
    
    # 写入 L2 Redis 缓存
    if redis_client is not None and ttl > 0:
        try:
            import json
            _t_rw = time.perf_counter()
            redis_client.setex(redis_key, int(ttl), json.dumps({
                "project_name": project_name,
                "plan_name": plan_name,
            }))
            if perf:
                print(
                    f"[PERF][react] project_plan_lookup_redis_setex "
                    f"ms={(time.perf_counter()-_t_rw)*1000:.1f} cumulative_ms={_elapsed_ms():.1f}"
                )
        except Exception:
            pass
    
    if perf:
        print(
            f"[PERF][react] project_plan_lookup_total_ms={_elapsed_ms():.1f} "
            f"project_name={'set' if project_name else 'none'} plan_name={'set' if plan_name else 'none'}"
        )
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


def _unified_thinking_is_tool_meta_only(s: str) -> bool:
    """模型把「没有合适工具、应自然语言回复」等决策说明写进 thinking，勿当作用户可见气泡。"""
    if not s or not isinstance(s, str):
        return False
    t = s.strip()
    if len(t) < 14:
        return False
    if "工具" in t and (
        "没有" in t
        or "不适合" in t
        or "无需调用" in t
        or "不调用" in t
        or "不存在" in t
        or "无适合" in t
    ):
        return True
    if "自然语言" in t and ("回复" in t or "回答" in t or "互动" in t):
        return True
    if "未提出" in t and ("需求" in t or "任务" in t):
        return True
    if "从现有" in t and "工具" in t:
        return True
    if "应以" in t and "自然语言" in t:
        return True
    if "应该" in t and "自然语言" in t and "回复" in t:
        return True
    return False


def _unified_chitchat_fallback_summary(llm_response: str, parsed_thinking: str) -> str:
    """
    统一流模型未给出 execute+tool 时（例如千帆只返回 {"category":"other_request_not_matched"}），
    避免前端走「统一总结 + steps_count=1」导致 finalResponse 被挡、界面像卡住。
    """
    base = (parsed_thinking or "").strip()
    if base and not _unified_thinking_is_tool_meta_only(base):
        return base
    if not llm_response or not isinstance(llm_response, str):
        return "（未收到可展示的模型输出；若为闲聊，可稍后重试或更换模型。）"
    t = llm_response.strip()
    t = re.sub(r"```(?:json)?\s*[\s\S]*?```", "", t, flags=re.IGNORECASE | re.DOTALL).strip()
    if t:
        return t
    try:
        raw = llm_response.strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE)
        inner = (m.group(1) if m else raw).strip()
        obj = json.loads(inner) if inner else None
        if isinstance(obj, dict):
            cat = str(obj.get("category") or "").strip()
            if cat == "other_request_not_matched":
                return (
                    "已识别为日常对话/非项目操作类请求；当前 Agent 模式按统一协议未调用工具。"
                    "你可以继续说明要在本项目中执行的操作（如检索、改 Bug 状态），或改用普通对话模式。"
                )
            if cat:
                return f"（意图分类：{cat}；未生成工具调用。请补充具体操作需求。）"
    except Exception:
        pass
    return "（模型未按统一协议返回决策；请重试或更换模型。）"


def _unified_finding_line(tool_name: str, observation: Any) -> str:
    """统一流 ``done.findings`` 单行摘要（非 LLM）。"""
    if not isinstance(observation, dict):
        return f"{tool_name}：完成"
    if observation.get("success") is False:
        err = observation.get("error") or observation.get("message") or "失败"
        return f"{tool_name}：{err}"
    summ = observation.get("summary") or observation.get("message")
    if isinstance(summ, str) and summ.strip():
        return f"{tool_name}：{summ.strip()[:800]}"
    return f"{tool_name}：成功"


def _normalize_unified_stream_tool_observation(obs: Any) -> Dict[str, Any]:
    """统一流工具结果须为 dict；None 会在 SSE 上被包成「无返回数据」，且下游 ``.get`` 会崩。"""
    if obs is None:
        return {
            "success": False,
            "error": "工具返回空结果",
            "message": "工具返回空结果",
        }
    if not isinstance(obs, dict):
        try:
            snippet = str(obs)
        except Exception:
            snippet = ""
        return {
            "success": False,
            "error": f"工具返回非字典: {type(obs).__name__}",
            "message": (snippet[:500] if snippet else "工具返回非字典"),
        }
    return obs


def _client_shell_excludes_local_bridge(shell: Optional[Dict[str, Any]]) -> bool:
    """桌面版或浏览器已连接 go-local-proxy 时不再向模型暴露 client_local_bridge。"""
    if not isinstance(shell, dict):
        return False
    if shell.get("is_electron") is True:
        return True
    if shell.get("local_proxy_ok") is True:
        return True
    return False


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
        if t in ("bug", "badcase", "card", "plan"):
            return t
        return "badcase"

    @staticmethod
    def _modify_target_from_card_grep_row(
        row: Any,
    ) -> Optional[Tuple[str, int, Optional[int]]]:
        from agents.intent.resolution import infer_source_tuple_from_card_dict

        return infer_source_tuple_from_card_dict(row)

    @staticmethod
    def _react_modify_grep_multi_batch_enabled() -> bool:
        v = (os.getenv("REACT_MODIFY_GREP_MULTI_BATCH", "1") or "1").strip().lower()
        return v not in ("0", "false", "no", "off", "")

    @staticmethod
    def _react_modify_grep_expand_single_id_to_batch_enabled() -> bool:
        """grep 多条命中但模型只传 target_id 为其中一条时，是否扩展为整批 target_ids（默认开）。"""
        v = (
            os.getenv("REACT_MODIFY_GREP_EXPAND_SINGLE_ID_TO_BATCH", "1") or "1"
        ).strip().lower()
        return v not in ("0", "false", "no", "off", "")

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

    def _enrich_modify_params_target_ids(
        self,
        params: Dict[str, Any],
        result_context: Dict[str, Any],
        target_type: str,
        *,
        log_prefix: str = "",
    ) -> None:
        """
        白名单模型传入的 target_ids / target_id 数组；grep 列表非空时只保留列表内 id。
        grep 多条命中时：未带 id 则注入 target_ids；仅带一条 target_id 且为该批成员之一时，
        默认扩展为整批 target_ids（REACT_MODIFY_GREP_EXPAND_SINGLE_ID_TO_BATCH=0 可关）。
        """
        ctx_ids = self._context_row_ids_for_modify_target(result_context, target_type)
        ctx_set = set(ctx_ids)

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
            and self._react_modify_grep_multi_batch_enabled()
        ):
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
        if inferred in ("bug", "badcase", "testcase", "card", "plan"):
            by_t = [x for x in items if self._normalize_modify_target(x.get("target")) == inferred]
            if by_t:
                items = by_t
        else:
            # 关键词弱过滤（未明确意图时）
            if user_text_implies_bug_entity_type(text):
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
        from llm.qwen_llm import QwenLLM, qwen_suppress_thinking_tls_ctx

        if isinstance(self.llm, QwenLLM):
            with qwen_suppress_thinking_tls_ctx():
                yield
        else:
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

    def _react_vision_images_for_llm(self) -> Optional[List[Dict[str, Any]]]:
        """
        将本轮用户上传的图片附带到 LLM（OpenAI 兼容 image_url）。
        轮次预算见 REACT_VISION_IMAGE_ATTACH_ROUNDS，避免每轮 observe 重复塞大图。
        """
        raw = getattr(self, "_react_stream_images", None)
        if not raw:
            return None
        try:
            budget = int(getattr(self, "_react_stream_images_round_budget", 0) or 0)
        except (TypeError, ValueError):
            budget = 0
        if budget <= 0:
            return None
        self._react_stream_images_round_budget = budget - 1
        return list(raw)

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

        imgs = self._react_vision_images_for_llm()
        fn = getattr(self.llm, "chat_stream_with_reasoning", None)
        if callable(fn):
            _kw: Dict[str, Any] = {}
            if max_tokens is not None:
                try:
                    if "max_tokens" in inspect.signature(fn).parameters:
                        _kw["max_tokens"] = max_tokens
                except (TypeError, ValueError):
                    pass
            if imgs is not None:
                try:
                    if "images" in inspect.signature(fn).parameters:
                        _kw["images"] = imgs
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
            if imgs is not None:
                try:
                    if "images" in inspect.signature(fb).parameters:
                        _kw2["images"] = imgs
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

        from llm.qwen_llm import QwenLLM, qwen_suppress_thinking_tls_ctx

        _is_qwen = isinstance(self.llm, QwenLLM)
        imgs = self._react_vision_images_for_llm()

        # Qwen：线程局部标记 content_only，勿改实例 force_disable_thinking（避免与主循环 think 并发互相污染）
        # 非 Qwen：仍须在迭代 LLM 流时保持 force_disable_thinking
        fn = getattr(self.llm, "chat_stream", None)
        if callable(fn):
            stream_kw: Dict[str, Any] = {}
            if max_tokens is not None:
                try:
                    if "max_tokens" in inspect.signature(fn).parameters:
                        stream_kw["max_tokens"] = max_tokens
                except (TypeError, ValueError):
                    pass
            if imgs is not None:
                try:
                    if "images" in inspect.signature(fn).parameters:
                        stream_kw["images"] = imgs
                except (TypeError, ValueError):
                    pass

            def _gen():
                def _core():
                    try:
                        if hasattr(self.llm, "force_disable_thinking") and not _is_qwen:
                            setattr(self.llm, "force_disable_thinking", True)
                        try:
                            for piece in fn(prompt, history, **stream_kw):
                                if isinstance(piece, str) and piece:
                                    yield {"type": "content_delta", "delta": piece}
                        except Exception as e:
                            yield {"type": "content_delta", "delta": f"Error: {e}"}
                        yield {"type": "done"}
                    finally:
                        if hasattr(self.llm, "force_disable_thinking") and not _is_qwen:
                            setattr(self.llm, "force_disable_thinking", False)

                if _is_qwen:

                    def _wrapped():
                        with qwen_suppress_thinking_tls_ctx():
                            yield from _core()

                    return _wrapped()
                return _core()

            return _gen()
        fn2 = getattr(self.llm, "chat_stream_with_reasoning", None)
        if callable(fn2):

            def _gen2():
                def _core2():
                    try:
                        if hasattr(self.llm, "force_disable_thinking") and not _is_qwen:
                            setattr(self.llm, "force_disable_thinking", True)
                        try:
                            _f2_kw: Dict[str, Any] = {}
                            if max_tokens is not None:
                                try:
                                    if "max_tokens" in inspect.signature(fn2).parameters:
                                        _f2_kw["max_tokens"] = max_tokens
                                except (TypeError, ValueError):
                                    pass
                            if imgs is not None:
                                try:
                                    if "images" in inspect.signature(fn2).parameters:
                                        _f2_kw["images"] = imgs
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
                        if hasattr(self.llm, "force_disable_thinking") and not _is_qwen:
                            setattr(self.llm, "force_disable_thinking", False)

                if _is_qwen:

                    def _wrapped2():
                        with qwen_suppress_thinking_tls_ctx():
                            yield from _core2()

                    return _wrapped2()
                return _core2()

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

    async def _stream_llm_text_with_reasoning(self, prompt: str):
        """
        流式收集 LLM 输出（content + reasoning），边收边 yield 结构化事件：
          {"type":"content","delta":"..."} / {"type":"reasoning","delta":"..."} / {"type":"error","message":"..."}
        仅用于需要呈现 reasoning 的链路（如 unified 流）；避免改动旧调用方对 _stream_llm_text 的假设（只产出 str）。
        """
        q: asyncio.Queue = asyncio.Queue()
        DONE = object()
        main_loop = asyncio.get_running_loop()

        def _sync_producer():
            try:
                for item in self._resolve_chat_stream_iter(prompt):
                    if not isinstance(item, dict):
                        continue
                    t = item.get("type")
                    if t == "content_delta":
                        d = item.get("delta") or ""
                        if d:
                            asyncio.run_coroutine_threadsafe(
                                q.put({"type": "content", "delta": str(d)}), main_loop
                            )
                    elif t == "reasoning_delta":
                        d = item.get("delta")
                        if isinstance(d, str) and d:
                            asyncio.run_coroutine_threadsafe(
                                q.put({"type": "reasoning", "delta": d}), main_loop
                            )
            except Exception as e:
                asyncio.run_coroutine_threadsafe(
                    q.put({"type": "error", "message": f"{e}"}), main_loop
                )
            finally:
                asyncio.run_coroutine_threadsafe(q.put(DONE), main_loop)

        threading.Thread(target=_sync_producer, daemon=True).start()

        while True:
            item = await q.get()
            if item is DONE:
                break
            if isinstance(item, dict):
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
        _fc_imgs = self._react_vision_images_for_llm()
        messages = [{"role": "user", "content": openai_style_user_content(prompt_fc, _fc_imgs)}]
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
        _fc_imgs = self._react_vision_images_for_llm()
        messages = [{"role": "user", "content": openai_style_user_content(prompt_fc, _fc_imgs)}]
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
        _fc_imgs = self._react_vision_images_for_llm()
        messages = [{"role": "user", "content": openai_style_user_content(prompt_fc, _fc_imgs)}]
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
        _fc_imgs = self._react_vision_images_for_llm()
        messages = [{"role": "user", "content": openai_style_user_content(prompt_fc, _fc_imgs)}]
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
                    # 是否在该流阶段保留模型 reasoning_delta：
                    # - 历史默认：observe/summary 走 content-only（会 force_disable_thinking），因此不会有 reasoning_delta
                    # - 新策略：允许 observe/decide/think 呈现 reasoning（若模型支持），summary 仍默认 content-only
                    _show_reasoning = (os.getenv("REACT_SHOW_REASONING", "1") or "1").strip().lower() not in (
                        "0",
                        "false",
                        "no",
                        "off",
                    )
                    _use_co = (stream_kind in ("summary",)) or (stream_kind == "observe" and not _show_reasoning)
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
            # 流结束收口：显式通知前端本段 agent_thought/reasoning 已完成（用于收敛等待态/冻结耗时/自动折叠等）
            # 注意：不同模型 reasoning/content 先后不一，靠“没新 token”会造成 UI 误判；用 done 事件更稳。
            try:
                if stream_kind in ("think", "decide", "observe"):
                    ev_done: Dict[str, Any] = {"event": "agent_thought_done", "segment": stream_kind}
                    if step_index is not None:
                        ev_done["index"] = step_index
                    yield ev_done
            except Exception:
                pass
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

    async def _wait_for_background_summary(self, state: Dict[str, Any], max_wait: Optional[float] = None) -> None:
        """等待后台增量总结线程完成，更新 state。

        旧实现只 busy-wait 约 3s 后对队列 ``get_nowait`` 一轮；此时 LLM 往往仍在输出，
        ``running_summary_state["text"]`` 会变成半句（例如停在括号前）。现改为
        ``thread.join(timeout)``（默认 90s，``REACT_BACKGROUND_SUMMARY_JOIN_TIMEOUT``）后再排空队列直至 ``DONE``。
        """
        _last_thread = state.get("_last_summary_thread")
        if not _last_thread:
            return
        _thr, _q, _DONE, _ver = _last_thread
        if max_wait is None:
            try:
                max_wait = float((os.getenv("REACT_BACKGROUND_SUMMARY_JOIN_TIMEOUT") or "90").strip())
            except Exception:
                max_wait = 90.0
        max_wait = max(5.0, min(max_wait, 600.0))

        loop = asyncio.get_running_loop()

        def _join_worker() -> None:
            _thr.join(timeout=max_wait)

        await loop.run_in_executor(None, _join_worker)

        def _drain_queue_parts() -> List[str]:
            parts: List[str] = []
            while True:
                try:
                    _item = _q.get_nowait()
                except queue.Empty:
                    break
                if _item is _DONE:
                    break
                if isinstance(_item, dict) and _item.get("type") == "content_delta":
                    _d = _item.get("delta") or ""
                    if _d:
                        parts.append(str(_d))
            return parts

        _full_parts: List[str] = _drain_queue_parts()

        # join 超时后线程仍可能在收尾；短轮询补取尾部 delta（最多再等 ~30s）
        if _thr.is_alive():
            _grace_until = time.time() + 30.0
            while _thr.is_alive() and time.time() < _grace_until:
                await asyncio.sleep(0.12)
                _full_parts.extend(_drain_queue_parts())

        _ft = "".join(_full_parts).strip()
        if _ft:
            state["text"] = _ft
            state["version"] = _ver
        print(
            f"[INCR-SUM] wait_for_background: thread_alive={_thr.is_alive()} "
            f"join_timeout_s={max_wait:.0f} result_chars={len(_ft)}"
        )

    async def _merge_running_summary_incremental_silent(
        self,
        state: Dict[str, Any],
        step_index: int,
        tool: str,
        todo: str,
        nl_obs: str,
        background: bool = False,
    ) -> None:
        """每步结束后仅后台合并运行总览，更新 state；不向 SSE 推流（避免中途半篇展示）。
        background=True: 真正后台执行，不阻塞主循环（主循环结束后需检查结果）
        """
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
            _w_start = time.time()
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
                print(f"[INCR-SUM] worker done: step={step_index} tool={tool} llm_s={time.time() - _w_start:.2f}")

        _t_start = time.time()
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        
        if background:
            # Fire-and-forget: 后台执行，不阻塞主循环
            # 存引用以便主循环结束时检查（可选）
            state["_last_summary_thread"] = (thread, q, DONE, next_ver)
            print(f"[INCR-SUM] step={step_index} tool={tool} background=True launched")
            return
        
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
        # 终局运行总览切片下发前有清空 reset + 分片间隔，前端先发 loading 避免长时间空白像「卡住」
        yield {"event": "unified_summary_loading", "active": True}
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
            if mapped in ('grep', 'modify', 'create', 'copy'):
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
                    elif user_input and (
                        user_text_implies_bug_entity_type(user_input) or '缺陷' in user_input
                    ):
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
                elif mapped == 'copy':
                    params.setdefault('target', 'bug')
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
            elif any(k in t for k in ('复制', '拷贝')) or (t.startswith('copy ') or ' copy ' in f' {t} '):
                tool_name = 'copy'
                todo_params['tool'] = 'copy'
                p = todo_params.get('params') or {}
                p.setdefault('target', 'bug')
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
            self._enrich_modify_params_target_ids(
                params, result_context, target_type, log_prefix="[REACT-thought] "
            )
            target_id = params.get("target_id")
            if target_type == "card":
                cid = params.get("card_id")
                if cid is None:
                    cid = grep_result.get("first_card_id")
                if cid is None and target_id is not None:
                    cid = target_id
                if cid is None:
                    tid_c = self._try_target_id_from_merged_lists(
                        result_context, target_type, user_input, todo
                    )
                    if tid_c is not None:
                        cid = tid_c
                        print(
                            f"[REACT-thought] 从合并列表注入 card_id={cid}, target={target_type}"
                        )
                if cid is not None:
                    try:
                        params["card_id"] = int(cid)
                        params.pop("target_id", None)
                        print(
                            f"[REACT-thought] 从 grep 结果获取 card_id={params['card_id']}, target={target_type}"
                        )
                    except (TypeError, ValueError):
                        pass
            elif not params.get("target_ids") and target_id is None:
                if target_type == 'bug':
                    target_id = grep_result.get('first_bug_id')
                elif target_type == 'testcase':
                    target_id = grep_result.get('first_testcase_id')
                elif target_type == 'plan':
                    target_id = grep_result.get('first_plan_id')
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
                    try:
                        params['target_id'] = int(target_id)
                        target_id = params['target_id']
                        print(
                            f"[REACT-thought] 从 grep 结果获取 target_id={target_id}, target={target_type}"
                        )
                    except (TypeError, ValueError):
                        target_id = None
            _missing_modify_loc = (
                not params.get("target_ids")
                and params.get("target_id") is None
                and (params.get("card_id") is None if target_type == "card" else True)
            )
            if _missing_modify_loc:
                print(f"[REACT-thought] ⚠️ 无法从 grep 结果获取 target_id (target={target_type})，尝试补救 grep…")
                kw = self._extract_title_keywords_for_grep(user_input, todo) or ''
                gparams: Dict[str, Any] = {
                    'project_id': project_id,
                    'keywords': kw,
                    'mode': 'locate',
                    'target': target_type if target_type in ('bug', 'badcase', 'testcase', 'card', 'plan') else 'all',
                    'userId': 'system_agent',
                }
                if self.plan_id is not None and gparams.get('target') not in ('all', 'plan'):
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
                    if target_type == "card":
                        cid2 = grep_result.get("first_card_id")
                        if cid2 is not None:
                            try:
                                params["card_id"] = int(cid2)
                                params.pop("target_id", None)
                                print(f"[REACT-thought] 补救 grep 后 card_id={params['card_id']}")
                            except (TypeError, ValueError):
                                pass
                        if params.get("card_id") is None:
                            tid_s = self._try_target_id_from_merged_lists(
                                result_context, target_type, user_input, todo
                            )
                            if tid_s is not None:
                                params["card_id"] = int(tid_s)
                                params.pop("target_id", None)
                                print(f"[REACT-thought] 技能分支补救 grep 后从列表注入 card_id={tid_s}")
                    elif target_type == 'bug':
                        target_id = grep_result.get('first_bug_id')
                        if target_id:
                            try:
                                params['target_id'] = int(target_id)
                                print(f"[REACT-thought] 补救 grep 后 target_id={params['target_id']}")
                            except (TypeError, ValueError):
                                pass
                    elif target_type == 'testcase':
                        target_id = grep_result.get('first_testcase_id')
                        if target_id:
                            try:
                                params['target_id'] = int(target_id)
                                print(f"[REACT-thought] 补救 grep 后 target_id={params['target_id']}")
                            except (TypeError, ValueError):
                                pass
                    elif target_type == 'plan':
                        target_id = grep_result.get('first_plan_id')
                        if target_id:
                            try:
                                params['target_id'] = int(target_id)
                                print(f"[REACT-thought] 补救 grep 后 target_id={params['target_id']}")
                            except (TypeError, ValueError):
                                pass
                    else:
                        target_id = grep_result.get('first_badcase_id')
                        if target_id:
                            try:
                                params['target_id'] = int(target_id)
                                print(f"[REACT-thought] 补救 grep 后 target_id={params['target_id']}")
                            except (TypeError, ValueError):
                                pass
                    if not params.get("target_ids") and params.get('target_id') is None and target_type != "card":
                        tid_s = self._try_target_id_from_merged_lists(
                            result_context, target_type, user_input, todo
                        )
                        if tid_s is not None:
                            params['target_id'] = tid_s
                            print(f"[REACT-thought] 技能分支补救 grep 后从列表注入 target_id={tid_s}")
            if not params.get("target_ids") and params.get("target_id") is None and (
                params.get("card_id") is None if target_type == "card" else True
            ):
                self._enrich_modify_params_target_ids(
                    params, result_context, target_type, log_prefix="[REACT-thought] 技能补全后 "
                )

            tid_explore = params.get("target_id")
            if tid_explore is None and params.get("target_ids"):
                _tls = params.get("target_ids")
                if isinstance(_tls, (list, tuple)) and len(_tls) > 0:
                    try:
                        tid_explore = int(_tls[0])
                    except (TypeError, ValueError):
                        tid_explore = None
            explore_target = target_type
            if target_type == "card" and params.get("card_id") is not None and self.tools.get(
                "modify"
            ):
                mt = self.tools.get("modify")

                def _card_explore_resolve():
                    with mt._get_app_context():
                        nt, _ = mt._normalize_target_using_card_row(
                            target_type,
                            params.get("project_id"),
                            params["card_id"],
                        )
                        sid = mt._resolve_target_id_from_card_id(
                            nt,
                            params["card_id"],
                            params.get("project_id"),
                        )
                        return nt, sid

                try:
                    loop = asyncio.get_event_loop()
                    nt_e, sid_e = await asyncio.wait_for(
                        loop.run_in_executor(self._tool_executor, _card_explore_resolve),
                        timeout=10,
                    )
                    if sid_e is not None:
                        explore_target = nt_e
                        tid_explore = int(sid_e)
                except Exception as e:
                    print(f"[REACT-thought] card→源表 explore 解析失败: {e}")

            # 思考意图 + 探索记录（类似 Cursor 探索文件）：有 target_id 时先探索当前记录与用户列表，再让大模型基于探索结果确认 modifications
            if tid_explore and (not params.get('modifications') or len(params.get('modifications', {})) == 0):
                modify_tool = self.tools.get('modify')
                if modify_tool and getattr(modify_tool, 'explore_record', None):
                    try:
                        loop = asyncio.get_event_loop()
                        exploration = await asyncio.wait_for(
                            loop.run_in_executor(
                                self._tool_executor,
                                lambda: modify_tool.explore_record(
                                    explore_target,
                                    tid_explore,
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

            _ui = (user_input or "").strip()
            _td = (todo or "").strip()
            wants_copy = (
                any(token in _ui for token in ("复制", "拷贝", "一样", "相同"))
                or any(token in _td for token in ("复制", "拷贝", "一样", "相同"))
                or bool(re.search(r"(?i)\bcopy\b", _ui))
                or bool(re.search(r"(?i)\bcopy\b", _td))
                or ("duplicate" in _ui.lower())
                or ("duplicate" in _td.lower())
            )
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
                elif target_type == 'card':
                    source_id = grep_result.get('first_card_id') or result_context.get('first_card_id')
                    if source_id and not fields.get('copy_from_card_id'):
                        fields['copy_from_card_id'] = source_id

            if target_type != "plan" and isinstance(fields, dict):
                _copy_src_keys = (
                    "copy_from_bug_id",
                    "source_bug_id",
                    "copy_from_badcase_id",
                    "source_badcase_id",
                    "copy_from_testcase_id",
                    "source_testcase_id",
                    "copy_from_card_id",
                    "source_card_id",
                )
                _has_copy_fields = any(
                    fields.get(k) not in (None, "", 0, "0") for k in _copy_src_keys
                )
                _ep = fields.get("plan_id")
                if not _has_copy_fields and _ep in (None, "", 0, "0"):
                    _chosen = None
                    if params.get("plan_id") not in (None, "", 0, "0"):
                        try:
                            _chosen = int(params.get("plan_id"))
                        except (TypeError, ValueError):
                            _chosen = None
                    if (_chosen is None or _chosen <= 0) and getattr(self, "plan_id", None) not in (
                        None,
                        "",
                        0,
                        "0",
                    ):
                        try:
                            _chosen = int(self.plan_id)
                        except (TypeError, ValueError):
                            _chosen = None
                    _fp_c = grep_result.get("first_plan_id") or result_context.get("first_plan_id")
                    if (_chosen is None or _chosen <= 0) and _fp_c is not None:
                        try:
                            _chosen = int(_fp_c)
                        except (TypeError, ValueError):
                            _chosen = None
                    if _chosen is not None and _chosen > 0:
                        fields["plan_id"] = _chosen

            params['fields'] = fields
            params.setdefault('confirm', False)
            params.setdefault('natural_query', user_input)
            print(f"[REACT-planing] create 参数补齐: target={target_type}, fields={fields}")

        if tool_name == 'copy':
            grep_result = result_context.get('grep_result', {})
            target_type = params.get('target') or self._infer_create_target(user_input, todo)
            params['target'] = target_type
            if not params.get('source_id'):
                if target_type == 'bug':
                    _sid = grep_result.get('first_bug_id') or result_context.get('first_bug_id')
                elif target_type == 'badcase':
                    _sid = grep_result.get('first_badcase_id') or result_context.get('first_badcase_id')
                elif target_type == 'testcase':
                    _sid = grep_result.get('first_testcase_id') or result_context.get('first_testcase_id')
                elif target_type == 'card':
                    _sid = grep_result.get('first_card_id') or result_context.get('first_card_id')
                else:
                    _sid = None
                if _sid:
                    params['source_id'] = _sid
            extracted_title = self._extract_create_title(user_input, todo)
            if extracted_title and not params.get('title'):
                params['title'] = extracted_title
            params.setdefault('natural_query', user_input)
            print(f"[REACT-planing] copy 参数补齐: target={params.get('target')}, source_id={params.get('source_id')}")

        if tool_name == "delete":
            grep_result = result_context.get("grep_result", {})
            target_type = params.get("target") or self._infer_modify_target(user_input, todo)
            params["target"] = target_type
            params.setdefault("confirm", False)
            tt = str(target_type).strip().lower()
            if tt == "plan":
                if not params.get("plan_id"):
                    _fp = grep_result.get("first_plan_id") or result_context.get("first_plan_id")
                    if _fp is not None:
                        params["plan_id"] = int(_fp)
                if not params.get("plan_id") and getattr(self, "plan_id", None) is not None:
                    params["plan_id"] = self.plan_id
            elif tt == "card":
                if not params.get("card_id") and not params.get("target_id"):
                    _cid = grep_result.get("first_card_id") or result_context.get("first_card_id")
                    if _cid:
                        params["card_id"] = _cid
            elif not params.get("target_id"):
                if tt == "bug":
                    _tid = grep_result.get("first_bug_id") or result_context.get("first_bug_id")
                elif tt == "testcase":
                    _tid = grep_result.get("first_testcase_id") or result_context.get("first_testcase_id")
                else:
                    _tid = grep_result.get("first_badcase_id") or result_context.get("first_badcase_id")
                if _tid:
                    params["target_id"] = _tid
            print(
                f"[REACT-planing] delete 参数补齐: target={params.get('target')}, "
                f"ids={params.get('target_id') or params.get('card_id') or params.get('plan_id')}"
            )

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
        top_sum = observation.get("summary")
        data_sum = (observation.get("data") or {}).get("summary") if isinstance(observation.get("data"), dict) else None
        _data_dict = observation.get("data") if isinstance(observation.get("data"), dict) else {}
        base_nl = None
        for _s in (top_sum, data_sum):
            if isinstance(_s, str) and _s.strip():
                base_nl = _s.strip()
                break
        if base_nl is not None:
            if (tool or "").lower() == "grep":
                base_nl = enrich_grep_observation_nl_with_plan_names(base_nl, _data_dict, loc)
            return base_nl[:2000]
        if isinstance(observation.get("message"), str) and observation["message"].strip():
            msg = observation["message"].strip()
            if (tool or "").lower() == "grep":
                msg = enrich_grep_observation_nl_with_plan_names(msg, _data_dict, loc)
            return msg[:2000]
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
                pt = data.get("plan_tree") or {}
                try:
                    plan_n = int(pt.get("total_plans") or 0)
                except (TypeError, ValueError):
                    plan_n = 0
                if plan_n <= 0 and isinstance(pt.get("plans"), list):
                    plan_n = len(pt["plans"])
                has_plan_material = plan_n > 0 or data.get("plan_records_tree") is not None
                if not has_plan_material:
                    return react_summarize_grep_done_empty(loc)
                ds = data.get("summary")
                if isinstance(ds, str) and ds.strip():
                    return enrich_grep_observation_nl_with_plan_names(ds.strip(), data, loc)[:2000]
                return react_summarize_grep_done_empty(loc)
            hit_nl = react_summarize_grep_done_hits(n, bug_n, bc_n, tc_n, loc)
            return enrich_grep_observation_nl_with_plan_names(hit_nl, data, loc)
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

    async def _run_unified_xml_stream(
        self,
        user_input: str,
        project_id: int = None,
        plan_id: int = None,
        locale: Optional[str] = None,
        pending_diff_context: Optional[List[Dict[str, Any]]] = None,
        agent_session_id: Optional[str] = None,
        long_memory_prefetch: Optional[Dict[str, Any]] = None,
        hint_project_name: Optional[str] = None,
        hint_plan_name: Optional[str] = None,
        client_shell: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
    ):
        '''唯一流式引擎：三段式 XML；前置 gather 与旧链路一致。'''
        perf = (os.getenv("PERF_LOG") == "1")
        print(f"\n[REACT] unified stream engine start")
        self._ui_locale = normalize_locale(locale)
        self._client_shell = client_shell if isinstance(client_shell, dict) else None
        self._agent_session_id = (agent_session_id or "").strip() or None
        if self._agent_session_id:
            _REACT_STREAM_CANCEL_EVENTS[self._agent_session_id] = threading.Event()
        self._tool_task_event_buffer = []
        self.project_id = project_id
        self.plan_id = plan_id
        # grep 纠偏：泛查时若模型窄化 target 会跳过 Card 表，导致「无卡片命中」
        self._react_stream_user_input = user_input or ""
        self._react_stream_images = list(images) if images else None
        try:
            _rb = int((os.getenv("REACT_VISION_IMAGE_ATTACH_ROUNDS") or "5").strip())
        except ValueError:
            _rb = 5
        self._react_stream_images_round_budget = (
            max(0, min(_rb, 32)) if self._react_stream_images else 0
        )
        self._index_pending_context(pending_diff_context or [])
        _t0 = time.time()
        _total_think_time = 0.0

        try:
            # 不再发送占位文本，直接进入 gather 阶段
            _gather_t0 = time.perf_counter()

            async def _gather_to_thread(label: str, fn, *args):
                _t_task = time.perf_counter()
                if perf:
                    print(
                        f"[PERF][react] unified_gather_task_{label}_start "
                        f"since_gather_start_ms={(time.perf_counter() - _gather_t0) * 1000:.1f}"
                    )
                try:
                    return await asyncio.to_thread(fn, *args)
                finally:
                    if perf:
                        print(
                            f"[PERF][react] unified_gather_task_{label}_wall_ms="
                            f"{(time.perf_counter() - _t_task) * 1000:.1f}"
                        )

            _exclude_tools: Tuple[str, ...] = (
                ("client_local_bridge",)
                if _client_shell_excludes_local_bridge(self._client_shell)
                else ()
            )
            (project_name, plan_name), tools_info, _pending_for_llm = await asyncio.gather(
                _gather_to_thread(
                    "project_plan_names",
                    _sync_load_project_plan_names,
                    project_id,
                    plan_id,
                    perf,
                    hint_project_name,
                    hint_plan_name,
                ),
                _gather_to_thread(
                    "format_tools_for_prompt",
                    format_tools_for_prompt,
                    self.tools,
                    _exclude_tools,
                ),
                _gather_to_thread("relevant_pending_for_llm", self._relevant_pending_for_llm, user_input),
            )
            if perf:
                print(
                    f"[PERF][react] unified_gather_parallel_wall_ms="
                    f"{(time.perf_counter() - _gather_t0) * 1000:.1f} "
                    f"(≈ max(names, tools, pending)，三者并行)"
                )
        except BaseException as e:
            print(f"[REACT] unified gather 异常: {e}")
            yield {"event": "error", "message": str(e)}
            yield {
                "event": "done",
                "status": "error",
                "findings": [f"上下文准备失败：{e}"],
                "steps_count": 0,
                "duration": time.time() - _t0,
                "summary": str(e),
            }
            return

        result_ctx: Dict[str, Any] = {}
        if project_id is not None:
            result_ctx["project_id"] = project_id
            if project_name:
                result_ctx["project_name"] = project_name
        if plan_id is not None:
            result_ctx["plan_id"] = plan_id
            if plan_name:
                result_ctx["plan_name"] = plan_name
        if _pending_for_llm:
            result_ctx["pending_diff_summary"] = [
                {
                    "target": x.get("target"),
                    "target_id": x.get("target_id"),
                    "modifications": x.get("modifications") or {},
                }
                for x in _pending_for_llm
            ]

        _lm_each_msg = (
            os.getenv("REACT_LONG_MEMORY_QUERY_EACH_MESSAGE", "0") or "0"
        ).strip().lower() in ("1", "true", "yes", "on")
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
                result_ctx["long_memory_text"] = _lmt
            if isinstance(_lmi, list) and _lmi:
                result_ctx["long_memory_items"] = _lmi
        elif _lm_each_msg:
            _lm_t0 = time.perf_counter()
            await self._inject_long_memory_into_context(
                user_input=user_input,
                result_context=result_ctx,
                project_id=project_id,
                plan_id=plan_id,
                agent_session_id=self._agent_session_id,
            )
            if perf:
                print(
                    f"[PERF][react] unified_long_memory_inject_ms="
                    f"{(time.perf_counter() - _lm_t0) * 1000:.1f}"
                )

        _cs = getattr(self, "_client_shell", None)
        if isinstance(_cs, dict):
            _co = str(_cs.get("os") or _cs.get("client_os") or "").strip().lower()
            if _co == "win":
                _co = "windows"
            if _co:
                result_ctx["client_os"] = _co

        _max_rounds = _react_max_rounds_cap()
        prev_observation: Optional[Dict[str, Any]] = None
        prev_action: Optional[Dict[str, Any]] = None

        _done_sent = False
        findings_acc: List[str] = []
        _steps_done = 0
        running_summary_state: Dict[str, Any] = {"text": "", "version": 0}
        unified_plan_steps: List[str] = []
        _plan_step_idx = 0
        _plan_step_fail_streak = 0
        _dup_win = _react_duplicate_action_window()
        _plan_step_max_fail = _react_plan_step_max_retries()
        _sig_history: deque = deque(maxlen=_dup_win)
        _unified_round_for_debug: int = -1
        try:
            for round_idx in range(_max_rounds):
                _unified_round_for_debug = round_idx
                if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                    print(f"[REACT-UNIFIED] round {round_idx + 1}/{_max_rounds}")
                if self._agent_session_id:
                    _cev = _REACT_STREAM_CANCEL_EVENTS.get(self._agent_session_id)
                    if _cev is not None and _cev.is_set():
                        if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                            print(
                                f"[REACT-UNIFIED] cancelled by client request_id={self._agent_session_id}",
                                flush=True,
                            )
                        yield {
                            "event": "finished",
                            "finished": True,
                            "steps_count": _steps_done,
                            "duration": time.time() - _t0,
                            "thinking_time": _total_think_time,
                        }
                        yield {
                            "event": "done",
                            "status": "cancelled",
                            "findings": findings_acc,
                            "steps_count": _steps_done,
                            "duration": time.time() - _t0,
                            "thinking_time": _total_think_time,
                            "summary": "用户已停止生成",
                        }
                        _done_sent = True
                        return
                if unified_plan_steps:
                    if _plan_step_idx < len(unified_plan_steps):
                        _round_todo = unified_plan_steps[_plan_step_idx]
                    else:
                        _round_todo = f"继续执行（已列出 {len(unified_plan_steps)} 步）"
                    yield {
                        "event": "todo_start",
                        "index": round_idx,
                        "step_id": _plan_step_idx + 1,
                        "todo": _round_todo,
                        "planned": True,
                        "expand_plan": True,
                        "todo_skip": round_idx == 0,
                    }
                else:
                    _round_todo = (
                        "理解需求并执行工具（检索 / 修改等）"
                        if round_idx == 0
                        else f"第 {round_idx + 1} 步：根据上下文继续执行"
                    )
                    yield {
                        "event": "todo_start",
                        "index": round_idx,
                        "step_id": round_idx + 1,
                        "todo": _round_todo,
                        "planned": False,
                        "expand_plan": False,
                        "todo_skip": True,
                    }
                _snap_rounds = _unified_snapshot_rounds_1based()
                if _snap_rounds is not None and (round_idx + 1) in _snap_rounds:
                    _print_unified_round_prompt_snapshot(
                        round_idx,
                        result_ctx,
                        prev_observation,
                        prev_action,
                    )
                _prompt_round_idx = _plan_step_idx if unified_plan_steps else round_idx
                base_unified_prompt = self._wrap_prompt(
                    ReactPromptTemplates.react_unified_prompt(
                        user_input=user_input,
                        available_tools=tools_info,
                        context=result_ctx,
                        round_idx=_prompt_round_idx,
                        prev_observation=prev_observation,
                        prev_action=prev_action,
                        plan_hints=None,
                        todo="",
                        scheduled_plan=unified_plan_steps if unified_plan_steps else None,
                        first_round_task_plan=_unified_first_round_task_plan_enabled(),
                        ui_locale=getattr(self, "_ui_locale", None),
                    )
                )
                yield {
                    "event": "phase_wait",
                    "index": round_idx,
                    "active": True,
                    "kind": "unified_round_think",
                    "message": react_phase_wait_message(
                        "unified_round_think", getattr(self, "_ui_locale", None)
                    ),
                }
                unified_prompt = base_unified_prompt
                llm_parts: List[str] = []
                _think_start = time.time()
                # 对外 SSE：块级状态机 + 语义标记（见 unified_think_stream_sanitize），原文仍进 llm_parts 供 parse_unified_response
                _think_san = create_unified_think_sanitizer(getattr(self, "_ui_locale", None))
                _markers_unified = react_unified_sse_xml_markers(getattr(self, "_ui_locale", None))
                _thinking_start_vis = str(_markers_unified.get("thinking_start") or "")
                _thinking_end_vis = str(_markers_unified.get("thinking_end") or "")
                _observation_start_vis = str(_markers_unified.get("observation_start") or "")
                _observation_end_vis = str(_markers_unified.get("observation_end") or "")
                _decision_start_vis = str(_markers_unified.get("decision_start") or "")
                _decision_end_vis = str(_markers_unified.get("decision_end") or "")
                _think_sse_parts: List[str] = []
                _unified_seg: Optional[str] = None  # thinking | observation | decision
                try:
                    _min_sse = max(
                        1,
                        int((os.getenv("REACT_UNIFIED_THINK_SSE_MIN_CHARS") or "4").strip() or "4"),
                    )
                except Exception:
                    _min_sse = 4

                def _react_phase_for_segment() -> str:
                    if _unified_seg == "observation":
                        return REACT_PHASE_OBSERVE
                    if _unified_seg == "decision":
                        return REACT_PHASE_DECIDE
                    return REACT_PHASE_THINK

                def _think_sse_flush() -> Optional[Dict[str, Any]]:
                    if not _think_sse_parts:
                        return None
                    d = "".join(_think_sse_parts)
                    _think_sse_parts.clear()
                    return {
                        "event": "agent_thought",
                        "delta": d,
                        "index": round_idx,
                        "processType": PROCESS_TYPE_STREAMING,
                        "react_phase": _react_phase_for_segment(),
                    }

                def _think_sse_append_text_all(s: str):
                    for ch in s:
                        _think_sse_parts.append(ch)
                        if sum(len(x) for x in _think_sse_parts) >= _min_sse:
                            ev = _think_sse_flush()
                            if ev:
                                yield ev

                def _emit_subprocess_end(react_ph: str) -> Dict[str, Any]:
                    out: Dict[str, Any] = {
                        "event": "agent_thought",
                        "delta": "",
                        "index": round_idx,
                        "processType": PROCESS_TYPE_END,
                        "react_phase": react_ph,
                    }
                    if react_ph == REACT_PHASE_THINK:
                        out["think_status"] = THINK_STREAM_STATUS_END
                    return out

                def _emit_think_block_closed() -> Dict[str, Any]:
                    """</thinking>：思考子过程结束（正文里不再下发 thinking_end 标记）。"""
                    nonlocal _unified_seg
                    _unified_seg = None
                    return {
                        "event": "agent_thought",
                        "delta": "",
                        "index": round_idx,
                        "processType": PROCESS_TYPE_END,
                        "react_phase": REACT_PHASE_THINK,
                        "think_status": THINK_STREAM_STATUS_END,
                    }

                def _emit_piece_split_end_markers(piece: str, d_pw: Optional[str] = None):
                    """按 thinking/observation/decision 结束标记切分；标记本身不下发。"""
                    nonlocal _unified_seg
                    
                    # 通过 d_pw 直接识别结束阶段
                    if d_pw in ("thinking_end", "observation_end", "decision_end", "task_plan_end"):
                        _ev = _think_sse_flush()
                        if _ev:
                            yield _ev
                        if d_pw == "thinking_end":
                            yield _emit_think_block_closed()
                        elif d_pw == "task_plan_end":
                            # task_plan 结束后保持当前阶段不变（可在 thinking 或 decision 中）
                            pass
                        elif d_pw == "observation_end":
                            _unified_seg = None
                            yield _emit_subprocess_end(REACT_PHASE_OBSERVE)
                        elif d_pw == "decision_end":
                            _unified_seg = None
                            yield _emit_subprocess_end(REACT_PHASE_DECIDE)
                        # 结束标记为空字符串时不输出
                        if piece:
                            yield from _think_sse_append_text_all(piece)
                        return
                    
                    # 兼容旧逻辑：通过标记文本识别
                    ends = [
                        (_thinking_end_vis, REACT_PHASE_THINK, "_think"),
                        (_observation_end_vis, REACT_PHASE_OBSERVE, "_obs"),
                        (_decision_end_vis, REACT_PHASE_DECIDE, "_dec"),
                    ]
                    # 如果 piece 为空且所有结束标记都为空，说明是结束标记本身
                    # 此时需要触发阶段结束逻辑
                    if not piece:
                        # 检查是否有空的结束标记
                        for s, rp, _k in ends:
                            if s == "":
                                _ev = _think_sse_flush()
                                if _ev:
                                    yield _ev
                                if rp == REACT_PHASE_THINK:
                                    yield _emit_think_block_closed()
                                else:
                                    _unified_seg = None
                                    yield _emit_subprocess_end(rp)
                                return
                        return
                    work = piece
                    while work:
                        best_at = None
                        best_s = ""
                        best_rp = REACT_PHASE_THINK
                        for s, rp, _k in ends:
                            if not s or s not in work:
                                continue
                            at = work.index(s)
                            if best_at is None or at < best_at:
                                best_at = at
                                best_s = s
                                best_rp = rp
                        if best_at is None:
                            yield from _think_sse_append_text_all(work)
                            return
                        before = work[:best_at]
                        if before:
                            yield from _think_sse_append_text_all(before)
                        _ev = _think_sse_flush()
                        if _ev:
                            yield _ev
                        if best_rp == REACT_PHASE_THINK:
                            yield _emit_think_block_closed()
                        else:
                            _unified_seg = None
                            yield _emit_subprocess_end(best_rp)
                        work = work[best_at + len(best_s) :]

                def _emit_sanitizer_piece(piece: str, d_pw: Optional[str]):
                    nonlocal _unified_seg
                    
                    # 处理 phase_wait 事件 (decision 阶段)
                    if d_pw == "start":
                        yield {
                            "event": "phase_wait",
                            "index": round_idx,
                            "active": True,
                            "kind": "unified_action_xml",
                            "message": react_phase_wait_message(
                                "decision_xml_parse", getattr(self, "_ui_locale", None)
                            ),
                        }
                    elif d_pw == "end":
                        yield {
                            "event": "phase_wait",
                            "index": round_idx,
                            "active": False,
                            "kind": "unified_action_xml",
                        }
                    
                    # 处理开始标记（通过 d_pw 识别阶段）
                    if d_pw in ("thinking_start", "observation_start", "decision_start"):
                        _ev = _think_sse_flush()
                        if _ev:
                            yield _ev
                        # 设置阶段
                        if d_pw == "thinking_start":
                            _unified_seg = "thinking"
                        elif d_pw == "observation_start":
                            _unified_seg = "observation"
                        elif d_pw == "decision_start":
                            _unified_seg = "decision"
                        # 标记为空字符串时不输出，只做阶段切换
                        if piece:
                            yield from _think_sse_append_text_all(piece)
                        return
                    
                    # 处理结束标记（通过 d_pw 识别阶段）
                    if d_pw in ("thinking_end", "observation_end", "decision_end", "task_plan_end"):
                        yield from _emit_piece_split_end_markers(piece, d_pw)
                        return
                    
                    # 兼容旧逻辑：通过标记文本识别（非空标记时）
                    if piece == _thinking_start_vis and piece:
                        _ev = _think_sse_flush()
                        if _ev:
                            yield _ev
                        _unified_seg = "thinking"
                        yield from _think_sse_append_text_all(piece)
                        return
                    if piece == _observation_start_vis and piece:
                        _ev = _think_sse_flush()
                        if _ev:
                            yield _ev
                        _unified_seg = "observation"
                        yield from _think_sse_append_text_all(piece)
                        return
                    if piece == _decision_start_vis and piece:
                        _ev = _think_sse_flush()
                        if _ev:
                            yield _ev
                        _unified_seg = "decision"
                        yield from _think_sse_append_text_all(piece)
                        return
                    
                    # 兼容旧逻辑：有内容的结束标记
                    if any(
                        m and m in piece
                        for m in (_thinking_end_vis, _observation_end_vis, _decision_end_vis)
                        if m
                    ):
                        yield from _emit_piece_split_end_markers(piece, None)
                        return
                    
                    # 普通内容
                    if not piece:
                        return
                    yield from _think_sse_append_text_all(piece)

                try:
                    yield {
                        "event": "agent_thought",
                        "delta": "",
                        "index": round_idx,
                        "think_status": THINK_STREAM_STATUS_START,
                        "processType": PROCESS_TYPE_STREAMING,
                        "react_phase": REACT_PHASE_THINK,
                    }
                    async for it in self._stream_llm_text_with_reasoning(unified_prompt):
                        if not isinstance(it, dict):
                            continue
                        if it.get("type") == "reasoning":
                            d = it.get("delta") or ""
                            if d:
                                yield {
                                    "event": "reasoning",
                                    "content": str(d),
                                    "react_phase": REACT_PHASE_THINK,
                                    "index": round_idx,
                                }
                            continue
                        if it.get("type") == "error":
                            em = it.get("message") or "unknown"
                            llm_parts.append(f"Error: {em}")
                            break
                        if it.get("type") != "content":
                            continue
                        chunk = it.get("delta") or ""
                        if not chunk:
                            continue
                        llm_parts.append(chunk)
                        for piece, d_pw in _think_san.feed(chunk):
                            for _ev in _emit_sanitizer_piece(piece, d_pw):
                                yield _ev
                        _ev = _think_sse_flush()
                        if _ev:
                            yield _ev
                    for piece, d_pw in _think_san.feed(""):
                        for _ev in _emit_sanitizer_piece(piece, d_pw):
                            yield _ev
                    for piece, d_pw in _think_san.end():
                        for _ev in _emit_sanitizer_piece(piece, d_pw):
                            yield _ev
                    _ev = _think_sse_flush()
                    if _ev:
                        yield _ev
                finally:
                    pass
                llm_response = "".join(llm_parts)
                parsed = parse_unified_response(llm_response)
                _parse_max = _unified_parse_retry_max()
                if _unified_should_retry_parse(parsed, 0, _parse_max):
                    _retry_extra = react_unified_strict_format_retry_suffix(
                        getattr(self, "_ui_locale", None)
                    )
                    _hint = (
                        "正在按严格格式重试本轮输出…\n\n"
                        if not is_english_locale(getattr(self, "_ui_locale", None))
                        else "Retrying with strict XML format…\n\n"
                    )
                    yield {
                        "event": "agent_thought",
                        "delta": _hint,
                        "index": round_idx,
                        "processType": PROCESS_TYPE_STREAMING,
                        "react_phase": REACT_PHASE_THINK,
                    }
                    if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                        print(
                            "[REACT-UNIFIED] parse retry: appending strict format reminder",
                            flush=True,
                        )
                    unified_prompt = base_unified_prompt + _retry_extra
                    llm_parts = []
                    _think_san = create_unified_think_sanitizer(getattr(self, "_ui_locale", None))
                    _think_sse_parts.clear()
                    _unified_seg = None
                    try:
                        async for it in self._stream_llm_text_with_reasoning(unified_prompt):
                            if not isinstance(it, dict):
                                continue
                            if it.get("type") == "reasoning":
                                d = it.get("delta") or ""
                                if d:
                                    yield {
                                        "event": "reasoning",
                                        "content": str(d),
                                        "react_phase": REACT_PHASE_THINK,
                                        "index": round_idx,
                                    }
                                continue
                            if it.get("type") == "error":
                                em = it.get("message") or "unknown"
                                llm_parts.append(f"Error: {em}")
                                break
                            if it.get("type") != "content":
                                continue
                            chunk = it.get("delta") or ""
                            if not chunk:
                                continue
                            llm_parts.append(chunk)
                            for piece, d_pw in _think_san.feed(chunk):
                                for _ev in _emit_sanitizer_piece(piece, d_pw):
                                    yield _ev
                            _ev = _think_sse_flush()
                            if _ev:
                                yield _ev
                        for piece, d_pw in _think_san.feed(""):
                            for _ev in _emit_sanitizer_piece(piece, d_pw):
                                yield _ev
                        for piece, d_pw in _think_san.end():
                            for _ev in _emit_sanitizer_piece(piece, d_pw):
                                yield _ev
                        _ev = _think_sse_flush()
                        if _ev:
                            yield _ev
                    finally:
                        pass
                    llm_response = "".join(llm_parts)
                    parsed = parse_unified_response(llm_response)
                _think_time = time.time() - _think_start
                _total_think_time += _think_time
                yield {
                    "event": "phase_wait",
                    "index": round_idx,
                    "active": False,
                    "kind": "unified_round_think",
                }
                if _unified_plan_diag_enabled():
                    _raw = llm_response or ""
                    _has_tp = "<task_plan" in _raw.lower()
                    _ps_dbg = parsed.get("plan_steps")
                    _n_ps = len(_ps_dbg) if isinstance(_ps_dbg, list) else -1
                    print(
                        "[REACT-UNIFIED][plan-diag] "
                        f"round={round_idx} llm_chars={len(_raw)} "
                        f"raw_has_task_plan_tag={_has_tp} parsed_plan_steps_n={_n_ps} "
                        f"first_round_task_plan_env={_unified_first_round_task_plan_enabled()} "
                        f"already_unified_plan_steps={bool(unified_plan_steps)}",
                        flush=True,
                    )
                    if isinstance(_ps_dbg, list) and _ps_dbg:
                        for _pi, _st in enumerate(_ps_dbg[:24]):
                            _s = str(_st)
                            _prev = (_s[:220] + "…") if len(_s) > 220 else _s
                            print(f"[REACT-UNIFIED][plan-diag]   step[{_pi}]: {_prev!r}", flush=True)
                    elif _has_tp:
                        print(
                            "[REACT-UNIFIED][plan-diag]   hint: 原文含 <task_plan> 但 plan_steps 为空，"
                            "请检查是否含标准 <step>...</step>",
                            flush=True,
                        )
                decision = parsed.get("decision") or {
                    "execute": False,
                    "tool": "",
                    "params": {},
                    "reason": "",
                }
                _goal_done = bool(parsed.get("goal_done"))
                if _goal_done and (round_idx > 0 or _steps_done > 0):
                    decision["execute"] = False
                    decision["tool"] = ""
                    decision["params"] = {}
                    if not (decision.get("reason") or "").strip():
                        decision["reason"] = "判定用户目标已达成，结束主循环"
                    if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                        print(
                            "[REACT-UNIFIED] goal_done=true → force execute=false, exit branch",
                            flush=True,
                        )
                if (
                    round_idx == 0
                    and _unified_first_round_task_plan_enabled()
                    and not unified_plan_steps
                ):
                    _ps = parsed.get("plan_steps") or []
                    if isinstance(_ps, list) and _ps:
                        _clean = [str(x).strip() for x in _ps if str(x).strip()]
                        if _clean:
                            unified_plan_steps = _cap_unified_task_plan_steps(_clean)
                            if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                                print(
                                    f"[REACT-UNIFIED] task_plan accepted n={len(unified_plan_steps)}"
                                )
                            _plan_rows = _normalize_plan_rows_for_sse(
                                _plan_rows_from_json_or_todos(unified_plan_steps, None)
                            )
                            yield {
                                "event": "plan_init",
                                "mode": "unified_task_plan",
                                "steps": _plan_rows,
                                "suppress_plan_ui": _should_suppress_plan_ui(
                                    len(unified_plan_steps), None
                                ),
                            }
                            if _unified_plan_diag_enabled():
                                print(
                                    "[REACT-UNIFIED][plan-diag] plan_init emitted "
                                    f"n_steps={len(unified_plan_steps)} "
                                    f"suppress_plan_ui={_should_suppress_plan_ui(len(unified_plan_steps), None)}",
                                    flush=True,
                                )
                if _unified_plan_diag_enabled() and round_idx == 0 and not unified_plan_steps:
                    if not _unified_first_round_task_plan_enabled():
                        print(
                            "[REACT-UNIFIED][plan-diag] round0: 未合并 task_plan（首轮 task_plan 已关 "
                            "REACT_UNIFIED_FIRST_ROUND_TASK_PLAN）",
                            flush=True,
                        )
                    else:
                        print(
                            "[REACT-UNIFIED][plan-diag] round0: 仍无 unified_plan_steps（模型未产出可解析 "
                            "<task_plan><step> 或步为空）",
                            flush=True,
                        )
                _round_todo_effective = _round_todo
                if unified_plan_steps and _plan_step_idx < len(unified_plan_steps):
                    _round_todo_effective = unified_plan_steps[_plan_step_idx]
                if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                    print(
                        f"[REACT-UNIFIED] decision execute={decision.get('execute')!r} "
                        f"tool={decision.get('tool')!r}"
                    )
                if not decision.get("execute") or not (decision.get("tool") or "").strip():
                    # 已跑过工具后收工：须先发 finished（reactMainLoopFinished）+ 增量总览，否则会只剩「执行统计」
                    if _steps_done > 0 or findings_acc:
                        # 等待后台增量总结线程完成（最多等 3 秒）
                        print(f"[INCR-SUM] main loop end, waiting for background summary...")
                        await self._wait_for_background_summary(running_summary_state)
                        yield {
                            "event": "finished",
                            "finished": True,
                            "steps_count": _steps_done,
                            "duration": time.time() - _t0,
                            "thinking_time": _total_think_time,
                        }
                        _incr_done = str(running_summary_state.get("text") or "").strip()
                        if use_react_incremental_running_summary() and _incr_done:
                            _lsi = max(0, (_steps_done if _steps_done > 0 else 1) - 1)
                            async for _rs_ev in self._stream_running_summary_final_wire(
                                running_summary_state,
                                last_step_index=_lsi,
                            ):
                                yield _rs_ev
                        _sum_lines = "\n".join(findings_acc).strip()
                        _th0 = (parsed.get("thinking") or "").strip()
                        _sum_body = _sum_lines
                        if _th0 and not _unified_thinking_is_tool_meta_only(_th0):
                            _sum_body = (
                                f"{_sum_lines}\n\n{_th0}".strip() if _sum_lines else _th0
                            )
                        yield {
                            "event": "done",
                            "status": "success",
                            "findings": findings_acc,
                            "steps_count": _steps_done,
                            "duration": time.time() - _t0,
                            "thinking_time": _total_think_time,
                            "summary": _sum_body or _sum_lines,
                        }
                        _done_sent = True
                        return

                    # 首轮纯闲聊：direct_reply + summary_stream 打字机
                    yield {"event": "direct_reply_prepare", "active": True}
                    yield {"event": "summary_stream_reset"}

                    _sgap = _summary_stream_yield_gap_s()
                    _stream_parts: List[str] = []
                    # 纯闲聊不要把模型的「thinking」当成最终答案（用户会看到“任务理解/推理模板”而非直接回复）。
                    # 一律走 chitchat 工具生成自然语言；若工具不可用再用 fallback。
                    _ct = self.tools.get("chitchat")
                    _got_body = False
                    if _ct is not None and callable(getattr(_ct, "stream_execute", None)):
                        try:
                            async for _delta in _ct.stream_execute(message=user_input):
                                if isinstance(_delta, str) and _delta:
                                    _stream_parts.append(_delta)
                                    yield {"event": "summary_stream", "delta": _delta}
                            _got_body = bool("".join(_stream_parts).strip())
                        except Exception as _ce:
                            if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                                print(f"[REACT-UNIFIED] chitchat 流式失败: {_ce}", flush=True)
                    if not _got_body:
                        _fallback = ""
                        if _ct is not None:
                            try:
                                _obs = await _ct.execute(message=user_input)
                                if isinstance(_obs, dict) and _obs.get("success"):
                                    _fallback = (
                                        (_obs.get("summary") or _obs.get("message") or "")
                                        .strip()
                                    )
                            except Exception as _ce2:
                                if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                                    print(f"[REACT-UNIFIED] chitchat 兜底失败: {_ce2}", flush=True)
                        if not _fallback:
                            _fallback = _unified_chitchat_fallback_summary(llm_response, "")
                        _stream_parts.clear()
                        for _delta in _iter_direct_chat_reply_stream_chunks(_fallback):
                            _stream_parts.append(_delta)
                            yield {"event": "summary_stream", "delta": _delta}
                            if _sgap > 0:
                                await asyncio.sleep(_sgap)

                    _summary = "".join(_stream_parts)
                    yield {
                        "event": "done",
                        "status": "success",
                        "findings": [],
                        "steps_count": 0,
                        "duration": time.time() - _t0,
                        "thinking_time": _think_time,
                        "summary": _summary,
                        "direct_reply": True,
                    }
                    _done_sent = True
                    return

                tool_name = str(decision.get("tool") or "").strip()
                if tool_name:
                    _tn_low = tool_name.lower()
                    if self.tools.get(tool_name) is None and self.tools.get(_tn_low) is not None:
                        tool_name = _tn_low
                tool_params = dict(decision.get("params") or {})
                if "userId" not in tool_params:
                    tool_params["userId"] = "system_agent"
                # 模型常下发 project_id: null，「in params」会为真导致旧逻辑漏注入；与 modify 分支的 get 补救对齐
                if not tool_params.get("project_id"):
                    if self.project_id:
                        tool_params["project_id"] = self.project_id
                    elif project_id is not None:
                        tool_params["project_id"] = project_id
                tool_params["ui_locale"] = normalize_locale(getattr(self, "_ui_locale", None))
                if tool_name in ("modify", "create", "delete") and "confirm" not in tool_params:
                    tool_params["confirm"] = False
                if tool_name == "modify":
                    if (
                        not tool_params.get("target_id")
                        and not tool_params.get("target_ids")
                        and not tool_params.get("natural_query")
                    ):
                        tool_params["natural_query"] = (user_input or "")[:500]
                    if not tool_params.get("project_id") and project_id is not None:
                        tool_params["project_id"] = project_id
                    _mt = str(tool_params.get("target") or "").strip().lower()
                    if _mt == "plan" and not tool_params.get("target_id"):
                        _grm = (result_ctx or {}).get("grep_result") or {}
                        _fpid = _grm.get("first_plan_id") or result_ctx.get("first_plan_id")
                        if _fpid is not None:
                            tool_params["target_id"] = int(_fpid)
                elif tool_name == "create":
                    # 闭环：与旧链路一致，避免模型只给空 fields / 漏 natural_query 时 create 直接报「缺参数」
                    if not tool_params.get("natural_query") and (user_input or "").strip():
                        tool_params["natural_query"] = (user_input or "")[:2000]
                    if not tool_params.get("project_id") and project_id is not None:
                        tool_params["project_id"] = project_id
                    _cf = tool_params.get("fields")
                    _cf_empty = _cf is None or (isinstance(_cf, dict) and len(_cf) == 0)
                    if _cf_empty:
                        _nq = (tool_params.get("natural_query") or user_input or "").strip()
                        if _nq:
                            _tgt = str(tool_params.get("target") or "bug").strip()
                            _tkey = "name" if _tgt == "plan" else "title"
                            tool_params["fields"] = {_tkey: _nq[:500]}
                    # 新建 Bug/BadCase/用例/卡片等：preview 缺 plan_id 时用「当前侧栏迭代」或 grep 首推计划写入 fields，
                    # 以便复制源未关联计划时仍归入当前 tab，避免预览出现「（未关联计划）」。
                    # 带 copy_from_* 时不注入：create_tool 从源 Card 取子迭代 plan，注入根迭代 id 会覆盖 Card。
                    _cf2 = tool_params.get("fields")
                    _tgt_inj = str(tool_params.get("target") or "bug").strip().lower()
                    if _tgt_inj != "plan" and isinstance(_cf2, dict):
                        _copy_src_keys_m = (
                            "copy_from_bug_id",
                            "source_bug_id",
                            "copy_from_badcase_id",
                            "source_badcase_id",
                            "copy_from_testcase_id",
                            "source_testcase_id",
                            "copy_from_card_id",
                            "source_card_id",
                        )
                        _has_copy_fields_m = any(
                            _cf2.get(k) not in (None, "", 0, "0") for k in _copy_src_keys_m
                        )
                        _ep = _cf2.get("plan_id")
                        if not _has_copy_fields_m and _ep in (None, "", 0, "0"):
                            _gr_c = (result_ctx or {}).get("grep_result") or {}
                            _fp_c = _gr_c.get("first_plan_id") or result_ctx.get("first_plan_id")
                            _chosen = None
                            _tp_pid = tool_params.get("plan_id")
                            if _tp_pid not in (None, "", 0, "0"):
                                try:
                                    _chosen = int(_tp_pid)
                                except (TypeError, ValueError):
                                    _chosen = None
                            if (_chosen is None or _chosen <= 0) and getattr(self, "plan_id", None) not in (
                                None,
                                "",
                                0,
                                "0",
                            ):
                                try:
                                    _chosen = int(self.plan_id)
                                except (TypeError, ValueError):
                                    _chosen = None
                            if (_chosen is None or _chosen <= 0) and _fp_c is not None:
                                try:
                                    _chosen = int(_fp_c)
                                except (TypeError, ValueError):
                                    _chosen = None
                            if _chosen is not None and _chosen > 0:
                                _cf2["plan_id"] = _chosen
                        # 与 _extract_todo_params 的 wants_copy 对齐：英文 copy / 仅 reason·todo 含复制语义时，
                        # 模型常漏写 copy_from_*，导致 preview 无 nav_copy_source_card_id、前端只能落「迭代」Tab。
                        if _tgt_inj == "bug" and isinstance(_cf2, dict):
                            if not any(
                                _cf2.get(k) not in (None, "", 0, "0")
                                for k in ("copy_from_bug_id", "source_bug_id")
                            ):
                                _gr_nav = (result_ctx or {}).get("grep_result") or {}
                                _fbid = _gr_nav.get("first_bug_id") or result_ctx.get(
                                    "first_bug_id"
                                )
                                if _fbid is not None:
                                    _nq_ex = (
                                        tool_params.get("natural_query") or user_input or ""
                                    ).strip()
                                    _rsn = str(decision.get("reason") or "")
                                    _todo_eff = str(_round_todo_effective or "")
                                    _nl = _nq_ex.lower()
                                    _copy_hint_x = (
                                        any(
                                            t in _nq_ex
                                            for t in ("复制", "拷贝", "一样", "相同")
                                        )
                                        or bool(re.search(r"(?i)\bcopy\b", _nq_ex))
                                        or ("duplicate" in _nl)
                                        or any(t in _rsn for t in ("复制", "拷贝"))
                                        or bool(re.search(r"(?i)\bcopy\b", _rsn))
                                        or any(t in _todo_eff for t in ("复制", "拷贝"))
                                        or bool(re.search(r"(?i)\bcopy\b", _todo_eff))
                                    )
                                    if _copy_hint_x:
                                        try:
                                            _cf2["copy_from_bug_id"] = int(_fbid)
                                        except (TypeError, ValueError):
                                            pass
                elif tool_name == "copy":
                    if not tool_params.get("project_id") and project_id is not None:
                        tool_params["project_id"] = project_id
                    _gr = (result_ctx or {}).get("grep_result") or {}
                    _tt = str(tool_params.get("target") or "bug").strip().lower()
                    if not tool_params.get("source_id"):
                        if _tt == "bug":
                            _sid = _gr.get("first_bug_id") or result_ctx.get("first_bug_id")
                        elif _tt == "badcase":
                            _sid = _gr.get("first_badcase_id") or result_ctx.get("first_badcase_id")
                        elif _tt == "testcase":
                            _sid = _gr.get("first_testcase_id") or result_ctx.get("first_testcase_id")
                        elif _tt == "card":
                            _sid = _gr.get("first_card_id") or result_ctx.get("first_card_id")
                        else:
                            _sid = None
                        if _sid:
                            tool_params["source_id"] = _sid
                    if not tool_params.get("title") and (user_input or "").strip():
                        _xt = self._extract_create_title(user_input, "")
                        if _xt:
                            tool_params["title"] = _xt
                elif tool_name == "delete":
                    if not tool_params.get("project_id") and project_id is not None:
                        tool_params["project_id"] = project_id
                    _gr = (result_ctx or {}).get("grep_result") or {}
                    _tt = str(tool_params.get("target") or "bug").strip().lower()
                    if _tt == "plan":
                        if not tool_params.get("plan_id"):
                            _fp = _gr.get("first_plan_id") or result_ctx.get("first_plan_id")
                            if _fp is not None:
                                tool_params["plan_id"] = int(_fp)
                        if not tool_params.get("plan_id") and getattr(self, "plan_id", None) is not None:
                            tool_params["plan_id"] = self.plan_id
                    elif _tt == "card":
                        if not tool_params.get("card_id") and not tool_params.get("target_id"):
                            _cid = _gr.get("first_card_id") or result_ctx.get("first_card_id")
                            if _cid:
                                tool_params["card_id"] = _cid
                    elif not tool_params.get("target_id"):
                        if _tt == "bug":
                            _tid = _gr.get("first_bug_id") or result_ctx.get("first_bug_id")
                        elif _tt == "testcase":
                            _tid = _gr.get("first_testcase_id") or result_ctx.get("first_testcase_id")
                        elif _tt == "badcase":
                            _tid = _gr.get("first_badcase_id") or result_ctx.get("first_badcase_id")
                        else:
                            _tid = None
                        if _tid:
                            tool_params["target_id"] = _tid

                decision_dict: Dict[str, Any] = {
                    "execute": True,
                    "tool": tool_name,
                    "params": tool_params,
                }
                _reason_nl = str(decision.get("reason") or "").strip()
                _step_id_ui = _plan_step_idx + 1 if unified_plan_steps else round_idx + 1
                _sig = _tool_params_signature(tool_name, tool_params)
                if (
                    len(_sig_history) == _dup_win
                    and len(set(_sig_history)) == 1
                    and _sig_history[0] == _sig
                ):
                    _stall_msg = react_unified_duplicate_action_stall_message(
                        getattr(self, "_ui_locale", None),
                        tool=tool_name,
                        window=_dup_win,
                    )
                    yield {
                        "event": "agent_thought",
                        "delta": _stall_msg + "\n\n",
                        "index": round_idx,
                        "processType": PROCESS_TYPE_STREAMING,
                        "react_phase": REACT_PHASE_THINK,
                    }
                    await self._wait_for_background_summary(running_summary_state)
                    findings_acc.append(_stall_msg)
                    yield {
                        "event": "finished",
                        "finished": True,
                        "steps_count": _steps_done,
                        "duration": time.time() - _t0,
                        "thinking_time": _total_think_time,
                    }
                    _sum_stall = "\n".join(findings_acc).strip()
                    yield {
                        "event": "done",
                        "status": "partial",
                        "findings": findings_acc,
                        "steps_count": _steps_done,
                        "duration": time.time() - _t0,
                        "thinking_time": _total_think_time,
                        "summary": _sum_stall,
                        "stop_reason": "duplicate_action",
                    }
                    _done_sent = True
                    return
                _sig_history.append(_sig)
                yield {"event": "tool_call", "tool": tool_name, "params": tool_params}
                yield {
                    "event": "executing",
                    "tool": tool_name,
                    "index": round_idx,
                    "step_id": _step_id_ui,
                    "params": tool_params,
                    "reason": _reason_nl,
                    "message": f"正在执行：{tool_name}",
                }

                observation: Dict[str, Any]
                tool_exc: Optional[BaseException] = None
                _dag_modify = False
                try:
                    from agents.agent_task_dag import use_react_agent_task_dag

                    _dag_modify = tool_name == "modify" and use_react_agent_task_dag()
                except Exception:
                    _dag_modify = False
                if tool_name == "modify" and not _dag_modify:
                    _tool_obj = self.tools.get(tool_name)
                    if _tool_obj is None:
                        observation = {
                            "success": False,
                            "error": react_tool_missing_error(
                                tool_name, getattr(self, "_ui_locale", None)
                            ),
                        }
                    else:
                        tool_timeout = int(os.getenv("AGENT_TOOL_TIMEOUT", "120"))
                        fut, progress_q = self._spawn_modify_executor_future(
                            _tool_obj, tool_params
                        )
                        wait_task = asyncio.create_task(
                            asyncio.wait_for(fut, timeout=tool_timeout)
                        )
                        try:
                            async for _side in self._iter_modify_side_events_while_task(
                                wait_task,
                                progress_q,
                                round_idx,
                                _reason_nl,
                            ):
                                yield _side
                            observation = wait_task.result()
                        except asyncio.TimeoutError:
                            observation = {
                                "success": False,
                                "error": react_modify_timeout(
                                    tool_timeout, getattr(self, "_ui_locale", None)
                                ),
                            }
                        except Exception as e:
                            tool_exc = e
                            print(f"[REACT-UNIFIED] modify error: {e}")
                            observation = {"success": False, "error": str(e)}
                        if isinstance(observation, dict) and "success" not in observation:
                            observation = dict(observation)
                            observation.setdefault("success", True)
                else:
                    try:
                        observation = await self._execute_tool(decision_dict)
                    except Exception as e:
                        tool_exc = e
                        print(f"[REACT-UNIFIED] tool error: {e}")
                        observation = {"success": False, "error": str(e)}
                    for _te in self._drain_tool_task_sse_buffer_list():
                        yield _te

                if tool_name == "modify" and not _dag_modify:
                    for _te in self._drain_tool_task_sse_buffer_list():
                        yield _te

                observation = _normalize_unified_stream_tool_observation(observation)

                if tool_exc is not None:
                    yield {
                        "event": "tool_error",
                        "tool": tool_name,
                        "index": round_idx,
                        "step_id": _step_id_ui,
                        "message": str(tool_exc),
                        "code": "exception",
                    }
                elif not observation.get("success"):
                    yield {
                        "event": "tool_error",
                        "tool": tool_name,
                        "index": round_idx,
                        "step_id": _step_id_ui,
                        "message": str(
                            observation.get("error")
                            or observation.get("message")
                            or "工具执行失败"
                        ),
                        "code": observation.get("code"),
                        "details": observation,
                    }

                obs_summary = (
                    observation.get("summary")
                    or observation.get("message")
                    or ("成功" if observation.get("success") else "失败")
                )
                if tool_name == "modify" and observation.get("success"):
                    tt = observation.get("target")
                    tid = observation.get("target_id")
                    if tt is not None and tid is not None:
                        if is_english_locale(getattr(self, "_ui_locale", None)):
                            _fact = (
                                f"(FACT: modify.target={tt}, modify.target_id={tid}; "
                                f"Confirmed must use this entity type and id; do not write BadCase unless target is badcase.) "
                            )
                        else:
                            _fact = (
                                f"（本步事实：modify.target={tt}，modify.target_id={tid}；"
                                f"已确认中的实体类型与 ID 必须与此一致；勿把 Bug 写成 BadCase，除非 target 为 badcase。）"
                            )
                        obs_summary = _fact + str(obs_summary)
                yield {
                    "event": "observation",
                    "tool": tool_name,
                    "index": round_idx,
                    "step_id": _step_id_ui,
                    "data": observation,
                    "summary_nl": str(obs_summary),
                    "success": observation.get("success", False),
                }
                _clr = observation.get("client_local_run")
                if isinstance(_clr, dict) and _clr:
                    for _pkt in engine_dict_to_wire_packets({"event": "client_local_run", **_clr}):
                        yield _pkt
                if (
                    tool_name == "terminal"
                    and observation.get("terminal_pause_for_client") is True
                    and isinstance(observation.get("command"), str)
                    and str(observation.get("command") or "").strip()
                ):
                    try:
                        _tmo = int(observation.get("timeout") or 60)
                    except (TypeError, ValueError):
                        _tmo = 60
                    _term_pkt: Dict[str, Any] = {
                        "event": "client_terminal_exec",
                        "command": str(observation.get("command") or "").strip(),
                        "cwd": str(observation.get("cwd") or "").strip(),
                        "timeout": max(1, min(_tmo, 86400)),
                        "react_phase": REACT_PHASE_ACT,
                    }
                    if observation.get("stop_on_error") is True:
                        _term_pkt["stop_on_error"] = True
                    for _pkt in engine_dict_to_wire_packets(_term_pkt):
                        yield _pkt
                if (
                    tool_name == "modify"
                    and observation.get("success")
                    and observation.get("batch_results")
                ):
                    yield {
                        "event": "modify_preview",
                        "results": observation.get("batch_results", []),
                        "confirmation_required": observation.get(
                            "confirmation_required", False
                        ),
                    }

                findings_acc.append(_unified_finding_line(tool_name, observation))
                prev_observation = (
                    deep_sse_json_safe(observation)
                    if isinstance(observation, dict)
                    else observation
                )
                prev_action = {
                    "tool": tool_name,
                    "params": _json_safe_tool_params(tool_params),
                }
                tool_params.pop("progress_queue", None)
                tool_params.pop("progress_callback", None)
                if unified_plan_steps and not observation.get("success"):
                    _plan_step_fail_streak += 1
                    if _plan_step_fail_streak >= _plan_step_max_fail:
                        _skip_msg = react_unified_plan_step_skip_failures_message(
                            getattr(self, "_ui_locale", None),
                            step_index_1based=min(_plan_step_idx + 1, len(unified_plan_steps)),
                            max_retries=_plan_step_max_fail,
                        )
                        yield {
                            "event": "agent_thought",
                            "delta": _skip_msg + "\n\n",
                            "index": round_idx,
                            "processType": PROCESS_TYPE_STREAMING,
                            "react_phase": REACT_PHASE_THINK,
                        }
                        findings_acc.append(_skip_msg)
                        _plan_step_idx = min(_plan_step_idx + 1, len(unified_plan_steps))
                        _plan_step_fail_streak = 0
                if observation.get("success"):
                    _sig_history.clear()
                    _plan_step_fail_streak = 0
                    await self._merge_running_summary_incremental_silent(
                        running_summary_state,
                        round_idx,
                        tool_name,
                        _round_todo_effective,
                        str(obs_summary),
                        background=True,  # 不阻塞主循环
                    )
                    if tool_name == "grep":
                        self._merge_grep_observation_into_context(
                            observation, tool_params, result_ctx
                        )
                    else:
                        for key in (
                            "bug_list",
                            "badcase_list",
                            "testcase_list",
                            "grep_result",
                        ):
                            if key in observation:
                                result_ctx[key] = observation[key]
                    if unified_plan_steps and _react_plan_sse_live_steps_enabled():
                        _pr = _plan_rows_from_json_or_todos(unified_plan_steps, None)
                        if _pr:
                            _ppi = min(_plan_step_idx, max(0, len(_pr) - 1))
                            _sync_plan_single_in_progress(_pr, _ppi)
                            yield {
                                "event": "plan_update",
                                "steps": _normalize_plan_rows_for_sse(_pr),
                                "reason": "unified_task_plan_progress",
                                "suppress_plan_ui": _should_suppress_plan_ui(
                                    len(unified_plan_steps), None
                                ),
                            }
                    if unified_plan_steps:
                        _plan_step_idx += 1

                # 沙箱/创建预览待用户确认：收束本轮 SSE，避免继续空转 round/LLM（确认后由新请求继续）
                _await_user = (
                    observation.get("confirmation_required") is True
                    and observation.get("success") is True
                )
                _terminal_pause = (
                    tool_name == "terminal"
                    and observation.get("success") is True
                    and observation.get("terminal_pause_for_client") is True
                )
                _plan_n = len(unified_plan_steps) if unified_plan_steps else 0
                _plan_round_done = (
                    _plan_n > 0
                    and observation.get("success") is True
                    and not _await_user
                    and not _terminal_pause
                    and (_plan_step_idx >= _plan_n)
                )
                if _await_user or _plan_round_done or _terminal_pause:
                    _steps_done = round_idx + 1
                    # 等待后台增量总结线程完成
                    await self._wait_for_background_summary(running_summary_state)
                    _sum_out = (
                        str(observation.get("message") or obs_summary or "").strip()
                        or (
                            "预览已生成，请在侧栏确认或拒绝后再继续。"
                            if _await_user
                            else (
                                "终端命令已在本机执行，输出已自动作为下一条上下文提交。"
                                if _terminal_pause
                                else "\n".join(findings_acc).strip()
                            )
                        )
                    )
                    yield {
                        "event": "finished",
                        "finished": True,
                        "steps_count": _steps_done,
                        "duration": time.time() - _t0,
                        "thinking_time": _total_think_time,
                    }
                    _incr_early = str(running_summary_state.get("text") or "").strip()
                    if use_react_incremental_running_summary() and _incr_early:
                        _lsi_e = max(0, (_steps_done if _steps_done > 0 else 1) - 1)
                        async for _rs_ev in self._stream_running_summary_final_wire(
                            running_summary_state,
                            last_step_index=_lsi_e,
                        ):
                            yield _rs_ev
                    yield {
                        "event": "done",
                        "status": "success",
                        "findings": findings_acc,
                        "steps_count": _steps_done,
                        "duration": time.time() - _t0,
                        "thinking_time": _total_think_time,
                        "summary": _sum_out,
                    }
                    _done_sent = True
                    return

                # 勿在 modify 成功后直接 break：无「待确认/计划已跑完」时仍可能进入下一轮（如再 create 副本）
                _steps_done = round_idx + 1

            _summary_text = "\n".join(findings_acc).strip()
            _partial_hdr = react_unified_partial_max_rounds_message(
                getattr(self, "_ui_locale", None),
                max_rounds=_max_rounds,
            )
            if _summary_text:
                _summary_text = _partial_hdr + "\n\n" + _summary_text
            else:
                _summary_text = _partial_hdr
            # 与旧主循环一致：先 tail/finished → 前端 reactMainLoopFinished，再下发增量运行总览 SSE
            # 等待后台增量总结线程完成
            await self._wait_for_background_summary(running_summary_state)
            yield {
                "event": "finished",
                "finished": True,
                "steps_count": _steps_done,
                "duration": time.time() - _t0,
                "thinking_time": _total_think_time,
            }
            _incr_md = str(running_summary_state.get("text") or "").strip()
            if use_react_incremental_running_summary() and _incr_md:
                _last_step_i = max(0, (_steps_done if _steps_done > 0 else 1) - 1)
                async for _rs_ev in self._stream_running_summary_final_wire(
                    running_summary_state,
                    last_step_index=_last_step_i,
                ):
                    yield _rs_ev
            yield {
                "event": "done",
                "status": "partial",
                "findings": findings_acc,
                "steps_count": _steps_done,
                "duration": time.time() - _t0,
                "thinking_time": _total_think_time,
                "summary": _summary_text,
                "stop_reason": "max_rounds",
            }
            _done_sent = True
        except Exception as e:
            print(f"[REACT-UNIFIED] stream error: {e}")
            if _unified_error_diag_enabled():
                print(traceback.format_exc(), flush=True)
                try:
                    print(
                        f"[REACT-UNIFIED][diag] last_round_1based={_unified_round_for_debug + 1} "
                        f"steps_done={_steps_done}",
                        flush=True,
                    )
                    _print_unified_round_prompt_snapshot(
                        max(0, _unified_round_for_debug),
                        result_ctx,
                        prev_observation,
                        prev_action,
                        tag="异常时（最近一轮）",
                    )
                except Exception as de:
                    print(f"[REACT-UNIFIED][diag] 附加快照失败: {de}", flush=True)
            yield {"event": "error", "message": str(e)}
            yield {
                "event": "done",
                "status": "error",
                "findings": [f"引擎异常：{e}"],
                "steps_count": _steps_done,
                "duration": time.time() - _t0,
                "thinking_time": _total_think_time,
                "summary": str(e),
            }
            _done_sent = True
        finally:
            try:
                self._react_stream_images = None
                self._react_stream_images_round_budget = 0
            except Exception:
                pass
            try:
                self._client_shell = None
            except Exception:
                pass
            _aid_fin = getattr(self, "_agent_session_id", None)
            if _aid_fin:
                _REACT_STREAM_CANCEL_EVENTS.pop(_aid_fin, None)
            if not _done_sent:
                yield {
                    "event": "done",
                    "status": "error",
                    "findings": ["流式引擎非正常结束（未发送完成包）"],
                    "steps_count": _steps_done,
                    "duration": time.time() - _t0,
                    "thinking_time": _total_think_time,
                    "summary": "非正常结束",
                }


    async def run_stream(
        self,
        user_input: str,
        project_id: int = None,
        plan_id: int = None,
        locale: Optional[str] = None,
        pending_diff_context: Optional[List[Dict[str, Any]]] = None,
        agent_session_id: Optional[str] = None,
        long_memory_prefetch: Optional[Dict[str, Any]] = None,
        hint_project_name: Optional[str] = None,
        hint_plan_name: Optional[str] = None,
        client_shell: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        流式执行 ReAct（Skill 工具）。plan_id 为当前迭代计划 ID，传入则 grep 可只检索该计划下记录。
        内部仍用 ``event`` 字典；本方法在出口统一转为 SSE v1（``type`` + ``payload``），上层无需再映射。
        """
        _last_wire_phase: Optional[str] = None
        async for raw in self._run_unified_xml_stream(
            user_input,
            project_id=project_id,
            plan_id=plan_id,
            locale=locale,
            pending_diff_context=pending_diff_context,
            agent_session_id=agent_session_id,
            long_memory_prefetch=long_memory_prefetch,
            hint_project_name=hint_project_name,
            hint_plan_name=hint_plan_name,
            client_shell=client_shell,
            images=images,
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

    async def run(
        self,
        user_input: str,
        project_id: int = None,
        locale: Optional[str] = None,
        long_memory_prefetch: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        仅收口用：与 ``run_stream`` 共用同一流式引擎，无独立非流式 ReAct 实现。
        """
        start_wall = time.time()
        result: Dict[str, Any] = {
            "status": "success",
            "steps": [],
            "context": {},
            "findings": [],
            "duration": 0.0,
            "error": None,
        }
        try:
            print(f"\n[REACT] run() drain unified stream | input[:60]={user_input[:60]!r}\n")
            try:
                _cap = int((os.getenv("REACT_RUN_COLLECT_EVENTS_MAX") or "500").strip())
            except Exception:
                _cap = 500
            _cap = max(0, min(_cap, 5000))
            stream_events: List[Dict[str, Any]] = []
            async for raw in self._run_unified_xml_stream(
                user_input,
                project_id=project_id,
                plan_id=None,
                locale=locale,
                pending_diff_context=None,
                agent_session_id=None,
                long_memory_prefetch=long_memory_prefetch,
            ):
                if not isinstance(raw, dict):
                    continue
                ev = raw.get("event")
                if _cap > 0 and isinstance(ev, str):
                    slim: Dict[str, Any] = {"event": ev}
                    for k in ("tool", "index", "step_id", "status", "success"):
                        if k in raw:
                            slim[k] = raw[k]
                    if len(stream_events) < _cap:
                        stream_events.append(slim)
                if ev == "error":
                    result["status"] = "error"
                    result["error"] = str(raw.get("message") or "")
                    continue
                if ev == "done":
                    result["findings"] = list(raw.get("findings") or [])
                    summ = raw.get("summary")
                    if isinstance(summ, str) and summ.strip():
                        result["summary"] = summ.strip()
                    _st = raw.get("status")
                    if _st == "error":
                        result["status"] = "error"
                        if not result.get("error"):
                            result["error"] = result["summary"] or "done(status=error)"
                    sc = raw.get("steps_count")
                    if isinstance(sc, int) and sc > 0:
                        result["steps"] = [
                            {"aggregated": True, "index": j} for j in range(sc)
                        ]
                    result["duration"] = float(
                        raw.get("duration") or (time.time() - start_wall)
                    )
                    tt = raw.get("thinking_time")
                    if tt is not None:
                        try:
                            result["thinking_time"] = float(tt)
                        except (TypeError, ValueError):
                            result["thinking_time"] = tt
            result["stream_events"] = stream_events
            if result["status"] != "error" and not result["duration"]:
                result["duration"] = time.time() - start_wall
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            result["duration"] = time.time() - start_wall
            print(f"[REACT] run() error: {e}")
        print(
            f"\n[REACT] run() done | steps={len(result['steps'])} | "
            f"findings={len(result['findings'])} | duration={result['duration']:.2f}s\n"
        )
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
            '批量处理', '多步骤操作', '完整流程',
            '复制', '拷贝', '参照', '一样',
        ]
        
        #检查是否为复杂任务
        is_complex_task = any(keyword in user_input.lower() or keyword in decision.get('reason', '').lower() 
                            for keyword in complex_task_keywords)
        
        if is_complex_task and tool_name in ['grep', 'modify', 'create', 'copy']:
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
            return [x for x in (lst or []) if isinstance(x, dict) and x.get("id") in idset]

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
        card_l = result_context.get('card_list') or []
        plan_l = result_context.get('plan_list') or []
        raw_bg = result_context.get('grep_modify_raw_bug_list') or []
        raw_bc = result_context.get('grep_modify_raw_badcase_list') or []
        raw_tc = result_context.get('grep_modify_raw_testcase_list') or []
        params["intent_has_raw_bug_list"] = bool(raw_bg)
        params["intent_has_raw_badcase_list"] = bool(raw_bc)
        params["intent_has_raw_testcase_list"] = bool(raw_tc)
        _card_rows_param = result_context.get("grep_modify_raw_card_list") or result_context.get("card_list")
        params["intent_card_rows"] = _card_rows_param if isinstance(_card_rows_param, list) else None
        params["intent_result_context"] = result_context
        explicit = self._infer_modify_target_explicit(user_input, todo)
        user_infer = self._infer_modify_target(user_input, todo)
        if explicit:
            target_type = explicit
        else:
            target_type = str(params.get('target') or '').strip().lower() or user_infer
        if tc_l and not bc_l and not bg_l and not card_l and not plan_l:
            target_type = 'testcase'
        elif bc_l and not tc_l and not bg_l and not card_l and not plan_l:
            target_type = 'badcase'
        elif bg_l and not tc_l and not bc_l and not card_l and not plan_l:
            target_type = 'bug'
        elif card_l and not tc_l and not bc_l and not bg_l and not plan_l:
            target_type = str(params.get("target") or user_infer or "bug").strip().lower()
            kw_g = self._extract_title_keywords_for_grep(user_input, todo) or ''
            tp = self._pick_best_match_from_list(card_l, kw_g, 'title')
            cr = tp[0] if tp else (card_l[0] if card_l else None)
            if isinstance(cr, dict):
                from agents.intent.resolution import infer_source_tuple_from_card_dict

                pr = infer_source_tuple_from_card_dict(cr)
                for k in ("card_id", "id"):
                    v = cr.get(k)
                    if v is None or str(v).strip() == "":
                        continue
                    try:
                        iv = int(v)
                        if iv > 0:
                            params["card_id"] = iv
                            break
                    except (TypeError, ValueError):
                        continue
                if pr and params.get("target_id") is None:
                    target_type = pr[0]
                    try:
                        params["target_id"] = int(pr[1])
                    except (TypeError, ValueError):
                        pass
        elif plan_l and not tc_l and not bc_l and not bg_l and not card_l:
            target_type = 'plan'
        _lgt = str(result_context.get('_last_grep_target') or '').lower()
        if _lgt == 'testcase' and tc_l:
            target_type = 'testcase'
        elif _lgt == 'badcase' and bc_l:
            target_type = 'badcase'
        elif _lgt == 'bug' and bg_l:
            target_type = 'bug'
        elif _lgt == 'card' and card_l:
            target_type = str(params.get("target") or user_infer or "bug").strip().lower()
            kw_g = self._normalize_rerank_keywords(
                params.get('keywords') or result_context.get('_last_grep_keywords') or ''
            ) or self._extract_title_keywords_for_grep(user_input, todo) or ''
            tp = self._pick_best_match_from_list(card_l, kw_g, 'title')
            cr = tp[0] if tp else (card_l[0] if card_l else None)
            if isinstance(cr, dict):
                from agents.intent.resolution import infer_source_tuple_from_card_dict

                pr = infer_source_tuple_from_card_dict(cr)
                for k in ("card_id", "id"):
                    v = cr.get(k)
                    if v is None or str(v).strip() == "":
                        continue
                    try:
                        iv = int(v)
                        if iv > 0:
                            params["card_id"] = iv
                            break
                    except (TypeError, ValueError):
                        continue
                if pr and params.get("target_id") is None:
                    target_type = pr[0]
                    try:
                        params["target_id"] = int(pr[1])
                    except (TypeError, ValueError):
                        pass
        elif _lgt == 'plan' and plan_l:
            target_type = 'plan'
        params['target'] = target_type
        self._enrich_modify_params_target_ids(
            params, result_context, target_type, log_prefix="[REACT-planing] "
        )
        target_id = params.get("target_id")

        if target_type == 'bug':
            _ctx_rows = bg_l or raw_bg
        elif target_type == 'testcase':
            _ctx_rows = tc_l or raw_tc
        elif target_type == 'card':
            _ctx_rows = card_l
        elif target_type == 'plan':
            _ctx_rows = plan_l
        else:
            _ctx_rows = bc_l or raw_bc
        if target_type == "card":
            cid_v = params.get("card_id")
            if cid_v is None:
                cid_v = target_id
            if cid_v is not None and _ctx_rows:
                _ok_c = False
                try:
                    iv = int(cid_v)
                except (TypeError, ValueError):
                    iv = None
                if iv is not None:
                    for x in _ctx_rows:
                        if not isinstance(x, dict):
                            continue
                        rid = x.get("id")
                        if rid is None:
                            rid = x.get("card_id")
                        try:
                            if rid is not None and int(rid) == iv:
                                _ok_c = True
                                break
                        except (TypeError, ValueError):
                            continue
                if not _ok_c:
                    print(
                        f"[REACT-planing] enrich 丢弃与 card 候选列表不一致的 card_id={cid_v}（避免串表）"
                    )
                    params.pop("card_id", None)
                    params.pop("target_id", None)
                    target_id = None
                else:
                    params["card_id"] = iv
                    params.pop("target_id", None)
                    target_id = None
        elif target_id is not None and _ctx_rows:
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

        if target_type == "card":
            cid = params.get("card_id")
            if cid is None:
                cid = grep_result.get("first_card_id") or result_context.get("first_card_id")
            if cid is None:
                tid_ca = self._try_target_id_from_merged_lists(
                    result_context, target_type, user_input, todo
                )
                if tid_ca is not None:
                    cid = tid_ca
                    print(f"[REACT-planing] enrich 从合并列表注入 card_id={cid} ({target_type})")
            if cid is not None:
                try:
                    params["card_id"] = int(cid)
                    params.pop("target_id", None)
                except (TypeError, ValueError):
                    pass
        elif not params.get("target_ids") and params.get("target_id") is None:
            if target_type == 'bug':
                target_id = grep_result.get('first_bug_id') or result_context.get('first_bug_id')
            elif target_type == 'testcase':
                target_id = grep_result.get('first_testcase_id') or result_context.get('first_testcase_id')
            elif target_type == 'plan':
                target_id = grep_result.get('first_plan_id') or result_context.get('first_plan_id')
            else:
                target_id = grep_result.get('first_badcase_id') or result_context.get('first_badcase_id')
            if target_id is not None:
                try:
                    params['target_id'] = int(target_id)
                    target_id = params['target_id']
                except (TypeError, ValueError):
                    target_id = None

        if target_type != "card" and not params.get("target_ids") and not params.get('target_id'):
            tid_m = self._try_target_id_from_merged_lists(
                result_context, target_type, user_input, todo
            )
            if tid_m is not None:
                params['target_id'] = tid_m
                print(f"[REACT-planing] enrich 从合并列表注入 target_id={tid_m} ({target_type})")

        if (
            target_type == "plan"
            and params.get("target_id") is None
            and self.plan_id is not None
        ):
            try:
                params["target_id"] = int(self.plan_id)
                print(
                    f"[REACT-planing] enrich 引擎上下文 plan_id → modify target_id={params['target_id']}"
                )
            except (TypeError, ValueError):
                pass

        _need_rescue = (
            not params.get("target_ids")
            and (
                (params.get("card_id") is None and target_type == "card")
                or (params.get("target_id") is None and target_type != "card")
            )
        )
        if _need_rescue:
            print(
                f"[REACT-thought] ⚠️ 主循环 modify：无法从上下文获取 target_id (target={target_type})，尝试补救 grep…"
            )
            kw = self._extract_title_keywords_for_grep(user_input, todo) or ''
            gparams: Dict[str, Any] = {
                'project_id': project_id,
                'keywords': kw,
                'mode': 'locate',
                'target': target_type if target_type in ('bug', 'badcase', 'testcase', 'card', 'plan') else 'all',
                'userId': 'system_agent',
            }
            if self.plan_id is not None and gparams.get('target') not in ('all', 'plan'):
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
                if target_type == "card":
                    cid_r = grep_result.get('first_card_id')
                    if cid_r is not None:
                        try:
                            params['card_id'] = int(cid_r)
                            params.pop('target_id', None)
                            print(f"[REACT-execution] 主循环补救 grep 后 card_id={params['card_id']}")
                        except (TypeError, ValueError):
                            pass
                    if params.get("card_id") is None:
                        tid2c = self._try_target_id_from_merged_lists(
                            result_context, target_type, user_input, todo
                        )
                        if tid2c is not None:
                            params['card_id'] = int(tid2c)
                            params.pop('target_id', None)
                            print(f"[REACT-planing] enrich 补救 grep 后从列表注入 card_id={tid2c}")
                elif target_type == 'bug':
                    target_id = grep_result.get('first_bug_id')
                    if target_id is not None:
                        try:
                            params['target_id'] = int(target_id)
                            print(f"[REACT-execution] 主循环补救 grep 后 target_id={params['target_id']}")
                        except (TypeError, ValueError):
                            pass
                elif target_type == 'testcase':
                    target_id = grep_result.get('first_testcase_id')
                    if target_id is not None:
                        try:
                            params['target_id'] = int(target_id)
                            print(f"[REACT-execution] 主循环补救 grep 后 target_id={params['target_id']}")
                        except (TypeError, ValueError):
                            pass
                elif target_type == 'plan':
                    target_id = grep_result.get('first_plan_id')
                    if target_id is not None:
                        try:
                            params['target_id'] = int(target_id)
                            print(f"[REACT-execution] 主循环补救 grep 后 target_id={params['target_id']}")
                        except (TypeError, ValueError):
                            pass
                else:
                    target_id = grep_result.get('first_badcase_id')
                    if target_id is not None:
                        try:
                            params['target_id'] = int(target_id)
                            print(f"[REACT-execution] 主循环补救 grep 后 target_id={params['target_id']}")
                        except (TypeError, ValueError):
                            pass
            if target_type != "card" and not params.get("target_ids") and not params.get('target_id'):
                tid2 = self._try_target_id_from_merged_lists(
                    result_context, target_type, user_input, todo
                )
                if tid2 is not None:
                    params['target_id'] = tid2
                    print(f"[REACT-planing] enrich 补救 grep 后从列表注入 target_id={tid2}")

        if not params.get("target_ids") and params.get("target_id") is None and (
            params.get("card_id") is None if target_type == "card" else True
        ):
            self._enrich_modify_params_target_ids(
                params, result_context, target_type, log_prefix="[REACT-planing] 补全后 "
            )

        tid = params.get('target_id')
        if tid is None and params.get("target_ids"):
            tls = params.get("target_ids")
            if isinstance(tls, (list, tuple)) and len(tls) > 0:
                try:
                    tid = int(tls[0])
                except (TypeError, ValueError):
                    tid = None
        explore_target = target_type
        if target_type == "card" and params.get("card_id") is not None and self.tools.get("modify"):
            mt = self.tools.get("modify")

            def _card_explore_resolve_ml():
                with mt._get_app_context():
                    nt, _ = mt._normalize_target_using_card_row(
                        target_type,
                        params.get("project_id"),
                        params["card_id"],
                    )
                    sid = mt._resolve_target_id_from_card_id(
                        nt,
                        params["card_id"],
                        params.get("project_id"),
                    )
                    return nt, sid

            try:
                loop = asyncio.get_event_loop()
                nt_e, sid_e = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, _card_explore_resolve_ml),
                    timeout=10,
                )
                if sid_e is not None:
                    explore_target = nt_e
                    tid = int(sid_e)
            except Exception as e:
                print(f"[REACT-execution] card→源表 explore 解析失败: {e}")

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
                                explore_target, _eid, _epid, getattr(self, "_ui_locale", None)
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

        if (
            (not params.get('target_id') and not params.get('target_ids'))
            or (not params.get('modifications'))
        ):
            infer = self._infer_modify_params(todo, result_context)
            if infer.get('execute') and isinstance(infer.get('params'), dict):
                ip = infer['params']
                for k in ('target_id', 'target', 'modifications', 'project_id', 'confirm'):
                    if k == 'target_id' and params.get('target_ids'):
                        continue
                    if k not in params or params.get(k) in (None, '', {}):
                        v = ip.get(k)
                        if v is not None and v != '' and v != {}:
                            params[k] = v
                print(f"[REACT-execution] 主循环 modify 已合并 _infer_modify_params 兜底: keys={list(params.keys())}")

        params["intent_combined_text"] = f"{user_input or ''} {todo or ''}".strip()
        params["intent_last_grep_target"] = str(result_context.get("_last_grep_target") or "").strip()

        if str(target_type or "").strip().lower() != "plan" and not params.get("target_ids"):
            mods_final = params.get("modifications")
            if isinstance(mods_final, dict) and mods_final:
                try:
                    from agents.intent.resolution import (
                        ModifyResolutionContext,
                        ModifyResolutionError,
                        normalize_modification_key_set,
                        remap_card_layer_modification_keys,
                        resolve_modify_target_and_id,
                    )

                    def _to_int(v):
                        if v is None or v == "":
                            return None
                        try:
                            i = int(v)
                            return i if i > 0 else None
                        except (TypeError, ValueError):
                            return None

                    rows_c = (
                        result_context.get("grep_modify_raw_card_list")
                        or result_context.get("card_list")
                        or []
                    )
                    ctx = ModifyResolutionContext(
                        last_grep_target=params.get("intent_last_grep_target"),
                        card_id=_to_int(params.get("card_id")),
                        target_id=_to_int(params.get("target_id")),
                        has_raw_bug_list=bool(params.get("intent_has_raw_bug_list")),
                        editing_surface=params.get("editing_surface"),
                        has_raw_badcase_list=bool(params.get("intent_has_raw_badcase_list")),
                        has_raw_testcase_list=bool(params.get("intent_has_raw_testcase_list")),
                        card_rows=rows_c if isinstance(rows_c, list) else None,
                    )
                    tt, pk, cid = resolve_modify_target_and_id(
                        mods_final,
                        params["intent_combined_text"],
                        ctx,
                    )
                    _mods_fp = tuple(
                        sorted(
                            normalize_modification_key_set(
                                remap_card_layer_modification_keys(dict(mods_final))
                            )
                        )
                    )
                    params["intent_resolve_reuse"] = {
                        "mods_fp": _mods_fp,
                        "resolved_target": tt,
                        "resolved_pk": pk,
                        "resolved_card_id": cid,
                    }
                    target_type = tt
                    if tt == "card":
                        if cid is not None:
                            params["card_id"] = cid
                        params.pop("target_id", None)
                    else:
                        if pk is not None:
                            params["target_id"] = pk
                        if cid is not None:
                            params["card_id"] = cid
                except ModifyResolutionError as _mre:
                    print(f"[REACT-planing] resolve_modify_target_and_id: {_mre}", flush=True)
                except Exception as _re:
                    print(f"[REACT-planing] resolve_modify_target_and_id 失败(忽略): {_re}", flush=True)
        params["target"] = target_type

        try:
            from agents.tools.modify_tool import modify_tool_params_log_snapshot

            _ctx_log = self._context_row_ids_for_modify_target(result_context, target_type)
            _enrich_snap = modify_tool_params_log_snapshot(dict(params), ctx_grep_ids=_ctx_log)
            print(
                "[MODIFY-ENRICH] main_loop " + json.dumps(_enrich_snap, ensure_ascii=False, default=str),
                flush=True,
            )
        except Exception as _log_e:
            print(f"[MODIFY-ENRICH] main_loop 入参日志失败(忽略): {_log_e}", flush=True)

        return decision, events

    @staticmethod
    def _modify_params_ready(params: Optional[Dict[str, Any]]) -> bool:
        """
        modify 执行前需：非空 modifications，且满足其一：
        - 已有 target_id；或 target_ids（批量）；或
        - target=card 且已提供 card_id；或
        - 提供 natural_query（交给 modify_tool 用 Text2SQL/ORM 解析 id）
        """
        if not params or not isinstance(params, dict):
            return False
        m = params.get('modifications')
        if not m or not isinstance(m, dict) or len(m) == 0:
            return False
        tids = params.get('target_ids')
        if isinstance(tids, (list, tuple)) and len(tids) > 0:
            return True
        if params.get('target_id') not in (None, ''):
            return True
        if str(params.get("target") or "").strip().lower() == "card" and params.get("card_id") not in (
            None,
            "",
        ):
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
            for tt in ('bug', 'testcase', 'badcase', 'card'):
                if tt == 'card':
                    tid = self._try_target_id_from_merged_lists(
                        result_context, tt, user_input, todo
                    )
                    if tid is not None:
                        params['card_id'] = tid
                        params.pop('target_id', None)
                        params['target'] = 'card'
                        print(f"[REACT-planing] last_resort 从列表选定 card_id={tid}, target=card")
                        break
                    continue
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
        elif target_type == 'card':
            lst = result_context.get('card_list') or []
        elif target_type == 'plan':
            lst = result_context.get('plan_list') or []
        else:
            lst = result_context.get('badcase_list') or []
        if not lst:
            return None
        pick = self._pick_best_match_from_list(lst, kw, 'title') if kw else lst[0]
        if not isinstance(pick, dict):
            return None
        tid = pick.get('card_id') if target_type == 'card' else pick.get('id')
        if tid is None:
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
        if target_type == "bug":
            _nk = "bug"
        elif target_type == "badcase":
            _nk = "badcase"
        elif target_type == "testcase":
            _nk = "testcase"
        elif target_type == "card":
            _nk = "card"
        elif target_type == "plan":
            _nk = "plan"
        else:
            _nk = "badcase"
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
            print(f"[REACT-execution] grep.params.target 按用户卡片意图纠正: {t!r} -> card")
            params['target'] = 'card'
        elif exp == 'plan' and t not in ('plan', 'all'):
            print(f"[REACT-execution] grep.params.target 按用户计划意图纠正: {t!r} -> plan")
            params['target'] = 'plan'

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
        import re

        text = f"{todo or ''} {user_input or ''}"
        text_lower = text.lower()
        if 'testcase' in text_lower or 'test_case' in text_lower or '测试用例' in text:
            return 'testcase'
        # Card 总表行（先于「计划」匹配，避免「迭代」误伤）
        if (
            'target=card' in text_lower
            or ' target card' in text_lower
            or '新建卡片' in text
            or '创建卡片' in text
        ):
            return 'card'
        # 迭代列表常见标题 bug1.21 / BUG2．3：含 bug 子串但不是缺陷 Bug 实体；须先于下方裸 bug 关键词
        if re.search(r'bug\s*\d{1,8}\s*[\.．]\s*\d{1,8}', text_lower) or re.search(
            r'(?<![a-z])bug\d{1,8}[\.．]\d{1,8}', text_lower
        ):
            return 'card'
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

    def _spawn_modify_executor_future(
        self,
        tool: Any,
        params: Dict[str, Any],
    ) -> Tuple[asyncio.Future, "queue.Queue[str]"]:
        """
        在线程池启动 modify；返回 (Future, progress_queue)。
        与 ``_execute_tool_implementation`` 共用，供统一流在 ``wait_for`` 期间轮询进度。
        """
        loop = asyncio.get_running_loop()
        progress_q: "queue.Queue[str]" = queue.Queue()
        try:
            from agents.tools.modify_tool import modify_tool_params_log_snapshot

            _pre_spawn = {
                k: v
                for k, v in params.items()
                if k not in ("progress_queue", "progress_callback")
            }
            print(
                "[MODIFY] spawn_executor "
                + json.dumps(
                    modify_tool_params_log_snapshot(dict(_pre_spawn)),
                    ensure_ascii=False,
                    default=str,
                ),
                flush=True,
            )
        except Exception as _se:
            print(f"[MODIFY] spawn_executor 入参日志失败: {_se}; keys={list(params.keys())}", flush=True)
        params["progress_queue"] = progress_q

        def _progress_cb(msg: str):
            try:
                progress_q.put(str(msg))
            except Exception:
                pass

        def _run_modify_in_thread():
            thread_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(thread_loop)
            try:
                params["progress_callback"] = _progress_cb
                if "confirm" not in params:
                    params["confirm"] = False
                return thread_loop.run_until_complete(tool.execute(**params))
            finally:
                thread_loop.close()

        fut = loop.run_in_executor(self._tool_executor, _run_modify_in_thread)
        return fut, progress_q

    async def _iter_modify_side_events_while_task(
        self,
        wait_task: "asyncio.Task[Any]",
        progress_q: "queue.Queue[str]",
        round_idx: int,
        progress_reason: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        """modify 执行期间：进度队列 + DAG buffer → 引擎事件（由调用方 yield）。"""
        while not wait_task.done():
            try:
                while True:
                    msg = progress_q.get_nowait()
                    yield _modify_progress_to_stream_event(
                        msg, round_idx, progress_reason
                    )
            except queue.Empty:
                pass
            for ev in self._drain_tool_task_sse_buffer_list():
                yield ev
            await asyncio.sleep(0.03)
        try:
            while True:
                msg = progress_q.get_nowait()
                yield _modify_progress_to_stream_event(
                    msg, round_idx, progress_reason
                )
        except queue.Empty:
            pass
        for ev in self._drain_tool_task_sse_buffer_list():
            yield ev
    
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
        # 注意：browser_assert / browser_click 等 L1 工具名也含 "browser"，不可一律映射到 browser_test（会缺少 test_case）
        _browser_subtools = frozenset(
            ("browser_assert", "browser_click", "browser_input", "browser_wait")
        )
        _tn = tool_name.lower() if isinstance(tool_name, str) else ""
        if "bug" in _tn and "management" in _tn:
            tool_name = "bug_management"
        elif _tn in _browser_subtools:
            pass
        elif "browser" in _tn:
            tool_name = "browser_test"
        elif "search" in _tn:
            tool_name = "search"
        
        print(f"[REACT] 正在执行工具: {original_tool_name} -> {tool_name}")

        if tool_name == "client_local_bridge" and _client_shell_excludes_local_bridge(
            getattr(self, "_client_shell", None)
        ):
            _loc = normalize_locale(getattr(self, "_ui_locale", None))
            _msg = (
                "当前环境已具备本机执行能力（桌面版或本地代理已连接），请勿使用 client_local_bridge；请使用 terminal 执行本机命令。"
                if not (_loc and str(_loc).lower().startswith("en"))
                else "Local execution is already available (desktop or local proxy connected). Use the `terminal` tool instead of `client_local_bridge`."
            )
            return {
                "success": False,
                "error": _msg,
                "message": _msg,
            }

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

            if tool_name == "grep":
                _grep_ui = (
                    getattr(self, "_react_stream_user_input", None)
                    or params.get("natural_query")
                    or ""
                )
                self._coerce_grep_target_for_user_intent(
                    {"execute": True, "tool": "grep", "params": params},
                    _grep_ui,
                    "",
                )
                self._widen_grep_target_to_include_cards_unless_explicit(
                    params, _grep_ui, ""
                )
                self._force_grep_card_layer_only_if_requested(params, _grep_ui, "")
            
            if tool_name != "modify":
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
                _ui = str(getattr(self, "_react_stream_user_input", None) or "").strip()
                if not str(params.get("intent_combined_text") or "").strip():
                    params["intent_combined_text"] = _ui
                params.setdefault(
                    "intent_last_grep_target",
                    str(getattr(self, "_session_last_grep_target", "") or ""),
                )
                print(
                    f"[REACT] modify 进入线程池执行（target_id={params.get('target_id')}, "
                    f"target_ids={params.get('target_ids')}, target={params.get('target')}）…"
                )
                fut, _progress_q = self._spawn_modify_executor_future(tool, params)
                tool_timeout = int(os.getenv("AGENT_TOOL_TIMEOUT", "120"))
                try:
                    res = await asyncio.wait_for(fut, timeout=tool_timeout)
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
                tool_name in ("modify", "create", "delete")
                and isinstance(res, dict)
                and res.get("success")
                and self._grep_result_cache
            ):
                self._grep_result_cache.clear()
                if os.getenv("PERF_LOG") == "1":
                    print("[PERF][grep_cache] cleared after modify/create/delete success")
            return res
        except Exception as e:
            print(f"[REACT] ❌ 工具执行异常: {str(e)}")
            return {'success': False, 'error': str(e)}
        finally:
            # 临时执行字段仅用于运行期心跳；必须清理，避免后续 JSON 序列化（observe_prompt/UI）报错
            if isinstance(params, dict):
                params.pop('progress_queue', None)
                params.pop('progress_callback', None)
                params.pop("intent_combined_text", None)
                params.pop("intent_last_grep_target", None)
