# agents/tools/database_tool.py
"""
数据库查询工具
查询已有的 Bug、历史记录、相似 Bug等
支持 Text2SQL 自然语言查询
"""

import json
from typing import Dict, Any, List
from ..tool_registry import BaseTool

# Text2SQL
try:
    from .vanna_text2sql import get_vanna_text2sql, VANNA_AVAILABLE
    TEXT2SQL_AVAILABLE = VANNA_AVAILABLE
except ImportError:
    TEXT2SQL_AVAILABLE = False
    print("[DB_TOOL]⚠️  Vanna Text2SQL 未安装，使用传统查询模式")


class DatabaseTool(BaseTool):
    """数据库查询工具"""
    
    def __init__(self, llm, db_session):
        """
        初始化数据库工具
        
        Args:
            llm: 语言模型实例
            db_session: SQLAlchemy 数据库会话
        """
        super().__init__(
            name='database_query',
            description='查询数据库获取 Bug列表、历史记录、相似 Bug等，支持自然语言查询'
        )
        self.llm = llm
        self.db = db_session
        
        # 初始化 Text2SQL工具
        if TEXT2SQL_AVAILABLE:
            self.text2sql_tool = get_vanna_text2sql("instance/badcase_doctor.db")
            print("[DB_TOOL]✅ Vanna Text2SQL已启用")
        else:
            self.text2sql_tool = None
            print("[DB_TOOL]⚠️  Vanna Text2SQL 不可用，使用传统查询模式")
    
    async def execute(
        self,
        query_type: str = None,
        project_id: str = None,
        bug_id: str = None,
        keywords: str = None,
        plan_id: str = None,
        limit: int = 10,
        natural_query: str = None,  # 新增自然语言查询参数
        **kwargs
    ) -> Dict[str, Any]:
        """
       执行数据库查询
        
        Args:
            query_type: 查询类型 (list_bugs/find_similar/get_history/search_pattern)
            project_id: 项目 ID
            bug_id: Bug ID
            keywords:搜索关键词
            limit: 返回数量限制
            natural_query: 自然语言查询（如："查询所有未解决的登录bug"）
            **kwargs:其他参数
            
        Returns:
            查询结果
        """
        # 优先处理自然语言查询
        if natural_query and self.text2sql_tool:
            print(f"[DB_QUERY]🗣  自然语言查询: {natural_query}")
            return self._execute_natural_query(natural_query, project_id)
        
        # 传统查询逻辑
        if not query_type:
            #尝从 kwargs 中获取，兼容 LLM可能没写对参数名的情况
            query_type = kwargs.get('type') or kwargs.get('action') or kwargs.get('operation') or kwargs.get('query')
            
        if not query_type:
            # 最终兜底：如果是在 bug_management场下，可能是搜索
            if 'keyword' in kwargs or 'project_id' in kwargs:
                query_type = 'search'
            else:
                return {'error': '缺少必需参数: query_type', 'success': False}
                
        print(f"[DB_QUERY]🔎执行数据库查询: {query_type}")
        
        #支持别名
        query_type_map = {
            'similar_bugs': 'find_similar',
            'bug_history': 'get_history',
            'bug_list': 'list_bugs',
            'find_bugs': 'find_similar',
            'find_known_bugs': 'find_similar',
            'find_all': 'list_bugs',
            'find_by_name': 'search_pattern',
            'find_by_title': 'search_pattern',
            'find_by_id': 'find_similar',
            'get_by_id': 'find_similar',
            'find_by_keyword': 'search_pattern',
            'search_by_keyword': 'search_pattern',
            'keyword_search': 'search_pattern',
            'search_bugs': 'search_pattern',
            'search': 'search_pattern',
            'list': 'list_bugs',
            'history': 'get_history'
        }
        query_type = query_type_map.get(query_type, query_type)
        
        # 使用Flask app context包装数据库操作
        from app import app
        with app.app_context():
            if query_type == 'list_bugs':
                return await self._list_bugs(project_id, plan_id, limit, **kwargs)
            elif query_type == 'find_similar':
                return await self._find_similar(bug_id, keywords, limit, **kwargs)
            elif query_type == 'get_history':
                return await self._get_history(project_id, limit, **kwargs)
            elif query_type == 'search_pattern':
                return await self._search_pattern(keywords, limit, **kwargs)
            else:
                return {'error': f'未知查询类型: {query_type}，支持的类型: list_bugs, find_similar, get_history, search_pattern', 'success': False}
    
    def _execute_natural_query(self, natural_query: str, project_id: str = None) -> Dict[str, Any]:
        """
       执行自然语言查询
        
        Args:
            natural_query: 自然语言查询语句
            project_id: 项目ID（可选上下文）
            
        Returns:
            查询结果
        """
        try:
            # 添加上下文信息
            context = {}
            if project_id:
                context['project_id'] = project_id
            
            #调用 Text2SQL工具
            result = self.text2sql_tool.query(natural_query, context)
            
            if result['success']:
                return {
                    'query_type': 'natural_language',
                    'natural_query': natural_query,
                    'generated_sql': result['generated_sql'],
                    'explanation': result['explanation'],
                    'results': result['results'],
                    'row_count': result['row_count'],
                    'execution_time': result['execution_time'],
                    'success': True
                }
            else:
                return {
                    'error': result['error'],
                    'natural_query': natural_query,
                    'success': False
                }
                
        except Exception as e:
            print(f"[DB_QUERY]❌ 自然语言查询失败: {str(e)}")
            return {
                'error': f'自然语言查询执行失败: {str(e)}',
                'natural_query': natural_query,
                'success': False
            }
    
    async def execute(
        self,
        query_type: str = None,
        project_id: str = None,
        bug_id: str = None,
        keywords: str = None,
        plan_id: str = None,  # 增加plan_id参数
        limit: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行数据库查询
        
        Args:
            query_type: 查询类型 (list_bugs/find_similar/get_history/search_pattern)
            project_id: 项目 ID
            bug_id: Bug ID
            keywords: 搜索关键词
            limit: 返回数量限制
            **kwargs: 其他参数
            
        Returns:
            查询结果
        """
        if not query_type:
            # 尝试从 kwargs 中获取，兼容 LLM 可能没写对参数名的情况
            query_type = kwargs.get('type') or kwargs.get('action') or kwargs.get('operation') or kwargs.get('query')
            
        if not query_type:
            # 最终兜底：如果是在 bug_management 场景下，可能是搜索
            if 'keyword' in kwargs or 'project_id' in kwargs:
                query_type = 'search'
            else:
                return {'error': '缺少必需参数: query_type', 'success': False}
            
        print(f"[DB_QUERY] 🔎 执行数据库查询: {query_type}")
        
        # 支持别名
        query_type_map = {
            'similar_bugs': 'find_similar',
            'bug_history': 'get_history',
            'bug_list': 'list_bugs',
            'find_bugs': 'find_similar',
            'find_known_bugs': 'find_similar',
            'find_all': 'list_bugs',
            'find_by_name': 'search_pattern',
            'find_by_title': 'search_pattern',
            'find_by_id': 'find_similar',
            'get_by_id': 'find_similar',
            'find_by_keyword': 'search_pattern',
            'search_by_keyword': 'search_pattern',
            'keyword_search': 'search_pattern',
            'search_bugs': 'search_pattern',
            'search': 'search_pattern',
            'list': 'list_bugs',
            'history': 'get_history'
        }
        query_type = query_type_map.get(query_type, query_type)
        
        # 使用Flask app context包装数据库操作
        from app import app
        with app.app_context():
            if query_type == 'list_bugs':
                return await self._list_bugs(project_id, plan_id, limit, **kwargs)
            elif query_type == 'find_similar':
                return await self._find_similar(bug_id, keywords, limit, **kwargs)
            elif query_type == 'get_history':
                return await self._get_history(project_id, limit, **kwargs)
            elif query_type == 'search_pattern':
                return await self._search_pattern(keywords, limit, **kwargs)
            else:
                return {'error': f'未知查询类型: {query_type}，支持的类型: list_bugs, find_similar, get_history, search_pattern', 'success': False}
    
    async def _list_bugs(self, project_id: str = None, plan_id: str = None, limit: int = 10, **kwargs) -> Dict[str, Any]:
        """获取 Bug 列表"""
        print(f"[DB_QUERY] 📋 列举Bug（项目: {project_id or 'all'}, 计划: {plan_id or 'all'}, 限制: {limit}）")
            
        try:
            # 动态导入模型避免循环导入
            from app import db, Bug, Project
                
            query = db.session.query(Bug)
                
            if project_id:
                query = query.filter_by(project_id=project_id)
                
            if plan_id:
                query = query.filter_by(plan_id=plan_id)
                
            bugs = query.order_by(Bug.created_at.desc()).limit(limit).all()
                
            bugs_data = []
            for bug in bugs:
                bugs_data.append({
                    'id': bug.id,
                    'title': bug.title,
                    'description': bug.description,
                    'severity': bug.severity,
                    'status': bug.status,
                    'project_id': bug.project_id,
                    'plan_id': bug.plan_id,
                    'created_at': bug.created_at.isoformat() if bug.created_at else None
                })
                
            return {
                'query_type': 'list_bugs',
                'total': len(bugs_data),
                'bugs': bugs_data,
                'success': True
            }
        
        except Exception as e:
            print(f"[DB_QUERY] ❌ 查询失败: {str(e)}")
            return {
                'error': str(e),
                'success': False
            }
    
    async def _find_similar(self, bug_id: str = None, keywords: str = None, limit: int = 5, **kwargs) -> Dict[str, Any]:
        """查找相似 Bug"""
        project_id = kwargs.get('project_id')
        plan_id = kwargs.get('plan_id')
        print(f"[DB_QUERY] 🔍 查找相似Bug (bug_id={bug_id}, keywords={keywords}, project_id={project_id}, plan_id={plan_id})")
            
        try:
            from app import db, Bug, Plan
                
            # 尝试多种方式获取关键词
            if bug_id:
                # 根据 bug_id 查找
                original_bug = db.session.query(Bug).filter_by(id=bug_id).first()
                if not original_bug:
                    return {'error': f'Bug {bug_id} 不存在', 'success': False}
                keywords = original_bug.title
                
            # 如果仍然没有keywords，尝试从上下文提取
            if not keywords:
                url = kwargs.get('url', '')
                if 'login' in url.lower():
                    keywords = '登录'
                elif 'project-detail' in url.lower():
                    keywords = '项目 界面'
                elif 'bug' in url.lower():
                    keywords = 'bug 编辑'
                else:
                    keywords = '界面'  # 默认关键词
                print(f"[DB_QUERY] 🧐 从 URL 自动提取关键词: {keywords}")
                
            if not keywords:
                return {
                    'error': '查找相似Bug需要提供 keywords 参数或 bug_id 参数',
                    'success': False,
                    'hint': '例: {"query_type": "find_similar", "keywords": "登录失败"} 或 {"query_type": "find_similar", "bug_id": "123"}'
                }
            
            # 简单的关键词匹配
            query = db.session.query(Bug).filter(
                Bug.title.ilike(f'%{keywords}%')
            )
            
            # 添加project_id过滤
            if project_id:
                query = query.filter_by(project_id=project_id)
                
                # 如果没有指定plan_id，查询项目下所有bug类型计划的Bug
                if not plan_id:
                    bug_type_plans = db.session.query(Plan).filter_by(
                        project_id=project_id,
                        type='bug'
                    ).all()
                    if bug_type_plans:
                        bug_plan_ids = [p.id for p in bug_type_plans]
                        query = query.filter(Bug.plan_id.in_(bug_plan_ids))
            
            # 处理plan_id：查询相同parent_id的所有同级计划下的Bug
            if plan_id:
                # 获取当前计划信息
                current_plan = db.session.query(Plan).filter_by(id=plan_id).first()
                if current_plan and current_plan.parent_id:
                    # 获取所有同级计划（相同parent_id）
                    sibling_plans = db.session.query(Plan).filter_by(parent_id=current_plan.parent_id).all()
                    sibling_plan_ids = [p.id for p in sibling_plans]
                    query = query.filter(Bug.plan_id.in_(sibling_plan_ids))
                else:
                    # 如果没有parent_id，只查询当前计划
                    query = query.filter_by(plan_id=plan_id)
            
            similar_bugs = query.limit(limit).all()
            
            bugs_data = [
                {
                    'id': bug.id,
                    'title': bug.title,
                    'severity': bug.severity,
                    'status': bug.status
                }
                for bug in similar_bugs
            ]
            
            return {
                'query_type': 'find_similar',
                'original_keywords': keywords,
                'similar_count': len(bugs_data),
                'bugs': bugs_data,
                'success': True
            }
        
        except Exception as e:
            print(f"[DB_QUERY] ❌ 查询失败: {str(e)}")
            return {'error': str(e), 'success': False}
    
    async def _get_history(self, project_id: str = None, limit: int = 10) -> Dict[str, Any]:
        """获取测试历史"""
        print(f"[DB_QUERY] 📊 获取测试历史")
        
        try:
            from app import db, Bug
            
            query = db.session.query(Bug)
            
            if project_id:
                query = query.filter_by(project_id=project_id)
            
            # 按严重程度分组统计
            bugs = query.all()
            
            severity_stats = {
                'critical': 0,
                'high': 0,
                'medium': 0,
                'low': 0
            }
            
            status_stats = {
                'pending_review': 0,
                'confirmed': 0,
                'in_progress': 0,
                'resolved': 0
            }
            
            for bug in bugs:
                severity = bug.severity or 'medium'
                severity_stats[severity] = severity_stats.get(severity, 0) + 1
                
                status = bug.status or 'pending_review'
                status_stats[status] = status_stats.get(status, 0) + 1
            
            return {
                'query_type': 'get_history',
                'total_bugs': len(bugs),
                'severity_distribution': severity_stats,
                'status_distribution': status_stats,
                'success': True
            }
        
        except Exception as e:
            print(f"[DB_QUERY] ❌ 查询失败: {str(e)}")
            return {'error': str(e), 'success': False}
    
    async def _search_pattern(self, keywords: str = None, limit: int = 10, name: str = None, title: str = None, **kwargs) -> Dict[str, Any]:
        """按模式搜索 Bug"""
        # 支持多种参数名
        search_term = keywords or name or title or kwargs.get('query', '')
        print(f"[DB_QUERY] 🔎 按模式搜索: {search_term}")
        
        try:
            from app import db, Bug
            
            bugs = db.session.query(Bug).filter(
                (Bug.title.ilike(f'%{search_term}%')) |
                (Bug.description.ilike(f'%{search_term}%'))
            ).limit(limit).all()
            
            bugs_data = [
                {
                    'id': bug.id,
                    'title': bug.title,
                    'description': bug.description[:100] if bug.description else '',
                    'severity': bug.severity
                }
                for bug in bugs
            ]
            
            return {
                'query_type': 'search_pattern',
                'keywords': keywords,
                'results_count': len(bugs_data),
                'bugs': bugs_data,
                'success': True
            }
        
        except Exception as e:
            print(f"[DB_QUERY] ❌ 查询失败: {str(e)}")
            return {'error': str(e), 'success': False}
