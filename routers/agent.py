# routers/agent.py
"""
通用 Agent 路由：根据用户意图自动分发任务到对应的 Agent
"""

from flask import Blueprint, request, jsonify, Response
from flask_login import login_required, current_user
import time
import json
import asyncio
import queue
import threading
import os
import uuid
from llm.factory import get_llm
from agents.browser_use_agent import BrowserUseAgent
from agents.test_agent import TestAgent
from agents.bug_management_agent import BugManagementAgent
from agents.intelligent_devops_agent import IntelligentDevOpsAgent
from utils.metrics import (
    MetricsRecorder,
    record_agent_execute,
    record_test_execute,
    record_bug_found,
    record_intent_detection,
    record_bugs_saved
)
from agents.evidence_extractor import deep_sse_json_safe as _sse_sanitize_for_json
from agents.sse_react_v1 import engine_dict_to_wire_packets, is_wire_v1_packet
import logging
import re
from llm.model_registry import choose_auto_model, supports_vision
from llm.model_registry import get_model

logger = logging.getLogger(__name__)

# Auto 路由：前端可能传 model="auto"（或误传 gpt/claude 等），但上游 LLM 不认识这些字符串。
# 这里将其解析为“实际可调用”的模型名，避免 invalid_model。
def _resolve_auto_model(model_name: str | None, *, has_images: bool) -> str | None:
    m = (model_name or "").strip()
    if not m:
        return None
    ml = m.lower()
    if ml == "auto":
        return choose_auto_model(has_images=has_images)
    return m

def model_supports_images(model_name: str) -> bool:
    """判断模型是否支持图片输入"""
    if not model_name:
        return False
    # Auto 模式视为支持
    if model_name == 'auto':
        return True
    return supports_vision(model_name)


def _user_followup_needs_react_after_image(text: str) -> bool:
    """
    用户是否在「读图」之外还要求走 ReAct 工具链（建 Bug / 定位 / 修改等）。
    用于非 vision 模型：先 OCR/描述图片后仍应进入主循环，而不是早退 bye。
    """
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    cn = (
        "提炼",
        "创建",
        "新建",
        "生成",
        "录入",
        "登记",
        "放到",
        "归入",
        "写入",
        "保存",
        "落库",
        "提交",
        "卡片",
        "缺陷",
        "用例",
        "测试用例",
        "badcase",
        "修改",
        "删除",
        "复制",
        "拷贝",
    )
    if any(k in raw for k in cn):
        return True
    if any(k in low for k in (" bug", "bug ", "bug#", "create ", "grep", "modify", "copy")):
        return True
    if re.search(r"\bbug\b", raw, re.I):
        return True
    return False


def _sse_json_dumps(obj, **kwargs) -> str:
    """对队列出队的 dict 做清洗后再 dumps；最后兜底避免整条 SSE 失败。"""
    try:
        clean = _sse_sanitize_for_json(obj)
        return json.dumps(clean, ensure_ascii=False, **kwargs)
    except Exception as ex:
        return json.dumps(
            {
                "type": "err",
                "payload": {"message": f"SSE JSON 序列化失败（已降级）: {ex}"},
            },
            ensure_ascii=False,
        )


agent_bp = Blueprint('agent', __name__, url_prefix='/api/agent')

_REACT_AGENT_CACHE_LOCK = threading.Lock()
_REACT_AGENT_CACHE: dict[str, IntelligentDevOpsAgent] = {}
_REACT_LLM_CACHE: dict[str, object] = {}


def _get_cached_llm(model_name: str):
    key = (model_name or "").strip() or "__default__"
    llm = _REACT_LLM_CACHE.get(key)
    if llm is not None:
        return llm
    with _REACT_AGENT_CACHE_LOCK:
        llm2 = _REACT_LLM_CACHE.get(key)
        if llm2 is not None:
            return llm2
        llm2 = get_llm(model=model_name)
        _REACT_LLM_CACHE[key] = llm2
        return llm2


def _get_cached_react_agent(model_name: str, db_session):
    key = (model_name or "").strip() or "__default__"
    agent = _REACT_AGENT_CACHE.get(key)
    if agent is not None:
        agent.set_db_session(db_session)
        return agent
    with _REACT_AGENT_CACHE_LOCK:
        agent2 = _REACT_AGENT_CACHE.get(key)
        if agent2 is not None:
            agent2.set_db_session(db_session)
            return agent2
        llm = _get_cached_llm(model_name)
        agent2 = IntelligentDevOpsAgent(llm=llm, db_session=db_session)
        _REACT_AGENT_CACHE[key] = agent2
        return agent2


