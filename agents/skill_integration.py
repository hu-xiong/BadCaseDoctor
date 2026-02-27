"""
Skill 集成模块 - 提供统一的Skill功能调用
简化Skill在现有Agent架构中的集成
"""

import os
import sys
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime

# 确保Python可以找到技能模块
current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from .skill_loader import SkillLoader
from .skill_registry import skill_registry
from .skill import Skill


class SkillIntegration:
    """
    Skill 集成管理器
    提供统一的Skill功能接口
    """
    
    def __init__(self, skill_dir: str = ".qoder/skills"):
        """
        初始化Skill集成管理器
        
        Args:
            skill_dir: Skill配置文件目录
        """
        self.skill_loader = SkillLoader(skill_dir)
        self.load_all_skills()
        print(f"[SKILL_INTEGRATION] 🚀 技能集成管理器已初始化")
        print(f"[SKILL_INTEGRATION] 📊 共加载 {len(self.list_skills())} 个技能")
    
    def load_all_skills(self) -> Dict[str, Skill]:
        """加载所有技能"""
        skills = self.skill_loader.load_all()
        
        # 注册所有技能到全局注册中心
        for skill_name, skill in skills.items():
            if not skill_registry.has_skill(skill_name):
                skill_registry.register(skill)
        
        return skills
    
    def match_skill(self, user_input: str, context: Dict[str, Any] = None) -> tuple[Optional[Skill], float]:
        """
        为输入匹配合适的技能
        
        Args:
            user_input: 用户输入文本
            context: 上下文信息
            
        Returns:
            (匹配的技能, 匹配分数)
        """
        return self.skill_loader.match_skill(user_input, context)
    
    def get_skill(self, skill_name: str) -> Optional[Skill]:
        """获取指定名称的技能"""
        # 首先从注册中心获取
        skill = skill_registry.get_skill(skill_name)
        if skill:
            return skill
        
        # 如果注册中心没有，尝试从加载器获取
        skill = self.skill_loader.get_skill(skill_name)
        if skill:
            skill_registry.register(skill)
        
        return skill
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有可用技能"""
        return self.skill_loader.list_skills()
    
    def get_skill_prompt(self, skill_name: str) -> str:
        """获取技能提示词"""
        return self.skill_loader.get_skill_prompt(skill_name)
    
    def execute_skill_workflow(self, skill: Skill, context: Dict[str, Any], 
                              tool_executor: Callable) -> Dict[str, Any]:
        """
        执行技能工作流
        
        Args:
            skill: 技能对象
            context: 执行上下文
            tool_executor: 工具执行函数 (tool_name, params) -> result
            
        Returns:
            执行结果
        """
        results = {
            'skill_name': skill.name,
            'steps': [],
            'context': context.copy(),
            'success': True,
            'error_messages': []
        }
        
        print(f"[SKILL_WORKFLOW] 🚀 开始执行技能: {skill.name}")
        print(f"[SKILL_WORKFLOW] 📋 工作流步骤: {len(skill.workflow)}")
        
        for workflow_step in skill.workflow:
            tool_name = workflow_step.tool
            
            # 查找对应的工具定义
            tool_def = None
            for tool in skill.tools:
                if tool.name == tool_name:
                    tool_def = tool
                    break
            
            if not tool_def:
                error_msg = f"未找到工具定义: {tool_name}"
                print(f"[SKILL_WORKFLOW] ❌ {error_msg}")
                results['error_messages'].append(error_msg)
                results['success'] = False
                continue
            
            # 生成参数
            params = self._generate_params_from_skill_tool(tool_def, context, results)
            
            print(f"[SKILL_WORKFLOW] 🎯 执行步骤 {workflow_step.step}: {workflow_step.description}")
            print(f"[SKILL_WORKFLOW] 🔧 工具: {tool_name}, 参数: {params}")
            
            # 执行工具
            try:
                step_result = tool_executor(tool_name, params)
                
                # 记录步骤结果
                step_record = {
                    'step': workflow_step.step,
                    'tool': tool_name,
                    'description': workflow_step.description,
                    'params': params,
                    'result': step_result,
                    'timestamp': datetime.now().isoformat()
                }
                
                results['steps'].append(step_record)
                
                # 更新上下文
                if step_result and isinstance(step_result, dict):
                    # 提取关键信息到上下文
                    key_name = f"{tool_name}_result"
                    results['context'][key_name] = step_result
                    
                    # 自动提取常见字段
                    if 'data' in step_result:
                        results['context'][f'{tool_name}_data'] = step_result['data']
                    if 'bugs_found' in step_result:
                        results['context']['bugs_found'] = step_result['bugs_found']
                    if 'badcase_analysis' in step_result:
                        results['context']['badcase_analysis'] = step_result['badcase_analysis']
                
                print(f"[SKILL_WORKFLOW] ✅ 步骤 {workflow_step.step} 完成")
                
            except Exception as e:
                error_msg = f"步骤 {workflow_step.step} 执行失败: {str(e)}"
                print(f"[SKILL_WORKFLOW] ❌ {error_msg}")
                results['error_messages'].append(error_msg)
                results['success'] = False
                break
        
        # 增加技能使用计数
        if results['success']:
            skill_registry.increment_usage(skill.name)
        
        print(f"[SKILL_WORKFLOW] 📊 工作流执行完成: 成功={results['success']}, 步骤数={len(results['steps'])}")
        return results
    
    def _generate_params_from_skill_tool(self, tool_def, context: Dict[str, Any], 
                                        results: Dict[str, Any]) -> Dict[str, Any]:
        """
        从技能工具定义生成参数
        
        Args:
            tool_def: 工具定义
            context: 用户提供的上下文
            results: 当前执行结果
            
        Returns:
            生成的参数
        """
        params = {}
        
        for key, value_template in tool_def.params.items():
            if isinstance(value_template, str):
                # 处理模板参数
                params[key] = self._resolve_template(value_template, context, results)
            else:
                params[key] = value_template
        
        return params
    
    def _resolve_template(self, template: str, context: Dict[str, Any], 
                         results: Dict[str, Any]) -> Any:
        """
        解析模板参数
        
        Args:
            template: 模板字符串，如 ${user_keywords}
            context: 上下文
            results: 执行结果
            
        Returns:
            解析后的值
        """
        if not template.startswith('${') or not template.endswith('}'):
            return template
        
        var_name = template[2:-1]
        
        # 1. 从用户提供的上下文中查找
        if var_name in context:
            return context[var_name]
        
        # 2. 从执行结果中查找
        if var_name in results['context']:
            return results['context'][var_name]
        
        # 3. 特殊变量处理
        special_vars = {
            'user_input': lambda: context.get('user_input', ''),
            'project_id': lambda: context.get('project_id', 1),
            'current_time': lambda: datetime.now().isoformat()
        }
        
        if var_name in special_vars:
            return special_vars[var_name]()
        
        # 4. 从步骤结果中提取
        if var_name.endswith('_result') and results['steps']:
            # 查找上一个步骤的结果
            last_step = results['steps'][-1]
            if 'result' in last_step and isinstance(last_step['result'], dict):
                return last_step['result'].get('data', {})
        
        # 5. 嵌套查找（如 grep_result.first_bug_id）
        if '.' in var_name:
            parts = var_name.split('.')
            base_var = parts[0]
            field_path = parts[1:]
            
            # 查找基础变量
            base_value = None
            if base_var in context:
                base_value = context[base_var]
            elif base_var in results['context']:
                base_value = results['context'][base_var]
            
            # 递归导航属性
            if base_value and isinstance(base_value, dict):
                current = base_value
                for field in field_path:
                    if field in current:
                        current = current[field]
                    else:
                        return template  # 返回原模板
                return current
        
        # 无法解析，返回原模板
        return template
    
    def generate_agent_prompt(self, user_input: str) -> str:
        """
        生成Agent提示词，包含匹配到的技能信息
        
        Args:
            user_input: 用户输入
            
        Returns:
            提示词内容
        """
        # 匹配技能
        matched_skill, skill_score = self.match_skill(user_input)
        
        base_prompt = f"""
