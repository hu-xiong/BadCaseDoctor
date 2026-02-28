"""
Text2SQL SQL执行器
安全执行 SQL 查询，包含结果限制和性能监控
"""

import sqlite3
import time
from typing import Dict, Any, List, Optional
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class SQLExecutorConfig:
    """SQL执行器配置"""
    max_result_rows: int = 1000
    query_timeout: int = 30  #秒    enable_result_truncation: bool = True
    allow_write_operations: bool = False  # 默认只读


class SQLExecutor:
    """安全 SQL执行器"""
    
    def __init__(self, database_path: str = "instance/badcase_doctor.db", 
                 config: SQLExecutorConfig = None):
        self.database_path = database_path
        self.config = config or SQLExecutorConfig()
        print(f"[SQL_EXECUTOR] 初始化执行器: {database_path}")
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = None
        try:
            conn = sqlite3.connect(
                self.database_path,
                timeout=self.config.query_timeout,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row  # 返回字典格式结果
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()
    
    def execute_query(self, sql: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        安全执行 SQL 查询
        
        Args:
            sql: SQL 语句
            params: 参数字典（用于参数化查询）
            
        Returns:
           执行结果
        """
        start_time = time.time()
        
        try:
            # 1.安全检查
            security_check = self._pre_execute_check(sql)
            if not security_check['allowed']:
                return {
                    'success': False,
                    'error': security_check['reason'],
                    'sql': sql
                }
            
            # 2.执行查询
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 设置查询超时
                cursor.execute(f"PRAGMA busy_timeout = {self.config.query_timeout * 1000}")
                
                # 执行 SQL
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                
                # 获取结果
                if sql.strip().upper().startswith('SELECT'):
                    results = [dict(row) for row in cursor.fetchall()]
                    row_count = len(results)
                    
                    # 结果限制
                    if self.config.enable_result_truncation and row_count > self.config.max_result_rows:
                        results = results[:self.config.max_result_rows]
                        print(f"[SQL_EXECUTOR] 结果已截断为 {self.config.max_result_rows} 行")
                else:
                    # 语句（INSERT/UPDATE/DELETE）
                    conn.commit()
                    results = []
                    row_count = cursor.rowcount
                
                execution_time = time.time() - start_time
                
                return {
                    'success': True,
                    'results': results,
                    'row_count': row_count,
                    'execution_time': execution_time,
                    'sql': sql
                }
                
        except sqlite3.OperationalError as e:
            return {
                'success': False,
                'error': f'数据库操作错误: {str(e)}',
                'sql': sql,
                'execution_time': time.time() - start_time
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'执行失败: {str(e)}',
                'sql': sql,
                'execution_time': time.time() - start_time
            }
    
    def _pre_execute_check(self, sql: str) -> Dict[str, Any]:
        """执行前安全检查"""
        sql_upper = sql.upper().strip()
        
        # 检查是否允许写操作
        write_operations = ['INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER']
        has_write = any(op in sql_upper for op in write_operations)
        
        if has_write and not self.config.allow_write_operations:
            return {
                'allowed': False,
                'reason': '写操作被禁用，当前配置为只读模式'
            }
        
        # 检查危险操作
        dangerous_patterns = [
            r'\bDROP\b', r'\bTRUNCATE\b', r'\bDELETE\s+FROM.*WHERE\s+1=1\b'
        ]
        
        import re
        for pattern in dangerous_patterns:
            if re.search(pattern, sql_upper):
                return {
                    'allowed': False,
                    'reason': f'检测到危险操作: {pattern}'
                }
        
        return {'allowed': True}
    
    def execute_batch(self, queries: List[str]) -> List[Dict[str, Any]]:
        """批量执行查询"""
        results = []
        for i, sql in enumerate(queries):
            print(f"[SQL_EXECUTOR]执行第 {i+1}/{len(queries)} 个查询")
            result = self.execute_query(sql)
            results.append(result)
        return results
    
    def get_table_stats(self, table_name: str) -> Dict[str, Any]:
        """获取表统计信息"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                #行统计
                cursor.execute(f"SELECT COUNT(*) as row_count FROM {table_name}")
                row_count = cursor.fetchone()[0]
                
                #列信息
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [dict(row) for row in cursor.fetchall()]
                
                return {
                    'table_name': table_name,
                    'row_count': row_count,
                    'column_count': len(columns),
                    'columns': columns
                }
                
        except Exception as e:
            return {
                'error': str(e),
                'table_name': table_name
            }
    
    def test_connection(self) -> Dict[str, Any]:
        """测试数据库连接"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                return {
                    'success': True,
                    'message': '数据库连接正常',
                    'test_result': result[0]
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


#全局实例
sql_executor = None

def get_sql_executor(database_path: str = "instance/badcase_doctor.db", 
                    config: SQLExecutorConfig = None):
    """获取全局 SQL执行器实例"""
    global sql_executor
    if sql_executor is None:
        sql_executor = SQLExecutor(database_path, config)
    return sql_executor