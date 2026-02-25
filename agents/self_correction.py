# agents/self_correction.py
"""
自我修正机制 - ReAct Observe + Claude Code Self-Reflect

设计思想：
1. 结果校验 - 检查工具执行结果是否符合预期
2. 失败分析 - 如果失败，分析根本原因
3. Todo 调整 - 根据失败原因调整后续 Todo
4. 重新执行 - 采用新策略重新执行

vs 传统 ReAct：
- 传统：执行失败就返回错误
- 增强：执行失败自动分析、调整、重试
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class CorrectionStrategy:
    """修正策略"""
    name: str  # 策略名
    description: str  # 策略描述
    action: str  # 执行的动作（retry/adjust_selector/change_tool/skip）
    new_params: Dict[str, Any]  # 新参数
    reason: str  # 修正原因


class ResultValidator:
    """结果校验器"""
    
    @staticmethod
    def validate(observation: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
        """
        校验工具执行结果
        
        Args:
            observation: 工具执行结果
            expected: 预期结果
            
        Returns:
            校验报告
        """
        report = {
            'valid': True,
            'issues': [],
            'severity': 'none',  # none / warning / critical
            'suggestions': []
        }
        
        # 检查是否成功
        if not observation.get('success'):
            report['valid'] = False
            report['severity'] = 'critical'
            report['issues'].append({
                'type': 'execution_failed',
                'message': observation.get('error', '工具执行失败'),
                'error_details': observation.get('error')
            })
        
        # 检查返回值类型
        if expected.get('output_type'):
            actual_type = type(observation.get('output')).__name__
            expected_type = expected['output_type']
            if actual_type != expected_type:
                report['valid'] = False
                report['severity'] = 'warning'
                report['issues'].append({
                    'type': 'type_mismatch',
                    'message': f'返回类型不匹配：期望 {expected_type}，得到 {actual_type}'
                })
        
        # 检查返回值内容
        if expected.get('output_contains'):
            for key in expected['output_contains']:
                if key not in (observation.get('output') or {}):
                    report['valid'] = False
                    report['severity'] = 'warning'
                    report['issues'].append({
                        'type': 'missing_output_field',
                        'message': f'缺少输出字段：{key}'
                    })
        
        return report


class FailureAnalyzer:
    """失败分析器 - 使用 LLM 分析根本原因"""
    
    def __init__(self, llm):
        self.llm = llm
    
    async def analyze(self, 
                     todo: str,
                     action: Dict[str, Any],
                     observation: Dict[str, Any],
                     context: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析执行失败的根本原因
        
        Args:
            todo: 当前 Todo
            action: 执行的行动
            observation: 工具返回结果
            context: 执行上下文
            
        Returns:
            失败分析报告
        """
        print(f"[CORRECT] 🔍 分析失败原因")
        
        prompt = f"""分析以下工具执行失败的根本原因。

当前 Todo: {todo}

执行的行动:
- 工具: {action.get('tool')}
- 参数: {json.dumps(action.get('params', {}), ensure_ascii=False)}

执行结果:
- 成功: {observation.get('success')}
- 错误: {observation.get('error')}
- 详情: {observation.get('error_details', '')}

执行上下文:
{json.dumps(context, ensure_ascii=False, indent=2)}

请分析根本原因（返回 JSON，仅 JSON）：
{{
    "root_cause": "根本原因（简洁说明）",
    "error_category": "selector_not_found / timeout / permission_denied / network_error / logic_error / other",
    "is_recoverable": true/false,
    "suggested_fix": "建议的修复方案"
}}
"""
        
        response = await self.llm.parse_intent(prompt)
        
        try:
            if isinstance(response, str):
                start = response.find('{')
                end = response.rfind('}') + 1
                if start != -1 and end > start:
                    analysis = json.loads(response[start:end])
            else:
                analysis = response if isinstance(response, dict) else {}
        except:
            analysis = {
                'root_cause': '无法解析失败原因',
                'error_category': 'other',
                'is_recoverable': False,
                'suggested_fix': '请手动检查'
            }
        
        print(f"[CORRECT]   根因: {analysis.get('root_cause')}")
        print(f"[CORRECT]   类型: {analysis.get('error_category')}")
        print(f"[CORRECT]   可恢复: {analysis.get('is_recoverable')}")
        
        return analysis


