# agents/react_simplified.py
"""
极简 ReAct 引擎 - 结合 Claude Code 强约束 Prompt + 自我修正
核心：单主循环 + Agent 自管理 Todo + 强约束提示词 + 自动修正
"""

import json
import time
from typing import Dict, Any, List
from .prompts import ReactPromptTemplates, format_tools_for_prompt
from .prompts import parse_xml_todos, parse_xml_decision, parse_xml_findings
from .self_correction import SelfCorrectionEngine
from .evidence_extractor import EvidenceExtractor


class SimplifiedReActEngine:
    """极简 ReAct 引擎 - Claude Code 风格 + 自我修正"""
    
    def __init__(self, llm, tool_registry):
        """初始化"""
        self.llm = llm
        self.tools = tool_registry
        self.correction_engine = SelfCorrectionEngine(llm)  # 自我修正引擎
        self.project_id = None  # 当前项目 ID
    
    async def run_stream(self, user_input: str, project_id: int = None):
        """流式执行 ReAct 循环"""
        print(f"\n[REACT] ReAct Stream Loop Start")
        self.project_id = project_id  # 保存项目ID
        start_time = time.time()
        
        result_context = {}
        findings = []
        steps = []
        
        try:
            # ===== STEP 1: THINK =====
            yield {'event': 'thought', 'message': '正在规划任务步骤...'}
            
            tools_info = format_tools_for_prompt(self.tools)
            prompt = ReactPromptTemplates.think_prompt(
                user_input,
                tools_info,
                result_context,
                []
            )
            
            response = await self.llm.parse_intent(prompt)
            todos = parse_xml_todos(response)
            
            print(f"[REACT-STREAM] 生成的Todos: {todos}")
            
            if not todos:
                yield {'event': 'error', 'message': '无法生成任务列表'}
                return
            
            yield {'event': 'todos', 'data': todos}
            
            # ===== MAIN LOOP: ACT =====
            for i, todo in enumerate(todos):
                yield {'event': 'todo_start', 'index': i, 'todo': todo}
                
                # 决策
                decision_prompt = ReactPromptTemplates.decide_prompt(
                    todo, user_input, tools_info, result_context
                )
                decision_response = await self.llm.parse_intent(decision_prompt)
                print(f"[REACT-STREAM] LLM决策原始响应: {decision_response}")
                decision = parse_xml_decision(decision_response)
                
                print(f"[REACT-STREAM] 决策结果: {decision}")
                
                # 🔧 兜底逻辑：当 LLM 返回空响应但 Todo 包含 modify 关键词时
                if not decision['execute'] and 'modify' in todo.lower():
                    print(f"[REACT-STREAM] 检测到 modify 任务但 LLM 返回空响应，尝试自动推断参数...")
                    decision = self._infer_modify_params(todo, result_context)
                    print(f"[REACT-STREAM] 自动推断的决策: {decision}")
                
                if not decision['execute']:
                    print(f"[REACT-STREAM] 跳过任务（execute=False）")
                    yield {'event': 'skip', 'todo': todo}
                    continue
                
                print(f"[REACT-STREAM] 执行工具: {decision['tool']}")
                yield {'event': 'executing', 'tool': decision['tool'], 'reason': decision['reason']}
                
                # 🔧 批量修改逻辑：如果是 modify 工具，检查是否需要修改多个 Bug
                if decision['tool'] == 'modify':
                    bug_list = result_context.get('bug_list', [])
                    if bug_list and len(bug_list) > 1:
                        # 批量修改所有 Bug
                        all_results = []
                        for bug in bug_list:
                            bug_id = bug.get('id')
                            if bug_id:
                                modify_decision = decision.copy()
                                modify_decision['params']['target_id'] = bug_id
                                print(f"[REACT-STREAM] 批量修改 Bug ID={bug_id}")
                                observation = await self._execute_tool(modify_decision)
                                all_results.append({'bug_id': bug_id, 'result': observation})
                        
                        # 合并结果
                        observation = {
                            'success': all(r['result'].get('success') for r in all_results),
                            'message': f'已批量修改 {len(all_results)} 个 Bug',
                            'results': all_results
                        }
                    else:
                        # 单个修改
                        observation = await self._execute_tool(decision)
                else:
                    observation = await self._execute_tool(decision)
                
                print(f"[REACT-STREAM] 工具执行结果:")
                print(f"[REACT-STREAM]   成功: {observation.get('success', False)}")
                if 'results' in observation:
                    results = observation.get('results', [])
                    print(f"[REACT-STREAM]   结果条数: {len(results)}")
                    if results:
                        print(f"[REACT-STREAM] === 搜索结果详情 ===")
                        for idx, item in enumerate(results[:3], 1):
                            if isinstance(item, dict):
                                title = item.get('title') or item.get('text') or str(item)[:80]
                            else:
                                title = str(item)[:80]
                            print(f"[REACT-STREAM]   [{idx}] {title}")
                        if len(results) > 3:
                            print(f"[REACT-STREAM]   ... 还有 {len(results)-3} 条结果")
                if 'query' in observation:
                    print(f"[REACT-STREAM]   查询: {observation.get('query')}")
                if 'engine' in observation:
                    print(f"[REACT-STREAM]   引擎: {observation.get('engine')}")
                if 'error' in observation:
                    print(f"[REACT-STREAM]   错误: {observation.get('error')}")
                print(f"[REACT-STREAM]   完整结果: {observation}")
                
                # 自动修正（最多1次）
                if not observation.get('success') and not observation.get('corrected'):
                    yield {'event': 'retry', 'message': '执行失败，正在尝试自动修正...'}
                    observation = await self.correction_engine.correct_and_retry(
                        todo=todo,
                        action=decision,
                        observation=observation,
                        context=result_context,
                        available_tools=tools_info,
                        execute_fn=self._execute_tool
                    )
                
                yield {'event': 'observation', 'data': observation}
                print(f"[REACT-DEBUG] Observation: {observation}")  # 调试日志
                
                # 提取执行证据并发送
                evidence = EvidenceExtractor.extract_from_observation(
                    decision['tool'],
                    decision.get('params', {}),
                    observation
                )
                # 直接发送 evidence 对象给前端
                yield {'event': 'evidence', 'data': evidence}
                
                # 将 evidence 转换为 findings 用于后续分析
                evidence_findings = EvidenceExtractor.format_as_findings(evidence)
                findings.extend(evidence_findings)
                
                # 分析
                analyze_prompt = ReactPromptTemplates.observe_prompt(
                    todo, decision, observation, result_context
                )
                analyze_response = await self.llm.parse_intent(analyze_prompt)
                analysis = parse_xml_findings(analyze_response)
                
                # 更新状态
                result_context.update(analysis.get('context_update', {}))
                
                # 🔧 兜底逻辑：如果 context 中没有 bug_list 但 observation 中有 bug_location，自动添加
                if 'bug_list' not in result_context and decision['tool'] == 'grep':
                    if isinstance(observation, dict) and 'data' in observation:
                        obs_data = observation.get('data', {})
                        bug_location = obs_data.get('bug_location', [])
                        if bug_location:
                            result_context['bug_list'] = bug_location
                            print(f"[REACT-STREAM] 自动将 bug_location 添加到 context: {bug_location}")
                
                if analysis.get('findings'):
                    findings.extend(analysis['findings'])
                    for f in analysis['findings']:
                        print(f"[REACT-DEBUG] Finding: {f}")  # 调试日志
                        yield {'event': 'finding', 'data': f}
                
                steps.append({
                    'todo': todo,
                    'decision': decision,
                    'observation': observation,
                    'analysis': analysis
                })
                
                yield {'event': 'todo_end', 'index': i}

            # 在结束前，让LLM总结关键发现（人类可读）
            summarized_findings = []
            if findings:
                print(f"[REACT] 开始总结 {len(findings)} 条原始发现...")
                try:
                    summary_prompt = f"""你是一个技术助手，需要将下面的技术执行结果总结为简洁、人类可读的关键发现。

原始结果：
{chr(10).join(f'{i+1}. {f}' for i, f in enumerate(findings))}

要求：
1. 提取最重要的 3-5 条关键信息
2. 用简洁的中文表述，每条不超过50字
3. 避免技术术语，使用业务语言
4. 每条以emoji开头（🔍/🐛/🎯/📊）
5. 直接输出列表，不需要额外说明

格式示例：
🔍 查询到 5 个登录相关的Bug
🐛 定位 2 条高优先级缺陷
🎯 建议将 3 个Bug调整到登录计划"""
                    
                    summary_response = await self.llm.chat(summary_prompt)
                    # 按行分割，过滤空行
                    summarized_findings = [line.strip() for line in summary_response.strip().split('\n') if line.strip()]
                    print(f"[REACT] LLM总结完成: {len(summarized_findings)} 条")
                except Exception as e:
                    print(f"[REACT] LLM总结失败: {e}，使用原始数据")
                    summarized_findings = findings[:5]  # 降级：只显示前5条
            
            # 使用总结后的findings
            final_findings = summarized_findings if summarized_findings else findings
            
            yield {'event': 'done', 'findings': final_findings, 'steps_count': len(steps), 'duration': time.time() - start_time}

        except Exception as e:
            yield {'event': 'error', 'message': str(e)}

    async def run(self, user_input: str, project_id: int = None) -> Dict[str, Any]:
        """
        极简主循环 - 三步：THINK / ACT-LOOP / RESULT
        """
        print(f"\n[REACT] ReAct Loop Start")
        print(f"[REACT] Input: {user_input[:60]}...\n")
        self.project_id = project_id  # 保存项目ID
        start_time = time.time()
        
        result = {
            'status': 'success',
            'steps': [],
            'context': {},
            'findings': [],
            'duration': 0,
            'error': None
        }
        
        try:
            # ===== STEP 1: THINK =====
            print(f"[REACT] STEP 1: THINK - Claude Prompt")
            
            tools_info = format_tools_for_prompt(self.tools)
            prompt = ReactPromptTemplates.think_prompt(
                user_input,
                tools_info,
                result['context'],
                []
            )
            
            response = await self.llm.parse_intent(prompt)
            todos = parse_xml_todos(response)
            
            if not todos:
                result['error'] = 'LLM 无法生成 Todo'
                result['status'] = 'error'
                return result
            
            print(f"[REACT]   Generated {len(todos)} Todos\n")
            
            # ===== MAIN LOOP: ACT =====
            print(f"[REACT] MAIN LOOP: Executing Todos\n")
            
            for i, todo in enumerate(todos):
                print(f"[REACT] Todo {i+1}/{len(todos)}: {todo}")
                
                # 决策（ACT）
                decision_prompt = ReactPromptTemplates.decide_prompt(
                    todo,
                    user_input,
                    tools_info,
                    result['context']
                )
                
                decision_response = await self.llm.parse_intent(decision_prompt)
                decision = parse_xml_decision(decision_response)
                
                if not decision['execute']:
                    print(f"[REACT]   Skip")
                    continue
                
                # 执行工具
                print(f"[REACT]   Tool: {decision['tool']}")
                observation = await self._execute_tool(decision)
                
                # 自我修正：如果执行失败，尝试自动修正
                if not observation.get('success'):
                    print(f"[REACT]   Execution failed, retrying with correction")
                    
                    tools_info = format_tools_for_prompt(self.tools)
                    observation = await self.correction_engine.correct_and_retry(
                        todo=todo,
                        action=decision,
                        observation=observation,
                        context=result['context'],
                        available_tools=tools_info,
                        execute_fn=self._execute_tool
                    )
                
                # 分析结果（OBSERVE） + 自我修正反馈
                analyze_prompt = ReactPromptTemplates.observe_prompt(
                    todo,
                    decision,
                    observation,
                    result['context']
                )
                
                analyze_response = await self.llm.parse_intent(analyze_prompt)
                analysis = parse_xml_findings(analyze_response)
                
                # 记录
                result['steps'].append({
                    'todo': todo,
                    'decision': decision,
                    'observation': observation,
                    'analysis': analysis
                })
                
                # 更新上下文
                result['context'].update(analysis.get('context_update', {}))
                
                # 提取发现
                if analysis.get('findings'):
                    result['findings'].extend(analysis['findings'])
                    for f in analysis['findings']:
                        print(f"[REACT]   Found: {f}")
        
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            print(f"[REACT] Error: {str(e)}")
        
        result['duration'] = time.time() - start_time
        print(f"\n[REACT] Done | Steps: {len(result['steps'])} | Findings: {len(result['findings'])} | Duration: {result['duration']:.2f}s\n")
        return result
    
    def _infer_modify_params(self, todo: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        从 Todo 和 Context 中推断 modify 工具参数
        当 LLM 返回空响应时作为兜底逻辑
        """
        import re
        
        result = {
            'execute': False,
            'tool': '',
            'params': {},
            'reason': ''
        }
        
        # 检查是否包含 modify 关键词
        if 'modify' not in todo.lower():
            return result
        
        # 从 context 中获取 bug_list
        bug_list = context.get('bug_list', [])
        if not bug_list and 'bug_location' in context:
            # 尝试从 grep 结果中提取
            bug_list = context.get('bug_location', [])
        
        if not bug_list:
            print(f"[REACT-STREAM] 无法从 context 中获取 bug_list")
            return result
        
        # 获取第一个 Bug 的 ID
        first_bug = bug_list[0] if isinstance(bug_list[0], dict) else bug_list[0]
        target_id = first_bug.get('id') if isinstance(first_bug, dict) else None
        
        if not target_id:
            print(f"[REACT-STREAM] 无法从 bug_list 中提取 target_id")
            return result
        
        # 从 Todo 中提取要修改的字段
        # 例如：修改Bug的状态字段为'resolved' -> modifications: {status: 'resolved'}
        modifications = {}
        
        # 匹配状态修改
        status_match = re.search(r"状态.*?['\"](\w+)['\"]|status.*?['\"](\w+)['\"]|状态.*?(resolved|已解决|closed|关闭)", todo, re.IGNORECASE)
        if status_match:
            status_value = status_match.group(1) or status_match.group(2) or status_match.group(3)
            modifications['status'] = status_value
        
        # 匹配优先级修改
        priority_match = re.search(r"优先级.*?['\"](\w+)['\"]|priority.*?['\"](\w+)['\"]", todo, re.IGNORECASE)
        if priority_match:
            modifications['priority'] = priority_match.group(1)
        
        # 如果没有提取到修改内容，默认修改状态
        if not modifications:
            modifications['status'] = 'resolved'
        
        # 获取 project_id
        project_id = context.get('project_id') or self.project_id or '1'
        
        result = {
            'execute': True,
            'tool': 'modify',
            'params': {
                'target': 'bug',
                'target_id': target_id,
                'modifications': modifications,
                'project_id': project_id,
                'confirm': True
            },
            'reason': f'自动推断：从 context 的 bug_list 中获取 target_id={target_id}，修改 {list(modifications.keys())} 字段'
        }
        
        return result
    
    async def _execute_tool(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        tool_name = decision['tool']
        original_tool_name = tool_name
        
        # 增加模糊匹配映射
        if 'bug' in tool_name.lower() and 'management' in tool_name.lower():
            tool_name = 'bug_management'
        elif 'browser' in tool_name.lower():
            tool_name = 'browser_test'
        elif 'search' in tool_name.lower():
            tool_name = 'search'
        
        print(f"[REACT] 正在执行工具: {original_tool_name} -> {tool_name}")
            
        tool = self.tools.get(tool_name)
        
        if not tool:
            print(f"[REACT] ❌ 工具不存在: {tool_name}")
            return {'success': False, 'error': f"工具不存在：{tool_name}"}
        
        try:
            # 确保传入 userId 和 project_id
            params = decision.get('params', {})
            if 'userId' not in params:
                params['userId'] = 'system_agent'
            if self.project_id and 'project_id' not in params:
                params['project_id'] = self.project_id
            
            print(f"[REACT] 工具参数: {params}")
            print(f"[REACT] 正在执行工具: {tool_name}")
            res = await tool.execute(**params)
            
            print(f"[REACT] ✅ 工具执行完成: {tool_name}")
            print(f"[REACT] 工具返回数据类型: {type(res).__name__}")
            if isinstance(res, dict) and 'results' in res:
                print(f"[REACT] 搜索结果数量: {len(res.get('results', []))}")
            if res is None:
                res = {'success': False, 'error': '工具返回空结果'}
            elif 'success' not in res:
                res['success'] = True # 默认成功
            return res
        except Exception as e:
            print(f"[REACT] ❌ 工具执行异常: {str(e)}")
            return {'success': False, 'error': str(e)}
