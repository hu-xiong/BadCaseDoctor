# -*- coding: utf-8 -*-
"""临时文件管理工具"""
import os
import time
import shutil
from typing import List

class TempFileManager:
    def __init__(self):
        self.temp_dir = os.path.expanduser('~/.badcase/tmp')
        os.makedirs(self.temp_dir, exist_ok=True)
        self.max_age = 24 * 3600  # 24小时
    
    def clean_expired(self) -> int:
        """清理过期的临时文件"""
        now = time.time()
        cleaned = 0
        
        for filename in os.listdir(self.temp_dir):
            file_path = os.path.join(self.temp_dir, filename)
            if os.path.isfile(file_path):
                mtime = os.path.getmtime(file_path)
                if now - mtime > self.max_age:
                    try:
                        os.remove(file_path)
                        cleaned += 1
                    except:
                        pass
        
        return cleaned
    
    def get_temp_file(self, prefix: str = "temp") -> str:
        """获取临时文件路径"""
        import uuid
        filename = f"{prefix}_{uuid.uuid4().hex[:8]}.txt"
        return os.path.join(self.temp_dir, filename)
    
    def list_files(self) -> List[str]:
        """列出所有临时文件"""
        files = []
        for filename in os.listdir(self.temp_dir):
            file_path = os.path.join(self.temp_dir, filename)
            if os.path.isfile(file_path):
                files.append(file_path)
        return files
    
    def clear_all(self) -> int:
        """清理所有临时文件"""
        cleared = 0
        for filename in os.listdir(self.temp_dir):
            file_path = os.path.join(self.temp_dir, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    cleared += 1
                except:
                    pass
        return cleared

# 全局实例
temp_file_manager = TempFileManager()

# 定期清理
import atexit
def cleanup_at_exit():
    temp_file_manager.clean_expired()

atexit.register(cleanup_at_exit)