用户输入: {user_input}

"""
        
        if matched_skill and skill_score >= 0.3:
            skill_prompt = self.get_skill_prompt(matched_skill.name)
            enhanced_prompt = f"""{base_prompt}
🎯 **检测到相关技能**: {matched_skill.name}

📋 **技能描述**: {matched_skill.description}

🧭 **标准工作流**:
"""
            # 添加工作流步骤
            for step in matched_skill.workflow:
                enhanced_prompt += f"  {step.step}. {step.description}\n"
            
            enhanced_prompt += f"""
🛠 **技能匹配分数**: {skill_score:.2f}

请根据上述技能指导进行任务处理。
"""
            return enhanced_prompt
        else:
            # 没有匹配到技能的情况
            no_skill_prompt = f"""{base_prompt}
ℹ️ **提示**: 未检测到匹配的标准技能。

请根据你的知识和可用的工具来完成任务。

可用技能列表："""
            
            # 添加可用技能概述
            skills = self.list_skills()
            if skills:
                no_skill_prompt += "\n"
                for skill_info in skills[:5]:  # 最多显示5个
                    no_skill_prompt += f"- {skill_info['name']}: {skill_info['description']}\n"
            
            return no_skill_prompt
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取技能使用统计"""
        return skill_registry.get_skill_statistics()
    
    def save_custom_skill(self, skill_data: Dict[str, Any], skill_name: str = None) -> str:
        """
        保存自定义技能
        
        Args:
            skill_data: 技能数据（字典格式）
            skill_name: 技能名称（可选，从数据中提取）
            
        Returns:
            保存的文件路径
        """
        skill = Skill.from_dict(skill_data)
        file_name = skill_name or f"{skill.name}.yaml"
        return self.skill_loader.save_skill(skill, file_name)


# 全局集成管理器实例
skill_integration = SkillIntegration()