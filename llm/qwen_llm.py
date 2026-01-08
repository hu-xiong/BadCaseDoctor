import json
import re
from typing import Any, Sequence
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
    def __init__(self):
        self.model = Config.QWEN_API_MODEL
        dashscope.api_key = Config.QWEN_API_KEY
        self.redis_agent = RedisAgent()
        self.conversation_history = []  # 存储对话历史

    def parse_intent(self, user_input: str, history: list = None) -> dict | None:
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
        - "agent": 字符串，值必须是 ["redis_agent", "mysql_agent", "other"] 之一。
        - "planActions": 字符串，详细描述该任务的执行步骤（例如："连接 Redis，获取 key 'user:1001' 的值"）。
        - "action": 字符串，表示操作类型。可选值包括：
            "connect", "disconnect", "query", "delete", "update", "add",
            "delete_table", "query_table", "query_column", "add_column", "delete_column",
            "add_index", "delete_index", "add_foreign_key", "delete_foreign_key",
            "add_trigger", "delete_trigger"
        - "info": 对象，包含数据库/Redis 连接信息，字段包括:
            "host" (字符串), "port" (整数), "username" (字符串), "password" (字符串),"database" (字符串),如果这些属性不存在，value值为“”
          如果不需要连接，设为 null。
        - "script": 字符串，是分配给子任务的具体指令（基于用户输入切分后的提示词）。
        - "isflag": 布尔值，如果是判断类问题（如“是否存在？”、“是否成功？”），设为 true，否则 false。

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

    def dealMysql(self, user_input: str, info: str, history: list = None) -> dict[
        str, int | str | Sequence[dict[str, Any]] | Result]:
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





