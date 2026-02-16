import json
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence, Dict, Union, Optional, List
from urllib.parse import quote_plus

import dashscope
from dashscope import Generation
from langchain_community.llms import Tongyi
from langchain_community.utilities import SQLDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from sqlalchemy import Result

from agents.redis_agent import RedisAgent
from config import Config


class QwenLLM:
    def __init__(self, model: str = None):
        self.model = model or Config.QWEN_API_MODEL
        dashscope.api_key = Config.QWEN_API_KEY
        self.redis_agent = RedisAgent()
        self.conversation_history = []  # 存储对话历史
        self.executor = ThreadPoolExecutor(max_workers=3)  # 线程池用于同步API调用

    async def parse_intent(self, user_input: str, history: list = None) -> Optional[dict]:
        """异步方法：在线程池中运行同步API调用"""
        def _sync_parse():
            # 增加检查：如果 user_input 已经包含了系统指令或特定格式，则不使用路由模板
            if "<system>" in user_input or "<format>" in user_input or "必须返回" in user_input:
                response = Generation.call(
                    model=self.model,
                    prompt=user_input,
                    result_format='text'
                )
                if response.status_code == 200:
                    text = response.output.text.strip()
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
    
        当前用户输入: "{user_input}"
        """.strip()
    
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
            
        # 在线程池中运行同步代码，协程等待
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(self.executor, _sync_parse)
        return result

    def chat_stream(self, prompt: str, history: list = None):
        """流式聊天方法 (同步生成器，方便 Flask 使用)"""
        responses = Generation.call(
            model=self.model,
            prompt=prompt,
            result_format='text',
            stream=True,
            incremental_output=True
        )
        for response in responses:
            if response.status_code == 200:
                yield response.output.text
            else:
                yield f"Error: {response.message}"

    async def chat(self, prompt: str, history: list = None) -> str:
        """通用聊天方法，直接返回文本"""
        def _sync_chat():
            response = Generation.call(
                model=self.model,
                prompt=prompt,
                result_format='text'
            )
            if response.status_code == 200:
                return response.output.text
            return f"Error: {response.message}"

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync_chat)

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


