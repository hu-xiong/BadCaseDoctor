# agents/intelligent_devops_agent.py
"""
综合型 AI 运维 Agent
整合 ReAct 推理 + 多工具编排 + 上下文管理
"""

import asyncio
import time
import os
from typing import Dict, Any
from .react_simplified import SimplifiedReActEngine
from .tool_registry import ToolRegistry
from .tools import BrowserTestTool, DatabaseTool, LogAnalyzerTool, AccuracyTesterTool
from .tools.search_tool import SearchTool
from .tools.login_state_tool import LoginStateTool
from .tools.layered_tool_factory import LayeredToolFactory


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
        self.llm = llm
        self.db = db_session
        
        # 初始化工具注册表
        self.tool_registry = ToolRegistry()
        
        # 初始化 ReAct 引擎（极简设计）- 必须在 _register_tools 之前
        self.react_engine = SimplifiedReActEngine(
            llm=llm,
            tool_registry=self.tool_registry
        )
        
        # 注册工具（在 react_engine 之后，因为 skill_tool 需要 react_engine）
        self._register_tools()
        
        # 记忆系统
        self.memory = ConversationMemory()
    
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
            
        print(f"[AGENT]工具注册完成，共 {len(self.tool_registry)} 个工具")
        print(f"[AGENT]   - 业务工具: 6 (browser_test, database_query, log_analyzer, accuracy_tester, search, grep)")
        print(f"[AGENT]   - 分层工具: {len(layered_tools)}")
        print(f"[AGENT]      - L1 (原子操作): 4 个")
        print(f"[AGENT]      - L2 (复合操作): 2 个") 
        print(f"[AGENT]      - L3 (完整流程): 2 个")
        print(f"[AGENT]   - 🎯 Skill工具: 1 个 (skill_executor)")
    
    async def handle_user_request_stream(self, user_input: str, project_id: int = None, plan_id: int = None):
        """流式处理用户请求。plan_id 为当前迭代计划ID时，grep 会只检索该计划下的记录（人类式先看本迭代）。"""
        print(f"\n[AGENT] User Request (Stream): {user_input}")
        if project_id:
            print(f"[AGENT] Project ID: {project_id}")
        if plan_id is not None:
            print(f"[AGENT] Plan ID (当前迭代): {plan_id}")
        
        # 0. 初始状态推送
        yield {'type': 'status', 'message': '正在分析请求意图...'}
        
        # 1. 分类意图
        intent = await self._classify_intent(user_input)
        yield {'type': 'intent', 'intent': intent}
        
        # 2. 启动 ReAct 循环 (流式) - 传入 project_id、plan_id
        async for step_data in self.react_engine.run_stream(user_input, project_id=project_id, plan_id=plan_id):
            yield {'type': 'step', 'data': step_data}
        
        # 3. 获取最终结果并格式化
        # 这里从 react_engine 的状态中获取最终结果可能更好，但目前 SimplifiedReActEngine 是无状态的
        # 我们让 run_stream 最后 yield 一个 summary
        
    async def handle_user_request(self, user_input: str, project_id: int = None) -> Dict[str, Any]:
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
        result = await self.react_engine.run(user_input, project_id=project_id)
        
        # 3. 后处理结果
        final_output = await self._format_output(result, intent)
        
        # 4. 保存到记忆
        await self.memory.add(user_input, result)
        
        print(f"\n[AGENT] Request Processed\n")
        
        return final_output
    
    async def _classify_intent(self, user_input: str) -> str:
        """
        分类用户意图
        
        使用 LLM 自动识别用户意图
        
        Returns:
            意图代码: run_test / find_bugs / locate_bug / test_accuracy / generate_badcase / diagnose
        """
        prompt = f"""
分析用户请求，归类为以下之一：
1. run_test - 执行自动化测试，获取 Bug 列表
2. find_bugs - 查询数据库中已有的 Bug
3. locate_bug - 根据日志定位问题根因
4. test_accuracy - 测试功能/对话准确率
5. generate_badcase - 生成失败用例列表
6. diagnose - 诊断系统问题

用户请求: {user_input}

直接返回类型代号(1-6):
"""
        
        response = await self.llm.parse_intent(prompt)
        
        # 映射回意图名
        intent_map = {
            '1': 'run_test',
            '2': 'find_bugs',
            '3': 'locate_bug',
            '4': 'test_accuracy',
            '5': 'generate_badcase',
            '6': 'diagnose'
        }
        
        # 提取数字
        for num, intent in intent_map.items():
            if num in str(response):
                return intent
        
        return 'diagnose'  # 默认
    
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
