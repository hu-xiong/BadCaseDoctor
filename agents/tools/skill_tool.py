# agents/tools/skill_tool.py
"""
Skill智能工具 -将Skill作为综合工具集成到ReAct循环中
设计理念：Skill本身就是一个完整的智能工具，内部处理匹配、规划、执行全流程
"""

from typing import Dict, Any, List
# 使用正确的导入路径
from agents.tool_registry import BaseTool


class SkillExecutorTool(BaseTool):
    """Skill综合执行工具 - 一体化处理技能匹配和执行"""
    
    def __init__(self, skill_loader, skill_registry, tool_registry):
        self.name = "skill_executor"
        self.description = "智能执行预定义的技能工作流，自动匹配最合适的技能并完成完整任务"
        self.skill_loader = skill_loader
        self.skill_registry = skill_registry
        self.tool_registry = tool_registry  #工具注册表引用
    
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        一体化执行Skill：匹配 +规 + 执行
        
        Args:
            params: {
                'user_input': str,      # 用户原始输入
                'context': Dict,        # 当前执行上下文
                'project_id': int,      #可选：项目ID
                'skill_name': str       # 可选：指定技能名称（绕过自动匹配）
            }
        """
        user_input = params.get('user_input', '')
        context = params.get('context', {})
        project_id = params.get('project_id')
        specified_skill = params.get('skill_name')
        
        print(f"[SKILL_EXECUTOR]🚀启动技能执行流程")
        print(f"[SKILL_EXECUTOR]📝用户输入: {user_input}")
        
        try:
            # 1️⃣技能匹配
            matched_skill, skill_score = await self._match_skill(user_input, context, specified_skill)
            if not matched_skill:
                return {
                    'success': False,
                    'message': '未找到匹配的技能',
                    'matched': False
                }
            
            print(f"[SKILL_EXECUTOR] 🎯匹配到技能: {matched_skill.name} (置信度: {skill_score:.2f})")
            
            # 2️⃣ 注册技能到全局注册中心
            self.skill_registry.register(matched_skill)
            
            # 3️⃣ 自动生成执行计划（Todo列表）
            todo_list = self._generate_todo_list(matched_skill, user_input)
            print(f"[SKILL_EXECUTOR] 📋生成执行计划: {len(todo_list)} 个步骤")
            
            # 4️⃣执行完整工作流
            execution_result = await self._execute_workflow(
                matched_skill, todo_list, context, project_id
            )
            
            return {
                'success': True,
                'message': f'技能 [{matched_skill.name}]执行完成',
                'skill_name': matched_skill.name,
                'skill_score': skill_score,
                'todo_list': todo_list,
                'execution_result': execution_result,
                'steps_completed': len(execution_result.get('successful_steps', [])),
                'total_steps': len(todo_list)
            }
            
        except Exception as e:
            print(f"[SKILL_EXECUTOR]❌执行失败: {str(e)}")
            return {
                'success': False,
                'message': f'技能执行异常: {str(e)}',
                'error': str(e)
            }
    
    async def _match_skill(self, user_input: str, context: Dict[str, Any], specified_skill: str = None):
        """智能技能匹配"""
        if specified_skill:
            # 使用指定技能
            skill = self.skill_registry.get(specified_skill)
            return skill, 1.0 if skill else None, 0.0
        else:
            # 自动匹配
            return self.skill_loader.match_skill(user_input, context)
    
    def _generate_todo_list(self, skill, user_input: str) -> List[str]:
        """根据技能工作流生成人性化的Todo列表"""
        todos = []
        for step in skill.workflow:
            if step.description and step.description != step.tool:
                # 使用自定义描述
                todo_desc = step.description
            else:
                # 生成默认描述
                todo_desc = f"执行 {step.tool}操作"
            todos.append(todo_desc)
        return todos
    
    async def _execute_workflow(self, skill, todo_list: List[str], context: Dict[str, Any], project_id: int = None):
        """执行技能工作流"""
        results = {
            'steps': [],
            'successful_steps': [],
            'failed_steps': [],
            'final_context': context.copy(),
            'observations': []
        }
        
        #按工作流步骤顺序执行
        for i, (step, todo_desc) in enumerate(zip(skill.workflow, todo_list)):
            print(f"[SKILL_EXECUTOR]🔧执行步骤 {i+1}/{len(todo_list)}: {todo_desc}")
            
            step_result = await self._execute_single_step(
                step, todo_desc, context, project_id
            )
            
            results['steps'].append(step_result)
            
            if step_result['success']:
                results['successful_steps'].append(step_result)
                # 更新上下文
                if 'data' in step_result['observation']:
                    results['final_context'].update(step_result['observation']['data'])
            else:
                results['failed_steps'].append(step_result)
                #检查是否需要中断
                if step.break_on_failure:
                    print(f"[SKILL_EXECUTOR]⚠️步失败且设置为中断执行")
                    break
        
        return results
    
    async def _execute_single_step(self, step, todo_desc: str, context: Dict[str, Any], project_id: int = None):
        """执行单个工作流步骤"""
        try:
            #准工具参数
            tool_params = step.params.copy() if step.params else {}
            
            # 添加必要参数
            if project_id:
                tool_params['project_id'] = str(project_id)
            
            #执行工具
            tool = self.tool_registry.get(step.tool)
            if not tool:
                raise ValueError(f"工具未找到: {step.tool}")
            
            observation = await tool.execute(tool_params)
            
            return {
                'step_index': step.index,
                'tool_name': step.tool,
                'description': todo_desc,
                'parameters': tool_params,
                'observation': observation,
                'success': observation.get('success', False)
            }
            
        except Exception as e:
            return {
                'step_index': step.index,
                'tool_name': step.tool,
                'description': todo_desc,
                'error': str(e),
                'success': False
            }


#工具定义
SKILL_EXECUTOR_TOOL_DEF = {
    "name": "skill_executor",
    "description": "智能技能执行工具，自动匹配最合适的预定义技能并执行完整工作流",
    "parameters": {
        "type": "object",
        "properties": {
            "user_input": {
                "type": "string",
                "description": "用户的原始输入内容"
            },
            "context": {
                "type": "object",
                "description": "当前对话上下文，用于技能匹配和参数填充"
            },
            "project_id": {
                "type": "integer",
                "description": "可选：项目ID，用于限定操作范围"
            },
            "skill_name": {
                "type": "string",
                "description": "可选：指定技能名称，绕过自动匹配"
            }
        },
        "required": ["user_input"]
    }
}