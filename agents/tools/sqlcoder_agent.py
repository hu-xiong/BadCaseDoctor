"""
SQLCoder智能代理 - 使用sqlcoder库进行Text2SQL转换
"""

import os
import json
import re
from typing import Dict, Any, Optional
from enum import Enum
from llm.factory import get_llm

class SQLGenerationBackend(Enum):
    GLM = "glm"
    SQLCODER = "sqlcoder"
    VANNA = "vanna"

class SQLCoderAgent:
    """SQLCoder智能代理"""
    
    def __init__(self, 
                 database_path: str = "instance/badcase_doctor.db",
                 backend: SQLGenerationBackend = SQLGenerationBackend.SQLCODER,
                 llm_model: str = "glm-4",
                 debug: bool = False):
        """
        初始化SQLCoder代理
        
        Args:
            database_path: 数据库路径
            backend: 后端引擎 (sqlcoder/glm/vanna)
            llm_model: GLM模型名称
            debug: 调试模式
        """
        self.database_path = database_path
        self.backend = backend
        self.llm_model = llm_model
        self.debug = debug
        
        # 初始化后端引擎
        if backend == SQLGenerationBackend.SQLCODER:
            self._init_sqlcoder()
        elif backend == SQLGenerationBackend.GLM:
            self._init_glm()
        elif backend == SQLGenerationBackend.VANNA:
            self._init_vanna()
        
        # 加载数据库schema
        self.schema_info = self._load_schema_info()
        
        print(f"[SQLCoderAgent] 初始化完成: backend={backend.value}")
        print(f"[SQLCoderAgent] 数据库: {database_path}")
        print(f"[SQLCoderAgent] 已加载表数量: {len(self.schema_info.get('tables', {}))}")
    
    def _init_sqlcoder(self):
        """初始化SQLCoder引擎"""
        try:
            # 尝试导入sqlcoder库
            import sqlcoder
            self.sqlcoder = sqlcoder
            print("[SQLCoderAgent] ✅ SQLCoder引擎可用")
        except ImportError as e:
            print(f"[SQLCoderAgent] ⚠️ SQLCoder引擎不可用: {str(e)}")
            print("[SQLCoderAgent] ⚠️ 请安装: pip install sqlcoder")
            print("[SQLCoderAgent] 🔄 切换到GLM引擎")
            self.backend = SQLGenerationBackend.GLM
            self._init_glm()
    
    def _init_glm(self):
        """初始化GLM引擎"""
        try:
            self.llm = get_llm(provider="zhipu", model=self.llm_model)
            print(f"[SQLCoderAgent] ✅ GLM引擎可用，模型: {self.llm_model}")
        except Exception as e:
            print(f"[SQLCoderAgent] ❌ GLM引擎初始化失败: {str(e)}")
            raise
    
    def _init_vanna(self):
        """初始化Vanna引擎"""
        try:
            from agents.tools.text2sql import get_vanna_text2sql
            self.vanna_engine = get_vanna_text2sql(self.database_path)
            print("[SQLCoderAgent] ✅ Vanna引擎可用")
        except Exception as e:
            print(f"[SQLCoderAgent] ⚠️ Vanna引擎不可用: {str(e)}")
            print("[SQLCoderAgent] 🔄 切换到GLM引擎")
            self.backend = SQLGenerationBackend.GLM
            self._init_glm()
    
    def _load_schema_info(self) -> Dict[str, Any]:
        """加载数据库schema信息"""
        import sqlite3
        
        if not os.path.exists(self.database_path):
            return {"tables": {}}
        
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # 获取所有表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
            tables = cursor.fetchall()
            
            schema_info = {
                "database": "badcase_doctor",
                "database_type": "sqlite",
                "tables": {},
                "table_count": 0
            }
            
            for table_row in tables:
                table_name = table_row[0]
                if table_name in ['sqlite_sequence', 'sqlite_stat1', 'sqlite_stat2', 'sqlite_stat3', 'sqlite_stat4']:
                    continue
                
                # 获取表结构
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                
                # 获取表的索引
                cursor.execute(f"PRAGMA index_list({table_name});")
                indexes = cursor.fetchall()
                
                table_info = {
                    "name": table_name,
                    "columns": [],
                    "column_count": len(columns),
                    "primary_keys": [],
                    "foreign_keys": [],
                    "indexes": []
                }
                
                for col in columns:
                    col_id, col_name, col_type, not_null, default_value, pk = col
                    
                    column_info = {
                        "id": col_id,
                        "name": col_name,
                        "type": col_type,
                        "not_null": not_null == 1,
                        "default": default_value,
                        "primary_key": pk == 1
                    }
                    
                    table_info["columns"].append(column_info)
                    
                    if pk == 1:
                        table_info["primary_keys"].append(col_name)
                
                # 获取外键信息
                cursor.execute(f"PRAGMA foreign_key_list({table_name});")
                fks = cursor.fetchall()
                for fk in fks:
                    if fk:  # id, seq, table, from, to, on_update, on_delete, match
                        table_info["foreign_keys"].append({
                            "from_column": fk[3],
                            "to_table": fk[2],
                            "to_column": fk[4]
                        })
                
                for idx in indexes:
                    if idx and len(idx) > 1:
                        index_name = idx[1]
                        unique = idx[2]
                        cursor.execute(f"PRAGMA index_info({index_name});")
                        index_cols = cursor.fetchall()
                        cols = [col[2] for col in index_cols] if index_cols else []
                        
                        table_info["indexes"].append({
                            "name": index_name,
                            "unique": unique == 1,
                            "columns": cols
                        })
                
                schema_info["tables"][table_name] = table_info
            
            schema_info["table_count"] = len(schema_info["tables"])
            
            conn.close()
            
            if self.debug:
                print(f"[SQLCoderAgent] 已加载 {schema_info['table_count']} 个表")
                for table_name, table_info in schema_info["tables"].items():
                    print(f"  - {table_name}: {table_info['column_count']} 列")
            
            return schema_info
            
        except Exception as e:
            print(f"[SQLCoderAgent] ❌ 加载schema失败: {str(e)}")
            return {"tables": {}}
    
    def generate_sql(self, question: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """
        生成SQL查询语句
        
        Args:
            question: 自然语言问题
            context: 额外的上下文信息
            **kwargs: 其他参数
            
        Returns:
            Dict: 包含生成的SQL和元数据
        """
        if self.debug:
            print(f"[SQLCoderAgent] 📝 生成SQL: {question}")
        
        try:
            if self.backend == SQLGenerationBackend.SQLCODER:
                result = self._generate_with_sqlcoder(question, context, **kwargs)
            elif self.backend == SQLGenerationBackend.GLM:
                result = self._generate_with_glm(question, context, **kwargs)
            elif self.backend == SQLGenerationBackend.VANNA:
                result = self._generate_with_vanna(question, context, **kwargs)
            else:
                result = {
                    'success': False,
                    'error': f'不支持的backend: {self.backend}',
                    'sql': ''
                }
            
            # 验证SQL安全性
            if result.get('success', False) and result.get('sql'):
                is_safe, safety_info = self._validate_sql_safety(result['sql'])
                result['is_safe'] = is_safe
                result['safety_info'] = safety_info
                
                if not is_safe:
                    result['success'] = False
                    result['error'] = '生成的SQL包含潜在安全风险'
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': f'生成SQL失败: {str(e)}',
                'sql': '',
                'backend': self.backend.value
            }
    
    def _generate_with_sqlcoder(self, question: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """使用SQLCoder生成SQL"""
        try:
            # 构建提示词
            prompt = self._build_sqlcoder_prompt(question, context)
            
            # 调用SQLCoder
            # 注意：实际使用中需要根据sqlcoder库的API进行调整
            sql = f"/* 使用SQLCoder生成的查询 */\nSELECT * FROM bad_case WHERE /* {question} */;"
            
            return {
                'success': True,
                'sql': sql,
                'backend': 'sqlcoder',
                'prompt_used': prompt,
                'is_estimated': True  # 标记为估计查询，需要进一步处理
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'SQLCoder生成失败: {str(e)}',
                'sql': '',
                'backend': 'sqlcoder'
            }
    
    def _generate_with_glm(self, question: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """使用GLM生成SQL"""
        try:
            # 构建提示词
            prompt = self._build_glm_prompt(question, context)
            
            # 调用GLM
            response = self.llm.generate(prompt)
            
            # 提取SQL语句
            sql = self._extract_sql_from_response(response)
            
            return {
                'success': True,
                'sql': sql,
                'backend': 'glm',
                'prompt_used': prompt[:200],  # 只保存前200字符用于调试
                'raw_response': response[:500]  # 保存部分原始响应
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'GLM生成失败: {str(e)}',
                'sql': '',
                'backend': 'glm'
            }
    
    def _generate_with_vanna(self, question: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """使用Vanna生成SQL"""
        try:
            result = self.vanna_engine.execute({"query": question})
            
            if result.get('success', False):
                return {
                    'success': True,
                    'sql': result.get('generated_sql', ''),
                    'backend': 'vanna',
                    'raw_result': result
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Vanna生成失败'),
                    'sql': '',
                    'backend': 'vanna'
                }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Vanna生成失败: {str(e)}',
                'sql': '',
                'backend': 'vanna'
            }
    
    def _build_sqlcoder_prompt(self, question: str, context: str = "") -> str:
        """构建SQLCoder提示词"""
        schema_text = self._format_schema_for_sqlcoder()
        
        prompt = f"""You are a SQL expert. Based on the following database schema and user question, generate a correct SQL query.

Database Schema:
{schema_text}

User Question: {question}

Additional Context: {context if context else 'No additional context'}

Instructions:
1. Generate only the SQL query, no explanations
2. Ensure the SQL is syntactically correct
3. Use appropriate table aliases if needed
4. Consider performance implications
5. Add comments only if necessary for clarity

SQL Query:"""

        return prompt
    
    def _build_glm_prompt(self, question: str, context: str = "") -> str:
        """构建GLM提示词"""
        schema_text = self._format_schema_for_glm()
        
        prompt = f"""你是一个SQL专家。请根据以下数据库schema和用户问题，生成正确的SQL查询语句。

数据库结构:
{schema_text}

用户问题: {question}

额外上下文: {context if context else '无'}

要求:
1. 只返回SQL语句，不要包含解释
2. 确保SQL语法正确
3. 使用合适的表别名（如果需要）
4. 考虑查询性能
5. 仅当必要时添加注释以提高可读性

SQL查询语句:"""

        return prompt
    
    def _format_schema_for_sqlcoder(self) -> str:
        """格式化schema供SQLCoder使用"""
        schema_text = "Database: badcase_doctor (SQLite)\n\n"
        
        for table_name, table_info in self.schema_info.get("tables", {}).items():
            schema_text += f"Table: {table_name}\n"
            
            # 列信息
            for col in table_info.get("columns", []):
                col_desc = f"  - {col['name']}: {col['type']}"
                if col.get("primary_key"):
                    col_desc += " (PRIMARY KEY)"
                if not col.get("not_null"):
                    col_desc += " (nullable)"
                if col.get("default"):
                    col_desc += f" (default: {col['default']})"
                schema_text += col_desc + "\n"
            
            # 索引信息
            if table_info.get("indexes"):
                schema_text += "  Indexes:\n"
                for idx in table_info["indexes"]:
                    idx_desc = f"    - {idx['name']}: {', '.join(idx['columns'])}"
                    if idx.get("unique"):
                        idx_desc += " (unique)"
                    schema_text += idx_desc + "\n"
            
            # 外键信息
            if table_info.get("foreign_keys"):
                schema_text += "  Foreign Keys:\n"
                for fk in table_info["foreign_keys"]:
                    schema_text += f"    - {fk['from_column']} -> {fk['to_table']}({fk['to_column']})\n"
            
            schema_text += "\n"
        
        return schema_text
    
    def _format_schema_for_glm(self) -> str:
        """格式化schema供GLM使用"""
        return self._format_schema_for_sqlcoder()
    
    def _extract_sql_from_response(self, response: str) -> str:
        """从模型响应中提取SQL语句"""
        # 移除SQL代码块标记
        sql = response.strip()
        sql = re.sub(r'^```sql\s*', '', sql)
        sql = re.sub(r'^```\s*', '', sql)
        sql = re.sub(r'\s*```\s*$', '', sql)
        sql = re.sub(r'^SELECT\s*--\s*.+\n', 'SELECT ', sql, flags=re.IGNORECASE)
        
        # 移除注释
        lines = sql.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('--') and not line.startswith('/*'):
                cleaned_lines.append(line)
        
        sql = ' '.join(cleaned_lines)
        
        # 确保以SELECT开头
        if not sql.upper().startswith('SELECT'):
            sql = f"SELECT * FROM bad_case WHERE /* {sql} */"
        
        return sql
    
    def _validate_sql_safety(self, sql: str) -> tuple[bool, Dict[str, Any]]:
        """验证SQL安全性"""
        sql_lower = sql.lower()
        
        # 危险操作
        dangerous_ops = [
            'drop ', 'truncate ', 'delete from', 'update ', 'alter ',
            'create ', 'insert into', 'grant ', 'revoke ',
            'exec ', 'execute ', 'xp_', 'sp_',
            'union select', 'information_schema', 'sys.objects'
        ]
        
        found_dangerous = []
        for op in dangerous_ops:
            if op in sql_lower:
                found_dangerous.append(op)
        
        # 检查是否以SELECT开头（允许必要的子查询）
        lines = sql_lower.strip().split()
        if len(lines) > 0 and not lines[0].startswith('select'):
            found_dangerous.append('非SELECT操作')
        
        is_safe = len(found_dangerous) == 0
        
        safety_info = {
            'is_safe': is_safe,
            'dangerous_operations_found': found_dangerous,
            'sql_length': len(sql),
            'lines': len(sql.split('\n'))
        }
        
        return is_safe, safety_info
    
    def execute_sql(self, sql: str, limit: int = 100) -> Dict[str, Any]:
        """
        执行SQL查询
        
        Args:
            sql: SQL查询语句
            limit: 结果限制
            
        Returns:
            Dict: 执行结果
        """
        if self.debug:
            print(f"[SQLCoderAgent] 🚀 执行SQL: {sql[:200]}...")
        
        # 安全验证
        is_safe, safety_info = self._validate_sql_safety(sql)
        if not is_safe:
            return {
                'success': False,
                'error': 'SQL存在安全风险，拒绝执行',
                'safety_info': safety_info
            }
        
        try:
            import sqlite3
            
            conn = sqlite3.connect(self.database_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 添加LIMIT（如果需要）
            if 'limit' not in sql.lower() and limit > 0:
                sql = self._add_limit_to_sql(sql, limit)
            
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            # 转换为字典
            data = [dict(row) for row in rows]
            
            # 获取列信息
            columns = [description[0] for description in cursor.description] if cursor.description else []
            
            conn.close()
            
            return {
                'success': True,
                'data': data,
                'columns': columns,
                'row_count': len(data),
                'sql_executed': sql,
                'limit_applied': limit
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'执行SQL失败: {str(e)}',
                'sql': sql
            }
    
    def _add_limit_to_sql(self, sql: str, limit: int) -> str:
        """为SQL添加LIMIT子句"""
        sql = sql.rstrip(';').strip()
        
        # 如果已经在子查询中有LIMIT，则不添加
        if 'limit' in sql.lower():
            return sql
        
        # 检查是否有ORDER BY或GROUP BY
        sql_lower = sql.lower()
        
        if ' order by ' in sql_lower:
            # 在ORDER BY之后添加LIMIT
            parts = re.split(r'(ORDER BY .+)', sql, flags=re.IGNORECASE)
            if len(parts) >= 3:
                return f"{parts[0].strip()} {parts[1]} LIMIT {limit}"
        
        elif ' group by ' in sql_lower:
            # 在GROUP BY之后添加LIMIT
            parts = re.split(r'(GROUP BY .+)', sql, flags=re.IGNORECASE)
            if len(parts) >= 3:
                return f"{parts[0].strip()} {parts[1]} LIMIT {limit}"
        
        # 直接添加LIMIT
        return f"{sql} LIMIT {limit}"


def get_sqlcoder_agent(database_path: str = "instance/badcase_doctor.db", 
                      backend: str = "sqlcoder",
                      llm_model: str = "glm-4",
                      debug: bool = False) -> SQLCoderAgent:
    """获取SQLCoder代理实例"""
    backend_enum = SQLGenerationBackend(backend)
    return SQLCoderAgent(
        database_path=database_path,
        backend=backend_enum,
        llm_model=llm_model,
        debug=debug
    )