"""
Skill 注册中心
管理技能的注册、卸载和查询
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from .skill import Skill


class SkillRegistry:
    """Skill 注册中心 - 单例模式"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.skills: Dict[str, Skill] = {}
        self.skill_load_time: Dict[str, datetime] = {}
        self.skill_usage_count: Dict[str, int] = {}
        self._initialized = True
        print(f"[SKILL_REGISTRY] 🪧 技能注册中心已初始化")
    
    def register(self, skill: Skill) -> bool:
        """
        注册新技能
        
        Args:
            skill: 技能对象
            
        Returns:
            是否注册成功
        """
        if not skill or not skill.name:
            print(f"[SKILL_REGISTRY] ❌ 无效的技能对象")
            return False
        
        if self.has_skill(skill.name):
            print(f"[SKILL_REGISTRY] ⚠️  技能已存在: {skill.name}")
            return False
        
        self.skills[skill.name] = skill
        self.skill_load_time[skill.name] = datetime.now()
        self.skill_usage_count[skill.name] = 0
        
        print(f"[SKILL_REGISTRY] ✅ 注册技能: {skill.name}")
        return True
    
    def unregister(self, skill_name: str) -> bool:
        """
        注销技能
        
        Args:
            skill_name: 技能名称
            
        Returns:
            是否注销成功
        """
        if not self.has_skill(skill_name):
            print(f"[SKILL_REGISTRY] ⚠️  技能不存在: {skill_name}")
            return False
        
        del self.skills[skill_name]
        del self.skill_load_time[skill_name]
        del self.skill_usage_count[skill_name]
        
        print(f"[SKILL_REGISTRY] 🗑️  注销技能: {skill_name}")
        return True
    
    def get_skill(self, skill_name: str) -> Optional[Skill]:
        """
        获取技能
        
        Args:
            skill_name: 技能名称
            
        Returns:
            技能对象，如果不存在则返回None
        """
        return self.skills.get(skill_name)
    
    def has_skill(self, skill_name: str) -> bool:
        """检查技能是否存在"""
        return skill_name in self.skills
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """
        列出所有已注册技能
        
        Returns:
            技能信息列表
        """
        skill_list = []
        for name, skill in self.skills.items():
            skill_list.append({
                'name': name,
                'description': skill.description,
                'tools': skill.get_tool_names(),
                'intents': skill.trigger.intents,
                'entities': skill.trigger.entities,
                'load_time': self.skill_load_time.get(name),
                'usage_count': self.skill_usage_count.get(name, 0)
            })
        
        # 按使用次数排序
        skill_list.sort(key=lambda x: x['usage_count'], reverse=True)
        return skill_list
    
    def increment_usage(self, skill_name: str) -> bool:
        """
        增加技能使用次数
        
        Args:
            skill_name: 技能名称
            
        Returns:
            是否成功
        """
        if not self.has_skill(skill_name):
            return False
        
        self.skill_usage_count[skill_name] = self.skill_usage_count.get(skill_name, 0) + 1
        return True
    
    def get_most_used_skills(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        获取最常用的技能
        
        Args:
            limit: 返回的最大数量
            
        Returns:
            技能信息列表
        """
        all_skills = self.list_skills()
        return all_skills[:limit]
    
    def get_skills_by_tool(self, tool_name: str) -> List[Skill]:
        """
        获取使用指定工具的所有技能
        
        Args:
            tool_name: 工具名称
            
        Returns:
            技能列表
        """
        matching_skills = []
        for skill in self.skills.values():
            if tool_name in skill.get_tool_names():
                matching_skills.append(skill)
        
        return matching_skills
    
    def get_skill_statistics(self) -> Dict[str, Any]:
        """获取技能统计信息"""
        total_skills = len(self.skills)
        total_usage = sum(self.skill_usage_count.values())
        
        # 按工具分类统计
        tools_usage = {}
        for skill_name, skill in self.skills.items():
            for tool_name in skill.get_tool_names():
                tools_usage[tool_name] = tools_usage.get(tool_name, 0) + self.skill_usage_count.get(skill_name, 0)
        
        # 按意图分类统计
        intent_usage = {}
        for skill_name, skill in self.skills.items():
            for intent in skill.trigger.intents:
                intent_usage[intent] = intent_usage.get(intent, 0) + self.skill_usage_count.get(skill_name, 0)
        
        return {
            'total_skills': total_skills,
            'total_usage': total_usage,
            'avg_usage_per_skill': total_usage / total_skills if total_skills > 0 else 0,
            'top_tools': dict(sorted(tools_usage.items(), key=lambda x: x[1], reverse=True)[:5]),
            'top_intents': dict(sorted(intent_usage.items(), key=lambda x: x[1], reverse=True)[:5]),
            'recently_loaded': [
                name for name, _ in 
                sorted(self.skill_load_time.items(), key=lambda x: x[1], reverse=True)[:5]
            ]
        }
    
    def clear(self) -> None:
        """清空所有注册的技能"""
        self.skills.clear()
        self.skill_load_time.clear()
        self.skill_usage_count.clear()
        print(f"[SKILL_REGISTRY] 🧹 已清空所有技能")
    
    def __len__(self) -> int:
        return len(self.skills)
    
    def __repr__(self) -> str:
        return f"<SkillRegistry: {len(self)} skills>"

# 全局注册中心实例
skill_registry = SkillRegistry()