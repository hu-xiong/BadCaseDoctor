# agents/redis_agent.py
import json

from django.db.models.expressions import result
from flask import Response, current_app
from langchain_core.language_models import BaseLLM

from .base import BaseAgent
from config import Config
import redis


class RedisAgent(BaseAgent):
    name = "redis"

    def __init__(self):
        self.redis_client=current_app.redis_client

        print("初始化RedisAgent")
        self.client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            decode_responses=True
        )


    def get_user_redis(self, userId: str) -> dict | None:
        key = f"redis:{userId}"
        data = self.client.hgetall(key)
        return data if data else None



    def handle(self, userId: str,action:str,llm_intent: str,llm: BaseLLM,llm_script:str,info:dict) -> dict[str, int | str] | Response:
        print("处理RedisAgent")
        redis_key="redis:"+userId
        redis_info=self.redis_client.get(redis_key)
       #用户redis的客户端
        r= None
        #判断host字符串是否为空
        print( redis_info)
        if len(info):
            #试图连接Redi
            print("正在连接Redis")
            try:
                r = redis.Redis(host=info.get("host"), port=info.get("port"),password=info.get("password"))
                if r.ping():
                   self.redis_client.set(redis_key,json.dumps(info))
                   print("连接成功")


                else:
                    print("连接失败")
            except Exception as e:
                print(e)
        else:
            if redis_info:
                #将redis_info转换成字典
                redis_info=json.loads(redis_info)
                try:
                    r = redis.Redis(host=redis_info.get("host"), port=redis_info.get("host"),
                                                    password=redis_info.get("password"))
                    if r.ping():
                        print("连接成功")

                    else:
                        print("连接失败")
                except Exception as e:
                    print(e)
            else :
                print("请先配置Redis")
                return Response("请先配置Redis", status=400)
        if action is not "connect":
            redis_info = self.redis_client.get(redis_key)
            redis_info = json.loads(redis_info)

            print("处理Redis:", llm_script)
            result=llm.dealRedis(user_input=llm_script, info=redis_info)
            print(result)
            try:
                print("python-script:",result.get("python-script"))
                r=redis.Redis(host=redis_info.get("host"), port=redis_info.get("port"),
                                                    password=redis_info.get("password"))
                reuslt=eval(result.get("python-script"))
                #将result转为字符串
                reuslt=reuslt.decode("utf-8")
                print("redis执行结果:",reuslt)
                return {"code":200,"message":"sucess","data":reuslt}
            except Exception as e:
                print(e)
                print("命令行执行失败")


















