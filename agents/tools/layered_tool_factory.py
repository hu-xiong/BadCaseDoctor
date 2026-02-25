# agents/tools/layered_tool_factory.py
"""
分层工具工厂
自动包装 L1/L2/L3 工具为统一接口
"""

from typing import Dict, Any, Type
from .tool_levels import (
    L1_BrowserActions,
    L2_FormOperations,
    L3_CompleteFlows,
    ToolExecutionResult
)
from ..tool_registry import BaseTool
import asyncio


class L1BrowserTool(BaseTool):
    """L1 工具包装 - 点击元素"""
    
    def __init__(self):
        super().__init__(
            name='browser_click',
            description='L1: 点击页面元素 (原子操作)'
        )
    
    async def execute(self, selector: str, **kwargs) -> Dict[str, Any]:
        """执行工具"""
        result = await L1_BrowserActions.click_element(selector)
        return result.to_dict()


class L1InputTool(BaseTool):
    """L1 工具包装 - 输入文本"""
    
    def __init__(self):
        super().__init__(
            name='browser_input',
            description='L1: 输入文本到元素 (原子操作)'
        )
    
    async def execute(self, selector: str, text: str, **kwargs) -> Dict[str, Any]:
        """执行工具"""
        result = await L1_BrowserActions.input_text(selector, text)
        return result.to_dict()


class L1WaitTool(BaseTool):
    """L1 工具包装 - 等待元素"""
    
    def __init__(self):
        super().__init__(
            name='browser_wait',
            description='L1: 等待元素出现 (原子操作)'
        )
    
    async def execute(self, selector: str, timeout: int = 5, **kwargs) -> Dict[str, Any]:
        """执行工具"""
        result = await L1_BrowserActions.wait_element(selector, timeout)
        return result.to_dict()


class L1AssertTool(BaseTool):
    """L1 工具包装 - 断言可见"""
    
    def __init__(self):
        super().__init__(
            name='browser_assert',
            description='L1: 断言元素可见 (原子操作)'
        )
    
    async def execute(self, selector: str, **kwargs) -> Dict[str, Any]:
        """执行工具"""
        result = await L1_BrowserActions.assert_visible(selector)
        return result.to_dict()


class L2FormTool(BaseTool):
    """L2 工具包装 - 表单填充"""
    
    def __init__(self):
        super().__init__(
            name='form_fill',
            description='L2: 填充表单 (复合操作，组合 L1 点击+输入)'
        )
    
    async def execute(self, form_data: Dict[str, str], **kwargs) -> Dict[str, Any]:
        """执行工具"""
        result = await L2_FormOperations.fill_form(form_data)
        return result.to_dict()


class L2SubmitTool(BaseTool):
    """L2 工具包装 - 表单提交"""
    
    def __init__(self):
        super().__init__(
            name='form_submit',
            description='L2: 提交表单 (复合操作，先断言再点击)'
        )
    
    async def execute(self, submit_button_selector: str = 'button[type="submit"]', **kwargs) -> Dict[str, Any]:
        """执行工具"""
        result = await L2_FormOperations.submit_form(submit_button_selector)
        return result.to_dict()


class L3LoginTool(BaseTool):
    """L3 工具包装 - 完整登录"""
    
    def __init__(self):
        super().__init__(
            name='complete_login',
            description='L3: 完整登录流程 (5 步流程：等待页→填充表→提交→等待首页→验证)'
        )
    
    async def execute(self, username: str, password: str, **kwargs) -> Dict[str, Any]:
        """执行工具"""
        result = await L3_CompleteFlows.complete_login(username, password)
        return result.to_dict()


class L3TestScenarioTool(BaseTool):
    """L3 工具包装 - 测试场景"""
    
    def __init__(self):
        super().__init__(
            name='test_scenario',
            description='L3: 完整测试场景 (组合多个 L1/L2 操作执行完整流程)'
        )
    
    async def execute(self, test_name: str, steps: list, **kwargs) -> Dict[str, Any]:
        """执行工具"""
        result = await L3_CompleteFlows.complete_test_scenario(test_name, steps)
        return result.to_dict()


