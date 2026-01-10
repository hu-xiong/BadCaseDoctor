# agents/mysql_agent.py
import json

import redis
from langchain_core.language_models import BaseLLM


from .base import BaseAgent
from config import Config

class MySQLAgent(BaseAgent):
    def __init__(self):
        self.client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            decode_responses=True
        )

    def handle(self, userId: str, action: str, llm_intent: str, llm_script: str, info: str, llm: BaseLLM,
               user_input: str) -> dict | None:
        userId = "124455"

        print("info type:", type(info))

        # 验证 info 类型并存储到 Redis
        if info is not None and isinstance(info, dict):
            print("info data:", info)
            # 验证所有必需字段是否非空
            required_fields = ["host", "port", "username", "password", "database"]

            if all(info.get(field) for field in required_fields):
                # 将字典转换为 JSON 字符串后存储
                info_json = json.dumps(info)
                self.client.hset(f"mysql:{userId}", "data", info_json)
                redis_info = info
            else:
                redis_info = self.client.hgetall(f"mysql:{userId}")

        else:
            # 从 Redis 获取存储的连接信息
            stored_data = self.client.hgetall(f"mysql:{userId}")
            if stored_data:
                try:
                    redis_info = stored_data
                except json.JSONDecodeError:
                    return {"error": "Redis 中存储的数据格式错误"}
            else:
                return {"error": "未找到连接信息"}

        if redis_info is not None:
            print("redis_info", redis_info)
            if action == "connect":
                # 连接操作直接返回成功信息
                return {"code": 200, "message": "连接成功", "data": redis_info}
            else:
                # 执行数据库操作
                try:
                    result = llm.dealMysql(user_input, redis_info)
                    history_record=self.history(sql=result.get("script"), userId=userId)
                    result["history"] =history_record
                    return result
                except Exception as e:
                    return {"error": f"数据库操作失败: {str(e)}"}
        else:
            return {"error": "请输入mysql连接信息"}

    def history(self,sql : str,userId: str):
        self.client.lpush(f"mysql:{userId}:history", sql)
        return self.client.lrange(f"mysql:{userId}:history", 0, -1)