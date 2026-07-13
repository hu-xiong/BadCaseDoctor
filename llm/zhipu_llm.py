# llm/zhipu_llm.py
"""
智谱GLM大模型适配器
支持GLM-5等模型
"""

import json
import asyncio
from typing import Any, Dict, Optional, List, Iterator
import requests
import os
from config import Config
from .http_session import get_session
from .prompt_log import (
    maybe_log_llm_chat_kwargs,
    maybe_log_llm_response_body,
    maybe_log_llm_stream_assembled,
)


class ZhipuLLM:
    """智谱GLM大模型"""
    
    def __init__(self, model: str = None):
        self.model = model or Config.ZHIPU_MODEL
        self.api_key = Config.ZHIPU_API_KEY
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        # 运行时开关：进入 modify 流程时强制“不带思考”
        self.force_disable_thinking = False

    async def parse_intent(
        self, user_input: str, history: list = None, locale: Optional[str] = None
    ) -> Optional[dict]:
        """解析意图"""
        from agents.locale_prompts import wrap_general_user_prompt

        prompt = wrap_general_user_prompt(user_input, locale)
        if not ("JSON" in prompt or "json" in prompt):
            prompt += "\n请务必只返回 JSON 格式结果。"

        result = await self.chat(prompt, history)
        
        try:
            import re
            json_match = re.search(r'\[.*\]|\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return json.loads(result)
        except:
            return result

    async def chat(self, prompt: str, history: list = None) -> str:
        """对话接口"""
        from llm.chat_messages import prompt_to_messages

        messages = prompt_to_messages(prompt, history=history)

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": Config.ZHIPU_MAX_TOKENS,
            "temperature": Config.ZHIPU_TEMPERATURE
        }
        
        # GLM-5 支持思考模式（modify 流程强制关闭）
        if self.model == "glm-5" and Config.ZHIPU_ENABLE_THINKING and not getattr(self, "force_disable_thinking", False):
            payload["thinking"] = {"type": "enabled"}

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        maybe_log_llm_chat_kwargs("zhipu", payload, tag="chat")

        def _do_request():
            # 连接池 + keep-alive
            timeout = (
                float(os.getenv("LLM_HTTP_TIMEOUT_CONNECT", "5")),
                float(os.getenv("LLM_HTTP_TIMEOUT_READ", "120")),
            )
            return get_session().post(self.base_url, headers=headers, json=payload, timeout=timeout)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _do_request)
        
        if response.status_code == 200:
            res_json = response.json()
            maybe_log_llm_response_body(
                "zhipu",
                res_json,
                tag="chat",
                model=self.model,
            )
            if "choices" in res_json and len(res_json["choices"]) > 0:
                return res_json["choices"][0]["message"]["content"]
            return ""
        else:
            error_msg = f"[ZhipuLLM] Error {response.status_code}: {response.text}"
            print(error_msg)
            maybe_log_llm_response_body(
                "zhipu",
                {"error": error_msg, "status_code": response.status_code},
                tag="chat_error",
                model=self.model,
            )
            return error_msg

    def chat_stream(self, prompt: str, history: list = None, locale: Optional[str] = None):
        """流式对话（逐 token 字符串）"""
        from agents.locale_prompts import wrap_general_user_prompt

        from llm.chat_messages import prompt_to_messages

        p = wrap_general_user_prompt(prompt, locale)
        messages = prompt_to_messages(p, history=history)

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": Config.ZHIPU_MAX_TOKENS,
            "temperature": Config.ZHIPU_TEMPERATURE,
            "stream": True
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        maybe_log_llm_chat_kwargs("zhipu", payload, tag="chat_stream")

        try:
            timeout = (
                float(os.getenv("LLM_HTTP_TIMEOUT_CONNECT", "5")),
                float(os.getenv("LLM_HTTP_TIMEOUT_READ", "120")),
            )
            response = get_session().post(
                self.base_url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=timeout
            )

            _acc_ct: List[str] = []
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = line[6:]
                        if data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                            if 'choices' in chunk and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    _acc_ct.append(content)
                                    yield content
                        except json.JSONDecodeError:
                            continue
            maybe_log_llm_stream_assembled(
                "zhipu",
                tag="chat_stream",
                model=self.model,
                content="".join(_acc_ct),
            )
        except Exception as e:
            yield f"[Error] {str(e)}"

    def chat_stream_with_reasoning(self, prompt: str, history: list = None) -> Iterator[Dict[str, Any]]:
        """
        与 Qwen/千帆对齐：统一产出 reasoning_delta / content_delta / done。
        智谱 GLM 流式当前仅映射到 content_delta。
        """
        for piece in self.chat_stream(prompt, history):
            if not isinstance(piece, str) or not piece:
                continue
            if piece.startswith("[Error]"):
                yield {"type": "content_delta", "delta": piece}
                yield {"type": "done"}
                return
            yield {"type": "content_delta", "delta": piece}
        yield {"type": "done"}

    def chat_stream_fallback_chunks(self, prompt: str, history: list = None) -> Iterator[Dict[str, Any]]:
        """非流式整段后分块 yield（与 parse_intent 解耦）；同步 HTTP，避免事件循环嵌套。"""
        from llm.chat_messages import prompt_to_messages

        messages = prompt_to_messages(prompt, history=history)
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": Config.ZHIPU_MAX_TOKENS,
            "temperature": Config.ZHIPU_TEMPERATURE,
        }
        if self.model == "glm-5" and Config.ZHIPU_ENABLE_THINKING and not getattr(self, "force_disable_thinking", False):
            payload["thinking"] = {"type": "enabled"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        timeout = (
            float(os.getenv("LLM_HTTP_TIMEOUT_CONNECT", "5")),
            float(os.getenv("LLM_HTTP_TIMEOUT_READ", "120")),
        )
        maybe_log_llm_chat_kwargs("zhipu", payload, tag="chat_stream_fallback_chunks")

        text = ""
        try:
            response = get_session().post(self.base_url, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 200:
                res_json = response.json()
                maybe_log_llm_response_body(
                    "zhipu",
                    res_json,
                    tag="chat_stream_fallback_chunks",
                    model=self.model,
                )
                if "choices" in res_json and len(res_json["choices"]) > 0:
                    text = res_json["choices"][0]["message"]["content"] or ""
            else:
                text = f"Error: {response.text}"
        except Exception as e:
            text = f"Error: {e}"
        chunk = 56
        for i in range(0, len(text), chunk):
            yield {"type": "content_delta", "delta": text[i : i + chunk]}
        yield {"type": "done"}
