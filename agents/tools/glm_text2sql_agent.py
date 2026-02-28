"""
GLM Text2SQL Agent
专为GLM模型优化的文本到SQL转换代理
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
import sqlite3
from llm.factory import get_llm

class GLMText2SQLAgent:
    """GLM Text2SQL代理"""
    
    def __init__(self, 
                 database_path: str = "instance/badcase_doctor.db",
                 llm_model: str = "glm-4"):
        """
        初始化GLM Text2SQL代理
        
        Args:
            database_path: 数据库路径
            llm_model: GLM模型名称
        """
        self.database_path = database_path
        self.llm_model = llm_model
        self.llm = get_llm(provider="zhipu", model=self.llm_model)
        
        # 获取数据库schema
        self.schema_info = self._load_schema_info()
        
        print(f"[GLM Text2SQL] 初始化完成，使用模型: {self.llm_model}")
        print(f"[GLM Text2SQL] 数据库: {database_path}")
    
    def _load_schema_info(self) -> Dict[str, Any]:
        """加载数据库schema信息"""
        if not os.path.exists(self.database_path):
            return {"tables": {}}
        
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # 获取所有表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            schema_info = {"tables": {}}
            
            for table in tables:
                table_name = table[0]
                # 获取表的列信息
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                
                column_info = []
                for col in columns:
                    column_info.append({
                        "name": col[1],
                        "type": col[2],
                        "not_null": col[3] == 1,
                        "default": col[4],
                        "primary_key": col[5] == 1
                    })
                
                schema_info["tables"][table_name] = {
                    "columns": column_info
                }
            
            return schema_info
        
        except Exception as e:
            print(f"[GLM Text2SQL] 加载schema失败: {str(e)}")
            return {"tables": {}}
    
    def generate_sql(self, question: str) -> str:
        """
        根据自然语言问题生成SQL查询
        
        Args:
            question: 自然语言问题
            
        Returns:
            str: 生成的SQL语句
        """
        # 构造提示词
        prompt = self._build_prompt(question)
        
        # 调用GLM模型
        response = self.llm.generate(prompt)
        
        # 提取SQL语句
        sql = self._extract_sql(response)
        
        return sql
    
    def _build_prompt(self, question: str) -> str:
        """构造GLM提示词"""
        schema_str = json.dumps(self.schema_info, indent=2, ensure_ascii=False)
        
        prompt = f"""你是一个专业的SQL生成助手。根据以下数据库schema和用户问题，生成正确的SQL查询语句。

数据库schema:
{schema_str}

用户问题: {question}

请只返回SQL语句，不要包含任何解释或注释。确保SQL语法正确且符合schema结构。"""
        
        return prompt
    
    def _extract_sql(self, response: str) -> str:
        """从模型响应中提取SQL语句"""
        # 简单实现：直接返回响应内容
        # 实际应用中可能需要更复杂的解析逻辑
        return response.strip()
    
    def execute_sql(self, sql: str, limit: int = 100) -> Dict[str, Any]:
        """
        执行SQL查询并返回结果
        
        Args:
            sql: SQL查询语句
            limit: 结果限制数量
            
        Returns:
            Dict: 执行结果
        """
        if not self._is_safe_sql(sql):
            return {
                'success': False,
                'error': '不安全的SQL语句',
                'message': '只允许执行SELECT查询'
            }
        
        try:
            conn = sqlite3.connect(self.database_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 添加LIMIT（如果需要）
            if "limit" not in sql.lower() and limit:
                sql = self._add_limit_to_sql(sql, limit)
            
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            # 转换为字典列表
            data = [dict(row) for row in rows]
            
            # 获取列名
            columns = [description[0] for description in cursor.description] if cursor.description else []
            
            return {
                'success': True,
                'data': data,
                'columns': columns,
                'row_count': len(data)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'sql': sql
            }
    
    def _is_safe_sql(self, sql: str) -> bool:
        """检查SQL是否安全"""
        sql_lower = sql.lower()
        
        # 危险操作检查
        dangerous_operations = [
            'drop ', 'truncate ', 'delete from', 'update ', 'alter ',
            'create ', 'insert into', 'grant ', 'revoke ',
            'exec ', 'execute ', 'xp_', 'sp_'
        ]
        
        for op in dangerous_operations:
            if op in sql_lower:
                return False
        
        # 必须是SELECT语句开头
        if not sql_lower.strip().startswith('select'):
            return False
        
        return True
    
    def _add_limit_to_sql(self, sql: str, limit: int) -> str:
        """为SQL添加LIMIT子句"""
        sql = sql.rstrip(';').strip()
        return f"{sql} LIMIT {limit}"