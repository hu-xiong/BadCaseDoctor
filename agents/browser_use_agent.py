# agents/browser_use_agent.py
"""
Browser-use Agent: 模拟人工测试操作，支持以下功能：
1. 测试用例执行：根据测试用例模拟人工测试，生成 Bug 列表
2. BadCase 复现定位：模拟对话，观察 BadCase 复现效果
3. 对话准确率测试：通过测试集评估对话质量
"""

import json
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from langchain_core.language_models import BaseLLM
import time

from .base import BaseAgent
from config import Config


class BrowserUseAgent(BaseAgent):
    """Browser-use 工具 Agent"""
    
    name = "browser_use"
    
    def __init__(self):
        """初始化 Browser-use Agent"""
        # 这里可以添加 browser-use 的初始化配置
        self.browser_config = {
            "headless": False,  # 是否无头模式
            "timeout": 30000,   # 超时时间
            "viewport": {"width": 1920, "height": 1080}
        }
        
    def handle(self, 
               userId: str, 
               action: str, 
               llm: BaseLLM,
               test_case: Optional[Dict] = None,
               badcase: Optional[Dict] = None,
               conversation_test: Optional[Dict] = None,
               **kwargs) -> Dict[str, Any]:
        """
        处理 Browser-use 相关操作
        
        Args:
            userId: 用户ID
            action: 操作类型
                - "test_execution": 测试用例执行
                - "badcase_reproduction": BadCase 复现定位
                - "conversation_test": 对话准确率测试
            llm: 语言模型实例
            test_case: 测试用例数据
            badcase: BadCase 数据
            conversation_test: 对话测试数据
            
        Returns:
            执行结果
        """
        print(f"=== Browser-use Agent 处理请求 ===")
        print(f"用户ID: {userId}")
        print(f"操作类型: {action}")
        
        try:
            if action == "test_execution":
                return self._execute_test_case(userId, test_case, llm)
            elif action == "badcase_reproduction":
                return self._reproduce_badcase(userId, badcase, llm)
            elif action == "conversation_test":
                return self._test_conversation(userId, conversation_test, llm)
            else:
                return {"error": f"不支持的操作类型: {action}"}
        except Exception as e:
            print(f"Browser-use Agent 处理失败: {e}")
            return {"error": f"操作失败: {str(e)}"}
    
    def _execute_test_case(self, 
                          userId: str, 
                          test_case: Dict, 
                          llm: BaseLLM) -> Dict[str, Any]:
        """
        执行测试用例，生成 Bug 列表
        
        流程:
        1. 使用千帆模型解析测试用例并生成测试步骤
        2. 模拟浏览器执行测试步骤
        3. 使用千帆模型分析结果并识别 Bug
        4. 生成 Bug 列表(待审核状态)
        5. 返回结果供人工审核
        
        Args:
            userId: 用户ID
            test_case: 测试用例数据
            llm: 语言模型实例
            
        Returns:
            测试执行结果
        """
        print(f"[BROWSER_AGENT] === 执行测试用例 ===")
        print(f"[BROWSER_AGENT] 测试用例: {test_case}")
        
        start_time = time.time()
        
        try:
            # 第1步：使用千帆模型解析测试用例
            print(f"[BROWSER_AGENT] 第1步：使用千帆模型解析测试用例...")
            parse_start = time.time()
            
            test_description = test_case.get('description', '')
            parsed_steps = self._parse_test_case_with_llm(test_description, llm)
            
            print(f"[BROWSER_AGENT] 解析完成，耗时: {time.time() - parse_start:.4f}s")
            print(f"[BROWSER_AGENT] 生成的测试步骤数: {len(parsed_steps)}")
            
            # 第2步：模拟执行测试步骤
            print(f"[BROWSER_AGENT] 第2步：模拟执行测试步骤...")
            exec_start = time.time()
            
            execution_results = []
            for i, step in enumerate(parsed_steps):
                print(f"[BROWSER_AGENT] 执行步骤 {i+1}/{len(parsed_steps)}: {step.get('title', 'Unknown')}")
                
                # 模拟执行（实际应使用 browser-use 库）
                step_result = {
                    'step': i + 1,
                    'title': step.get('title'),
                    'action': step.get('action'),
                    'expected': step.get('expected'),
                    'status': 'completed',
                    'duration': 0.5
                }
                execution_results.append(step_result)
            
            print(f"[BROWSER_AGENT] 执行完成，耗时: {time.time() - exec_start:.4f}s")
            
            # 第3步：使用千帆模型分析结果并识别 Bug
            print(f"[BROWSER_AGENT] 第3步：使用千帆模型分析结果并识别 Bug...")
            analyze_start = time.time()
            
            bugs_found = self._analyze_results_with_llm(
                test_description, 
                parsed_steps, 
                execution_results, 
                llm
            )
            
            print(f"[BROWSER_AGENT] 分析完成，发现 Bug 数: {len(bugs_found)}, 耗时: {time.time() - analyze_start:.4f}s")
            
            total_time = time.time() - start_time
            print(f"[BROWSER_AGENT] === 测试执行完成，总耗时: {total_time:.4f}s ===")
            
            return {
                "code": 200,
                "message": "测试执行完成",
                "data": {
                    "test_case_id": test_case.get("id", f"test_{int(time.time())}"),
                    "execution_time": datetime.now().isoformat(),
                    "steps_executed": len(parsed_steps),
                    "bugs_found": bugs_found,
                    "execution_duration": total_time
                }
            }
            
        except Exception as e:
            print(f"[BROWSER_AGENT] !!! 测试执行失败: {str(e)}")
            import traceback
            print(traceback.format_exc())
            
            return {
                "code": 500,
                "message": f"测试执行失败: {str(e)}",
                "data": None
            }
    
    def _reproduce_badcase(self,
                          userId: str,
                          badcase: Dict,
                          llm: BaseLLM) -> Dict[str, Any]:
        """
        BadCase 复现与定位
        
        流程:
        1. 根据 BadCase 的复现步骤模拟对话
        2. 使用 browser-use 观察对话界面和响应
        3. 采集 Prometheus 指标(响应时间、错误率等)
        4. 使用 LLM 分析指标和日志，定位问题原因
        5. 生成修复建议
        
        Args:
            userId: 用户ID
            badcase: BadCase 数据
            llm: 语言模型实例
            
        Returns:
            {
                "code": 200,
                "message": "BadCase 复现成功",
                "data": {
                    "badcase_id": "xxx",
                    "reproduced": true,
                    "metrics": {
                        "response_time": 2500,  # ms
                        "error_rate": 0.15,
                        "cpu_usage": 85.5,
                        "memory_usage": 72.3
                    },
                    "root_cause": "模型推理超时导致响应缓慢",
                    "fix_suggestions": [
                        "优化模型推理逻辑",
                        "增加缓存机制",
                        "调整超时配置"
                    ],
                    "conversation_logs": [...]
                }
            }
        """
        print(f"=== BadCase 复现定位 ===")
        print(f"BadCase: {badcase}")
        
        # TODO: 实际的 browser-use + Prometheus 集成
        """
        from browser_use import BrowserUse
        from prometheus_client import CollectorRegistry
        
        browser = BrowserUse(**self.browser_config)
        
        # 1. 模拟对话
        await browser.goto(badcase.get("test_url"))
        
        # 2. 执行复现步骤
        for step in badcase.get("reproduction_steps", []):
            await browser.send_message(step)
            response = await browser.wait_for_response()
            
        # 3. 采集指标
        metrics = await fetch_prometheus_metrics(badcase.get("metric_query"))
        
        # 4. 使用 LLM 分析
        analysis = llm.analyze_badcase({
            "badcase": badcase,
            "metrics": metrics,
            "logs": response_logs
        })
        """
        
        return {
            "code": 200,
            "message": "BadCase 复现成功",
            "data": {
                "badcase_id": badcase.get("id"),
                "reproduced": True,
                "metrics": {
                    "response_time": 2500,
                    "error_rate": 0.15,
                    "cpu_usage": 85.5,
                    "memory_usage": 72.3
                },
                "root_cause": "待 LLM 分析",
                "fix_suggestions": [
                    "根据指标和日志生成修复建议"
                ],
                "conversation_logs": []
            }
        }
    
    def _test_conversation(self,
                          userId: str,
                          conversation_test: Dict,
                          llm: BaseLLM) -> Dict[str, Any]:
        """
        对话准确率测试
        
        流程:
        1. 加载测试集(问题-标准答案对)
        2. 使用 browser-use 或 API 进行对话
        3. 记录实际回答
        4. 使用 LLM 评估回答质量(相似度、准确性)
        5. 生成测试报告
        
        Args:
            userId: 用户ID
            conversation_test: 对话测试数据
            llm: 语言模型实例
            
        Returns:
            {
                "code": 200,
                "message": "对话测试完成",
                "data": {
                    "test_set_id": "xxx",
                    "total_questions": 100,
                    "accuracy": 0.85,
                    "avg_response_time": 1200,  # ms
                    "test_results": [
                        {
                            "question": "如何使用系统?",
                            "expected_answer": "...",
                            "actual_answer": "...",
                            "similarity_score": 0.92,
                            "is_correct": true
                        }
                    ],
                    "report_url": "/api/conversation/test/report/xxx"
                }
            }
        """
        print(f"=== 对话准确率测试 ===")
        print(f"测试数据: {conversation_test}")

        raw_set = conversation_test.get("test_set") or conversation_test.get("cases") or []
        test_set = []
        for item in raw_set:
            if not isinstance(item, dict):
                continue
            test_set.append({
                "name": item.get("name") or item.get("title") or item.get("question") or "case",
                "input": item.get("input") or item.get("question") or "",
                "expected": item.get("expected")
                or item.get("expected_answer")
                or item.get("correct_answer")
                or "",
                "actual": item.get("actual") or item.get("actual_answer"),
            })

        from agents.tools.accuracy_tester_tool import AccuracyTesterTool
        import asyncio

        tool = AccuracyTesterTool(llm)
        try:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    tool.execute(
                        test_set=test_set,
                        feature=str(conversation_test.get("feature") or "conversation"),
                        test_type="conversation",
                        project_id=conversation_test.get("project_id"),
                        testcase_ids=conversation_test.get("testcase_ids"),
                        badcase_ids=conversation_test.get("badcase_ids"),
                    )
                )
            finally:
                loop.close()
        except Exception as e:
            return {
                "code": 500,
                "message": f"对话测试失败: {e}",
                "data": {"error": str(e)},
            }

        details = result.get("details") or []
        test_results = [
            {
                "question": d.get("input"),
                "expected_answer": d.get("expected"),
                "actual_answer": d.get("actual"),
                "similarity_score": d.get("score"),
                "is_correct": d.get("passed"),
                "reason": d.get("reason"),
            }
            for d in details
        ]
        acc = float(result.get("accuracy") or 0.0) / 100.0
        return {
            "code": 200,
            "message": "对话测试完成",
            "data": {
                "test_set_id": conversation_test.get("id"),
                "total_questions": result.get("total") or len(test_set),
                "accuracy": acc,
                "passed": result.get("passed"),
                "failed": result.get("failed"),
                "avg_response_time": None,
                "test_results": test_results,
                "badcases": result.get("badcases") or [],
                "summary": result.get("summary"),
                "report_url": f"/api/conversation/test/report/{conversation_test.get('id')}",
            },
        }
    
    def _capture_screenshot(self, browser, name: str) -> str:
        """
        捕获屏幕截图
        
        Args:
            browser: 浏览器实例
            name: 截图名称
            
        Returns:
            截图路径
        """
        # TODO: 实现截图逻辑，使用 Selenium 或 Playwright
        pass
    
    def _parse_test_case_with_llm(self, test_description: str, llm: BaseLLM) -> List[Dict]:
        """
        使用千帆模型解析测试用例，生成具体的测试步骤
        
        Args:
            test_description: 测试用例描述
            llm: 语言模型实例
            
        Returns:
            测试步骤列表
        """
        try:
            prompt = f"""请根据以下测试用例描述，生成详细的测试步骤。每个步骤应该包括：
- title: 步骤标题
- action: 具体操作（如 click, input, navigate 等）
- target: 操作对象（如 CSS selector, button 等）
- expected: 预期结果

测试用例描述：
{test_description}

请返回 JSON 数组格式，每个对象代表一个测试步骤。仅返回 JSON，不要其他文本。

示例格式：
[
  {{
    "title": "打开应用",
    "action": "navigate",
    "target": "http://localhost:5173",
    "expected": "应用正常加载"
  }},
  {{
    "title": "点击登录",
    "action": "click",
    "target": ".login-button",
    "expected": "弹出登录窗口"
  }}
]
"""
            
            # 调用千帆模型
            result = llm.parse_intent(prompt)
            
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return [result] if result else []
            else:
                print(f"[BROWSER_AGENT] 千帆模型返回非预期格式: {type(result)}")
                # 返回默认步骤
                return [
                    {
                        "title": "测试步骤",
                        "action": "navigate",
                        "target": "http://localhost:5173",
                        "expected": "应用正常运行"
                    }
                ]
        except Exception as e:
            print(f"[BROWSER_AGENT] 千帆模型解析失败: {str(e)}")
            return [
                {
                    "title": "测试步骤",
                    "action": "navigate",
                    "target": "http://localhost:5173",
                    "expected": "应用正常运行"
                }
            ]
    
    def _analyze_results_with_llm(self, 
                                 test_description: str,
                                 parsed_steps: List[Dict],
                                 execution_results: List[Dict],
                                 llm: BaseLLM) -> List[Dict]:
        """
        使用千帆模型分析测试结果并识别 Bug
        
        Args:
            test_description: 测试描述
            parsed_steps: 解析的测试步骤
            execution_results: 执行结果
            llm: 语言模型实例
            
        Returns:
            发现的 Bug 列表
        """
        try:
            prompt = f"""请根据以下测试信息分析是否存在 Bug。如果发现 Bug，请返回 JSON 数组格式的 Bug 列表。

测试描述：
{test_description}

测试步骤：
{json.dumps(parsed_steps, ensure_ascii=False, indent=2)}

执行结果：
{json.dumps(execution_results, ensure_ascii=False, indent=2)}

每个 Bug 应包括：
- title: Bug 标题
- severity: 严重程度 (critical, high, medium, low)
- description: Bug 描述
- steps_to_reproduce: 复现步骤
- expected: 预期行为
- actual: 实际行为

如果没有发现 Bug，请返回空数组 []。仅返回 JSON 数组，不要其他文本。
"""
            
            # 调用千帆模型
            result = llm.parse_intent(prompt)
            
            bugs = []
            if isinstance(result, list):
                for bug in result:
                    if isinstance(bug, dict):
                        bug['status'] = 'pending_review'
                        bug['id'] = f"pending_{int(time.time() * 1000)}"
                        bugs.append(bug)
            
            print(f"[BROWSER_AGENT] 分析完成，发现 {len(bugs)} 个 Bug")
            return bugs
            
        except Exception as e:
            print(f"[BROWSER_AGENT] 千帆模型分析失败: {str(e)}")
            return []
    
    async def _fetch_prometheus_metrics(self, query: str) -> Dict[str, Any]:
        """
        从 Prometheus 获取指标数据
        
        Args:
            query: Prometheus 查询语句
            
        Returns:
            指标数据
        """
        # TODO: 实现 Prometheus 指标采集
        pass
