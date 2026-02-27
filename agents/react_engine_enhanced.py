"""
增强版 ReAct 循环引擎 - 支持 Skill 动态加载
继承原始引擎并添加 Skill 功能
"""

import json
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from .react_engine import ReActEngine, ReActState, ReActStep
from .skill_loader import SkillLoader
from .skill_registry import skill_registry
from .skill import Skill


class EnhancedReActState(ReActState):
    """增强的 ReAct 执行状态，支持 Skill"""
    
    def __init__(self, task: str):
        super().__init__(task)
        self.active_skill: Optional[Skill] = None
        self.skill_matched: bool = False
        self.skill_score: float = 0.0
        self.skill_context: Dict[str, Any] = {}  # Skill 特定上下文
        self.skill_steps_completed: int = 0  # 已完成的 Skill 步骤数
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含 Skill 信息"""
        base_dict = super().to_dict()
        base_dict.update({
            'active_skill': self.active_skill.name if self.active_skill else None,
            'skill_matched': self.skill_matched,
            'skill_score': self.skill_score,
            'skill_context': self.skill_context,
            'skill_steps_completed': self.skill_steps_completed
        })
        return base_dict


class EnhancedReActEngine(ReActEngine):
    """
    增强版 ReAct 循环引擎，支持动态 Skill 加载
    
    新增功能：
    1. Skill 匹配与加载
    2. 基于 Skill 的智能工具调用
    3. Skill 工作流执行跟踪
    4. 上下文感知的参数填充
    """
    
    def __init__(self, llm, tool_registry, max_steps=10, timeout=300, skill_dir=".qoder/skills"):
        """
        初始化增强版 ReAct 引擎
        
        Args:
            llm: 语言模型实例
            tool_registry: 工具注册表
            max_steps: 最大步骤数
            timeout: 超时时间（秒）
            skill_dir: Skill配置文件目录
        """
        super().__init__(llm, tool_registry, max_steps, timeout)
        self.skill_loader = SkillLoader(skill_dir)
        self.skill_registry = skill_registry
        print(f"[ENHANCED_REACT] 💡 增强版引擎已初始化，Skill目录: {skill_dir}")
    
    async def run(self, task: str) -> Dict[str, Any]:
        """
        执行增强版 ReAct 循环
        
        Args:
            task: 用户任务
            
        Returns:
            执行结果（包含Skill相关信息）
        """
        print(f"\n[ENHANCED_REACT] 🚀 开始增强版 ReAct 循环")
        print(f"[ENHANCED_REACT] 📋 任务: {task}")
        
        # 加载所有可用的技能
        skills = self.skill_loader.load_all()
        print(f"[ENHANCED_REACT] 🛠  加载 {len(skills)} 个技能")
        
        # 创建增强版状态
        state = EnhancedReActState(task)
        
        # 1️⃣ Skill匹配阶段：根据任务匹配合适的Skill
        matched_skill, skill_score = self._match_skill_for_task(task, state)
        if matched_skill and skill_score >= 0.3:  # 匹配阈值
            state.active_skill = matched_skill
            state.skill_matched = True
            state.skill_score = skill_score
            state.context['matched_skill'] = matched_skill.name
            state.context['skill_score'] = skill_score
            
            # 注册技能到全局注册中心
            self.skill_registry.register(matched_skill)
            
            print(f"[ENHANCED_REACT] 🎯 匹配到Skill: {matched_skill.name} (分数: {skill_score:.2f})")
            
            # 根据Skill的工作流初始化Todo列表
            if matched_skill.workflow:
                todo_list = self._generate_todo_from_workflow(matched_skill, task)
                state.set_todo_list(todo_list)
                print(f"[ENHANCED_REACT] 📋 生成 {len(todo_list)} 个Todo")
        
        # 执行原始的ReAct循环
        start_time = time.time()
        
        for step_num in range(self.max_steps):
            # 检查超时
            if time.time() - start_time > self.timeout:
                print(f"[ENHANCED_REACT] ⏱ 超时，停止循环")
                state.status = 'timeout'
                break
            
            print(f"[ENHANCED_REACT] ━━━━━━━━━━━━━━━━ 步骤 {step_num + 1}/{self.max_steps} ━━━━━━━━━━━━━━━━")
            
            step = ReActStep()
            
            # 1️⃣ Thought: 使用Skill增强的思考
            try:
                step.thought = await self._think_enhanced(task, state)
                print(f"[ENHANCED_REACT] ?? 思考: {step.thought[:100]}...")
            except Exception as e:
                print(f"[ENHANCED_REACT] ❌ 思考失败: {str(e)}")
                state.status = 'failed'
                break
            
            # 2️⃣ Action: 技能增强的行动规划
            try:
                step.action = await self._plan_action_enhanced(step.thought, state)
                print(f"[ENHANCED_REACT] 🎯 行动: {step.action['tool']} - {step.action.get('reason', '')}")
            except Exception as e:
                print(f"[ENHANCED_REACT] ❌ 规划行动失败: {str(e)}")
                step.action = {'tool': 'stop', 'reason': '规划失败'}
            
            # 3️⃣ Observe: 执行工具
            if step.action['tool'] == 'stop':
                print(f"[ENHANCED_REACT] 🛑 Agent 决定停止")
                state.status = 'success' if state.skill_matched else 'success_manual'
                state.add_step(step)
                break
            
            try:
                step.observation = await self._execute_tool(step.action)
                print(f"[ENHANCED_REACT] 👁 观察: 工具执行成功，获得 {len(str(step.observation))} 字符结果")
            except Exception as e:
                print(f"[ENHANCED_REACT] ❌ 工具执行失败: {str(e)}")
                step.observation = {'error': str(e), 'success': False}
            
            # 4️⃣ 更新状态（增强版更新）
            state.add_step(step)
            await self._update_state_enhanced(state, step)
            
            # 5️⃣ 检查Skill流程是否完成
            if await self._should_stop_enhanced(state):
                print(f"[ENHANCED_REACT] ✅ 任务完成")
                state.status = 'success_skill' if state.skill_matched else 'success'
                break
        
        else:
            # 超过最大步骤
            print(f"[ENHANCED_REACT] ⚠️  达到最大步骤数")
            state.status = 'max_steps'
        
        # 记录技能使用
        if state.active_skill:
            self.skill_registry.increment_usage(state.active_skill.name)
        
        print(f"\n[ENHANCED_REACT] 📊 循环完成")
        print(f"[ENHANCED_REACT] 📈 步骤数: {len(state.steps)}")
        print(f"[ENHANCED_REACT] 🔍 发现数: {len(state.findings)}")
        print(f"[ENHANCED_REACT] 🎯 Skill匹配: {state.skill_matched}")
        if state.active_skill:
            print(f"[ENHANCED_REACT] ⚡ Skill使用: {state.active_skill.name}")
        print(f"[ENHANCED_REACT] ⏱ 耗时: {time.time() - start_time:.2f}s\n")
        
        return state.to_dict()
    
    def _match_skill_for_task(self, task: str, state: EnhancedReActState) -> Tuple[Optional[Skill], float]:
        """
        为任务匹配最合适的Skill
        
        Args:
            task: 用户任务
            state: 执行状态
            
        Returns:
            (匹配的技能, 匹配分数)
        """
        return self.skill_loader.match_skill(task, state.context)
    
    def _generate_todo_from_workflow(self, skill: Skill, task: str) -> List[str]:
        """
        根据Skill工作流生成Todo列表
        
        Args:
            skill: 匹配的Skill
            task: 用户任务
            
        Returns:
            Todo描述列表
        """
        todo_list = []
        
        for workflow_step in skill.workflow:
            # 查找对应的工具定义
            tool_def = None
            for tool in skill.tools:
                if tool.name == workflow_step.tool:
                    tool_def = tool
                    break
            
            if tool_def:
                # 生成人性化的Todo描述
                todo_desc = self._format_todo_description(workflow_step, tool_def, task)
                todo_list.append(todo_desc)
        
        return todo_list
    
    def _format_todo_description(self, workflow_step, tool_def, task: str) -> str:
        """格式化Todo描述"""
        description = workflow_step.description
        
        # 如果描述是通用的，使用更具体的语句
        if description == workflow_step.tool or '/':
            # 根据任务内容优化描述
            if '查询' in task or '搜索' in task or '查找' in task:
                description = f"使用 {workflow_step.tool} 查找相关信息"
            elif '修改' in task or '更新' in task:
                description = f"使用 {workflow_step.tool} 执行修改操作"
            elif '创建' in task or '新建' in task:
                description = f"使用 {workflow_step.tool} 创建新条目"
            else:
                description = f"执行 {workflow_step.tool} 步骤"
        
        return description
    
    async def _think_enhanced(self, task: str, state: EnhancedReActState) -> str:
        """
        增强版思考阶段，结合Skill提示
        
        Args:
            task: 用户任务
            state: 增强版执行状态
            
        Returns:
            思考内容
        """
        # 构建Skill增强的上下文提示
        skill_prompt = ""
        if state.active_skill:
            skill_prompt = self.skill_loader.get_skill_prompt(state.active_skill.name)
        
        # 生成增强版上下文提示
        context_prompt = f"""