class StrategyGenerator:
    """修正策略生成器"""
    
    def __init__(self, llm):
        self.llm = llm
    
    async def generate(self,
                      todo: str,
                      action: Dict[str, Any],
                      analysis: Dict[str, Any],
                      available_tools: list) -> Optional[CorrectionStrategy]:
        """
        根据失败分析生成修正策略
        
        Args:
            todo: 当前 Todo
            action: 原始行动
            analysis: 失败分析报告
            available_tools: 可用工具列表
            
        Returns:
            修正策略
        """
        print(f"[CORRECT] 💡 生成修正策略")
        
        # 如果不可恢复，返回 None
        if not analysis.get('is_recoverable'):
            print(f"[CORRECT]   无法恢复，放弃修正")
            return None
        
        error_category = analysis.get('error_category')
        
        # 根据错误类型生成不同策略
        if error_category == 'selector_not_found':
            # 尝试更新 CSS 选择器
            prompt = f"""原始选择器 {action.get('params', {}).get('selector')} 未找到元素。

请生成一个备选选择器（返回纯选择器文本，不需要 JSON）：
"""
            new_selector = await self.llm.parse_intent(prompt)
            
            # 处理返回值可能是字典或字符串的情况
            if isinstance(new_selector, dict):
                selector_str = new_selector.get('selector', '').strip()
            else:
                selector_str = str(new_selector).strip() if new_selector else ''
            
            return CorrectionStrategy(
                name='adjust_selector',
                description='调整 CSS 选择器重试',
                action='retry',
                new_params={
                    **action['params'],
                    'selector': selector_str
                },
                reason=f'原选择器不存在，尝试备选: {selector_str}'
            )
        
        elif error_category == 'timeout':
            # 增加超时时间
            timeout = action.get('params', {}).get('timeout', 5)
            new_timeout = min(timeout * 2, 30)  # 最多 30 秒
            
            return CorrectionStrategy(
                name='increase_timeout',
                description='增加超时时间重试',
                action='retry',
                new_params={
                    **action['params'],
                    'timeout': new_timeout
                },
                reason=f'网络延迟，超时时间从 {timeout}s 增加到 {new_timeout}s'
            )
        
        elif error_category == 'logic_error':
            # 切换工具
            tools_str = json.dumps(available_tools, ensure_ascii=False)
            
            prompt = f"""当前工具执行失败，原因是逻辑错误。

可用工具:
{tools_str}

原始 Todo: {todo}

请推荐一个更合适的工具（返回工具名，不需要其他文本）：
"""
            new_tool = await self.llm.parse_intent(prompt)
            
            # 验证工具是否存在
            # 处理返回值可能是字典或字符串的情况
            if isinstance(new_tool, dict):
                tool_name = new_tool.get('tool_name', '').strip()
            else:
                tool_name = str(new_tool).strip() if new_tool else ''
            
            available_tool_names = [t['name'] for t in available_tools]
            
            if tool_name not in available_tool_names:
                print(f"[CORRECT]   ⚠️ LLM 建议的工具 '{tool_name}' 不在可用工具列表中")
                print(f"[CORRECT]   可用工具: {available_tool_names}")
                # 返回 None，表示无法修正
                return None
            
            return CorrectionStrategy(
                name='change_tool',
                description='切换工具重试',
                action='retry',
                new_params=action.get('params', {}),  # 保持参数
                reason=f'切换到工具: {tool_name}'
            )
        
        elif error_category == 'network_error':
            # 重试（等待网络恢复）
            retry_count = action.get('retry_count', 0)
            
            if retry_count >= 3:
                print(f"[CORRECT]   已重试 3 次，放弃")
                return None
            
            return CorrectionStrategy(
                name='retry_on_network',
                description='网络错误，重试执行',
                action='retry',
                new_params={
                    **action['params'],
                    'retry_count': retry_count + 1
                },
                reason=f'网络错误，重试（{retry_count + 1}/3）'
            )
        
        # 其他错误，跳过此 Todo
        return CorrectionStrategy(
            name='skip',
            description='跳过此 Todo',
            action='skip',
            new_params={},
            reason=analysis.get('suggested_fix', '无法修正，跳过')
        )


