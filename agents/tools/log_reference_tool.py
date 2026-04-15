# -*- coding: utf-8 -*-
"""终端日志引用解析工具"""
import re
import os
from typing import Dict, Optional

from agents.tool_registry import BaseTool
from agents.tools.terminal_logger import terminal_logger

class LogReferenceTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="resolve_log_ref",
            description=(
                "解析终端日志引用并提取对应内容。"  
                "引用格式：@log:session_<id>#L<start>-L<end>"  
                "例如：@log:session_123#L100-L200 表示从会话123的日志中提取第100-200行。"  
                "参数：reference（必填，引用字符串）"  
                "返回：提取的内容或错误信息。"
            ),
        )
    
    def parse_reference(self, reference: str) -> Optional[Dict]:
        """解析引用字符串"""
        # 支持两种格式：
        # 1. 旧格式：@log:session_<id>#L<start>-L<end>
        # 2. 新格式：📱 Terminal <start>-<end>
        
        # 尝试匹配新格式
        new_pattern = r'📱 Terminal (\d+)-(\d+)'
        new_match = re.match(new_pattern, reference)
        if new_match:
            start_line = int(new_match.group(1))
            end_line = int(new_match.group(2))
            if start_line > end_line:
                return None
            return {
                'session_id': 'default',  # 使用默认会话
                'start_line': start_line,
                'end_line': end_line
            }
        
        # 尝试匹配旧格式
        old_pattern = r'@log:(session_[a-f0-9]+)#L(\d+)-L(\d+)'
        old_match = re.match(old_pattern, reference)
        if old_match:
            session_id = old_match.group(1)
            start_line = int(old_match.group(2))
            end_line = int(old_match.group(3))
            if start_line > end_line:
                return None
            return {
                'session_id': session_id,
                'start_line': start_line,
                'end_line': end_line
            }
        
        return None
    
    async def execute(self, **kwargs: Dict) -> Dict:
        reference = str(kwargs.get("reference") or "").strip()
        if not reference:
            return {
                "success": False,
                "error": "缺少 reference 参数",
                "message": "缺少 reference 参数"
            }
        
        parsed = self.parse_reference(reference)
        if not parsed:
            return {
                "success": False,
                "error": "无效的引用格式，请使用 @log:session_<id>#L<start>-L<end> 格式",
                "message": "无效的引用格式"
            }
        
        session_id = parsed['session_id']
        start_line = parsed['start_line']
        end_line = parsed['end_line']
        
        # 读取日志内容
        lines = terminal_logger.read_log_range(session_id, start_line, end_line)
        if not lines:
            return {
                "success": False,
                "error": f"未找到会话 {session_id} 的日志内容",
                "message": "未找到日志内容"
            }
        
        content = "\n".join(lines)
        
        # 生成临时文件
        temp_dir = os.path.join(os.path.expanduser('~/.badcase/tmp'))
        os.makedirs(temp_dir, exist_ok=True)
        
        import uuid
        temp_file = os.path.join(temp_dir, f"log_ref_{uuid.uuid4().hex[:8]}.txt")
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return {
            "success": True,
            "content": content,
            "file_path": temp_file,
            "message": f"成功提取会话 {session_id} 的第 {start_line}-{end_line} 行",
            "summary": f"提取了 {len(lines)} 行日志内容"
        }

# 注册工具
from agents.tool_registry import tool_registry
log_reference_tool = LogReferenceTool()
tool_registry.register_tool(log_reference_tool)