当前任务: {task}

{'='*50}
🧠 **技能匹配信息**:
{'='*50}
{skill_prompt if skill_prompt else "⚠️ 未匹配到技能，使用标准流程"}

{'='*50}
📝 **执行上下文**:
{'='*50}
已完成步骤: {len(state.steps)}
当前Todo: {state.get_current_todo() or '无'}

步骤历史:
{self._format_history(state.steps)}

当前上下文:
{json.dumps(state.context, ensure_ascii=False, indent=2)}

关键发现:
{chr(10).join(f"- {f}" for f in state.findings[-5:]) if state.findings else "暂无"}

{'='*50}
🛠 **可用工具**:
{'='*50}
{self.tools.get_tools_prompt()}

请分析:
1. 基于匹配的技能（如果有），下一步应该做什么？
2. 当前Todo是什么？是否需要修改参数？
3. 还需要什么信息来完成下一步？
"""
        
        response = await self.llm.parse_intent(context_prompt)
        
        # 提取思考内容
        if isinstance(response, dict):
            return response.get('thought', str(response))
        return str(response)
    
    async def _plan_action_enhanced(self, thought: str, state: EnhancedReActState) -> Dict[str, Any]:
        """
        增强版行动规划，结合Skill上下文
        
        Args:
            thought: 思考内容
            state: 增强版执行状态
            
        Returns:
            行动规划
        """
        # 如果有活跃的Skill，根据工作流决定下一步
        if state.active_skill and state.active_skill.workflow:
            # 获取当前应该执行的步骤
            current_step_index = state.skill_steps_completed
            if current_step_index < len(state.active_skill.workflow):
                workflow_step = state.active_skill.workflow[current_step_index]
                
                # 查找对应的工具定义
                tool_def = None
                for tool in state.active_skill.tools:
                    if tool.name == workflow_step.tool:
                        tool_def = tool
                        break
                
                if tool_def:
                    # 生成基于Skill的行动
                    return {
                        'tool': workflow_step.tool,
                        'params': self._generate_params_from_skill(tool_def, state),
                        'reason': f"执行Skill '{state.active_skill.name}' 第{current_step_index + 1}步: {workflow_step.description}"
                    }
        
        # 如果没有Skill或Skill未匹配，使用原始规划
        return await super()._plan_action(thought, state)
    
    def _generate_params_from_skill(self, tool_def, state: EnhancedReActState) -> Dict[str, Any]:
        """
        从Skill定义生成参数
        
        Args:
            tool_def: 工具定义
            state: 执行状态
            
        Returns:
            工具参数
        """
        params = {}
        
        # 处理模板参数（如 ${user_input}, ${grep_result}）
        for key, value in tool_def.params.items():
            if isinstance(value, str):
                # 替换模板变量
                if value.startswith('${') and value.endswith('}'):
                    var_name = value[2:-1]
                    
                    # 从状态上下文中获取值
                    if var_name in state.context:
                        params[key] = state.context[var_name]
                    # 从Skill上下文中获取值
                    elif var_name in state.skill_context:
                        params[key] = state.skill_context[var_name]
                    # 特殊变量处理
                    elif var_name == 'user_input':
                        params[key] = state.task
                    elif var_name == 'project_id':
                        # 从上下文或默认值获取
                        params[key] = state.context.get('project_id', 1)
                    else:
                        params[key] = value  # 保持原样
                else:
                    params[key] = value
            else:
                params[key] = value
        
        return params
    
    async def _update_state_enhanced(self, state: EnhancedReActState, step: ReActStep):
        """
        增强版状态更新，处理Skill相关逻辑
        
        Args:
            state: 增强版执行状态
            step: 当前步骤
        """
        # 调用父类的基础更新
        await super()._update_state(state, step)
        
        # Skill特定的更新逻辑
        if state.active_skill and step.observation.get('success'):
            # 更新Skill步骤完成计数
            state.skill_steps_completed += 1
            
            # 从工具结果中提取信息到Skill上下文
            observation_data = step.observation
            
            # 常见的提取模式
            if 'bugs_found' in observation_data and observation_data['bugs_found']:
                state.skill_context['grep_result'] = observation_data['bugs_found']
                state.skill_context['first_bug_id'] = observation_data['bugs_found'][0]['id'] if observation_data['bugs_found'] else None
            
            if 'badcase_analysis' in observation_data:
                state.skill_context['badcase_analysis'] = observation_data['badcase_analysis']
            
            if 'data' in observation_data and isinstance(observation_data['data'], dict):
                for key, value in observation_data['data'].items():
                    state.skill_context[key] = value
            
            # 标记Todo完成
            if state.get_current_todo():
                state.mark_todo_done()
    
    async def _should_stop_enhanced(self, state: EnhancedReActState) -> bool:
        """
        增强版停止条件判断
        
        Args:
            state: 增强版执行状态
            
        Returns:
            是否应该停止
        """
        # 标准停止条件
        if await super()._should_stop(state):
            return True
        
        # Skill流程完成条件
        if state.active_skill:
            # 如果Skill所有步骤都完成了
            if state.skill_steps_completed >= len(state.active_skill.workflow):
                return True
            
            # 如果Todo列表已完成
            if state.is_todo_list_complete():
                return True
        
        return False
    
    def list_available_skills(self) -> List[Dict[str, Any]]:
        """
        列出所有可用技能
        
        Returns:
            技能信息列表
        """
        return self.skill_loader.list_skills()
    
    def get_skill_statistics(self) -> Dict[str, Any]:
        """
        获取技能统计信息
        
        Returns:
            统计信息
        """
        return self.skill_registry.get_skill_statistics()