@agent_bp.route('/execute', methods=['POST'])
@login_required
def execute_agent():
    """
    通用 Agent 执行接口
    
    请求格式：
    {
        "user_input": "用户输入的对话内容",
        "conversation_history": [],  # 可选，对话历史
        "agent_mode": "auto"  # 可选，"auto" 自动识别意图，或指定具体 agent
    }
    
    返回格式：
    {
        "code": 200,
        "message": "成功",
        "data": {
            "detected_agent": "browser_use",  # 识别出的 Agent 类型
            "detected_intent": "test_execution",  # 识别出的意图
            "result": {...}  # 各 Agent 的执行结果
        }
    }
    """
    try:
        start_time = time.time()
        print(f"\n[AGENT] === 开始执行 Agent 请求 {time.time()} ===")
        
        data = request.get_json() or {}
        user_input = data.get('user_input', '')
        conversation_history = data.get('conversation_history', [])
        agent_mode = data.get('agent_mode', 'auto')
        model_name = _resolve_auto_model(data.get('model'), has_images=False)
        project_id = data.get('project_id')  # 获取项目ID
        ui_locale = data.get('locale') or data.get('ui_locale')
        
        print(f"[AGENT] 用户ID: {current_user.id}")
        print(f"[AGENT] 用户输入: {user_input}")
        print(f"[AGENT] Agent 模式: {agent_mode}")
        print(f"[AGENT] 项目ID: {project_id}")
        print(f"[AGENT] 对话历史长度: {len(conversation_history)}")
        
        if not user_input.strip():
            return jsonify({
                'code': 400,
                'message': '用户输入不能为空',
                'data': None
            }), 400
        
        # 初始化模型用于意图识别
        print(f"[AGENT] 初始化模型: {model_name or 'default'}...")
        llm = get_llm(model=model_name)
        
        # 如果是自动模式，先识别意图
        detected_agent = None
        detected_intent = None
        
        if agent_mode == 'auto':
            print(f"[AGENT] 开始识别用户意图...")
            intent_start = time.time()
            
            with MetricsRecorder('intent_detection'):
                intent_result = _detect_intent(user_input, conversation_history, llm, locale=ui_locale)
            
            detected_agent = intent_result.get('agent', 'unknown')
            detected_intent = intent_result.get('intent', 'unknown')
            
            # 记录意图识别指标
            record_intent_detection(detected_intent, status='success')
            
            print(f"[AGENT] 意图识别完成 - Agent: {detected_agent}, 意图: {detected_intent}, 耗时: {time.time() - intent_start:.4f}s")
        else:
            # 直接使用指定的 Agent
            detected_agent = agent_mode
            print(f"[AGENT] 使用指定的 Agent: {detected_agent}")
        
        # 分发到对应的 Agent 执行
        print(f"[AGENT] 分发到 Agent: {detected_agent}")
        
        with MetricsRecorder('agent_execute', labels={'agent_type': detected_agent}):
            agent_result = _dispatch_to_agent(
                detected_agent,
                user_input,
                conversation_history,
                current_user.id,
                llm,
                project_id  # 传入项目ID
            )
        
        # 记录 Agent 执行指标
        record_agent_execute(detected_agent, status='success')
        
        total_time = time.time() - start_time
        print(f"[AGENT] === Agent 执行完成，总耗时: {total_time:.4f}s ===\n")
        
        return jsonify({
            'code': 200,
            'message': '成功',
            'data': {
                'detected_agent': detected_agent,
                'detected_intent': detected_intent,
                'result': agent_result,
                'execution_time': total_time
            }
        })
        
    except Exception as e:
        print(f"[AGENT] !!! 发生异常: {str(e)}")
        import traceback
        print(traceback.format_exc())
        
        # 记录失败指标
        record_agent_execute('unknown', status='failure')
        record_intent_detection('unknown', status='failure')
        
        return jsonify({
            'code': 500,
            'message': '服务器内部错误',
            'data': None
        }), 500


def _detect_intent(user_input: str, conversation_history: list, llm, locale=None) -> dict:
    """
    使用千帆模型识别用户意图
    
    返回格式：
    {
        "agent": "browser_use" | "test_agent" | "bug_management" | "other",
        "intent": "test_execution" | "bug_search" | "badcase_reproduction" | "general",
        "confidence": 0.95
    }
    """
    try:
        print(f"[AGENT-INTENT] 调用千帆模型进行意图识别...")
        
        prompt = f"""你是一个智能 Agent 意图识别系统。请分析用户输入，识别其意图并返回 JSON。

用户历史对话：
{_format_conversation_history(conversation_history)}

当前用户输入："{user_input}"

请返回以下格式的 JSON（仅 JSON，无其他文本）：
{{
    "agent": "browser_use|test_agent|bug_management|other",
    "intent": "test_execution|bug_search|badcase_reproduction|general|other",
    "confidence": 0.0-1.0,
    "reasoning": "简要说明识别理由"
}}

识别规则：
- browser_use: 用户要求测试、执行测试用例、模拟用户操作等
- test_agent: 用户要求运行测试集、生成测试报告等
- bug_management: 用户要求查询 Bug、创建 Bug、搜索问题、修改 Bug(包括修改期望结果、复现步骤、描述等)、删除 Bug 等
- test_execution: 用户提供了具体的测试步骤
- bug_search: 用户要求查找/搜索 Bug 相关信息
- badcase_reproduction: 用户要求重现/定位某个 BadCase
- bug_modify: 用户要求修改 Bug 的字段 (期望结果、复现步骤、描述、状态、优先级等)
- general: 其他通用对话
"""
        response = llm.parse_intent(prompt, conversation_history, locale=locale)
        
        if isinstance(response, list) and len(response) > 0:
            intent_data = response[0]
        else:
            intent_data = response if isinstance(response, dict) else {}
        
        # 设置默认值
        result = {
            'agent': intent_data.get('agent', 'other'),
            'intent': intent_data.get('intent', 'general'),
            'confidence': intent_data.get('confidence', 0.5),
            'reasoning': intent_data.get('reasoning', '使用默认推理')
        }
        
        print(f"[AGENT-INTENT] 意图识别结果: {result}")
        return result
        
    except Exception as e:
        print(f"[AGENT-INTENT] !!! 意图识别失败: {str(e)}")
        # 返回默认意图
        return {
            'agent': 'other',
            'intent': 'general',
            'confidence': 0.0,
            'reasoning': f'识别异常: {str(e)}'
        }


