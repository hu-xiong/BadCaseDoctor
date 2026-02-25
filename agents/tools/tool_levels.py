# agents/tools/tool_levels.py
"""
工具分层架构 - 参考 Claude Code 设计
https://minusx.ai/blog/decoding-claude-code/

三层工具体系：
1. 低阶工具 (L1) - 原子操作
   - 单一职责，无状态
   - 例：点击元素、输入文本、等待元素
   - 风险：需要大量 ReAct 循环步骤

2. 中阶工具 (L2) - 复合操作
   - 组合 L1 工具，有限状态管理
   - 例：完整登录流程、表单填充
   - 优势：减少 ReAct 步骤，提高准确率

3. 高阶工具 (L3) - 流程工具
   - 组合 L2 工具，完整业务流程
   - 例：端到端登录+验证、完整购物流程
   - 优势：一次调用完成复杂任务

设计原则：
- 逐层抽象：L2 基于 L1，L3 基于 L2
- 错误冒泡：低层错误不隐瞒，直接上报
- 可组合性：各层工具独立可用
- 可观测性：每层都提供详细的执行日志
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import asyncio
import json


@dataclass
class ToolExecutionResult:
    """工具执行结果"""
    success: bool
    level: int  # 1=L1, 2=L2, 3=L3
    tool_name: str
    output: Any
    error: Optional[str] = None
    steps: List[Dict[str, Any]] = None  # 执行步骤详情
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'level': self.level,
            'tool': self.tool_name,
            'output': self.output,
            'error': self.error,
            'steps': self.steps or []
        }


# ==================== L1: 低阶工具 ====================

class L1_BrowserActions:
    """L1 低阶工具 - 浏览器原子操作"""
    
    @staticmethod
    async def click_element(selector: str) -> ToolExecutionResult:
        """点击元素"""
        print(f"[L1] 🖱 点击元素: {selector}")
        
        # 模拟执行
        await asyncio.sleep(0.1)
        
        return ToolExecutionResult(
            success=True,
            level=1,
            tool_name='click_element',
            output={'selector': selector, 'status': 'clicked'},
            steps=[{'action': 'click', 'selector': selector, 'status': 'success'}]
        )
    
    @staticmethod
    async def input_text(selector: str, text: str) -> ToolExecutionResult:
        """输入文本"""
        print(f"[L1] ⌨ 输入文本: {selector} = {text[:20]}...")
        
        await asyncio.sleep(0.1)
        
        return ToolExecutionResult(
            success=True,
            level=1,
            tool_name='input_text',
            output={'selector': selector, 'text': text, 'status': 'input'},
            steps=[{'action': 'input', 'selector': selector, 'length': len(text), 'status': 'success'}]
        )
    
    @staticmethod
    async def wait_element(selector: str, timeout: int = 5) -> ToolExecutionResult:
        """等待元素出现"""
        print(f"[L1] ⏳ 等待元素: {selector} (超时: {timeout}s)")
        
        await asyncio.sleep(0.2)
        
        return ToolExecutionResult(
            success=True,
            level=1,
            tool_name='wait_element',
            output={'selector': selector, 'found': True},
            steps=[{'action': 'wait', 'selector': selector, 'timeout': timeout, 'status': 'success'}]
        )
    
    @staticmethod
    async def get_text(selector: str) -> ToolExecutionResult:
        """获取元素文本"""
        print(f"[L1] 📖 获取文本: {selector}")
        
        await asyncio.sleep(0.1)
        
        return ToolExecutionResult(
            success=True,
            level=1,
            tool_name='get_text',
            output={'selector': selector, 'text': 'Sample Text'},
            steps=[{'action': 'get_text', 'selector': selector, 'status': 'success'}]
        )
    
    @staticmethod
    async def assert_visible(selector: str) -> ToolExecutionResult:
        """断言元素可见"""
        print(f"[L1] ✓ 断言可见: {selector}")
        
        await asyncio.sleep(0.1)
        
        return ToolExecutionResult(
            success=True,
            level=1,
            tool_name='assert_visible',
            output={'selector': selector, 'visible': True},
            steps=[{'action': 'assert_visible', 'selector': selector, 'status': 'success'}]
        )


# ==================== L2: 中阶工具 ====================

class L2_FormOperations:
    """L2 中阶工具 - 表单复合操作"""
    
    @staticmethod
    async def fill_form(form_data: Dict[str, str]) -> ToolExecutionResult:
        """填充表单（组合多个 L1 操作）"""
        print(f"[L2] 📋 填充表单，字段数: {len(form_data)}")
        
        steps = []
        l1_actions = L1_BrowserActions()
        
        for field, value in form_data.items():
            print(f"[L2]   → {field} = {value[:20]}...")
            
            # 调用 L1 工具
            result = await l1_actions.input_text(field, value)
            steps.append({
                'field': field,
                'action': 'input',
                'status': 'success' if result.success else 'failed'
            })
        
        return ToolExecutionResult(
            success=True,
            level=2,
            tool_name='fill_form',
            output={'fields_filled': len(form_data)},
            steps=steps
        )
    
    @staticmethod
    async def submit_form(submit_button_selector: str = 'button[type="submit"]') -> ToolExecutionResult:
        """提交表单"""
        print(f"[L2] 🔘 提交表单")
        
        steps = []
        l1_actions = L1_BrowserActions()
        
        # 先断言按钮可见
        assert_result = await l1_actions.assert_visible(submit_button_selector)
        steps.append({
            'action': 'assert_visible',
            'target': submit_button_selector,
            'status': 'success' if assert_result.success else 'failed'
        })
        
        # 再点击
        click_result = await l1_actions.click_element(submit_button_selector)
        steps.append({
            'action': 'click',
            'target': submit_button_selector,
            'status': 'success' if click_result.success else 'failed'
        })
        
        return ToolExecutionResult(
            success=True,
            level=2,
            tool_name='submit_form',
            output={'submitted': True},
            steps=steps
        )


# ==================== L3: 高阶工具 ====================

class L3_CompleteFlows:
    """L3 高阶工具 - 完整业务流程"""
    
    @staticmethod
    async def complete_login(username: str, password: str) -> ToolExecutionResult:
        """完整登录流程（组合 L2 操作）"""
        print(f"\n[L3] 🔐 完整登录流程")
        print(f"[L3]   用户: {username}")
        
        steps = []
        l2_actions = L2_FormOperations()
        l1_actions = L1_BrowserActions()
        
        try:
            # Step 1: 等待登录页加载
            print(f"[L3] 步骤 1: 等待登录页加载")
            wait_result = await l1_actions.wait_element('.login-form', timeout=5)
            steps.append({
                'step': 1,
                'action': 'wait_login_form',
                'status': 'success' if wait_result.success else 'failed'
            })
            
            if not wait_result.success:
                return ToolExecutionResult(
                    success=False,
                    level=3,
                    tool_name='complete_login',
                    output=None,
                    error='登录页加载失败',
                    steps=steps
                )
            
            # Step 2: 填充登录表单
            print(f"[L3] 步骤 2: 填充表单")
            fill_result = await l2_actions.fill_form({
                'input[name="username"]': username,
                'input[name="password"]': password
            })
            steps.append({
                'step': 2,
                'action': 'fill_form',
                'fields': 2,
                'status': 'success' if fill_result.success else 'failed'
            })
            
            if not fill_result.success:
                return ToolExecutionResult(
                    success=False,
                    level=3,
                    tool_name='complete_login',
                    output=None,
                    error='表单填充失败',
                    steps=steps
                )
            
            # Step 3: 提交表单
            print(f"[L3] 步骤 3: 提交表单")
            submit_result = await l2_actions.submit_form()
            steps.append({
                'step': 3,
                'action': 'submit_form',
                'status': 'success' if submit_result.success else 'failed'
            })
            
            if not submit_result.success:
                return ToolExecutionResult(
                    success=False,
                    level=3,
                    tool_name='complete_login',
                    output=None,
                    error='表单提交失败',
                    steps=steps
                )
            
            # Step 4: 等待登录完成（检查首页加载）
            print(f"[L3] 步骤 4: 等待登录完成")
            home_result = await l1_actions.wait_element('.home-page', timeout=10)
            steps.append({
                'step': 4,
                'action': 'wait_home_page',
                'status': 'success' if home_result.success else 'failed'
            })
            
            if not home_result.success:
                return ToolExecutionResult(
                    success=False,
                    level=3,
                    tool_name='complete_login',
                    output=None,
                    error='登录超时，首页未加载',
                    steps=steps
                )
            
            # Step 5: 验证登录成功（检查用户名显示）
            print(f"[L3] 步骤 5: 验证登录成功")
            verify_result = await l1_actions.assert_visible('.user-profile')
            steps.append({
                'step': 5,
                'action': 'verify_login',
                'status': 'success' if verify_result.success else 'failed'
            })
            
            print(f"[L3] ✅ 登录流程完成")
            
            return ToolExecutionResult(
                success=True,
                level=3,
                tool_name='complete_login',
                output={
                    'username': username,
                    'status': 'logged_in',
                    'timestamp': '2024-01-26 10:00:00'
                },
                steps=steps
            )
        
        except Exception as e:
            return ToolExecutionResult(
                success=False,
                level=3,
                tool_name='complete_login',
                output=None,
                error=str(e),
                steps=steps
            )
    
    @staticmethod
    async def complete_test_scenario(test_name: str, steps_config: List[Dict]) -> ToolExecutionResult:
        """完整测试场景（高度可组合）"""
        print(f"\n[L3] 🧪 完整测试场景: {test_name}")
        
        steps = []
        all_passed = True
        
        for i, step_config in enumerate(steps_config, 1):
            action = step_config.get('action')
            params = step_config.get('params', {})
            
            print(f"[L3] 场景步骤 {i}: {action}")
            
            # 根据 action 类型调用相应的 L1/L2 工具
            if action == 'click':
                result = await L1_BrowserActions.click_element(params.get('selector'))
            elif action == 'input':
                result = await L1_BrowserActions.input_text(
                    params.get('selector'),
                    params.get('text')
                )
            elif action == 'assert':
                result = await L1_BrowserActions.assert_visible(params.get('selector'))
            else:
                result = ToolExecutionResult(
                    success=False,
                    level=1,
                    tool_name=action,
                    output=None,
                    error=f'未知 action: {action}'
                )
            
            steps.append({
                'step': i,
                'action': action,
                'status': 'success' if result.success else 'failed',
                'error': result.error
            })
            
            if not result.success:
                all_passed = False
                break
        
        print(f"[L3] 测试场景 {'✅ 成功' if all_passed else '❌ 失败'}")
        
        return ToolExecutionResult(
            success=all_passed,
            level=3,
            tool_name='complete_test_scenario',
            output={
                'test_name': test_name,
                'steps_passed': sum(1 for s in steps if s['status'] == 'success'),
                'total_steps': len(steps)
            },
            steps=steps
        )
