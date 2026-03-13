# agents/react_simplified.py
"""
极简 ReAct 引擎 - 结合 Claude Code 强约束 Prompt + 自我修正 + Skill动态加载 + Text2SQL
核心：单主循环 + Agent 自管理 Todo +强约束提示词 + 自动修正 +技能匹配 + 自然语言SQL
"""

import asyncio
import concurrent.futures
import json
import time
from typing import Dict, Any, List

#原依赖
from .prompts import ReactPromptTemplates, format_tools_for_prompt
from .prompts import parse_xml_todos, parse_xml_decision, parse_xml_findings
from .self_correction import SelfCorrectionEngine
from .evidence_extractor import EvidenceExtractor

# Skill 动态加载
from .skill_loader import SkillLoader
from .skill_registry import skill_registry
from .skill import Skill
from .skill_integration import skill_integration  # Skill 集成管理器

# Text2SQL
try:
    from .tools.sqlcoder_agent import Text2SQLAgent, LLMBackend
    TEXT2SQL_AVAILABLE = True
except ImportError:
    TEXT2SQL_AVAILABLE = False
    print("[REACT]⚠  Text2SQLAgent 未安装，使用传统查询模式")


def get_text2sql_tool(db_path="instance/badcase_doctor.db"):
    """获取 Text2SQL 工具实例"""
    if TEXT2SQL_AVAILABLE:
        try:
            return Text2SQLAgent(
                database_path=db_path,
                llm_backend=LLMBackend.GLM_5,
                debug=False
            )
        except Exception as e:
            print(f"[REACT] Text2SQL初始化失败: {e}")
            return None
    return None


