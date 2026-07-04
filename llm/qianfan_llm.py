import json
import asyncio
from typing import Any, Dict, Optional, List, Iterator
import requests
import os
from config import Config
from .http_session import get_session
from .prompt_log import maybe_log_llm_chat_kwargs

class QianfanLLM:
    def __init__(self, model: str = None):
        self.model = model or Config.QIANFAN_MODEL
        self.api_key = Config.QIANFAN_API_KEY
        self.secret_key = Config.QIANFAN_SECRET_KEY
        # 运行时开关：进入 modify 流程时强制“不带思考”
        # 千帆没有显式 enable_thinking 参数，只能通过“降级到非推理模型”实现。
        self.force_disable_thinking = False

    async def parse_intent(
        self, user_input: str, history: list = None, locale: Optional[str] = None
    ) -> Optional[dict]:
        """解析意图"""
        from agents.locale_prompts import wrap_general_user_prompt

        # 这里简化处理，直接调用对话接口并尝试解析 JSON
        prompt = wrap_general_user_prompt(user_input, locale)
        if not ("JSON" in prompt or "json" in prompt):
             prompt += "\n请务必只返回 JSON 格式结果。"

        result = await self.chat(prompt, history)
        
        print(f"[QIANFAN-LLM] 原始响应: {result[:500] if result else 'None'}...")
        
        if not result or result.startswith("Error:"):
            print(f"[QIANFAN-LLM] 错误响应: {result}")
            return result  # 返回原始字符串，让调用者处理
        
        try:
            # 提取 JSON 部分 - 支持嵌套结构
            import re
            
            # 方法1: 尝试直接解析整个结果
            try:
                parsed = json.loads(result.strip())
                print(f"[QIANFAN-LLM] 直接解析成功: {parsed}")
                return parsed
            except:
                pass
            
            # 方法2: 提取第一个完整的 JSON 对象（支持嵌套）
            # 找到第一个 { 和最后一个匹配的 }
            start = result.find('{')
            if start != -1:
                brace_count = 0
                end = start
                for i, char in enumerate(result[start:], start):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break
                
                if end > start:
                    json_str = result[start:end]
                    parsed = json.loads(json_str)
                    print(f"[QIANFAN-LLM] 提取解析成功: {parsed}")
                    return parsed
            
            # 方法3: 如果包含 XML 标签，返回原始字符串让 parse_xml_* 函数处理
            if '<' in result and '>' in result:
                print(f"[QIANFAN-LLM] 检测到XML格式，返回原始字符串")
                return result
            
            print(f"[QIANFAN-LLM] 未能提取JSON，返回原始字符串")
            return result
        except Exception as e:
            print(f"[QIANFAN-LLM] JSON解析失败: {e}, 返回原始字符串")
            return result  # 返回原始字符串

    async def chat(self, prompt: str, history: list = None) -> str:
        """对话接口 - 使用 Qianfan V2 (OpenAI 兼容接口)"""
        url = "https://qianfan.baidubce.com/v2/chat/completions"
        model_to_use = self.model
        # modify 流程强制不带思考：若当前是 X1，则降级到 4.5 turbo
        if getattr(self, "force_disable_thinking", False) and isinstance(model_to_use, str) and model_to_use.lower().startswith("ernie-x1"):
            model_to_use = "ernie-4.5-turbo-128k"
        
        from llm.chat_messages import prompt_to_messages

        messages = prompt_to_messages(prompt, history=history)

        payload = json.dumps({
            "model": model_to_use,
            "messages": messages,
            "temperature": Config.QIANFAN_TEMPERATURE,
            "top_p": Config.QIANFAN_TOP_P
        })
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        def _do_request():
            timeout = (
                float(os.getenv("LLM_HTTP_TIMEOUT_CONNECT", "5")),
                float(os.getenv("LLM_HTTP_TIMEOUT_READ", "120")),
            )
            return get_session().request("POST", url, headers=headers, data=payload, timeout=timeout)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _do_request)
        
        if response.status_code == 200:
            res_json = response.json()
            if "choices" in res_json and len(res_json["choices"]) > 0:
                return res_json["choices"][0]["message"]["content"]
            return res_json.get("result", "") # 兼容 V1 字段名(如果有的话)
        else:
            return f"Error: {response.text}"

    async def chat_completion_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        tool_choice: Any = "auto",
        parallel_tool_calls: bool = False,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        千帆 v2 OpenAI 兼容接口：非流式，携带 tools / tool_choice / parallel_tool_calls。
        返回 choices[0].message 字典（含 content、tool_calls 等）。
        """
        url = "https://qianfan.baidubce.com/v2/chat/completions"
        model_to_use = self.model
        if getattr(self, "force_disable_thinking", False) and isinstance(
            model_to_use, str
        ) and model_to_use.lower().startswith("ernie-x1"):
            model_to_use = "ernie-4.5-turbo-128k"

        from llm.chat_messages import normalize_chat_messages

        messages = normalize_chat_messages(messages)
        payload: Dict[str, Any] = {
            "model": model_to_use,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "parallel_tool_calls": parallel_tool_calls,
            "temperature": Config.QIANFAN_TEMPERATURE,
            "top_p": Config.QIANFAN_TOP_P,
            "stream": False,
        }
        if max_tokens is not None and max_tokens > 0:
            payload["max_tokens"] = max_tokens
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        def _do_request():
            timeout = (
                float(os.getenv("LLM_HTTP_TIMEOUT_CONNECT", "5")),
                float(os.getenv("LLM_HTTP_TIMEOUT_READ", "120")),
            )
            return get_session().request(
                "POST", url, headers=headers, json=payload, timeout=timeout
            )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _do_request)
        if response.status_code != 200:
            raise RuntimeError(response.text or f"HTTP {response.status_code}")
        res_json = response.json()
        choices = res_json.get("choices") or []
        if not choices:
            return {}
        msg = (choices[0] or {}).get("message") or {}
        return msg if isinstance(msg, dict) else {}

    def chat_completion_with_tools_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        tool_choice: Any = "auto",
        parallel_tool_calls: bool = False,
        max_tokens: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        千帆 v2 流式 FC：SSE data 行解析为与 OpenAI 兼容的整包 JSON（choices[0].delta）。
        """
        from llm.chat_messages import normalize_chat_messages

        messages = normalize_chat_messages(messages)
        url = "https://qianfan.baidubce.com/v2/chat/completions"
        model_to_use = self.model
        if getattr(self, "force_disable_thinking", False) and isinstance(
            model_to_use, str
        ) and model_to_use.lower().startswith("ernie-x1"):
            model_to_use = "ernie-4.5-turbo-128k"

        payload: Dict[str, Any] = {
            "model": model_to_use,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "parallel_tool_calls": parallel_tool_calls,
            "temperature": Config.QIANFAN_TEMPERATURE,
            "top_p": Config.QIANFAN_TOP_P,
            "stream": True,
        }
        if max_tokens is not None and max_tokens > 0:
            payload["max_tokens"] = max_tokens
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        timeout = (
            float(os.getenv("LLM_HTTP_TIMEOUT_CONNECT", "5")),
            float(os.getenv("LLM_HTTP_TIMEOUT_READ", "120")),
        )
        with get_session().post(
            url, headers=headers, json=payload, stream=True, timeout=timeout
        ) as resp:
            if resp.status_code != 200:
                raise RuntimeError(resp.text or f"HTTP {resp.status_code}")
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                s = line.strip()
                if not s.startswith("data:"):
                    continue
                data = s[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    j = json.loads(data)
                except Exception:
                    continue
                if isinstance(j, dict):
                    yield j

    async def chat_completion_messages(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """v2 非流式，仅 messages（第二轮 FC / 观察续写，不传 tools）。"""
        url = "https://qianfan.baidubce.com/v2/chat/completions"
        model_to_use = self.model
        if getattr(self, "force_disable_thinking", False) and isinstance(
            model_to_use, str
        ) and model_to_use.lower().startswith("ernie-x1"):
            model_to_use = "ernie-4.5-turbo-128k"
        payload: Dict[str, Any] = {
            "model": model_to_use,
            "messages": messages,
            "temperature": Config.QIANFAN_TEMPERATURE,
            "top_p": Config.QIANFAN_TOP_P,
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        def _do_request():
            timeout = (
                float(os.getenv("LLM_HTTP_TIMEOUT_CONNECT", "5")),
                float(os.getenv("LLM_HTTP_TIMEOUT_READ", "120")),
            )
            return get_session().request(
                "POST", url, headers=headers, json=payload, timeout=timeout
            )

        maybe_log_llm_chat_kwargs("qianfan", payload, tag="chat_completion_messages")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _do_request)
        if response.status_code != 200:
            raise RuntimeError(response.text or f"HTTP {response.status_code}")
        res_json = response.json()
        choices = res_json.get("choices") or []
        if not choices:
            return {}
        msg = (choices[0] or {}).get("message") or {}
        return msg if isinstance(msg, dict) else {}

    async def chat_with_reasoning(self, prompt: str, history: list = None) -> Dict[str, Any]:
        """
        返回整段结果；实现上只复用 chat_stream_with_reasoning 的流式 SSE，再汇总，
        与非流式 JSON 请求保持一致的一条链路，避免两套解析逻辑漂移。
        """
        def _aggregate_from_stream():
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
                return {"content": f"Error: {e}", "reasoning_content": None}
            rc = "".join(reasoning_parts).strip() or None
            ct = "".join(content_parts).strip()
            return {"content": ct, "reasoning_content": rc}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _aggregate_from_stream)

    def chat_stream_with_reasoning(self, prompt: str, history: list = None) -> Iterator[Dict[str, Any]]:
        """
        流式对话并输出 reasoning/content 增量（用于 ERNIE-X1 等带 reasoning 的模型）。
        产出形如：
          {"type": "reasoning_delta", "delta": "..."}
          {"type": "content_delta", "delta": "..."}
          {"type": "done"}
        """
        from llm.chat_messages import prompt_to_messages

        url = "https://qianfan.baidubce.com/v2/chat/completions"
        messages = prompt_to_messages(prompt, history=history)

        model_to_use = self.model
        if getattr(self, "force_disable_thinking", False) and isinstance(
            model_to_use, str
        ) and model_to_use.lower().startswith("ernie-x1"):
            model_to_use = "ernie-4.5-turbo-128k"

        payload = {
            "model": model_to_use,
            "messages": messages,
            "temperature": Config.QIANFAN_TEMPERATURE,
            "top_p": Config.QIANFAN_TOP_P,
            "stream": True
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream"
        }

        try:
            timeout = (
                float(os.getenv("LLM_HTTP_TIMEOUT_CONNECT", "5")),
                float(os.getenv("LLM_HTTP_TIMEOUT_READ", "120")),
            )
            with get_session().post(url, headers=headers, json=payload, stream=True, timeout=timeout) as resp:
                if resp.status_code != 200:
                    yield {"type": "content_delta", "delta": f"Error: {resp.text}"}
                    yield {"type": "done"}
                    return

                # chunk_size=1 可以显著降低缓冲，提高“打字机”观感
                for raw_line in resp.iter_lines(decode_unicode=True, chunk_size=1):
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if not data or data == "[DONE]":
                        break

                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue

                    # OpenAI 兼容流式：choices[0].delta.content / delta.reasoning_content
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}) if isinstance(choices[0], dict) else {}
                    if not delta:
                        # 有的实现可能直接给 message
                        delta = (choices[0].get("message") or {}) if isinstance(choices[0], dict) else {}

                    r = delta.get("reasoning_content")
                    c = delta.get("content")
                    if r:
                        yield {"type": "reasoning_delta", "delta": r}
                    if c:
                        yield {"type": "content_delta", "delta": c}

                yield {"type": "done"}
        except Exception as e:
            yield {"type": "content_delta", "delta": f"Error: {e}"}
            yield {"type": "done"}

    def chat_stream_fallback_chunks(self, prompt: str, history: list = None) -> Iterator[Dict[str, Any]]:
        """
        流式不可用时：同步 HTTP 非流式 completion，按块 yield（与 parse_intent 解耦）。
        """
        url = "https://qianfan.baidubce.com/v2/chat/completions"
        model_to_use = self.model
        if getattr(self, "force_disable_thinking", False) and isinstance(model_to_use, str) and model_to_use.lower().startswith("ernie-x1"):
            model_to_use = "ernie-4.5-turbo-128k"
        from llm.chat_messages import prompt_to_messages

        messages = prompt_to_messages(prompt, history=history)
        payload = json.dumps({
            "model": model_to_use,
            "messages": messages,
            "temperature": Config.QIANFAN_TEMPERATURE,
            "top_p": Config.QIANFAN_TOP_P,
        })
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        def _do_request():
            timeout = (
                float(os.getenv("LLM_HTTP_TIMEOUT_CONNECT", "5")),
                float(os.getenv("LLM_HTTP_TIMEOUT_READ", "120")),
            )
            return get_session().request("POST", url, headers=headers, data=payload, timeout=timeout)

        text = ""
        try:
            resp = _do_request()
            if resp.status_code == 200:
                res_json = resp.json()
                if "choices" in res_json and len(res_json["choices"]) > 0:
                    text = (res_json["choices"][0].get("message") or {}).get("content") or ""
                else:
                    text = res_json.get("result", "") or ""
            else:
                text = f"Error: {resp.text}"
        except Exception as e:
            text = f"Error: {e}"
        chunk = 56
        for i in range(0, len(text), chunk):
            yield {"type": "content_delta", "delta": text[i : i + chunk]}
        yield {"type": "done"}

    def chat_stream(self, prompt: str, history: list = None, locale: Optional[str] = None):
        """
        流式对话：与 Qwen/Zhipu 一致逐段 yield 正文字符串。
        复用 chat_stream_with_reasoning 的 SSE，只转发 content_delta（不透出 reasoning）。
        """
        from agents.locale_prompts import wrap_general_user_prompt

        p = wrap_general_user_prompt(prompt, locale)
        for item in self.chat_stream_with_reasoning(p, history):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "reasoning_delta":
                continue
            if item.get("type") == "content_delta":
                d = item.get("delta") or ""
                if isinstance(d, str) and d:
                    yield d