def _dispatch_to_agent(agent_type: str,
                       user_input: str, 
                       conversation_history: list,
                       user_id: str,
                       llm,
                       project_id: int = None) -> dict:
    """
    根据 Agent 类型分发任务
    """
    print(f"[AGENT-DISPATCH] 分发到 Agent: {agent_type}, project_id: {project_id}")
    
    try:
        if agent_type == 'browser_use':
            print(f"[AGENT-DISPATCH] 调用 BrowserUseAgent...")
            browser_agent = BrowserUseAgent()
            result = browser_agent.handle(
                userId=user_id,
                action='test_execution',
                llm=llm,
                test_case={'description': user_input}
            )
            return result
            
        elif agent_type == 'test_agent':
            print(f"[AGENT-DISPATCH] 调用 TestAgent...")
            test_agent = TestAgent()
            result = test_agent.handle(
                userId=user_id,
                user_input=user_input,
                llm=llm
            )
            return result
            
        elif agent_type == 'bug_management':
            print(f"[AGENT-DISPATCH] 调用 BugManagementAgent...")
            bug_agent = BugManagementAgent()
            result = bug_agent.handle(
                userId=user_id,
                user_input=user_input,
                llm=llm
            )
            return result
            
        else:
            print(f"[AGENT-DISPATCH] 使用默认处理")
            return {
                'code': 200,
                'message': '已接收您的输入，正在处理...',
                'data': {
                    'user_input': user_input,
                    'conversation_history': conversation_history,
                    'status': 'processing'
                }
            }
            
    except Exception as e:
        print(f"[AGENT-DISPATCH] !!! Agent 执行失败: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {
            'code': 500,
            'message': f'Agent 执行失败: {str(e)}',
            'data': None
        }


@agent_bp.route('/save-bugs', methods=['POST'])
@login_required
def save_bugs():
    """
    保存 Agent 生成的 Bug 列表到数据库
    
    请求格式：
    {
        "project_id": 1,
        "bugs": [
            {
                "title": "Bug 标题",
                "severity": "high",
                "description": "Bug 描述",
                "steps_to_reproduce": "1. xxx\n2. xxx",
                "expected": "预期行为",
                "actual": "实际行为",
                "source": "agent_test"
            }
        ]
    }
    
    返回格式：
    {
        "code": 200,
        "message": "成功保存15个 Bug",
        "data": {
            "saved_count": 15,
            "failed_count": 0,
            "bug_ids": [1, 2, 3, ...]
        }
    }
    """
    try:
        # 此处使用 Flask app 中的全局库
        from app import db, Bug, Project
        
        start_time = time.time()
        print(f"\n[AGENT-SAVE] === 开始保存 Bug ===")
        
        data = request.get_json() or {}
        project_id = data.get('project_id')
        bugs_data = data.get('bugs', [])
        
        if not project_id:
            print(f"[AGENT-SAVE] 错误: 不指定 project_id")
            return jsonify({
                'code': 400,
                'message': 'project_id 必需',
                'data': None
            }), 400
        
        # 验证项目是否存在
        project = Project.query.get(project_id)
        if not project:
            print(f"[AGENT-SAVE] 错误: 项目不存在 (ID: {project_id})")
            return jsonify({
                'code': 404,
                'message': '项目不存在',
                'data': None
            }), 404
        
        # 验证用户是否有权限
        if project.creator_id != current_user.id and current_user.id not in [m.id for m in project.members]:
            print(f"[AGENT-SAVE] 错误: 没有权限修改项目 (ID: {project_id})")
            return jsonify({
                'code': 403,
                'message': '你没有权限修改该项目',
                'data': None
            }), 403
        
        print(f"[AGENT-SAVE] 用户ID: {current_user.id}")
        print(f"[AGENT-SAVE] 项目 ID: {project_id}")
        print(f"[AGENT-SAVE] 待保存 Bug 数: {len(bugs_data)}")
        
        saved_count = 0
        failed_count = 0
        saved_bug_ids = []
        
        # 逐个保存 Bug
        for i, bug_info in enumerate(bugs_data):
            try:
                print(f"[AGENT-SAVE] 正在保存 Bug {i+1}/{len(bugs_data)}: {bug_info.get('title')}")
                
                new_bug = Bug(
                    title=bug_info.get('title', ''),
                    description=bug_info.get('description', ''),
                    severity=bug_info.get('severity', 'medium'),
                    priority=bug_info.get('priority', 'medium'),
                    status='open',
                    project_id=project_id,
                    creator_id=current_user.id,
                    source=bug_info.get('source', 'agent_test')
                )
                
                # 保存复现步骤和预预期结果
                if bug_info.get('steps_to_reproduce'):
                    new_bug.reproduction_steps = bug_info.get('steps_to_reproduce')
                if bug_info.get('expected'):
                    new_bug.expected_result = bug_info.get('expected')
                if bug_info.get('actual'):
                    new_bug.actual_result = bug_info.get('actual')
                
                db.session.add(new_bug)
                db.session.flush()  # 获取自动需 ID
                
                saved_bug_ids.append(new_bug.id)
                saved_count += 1
                
                # 记录发现的 Bug
                severity = bug_info.get('severity', 'medium')
                record_bug_found(severity=severity)
                
                print(f"[AGENT-SAVE] Bug 保存成功 (ID: {new_bug.id})")
                
            except Exception as e:
                print(f"[AGENT-SAVE] !!! 保存 Bug 失败: {str(e)}")
                failed_count += 1
        
        # 提交事务
        db.session.commit()
        
        total_time = time.time() - start_time
        print(f"[AGENT-SAVE] === 保存完成 ===")
        print(f"[AGENT-SAVE] 成功: {saved_count}, 失败: {failed_count}, 耗时: {total_time:.4f}s")
        
        # 记录 Bug 保存指标
        record_bugs_saved(saved_count, status='success')
        
        return jsonify({
            'code': 200,
            'message': f'成功保存{saved_count}个 Bug{", 失败" + str(failed_count) + "个" if failed_count > 0 else ""}',
            'data': {
                'saved_count': saved_count,
                'failed_count': failed_count,
                'bug_ids': saved_bug_ids
            }
        })
        
    except Exception as e:
        print(f"[AGENT-SAVE] !!! 发生且外: {str(e)}")
        import traceback
        print(traceback.format_exc())
        
        # 记录保存失败指标
        record_bugs_saved(0, status='failure')
        
        try:
            from app import db
            db.session.rollback()
        except:
            pass
        
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}',
            'data': None
        }), 500


