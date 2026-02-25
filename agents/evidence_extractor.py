# agents/evidence_extractor.py
"""
执行证据提取器 - 从工具结果中智能提取执行证据
用于向前端展示"真实执行发生了什么"
"""

import json
from typing import Dict, Any, List


class EvidenceExtractor:
    """从工具执行结果中提取证据"""
    
    @staticmethod
    def extract_from_observation(tool_name: str, params: Dict[str, Any], observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        从工具执行结果中提取执行证据
        
        Args:
            tool_name: 工具名称（如 browser_test, database_query 等）
            params: 工具参数
            observation: 工具执行结果
            
        Returns:
            结构化的执行证据
        """
        evidence = {
            'tool_used': tool_name,
            'tool_params': params,
            'url_accessed': None,
            'execution_time_ms': None,
            'results': [],
            'status': 'unknown'
        }
        
        if not isinstance(observation, dict):
            return evidence
        
        # 1. 提取 URL
        evidence['url_accessed'] = observation.get('url') or observation.get('target_url') or params.get('url')
        
        # 2. 提取执行时间
        for time_key in ['duration', 'execution_time', 'elapsed_time', 'time_taken']:
            if time_key in observation:
                time_val = observation[time_key]
                # 转换为毫秒
                if isinstance(time_val, (int, float)):
                    evidence['execution_time_ms'] = int(time_val * 1000) if time_val < 1000 else int(time_val)
                break
        
        # 3. 提取结果内容（按优先级）
        result_keys = ['bugs_found', 'elements_found', 'issues_found', 'data', 'results', 'output']
        for key in result_keys:
            if key in observation and observation[key]:
                value = observation[key]
                if isinstance(value, list):
                    evidence['results'].extend([str(item) for item in value])
                elif isinstance(value, dict):
                    evidence['results'].append(json.dumps(value, ensure_ascii=False))
                else:
                    evidence['results'].append(str(value))
        
        # 4. 提取执行状态
        evidence['status'] = 'success' if observation.get('success', True) else 'failure'
        
        return evidence
    
    @staticmethod
    def format_evidence_for_display(evidence: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化执行证据供前端展示
        
        Returns:
            包含人类可读文本的证据格式
        """
        display = {
            'evidence_text': [],
            'evidence_structured': evidence
        }
        
        # 构建人类可读的证据描述
        text_parts = []
        
        if evidence.get('tool_used'):
            tool_name = evidence['tool_used']
            text_parts.append(f"🔧 使用工具: {tool_name}")
        
        if evidence.get('url_accessed'):
            text_parts.append(f"🌐 访问 URL: {evidence['url_accessed']}")
        
        if evidence.get('tool_params'):
            params_str = json.dumps(evidence['tool_params'], ensure_ascii=False)
            text_parts.append(f"⚙️ 工具参数: {params_str}")
        
        if evidence.get('execution_time_ms'):
            ms = evidence['execution_time_ms']
            if ms >= 1000:
                time_str = f"{ms / 1000:.2f}s"
            else:
                time_str = f"{ms}ms"
            text_parts.append(f"⏱️ 执行耗时: {time_str}")
        
        if evidence.get('results'):
            text_parts.append(f"📊 执行结果 ({len(evidence['results'])} 项):")
            for i, result in enumerate(evidence['results'][:10], 1):  # 最多显示10项
                # 截断过长的结果
                result_display = result[:100] + '...' if len(result) > 100 else result
                text_parts.append(f"   {i}. {result_display}")
            if len(evidence['results']) > 10:
                text_parts.append(f"   ... 还有 {len(evidence['results']) - 10} 项结果")
        
        if evidence.get('status'):
            status_icon = '✅' if evidence['status'] == 'success' else '❌'
            text_parts.append(f"{status_icon} 执行状态: {evidence['status']}")
        
        display['evidence_text'] = text_parts
        return display
    
    @staticmethod
    def format_as_findings(evidence: Dict[str, Any]) -> List[str]:
        """
        将执行证据转换为 findings 列表
        
        Returns:
            可直接作为 ReAct findings 的列表
        """
        findings = []
        
        # 添加工具链路证据
        if evidence.get('tool_used'):
            finding = f"🔧 使用 {evidence['tool_used']} 工具"
            if evidence.get('url_accessed'):
                finding += f" (访问: {evidence['url_accessed']})"
            findings.append(finding)
        
        # 添加执行时间证据
        if evidence.get('execution_time_ms'):
            ms = evidence['execution_time_ms']
            if ms >= 1000:
                time_str = f"{ms / 1000:.2f}s"
            else:
                time_str = f"{ms}ms"
            findings.append(f"⏱️ 执行耗时: {time_str}")
        
        # 添加结果内容证据
        if evidence.get('results'):
            for result in evidence['results'][:20]:  # 最多20项
                findings.append(f"📋 {result}")
        
        # 添加状态证据
        if evidence.get('status') == 'success':
            findings.append("✅ 执行成功")
        elif evidence.get('status') == 'failure':
            findings.append("❌ 执行失败")
        
        return findings
