# llm/zhipu_llm.py
"""
智谱GLM大模型适配器
支持GLM-5等模型
"""

import json
import asyncio
from typing import Any, Dict, Optional, List
import requests
import os
from config import Config
from .http_session import get_session


class ZhipuLLM:
    """智谱GLM大模型"""
    
    def __init__(self, model: str = None):
        self.model = model or Config.ZHIPU_MODEL
        self.api_key = Config.ZHIPU_API_KEY
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        # 运行时开关：进入 modify 流程时强制“不带思考”
        self.force_disable_thinking = False

    async def parse_intent(self, user_input: str, history: list = None) -> Optional[dict]:
        """解析意图"""
        prompt = user_input
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
        messages = []
        if history:
            for msg in history:
                messages.append({
                    "role": msg.get("role", "user"), 
                    "content": msg.get("content", "")
                })
        messages.append({"role": "user", "content": prompt})

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
            if "choices" in res_json and len(res_json["choices"]) > 0:
                return res_json["choices"][0]["message"]["content"]
            return ""
        else:
            error_msg = f"[ZhipuLLM] Error {response.status_code}: {response.text}"
            print(error_msg)
            return error_msg

    def chat_stream(self, prompt: str, history: list = None):
        """流式对话"""
        messages = []
        if history:
            for msg in history:
                messages.append({
                    "role": msg.get("role", "user"), 
                    "content": msg.get("content", "")
                })
        messages.append({"role": "user", "content": prompt})

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
                                    yield content
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield f"[Error] {str(e)}"