@agent_bp.route('/react/cancel', methods=['POST'])
@login_required
def react_agent_stream_cancel():
    """前端「停止生成」时合作式通知统一流：须携带与 SSE 包一致的 request_id。"""
    try:
        data = request.get_json() or {}
        rid = (data.get('request_id') or data.get('react_request_id') or '').strip()
        if not rid:
            return jsonify({'code': 400, 'message': 'missing request_id'}), 400
        from agents.react_simplified import request_react_stream_cancel

        ok = bool(request_react_stream_cancel(rid))
        return jsonify({'code': 200, 'ok': ok})
    except Exception as e:
        logger.exception('[REACT] /react/cancel: %s', e)
        return jsonify({'code': 500, 'message': str(e)}), 500


@agent_bp.route('/react', methods=['POST'])
def react_agent():
    """
    综合型 AI 运维 Agent - ReAct 推理循环 (支持流式)
    """
    try:
        perf = (os.getenv("PERF_LOG") == "1")
        t_req0 = time.perf_counter()
        req_id = str(uuid.uuid4())[:8]
        logger.info("%s", "\n" + ("=" * 60))
        logger.info("[REACT] ReAct Agent Request (Stream) - START")
        logger.info("%s", "=" * 60)
        logger.info("[REACT] 请求时间：%s", time.strftime('%Y-%m-%d %H:%M:%S'))
        
        data = request.get_json() or {}
        if perf:
            logger.info(
                "[PERF][react_api][%s] parse_json_ms=%.1f",
                req_id,
                (time.perf_counter() - t_req0) * 1000,
            )
        user_input = data.get('user_input', '')
        images = data.get('images') or []
        stream_mode = data.get('stream', True)
        raw_model_name = data.get('model')
        model_name = _resolve_auto_model(raw_model_name, has_images=bool(images))
        project_id = data.get('project_id')
        plan_id = data.get('plan_id')
        card_id = data.get('card_id') or data.get('cardId')
        card_type = data.get('card_type') or data.get('cardType')
        ui_locale = data.get('locale') or data.get('ui_locale')
        pending_diff_context = data.get('pending_diff_context') or []
        long_memory_context = data.get('long_memory_context') or data.get('longMemoryContext')
        if not isinstance(long_memory_context, dict):
            long_memory_context = None

        logger.info("[REACT] 请求参数:")
        logger.info("  - user_input 长度: %s", len(user_input))
        logger.info("  - model(raw): %s", raw_model_name)
        logger.info("  - model(resolved): %s", model_name or "__default__")
        try:
            if str(raw_model_name or "").strip().lower() == "auto":
                ms = get_model(model_name or "")
                logger.info(
                    "  - model(auto_pick): %s provider=%s vision=%s enabled=%s",
                    (ms.id if ms else (model_name or "__default__")),
                    (ms.provider if ms else "unknown"),
                    (ms.vision if ms else supports_vision(model_name or "")),
                    (ms.enabled if ms else None),
                )
        except Exception:
            pass
        logger.info("  - stream: %s", stream_mode)
        logger.info("  - project_id: %s", project_id)
        logger.info("  - plan_id: %s", plan_id)
        logger.info("  - card_id: %s", card_id)
        logger.info("  - card_type: %s", card_type)
        try:
            logger.info(
                "  - pending_diff_context: %s",
                len(pending_diff_context) if isinstance(pending_diff_context, list) else 0,
            )
        except Exception:
            pass

        if not user_input.strip():
            return jsonify({'code': 400, 'message': '输入不能为空'}), 400

        # 预热 Redis：避免首条 ReAct 在 asyncio.to_thread 里首次 get_redis_client 冷连拖慢 gather（数百 ms～数秒）
        try:
            from app import get_redis_client

            get_redis_client()
        except Exception:
            pass

        _hpn = data.get("project_display_name") or data.get("context_project_name")
        _hpln = data.get("plan_display_name") or data.get("context_plan_name")
        hint_project_name = str(_hpn).strip() if _hpn is not None and str(_hpn).strip() else None
        hint_plan_name = str(_hpln).strip() if _hpln is not None and str(_hpln).strip() else None

        _cs = data.get("client_shell") or data.get("clientShell")
        client_shell = _cs if isinstance(_cs, dict) else None

        t_llm0 = time.perf_counter()
        llm = _get_cached_llm(model_name)
        if perf:
            logger.info(
                "[PERF][react_api][%s] get_llm_ms=%.1f model=%s",
                req_id,
                (time.perf_counter() - t_llm0) * 1000,
                model_name,
            )
        from app import db
        t_agent0 = time.perf_counter()
        _fresh = (os.getenv("BADCASE_REACT_AGENT_PER_REQUEST", "").strip().lower() in ("1", "true", "yes"))
        if _fresh:
            agent = IntelligentDevOpsAgent(llm=llm, db_session=db.session)
        else:
            agent = _get_cached_react_agent(model_name, db.session)
        if perf:
            logger.info(
                "[PERF][react_api][%s] agent_init_ms=%.1f fresh_agent=%s",
                req_id,
                (time.perf_counter() - t_agent0) * 1000,
                "1" if _fresh else "0",
            )

        # 长期记忆：把 user_id 注入到 ReAct 引擎实例（供 ES 向量检索 scope 过滤）
        try:
            if hasattr(agent, "react_engine"):
                setattr(agent.react_engine, "user_id", str(getattr(current_user, "id", "") or ""))
        except Exception:
            pass
        
        if not stream_mode:
            # 非流式模式
            result = asyncio.run(
                agent.handle_user_request(user_input, project_id=project_id, locale=ui_locale)
            )
            return jsonify({'code': 200, 'data': result})

        # 流式模式 - 使用 Queue 桥接异步生成器到同步生成器
        from flask import stream_with_context

        # §6.1.2 信封：整次 SSE 连接唯一 request_id（与 seq 配套，便于日志与前端 reducer）
        react_request_id = str(uuid.uuid4())
        t_sse0 = time.perf_counter()

        def _ms_since(t0: float) -> float:
            try:
                return (time.perf_counter() - t0) * 1000.0
            except Exception:
                return -1.0
        
        def _with_protocol_version(payload: dict) -> dict:
            """Agent SSE 协议版本（与 docs/需求文档_agent执行流程现状与优化需求_20260324.md 对齐，便于前端灰度）。"""
            if not isinstance(payload, dict):
                return payload
            out = dict(payload)
            out.setdefault('protocol_version', 1)
            out.setdefault('request_id', react_request_id)
            return out

        def generate():
            t_first_yield0 = time.perf_counter()
            # 发送初始字节以"破解"代理缓冲 (2KB 空白)
            yield ":" + " " * 2048 + "\n\n"
            # 首包 hello 由 Agent 流内发出（协议 v1），此处不再发送旧 type=status
            if perf:
                logger.info(
                    "[PERF][react_api][%s] first_yield_ms=%.1f",
                    req_id,
                    (time.perf_counter() - t_first_yield0) * 1000,
                )
            
            q = queue.Queue()
            done = object()
            # 关键：立刻推一个可见 JSON 首包，避免"只有注释首字节但 UI 无变化"造成的卡顿错觉
            # 前端 consumeAgentSseV1Chunk 会消费 hello 并确保 understanding 有值
            q.put({"type": "hello"})
            # 可选：在 Agent 真正产出 phase 之前先告知进入 think，避免首包阶段空白
            q.put({"type": "phase", "payload": {"name": "think", "n": 1}})
            # Auto 选模结果：默认不写入 SSE（避免污染对话框）。
            # 如需排查，可设置环境变量 REACT_SSE_AUTO_MODEL_HINT=1 才向前端流里发提示。
            try:
                if (
                    str(raw_model_name or "").strip().lower() == "auto"
                    and (os.getenv("REACT_SSE_AUTO_MODEL_HINT", "0") or "0").strip().lower()
                    in ("1", "true", "yes", "on")
                ):
                    q.put({
                        "type": "stream",
                        "payload": {
                            "lane": "think",
                            "delta": f"[AUTO] model={model_name or 'default'}\n",
                            "react_phase": "think",
                            "stream_channel": "content",
                        },
                    })
            except Exception:
                pass
            if perf:
                logger.info(
                    "[PERF][react_api][%s] queued_hello_phase_ms=%.1f react_request_id=%s",
                    req_id,
                    _ms_since(t_sse0),
                    react_request_id,
                )

            def run_async_loop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                async def task():
                    try:
                        if perf:
                            logger.info(
                                "[PERF][react_api][%s] async_loop_start_ms=%.1f",
                                req_id,
                                _ms_since(t_req0),
                            )
                        logger.info("[REACT] 开始异步任务循环")
                        # 图片理解放到异步线程里执行，避免阻塞 SSE 连接建立（否则前端会"卡住"）
                        _effective_input = user_input
                        # 图片意图路由：
                        # - ocr: 读字/图片说了什么 → 只做视觉，不进 ReAct（避免触发 grep/modify 等工具链）
                        # - prototype: 原型图/测试用例 → 先视觉结构化描述，再注入 ReAct（允许工具链）
                        # - react: 其他 → 走原 ReAct
                        def _classify_image_intent(_text: str) -> str:
                            t = (_text or '').strip()
                            low = t.lower()
                            # 需要走工具链：建 Bug / 写入卡片等，勿判成纯 OCR 早退
                            if any(
                                k in t
                                for k in (
                                    '提炼成bug',
                                    '提炼成 bug',
                                    '创建bug',
                                    '新建bug',
                                    '生成bug',
                                    '放到卡片',
                                    '写到卡片',
                                    '卡片里',
                                    '卡片中',
                                    '放进卡片',
                                )
                            ) or any(
                                k in low
                                for k in (
                                    'create bug',
                                    'new bug',
                                    'into card',
                                    'to card',
                                    'in card',
                                )
                            ):
                                return 'react'
                            if not t:
                                return 'ocr'
                            # 原型图 / 测试用例优先（避免被"图片"关键词误判成 ocr）
                            prototype_keys = (
                                '原型', '原型图', '界面原型', 'ui', '页面', '交互', '按钮', '输入框',
                                '生成测试', '测试用例', '用例', '用例生成', '测试点', '测试步骤'
                            )
                            if any(k in t for k in prototype_keys):
                                return 'prototype'
                            # OCR/读字
                            ocr_keys = (
                                '图片说了什么', '图上写了什么', '图里写了什么', '图片写了什么',
                                '识别文字', '提取文字', '读字', 'ocr', '识别一下', '这张图是什么'
                            )
                            if any(k in t for k in ocr_keys):
                                return 'ocr'
                            # 泛化：仅仅包含"图片/图上/这张图"但未提测试/原型时，也更像"解释图片"
                            if any(k in t for k in ('图片', '图上', '这张图', '图里')):
                                return 'ocr'
                            return 'react'

                        _image_intent = _classify_image_intent(user_input) if images else 'react'
                        _model_has_vision = model_supports_images(model_name)
                        if images:
                            # 多模态优先：仅当模型不支持图片输入时，才走下方 VisionDescribeService（独立 OCR/原型描述）。
                            # vision=true 时：不调用图片描述服务，不把图转成纯文本再喂 ReAct（避免重复、降质、多耗一次）。
                            if _model_has_vision:
                                # 模型支持图片：用户文本 + 图片应由后续 LLM 多模态调用消费（不在本路由做离线描述）。
                                q.put({
                                    'type': 'stream',
                                    'payload': {
                                        'lane': 'think',
                                        'delta': f'🌄 检测到 {len(images)} 张图片，模型 {model_name} 支持图片输入，将直接发送至模型处理…\n',
                                        'react_phase': 'think',
                                        'stream_channel': 'content',
                                    }
                                })
                                # OCR 场景下，如果模型支持图片，也进入 ReAct 主循环（而不是直接返回）
                                if _image_intent == 'ocr':
                                    logger.info("[REACT] 模型支持图片，OCR 场景也进入 ReAct 主循环")
                                    _effective_input = user_input
                                q.put({
                                    'type': 'stream',
                                    'payload': {
                                        'lane': 'think',
                                        'delta': '图片处理完成，开始推理…\n',
                                        'react_phase': 'think',
                                        'stream_channel': 'content',
                                    }
                                })
                            else:
                                # 模型不支持图片：无法用多模态消息带图，只能先调用图片描述服务生成文本，再注入 ReAct。
                                q.put({
                                    'type': 'stream',
                                    'payload': {
                                        'lane': 'think',
                                        'delta': '正在解析图片内容（模型不支持图片，先生成描述）…\n',
                                        'react_phase': 'think',
                                        'stream_channel': 'content',
                                    }
                                })
                                try:
                                    from agents.locale_prompts import vision_image_block_labels
                                    from agents.vision_describe import VisionDescribeService

                                    def _describe_sync():
                                        vision_svc = VisionDescribeService()
                                        descriptions = []
                                        for img in images[:5]:
                                            data_field = img.get('data') or img.get('url', '')
                                            if not data_field:
                                                continue
                                            if _image_intent == 'ocr':
                                                desc = vision_svc.describe_image(
                                                    data_field, user_intent=user_input or '', context=''
                                                )
                                            else:
                                                desc = vision_svc.describe_prototype_for_testcase(
                                                    data_field, user_input or '', locale=ui_locale
                                                )
                                            if desc:
                                                descriptions.append(desc)
                                        return descriptions

                                    # 放到线程池，避免卡住事件循环；同时让 SSE 心跳/状态可以先发出去
                                    descriptions = await loop.run_in_executor(None, _describe_sync)
                                    if descriptions:
                                        if _image_intent == 'ocr':
                                            # OCR 结果也走流式：边到边出，避免一次性渲染"看起来卡住/突变"
                                            for i, d in enumerate(descriptions):
                                                piece = (str(d).strip() + "\n\n") if str(d).strip() else ""
                                                if piece:
                                                    q.put({
                                                        'type': 'stream',
                                                        'payload': {
                                                            'lane': 'think',
                                                            'delta': piece,
                                                            'react_phase': 'think',
                                                            'stream_channel': 'content',
                                                        }
                                                    })
                                                    await asyncio.sleep(0)
                                        # 仅「读图/识字」且后续不要求工具链时早退；否则把描述注入 user_input 继续 ReAct
                                        if (
                                            _image_intent == 'ocr'
                                            and not _user_followup_needs_react_after_image(user_input)
                                        ):
                                            q.put({
                                                'type': 'bye',
                                                'payload': {
                                                    'findings': descriptions,
                                                    'steps_count': 0,
                                                    'duration': 0,
                                                    'thinking_time': 0,
                                                    'react_phase': 'think',
                                                }
                                            })
                                            return
                                        _ip, _ul, _def = vision_image_block_labels(ui_locale)
                                        _joined = "\n\n".join(
                                            str(x).strip() for x in descriptions if str(x).strip()
                                        )
                                        _effective_input = (
                                            _ip
                                            + "\n"
                                            + _joined
                                            + f"\n\n{_ul} "
                                            + (user_input or _def)
                                        )
                                        logger.info(
                                            "[REACT] 已注入 %s 条图片描述，丰富后的 user_input 长度: %s",
                                            len(descriptions),
                                            len(_effective_input),
                                        )
                                    else:
                                        _ip, _ul, _def = vision_image_block_labels(ui_locale)
                                        _effective_input = (
                                            _ip
                                            + "\n"
                                            + "\n\n".join(descriptions)
                                            + f"\n\n{_ul} "
                                            + (user_input or _def)
                                        )
                                        logger.info(
                                            "[REACT] 已注入 %s 条图片描述，丰富后的 user_input 长度: %s",
                                            len(descriptions),
                                            len(_effective_input),
                                        )
                                except Exception as ve:
                                    logger.exception("[REACT] 视觉描述失败，将使用原始输入: %s", ve)
                                finally:
                                    q.put({
                                        'type': 'stream',
                                        'payload': {
                                            'lane': 'think',
                                            'delta': '图片解析完成，开始推理…\n',
                                            'react_phase': 'think',
                                            'stream_channel': 'content',
                                        }
                                    })
                        _stream_images = (
                            images if images and _model_has_vision else None
                        )
                        async for chunk in agent.handle_user_request_stream(
                            _effective_input,
                            project_id=project_id,
                            plan_id=plan_id,
                            card_id=card_id,
                            card_type=card_type,
                            locale=ui_locale,
                            pending_diff_context=pending_diff_context,
                            agent_session_id=react_request_id,
                            long_memory_context=long_memory_context,
                            hint_project_name=hint_project_name,
                            hint_plan_name=hint_plan_name,
                            client_shell=client_shell,
                            images=_stream_images,
                        ):
                            if perf and not getattr(task, "_first_chunk_logged", False):
                                setattr(task, "_first_chunk_logged", True)
                                try:
                                    _t = chunk.get("type") if isinstance(chunk, dict) else type(chunk).__name__
                                except Exception:
                                    _t = "unknown"
                                logger.info(
                                    "[PERF][react_api][%s] agent_first_chunk_ms=%.1f type=%s",
                                    req_id,
                                    _ms_since(t_req0),
                                    _t,
                                )
                            try:
                                logger.info("[REACT] 产出 chunk type=%s", chunk.get("type"))
                            except Exception:
                                logger.info("[REACT] 产出 chunk type=unknown")
                            # 防御：先做一次深度 JSON 安全清洗，避免 Queue/callback 混入后续 SSE 序列化
                            # 转换引擎内部格式为 v1 协议格式
                            try:
                                if isinstance(chunk, dict) and not is_wire_v1_packet(chunk):
                                    # 引擎内部格式 {event: ...} 转换为 v1 格式 {type: ..., payload: ...}
                                    for wire_packet in engine_dict_to_wire_packets(chunk):
                                        q.put(_sse_sanitize_for_json(wire_packet))
                                else:
                                    q.put(_sse_sanitize_for_json(chunk))
                            except Exception:
                                q.put(chunk)
                    except Exception as e:
                        logger.exception("[REACT-execution] 异常: %s", str(e))
                        q.put({'type': 'err', 'payload': {'message': str(e)}})
                    finally:
                        logger.info("[REACT] 任务结束")
                        q.put(done)
                try:
                    loop.run_until_complete(task())
                except Exception as e:
                    logger.exception("[REACT-execution] 事件循环异常: %s", str(e))
                finally:
                    loop.close()

            t = threading.Thread(target=run_async_loop)
            t.daemon = True
            t.start()

            _sse_seq = [0]

            def _with_seq(d):
                if not isinstance(d, dict):
                    return d
                o = _with_protocol_version(d)
                _sse_seq[0] += 1
                o['seq'] = _sse_seq[0]
                return o

            # 心跳间隔：默认 1 秒，避免"无 chunk 时前端 10 秒无感知"
            try:
                heartbeat_timeout = float(os.getenv("REACT_SSE_HEARTBEAT_TIMEOUT", "1"))
            except Exception:
                heartbeat_timeout = 1.0
            if heartbeat_timeout <= 0:
                heartbeat_timeout = 1.0

            while True:
                try:
                    item = q.get(timeout=heartbeat_timeout)
                    if item is done:
                        break
                    # 防御：任何非 dict 的异常入队都不应炸掉 SSE 线程
                    if not isinstance(item, dict):
                        try:
                            bad_t = type(item).__name__
                        except Exception:
                            bad_t = "unknown"
                        item = {
                            "type": "err",
                            "payload": {
                                "message": f"SSE internal error: non-JSON item in queue ({bad_t})"
                            },
                        }
                    # 每条 data 后带一个注释，促使部分 WSGI 服务器尽快刷新，避免"修改中"长时间不更新
                    payload = _sse_json_dumps(_with_seq(item))
                    if perf and not getattr(generate, "_first_data_logged", False):
                        setattr(generate, "_first_data_logged", True)
                        try:
                            _t = item.get("type") if isinstance(item, dict) else type(item).__name__
                        except Exception:
                            _t = "unknown"
                        logger.info(
                            "[PERF][react_api][%s] sse_first_data_ms=%.1f type=%s",
                            req_id,
                            _ms_since(t_req0),
                            _t,
                        )
                    yield f"data: {payload}\n\n: \n\n"
                except queue.Empty:
                    # 只有当线程还在运行时才发送心跳
                    if t.is_alive():
                        yield f"data: {_sse_json_dumps(_with_seq({'type': 'heartbeat'}))}\n\n"
                    else:
                        break

        response = Response(stream_with_context(generate()), mimetype='text/event-stream')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Accel-Buffering'] = 'no'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # 注意：不再显式设置 Connection 头，避免在 waitress 等严格 WSGI 服务器下触发
        # "hop-by-hop header" 的断言错误；是否 keep-alive 由服务器 / 反向代理自行控制。
        return response
        
    except Exception as e:
        import traceback
        logger.exception("[REACT] ❌ 错误: %s", str(e))
        return jsonify({'code': 500, 'message': str(e)}), 500


