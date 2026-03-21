import json
import re
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence, Dict, Union, Optional, List, Iterator
from urllib.parse import quote_plus

import dashscope
from dashscope import Generation
from langchain_community.llms import Tongyi
from langchain_community.utilities import SQLDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from sqlalchemy import Result

from config import Config


class QwenLLM:
    def _supports_deep_thinking(self) -> bool:
        """只对明确支持 enable_thinking 的模型启用深度思考策略。"""
        m = (self.model or "").strip().lower()
        # 明确的 thinking 模型/别名
        if "thinking" in m:
            return True
        # qwen-max 系列支持 enable_thinking（通过 DashScope 参数）
        if m in ("qwen-max",) or m.startswith("qwen3-max"):
            return True
        return False

    def _assess_task_difficulty(self, text: str) -> str:
        """
        用 qwen-max（不带 enable_thinking）先做一次极简难度评估，返回 'easy' 或 'hard'。
        作为统一“难度判定器”供 glm-5 / ernie-x1 等思考模型做开关决策。
        """
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
            resp = Generation.call(
                model="qwen-max",
                messages=[{"role": "user", "content": judge_prompt}],
                result_format="message",
            )
            if getattr(resp, "status_code", None) == 200:
                out = (resp.output.choices[0].message.content or "").strip().lower()
                if "hard" in out:
                    return "hard"
                if "easy" in out:
                    return "easy"
            return "easy"
        except Exception:
            return "easy"
    def _is_simple_task(self, text: str) -> bool:
        """极简判断：简单任务不开启 thinking。"""
        t = (text or "").strip()
        if not t:
            return True
        # 很短且不包含明显分析/多步骤信号
        if len(t) <= 120 and not any(k in t for k in ("分析", "定位", "排查", "原因", "为什么", "如何", "方案", "对比", "权衡", "步骤", "同时", "分别")):
            return True
        return False

    def _thinking_enabled_for(self, text: str) -> bool:
        """
        thinking 开关：
        - qwen-max-thinking / thinking 模型：按原逻辑开启
        - glm-5：按任务难度（简单任务不开启）
        - 其它：按原逻辑
        支持环境变量覆盖：GLM5_THINKING_MODE=always|auto|never（默认 auto）
        """
        # 强制关闭（例如 modify 流程要求不带思考）
        if getattr(self, "force_disable_thinking", False):
            return False
        if self.enable_thinking:
            return True
        model = (self.model or "").strip().lower()
        # qwen-max：先用不思考评估难度，难则开启（前提：模型支持深度思考）
        if model == "qwen-max" and self._supports_deep_thinking():
            return self._assess_task_difficulty(text) == "hard"
        if model == "glm-5":
            # 按你的要求：glm-5 是否开启思考也用 qwen-max（不思考）先判任务难度
            mode = (os.getenv("GLM5_THINKING_MODE", "auto") or "auto").strip().lower()
            if mode == "always":
                return True
            if mode == "never":
                return False
            # auto：easy 不开，hard 才开
            return self._assess_task_difficulty(text) == "hard"
        return False

    def __init__(self, model: str = None):
        # 步骤推理 / Agent：支持多种模型选择
        # 优先级：传入的 model 参数 > DASHSCOPE_MODEL > QWEN_API_MODEL
        # 特殊处理：qwen-max-thinking 使用 QWEN3_MAX_THINKING_MODEL 配置
        print(f"[QWEN-LLM-INIT] 传入的 model 参数：{model}")
        
        self.enable_thinking = False
        # 外部可临时置 True 来强制关闭 enable_thinking
        self.force_disable_thinking = False
        if model == 'qwen-max-thinking':
            # 兼容旧别名：视为 qwen-max（后续按难度决定是否开启 enable_thinking）
            self.model = 'qwen-max'
            self.enable_thinking = False
            print(f"[QWEN-LLM-INIT] 使用旧别名 qwen-max-thinking -> qwen-max (auto thinking)")
        else:
            self.model = model or getattr(Config, 'DASHSCOPE_MODEL', None) or Config.QWEN_API_MODEL
            print(f"[QWEN-LLM-INIT] 使用其他模型：{self.model}")
            # 兼容直接传入包含 thinking 的模型名
            if isinstance(self.model, str) and ('thinking' in self.model.lower()):
                self.enable_thinking = True
        
        print(f"[QWEN-LLM-INIT] 最终使用的模型：{self.model}")
        
        _api_key = getattr(Config, 'DASHSCOPE_API_KEY', None) or Config.QWEN_API_KEY
        dashscope.api_key = _api_key
        self.conversation_history = []  # 存储对话历史
        self.executor = ThreadPoolExecutor(max_workers=3)  # 线程池用于同步 API 调用

    async def parse_intent(self, user_input: str, history: list = None) -> Optional[dict]:
        """异步方法：在线程池中运行同步 API 调用"""
        def _sync_parse():
            # 增加检查：如果 user_input 已经包含了系统指令或特定格式，则不使用路由模板
            if "<system>" in user_input or "<format>" in user_input or "必须返回" in user_input:
                # 使用 messages 格式（DashScope API 标准）
                messages = [{"role": "user", "content": user_input}]
                        
                extra_params = {}
                if self._thinking_enabled_for(user_input):
                    extra_params['enable_thinking'] = True
                    print(f"[QWEN-LLM-PARSE] enable_thinking=True model={self.model}")
                else:
                    # Windows 控制台可能是 gbk，避免特殊字符导致 UnicodeEncodeError
                    print(f"[QWEN-LLM-PARSE] 未开启思考模式：model={self.model}")
                        
                response = Generation.call(
                    model=self.model,
                    messages=messages,  # 使用 messages 而非 prompt
                    result_format='message',  # 使用 message 格式
                    **extra_params  # 传递额外参数
                )
                if response.status_code == 200:
                    text = response.output.choices[0].message.content.strip()
                    # 尝试解析为 JSON，如果失败则返回原字符串
                    try:
                        return json.loads(text)
                    except:
                        return text
                return None
            
            example_json = '[{"agent": "", "planActions": "", "action": "", "script": ""}, {"agent": "", "planActions": "", "action": "", "script": ""}]'
            print("#"*50)
            # 构建包含历史对话的提示词
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
                
            # 使用 messages 格式（DashScope API 标准）
            messages = [{"role": "user", "content": prompt}]
                    
            extra_params = {}
            if self._thinking_enabled_for(prompt):
                extra_params['enable_thinking'] = True
                print(f"[QWEN-LLM-PARSE] enable_thinking=True model={self.model}")
            else:
                # Windows 控制台可能是 gbk，避免特殊字符导致 UnicodeEncodeError
                print(f"[QWEN-LLM-PARSE] 未开启思考模式：model={self.model}")
                    
            response = Generation.call(
                model=self.model,
                messages=messages,  # 使用 messages 而非 prompt
                result_format='message',  # 使用 message 格式
                **extra_params  # 传递额外参数
            )
            if response.status_code == 200:
                try:
                    # 打印完整的响应信息，包括思考内容
                    print(f"[QWEN-LLM-PARSE] status_code={response.status_code}")
                    print(f"[QWEN-LLM-PARSE] 完整 output 对象：{response.output}")
                    print(f"[QWEN-LLM-PARSE] output 类型：{type(response.output)}")
                    
                    # 检查 output 的所有属性
                    if hasattr(response.output, '__dict__'):
                        print(f"[QWEN-LLM-PARSE] output.__dict__={response.output.__dict__}")
                    
                    # 检查 choices[0].message 的所有属性
                    message_obj = response.output.choices[0].message
                    print(f"[QWEN-LLM-PARSE] message 对象：{message_obj}")
                    print(f"[QWEN-LLM-PARSE] message 类型：{type(message_obj)}")
                    if hasattr(message_obj, '__dict__'):
                        print(f"[QWEN-LLM-PARSE] message.__dict__={message_obj.__dict__}")
                    
                    # 思考内容：统一只使用 OpenAI/DashScope 兼容字段 reasoning_content
                    reasoning = getattr(message_obj, 'reasoning_content', None)
                    if reasoning:
                        print(f"[QWEN-LLM-PARSE] reasoning_len={len(reasoning)}")
                    print(f"[QWEN-LLM-PARSE] content={message_obj.content}")
                    # 仅用 message.content 做 JSON 解析，避免 response.output.text 内部访问 thinking_content 报错
                    text = (message_obj.content or "").strip()
                    return json.loads(text)
                except json.JSONDecodeError as e:
                    print(f"JSON 解析错误：{e}")
                    return {"agent": "other", "action": "other", "info": {}}
            else:
                print("error")
                return {"agent": "other", "action": "other", "info": {}}
            
        # 在线程池中运行同步代码，协程等待
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self.executor, _sync_parse)
        return result

    def chat_stream(self, prompt: str, history: list = None):
        """流式聊天方法 (同步生成器，方便 Flask 使用)"""
        # 构建 messages 格式
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        
        extra_params = {}
        if self._thinking_enabled_for(prompt):
            extra_params['enable_thinking'] = True
            print(f"[QWEN-LLM-STREAM] enable_thinking=True model={self.model}")
        else:
            print(f"[QWEN-LLM-STREAM] 未开启思考模式：model={self.model}")
        
        responses = Generation.call(
            model=self.model,
            messages=messages,  # 使用 messages
            result_format='message',  # 使用 message 格式
            stream=True,
            incremental_output=True,
            **extra_params  # 传递额外参数
        )
        for response in responses:
            if response.status_code == 200:
                # 从 message 格式提取 content
                yield response.output.choices[0].message.content
            else:
                yield f"Error: {response.message}"

    def chat_stream_with_reasoning(self, prompt: str, history: list = None) -> Iterator[Dict[str, Any]]:
        """
        流式对话并实时输出 reasoning/content 增量（与文心 X1 一致）。
        产出：{"type": "reasoning_delta", "delta": "..."} / {"type": "content_delta", "delta": "..."} / {"type": "done"}
        """
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        extra_params = {}
        if self._thinking_enabled_for(prompt):
            extra_params['enable_thinking'] = True
            extra_params['stream'] = True
            extra_params['incremental_output'] = True
            print(f"[QWEN-LLM-STREAM-REASONING] enable_thinking=True model={self.model}")
        else:
            extra_params['stream'] = True
            extra_params['incremental_output'] = True

        def _get_safe(obj, key, default=None):
            if obj is None:
                return default
            if isinstance(obj, dict):
                return obj.get(key, default)
            try:
                return getattr(obj, key, default)
            except (KeyError, AttributeError):
                return default

        try:
            responses = Generation.call(
                model=self.model,
                messages=messages,
                result_format='message',
                **extra_params
            )
            for response in responses:
                if response.status_code != 200:
                    yield {"type": "content_delta", "delta": f"Error: {response.message}"}
                    yield {"type": "done"}
                    return
                if not getattr(response, 'output', None) or not getattr(response.output, 'choices', None):
                    continue
                choice = response.output.choices[0]
                msg = _get_safe(choice, 'message') or _get_safe(choice, 'delta')
                if msg is None:
                    continue
                rc = _get_safe(msg, 'reasoning_content')
                if rc and isinstance(rc, str):
                    yield {"type": "reasoning_delta", "delta": rc}
                ct = _get_safe(msg, 'content')
                if ct and isinstance(ct, str):
                    yield {"type": "content_delta", "delta": ct}
            yield {"type": "done"}
        except Exception as e:
            yield {"type": "content_delta", "delta": f"Error: {e}"}
            yield {"type": "done"}

    def chat_stream_fallback_chunks(self, prompt: str, history: list = None) -> Iterator[Dict[str, Any]]:
        """
        无可用流式 API 或上层显式降级时：直连用户 prompt 做一次非流式 completion，
        再按块 yield reasoning_delta/content_delta（与 parse_intent 路由 JSON 完全解耦）。
        """
        messages: List[Dict[str, str]] = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        extra_params: Dict[str, Any] = {}
        if self._thinking_enabled_for(prompt):
            extra_params["enable_thinking"] = True
        try:
            response = Generation.call(
                model=self.model,
                messages=messages,
                result_format="message",
                **extra_params,
            )
            if response.status_code != 200:
                err = f"Error: {getattr(response, 'message', response)}"
                yield {"type": "content_delta", "delta": err}
                yield {"type": "done"}
                return
            msg = response.output.choices[0].message
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
            # 构建 messages 格式
            messages = [{"role": "user", "content": prompt}]
            
            # 为 qwen-max-thinking 开启思考模式
            extra_params = {}
            if self.enable_thinking:
                extra_params['enable_thinking'] = True
                print(f"[QWEN-LLM-CHAT] enable_thinking=True model={self.model}")
            else:
                print(f"[QWEN-LLM-CHAT] 未开启思考模式：model={self.model}")
            
            response = Generation.call(
                model=self.model,
                messages=messages,  # 使用 messages
                result_format='message',  # 使用 message 格式
                **extra_params  # 传递额外参数
            )
            if response.status_code == 200:
                return response.output.choices[0].message.content
            return f"Error: {response.message}"

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync_chat)

    async def chat_with_reasoning(self, prompt: str, history: list = None) -> Dict[str, Any]:
        """
        返回整段 {"content", "reasoning_content"}，供仅需一次性结果的场景（如 ReAct 回退）。
        实现上只复用 chat_stream_with_reasoning 的同一条流式链路，在这里把 delta 拼成整段，
        避免与 chat_stream_with_reasoning 各写一套 Generation.call（行为不一致、难维护）。
        """
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
        # 通过占位符将info中的信息替换uri中的用户名密码等信息
        print(type(info))
        print(info)
        uri = url.format(
            quote_plus(info["username"]),
            quote_plus(info["password"]),  # 关键！
            info["host"],
            info["port"],
            info["database"]
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
            temperature=0
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

        # 执行SQL
        try:
            result = db._execute(sql)
            return {"code": 200, "script": sql, "task": user_input, "message": "success", "data": result}
        except Exception as e:
            return {"code": 500, "script": sql, "task": user_input, "message": f"Error executing query: {str(e)}",
                    "data": None}

    def dealRedis(self, user_input: str, info: str,history: list = None):
        prompt=f"""
        该任务是redis任务，要生成可执行的的python的redis脚本:
        输入:{user_input}
        用户信息:{info}
        只输出标准json，不要任何格式，不要任何解释，以供代码解析，不要多余字节，要可以给
        - python-script 为python的执行脚本，只是该语句的脚本，不要引包，不要连接，如查询redis的key为12，则是r.get("12")
        - script为redis原始命令
        """
        response = Generation.call(
            model=self.model,
            prompt=prompt,
            result_format='text'
        )
        cleaned = re.sub(r'^```(?:json)?\s*', '', response.output.text, flags=re.MULTILINE)
        cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        print("redis",cleaned)
        if response.status_code == 200:
            try:
                return json.loads(cleaned)

            except json.JSONDecodeError as e:
                print(f"JSON 解析错误: {e}")
                return {"agent": "other", "action": "other", "info": {}}
        else:
            print("error")
            return {"agent": "other", "action": "other", "info": {}}






    def splitTask(self, user_input: str, info: str,history: list = None):
        prompt=f"""
        该任务是将用户的描述细分化，要将任务拆分成每一个小步骤，如排查host1，host2，host3，是否有文件aa是否有error存在，则生成多个对象，1.校验各个host是否联通，2.查找文件aa位置，3.打开文件aa，4.查找error，5退出操作，如，要生成执行步骤:
        每个步骤都用一个json对象表示，格式为:
         每个数组元素是一个任务对象，包含以下字段：
            "task":"任务名词",  
            "info": "任务具体步骤，将任务详情化"
        输入:{user_input}
        用户信息:{info}
        只输出标准json，不要任何格式，不要任何解释，以供代码解析，不要多余字节，要可以给
        """
        response = Generation.call(
            model=self.model,
            prompt=prompt,
            result_format='text'
        )
        if response.status_code == 200:
            try:
                print("=--=")
                print(response.output.text)
                print("----===0")
                return json.loads(response.output.text.strip())
            except json.JSONDecodeError as e:
                print(f"JSON 解析错误: {e}")
                return {"agent": "other", "action": "other", "info": {}}
        else:
            print("error")
            return {"agent": "other", "action": "other", "info": {}}

    def generateScript(self, user_input: str, info: str,history: list = None):
        prompt=f"""
        该任务是生成linux脚本，请生成
        输入:{user_input}
        用户信息:{info}
        只输出标准json，不要任何格式，不要任何解释，以供代码解析，不要多余字节，要可以给
        """
        response = Generation.call(
            model=self.model,
            prompt=prompt,
            result_format='text'
        )
        if response.status_code == 200:
            try:
                print("=--=")
                print(response.output.text)
                print("----===0")
                return json.loads(response.output.text.strip())
            except json.JSONDecodeError as e:
                print(f"JSON 解析错误: {e}")
                return {"agent": "other", "action": "other", "info": {}}
        else:
            print("error")
            return {"agent": "other", "action": "other", "info": {}}
    def dealScript(self, user_input: str, info: str,history: list = None):
        print("dealScript",user_input)

        print("uiiy-"*30)
        print(user_input)
        prompt=f"""
        该任务是生成将各个任务linux脚本合成一个可执行的脚本，请生成
        输入:{user_input}
        用户信息:{info}
        只输出标准json，不要任何格式，不要任何解释，以供代码解析，不要多余字节，要可以给
        """

        response = Generation.call(
            model=self.model,
            prompt=prompt,
            result_format='text'
        )
        if response.status_code == 200:
            try:
                print("=--=")
                print(response.output.text)
                print("----===0")
                return json.loads(response.output.text.strip())
            except json.JSONDecodeError as e:
                print(f"JSON 解析错误: {e}")
                return {"agent": "other", "action": "other", "info": {}}
        else:
            print("error")
            return {"agent": "other", "action": "other", "info": {}}


