# agents/react_engine.py
"""
ReAct 循环引擎 - 结合 Claude Code 极简设计
https://minusx.ai/blog/decoding-claude-code/

核心原则（Claude Code 启发）：
1. 单主循环 - 严格的 Think→Act→Observe 三步
2. 最多 1 个分支 - 简化决策流，避免条件爆炸
3. Agent 自管理 Todo - 替代复杂任务拆分，保持可控
4. 极简状态机 - 只有 running/success/error 三态

优势：
- 调试清晰：每步输出都是确定的
- 可控性强：Agent 主动管理任务，不会跑偏
- 错误恢复：单层循环易实现重试机制
- 可解释性：推理链完全透明
"""

import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field


class ReActStep:
    """单个 ReAct 步骤"""
    
    def __init__(self):
        self.thought: str = ""  # 思考过程
        self.action: Dict[str, Any] = {}  # 选择的工具和参数
        self.observation: Dict[str, Any] = {}  # 工具执行结果
        self.timestamp: float = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'thought': self.thought,
            'action': self.action,
            'observation': self.observation,
            'timestamp': self.timestamp
        }


class ReActState:
    """ReAct 执行状态 - 极简状态机"""
    
    def __init__(self, task: str):
        self.task = task
        self.steps: List[ReActStep] = []  # 推理链
        self.todo_list: List[str] = []   # Agent 自管理的 Todo 列表
        self.current_todo_index = 0
        self.context: Dict[str, Any] = {}  # 累积上下文
        self.findings: List[str] = []  # 关键发现
        self.status = 'running'  # running / success / error
        self.error_message = ''
        self.start_time = time.time()
    
    def add_step(self, step: ReActStep):
        """添加推理步骤"""
        self.steps.append(step)
    
    def set_todo_list(self, todos: List[str]):
        """设置 Todo 列表（Agent 自管理）"""
        self.todo_list = todos
        self.current_todo_index = 0
        print(f"[STATE] 📋 Todo 列表已更新，共 {len(todos)} 项")
        for i, todo in enumerate(todos):
            print(f"[STATE]   {i+1}. {todo}")
    
    def get_current_todo(self) -> Optional[str]:
        """获取当前 Todo"""
        if self.current_todo_index < len(self.todo_list):
            return self.todo_list[self.current_todo_index]
        return None
    
    def mark_todo_done(self):
        """标记当前 Todo 完成"""
        if self.current_todo_index < len(self.todo_list):
            todo = self.todo_list[self.current_todo_index]
            print(f"[STATE] ✅ Todo 完成: {todo}")
            self.current_todo_index += 1
    
    def is_todo_list_complete(self) -> bool:
        """检查 Todo 列表是否完成"""
        return self.current_todo_index >= len(self.todo_list)
    
    def update_context(self, key: str, value: Any):
        """更新上下文"""
        self.context[key] = value
    
    def add_finding(self, finding: str):
        """记录发现"""
        self.findings.append(finding)
        print(f"[FINDING] 🔍 {finding}")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'task': self.task,
            'status': self.status,
            'error': self.error_message,
            'steps': [step.to_dict() for step in self.steps],
            'context': self.context,
            'findings': self.findings,
            'duration': time.time() - self.start_time,
            'step_count': len(self.steps),
            'todo_completion': f"{self.current_todo_index}/{len(self.todo_list)}"
        }


