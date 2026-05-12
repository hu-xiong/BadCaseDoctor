import contextlib
import json
import re
import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence, Dict, Union, Optional, List, Iterator
from urllib.parse import quote_plus

from langchain_community.llms import Tongyi
from langchain_community.utilities import SQLDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from sqlalchemy import Result

from config import Config
from .dashscope_compat import get_dashscope_compat_client
from .prompt_log import maybe_log_llm_chat_kwargs
from .multimodal_content import openai_style_user_content


def _log_compat_stream_first(
    tag: str, model: str, chunk, *, prompt_len: int = 0, first: bool = False
) -> None:
    """compatible-mode 流式首包日志。"""
    if not first:
        return
    try:
        cid = getattr(chunk, "id", None)
        print(
            f"[LLM-COMPAT] {tag} model={model!r} chunk_id={cid!r} prompt_len={prompt_len}"
        )
    except Exception as e:
        print(f"[LLM-COMPAT] {tag} log_failed: {e}")


def _delta_reasoning_content(delta) -> Optional[str]:
    if delta is None:
        return None
    v = getattr(delta, "reasoning_content", None)
    if v:
        return v
    if isinstance(delta, dict):
        return delta.get("reasoning_content")
    return None


def _delta_content(delta) -> Optional[str]:
    if delta is None:
        return None
    v = getattr(delta, "content", None)
    if v:
        return v
    if isinstance(delta, dict):
        return delta.get("content")
    return None


def _norm_qwen_model_id(s: Optional[str]) -> str:
    return (s or "").strip().lower().replace("_", "-")


def _qwen_thinking_debug_enabled() -> bool:
    return (os.getenv("QWEN_THINKING_DEBUG") or "").strip().lower() in ("1", "true", "yes", "on")


def _qwen_thinking_stream_off_env() -> bool:
    """设为 1：请求百炼时不带 enable_thinking，显著缩短 content 首字延迟（无 reasoning 链）。"""
    return (os.getenv("QWEN_THINKING_STREAM_OFF") or "").strip().lower() in ("1", "true", "yes", "on")


def _qwen_first_token_log_enabled() -> bool:
    return (os.getenv("QWEN_FIRST_TOKEN_LOG") or "").strip().lower() in ("1", "true", "yes", "on")


def _is_qwen_max_family_model(model_id: Optional[str]) -> bool:
    """qwen-max / qwen3-max* 等走自动难度思考分支的模型。"""
    m = _norm_qwen_model_id(model_id)
    return m == "qwen-max" or m.startswith("qwen3-max") or "qwen-max-thinking" in m


# ReAct 主循环与 INCR-SUM 后台线程共用一个 QwenLLM 时，勿用实例字段 force_disable_thinking 跨线程传递。
_qwen_tls_suppress = threading.local()


def qwen_suppress_thinking_tls_depth() -> int:
    return int(getattr(_qwen_tls_suppress, "depth", 0) or 0)


@contextlib.contextmanager
def qwen_suppress_thinking_tls_ctx():
    """仅当前线程：标记处于 content_only / 说明流，不污染其它线程对 enable_thinking 的判定。"""
    cur = qwen_suppress_thinking_tls_depth()
    _qwen_tls_suppress.depth = cur + 1
    try:
        yield
    finally:
        d = qwen_suppress_thinking_tls_depth() - 1
        if d <= 0:
            if hasattr(_qwen_tls_suppress, "depth"):
                delattr(_qwen_tls_suppress, "depth")
        else:
            _qwen_tls_suppress.depth = d


