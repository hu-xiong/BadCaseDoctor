# llm/openai_llm.py
from openai import OpenAI
from config import Config
import json


class OpenAILLM:
    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.OPENAI_MODEL

    def parse_intent(self, user_input: str) -> dict:
        print("================")
        prompt = f"""
你是一个智能路由助手。请根据用户输入，输出一个 JSON 对象，包含：
- agent: 可选值 ["redis_agent", "mysql_agent", "other"]
- action: 获取redis_agent的action,如connect,delete,hset,hget,hdel,hkeys,hvals,hgetall,hincrby,hincrbyfloat,hmset,hmget,hstrlen,hdel,hexists,hkeys,hvals,hgetall,hincrby,hincrbyfloat,hmset,hmget,hstrlen,hdel,hexists,hkeys,hvals,hgetall,hincrby,hincrbyfloat,hmset,hmget,hstrlen,hdel,hexists,hkeys,hvals,hgetall,hincrby,hincrbyfloat等关于redis的操作
- info :如果是redis要获取的redis信息，请填写。如redis的host,port,username,password,以json格式填写。


用户输入: "{user_input}"
只输出 JSON，不要任何解释。
        """.strip()

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        print("================")
        print(resp.choices[0].message.content)
        try:
            return json.loads(resp.choices[0].message.content)
        except:
            return {"agent": "other", "action": None}