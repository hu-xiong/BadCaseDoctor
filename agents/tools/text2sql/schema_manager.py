"""
Text2SQL Schema管理器
自动发现和缓存数据库表结构信息
"""

import sqlite3
import json
from typing import Dict, List, Any
from datetime import datetime


class SchemaManager:
    """数据库 Schema管理器"""
    
    def __init__(self, database_path: str):
        self.database_path = database_path
        self._schema_cache = None
        self._cache_timestamp = None
    
    def get_schema_info(self) -> Dict[str, Any]:
        """
        获取数据库 Schema信息（带缓存）
        
        Returns:
            {
                'tables': [
                    {
                        'name': str,
                        'columns': [
                            {'name': str, 'type': str, 'nullable': bool}
                        ]
                    }
                ],
                'generated_at': str
            }
        """
        #检查缓存是否有效（5分钟内）
        if self._schema_cache and self._cache_timestamp:
            cache_age = (datetime.now() - self._cache_timestamp).total_seconds()
            if cache_age < 300:  # 5分钟
                return self._schema_cache
        
        # 重新加载 Schema
        schema_info = self._load_schema_from_database()
        self._schema_cache = schema_info
        self._cache_timestamp = datetime.now()
        
        return schema_info
    
    def _load_schema_from_database(self) -> Dict[str, Any]:
        """从数据库加载 Schema 信息"""
        tables = []
        
        try:
            conn = sqlite3.connect(self.database_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 获取所有表名
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            table_names = [row[0] for row in cursor.fetchall()]
            
            # 为每个表获取列信息
            for table_name in table_names:
                # 获取表的列信息
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = []
                for row in cursor.fetchall():
                    columns.append({
                        'name': row['name'],
                        'type': row['type'],
                        'nullable': row['notnull'] == 0,
                        'primary_key': row['pk'] == 1
                    })
                
                tables.append({
                    'name': table_name,
                    'columns': columns
                })
            
            conn.close()
            
        except Exception as e:
            print(f"[SCHEMA_MANAGER] 加载Schema失败: {e}")
            return {'tables': [], 'error': str(e)}
        
        return {
            'tables': tables,
            'generated_at': datetime.now().isoformat()
        }
    
    def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """获取指定表的列信息"""
        schema_info = self.get_schema_info()
        for table in schema_info['tables']:
            if table['name'] == table_name:
                return table['columns']
        return []
    
    def get_table_names(self) -> List[str]:
        """获取所有表名"""
        schema_info = self.get_schema_info()
        return [table['name'] for table in schema_info['tables']]
    
    def refresh_schema(self) -> Dict[str, Any]:
        """强制刷新 Schema缓存"""
        self._schema_cache = None
        self._cache_timestamp = None
        return self.get_schema_info()


#全局实例
schema_manager = None

def get_schema_manager(database_path: str = "instance/badcase_doctor.db"):
    """获取全局 Schema管器实例"""
    global schema_manager
    if schema_manager is None:
        schema_manager = SchemaManager(database_path)
    return schema_manager