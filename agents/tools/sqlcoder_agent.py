"""
Text2SQL智能代理 - 使用LangChain + SQLDatabaseToolkit + GLM实现

支持的LLM后端:
- GLM-4-Flash: 快速响应，适合简单查询
- GLM-5: 支持复杂推理，适合复杂SQL生成
"""

import os
import re
import sqlite3
from typing import Dict, Any, Optional, Tuple
from enum import Enum
import threading
import time
from collections import OrderedDict

from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit, create_sql_agent


class LLMBackend(Enum):
    """LLM后端类型"""
    GLM_4_FLASH = "glm-4-flash"
    GLM_5 = "glm-5"


class ExecutionMode(Enum):
    """执行模式"""
    DIRECT = "direct"      # 直接执行（默认）
    SANDBOX = "sandbox"    # Docker 沙箱执行


class Text2SQLAgent:
    """Text2SQL智能代理 - 基于LangChain SQLDatabaseToolkit，支持沙箱执行"""
    
    def __init__(self, 
                 database_path: str = "instance/badcase_doctor.db",
                 llm_backend: LLMBackend = LLMBackend.GLM_5,
                 api_key: str = None,
                 debug: bool = False,
                 execution_mode: ExecutionMode = ExecutionMode.DIRECT):
        """
        初始化Text2SQL代理
        
        Args:
            database_path: 数据库路径（支持SQLite和MySQL）
            llm_backend: LLM后端类型
            api_key: GLM API Key（为None时从环境变量读取）
            debug: 调试模式
            execution_mode: 执行模式 (direct/sandbox)
        """
        self.database_path = self._resolve_database_path(database_path)
        self.llm_backend = llm_backend
        self.debug = debug
        self.execution_mode = execution_mode
        self._sql_cache_lock = threading.Lock()
        self._sql_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        try:
            self._sql_cache_ttl_s = max(0, int((os.getenv("TEXT2SQL_SQL_CACHE_TTL", "30") or "30").strip()))
        except Exception:
            self._sql_cache_ttl_s = 30
        try:
            self._sql_cache_max = max(8, int((os.getenv("TEXT2SQL_SQL_CACHE_MAX", "128") or "128").strip()))
        except Exception:
            self._sql_cache_max = 128
        
        # 获取API Key
        self.api_key = api_key or os.getenv('ZHIPU_API_KEY') or self._get_api_key_from_config()
        
        # 初始化LLM
        self.llm = self._init_llm()
        
        # 初始化数据库连接
        self.db = self._init_database()
        
        # 初始化SQLDatabaseToolkit
        self.toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        
        # 加载schema信息
        self.schema_info = self._load_schema_info()
        self._schema_prompt_ver: Optional[Tuple] = None
        self._schema_prompt_cache_key: Optional[Tuple] = None
        self._schema_prompt_cached: Optional[str] = None
        
        # 初始化沙箱执行器（如果需要）
        self._sandbox_executor = None
        if execution_mode == ExecutionMode.SANDBOX:
            self._init_sandbox_executor()
        
        print(f"[Text2SQLAgent] 初始化完成")
        print(f"[Text2SQLAgent] LLM后端: {llm_backend.value}")
        print(f"[Text2SQLAgent] 数据库: {self.database_path}")
        print(f"[Text2SQLAgent] 执行模式: {execution_mode.value}")
        print(f"[Text2SQLAgent] 已加载表数量: {len(self.schema_info.get('tables', {}))}")
    
    def _init_sandbox_executor(self):
        """初始化沙箱执行器"""
        try:
            from .text2sql.sandbox_executor import get_sandbox_executor
            self._sandbox_executor = get_sandbox_executor(fallback_to_local=True)
            print(f"[Text2SQLAgent] 沙箱执行器已初始化")
        except ImportError as e:
            print(f"[Text2SQLAgent] 沙箱执行器初始化失败: {e}")
            self._sandbox_executor = None
        except Exception as e:
            print(f"[Text2SQLAgent] 沙箱执行器初始化异常: {e}")
            self._sandbox_executor = None
    
    def _get_api_key_from_config(self) -> str:
        """从config.py获取API Key"""
        try:
            from config import Config
            return Config.ZHIPU_API_KEY
        except:
            raise ValueError("未找到ZHIPU_API_KEY，请配置环境变量或在config.py中设置")
    
    def _resolve_database_path(self, database_path: str) -> str:
        """解析数据库路径或 URI"""
        if os.path.isabs(database_path):
            return database_path
        
        # 完整 URI：MySQL/PostgreSQL/SQLite，直接返回
        if database_path.startswith(('mysql', 'postgresql', 'postgres', 'sqlite:///')):
            return database_path
        
        # 相对路径转绝对路径
        if os.path.exists(database_path):
            return os.path.abspath(database_path)
        
        # 尝试相对于项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        abs_path = os.path.join(project_root, database_path)
        if os.path.exists(abs_path):
            return abs_path
        
        return database_path
    
    def _init_llm(self):
        """初始化LLM（OpenAI兼容接口）。

        支持：
        - 智谱（默认）：https://open.bigmodel.cn/api/paas/v4
        - 阿里云百炼（DashScope OpenAI 兼容模式）：https://dashscope.aliyuncs.com/compatible-mode/v1

        通过环境变量控制：
        - TEXT2SQL_PROVIDER: zhipu | bailian
        - TEXT2SQL_API_BASE: 覆盖 base_url
        - TEXT2SQL_API_KEY: 覆盖 api_key
        - TEXT2SQL_MODEL: 覆盖 model（默认用 llm_backend.value，例如 glm-4-flash/glm-5）
        """
        try:
            from langchain_openai import ChatOpenAI
            
            import os
            from config import Config

            provider = (os.getenv("TEXT2SQL_PROVIDER", "zhipu") or "zhipu").strip().lower()
            # 兼容：用户习惯把“百炼/通义”写成 qwen
            is_bailian = provider in ("bailian", "dashscope", "aliyun", "qwen")
            model_name = (os.getenv("TEXT2SQL_MODEL", "") or "").strip() or self.llm_backend.value

            api_base = (os.getenv("TEXT2SQL_API_BASE", "") or "").strip()
            api_key = (os.getenv("TEXT2SQL_API_KEY", "") or "").strip()

            if not api_base:
                if is_bailian:
                    api_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
                else:
                    api_base = "https://open.bigmodel.cn/api/paas/v4"

            if not api_key:
                if is_bailian:
                    api_key = getattr(Config, "DASHSCOPE_API_KEY", None) or getattr(Config, "QWEN_API_KEY", None)
                else:
                    api_key = self.api_key

            if not api_key:
                raise ValueError("TEXT2SQL API key 未配置（百炼/通义用 DASHSCOPE_API_KEY/QWEN_API_KEY，智谱用 ZHIPU_API_KEY）")

            llm = ChatOpenAI(
                model=model_name,
                openai_api_key=api_key,
                openai_api_base=api_base,
                temperature=0.1,  # SQL生成使用低温度
                max_tokens=4096,
            )
            
            # Windows 控制台可能是 gbk，避免 emoji 导致 UnicodeEncodeError
            print(f"[Text2SQLAgent] LLM初始化成功: provider={provider}, model={model_name}, base={api_base}")
            return llm
            
        except ImportError as e:
            print(f"[Text2SQLAgent] 缺少依赖: {str(e)}")
            print("[Text2SQLAgent] 请安装: pip install langchain-openai")
            raise
        except Exception as e:
            print(f"[Text2SQLAgent] LLM初始化失败: {str(e)}")
            raise
    
    def _init_database(self) -> SQLDatabase:
        """初始化数据库连接"""
        try:
            # 完整 URI：MySQL/PostgreSQL/SQLite，直接使用
            if self.database_path.startswith(('mysql://', 'mysql+pymysql://', 'postgresql://', 'postgres://', 'sqlite:///')):
                db = SQLDatabase.from_uri(self.database_path)
            else:
                # 本地文件路径
                db = SQLDatabase.from_uri(f"sqlite:///{self.database_path}")
            
            print(f"[Text2SQLAgent] 数据库连接成功")
            return db
            
        except Exception as e:
            print(f"[Text2SQLAgent] 数据库连接失败: {str(e)}")
            raise
    
    def _load_schema_info(self) -> Dict[str, Any]:
        """加载数据库schema信息"""
        schema_info = {
            "database": "badcase_doctor",
            "database_type": "sqlite" if not self.database_path.startswith(('mysql', 'postgres')) else "mysql",
            "tables": {},
            "table_count": 0
        }
        
        try:
            # 使用LangChain的SQLDatabase获取schema
            table_info = self.db.get_table_info()
            
            # 解析表信息
            current_table = None
            for line in table_info.split('\n'):
                line = line.strip()
                if line.startswith('CREATE TABLE'):
                    match = re.search(r'CREATE TABLE (\w+)', line)
                    if match:
                        current_table = match.group(1)
                        schema_info["tables"][current_table] = {
                            "name": current_table,
                            "columns": [],
                            "column_count": 0
                        }
                elif current_table and line and not line.startswith(')') and not line.startswith('FOREIGN'):
                    # 解析列信息
                    col_match = re.match(r'(\w+)\s+(\w+)', line)
                    if col_match:
                        col_name, col_type = col_match.groups()
                        schema_info["tables"][current_table]["columns"].append({
                            "name": col_name,
                            "type": col_type
                        })
            
            # 更新列数量
            for table_name, table_info in schema_info["tables"].items():
                table_info["column_count"] = len(table_info["columns"])
            
            schema_info["table_count"] = len(schema_info["tables"])
            
            if self.debug:
                print(f"[Text2SQLAgent] 已加载 {schema_info['table_count']} 个表")
                for table_name, table_info in schema_info["tables"].items():
                    print(f"  - {table_name}: {table_info['column_count']} 列")
            
            return schema_info
            
        except Exception as e:
            print(f"[Text2SQLAgent] 加载schema失败: {str(e)}，使用空schema")
            return schema_info

    def _schema_cache_identity(self) -> tuple:
        """SQLite 文件用 mtime 区分；避免重复解析整库 schema（generate_sql 热路径）。"""
        path = self.database_path
        if path.startswith("sqlite:///"):
            path = path.replace("sqlite:///", "", 1)
        try:
            if path and os.path.isfile(path):
                ap = os.path.abspath(path)
                return ("file", ap, os.path.getmtime(ap))
        except OSError:
            pass
        return ("path", path, 0.0)

    def _get_schema_prompt_for_generate(self) -> str:
        """带缓存的 schema 文本；DB 文件变更时重载 self.schema_info 再格式化。"""
        ident = self._schema_cache_identity()
        if self._schema_prompt_cache_key == ident and self._schema_prompt_cached:
            return self._schema_prompt_cached
        if getattr(self, "_schema_prompt_ver", None) != ident:
            try:
                self.schema_info = self._load_schema_info()
            except Exception:
                pass
            self._schema_prompt_ver = ident
        text = self._format_schema_for_prompt()
        self._schema_prompt_cached = text
        self._schema_prompt_cache_key = ident
        return text
    
    def generate_sql(self, question: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """
        生成SQL查询语句
        
        Args:
            question: 自然语言问题
            context: 额外的上下文信息（可选）
            **kwargs: 其他参数
            
        Returns:
            Dict: 包含生成的SQL和元数据
        """
        if self.debug:
            print(f"[Text2SQLAgent] 生成SQL: {question}")
        
        try:
            cache_key = f"{self.llm_backend.value}|{question.strip()}|{context.strip()}"
            cached = self._sql_cache_get(cache_key)
            if cached is not None:
                if self.debug:
                    print("[Text2SQLAgent] 命中SQL生成缓存")
                return cached

            # 构建提示词（schema 按库文件 mtime 缓存，减少重复 get_table_info 开销）
            schema_info = self._get_schema_prompt_for_generate()
            
            prompt = f"""你是一个SQL专家。请根据以下数据库结构和用户问题，生成正确的SQLite SQL查询语句。

数据库结构:
{schema_info}

用户问题: {question}

额外上下文: {context if context else '无'}

要求:
1. 只返回SQL语句，不要包含任何解释
2. 确保SQL语法正确
3. 使用SQLite语法
4. 表名和字段名要准确匹配上面的数据库结构
5. 如果需要排序，请使用合适的字段排序
6. 优先性能：仅查询必要列，避免 SELECT *；可加 LIMIT 时必须加 LIMIT

SQL查询语句:"""

            # 调用LLM
            response = self.llm.invoke(prompt)
            
            # 提取SQL
            output = response.content if hasattr(response, 'content') else str(response)
            sql = self._extract_sql_from_result(output)
            
            # 验证SQL安全性
            if sql:
                is_safe, safety_info = self._validate_sql_safety(sql)
                
                result = {
                    'success': is_safe,
                    'sql': sql,
                    'backend': self.llm_backend.value,
                    'is_safe': is_safe,
                    'safety_info': safety_info,
                    'error': None if is_safe else '生成的SQL包含潜在安全风险',
                    'raw_output': output[:500] if self.debug else None
                }
                if result.get("success"):
                    self._sql_cache_put(cache_key, result)
                return result
            else:
                return {
                    'success': False,
                    'error': '无法从响应中提取SQL语句',
                    'sql': '',
                    'backend': self.llm_backend.value,
                    'raw_output': output[:500]
                }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'生成SQL失败: {str(e)}',
                'sql': '',
                'backend': self.llm_backend.value
            }
    
    def _format_schema_for_prompt(self) -> str:
        """格式化schema用于提示词"""
        schema_text = "数据库: badcase_doctor (SQLite)\n\n"
        
        for table_name, table_info in self.schema_info.get("tables", {}).items():
            schema_text += f"表: {table_name}\n"
            schema_text += "字段:\n"
            
            for col in table_info.get("columns", []):
                col_desc = f"  - {col['name']}: {col['type']}"
                schema_text += col_desc + "\n"
            
            schema_text += "\n"
        
        return schema_text
    
    def _extract_sql_from_result(self, output: str) -> str:
        """从Agent输出中提取SQL语句"""
        # 尝试多种模式提取SQL
        patterns = [
            r'```sql\s*([\s\S]*?)\s*```',  # ```sql ... ```
            r'```\s*([\s\S]*?)\s*```',      # ``` ... ```
            r'(SELECT[\s\S]*?)(?:;|$)',     # SELECT ... ;
            r'(UPDATE[\s\S]*?)(?:;|$)',     # UPDATE ... ;
            r'SELECT\s+[\w\s,.*]+\s+FROM[\s\S]*?(?:;|$)',  # SELECT ... FROM ...
            r'UPDATE\s+\w+\s+SET[\s\S]*?(?:;|$)',  # UPDATE ... SET ...
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                sql = match.group(1).strip() if match.lastindex else match.group(0).strip()
                # 清理SQL
                sql = re.sub(r'^```sql?\s*', '', sql, flags=re.IGNORECASE)
                sql = re.sub(r'\s*```\s*$', '', sql)
                sql = sql.strip().rstrip(';') + ';'
                # 支持 SELECT 和 UPDATE
                if sql.upper().startswith(('SELECT', 'UPDATE')):
                    print(f"[SQL-EXTRACT] 提取到SQL: {sql}")
                    return sql
        
        # 如果没找到，尝试直接查找 SELECT 或 UPDATE
        for keyword in ['SELECT', 'UPDATE']:
            idx = output.upper().find(keyword)
            if idx != -1:
                sql = output[idx:].strip()
                sql = re.sub(r'\s+', ' ', sql)  # 压缩空白
                sql = sql.split(';')[0] + ';'
                print(f"[SQL-EXTRACT] 直接提取到SQL: {sql}")
                return sql
        
        return ''
    
    def query_natural_language(self, question: str, context: str = "") -> Dict[str, Any]:
        """
        自然语言查询（生成SQL并执行）
        
        Args:
            question: 自然语言问题
            context: 额外上下文
            
        Returns:
            Dict: 包含SQL、执行结果和元数据
        """
        # 先生成SQL
        sql_result = self.generate_sql(question, context)
        
        if not sql_result.get('success'):
            return sql_result
        
        sql = sql_result['sql']
        
        # 执行SQL
        exec_result = self.execute_sql(sql)
        
        # 合并结果
        return {
            **sql_result,
            'data': exec_result.get('data', []),
            'columns': exec_result.get('columns', []),
            'row_count': exec_result.get('row_count', 0),
            'executed': exec_result.get('success', False),
            'exec_error': exec_result.get('error')
        }
    
    def _validate_sql_safety(self, sql: str) -> tuple:
        """验证SQL安全性"""
        sql_lower = sql.lower()
        sql_stripped = sql.strip().lower()
        
        # 危险操作（绝对禁止）
        absolutely_dangerous = [
            'drop ', 'truncate ', 'alter ',
            'create ', 'grant ', 'revoke ',
            'exec ', 'execute ', 'xp_', 'sp_',
            'union select', 'information_schema', 'sys.objects'
        ]
        
        # 有条件允许的操作（需要额外检查）
        conditional_ops = {
            'delete from': 'DELETE 需要WHERE条件',
            'insert into': 'INSERT 需要检查目标表',
        }
        
        found_dangerous = []
        
        # 检查绝对危险操作
        for op in absolutely_dangerous:
            if op in sql_lower:
                found_dangerous.append(f'危险操作: {op}')
        
        # 检查 SQL 类型
        if sql_stripped.startswith('select'):
            # SELECT 语句安全
            pass
        elif sql_stripped.startswith('update'):
            # UPDATE 需要有 WHERE 条件
            if 'where' not in sql_lower:
                found_dangerous.append('UPDATE 缺少WHERE条件')
            else:
                print(f"[SQL-SAFETY] UPDATE 语句通过安全检查")
        elif sql_stripped.startswith('delete'):
            # DELETE 需要有 WHERE 条件
            if 'where' not in sql_lower:
                found_dangerous.append('DELETE 缺少WHERE条件')
        else:
            found_dangerous.append(f'未知SQL类型')
        
        is_safe = len(found_dangerous) == 0
        
        safety_info = {
            'is_safe': is_safe,
            'dangerous_operations_found': found_dangerous,
            'sql_length': len(sql),
        }
        
        return is_safe, safety_info
    
    def execute_sql(self, sql: str, limit: int = 100, force_mode: ExecutionMode = None) -> Dict[str, Any]:
        """
        执行SQL查询
        
        Args:
            sql: SQL查询语句
            limit: 结果限制
            force_mode: 强制指定执行模式（可选）
            
        Returns:
            Dict: 执行结果
        """
        if self.debug:
            print(f"[Text2SQLAgent] 执行SQL: {sql[:200]}...")
        
        # 安全验证
        is_safe, safety_info = self._validate_sql_safety(sql)
        if not is_safe:
            return {
                'success': False,
                'error': 'SQL存在安全风险，拒绝执行',
                'safety_info': safety_info
            }
        
        # 决定执行模式
        exec_mode = force_mode or self.execution_mode
        
        # 如果是沙箱模式，且沙箱执行器可用，则使用沙箱执行
        if exec_mode == ExecutionMode.SANDBOX and self._sandbox_executor:
            return self._execute_sql_via_sandbox(sql, limit)
        
        # 否则直接执行
        return self._execute_sql_direct(sql, limit)
    
    def _execute_sql_via_sandbox(self, sql: str, limit: int) -> Dict[str, Any]:
        """
        通过沙箱执行SQL
        
        流程：
        1. SQL -> Python 代码封装
        2. 代码 -> Docker 沙箱执行
        3. 返回结果
        """
        if self.debug:
            print(f"[Text2SQLAgent] 通过沙箱执行SQL...")
        
        try:
            # 数据库配置
            db_config = {
                'path': self.database_path,
                'type': 'sqlite' if not self.database_path.startswith(('mysql', 'postgres')) else 'mysql'
            }
            
            # 添加 LIMIT
            if 'limit' not in sql.lower() and limit > 0:
                sql = self._add_limit_to_sql(sql, limit)
            
            # 直接调用沙箱执行器
            result = self._sandbox_executor.execute_sql(sql, db_config)
            
            if not result.get('success'):
                print(f"[Text2SQLAgent] 沙箱执行失败: {result.get('error')}")
            
            return result
                
        except Exception as e:
            print(f"[Text2SQLAgent] 沙箱执行失败: {e}")
            return {
                'success': False,
                'error': f'沙箱执行失败: {str(e)}',
                'sql': sql
            }
    
    def _execute_sql_direct(self, sql: str, limit: int) -> Dict[str, Any]:
        """直接执行SQL（非沙箱模式）"""
        try:
            # 判断 SQL 类型
            sql_upper = sql.strip().upper()
            is_select = sql_upper.startswith('SELECT')
            is_update = sql_upper.startswith('UPDATE')
            is_delete = sql_upper.startswith('DELETE')
            
            # 解析结果
            # 如果是SQLite，直接连接执行
            if not self.database_path.startswith(('mysql', 'postgres')):
                # 支持 sqlite:/// 或 文件路径
                db_path = self.database_path
                if db_path.startswith('sqlite:///'):
                    db_path = self.database_path[10:]  # 去掉 sqlite:///
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # 只对 SELECT 添加 LIMIT
                if is_select and 'limit' not in sql.lower() and limit > 0:
                    sql = self._add_limit_to_sql(sql, limit)
                
                print(f"[SQL-EXEC] 执行SQL: {sql}")
                cursor.execute(sql)
                
                if is_select:
                    # SELECT 返回查询结果
                    rows = cursor.fetchall()
                    data = [dict(row) for row in rows]
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []
                    conn.close()
                    return {
                        'success': True,
                        'data': data,
                        'columns': columns,
                        'row_count': len(data),
                        'sql_executed': sql,
                        'limit_applied': limit,
                        'execution_mode': 'direct'
                    }
                elif is_update or is_delete:
                    # UPDATE/DELETE 返回影响行数
                    conn.commit()
                    affected_rows = cursor.rowcount
                    conn.close()
                    print(f"[SQL-EXEC] UPDATE/DELETE 执行成功，影响 {affected_rows} 行")
                    return {
                        'success': True,
                        'affected_rows': affected_rows,
                        'sql_executed': sql,
                        'execution_mode': 'direct'
                    }
                else:
                    conn.close()
                    return {
                        'success': True,
                        'sql_executed': sql,
                        'execution_mode': 'direct'
                    }
            else:
                # MySQL/PostgreSQL 使用 LangChain 的结果
                result = self.db.run(sql)
                return {
                    'success': True,
                    'data': result,
                    'sql_executed': sql,
                    'raw_result': str(result)[:1000],
                    'execution_mode': 'direct'
                }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'执行SQL失败: {str(e)}',
                'sql': sql
            }

    def _sql_cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        if self._sql_cache_ttl_s <= 0:
            return None
        now = time.time()
        with self._sql_cache_lock:
            item = self._sql_cache.get(key)
            if not item:
                return None
            if now - float(item.get("ts", 0.0)) > self._sql_cache_ttl_s:
                self._sql_cache.pop(key, None)
                return None
            self._sql_cache.move_to_end(key)
            return dict(item.get("value") or {})

    def _sql_cache_put(self, key: str, value: Dict[str, Any]) -> None:
        if self._sql_cache_ttl_s <= 0:
            return
        with self._sql_cache_lock:
            self._sql_cache[key] = {"ts": time.time(), "value": dict(value or {})}
            self._sql_cache.move_to_end(key)
            while len(self._sql_cache) > self._sql_cache_max:
                self._sql_cache.popitem(last=False)
    
    def _add_limit_to_sql(self, sql: str, limit: int) -> str:
        """为SQL添加LIMIT子句"""
        sql = sql.rstrip(';').strip()
        
        if 'limit' in sql.lower():
            return sql
        
        sql_lower = sql.lower()
        
        if ' order by ' in sql_lower:
            parts = re.split(r'(ORDER BY .+)', sql, flags=re.IGNORECASE)
            if len(parts) >= 3:
                return f"{parts[0].strip()} {parts[1]} LIMIT {limit}"
        
        elif ' group by ' in sql_lower:
            parts = re.split(r'(GROUP BY .+)', sql, flags=re.IGNORECASE)
            if len(parts) >= 3:
                return f"{parts[0].strip()} {parts[1]} LIMIT {limit}"
        
        return f"{sql} LIMIT {limit}"

    def get_schema_description(self) -> str:
        """获取数据库schema描述"""
        return self.db.get_table_info()
    
    def get_table_names(self) -> list:
        """获取所有表名"""
        return list(self.schema_info.get("tables", {}).keys())


