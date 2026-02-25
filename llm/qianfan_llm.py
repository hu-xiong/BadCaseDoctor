import json
import asyncio
from typing import Any, Dict, Optional, List
import requests
from config import Config

class QianfanLLM:
    def __init__(self, model: str = None):
        self.model = model or Config.QIANFAN_MODEL
        self.api_key = Config.QIANFAN_API_KEY
        self.secret_key = Config.QIANFAN_SECRET_KEY

    async def parse_intent(self, user_input: str, history: list = None) -> Optional[dict]:
        """解析意图"""
        # 这里简化处理，直接调用对话接口并尝试解析 JSON
        prompt = user_input
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
        
        messages = []
        if history:
            for msg in history:
                messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": Config.QIANFAN_TEMPERATURE,
            "top_p": Config.QIANFAN_TOP_P
        })
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        def _do_request():
            return requests.request("POST", url, headers=headers, data=payload)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _do_request)
        
        if response.status_code == 200:
            res_json = response.json()
            if "choices" in res_json and len(res_json["choices"]) > 0:
                return res_json["choices"][0]["message"]["content"]
            return res_json.get("result", "") # 兼容 V1 字段名(如果有的话)
        else:
            return f"Error: {response.text}"

    def chat_stream(self, prompt: str, history: list = None):
        """流式对话"""
        # 这里简化为非流式，因为 requests 处理流式比较麻烦，且后端桥接需要稳定
        result = asyncio.run(self.chat(prompt, history))
        yield result
