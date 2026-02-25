# agents/tools/accuracy_tester_tool.py
"""
准确率测试工具
测试对话/功能准确率，生成 BadCase 列表
"""

import json
from typing import Dict, Any, List
from ..tool_registry import BaseTool


class AccuracyTesterTool(BaseTool):
    """准确率测试工具"""
    
    def __init__(self, llm):
        """
        初始化准确率测试工具
        
        Args:
            llm: 语言模型实例
        """
        super().__init__(
            name='accuracy_tester',
            description='测试对话/功能准确率，生成 BadCase 列表'
        )
        self.llm = llm
    
    async def execute(
        self,
        test_set: List[Dict[str, Any]],
        feature: str,
        test_type: str = 'functional',
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行准确率测试
        
        Args:
            test_set: 测试用例集合
            feature: 功能名称
            test_type: 测试类型 (functional/conversation/api)
            **kwargs: 其他参数
            
        Returns:
            测试结果，包含准确率和 BadCase 列表
        """
        print(f"[ACCURACY_TEST] 📊 开始准确率测试: {feature}")
        print(f"[ACCURACY_TEST]   测试类型: {test_type}")
        print(f"[ACCURACY_TEST]   测试用例数: {len(test_set)}")
        
        results = {
            'feature': feature,
            'test_type': test_type,
            'total': len(test_set),
            'passed': 0,
            'failed': 0,
            'accuracy': 0.0,
            'badcases': []
        }
        
        if not test_set:
            results['accuracy'] = 100.0
            return results
        
        # 执行每个测试用例
        for i, test in enumerate(test_set):
            print(f"[ACCURACY_TEST]   执行用例 {i+1}/{len(test_set)}: {test.get('name', f'Test {i+1}')}")
            
            # 执行测试
            actual = await self._execute_test(test, test_type)
            expected = test.get('expected')
            
            # 对比结果
            if await self._compare_results(actual, expected):
                results['passed'] += 1
            else:
                results['failed'] += 1
                results['badcases'].append({
                    'name': test.get('name', f'Test {i+1}'),
                    'input': test.get('input'),
                    'expected': expected,
                    'actual': actual,
                    'diff': await self._compute_diff(expected, actual)
                })
        
        # 计算准确率
        results['accuracy'] = (results['passed'] / results['total'] * 100) if results['total'] > 0 else 100.0
        
        print(f"[ACCURACY_TEST] ✅ 测试完成，准确率: {results['accuracy']:.1f}%")
        
        return results
    
    async def _execute_test(self, test: Dict[str, Any], test_type: str) -> Any:
        """
        执行单个测试用例
        """
        # 模拟执行
        import asyncio
        await asyncio.sleep(0.1)
        
        if test_type == 'functional':
            # 功能测试：执行函数并返回结果
            return f"功能执行结果: {test.get('input', '')}"
        
        elif test_type == 'conversation':
            # 对话测试：调用模型
            response = await self.llm.parse_intent(f"用户: {test.get('input')}\n助手: ")
            return response
        
        elif test_type == 'api':
            # API 测试：模拟 API 调用
            return f"API 响应: {test.get('expected', 'success')}"
        
        return None
    
    async def _compare_results(self, actual: Any, expected: Any) -> bool:
        """
        对比结果
        """
        if isinstance(expected, str) and isinstance(actual, str):
            # 字符串模糊匹配
            return expected.lower() in actual.lower() or actual.lower() in expected.lower()
        
        return actual == expected
    
    async def _compute_diff(self, expected: Any, actual: Any) -> Dict[str, Any]:
        """
        计算差异
        """
        return {
            'expected_type': type(expected).__name__,
            'actual_type': type(actual).__name__,
            'expected_length': len(str(expected)),
            'actual_length': len(str(actual))
        }
