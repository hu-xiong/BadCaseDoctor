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
from datetime import datetime
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

agent_bp = Blueprint('agent', __name__, url_prefix='/api/agent')


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
        model_name = data.get('model')
        project_id = data.get('project_id')  # 获取项目ID
        
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
                intent_result = _detect_intent(user_input, conversation_history, llm)
            
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


def _detect_intent(user_input: str, conversation_history: list, llm) -> dict:
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
- bug_management: 用户要求查询 Bug、创建 Bug、搜索问题等
- test_execution: 用户提供了具体的测试步骤
- bug_search: 用户要求查找/搜索 Bug 相关信息
- badcase_reproduction: 用户要求重现/定位某个 BadCase
- general: 其他通用对话
"""
        
        response = llm.parse_intent(prompt, conversation_history)
        
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


@agent_bp.route('/react', methods=['POST'])
def react_agent():
    """
    综合型 AI 运维 Agent - ReAct 推理循环 (支持流式)
    """
    try:
        print(f"\n[REACT] ReAct Agent Request (Stream)")
        
        data = request.get_json() or {}
        user_input = data.get('user_input', '')
        stream_mode = data.get('stream', True)  # 默认开启流式
        model_name = data.get('model')  # 获取模型名称
        project_id = data.get('project_id')  # 获取项目ID
        
        if not user_input.strip():
            return jsonify({'code': 400, 'message': '输入不能为空'}), 400
        
        llm = get_llm(model=model_name)
        from app import db
        agent = IntelligentDevOpsAgent(llm=llm, db_session=db.session)
        
        if not stream_mode:
            # 非流式模式
            result = asyncio.run(agent.handle_user_request(user_input, project_id=project_id))
            return jsonify({'code': 200, 'data': result})

        # 流式模式 - 使用 Queue 桥接异步生成器到同步生成器
        from flask import stream_with_context
        
        def generate():
            # 发送初始字节以“破解”代理缓冲 (2KB 空白)
            yield ":" + " " * 2048 + "\n\n"
            yield f"data: {json.dumps({'type': 'status', 'message': '连接已建立，准备执行...'})}\n\n"
            
            q = queue.Queue()
            done = object()

            def run_async_loop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                async def task():
                    try:
                        print(f"[REACT-STREAM] 开始异步任务循环")
                        async for chunk in agent.handle_user_request_stream(user_input, project_id=project_id):
                            print(f"[REACT-STREAM] 产出 chunk: {chunk.get('type')}")
                            q.put(chunk)
                    except Exception as e:
                        print(f"[REACT-STREAM] 异常: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        q.put({'type': 'error', 'message': str(e)})
                    finally:
                        print(f"[REACT-STREAM] 任务结束")
                        q.put(done)
                try:
                    loop.run_until_complete(task())
                except Exception as e:
                    print(f"[REACT-STREAM] 事件循环异常: {str(e)}")
                    import traceback
                    traceback.print_exc()
                finally:
                    loop.close()

            t = threading.Thread(target=run_async_loop)
            t.daemon = True
            t.start()

            while True:
                try:
                    item = q.get(timeout=10) # 缩短超时，更频繁地发送心跳
                    if item is done:
                        break
                    yield f"data: {json.dumps(item)}\n\n"
                except queue.Empty:
                    # 只有当线程还在运行时才发送心跳
                    if t.is_alive():
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    else:
                        break

        response = Response(stream_with_context(generate()), mimetype='text/event-stream')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Accel-Buffering'] = 'no'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Connection'] = 'keep-alive'
        return response
        
    except Exception as e:
        import traceback
        print(f"[REACT] ❌ 错误: {str(e)}")
        traceback.print_exc()
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
        print(f"[MODIFY_CONFIRM] 修改失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