class SimplifiedReActEngine:
    """增强版极简 ReAct 引擎 -集 Skill + Text2SQL"""
    
    def __init__(self, llm, tool_registry, skill_dir=".qoder/skills"):
        """初始化"""
        self.llm = llm
        self.tools = tool_registry
        self.correction_engine = SelfCorrectionEngine(llm)  # 自我修正引擎
        self.project_id = None  # 当前项目 ID
        
        # Skill动态加载
        self.skill_loader = SkillLoader(skill_dir)
        self.skill_registry = skill_registry
        print(f"[REACT]💡引擎已初始化，Skill目录: {skill_dir}")
        
        # Text2SQL
        if TEXT2SQL_AVAILABLE:
            self.text2sql_tool = get_text2sql_tool("instance/badcase_doctor.db")
            print("[REACT] ✅ Text2SQL已启用")
        else:
            self.text2sql_tool = None
            print("[REACT] ⚠️  Text2SQL 不可用")
        # 线程池：modify 等工具内部有同步 DB（Flask/SQLAlchemy），在事件循环中会阻塞，导致流式“修改中...”卡住
        self._tool_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="react_tool")
    
    async def run_stream(self, user_input: str, project_id: int = None, plan_id: int = None):
        """流式执行 ReAct循环（使用Skill工具）。plan_id 为当前迭代计划ID，传入则 grep 可只检索该计划下的记录（人类式先看本迭代）。"""
        print(f"\n[REACT] ReAct Stream Loop Start")
        self.project_id = project_id
        self.plan_id = plan_id  # 当前迭代计划，供 grep 按计划检索
        start_time = time.time()
        
        result_context = {}
        if plan_id is not None:
            result_context['plan_id'] = plan_id  # 供 LLM 传给 grep，先检索本计划再阅读
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
            
            # ===== SKILL 匹配：检查是否有匹配的技能工作流 =====
            matched_skill, skill_score = skill_integration.match_skill(user_input, result_context)
            
            if matched_skill and skill_score >= 0.3:
                print(f"[REACT-STREAM] 🎯 匹配到技能: {matched_skill.name} (分数: {skill_score:.2f})")
                print(f"[REACT-STREAM] 📋 将按 todos 逐个执行，共 {len(todos)} 个任务")
                yield {'event': 'skill_matched', 'skill': matched_skill.name, 'score': skill_score}
                
                # 初始化 observation 变量
                observation = {}
                batch_results = []  # 收集所有批量修改结果
                
                # 按 todos 逐个执行，而不是按固定技能工作流
                for i, todo in enumerate(todos):
                    yield {'event': 'todo_start', 'index': i, 'todo': todo}
                    
                    # 从 todo 中提取关键词和状态
                    todo_params = await self._extract_todo_params(todo, user_input)
                    tool_name = todo_params['tool']
                    
                    print(f"[REACT-STREAM] Todo[{i}] 提取参数: tool={tool_name}, params={todo_params}")
                    
                    # 确保必要参数
                    params = todo_params['params']
                    if 'project_id' not in params and project_id:
                        params['project_id'] = project_id
                    if 'userId' not in params:
                        params['userId'] = 'system_agent'
                    
                    # 如果是 modify 工具，需要从 grep 结果中获取 target_id（含 testcase）
                    if tool_name == 'modify':
                        grep_result = result_context.get('grep_result', {})
                        target_type = params.get('target', 'badcase')
                        if target_type == 'bug':
                            target_id = grep_result.get('first_bug_id')
                        elif target_type == 'testcase':
                            target_id = grep_result.get('first_testcase_id')
                        else:
                            target_id = grep_result.get('first_badcase_id')
                        if target_id:
                            params['target_id'] = target_id
                            print(f"[REACT-STREAM] 从 grep 结果获取 target_id={target_id}")
                        else:
                            print(f"[REACT-STREAM] ⚠️ 无法从 grep 结果获取 target_id")
                    
                    # 执行工具
                    decision = {'execute': True, 'tool': tool_name, 'params': params}
                    yield {'event': 'executing', 'tool': tool_name, 'reason': f'Todo步骤 {i+1}'}
                    
                    observation = await self._execute_tool(decision)
                    print(f"[REACT-STREAM] Todo[{i}] 工具 {tool_name} 结果: success={observation.get('success')}")
                    
                    # 更新上下文（供后续步骤使用，含 testcase；id 用 rerank 取分高的）
                    if tool_name == 'grep' and observation.get('success'):
                        grep_data = observation.get('data', {})
                        badcase_list = grep_data.get('badcase_analysis', [])
                        bug_list = grep_data.get('bug_location', [])
                        testcase_list = grep_data.get('testcase_location', [])
                        kw = (params.get('keywords') or result_context.get('_last_grep_keywords') or '')
                        result_context['_last_grep_keywords'] = kw or params.get('keywords') or ''
                        def first_id(lst, kws):
                            if not lst: return None
                            picked = self._rerank_and_pick(lst, kws, 'title', 1)
                            return picked[0].get('id') if picked else lst[0].get('id')
                        result_context['grep_result'] = {
                            'first_badcase_id': first_id(badcase_list, kw),
                            'first_bug_id': first_id(bug_list, kw),
                            'first_testcase_id': first_id(testcase_list, kw),
                            'badcase_list': badcase_list,
                            'bug_list': bug_list,
                            'testcase_list': testcase_list
                        }
                        result_context['badcase_list'] = badcase_list
                        result_context['bug_list'] = bug_list
                        result_context['testcase_list'] = testcase_list
                        print(f"[REACT-STREAM] grep 结果: {len(badcase_list)} badcase, {len(bug_list)} bug, {len(testcase_list)} testcase")
                    
                    # 如果是 modify，收集结果（含 testcase）
                    if tool_name == 'modify':
                        target_list = (result_context.get('badcase_list') or result_context.get('bug_list') or result_context.get('testcase_list') or [])
                        target_type = 'badcase' if result_context.get('badcase_list') else ('bug' if result_context.get('bug_list') else 'testcase')
                        
                        if observation.get('success'):
                            batch_results.append({
                                'target_id': params.get('target_id'),
                                'target': target_type,
                                'plan_id': None,
                                'diff': observation.get('diff', []),
                                'modifications': params.get('modifications', {}),
                                'before': observation.get('before', {}),
                                'after': observation.get('after', {}),
                                'confirmation_required': observation.get('confirmation_required', True),
                                'success': True
                            })
                    
                    # 发送观察结果
                    yield {'event': 'observation', 'data': observation}
                    yield {'event': 'todo_end', 'index': i}
                
                # 技能工作流完成
                print(f"[REACT-STREAM] ✅ Todos 执行完成")
                
                # 汇总结果
                workflow_findings = []
                if batch_results:
                    # 批量修改结果
                    target_name = 'BadCase'
                    mod_summaries = []
                    for r in batch_results:
                        mods = r.get('modifications', {})
                        status = mods.get('status', '')
                        if status:
                            mod_summaries.append(f"ID={r['target_id']} 状态={status}")
                    
                    observation = {
                        'success': all(r.get('success') for r in batch_results),
                        'message': f'已生成 {len(batch_results)} 条修改预览',
                        'summary': f'批量修改预览：{"、".join(mod_summaries)}',
                        'batch_modify': True,
                        'batch_results': batch_results,
                        'batch_count': len(batch_results),
                        'target': 'badcase'
                    }
                    workflow_findings.append(observation['summary'])
                    yield {'event': 'observation', 'data': observation}
                
                # 发送 done 事件
                yield {
                    'event': 'done', 
                    'findings': workflow_findings, 
                    'steps_count': len(todos),
                    'duration': time.time() - start_time
                }
                return
            
            # ===== MAIN LOOP: ACT（正常流程，当没有匹配技能时）=====
            for i, todo in enumerate(todos):
                yield {'event': 'todo_start', 'index': i, 'todo': todo}
                
                # 决策：LLM决定使用哪个工具
                decision_prompt = ReactPromptTemplates.decide_prompt(
                    todo, user_input, tools_info, result_context
                )
                decision_response = await self.llm.parse_intent(decision_prompt)
                print(f"[REACT-STREAM] LLM决策原始响应: {decision_response}")
                decision = parse_xml_decision(decision_response)
                
                print(f"[REACT-STREAM] 决策结果: {decision}")
                
                # 兜底逻辑：当 LLM 返回空响应但 Todo包含 modify 关键词时
                if not decision['execute'] and 'modify' in todo.lower():
                    print(f"[REACT-STREAM] 检测到 modify 任务但 LLM 返回空响应，尝试自动推断参数...")
                    decision = self._infer_modify_params(todo, result_context)
                    print(f"[REACT-STREAM] 自动推断的决策: {decision}")
                
                # Skill工具优化：智能任务处理
                if decision['execute']:
                    decision = await self._optimize_with_skill_tool(decision, user_input, result_context, project_id)
                
                if not decision['execute']:
                    print(f"[REACT-STREAM] 跳过任务（execute=False）")
                    yield {'event': 'skip', 'todo': todo, 'index': i}
                    yield {'event': 'todo_end', 'index': i}
                    continue
                
                # Text2SQL 优化：数据库查询优先使用自然语言
                if decision['execute'] and decision['tool'] == 'database_query':
                    natural_query = self._extract_natural_query(todo, user_input)
                    if natural_query and self.text2sql_tool:
                        print(f"[REACT-STREAM] 优先使用 Text2SQL执行: {natural_query}")
                        decision['params']['natural_query'] = natural_query
                
                print(f"[REACT-STREAM] 执行工具: {decision['tool']}")
                yield {'event': 'executing', 'tool': decision['tool'], 'reason': decision.get('reason', '')}
                
                # 批量修改逻辑：如果是 modify 工具，检查是否有候选列表（badcase/bug/testcase）
                if decision['tool'] == 'modify':
                    badcase_list = result_context.get('badcase_list', [])
                    bug_list = result_context.get('bug_list', [])
                    testcase_list = result_context.get('testcase_list', [])
                    target_list = badcase_list or bug_list or testcase_list
                    target_type = 'badcase' if badcase_list else ('bug' if bug_list else 'testcase')
                    
                    if target_list and len(target_list) > 1:
                        # 批量修改所有记录
                        all_results = []
                        for item in target_list:
                            item_id = item.get('id')
                            item_plan_id = item.get('plan_id')  # 获取 plan_id
                            if item_id:
                                modify_decision = decision.copy()
                                modify_decision['params']['target_id'] = item_id
                                modify_decision['params']['target'] = target_type
                                print(f"[REACT-STREAM] 批量修改 {target_type} ID={item_id}, plan_id={item_plan_id}")
                                observation = await self._execute_tool(modify_decision)
                                all_results.append({
                                    'id': item_id,
                                    'plan_id': item_plan_id,  # 添加 plan_id
                                    'result': observation
                                })
                        
                        # 合并结果
                        target_name = 'Bug' if target_type == 'bug' else ('测试用例' if target_type == 'testcase' else 'BadCase')
                        modifications = decision.get('params', {}).get('modifications', {})
                        mod_summary = '、'.join([f'{k}:{v}' for k, v in modifications.items()])
                        observation = {
                            'success': all(r['result'].get('success') for r in all_results),
                            'message': f'已批量修改 {len(all_results)} 个 {target_type}',
                            'summary': f'批量修改{len(all_results)}条{target_name}：{mod_summary}',
                            'results': all_results,
                            'batch_modify': True,
                            'target': target_type
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
                
                # 智能重试：如果 modify 缺少 target_id，自动执行 grep 查询
                if decision['tool'] == 'modify' and observation.get('need_grep_first'):
                    print(f"[REACT-STREAM] modify 缺少 target_id，自动执行 grep 查询...")
                    yield {'event': 'retry', 'message': '正在执行 grep 工具定位目标记录...'}
                    
                    suggested_params = observation.get('suggested_params', {})
                    # 从用户输入/ todo 中提取要查找的标题作为 keywords（拆分模糊匹配由 grep 内部处理）
                    keywords = self._extract_title_keywords_for_grep(user_input, todo)
                    grep_params = {
                        'target': suggested_params.get('target', 'badcase'),
                        'project_id': suggested_params.get('project_id', self.project_id),
                        'userId': 'system_agent'
                    }
                    if keywords:
                        grep_params['keywords'] = keywords
                        print(f"[REACT-STREAM] 从用户输入提取 grep keywords: '{keywords}'")
                    # 若有当前迭代计划，只查该计划下的记录（人类式先检索本迭代）
                    if result_context.get('plan_id') is not None or getattr(self, 'plan_id', None) is not None:
                        grep_params['plan_id'] = result_context.get('plan_id') or self.plan_id
                    grep_decision = {
                        'execute': True,
                        'tool': 'grep',
                        'params': grep_params
                    }
                    grep_observation = await self._execute_tool(grep_decision)
                    print(f"[REACT-STREAM] grep 结果: success={grep_observation.get('success')}")
                    
                    # 从 grep 结果中提取 target_id（rerank 分高的选一条；支持 badcase/bug/testcase）
                    if grep_observation.get('success'):
                        grep_data = grep_observation.get('data', {})
                        badcase_list = grep_data.get('badcase_analysis', [])
                        bug_list = grep_data.get('bug_location', [])
                        testcase_list = grep_data.get('testcase_location', [])
                        
                        if badcase_list:
                            result_context['badcase_list'] = badcase_list
                            best = self._pick_best_match_from_list(badcase_list, keywords, key_title='title')
                            result_context['first_badcase_id'] = best.get('id')
                            print(f"[REACT-STREAM] BadCase rerank 选中 id={best.get('id')}")
                        if bug_list:
                            result_context['bug_list'] = bug_list
                            best = self._pick_best_match_from_list(bug_list, keywords, key_title='title')
                            result_context['first_bug_id'] = best.get('id')
                            print(f"[REACT-STREAM] Bug rerank 选中 id={best.get('id')}")
                        if testcase_list:
                            result_context['testcase_list'] = testcase_list
                            best = self._pick_best_match_from_list(testcase_list, keywords, key_title='title')
                            result_context['first_testcase_id'] = best.get('id')
                            print(f"[REACT-STREAM] 测试用例 rerank 选中 id={best.get('id')}")
                        
                        yield {'event': 'observation', 'data': grep_observation}
                        
                        target_list = result_context.get('badcase_list') or result_context.get('bug_list') or result_context.get('testcase_list')
                        if target_list:
                            target_type = 'badcase' if result_context.get('badcase_list') else ('bug' if result_context.get('bug_list') else 'testcase')
                            best_match = self._pick_best_match_from_list(target_list, keywords, key_title='title')
                            target_list = [best_match]
                            result_context['first_badcase_id' if target_type == 'badcase' else ('first_bug_id' if target_type == 'bug' else 'first_testcase_id')] = best_match.get('id')
                            # 单条修改（不再按“多条就批量”）
                            if len(target_list) >= 1:
                                print(f"[REACT-STREAM] 重试批量修改 {len(target_list)} 条 {target_type}")
                                all_results = []
                                for item in target_list:
                                    item_id = item.get('id')
                                    if item_id:
                                        retry_decision = decision.copy()
                                        retry_decision['params']['target_id'] = item_id
                                        retry_decision['params']['target'] = target_type
                                        retry_obs = await self._execute_tool(retry_decision)
                                        all_results.append({'id': item_id, 'plan_id': item.get('plan_id'), 'result': retry_obs})
                                
                                observation = {
                                    'success': all(r['result'].get('success') for r in all_results),
                                    'message': f'已批量修改 {len(all_results)} 个 {target_type}',
                                    'summary': f'批量修改{len(all_results)}条{"Bug" if target_type == "bug" else ("测试用例" if target_type == "testcase" else "BadCase")}',
                                    'results': all_results,
                                    'batch_modify': True,
                                    'target': target_type
                                }
                            else:
                                # 单个修改
                                retry_decision = decision.copy()
                                retry_decision['params']['target_id'] = target_list[0].get('id')
                                retry_decision['params']['target'] = target_type
                                print(f"[REACT-STREAM] 重试单个修改: target_id={retry_decision['params']['target_id']}")
                                observation = await self._execute_tool(retry_decision)
                
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
                
                # 兜底逻辑：如果 context 中没有 bug_list/badcase_list 但 observation 中有，自动添加
                if decision['tool'] == 'grep' and isinstance(observation, dict):
                    # 多种可能的数据位置
                    obs_data = observation.get('data', observation)
                    if not isinstance(obs_data, dict):
                        obs_data = {}
                    
                    # Bug 列表 - 从多个可能的位置提取
                    if 'bug_list' not in result_context:
                        bug_location = obs_data.get('bug_location', []) or observation.get('bug_location', [])
                        if bug_location and isinstance(bug_location, list) and len(bug_location) > 0:
                            result_context['bug_list'] = bug_location
                            kw = result_context.get('_last_grep_keywords', '')
                            best = self._pick_best_match_from_list(bug_location, kw, 'title') if kw else (bug_location[0] if isinstance(bug_location[0], dict) else None)
                            result_context['first_bug_id'] = best.get('id') if isinstance(best, dict) else (bug_location[0].get('id') if isinstance(bug_location[0], dict) else None)
                            print(f"[REACT-STREAM] 自动将 bug_location 添加到 context: {len(bug_location)} 条")
                    
                    # BadCase 列表 - 从多个可能的位置提取
                    if 'badcase_list' not in result_context:
                        badcase_analysis = obs_data.get('badcase_analysis', []) or observation.get('badcase_analysis', [])
                        if badcase_analysis and isinstance(badcase_analysis, list) and len(badcase_analysis) > 0:
                            # 提取为简化列表格式
                            badcase_list = []
                            for bc in badcase_analysis:
                                if not isinstance(bc, dict):
                                    continue
                                bc_id = bc.get('id')
                                if bc_id is None:
                                    continue
                                badcase_list.append({
                                    'id': bc_id,
                                    'title': bc.get('title', ''),
                                    'status': bc.get('status'),
                                    'plan_id': bc.get('plan_id')
                                })
                            
                            if badcase_list:
                                result_context['badcase_list'] = badcase_list
                                result_context['badcase_analysis'] = badcase_analysis
                                kw = result_context.get('_last_grep_keywords', '')
                                best = self._pick_best_match_from_list(badcase_list, kw, 'title') if kw else badcase_list[0]
                                result_context['first_badcase_id'] = best.get('id')
                                print(f"[REACT-STREAM] 自动将 badcase_list 添加到 context: {len(badcase_list)} 条")
                    
                    if 'testcase_list' not in result_context:
                        testcase_location = obs_data.get('testcase_location', []) or observation.get('testcase_location', [])
                        if testcase_location and isinstance(testcase_location, list) and len(testcase_location) > 0:
                            testcase_list = [{'id': tc.get('id'), 'title': tc.get('title'), 'plan_id': tc.get('current_plan_id')} for tc in testcase_location if isinstance(tc, dict) and tc.get('id') is not None]
                            if testcase_list:
                                result_context['testcase_list'] = testcase_list
                                kw = result_context.get('_last_grep_keywords', '')
                                best = self._pick_best_match_from_list(testcase_list, kw, 'title') if kw else testcase_list[0]
                                result_context['first_testcase_id'] = best.get('id')
                                print(f"[REACT-STREAM] 自动将 testcase_list 添加到 context: {len(testcase_list)} 条")
                    
                    print(f"[REACT-STREAM] Context 更新后: bug_list={len(result_context.get('bug_list', []))}条, badcase_list={len(result_context.get('badcase_list', []))}条, testcase_list={len(result_context.get('testcase_list', []))}条")
                
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
                
                # 动态添加批量修改任务（仅当没有已有的modify任务时）
                if decision['tool'] == 'grep':
                    # 支持 BadCase 和 Bug 批量修改
                    target_list = result_context.get('badcase_list', []) or result_context.get('bug_list', [])
                    target_type = 'badcase' if result_context.get('badcase_list') else 'bug'
                    
                    # 检测用户是否有批量修改意图
                    modify_keywords = ['修改', '改成', '更新', '设为', '状态', '关闭', 'closed', 'resolved']
                    has_modify_intent = any(kw in user_input for kw in modify_keywords)
                    
                    # 检查是否已有 modify 任务（避免重复添加）
                    existing_modify_count = sum(1 for t in todos if 'modify' in t.lower())
                    
                    if has_modify_intent and target_list and len(target_list) > 1 and existing_modify_count == 0:
                        print(f"[REACT-STREAM] 检测到批量修改意图，{len(target_list)} 个 {target_type}，使用批量模式")
                        
                        # 只添加一个批量修改任务（后端会处理全部）
                        ids_str = ', '.join([str(item['id']) for item in target_list])
                        new_todo = f"使用 modify 工具批量修改 {len(target_list)} 个 {target_type} (ID: {ids_str}) 的状态"
                        todos.append(new_todo)
                        print(f"[REACT-STREAM] 添加批量修改任务: {new_todo}")
                        
                        # 通知前端任务列表已更新
                        yield {'event': 'todos', 'data': todos}
                
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
    
    async def _optimize_with_skill_tool(self, decision: Dict[str, Any], user_input: str, context: Dict[str, Any], project_id: int = None) -> Dict[str, Any]:
        """
        使用Skill工具优化决策
        当检测到复杂任务时，建议使用skill_executor工具
        """
        tool_name = decision['tool']
        
        # 识别需要Skill处理的复杂任务
        complex_task_keywords = [
            '修改缺陷', '创建缺陷', '查询缺陷',
            '修改badcase', '创建badcase', '查询badcase',
            '批量处理', '多步骤操作', '完整流程'
        ]
        
        #检查是否为复杂任务
        is_complex_task = any(keyword in user_input.lower() or keyword in decision.get('reason', '').lower() 
                            for keyword in complex_task_keywords)
        
        if is_complex_task and tool_name in ['grep', 'modify', 'create']:
            print(f"[REACT-STREAM] 🎯检测到复杂任务，建议使用Skill工具优化")
            
            # 重定向到skill_executor工具
            return {
                'execute': True,
                'tool': 'skill_executor',
                'params': {
                    'user_input': user_input,
                    'context': context,
                    'project_id': project_id
                },
                'reason': f'检测到复杂任务"{user_input}"，使用Skill工具进行智能处理'
            }
        
        # Text2SQL优化：数据库查询优先使用自然语言
        if tool_name == 'database_query':
            natural_query = self._extract_natural_query(user_input, user_input)
            if natural_query and self.text2sql_tool:
                print(f"[REACT-STREAM]📊优先使用 Text2SQL执行: {natural_query}")
                decision['params']['natural_query'] = natural_query
        
        return decision
        """传统 THINK - 生成 Todo列表"""
        tools_info = format_tools_for_prompt(self.tools)
        prompt = ReactPromptTemplates.think_prompt(
            user_input,
            tools_info,
            context,
            []
        )
        
        response = await self.llm.parse_intent(prompt)
        todos = parse_xml_todos(response)
        print(f"[REACT-STREAM] 传统模式生成的Todos: {todos}")
        return todos
    
    def _generate_todos_from_skill_workflow(self, skill: Skill, user_input: str) -> List[str]:
        """根据技能工作流生成 Todo列表"""
        todos = []
        for workflow_step in skill.workflow:
            # 生成人性化的 Todo描述
            if workflow_step.description and workflow_step.description != workflow_step.tool:
                todo_desc = workflow_step.description
            else:
                # 使用默认描述
                todo_desc = f"执行 {workflow_step.tool} 操作"
            
            todos.append(todo_desc)
        
        return todos
    
    async def _execute_tool_with_text2sql(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """使用 Text2SQL执行数据库工具"""
        if tool_name == 'database_query' and self.text2sql_tool:
            natural_query = params.get('natural_query')
            if natural_query:
                print(f"[REACT] Text2SQL执行: {natural_query}")
                return self.text2sql_tool.query(natural_query, params)
        
        #回到传统工具执行
        return await self._execute_tool(tool_name, params)
    
    def _extract_natural_query(self, todo: str, user_input: str) -> str:
        """从 Todo中提取自然语言查询"""
        # 关键词匹配
        query_keywords = ['查询', '搜索', '查找', '显示', '列出', '统计']
        
        for keyword in query_keywords:
            if keyword in todo or keyword in user_input:
                #构造自然语言查询
                if '登录' in todo or '登录' in user_input:
                    return "查询登录相关的缺陷"
                elif '未解决' in todo or '未解决' in user_input:
                    return "查询所有未解决的缺陷"
                elif '统计' in todo or '统计' in user_input:
                    return "统计缺陷数量"
                else:
                    return user_input  # 使用原始用户输入
        
        return ""

    def _rerank_score(self, item: Dict, keywords: str, key_title: str = 'title') -> float:
        """
        Rerank 打分：分高的优先。关键词命中数×10 + 整句命中加 50，便于选最相关的一条。
        """
        if not keywords or not keywords.strip():
            return 1.0
        import re
        title = (item.get(key_title) or '').strip()
        text = re.sub(r'[和与]', ' ', keywords.strip())
        parts = [p.strip() for p in text.split() if p.strip()]
        stop = {'的', '为', '与', '和', '或', '及'}
        terms = [p for p in parts if p not in stop and (len(p) > 1 or p not in stop)]
        if not terms:
            return 50.0 if keywords.strip() in title else 0.0
        score = sum(10 for t in terms if t in title)
        if keywords.strip() in title:
            score += 50
        return float(score)

    def _rerank_and_pick(self, items: List[Dict], keywords: str, key_title: str = 'title', top_k: int = 1) -> List[Dict]:
        """
        Rerank 后取分高的：按 _rerank_score 排序，返回 top_k 条（分高的就都可以，默认取 1 条）。
        """
        if not items:
            return []
        if not keywords or not keywords.strip():
            return items[:top_k]
        scored = [(item, self._rerank_score(item, keywords, key_title)) for item in items]
        scored.sort(key=lambda x: -x[1])
        # 同分都算「分高的」：取所有与最高分相同的项，再截 top_k
        if not scored:
            return []
        best_score = scored[0][1]
        top = [item for item, s in scored if s == best_score][:top_k]
        return top if top else [scored[0][0]]

    def _pick_best_match_from_list(self, items: List[Dict], keywords: str, key_title: str = 'title') -> Dict:
        """Rerank 后取分最高的那一条（兼容旧调用）。"""
        picked = self._rerank_and_pick(items, keywords, key_title, top_k=1)
        return picked[0] if picked else {}

    def _extract_title_keywords_for_grep(self, user_input: str, todo: str) -> str:
        """
        从用户输入或 todo 中提取要修改的 BadCase/Bug 标题，用于 grep 的 keywords 参数。
        例如：「修改雪碧和七喜的正确答案为理解正确」 -> 「雪碧和七喜」
        """
        import re
        text = (user_input or '') + ' ' + (todo or '')
        if not text.strip():
            return ''
        # 修改/把/将 XXX 的 … -> XXX（非贪婪，取到第一个「的」为止）
        for pattern in [
            r'修改\s*(.+?)\s*的',
            r'把\s*(.+?)\s*的',
            r'将\s*(.+?)\s*的',
            r'标题[是为]\s*([^，。\n]+)',
        ]:
            m = re.search(pattern, text)
            if m:
                kw = m.group(1).strip()
                if kw and len(kw) <= 50:  # 避免整句当关键词
                    return kw
        return ''

    def _infer_modify_params(self, todo: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        从 Todo 和 Context 中推断 modify工具参数
        当 LLM 返回空响应时作为兜底逻辑
        优先使用技能匹配，回退到标准逻辑
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
        
        #检查是否包含 modify 关键词
        if 'modify' not in todo.lower():
            return result
        
        #先尝匹配技能
        matched_skill, score = skill_integration.match_skill(todo, context)
        
        if matched_skill and score >= 0.3:
            #使用技能工作流参数
            for workflow_step in matched_skill.workflow:
                if workflow_step.tool == 'modify':
                    # 从技能配置中提取参数模板
                    tool_def = next((t for t in matched_skill.tools if t.name == 'modify'), None)
                    if tool_def:
                        params = tool_def.params.copy()
                        # 解析参数变量
                        for key, value in list(params.items()):  # 使用 list 避免迭代时修改
                            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                                var_name = value[2:-1]  #去除${}
                                
                                # 支持嵌套变量：grep_result.first_bug_id
                                resolved_value = None
                                
                                if '.' in var_name:
                                    # 嵌套变量解析
                                    parts = var_name.split('.')
                                    base_var = parts[0]  # grep_result
                                    field_path = parts[1:]  # ['first_bug_id']
                                    
                                    # 从 context 中获取基础变量
                                    base_value = context.get(base_var)
                                    if base_value and isinstance(base_value, dict):
                                        # 递归获取嵌套字段
                                        current = base_value
                                        for field in field_path:
                                            if isinstance(current, dict) and field in current:
                                                current = current[field]
                                            else:
                                                current = None
                                                break
                                        resolved_value = current
                                else:
                                    # 简单变量解析
                                    if var_name == 'user_modifications':
                                        resolved_value = self._extract_modifications_from_todo(todo)
                                    elif var_name == 'target_id':
                                        resolved_value = (context.get('first_bug_id') or context.get('first_badcase_id') or context.get('first_testcase_id'))
                                    elif var_name == 'project_id':
                                        resolved_value = context.get('project_id', '1')
                                    elif var_name in context:
                                        resolved_value = context[var_name]
                                
                                # 更新参数或删除无法解析的变量
                                if resolved_value is not None:
                                    params[key] = resolved_value
                                else:
                                    # 无法解析，删除该参数或跳过
                                    print(f"[REACT-STREAM] ⚠️ 无法解析变量: {var_name}")
                                    # 如果是 target_id，尝试从其他来源获取
                                    if key == 'target_id':
                                        target_id = (context.get('first_bug_id') or 
                                                    context.get('first_badcase_id') or 
                                                    context.get('first_testcase_id') or
                                                    context.get('target_id'))
                                        if target_id:
                                            params[key] = target_id
                                        else:
                                            # 没有有效的 target_id，不执行
                                            print(f"[REACT-STREAM] ❌ 缺少有效的 target_id，跳过执行")
                                            return result
                                    else:
                                        del params[key]  # 删除无法解析的参数
                        
                        # 检查必要参数是否完整
                        if 'target_id' not in params or params.get('target_id') is None:
                            print(f"[REACT-STREAM] ❌ 缺少 target_id，无法执行 modify")
                            return result
                        
                        result = {
                            'execute': True,
                            'tool': 'modify',
                            'params': params,
                            'reason': f'基于匹配技能 {matched_skill.name} 的工作流参数'
                        }
                        return result
        
        # 如果技能匹配失败，回到标准流程（含 testcase）
        bug_list = context.get('bug_list', [])
        badcase_list = context.get('badcase_list', [])
        testcase_list = context.get('testcase_list', [])
        if not bug_list and 'bug_location' in context:
            bug_list = context.get('bug_location', [])
        if not badcase_list and 'badcase_analysis' in context:
            badcase_analysis = context.get('badcase_analysis', [])
            if badcase_analysis and isinstance(badcase_analysis, list):
                badcase_list = badcase_analysis
        if not testcase_list and 'testcase_location' in context:
            testcase_list = context.get('testcase_location', [])
        target_list = bug_list or badcase_list or testcase_list
        target_type = 'bug' if bug_list else ('badcase' if badcase_list else ('testcase' if testcase_list else None))
        
        if not target_list or not isinstance(target_list, list) or len(target_list) == 0:
            print(f"[REACT-STREAM] 无法从 context 中获取有效的 bug_list 或 badcase_list")
            print(f"[REACT-STREAM] context keys: {list(context.keys())}")
            return result
        
        # 获取第一个目标的 ID
        first_item = target_list[0]
        if not isinstance(first_item, dict):
            print(f"[REACT-STREAM] target_list[0] 不是字典: {type(first_item)}")
            return result
        
        target_id = first_item.get('id')
        if target_id is None:
            print(f"[REACT-STREAM] 无法从 target_list 中提取 id")
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
        
        # 状态值标准化（确保使用英文）
        status_normalize = {
            '关闭': 'closed', '已关闭': 'closed', 'close': 'closed',
            '解决': 'resolved', '已解决': 'resolved',
            '重新打开': 'reopened', '重开': 'reopened', 'reopen': 'reopened',
            '新建': 'new', '新': 'new',
            '待处理': 'pending',
            '搁置': 'hold',
        }
        if 'status' in modifications:
            modifications['status'] = status_normalize.get(modifications['status'].lower(), modifications['status'])
        
        # 获取 project_id
        project_id = context.get('project_id') or self.project_id or '1'
        
        result = {
            'execute': True,
            'tool': 'modify',
            'params': {
                'target': target_type or 'badcase',  # 使用推断的目标类型
                'target_id': target_id,
                'modifications': modifications,
                'project_id': project_id,
                'confirm': False  # 默认使用沙箱预览模式，需要用户确认后才执行
            },
            'reason': f'基于 todo内容和 context推断的 modify 参数，target={target_type}, target_id={target_id}'
        }
        
        print(f"[REACT-STREAM] _infer_modify_params 返回: {result}")
        return result
    
    def _resolve_skill_params(self, param_template: Dict[str, Any], context: Dict[str, Any], user_input: str, project_id: int = None) -> Dict[str, Any]:
        """
        解析技能参数模板中的变量
        
        支持：
        - ${user_keywords}: 从用户输入提取关键词
        - ${user_modifications}: 从用户输入提取修改内容
        - ${grep_result.first_badcase_id}: 从上下文获取嵌套值
        - ${project_id}: 项目ID
        """
        import re
        params = {}
        
        for key, value in param_template.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                var_name = value[2:-1]  # 去除 ${}
                
                # 特殊变量处理
                if var_name == 'user_keywords':
                    # 从用户输入提取关键词
                    # 优先匹配“标题为XXX”或“标题是XXX”的模式
                    title_match = re.search(r'标题[是为]([^，。,]+)', user_input)
                    if title_match:
                        keywords = title_match.group(1).strip()
                        print(f"[REACT] 从用户输入提取标题关键词: '{keywords}'")
                    else:
                        # 回退：去除常见动词
                        keywords = re.sub(r'(修改|更新|调整|所有|状态|改成|设为|标题|为|是)', '', user_input).strip()
                    params[key] = keywords if keywords else ''
                
                elif var_name == 'user_modifications':
                    # 从用户输入提取修改内容
                    modifications = self._extract_modifications_from_todo(user_input)
                    params[key] = modifications if modifications else {}
                
                elif var_name == 'project_id':
                    params[key] = project_id or context.get('project_id', '1')
                
                elif '.' in var_name:
                    # 嵌套变量解析：grep_result.first_badcase_id
                    parts = var_name.split('.')
                    base_var = parts[0]
                    field_path = parts[1:]
                    
                    base_value = context.get(base_var)
                    if base_value:
                        current = base_value
                        for field in field_path:
                            if isinstance(current, dict) and field in current:
                                current = current[field]
                            else:
                                current = None
                                break
                        params[key] = current
                    else:
                        params[key] = None
                
                else:
                    # 简单变量
                    params[key] = context.get(var_name)
            
            else:
                # 非变量，直接使用
                params[key] = value
        
        return params
    
    def _extract_modifications_from_todo(self, todo: str) -> Dict[str, Any]:
        """
        从 todo描述中提取修改内容
        """
        import re
        modifications = {}
        
        # 中文状态映射
        status_map = {
            '重新打开': 'reopened', '重开': 'reopened', 'reopen': 'reopened',
            '已关闭': 'closed', '关闭': 'closed', 'close': 'closed',
            '新建': 'new', '新': 'new',
            '待处理': 'pending', '等待': 'pending',
            '已解决': 'resolved', '解决': 'resolved',
            '搁置': 'hold', '暂停': 'hold',
        }
        
        # 状态修改 - 支持中文
        status_value = None
        
        # 检查中文状态关键词
        for cn_status, en_status in status_map.items():
            if cn_status in todo:
                status_value = en_status
                print(f"[REACT] 从 todo 提取状态: '{cn_status}' -> '{en_status}'")
                break
        
        # 正则匹配英文状态
        if not status_value:
            status_match = re.search(r"status.*?['\"](\w+)['\"]|设为(\w+)", todo, re.IGNORECASE)
            if status_match:
                status_value = status_match.group(1) or status_match.group(2)
        
        if status_value:
            modifications['status'] = status_value
        
        # 优先级修改
        priority_match = re.search(r"优先级.*?(\w+)", todo, re.IGNORECASE)
        if priority_match:
            modifications['priority'] = priority_match.group(1)
        
        # 如果没有提取到任何内容，返回空
        if not modifications:
            print(f"[REACT] 无法从 todo 提取修改内容: {todo}")
            return {}
            
        return modifications
    
    async def _extract_modifications_with_llm(self, todo: str, user_input: str = '') -> Dict[str, Any]:
        """
        使用大模型从 todo 中提取修改参数
        
        Args:
            todo: todo 描述文本
            user_input: 原始用户输入（用于更准确识别字段）
            
        Returns:
            modifications: {字段名: 新值}
        """
        import re
        import json
        
        # 构建上下文，包含原始用户输入
        prompt = f"""
原始用户请求：{user_input}
任务步骤描述：{todo}

请根据原始用户请求识别要修改的字段，返回JSON格式。

【重要】字段名映射规则：
- "相似问题"、"具体问题"、"问题" -> 必须映射为 base_problem
- "标题" -> title
- "状态" -> status (值：new/pending/resolved/closed/reopened/hold)
- "优先级" -> priority (值：p1/p2/p3)
- "负责人" -> assignee
- "复现步骤" -> reproduction_steps
- "正确答案" -> correct_answer
- "解决方式" -> solution
- "问题原因" -> problem_reason

示例：
- 用户说"修改相似问题为XXX" -> {{"base_problem": "XXX"}}
- 用户说"状态改为已解决" -> {{"status": "resolved"}}
- 用户说"标题改成测试标题" -> {{"title": "测试标题"}}

请直接返回JSON，不要包含其他内容："""
        
        try:
            response = await self.llm.parse_intent(prompt)
            print(f"[REACT-LLM] 提取修改参数响应: {response}")
            
            # 如果 parse_intent 已经返回字典，直接使用
            if isinstance(response, dict):
                print(f"[REACT-LLM] 提取的修改参数: {response}")
                return response
            
            # 如果是字符串，提取 JSON 部分
            if isinstance(response, str):
                json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
                if json_match:
                    modifications = json.loads(json_match.group())
                    print(f"[REACT-LLM] 提取的修改参数: {modifications}")
                    return modifications
        except Exception as e:
            print(f"[REACT-LLM] 提取修改参数失败: {e}")
        
        return {}
    
    async def _extract_todo_params(self, todo: str, user_input: str) -> Dict[str, Any]:
        """
        从 todo 中提取工具名称和参数
        
        支持的 todo 格式:
        - "使用 grep 工具搜索标题为XXX的BadCase，keywords=XXX，target=badcase"
        - "使用 modify 工具将标题为XXX的BadCase状态修改为resolved"
        """
        import re
        result = {'tool': None, 'params': {}}
        
        # 1. 确定工具类型 - 优先匹配 modify，因为 modify 的 todo 中可能包含"搜索"关键词
        # 例如："使用 modify 工具将搜索到的BadCase状态修改为resolved"
        
        # 先检查是否明确指定了 modify 工具
        if 'modify' in todo.lower() or ('修改' in todo and 'grep' not in todo.lower()):
            result['tool'] = 'modify'
            
            # 使用大模型提取修改参数（更准确）
            modifications = await self._extract_modifications_with_llm(todo, user_input)
            
            # 提取目标类型
            if 'bug' in todo.lower():
                target = 'bug'
            elif 'badcase' in todo.lower():
                target = 'badcase'
            else:
                target = 'badcase'  # 默认
            
            result['params'] = {
                'target': target,
                'modifications': modifications,
                'confirm': False,
            }
            print(f"[REACT] 从 todo 提取 modify 参数: modifications={modifications}, target={target}")
        
        # 再检查 grep 工具
        elif 'grep' in todo.lower() or '搜索' in todo or '查找' in todo or '定位' in todo:
            result['tool'] = 'grep'
            
            # 提取关键词 - 优先匹配 keywords=XXX 格式
            keywords_match = re.search(r'keywords[=：]\s*([^，,]+)', todo, re.IGNORECASE)
            if keywords_match:
                keywords = keywords_match.group(1).strip()
            else:
                # 回退：匹配“标题为XXX”格式
                title_match = re.search(r'标题[是为]([^，。,]+)', todo)
                keywords = title_match.group(1).strip() if title_match else ''
            
            # 提取目标类型
            if 'bug' in todo.lower():
                target = 'bug'
            elif 'badcase' in todo.lower():
                target = 'badcase'
            else:
                target = 'badcase'  # 默认
            
            result['params'] = {
                'target': target,
                'mode': 'locate',
                'keywords': keywords,
            }
            print(f"[REACT] 从 todo 提取 grep 参数: keywords='{keywords}', target={target}")
        
        else:
            # 未知工具，返回空
            print(f"[REACT] 无法从 todo 识别工具: {todo}")
            result['tool'] = 'unknown'
        
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
            # modify 工具内部使用 Flask/SQLAlchemy 同步 DB，会阻塞 asyncio 事件循环，导致流式一直“修改中...”
            # 放到线程池中执行，在独立线程里跑新事件循环，避免阻塞主循环
            if tool_name == 'modify':
                loop = asyncio.get_event_loop()
                def _run_modify_in_thread():
                    thread_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(thread_loop)
                    try:
                        return thread_loop.run_until_complete(tool.execute(**params))
                    finally:
                        thread_loop.close()
                res = await loop.run_in_executor(self._tool_executor, _run_modify_in_thread)
            else:
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