# 兼容旧API的别名
SQLCoderAgent = Text2SQLAgent
SQLGenerationBackend = LLMBackend


def get_text2sql_agent(database_path: str = "instance/badcase_doctor.db",
                       llm_backend: str = "glm-4-flash",
                       api_key: str = None,
                       debug: bool = False,
                       execution_mode: str = "direct") -> Text2SQLAgent:
    """
    获取Text2SQL代理实例
    
    Args:
        database_path: 数据库路径
        llm_backend: LLM后端
        api_key: API密钥
        debug: 调试模式
        execution_mode: 执行模式 (direct/sandbox/hybrid)
    """
    backend_enum = LLMBackend(llm_backend)
    mode_enum = ExecutionMode(execution_mode)
    return Text2SQLAgent(
        database_path=database_path,
        llm_backend=backend_enum,
        api_key=api_key,
        debug=debug,
        execution_mode=mode_enum
    )


_TEXT2SQL_CACHE_LOCK = threading.Lock()
_TEXT2SQL_CACHE: Dict[str, object] = {}
_TEXT2SQL_NONE = object()


def get_cached_text2sql_agent(
    database_path: str = "instance/badcase_doctor.db",
    llm_backend: str = "glm-4-flash",
    api_key: str = None,
    debug: bool = False,
    execution_mode: str = "direct",
) -> Optional[Text2SQLAgent]:
    """
    进程级缓存 Text2SQLAgent，避免每次请求/每个工具重复初始化（连接DB/加载schema/初始化沙箱等）。
    """
    key = f"{database_path}|{llm_backend}|{execution_mode}|{int(bool(debug))}|{api_key or ''}"
    cached = _TEXT2SQL_CACHE.get(key, None)
    if cached is _TEXT2SQL_NONE:
        return None
    if isinstance(cached, Text2SQLAgent):
        return cached
    with _TEXT2SQL_CACHE_LOCK:
        cached2 = _TEXT2SQL_CACHE.get(key, None)
        if cached2 is _TEXT2SQL_NONE:
            return None
        if isinstance(cached2, Text2SQLAgent):
            return cached2
        try:
            agent = get_text2sql_agent(
                database_path=database_path,
                llm_backend=llm_backend,
                api_key=api_key,
                debug=debug,
                execution_mode=execution_mode,
            )
        except Exception as e:
            msg = str(e)
            # glm-5 常见失败：429/1113（配额/资源不足）；自动降级到 glm-4-flash
            if ("429" in msg or "1113" in msg) and llm_backend in ("glm-5", "glm5"):
                try:
                    agent = get_text2sql_agent(
                        database_path=database_path,
                        llm_backend="glm-4-flash",
                        api_key=api_key,
                        debug=debug,
                        execution_mode=execution_mode,
                    )
                except Exception as e2:
                    agent = None
                    print(f"[Text2SQLAgent] 缓存初始化失败（降级也失败）: {e2}")
            else:
                agent = None
                print(f"[Text2SQLAgent] 缓存初始化失败: {e}")
        _TEXT2SQL_CACHE[key] = agent if agent is not None else _TEXT2SQL_NONE
        return agent


# 兼容旧API
def get_sqlcoder_agent(database_path: str = "instance/badcase_doctor.db",
                       backend: str = "glm-4-flash",
                       llm_model: str = "glm-4-flash",
                       debug: bool = False,
                       execution_mode: str = "direct") -> SQLCoderAgent:
    """获取SQLCoder代理实例（兼容旧API）"""
    return get_text2sql_agent(
        database_path=database_path,
        llm_backend=backend or llm_model,
        debug=debug,
        execution_mode=execution_mode
    )
