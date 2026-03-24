# agents/intelligent_devops_agent.py
"""
综合型 AI 运维 Agent
整合 ReAct 推理 + 多工具编排 + 上下文管理
"""

import asyncio
import time
import os
from typing import Any, Dict

from .react_simplified import SimplifiedReActEngine
from .tool_registry import ToolRegistry
from .tools import BrowserTestTool, DatabaseTool, LogAnalyzerTool, AccuracyTesterTool
from .tools.search_tool import SearchTool
from .tools.login_state_tool import LoginStateTool
from .tools.layered_tool_factory import LayeredToolFactory

# ReAct 三阶段（与前端约定）：think=思考 | act=执行 | observe_decide=观察与决策
# stream_channel：该步若开启模型 reasoning，则 reasoning 与 content 两轨分流展示
REACT_PHASE_THINK = "think"
REACT_PHASE_ACT = "act"
REACT_PHASE_OBSERVE_DECIDE = "observe_decide"


def _react_sse_meta(step_data: Dict[str, Any]) -> Dict[str, Any]:
    """为每条 step 事件附加 react_phase / stream_channel，便于前端分类与分样式渲染。"""
    ev = step_data.get("event")
    if not ev:
        return {}
    if ev == "reasoning_timing":
        seg = (step_data.get("segment") or "").lower()
        if seg == "think":
            return {"react_phase": REACT_PHASE_THINK}
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev == "reasoning":
        return {"react_phase": REACT_PHASE_THINK, "stream_channel": "reasoning"}
    if ev == "todos_stream":
        return {"react_phase": REACT_PHASE_THINK, "stream_channel": "content"}
    if ev in ("todos_partial", "todos"):
        return {"react_phase": REACT_PHASE_THINK}
    if ev in ("plan", "plan_update", "plan_init"):
        return {"react_phase": REACT_PHASE_THINK}
    if ev == "skill_matched":
        return {"react_phase": REACT_PHASE_THINK}
    if ev in ("immutable_field_rejection", "intent_clarification"):
        return {"react_phase": REACT_PHASE_THINK}
    if ev == "agent_thought":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "content"}
    if ev == "agent_thought_done":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev == "reasoning_step":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "reasoning"}
    if ev == "thought_content_step":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "content"}
    if ev == "react_ui_stream":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "content"}
    if ev == "llm_text_stream":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "content"}
    if ev == "executing":
        return {"react_phase": REACT_PHASE_ACT}
    if ev == "observation":
        return {"react_phase": REACT_PHASE_ACT}
    if ev in ("exploring", "retry"):
        return {"react_phase": REACT_PHASE_ACT}
    if ev in ("todo_start", "todo_end"):
        return {"react_phase": REACT_PHASE_ACT}
    if ev == "step_status":
        return {"react_phase": REACT_PHASE_ACT}
    if ev == "skip":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev in ("finding", "evidence"):
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev == "summary_stream":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "content"}
    if ev == "summary_stream_reset":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev in ("done", "finished"):
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev == "phase_wait":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    return {}


class ConversationMemory:
    """对话记忆管理"""
    
    def __init__(self, max_history=10):
        self.history = []
        self.max_history = max_history
    
    async def add(self, user_input: str, result: Dict[str, Any]):
        """添加对话记录"""
        self.history.append({
            'user_input': user_input,
            'result': result,
            'timestamp': time.time()
        })
        
        # 保持历史记录大小
        if len(self.history) > self.max_history:
            self.history.pop(0)
    
    def get_context(self, limit: int = 3) -> str:
        """获取上下文"""
        if not self.history:
            return "无"
        
        context = []
        for item in self.history[-limit:]:
            context.append(f"Q: {item['user_input']}")
            findings = item['result'].get('findings', [])
            if findings:
                context.append(f"A: 发现 - {', '.join(findings[:2])}")
        
        return '\n'.join(context)


