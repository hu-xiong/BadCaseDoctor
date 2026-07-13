# -*- coding: utf-8 -*-
"""
火山方舟（Ark）豆包大模型 — OpenAI 兼容 Chat Completions API。
文档：https://www.volcengine.com/docs/82379
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterator, List, Optional, Union

from openai import OpenAI

from config import Config

from .prompt_log import (
    maybe_log_llm_chat_kwargs,
    maybe_log_llm_openai_completion,
    maybe_log_llm_response_body,
    maybe_log_llm_stream_assembled,
)


def _delta_content(delta: Any) -> Optional[str]:
    if delta is None:
        return None
    v = getattr(delta, "content", None)
    if v:
        return v
    if isinstance(delta, dict):
        return delta.get("content")
    return None


class DoubaoLLM:
    """豆包（火山方舟 Ark OpenAI 兼容接口）。"""

    def __init__(self, model: Optional[str] = None):
        self.model = (model or getattr(Config, "DOUBAO_MODEL", None) or "doubao-1-5-pro-32k").strip()
        self.force_disable_thinking = False
        self.enable_thinking = False
        self._oa: Optional[OpenAI] = None
        self.executor = ThreadPoolExecutor(max_workers=3)
        if not (getattr(Config, "DOUBAO_API_KEY", None) or "").strip():
            print("[DOUBAO-LLM] 警告：未配置 DOUBAO_API_KEY，调用将失败")

    def _get_client(self) -> OpenAI:
        if self._oa is None:
            key = (getattr(Config, "DOUBAO_API_KEY", None) or "").strip()
            if not key:
                raise ValueError("未配置 DOUBAO_API_KEY")
            base = (
                getattr(Config, "DOUBAO_API_BASE_URL", None)
                or "https://ark.cn-beijing.volces.com/api/v3"
            ).strip().rstrip("/")
            self._oa = OpenAI(api_key=key, base_url=base)
        return self._oa

    def _temperature(self) -> float:
        try:
            return float(os.getenv("DOUBAO_TEMPERATURE", str(getattr(Config, "DOUBAO_TEMPERATURE", 0.7))))
        except Exception:
            return 0.7

    def _chat_create(
        self,
        messages: List[Dict[str, Any]],
        *,
        stream: bool,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Union[str, Dict[str, Any], None] = None,
        parallel_tool_calls: bool = False,
    ):
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": self._temperature(),
        }
        if max_tokens is not None and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens
        if tools is not None:
            kwargs["tools"] = tools
            kwargs["parallel_tool_calls"] = parallel_tool_calls
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice
        if stream:
            kwargs["stream_options"] = {"include_usage": True}
        maybe_log_llm_chat_kwargs("doubao", kwargs, tag="_chat_create")
        resp = self._get_client().chat.completions.create(**kwargs)
        if not stream:
            maybe_log_llm_openai_completion("doubao", resp, tag="_chat_create", model=self.model)
        return resp

    def chat_completion_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        parallel_tool_calls: bool = False,
        max_tokens: Optional[int] = None,
    ):
        from llm.chat_messages import normalize_chat_messages

        messages = normalize_chat_messages(messages)
        resp = self._chat_create(
            messages,
            stream=False,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
        )
        msg = resp.choices[0].message
        out: Dict[str, Any] = {"role": "assistant", "content": getattr(msg, "content", None) or ""}
        tcs = getattr(msg, "tool_calls", None)
        if tcs:
            serialized = []
            for tc in tcs:
                fn = getattr(tc, "function", None)
                serialized.append(
                    {
                        "id": getattr(tc, "id", "") or "",
                        "type": getattr(tc, "type", None) or "function",
                        "function": {
                            "name": getattr(fn, "name", "") if fn else "",
                            "arguments": getattr(fn, "arguments", "") if fn else "",
                        },
                    }
                )
            out["tool_calls"] = serialized
        else:
            out["tool_calls"] = None
        maybe_log_llm_response_body("doubao", out, tag="chat_completion_with_tools", model=self.model)
        return out

    def chat_completion_with_tools_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        parallel_tool_calls: bool = False,
        max_tokens: Optional[int] = None,
    ) -> Iterator[Any]:
        from llm.chat_messages import normalize_chat_messages

        messages = normalize_chat_messages(messages)
        stream = self._chat_create(
            messages,
            stream=True,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
        )
        for chunk in stream:
            yield chunk

    def chat_completion_messages(self, messages: List[Dict[str, Any]]):
        return self._chat_create(messages, stream=False)

    def chat_stream_with_reasoning(
        self,
        prompt: str,
        history: Optional[list] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[Dict[str, Any]]:
        from llm.chat_messages import prompt_to_messages

        messages = prompt_to_messages(prompt, history=history, images=images)
        try:
            stream = self._chat_create(messages, stream=True, max_tokens=max_tokens)
            _acc_ct: List[str] = []
            _last_usage = None
            for chunk in stream:
                u = getattr(chunk, "usage", None)
                if u is not None:
                    _last_usage = u
                if not chunk.choices:
                    continue
                ct = _delta_content(chunk.choices[0].delta)
                if ct and isinstance(ct, str):
                    _acc_ct.append(ct)
                    yield {"type": "content_delta", "delta": ct}
            maybe_log_llm_stream_assembled(
                "doubao",
                tag="chat_stream_with_reasoning",
                model=self.model,
                content="".join(_acc_ct),
                usage=_last_usage,
            )
            yield {"type": "done"}
        except Exception as e:
            yield {"type": "content_delta", "delta": f"Error: {e}"}
            yield {"type": "done"}

    def chat_stream_fallback_chunks(
        self,
        prompt: str,
        history: Optional[list] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[Dict[str, Any]]:
        from llm.chat_messages import prompt_to_messages

        messages = prompt_to_messages(prompt, history=history, images=images)
        try:
            resp = self._chat_create(messages, stream=False, max_tokens=max_tokens)
            maybe_log_llm_openai_completion("doubao", resp, tag="chat_stream_fallback_chunks", model=self.model)
            ct = (resp.choices[0].message.content or "").strip()
            for i in range(0, len(ct), 64):
                yield {"type": "content_delta", "delta": ct[i : i + 64]}
        except Exception as e:
            yield {"type": "content_delta", "delta": f"Error: {e}"}
        yield {"type": "done"}

    def chat_stream(
        self,
        prompt: str,
        history: Optional[list] = None,
        locale: Optional[str] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[Dict[str, Any]]] = None,
    ):
        from agents.locale_prompts import wrap_general_user_prompt

        p = wrap_general_user_prompt(prompt, locale)
        for item in self.chat_stream_with_reasoning(
            p, history, max_tokens=max_tokens, images=images
        ):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "content_delta":
                d = item.get("delta") or ""
                if isinstance(d, str) and d:
                    yield d

    async def chat(self, prompt: str, history: Optional[list] = None) -> str:
        def _sync() -> str:
            from llm.chat_messages import prompt_to_messages

            messages = prompt_to_messages(prompt, history=history)
            resp = self._chat_create(messages, stream=False)
            return (resp.choices[0].message.content or "").strip()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync)

    async def chat_with_reasoning(self, prompt: str, history: Optional[list] = None) -> Dict[str, Any]:
        def _sync() -> Dict[str, Any]:
            content_parts: List[str] = []
            try:
                for item in self.chat_stream_with_reasoning(prompt, history):
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "content_delta":
                        d = item.get("delta") or ""
                        if d:
                            content_parts.append(d)
            except Exception as e:
                return {"content": f"Error: {e}", "reasoning_content": None}
            return {"content": "".join(content_parts).strip(), "reasoning_content": None}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync)

    async def parse_intent(
        self, user_input: str, history: Optional[list] = None, locale: Optional[str] = None
    ) -> Optional[dict]:
        from agents.locale_prompts import wrap_general_user_prompt

        def _sync_parse() -> Optional[dict]:
            user_input_wrapped = wrap_general_user_prompt(user_input, locale)
            if "<system>" in user_input or "<format>" in user_input or "必须返回" in user_input:
                from llm.chat_messages import prompt_to_messages

                messages = prompt_to_messages(user_input_wrapped)
                try:
                    resp = self._chat_create(messages, stream=False)
                    text = (resp.choices[0].message.content or "").strip()
                    try:
                        return json.loads(text)
                    except Exception:
                        return text
                except Exception as e:
                    print(f"[DOUBAO-LLM-PARSE] error: {e}")
                    return None

            prompt = user_input_wrapped
            if not ("JSON" in prompt or "json" in prompt):
                prompt += "\n请务必只返回 JSON 格式结果。"
            messages = [{"role": "user", "content": prompt}]
            try:
                resp = self._chat_create(messages, stream=False)
                text = (resp.choices[0].message.content or "").strip()
                json_match = re.search(r"\[.*\]|\{.*\}", text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                return json.loads(text)
            except Exception as e:
                print(f"[DOUBAO-LLM-PARSE] error: {e}")
                return {"agent": "other", "action": "other", "info": {}}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync_parse)