class LayeredToolFactory:
    """分层工具工厂"""
    
    @staticmethod
    def create_all_tools() -> Dict[str, BaseTool]:
        """创建所有分层工具"""
        return {
            # L1: 原子操作
            'browser_click': L1BrowserTool(),
            'browser_input': L1InputTool(),
            'browser_wait': L1WaitTool(),
            'browser_assert': L1AssertTool(),
            
            # L2: 复合操作
            'form_fill': L2FormTool(),
            'form_submit': L2SubmitTool(),
            
            # L3: 完整流程
            'complete_login': L3LoginTool(),
            'test_scenario': L3TestScenarioTool(),
        }
    
    @staticmethod
    def get_tool_by_level(level: int) -> list:
        """按级别获取工具"""
        all_tools = LayeredToolFactory.create_all_tools()
        
        if level == 1:
            return {
                k: v for k, v in all_tools.items()
                if k.startswith('browser_')
            }
        elif level == 2:
            return {
                k: v for k, v in all_tools.items()
                if k.startswith('form_')
            }
        elif level == 3:
            return {
                k: v for k, v in all_tools.items()
                if k in ['complete_login', 'test_scenario']
            }
        else:
            return {}
    
    @staticmethod
    def get_recommended_tool_for_task(task_description: str) -> str:
        """根据任务描述推荐工具"""
        task_lower = task_description.lower()
        
        # 高优先级：完整流程用 L3
        if '登录' in task_lower and ('完成' in task_lower or '端到端' in task_lower):
            return 'complete_login'
        
        if '测试' in task_lower and '场景' in task_lower:
            return 'test_scenario'
        
        # 中优先级：表单用 L2
        if '填充表单' in task_lower or '表单填充' in task_lower:
            return 'form_fill'
        
        if '提交' in task_lower and '表单' in task_lower:
            return 'form_submit'
        
        # 低优先级：原子操作用 L1
        if '点击' in task_lower:
            return 'browser_click'
        
        if '输入' in task_lower:
            return 'browser_input'
        
        if '等待' in task_lower:
            return 'browser_wait'
        
        if '断言' in task_lower or '验证' in task_lower:
            return 'browser_assert'
        
        # 默认
        return None


def print_tool_hierarchy():
    """打印工具层级信息"""
    print("\n[TOOLS] 分层工具体系\n")
    
    print("=" * 60)
    print("L1: 低阶工具 - 原子操作（无状态）")
    print("=" * 60)
    print("""
    browser_click    - 点击元素
    browser_input    - 输入文本
    browser_wait     - 等待元素出现
    browser_assert   - 断言元素可见
    
    风险：需要大量 ReAct 循环步骤
    优势：灵活，支持任意组合
    """)
    
    print("=" * 60)
    print("L2: 中阶工具 - 复合操作（有限状态）")
    print("=" * 60)
    print("""
    form_fill        - 填充表单（组合 L1）
    form_submit      - 提交表单（先断言再点击）
    
    优势：减少 ReAct 步骤，提高准确率
    应用：表单操作、常见交互
    """)
    
    print("=" * 60)
    print("L3: 高阶工具 - 完整流程（完整业务）")
    print("=" * 60)
    print("""
    complete_login   - 完整登录（5 步流程）
    test_scenario    - 完整测试场景（任意步骤组合）
    
    优势：一次调用完成复杂任务，最少 ReAct 步骤
    应用：端到端测试、业务流程
    """)
    
    print("=" * 60)
    print("设计原则")
    print("=" * 60)
    print("""
    1. 逐层抽象：L2 基于 L1，L3 基于 L2
    2. 错误冒泡：低层错误不隐瞒，直接上报
    3. 可组合性：各层工具独立可用
    4. 可观测性：每层都提供详细执行日志
    5. ReAct 优化：优先使用高层工具减少循环步数
    """)
