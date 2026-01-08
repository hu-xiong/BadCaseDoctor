# routers/chat.py
import json

from flask import Blueprint, request, jsonify, current_app, Response
from flask_login import current_user

from agents.mysql_agent import MySQLAgent
from agents.redis_agent import RedisAgent
from llm.factory import get_llm

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/chat', methods=['POST'])
def chat_stream():
    print("=========")
    data = request.json
    user_input = data.get("inputMessage")
    print(user_input)

    if not user_input:
        return Response("data: {\"error\": \"Missing 'content'\"}\n\n", mimetype='text/event-stream')

    # Step 1: 用 LLM 解析意图

    llm = get_llm("qwen")
    intentList = llm.parse_intent(user_input)
    current_user.id = "2"

    for intent in intentList:

        agent = intent.get("agent")
        print(agent)
        if agent == "redis_agent":
            redis_agent = RedisAgent()
            result = redis_agent.handle(userId=current_user.id,action=intent.get("action"),llm_intent="",llm=llm, llm_script=intent.get("script"),info=intent.get("info"))
            return jsonify(result)
        elif agent == "mysql_agent":
            mysql_agent = MySQLAgent()
            result = mysql_agent.handle(user_input, intent.get("info"))
            return jsonify({"code":200,"message":"sucess","data":result})
        print("================")
        print(intent)

    return jsonify({"code":200,"message":"sucess","data":intentList})
