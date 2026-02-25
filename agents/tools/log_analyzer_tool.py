# agents/tools/log_analyzer_tool.py
"""
日志分析工具
分析日志找出问题根因
"""

import json
from typing import Dict, Any
from ..tool_registry import BaseTool


class LogAnalyzerTool(BaseTool):
    """日志分析工具"""
    
    def __init__(self, llm):
        """
        初始化日志分析工具
        
        Args:
            llm: 语言模型实例
        """
        super().__init__(
            name='log_analyzer',
            description='分析日志找出问题根因、堆栈追踪等'
        )
        self.llm = llm
    
    async def execute(
        self,
        log_source: str = None,
        error_type: str = None,
        time_range: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行日志分析
        
        Args:
            log_source: 日志来源 (file_path/server_logs/database_logs/application_logs)
            error_type: 错误类型
            time_range: 时间范围
            **kwargs: 其他参数
            
        Returns:
            分析结果
        """
        if not log_source:
            # 兼容性处理
            log_source = kwargs.get('source') or kwargs.get('path') or kwargs.get('target') or kwargs.get('log_source')
            
        if not log_source:
            # 兜底：默认分析应用日志
            log_source = 'application_logs'
            print(f"[LOG_ANALYZER] ⚠️ 未指定 log_source，默认使用 application_logs")
            
        print(f"[LOG_ANALZER] 📖 分析日志: {log_source}")
        
        # 1️⃣ 获取日志
        logs = await self._fetch_logs(log_source, time_range)
        
        if not logs:
            return {
                'error': f'无法获取日志: {log_source}',
                'success': False
            }
        
        # 2️⃣ 使用 LLM 分析日志
        analysis = await self._analyze_with_llm(logs, error_type)
        
        return analysis
    
    async def _fetch_logs(self, log_source: str, time_range: str = None) -> str:
        """
        获取日志
        
        实际应用中应该从真实日志系统获取
        """
        print(f"[LOG_ANALYZER] 📥 获取日志: {log_source}")
        
        # 模拟日志数据
        mock_logs = {
            'application': """
2024-01-26 10:15:23 ERROR [main] Failed to connect to database
  java.sql.SQLException: Connection timeout
  at com.mysql.jdbc.ConnectionImpl.createNewIO(ConnectionImpl.java:2343)
  at com.mysql.jdbc.ConnectionImpl.<init>(ConnectionImpl.java:717)
  ...
2024-01-26 10:15:24 ERROR [auth] Invalid user credentials
2024-01-26 10:15:25 ERROR [api] 500 Internal Server Error
""",
            'server': """
[2024-01-26 10:15:23] nginx error: connect() failed
[2024-01-26 10:15:24] backend service unavailable
[2024-01-26 10:15:25] memory usage: 95%
""",
            'database': """
2024-01-26 10:15:22 ERROR: too many connections
2024-01-26 10:15:23 ERROR: connection timeout
2024-01-26 10:15:24 ERROR: query execution timeout
"""
        }
        
        # 返回对应的模拟日志
        for key, value in mock_logs.items():
            if key in log_source:
                return value
        
        return mock_logs.get('application', '')
    
    async def _analyze_with_llm(self, logs: str, error_type: str = None) -> Dict[str, Any]:
        """
        使用 LLM 分析日志
        """
        print(f"[LOG_ANALYZER] 🔍 LLM 分析中...")
        
        prompt = f"""
分析以下日志，找出问题根因。

{f"错误类型: {error_type}" if error_type else ""}

日志内容:
```
{logs}
```

请进行根因分析，返回 JSON 格式（仅返回 JSON，不要其他文本）:
{{
    "root_cause": "根本原因（一句话总结）",
    "severity": "critical/high/medium/low",
    "affected_component": "受影响的组件",
    "error_code": "错误代码（如有）",
    "timestamp": "问题发生时间",
    "affected_users": "受影响用户数（如有）",
    "recommendations": [
        "建议1",
        "建议2",
        "建议3"
    ],
    "related_errors": [
        "相关错误1",
        "相关错误2"
    ],
    "potential_fix": "可能的修复方案"
}}
"""
        
        response = await self.llm.parse_intent(prompt)
        
        # 解析 JSON
        try:
            if isinstance(response, str):
                start = response.find('{')
                end = response.rfind('}') + 1
                if start != -1 and end > start:
                    analysis = json.loads(response[start:end])
                else:
                    analysis = json.loads(response)
            else:
                analysis = response if isinstance(response, dict) else {}
        except json.JSONDecodeError:
            analysis = {
                'root_cause': '无法解析日志',
                'severity': 'medium',
                'recommendations': []
            }
        
        analysis['success'] = True
        analysis['query_type'] = 'log_analysis'
        
        return analysis
