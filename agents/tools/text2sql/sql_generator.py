"""
Text2SQL SQL生成器
使用简单的规则匹配将自然语言转换为 SQL
"""

import re
from typing import Dict, Any, List, Optional
from .schema_manager import get_schema_manager


class SQLGenerator:
    """SQL生成器"""
    
    def __init__(self, database_path: str = "instance/badcase_doctor.db"):
        self.schema_manager = get_schema_manager(database_path)
        self._init_patterns()
    
    def _init_patterns(self):
        """初始化匹配模式"""
        # 查询相关关键词
        self.query_patterns = [
            (r'查询.*?(\w+).*?信息|查询.*?(\w+).*?详情|搜索.*?(\w+)', 'select'),
            (r'列出.*?(\w+)|显示.*?(\w+).*?列表|所有.*?(\w+)', 'select_all'),
            (r'统计.*?(\w+).*?数量|有多少.*?(\w+)', 'count'),
        ]
        
        #表名映射（自然语言 -> 表名）
        self.table_mappings = {
            '缺陷': 'defects',
            '缺陷信息': 'defects',
            'bug': 'defects',
            'bugs': 'defects',
            '问题': 'defects',
            'badcase': 'bad_cases',
            '坏案例': 'bad_cases',
            '测试用例': 'test_cases',
            '测试集': 'test_suites',
            '用例': 'test_cases'
        }
        
        #常见字段映射
        self.column_mappings = {
            '状态': 'status',
            '优先级': 'priority',
            '负责人': 'assignee',
            '标题': 'title',
            '描述': 'description',
            '创建时间': 'created_at'
        }
    
    def generate_sql(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        生成 SQL语句
        
        Args:
            query: 自然语言查询
            context: 上下文信息
            
        Returns:
            生成结果
        """
        try:
            # 1. 识别意图
            intent = self._identify_intent(query)
            if not intent['success']:
                return intent
            
            # 2.匹表名
            table_name = self._match_table_name(query)
            if not table_name:
                return {
                    'success': False,
                    'error': '无法识别要查询的表',
                    'table_used': None
                }
            
            # 3.生成对应SQL
            if intent['type'] == 'select':
                sql_result = self._generate_select_sql(query, table_name)
            elif intent['type'] == 'select_all':
                sql_result = self._generate_select_all_sql(table_name)
            elif intent['type'] == 'count':
                sql_result = self._generate_count_sql(query, table_name)
            elif intent['type'] == 'update':
                sql_result = self._generate_update_sql(query, table_name)
            else:
                sql_result = self._generate_basic_select_sql(table_name)
            
            if not sql_result['success']:
                return sql_result
            
            # 4. 添加解释
            explanation = self._generate_explanation(query, intent, table_name)
            
            return {
                'success': True,
                'sql': sql_result['sql'],
                'explanation': explanation,
                'table_used': table_name,
                'confidence': intent['confidence'],
                'intent': intent['type']
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'SQL生成失败: {str(e)}',
                'sql': None
            }
    
    def _identify_intent(self, query: str) -> Dict[str, Any]:
        """识别查询意图"""
        query_lower = query.lower()
            
        # 检查更新关键词（优先级最高）
        if any(keyword in query_lower for keyword in ['更新', '修改', '改', 'update', 'set', '改为']):
            return {'success': True, 'type': 'update', 'confidence': 0.95}
            
        # 检查查询关键词
        if any(keyword in query_lower for keyword in ['查询', '搜索', '查找', 'search', 'find']):
            return {'success': True, 'type': 'select', 'confidence': 0.9}
            
        # 检查列表关键词
        if any(keyword in query_lower for keyword in ['列出', '显示', '所有', 'list', 'show', 'all']):
            return {'success': True, 'type': 'select_all', 'confidence': 0.8}
            
        # 检查统计关键词
        if any(keyword in query_lower for keyword in ['统计', '数量', '多少', 'count', 'total']):
            return {'success': True, 'type': 'count', 'confidence': 0.85}
            
        # 默认为基本查询
        return {'success': True, 'type': 'select', 'confidence': 0.7}
    
    def _match_table_name(self, query: str) -> Optional[str]:
        """匹配表名"""
        query_lower = query.lower()
        
        #直接匹配表名
        schema_info = self.schema_manager.get_schema_info()
        table_names = [table['name'] for table in schema_info['tables']]
        
        for table_name in table_names:
            if table_name in query_lower:
                return table_name
        
        # 通过映射匹配
        for natural_name, table_name in self.table_mappings.items():
            if natural_name in query:
                if table_name in table_names:
                    return table_name
        
        # 默认返回第一个表
        return table_names[0] if table_names else None
    
    def _generate_select_sql(self, query: str, table_name: str) -> Dict[str, Any]:
        """生成 SELECT 查询 SQL"""
        # 提取关键词
        keywords = self._extract_keywords(query)
        
        if keywords:
            #构建 WHERE 条件
            where_conditions = []
            for keyword in keywords:
                #的模糊匹配
                where_conditions.append(f"title LIKE '%{keyword}%' OR description LIKE '%{keyword}%'")
            
            where_clause = " WHERE " + " OR ".join(where_conditions)
            sql = f"SELECT * FROM {table_name}{where_clause} LIMIT 50"
        else:
            sql = f"SELECT * FROM {table_name} LIMIT 50"
        
        return {'success': True, 'sql': sql}
    
    def _generate_select_all_sql(self, table_name: str) -> Dict[str, Any]:
        """生成查询所有记录的 SQL"""
        sql = f"SELECT * FROM {table_name} LIMIT 100"
        return {'success': True, 'sql': sql}
    
    def _generate_count_sql(self, query: str, table_name: str) -> Dict[str, Any]:
        """生成统计数量的 SQL"""
        # 检查是否有条件
        keywords = self._extract_keywords(query)
        
        if keywords:
            where_conditions = []
            for keyword in keywords:
                where_conditions.append(f"title LIKE '%{keyword}%' OR description LIKE '%{keyword}%'")
            
            where_clause = " WHERE " + " OR ".join(where_conditions)
            sql = f"SELECT COUNT(*) as count FROM {table_name}{where_clause}"
        else:
            sql = f"SELECT COUNT(*) as count FROM {table_name}"
        
        return {'success': True, 'sql': sql}
    
    def _generate_update_sql(self, query: str, table_name: str) -> Dict[str, Any]:
        """
        生成 UPDATE SQL
        
        输入示例: "更新bug表中ID为3的记录，将assignee_id改为33"
        输出示例: "UPDATE bug SET assignee_id = 33 WHERE id = 3"
        """
        import re
        
        try:
            # 提取 WHERE 条件（ID）
            id_match = re.search(r'ID[为等于:]\s*(\d+)', query, re.IGNORECASE)
            record_id = id_match.group(1) if id_match else None
            
            if not record_id:
                # 尝试其他ID提取模式
                id_match = re.search(r'id\s*[=为]\s*(\d+)', query, re.IGNORECASE)
                record_id = id_match.group(1) if id_match else None
            
            # 提取 SET 子句
            # 模式："字段名改为值" 或 "将字段名改为值"
            set_matches = re.findall(r'(\w+)\s*改为\s*[\'"]?([^，。、\s\'"]+)[\'"]?', query)
            
            if not set_matches:
                # 尝试其他模式
                set_matches = re.findall(r'(\w+)\s*[=设置]\s*[\'"]?([^，。、\s\'"]+)[\'"]?', query)
            
            if not record_id or not set_matches:
                return {
                    'success': False,
                    'error': f'无法解析UPDATE语句，ID={record_id}, SET={set_matches}',
                    'sql': None
                }
            
            # 构建 SET 子句
            set_clauses = []
            for field, value in set_matches:
                # 判断值类型
                try:
                    # 尝试解析为数字
                    num_value = int(value)
                    set_clauses.append(f"{field} = {num_value}")
                except ValueError:
                    # 字符串值
                    set_clauses.append(f"{field} = '{value}'")
            
            set_clause = ", ".join(set_clauses)
            
            # 构建 UPDATE SQL
            sql = f"UPDATE {table_name} SET {set_clause} WHERE id = {record_id}"
            
            print(f"[SQL-GEN] 生成 UPDATE SQL: {sql}")
            
            return {
                'success': True,
                'sql': sql,
                'table': table_name,
                'record_id': record_id,
                'changes': dict(set_matches)
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'UPDATE SQL生成失败: {str(e)}',
                'sql': None
            }
    
    def _generate_basic_select_sql(self, table_name: str) -> Dict[str, Any]:
        """生成基本 SELECT SQL"""
        sql = f"SELECT * FROM {table_name} LIMIT 20"
        return {'success': True, 'sql': sql}
    
    def _extract_keywords(self, query: str) -> List[str]:
        """从查询中提取关键词"""
        #移除常见停用词
        stop_words = ['查询', '搜索', '查找', '显示', '列出', '所有', '的', '信息', '详情']
        keywords = []
        
        #简单的中文分词（按字符分割）
        for char in query:
            if char.isalnum() and char not in stop_words and len(char) > 1:
                keywords.append(char)
        
        # 如果没提取到，使用整个查询（除去停用词）
        if not keywords:
            #移除停用词后的剩余文本
            clean_query = query
            for stop_word in stop_words:
                clean_query = clean_query.replace(stop_word, '')
            if clean_query.strip():
                keywords = [clean_query.strip()]
        
        return keywords[:3]  # 最多返回3个关键词
    
    def _generate_explanation(self, query: str, intent: Dict[str, Any], table_name: str) -> str:
        """生成解释说明"""
        intent_desc = {
            'select': '查询符合条件的记录',
            'select_all': '查询所有记录',
            'count': '统计记录数量',
            'update': '更新记录'
        }
        
        intent_text = intent_desc.get(intent['type'], '执行查询')
        return f"将自然语言查询 '{query}'为 {intent_text}，目标表为 {table_name}"


#全局实例
sql_generator = None

def get_sql_generator(database_path: str = "instance/badcase_doctor.db"):
    """获取全局 SQL生成器实例"""
    global sql_generator
    if sql_generator is None:
        sql_generator = SQLGenerator(database_path)
    return sql_generator