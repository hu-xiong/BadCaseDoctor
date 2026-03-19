# routers/chat.py
import json
import asyncio

from flask import Blueprint, request, jsonify, current_app, Response
from flask_login import current_user

from agents.mysql_agent import MySQLAgent
from agents.redis_agent import RedisAgent
from agents.scriptAgent import scriptAgengt
from agents.bug_management_agent import BugManagementAgent
from llm.factory import get_llm

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/chat', methods=['POST'])
def chat_stream():
    print("=========")
    data = request.json
    user_input = data.get("inputMessage")
    project_id = data.get("projectId") # 获取项目ID
    model_name = data.get("model") # 获取模型名称
    print(user_input)

    if not user_input:
        return Response("data: {\"error\": \"Missing 'content'\"}\n\n", mimetype='text/event-stream')

    llm = get_llm(model=model_name)
    
    def generate():
        try:
            # Step 1: 解析意图 (同步运行异步方法)
            intentList = asyncio.run(llm.parse_intent(user_input))
            
            # 如果解析出的意图是 "other" 或者没有明确的 Agent，执行普通流式聊天
            is_general_chat = True
            if intentList and isinstance(intentList, list):
                for intent in intentList:
                    if intent.get("agent") not in ["other", None]:
                        is_general_chat = False
                        break
            
            if is_general_chat:
                yield f"data: {json.dumps({'type': 'start', 'message': '开始普通聊天'})}\n\n"
                # llm.chat_stream 现在是同步生成器
                for chunk in llm.chat_stream(user_input):
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
                return

            # 如果有具体 Agent 意图
            for intent in intentList:
                agent_type = intent.get("agent")
                yield f"data: {json.dumps({'type': 'agent_start', 'agent': agent_type})}\n\n"
                
                result = None
                if agent_type == "redis_agent":
                    from agents.redis_agent import RedisAgent
                    agent = RedisAgent()
                    result = agent.handle(
                        userId="2", action=intent.get("action"), llm_intent="", 
                        llm=llm, llm_script=intent.get("script"), info=intent.get("info")
                    )
                elif agent_type == "mysql_agent":
                    from agents.mysql_agent import MySQLAgent
                    agent = MySQLAgent()
                    result = agent.dealMysql(user_input, intent.get("info"))
                elif agent_type == "scriptAgent":
                    from agents.scriptAgent import scriptAgengt
                    agent = scriptAgengt()
                    result = agent.handle(
                        userId="2", action=intent.get("action"), llm_intent="", 
                        llm=llm, llm_script=intent.get("script"), info=intent.get("info")
                    )
                elif agent_type == "bug_management_agent":
                    from agents.bug_management_agent import BugManagementAgent
                    agent = BugManagementAgent()
                    info = intent.get("info") or {}
                    if project_id: info["project_id"] = project_id
                    result = agent.handle(
                        userId="2", action=intent.get("action"), llm=llm, info=info
                    )
                
                if result:
                    yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
            
            yield f"data: {json.dumps({'type': 'end'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    # 不显式设置 Connection，交由服务器/代理处理，以兼容 waitress 等 WSGI 服务器
    return response