class IntelligentDevOpsAgent:
    """
    综合型 AI 运维 Agent
    
    功能：
    1. 执行自动化测试 -> 生成 Bug 列表
    2. 分析日志 -> 定位问题根因
    3. 测试准确率 -> 生成 BadCase 列表
    4. 多工具协调 -> 复杂问题诊断
    """
    
    def __init__(self, llm, db_session=None):
        """
        初始化 Agent
        
        Args:
            llm: 语言模型（千帆）
            db_session: 数据库会话
        """
        perf = (os.getenv("PERF_LOG") == "1")
        t0 = time.perf_counter()
        self.llm = llm
        self.db = db_session
        
        # 初始化工具注册表
        self.tool_registry = ToolRegistry()
        
        # 初始化 ReAct 引擎（极简设计）- 必须在 _register_tools 之前
        t_engine0 = time.perf_counter()
        self.react_engine = SimplifiedReActEngine(
            llm=llm,
            tool_registry=self.tool_registry
        )
        if perf:
            print(f"[PERF][agent] react_engine_init_ms={(time.perf_counter()-t_engine0)*1000:.1f}")
        
        # 注册工具（在 react_engine 之后，因为 skill_tool 需要 react_engine）
        t_reg0 = time.perf_counter()
        self._register_tools()
        if perf:
            print(f"[PERF][agent] register_tools_ms={(time.perf_counter()-t_reg0)*1000:.1f} tools={len(self.tool_registry)}")
        
        # 记忆系统
        self.memory = ConversationMemory()
        if perf:
            print(f"[PERF][agent] agent_init_total_ms={(time.perf_counter()-t0)*1000:.1f}")
    
    def _register_tools(self):
        """注册所有工具 - 包含分层工具和Skill工具"""
        # 注册业务工具（BrowserTestTool 依赖 playwright，可能未安装）
        if BrowserTestTool is not None:
            self.tool_registry.register(BrowserTestTool(self.llm))
        execution_mode = (os.getenv("TEXT2SQL_EXECUTION_MODE", "direct") or "direct").strip().lower()
        self.tool_registry.register(DatabaseTool(self.llm, self.db, execution_mode=execution_mode))
        self.tool_registry.register(LogAnalyzerTool(self.llm))
        self.tool_registry.register(AccuracyTesterTool(self.llm))
        self.tool_registry.register(SearchTool(self.llm))
        self.tool_registry.register(LoginStateTool())  # 登录状态管理工具
            
        # 注册grep工具
        from agents.tools.grep_tool import GrepTool
        self.tool_registry.register(GrepTool())
            
        # 注册modify工具
        from agents.tools.modify_tool import ModifyTool
        self.tool_registry.register(ModifyTool(self.db))
            
        # 注册create工具
        from agents.tools.create_tool import CreateTool
        self.tool_registry.register(CreateTool(self.db))
            
        # 注册分层工具（L1/L2/L3）
        layered_tools = LayeredToolFactory.create_all_tools()
        for tool_name, tool in layered_tools.items():
            self.tool_registry.register(tool)
            
        #🎯 注册Skill工具
        from agents.tools.skill_tool import SkillExecutorTool
        skill_tool = SkillExecutorTool(
            skill_loader=self.react_engine.skill_loader,
            skill_registry=self.react_engine.skill_registry,
            tool_registry=self.tool_registry  #传递工具注册表引用
        )
        self.tool_registry.register(skill_tool)
            
        if os.getenv("QUIET_LOG") != "1":
            print(f"[AGENT]工具注册完成，共 {len(self.tool_registry)} 个工具")
            print(f"[AGENT]   - 业务工具: 6 (browser_test, database_query, log_analyzer, accuracy_tester, search, grep)")
            print(f"[AGENT]   - 分层工具: {len(layered_tools)}")
            print(f"[AGENT]      - L1 (原子操作): 4 个")
            print(f"[AGENT]      - L2 (复合操作): 2 个") 
            print(f"[AGENT]      - L3 (完整流程): 2 个")
            print(f"[AGENT]   - 🎯 Skill工具: 1 个 (skill_executor)")

    def set_db_session(self, db_session):
        """允许复用 Agent 实例时更新 db session 引用。"""
        self.db = db_session
        try:
            for tool_name in ("database_query", "modify", "create"):
                tool = self.tool_registry.get(tool_name)
                if tool is not None and hasattr(tool, "db"):
                    setattr(tool, "db", db_session)
        except Exception:
            pass
    
    async def handle_user_request_stream(
        self,
        user_input: str,
        project_id: int = None,
        plan_id: int = None,
        locale: str = None,
        pending_diff_context: list = None,
    ):
        """流式处理用户请求。plan_id 为当前迭代计划ID时，grep 会只检索该计划下的记录（人类式先看本迭代）。"""
        _llm = self.llm
        print(
            f"[AGENT-LLM] 本请求绑定 LLM: class={type(_llm).__name__} "
            f"model_attr={getattr(_llm, 'model', None)!r} instance_id={id(_llm)}"
        )
        print(f"\n[AGENT] User Request (Stream): {user_input}")
        if project_id:
            print(f"[AGENT] Project ID: {project_id}")
        if plan_id is not None:
            print(f"[AGENT] Plan ID (当前迭代): {plan_id}")
        
        # 0. 初始状态推送：仅用于触发前端显示「...」思考中，无需具体文案
        yield {'type': 'status', 'message': '...'}

        # 不推假的 reasoning 占位：深度思考区块仅在有实质思考内容时由前端展示（见 SimpleChatPanel substantiveReasoning）。

        # 1. 分类意图（不阻塞首屏；前端也不会展示 intent）
        intent_task = asyncio.create_task(self._classify_intent(user_input))
        
        # 2. 启动 ReAct 循环 (流式) - 传入 project_id、plan_id
        async for _raw in self.react_engine.run_stream(
            user_input,
            project_id=project_id,
            plan_id=plan_id,
            locale=locale,
            pending_diff_context=pending_diff_context,
        ):
            step_data = _raw
            if isinstance(step_data, dict):
                _meta = _react_sse_meta(step_data)
                if _meta:
                    step_data = {**step_data, **_meta}
                ev = step_data.get('event')
                # 顶层 SSE：与 step 内事件同源；附带 react_phase / stream_channel 供分类订阅
                if ev == 'plan':
                    _pl = {
                        'type': 'plan',
                        'steps': step_data.get('steps') or [],
                        'react_phase': step_data.get('react_phase'),
                    }
                    if step_data.get('overview_only') is not None:
                        _pl['overview_only'] = bool(step_data.get('overview_only'))
                    yield _pl
                elif ev == 'plan_init':
                    yield {
                        'type': 'plan_init',
                        'mode': step_data.get('mode'),
                        'steps': step_data.get('steps') or [],
                        'react_phase': step_data.get('react_phase'),
                    }
                elif ev == 'plan_update':
                    yield {
                        'type': 'plan_update',
                        'steps': step_data.get('steps') or [],
                        'reason': step_data.get('reason') or '',
                        'react_phase': step_data.get('react_phase'),
                    }
                elif ev == 'reasoning':
                    yield {
                        'type': 'thinking',
                        'content': step_data.get('content') or '',
                        'step_id': None,
                        'react_phase': step_data.get('react_phase'),
                        'stream_channel': step_data.get('stream_channel'),
                    }
                elif ev == 'reasoning_step':
                    _idx = step_data.get('index')
                    yield {
                        'type': 'thinking',
                        'content': step_data.get('content') or '',
                        'step_id': int(_idx) + 1 if _idx is not None else None,
                        'segment': step_data.get('segment'),
                        'react_phase': step_data.get('react_phase'),
                        'stream_channel': step_data.get('stream_channel'),
                    }
                elif ev == 'executing':
                    _idx = step_data.get('index')
                    yield {
                        'type': 'action_start',
                        'action': step_data.get('tool') or step_data.get('action'),
                        'params': step_data.get('params'),
                        'step_id': int(_idx) + 1 if _idx is not None else None,
                        'index': _idx,
                        'message': step_data.get('message'),
                        'reason': step_data.get('reason'),
                        'react_phase': step_data.get('react_phase'),
                    }
                elif ev == 'observation':
                    _idx = step_data.get('index')
                    _sid = step_data.get('step_id')
                    yield {
                        'type': 'action_result',
                        'result': step_data.get('data'),
                        'summary_nl': step_data.get('summary_nl'),
                        'tool': step_data.get('tool'),
                        'step_id': _sid if _sid is not None else (int(_idx) + 1 if _idx is not None else None),
                        'index': _idx,
                        'react_phase': step_data.get('react_phase'),
                    }
                elif ev == 'step_status':
                    _idx = step_data.get('index')
                    yield {
                        'type': 'step_status',
                        'status': step_data.get('status'),
                        'step_id': step_data.get('step_id'),
                        'index': _idx,
                        'react_phase': step_data.get('react_phase'),
                    }
                elif ev == 'finished':
                    yield {
                        'type': 'finished',
                        'mode': step_data.get('mode'),
                        'finished': step_data.get('finished'),
                        'steps_count': step_data.get('steps_count'),
                        'duration': step_data.get('duration'),
                        'thinking_time': step_data.get('thinking_time'),
                        'observations': step_data.get('observations'),
                        'plan_snapshot': step_data.get('plan_snapshot'),
                        'react_phase': step_data.get('react_phase'),
                    }
                elif ev == 'phase_wait':
                    yield {
                        'type': 'phase_wait',
                        'kind': step_data.get('kind'),
                        'active': step_data.get('active'),
                        'index': step_data.get('index'),
                        'message': step_data.get('message') or '',
                        'react_phase': step_data.get('react_phase'),
                    }
            yield {'type': 'step', 'data': step_data}

        # 结束前再补发 intent（如已完成）；避免阻塞主流程
        try:
            if intent_task.done():
                intent = intent_task.result()
                yield {'type': 'intent', 'intent': intent}
        except Exception:
            pass
        
        # 3. 获取最终结果并格式化
        # 这里从 react_engine 的状态中获取最终结果可能更好，但目前 SimplifiedReActEngine 是无状态的
        # 我们让 run_stream 最后 yield 一个 summary
        
    async def handle_user_request(
        self, user_input: str, project_id: int = None, locale: str = None
    ) -> Dict[str, Any]:
        """
        处理用户请求
        
        Args:
            user_input: 用户输入
            project_id: 项目ID，用于获取登录配置
            
        Returns:
            执行结果
        """
        print(f"\n[AGENT] User Request: {user_input}")
        if project_id:
            print(f"[AGENT] Project ID: {project_id}")
        
        # 1. 分类意图
        intent = await self._classify_intent(user_input)
        print(f"[AGENT] Intent Classification: {intent}")
        
        # 2. 启动 ReAct 循环 - 传入 project_id
        result = await self.react_engine.run(user_input, project_id=project_id, locale=locale)
        
        # 3. 后处理结果
        final_output = await self._format_output(result, intent)
        
        # 4. 保存到记忆
        await self.memory.add(user_input, result)
        
        print(f"\n[AGENT] Request Processed\n")
        
        return final_output
    
    async def _classify_intent(self, user_input: str) -> str:
        """
        分类用户意图
        
        使用 LLM 自动识别用户意图；对「修改/编辑」类请求做关键词兜底，避免千问等误判为 find_bugs/run_test。
        
        Returns:
            意图代码: run_test / find_bugs / locate_bug / test_accuracy / generate_badcase / diagnose
        """
        # 关键词兜底：明确出现修改/编辑/更新或具体字段修改时直接判为 diagnose，不依赖模型（千问/GLM 易误判）
        modify_keywords = ('修改', '编辑', '改为', '改成', '更新', '把', '的答案', '复现步骤', '标题', '期望结果', '预期结果')
        text = (user_input or '').strip()
        if any(kw in text for kw in modify_keywords):
            return 'diagnose'

        prompt = f"""
分析用户请求，归类为以下之一（只返回一个代号或英文名）：
1. run_test - 执行自动化测试，获取 Bug 列表
2. find_bugs - 查询数据库中已有的 Bug（仅查询、列出，不修改）
3. locate_bug - 根据日志定位问题根因
4. test_accuracy - 测试功能/对话准确率
5. generate_badcase - 生成失败用例列表
6. diagnose - 修改/编辑数据：改 BadCase/Bug/测试用例 的答案、复现步骤、标题等，或定位并编辑某条记录

用户请求: {user_input}

只返回一个：数字 6 表示修改或编辑数据，数字 1-5 表示其他。或直接返回英文：diagnose / run_test / find_bugs 等。
"""
        
        response = await self.llm.parse_intent(prompt)
        raw = str(response).strip().lower()
        
        # 先按英文意图名匹配（兼容模型直接返回 diagnose、run_test 等）
        intent_names = ['run_test', 'find_bugs', 'locate_bug', 'test_accuracy', 'generate_badcase', 'diagnose']
        for name in intent_names:
            if name in raw:
                return name
        
        # 再按数字代号匹配
        intent_map = {
            '1': 'run_test',
            '2': 'find_bugs',
            '3': 'locate_bug',
            '4': 'test_accuracy',
            '5': 'generate_badcase',
            '6': 'diagnose'
        }
        for num, intent in intent_map.items():
            if num in raw:
                return intent
        
        return 'diagnose'  # 默认：拿不准时走 diagnose
    
    async def _format_output(self, result: Dict[str, Any], intent: str) -> Dict[str, Any]:
        """
        格式化输出
        
        根据意图类型组织结果
        """
        formatted = {
            'intent': intent,
            'status': result['status'],
            'findings': result['findings'],
            'context': await self._get_execution_context(result),
            'recommendations': []
        }
        
        # 根据意图类型提供建议
        if intent == 'run_test':
            bugs_count = len(result['context'].get('bugs', []))
            formatted['recommendations'] = [
                f"已生成 {bugs_count} 个 Bug",
                "建议优先处理 high 和 critical 级别的 Bug",
                "点击『保存 Bug』按钮可将其导入数据库"
            ]
        
        elif intent == 'test_accuracy':
            accuracy = result['context'].get('accuracy', 0)
            formatted['recommendations'] = [
                f"准确率: {accuracy:.2%}",
                f"已识别 {len(result['context'].get('badcases', []))} 个 BadCase",
                "建议分析失败用例，优化对应功能"
            ]
        
        elif intent == 'locate_bug':
            root_cause = result['context'].get('root_cause', '')
            formatted['recommendations'] = [
                f"根因分析: {root_cause}",
                "建议立即修复或上报",
                "已提取相关日志片段供参考"
            ]
        
        return formatted
    
    async def _get_execution_context(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """获取执行上下文 - 兼容ReAct新格式"""
        return {
            'step_count': len(result.get('steps', [])),
            'duration': result.get('duration', 0),
            'previous_context': self.memory.get_context(limit=2)
        }
