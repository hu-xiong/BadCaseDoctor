# routers/chat.py
import asyncio
import json

import os

from flask import Blueprint, jsonify, request, Response
from flask_login import current_user, login_required

from llm.failure_attribution import record_auto_route_outcome
from llm.factory import get_llm
from llm.model_router import resolve_route
from llm.task_complexity import classify_image_intent
from utils.agent_rate_limit import check_agent_rate_limit, release_agent_slot

chat_bp = Blueprint('chat', __name__)


def _chat_session_id(data: dict, uid: str, project_id) -> str:
    sid = (data.get("session_id") or data.get("sessionId") or "").strip()
    if sid:
        return sid
    return f"chat:{uid or 'anon'}:{project_id or 0}"


@chat_bp.route('/api/chat', methods=['POST'])
@login_required
def chat_stream():
    print("=========")
    data = request.json or {}
    user_input = data.get("inputMessage", "") or data.get("message", "")
    images = data.get("images") or []
    project_id = data.get("projectId") or data.get("project_id")
    uid = str(getattr(current_user, "id", "") or "") if current_user.is_authenticated else ""

    ok_rl, rl_err = check_agent_rate_limit(uid or "anon", action="chat")
    if not ok_rl:
        try:
            retry_after = int((os.getenv("AGENT_RATE_RETRY_AFTER") or "60").strip() or "60")
        except ValueError:
            retry_after = 60
        retry_after = max(1, min(retry_after, 3600))
        msg = (
            "请求过于频繁，请稍后再试"
            if rl_err == "rate_limited"
            else "并发任务过多，请稍后再试"
        )
        resp = jsonify({"success": False, "error": rl_err or "rate_limited", "message": msg})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    image_intent = classify_image_intent(user_input) if images else None
    session_id = _chat_session_id(data, uid, project_id)
    _route = resolve_route(
        data.get("model"),
        has_images=bool(images),
        channel="chat",
        image_intent=image_intent,
        project_id=project_id,
        session_id=session_id,
        user_input=user_input,
        user_id=uid or None,
    )
    model_name = _route.business_model_id
    ui_locale = data.get("locale") or data.get("ui_locale")

    if images:
        try:
            from agents.locale_prompts import vision_image_block_labels
            from agents.vision_describe import VisionDescribeService

            vision_svc = VisionDescribeService(vision_model=_route.vision_model_id)
            descriptions = []
            for img in images[:5]:
                data_field = img.get("data") or img.get("url", "")
                if not data_field:
                    continue
                desc = vision_svc.describe_prototype_for_testcase(
                    data_field, user_input or "", locale=ui_locale
                )
                if desc:
                    descriptions.append(desc)
            if descriptions:
                _ip, _ul, _def = vision_image_block_labels(ui_locale)
                user_input = (
                    _ip
                    + "\n"
                    + "\n\n".join(descriptions)
                    + f"\n\n{_ul} "
                    + (user_input or _def)
                )
        except Exception as ve:
            print(f"[CHAT] 视觉描述失败: {ve}")

    if not user_input:
        release_agent_slot(uid or "anon")
        return Response("data: {\"error\": \"Missing 'content'\"}\n\n", mimetype='text/event-stream')

    llm = get_llm(model=model_name)

    def generate():
        _ok = True
        _err = ""
        try:
            intentList = asyncio.run(llm.parse_intent(user_input, locale=ui_locale))

            is_general_chat = True
            if intentList and isinstance(intentList, list):
                for intent in intentList:
                    if intent.get("agent") not in ["other", None]:
                        is_general_chat = False
                        break

            if is_general_chat:
                yield f"data: {json.dumps({'type': 'start', 'message': '开始普通聊天'})}\n\n"
                for chunk in llm.chat_stream(user_input, locale=ui_locale):
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
                return

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
                    if project_id:
                        info["project_id"] = project_id
                    result = agent.handle(
                        userId="2", action=intent.get("action"), llm=llm, info=info
                    )

                if result:
                    yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"

            yield f"data: {json.dumps({'type': 'end'})}\n\n"

        except Exception as e:
            _ok = False
            _err = str(e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            try:
                record_auto_route_outcome(
                    user_id=uid,
                    project_id=project_id,
                    session_id=session_id,
                    used_auto=_route.used_auto,
                    business_model_id=model_name,
                    vision_model_id=_route.vision_model_id,
                    success=_ok,
                    error_message=_err,
                    task_was_simple=(_route.task_complexity == "simple"),
                )
            except Exception:
                pass
            try:
                release_agent_slot(uid or "anon")
            except Exception:
                pass

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response