@agent_bp.route('/modify_confirm', methods=['POST'])
@login_required
def modify_confirm():
    """
    确认修改接口
    
    请求格式：
    {
        "target": "bug" 或 "badcase",
        "target_id": 目标ID,
        "modifications": {field: {old: xxx, new: xxx}},
        "project_id": 项目ID
    }
    """
    try:
        data = request.get_json()
        target = data.get('target')
        target_id = data.get('target_id')
        modifications = data.get('modifications', {})
        project_id = data.get('project_id')
        
        if not target or not target_id:
            return jsonify({'success': False, 'error': '缺少必要参数'}), 400
        
        from app import db, Bug, BadCase
        
        if target == 'bug':
            bug = db.session.query(Bug).filter(
                Bug.id == target_id,
                Bug.project_id == project_id
            ).first()
            
            if not bug:
                return jsonify({'success': False, 'error': 'Bug不存在'}), 404
            
            for field, value in modifications.items():
                if hasattr(bug, field):
                    actual_value = value.get('new') if isinstance(value, dict) else value
                    setattr(bug, field, actual_value)
            
            db.session.commit()
            return jsonify({'success': True, 'message': '修改成功'})
        
        elif target == 'badcase':
            badcase = db.session.query(BadCase).filter(
                BadCase.id == target_id,
                BadCase.project_id == project_id
            ).first()
            
            if not badcase:
                return jsonify({'success': False, 'error': 'BadCase不存在'}), 404
            
            for field, value in modifications.items():
                if hasattr(badcase, field):
                    actual_value = value.get('new') if isinstance(value, dict) else value
                    setattr(badcase, field, actual_value)
            
            db.session.commit()
            return jsonify({'success': True, 'message': '修改成功'})
        
        else:
            return jsonify({'success': False, 'error': '不支持的target类型'}), 400
    
    except Exception as e:
        db.session.rollback()
        logger.exception("[MODIFY_CONFIRM] 修改失败: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@agent_bp.route('/tasks', methods=['GET'])
@login_required
def api_list_agent_tasks():
    """按 session_id（通常即单次 ReAct 的 react_request_id）查询持久化工具任务。"""
    try:
        session_id = (request.args.get('session_id') or '').strip()
        if not session_id:
            return jsonify({'success': False, 'error': '缺少 session_id'}), 400
        limit = min(int(request.args.get('limit', 100)), 500)
        from app import AgentTask

        rows = (
            AgentTask.query.filter(AgentTask.session_id == session_id[:64])
            .order_by(AgentTask.created_at.asc())
            .limit(limit)
            .all()
        )
        return jsonify(
            {
                'success': True,
                'tasks': [
                    {
                        'id': r.id,
                        'name': r.name,
                        'status': r.status,
                        'params': r.params,
                        'result': r.result,
                        'error': r.error,
                        'dependencies': r.dependencies or [],
                        'session_id': r.session_id,
                        'created_at': r.created_at.isoformat() if r.created_at else None,
                        'started_at': r.started_at.isoformat() if r.started_at else None,
                        'finished_at': r.finished_at.isoformat() if r.finished_at else None,
                    }
                    for r in rows
                ],
            }
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
