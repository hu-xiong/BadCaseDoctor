# agents/tool_registry.py
"""
工具注册表和基类
参考 Claude Code Interpreter 架构
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import json
import os


class BaseTool(ABC):
    """所有工具的基类"""
    
    def __init__(self, name: str, description: str):
        """
        初始化工具
        
        Args:
            name: 工具名称（在 ReAct 中使用）
            description: 工具描述（供 LLM 参考）
        """
        self.name = name
        self.description = description
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工具
        
        所有子类必须实现此方法
        """
        pass
    
    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"


class ToolRegistry:
    """工具注册中心"""
    
    def __init__(self):
        """初始化工具注册表"""
        self.tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool):
        """
        注册工具
        
        Args:
            tool: BaseTool 实例
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(f"tool 必须是 BaseTool 的实例，得到 {type(tool)}")
        
        self.tools[tool.name] = tool
        if os.getenv("QUIET_LOG") != "1":
            print(f"[REGISTRY] ✅ 工具已注册: {tool.name}")
    
    def get(self, name: str) -> Optional[BaseTool]:
        """
        获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            工具实例或 None
        """
        return self.tools.get(name)
    
    def has_tool(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self.tools
    
    def list_tools(self) -> List[Dict[str, str]]:
        """
        返回所有工具的描述
        
        Returns:
            工具列表，包含 name 和 description
        """
        return [
            {
                'name': tool.name,
                'description': tool.description
            }
            for tool in self.tools.values()
        ]
    
    def get_tools_prompt(self) -> str:
        """
        生成工具列表提示词
        
        供 LLM 调用时使用
        """
        tools_list = self.list_tools()
        prompt = "可用工具列表:\n"
        for tool in tools_list:
            prompt += f"- {tool['name']}: {tool['description']}\n"
        return prompt
    
    def __len__(self):
        return len(self.tools)
    
    def __repr__(self):
        return f"<ToolRegistry: {len(self.tools)} tools>"
