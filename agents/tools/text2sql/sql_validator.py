"""
Text2SQL SQL验证器
使用 sqlglot进行 SQL语法验证和安全检查
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import re


@dataclass
class ValidationResult:
    """SQL验证结果"""
    valid: bool
    safe: bool = True
    error: Optional[str] = None
    warnings: List[str] = None
    normalized_sql: Optional[str] = None
    security_violation: bool = False
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'valid': self.valid,
            'safe': self.safe,
            'error': self.error,
            'warnings': self.warnings,
            'normalized_sql': self.normalized_sql,
            'security_violation': self.security_violation
        }


class SQLValidator:
    """SQL验证器"""
    
    def __init__(self):
        self._init_dangerous_patterns()
    
    def _init_dangerous_patterns(self):
        """初始化危险操作模式"""
        #危 SQL操作
        self.dangerous_operations = [
            r'\b(DROP|TRUNCATE|DELETE\s+FROM)\b',
            r'\b(ALTER\s+TABLE)\b',
            r'\b(CREATE\s+(USER|DATABASE|TABLE))\b',
            r'\b(GRANT|REVOKE)\b',
            r'\b(UPDATE.*WHERE\s+1=1)\b',  # 无条件更新
            r'\b(DELETE.*WHERE\s+1=1)\b',  # 无条件删除
        ]
        
        #危函数
        self.dangerous_functions = [
            r'\b(SLEEP|BENCHMARK|WAITFOR)\b',
            r'\b(LOAD_FILE|DUMPFILE)\b',
            r'\b(SYSTEM|EXEC|EXECUTE)\b',
        ]
    
    def validate_sql(self, sql: str) -> Dict[str, Any]:
        """
       验证 SQL语句的安全性
        
        Args:
            sql:待的 SQL 语句
            
        Returns:
           验证结果
        """
        try:
            # 1.基语法检查
            syntax_check = self._check_syntax(sql)
            if not syntax_check['valid']:
                return syntax_check
            
            # 2.安全检查
            security_check = self._check_security(sql)
            if not security_check['safe']:
                return {
                    'valid': False,
                    'error': security_check['reason'],
                    'security_violation': True
                }
            
            # 3. 结构检查
            structure_check = self._check_structure(sql)
            if not structure_check['valid']:
                return structure_check
            
            return {
                'valid': True,
                'safe': True,
                'warnings': structure_check.get('warnings', []),
                'normalized_sql': self._normalize_sql(sql)
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': f'验证过程出错: {str(e)}'
            }
    
    def _check_syntax(self, sql: str) -> Dict[str, Any]:
        """检查基本语法"""
        sql_upper = sql.upper().strip()
        
        #检查是否以允许的操作开头
        allowed_prefixes = ['SELECT', 'INSERT', 'UPDATE', 'WITH']
        
        if not any(sql_upper.startswith(prefix) for prefix in allowed_prefixes):
            return {
                'valid': False,
                'error': f'不允许的 SQL操作。只允许: {", ".join(allowed_prefixes)}'
            }
        
        # 检查基本结构
        if 'SELECT' in sql_upper:
            if 'FROM' not in sql_upper:
                return {
                    'valid': False,
                    'error': 'SELECT 语句必须包含 FROM子句'
                }
        
        return {'valid': True}
    
    def _check_security(self, sql: str) -> Dict[str, Any]:
        """安全检查"""
        sql_lower = sql.lower()
        
        # 检查危险操作
        for pattern in self.dangerous_operations:
            if re.search(pattern, sql_lower, re.IGNORECASE):
                return {
                    'safe': False,
                    'reason': f'检测到危险操作: {pattern}'
                }
        
        # 检查危险函数
        for pattern in self.dangerous_functions:
            if re.search(pattern, sql_lower, re.IGNORECASE):
                return {
                    'safe': False,
                    'reason': f'检测到危险函数: {pattern}'
                }
        
        # 检查注释注入
        if '--' in sql or '/*' in sql or '*/' in sql:
            return {
                'safe': False,
                'reason': '检测到 SQL 注释，可能存在注入风险'
            }
        
        # 检查多语句执行
        if ';' in sql.rstrip(';'):  #允结尾的分号
            #检查是否有多条语句
            statements = [s.strip() for s in sql.split(';') if s.strip()]
            if len(statements) > 1:
                return {
                    'safe': False,
                    'reason': '不允许执行多条 SQL 语句'
                }
        
        # 检查 UNION 注入
        if 'union' in sql_lower and 'select' in sql_lower:
            #简单检查是否是合法的 UNION
            union_parts = sql_lower.split('union')
            if len(union_parts) > 1:
                # 检查每个部分是否都有 SELECT
                for part in union_parts:
                    if 'select' not in part:
                        return {
                            'safe': False,
                            'reason': '检测到可疑的 UNION 操作'
                        }
        
        return {'safe': True}
    
    def _check_structure(self, sql: str) -> Dict[str, Any]:
        """检查 SQL 结构合理性"""
        warnings = []
        sql_lower = sql.lower()
        
        # 检查 LIMIT
        if 'select' in sql_lower and 'limit' not in sql_lower:
            warnings.append('建议添加 LIMIT子句以限制返回结果数量')
        
        # 检查 WHERE条（件（针对 UPDATE/DELETE）
        if any(op in sql_lower for op in ['update', 'delete']):
            if 'where' not in sql_lower:
                return {
                    'valid': False,
                    'error': 'UPDATE/DELETE操作必须包含 WHERE 条件'
                }
        
        # 检查表名引用
        table_references = self._extract_table_references(sql)
        if len(table_references) > 5:
            warnings.append(f'查询涉及 {len(table_references)} 个表，可能影响性能')
        
        return {
            'valid': True,
            'warnings': warnings
        }
    
    def _extract_table_references(self, sql: str) -> List[str]:
        """提取 SQL 中的表引用"""
        #简单的表名提取（FROM 和 JOIN后面的表）
        tables = []
        sql_lower = sql.lower()
        
        # FROM后的表
        from_match = re.search(r'from\s+(\w+)', sql_lower)
        if from_match:
            tables.append(from_match.group(1))
        
        # JOIN后的表
        join_matches = re.findall(r'(?:inner|left|right|full)?\s*join\s+(\w+)', sql_lower)
        tables.extend(join_matches)
        
        return list(set(tables))  #去
    
    def _normalize_sql(self, sql: str) -> str:
        """标准化 SQL 语句"""
        #移除多余空格
        normalized = re.sub(r'\s+', ' ', sql.strip())
        #统一大小写（关键字大写）
        keywords = ['SELECT', 'FROM', 'WHERE', 'ORDER BY', 'GROUP BY', 'LIMIT']
        for keyword in keywords:
            normalized = re.sub(rf'\b{keyword.lower()}\b', keyword, normalized, flags=re.IGNORECASE)
        
        return normalized
    
    def sanitize_sql(self, sql: str) -> str:
        """清理 SQL 语句（移除危险内容）"""
        #移除注释
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        
        #移除危险关键字
        dangerous_keywords = ['DROP', 'TRUNCATE', 'CREATE', 'ALTER', 'GRANT', 'REVOKE']
        for keyword in dangerous_keywords:
            sql = re.sub(rf'\b{keyword}\b', '', sql, flags=re.IGNORECASE)
        
        return sql.strip()


# 全局实例
sql_validator = SQLValidator()


def get_sql_validator() -> SQLValidator:
    """获取全局 SQL 验证器实例"""
    return sql_validator