class QwenLLM:
    def _supports_deep_thinking(self) -> bool:
        """只对明确支持 enable_thinking 的模型启用深度思考策略。"""
        m = (self.model or "").strip().lower()
        if "thinking" in m:
            return True
        if m in ("qwen-max",) or m.startswith("qwen3-max"):
            return True
        return False

    def _assess_task_difficulty(self, text: str) -> str:
        t = (text or "").strip()
        if not t:
            return "easy"
        try:
            judge_prompt = (
                "你是任务难度评估器。只输出一行：easy 或 hard。\n"
                "判 hard：多步骤/需要分析推理/需要定位原因/涉及多文件修改/涉及复杂约束。\n"
                "判 easy：单步简单问答/简单改一两个字段/短文本。\n"
                f"用户任务：{t}"
            )
            client = get_dashscope_compat_client()
            _judge_kw = {
                "model": "qwen-max",
                "messages": [{"role": "user", "content": judge_prompt}],
            }
            maybe_log_llm_chat_kwargs("qwen", _judge_kw, tag="assess_task_difficulty")
            resp = client.chat.completions.create(**_judge_kw)
            out = (resp.choices[0].message.content or "").strip().lower()
            if "hard" in out:
                return "hard"
            if "easy" in out:
                return "easy"
            return "easy"
        except Exception:
            return "easy"

    def _is_simple_task(self, text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return True
        if len(t) <= 120 and not any(
            k in t
            for k in (
                "分析",
                "定位",
                "排查",
                "原因",
                "为什么",
                "如何",
                "方案",
                "对比",
                "权衡",
                "步骤",
                "同时",
                "分别",
            )
        ):
            return True
        return False

    def _thinking_enabled_for(self, text: str) -> bool:
        if qwen_suppress_thinking_tls_depth() > 0:
            return False
        if _qwen_thinking_stream_off_env():
            return False
        if getattr(self, "force_disable_thinking", False):
            return False
        if self._is_qwen_thinking_disabled_for_model():
            return False
        if self.enable_thinking:
            return True
        model = (self.model or "").strip().lower()
        if model == "qwen-max" and self._supports_deep_thinking():
            diff = self._assess_task_difficulty(text)
            out = diff == "hard"
            if _qwen_thinking_debug_enabled():
                print(
                    f"[QWEN-THINKING] qwen-max difficulty_assess={diff!r} -> enable_thinking={out}",
                    flush=True,
                )
            return out
        if model == "glm-5":
            mode = (os.getenv("GLM5_THINKING_MODE", "auto") or "auto").strip().lower()
            if mode == "always":
                return True
            if mode == "never":
                return False
            return self._assess_task_difficulty(text) == "hard"
        return False

    def _is_qwen_thinking_disabled_for_model(self) -> bool:
        """名单内模型不启用 thinking（含自动难度开的 qwen-max / glm-5 分支）。"""
        raw = getattr(Config, "QWEN_THINKING_DISABLE_MODELS", "") or ""
        raw = str(raw).strip()
        if not raw:
            return False
        mid = _norm_qwen_model_id(self.model)
        for part in raw.split(","):
            pat = _norm_qwen_model_id(part)
            if not pat:
                continue
            if pat.endswith("*"):
                p = pat[:-1]
                if p and mid.startswith(p):
                    return True
            elif mid == pat:
                return True
        return False

    def __init__(self, model: str = None):
        print(f"[QWEN-LLM-INIT] 传入的 model 参数：{model}")

        self.enable_thinking = False
        self.force_disable_thinking = False
        self._oa = None  # lazy OpenAI 兼容客户端缓存（按实例）

        if model == "qwen-max-thinking":
            self.model = "qwen-max"
            self.enable_thinking = False
            print(
                "[QWEN-LLM-INIT] 使用旧别名 qwen-max-thinking -> qwen-max (auto thinking)"
            )
        else:
            self.model = model or getattr(Config, "DASHSCOPE_MODEL", None) or Config.QWEN_API_MODEL
            print(f"[QWEN-LLM-INIT] 使用其他模型：{self.model}")
            if isinstance(self.model, str) and ("thinking" in self.model.lower()):
                self.enable_thinking = True

        print(f"[QWEN-LLM-INIT] 最终使用的模型：{self.model}（OpenAI 兼容 /chat/completions）")
        if self._is_qwen_thinking_disabled_for_model():
            print(
                "[QWEN-LLM-INIT] 本模型在 QWEN_THINKING_DISABLE_MODELS 中，已关闭思考链（reasoning）"
            )

        self.conversation_history = []
        self.executor = ThreadPoolExecutor(max_workers=3)

    def _get_client(self):
        if self._oa is None:
            self._oa = get_dashscope_compat_client()
        return self._oa

    def _apply_qwen_thinking_extra_body(
        self, kwargs: Dict[str, Any], *, enable_thinking: bool
    ) -> None:
        if enable_thinking:
            kwargs["extra_body"] = {"enable_thinking": True}
        elif getattr(Config, "QWEN_EXPLICIT_DISABLE_THINKING_BODY", True):
            kwargs["extra_body"] = {"enable_thinking": False}

    def _chat_create(
        self,
        messages: List[Dict[str, Any]],
        *,
        stream: bool,
        enable_thinking: bool,
        max_tokens: Optional[int] = None,
    ):
        kwargs: Dict[str, Any] = {"model": self.model, "messages": messages}
        if max_tokens is not None and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens
        self._apply_qwen_thinking_extra_body(kwargs, enable_thinking=enable_thinking)
        if stream:
            kwargs["stream"] = True
        if stream and _is_qwen_max_family_model(self.model):
            print(
                "[QWEN-THINKING] _chat_create "
                f"model={self.model!r} stream=True "
                f"request_enable_thinking={enable_thinking} "
                f"extra_body={kwargs.get('extra_body')!r} "
                f"force_disable_thinking={getattr(self, 'force_disable_thinking', False)} "
                f"self.enable_thinking_flag={getattr(self, 'enable_thinking', False)} "
                f"disabled_by_env_list={self._is_qwen_thinking_disabled_for_model()}",
                flush=True,
            )
        maybe_log_llm_chat_kwargs(
            "qwen",
            kwargs,
            tag=f"_chat_create thinking={enable_thinking}",
        )
        return self._get_client().chat.completions.create(**kwargs)

    def chat_completion_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        parallel_tool_calls: bool = False,
        max_tokens: Optional[int] = None,
    ):
        """
        百炼 OpenAI 兼容 /chat/completions：透传 tools、tool_choice、parallel_tool_calls。
        ReAct 决策步使用；不开启 enable_thinking，避免干扰结构化 tool 参数。
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "parallel_tool_calls": parallel_tool_calls,
            "stream": False,
        }
        if max_tokens is not None and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens
        self._apply_qwen_thinking_extra_body(kwargs, enable_thinking=False)
        maybe_log_llm_chat_kwargs("qwen", kwargs, tag="chat_completion_with_tools")
        return self._get_client().chat.completions.create(**kwargs)

    def chat_completion_with_tools_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        parallel_tool_calls: bool = False,
        max_tokens: Optional[int] = None,
    ) -> Iterator[Any]:
        """
        流式 FC：与 chat_completion_with_tools 相同参数，stream=True。
        迭代 yield 原生 chunk（OpenAI SDK ChatCompletionChunk），供 ReAct 边收边推 agent_thought、累积 tool_calls。
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "parallel_tool_calls": parallel_tool_calls,
            "stream": True,
        }
        if max_tokens is not None and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens
        self._apply_qwen_thinking_extra_body(kwargs, enable_thinking=False)
        maybe_log_llm_chat_kwargs("qwen", kwargs, tag="chat_completion_with_tools_stream")
        stream = self._get_client().chat.completions.create(**kwargs)
        for chunk in stream:
            yield chunk

    def chat_completion_messages(self, messages: List[Dict[str, Any]]):
        """
        仅 messages、非流式；用于 FC 第二轮（user + assistant.tool_calls + tool + user）等，不传 tools。
        """
        _kw: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        self._apply_qwen_thinking_extra_body(_kw, enable_thinking=False)
        maybe_log_llm_chat_kwargs("qwen", _kw, tag="chat_completion_messages")
        return self._get_client().chat.completions.create(**_kw)

    async def parse_intent(
        self, user_input: str, history: list = None, locale: Optional[str] = None
    ) -> Optional[dict]:
        """异步方法：在线程池中运行同步 API 调用"""

        def _sync_parse():
            from agents.locale_prompts import wrap_general_user_prompt

            user_input_wrapped = wrap_general_user_prompt(user_input, locale)
            if "<system>" in user_input or "<format>" in user_input or "必须返回" in user_input:
                messages = [{"role": "user", "content": user_input_wrapped}]
                eth = self._thinking_enabled_for(user_input)
                if eth:
                    print(f"[QWEN-LLM-PARSE] enable_thinking=True model={self.model}")
                else:
                    print(f"[QWEN-LLM-PARSE] 未开启思考模式：model={self.model}")
                try:
                    resp = self._chat_create(
                        messages, stream=False, enable_thinking=eth
                    )
                    text = (resp.choices[0].message.content or "").strip()
                    try:
                        return json.loads(text)
                    except Exception:
                        return text
                except Exception as e:
                    print(f"[QWEN-LLM-PARSE] compatible 调用失败: {e}")
                    return None

            example_json = '[{"agent": "", "planActions": "", "action": "", "script": ""}, {"agent": "", "planActions": "", "action": "", "script": ""}]'
            print("#" * 50)
            history_text = ""
            if history:
                history_text = "\n历史对话:\n"
                for msg in history:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    history_text += f"{role}: {content}\n"

            prompt = f"""
        你是一个智能路由助手。请根据用户输入和历史对话，**严格输出一个 JSON 数组**，不要任何其他内容（不要解释、不要代码块、不要 Markdown）。
                
        每个数组元素是一个任务对象，包含以下字段：
        - "agent": 字符串，值必须是 ["redis_agent", "mysql_agent", "bug_management_agent", "other", "scriptAgent"] 之一。
        - "planActions": 字符串，详细描述该任务的执行步骤。
        - "action": 字符串，表示操作类型。对于 bug_management_agent，可选值包括："list", "create", "update", "delete", "assign", "change_status", "search"。
        - "info": 对象，包含数据库/Redis 连接信息或 Bug 相关参数（如 project_id, title, status 等）。
        - "script": 字符串，是分配给子任务的具体指令。
        - "isflag": 布尔值，如果是判断类问题（如"是否存在？"、"是否成功？"），设为 true，否则 false。
                
        输出必须是合法 JSON，可被 Python json.loads() 解析。
        不要包含任何额外文本、注释、反引号或说明。
                
        历史对话:
        {history_text}
                
        当前用户输入："{user_input}"
        """.strip()

            prompt = wrap_general_user_prompt(prompt, locale)
            messages = [{"role": "user", "content": prompt}]
            eth = self._thinking_enabled_for(prompt)
            if eth:
                print(f"[QWEN-LLM-PARSE] enable_thinking=True model={self.model}")
            else:
                print(f"[QWEN-LLM-PARSE] 未开启思考模式：model={self.model}")
            try:
                resp = self._chat_create(messages, stream=False, enable_thinking=eth)
                msg = resp.choices[0].message
                reasoning = getattr(msg, "reasoning_content", None)
                if reasoning:
                    print(f"[QWEN-LLM-PARSE] reasoning_len={len(reasoning)}")
                text = (msg.content or "").strip()
                return json.loads(text)
            except json.JSONDecodeError as e:
                print(f"JSON 解析错误：{e}")
                return {"agent": "other", "action": "other", "info": {}}
            except Exception as e:
                print(f"[QWEN-LLM-PARSE] error: {e}")
                return {"agent": "other", "action": "other", "info": {}}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync_parse)

    def chat_stream(
        self,
        prompt: str,
        history: list = None,
        locale: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ):
        """流式聊天方法 (同步生成器，方便 Flask 使用)。max_tokens 供 ReAct observe 等场景可选上限。"""
        from agents.locale_prompts import wrap_general_user_prompt

        p = wrap_general_user_prompt(prompt, locale)
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": p})

        eth = self._thinking_enabled_for(p)
        if eth:
            print(f"[QWEN-LLM-STREAM] enable_thinking=True model={self.model}")
        else:
            print(f"[QWEN-LLM-STREAM] 未开启思考模式：model={self.model}")
        try:
            stream = self._chat_create(
                messages, stream=True, enable_thinking=eth, max_tokens=max_tokens
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                d = chunk.choices[0].delta
                c = _delta_content(d)
                if c:
                    yield c
        except Exception as e:
            yield f"Error: {e}"

    def chat_stream_with_reasoning(
        self,
        prompt: str,
        history: list = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[Dict[str, Any]]:
        messages = []
        if history:
            messages.extend(history)
        messages.append(
            {"role": "user", "content": openai_style_user_content(prompt, images)}
        )
        eth = self._thinking_enabled_for(prompt)
        if eth:
            print(f"[QWEN-LLM-STREAM-REASONING] enable_thinking=True model={self.model}")
        if _is_qwen_max_family_model(self.model):
            print(
                "[QWEN-THINKING] chat_stream_with_reasoning "
                f"model={self.model!r} request_enable_thinking={eth} "
                f"(实例 enable_thinking 标志={self.enable_thinking}；"
                f"随后一行 [QWEN-THINKING] _chat_create 为真正发往百炼的 extra_body)",
                flush=True,
            )
        _pl = len(prompt) if isinstance(prompt, str) else 0

        try:
            stream = self._chat_create(
                messages, stream=True, enable_thinking=eth, max_tokens=max_tokens
            )
            _first = True
            _t0 = time.monotonic()
            _first_reasoning_s: Optional[float] = None
            _first_content_s: Optional[float] = None
            _n_rc = 0
            _n_ct = 0
            for chunk in stream:
                _log_compat_stream_first(
                    "chat_stream_with_reasoning",
                    self.model,
                    chunk,
                    prompt_len=_pl,
                    first=_first,
                )
                _first = False
                if not chunk.choices:
                    continue
                d = chunk.choices[0].delta
                rc = _delta_reasoning_content(d)
                if rc and isinstance(rc, str):
                    _n_rc += 1
                    if _first_reasoning_s is None:
                        _first_reasoning_s = time.monotonic() - _t0
                    yield {"type": "reasoning_delta", "delta": rc}
                ct = _delta_content(d)
                if ct and isinstance(ct, str):
                    _n_ct += 1
                    if _first_content_s is None:
                        _first_content_s = time.monotonic() - _t0
                    yield {"type": "content_delta", "delta": ct}
            if _qwen_first_token_log_enabled():
                _gap = (
                    None
                    if _first_reasoning_s is None or _first_content_s is None
                    else (_first_content_s - _first_reasoning_s)
                )
                print(
                    "[QWEN-TTFT] chat_stream_with_reasoning "
                    f"model={self.model!r} enable_thinking={eth} "
                    f"first_reasoning_s={_first_reasoning_s} first_content_s={_first_content_s} "
                    f"content_after_reasoning_s={_gap} "
                    f"chunks_reasoning={_n_rc} chunks_content={_n_ct}",
                    flush=True,
                )
            yield {"type": "done"}
        except Exception as e:
            yield {"type": "content_delta", "delta": f"Error: {e}"}
            yield {"type": "done"}

    def chat_stream_fallback_chunks(
        self,
        prompt: str,
        history: list = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if history:
            messages.extend(history)
        messages.append(
            {"role": "user", "content": openai_style_user_content(prompt, images)}
        )
        eth = self._thinking_enabled_for(prompt)
        _pl = len(prompt) if isinstance(prompt, str) else 0
        try:
            resp = self._chat_create(
                messages, stream=False, enable_thinking=eth, max_tokens=max_tokens
            )
            _log_compat_stream_first(
                "chat_stream_fallback_chunks",
                self.model,
                resp,
                prompt_len=_pl,
                first=True,
            )
            msg = resp.choices[0].message
            rc = getattr(msg, "reasoning_content", None)
            if rc and isinstance(rc, str) and rc.strip():
                for i in range(0, len(rc), 64):
                    yield {"type": "reasoning_delta", "delta": rc[i : i + 64]}
            ct = (getattr(msg, "content", None) or "").strip()
            for i in range(0, len(ct), 64):
                yield {"type": "content_delta", "delta": ct[i : i + 64]}
        except Exception as e:
            yield {"type": "content_delta", "delta": f"Error: {e}"}
        yield {"type": "done"}

    async def chat(self, prompt: str, history: list = None) -> str:
        """通用聊天方法，直接返回文本"""

        def _sync_chat():
            messages = [{"role": "user", "content": prompt}]
            eth = self.enable_thinking
            if eth:
                print(f"[QWEN-LLM-CHAT] enable_thinking=True model={self.model}")
            else:
                print(f"[QWEN-LLM-CHAT] 未开启思考模式：model={self.model}")
            try:
                resp = self._chat_create(
                    messages, stream=False, enable_thinking=eth
                )
                return resp.choices[0].message.content or ""
            except Exception as e:
                return f"Error: {e}"

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync_chat)

    async def chat_with_reasoning(self, prompt: str, history: list = None) -> Dict[str, Any]:
        def _sync_chat_with_reasoning():
            reasoning_parts: List[str] = []
            content_parts: List[str] = []
            try:
                for item in self.chat_stream_with_reasoning(prompt, history):
                    if not isinstance(item, dict):
                        continue
                    typ = item.get("type")
                    if typ == "reasoning_delta":
                        d = item.get("delta")
                        if isinstance(d, str) and d:
                            reasoning_parts.append(d)
                    elif typ == "content_delta":
                        d = item.get("delta") or ""
                        if d:
                            content_parts.append(d)
            except Exception as e:
                print(f"[QWEN-LLM-REASONING] 汇总流式结果异常: {e}")
                return {"content": f"Error: {e}", "reasoning_content": None}
            rc_joined = "".join(reasoning_parts).strip() or None
            ct = "".join(content_parts).strip()
            if rc_joined:
                print(f"[QWEN-LLM-REASONING] reasoning_len={len(rc_joined)}")
            return {"content": ct, "reasoning_content": rc_joined}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync_chat_with_reasoning)

    def dealMysql(self, user_input: str, info: str, history: list = None) -> Dict[
        str, Union[int, str, Sequence[Dict[str, Any]], Result]]:
        print("info=====", info)
        if isinstance(info, list):
            if len(info) != 5:
                raise ValueError("List must have 5 elements: [user, pass, host, port, db]")
            keys = ["username", "password", "host", "port", "database"]
            info = dict(zip(keys, info))

        url = "mysql+pymysql://{}:{}@{}:{}/{}"
        print(type(info))
        print(info)
        uri = url.format(
            quote_plus(info["username"]),
            quote_plus(info["password"]),
            info["host"],
            info["port"],
            info["database"],
        )
        print("uri", uri)

        db = SQLDatabase.from_uri(uri)
        template = """
        Given the following database schema:
        {schema}

        Generate a MySQL query for this question: {question}

        Only output the SQL, no explanation.
        You are a precise SQL generator for any database.

        ### Rules:
        1. Analyze the database schema carefully.
        2. Identify which table(s) contain the data needed to answer the question.
        3. ONLY use tables that are directly relevant to the question. Do NOT include unrelated tables unless explicitly mentioned in the question.
        4. When the question requests data from related tables (e.g., "order and order details", "user and their orders"), use JOINs to combine the data in a single query.
        5. When the question explicitly asks for multiple related entities (e.g., "orders and their details"), use appropriate JOINs (INNER JOIN, LEFT JOIN, etc.) to connect them based on table relationships and foreign keys.
        6. Use table aliases to make queries more readable (e.g., o for order_info, od for order_detail).
        7. Generate efficient queries with proper JOIN conditions and WHERE clauses.
        8. For queries involving related data like "order and details", always use JOIN instead of separate queries.
        9. Generate exactly ONE SELECT statement that may include multiple tables if they are directly related to the question.
        """

        llm = Tongyi(
            model="qwen-turbo",
            api_key=Config.QWEN_API_KEY,
            temperature=0,
        )
        print("===MySQL Multi-table Query====")
        prompt = ChatPromptTemplate.from_template(template)
        chain = (
            {"schema": lambda _: db.get_table_info(), "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
        sql = chain.invoke(user_input)
        print("sql", sql)

        try:
            result = db._execute(sql)
            return {"code": 200, "script": sql, "task": user_input, "message": "success", "data": result}
        except Exception as e:
            return {
                "code": 500,
                "script": sql,
                "task": user_input,
                "message": f"Error executing query: {str(e)}",
                "data": None,
            }

    def _compat_json_text(self, prompt: str) -> Optional[str]:
        """非流式：返回模型输出文本。"""
        try:
            resp = self._chat_create(
                [{"role": "user", "content": prompt}],
                stream=False,
                enable_thinking=False,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"[QWEN-LLM] _compat_json_text error: {e}")
            return None

    def dealRedis(self, user_input: str, info: str, history: list = None):
        prompt = f"""
        该任务是redis任务，要生成可执行的的python的redis脚本:
        输入:{user_input}
        用户信息:{info}
        只输出标准json，不要任何格式，不要任何解释，以供代码解析，不要多余字节，要可以给
        - python-script 为python的执行脚本，只是该语句的脚本，不要引包，不要连接，如查询redis的key为12，则是r.get("12")
        - script为redis原始命令
        """
        raw = self._compat_json_text(prompt)
        if not raw:
            return {"agent": "other", "action": "other", "info": {}}
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()
        print("redis", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误: {e}")
            return {"agent": "other", "action": "other", "info": {}}

    def splitTask(self, user_input: str, info: str, history: list = None):
        prompt = f"""
        该任务是将用户的描述细分化，要将任务拆分成每一个小步骤，如排查host1，host2，host3，是否有文件aa是否有error存在，则生成多个对象，1.校验各个host是否联通，2.查找文件aa位置，3.打开文件aa，4.查找error，5退出操作，如，要生成执行步骤:
        每个步骤都用一个json对象表示，格式为:
         每个数组元素是一个任务对象，包含以下字段：
            "task":"任务名词",  
            "info": "任务具体步骤，将任务详情化"
        输入:{user_input}
        用户信息:{info}
        只输出标准json，不要任何格式，不要任何解释，以供代码解析，不要多余字节，要可以给
        """
        raw = self._compat_json_text(prompt)
        if not raw:
            return {"agent": "other", "action": "other", "info": {}}
        try:
            print("=--=")
            print(raw)
            print("----===0")
            return json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误: {e}")
            return {"agent": "other", "action": "other", "info": {}}

    def generateScript(self, user_input: str, info: str, history: list = None):
        prompt = f"""
        该任务是生成linux脚本，请生成
        输入:{user_input}
        用户信息:{info}
        只输出标准json，不要任何格式，不要任何解释，以供代码解析，不要多余字节，要可以给
        """
        raw = self._compat_json_text(prompt)
        if not raw:
            return {"agent": "other", "action": "other", "info": {}}
        try:
            print("=--=")
            print(raw)
            print("----===0")
            return json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误: {e}")
            return {"agent": "other", "action": "other", "info": {}}

    def dealScript(self, user_input: str, info: str, history: list = None):
        print("dealScript", user_input)
        print("uiiy-" * 30)
        print(user_input)
        prompt = f"""
        该任务是生成将各个任务linux脚本合成一个可执行的脚本，请生成
        输入:{user_input}
        用户信息:{info}
        只输出标准json，不要任何格式，不要任何解释，以供代码解析，不要多余字节，要可以给
        """
        raw = self._compat_json_text(prompt)
        if not raw:
            return {"agent": "other", "action": "other", "info": {}}
        try:
            print("=--=")
            print(raw)
            print("----===0")
            return json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误: {e}")
            return {"agent": "other", "action": "other", "info": {}}
