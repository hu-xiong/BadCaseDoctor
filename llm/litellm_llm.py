# -*- coding: utf-8 -*-
"""
LiteLLM 适配器：对齐 QwenLLM/DeepSeekLLM 的 FC 表面，供 ReAct / LangGraph 使用。

不负责 Auto 选模（见 model_router）；仅做 completion 传输与 endpoint fallback。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Union

from .litellm_transport import (
    LiteLLMEndpoint,
    endpoints_for_request,
    litellm_num_retries,
)
from .prompt_log import maybe_log_llm_chat_kwargs, maybe_log_llm_response_body

logger = logging.getLogger(__name__)


def _import_litellm():
    try:
        import litellm

        return litellm
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "未安装 litellm。请执行: pip install 'litellm>=1.50.0,<2'\n"
            "或设置 LLM_TRANSPORT=native 使用原厂 SDK"
        ) from e


class LiteLLMLLM:
    """OpenAI 兼容 completion，经 LiteLLM 发往各厂商。"""

    def __init__(self, model: Optional[str] = None):
        self.model = (model or "").strip() or "qwen3.5-plus"
        self._litellm = _import_litellm()
        # 降低 litellm 默认啰嗦日志
        try:
            self._litellm.suppress_debug_info = True
        except Exception:
            pass

    def _kwargs_for_endpoint(
        self,
        ep: LiteLLMEndpoint,
        *,
        messages: List[Dict[str, Any]],
        stream: bool,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        parallel_tool_calls: bool = False,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        kw: Dict[str, Any] = {
            "model": ep.litellm_model,
            "messages": messages,
            "stream": stream,
            "api_key": ep.api_key or None,
            "num_retries": litellm_num_retries(),
        }
        if ep.api_base:
            kw["api_base"] = ep.api_base
        if tools:
            kw["tools"] = tools
            kw["tool_choice"] = tool_choice
            # 部分厂商不支持 parallel_tool_calls；失败时由上层 fallback
            kw["parallel_tool_calls"] = parallel_tool_calls
        if max_tokens is not None and max_tokens > 0:
            kw["max_tokens"] = max_tokens
        return kw

    def _completion_with_fallback(self, **base_kw) -> Any:
        chain = endpoints_for_request(self.model)
        last_err: Optional[BaseException] = None
        for i, ep in enumerate(chain):
            kw = dict(base_kw)
            kw["model"] = ep.litellm_model
            kw["api_key"] = ep.api_key or None
            if ep.api_base:
                kw["api_base"] = ep.api_base
            else:
                kw.pop("api_base", None)
            try:
                maybe_log_llm_chat_kwargs("litellm", kw, tag=f"completion[{ep.provider}]")
                print(
                    f"[LITELLM] try#{i} business={ep.business_model_id!r} "
                    f"litellm={ep.litellm_model!r} base={ep.api_base!r}",
                    flush=True,
                )
                return self._litellm.completion(**kw)
            except Exception as e:
                last_err = e
                logger.warning(
                    "[LITELLM] endpoint failed business=%s err=%s",
                    ep.business_model_id,
                    e,
                )
                print(f"[LITELLM] fail#{i} {ep.business_model_id}: {e}", flush=True)
                continue
        if last_err is not None:
            raise last_err
        raise RuntimeError("LiteLLM: no endpoints configured")

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
        chain = endpoints_for_request(self.model)
        last_err: Optional[BaseException] = None
        for i, ep in enumerate(chain):
            kw = self._kwargs_for_endpoint(
                ep,
                messages=messages,
                stream=False,
                tools=tools,
                tool_choice=tool_choice,
                parallel_tool_calls=parallel_tool_calls,
                max_tokens=max_tokens,
            )
            try:
                maybe_log_llm_chat_kwargs("litellm", kw, tag="chat_completion_with_tools")
                print(
                    f"[LITELLM] FC try#{i} {ep.business_model_id} → {ep.litellm_model}",
                    flush=True,
                )
                resp = self._litellm.completion(**kw)
                maybe_log_llm_response_body(
                    "litellm",
                    {"model": ep.business_model_id},
                    tag="chat_completion_with_tools",
                    model=ep.business_model_id,
                )
                return resp
            except TypeError:
                # 个别后端不认 parallel_tool_calls
                kw.pop("parallel_tool_calls", None)
                try:
                    return self._litellm.completion(**kw)
                except Exception as e2:
                    last_err = e2
                    print(f"[LITELLM] FC fail#{i} {ep.business_model_id}: {e2}", flush=True)
                    continue
            except Exception as e:
                last_err = e
                print(f"[LITELLM] FC fail#{i} {ep.business_model_id}: {e}", flush=True)
                continue
        if last_err is not None:
            raise last_err
        raise RuntimeError("LiteLLM FC: no endpoints")

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
        # 流式：仅主 endpoint（fallback 难以半截切换）
        ep = endpoints_for_request(self.model)[0]
        kw = self._kwargs_for_endpoint(
            ep,
            messages=messages,
            stream=True,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            max_tokens=max_tokens,
        )
        maybe_log_llm_chat_kwargs("litellm", kw, tag="chat_completion_with_tools_stream")
        try:
            stream = self._litellm.completion(**kw)
        except TypeError:
            kw.pop("parallel_tool_calls", None)
            stream = self._litellm.completion(**kw)
        for chunk in stream:
            yield chunk

    def chat_completion_messages(self, messages: List[Dict[str, Any]]):
        from llm.chat_messages import normalize_chat_messages

        messages = normalize_chat_messages(messages)
        return self._completion_with_fallback(messages=messages, stream=False)

    def chat(self, prompt: str, history: list = None) -> str:
        from llm.chat_messages import prompt_to_messages

        messages = prompt_to_messages(prompt, history=history)
        resp = self._completion_with_fallback(messages=messages, stream=False)
        try:
            return (resp.choices[0].message.content or "") if resp.choices else ""
        except Exception:
            return str(resp)

    def chat_stream_fallback_chunks(
        self, prompt: str, history: list = None
    ) -> Iterator[Dict[str, Any]]:
        from llm.chat_messages import prompt_to_messages

        messages = prompt_to_messages(prompt, history=history)
        ep = endpoints_for_request(self.model)[0]
        kw = self._kwargs_for_endpoint(ep, messages=messages, stream=True)
        stream = self._litellm.completion(**kw)
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None) or ""
                if content:
                    yield {"type": "content", "text": content}
            except Exception:
                continue
