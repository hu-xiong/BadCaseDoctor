# -*- coding: utf-8 -*-
"""终端会话日志记录模块"""
import os
import json
import time
import uuid
from typing import List, Dict, Optional

class TerminalLogger:
    def __init__(self):
        self.log_dir = os.path.expanduser('~/.badcase/logs')
        os.makedirs(self.log_dir, exist_ok=True)
        self.active_sessions = {}
    
    def create_session(self) -> str:
        """创建新的会话"""
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        log_path = os.path.join(self.log_dir, f"{session_id}.log")
        self.active_sessions[session_id] = {
            'path': log_path,
            'start_time': time.time(),
            'lines': 0
        }
        return session_id
    
    def log_output(self, session_id: str, stream: str, content: str) -> None:
        """记录终端输出"""
        if session_id not in self.active_sessions:
            return
        
        log_path = self.active_sessions[session_id]['path']
        with open(log_path, 'a', encoding='utf-8') as f:
            for line in content.split('\n'):
                if line:
                    timestamp = time.time()
                    f.write(f"[{stream}] {timestamp} {line}\n")
                    self.active_sessions[session_id]['lines'] += 1
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """获取会话信息"""
        return self.active_sessions.get(session_id)
    
    def list_sessions(self) -> List[str]:
        """列出所有会话"""
        sessions = []
        for filename in os.listdir(self.log_dir):
            if filename.endswith('.log') and filename.startswith('session_'):
                session_id = filename.replace('.log', '')
                sessions.append(session_id)
        return sessions
    
    def read_log_range(self, session_id: str, start_line: int, end_line: int) -> List[str]:
        """读取指定行范围的日志"""
        log_path = os.path.join(self.log_dir, f"{session_id}.log")
        if not os.path.exists(log_path):
            return []
        
        lines = []
        current_line = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                current_line += 1
                if start_line <= current_line <= end_line:
                    lines.append(line.rstrip())
                elif current_line > end_line:
                    break
        
        return lines
    
    def close_session(self, session_id: str) -> None:
        """关闭会话"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]

# 全局实例
terminal_logger = TerminalLogger()