class ReActEngine:
    """
    ReAct 循环引擎
    
    参考 Claude 的设计：
    - Thought: LLM 进行推理
    - Action: 调用工具
    - Observation: 获得结果
    - 循环直到完成
    """
    
    def __init__(self, llm, tool_registry, max_steps=10, timeout=300):
        """
        初始化 ReAct 引擎
        
        Args:
            llm: 语言模型实例（千帆）
            tool_registry: 工具注册表
            max_steps: 最大步骤数
            timeout: 超时时间（秒）
        """
        self.llm = llm
        self.tools = tool_registry
        self.max_steps = max_steps
        self.timeout = timeout
    
    async def run(self, task: str) -> Dict[str, Any]:
        """
        执行 ReAct 循环
        
        Args:
            task: 用户任务
            
        Returns:
            执行结果
        """
        print(f"\n[REACT] 🚀 开始 ReAct 循环")
        print(f"[REACT] 📋 任务: {task}")
        print(f"[REACT] 🛠 可用工具: {self.tools.list_tools()}\n")
        
        state = ReActState(task)
        start_time = time.time()
        
        for step_num in range(self.max_steps):
            # 检查超时
            if time.time() - start_time > self.timeout:
                print(f"[REACT] ⏱ 超时，停止循环")
                state.status = 'timeout'
                break
            
            print(f"[REACT] ━━━━━━━━━━━━━━━━ 步骤 {step_num + 1}/{self.max_steps} ━━━━━━━━━━━━━━━━")
            
            step = ReActStep()
            
            # 1️⃣ Thought: LLM 思考下一步
            try:
                step.thought = await self._think(task, state)
                print(f"[REACT] 💭 思考: {step.thought[:100]}...")
            except Exception as e:
                print(f"[REACT] ❌ 思考失败: {str(e)}")
                state.status = 'failed'
                break
            
            # 2️⃣ Action: 规划行动
            try:
                step.action = await self._plan_action(step.thought, state)
                print(f"[REACT] 🎯 行动: {step.action['tool']} - {step.action.get('reason', '')}")
            except Exception as e:
                print(f"[REACT] ❌ 规划行动失败: {str(e)}")
                step.action = {'tool': 'stop', 'reason': '规划失败'}
            
            # 3️⃣ Observe: 执行工具获得观察结果
            if step.action['tool'] == 'stop':
                print(f"[REACT] 🛑 Agent 决定停止")
                state.status = 'success'
                state.add_step(step)
                break
            
            try:
                step.observation = await self._execute_tool(step.action)
                print(f"[REACT] 👁 观察: 工具执行成功，获得 {len(str(step.observation))} 字符结果")
            except Exception as e:
                print(f"[REACT] ❌ 工具执行失败: {str(e)}")
                step.observation = {'error': str(e), 'success': False}
            
            # 4️⃣ 更新状态
            state.add_step(step)
            await self._update_state(state, step)
            
            # 5️⃣ 检查是否完成
            if await self._should_stop(state):
                print(f"[REACT] ✅ 任务完成")
                state.status = 'success'
                break
        else:
            # 超过最大步骤
            print(f"[REACT] ⚠️  达到最大步骤数")
            state.status = 'max_steps'
        
        print(f"\n[REACT] 📊 循环完成")
        print(f"[REACT] 📈 步骤数: {len(state.steps)}")
        print(f"[REACT] 🔍 发现数: {len(state.findings)}")
        print(f"[REACT] ⏱ 耗时: {time.time() - start_time:.2f}s\n")
        
        return state.to_dict()
    
    async def _think(self, task: str, state: ReActState) -> str:
        """
        🧠 思考阶段
        
        LLM 分析当前状态，决定下一步行动
        """
        # 构建上下文提示
        context_prompt = f"""
当前任务: {task}

已完成步骤: {len(state.steps)}
步骤历史:
{self._format_history(state.steps)}

当前上下文:
{json.dumps(state.context, ensure_ascii=False, indent=2)}

关键发现:
{chr(10).join(f"- {f}" for f in state.findings[-5:]) if state.findings else "暂无"}

{self.tools.get_tools_prompt()}

请分析:
1. 目前了解到什么
2. 还需要什么信息
3. 下一步应该做什么（选择上述工具之一或 stop）
"""
        
        response = await self.llm.parse_intent(context_prompt)
        
        # 提取思考内容
        if isinstance(response, dict):
            return response.get('thought', str(response))
        return str(response)
    
    async def _plan_action(self, thought: str, state: ReActState) -> Dict[str, Any]:
        """
        📋 规划行动
        
        根据思考结果，选择工具和参数
        """
        action_prompt = f"""
基于以下思考: {thought}

请返回 JSON 格式的行动（仅返回JSON，不要其他文本）:
{{
    "tool": "工具名（从可用列表中选择）或 'stop' 表示任务完成",
    "params": {{
        "参数名": "参数值"
    }},
    "reason": "选择此工具的原因"
}}

{self.tools.get_tools_prompt()}

例如，查询已关闭的BadCase:
{{
    "tool": "grep",
    "params": {{"project_id": 1, "target": "badcase", "status": "已关闭"}},
    "reason": "查询状态为已关闭的BadCase"
}}

例如，修改BadCase状态:
{{
    "tool": "modify",
    "params": {{"target": "badcase", "target_id": 1, "modifications": {{"status": "已关闭"}}}},
    "reason": "修改BadCase状态"
}}
"""
        
        response = await self.llm.parse_intent(action_prompt)
        
        # 解析 JSON
        if isinstance(response, str):
            try:
                # 尝试找到 JSON 块
                start = response.find('{')
                end = response.rfind('}') + 1
                if start != -1 and end > start:
                    action = json.loads(response[start:end])
                else:
                    action = json.loads(response)
            except json.JSONDecodeError:
                # 降级处理
                action = {
                    'tool': 'stop',
                    'params': {},
                    'reason': '无法解析行动'
                }
        else:
            action = response if isinstance(response, dict) else {}
        
        # 验证工具存在
        if action.get('tool') and action['tool'] != 'stop':
            if not self.tools.has_tool(action['tool']):
                print(f"[REACT] ⚠️  工具 {action['tool']} 不存在，改为 stop")
                action['tool'] = 'stop'
                action['reason'] = '工具不存在'
        
        return action
    
    async def _execute_tool(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔧 执行工具
        
        调用选定的工具
        """
        tool_name = action.get('tool')
        params = action.get('params', {})
        
        if tool_name == 'stop':
            return {'status': 'stopped', 'reason': action.get('reason', '')}
        
        tool = self.tools.get(tool_name)
        if not tool:
            return {'error': f'工具 {tool_name} 不存在', 'success': False}
        
        try:
            result = await tool.execute(**params)
            if result is None:
                result = {'error': '工具未返回任何结果', 'success': False}
            else:
                result['success'] = True
            return result
        except Exception as e:
            return {
                'error': str(e),
                'success': False,
                'tool': tool_name
            }
    
    async def _update_state(self, state: ReActState, step: ReActStep):
        """
        更新执行状态
        
        从工具结果中提取关键信息
        """
        if step.observation.get('success'):
            # 提取关键发现
            if 'bugs_found' in step.observation:
                count = len(step.observation['bugs_found'])
                state.add_finding(f"发现 {count} 个 Bug")
            
            if 'accuracy' in step.observation:
                acc = step.observation['accuracy']
                state.add_finding(f"准确率: {acc:.2%}")
            
            if 'root_cause' in step.observation:
                state.add_finding(f"根因: {step.observation['root_cause']}")
            
            # 更新上下文
            for key in ['test_result', 'bugs', 'accuracy', 'diagnosis']:
                if key in step.observation:
                    state.update_context(key, step.observation[key])
    
    async def _should_stop(self, state: ReActState) -> bool:
        """
        判断是否应该停止
        
        检查最后一步的行动是否为 stop
        """
        if not state.steps:
            return False
        
        last_action = state.steps[-1].action.get('tool')
        return last_action == 'stop'
    
    def _format_history(self, steps: List[ReActStep]) -> str:
        """格式化历史记录"""
        if not steps:
            return "无"
        
        history = []
        for i, step in enumerate(steps[-3:], 1):  # 只显示最后3步
            history.append(f"  步骤 {i}: {step.thought[:50]}...")
        
        return '\n'.join(history)