class TodoAdjuster:
    """Todo 列表调整器"""
    
    def __init__(self, llm):
        self.llm = llm
    
    async def adjust(self,
                    current_todos: List[str],
                    failed_todo_index: int,
                    analysis: Dict[str, Any],
                    context: Dict[str, Any]) -> List[str]:
        """
        根据失败分析调整 Todo 列表
        
        Args:
            current_todos: 当前 Todo 列表
            failed_todo_index: 失败的 Todo 索引
            analysis: 失败分析报告
            context: 执行上下文
            
        Returns:
            调整后的 Todo 列表
        """
        print(f"[CORRECT] 📝 调整 Todo 列表")
        
        # 保留已执行的 Todo
        remaining_todos = current_todos[failed_todo_index:]
        
        # 如果分析建议了修复方案，生成新的 Todo
        suggested_fix = analysis.get('suggested_fix')
        
        if suggested_fix and suggested_fix != '请手动检查':
            # 在失败 Todo 后插入修复 Todo
            new_todos = (
                current_todos[:failed_todo_index] +
                [f"修复: {suggested_fix}"] +
                remaining_todos[1:]  # 跳过原失败 Todo
            )
            
            print(f"[CORRECT]   在索引 {failed_todo_index} 后插入修复 Todo")
            return new_todos
        
        # 否则跳过失败的 Todo
        return (
            current_todos[:failed_todo_index] +
            remaining_todos[1:]
        )


class SelfCorrectionEngine:
    """自我修正引擎 - 综合所有组件"""
    
    def __init__(self, llm):
        self.llm = llm
        self.validator = ResultValidator()
        self.analyzer = FailureAnalyzer(llm)
        self.strategy_gen = StrategyGenerator(llm)
        self.todo_adjuster = TodoAdjuster(llm)
    
    async def correct_and_retry(self,
                               todo: str,
                               action: Dict[str, Any],
                               observation: Dict[str, Any],
                               context: Dict[str, Any],
                               available_tools: list,
                               execute_fn) -> Dict[str, Any]:
        """
        执行完整的修正和重试流程
        
        Args:
            todo: 当前 Todo
            action: 原始行动
            observation: 工具返回结果
            context: 执行上下文
            available_tools: 可用工具列表
            execute_fn: 工具执行函数（async）
            
        Returns:
            修正后的执行结果
        """
        print(f"\n[CORRECT] 🔄 自我修正流程启动\n")
        
        # Step 1: 校验结果
        expected = {'output_type': 'dict'}
        validation_report = self.validator.validate(observation, expected)
        
        if validation_report['valid']:
            print(f"[CORRECT] ✅ 结果校验通过，无需修正")
            return observation
        
        print(f"[CORRECT] ❌ 校验失败: {validation_report['issues']}")
        
        # Step 2: 分析失败原因
        analysis = await self.analyzer.analyze(todo, action, observation, context)
        
        # Step 3: 生成修正策略
        strategy = await self.strategy_gen.generate(
            todo, action, analysis, available_tools
        )
        
        if not strategy:
            print(f"[CORRECT] 无法生成修正策略，返回原错误")
            return observation
        
        print(f"[CORRECT] 📋 修正策略: {strategy.name}")
        print(f"[CORRECT]    描述: {strategy.description}")
        print(f"[CORRECT]    原因: {strategy.reason}")
        
        # Step 4: 执行修正
        if strategy.action == 'skip':
            print(f"[CORRECT] ⏭ 跳过此 Todo")
            return {
                'success': False,
                'error': 'skipped',
                'reason': strategy.reason,
                'corrected': True
            }
        
        elif strategy.action == 'retry':
            print(f"[CORRECT] 🔁 重试执行")
            
            # 更新行动参数
            new_action = {
                'tool': action['tool'],
                'params': strategy.new_params
            }
            
            # 重新执行工具
            retry_result = await execute_fn(new_action)
            
            if retry_result.get('success'):
                print(f"[CORRECT] ✅ 修正成功！")
                return {
                    **retry_result,
                    'corrected': True,
                    'correction_strategy': strategy.name
                }
            else:
                print(f"[CORRECT] ❌ 修正失败，再次失败")
                return {
                    **retry_result,
                    'corrected': False,
                    'correction_attempts': 1
                }
        
        return observation
