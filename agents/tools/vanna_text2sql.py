"""
Vanna AI模块
将开源的 Vanna Text2SQL集成到项目中
"""

import os
import sqlite3
from typing import Dict, Any, List, Optional
import pandas as pd

# Vanna AI
try:
    from vanna.base import VannaBase
    from vanna.sqlite import SQLiteVanna
    VANNA_AVAILABLE = True
except ImportError:
    VANNA_AVAILABLE = False
    print("[VANNA]⚠  Vanna 未安装")


class VannaText2SQL:
    """Vanna AI Text2SQL"""
    
    def __init__(self, database_path: str = "instance/badcase_doctor.db"):
        """
        初始化 Vanna Text2SQL
        
        Args:
            database_path: SQLite 数据库路径
        """
        if not VANNA_AVAILABLE:
            raise ImportError("Vanna AI 未安装，请运行: pip install vanna")
        
        self.database_path = database_path
        self.vn = None
        self._setup_vanna()
    
    def _setup_vanna(self):
        """设置 Vanna连接"""
        try:
            # 初始化 SQLite Vanna
            self.vn = SQLiteVanna(
                config={
                    'database': self.database_path
                }
            )
            
            #训模型
            self._train_model()
            print(f"[VANNA]✅ Vanna已初始化，数据库: {self.database_path}")
            
        except Exception as e:
            print(f"[VANNA] ❌ 初始化失败: {e}")
            raise
    
    def _train_model(self):
        """训练 Vanna模型"""
        try:
            #连接数据库获取表结构
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # 获取所有表名
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            # 为每个表训练
            for table_row in tables:
                table_name = table_row[0]
                if table_name in ['sqlite_sequence']:  #跳过系统表
                    continue
                
                print(f"[VANNA]📊训表: {table_name}")
                
                # 获取表的列信息
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                #构建训练数据
                for column in columns:
                    column_name = column[1]
                    column_type = column[2]
                    
                    # 添加列信息到训练数据
                    training_text = f"表 {table_name}包含列 {column_name}，类型为 {column_type}"
                    self.vn.train(documentation=training_text)
            
            conn.close()
            print(f"[VANNA]✅模型训练完成")
            
        except Exception as e:
            print(f"[VANNA]⚠️ 训失败: {e}")
    
    def query(self, natural_query: str) -> Dict[str, Any]:
        """
        自然语言查询
        
        Args:
            natural_query: 自然语言查询语句
            
        Returns:
            查询结果
        """
        try:
            print(f"[VANNA]🗣 自然语言查询: {natural_query}")
            
            # 使用 Vanna 生成 SQL
            sql_query = self.vn.generate_sql(natural_query)
            print(f"[VANNA] ✅ 生成 SQL: {sql_query}")
            
            #执行查询
            df = self.vn.run_sql(sql_query)
            
            #结果格式
            results = []
            if not df.empty:
                results = df.to_dict('records')
            
            return {
                'success': True,
                'natural_query': natural_query,
                'generated_sql': sql_query,
                'results': results,
                'row_count': len(results),
                'columns': list(df.columns) if not df.empty else []
            }
            
        except Exception as e:
            print(f"[VANNA]❌ 查询失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'natural_query': natural_query
            }
    
    def get_schema_info(self) -> Dict[str, Any]:
        """获取数据库 Schema 信息"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # 获取表信息
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            schema_info = {
                'tables': []
            }
            
            for table_row in tables:
                table_name = table_row[0]
                if table_name in ['sqlite_sequence']:
                    continue
                
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                table_info = {
                    'name': table_name,
                    'columns': [
                        {
                            'name': col[1],
                            'type': col[2],
                            'nullable': col[3] == 0,
                            'primary_key': col[5] == 1
                        }
                        for col in columns
                    ]
                }
                schema_info['tables'].append(table_info)
            
            conn.close()
            return schema_info
            
        except Exception as e:
            return {'error': str(e), 'tables': []}


#全局实例
vanna_text2sql = None

def get_vanna_text2sql(database_path: str = "instance/badcase_doctor.db"):
    """获取 Vanna Text2SQL 实例"""
    global vanna_text2sql
    if vanna_text2sql is None:
        vanna_text2sql = VannaText2SQL(database_path)
    return vanna_text2sql


#兼性函数
def quick_query(query: str, database_path: str = "instance/badcase_doctor.db") -> Dict[str, Any]:
    """
   快速查询函数（兼容旧接口）
    
    Args:
        query: 自然语言查询
        database_path: 数据库路径
        
    Returns:
        查询结果
    """
    try:
        vanna = get_vanna_text2sql(database_path)
        return vanna.query(query)
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'natural_query': query
        }